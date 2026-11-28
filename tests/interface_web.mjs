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
  async function viewport(width, height = 1000) {
    await call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
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
  await evaluate(`import('/js/api.js').then(api => api.logout())`);
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

  // TH-31 exercises the delivered modules against this suite's isolated server.
  await call('Page.navigate', { url: `${base}/index.html#alunos` });
  await until(`!document.querySelector('#alunos-table-container').hidden && !document.querySelector('#create-aluno').disabled`);
  assert.equal(await evaluate('document.title'), 'Alunos | TrainingHub');
  for (const [width, height] of [[1440, 1000], [375, 812]]) {
    await viewport(width, height);
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true);
    await screenshot(`alunos-${width}`);
    await click('#create-aluno');
    await until(`document.querySelector('#aluno-create-modal').classList.contains('show') && document.activeElement.id === 'aluno-create-mode'`);
    assert.equal(await evaluate(`document.querySelector('#aluno-create-modal').scrollWidth <= innerWidth`), true);
    await screenshot(`alunos-cadastro-${width}`);
    await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await until(`!document.querySelector('.modal-backdrop') && document.activeElement.id === 'create-aluno'`);
  }
  await click('#create-aluno');
  await until(`document.activeElement.id === 'aluno-create-mode'`);
  await evaluate(`(() => {
    document.querySelector('#aluno-create-name').value = 'Aluno com nome longo para validar cadastro e responsividade';
    document.querySelector('#aluno-create-email').value = 'aluno.th31.browser@example.test';
    document.querySelector('#aluno-create-password').value = 'TH31-browser-password';
  })()`);
  await click('#aluno-create-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#alunos-rows').children.length === 2`);
  assert.equal(await evaluate(`document.querySelector('#aluno-create-password').value`), '');
  await click('#alunos-rows tr:last-child button:first-child');
  await until(`document.activeElement.id === 'aluno-edit-name'`);
  const maliciousName = '<img src=x onerror="window.th31Injected=true"> Nome longo para validação';
  await evaluate(`document.querySelector('#aluno-edit-name').value = ${JSON.stringify(maliciousName)}`);
  await screenshot('alunos-edicao-375');
  await click('#aluno-edit-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#alunos-rows').textContent.includes(${JSON.stringify(maliciousName)})`);
  assert.equal(await evaluate(`document.querySelector('#alunos-rows img') === null && window.th31Injected !== true`), true);
  await click('#alunos-rows tr:last-child button[data-action="status"]');
  await until(`document.activeElement.id === 'aluno-status-submit'`);
  assert.equal(await evaluate(`document.querySelector('#aluno-status-question img') === null`), true);
  assert.match(await evaluate(`document.querySelector('#aluno-status-explanation').textContent`), /impede.*login/);
  await screenshot('alunos-status-375');
  await click('#aluno-status-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#alunos-rows tr:last-child').textContent.includes('Inativo')`);
  await click('#alunos-rows tr:last-child button[data-action="status"]');
  await until(`document.activeElement.id === 'aluno-status-submit'`);
  await click('#aluno-status-submit');
  await until(`!document.querySelector('.modal-backdrop') && !document.querySelector('#alunos-rows tr:last-child').textContent.includes('Inativo')`);
  const beforeRefresh = requests.length;
  await click('#refresh-alunos');
  await until(`document.querySelector('#alunos-panel').getAttribute('aria-busy') === 'false' && !document.querySelector('#create-aluno').disabled`);
  assert.equal(requests.slice(beforeRefresh).filter(url => url === base + '/api/alunos').length, 1);
  assert.equal(requests.slice(beforeRefresh).filter(url => url.startsWith(base + '/api/usuarios?')).length, 1);
  assert.equal(requests.slice(beforeRefresh).some(url => url.startsWith(base + '/api/usuarios/')), false);

  events.set('Fetch.requestPaused', []);
  let alunoMode = 'empty';
  let releaseAlunos;
  on('Fetch.requestPaused', async ({requestId}) => {
    if (alunoMode === 'hold') { releaseAlunos = requestId; return; }
    await call('Fetch.fulfillRequest', { requestId, responseCode: alunoMode === 'error' ? 500 : 200,
      responseHeaders: [{name:'Content-Type',value:'application/json'}],
      body:Buffer.from(alunoMode === 'empty' ? '[]' : '{}').toString('base64') });
  });
  await call('Fetch.enable', { patterns: [{urlPattern:`${base}/api/alunos`,requestStage:'Request'}] });
  await click('#refresh-alunos');
  await until(`document.querySelector('#alunos-state').textContent.includes('Nenhum aluno cadastrado.') && !document.querySelector('#create-aluno').disabled`);
  await screenshot('alunos-vazio-375');
  alunoMode = 'error';
  await click('#refresh-alunos');
  await until(`!document.querySelector('#alunos-error').hidden && !document.querySelector('#refresh-alunos').disabled`);
  await screenshot('alunos-erro-375');
  alunoMode = 'hold';
  await click('#retry-alunos');
  await until(`document.querySelector('#alunos-panel').getAttribute('aria-busy') === 'true'`);
  assert.match(await evaluate(`document.querySelector('#alunos-state').textContent`), /Carregando alunos/);
  await screenshot('alunos-loading-375');
  for(let i=0;!releaseAlunos && i<100;i++) await delay(20);
  assert(releaseAlunos);
  await call('Fetch.continueRequest', {requestId:releaseAlunos});
  await until(`!document.querySelector('#alunos-table-container').hidden`);
  await call('Fetch.disable');
  assert.equal(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), true);
  assert.equal(await evaluate(`localStorage.length === 0 && sessionStorage.length === 0`), true);
  console.log('TH-31 Chrome passed: direct hash, list/join/no N+1, real create/edit/deactivate/reactivate, XSS, modal focus/Escape/return, loading/empty/error/retry, desktop and 375x812 without global overflow.');
  {
  // TH-32 exercises the delivered modules against this suite's isolated server.
  await call('Page.navigate', { url: `${base}/index.html#instrutores` });
  await until(`!document.querySelector('#instrutores-table-container').hidden && !document.querySelector('#create-instrutor').disabled`);
  assert.equal(await evaluate('document.title'), 'Instrutores | TrainingHub');
  for (const [width, height] of [[1440, 1000], [375, 812]]) {
    await viewport(width, height);
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true);
    await screenshot(`instrutores-${width}`);
    await click('#create-instrutor');
    await until(`document.querySelector('#instrutor-create-modal').classList.contains('show') && document.activeElement.id === 'instrutor-create-mode'`);
    assert.equal(await evaluate(`document.querySelector('#instrutor-create-modal').scrollWidth <= innerWidth`), true);
    await screenshot(`instrutores-cadastro-${width}`);
    await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await until(`!document.querySelector('.modal-backdrop') && document.activeElement.id === 'create-instrutor'`);
  }
  await click('#create-instrutor');
  await until(`document.activeElement.id === 'instrutor-create-mode'`);
  await evaluate(`(() => {
    document.querySelector('#instrutor-create-name').value = 'Instrutor com nome longo para validar cadastro e responsividade';
    document.querySelector('#instrutor-create-email').value = 'instrutor.th32.browser@example.test';
    document.querySelector('#instrutor-create-password').value = 'TH32-browser-password';
  })()`);
  await click('#instrutor-create-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#instrutores-rows').children.length === 2`);
  assert.equal(await evaluate(`document.querySelector('#instrutor-create-password').value`), '');
  await click('#instrutores-rows tr:last-child button:first-child');
  await until(`document.activeElement.id === 'instrutor-edit-name'`);
  const maliciousName = '<img src=x onerror="window.th32Injected=true"> Nome longo para validação';
  await evaluate(`document.querySelector('#instrutor-edit-name').value = ${JSON.stringify(maliciousName)}`);
  await screenshot('instrutores-edicao-375');
  await click('#instrutor-edit-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#instrutores-rows').textContent.includes(${JSON.stringify(maliciousName)})`);
  assert.equal(await evaluate(`document.querySelector('#instrutores-rows img') === null && window.th32Injected !== true`), true);
  await click('#instrutores-rows tr:last-child button:last-child');
  await until(`document.activeElement.id === 'instrutor-status-submit'`);
  assert.equal(await evaluate(`document.querySelector('#instrutor-status-question img') === null`), true);
  assert.match(await evaluate(`document.querySelector('#instrutor-status-explanation').textContent`), /impede.*login/);
  await screenshot('instrutores-status-375');
  await click('#instrutor-status-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#instrutores-rows tr:last-child').textContent.includes('Inativo')`);
  await click('#instrutores-rows tr:last-child button:last-child');
  await until(`document.activeElement.id === 'instrutor-status-submit'`);
  await click('#instrutor-status-submit');
  await until(`!document.querySelector('.modal-backdrop') && !document.querySelector('#instrutores-rows tr:last-child').textContent.includes('Inativo')`);
  const beforeRefresh = requests.length;
  await click('#refresh-instrutores');
  await until(`document.querySelector('#instrutores-panel').getAttribute('aria-busy') === 'false' && !document.querySelector('#create-instrutor').disabled`);
  assert.equal(requests.slice(beforeRefresh).filter(url => url === base + '/api/instrutores').length, 1);
  assert.equal(requests.slice(beforeRefresh).filter(url => url.startsWith(base + '/api/usuarios?')).length, 1);
  assert.equal(requests.slice(beforeRefresh).some(url => url.startsWith(base + '/api/usuarios/')), false);

  events.set('Fetch.requestPaused', []);
  let instrutorMode = 'empty';
  let releaseInstrutores;
  on('Fetch.requestPaused', async ({requestId}) => {
    if (instrutorMode === 'hold') { releaseInstrutores = requestId; return; }
    await call('Fetch.fulfillRequest', { requestId, responseCode: instrutorMode === 'error' ? 500 : 200,
      responseHeaders: [{name:'Content-Type',value:'application/json'}],
      body:Buffer.from(instrutorMode === 'empty' ? '[]' : '{}').toString('base64') });
  });
  await call('Fetch.enable', { patterns: [{urlPattern:`${base}/api/instrutores`,requestStage:'Request'}] });
  await click('#refresh-instrutores');
  await until(`document.querySelector('#instrutores-state').textContent.includes('Nenhum instrutor cadastrado.') && !document.querySelector('#create-instrutor').disabled`);
  await screenshot('instrutores-vazio-375');
  instrutorMode = 'error';
  await click('#refresh-instrutores');
  await until(`!document.querySelector('#instrutores-error').hidden && !document.querySelector('#refresh-instrutores').disabled`);
  await screenshot('instrutores-erro-375');
  instrutorMode = 'hold';
  await click('#retry-instrutores');
  await until(`document.querySelector('#instrutores-panel').getAttribute('aria-busy') === 'true'`);
  assert.match(await evaluate(`document.querySelector('#instrutores-state').textContent`), /Carregando instrutores/);
  await screenshot('instrutores-loading-375');
  for(let i=0;!releaseInstrutores && i<100;i++) await delay(20);
  assert(releaseInstrutores);
  await call('Fetch.continueRequest', {requestId:releaseInstrutores});
  await until(`!document.querySelector('#instrutores-table-container').hidden`);
  await call('Fetch.disable');
  assert.equal(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), true);
  assert.equal(await evaluate(`localStorage.length === 0 && sessionStorage.length === 0`), true);
  console.log('TH-32 Chrome passed: direct hash, list/join/no N+1, real create/edit/deactivate/reactivate, XSS, modal focus/Escape/return, loading/empty/error/retry, desktop and 375x812 without global overflow.');
  }
  // TH-33 uses the same isolated server and records created by TH-31/TH-32.
  await call('Page.navigate', { url: `${base}/index.html#alunos` });
  await until(`!document.querySelector('#alunos-table-container').hidden && !document.querySelector('#create-aluno').disabled`);
  const th33Instructors = await evaluate(`import('/js/api.js').then(api => api.getJson('/api/instrutores'))`);
  assert(th33Instructors.length >= 2);
  const th33Action = '#alunos-rows tr:first-child button[data-action="responsavel"]';
  const setInstructor = async (id) => evaluate(`(() => {
    const select = document.querySelector('#aluno-responsavel-select');
    select.value = ${JSON.stringify(id)}; select.dispatchEvent(new Event('change', {bubbles:true}));
  })()`);
  for (const [width, height] of [[1440, 1000], [375, 812]]) {
    await viewport(width, height);
    const beforeModal = requests.length;
    await evaluate(`window.th33Opener = document.querySelector(${JSON.stringify(th33Action)})`);
    await click(th33Action);
    await until(`document.querySelector('#aluno-responsavel-modal').classList.contains('show') && document.querySelector('#aluno-responsavel-form').getAttribute('aria-busy') === 'false' && document.activeElement.id === 'aluno-responsavel-cancel'`);
    assert.equal(requests.slice(beforeModal).filter(url => url.startsWith(base+'/api/')).length, 4);
    assert.equal(requests.slice(beforeModal).filter(url => /\/alunos\/[^/]+\/instrutor$/.test(url)).length, 1);
    assert.match(await evaluate(`document.querySelector('#aluno-responsavel-current').textContent`), /Nenhum instrutor definido/);
    assert.equal(await evaluate(`document.documentElement.scrollWidth <= innerWidth && document.querySelector('#aluno-responsavel-modal').scrollWidth <= innerWidth`), true);
    await screenshot(`aluno-instrutor-${width}`);
    await evaluate(`document.querySelector('#aluno-responsavel-select').focus()`);
    await call('Input.dispatchKeyEvent', {type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
    await call('Input.dispatchKeyEvent', {type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
    assert.equal(await evaluate(`document.activeElement.id`), 'aluno-responsavel-refresh');
    await call('Input.dispatchKeyEvent', {type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9,modifiers:8});
    await call('Input.dispatchKeyEvent', {type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9,modifiers:8});
    assert.equal(await evaluate(`document.activeElement.id`), 'aluno-responsavel-select');
    await call('Input.dispatchKeyEvent', {type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await call('Input.dispatchKeyEvent', {type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await until(`!document.querySelector('.modal-backdrop') && document.activeElement === window.th33Opener`);
  }
  // I1: an enabled opener during Bootstrap's hide transition used to start a
  // load whose show() was ignored, leaving the section permanently locked.
  await click(th33Action);
  await until(`document.activeElement.id === 'aluno-responsavel-cancel' && document.querySelector('#aluno-responsavel-form').getAttribute('aria-busy') === 'false'`);
  const beforeClosing = requests.length;
  const closingState = await evaluate(`(() => {
    const modal=document.querySelector('#aluno-responsavel-modal');
    window.th33TransitionOpener=document.querySelector(${JSON.stringify(th33Action)});
    document.querySelector('#aluno-responsavel-cancel').click();
    const next=document.querySelector('#alunos-rows tr:last-child button[data-action="responsavel"]');
    const state={transitioning:window.bootstrap.Modal.getInstance(modal)._isTransitioning,
      nextDisabled:next.disabled,refreshDisabled:document.querySelector('#refresh-alunos').disabled};
    next.click();return state;
  })()`);
  assert.equal(closingState.transitioning,true);
  assert.equal(closingState.nextDisabled,true);
  assert.equal(closingState.refreshDisabled,true);
  await until(`!document.querySelector('.modal-backdrop') && !document.querySelector('#refresh-alunos').disabled`);
  assert.equal(requests.length,beforeClosing,'I1: closing must not start B GETs');
  assert.equal(await evaluate(`document.activeElement === window.th33TransitionOpener && document.querySelector('#aluno-responsavel-form').getAttribute('aria-busy') === 'false'`),true);
  const th33StudentB=await evaluate(`document.querySelector('#alunos-rows tr:last-child td:first-child').textContent`);
  const beforeReopen=requests.length;
  await click('#alunos-rows tr:last-child button[data-action="responsavel"]');
  await until(`document.activeElement.id === 'aluno-responsavel-cancel' && document.querySelector('#aluno-responsavel-form').getAttribute('aria-busy') === 'false'`);
  assert.equal(requests.length,beforeReopen+4);
  assert.equal(await evaluate(`document.querySelector('#aluno-responsavel-aluno').textContent`),th33StudentB);
  assert.equal(await evaluate(`document.querySelector('#aluno-responsavel-modal').classList.contains('show')`),true);
  await click('#aluno-responsavel-modal .btn-close');
  await until(`!document.querySelector('.modal-backdrop') && !document.querySelector('#refresh-alunos').disabled`);
  await click(th33Action);
  await until(`document.querySelector('#aluno-responsavel-form').getAttribute('aria-busy') === 'false'`);
  await setInstructor(th33Instructors[0].id);
  const beforeDefine = requests.length;
  await click('#aluno-responsavel-submit');
  await until(`document.querySelector('#aluno-responsavel-feedback').textContent.includes('definido com sucesso')`);
  assert.equal(requests.length, beforeDefine+1, 'Successful definition adds only one PUT');
  await setInstructor(th33Instructors[0].id);
  assert.equal(await evaluate(`document.querySelector('#aluno-responsavel-submit').disabled`), true);
  await click('#aluno-responsavel-cancel');
  await until(`!document.querySelector('.modal-backdrop')`);
  const th33HistoricalUser=await evaluate(`import('/js/api.js').then(api => api.getJson('/api/usuarios/${th33Instructors[0].usuario_id}?academia_id=1'))`);
  assert.notEqual(th33Instructors[0].id,th33HistoricalUser.id);
  await evaluate(`import('/js/api.js').then(api => api.putJson('/api/usuarios/${th33Instructors[0].usuario_id}/status', {ativo:false}))`);
  await click(th33Action);
  await until(`document.querySelector('#aluno-responsavel-form').getAttribute('aria-busy') === 'false'`);
  assert.match(await evaluate(`document.querySelector('#aluno-responsavel-history').textContent`), /Indisponível para nova seleção/);
  assert.equal(await evaluate(`Array.from(document.querySelector('#aluno-responsavel-select').options).some(option => option.value === ${JSON.stringify(th33Instructors[0].id)})`), false);
  assert.equal(await evaluate(`document.querySelector('#aluno-responsavel-current').textContent.includes('Nenhum')`), false);
  assert.equal(await evaluate(`document.querySelector('#aluno-responsavel-current').textContent`),`${th33HistoricalUser.nome} — ${th33HistoricalUser.email}`);
  assert.equal(await evaluate(`Array.from(document.querySelector('#aluno-responsavel-select').options).some(option => option.value === ${JSON.stringify(th33Instructors[1].id)})`),true);
  await screenshot('aluno-instrutor-historico-375');
  await setInstructor(th33Instructors[1].id);
  await click('#aluno-responsavel-submit');
  await until(`document.querySelector('#aluno-responsavel-feedback').textContent.includes('alterado com sucesso')`);
  assert.equal(await evaluate(`document.querySelector('#aluno-responsavel-modal img') === null && window.th32Injected !== true`), true);
  assert.equal(await evaluate(`document.documentElement.scrollWidth <= innerWidth && document.querySelector('#aluno-responsavel-modal').scrollWidth <= innerWidth`), true);
  await screenshot('aluno-instrutor-alterado-375');
  await click('#aluno-responsavel-cancel');
  await until(`!document.querySelector('.modal-backdrop')`);
  await evaluate(`import('/js/api.js').then(api => api.putJson('/api/usuarios/${th33Instructors[0].usuario_id}/status', {ativo:true}))`);
  await click(th33Action);
  await until(`document.querySelector('#aluno-responsavel-form').getAttribute('aria-busy') === 'false'`);
  await setInstructor(th33Instructors[0].id);
  events.set('Fetch.requestPaused', []);
  let th33Write;
  on('Fetch.requestPaused', async ({requestId}) => { th33Write=requestId; });
  await call('Fetch.enable', {patterns:[{urlPattern:`${base}/api/alunos/*/instrutor`,requestStage:'Request'}]});
  await click('#aluno-responsavel-submit');
  await until(`document.querySelector('#aluno-responsavel-submit').disabled && document.querySelector('#aluno-responsavel-feedback').textContent === 'Salvando...'`);
  const beforeDouble = requests.length;
  await click('#aluno-responsavel-submit');
  assert.equal(requests.length,beforeDouble);
  await call('Input.dispatchKeyEvent', {type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await call('Input.dispatchKeyEvent', {type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  assert.equal(await evaluate(`document.querySelector('#aluno-responsavel-modal').classList.contains('show') && document.querySelector('#aluno-responsavel-cancel').disabled`), true);
  for(let index=0; !th33Write && index<100; index++) await delay(20);
  assert(th33Write);
  await call('Fetch.continueRequest', {requestId:th33Write});
  await until(`document.querySelector('#aluno-responsavel-feedback').textContent.includes('alterado com sucesso')`);
  await call('Fetch.disable');
  await click('#aluno-responsavel-cancel');
  await until(`!document.querySelector('.modal-backdrop')`);
  console.log('TH-33 Chrome passed: closing/hidden/reopen lifecycle, real definition/replacement/historical identity, four-GET modal, one-PUT save, XSS, double-submit/Escape write lock, keyboard/focus return, desktop and 375x812 without global overflow.');
  // TH-39 uses the delivered forms and the real Planos API in this isolated database.
  await viewport(1440);
  await click('[data-page="planos"]');
  await until(`!document.querySelector('#planos').hidden && document.querySelector('#planos-panel').getAttribute('aria-busy') === 'false'`);
  assert.equal(await evaluate(`document.title`), 'Planos | TrainingHub');
  assert.equal(await evaluate(`document.activeElement.id`), 'main-content');
  assert.match(await evaluate(`document.querySelector('#planos-state').textContent`), /Nenhum plano cadastrado/);
  await evaluate(`(() => {
    window.th39ModalWrites = [];
    window.th39OriginalFetch = window.fetch;
    window.fetch = function(input, options) {
      if (['POST','PUT'].includes(options?.method) && String(input).startsWith('/api/planos')) window.th39ModalWrites.push(options.method);
      return window.th39OriginalFetch.apply(this, arguments);
    };
  })()`);
  async function cancelPlanoDuringTransition(kind, opener, escape = false) {
    await click(opener);
    await until(`!document.querySelector('#plano-${kind}-submit').disabled`);
    const before = await evaluate(`window.th39ModalWrites.length`);
    await evaluate(`(() => {
      const kind = ${JSON.stringify(kind)}, modal = document.getElementById('plano-'+kind+'-modal');
      if (kind === 'create') {
        for (const [field,value] of [['name','Cancelado'],['value','99,90'],['duration','30']]) document.getElementById('plano-create-'+field).value=value;
      }
      window.th39DuringHide = null;
      modal.addEventListener('hide.bs.modal', () => queueMicrotask(() => {
        const submit = document.getElementById('plano-'+kind+'-submit');
        window.th39DuringHide = {disabled:submit.disabled, visible:modal.style.display !== 'none'};
        const target = kind === 'status' ? submit : document.getElementById('plano-'+kind+'-form');
        target.dispatchEvent(new Event(kind === 'status' ? 'click' : 'submit', {bubbles:true,cancelable:true}));
      }), {once:true});
    })()`);
    if (escape) {
      await call('Input.dispatchKeyEvent', {type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
      await call('Input.dispatchKeyEvent', {type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    } else await click(`#plano-${kind}-modal .modal-footer [data-bs-dismiss="modal"]`);
    await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#planos-panel').getAttribute('aria-busy') === 'false'`);
    assert.deepEqual(await evaluate(`window.th39DuringHide`), {disabled:true,visible:true});
    assert.equal(await evaluate(`window.th39ModalWrites.length`), before, `${kind} wrote after cancellation`);
    assert.equal(await evaluate(`document.querySelector('#refresh-planos').disabled || document.querySelector('#create-plano').disabled`), false);
    assert.equal(await evaluate(`document.activeElement === document.querySelector(${JSON.stringify(opener)})`), true);
  }
  await cancelPlanoDuringTransition('create', '#create-plano');
  await cancelPlanoDuringTransition('create', '#create-plano', true);
  await click('#create-plano');
  await until(`document.querySelector('#plano-create-modal').classList.contains('show') && document.activeElement.id === 'plano-create-name'`);
  await call('Input.dispatchKeyEvent', {type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  await call('Input.dispatchKeyEvent', {type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  assert.equal(await evaluate(`document.activeElement.id`), 'plano-create-description');
  const th39Name = '<img src=x onerror="window.th39Injected=true"> Plano TH39';
  const th39Description = '<script>window.th39Injected=true</script> Descrição completa\n' + 'conteúdo '.repeat(90);
  await evaluate(`(() => {
    for (const [field,value] of ${JSON.stringify([['name',th39Name],['description',th39Description],['value','99,90'],['duration','30']])}) {
      const input=document.getElementById('plano-create-'+field); input.value=value; input.dispatchEvent(new Event('input',{bubbles:true}));
    }
  })()`);
  await click('#plano-create-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#planos-feedback').textContent.includes('cadastrado com sucesso') && document.querySelector('#planos-panel').getAttribute('aria-busy') === 'false'`);
  assert.equal(await evaluate(`document.querySelectorAll('#planos-rows tr').length`), 1);
  assert.equal(await evaluate(`document.querySelectorAll('#planos-rows img, #planos-rows script').length`), 0);
  assert.equal(await evaluate(`window.th39Injected === undefined`), true);
  assert.match(await evaluate(`document.querySelector('#planos-rows').textContent`), /R\$ 99,90/);
  await cancelPlanoDuringTransition('edit', '#planos-rows button[aria-label^="Editar plano"]');
  await cancelPlanoDuringTransition('edit', '#planos-rows button[aria-label^="Editar plano"]', true);
  await cancelPlanoDuringTransition('status', '#planos-rows button[aria-label^="Desativar plano"]');
  await cancelPlanoDuringTransition('status', '#planos-rows button[aria-label^="Desativar plano"]', true);
  await click('#planos-rows button[aria-label^="Desativar plano"]');
  await until(`!document.querySelector('#plano-status-submit').disabled && document.querySelector('#plano-status-modal').classList.contains('show')`);
  await click('#plano-status-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#planos-feedback').textContent.includes('desativado com sucesso') && !document.querySelector('#planos-rows button[aria-label^="Editar plano"]').disabled`);
  await click('#planos-rows button[aria-label^="Editar plano"]');
  await until(`!document.querySelector('#plano-edit-submit').disabled && document.activeElement.id === 'plano-edit-name'`);
  assert.equal(await evaluate(`document.querySelector('#plano-edit-description').value`), th39Description);
  await evaluate(`document.querySelector('#plano-edit-value').value='92233720368547758,07';document.querySelector('#plano-edit-duration').value='9223372036854775807';`);
  await click('#plano-edit-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#planos-feedback').textContent.includes('atualizado com sucesso') && document.querySelector('#planos-panel').getAttribute('aria-busy') === 'false'`);
  assert.match(await evaluate(`document.querySelector('#planos-rows').textContent`), /92\.233\.720\.368\.547\.758,07/);
  assert.match(await evaluate(`document.querySelector('#planos-rows').textContent`), /9223372036854775807 dias/);
  await click('#planos-rows button[aria-label^="Ativar plano"]');
  await until(`!document.querySelector('#plano-status-submit').disabled`);
  await click('#plano-status-submit');
  await until(`!document.querySelector('.modal-backdrop') && document.querySelector('#planos-feedback').textContent.includes('ativado com sucesso') && document.querySelector('#planos-panel').getAttribute('aria-busy') === 'false'`);
  for(const width of [1440,1024,768,375]){
    await viewport(width); await delay(150);
    assert.equal(await evaluate(`document.documentElement.scrollWidth <= innerWidth`),true,`Planos overflow at ${width}`);
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('#planos-rows td')).display`),width<576?'block':'table-cell');
    await screenshot(`planos-${width}`);
  }
  await click('#planos-rows button[aria-label^="Editar plano"]');
  await until(`document.activeElement.id === 'plano-edit-name'`);
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await until(`!document.querySelector('.modal-backdrop')`);
  assert.match(await evaluate(`document.activeElement.getAttribute('aria-label')`),/^Editar plano/);
  await evaluate(`window.fetch = window.th39OriginalFetch`);
  console.log('TH-39 Chrome passed: navigation/title/focus, real create/edit/status, full description, XSS, exact int64, keyboard/Escape/focus return and stacked mobile at 375px.');
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
