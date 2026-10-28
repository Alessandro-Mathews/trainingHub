"""TH-19 HTTP checks against a temporary database and isolated server."""

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
SERVER = ROOT / "build" / "traininghub.exe"


def run():
    development_db = ROOT / "data" / "traininghub.db"
    before = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    checked = 0
    password = "TH19-test-password"
    hashes = []
    large_id = 2**40
    public_fields = {"id", "academia_id", "perfil_id", "nome", "email", "ativo", "criado_em"}

    try:
        with tempfile.TemporaryDirectory(prefix="th19-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "usuario.db"
            with closing(sqlite3.connect(database)) as db:
                db.executescript((ROOT / "migrations" / "001_initial_schema.sql").read_text(encoding="utf-8"))
                db.executemany("INSERT INTO academia (id, nome, ativo) VALUES (?, ?, ?)",
                               [(1, "A", 1), (2, "B", 1), (3, "Inativa", 0),
                                (4, "Vazia", 1), (large_id, "Grande", 1)])
                db.executemany("INSERT INTO perfil (id, nome, ativo) VALUES (?, ?, ?)",
                               [(1, "Aluno", 1), (2, "Inativo", 0), (5, "Corrida FK", 1),
                                (large_id, "Grande", 1)])
                # Force generated user IDs beyond 32 bits without adding a fixture user.
                db.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('usuario', ?)", (large_id,))
                db.commit()

            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
            config["listeners"] = [{"address": "127.0.0.1", "port": port}]
            config["db_clients"][0]["filename"] = database.as_posix()
            config["db_clients"][0]["connection_number"] = 3
            (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
            base = f"http://127.0.0.1:{port}"
            jar = http.cookiejar.CookieJar()
            auth = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

            def request(method, path, body=None, expected=200, opener=None,
                        content_type="application/json"):
                nonlocal checked
                data = body if isinstance(body, bytes) else (
                    json.dumps(body).encode() if body is not None else None
                )
                req = urllib.request.Request(base + path, data=data, method=method,
                                             headers={"Content-Type": content_type})
                try:
                    response = (opener or urllib.request.build_opener()).open(req, timeout=20)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read()
                    assert response.code == expected, (method, path, response.code, content)
                    payload = json.loads(content)
                    assert b'"senha"' not in content and b'"senha_hash"' not in content
                    assert password.encode() not in content and b"$argon2id$" not in content
                    if response.code >= 400:
                        assert "SELECT " not in str(payload) and "constraint failed" not in str(payload)
                    checked += 1
                    return payload

            def create(overrides=None, expected=201, opener=None):
                body = {"academia_id": 1, "perfil_id": 1, "nome": "Joao Silva",
                        "email": "joao@example.test", "senha": password}
                return request("POST", "/api/usuarios", body | (overrides or {}), expected, opener)

            with (directory / "server.log").open("w+", encoding="utf-8") as log:
                server = subprocess.Popen([str(SERVER)], cwd=directory, env=env,
                                          stdout=log, stderr=log,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    for _ in range(100):
                        try:
                            request("GET", "/api/health")
                            break
                        except urllib.error.URLError:
                            if server.poll() is not None:
                                log.seek(0)
                                raise RuntimeError("Server exited: " + log.read())
                            time.sleep(0.1)
                    else:
                        raise RuntimeError("Isolated server did not start")

                    request("GET", "/api/health/database")
                    request("GET", "/api/academias")
                    request("GET", "/api/perfis")
                    assert request("GET", "/api/usuarios?academia_id=4") == []
                    assert request("GET", "/api/usuarios?academia_id=999") == []
                    saved = create(opener=auth)
                    assert set(saved) == public_fields
                    user_id = saved["id"]
                    assert user_id > 2**32 and saved["ativo"] is True and saved["criado_em"]
                    assert saved["academia_id"] == 1 and saved["perfil_id"] == 1
                    assert saved["nome"] == "Joao Silva" and saved["email"] == "joao@example.test"
                    request("GET", "/api/auth/me", expected=401, opener=auth)

                    with closing(sqlite3.connect(database)) as db:
                        encoded = db.execute("SELECT senha_hash FROM usuario WHERE id = ?", (user_id,)).fetchone()[0]
                        assert encoded.startswith("$argon2id$") and encoded != password
                        hashes.append(encoded)
                    credentials = {"academia_id": 1, "email": saved["email"], "senha": password}
                    context = request("POST", "/api/auth/login", credentials, opener=auth)
                    assert context == {"userId": user_id, "academiaId": 1, "perfilId": 1}
                    assert request("GET", "/api/auth/me", opener=auth) == context
                    request("POST", "/api/auth/logout", opener=auth)
                    request("GET", "/api/auth/me", expected=401, opener=auth)

                    path = f"/api/usuarios/{user_id}"
                    assert request("GET", path + "?academia_id=1") == saved
                    assert request("GET", "/api/usuarios?academia_id=1") == [saved]
                    request("GET", path + "?academia_id=2", expected=404)
                    request("GET", "/api/usuarios/999?academia_id=1", expected=404)
                    for suffix in ["", "?academia_id=", "?academia_id=0", "?academia_id=-1",
                                   "?academia_id=1.0", "?academia_id=true", "?academia_id=1x",
                                   "?academia_id=9223372036854775808", "?academia_id=%201"]:
                        request("GET", "/api/usuarios" + suffix, expected=400)
                        request("GET", path + suffix, expected=400)
                    for invalid_id in ["0", "-1", "1.0", "true", "1x", "9223372036854775808"]:
                        request("GET", f"/api/usuarios/{invalid_id}?academia_id=1", expected=400)

                    for body in [None, b"{", b"null", [], 1, "text", {}]:
                        request("POST", "/api/usuarios", body, expected=400)
                    valid = {"academia_id": 1, "perfil_id": 1, "nome": "A",
                             "email": "a@example.test", "senha": password}
                    for field in valid:
                        request("POST", "/api/usuarios",
                                {key: value for key, value in valid.items() if key != field}, expected=400)
                    for field in ["academia_id", "perfil_id"]:
                        for value in [0, -1, True, 1.0, "1", None, [], {}, 2**63, 2**64]:
                            create({field: value}, expected=400)
                    for field in ["nome", "email", "senha"]:
                        for value in [None, True, 1, [], {}]:
                            create({field: value}, expected=400)
                    for value in ["", " \t\r\n"]:
                        create({"nome": value}, expected=400)
                    for value in ["", "invalid", "@domain", "local@", "a@@b", "a b@c", "a@b\n", "a\0@b"]:
                        create({"email": value}, expected=400)
                    create({"senha": ""}, expected=400)
                    create({"senha_hash": "precomputed"}, expected=400)
                    create({"academia_id": 999}, expected=404)
                    create({"perfil_id": 999}, expected=404)
                    create({"academia_id": 3}, expected=400)
                    create({"perfil_id": 2}, expected=400)

                    create(expected=409)
                    other = create({"academia_id": 2})
                    assert other["academia_id"] == 2
                    assert request("GET", "/api/usuarios?academia_id=2") == [other]
                    # GET scope comes exclusively from the query, never form data.
                    form = "application/x-www-form-urlencoded"
                    for read_path in ["/api/usuarios", path]:
                        request("GET", read_path, b"academia_id=1", expected=400, content_type=form)
                        request("GET", read_path + "?academia_id=9223372036854775808",
                                b"academia_id=1", expected=400, content_type=form)
                    request("GET", path + "?academia_id=2", b"academia_id=1",
                            expected=404, content_type=form)
                    assert request("GET", "/api/usuarios?academia_id=2", b"academia_id=1",
                                   content_type=form) == [other]
                    assert request("GET", path + "?academia_id=1", b"academia_id=2",
                                   content_type=form) == saved
                    assert request("GET", "/api/usuarios?academia_id=1", b"academia_id=2",
                                   content_type=form) == [saved]
                    assert request("GET", "/api/usuarios?other=value&acad%65mia_id=%32") == [other]
                    assert request("GET", path + "?other=value&acad%65mia_id=%31") == saved
                    case = create({"email": "Joao@example.test"})
                    assert case["email"] == "Joao@example.test"
                    # No arbitrary password complexity rule; even a single space is nonempty.
                    create({"email": "short@example.test", "senha": " "})
                    large = create({"academia_id": large_id, "perfil_id": large_id})
                    assert large["academia_id"] == large_id and large["perfil_id"] == large_id
                    assert request("GET", f"/api/usuarios/{large['id']}?academia_id={large_id}") == large
                    assert request("GET", f"/api/usuarios?academia_id={large_id}") == [large]

                    def concurrent_create(_):
                        req = urllib.request.Request(base + "/api/usuarios", method="POST",
                                                     data=json.dumps(valid | {"email": "race@example.test"}).encode(),
                                                     headers={"Content-Type": "application/json"})
                        try:
                            response = urllib.request.urlopen(req, timeout=30)
                        except urllib.error.HTTPError as error:
                            response = error
                        with response:
                            return response.code

                    with ThreadPoolExecutor(max_workers=6) as pool:
                        statuses = list(pool.map(concurrent_create, range(6)))
                    assert sorted(statuses) == [201] + [409] * 5, statuses
                    checked += len(statuses)
                    with closing(sqlite3.connect(database)) as db:
                        assert db.execute("SELECT COUNT(*) FROM usuario WHERE email='race@example.test'").fetchone()[0] == 1
                        # Simulate losing a parent after service validation, inside the INSERT.
                        db.executescript("""
                            CREATE TRIGGER lose_parent BEFORE INSERT ON usuario
                            WHEN NEW.perfil_id = 5 BEGIN
                                DELETE FROM perfil WHERE id = 5;
                            END;
                        """)
                        db.commit()
                    create({"perfil_id": 5, "email": "fk@example.test"}, expected=409)
                    with closing(sqlite3.connect(database)) as db:
                        assert db.execute("SELECT id FROM perfil WHERE id=5").fetchone()
                        assert db.execute("SELECT id FROM usuario WHERE email='fk@example.test'").fetchone() is None
                        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
                        db.execute("DROP TRIGGER lose_parent")
                        db.commit()

                    # Schema-valid values that cannot map to int must not escape async callbacks.
                    for invalid_active in ["invalid", 2**40]:
                        with closing(sqlite3.connect(database)) as db:
                            db.execute("UPDATE usuario SET ativo = ? WHERE id = ?", (invalid_active, user_id))
                            db.commit()
                        request("GET", "/api/usuarios?academia_id=1", expected=500)
                        request("GET", path + "?academia_id=1", expected=500)
                        request("POST", "/api/auth/login", credentials, expected=500)
                        assert server.poll() is None
                        request("GET", "/api/health")
                        request("GET", "/api/health/database")
                    with closing(sqlite3.connect(database)) as db:
                        db.execute("UPDATE usuario SET ativo=1 WHERE id=?", (user_id,))
                        db.execute("UPDATE academia SET ativo='invalid' WHERE id=4")
                        db.commit()
                    create({"academia_id": 4}, expected=500)
                    with closing(sqlite3.connect(database)) as db:
                        db.execute("UPDATE academia SET ativo=1 WHERE id=4")
                        db.execute("UPDATE perfil SET ativo='invalid' WHERE id=5")
                        db.commit()
                    create({"perfil_id": 5}, expected=500)
                    request("GET", "/api/health")
                    with closing(sqlite3.connect(database)) as db:
                        db.execute("UPDATE perfil SET ativo=1 WHERE id=5")
                        db.execute("ALTER TABLE usuario RENAME TO usuario_unavailable")
                        db.commit()
                    request("GET", "/api/usuarios?academia_id=1", expected=500)
                    request("GET", path + "?academia_id=1", expected=500)
                    create({"email": "failure@example.test"}, expected=500)
                    request("GET", "/api/health")
                    request("GET", "/api/health/database")
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
                log.seek(0)
                logs = log.read()
                assert password not in logs and all(encoded not in logs for encoded in hashes)
    finally:
        after = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
        assert before == after, "Development database changed"

    print(f"TH-19 passed: {checked} HTTP checks; registration, validation, tenant scope, 64-bit IDs, "
          "Argon2id, login/me/logout, concurrent UNIQUE, FK race, safe mapping, DB errors and health. "
          "Development DB unchanged.")


if __name__ == "__main__":
    run()
