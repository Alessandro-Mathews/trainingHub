"""TH-21: real HTTP checks with an isolated database; optional Chrome UI checks."""

import argparse
from contextlib import closing
from html.parser import HTMLParser
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


class LoginMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}
        self.labels = set()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.elements[attrs["id"]] = (tag, attrs)
        if tag == "label":
            self.labels.add(attrs.get("for"))
        for name in ("src", "href"):
            if name in attrs:
                self.assets.append(attrs[name])


def check_login_markup():
    markup = LoginMarkup()
    markup.feed((ROOT / "public/login.html").read_text(encoding="utf-8"))
    for name, kind, autocomplete in [("academia-code", "text", None),
                                      ("login-email", "email", "username"),
                                      ("login-password", "password", "current-password")]:
        tag, attrs = markup.elements[name]
        assert tag == "input" and attrs["type"] == kind and "required" in attrs
        assert attrs.get("name") and name in markup.labels
        if autocomplete:
            assert attrs["autocomplete"] == autocomplete
    assert markup.elements["academia-code"][1]["inputmode"] == "numeric"
    assert markup.elements["login-form"][1]["aria-busy"] == "true"
    assert markup.elements["login-form"][1]["method"] == "post"
    assert markup.elements["login-feedback"][1]["aria-live"] == "polite"
    assert markup.elements["login-spinner"][1]["aria-hidden"] == "true"
    assert "disabled" in markup.elements["login-submit"][1]
    assert all(asset.startswith("/") and not asset.startswith("//") for asset in markup.assets)
    assert {"/images/traininghub-logo.png", "/vendor/bootstrap/bootstrap.min.css", "/css/style.css", "/js/login.js"} <= set(markup.assets)
    source = (ROOT / "public/js/login.js").read_text(encoding="utf-8")
    assert "from './api.js'" in source and "getAuthContext" in source
    assert not any(token in source for token in ["innerHTML", "localStorage", "sessionStorage", "console.", "document.cookie", "type = 'text'"])
    assert len([name for name, (tag, _) in markup.elements.items() if tag == "button"]) == 1
    assert not any(token in (ROOT / "public/css/style.css").read_text(encoding="utf-8") for token in ["@import", "fonts.googleapis.com"])


