"""TH-21: real HTTP checks with an isolated database; optional Chrome UI checks."""

import argparse
from contextlib import closing
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def run(browser):
    development_db = ROOT / "data" / "traininghub.db"
    before = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    encoded = subprocess.check_output(
        [str(ROOT / "build" / "security-tests" / "security_tests.exe"), "--fixture-hash"],
        env=env, text=True,
    ).strip()
    with tempfile.TemporaryDirectory(prefix="th21-", dir=ROOT / "build") as temporary:
        directory = Path(temporary)
        database = directory / "interface.db"
        with closing(sqlite3.connect(database)) as db:
            db.executescript((ROOT / "migrations" / "001_initial_schema.sql").read_text(encoding="utf-8"))
            db.executemany(
                "INSERT INTO academia (nome, cnpj, email, telefone, ativo) VALUES (?, ?, ?, ?, ?)",
                [("Academia Centro", "12345678000190", "centro@example.test", "(11) 99999-0000", 1),
                 ("Studio Evolução", None, None, None, 0)],
            )
            db.execute("INSERT INTO perfil (id, nome) VALUES (17, 'Administrador')")
            db.execute(
                "INSERT INTO usuario (academia_id, perfil_id, nome, email, senha_hash) "
                "VALUES (1, 17, 'Admin de teste', 'interface@example.test', ?)", (encoded,),
            )
            db.commit()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        config["listeners"] = [{"address": "127.0.0.1", "port": port}]
        config["db_clients"][0]["filename"] = database.as_posix()
        config["app"]["document_root"] = (ROOT / "public").as_posix()
        (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
        base = f"http://127.0.0.1:{port}"
        with (directory / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([str(ROOT / "build" / "traininghub.exe")], cwd=directory,
                                      env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(base + "/api/health", timeout=1):
                            break
                    except (OSError, urllib.error.URLError):
                        if server.poll() is not None:
                            raise RuntimeError("TrainingHub exited before readiness")
                        time.sleep(0.1)
                else:
                    raise RuntimeError("TrainingHub did not start")

                def get(path, opener=None):
                    with (opener or urllib.request.build_opener()).open(base + path, timeout=5) as response:
                        return response.headers.get_content_type(), response.read()

                def expect_status(path, status, opener=None):
                    try:
                        get(path, opener)
                    except urllib.error.HTTPError as error:
                        with error:
                            assert error.code == status, (path, error.code)
                    else:
                        raise AssertionError(f"Expected {status}: {path}")

                jar = http.cookiejar.CookieJar()
                admin = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

                def login():
                    body = {"academia_id": 1, "email": "interface@example.test", "senha": "TH24-test-password"}
                    req = urllib.request.Request(base + "/api/auth/login", method="POST",
                                                 data=json.dumps(body).encode(),
                                                 headers={"Content-Type": "application/json"})
                    with admin.open(req, timeout=10) as response:
                        context = json.loads(response.read())
                        assert context["academiaId"] == 1 and context["perfilId"] == 17

                for path, content_type in [
                    ("/", "text/html"), ("/index.html", "text/html"),
                    ("/css/style.css", "text/css"), ("/js/app.js", "application/javascript"),
                    ("/js/api.js", "application/javascript"), ("/js/academias.js", "application/javascript"),
                    ("/vendor/bootstrap/bootstrap.min.css", "text/css"),
                    ("/vendor/bootstrap/bootstrap.bundle.min.js", "application/javascript"),
                    ("/images/traininghub-logo.png", "image/png"),
                ]:
                    actual, body = get(path)
                    allowed = {content_type, "text/javascript"} if content_type == "application/javascript" else {content_type}
                    assert actual in allowed, (path, actual)
                    assert body, path
                assert json.loads(get("/api/health")[1]) == {"status": "ok", "application": "TrainingHub"}
                assert json.loads(get("/api/health/database")[1]) == {"status": "ok", "database": "connected"}
                expect_status("/api/academias", 401)
                login()
                academias = json.loads(get("/api/academias", admin)[1])
                assert len(academias) == 1 and academias[0]["id"] == 1
                assert set(academias[0]) == {"id", "nome", "cnpj", "email", "telefone", "ativo", "criado_em"}
                assert academias[0]["ativo"] is True
                assert academias[0]["nome"] == "Academia Centro"
                assert all(item["nome"] != "Studio Evolução" for item in academias)
                for path in ["/config.json", "/migrations/001_initial_schema.sql", "/src/main.cpp"]:
                    try:
                        get(path)
                    except urllib.error.HTTPError as error:
                        assert error.code == 404
                    else:
                        raise AssertionError(f"Private file exposed: {path}")
                print("TH-21 HTTP passed: public HTML/assets/MIME/health, anonymous API denial, "
                      "authenticated own-Academia contract, cross-tenant exclusion, private files.", flush=True)
                if browser:
                    chrome = os.environ.get("TH21_CHROME") or shutil.which("google-chrome") or shutil.which("chromium")
                    if not chrome:
                        candidate = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
                        if candidate.exists():
                            chrome = str(candidate)
                    if not chrome:
                        raise RuntimeError("Set TH21_CHROME to an installed Chrome/Chromium executable")
                    browser_env = env | {"TH21_SESSION_ID": next(cookie.value for cookie in jar
                                                                if cookie.name == "JSESSIONID")}
                    subprocess.run(["node", str(ROOT / "tests" / "interface_web.mjs"), base, chrome,
                                    str(directory / "chrome-profile")], env=browser_env, cwd=ROOT, check=True)
                with closing(sqlite3.connect(database)) as db:
                    db.execute("UPDATE academia SET cnpj=NULL, email=NULL, telefone=NULL WHERE id=1")
                    db.commit()
                own = json.loads(get("/api/academias", admin)[1])
                assert len(own) == 1 and all(own[0][field] is None for field in ["cnpj", "email", "telefone"])
                with closing(sqlite3.connect(database)) as db:
                    db.execute("UPDATE academia SET ativo=0 WHERE id=1")
                    db.commit()
                expect_status("/api/academias", 401, admin)
                # An authenticated tenant always has an active Academia. Missing or
                # inactive tenants now return 401; empty UI rendering is tested in CDP.
                with closing(sqlite3.connect(database)) as db:
                    db.execute("UPDATE academia SET ativo=1 WHERE id=1")
                    db.commit()
                login()
                with closing(sqlite3.connect(database)) as db:
                    db.execute("DELETE FROM academia WHERE id=1")
                    db.commit()
                expect_status("/api/academias", 401, admin)
                print("TH-21 NULL contract and inactive/missing tenant denial passed; "
                      "empty rendering remains covered by browser response fixtures.", flush=True)
            finally:
                server.terminate()
                server.wait(timeout=10)
    after = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
    assert before == after, "Development database changed"
    print("Development database unchanged; temporary server and database removed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true", help="Also run UI checks with installed Chrome and Node 22+")
    run(parser.parse_args().browser)
