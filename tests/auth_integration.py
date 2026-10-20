"""Run against an isolated server/database; never write to the development DB."""

import hashlib
from contextlib import closing
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
SECURITY_TESTS = ROOT / "build" / "security-tests" / "security_tests.exe"


def run():
    development_db = ROOT / "data" / "traininghub.db"
    before = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
    if before is not None:
        with closing(sqlite3.connect(development_db.as_uri() + "?mode=ro", uri=True)) as db:
            schema = db.execute("SELECT sql FROM sqlite_master WHERE name = 'usuario'").fetchone()
            assert schema and "UNIQUE (academia_id, email)" in schema[0]
            print("Development schema inspected read-only: usuario has tenant/email uniqueness.")

    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    subprocess.run([str(SECURITY_TESTS)], check=True, env=env)
    encoded = subprocess.check_output(
        [str(SECURITY_TESTS), "--fixture-hash"], text=True, env=env
    ).strip()

    with tempfile.TemporaryDirectory(prefix="th24-", dir=ROOT / "build") as temporary:
        directory = Path(temporary)
        database = directory / "auth.db"
        with closing(sqlite3.connect(database)) as db:
            db.executescript((ROOT / "migrations" / "001_initial_schema.sql").read_text())
            db.executemany("INSERT INTO academia (id, nome) VALUES (?, ?)",
                           [(1, "A"), (2, "B")])
            db.execute("INSERT INTO perfil (id, nome) VALUES (1, 'Teste')")
            db.executemany(
                "INSERT INTO usuario (id, academia_id, perfil_id, nome, email, senha_hash, ativo) "
                "VALUES (?, ?, 1, 'Teste', ?, ?, ?)",
                [(2**40, 1, "shared@example.test", encoded, 1),
                 (2**40 + 1, 2, "shared@example.test", encoded, 1),
                 (3, 1, "inactive@example.test", encoded, 0),
                 (4, 1, "broken@example.test", "invalid-hash", 1)],
            )
            db.commit()

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = json.loads((ROOT / "config.json").read_text())
        config["listeners"] = [{"address": "127.0.0.1", "port": port}]
        config["db_clients"][0]["filename"] = database.as_posix()
        (directory / "config.json").write_text(json.dumps(config))
        base = f"http://127.0.0.1:{port}"
        jar = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        def request(method, path, body=None, expected=200, opener=client):
            data = body if isinstance(body, bytes) else (
                json.dumps(body).encode() if body is not None else None
            )
            req = urllib.request.Request(base + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
            try:
                response = opener.open(req, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                payload = json.loads(response.read())
                assert response.code == expected, (path, response.code, payload)
                if path.startswith("/api/auth/"):
                    assert response.headers.get("Cache-Control") == "no-store"
                    assert not {"senha", "senha_hash", "password", "email"}.intersection(payload)
                return payload, response.headers

        def session_id():
            return next(cookie.value for cookie in jar if cookie.name == "JSESSIONID")

        with (directory / "server.log").open("w+") as log:
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
                            raise RuntimeError("Test server exited before startup")
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Test server did not start")

                request("GET", "/api/health/database")
                request("GET", "/api/academias")
                request("GET", "/api/auth/me", expected=401)
                for body in [None, b"{", [], {},
                             {"academia_id": 1, "email": "a"},
                             {"academia_id": True, "email": "a", "senha": "b"},
                             {"academia_id": 1.0, "email": "a", "senha": "b"},
                             {"academia_id": 2**63, "email": "a", "senha": "b"},
                             {"academia_id": 0, "email": "a", "senha": "b"},
                             {"academia_id": "1", "email": "a", "senha": "b"},
                             {"academia_id": 1, "email": 5, "senha": "b"},
                             {"academia_id": 1, "email": "a", "senha": ""}]:
                    request("POST", "/api/auth/login", body, expected=400)

                credentials = {"academia_id": 1, "email": "shared@example.test",
                               "senha": "TH24-test-password"}
                failures = []
                for override in [{"senha": "wrong"}, {"email": "absent@example.test"},
                                 {"email": "inactive@example.test"}, {"academia_id": 3},
                                 {"email": "broken@example.test"},
                                 {"email": "' OR 1=1 --"}]:
                    payload, _ = request("POST", "/api/auth/login",
                                         credentials | override, expected=401)
                    failures.append(payload)
                assert all(payload == failures[0] for payload in failures)
                request("GET", "/api/auth/me", expected=401)
                old_id = session_id()
                context, headers = request("POST", "/api/auth/login", credentials)
                assert context == {"userId": 2**40, "academiaId": 1, "perfilId": 1}
                assert old_id != session_id()
                cookie = headers.get("Set-Cookie", "")
                assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
                assert request("GET", "/api/auth/me")[0] == context
                anonymous = urllib.request.build_opener()
                request("GET", "/api/auth/me", expected=401, opener=anonymous)

                old_id = session_id()
                context, _ = request("POST", "/api/auth/login",
                                     credentials | {"academia_id": 2})
                assert context == {"userId": 2**40 + 1, "academiaId": 2, "perfilId": 1}
                assert old_id != session_id()
                assert request("GET", "/api/auth/me")[0] == context
                old_id = session_id()
                request("POST", "/api/auth/logout")
                assert old_id != session_id()
                request("GET", "/api/auth/me", expected=401)
                request("POST", "/api/auth/logout")
                request("GET", "/api/auth/me", expected=401)

                with closing(sqlite3.connect(database)) as db:
                    db.execute("DROP TABLE usuario")
                    db.commit()
                request("POST", "/api/auth/login", credentials, expected=500)
                print("HTTP tests passed: validation, tenant isolation, inactive/missing users, "
                      "wrong/malformed hashes, SQL injection, login/me/logout, cookie rotation, "
                      "64-bit IDs, safe responses, DB failure and existing endpoints.")
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
            log.seek(0)
            logs = log.read()
            assert "TH24-test-password" not in logs and encoded not in logs

    after = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
    assert before == after, "Development database changed"
    print("Development database unchanged; temporary test data removed.")


if __name__ == "__main__":
    run()
