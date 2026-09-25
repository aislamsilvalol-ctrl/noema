// Visual QA without Playwright: drives the system Google Chrome over the DevTools
// protocol (Node 22 has WebSocket built in). See scripts/visual/README.md.
// Screenshots through the Chrome DevTools Protocol, no dependencies.
// node shoot.mjs <outdir> <jobs.json>   jobs: [{url,name,width,height,full,mobile,auth,wait,before}]
import { spawn } from 'node:child_process';
import { writeFileSync, readFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [outDir, jobsFile] = process.argv.slice(2);
const jobs = JSON.parse(readFileSync(jobsFile, 'utf8'));
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9333;
const ORIGIN = process.env.ORIGIN || 'https://web-production-34d29.up.railway.app';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), 'cdp-'))}`, 'about:blank'],
  { stdio: 'ignore' });
let version;
for (let i = 0; i < 60; i++) { try { version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); break; } catch { await sleep(250); } }
const ws = new WebSocket(version.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const n = ++id; pending.set(n, (m) => m.error ? reject(new Error(method + ': ' + m.error.message)) : resolve(m.result));
  ws.send(JSON.stringify({ id: n, method, params, sessionId }));
});

async function login() {
  const email = process.env.QA_EMAIL, password = process.env.QA_PASSWORD;
  const res = await fetch(`${ORIGIN}/api/v1/auth/login`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email, password }) });
  const cookies = res.headers.getSetCookie().map((c) => { const [pair] = c.split(';'); const i = pair.indexOf('='); return { name: pair.slice(0, i), value: pair.slice(i + 1) }; });
  if (!res.ok) throw new Error('login failed ' + res.status);
  return cookies;
}
const authCookies = jobs.some((j) => j.auth) ? await login() : [];

for (const job of jobs) {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const s = (m, p) => send(m, p, sessionId);
  await s('Page.enable'); await s('Network.enable');
  const width = job.width ?? 1440, height = job.height ?? 900, mobile = !!job.mobile;
  await s('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile });
  if (mobile) await s('Emulation.setUserAgentOverride', { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1' });
  if (job.auth) for (const c of authCookies) await s('Network.setCookie', { ...c, url: ORIGIN, secure: ORIGIN.startsWith('https') });
  if (job.locale) await s('Emulation.setLocaleOverride', { locale: job.locale }).catch(() => {});
  await s('Page.navigate', { url: job.url.startsWith('http') ? job.url : ORIGIN + job.url });
  await sleep(job.wait ?? 5000);
  if (job.before) { await s('Runtime.evaluate', { expression: job.before, awaitPromise: true }); await sleep(job.afterWait ?? 3000); }
  let clip;
  if (job.full) {
    const { result } = await s('Runtime.evaluate', { expression: 'document.documentElement.scrollHeight', returnByValue: true });
    const total = result.value;
    for (let y = 0; y < total; y += Math.floor(height * 0.7)) { await s('Runtime.evaluate', { expression: `window.scrollTo(0, ${y})` }); await sleep(350); }
    await s('Runtime.evaluate', { expression: 'window.scrollTo(0, 0)' }); await sleep(800);
    clip = { x: 0, y: 0, width, height: Math.min(total, 16000), scale: job.scale ?? 0.5 };
  }
  const shot = await s('Page.captureScreenshot', { format: 'jpeg', quality: 70, captureBeyondViewport: !!job.full, ...(clip ? { clip } : {}) });
  writeFileSync(join(outDir, job.name + '.jpg'), Buffer.from(shot.data, 'base64'));
  console.log('shot', job.name);
  await send('Target.closeTarget', { targetId });
}
ws.close(); chrome.kill();
process.exit(0);
