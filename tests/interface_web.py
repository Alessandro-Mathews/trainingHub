"""TH-21: real HTTP checks with an isolated database; optional Chrome UI checks."""

import argparse
from contextlib import closing
import hashlib
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

                def get(path):
                    with urllib.request.urlopen(base + path, timeout=5) as response:
                        return response.headers.get_content_type(), response.read()

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
                academias = json.loads(get("/api/academias")[1])
                assert len(academias) == 2
                assert set(academias[0]) == {"id", "nome", "cnpj", "email", "telefone", "ativo", "criado_em"}
                assert academias[0]["ativo"] is True and academias[1]["ativo"] is False
                assert academias[1]["cnpj"] is None
                for path in ["/config.json", "/migrations/001_initial_schema.sql", "/src/main.cpp"]:
                    try:
                        get(path)
                    except urllib.error.HTTPError as error:
                        assert error.code == 404
                    else:
                        raise AssertionError(f"Private file exposed: {path}")
                print("TH-21 HTTP passed: HTML, assets/MIME, real Academia contract, health, private files.", flush=True)
                if browser:
                    chrome = os.environ.get("TH21_CHROME") or shutil.which("google-chrome") or shutil.which("chromium")
                    if not chrome:
                        candidate = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
                        if candidate.exists():
                            chrome = str(candidate)
                    if not chrome:
                        raise RuntimeError("Set TH21_CHROME to an installed Chrome/Chromium executable")
                    subprocess.run(["node", str(ROOT / "tests" / "interface_web.mjs"), base, chrome,
                                    str(directory / "chrome-profile")], env=env, cwd=ROOT, check=True)
                with closing(sqlite3.connect(database)) as db:
                    db.execute("DELETE FROM academia")
                    db.commit()
                assert json.loads(get("/api/academias")[1]) == []
                print("TH-21 real empty list passed.", flush=True)
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
