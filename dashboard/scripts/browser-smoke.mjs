// Dependency-free browser smoke test using Chrome DevTools and Node's native WebSocket.
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

const executable =
  process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const output = resolve('artifacts');
await mkdir(output, { recursive: true });
const server = spawn(
  process.execPath,
  ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '4173', '--strictPort'],
  {
    env: { ...process.env, VITE_USE_MOCK: 'false', VITE_API_URL: 'http://127.0.0.1:8999' },
    windowsHide: true,
    stdio: 'pipe',
  },
);
let chrome;
let socket;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
try {
  let ready = false;
  for (let i = 0; i < 60; i++) {
    try {
      ready = (await fetch('http://127.0.0.1:4173')).ok;
    } catch {
      /* Starting. */
    }
    if (ready) break;
    await sleep(500);
  }
  assert(ready, 'Vite failed to start');
  chrome = spawn(
    executable,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--remote-debugging-port=0',
      `--user-data-dir=${resolve(output, 'chrome-profile')}`,
      'about:blank',
    ],
    { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] },
  );
  const endpoint = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Chrome startup timed out')), 20000);
    chrome.on('error', reject);
    chrome.stderr.on('data', (data) => {
      const match = data.toString().match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timeout);
        resolve(match[1]);
      }
    });
  });
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = reject;
  });
  let id = 0;
  const pending = new Map();
  const errors = [];
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === 'Runtime.exceptionThrown')
      errors.push(message.params.exceptionDetails.text);
    if (message.id) {
      const task = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) task.reject(new Error(JSON.stringify(message.error)));
      else task.resolve(message.result);
    }
  };
  function command(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const requestId = ++id;
      pending.set(requestId, { resolve, reject });
      socket.send(
        JSON.stringify({ id: requestId, method, params, ...(sessionId ? { sessionId } : {}) }),
      );
    });
  }
  const { targetId } = await command('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await command('Target.attachToTarget', { targetId, flatten: true });
  const call = (method, params) => command(method, params, sessionId);
  const evaluate = async (expression) => {
    const result = await call('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const waitFor = async (expression) => {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(expression)) return;
      await sleep(250);
    }
    throw new Error(`Timed out: ${expression}`);
  };
  const clickText = (label) =>
    evaluate(
      `[...document.querySelectorAll('button')].find(button => button.textContent.includes(${JSON.stringify(label)}))?.click()`,
    );
  await call('Runtime.enable');
  await call('Page.enable');
  // API calls are intercepted inside the page: no real backend is contacted.
  await call('Page.addScriptToEvaluateOnNewDocument', {
    source: `
    localStorage.removeItem('b2g-theme');
    window.__fixtureOnline = false;
    window.__fixtureHistoryError = true;
    window.__fixtureSends = 0;
    const records = Array.from({length: 100}, (_, index) => ({
      timestamp: new Date(Date.UTC(2025,5,1) + index*900000).toISOString(),
      coverage_ratio: 0.94, coverage_status: 'AT_RISK', active_actions: ['peak_shaving'],
      tier_1_protected: index !== 98, battery_soc: 62, grid_power: index%2 ? 12 : -8,
      p2p_energy: -2, anomaly_flag: index === 97, anomaly_source: index === 97 ? 'Capteur de test' : null,
      energy_price: 0.22
    }));
    const originalFetch = window.fetch;
    window.fetch = (input, options) => {
      const url = String(input);
      if (!url.startsWith('http://127.0.0.1:8999')) return originalFetch(input, options);
      if (!window.__fixtureOnline) return Promise.reject(new TypeError('Test: backend offline'));
      if (url.includes('/health')) return Promise.resolve(new Response('{}'));
      if (url.includes('/latest')) return Promise.resolve(new Response(null, {status:404}));
      if (url.includes('/history')) return Promise.resolve(window.__fixtureHistoryError ? new Response(null,{status:503}) : new Response(JSON.stringify(records)));
      return Promise.resolve(new Response('{}'));
    };
    window.WebSocket = class {
      static OPEN = 1;
      readyState = 0;
      constructor() { window.__fixtureSocket = this; setTimeout(() => { if(this.readyState === 3) return; this.readyState=1; this.onopen?.(); }, 10); }
      close() { if(this.readyState === 3) return; this.readyState=3; setTimeout(() => this.onclose?.(), 0); }
      send() { window.__fixtureSends++; setTimeout(() => {
        for(const record of records) this.onmessage?.({data:JSON.stringify(record)});
        this.onmessage?.({data:'{"type":"summary","data":{}}'});
      }, 20); }
    };
  `,
  });
  await call('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1080,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await call('Page.navigate', { url: 'http://127.0.0.1:4173' });
  await waitFor(`document.querySelectorAll('.recharts-surface').length === 4`);
  assert(await evaluate(`document.body.innerText.includes('Données simulées')`));
  assert(await evaluate(`document.body.innerText.includes('Protégées')`));
  assert(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), 'Desktop overflow');
  await writeFile(
    resolve(output, 'dashboard-desktop.png'),
    Buffer.from(
      (await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })).data,
      'base64',
    ),
  );
  await evaluate(`document.querySelector('[aria-label="Activer le thème sombre"]').click()`);
  assert(await evaluate(`Boolean(document.querySelector('.app.dark'))`));
  await evaluate(
    `(() => { const select=document.querySelector('#scenario'); select.value='price_spike'; select.dispatchEvent(new Event('change',{bubbles:true})); })()`,
  );
  await clickText('Lancer le scénario');
  await waitFor(`document.body.innerText.includes('Courbe violette')`);
  await clickText('Historique');
  await waitFor(`Boolean(document.querySelector('input[type=date]'))`);
  await evaluate(
    `(() => { const input=document.querySelector('[aria-label="Date de fin"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'2025-09-30'); input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); })()`,
  );
  await clickText('Afficher la période');
  await waitFor(`document.body.innerText.replace(/\\s/g,'').includes('11712mesures')`);
  await clickText('En direct');
  await call('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await sleep(500);
  assert(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), 'Mobile overflow');
  await writeFile(
    resolve(output, 'dashboard-mobile.png'),
    Buffer.from(
      (await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })).data,
      'base64',
    ),
  );
  await evaluate(`window.__fixtureOnline = true`);
  await waitFor(`Boolean(document.querySelector('.connection.live'))`);
  assert(
    await evaluate(`!document.body.innerText.includes('Données simulées')`),
    'Mock badge must disappear after recovery',
  );
  await clickText('Lancer le scénario');
  await waitFor(`Boolean(document.querySelector('.blocking-alert'))`);
  assert(
    await evaluate(`document.querySelector('.period-label').textContent.includes('96 mesures')`),
    'Live window must retain only 96 points',
  );
  assert.equal(await evaluate(`window.__fixtureSends`), 1, 'Exactly one scenario command');
  await evaluate(`window.__fixtureSocket.close()`);
  await waitFor(`Boolean(document.querySelector('.connection.reconnecting'))`);
  await waitFor(`Boolean(document.querySelector('.connection.live'))`);
  assert.equal(
    await evaluate(`window.__fixtureSends`),
    1,
    'Reconnect must not rerun the simulation',
  );
  await clickText('Historique');
  await waitFor(`document.body.innerText.includes('Impossible de charger')`);
  await evaluate(`window.__fixtureHistoryError = false`);
  await clickText('Réessayer');
  await waitFor(`document.querySelector('.period-label').textContent.includes('100 mesures')`);
  assert.deepEqual(errors, [], 'Browser runtime errors');
  console.log(
    'PASS: desktop/mobile, fallback/recovery, dark theme, price scenario, full history, 96-point live window, Tier 1 alert, reconnect without rerun, historical error/retry; no runtime errors.',
  );
} finally {
  socket?.close();
  chrome?.kill();
  server.kill();
}