def check_api_javascript(env):
    node = shutil.which("node")
    if not node:
        candidate = Path("C:/Program Files/nodejs/node.exe")
        node = str(candidate) if candidate.exists() else None
    if not node:
        print("TH-28 JavaScript unit checks unavailable: Node not installed; HTTP/markup checks still run.")
        return None
    script = r'''
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile('public/js/api.js', 'utf8');
const api = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const invalidCodes = ['0', '00', '01', '0001', '-1', '+1', '1.5', '1e3', '0x10', 'abc',
  ' 1', '1 ', '1 0', '9223372036854775808', '', '1e0', 'Infinity', 'NaN', 1];
for (const value of invalidCodes) {
  assert.equal(api.parseAcademiaCode(value), null, String(value));
}
for (const value of ['1', '10', '9007199254740993', '9223372036854775807']) {
  assert.equal(api.parseAcademiaCode(value), value);
}
const calls = [];
globalThis.fetch = async (url, options) => {
  calls.push({ url, options });
  return { ok: true, json: async () => ({ userId: 1, academiaId: 1, perfilId: 17 }) };
};
const bodies = [];
for (const code of invalidCodes) {
  await assert.rejects(api.login(code, 'interface@example.test', 'TH24-test-password'),
    (error) => error.status === 400);
}
assert.equal(calls.length, 0, 'Invalid academy codes must not issue any request');
for (const code of ['1', '9223372036854775807']) {
  await api.login(code, 'interface@example.test', 'TH24-test-password');
  const call = calls.at(-1);
  assert.equal(call.url, '/api/auth/login');
  assert.equal(call.options.method, 'POST');
  assert.equal(call.options.body,
    '{"academia_id":' + code + ',"email":"interface@example.test","senha":"TH24-test-password"}');
  assert.equal(call.options.headers['Content-Type'], 'application/json');
  bodies.push(call.options.body);
}
const secret = ' x"\n ';
await api.login('1', 'Case@example.test', secret);
assert.equal(JSON.parse(calls.at(-1).options.body).senha, secret);
assert.equal(JSON.parse(calls.at(-1).options.body).email, 'Case@example.test');
await api.getAuthContext();
assert.equal(calls.at(-1).url, '/api/auth/me');
await api.logout();
assert.equal(calls.at(-1).url, '/api/auth/logout');
assert.equal(calls.at(-1).options.method, 'POST');
await api.getJson('/api/health');
assert.equal(calls.at(-1).options.method, 'GET');
for (const { options } of calls) {
  assert.equal(options.credentials, 'same-origin');
  assert.equal(options.cache, 'no-store');
  assert(options.signal instanceof AbortSignal);
}
for (const status of [400, 401, 403, 500]) {
  globalThis.fetch = async () => ({ ok: false, status, json: async () => { throw Error('Must not expose body'); } });
  await assert.rejects(api.getAuthContext(), (error) => error.status === status && error.message === 'Request failed');
}
for (const failure of [new TypeError('Internal network detail'), new DOMException('Timeout', 'TimeoutError')]) {
  globalThis.fetch = async () => { throw failure; };
  await assert.rejects(api.login('1', 'a@b', 'secret'), (error) => error.status === 0 && error.message === 'Request failed');
}
const bodyFailures = [new DOMException('Internal abort detail', 'AbortError'),
  new TypeError('Internal read detail'), new DOMException('Internal timeout detail', 'TimeoutError')];
function failedBody(failure) {
  return new Response(new ReadableStream({ start(controller) { controller.error(failure); } }), { status: 200 });
}
for (const failure of bodyFailures) {
  globalThis.fetch = async () => failedBody(failure);
  await assert.rejects(api.getJson('/api/health'),
    (error) => error instanceof api.ApiError && error.status === 0 && error.message === 'Request failed');
}
globalThis.fetch = async () => new Response('{invalid JSON', { status: 200 });
await assert.rejects(api.getJson('/api/health'),
  (error) => error.status === 502 && error.message === 'Request failed');
globalThis.fetch = async () => ({ ok: true, json: async () => ({}) });
await assert.rejects(api.getAuthContext(), (error) => error.status === 502);
// Exercise the delivered page modules with a small DOM double. These checks
// cover state transitions, not browser rendering, accessibility APIs or layout.
class Element {
  constructor(id) {
    this.id = id; this.value = ''; this.hidden = false; this.disabled = false;
    this.textContent = ''; this.listeners = {}; this.attributes = {}; this.validation = '';
    this.classList = { toggle() {}, contains() { return false; }, add() {}, remove() {} };
  }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key]; }
  removeAttribute(key) { delete this.attributes[key]; }
  setCustomValidity(value) { this.validation = value; }
  get validity() {
    const typeMismatch = this.id === 'login-email' && !/^[^@]+@[^@]+$/.test(this.value);
    return { typeMismatch, valid: !this.validation && !!this.value && !typeMismatch };
  }
  reportValidity() { return ['academia-code', 'login-email', 'login-password'].every((id) => document.getElementById(id).validity.valid); }
  focus() { document.activeElement = this; }
  replaceChildren(...children) { this.children = children; }
  append(...children) { this.children = [...(this.children || []), ...children]; }
  querySelector(selector) { return document.getElementById(this.id + selector); }
}
function pageFixture() {
  const elements = new Map();
  globalThis.document = {
    getElementById(id) { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); },
    querySelectorAll() { return []; },
    createElement(tag) { return new Element(tag); },
  };
  globalThis.window = { listeners: {}, addEventListener(event, handler) { this.listeners[event] = handler; } };
  globalThis.location = { hash: '', destinations: [], replace(path) { this.destinations.push(path); }, reload() {} };
  document.getElementById('authenticated-app').hidden = true;
  return document.getElementById.bind(document);
}
const tick = () => new Promise((resolve) => setImmediate(resolve));
const identity = { userId: 1, academiaId: 1, perfilId: 17 };
const response = (status, data = identity) => ({ ok: status < 400, status, json: async () => data });
const apiURL = 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
let pageSequence = 0;
async function pageModule(name, replaceAcademias = false) {
  let text = (await readFile('public/js/' + name, 'utf8')).replace("'./api.js'", JSON.stringify(apiURL));
  if (replaceAcademias) {
    const stub = 'data:text/javascript,export function loadAcademias(){globalThis.academiaLoads++;}';
    text = text.replace("'./academias.js'", JSON.stringify(stub));
  }
  return import('data:text/javascript;base64,' + Buffer.from(text).toString('base64') + '#' + pageSequence++);
}
let element = pageFixture();
globalThis.fetch = async () => response(401);
await pageModule('login.js');
await tick();
assert.equal(element('login-submit').disabled, false);
assert.equal(element('login-feedback').textContent, '');
function fillLogin(code = '1') {
  for (const [id, value] of [['academia-code', code], ['login-email', 'Case@example.test'], ['login-password', ' secret ']]) {
    element(id).value = value;
    element(id).listeners.input();
  }
}
let submits = 0;
let release;
globalThis.fetch = async (url, options) => {
  if (url.endsWith('/login')) { submits++; return new Promise((resolve) => { release = resolve; }); }
  return response(200);
};
fillLogin();
const submitEvent = { preventDefault() {} };
const inFlight = element('login-form').listeners.submit(submitEvent);
assert.equal(element('login-submit').disabled, true);
assert.equal(element('login-form').getAttribute('aria-busy'), 'true');
assert.equal(element('login-submit-text').textContent, 'Entrando...');
await element('login-form').listeners.submit(submitEvent);
assert.equal(submits, 1);
release(response(200));
await inFlight;
assert.deepEqual(location.destinations, ['/index.html']);
assert.equal(element('login-password').value, '');
for (const [status, message] of [[400, 'Confira os dados informados.'],
  [401, 'Não foi possível entrar. Verifique suas credenciais.'],
  [500, 'Não foi possível entrar agora. Tente novamente.'],
  [0, 'Não foi possível conectar ao TrainingHub.']]) {
  fillLogin(); location.destinations = [];
  globalThis.fetch = async () => { if (!status) throw new TypeError(); return response(status); };
  await element('login-form').listeners.submit(submitEvent);
  assert.equal(element('login-feedback').textContent, message);
  assert.equal(element('login-submit').disabled, false);
  assert.equal(element('login-password').value, '');
  assert.deepEqual(location.destinations, []);
}
for (const failedPath of ['/login', '/me']) {
  for (const failure of bodyFailures) {
    fillLogin(); location.destinations = [];
    globalThis.fetch = async (url) => url.endsWith(failedPath) ? failedBody(failure) : response(200);
    await element('login-form').listeners.submit(submitEvent);
    assert.equal(element('login-feedback').textContent, 'Não foi possível conectar ao TrainingHub.');
    assert.equal(element('login-submit').disabled, false);
    assert.equal(element('login-password').value, '');
    assert.deepEqual(location.destinations, []);
  }
}
fillLogin();
globalThis.fetch = async () => new Response('{invalid JSON', { status: 200 });
await element('login-form').listeners.submit(submitEvent);
assert.equal(element('login-feedback').textContent, 'Não foi possível entrar agora. Tente novamente.');
let invalidRequests = 0;
globalThis.fetch = async () => { invalidRequests++; return response(200); };
for (const code of invalidCodes.filter((value) => typeof value === 'string')) {
  fillLogin(code);
  await element('login-form').listeners.submit(submitEvent);
  assert.equal(element('academia-code').validity.valid, false, code);
}
assert.equal(invalidRequests, 0, 'Invalid form must not request authentication');
fillLogin();
globalThis.fetch = async (url) => response(url.endsWith('/me') ? 403 : 200);
await element('login-form').listeners.submit(submitEvent);
assert.equal(element('login-feedback').textContent, 'Sua conta não tem permissão para acessar esta área.');
assert.deepEqual(location.destinations, []);
for (const status of [200, 401, 403, 500, 0]) {
  element = pageFixture(); globalThis.academiaLoads = 0;
  globalThis.fetch = async (url) => {
    if (url.endsWith('/me')) { if (!status) throw new TypeError(); return response(status); }
    return response(200, { status: 'ok', application: 'TrainingHub', database: 'connected' });
  };
  await pageModule('app.js', true);
  await tick();
  assert.equal(globalThis.academiaLoads, status === 200 ? 1 : 0);
  assert.equal(element('authenticated-app').hidden, status !== 200);
  assert.deepEqual(location.destinations, status === 401 ? ['/login.html'] : []);
  if (status === 403) assert.equal(element('session-title').textContent, 'Acesso indisponível');
  if (status === 200) {
    await element('logout-button').listeners.click();
    assert.deepEqual(location.destinations, ['/login.html']);
    assert.equal(element('authenticated-app').hidden, true);
  }
}
for (const status of [401, 403, 500]) {
  element = pageFixture();
  element('authenticated-app').hidden = false;
  globalThis.fetch = async () => response(status);
  const academias = await pageModule('academias.js');
  await academias.loadAcademias();
  assert.deepEqual(location.destinations, status === 401 ? ['/login.html'] : []);
  if (status === 403) assert.equal(element('academias-count').textContent, 'Sem permissão');
  assert.equal(element('refresh-academias').disabled, false);
}
console.log(JSON.stringify(bodies));
'''
    result = subprocess.check_output([node, "--input-type=module", "-"], input=script, text=True, env=env, cwd=ROOT)
    print("TH-28 JavaScript passed: exact int64, escaping, API errors, login/loading/double submit, session gate, logout and resource 401/403 (DOM double, not visual proof).")
    return json.loads(result)


