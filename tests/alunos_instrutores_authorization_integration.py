"""TH-34: authorization of eight real HTTP routes, without changing policy.

The database, configuration, log and server are isolated under build/. Adversarial
requests and revoked actors provide security proofs without mutating production
sources or replacing the existing C++ authorization matrix.
"""

from contextlib import closing
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "TH24-test-password"
MISSING = 999999999


def routes(aluno=500, instrutor=600, aluno_user=202, instrutor_user=204):
    return [
        ("alunos.list", "GET", "/api/alunos", None),
        ("alunos.detail", "GET", f"/api/alunos/{aluno}", None),
        ("alunos.create", "POST", "/api/alunos", {"usuario_id": aluno_user}),
        ("instrutores.list", "GET", "/api/instrutores", None),
        ("instrutores.detail", "GET", f"/api/instrutores/{instrutor}", None),
        ("instrutores.create", "POST", "/api/instrutores", {"usuario_id": instrutor_user}),
        ("vinculo.read", "GET", f"/api/alunos/{aluno}/instrutor", None),
        ("vinculo.manage", "PUT", f"/api/alunos/{aluno}/instrutor", {"instrutor_id": instrutor}),
    ]


def malicious_inputs(path, body, tenant):
    for field in ("academia_id", "academiaId"):
        yield path + f"?{field}={tenant}", body
        yield path, (body or {}) | {field: tenant}


