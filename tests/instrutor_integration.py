"""TH-27 checks with a real server, sessions, and SQLite isolated from local data."""

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


def run():
    development = ROOT / "data/traininghub.db"
    before = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    encoded = subprocess.check_output([str(ROOT / "build/security-tests/security_tests.exe"),
                                       "--fixture-hash"], env=env, text=True).strip()
    checked = 0
    large_id = 2**40
    try:
        with tempfile.TemporaryDirectory(prefix="th27-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "instrutor.db"

            def sql(statement, values=()):
                # Some fixtures deliberately simulate external changes/corruption. Constraint
                # checks below use a separate connection with foreign_keys explicitly enabled.
                with closing(sqlite3.connect(database, timeout=10)) as db:
                    result = db.execute(statement, values).fetchall()
                    db.commit()
                    return result

            with closing(sqlite3.connect(database)) as db:
                db.executescript((ROOT / "migrations/001_initial_schema.sql").read_text(encoding="utf-8"))
                # The canonical Instructor role must work independently of its database ID.
                db.execute("INSERT INTO perfil (id,nome) VALUES (?, 'Instrutor')", (large_id + 7,))
                db.commit()
                for migration in ["002_canonical_profiles.sql", "003_aluno.sql", "004_instrutor.sql"]:
                    db.executescript((ROOT / "migrations" / migration).read_text(encoding="utf-8"))
                roles = dict(db.execute("SELECT nome,id FROM perfil"))
                for name in ["instrutor", "INSTRUTOR", "Instrutor ", "Instructor", "Desconhecido"]:
                    roles[name] = db.execute("INSERT INTO perfil (nome) VALUES (?)", (name,)).lastrowid
                db.executemany("INSERT INTO academia (id,nome) VALUES (?,?)", [(1, "A"), (2, "B"), (large_id, "Grande")])

                def user(user_id, role="Instrutor", academia=1, active=1):
                    db.execute("INSERT INTO usuario (id,academia_id,perfil_id,nome,email,senha_hash,ativo) "
                               "VALUES (?,?,?,'Teste',?,?,?)",
                               (user_id, academia, roles[role], f"u{user_id}@example.test", encoded, active))

                for user_id, role in [(100, "Administrador"), (101, "Gestor"), (102, "Instrutor"),
                                      (103, "Aluno"), (104, "Desconhecido")]:
                    user(user_id, role)
                user(110, "Administrador", 2)
                user(111, "Gestor", 2)
                user(120, "Administrador", large_id)
                for user_id in range(200, 208):
                    user(user_id)
                user(220, active=0)
                for user_id, role in [(221, "Aluno"), (222, "Gestor"), (223, "Administrador"),
                                      (224, "instrutor"), (225, "INSTRUTOR"), (226, "Instrutor "),
                                      (227, "Instructor"), (228, "Desconhecido")]:
                    user(user_id, role)
                user(229, active=2)
                user(250, "Aluno")
                user(300, academia=2)
                user(large_id, academia=large_id)
                user(2**63 - 1)
                db.execute("INSERT INTO sqlite_sequence (name,seq) VALUES ('instrutor',?)", (large_id,))
                db.commit()

            columns = sql("PRAGMA table_info(instrutor)")
            assert [column[1] for column in columns] == ["id", "usuario_id", "criado_em"]
            assert columns[1][3] == columns[2][3] == 1
            assert sql("PRAGMA foreign_key_list(instrutor)")[0][2:7] == (
                "usuario", "usuario_id", "id", "RESTRICT", "RESTRICT")

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

            def request(method, path, body=None, expected=200, client=None, with_status=False):
                nonlocal checked
                data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(base + path, method=method, data=data,
                                             headers={"Content-Type": "application/json"})
                try:
                    response = (client or admin).open(req, timeout=20)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read()
                    allowed = (expected,) if isinstance(expected, int) else expected
                    assert response.code in allowed, (method, path, response.code, content)
                    assert "application/json" in response.headers.get("Content-Type", "")
                    assert not any(value in content for value in [b'"senha"', b'"senha_hash"', PASSWORD.encode(), encoded.encode()])
                    payload = json.loads(content)
                    if response.code >= 400:
                        assert set(payload) in ({"erro"}, {"message"}), payload
                        assert not any(token in content.lower() for token in [b"sqlite", b"select ", b"insert ",
                            b"constraint", b"no such", b"schema", b"traceback", b".db", b"c:\\"])
                    checked += 1
                    return (response.code, payload) if with_status else payload

            def login(user_id, academia=1):
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                request("POST", "/api/auth/login", {"academia_id": academia,
                    "email": f"u{user_id}@example.test", "senha": PASSWORD}, client=client)
                return client

            def create(user_id=200, expected=201, client=None):
                return request("POST", "/api/instrutores", {"usuario_id": user_id}, expected, client)

            def assert_instrutor(value, user_id):
                assert set(value) == {"id", "usuario_id", "criado_em"}, value
                assert value["usuario_id"] == user_id and value["id"] > large_id
                assert isinstance(value["criado_em"], str) and value["criado_em"]

            admin = anonymous
            with (directory / "server.log").open("w+", encoding="utf-8") as log:
                server = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory, env=env,
                    stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    for _ in range(100):
                        try:
                            request("GET", "/api/health", client=anonymous)
                            break
                        except urllib.error.URLError:
                            if server.poll() is not None:
                                raise RuntimeError("Isolated server failed to start")
                            time.sleep(0.1)
                    else:
                        raise RuntimeError("Isolated server did not start")

                    admin = login(100)
                    gestor = login(101)
                    admin_b = login(110, 2)
                    gestor_b = login(111, 2)
                    admin_large = login(120, large_id)
                    for client, status in [(anonymous, 401), (login(102), 403), (login(103), 403), (login(104), 403)]:
                        create(expected=status, client=client)
                        request("GET", "/api/instrutores", expected=status, client=client)
                        request("GET", "/api/instrutores/1", expected=status, client=client)
                    assert request("GET", "/api/instrutores") == []
                    assert request("GET", "/api/instrutores", client=gestor) == []
                    first = create()
                    second = create(201, client=gestor)
                    assert_instrutor(first, 200)
                    assert_instrutor(second, 201)
                    path = f"/api/instrutores/{first['id']}"
                    for client in [admin, gestor]:
                        assert request("GET", path, client=client) == first
                        assert request("GET", "/api/instrutores", client=client) == [first, second]
                        create(expected=409, client=client)
                        create(300, 404, client)
                        create(999999, 404, client)
                    other = create(300, client=admin_b)
                    for client in [admin, gestor]:
                        request("GET", f"/api/instrutores/{other['id']}", expected=404, client=client)
                    assert request("GET", "/api/instrutores", client=gestor_b) == [other]
                    request("GET", path, expected=404, client=admin_b)
                    request("GET", "/api/instrutores/999999", expected=404)
                    assert request("GET", "/api/instrutores") == [first, second]

                    for user_id in range(220, 230):
                        create(user_id, 400)
                        assert sql("SELECT COUNT(*) FROM instrutor WHERE usuario_id=?", (user_id,)) == [(0,)]
                    sql("UPDATE usuario SET perfil_id=999999 WHERE id=204")
                    create(204, 400)
                    sql("UPDATE usuario SET perfil_id=? WHERE id=204", (roles["Instrutor"],))
                    sql("UPDATE perfil SET ativo=0 WHERE id=?", (roles["Instrutor"],))
                    create(204, 400)
                    assert request("GET", path) == first
                    assert request("GET", "/api/instrutores") == [first, second]
                    sql("UPDATE perfil SET ativo=1 WHERE id=?", (roles["Instrutor"],))
                    for statement, values in [
                        ("UPDATE usuario SET ativo=0 WHERE id=200", ()),
                        ("UPDATE usuario SET perfil_id=? WHERE id=200", (roles["Aluno"],)),
                    ]:
                        sql(statement, values)
                        assert request("GET", path) == first
                        assert request("GET", "/api/instrutores", client=gestor) == [first, second]
                    sql("UPDATE usuario SET ativo=1,perfil_id=? WHERE id=200", (roles["Instrutor"],))

                    # Create the historical record through its real API, then change only the
                    # temporary fixture's profile: production has no profile-transfer endpoint.
                    historical = request("POST", "/api/alunos", {"usuario_id": 250}, 201)
                    create(250, 400)
                    sql("UPDATE usuario SET perfil_id=? WHERE id=250", (roles["Instrutor"],))
                    converted = create(250)
                    assert_instrutor(converted, 250)
                    assert request("GET", f"/api/alunos/{historical['id']}") == historical
                    assert request("GET", f"/api/instrutores/{converted['id']}") == converted
                    assert sql("SELECT COUNT(*) FROM aluno WHERE usuario_id=250") == [(1,)]
                    assert sql("SELECT COUNT(*) FROM instrutor WHERE usuario_id=250") == [(1,)]
                    converted_client = login(250)
                    request("GET", "/api/alunos", expected=403, client=converted_client)
                    request("GET", "/api/instrutores", expected=403, client=converted_client)

                    strict_cases = [b'{"usuario_id":202} {"academia_id":2}', b'{"usuario_id":202} null',
                        b'{"usuario_id":202} invalid', b'{"usuario_id":202 // comment\n}',
                        b'{/* comment */ "usuario_id":202}', b'{"usuario_id":202,}']
                    invalid_bodies = [None, b"{", b"null", [], 1, "text", {}, {"other": 202}]
                    invalid_bodies += strict_cases
                    invalid_bodies += [{"usuario_id": value} for value in
                                       [True, False, "202", 202.0, 0, -1, None, [], {}, 2**63, 2**64]]
                    invalid_bodies += [{"usuario_id": 202, field: 1} for field in
                                       ["academia_id", "nome", "email", "perfil_id", "ativo", "aluno_id", "senha_hash"]]
                    for body in invalid_bodies:
                        request("POST", "/api/instrutores", body, 400)
                        assert sql("SELECT COUNT(*) FROM instrutor WHERE usuario_id=202") == [(0,)]
                    for suffix in ["?academia_id=1", "?academia_id=2", "?acad%65mia_id=2",
                                   "?academia_id=1&academia_id=2", "?other=1", "?academia_id", "?x"]:
                        request("POST", "/api/instrutores" + suffix, {"usuario_id": 202}, 400)
                        request("GET", "/api/instrutores" + suffix, expected=400)
                        request("GET", path + suffix, expected=400)
                        assert sql("SELECT COUNT(*) FROM instrutor WHERE usuario_id=202") == [(0,)]
                    for read_path in ["/api/instrutores", path]:
                        request("GET", read_path, {"academia_id": 2}, 400)
                    normal = request("POST", "/api/instrutores", b' \n {"usuario_id":202} \t\r\n', 201)
                    assert_instrutor(normal, 202)
                    for invalid_id in ["0", "-1", "1.0", "true", "1x", "+1", "%201", "9223372036854775808", "1%20OR%201=1"]:
                        request("GET", "/api/instrutores/" + invalid_id, expected=400)
                    maximum_user = create(2**63 - 1)
                    assert maximum_user["usuario_id"] == 2**63 - 1
                    large = create(large_id, client=admin_large)
                    assert_instrutor(large, large_id)
                    assert request("GET", f"/api/instrutores/{large['id']}", client=admin_large) == large
                    assert request("GET", "/api/instrutores", client=admin_large) == [large]

                    race_clients = [login(100), login(101)]
                    barrier = threading.Barrier(2)

                    def concurrent_create(index):
                        barrier.wait(timeout=10)
                        return request("POST", "/api/instrutores", {"usuario_id": 203}, (201, 409),
                                       race_clients[index], with_status=True)

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(concurrent_create, range(2)))
                    assert sorted(status for status, _ in results) == [201, 409], results
                    assert sql("SELECT COUNT(*) FROM instrutor WHERE usuario_id=203") == [(1,)]

                    sql("CREATE TRIGGER lose_parent BEFORE INSERT ON instrutor WHEN NEW.usuario_id=205 "
                        "BEGIN DELETE FROM usuario WHERE id=205; END")
                    create(205, 409)
                    assert sql("SELECT COUNT(*) FROM usuario WHERE id=205") == [(1,)]
                    assert sql("SELECT COUNT(*) FROM instrutor WHERE usuario_id=205") == [(0,)]
                    sql("DROP TRIGGER lose_parent")
                    with closing(sqlite3.connect(database)) as db:
                        db.execute("PRAGMA foreign_keys=ON")
                        for statement, values in [
                            ("DELETE FROM usuario WHERE id=200", ()),
                            ("UPDATE usuario SET id=999999 WHERE id=200", ()),
                            ("INSERT INTO instrutor (usuario_id) VALUES (?)", (200,)),
                            ("INSERT INTO instrutor (usuario_id) VALUES (?)", (999999,)),
                            ("INSERT INTO instrutor (usuario_id) VALUES (NULL)", ()),
                        ]:
                            try:
                                db.execute(statement, values)
                            except sqlite3.IntegrityError:
                                db.rollback()
                            else:
                                raise AssertionError("Database accepted invalid relationship")
                        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

                    sql("UPDATE instrutor SET id=? WHERE usuario_id=?", (2**63 - 1, 2**63 - 1))
                    maximum = request("GET", f"/api/instrutores/{2**63 - 1}")
                    assert maximum["id"] == maximum["usuario_id"] == 2**63 - 1
                    listed = request("GET", "/api/instrutores")
                    assert [value["id"] for value in listed] == sorted(value["id"] for value in listed)
                    sql("UPDATE academia SET ativo=0 WHERE id=1")
                    create(206, 401)
                    request("GET", "/api/instrutores", expected=401, client=gestor)
                    sql("UPDATE academia SET ativo=1 WHERE id=1")
                    admin = login(100)
                    sql("UPDATE usuario SET ativo=0 WHERE id=100")
                    request("GET", path, expected=401)
                    sql("UPDATE usuario SET ativo=1 WHERE id=100")
                    admin = login(100)
                    sql("ALTER TABLE instrutor RENAME TO instrutor_unavailable")
                    request("GET", "/api/instrutores", expected=500)
                    request("GET", path, expected=500)
                    create(206, 500)
                    sql("ALTER TABLE instrutor_unavailable RENAME TO instrutor")
                    sql("UPDATE usuario SET ativo='invalid' WHERE id=206")
                    create(206, 500)
                    sql("UPDATE usuario SET ativo=1 WHERE id=206")
                    request("GET", "/api/health")
                    assert server.poll() is None
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
                log.seek(0)
                logs = log.read()
                assert PASSWORD not in logs and encoded not in logs
    finally:
        after = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
        assert before == after, "Development database changed"
    print(f"TH-27 passed: {checked} HTTP checks; real sessions, role matrix, strict JSON, tenant isolation, "
          "eligibility, historical reads, cross-table history, int64, concurrent UNIQUE, FK RESTRICT, "
          "safe errors. Development DB unchanged.")


if __name__ == "__main__":
    run()
