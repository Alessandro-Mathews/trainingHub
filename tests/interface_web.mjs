// Optional UI acceptance checks. Uses installed Chrome and Node's native CDP WebSocket; no npm dependencies.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { setTimeout as delay } from 'node:timers/promises';
import path from 'node:path';

const [base, chrome, profile] = process.argv.slice(2);
assert(base && chrome && profile, 'Run through python tests/interface_web.py --browser');
const browser = spawn(chrome, ['--headless=new', '--disable-gpu', '--in-process-gpu', '--no-first-run',
  '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile.replaceAll('\\', '/')}`, 'about:blank'],
  { stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true });
let browserLog = '';
browser.stderr.on('data', (data) => { browserLog += data; });
let socket;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = (await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; }
    catch { await delay(100); }
  }
  assert(port, `Chrome debugging port unavailable (exit ${browser.exitCode}): ${browserLog}`);
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(10000) })).json();
  socket = new WebSocket(targets.find((target) => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Chrome WebSocket connection timed out')), 10000);
    socket.onopen = () => { clearTimeout(timer); resolve(); };
    socket.onerror = (error) => { clearTimeout(timer); reject(error); };
  });
  let sequence = 0;
  const pending = new Map();
  const events = new Map();
  const errors = [];
  const requests = [];
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.id) {
      const entry = pending.get(message.id);
      if (!entry) return;
      pending.delete(message.id);
      if (message.error) entry.reject(new Error(JSON.stringify(message.error)));
      else entry.resolve(message.result);
    } else {
      for (const handler of events.get(message.method) ?? []) handler(message.params);
    }
  };
  function call(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 10000);
      pending.set(id, {
        resolve: (result) => { clearTimeout(timer); resolve(result); },
        reject: (error) => { clearTimeout(timer); reject(error); },
      });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  function on(event, handler) { events.set(event, [...(events.get(event) ?? []), handler]); }
  async function evaluate(expression) {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function until(expression) {
    for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await delay(100); }
    throw new Error(`Timed out: ${expression}`);
  }
  async function click(selector) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
  async function viewport(width) {
    await call('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
  }
  const screenshotDirectory = path.resolve('build/th21-screenshots');
  await mkdir(screenshotDirectory, { recursive: true });
  async function screenshot(name) {
    const { data } = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    await writeFile(path.join(screenshotDirectory, `${name}.png`), Buffer.from(data, 'base64'));
  }
  await call('Page.enable');
  await call('Runtime.enable');
  await call('Network.enable');
  on('Runtime.exceptionThrown', (event) => errors.push(event.exceptionDetails));
  on('Network.requestWillBeSent', (event) => requests.push(event.request.url));
  const password = 'TH24-test-password';
  async function fillLogin(code = '1', email = 'interface@example.test', secret = password) {
    await evaluate(`(() => {
      for (const [id, value] of ${JSON.stringify([['academia-code', code], ['login-email', email], ['login-password', secret]])}) {
        const input = document.getElementById(id);
        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    })()`);
  }
  async function loginReady() {
    await until(`location.pathname === '/login.html' && document.querySelector('#login-submit')?.disabled === false`);
  }
  async function dashboardReady() {
    await until(`location.pathname === '/index.html' && document.querySelector('#authenticated-app')?.hidden === false`);
  }
  // Start without a fixture cookie: the real page must establish its own session.
  await call('Page.navigate', { url: `${base}/index.html` });
  await loginReady();
  assert.equal(await evaluate(`document.querySelector('#login-password').type`), 'password');
  for (const width of [1440, 375]) {
    await viewport(width);
    assert.equal(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), true);
    await screenshot(`login-${width}`);
  }
  await evaluate(`document.querySelector('#academia-code').focus()`);
  await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  assert.equal(await evaluate(`document.activeElement.id`), 'login-email');
  for (const code of ['0', '-1', '1.5', 'abc', '9223372036854775808']) {
    await fillLogin(code);
    await click('#login-submit');
    assert.equal(await evaluate(`document.querySelector('#academia-code').validity.valid`), false);
  }
  await fillLogin('1', 'invalid-email');
  await click('#login-submit');
  assert.equal(await evaluate(`document.querySelector('#login-email').validity.valid`), false);
  await fillLogin('1', 'interface@example.test', '');
  await click('#login-submit');
  assert.equal(await evaluate(`document.querySelector('#login-password').validity.valid`), false);
  await fillLogin('1', 'interface@example.test', 'wrong');
  await click('#login-submit');
  await until(`document.querySelector('#login-feedback')?.textContent === 'Não foi possível entrar. Verifique suas credenciais.' && !document.querySelector('#login-submit').disabled`);
  assert.equal(await evaluate(`document.querySelector('#login-password').value`), '');

  let loginMode = 'hold';
  let heldLogin;
  let interceptedLogins = 0;
  const loginInterceptionErrors = [];
  on('Fetch.requestPaused', async ({ requestId, request }) => {
    if (request.url !== `${base}/api/auth/login`) return;
    try {
      interceptedLogins++;
      if (loginMode === 'hold') { heldLogin = requestId; return; }
      if (loginMode === 'network') {
        await call('Fetch.failRequest', { requestId, errorReason: 'ConnectionFailed' });
      } else {
        await call('Fetch.fulfillRequest', { requestId, responseCode: Number(loginMode),
          responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
          body: Buffer.from(JSON.stringify({ message: '<img src=x onerror="window.injected=true"> SQL internal detail' })).toString('base64') });
      }
    } catch (error) { loginInterceptionErrors.push(error); }
  });
  await call('Fetch.enable', { patterns: [{ urlPattern: `${base}/api/auth/login`, requestStage: 'Request' }] });
  for (const [mode, text] of [['400', 'Confira os dados informados.'],
                            ['500', 'Não foi possível entrar agora. Tente novamente.'],
                            ['network', 'Não foi possível conectar ao TrainingHub.']]) {
    loginMode = mode;
    await fillLogin();
    await click('#login-submit');
    await until(`document.querySelector('#login-feedback')?.textContent === ${JSON.stringify(text)} && !document.querySelector('#login-submit').disabled`);
    assert.equal(await evaluate(`document.querySelector('#login-feedback img') === null && window.injected !== true`), true);
  }
  loginMode = 'hold';
  await fillLogin();
  const attemptsBefore = interceptedLogins;
  await click('#login-submit');
  await until(`document.querySelector('#login-form').getAttribute('aria-busy') === 'true'`);
  assert.equal(await evaluate(`document.querySelector('#login-submit').disabled`), true);
  assert.equal(await evaluate(`document.querySelector('#login-submit-text').textContent`), 'Entrando...');
  await evaluate(`document.querySelector('#login-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))`);
  for (let i = 0; !heldLogin && i < 100; i++) await delay(20);
  assert(heldLogin);
  await delay(100);
  assert.equal(interceptedLogins - attemptsBefore, 1, 'Double submit issued another request');
  await screenshot('login-loading-375');
  await call('Fetch.continueRequest', { requestId: heldLogin });
  await dashboardReady();
  await call('Fetch.disable');
  assert.deepEqual(loginInterceptionErrors, []);
  assert.equal(await evaluate(`localStorage.length === 0 && sessionStorage.length === 0`), true);
  assert.equal(requests.some((url) => url.includes(password) || url.includes('senha=')), false);
  await call('Page.navigate', { url: `${base}/login.html` });
  await dashboardReady();
  await click('#logout-button');
  await loginReady();
  await fillLogin('1', 'gestor@example.test');
  await click('#login-submit');
  await dashboardReady();
  await until(`document.querySelector('#academias-count')?.textContent === 'Sem permissão'`);
  assert.equal(await evaluate(`location.pathname`), '/index.html');
  await click('#logout-button');
  await loginReady();
  await fillLogin('1', 'unknown@example.test');
  await click('#login-submit');
  await until(`document.querySelector('#login-feedback')?.textContent === 'Sua conta não tem permissão para acessar esta área.' && !document.querySelector('#login-submit').disabled`);
  assert.equal(await evaluate(`location.pathname`), '/login.html');
  await call('Page.navigate', { url: `${base}/index.html` });
  await until(`document.querySelector('#session-title')?.textContent === 'Acesso indisponível'`);
  assert.equal(await evaluate(`document.querySelector('#authenticated-app').hidden`), true);
  await click('#session-logout');
  await loginReady();
  await fillLogin();
  await click('#login-submit');
  await dashboardReady();
  console.log('TH-28 Chrome passed: real form/session/logout, validation, keyboard, mobile/desktop, loading/double submit, HTTP/network errors, 401 redirects, 403 without loop, no storage or credential URL.');
  await viewport(1440);
  await until(`document.querySelector('#academias-total')?.textContent === '1' && document.querySelector('#database-status')?.textContent === 'Conectado'`);
  assert.equal(await evaluate(`document.querySelector('#system-status').textContent`), 'Operacional');
  assert.equal(await evaluate(`document.querySelector('#brand-logo').naturalWidth > 0`), true);
  await screenshot('dashboard-1440');
  await click('[data-page="academias"]');
  await until(`!document.querySelector('#academias').hidden`);
  assert.equal(await evaluate(`document.title`), 'Academias | TrainingHub');
  assert.equal(await evaluate(`document.querySelectorAll('#academias-rows tr').length`), 1);
  assert.match(await evaluate(`document.querySelector('#academias-rows').textContent`), /Academia Centro/);
  assert.equal(await evaluate(`document.querySelector('#academias-rows').textContent.includes('Studio Evolução')`), false);
  assert.equal(await evaluate(`document.activeElement.id`), 'main-content');

  for (const width of [1440, 1024, 768, 375]) {
    await viewport(width);
    await delay(200);
    assert.equal(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), true, `Overflow at ${width}`);
    await screenshot(`academias-${width}`);
    if (width < 992) {
      assert.equal(await evaluate(`getComputedStyle(document.querySelector('.menu-toggle')).display !== 'none'`), true);
      await click('.menu-toggle');
      await until(`document.querySelector('#sidebar').classList.contains('show')`);
      await delay(400);
      await screenshot(`menu-${width}`);
      await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
      await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
      await until(`!document.querySelector('#sidebar').classList.contains('show') && !document.querySelector('.offcanvas-backdrop')`);
      await click('.menu-toggle');
      await until(`document.querySelector('#sidebar').classList.contains('show')`);
      await delay(400);
      await click('[data-page="dashboard"]');
      await until(`!document.querySelector('#dashboard').hidden && !document.querySelector('.offcanvas-backdrop')`);
      assert.equal(await evaluate(`document.activeElement.id`), 'main-content');
      assert.equal(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), true);
      await screenshot(`dashboard-${width}`);
      await evaluate(`location.hash = 'academias'`);
      await until(`!document.querySelector('#academias').hidden`);
    }
  }
  // Intercept only this browser's reads. The backend and development data remain untouched.
  let mode = 'loading';
  let heldRequest;
  const interceptionErrors = [];
  on('Fetch.requestPaused', async ({ requestId }) => {
    try {
      if (mode === 'loading') { heldRequest = requestId; return; }
      if (mode === 'real') { await call('Fetch.continueRequest', { requestId }); return; }
      if (mode === 'network') { await call('Fetch.failRequest', { requestId, errorReason: 'ConnectionFailed' }); return; }
      const body = mode === 'empty' ? [] : mode === 'invalid' ? { data: [] } : mode === 'nullable-inactive' ?
        [{ id: 1, nome: 'Academia Centro', ativo: true, cnpj: '12345678000190', email: 'centro@example.test', telefone: '(11) 99999-0000' },
         { id: 2, nome: 'Studio Evolução', ativo: false, cnpj: null, email: null, telefone: null }] : mode === 'xss' ?
        [{ id: 9, nome: '<img src=x onerror="window.injected=true">', ativo: true, cnpj: null, email: null, telefone: null }] :
        { message: 'SQL internal detail must not appear' };
      const status = mode === 'error' ? 500 : mode === 'unauthenticated' ? 401 : mode === 'forbidden' ? 403 : 200;
      await call('Fetch.fulfillRequest', { requestId, responseCode: status,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
        body: Buffer.from(JSON.stringify(body)).toString('base64') });
    } catch (error) { interceptionErrors.push(error); }
  });
  await call('Fetch.enable', { patterns: [{ urlPattern: `${base}/api/academias`, requestStage: 'Request' }] });
  await click('#refresh-academias');
  await until(`document.querySelector('#academias-panel').getAttribute('aria-busy') === 'true'`);
  assert.match(await evaluate(`document.querySelector('#academias-state').textContent`), /Carregando academias/);
  assert.equal(await evaluate(`document.querySelector('#refresh-academias').disabled`), true);
  await screenshot('loading-375');
  for (let i = 0; !heldRequest && i < 100; i++) await delay(20);
  assert(heldRequest);
  mode = 'empty';
  await call('Fetch.fulfillRequest', { requestId: heldRequest, responseCode: 200,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from('[]').toString('base64') });
  await until(`document.querySelector('#academias-total').textContent === '0'`);
  assert.match(await evaluate(`document.querySelector('#academias-state').textContent`), /Nenhuma academia cadastrada/);
  await screenshot('empty-375');
  for (mode of ['error', 'forbidden', 'network', 'invalid']) {
    await click('#refresh-academias');
    await until(`!document.querySelector('#academias-error').hidden && document.querySelector('#academias-panel').getAttribute('aria-busy') === 'false'`);
    assert.equal(await evaluate(`document.querySelector('#academias-total').textContent`), '—');
    assert.equal(await evaluate(`document.body.innerText.includes('SQL internal detail')`), false);
  }
  await screenshot('error-375');
  mode = 'real';
  await click('#retry-academias');
  await until(`document.querySelector('#academias-total').textContent === '1'`);
  // Preserve legacy NULL/inactive rendering coverage with browser-only data;
  // the authenticated API must never expose another Academia to this tenant.
  mode = 'nullable-inactive';
  await click('#refresh-academias');
  await until(`document.querySelector('#academias-total').textContent === '2'`);
  assert.equal(await evaluate(`document.querySelectorAll('#academias-rows tr').length`), 2);
  assert.match(await evaluate(`document.querySelector('#academias-rows').textContent`), /Não informado/);
  assert.match(await evaluate(`document.querySelector('#academias-rows').textContent`), /Inativa/);
  mode = 'xss';
  await click('#refresh-academias');
  await until(`document.querySelector('#academias-total').textContent === '1'`);
  assert.equal(await evaluate(`document.querySelectorAll('#academias-rows img').length`), 0);
  assert.equal(await evaluate(`window.injected === true`), false);
  assert.match(await evaluate(`document.querySelector('#academias-rows').textContent`), /<img src=x/);
  // A real session revocation makes both the resource and /me return 401.
  // This replaces the old generic-error assertion with the approved login redirect.
  await evaluate(`(await import('/js/api.js')).logout()`);
  mode = 'unauthenticated';
  await click('#refresh-academias');
  await loginReady();
  await call('Fetch.disable');
  await fillLogin();
  await click('#login-submit');
  await dashboardReady();
  await evaluate(`document.querySelector('#brand-logo').src = '/images/not-present.png'`);
  await until(`document.querySelector('#brand-logo').hidden`);
  assert.equal(await evaluate(`document.querySelector('.brand').textContent.includes('TrainingHub')`), true);
  await evaluate(`location.hash = 'unknown'`);
  await until(`!document.querySelector('#dashboard').hidden`);
  assert.equal(await evaluate(`document.querySelectorAll('[aria-current="page"]').length`), 1);
  assert.equal(requests.some((url) => /^https?:/.test(url) && !url.startsWith(base + '/')), false, 'External request');
  assert.deepEqual(errors, [], 'Browser runtime exceptions');
  assert.deepEqual(interceptionErrors, [], 'Interception failures');
  console.log('TH-21 Chrome passed: real list, NULL/inactive, loading, empty, HTTP/network/contract errors, retry, XSS, logo fallback, navigation, focus, offcanvas/Escape, 1440/1024/768/375px, no external requests.');
  console.log(`Screenshots: ${screenshotDirectory}`);
} catch (error) {
  console.error(browserLog.slice(-5000));
  throw error;
} finally {
  socket?.close();
  browser.kill();
  await new Promise((resolve) => { if (browser.exitCode !== null) resolve(); else browser.once('exit', resolve); });
  await delay(500);
}
