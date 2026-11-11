"""TH-19 HTTP checks against a temporary database and isolated server."""

from auth_fixture import insert_admin, login_client
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
SERVER = ROOT / "build" / "traininghub.exe"


def run():
    development_db = ROOT / "data" / "traininghub.db"
    before = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    checked = 0
    password = "TH19-test-password"
    hashes = []
    encoded_admin = subprocess.check_output([str(ROOT / "build/security-tests/security_tests.exe"), "--fixture-hash"], text=True, env=env).strip()
    large_id = 2**40
    public_fields = {"id", "academia_id", "perfil_id", "nome", "email", "ativo", "criado_em"}
    wrong_password = "TH63-WRONG-PASSWORD-SENTINEL"

    def assert_safe(content, internal=False):
        assert not any(secret in content for secret in [password.encode(), b"TH24-test-password",
            wrong_password.encode(), encoded_admin.encode(), b"$argon2id$", b'"senha_hash"', b'"senha"']), "Credential exposed"
        assert all(encoded.encode() not in content for encoded in hashes), "Password hash exposed"
        if internal:
            assert not any(token in content.lower() for token in [b"select ", b"update ", b"insert ",
                b"sqlite", b"constraint", b"no such", b"traceback", b"schema", b".db", b"c:\\"]), "Internal detail exposed"

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
                               [(1, "Aluno", 1), (2, "Inativo", 0), (5, "Instrutor", 1),
                                (large_id, "Gestor", 1)])
                insert_admin(db, encoded_admin)
                insert_admin(db, encoded_admin, 2, 101)
                insert_admin(db, encoded_admin, large_id, 102)
                insert_admin(db, encoded_admin, 4, 103)
                # Generated user IDs remain beyond 32 bits, independently of actor IDs.
                db.execute("UPDATE sqlite_sequence SET seq=? WHERE name='usuario'", (large_id,))
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

            admin = None

            def request(method, path, body=None, expected=200, opener=None,
                        content_type="application/json", preserve=True):
                nonlocal checked
                snapshot = None
                if preserve and method == "PUT" and path.startswith("/api/usuarios/"):
                    try:
                        target = int(path.split("/")[3].split("?")[0])
                    except ValueError:
                        target = None
                    if target is not None and 0 < target <= 2**63 - 1:
                        with closing(sqlite3.connect(database)) as db:
                            try:
                                snapshot = db.execute("SELECT * FROM usuario WHERE id=?", (target,)).fetchall()
                            except sqlite3.OperationalError:
                                # Controlled schema-failure checks deliberately remove this table.
                                snapshot = None
                data = body if isinstance(body, bytes) else (
                    json.dumps(body).encode() if body is not None else None
                )
                req = urllib.request.Request(base + path, data=data, method=method,
                                             headers={"Content-Type": content_type})
                try:
                    response = (opener or admin or urllib.request.build_opener()).open(req, timeout=20)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read()
                    assert_safe(content, response.code >= 400)
                    assert response.code == expected, (method, path, response.code, content)
                    payload = json.loads(content)
                    assert_safe(json.dumps(payload, ensure_ascii=False).encode(), response.code >= 400)
                    if method == "PUT":
                        assert response.headers.get("Cache-Control") == "no-store"
                        if response.code >= 400 and snapshot is not None:
                            with closing(sqlite3.connect(database)) as db:
                                assert db.execute("SELECT * FROM usuario WHERE id=?", (target,)).fetchall() == snapshot, "Rejected update changed user"
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

            def management_checks():
                nonlocal checked
                def sql(statement, values=()):
                    with closing(sqlite3.connect(database, timeout=10)) as db:
                        rows = db.execute(statement, values).fetchall()
                        db.commit()
                        return rows

                with closing(sqlite3.connect(database)) as db:
                    for migration in ["002_canonical_profiles.sql", "003_aluno.sql", "004_instrutor.sql",
                                      "005_aluno_instrutor.sql"]:
                        db.executescript((ROOT / "migrations" / migration).read_text(encoding="utf-8"))
                    unknown = db.execute("INSERT INTO perfil(nome) VALUES ('TH63 desconhecido')").lastrowid
                    for identity, profile, academy in [(105, large_id, 1), (106, 5, 1), (107, 1, 1),
                            (108, unknown, 1), (1, 1, 1), (500, 1, 1), (501, 5, 1), (502, 1, 1),
                            (503, 1, 2), (504, 2, 1), (large_id, 1, 1), (2**63 - 1, 1, 1)]:
                        db.execute("INSERT INTO usuario(id,academia_id,perfil_id,nome,email,senha_hash) "
                                   "VALUES (?,?,?,'Original',?,?)",
                                   (identity, academy, profile, f"th63-{identity}@example.test", encoded_admin))
                    db.execute("INSERT INTO aluno(id,usuario_id) VALUES (500,500)")
                    db.execute("INSERT INTO instrutor(id,usuario_id) VALUES (501,501)")
                    db.execute("UPDATE aluno SET instrutor_id=501 WHERE id=500")
                    db.commit()

                def row(identity):
                    return sql("SELECT id,academia_id,perfil_id,nome,email,senha_hash,ativo,criado_em "
                               "FROM usuario WHERE id=?", (identity,))[0]

                def login_as(identity, academy=1, expected=200, email=None, secret="TH24-test-password"):
                    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                    request("POST", "/api/auth/login", {"academia_id": academy,
                        "email": email or f"th63-{identity}@example.test", "senha": secret}, expected, client)
                    return client

                def update(identity=500, name="Alterado", email=None, expected=200, client=None, preserve=True):
                    previous = row(identity) if expected == 200 else None
                    payload = request("PUT", f"/api/usuarios/{identity}",
                        {"nome": name, "email": email or f"th63-{identity}@example.test"}, expected, client,
                        preserve=preserve)
                    if expected == 200:
                        saved = row(identity)
                        assert set(payload) == public_fields
                        assert payload["id"] == identity and payload["nome"] == saved[3] == name
                        assert payload["email"] == saved[4] == (email or f"th63-{identity}@example.test")
                        assert all(saved[index] == previous[index] for index in [0, 1, 2, 5, 6, 7]), "Protected field changed"
                    return payload

                def status(identity=500, active=False, expected=200, client=None):
                    previous = row(identity) if expected == 200 else None
                    payload = request("PUT", f"/api/usuarios/{identity}/status", {"ativo": active}, expected, client)
                    if expected == 200:
                        saved = row(identity)
                        assert set(payload) == public_fields and payload["ativo"] is active
                        assert saved[6] == int(active)
                        assert all(saved[index] == previous[index] for index in [0, 1, 2, 3, 4, 5, 7]), "Protected field changed"
                    return payload

                gestor = login_as(105)
                anonymous = urllib.request.build_opener()
                forged = urllib.request.build_opener()
                forged.addheaders = [("Cookie", "JSESSIONID=TH63-invalid")]
                for client, code in [(anonymous, 401), (forged, 401), (login_as(106), 403),
                                     (login_as(107), 403), (login_as(108), 403)]:
                    update(expected=code, client=client)
                    status(expected=code, client=client)
                    request("PUT", "/api/usuarios/500", b"{", code, client)
                for client in [admin, gestor]:
                    update(client=client)
                    update(name="Nome Unicode João", client=client)
                    update(name="Nome Unicode João", email="NewCase@example.test", client=client)
                    update(name="Nome Unicode João", email="NewCase@example.test", client=client)
                    status(client=client)
                    status(client=client)
                    update(name="  Nome preservado  ", client=client)
                    status(active=True, client=client)
                    status(active=True, client=client)
                    update(503, expected=404, client=client)
                    status(503, expected=404, client=client)
                    update(999999, expected=404, client=client)
                    status(999999, expected=404, client=client)
                for identity, client in [(100, admin), (105, gestor)]:
                    current = row(identity)
                    update(identity, "Autoedição", current[4], client=client)
                    status(identity, True, client=client)
                    status(identity, False, 403, client)
                update(email="th63-502@example.test", expected=409)
                update(email="th63-503@example.test")
                update(email="TH63-503@example.test")
                for identity in [1, large_id, 2**63 - 1]:
                    update(identity)
                    status(identity, False)
                    status(identity, True)

                for field in ["academia_id", "perfil_id", "senha", "senha_hash", "password", "id", "criado_em", "ativo", "alias"]:
                    request("PUT", "/api/usuarios/500", {"nome": "A", "email": "a@b", field: 1}, 400)
                for field in ["academia_id", "perfil_id", "senha", "senha_hash", "password", "id", "criado_em", "nome", "email"]:
                    request("PUT", "/api/usuarios/500/status", {"ativo": True, field: 1}, 400)
                for body in [None, b"{", b"null", [], {}, {"nome": "A"}, {"email": "a@b"},
                             b'{"nome":"A","email":"a@b"} {}', b'{"nome":"A","email":"a@b",}',
                             b'{/* comment */"nome":"A","email":"a@b"}',
                             b'{"nome":"A","email":"a@b"} garbage']:
                    request("PUT", "/api/usuarios/500", body, 400)
                for field in ["nome", "email"]:
                    for value in [None, True, 1, [], {}]:
                        request("PUT", "/api/usuarios/500", {"nome": "A", "email": "a@b"} | {field: value}, 400)
                for name in ["", " \t\r\n\f\v"]:
                    update(name=name, expected=400)
                for email in ["", "invalid", "@domain", "local@", "a@@b", " a@b", "a@b ", "a@b\n", "a\0@b"]:
                    request("PUT", "/api/usuarios/500", {"nome": "A", "email": email}, 400)
                for body in [None, b"{", b"null", [], {}, {"ativo": True, "other": 1},
                             b'{"ativo":true} {}', b'{"ativo":true,}', b'{/* comment */"ativo":true}']:
                    request("PUT", "/api/usuarios/500/status", body, 400)
                for value in [0, 1, "true", "false", None, [], {}, 1.0]:
                    request("PUT", "/api/usuarios/500/status", {"ativo": value}, 400)
                for endpoint, body in [("/api/usuarios/500", {"nome": "A", "email": "a@b"}),
                                       ("/api/usuarios/500/status", {"ativo": False})]:
                    request("PUT", endpoint, body, 400, content_type="text/plain")
                    for suffix in ["?academia_id=1", "?academia_id=2", "?acad%65mia_id=1", "?x", "?other=1"]:
                        request("PUT", endpoint + suffix, body, 400)
                for invalid in ["0", "-1", "9223372036854775808", "+1", "%201", "1%20", "1.0", "1x", "text", "true", "null", "1%20OR%201=1"]:
                    request("PUT", f"/api/usuarios/{invalid}", {"nome": "A", "email": "a@b"}, 400)
                    request("PUT", f"/api/usuarios/{invalid}/status", {"ativo": False}, 400)

                # Administrative recovery is independent of the target's current profile eligibility.
                update(504)
                status(504, False)
                status(504, True)
                login_as(504, expected=401)
                original_profile = row(504)[2]
                sql("UPDATE usuario SET perfil_id=999999 WHERE id=504")
                try:
                    update(504)
                    status(504, False)
                    status(504, True)
                    login_as(504, expected=401)
                finally:
                    sql("UPDATE usuario SET perfil_id=? WHERE id=504", (original_profile,))

                old_session = login_as(500, email=row(500)[4])
                update(email="changed-login@example.test")
                login_as(500, expected=401, email="TH63-503@example.test")
                fresh = login_as(500, email="changed-login@example.test")
                request("GET", "/api/auth/me", opener=old_session)
                request("GET", "/api/auth/me", opener=fresh)
                status(active=False)
                login_as(500, expected=401, email="changed-login@example.test")
                request("GET", "/api/auth/me", expected=401, opener=old_session)
                request("GET", "/api/auth/me", expected=401, opener=fresh)
                status(active=True)
                login_as(500, email="changed-login@example.test")
                request("GET", "/api/auth/me", expected=401, opener=old_session)
                login_as(500, expected=401, email="changed-login@example.test", secret=wrong_password)
                logged_out = login_as(500, email="changed-login@example.test")
                request("POST", "/api/auth/logout", opener=logged_out)
                update(expected=401, client=logged_out)
                status(expected=401, client=logged_out)

                history = sql("SELECT * FROM aluno"), sql("SELECT * FROM instrutor")
                for identity in [500, 501]:
                    update(identity)
                    status(identity, False)
                    assert request("GET", "/api/alunos/500/instrutor") == {"instrutor_id": 501}
                    status(identity, True)
                    assert (sql("SELECT * FROM aluno"), sql("SELECT * FROM instrutor")) == history
                assert sql("PRAGMA foreign_key_check") == []

                # Independent sessions and a barrier exercise competing writes without sleeps.
                competitors = [login_client(base), login_as(105)]
                barrier = threading.Barrier(2)

                def competing_email(index):
                    barrier.wait(timeout=10)
                    target = [500, 502][index]
                    req = urllib.request.Request(base + f"/api/usuarios/{target}", method="PUT",
                        data=json.dumps({"nome": "Concorrente", "email": "unique-th63@example.test"}).encode(),
                        headers={"Content-Type": "application/json"})
                    try:
                        response = competitors[index].open(req, timeout=20)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        content = response.read()
                        assert_safe(content, response.code >= 400)
                        assert response.headers.get("Cache-Control") == "no-store"
                        return response.code

                with ThreadPoolExecutor(max_workers=2) as pool:
                    codes = list(pool.map(competing_email, range(2)))
                assert sorted(codes) == [200, 409]
                checked += len(codes)
                assert sql("SELECT COUNT(*) FROM usuario WHERE email='unique-th63@example.test'") == [(1,)]
                barrier = threading.Barrier(2)

                def competing_status(index):
                    barrier.wait(timeout=10)
                    result = request("PUT", "/api/usuarios/500/status", {"ativo": bool(index)}, opener=competitors[index])
                    assert result["ativo"] is bool(index)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    list(pool.map(competing_status, range(2)))
                assert row(500)[6] in (0, 1)
                status(500, True)

                # The external transaction owns the writer slot before the HTTP request starts.
                # Regardless of scheduling, the eventual UPDATE must see the committed new tenant.
                started = threading.Event()
                before_move = row(502)
                with closing(sqlite3.connect(database, timeout=10)) as writer:
                    writer.execute("BEGIN IMMEDIATE")
                    writer.execute("UPDATE usuario SET academia_id=2 WHERE id=502")
                    def moved_target():
                        started.set()
                        return update(502, expected=404, preserve=False)
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pending = pool.submit(moved_target)
                        assert started.wait(timeout=10)
                        writer.commit()
                        pending.result(timeout=20)
                after_move = row(502)
                assert after_move[1] == 2
                assert all(after_move[index] == before_move[index] for index in [0, 2, 3, 4, 5, 6, 7])
                sql("UPDATE usuario SET academia_id=1 WHERE id=502")
                status(502, True)
                print("TH-63 management passed: exact contracts, role/tenant matrix, immutable fields, int64, "
                      "self-deactivation guard, login revalidation, specialized history and concurrent UNIQUE/status/tenant.")

            with (directory / "server.log").open("w+", encoding="utf-8") as log:
                server = subprocess.Popen([str(SERVER)], cwd=directory, env=env,
                                          stdout=log, stderr=log,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                primary_error = None
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

                    admin = login_client(base)
                    admin_b = login_client(base, 2)
                    admin_large = login_client(base, large_id)
                    admin_empty = login_client(base, 4)
                    actor_a = request("GET", "/api/usuarios/100?academia_id=1")
                    actor_b = request("GET", "/api/usuarios/101?academia_id=2", opener=admin_b)
                    actor_large = request("GET", f"/api/usuarios/102?academia_id={large_id}", opener=admin_large)
                    request("GET", "/api/health/database")
                    request("GET", "/api/academias")
                    request("GET", "/api/perfis")
                    request("GET", "/api/usuarios?academia_id=4", expected=403)
                    request("GET", "/api/usuarios?academia_id=999", expected=403)
                    saved = create()
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
                    assert request("GET", "/api/usuarios?academia_id=1") == [actor_a, saved]
                    request("GET", path + "?academia_id=2", expected=403)
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
                    create({"academia_id": 999}, expected=403)
                    create({"perfil_id": 999}, expected=404)
                    create({"academia_id": 3}, expected=403)
                    create({"perfil_id": 2}, expected=400)

                    create(expected=409)
                    other = create({"academia_id": 2}, opener=admin_b)
                    assert other["academia_id"] == 2
                    assert request("GET", "/api/usuarios?academia_id=2", opener=admin_b) == [actor_b, other]
                    # GET scope comes exclusively from the query, never form data.
                    form = "application/x-www-form-urlencoded"
                    for read_path in ["/api/usuarios", path]:
                        request("GET", read_path, b"academia_id=1", expected=400, content_type=form)
                        request("GET", read_path + "?academia_id=9223372036854775808",
                                b"academia_id=1", expected=400, content_type=form)
                    request("GET", path + "?academia_id=2", b"academia_id=1",
                            expected=403, content_type=form)
                    assert request("GET", "/api/usuarios?academia_id=2", b"academia_id=1",
                                   content_type=form, opener=admin_b) == [actor_b, other]
                    assert request("GET", path + "?academia_id=1", b"academia_id=2",
                                   content_type=form) == saved
                    assert request("GET", "/api/usuarios?academia_id=1", b"academia_id=2",
                                   content_type=form) == [actor_a, saved]
                    assert request("GET", "/api/usuarios?other=value&acad%65mia_id=%32", opener=admin_b) == [actor_b, other]
                    assert request("GET", path + "?other=value&acad%65mia_id=%31") == saved
                    case = create({"email": "Joao@example.test"})
                    assert case["email"] == "Joao@example.test"
                    # No arbitrary password complexity rule; even a single space is nonempty.
                    create({"email": "short@example.test", "senha": " "})
                    large = create({"academia_id": large_id, "perfil_id": large_id}, opener=admin_large)
                    assert large["academia_id"] == large_id and large["perfil_id"] == large_id
                    assert request("GET", f"/api/usuarios/{large['id']}?academia_id={large_id}", opener=admin_large) == large
                    assert request("GET", f"/api/usuarios?academia_id={large_id}", opener=admin_large) == [actor_large, large]

                    def concurrent_create(_):
                        req = urllib.request.Request(base + "/api/usuarios", method="POST",
                                                     data=json.dumps(valid | {"email": "race@example.test"}).encode(),
                                                     headers={"Content-Type": "application/json"})
                        try:
                            response = admin.open(req, timeout=30)
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

                    management_checks()

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
                    create({"academia_id": 4}, expected=500, opener=admin_empty)
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
                    request("PUT", "/api/usuarios/500", {"nome": "A", "email": "a@b"}, 500)
                    request("PUT", "/api/usuarios/500/status", {"ativo": False}, 500)
                    request("GET", "/api/health")
                    request("GET", "/api/health/database")
                    log.flush()
                    log.seek(0)
                    assert "Falha interna ao autenticar usuario." in log.read(), "Controlled log entry missing"
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
                        assert_safe(log.read().encode(), internal=True)
                    except Exception:
                        if primary_error is None:
                            raise
    finally:
        after = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
        assert before == after, "Development database changed"

    print(f"TH-19/TH-63 passed: {checked} HTTP checks; registration, management, validation, tenant scope, 64-bit IDs, "
          "Argon2id, login/me/logout, concurrent UNIQUE, FK race, safe mapping, DB errors and health. "
          "Development DB unchanged.")


if __name__ == "__main__":
    run()
