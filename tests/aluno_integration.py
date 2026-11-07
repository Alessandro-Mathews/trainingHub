"""TH-26 HTTP and database checks using real sessions and an isolated SQLite database."""

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
        with tempfile.TemporaryDirectory(prefix="th26-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "aluno.db"

            def sql(statement, values=()):
                with closing(sqlite3.connect(database, timeout=10)) as db:
                    result = db.execute(statement, values).fetchall()
                    db.commit()
                    return result

            with closing(sqlite3.connect(database)) as db:
                db.executescript((ROOT / "migrations/001_initial_schema.sql").read_text(encoding="utf-8"))
                # Role IDs are arbitrary and deliberately exceed 32 bits.
                db.execute("INSERT INTO perfil (id,nome) VALUES (?, 'Aluno')", (large_id + 3,))
                db.commit()
                db.executescript((ROOT / "migrations/002_canonical_profiles.sql").read_text(encoding="utf-8"))
                db.executescript((ROOT / "migrations/003_aluno.sql").read_text(encoding="utf-8"))
                roles = dict(db.execute("SELECT nome,id FROM perfil"))
                for name in ["aluno", "Aluno ", "Desconhecido"]:
                    roles[name] = db.execute("INSERT INTO perfil (nome) VALUES (?)", (name,)).lastrowid
                db.executemany("INSERT INTO academia (id,nome,ativo) VALUES (?,?,?)",
                               [(1, "A", 1), (2, "B", 1), (3, "Inativa", 0), (large_id, "Grande", 1)])

                def user(user_id, role="Aluno", academia=1, active=1):
                    db.execute("INSERT INTO usuario (id,academia_id,perfil_id,nome,email,senha_hash,ativo) "
                               "VALUES (?,?,?,'Teste',?,?,?)",
                               (user_id, academia, roles[role], f"u{user_id}@example.test", encoded, active))

                for user_id, role in [(100, "Administrador"), (101, "Gestor"), (102, "Instrutor"),
                                      (103, "Aluno"), (104, "Desconhecido")]:
                    user(user_id, role)
                user(110, "Administrador", 2)
                user(111, "Gestor", 2)
                user(120, "Administrador", large_id)
                for user_id in range(200, 215):
                    user(user_id)
                user(220, active=0)
                user(221, "Instrutor")
                user(222, "aluno")
                user(223, "Desconhecido")
                user(224, "Aluno ")
                user(225, active=2)
                user(300, academia=2)
                user(large_id, academia=large_id)
                user(2**63 - 1)
                db.execute("INSERT INTO sqlite_sequence (name,seq) VALUES ('aluno',?)", (large_id,))
                db.commit()

            columns = sql("PRAGMA table_info(aluno)")
            assert [column[1] for column in columns] == ["id", "usuario_id", "criado_em"]
            assert columns[1][3] == columns[2][3] == 1
            fk = sql("PRAGMA foreign_key_list(aluno)")
            assert len(fk) == 1 and fk[0][2:7] == ("usuario", "usuario_id", "id", "RESTRICT", "RESTRICT")
            assert any(index[2] == 1 for index in sql("PRAGMA index_list(aluno)"))

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

            def request(method, path, body=None, expected=200, client=None):
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
                    assert not any(value in content for value in [b'"senha"', b'"senha_hash"',
                                                                  PASSWORD.encode(), encoded.encode()])
                    if response.code >= 400:
                        assert not any(value in content.lower() for value in [b"select ", b"insert ",
                            b"constraint", b"sqlite", b"no such", b"traceback", b"schema", b".db", b"c:\\"])
                        payload = json.loads(content)
                        assert set(payload) in ({"erro"}, {"message"}), payload
                    checked += 1
                    return json.loads(content)

            def login(user_id, academia=1):
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                request("POST", "/api/auth/login", {"academia_id": academia,
                    "email": f"u{user_id}@example.test", "senha": PASSWORD}, client=client)
                return client

            def create(user_id=200, expected=201, client=None):
                return request("POST", "/api/alunos", {"usuario_id": user_id}, expected, client)

            def assert_aluno(value, user_id):
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
                    for client, status in [(anonymous, 401), (login(102), 403),
                                           (login(103), 403), (login(104), 403)]:
                        create(expected=status, client=client)
                        request("GET", "/api/alunos", expected=status, client=client)
                        request("GET", "/api/alunos/1", expected=status, client=client)

                    assert request("GET", "/api/alunos") == []
                    assert request("GET", "/api/alunos", client=gestor) == []
                    first = create()
                    second = create(201, client=gestor)
                    assert_aluno(first, 200)
                    assert_aluno(second, 201)
                    path = f"/api/alunos/{first['id']}"
                    assert request("GET", path) == first
                    assert request("GET", path, client=gestor) == first
                    assert request("GET", "/api/alunos") == [first, second]
                    assert request("GET", "/api/alunos", client=gestor) == [first, second]
                    create(expected=409)
                    create(expected=409, client=gestor)
                    for client in [admin, gestor]:
                        create(300, 404, client)
                        create(999999, 404, client)
                    other = create(300, client=admin_b)
                    assert request("GET", "/api/alunos", client=gestor_b) == [other]
                    assert request("GET", "/api/alunos") == [first, second]
                    for client in [admin, gestor]:
                        request("GET", f"/api/alunos/{other['id']}", expected=404, client=client)
                    request("GET", path, expected=404, client=admin_b)
                    request("GET", "/api/alunos/999999", expected=404)

                    for user_id in range(220, 226):
                        create(user_id, 400)
                    # A missing profile is possible in a database modified with FK checks disabled.
                    sql("UPDATE usuario SET perfil_id=999999 WHERE id=202")
                    create(202, 400)
                    sql("UPDATE usuario SET perfil_id=? WHERE id=202", (roles["Aluno"],))
                    sql("UPDATE perfil SET ativo=0 WHERE id=?", (roles["Aluno"],))
                    create(202, 400)
                    assert request("GET", path) == first
                    assert request("GET", "/api/alunos") == [first, second]
                    sql("UPDATE perfil SET ativo=1 WHERE id=?", (roles["Aluno"],))

                    for statement, values in [
                        ("UPDATE usuario SET ativo=0 WHERE id=?", (200,)),
                        ("UPDATE usuario SET perfil_id=? WHERE id=?", (roles["Instrutor"], 200)),
                    ]:
                        sql(statement, values)
                        assert request("GET", path) == first
                        assert request("GET", "/api/alunos", client=gestor) == [first, second]
                    sql("UPDATE usuario SET ativo=1,perfil_id=? WHERE id=200", (roles["Aluno"],))

                    strict_json_cases = [
                        ("second object", b'{"usuario_id":202} {"academia_id":2}'),
                        ("trailing null", b'{"usuario_id":202} null'),
                        ("trailing garbage", b'{"usuario_id":202} invalid'),
                        ("line comment", b'{"usuario_id":202 // comment\n}'),
                        ("block comment", b'{/* comment */ "usuario_id":202}'),
                        ("trailing comma", b'{"usuario_id":202,}'),
                    ]
                    for scenario, body in strict_json_cases:
                        request("POST", "/api/alunos", body, 400)
                        assert sql("SELECT COUNT(*) FROM aluno WHERE usuario_id=202") == [(0,)], scenario
                    normal = request("POST", "/api/alunos", b' \n {"usuario_id":202} \t\r\n', 201)
                    assert_aluno(normal, 202)
                    assert sql("SELECT COUNT(*) FROM aluno WHERE usuario_id=202") == [(1,)]
                    print("Strict JSON passed: second object, trailing null/garbage, line/block comments, "
                          "trailing comma all returned 400 without persistence; valid JSON returned 201.")

                    for body in [None, b"{", b"null", [], 1, "text", {}, {"other": 200}]:
                        request("POST", "/api/alunos", body, 400)
                    for value in [True, False, "200", 200.0, 0, -1, None, [], {}, 2**63, 2**64]:
                        request("POST", "/api/alunos", {"usuario_id": value}, 400)
                    for extra in ["academia_id", "nome", "email", "perfil_id", "ativo", "instrutor_id", "senha_hash"]:
                        request("POST", "/api/alunos", {"usuario_id": 202, extra: 1}, 400)
                    for suffix in ["?academia_id=1", "?academia_id=2", "?acad%65mia_id=1",
                                   "?academia_id=1&academia_id=2", "?other=1", "?academia_id", "?x"]:
                        request("POST", "/api/alunos" + suffix, {"usuario_id": 202}, 400)
                        request("GET", "/api/alunos" + suffix, expected=400)
                        request("GET", path + suffix, expected=400)
                    for read_path in ["/api/alunos", path]:
                        request("GET", read_path, {"academia_id": 2}, 400)
                    for invalid_id in ["0", "-1", "1.0", "true", "1x", "+1", "%201", "9223372036854775808", "1%20OR%201=1"]:
                        request("GET", "/api/alunos/" + invalid_id, expected=400)
                    create(2**63 - 1)
                    large = create(large_id, client=admin_large)
                    assert_aluno(large, large_id)
                    assert request("GET", f"/api/alunos/{large['id']}", client=admin_large) == large
                    assert request("GET", "/api/alunos", client=admin_large) == [large]

                    # Both requests start together, each with a real authenticated session.
                    race_clients = [login(100), login(101)]
                    barrier = threading.Barrier(2)

                    def concurrent_create(index):
                        barrier.wait(timeout=10)
                        return create(203, expected=(201, 409), client=race_clients[index])

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(concurrent_create, range(2)))
                    assert sum("id" in result for result in results) == 1, results
                    assert sql("SELECT COUNT(*) FROM aluno WHERE usuario_id=203") == [(1,)]

                    # Hold a writer lock while an HTTP request starts. A committed change must
                    # never leave a cross-tenant or ineligible association, regardless of scheduling.
                    for statement, values, restore, restore_values, errors in [
                        ("UPDATE usuario SET ativo=0 WHERE id=204", (),
                         "UPDATE usuario SET ativo=1 WHERE id=204", (), (400, 409)),
                        ("UPDATE usuario SET perfil_id=? WHERE id=204", (roles["Instrutor"],),
                         "UPDATE usuario SET perfil_id=? WHERE id=204", (roles["Aluno"],), (400, 409)),
                        ("UPDATE perfil SET ativo=0 WHERE id=?", (roles["Aluno"],),
                         "UPDATE perfil SET ativo=1 WHERE id=?", (roles["Aluno"],), (400, 409)),
                        ("UPDATE usuario SET academia_id=2 WHERE id=204", (),
                         "UPDATE usuario SET academia_id=1 WHERE id=204", (), (404, 409)),
                    ]:
                        with closing(sqlite3.connect(database)) as writer:
                            writer.execute("BEGIN IMMEDIATE")
                            writer.execute(statement, values)
                            with ThreadPoolExecutor(max_workers=1) as pool:
                                future = pool.submit(create, 204, errors)
                                time.sleep(0.3)
                                writer.commit()
                                future.result(timeout=20)
                        assert sql("SELECT COUNT(*) FROM aluno WHERE usuario_id=204") == [(0,)]
                        sql(restore, restore_values)

                    # Foreign-key loss inside the insert must roll back and return a safe conflict.
                    sql("CREATE TRIGGER lose_parent BEFORE INSERT ON aluno WHEN NEW.usuario_id=205 "
                        "BEGIN DELETE FROM usuario WHERE id=205; END")
                    create(205, 409)
                    assert sql("SELECT COUNT(*) FROM usuario WHERE id=205") == [(1,)]
                    assert sql("SELECT COUNT(*) FROM aluno WHERE usuario_id=205") == [(0,)]
                    sql("DROP TRIGGER lose_parent")

                    with closing(sqlite3.connect(database)) as db:
                        db.execute("PRAGMA foreign_keys=ON")
                        for statement, values in [
                            ("DELETE FROM usuario WHERE id=200", ()),
                            ("UPDATE usuario SET id=999999 WHERE id=200", ()),
                            ("INSERT INTO aluno (usuario_id) VALUES (?)", (200,)),
                            ("INSERT INTO aluno (usuario_id) VALUES (?)", (999999,)),
                            ("INSERT INTO aluno (usuario_id) VALUES (NULL)", ()),
                        ]:
                            try:
                                db.execute(statement, values)
                            except sqlite3.IntegrityError:
                                db.rollback()
                            else:
                                raise AssertionError("Database accepted invalid relationship")
                        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

                    # IDs at the positive int64 limit must also round-trip through the URL/JSON.
                    sql("UPDATE aluno SET id=? WHERE usuario_id=?", (2**63 - 1, 2**63 - 1))
                    maximum = request("GET", f"/api/alunos/{2**63 - 1}")
                    assert maximum["id"] == maximum["usuario_id"] == 2**63 - 1
                    listed = request("GET", "/api/alunos")
                    assert [item["id"] for item in listed] == sorted(item["id"] for item in listed)

                    sql("UPDATE academia SET ativo=0 WHERE id=1")
                    create(206, 401)
                    request("GET", "/api/alunos", expected=401, client=gestor)
                    sql("UPDATE academia SET ativo=1 WHERE id=1")
                    admin = login(100)
                    sql("UPDATE usuario SET ativo=0 WHERE id=100")
                    request("GET", path, expected=401)
                    sql("UPDATE usuario SET ativo=1 WHERE id=100")
                    admin = login(100)

                    sql("ALTER TABLE aluno RENAME TO aluno_unavailable")
                    request("GET", "/api/alunos", expected=500)
                    request("GET", path, expected=500)
                    create(206, 500)
                    sql("ALTER TABLE aluno_unavailable RENAME TO aluno")
                    # Malformed mapped values must reach the error callback without killing workers.
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
    print(f"TH-26 passed: {checked} HTTP checks; real sessions, role matrix, tenant isolation, "
          "creation eligibility, persistent administrative reads, int64, concurrent UNIQUE, "
          "conditional writes, FK RESTRICT, safe errors. Development DB unchanged.")


if __name__ == "__main__":
    run()
