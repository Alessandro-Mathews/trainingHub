"""TH-36: real HTTP sessions and SQLite persistence, isolated from development data."""

from concurrent.futures import ThreadPoolExecutor
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
import threading
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "TH24-test-password"
LARGE = 2**40
MAXIMUM = 2**63 - 1
FIELDS = {"id", "academia_id", "nome", "descricao", "valor_centavos", "duracao_dias", "ativo", "criado_em"}
VALID = {"nome": "Mensal", "descricao": "Plano mensal da academia", "valor_centavos": 9990, "duracao_dias": 30}


def run():
    development = ROOT / "data/traininghub.db"
    before = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    checked = 0
    try:
        encoded = subprocess.check_output([str(ROOT / "build/security-tests/security_tests.exe"),
                                           "--fixture-hash"], env=env, text=True).strip()

        def safe(content, internal=False):
            assert not any(secret in content for secret in
                           (PASSWORD.encode(), encoded.encode(), b'"senha"', b'"senha_hash"', b"$argon2id$")), "Credential exposed"
            if internal:
                assert not any(token in content.lower() for token in
                    (b"select ", b"insert ", b"update ", b"sqlite", b"constraint", b"schema", b"traceback", b".db", b"c:\\")), "Internal detail exposed"

        with tempfile.TemporaryDirectory(prefix="th36-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "plano.db"

            def sql(statement, values=()):
                with closing(sqlite3.connect(database, timeout=10)) as db:
                    rows = db.execute(statement, values).fetchall()
                    db.commit()
                    return rows

            with closing(sqlite3.connect(database)) as db:
                for migration in sorted((ROOT / "migrations").glob("*.sql")):
                    if migration.name != "006_plano.sql":
                        db.executescript(migration.read_text(encoding="utf-8"))
                # Names, not numeric profile IDs, determine permissions.
                db.execute("UPDATE perfil SET id=id+?", (LARGE,))
                db.execute("INSERT INTO perfil(nome) VALUES('TH36 desconhecido')")
                roles = dict(db.execute("SELECT nome,id FROM perfil"))
                db.executemany("INSERT INTO academia(id,nome) VALUES(?,?)",
                               [(1, "A"), (2, "B"), (3, "FK sem Usuarios"), (LARGE, "Grande")])
                for identity, role, tenant in [(100, "Administrador", 1), (101, "Gestor", 1),
                        (102, "Instrutor", 1), (103, "Aluno", 1), (104, "TH36 desconhecido", 1),
                        (110, "Administrador", 2), (111, "Gestor", 2), (120, "Administrador", LARGE)]:
                    db.execute("INSERT INTO usuario(id,academia_id,perfil_id,nome,email,senha_hash) VALUES(?,?,?,'TH36',?,?)",
                               (identity, tenant, roles[role], f"u{identity}@example.test", encoded))
                db.execute("INSERT INTO aluno(usuario_id) VALUES(103)")
                db.execute("INSERT INTO instrutor(usuario_id) VALUES(102)")
                db.commit()
                tables = ("academia", "perfil", "usuario", "aluno", "instrutor")
                previous = {table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in tables}
                db.executescript((ROOT / "migrations/006_plano.sql").read_text(encoding="utf-8"))
                assert previous == {table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in tables}
                assert db.execute("SELECT * FROM plano").fetchall() == []
                db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('plano',?)", (LARGE,))
                db.commit()
            assert [column[1] for column in sql("PRAGMA table_info(plano)")] == [
                "id", "academia_id", "nome", "descricao", "valor_centavos", "duracao_dias", "ativo", "criado_em"]
            assert sql("PRAGMA foreign_key_list(plano)")[0][2:7] == ("academia", "academia_id", "id", "RESTRICT", "RESTRICT")
            assert any(index[1] == "idx_plano_academia_id" for index in sql("PRAGMA index_list(plano)"))
            assert any(index[2] == 1 for index in sql("PRAGMA index_list(plano)"))

            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
            config["listeners"] = [{"address": "127.0.0.1", "port": port}]
            config["db_clients"][0]["filename"] = database.as_posix()
            config["db_clients"][0]["connection_number"] = 3
            config["app"]["document_root"] = (ROOT / "public").as_posix()
            (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
            base = f"http://127.0.0.1:{port}"
            anonymous = urllib.request.build_opener()
            admin = anonymous

            def snapshot():
                try:
                    return sql("SELECT * FROM plano ORDER BY id")
                except sqlite3.OperationalError:
                    # Only the controlled missing-table checks make this snapshot unavailable.
                    return None

            def request(method, path, body=None, expected=200, client=None, content_type="application/json"):
                nonlocal checked
                previous = snapshot() if expected >= 400 else None
                data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(base + path, method=method, data=data,
                                             headers={"Content-Type": content_type})
                try:
                    response = (client or admin).open(req, timeout=20)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read()
                    assert response.code == expected, (method, path, response.code, expected, content)
                    safe(content, response.code >= 400)
                    payload = json.loads(content)
                    safe(json.dumps(payload, ensure_ascii=False).encode(), response.code >= 400)
                    assert "application/json" in response.headers.get("Content-Type", "")
                    if path.startswith("/api/planos"):
                        assert response.headers.get("Cache-Control") == "no-store"
                    if response.code >= 400:
                        assert set(payload) in ({"erro"}, {"message"})
                        if previous is not None:
                            assert snapshot() == previous, "Rejected request changed plans"
                    checked += 1
                    return payload

            def login(identity, tenant=1):
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                context = request("POST", "/api/auth/login", {"academia_id": tenant,
                    "email": f"u{identity}@example.test", "senha": PASSWORD}, client=client)
                assert context["userId"] == identity and context["academiaId"] == tenant
                return client

            def persisted(value):
                assert set(value) == FIELDS
                assert all(type(value[key]) is int for key in ("id", "academia_id", "valor_centavos", "duracao_dias"))
                assert value["id"] > 0 and value["valor_centavos"] >= 0 and value["duracao_dias"] > 0
                assert type(value["ativo"]) is bool
                assert isinstance(value["criado_em"], str) and value["criado_em"]
                assert sql("SELECT id,academia_id,nome,descricao,valor_centavos,duracao_dias,ativo,criado_em "
                    "FROM plano WHERE id=?", (value["id"],)) == [(value["id"], value["academia_id"], value["nome"],
                    value["descricao"], value["valor_centavos"], value["duracao_dias"], int(value["ativo"]), value["criado_em"])]

            def create(body=None, client=None, tenant=1):
                body = VALID if body is None else body
                value = request("POST", "/api/planos", body, 201, client)
                persisted(value)
                assert value["academia_id"] == tenant and value["ativo"] is True
                assert all(value[key] == body[key] for key in ("nome", "valor_centavos", "duracao_dias"))
                assert value["descricao"] == body.get("descricao")
                return value

            def update(identity, body, client=None):
                previous = sql("SELECT academia_id,ativo,criado_em FROM plano WHERE id=?", (identity,))
                value = request("PUT", f"/api/planos/{identity}", body, client=client)
                persisted(value)
                assert value["id"] == identity
                assert all(value[key] == body[key] for key in ("nome", "valor_centavos", "duracao_dias"))
                assert value["descricao"] == body.get("descricao")
                assert sql("SELECT academia_id,ativo,criado_em FROM plano WHERE id=?", (identity,)) == previous
                return value

            def status(identity, active, client=None):
                previous = sql("SELECT id,academia_id,nome,descricao,valor_centavos,duracao_dias,criado_em FROM plano WHERE id=?", (identity,))
                value = request("PUT", f"/api/planos/{identity}/status", {"ativo": active}, client=client)
                persisted(value)
                assert value["id"] == identity and value["ativo"] is active
                assert sql("SELECT id,academia_id,nome,descricao,valor_centavos,duracao_dias,criado_em FROM plano WHERE id=?", (identity,)) == previous
                return value

            with (directory / "server.log").open("w+b") as log:
                server = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory, env=env,
                    stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    for _ in range(100):
                        try:
                            request("GET", "/api/health", client=anonymous)
                            break
                        except urllib.error.URLError:
                            if server.poll() is not None:
                                raise RuntimeError("Isolated TH-36 server failed to start")
                            time.sleep(0.1)
                    else:
                        raise RuntimeError("Isolated TH-36 server startup timed out")

                    admin = login(100)
                    gestor = login(101)
                    admin_b = login(110, 2)
                    gestor_b = login(111, 2)
                    admin_large = login(120, LARGE)
                    assert request("GET", "/api/planos") == []
                    assert request("GET", "/api/planos", client=admin_b) == []
                    first = create()
                    path = f"/api/planos/{first['id']}"
                    assert first["id"] > LARGE
                    assert request("GET", "/api/planos") == [first]
                    assert request("GET", path) == first
                    second = create({"nome": "  Livre João  ", "valor_centavos": 0, "duracao_dias": 1}, gestor)
                    assert request("GET", "/api/planos", client=gestor) == [first, second]
                    create(VALID | {"nome": "Null", "descricao": None})
                    create(VALID | {"nome": "Descricao vazia", "descricao": ""})
                    request("POST", "/api/planos", VALID, 409)
                    other = create(client=admin_b, tenant=2)
                    other_second = create(VALID | {"nome": "Exclusivo B"}, gestor_b, 2)
                    request("PUT", f"/api/planos/{second['id']}", VALID, 409)
                    update(first["id"], VALID | {"nome": other_second["nome"]})
                    update(first["id"], VALID)
                    create(VALID | {"nome": "mensal"})  # Default SQLite collation is case-sensitive.

                    routes = [("GET", "/api/planos", None), ("GET", path, None),
                              ("POST", "/api/planos", VALID | {"nome": "Negado"}),
                              ("PUT", path, VALID), ("PUT", path + "/status", {"ativo": False})]
                    forged = urllib.request.build_opener()
                    forged.addheaders = [("Cookie", "JSESSIONID=TH36-invalid")]
                    for client, code in [(anonymous, 401), (forged, 401), (login(102), 403),
                                         (login(103), 403), (login(104), 403)]:
                        for method, endpoint, body in routes:
                            request(method, endpoint, body, code, client)
                        request("POST", "/api/planos", b"{", code, client)
                    for client, label in [(admin, "Admin"), (gestor, "Gestor")]:
                        create(VALID | {"nome": label}, client)
                        assert request("GET", path, client=client)["id"] == first["id"]
                        for value in request("GET", "/api/planos", client=client):
                            persisted(value)
                            assert value["academia_id"] == 1
                        changed = VALID | {"nome": "Editado " + label, "descricao": "  Descrição ç 😀  ",
                                           "valor_centavos": 24990, "duracao_dias": 90}
                        update(first["id"], changed, client)
                        assert update(first["id"], changed, client) == request("GET", path, client=client)
                        inactive = status(first["id"], False, client)
                        assert request("GET", path, client=client) == inactive
                        assert inactive in request("GET", "/api/planos", client=client)
                        status(first["id"], False, client)
                        update(first["id"], {key: value for key, value in VALID.items() if key != "descricao"}, client)
                        status(first["id"], True, client)
                        status(first["id"], True, client)

                    for client, tenant, foreign in [(admin, 1, other["id"]), (gestor, 1, other["id"]),
                                                     (admin_b, 2, first["id"]), (gestor_b, 2, first["id"])]:
                        values = request("GET", "/api/planos", client=client)
                        expected = sql("SELECT id FROM plano WHERE academia_id=? ORDER BY id", (tenant,))
                        assert [item["id"] for item in values] == [row[0] for row in expected]
                        assert all(item["academia_id"] == tenant for item in values)
                        for method, suffix, body in [("GET", "", None), ("PUT", "", VALID), ("PUT", "/status", {"ativo": False})]:
                            hidden = request(method, f"/api/planos/{foreign}" + suffix, body, 404, client)
                            absent = request(method, "/api/planos/999999" + suffix, body, 404, client)
                            assert hidden == absent

                    invalid = [None, b"{", b"null", [], 1, True, "text", {},
                        b'{"nome":"A","valor_centavos":0,"duracao_dias":1} {}',
                        b'{"nome":"A","valor_centavos":0,"duracao_dias":1} null',
                        b'{"nome":"A","valor_centavos":0,"duracao_dias":1} garbage',
                        b'{"nome":"A","valor_centavos":0,"duracao_dias":1,}',
                        b'{/* comment */"nome":"A","valor_centavos":0,"duracao_dias":1}',
                        b'{"nome":"A","valor_centavos":0,"duracao_dias":1 // comment\n}']
                    invalid += [{key: value for key, value in VALID.items() if key != missing}
                                for missing in ("nome", "valor_centavos", "duracao_dias")]
                    invalid += [VALID | {"nome": value} for value in ("", " \t\r\n\f\v", None, True, 1, [], {})]
                    invalid += [VALID | {"descricao": value} for value in (True, 1, [], {})]
                    for key in ("valor_centavos", "duracao_dias"):
                        invalid += [VALID | {key: value} for value in (-1, True, False, 1.0, "1", None, [], {}, 2**63, 2**64)]
                    invalid += [VALID | {"duracao_dias": 0}]
                    protected = ("academia_id", "academiaId", "id", "ativo", "criado_em", "outro")
                    invalid += [VALID | {key: 1} for key in protected]
                    for body in invalid:
                        request("POST", "/api/planos", body, 400)
                        request("PUT", path, body, 400)
                    for method, endpoint in [("POST", "/api/planos"), ("PUT", path)]:
                        for content_type in ("text/plain", "application/x-www-form-urlencoded", "text/plain; x=application/json"):
                            request(method, endpoint, VALID, 400, content_type=content_type)
                    update(first["id"], VALID, gestor)
                    assert request("PUT", path, b' \n {"nome":"Mensal","valor_centavos":0,"duracao_dias":1} \t\r\n',
                                   content_type="application/json; charset=utf-8")["valor_centavos"] == 0

                    for body in [None, b"{", b"null", [], 1, True, {}, {"other": True},
                                 b'{"ativo":true} {}', b'{"ativo":true,}', b'{/*comment*/"ativo":true}']:
                        request("PUT", path + "/status", body, 400)
                    for value in (0, 1, 1.0, "true", "false", None, [], {}):
                        request("PUT", path + "/status", {"ativo": value}, 400)
                    for key in (*protected, "nome", "descricao", "valor_centavos", "duracao_dias"):
                        request("PUT", path + "/status", {"ativo": False, key: 1}, 400)
                    request("PUT", path + "/status", {"ativo": False}, 400, content_type="text/plain")
                    for client, target, external in [(admin, first["id"], 2), (admin_b, other["id"], 1)]:
                        scoped_path = f"/api/planos/{target}"
                        scoped_routes = [("GET", "/api/planos", None), ("GET", scoped_path, None),
                                         ("POST", "/api/planos", VALID), ("PUT", scoped_path, VALID),
                                         ("PUT", scoped_path + "/status", {"ativo": False})]
                        for suffix in ("?academia_id=1", "?academia_id=2", "?academiaId=2", "?acad%65mia_id=2",
                                       "?academia_id=1&academia_id=2", "?other=1", "?x"):
                            for method, endpoint, body in scoped_routes:
                                request(method, endpoint + suffix, body, 400, client)
                        for key in ("academia_id", "academiaId"):
                            for method, endpoint, body in scoped_routes:
                                request(method, endpoint, (body or {}) | {key: external}, 400, client)
                    for invalid_id in ("0", "-1", "text", "true", "1.0", "1x", "+1", "%201", "1%20", "9223372036854775808"):
                        endpoint = "/api/planos/" + invalid_id
                        request("GET", endpoint, expected=400)
                        request("PUT", endpoint, VALID, 400)
                        request("PUT", endpoint + "/status", {"ativo": False}, 400)

                    # Independent clients start together; UNIQUE, not request ordering, selects one winner.
                    race_clients = [login(100), login(101)]
                    barrier = threading.Barrier(2)
                    def concurrent_create(index):
                        barrier.wait(timeout=10)
                        req = urllib.request.Request(base + "/api/planos", method="POST",
                            data=json.dumps(VALID | {"nome": "Concorrente"}).encode(), headers={"Content-Type": "application/json"})
                        try:
                            response = race_clients[index].open(req, timeout=20)
                        except urllib.error.HTTPError as error:
                            response = error
                        with response:
                            content = response.read()
                            safe(content, response.code >= 400)
                            assert response.headers.get("Cache-Control") == "no-store"
                            return response.code, json.loads(content)
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(concurrent_create, range(2)))
                    assert sorted(code for code, _ in results) == [201, 409]
                    checked += len(results)
                    persisted(next(value for code, value in results if code == 201))
                    assert sql("SELECT COUNT(*) FROM plano WHERE academia_id=1 AND nome='Concorrente'") == [(1,)]

                    # Losing the tenant inside INSERT rolls back the trigger's parent/user deletions.
                    sql(f"CREATE TRIGGER lose_academia BEFORE INSERT ON plano WHEN NEW.nome='TH36 FK loss' "
                        f"BEGIN DELETE FROM usuario WHERE academia_id={LARGE}; DELETE FROM academia WHERE id={LARGE}; END")
                    request("POST", "/api/planos", VALID | {"nome": "TH36 FK loss"}, 409, admin_large)
                    assert sql("SELECT id FROM academia WHERE id=?", (LARGE,)) == [(LARGE,)]
                    assert sql("SELECT id FROM usuario WHERE id=120") == [(120,)]
                    sql("DROP TRIGGER lose_academia")
                    maximum = create(VALID | {"nome": "Limites", "valor_centavos": MAXIMUM, "duracao_dias": MAXIMUM}, admin_large, LARGE)
                    assert request("GET", f"/api/planos/{maximum['id']}", client=admin_large) == maximum

                    # A tenant without Usuarios isolates Plano's own FK RESTRICT from other FKs.
                    sql("INSERT INTO plano(academia_id,nome,valor_centavos,duracao_dias) VALUES(3,'FK',0,1)")
                    with closing(sqlite3.connect(database)) as db:
                        db.execute("PRAGMA foreign_keys=ON")
                        assert db.execute("PRAGMA foreign_keys").fetchone() == (1,)
                        original = db.execute("SELECT * FROM plano ORDER BY id").fetchall()
                        for statement in [
                            "INSERT INTO plano(academia_id,nome,valor_centavos,duracao_dias) VALUES(999999,'FK',0,1)",
                            "INSERT INTO plano(academia_id,nome,valor_centavos,duracao_dias) VALUES(3,'FK',0,1)",
                            "DELETE FROM academia WHERE id=3", "UPDATE academia SET id=999999 WHERE id=3",
                            "UPDATE plano SET ativo=2 WHERE academia_id=3",
                            "UPDATE plano SET valor_centavos=-1 WHERE academia_id=3",
                            "UPDATE plano SET valor_centavos=1.5 WHERE academia_id=3",
                            "UPDATE plano SET valor_centavos=9223372036854775808 WHERE academia_id=3",
                            "UPDATE plano SET duracao_dias=0 WHERE academia_id=3",
                            "UPDATE plano SET duracao_dias=-1 WHERE academia_id=3",
                            "UPDATE plano SET duracao_dias=1.5 WHERE academia_id=3",
                            "UPDATE plano SET duracao_dias=9223372036854775808 WHERE academia_id=3",
                            "UPDATE plano SET nome=NULL WHERE academia_id=3",
                        ]:
                            try:
                                db.execute(statement)
                            except sqlite3.IntegrityError:
                                db.rollback()
                            else:
                                raise AssertionError("Invalid direct persistence accepted: " + statement)
                            assert db.execute("SELECT * FROM plano ORDER BY id").fetchall() == original
                        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

                    # Corruption is confined to this fixture; reads must reject a third activity state.
                    saved_active = sql("SELECT ativo FROM plano WHERE id=?", (first["id"],))[0][0]
                    with closing(sqlite3.connect(database)) as db:
                        db.execute("PRAGMA ignore_check_constraints=ON")
                        db.execute("UPDATE plano SET ativo=2 WHERE id=?", (first["id"],))
                        db.commit()
                    try:
                        request("GET", path, expected=500)
                        request("GET", "/api/planos", expected=500)
                        assert request("GET", "/api/planos", client=admin_b)
                    finally:
                        sql("UPDATE plano SET ativo=? WHERE id=?", (saved_active, first["id"]))

                    # Seed the maximum ID only after every successful INSERT has finished.
                    sql("UPDATE plano SET id=? WHERE id=?", (MAXIMUM, maximum["id"]))
                    exact_path = f"/api/planos/{MAXIMUM}"
                    assert request("GET", exact_path, client=admin_large)["id"] == MAXIMUM
                    update(MAXIMUM, VALID | {"nome": "Limite editado", "valor_centavos": MAXIMUM, "duracao_dias": MAXIMUM}, admin_large)
                    status(MAXIMUM, False, admin_large)
                    status(MAXIMUM, True, admin_large)

                    previous = snapshot()
                    sql("ALTER TABLE plano RENAME TO plano_unavailable")
                    try:
                        for method, endpoint, body in routes:
                            request(method, endpoint, body, 500)
                    finally:
                        sql("ALTER TABLE plano_unavailable RENAME TO plano")
                    assert snapshot() == previous
                    assert sql("PRAGMA foreign_key_check") == []
                    request("GET", "/api/health")
                    assert server.poll() is None
                finally:
                    if server.poll() is None:
                        server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
                    log.seek(0)
                    safe(log.read())
    finally:
        after = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
        assert before == after, "Development database changed"
    print(f"TH-36 passed: {checked} HTTP checks; create/read/update/status, strict contracts, int64, exact cents/days, "
          "role matrix, bidirectional tenant isolation, concurrent UNIQUE, FK/CHECK/RESTRICT, "
          "safe 400/401/403/404/409/500 and isolated SQLite. Development DB unchanged.")


if __name__ == "__main__":
    run()
