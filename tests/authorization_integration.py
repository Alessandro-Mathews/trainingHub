"""TH-25 authorization checks against a new temporary database and server."""

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


def run():
    development = ROOT / "data/traininghub.db"
    before = hashlib.sha256(development.read_bytes()).digest() if development.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    encoded = subprocess.check_output([str(ROOT / "build/security-tests/security_tests.exe"),
                                       "--fixture-hash"], env=env, text=True).strip()
    checked = 0
    try:
        with tempfile.TemporaryDirectory(prefix="th25-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "authorization.db"

            def sql(statement, values=()):
                with closing(sqlite3.connect(database)) as db:
                    db.execute(statement, values)
                    db.commit()

            with closing(sqlite3.connect(database)) as db:
                db.executescript((ROOT / "migrations/001_initial_schema.sql").read_text(encoding="utf-8"))
                # ID 1 deliberately belongs to Aluno; role IDs are not permissions.
                db.execute("INSERT INTO perfil (id, nome) VALUES (1, 'Aluno')")
                db.execute("INSERT INTO perfil (id, nome) VALUES (?, 'Administrador')", (2**40,))
                seed = (ROOT / "migrations/002_canonical_profiles.sql").read_text(encoding="utf-8")
                db.executescript(seed)
                original = db.execute("SELECT id,nome,ativo FROM perfil ORDER BY id").fetchall()
                db.executescript(seed)
                assert db.execute("SELECT id,nome,ativo FROM perfil ORDER BY id").fetchall() == original
                roles = dict(db.execute("SELECT nome,id FROM perfil"))
                for name in ["Desconhecido", "admin", "ADMIN", "administrador", "Administrador "]:
                    roles[name] = db.execute("INSERT INTO perfil (nome) VALUES (?)", (name,)).lastrowid
                db.executemany("INSERT INTO academia (id,nome) VALUES (?,?)", [(1, "A"), (2, "B")])
                actors = {}
                for user_id, name in enumerate(roles, start=10):
                    db.execute("INSERT INTO usuario (id,academia_id,perfil_id,nome,email,senha_hash) "
                               "VALUES (?,1,?,'Teste',?,?)",
                               (user_id, roles[name], name + "@example.test", encoded))
                    actors[name] = user_id
                db.execute("INSERT INTO usuario (id,academia_id,perfil_id,nome,email,senha_hash) "
                           "VALUES (200,2,?,'Outro','other@example.test',?)",
                           (roles["Administrador"], encoded))
                db.commit()

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

            def request(method, path, body=None, expected=200, client=anonymous, raw=False):
                nonlocal checked
                req = urllib.request.Request(base + path, method=method,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={"Content-Type": "application/json"})
                try:
                    response = client.open(req, timeout=20)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read()
                    assert response.code == expected, (method, path, response.code, content)
                    if not raw:
                        assert b'"senha"' not in content and b'"senha_hash"' not in content
                        assert PASSWORD.encode() not in content and encoded.encode() not in content
                        if response.code >= 400:
                            assert not any(token in content for token in [b"SELECT ", b"constraint failed", b"no such table"])
                    checked += 1
                    return content if raw else json.loads(content)

            def login(name="Administrador", academia=1, expected=200, email=None):
                jar = http.cookiejar.CookieJar()
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
                request("POST", "/api/auth/login",
                    {"academia_id": academia, "email": email or name + "@example.test", "senha": PASSWORD},
                    expected, client)
                return client, jar

            with (directory / "server.log").open("w+", encoding="utf-8") as log:
                server = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory, env=env,
                    stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    for _ in range(100):
                        try:
                            request("GET", "/api/health")
                            break
                        except urllib.error.URLError:
                            if server.poll() is not None:
                                raise RuntimeError("Isolated server failed to start")
                            time.sleep(0.1)
                    else:
                        raise RuntimeError("Isolated server startup timed out")

                    protected = [("GET", "/api/auth/me"), ("GET", "/api/academias"),
                        ("GET", "/api/perfis"), ("GET", "/api/perfis/1"), ("POST", "/api/perfis"),
                        ("PUT", "/api/perfis/1"), ("DELETE", "/api/perfis/1"),
                        ("GET", "/api/usuarios?academia_id=1"), ("GET", "/api/usuarios/10?academia_id=1"),
                        ("POST", "/api/usuarios")]
                    for method, path in protected:
                        request(method, path, expected=401)
                    request("GET", "/api/health/database")
                    request("POST", "/api/auth/logout")
                    for path in ["/", "/index.html", "/css/style.css", "/js/app.js", "/js/api.js",
                                 "/js/academias.js", "/vendor/bootstrap/bootstrap.min.css",
                                 "/vendor/bootstrap/bootstrap.bundle.min.js", "/images/traininghub-logo.png"]:
                        assert request("GET", path, raw=True)
                    forged = urllib.request.build_opener()
                    forged.addheaders = [("Cookie", "JSESSIONID=unknown-session")]
                    request("GET", "/api/auth/me", expected=401, client=forged)

                    admin, _ = login()
                    gestor, _ = login("Gestor")
                    assert request("GET", "/api/auth/me", client=admin)["perfilId"] == 2**40
                    assert [a["id"] for a in request("GET", "/api/academias", client=admin)] == [1]
                    other, _ = login(academia=2, email="other@example.test")
                    assert [a["id"] for a in request("GET", "/api/academias", client=other)] == [2]
                    for client in [admin, gestor]:
                        request("GET", "/api/perfis", client=client)
                        request("GET", "/api/perfis/1", client=client)
                        request("GET", "/api/usuarios?academia_id=1", client=client)
                        request("GET", f"/api/usuarios/{actors['Aluno']}?academia_id=1", client=client)
                    for method, path in protected:
                        if path.startswith("/api/perfis") and method != "GET" or path == "/api/academias":
                            request(method, path, expected=403, client=gestor)
                    for name in ["Instrutor", "Aluno", "Desconhecido", "admin", "ADMIN", "administrador", "Administrador "]:
                        client, _ = login(name)
                        request("GET", "/api/auth/me", expected=200 if name in ["Aluno", "Instrutor"] else 403, client=client)
                        for method, path in protected[1:]:
                            request(method, path, expected=403, client=client)

                    # Use fresh actors for the tenant and assignment checks.
                    admin, admin_jar = login()
                    gestor, _ = login("Gestor")
                    for client in [admin, gestor]:
                        request("GET", "/api/usuarios?academia_id=2", expected=403, client=client)
                        request("GET", "/api/usuarios/200?academia_id=1", expected=404, client=client)
                        request("GET", "/api/usuarios/999999?academia_id=1", expected=404, client=client)
                    for query in ["academia_id=1&academia_id=2", "academia_id=2&academia_id=1",
                                  "academia_id=x&academia_id=1", "academia_id=1&acad%65mia_id=1"]:
                        request("GET", "/api/usuarios?" + query, expected=400, client=admin)
                    request("GET", "/api/usuarios?acad%65mia_id=%32", expected=403, client=admin)
                    request("GET", "/api/usuarios?academia_id=9223372036854775808", expected=400, client=admin)
                    body = {"academia_id": 1, "perfil_id": roles["Aluno"], "nome": "Novo",
                            "email": "new@example.test", "senha": PASSWORD}
                    request("POST", "/api/usuarios", body | {"academia_id": 2}, 403, admin)
                    request("POST", "/api/usuarios", body | {"academia_id": 2}, 403, gestor)
                    for client, prefix, allowed in [(admin, "a", ["Gestor", "Instrutor", "Aluno"]),
                                                     (gestor, "g", ["Instrutor", "Aluno"])]:
                        for target in ["Administrador", "Gestor", "Instrutor", "Aluno", "Desconhecido", "admin"]:
                            result = request("POST", "/api/usuarios", body | {"perfil_id": roles[target],
                                "email": prefix + target + "@example.test"}, 201 if target in allowed else 403, client)
                            if target in allowed:
                                assert result["academia_id"] == 1 and result["perfil_id"] == roles[target]

                    # Canonical identities cannot change through ordinary profile management.
                    for name in ["Administrador", "Gestor", "Instrutor", "Aluno"]:
                        path = f"/api/perfis/{roles[name]}"
                        full = {"nome": name, "ativo": 1, "descricao": "Descricao editada"}
                        request("PUT", path, full, client=admin)
                        request("PUT", path, full | {"ativo": 0}, 403, admin)
                        request("PUT", path, full | {"nome": "Outro nome"}, 403, admin)
                        request("DELETE", path, expected=403, client=admin)
                        request("POST", "/api/perfis", {"nome": name}, 403, admin)
                    custom = request("POST", "/api/perfis", {"nome": "Personalizado"}, 201, admin)["id"]
                    request("PUT", f"/api/perfis/{custom}",
                        {"nome": "Gestor", "ativo": 1, "descricao": None}, 403, admin)
                    request("DELETE", f"/api/perfis/{custom}", client=admin)

                    for statement, restore, status in [
                        ("UPDATE usuario SET ativo=0 WHERE id=?", "UPDATE usuario SET ativo=1 WHERE id=?", 401),
                        ("UPDATE usuario SET perfil_id=1 WHERE id=?", "UPDATE usuario SET perfil_id=? WHERE id=?", 401),
                        ("UPDATE usuario SET academia_id=2 WHERE id=?", "UPDATE usuario SET academia_id=1 WHERE id=?", 401),
                    ]:
                        client, _ = login()
                        sql(statement, (actors["Administrador"],))
                        request("GET", "/api/auth/me", expected=status, client=client)
                        request("POST", "/api/auth/logout", client=client)
                        values = (roles["Administrador"], actors["Administrador"]) if "perfil_id=?" in restore else (actors["Administrador"],)
                        sql(restore, values)
                    for table, record_id, status in [("perfil", roles["Administrador"], 403), ("academia", 1, 401)]:
                        client, _ = login()
                        sql(f"UPDATE {table} SET ativo=0 WHERE id=?", (record_id,))
                        request("GET", "/api/auth/me", expected=status, client=client)
                        failed, _ = login(expected=401)
                        request("GET", "/api/auth/me", expected=401, client=failed)
                        request("POST", "/api/auth/logout", client=client)
                        sql(f"UPDATE {table} SET ativo=1 WHERE id=?", (record_id,))

                    # Orphaned references are possible in externally corrupted databases.
                    for column, status in [("perfil_id", 403), ("academia_id", 401)]:
                        sql(f"UPDATE usuario SET {column}=999999 WHERE id=?", (actors["Administrador"],))
                        login(expected=401)
                        # The old session must also deny access if its referenced parent disappears.
                        restore_id = roles["Administrador"] if column == "perfil_id" else 1
                        sql(f"UPDATE usuario SET {column}=? WHERE id=?", (restore_id, actors["Administrador"]))
                        client, _ = login()
                        table = "perfil" if column == "perfil_id" else "academia"
                        sql(f"UPDATE {table} SET id=999999 WHERE id=?", (restore_id,))
                        request("GET", "/api/auth/me", expected=status, client=client)
                        request("POST", "/api/auth/logout", client=client)
                        sql(f"UPDATE {table} SET id=? WHERE id=999999", (restore_id,))

                    client, _ = login()
                    sql("DELETE FROM usuario WHERE id=?", (actors["Administrador"],))
                    request("GET", "/api/auth/me", expected=401, client=client)
                    sql("INSERT INTO usuario (id,academia_id,perfil_id,nome,email,senha_hash) VALUES (?,1,?,'Teste',?,?)",
                        (actors["Administrador"], roles["Administrador"], "Administrador@example.test", encoded))
                    admin, jar = login()
                    old_cookie = next(c.value for c in jar if c.name == "JSESSIONID")
                    request("POST", "/api/auth/logout", client=admin)
                    request("POST", "/api/auth/logout", client=admin)
                    request("GET", "/api/auth/me", expected=401, client=admin)
                    stale = urllib.request.build_opener()
                    stale.addheaders = [("Cookie", "JSESSIONID=" + old_cookie)]
                    request("GET", "/api/auth/me", expected=401, client=stale)
                    for table in ["usuario", "perfil", "academia"]:
                        client, _ = login()
                        sql(f"ALTER TABLE {table} RENAME TO {table}_unavailable")
                        request("GET", "/api/academias", expected=500, client=client)
                        request("POST", "/api/auth/login", {"academia_id": 1,
                            "email": "Administrador@example.test", "senha": PASSWORD}, 500)
                        request("POST", "/api/auth/logout", client=client)
                        request("GET", "/api/health")
                        sql(f"ALTER TABLE {table}_unavailable RENAME TO {table}")
                    assert server.poll() is None

                    # Only the expiry phase uses a short timeout. Argon2 and slow
                    # CI workers must not expire actors during the access matrix.
                    server.terminate()
                    server.wait(timeout=5)
                    config["app"]["session_timeout"] = 2
                    (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
                    server = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory, env=env,
                        stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    for _ in range(100):
                        try:
                            request("GET", "/api/health")
                            break
                        except urllib.error.URLError:
                            if server.poll() is not None:
                                raise RuntimeError("Expiry server failed to start")
                            time.sleep(0.1)
                    else:
                        raise RuntimeError("Expiry server startup timed out")
                    expired, _ = login()
                    time.sleep(4)
                    request("GET", "/api/auth/me", expected=401, client=expired)
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
    print(f"TH-25 passed: {checked} HTTP checks; role matrix, assignment, canonical profiles, tenant isolation, "
          "revalidation, login/logout, expiry, public assets, database failures; development DB unchanged.")


if __name__ == "__main__":
    run()