def run(browser):
    development_db = ROOT / "data" / "traininghub.db"
    before = hashlib.sha256(development_db.read_bytes()).digest() if development_db.exists() else None
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    check_login_markup()
    serialized_bodies = check_api_javascript(env)
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
            db.executemany("INSERT INTO perfil (id,nome) VALUES (?,?)",
                           [(18, "Gestor"), (19, "Instrutor"), (20, "Aluno"), (21, "Desconhecido")])
            for profile, email in [(18, "gestor@example.test"), (19, "instrutor@example.test"),
                                    (20, "aluno@example.test"), (21, "unknown@example.test")]:
                db.execute("INSERT INTO usuario (academia_id,perfil_id,nome,email,senha_hash) VALUES (1,?,'Teste',?,?)",
                           (profile, email, encoded))
            for academy, name in [(3, "Outra academia"), (2**63 - 1, "Limite int64")]:
                db.execute("INSERT INTO academia (id,nome) VALUES (?,?)", (academy, name))
                db.execute("INSERT INTO usuario (academia_id,perfil_id,nome,email,senha_hash) VALUES (?,17,'Admin','interface@example.test',?)",
                           (academy, encoded))
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
                    ("/", "text/html"), ("/index.html", "text/html"), ("/login.html", "text/html"),
                    ("/css/style.css", "text/css"), ("/js/app.js", "application/javascript"),
                    ("/js/api.js", "application/javascript"), ("/js/academias.js", "application/javascript"),
                    ("/js/login.js", "application/javascript"),
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
                expect_status("/api/auth/me", 401)

                def auth_request(client, path, body=None, expected=200):
                    data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
                    req = urllib.request.Request(base + path, method="POST", data=data,
                                                 headers={"Content-Type": "application/json"})
                    try:
                        response = client.open(req, timeout=15)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        content = response.read()
                        assert response.code == expected, (path, response.code, content)
                        assert response.headers.get("Cache-Control") == "no-store"
                        assert b"TH24-test-password" not in content and b"senha_hash" not in content
                        return json.loads(content)

                invalid = {"academia_id": 1, "email": "interface@example.test", "senha": "wrong"}
                assert auth_request(admin, "/api/auth/login", invalid, 401) == {"message": "Credenciais invalidas."}
                expect_status("/api/auth/me", 401, admin)
                for value in [0, -1, 1.5, "abc", 2**63]:
                    auth_request(admin, "/api/auth/login", invalid | {"academia_id": value}, 400)
                # Use the exact bodies generated by api.js when Node is available.
                for code, body in zip([1, 2**63 - 1], serialized_bodies or [None, None]):
                    payload = body.encode() if body else {"academia_id": code, "email": "interface@example.test", "senha": "TH24-test-password"}
                    context = auth_request(admin, "/api/auth/login", payload)
                    assert context["academiaId"] == code
                    assert json.loads(get("/api/auth/me", admin)[1]) == context
                    cookie = next(cookie for cookie in jar if cookie.name == "JSESSIONID")
                    assert cookie.has_nonstandard_attr("HttpOnly")
                    auth_request(admin, "/api/auth/logout")
                    expect_status("/api/auth/me", 401, admin)
                for email, context_status in [("gestor@example.test", 200), ("instrutor@example.test", 200),
                                               ("aluno@example.test", 200), ("unknown@example.test", 403)]:
                    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                    auth_request(client, "/api/auth/login", {"academia_id": 1, "email": email, "senha": "TH24-test-password"})
                    if context_status == 200:
                        assert json.loads(get("/api/auth/me", client)[1])["academiaId"] == 1
                    else:
                        expect_status("/api/auth/me", 403, client)
                    expect_status("/api/academias", 403, client)
                    auth_request(client, "/api/auth/logout")
                auth_request(admin, "/api/auth/login", {"academia_id": 3, "email": "interface@example.test", "senha": "TH24-test-password"})
                assert [item["id"] for item in json.loads(get("/api/academias", admin)[1])] == [3]
                auth_request(admin, "/api/auth/logout")
                print("TH-28 HTTP/markup passed: local login assets, fields/a11y, real login/me/logout, invalid credentials, int64, 401/403, tenant isolation.", flush=True)
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
                    subprocess.run(["node", str(ROOT / "tests" / "interface_web.mjs"), base, chrome,
                                    str(directory / "chrome-profile")], env=env, cwd=ROOT, check=True)
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