def run():
    development = ROOT / "data/traininghub.db"
    before = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    encoded = subprocess.check_output([str(ROOT / "build/security-tests/security_tests.exe"),
                                       "--fixture-hash"], env=env, text=True).strip()
    checked = 0
    rejected = 0
    covered = {}

    def safe(content):
        assert not any(secret in content for secret in
                       (PASSWORD.encode(), encoded.encode(), b'"senha"', b'"senha_hash"', b"$argon2id$")), "Credential exposed"

    try:
        with tempfile.TemporaryDirectory(prefix="th34-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "authorization.db"

            def sql(statement, values=()):
                # Only this disposable fixture may simulate out-of-band revocation.
                with closing(sqlite3.connect(database, timeout=10)) as db:
                    result = db.execute(statement, values).fetchall()
                    db.commit()
                    return result

            with closing(sqlite3.connect(database)) as db:
                db.executescript((ROOT / "migrations/001_initial_schema.sql").read_text(encoding="utf-8"))
                profile_ids = {"Aluno": 1, "Administrador": 4294967297, "Gestor": 1099511627793,
                               "Instrutor": 37, "Administrador ": 73}
                db.executemany("INSERT INTO perfil(id,nome) VALUES(?,?)",
                               [(identity, name) for name, identity in profile_ids.items()])
                for migration in sorted((ROOT / "migrations").glob("*.sql")):
                    if migration.name != "001_initial_schema.sql":
                        db.executescript(migration.read_text(encoding="utf-8"))
                roles = dict(db.execute("SELECT nome,id FROM perfil"))
                assert roles == profile_ids, "Canonical seed changed arbitrary profile IDs"
                db.executemany("INSERT INTO academia(id,nome) VALUES(?,?)", [(1, "A"), (2, "B")])
                fixtures = [(100, "Administrador", 1), (101, "Gestor", 1), (102, "Instrutor", 1),
                            (103, "Aluno", 1), (104, "Administrador ", 1),
                            (110, "Administrador", 2), (111, "Gestor", 2),
                            (200, "Aluno", 1), (201, "Instrutor", 1), (202, "Aluno", 1),
                            (203, "Aluno", 1), (204, "Instrutor", 1), (205, "Instrutor", 1),
                            (206, "Instrutor", 1), (300, "Aluno", 2), (301, "Instrutor", 2)]
                identities = {identity: (roles[role], tenant) for identity, role, tenant in fixtures}
                for identity, role, tenant in fixtures:
                    db.execute("INSERT INTO usuario(id,academia_id,perfil_id,nome,email,senha_hash) "
                               "VALUES(?,?,?,'TH34',?,?)",
                               (identity, tenant, roles[role], f"u{identity}@example.test", encoded))
                db.executemany("INSERT INTO aluno(id,usuario_id) VALUES(?,?)",
                               [(500, 200), (503, 103), (700, 300)])
                db.executemany("INSERT INTO instrutor(id,usuario_id) VALUES(?,?)",
                               [(600, 201), (601, 206), (602, 102), (800, 301)])
                db.commit()

            def snapshot():
                return (sql("SELECT * FROM aluno ORDER BY id"),
                        sql("SELECT * FROM instrutor ORDER BY id"),
                        sql("SELECT id,academia_id,perfil_id,ativo FROM usuario ORDER BY id"))

            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
            config["listeners"] = [{"address": "127.0.0.1", "port": port}]
            config["db_clients"][0]["filename"] = database.as_posix()
            config["db_clients"][0]["connection_number"] = 3
            (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
            anonymous = urllib.request.build_opener()

            def request(client, method, path, body=None, expected=200):
                nonlocal checked, rejected
                previous = snapshot() if expected >= 400 else None
                data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(base + path, method=method, data=data,
                                             headers={"Content-Type": "application/json"})
                try:
                    response = client.open(req, timeout=20)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read()
                    safe(content)
                    assert response.code == expected, (method, path, response.code, expected)
                    assert "application/json" in response.headers.get("Content-Type", "")
                    payload = json.loads(content)
                    if expected >= 400:
                        assert set(payload) in ({"erro"}, {"message"})
                        assert not any(token in content.lower() for token in
                                       (b"select ", b"insert ", b"update ", b"sqlite", b"constraint", b"traceback")), "Internal detail exposed"
                        assert snapshot() == previous, "Denied request changed domain records or user identity"
                        rejected += 1
                    checked += 1
                    return payload

            def login(identity, tenant=1):
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                context = request(client, "POST", "/api/auth/login", {"academia_id": tenant,
                    "email": f"u{identity}@example.test", "senha": PASSWORD})
                assert context == {"userId": identity, "academiaId": tenant, "perfilId": identities[identity][0]}
                return client

            def denied_matrix(label, clients, endpoints, status):
                covered[label] = set()
                for client, (name, method, path, body) in zip(clients, endpoints, strict=True):
                    request(client, method, path, body, status)
                    for malicious_path, malicious_body in malicious_inputs(path, body, 2):
                        request(client, method, malicious_path, malicious_body, status)
                    # Even invalid JSON must not turn an authentication/permission denial into 400.
                    request(client, method, path, b"{", status)
                    covered[label].add(name)

            def allowed_matrix(label, client, endpoints, tenant=1):
                covered[label] = set()
                for name, method, path, body in endpoints:
                    payload = request(client, method, path, body, 201 if method == "POST" else 200)
                    if name.endswith(".list"):
                        table, alias = ("aluno", "al") if name.startswith("alunos.") else ("instrutor", "i")
                        expected = sql(f"SELECT {alias}.id,{alias}.usuario_id FROM {table} {alias} "
                                       f"JOIN usuario u ON u.id={alias}.usuario_id WHERE u.academia_id=? ORDER BY {alias}.id", (tenant,))
                        assert [(item["id"], item["usuario_id"]) for item in payload] == expected, "Tenant listing leaked or omitted records"
                    elif name.startswith("vinculo."):
                        aluno_id = int(path.split("/")[3])
                        assert payload == {"instrutor_id": sql("SELECT instrutor_id FROM aluno WHERE id=?", (aluno_id,))[0][0]}
                        if method == "PUT":
                            assert payload["instrutor_id"] == body["instrutor_id"]
                    else:
                        table = "aluno" if name.startswith("alunos.") else "instrutor"
                        assert set(payload) == {"id", "usuario_id", "criado_em"}
                        assert sql(f"SELECT usuario_id FROM {table} WHERE id=?", (payload["id"],)) == [(payload["usuario_id"],)]
                        if method == "POST":
                            assert payload["usuario_id"] == body["usuario_id"]
                        else:
                            assert payload["id"] == int(path.rsplit("/", 1)[1])
                        assert sql("SELECT academia_id FROM usuario WHERE id=?", (payload["usuario_id"],)) == [(tenant,)]
                    covered[label].add(name)

            with (directory / "server.log").open("w+b") as log:
                server = None
                primary_error = None

                def start():
                    process = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory, env=env,
                        stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    return process

                def ready():
                    for _ in range(100):
                        try:
                            request(anonymous, "GET", "/api/health")
                            return
                        except urllib.error.URLError:
                            if server.poll() is not None:
                                raise RuntimeError("Isolated TH-34 server failed to start")
                            time.sleep(0.1)
                    raise RuntimeError("Isolated TH-34 server startup timed out")

                def stop():
                    if server is None:
                        return
                    if server.poll() is None:
                        server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)

                try:
                    server = start()
                    ready()
                    denied_matrix("anonymous", [anonymous] * 8, routes(), 401)
                    forged = urllib.request.build_opener()
                    forged.addheaders = [("Cookie", "JSESSIONID=TH34-forged-session")]
                    denied_matrix("forged", [forged] * 8, routes(), 401)
                    for identity, label, endpoints in [
                        (102, "instrutor", routes(instrutor=602)),
                        (103, "aluno", routes(aluno=503)),
                        (104, "unknown", routes()),
                    ]:
                        denied_matrix(label, [login(identity)] * 8, endpoints, 403)

                    # Both own-resource IDs above exist and belong to the denied actors.
                    assert sql("SELECT usuario_id FROM aluno WHERE id=503") == [(103,)]
                    assert sql("SELECT usuario_id FROM instrutor WHERE id=602") == [(102,)]
                    admins = [(login(100), 1), (login(101), 1), (login(110, 2), 2), (login(111, 2), 2)]
                    allowed_matrix("admin", admins[0][0], routes())
                    allowed_matrix("gestor", admins[1][0], routes(instrutor=601, aluno_user=203, instrutor_user=205))

                    for client, tenant in admins:
                        endpoints = routes() if tenant == 1 else routes(aluno=700, instrutor=800)
                        external = 2 if tenant == 1 else 1
                        # List content, not merely status 200, proves tenant isolation in both directions.
                        for name, method, path, body in endpoints:
                            if name.endswith(".list"):
                                values = request(client, method, path)
                                table = "aluno" if name.startswith("alunos.") else "instrutor"
                                own = sql(f"SELECT r.id FROM {table} r JOIN usuario u ON u.id=r.usuario_id "
                                          "WHERE u.academia_id=? ORDER BY r.id", (tenant,))
                                assert [item["id"] for item in values] == [row[0] for row in own]
                            for malicious_path, malicious_body in malicious_inputs(path, body, external):
                                request(client, method, malicious_path, malicious_body, 400)

                        own_aluno, own_instrutor = (500, 600) if tenant == 1 else (700, 800)
                        foreign_aluno, foreign_instrutor, foreign_user_aluno, foreign_user_instrutor = (
                            (700, 800, 300, 301) if tenant == 1 else (500, 600, 200, 201))
                        unavailable = [
                            ("GET", f"/api/alunos/{foreign_aluno}", None, f"/api/alunos/{MISSING}", None),
                            ("GET", f"/api/instrutores/{foreign_instrutor}", None, f"/api/instrutores/{MISSING}", None),
                            ("POST", "/api/alunos", {"usuario_id": foreign_user_aluno}, "/api/alunos", {"usuario_id": MISSING}),
                            ("POST", "/api/instrutores", {"usuario_id": foreign_user_instrutor}, "/api/instrutores", {"usuario_id": MISSING}),
                            ("GET", f"/api/alunos/{foreign_aluno}/instrutor", None, f"/api/alunos/{MISSING}/instrutor", None),
                            ("PUT", f"/api/alunos/{foreign_aluno}/instrutor", {"instrutor_id": own_instrutor},
                             f"/api/alunos/{MISSING}/instrutor", {"instrutor_id": own_instrutor}),
                            ("PUT", f"/api/alunos/{own_aluno}/instrutor", {"instrutor_id": foreign_instrutor},
                             f"/api/alunos/{own_aluno}/instrutor", {"instrutor_id": MISSING}),
                        ]
                        for method, path, body, missing_path, missing_body in unavailable:
                            hidden = request(client, method, path, body, 404)
                            absent = request(client, method, missing_path, missing_body, 404)
                            assert hidden == absent, "Cross-tenant error enumerates resources"

                    for client, aluno_user, instrutor_user in [(admins[0][0], 202, 204), (admins[1][0], 203, 205)]:
                        request(client, "POST", "/api/alunos", {"usuario_id": aluno_user}, 409)
                        request(client, "POST", "/api/instrutores", {"usuario_id": instrutor_user}, 409)
                        request(client, "POST", "/api/alunos", {"usuario_id": 201}, 400)
                        request(client, "POST", "/api/instrutores", {"usuario_id": 200}, 400)

                    gestor_profile = roles["Gestor"]
                    revocations = [
                        ("changed_profile_id", "UPDATE usuario SET perfil_id=? WHERE id=101", (roles["Aluno"],),
                         "UPDATE usuario SET perfil_id=? WHERE id=101", (gestor_profile,), 401),
                        ("inactive_profile", "UPDATE perfil SET ativo=0 WHERE id=?", (gestor_profile,),
                         "UPDATE perfil SET ativo=1 WHERE id=?", (gestor_profile,), 403),
                        ("inactive_user", "UPDATE usuario SET ativo=0 WHERE id=101", (),
                         "UPDATE usuario SET ativo=1 WHERE id=101", (), 401),
                        ("inactive_academia", "UPDATE academia SET ativo=0 WHERE id=1", (),
                         "UPDATE academia SET ativo=1 WHERE id=1", (), 401),
                        ("changed_profile_name", "UPDATE perfil SET nome='TH34 revogado' WHERE id=?", (gestor_profile,),
                         "UPDATE perfil SET nome='Gestor' WHERE id=?", (gestor_profile,), 403),
                    ]
                    for label, statement, values, restore, restored, status in revocations:
                        # A separate session per endpoint prevents the first 401/logout from
                        # masking missing revalidation on the other seven endpoints.
                        clients = [login(101) for _ in routes()]
                        sql(statement, values)
                        try:
                            denied_matrix(label, clients, routes(), status)
                        finally:
                            sql(restore, restored)

                    clients = [login(101) for _ in routes()]
                    for client in clients:
                        request(client, "POST", "/api/auth/logout")
                    denied_matrix("logout", clients, routes(), 401)

                    # Only the expiration phase uses short sessions; normal Argon2/matrix
                    # checks must not expire actors on slower CI workers.
                    stop()
                    config["app"]["session_timeout"] = 2
                    (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
                    server = start()
                    ready()
                    clients = [login(101) for _ in routes()]
                    time.sleep(4)
                    denied_matrix("expired", clients, routes(), 401)

                    expected_routes = {name for name, _, _, _ in routes()}
                    expected_groups = {"anonymous", "forged", "admin", "gestor", "instrutor", "aluno", "unknown",
                                       "changed_profile_id", "inactive_profile", "inactive_user", "inactive_academia",
                                       "changed_profile_name", "logout", "expired"}
                    assert set(covered) == expected_groups
                    assert all(names == expected_routes for names in covered.values()), "Incomplete eight-route matrix"
                except BaseException as error:
                    primary_error = error
                    raise
                finally:
                    try:
                        stop()
                        log.seek(0)
                        safe(log.read())
                    except Exception:
                        if primary_error is None:
                            raise
    finally:
        after = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
        assert before == after, "Development database changed"
    print(f"TH-34 passed: {checked} HTTP checks; {len(covered)} complete eight-route matrices; "
          f"{rejected} rejected requests with unchanged domain/identity snapshots; arbitrary profile IDs, "
          "self-access denied, bidirectional tenant isolation/non-enumeration, snake/camel injection, "
          "per-route revocation, logout and expiry. Production sources and development DB unchanged.")


if __name__ == "__main__":
    run()
