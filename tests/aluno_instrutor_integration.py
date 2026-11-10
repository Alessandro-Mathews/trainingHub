"""TH-30: real HTTP sessions and relationship persistence in an isolated SQLite database."""

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
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "TH24-test-password"
WRONG_PASSWORD = "TH30-WRONG-PASSWORD-SENTINEL"
LARGE = 2**40
MAXIMUM = 2**63 - 1


def run():
    development = ROOT / "data/traininghub.db"
    before = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    encoded = subprocess.check_output([str(ROOT / "build/security-tests/security_tests.exe"),
                                       "--fixture-hash"], env=env, text=True).strip()
    secrets = (PASSWORD.encode(), WRONG_PASSWORD.encode(), encoded.encode(), b"$argon2id$",
               b'"senha"', b'"senha_hash"')
    checked = 0

    def safe(content):
        assert not any(secret in content for secret in secrets), "Credential exposed"
        assert not any(token in content.lower() for token in [b"select ", b"update ", b"insert ",
            b"sqlite", b"constraint", b"no such", b"traceback", b"schema", b".db", b"c:\\"]), "Internal detail exposed"

    try:
        with tempfile.TemporaryDirectory(prefix="th30-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "relationship.db"

            def sql(statement, values=()):
                # External corruption fixtures deliberately use a separate FK-disabled connection.
                with closing(sqlite3.connect(database, timeout=10)) as db:
                    result = db.execute(statement, values).fetchall()
                    db.commit()
                    return result

            with closing(sqlite3.connect(database)) as db:
                for migration in ["001_initial_schema.sql", "002_canonical_profiles.sql",
                                  "003_aluno.sql", "004_instrutor.sql"]:
                    db.executescript((ROOT / "migrations" / migration).read_text(encoding="utf-8"))
                # Canonical names work with arbitrary IDs beyond 32 bits.
                db.execute("UPDATE perfil SET id=id+?", (LARGE,))
                roles = dict(db.execute("SELECT nome,id FROM perfil"))
                for name in ["Desconhecido", "aluno", "Instrutor "]:
                    roles[name] = db.execute("INSERT INTO perfil (nome) VALUES (?)", (name,)).lastrowid
                db.executemany("INSERT INTO academia (id,nome) VALUES (?,?)", [(1, "A"), (2, "B")])

                def user(user_id, role, academy=1):
                    db.execute("INSERT INTO usuario (id,academia_id,perfil_id,nome,email,senha_hash) "
                               "VALUES (?,?,?,'Teste',?,?)",
                               (user_id, academy, roles[role], f"u{user_id}@example.test", encoded))

                for user_id, role, academy in [(100, "Administrador", 1), (101, "Gestor", 1),
                        (102, "Instrutor", 1), (103, "Aluno", 1), (104, "Desconhecido", 1),
                        (110, "Administrador", 2), (111, "Gestor", 2),
                        (200, "Aluno", 1), (201, "Aluno", 1), (202, "Aluno", 2),
                        (300, "Instrutor", 1), (301, "Instrutor", 1), (302, "Instrutor", 2),
                        (203, "Aluno", 1), (303, "Instrutor", 1)]:
                    user(user_id, role, academy)
                db.executemany("INSERT INTO aluno (id,usuario_id) VALUES (?,?)",
                               [(1, 203), (LARGE, 200), (LARGE + 1, 201), (LARGE + 2, 202)])
                db.executemany("INSERT INTO instrutor (id,usuario_id) VALUES (?,?)",
                               [(1, 303), (LARGE, 300), (LARGE + 1, 301), (LARGE + 2, 302)])
                user(MAXIMUM - 1, "Aluno")
                user(MAXIMUM, "Instrutor")
                db.execute("INSERT INTO aluno (id,usuario_id) VALUES (?,?)", (MAXIMUM, MAXIMUM - 1))
                db.execute("INSERT INTO instrutor (id,usuario_id) VALUES (?,?)", (MAXIMUM, MAXIMUM))
                db.commit()
                previous = db.execute("SELECT * FROM aluno ORDER BY id").fetchall()
                db.executescript((ROOT / "migrations/005_aluno_instrutor.sql").read_text(encoding="utf-8"))
                assert db.execute("SELECT id,usuario_id,criado_em FROM aluno ORDER BY id").fetchall() == previous
                assert db.execute("SELECT instrutor_id FROM aluno").fetchall() == [(None,)] * len(previous)
                assert db.execute("PRAGMA foreign_keys").fetchone() == (1,)
                column = next(row for row in db.execute("PRAGMA table_info(aluno)") if row[1] == "instrutor_id")
                assert column[3] == 0 and column[4] is None
                assert any(row[2:7] == ("instrutor", "instrutor_id", "id", "RESTRICT", "RESTRICT")
                           for row in db.execute("PRAGMA foreign_key_list(aluno)"))

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
            path = f"/api/alunos/{LARGE}/instrutor"
            admin = anonymous

            def state():
                return sql("SELECT id,instrutor_id FROM aluno ORDER BY id")

            def request(method, url, body=None, expected=200, client=None, content_type="application/json"):
                nonlocal checked
                snapshot = state()
                data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(base + url, method=method, data=data,
                                             headers={"Content-Type": content_type})
                try:
                    response = (client or admin).open(req, timeout=20)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read()
                    safe(content)
                    payload = json.loads(content)
                    safe(json.dumps(payload, ensure_ascii=False).encode())
                    assert response.code == expected, (method, url, response.code, expected, payload)
                    assert "application/json" in response.headers.get("Content-Type", "")
                    if url.split("?")[0].endswith("/instrutor"):
                        assert response.headers.get("Cache-Control") == "no-store"
                    if response.code >= 400:
                        assert set(payload) in ({"erro"}, {"message"})
                        assert state() == snapshot, "Rejected request changed relationship"
                    checked += 1
                    return payload

            def login(user_id=100, academy=1):
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                request("POST", "/api/auth/login", {"academia_id": academy,
                    "email": f"u{user_id}@example.test", "senha": PASSWORD}, client=client)
                return client

            def put(instructor=LARGE, expected=200, client=None, url=path):
                result = request("PUT", url, {"instrutor_id": instructor}, expected, client)
                if expected == 200:
                    assert result == {"instrutor_id": instructor}
                    student = int(url.split("/")[3])
                    assert sql("SELECT instrutor_id FROM aluno WHERE id=?", (student,)) == [(instructor,)]
                return result

            with (directory / "server.log").open("w+b") as log:
                server = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory, env=env,
                    stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                primary_error = None
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
                        raise RuntimeError("Isolated server startup timed out")

                    forged = urllib.request.build_opener()
                    forged.addheaders = [("Cookie", "JSESSIONID=TH30-invalid-session")]
                    for client in [anonymous, forged]:
                        request("GET", path, expected=401, client=client)
                        put(expected=401, client=client)
                    admin = login()
                    gestor = login(101)
                    admin_b = login(110, 2)
                    gestor_b = login(111, 2)
                    for user_id in [102, 103, 104]:
                        client = login(user_id)
                        request("GET", path, expected=403, client=client)
                        put(expected=403, client=client)
                        request("PUT", path, b"{", 403, client)
                    logged_out = login()
                    request("POST", "/api/auth/logout", client=logged_out)
                    request("GET", path, expected=401, client=logged_out)
                    put(expected=401, client=logged_out)
                    request("POST", "/api/auth/login", {"academia_id": 1,
                        "email": "u100@example.test", "senha": WRONG_PASSWORD}, 401, anonymous)

                    assert request("GET", path) == {"instrutor_id": None}
                    assert request("GET", path, client=gestor) == {"instrutor_id": None}
                    put()
                    assert request("GET", path) == {"instrutor_id": LARGE}
                    put(LARGE + 1, client=gestor)
                    assert request("GET", path, client=gestor) == {"instrutor_id": LARGE + 1}
                    put(LARGE + 1)
                    put(LARGE + 1, url=f"/api/alunos/{LARGE + 1}/instrutor")
                    assert sql("SELECT COUNT(*) FROM aluno WHERE instrutor_id=?", (LARGE + 1,)) == [(2,)]
                    put(1, url="/api/alunos/1/instrutor")
                    put(MAXIMUM, url=f"/api/alunos/{MAXIMUM}/instrutor")
                    assert request("GET", f"/api/alunos/{MAXIMUM}/instrutor") == {"instrutor_id": MAXIMUM}
                    assert set(request("GET", f"/api/alunos/{LARGE}")) == {"id", "usuario_id", "criado_em"}
                    assert all(set(row) == {"id", "usuario_id", "criado_em"}
                               for row in request("GET", "/api/alunos"))

                    for client, outside in [(admin, LARGE + 2), (gestor, LARGE + 2),
                                            (admin_b, LARGE), (gestor_b, LARGE)]:
                        foreign = f"/api/alunos/{outside}/instrutor"
                        request("GET", foreign, expected=404, client=client)
                        put(expected=404, client=client, url=foreign)
                    for client in [admin, gestor]:
                        put(LARGE + 2, 404, client)
                        put(999999, 404, client)
                        request("GET", "/api/alunos/999999/instrutor", expected=404, client=client)
                        put(expected=404, client=client, url="/api/alunos/999999/instrutor")
                    put(LARGE + 2, client=admin_b, url=f"/api/alunos/{LARGE + 2}/instrutor")

                    # All mutations concern target users, never the authenticated actors.
                    for user_id, canonical, wrong, noncanonical in [
                            (200, "Aluno", "Instrutor", "aluno"),
                            (301, "Instrutor", "Aluno", "Instrutor ")]:
                        mutations = [("UPDATE usuario SET ativo=? WHERE id=?", (0, user_id)),
                                     ("UPDATE usuario SET ativo=? WHERE id=?", (2, user_id))]
                        mutations += [("UPDATE usuario SET perfil_id=? WHERE id=?", (profile, user_id))
                                      for profile in [roles[wrong], roles[noncanonical], 999999]]
                        for statement, values in mutations:
                            sql(statement, values)
                            put(LARGE + 1, 400)
                            assert request("GET", path) == {"instrutor_id": LARGE + 1}
                            sql("UPDATE usuario SET ativo=1,perfil_id=? WHERE id=?", (roles[canonical], user_id))
                        sql("UPDATE perfil SET ativo=0 WHERE id=?", (roles[canonical],))
                        put(LARGE + 1, 400)
                        assert request("GET", path) == {"instrutor_id": LARGE + 1}
                        sql("UPDATE perfil SET ativo=1 WHERE id=?", (roles[canonical],))
                    sql("UPDATE usuario SET academia_id=2 WHERE id=301")
                    request("GET", path, expected=404)
                    sql("UPDATE usuario SET academia_id=1 WHERE id=301")
                    sql("UPDATE aluno SET instrutor_id=999999 WHERE id=?", (LARGE,))
                    request("GET", path, expected=404)
                    sql("UPDATE aluno SET instrutor_id=? WHERE id=?", (LARGE + 1, LARGE))

                    invalid_bodies = [None, b"{", b"null", [], 1, "text", {}, {"other": LARGE}]
                    invalid_bodies += [{"instrutor_id": value} for value in
                                       [None, True, False, "1", 1.0, 0, -1, [], {}, 2**63, 2**64]]
                    invalid_bodies += [{"instrutor_id": LARGE, extra: 1} for extra in
                                       ["academia_id", "usuario_id", "ativo", "senha_hash"]]
                    invalid_bodies += [b'{"instrutor_id":1} {}', b'{"instrutor_id":1} null',
                        b'{"instrutor_id":1} garbage', b'{"instrutor_id":1,}',
                        b'{/* comment */"instrutor_id":1}', b'{"instrutor_id":1 // comment\n}']
                    for body in invalid_bodies:
                        request("PUT", path, body, 400)
                    assert request("PUT", path, b' \n {"instrutor_id":1099511627777} \t\r\n') == {
                        "instrutor_id": LARGE + 1}
                    request("PUT", path, {"instrutor_id": LARGE}, 400, content_type="text/plain")
                    for query in ["?academia_id=1", "?academia_id=2", "?acad%65mia_id=1",
                                  "?academia_id=1&academia_id=2", "?x", "?other=1"]:
                        request("GET", path + query, expected=400)
                        put(expected=400, url=path + query)
                    request("GET", path, {"instrutor_id": LARGE}, 400)
                    for invalid in ["0", "-1", "1.0", "true", "1x", "+1", "%201", "1%20",
                                    "9223372036854775808", "1%20OR%201=1"]:
                        url = f"/api/alunos/{invalid}/instrutor"
                        request("GET", url, expected=400)
                        put(expected=400, url=url)

                    # Hold a writer lock so service reads see the old eligible state. Once the
                    # change commits, the blocked UPDATE must recheck both targets and reject it.
                    for statement, values, restore, restored in [
                        ("UPDATE usuario SET ativo=0 WHERE id=?", (200,), "UPDATE usuario SET ativo=1 WHERE id=?", (200,)),
                        ("UPDATE usuario SET ativo=0 WHERE id=?", (300,), "UPDATE usuario SET ativo=1 WHERE id=?", (300,)),
                        ("UPDATE usuario SET academia_id=2 WHERE id=?", (200,), "UPDATE usuario SET academia_id=1 WHERE id=?", (200,)),
                        ("UPDATE usuario SET academia_id=2 WHERE id=?", (300,), "UPDATE usuario SET academia_id=1 WHERE id=?", (300,)),
                        ("UPDATE usuario SET perfil_id=? WHERE id=?", (roles["Instrutor"], 200),
                         "UPDATE usuario SET perfil_id=? WHERE id=?", (roles["Aluno"], 200)),
                        ("UPDATE usuario SET perfil_id=? WHERE id=?", (roles["Aluno"], 300),
                         "UPDATE usuario SET perfil_id=? WHERE id=?", (roles["Instrutor"], 300)),
                        ("UPDATE perfil SET ativo=0 WHERE id=?", (roles["Aluno"],),
                         "UPDATE perfil SET ativo=1 WHERE id=?", (roles["Aluno"],)),
                        ("UPDATE perfil SET ativo=0 WHERE id=?", (roles["Instrutor"],),
                         "UPDATE perfil SET ativo=1 WHERE id=?", (roles["Instrutor"],)),
                        ("UPDATE academia SET ativo=0 WHERE id=1", (), "UPDATE academia SET ativo=1 WHERE id=1", ()),
                    ]:
                        try:
                            with closing(sqlite3.connect(database, timeout=10)) as writer:
                                writer.execute("BEGIN IMMEDIATE")
                                writer.execute(statement, values)
                                with ThreadPoolExecutor(max_workers=1) as pool:
                                    pending = pool.submit(put, LARGE, 409)
                                    time.sleep(0.6)
                                    writer.commit()
                                    pending.result(timeout=20)
                        finally:
                            sql(restore, restored)

                    with closing(sqlite3.connect(database)) as db:
                        db.execute("PRAGMA foreign_keys=ON")
                        assert db.execute("PRAGMA foreign_keys").fetchone() == (1,)
                        for statement, values in [
                            ("DELETE FROM instrutor WHERE id=?", (LARGE + 1,)),
                            ("UPDATE instrutor SET id=999999 WHERE id=?", (LARGE + 1,)),
                            ("UPDATE aluno SET instrutor_id=999999 WHERE id=?", (LARGE,)),
                        ]:
                            try:
                                db.execute(statement, values)
                            except sqlite3.IntegrityError:
                                db.rollback()
                            else:
                                raise AssertionError("Invalid relationship accepted")
                        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
                    assert sql("SELECT COUNT(*) FROM aluno al JOIN usuario ua ON ua.id=al.usuario_id "
                        "JOIN instrutor i ON i.id=al.instrutor_id JOIN usuario ui ON ui.id=i.usuario_id "
                        "WHERE ua.academia_id<>ui.academia_id") == [(0,)]

                    sql("CREATE TRIGGER lose_instructor BEFORE UPDATE OF instrutor_id ON aluno "
                        "WHEN NEW.instrutor_id=1 BEGIN DELETE FROM instrutor WHERE id=1; END")
                    # Remove the unrelated reference first, only in the fixture, to isolate FK loss.
                    sql("UPDATE aluno SET instrutor_id=NULL WHERE id=1")
                    put(1, 409)
                    assert sql("SELECT id FROM instrutor WHERE id=1") == [(1,)]
                    sql("DROP TRIGGER lose_instructor")
                    for table in ["aluno", "instrutor"]:
                        sql(f"ALTER TABLE {table} RENAME TO {table}_unavailable")
                        try:
                            # state() also needs aluno; bypass the helper only for its schema failure.
                            if table == "aluno":
                                sql("CREATE VIEW aluno AS SELECT * FROM aluno_unavailable")
                                put(expected=500)
                            else:
                                request("GET", path, expected=500)
                                put(expected=500)
                        finally:
                            if table == "aluno":
                                sql("DROP VIEW aluno")
                            sql(f"ALTER TABLE {table}_unavailable RENAME TO {table}")
                        request("GET", "/api/health")
                    sql("UPDATE usuario SET ativo='invalid' WHERE id=300")
                    put(expected=500)
                    sql("UPDATE usuario SET ativo=1 WHERE id=300")
                    invalidated = login()
                    sql("UPDATE usuario SET ativo=0 WHERE id=100")
                    request("GET", path, expected=401, client=invalidated)
                    put(expected=401, client=invalidated)
                    sql("UPDATE usuario SET ativo=1 WHERE id=100")
                    admin = login()
                    sql("UPDATE perfil SET ativo=0 WHERE id=?", (roles["Administrador"],))
                    request("GET", path, expected=403)
                    put(expected=403)
                    sql("UPDATE perfil SET ativo=1 WHERE id=?", (roles["Administrador"],))
                    sql("UPDATE academia SET ativo=0 WHERE id=1")
                    request("GET", path, expected=401)
                    sql("UPDATE academia SET ativo=1 WHERE id=1")
                    # Produce a known generic log entry so log-safety assertions are not vacuous.
                    sql("ALTER TABLE usuario RENAME TO usuario_unavailable")
                    try:
                        request("POST", "/api/auth/login", {"academia_id": 1,
                            "email": "u100@example.test", "senha": WRONG_PASSWORD}, 500, anonymous)
                    finally:
                        sql("ALTER TABLE usuario_unavailable RENAME TO usuario")

                    # Restart only for expiration: short sessions must not affect the role matrix.
                    server.terminate()
                    server.wait(timeout=5)
                    config["app"]["session_timeout"] = 2
                    (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
                    server = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory, env=env,
                        stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    for _ in range(100):
                        try:
                            request("GET", "/api/health", client=anonymous)
                            break
                        except urllib.error.URLError:
                            if server.poll() is not None:
                                raise RuntimeError("Expiry server failed to start")
                            time.sleep(0.1)
                    else:
                        raise RuntimeError("Expiry server startup timed out")
                    expired = login()
                    time.sleep(4)
                    request("GET", path, expected=401, client=expired)
                    put(expected=401, client=expired)
                    request("GET", "/api/health")
                    assert server.poll() is None
                    log.seek(0)
                    assert b"Falha interna ao autenticar usuario." in log.read(), "Controlled log entry missing"
                except BaseException as error:
                    primary_error = error
                    raise
                finally:
                    try:
                        if server.poll() is None:
                            server.terminate()
                        try:
                            server.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            server.kill()
                            server.wait(timeout=5)
                        log.seek(0)
                        safe(log.read())
                    except Exception:
                        if primary_error is None:
                            raise
    finally:
        after = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
        assert before == after, "Development database changed"
    print(f"TH-30 passed: {checked} HTTP checks; incremental migration, real sessions, role matrix, "
          "N:1 persistence, idempotence, tenant isolation, eligibility, historical reads, strict JSON, "
          "int64, conditional-write conflicts, FK RESTRICT, safe errors/logs. Development DB unchanged.")


if __name__ == "__main__":
    run()
