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
  await viewport(1440);
  await call('Page.navigate', { url: base });
  await until(`document.querySelector('#academias-total')?.textContent === '2' && document.querySelector('#database-status')?.textContent === 'Conectado'`);
  assert.equal(await evaluate(`document.querySelector('#system-status').textContent`), 'Operacional');
  assert.equal(await evaluate(`document.querySelector('#brand-logo').naturalWidth > 0`), true);
  await screenshot('dashboard-1440');
  await click('[data-page="academias"]');
  await until(`!document.querySelector('#academias').hidden`);
  assert.equal(await evaluate(`document.title`), 'Academias | TrainingHub');
  assert.equal(await evaluate(`document.querySelectorAll('#academias-rows tr').length`), 2);
  assert.match(await evaluate(`document.querySelector('#academias-rows').textContent`), /Academia Centro/);
  assert.match(await evaluate(`document.querySelector('#academias-rows').textContent`), /Não informado/);
  assert.match(await evaluate(`document.querySelector('#academias-rows').textContent`), /Inativa/);
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
      const body = mode === 'empty' ? [] : mode === 'invalid' ? { data: [] } : mode === 'xss' ?
        [{ id: 9, nome: '<img src=x onerror="window.injected=true">', ativo: true, cnpj: null, email: null, telefone: null }] :
        { message: 'SQL internal detail must not appear' };
      await call('Fetch.fulfillRequest', { requestId, responseCode: mode === 'error' ? 500 : 200,
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
  for (mode of ['error', 'network', 'invalid']) {
    await click('#refresh-academias');
    await until(`!document.querySelector('#academias-error').hidden && document.querySelector('#academias-panel').getAttribute('aria-busy') === 'false'`);
    assert.equal(await evaluate(`document.querySelector('#academias-total').textContent`), '—');
    assert.equal(await evaluate(`document.body.innerText.includes('SQL internal detail')`), false);
  }
  await screenshot('error-375');
  mode = 'real';
  await click('#retry-academias');
  await until(`document.querySelector('#academias-total').textContent === '2'`);
  mode = 'xss';
  await click('#refresh-academias');
  await until(`document.querySelector('#academias-total').textContent === '1'`);
  assert.equal(await evaluate(`document.querySelectorAll('#academias-rows img').length`), 0);
  assert.equal(await evaluate(`window.injected === true`), false);
  assert.match(await evaluate(`document.querySelector('#academias-rows').textContent`), /<img src=x/);
  await call('Fetch.disable');
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
