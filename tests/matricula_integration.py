"""TH-37: historical contracts through real HTTP, using disposable SQLite only."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
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
FIELDS = ["id", "academia_id", "aluno_id", "plano_id", "nome_plano_contratado",
          "valor_contratado_centavos", "duracao_contratada_dias", "data_inicio", "data_fim", "criado_em"]
PERSISTED_FIELDS = FIELDS + ["cancelado_em"]
PUBLIC_FIELDS = PERSISTED_FIELDS + ["situacao"]
REQUIRED_DATES = ["data_inicio", "data_fim", "criado_em"]
VALID = {"aluno_id": 500, "plano_id": 600}


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
                    (b"select ", b"insert ", b"sqlite", b"constraint", b"schema", b"traceback", b".db", b"c:\\")), "Internal detail exposed"

        with tempfile.TemporaryDirectory(prefix="th37-", dir=ROOT / "build") as temporary:
            directory = Path(temporary)
            database = directory / "matricula.db"

            def sql(statement, values=()):
                with closing(sqlite3.connect(database, timeout=10)) as db:
                    rows = db.execute(statement, values).fetchall()
                    db.commit()
                    return rows

            with closing(sqlite3.connect(database)) as db:
                for migration in sorted((ROOT / "migrations").glob("*.sql")):
                    if migration.name < "007_matricula.sql":
                        db.executescript(migration.read_text(encoding="utf-8"))
                db.execute("UPDATE perfil SET id=id+?", (LARGE,))
                db.execute("INSERT INTO perfil(nome) VALUES('TH37 desconhecido')")
                roles = dict(db.execute("SELECT nome,id FROM perfil"))
                db.executemany("INSERT INTO academia(id,nome) VALUES(?,?)", [(1, "A"), (2, "B"), (LARGE, "Grande")])
                for identity, role, tenant in [(100, "Administrador", 1), (101, "Gestor", 1),
                        (102, "Instrutor", 1), (103, "Aluno", 1), (104, "TH37 desconhecido", 1),
                        (110, "Administrador", 2), (111, "Gestor", 2), (120, "Administrador", LARGE),
                        (200, "Aluno", 1), (201, "Aluno", 1), (300, "Aluno", 2), (LARGE, "Aluno", LARGE)]:
                    db.execute("INSERT INTO usuario(id,academia_id,perfil_id,nome,email,senha_hash) VALUES(?,?,?,'TH37',?,?)",
                        (identity, tenant, roles[role], f"u{identity}@example.test", encoded))
                db.executemany("INSERT INTO aluno(id,usuario_id) VALUES(?,?)",
                               [(500, 200), (501, 201), (503, 103), (700, 300), (MAXIMUM, LARGE)])
                db.executemany("INSERT INTO plano(id,academia_id,nome,valor_centavos,duracao_dias) VALUES(?,?,?,?,?)",
                    [(600, 1, "Mensal", 9990, 30), (800, 2, "Mensal B", 5000, 30)])
                db.commit()
                tables = ("academia", "perfil", "usuario", "aluno", "instrutor", "plano")
                previous = {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
                db.executescript((ROOT / "migrations/007_matricula.sql").read_text(encoding="utf-8"))
                assert previous == {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
                assert [column[1] for column in db.execute("PRAGMA table_info(matricula)")] == FIELDS
                # An existing TH-37 row must survive the additive lifecycle migration unchanged.
                db.execute("INSERT INTO matricula(academia_id,aluno_id,plano_id,nome_plano_contratado,"
                           "valor_contratado_centavos,duracao_contratada_dias,data_inicio,data_fim) "
                           "VALUES(1,500,600,'Legado',0,1,'2020-01-01 00:00:00','2020-01-02 00:00:00')")
                legacy = db.execute("SELECT * FROM matricula").fetchall()
                db.commit()
                for migration in sorted((ROOT / "migrations").glob("*.sql")):
                    if migration.name > "007_matricula.sql":
                        db.executescript(migration.read_text(encoding="utf-8"))
                assert db.execute("SELECT " + ",".join(FIELDS) + " FROM matricula").fetchall() == legacy
                assert db.execute("SELECT cancelado_em FROM matricula").fetchall() == [(None,)]
                assert previous == {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
                # Remove only the migration probe so original empty-history checks remain intact.
                db.execute("DELETE FROM matricula")
                db.commit()
            columns = sql("PRAGMA table_info(matricula)")
            assert [column[1] for column in columns] == PERSISTED_FIELDS
            assert columns[-1][2:5] == ("DATETIME", 0, None)
            assert not sql("SELECT name FROM sqlite_master WHERE type='trigger'")
            assert {(row[2], row[3], row[5], row[6]) for row in sql("PRAGMA foreign_key_list(matricula)")} == {
                ("academia", "academia_id", "RESTRICT", "RESTRICT"),
                ("aluno", "aluno_id", "RESTRICT", "RESTRICT"), ("plano", "plano_id", "RESTRICT", "RESTRICT")}
            indices = sql("PRAGMA index_list(matricula)")
            assert {row[1] for row in indices} == {"idx_matricula_academia_id", "idx_matricula_aluno_academia", "idx_matricula_plano_id"}
            assert all(row[2] == 0 for row in indices), "Commercial uniqueness must not exist"

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
                    return sql("SELECT * FROM matricula ORDER BY id")
                except sqlite3.OperationalError:
                    return None  # Controlled missing-table scenario only.

            def request(method, path, body=None, expected=200, client=None, content_type="application/json"):
                nonlocal checked
                previous = snapshot() if expected >= 400 else None
                data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(base + path, method=method, data=data,
                                             headers={"Content-Type": content_type} if content_type else {})
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
                    if "matriculas" in path:
                        assert response.headers.get("Cache-Control") == "no-store"
                    if response.code >= 400:
                        assert set(payload) in ({"erro"}, {"message"})
                        if previous is not None:
                            assert snapshot() == previous, "Rejected request changed contracts"
                    checked += 1
                    return payload

            def login(identity, tenant=1):
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                context = request("POST", "/api/auth/login", {"academia_id": tenant,
                    "email": f"u{identity}@example.test", "senha": PASSWORD}, client=client)
                assert context["userId"] == identity and context["academiaId"] == tenant
                return client

            def persisted(value):
                assert set(value) == set(PUBLIC_FIELDS)
                assert all(type(value[key]) is int for key in FIELDS[:4] + FIELDS[5:7])
                assert all(value[key] > 0 for key in FIELDS[:4])
                assert value["valor_contratado_centavos"] >= 0
                start, end, created = [datetime.strptime(value[key], "%Y-%m-%d %H:%M:%S") for key in REQUIRED_DATES]
                assert end - start == timedelta(days=value["duracao_contratada_dias"])
                assert created == start and end > start
                if value["cancelado_em"] is not None:
                    cancelled = datetime.strptime(value["cancelado_em"], "%Y-%m-%d %H:%M:%S")
                    assert start <= cancelled < end
                    assert value["situacao"] == "CANCELADA"
                else:
                    assert value["situacao"] in ("ATIVA", "INATIVA")
                assert sql("SELECT " + ",".join(PERSISTED_FIELDS) + " FROM matricula WHERE id=?", (value["id"],)) == [tuple(value[key] for key in PERSISTED_FIELDS)]

            def create(body=None, client=None, tenant=1):
                body = VALID if body is None else body
                plan = sql("SELECT nome,valor_centavos,duracao_dias FROM plano WHERE id=?", (body["plano_id"],))[0]
                start = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
                value = request("POST", "/api/matriculas", body, 201, client)
                end = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
                persisted(value)
                assert value["situacao"] == "ATIVA" and value["cancelado_em"] is None
                assert start <= datetime.strptime(value["data_inicio"], "%Y-%m-%d %H:%M:%S") <= end
                assert value["academia_id"] == tenant and value["aluno_id"] == body["aluno_id"] and value["plano_id"] == body["plano_id"]
                assert tuple(value[key] for key in FIELDS[4:7]) == plan
                return value

            def historical(value, client=None):
                assert request("GET", f'/api/matriculas/{value["id"]}', client=client) == value
                assert value in request("GET", "/api/matriculas", client=client)
                assert value in request("GET", f'/api/alunos/{value["aluno_id"]}/matriculas', client=client)
                persisted(value)

            with (directory / "server.log").open("w+b") as log:
                server = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory, env=env,
                    stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    for _ in range(100):
                        assert server.poll() is None, "Server exited during startup"
                        try:
                            with anonymous.open(base + "/api/health", timeout=1) as response:
                                if response.code == 200:
                                    break
                        except (urllib.error.URLError, TimeoutError):
                            time.sleep(0.05)
                    else:
                        raise AssertionError("Server did not become ready")
                    admin = login(100)
                    gestor, instructor, aluno, unknown = [login(identity) for identity in (101, 102, 103, 104)]
                    admin_b, gestor_b, admin_large = login(110, 2), login(111, 2), login(120, LARGE)
                    assert request("GET", "/api/matriculas") == []
                    assert request("GET", "/api/alunos/501/matriculas") == []
                    first = create()
                    second = create(client=gestor)
                    assert first["id"] != second["id"]
                    foreign = create({"aluno_id": 700, "plano_id": 800}, admin_b, 2)
                    create({"aluno_id": 700, "plano_id": 800}, gestor_b, 2)
                    own = create({"aluno_id": 503, "plano_id": 600})
                    for client in (admin, gestor):
                        historical(first, client)
                    for client in (admin_b, gestor_b):
                        historical(foreign, client)
                    for tenant, client in ((1, admin), (2, admin_b)):
                        values = request("GET", "/api/matriculas", client=client)
                        assert [value["id"] for value in values] == [row[0] for row in sql("SELECT id FROM matricula WHERE academia_id=? ORDER BY id", (tenant,))]
                        assert all(value["academia_id"] == tenant for value in values)
                    for client in (admin, admin_b):
                        missing = request("POST", "/api/matriculas", {"aluno_id": 9999, "plano_id": 9999}, 404, client)
                        for body in ({"aluno_id": 500, "plano_id": 800}, {"aluno_id": 700, "plano_id": 600},
                                     {"aluno_id": 500, "plano_id": 9999}, {"aluno_id": 9999, "plano_id": 600},
                                     {"aluno_id": 700, "plano_id": 800} if client is admin else VALID):
                            assert request("POST", "/api/matriculas", body, 404, client) == missing
                        external = foreign if client is admin else first
                        assert request("GET", f'/api/matriculas/{external["id"]}', expected=404, client=client) == request("GET", "/api/matriculas/9999", expected=404, client=client)
                        assert request("GET", f'/api/alunos/{external["aluno_id"]}/matriculas', expected=404, client=client) == request("GET", "/api/alunos/9999/matriculas", expected=404, client=client)
                    request("POST", "/api/matriculas", VALID | {"aluno_id": 200}, 404)  # Usuario.id is not Aluno.id.

                    routes = [("POST", "/api/matriculas", VALID), ("GET", "/api/matriculas", None),
                              ("GET", f'/api/matriculas/{own["id"]}', None), ("GET", "/api/alunos/503/matriculas", None)]
                    cancellation_path = f'/api/matriculas/{own["id"]}/cancelamento'
                    forged = urllib.request.build_opener()
                    forged.addheaders = [("Cookie", "JSESSIONID=TH37-forged-session")]
                    for client, expected in ((instructor, 403), (aluno, 403), (unknown, 403), (anonymous, 401), (forged, 401)):
                        for method, path, body in routes:
                            request(method, path, body, expected, client)
                            request(method, path + "?academia_id=2", b"{invalid", expected, client)
                        request("PUT", cancellation_path, expected=expected, client=client)
                        request("PUT", cancellation_path + "?academia_id=2", b"{invalid", expected, client)

                    for field in ("aluno_id", "plano_id"):
                        request("POST", "/api/matriculas", {key: value for key, value in VALID.items() if key != field}, 400)
                        for value in (0, -1, 1.0, "500", True, False, None, [], {}, 2**63, 2**64):
                            request("POST", "/api/matriculas", VALID | {field: value}, 400)
                    for body in ({}, [], None, True, 1, "invalid", b"", b"{", b'{} {}',
                                 b'{"aluno_id":500,"plano_id":600,}', b'{/* comment */"aluno_id":500,"plano_id":600}',
                                 b'{"aluno_id":500,"plano_id":600} false', b'{"aluno_id":500,"aluno_id":501,"plano_id":600}'):
                        request("POST", "/api/matriculas", body, 400)
                    for field in ("academia_id", "academiaId", "nome_plano_contratado", "valor_contratado_centavos",
                                  "duracao_contratada_dias", "data_inicio", "data_fim", "criado_em", "cancelado_em", "situacao", "ativo", "id", "extra"):
                        request("POST", "/api/matriculas", VALID | {field: 1}, 400)
                    for content_type in ("text/plain", "application/x-www-form-urlencoded", "application/xml"):
                        request("POST", "/api/matriculas", VALID, 400, content_type=content_type)
                    value = request("POST", "/api/matriculas", VALID, 201, content_type="application/json; charset=utf-8")
                    persisted(value)
                    request("POST", "/api/matriculas?academia_id=2", VALID, 400)
                    for _, path, _ in routes[1:]:
                        request("GET", path + "?id=1", expected=400)
                        request("GET", path, {}, 400)
                    for identity in ("0", "-1", "1.0", "abc", "1x", "%2B1", "%201", str(2**63), str(2**64)):
                        request("GET", f"/api/matriculas/{identity}", expected=400)
                        request("GET", f"/api/alunos/{identity}/matriculas", expected=400)

                    # Historical snapshots survive changes through the existing Plano API.
                    request("PUT", "/api/planos/600", {"nome": "Mensal Novo", "valor_centavos": 12990, "duracao_dias": 45})
                    historical(first)
                    updated = create()
                    assert updated["duracao_contratada_dias"] == 45
                    request("PUT", "/api/planos/600/status", {"ativo": False})
                    request("POST", "/api/matriculas", VALID, 400)
                    historical(first)
                    request("PUT", "/api/planos/600/status", {"ativo": True})
                    for statement, values, restore, original in [
                        ("UPDATE usuario SET ativo=? WHERE id=200", (0,), "UPDATE usuario SET ativo=? WHERE id=200", (1,)),
                        ("UPDATE usuario SET perfil_id=? WHERE id=200", (roles["Instrutor"],), "UPDATE usuario SET perfil_id=? WHERE id=200", (roles["Aluno"],)),
                        ("UPDATE perfil SET ativo=0 WHERE id=?", (roles["Aluno"],), "UPDATE perfil SET ativo=1 WHERE id=?", (roles["Aluno"],)),
                        ("UPDATE usuario SET perfil_id=? WHERE id=200", (99999,), "UPDATE usuario SET perfil_id=? WHERE id=200", (roles["Aluno"],)),
                        ("UPDATE perfil SET nome='aluno' WHERE id=?", (roles["Aluno"],), "UPDATE perfil SET nome='Aluno' WHERE id=?", (roles["Aluno"],))]:
                        sql(statement, values)
                        try:
                            request("POST", "/api/matriculas", VALID, 400)
                            historical(first)
                        finally:
                            sql(restore, original)
                    extreme = request("POST", "/api/planos", {"nome": "Extremo", "valor_centavos": 0, "duracao_dias": MAXIMUM}, 201)
                    request("POST", "/api/matriculas", VALID | {"plano_id": extreme["id"]}, 400)

                    # Out-of-band parent tenant changes must not expose inconsistent history.
                    for statement, restore in (("UPDATE plano SET academia_id=2 WHERE id=600", "UPDATE plano SET academia_id=1 WHERE id=600"),
                                               ("UPDATE usuario SET academia_id=2 WHERE id=200", "UPDATE usuario SET academia_id=1 WHERE id=200")):
                        sql(statement)
                        try:
                            request("GET", f'/api/matriculas/{first["id"]}', expected=404)
                            assert first not in request("GET", "/api/matriculas")
                            if "plano" in statement:
                                assert request("GET", "/api/alunos/500/matriculas") == []
                            else:
                                request("GET", "/api/alunos/500/matriculas", expected=404)
                                assert request("GET", "/api/alunos/500/matriculas", client=admin_b) == []
                        finally:
                            sql(restore)

                    # Both simultaneous, otherwise valid contracts are intentionally accepted.
                    barrier = threading.Barrier(2)

                    def concurrent_create(client):
                        barrier.wait(timeout=10)
                        return create(client=client)

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        pair = list(pool.map(concurrent_create, (admin, gestor)))
                    assert pair[0]["id"] != pair[1]["id"]
                    for value in pair:
                        historical(value)

                    # A deterministic FK failure after prevalidation exercises 409 and rollback.
                    conflict = request("POST", "/api/planos", {"nome": "Conflito FK", "valor_centavos": 0, "duracao_dias": 1}, 201)
                    sql(f'CREATE TRIGGER th37_fk BEFORE INSERT ON matricula WHEN NEW.plano_id={conflict["id"]} BEGIN DELETE FROM plano WHERE id=NEW.plano_id; END')
                    try:
                        request("POST", "/api/matriculas", VALID | {"plano_id": conflict["id"]}, 409)
                        assert sql("SELECT id FROM plano WHERE id=?", (conflict["id"],)) == [(conflict["id"],)]
                    finally:
                        sql("DROP TRIGGER th37_fk")

                    def rejected_sql(statement, values=()):
                        previous = snapshot()
                        with closing(sqlite3.connect(database)) as db:
                            db.execute("PRAGMA foreign_keys=ON")
                            try:
                                db.execute(statement, values)
                            except sqlite3.IntegrityError:
                                db.rollback()
                            else:
                                raise AssertionError("Invalid SQL write accepted")
                        assert snapshot() == previous

                    baseline = [1, 500, 600, "Contrato", 0, 30, "2026-01-01 00:00:00", "2026-01-31 00:00:00"]
                    insert = "INSERT INTO matricula(" + ",".join(FIELDS[1:9]) + ") VALUES(?,?,?,?,?,?,?,?)"
                    for index, value in ((0, 9999), (1, 9999), (2, 9999), (4, -1), (4, 1.5), (5, 0), (5, -1), (5, 1.5),
                                         (6, "invalid"), (6, None), (7, None), (7, "invalid"), (7, baseline[6]), (7, "2025-01-01 00:00:00")):
                        values = baseline.copy()
                        values[index] = value
                        rejected_sql(insert, values)
                    for table, identity in (("academia", 1), ("aluno", 500), ("plano", 600)):
                        rejected_sql(f"DELETE FROM {table} WHERE id=?", (identity,))
                        rejected_sql(f"UPDATE {table} SET id=900000 WHERE id=?", (identity,))
                    assert sql("PRAGMA foreign_key_check") == []

                    # Lifecycle fixtures use controlled SQLite dates, never expiration sleeps.
                    def lifecycle_fixture(start, end, cancelled=None):
                        identity = sql("INSERT INTO matricula(academia_id,aluno_id,plano_id,nome_plano_contratado,"
                            "valor_contratado_centavos,duracao_contratada_dias,data_inicio,data_fim,criado_em,cancelado_em) "
                            "VALUES(1,500,600,'Historico controlado',0,1,?,?,?,?) RETURNING id",
                            (start, end, start, cancelled))
                        return request("GET", f'/api/matriculas/{identity[0][0]}')

                    # Nullable canonical timestamps and both inclusive/exclusive cancellation bounds.
                    for invalid in ("", "invalid", "2026-01-15T00:00:00", "2026-01-15 00:00:00Z",
                                    "2026-01-15 00:00:00.000", "2026-01-15 25:00:00",
                                    "2025-12-31 23:59:59", "2026-01-31 00:00:00", "2026-02-01 00:00:00"):
                        rejected_sql("INSERT INTO matricula(" + ",".join(FIELDS[1:9]) + ",cancelado_em) VALUES(?,?,?,?,?,?,?,?,?)",
                                     baseline + [invalid])

                    expired_start, expired_end, future_start, future_end = sql(
                        "SELECT datetime('now','-2 days'),datetime('now','-1 day'),"
                        "datetime('now','+1 day'),datetime('now','+2 days')")[0]
                    expired = lifecycle_fixture(expired_start, expired_end)
                    future = lifecycle_fixture(future_start, future_end)
                    cancelled_past = lifecycle_fixture(expired_start, expired_end, expired_start)
                    for value in (expired, future):
                        assert value["situacao"] == "INATIVA" and value["cancelado_em"] is None
                        historical(value)
                        request("PUT", f'/api/matriculas/{value["id"]}/cancelamento', expected=409)
                    assert cancelled_past["situacao"] == "CANCELADA"
                    historical(cancelled_past)
                    request("PUT", f'/api/matriculas/{cancelled_past["id"]}/cancelamento', expected=409)

                    for client, external in ((admin, foreign), (admin_b, first)):
                        missing = request("PUT", "/api/matriculas/9999/cancelamento", expected=404, client=client)
                        assert request("PUT", f'/api/matriculas/{external["id"]}/cancelamento',
                                       expected=404, client=client) == missing
                    for identity in ("0", "-1", "1.0", "abc", "1x", "%2B1", "%201", str(2**63), str(2**64)):
                        request("PUT", f"/api/matriculas/{identity}/cancelamento", expected=400)
                    for body in ({}, [], None, True, 1, "invalid", b" ", b"{", {"cancelado_em": expired_start},
                                 {"situacao": "CANCELADA"}, {"academia_id": 2}, {"data_fim": expired_end}):
                        # None normally means no body in request(); send literal JSON null here.
                        request("PUT", cancellation_path, b"null" if body is None else body, 400)
                    request("PUT", cancellation_path + "?academia_id=1", expected=400)

                    for client, tenant, body in ((admin, 1, VALID), (gestor, 1, VALID),
                                                 (gestor_b, 2, {"aluno_id": 700, "plano_id": 800})):
                        original = create(body, client, tenant)
                        path = f'/api/matriculas/{original["id"]}/cancelamento'
                        before_cancel = sql("SELECT CURRENT_TIMESTAMP")[0][0]
                        cancelled = request("PUT", path, client=client, content_type=None)
                        after_cancel = sql("SELECT CURRENT_TIMESTAMP")[0][0]
                        assert cancelled["situacao"] == "CANCELADA"
                        assert before_cancel <= cancelled["cancelado_em"] <= after_cancel
                        assert {key: cancelled[key] for key in FIELDS} == {key: original[key] for key in FIELDS}
                        historical(cancelled, client)
                        request("PUT", path, expected=409, client=client)
                        historical(cancelled, client)
                        # Earlier cancelled contracts do not block a new independent contract.
                        create(body, client, tenant)

                    concurrent_original = create()
                    concurrent_path = f'/api/matriculas/{concurrent_original["id"]}/cancelamento'
                    barrier = threading.Barrier(2)

                    def concurrent_cancel(client):
                        barrier.wait(timeout=10)
                        req = urllib.request.Request(base + concurrent_path, method="PUT")
                        try:
                            response = client.open(req, timeout=20)
                        except urllib.error.HTTPError as error:
                            response = error
                        with response:
                            content = response.read()
                            safe(content, response.code >= 400)
                            assert response.headers.get("Cache-Control") == "no-store"
                            return response.code, json.loads(content)

                    previous_count = len(snapshot())
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(concurrent_cancel, (admin, gestor)))
                    assert sorted(status for status, _ in results) == [200, 409]
                    checked += len(results)
                    winner = next(value for status, value in results if status == 200)
                    assert len(snapshot()) == previous_count
                    assert {key: winner[key] for key in FIELDS} == {key: concurrent_original[key] for key in FIELDS}
                    historical(winner)
                    request("PUT", concurrent_path, expected=409)
                    historical(winner)
                    assert sql("PRAGMA foreign_key_check") == []

                    # Independent fixtures prove full int64 without exhausting IDs prematurely.
                    sql("INSERT INTO plano(id,academia_id,nome,valor_centavos,duracao_dias) VALUES(?,?,'Int64',?,1)", (MAXIMUM, LARGE, MAXIMUM))
                    maximum = create({"aluno_id": MAXIMUM, "plano_id": MAXIMUM}, admin_large, LARGE)
                    assert maximum["valor_contratado_centavos"] == MAXIMUM
                    sql("UPDATE matricula SET id=? WHERE id=?", (MAXIMUM, maximum["id"]))
                    maximum["id"] = MAXIMUM
                    historical(maximum, admin_large)
                    assert request("GET", "/api/alunos/501/matriculas") == []

                    previous = snapshot()
                    sql("ALTER TABLE matricula RENAME TO matricula_unavailable")
                    try:
                        for method, path, body in routes:
                            request(method, path, body, 500)
                        request("PUT", cancellation_path, expected=500)
                    finally:
                        sql("ALTER TABLE matricula_unavailable RENAME TO matricula")
                    assert snapshot() == previous
                    historical(first)
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
    print(f"TH-37/TH-38 passed: {checked} HTTP checks; immutable snapshot, UTC validity, int64, repeated contracts, "
          "four-route role matrix, bidirectional tenant isolation, historical reads, FK/CHECK/RESTRICT, "
          "safe 400/401/403/404/409/500 and isolated SQLite. Development DB unchanged. "
          "Eligibility race window not forced: no deterministic production synchronization hook.")


if __name__ == "__main__":
    run()
