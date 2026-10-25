"""TH-20 HTTP regression tests. All writes use an isolated temporary database."""

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
SECURITY_TESTS = ROOT / "build" / "security-tests" / "security_tests.exe"


def run():
    development_db = ROOT / "data" / "traininghub.db"
    before = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    encoded = subprocess.check_output(
        [str(SECURITY_TESTS), "--fixture-hash"], env=env, text=True
    ).strip()
    checked = 0

    try:
        with tempfile.TemporaryDirectory(prefix="th20-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "perfil.db"
            with closing(sqlite3.connect(database)) as db:
                db.executescript((ROOT / "migrations" / "001_initial_schema.sql").read_text(encoding="utf-8"))
                db.execute("INSERT INTO academia (id, nome) VALUES (1, 'Academia de teste')")
                db.execute("INSERT INTO perfil (id, nome) VALUES (?, 'Vinculado')", (2**40,))
                db.execute(
                    "INSERT INTO usuario (academia_id, perfil_id, nome, email, senha_hash) "
                    "VALUES (1, ?, 'Teste', 'perfil@example.test', ?)", (2**40, encoded)
                )
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

            def request(method, path, body=None, expected=200, opener=None):
                nonlocal checked
                data = body if isinstance(body, bytes) else (
                    json.dumps(body).encode() if body is not None else None
                )
                req = urllib.request.Request(base + path, data=data, method=method,
                                             headers={"Content-Type": "application/json"})
                client = opener or urllib.request.build_opener()
                try:
                    response = client.open(req, timeout=10)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read()
                    assert response.code == expected, (method, path, response.code, content)
                    checked += 1
                    if response.code == 404 and path.startswith("/perfis"):
                        return None
                    payload = json.loads(content)
                    if response.code >= 400:
                        assert "SELECT " not in str(payload) and "constraint failed" not in str(payload)
                    return payload

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
                                raise RuntimeError("Isolated server exited before startup")
                            time.sleep(0.1)
                    else:
                        raise RuntimeError("Isolated server did not start")

                    request("GET", "/api/health/database")
                    request("GET", "/api/academias")
                    request("GET", "/perfis", expected=404)
                    request("GET", "/perfis/1", expected=404)
                    initial = request("GET", "/api/perfis")
                    assert len(initial) == 1 and initial[0]["id"] == 2**40
                    created = request("POST", "/api/perfis", {"nome": "Aluno"}, expected=201)
                    perfil_id = created["id"]
                    path = f"/api/perfis/{perfil_id}"
                    current = request("GET", path)
                    assert current["nome"] == "Aluno" and current["descricao"] is None
                    assert current["ativo"] == 1 and current["criado_em"]
                    assert [p["id"] for p in request("GET", "/api/perfis")] == [2**40, perfil_id]
                    assert request("GET", "/api/perfis/999999", expected=404) == {
                        "erro": "Perfil não encontrado"
                    }
                    request("GET", "/api/perfis/0", expected=400)
                    request("DELETE", "/api/perfis/0", expected=400)
                    request("PUT", "/api/perfis/0",
                            {"nome": "Aluno", "ativo": 1, "descricao": None}, expected=400)

                    invalid = [None, b"{", b"null", [], 1, "text", {}, {"nome": None},
                               {"nome": ""}, {"nome": " \t\n\r"}, {"nome": 5},
                               {"nome": True}, {"nome": []}, {"nome": {}},
                               {"nome": "A", "descricao": 1},
                               {"nome": "A", "descricao": []},
                               {"nome": "A", "descricao": {}},
                               {"nome": "A", "descricao": False}]
                    invalid += [{"nome": "A", "ativo": value}
                                for value in [-1, 2, 7, 1.0, "1", True, None, [], {}, 2**64]]
                    for body in invalid:
                        request("POST", "/api/perfis", body, expected=400)
                        update_body = ({"ativo": 1, "descricao": None} | body
                                       if isinstance(body, dict) else body)
                        request("PUT", path, update_body, expected=400)

                    request("POST", "/api/perfis", {"nome": "Aluno"}, expected=409)
                    # SQLite's existing case-sensitive uniqueness remains unchanged.
                    case_id = request("POST", "/api/perfis", {"nome": "aluno"}, expected=201)["id"]
                    request("PUT", f"/api/perfis/{case_id}",
                            {"nome": "Aluno", "ativo": 1, "descricao": None}, expected=409)

                    full = {"nome": "Aluno atualizado", "ativo": 0, "descricao": "Descrição"}
                    request("PUT", path, full)
                    current = request("GET", path)
                    assert all(current[key] == value for key, value in full.items())
                    request("PUT", path, full)  # Same values must not become 404.
                    for missing in ["nome", "ativo", "descricao"]:
                        request("PUT", path, {k: v for k, v in full.items() if k != missing}, expected=400)
                        current = request("GET", path)
                        assert current["ativo"] == 0 and current["descricao"] == "Descrição"
                    request("PUT", path, full | {"descricao": None})
                    assert request("GET", path)["descricao"] is None
                    request("PUT", path, full | {"descricao": "", "ativo": 1})
                    assert request("GET", path)["descricao"] == ""
                    request("PUT", "/api/perfis/999999", full, expected=404)

                    explicit_null = request("POST", "/api/perfis",
                                            {"nome": "Null", "descricao": None, "ativo": 0}, expected=201)["id"]
                    assert request("GET", f"/api/perfis/{explicit_null}")["descricao"] is None
                    empty_text = request("POST", "/api/perfis",
                                         {"nome": "Empty", "descricao": ""}, expected=201)["id"]
                    assert request("GET", f"/api/perfis/{empty_text}")["descricao"] == ""

                    # A short external write lock must not cause a spurious 500.
                    with closing(sqlite3.connect(database)) as writer:
                        writer.execute("BEGIN IMMEDIATE")
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            pending = pool.submit(request, "POST", "/api/perfis",
                                                  {"nome": "Espera de escrita"}, 201)
                            time.sleep(0.15)
                            writer.commit()
                            pending.result()

                    def concurrent_create(_):
                        req = urllib.request.Request(base + "/api/perfis", method="POST",
                                                     data=b'{"nome":"Concorrente"}',
                                                     headers={"Content-Type": "application/json"})
                        try:
                            with urllib.request.urlopen(req, timeout=10) as response:
                                return response.code
                        except urllib.error.HTTPError as error:
                            with error:
                                return error.code

                    with ThreadPoolExecutor(max_workers=8) as pool:
                        statuses = list(pool.map(concurrent_create, range(8)))
                    assert sorted(statuses) == [201] + [409] * 7, statuses
                    checked += len(statuses)

                    # The server's connections must enforce the FK on DELETE.
                    for _ in range(6):
                        request("DELETE", f"/api/perfis/{2**40}", expected=409)
                    assert request("GET", f"/api/perfis/{2**40}")["nome"] == "Vinculado"
                    with closing(sqlite3.connect(database)) as db:
                        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
                        assert db.execute("SELECT perfil_id FROM usuario").fetchone()[0] == 2**40

                    request("DELETE", path)
                    request("GET", path, expected=404)
                    request("DELETE", path, expected=404)
                    request("DELETE", "/api/perfis/999999", expected=404)

                    jar = http.cookiejar.CookieJar()
                    auth = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
                    request("GET", "/api/auth/me", expected=401, opener=auth)
                    context = request("POST", "/api/auth/login",
                                      {"academia_id": 1, "email": "perfil@example.test",
                                       "senha": "TH24-test-password"}, opener=auth)
                    assert context == {"userId": 1, "academiaId": 1, "perfilId": 2**40}
                    assert request("GET", "/api/auth/me", opener=auth) == context
                    request("POST", "/api/auth/logout", opener=auth)
                    request("GET", "/api/auth/me", expected=401, opener=auth)

                    # Each schema-valid but unmappable row is tested separately.
                    for invalid_active in ["invalid", 1099511627776]:
                        with closing(sqlite3.connect(database)) as db:
                            invalid_id = db.execute(
                                "INSERT INTO perfil (nome, ativo) VALUES (?, ?)",
                                ("Mapeamento inválido", invalid_active)
                            ).lastrowid
                            db.commit()
                        try:
                            for read_path in ["/api/perfis", f"/api/perfis/{invalid_id}"]:
                                assert request("GET", read_path, expected=500) == {
                                    "erro": "Erro interno ao acessar perfis"
                                }
                                assert server.poll() is None, "Mapping error stopped the server"
                                request("GET", "/api/health")
                                request("GET", "/api/health/database")
                        finally:
                            with closing(sqlite3.connect(database)) as db:
                                db.execute("DELETE FROM perfil WHERE id = ?", (invalid_id,))
                                db.commit()
                        request("GET", "/api/perfis")
                        request("GET", f"/api/perfis/{2**40}")

                    with closing(sqlite3.connect(database)) as db:
                        db.execute("ALTER TABLE perfil RENAME TO perfil_unavailable")
                        db.commit()
                    request("GET", "/api/perfis", expected=500)
                    request("GET", path, expected=500)
                    request("POST", "/api/perfis", {"nome": "Falha"}, expected=500)
                    request("PUT", path, full, expected=500)
                    request("DELETE", path, expected=500)
                    request("GET", "/api/health")
                    request("GET", "/api/health/database")
                except Exception:
                    log.flush()
                    log.seek(0)
                    for line in log:
                        if "Falha no banco do modulo Perfil" in line:
                            print(line.rstrip())
                    raise
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
    finally:
        after = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
        assert before == after, "Development database changed"

    print(f"TH-20 passed: {checked} HTTP checks; CRUD, validation, NULL, complete PUT, concurrent UNIQUE, "
          "FK DELETE with pool=3, database errors, health and TH-24. Development DB unchanged.")


if __name__ == "__main__":
    run()
