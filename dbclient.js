#!/usr/bin/env node
// dbclient.js — Discord Bot Client (แนวเดียวกับ aiko-chan-ai/DiscordBotClient) ไฟล์เดียว รันใน Termux แล้วเปิดในเบราว์เซอร์มือถือ
//
//  วิธีใช้ (Termux):   pkg install nodejs -y
//                      node dbclient.js            <- ครั้งแรกจะโหลดตัวติดตั้งของ repo มาแยกไฟล์ให้เอง (ต้องมีเน็ต ใช้พื้นที่ ~300MB ชั่วคราว)
//                      เปิด http://127.0.0.1:8080  แล้วใส่ Bot Token
//
//  ตัวเลือก:   --setup          ติดตั้งส่วนประกอบใหม่ทั้งหมด        --info    ดูรายการไฟล์ใน release
//              --live           ลองใช้หน้าเว็บ Discord สด (ทดลอง ถ้าเด้งออกให้รันแบบปกติ)
//              PORT=9000        เปลี่ยนพอร์ต                         DBC_ASSET_URL=...  ระบุไฟล์ release เอง
//              DBC_SRC=/path    ใช้โฟลเดอร์ที่แตกไว้แล้ว (มี build/ assets/ VencordExtension/ node_modules/)
//
//  ไฟล์ log:   dbc-data/debug.log  (ไม่มี token)
'use strict';
const fs = require('fs'), path = require('path'), http = require('http'), https = require('https'), cp = require('child_process');
const realHttpsCreateServer = https.createServer.bind(https); // เก็บตัวจริงไว้ก่อน startInner() จะ monkey-patch https.createServer สำหรับเซิร์ฟเวอร์ภายในของ repo
const stream = require('stream'), Module = require('module'), EventEmitter = require('events');

const ROOT = __dirname, DATA = path.join(ROOT, 'dbc-data'), APP = process.env.DBC_SRC ? path.resolve(process.env.DBC_SRC) : path.join(DATA, 'app');
const USERDATA = path.join(DATA, 'userdata'), TMP = path.join(DATA, 'tmp'), LOGF = path.join(DATA, 'debug.log');
const TLSDIR = path.join(DATA, 'tls'), TLSKEY = path.join(TLSDIR, 'key.pem'), TLSCERT = path.join(TLSDIR, 'cert.pem');
const PORT = Number(process.env.PORT) || 8080;
const BIND = process.env.DC_BIND || '127.0.0.1'; // ตั้งเป็น 0.0.0.0 เมื่อรันบน VPS เพื่อให้เข้าจากอินเทอร์เน็ตได้
const ALLOWED_HOSTS = (process.env.DC_ALLOWED_HOST || '').split(',').map((s) => s.trim()).filter(Boolean); // เช่น DC_ALLOWED_HOST=bot.example.com
const ACCESS_KEY = process.env.DC_ACCESS_KEY || ''; // ตั้งรหัสผ่านกันคนอื่นเข้าถึงหน้าเว็บ (จำเป็นมากถ้า DC_BIND=0.0.0.0 เพราะหน้านี้เปิดเน็ตสาธารณะ)
const ARGV = process.argv.slice(2), LIVE = ARGV.includes('--live') || !!process.env.DC_LIVE;
const RELEASE_API = process.env.DBC_RELEASE_API || 'https://api.github.com/repos/aiko-chan-ai/DiscordBotClient/releases/latest';
const UA = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36';
fs.mkdirSync(DATA, { recursive: true }); fs.mkdirSync(USERDATA, { recursive: true });
try { fs.writeFileSync(LOGF, ''); } catch {}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => { const s = a.map((x) => (typeof x === 'string' ? x : x && x.stack ? x.stack : String(x))).join(' '); console.log(new Date().toLocaleTimeString(), s); try { fs.appendFileSync(LOGF, new Date().toISOString() + ' ' + s + '\n'); } catch {} };
const dlog = (s) => { try { fs.appendFileSync(LOGF, new Date().toISOString() + ' ' + s + '\n'); } catch {} };
process.on('uncaughtException', (e) => log('uncaughtException', e));
process.on('unhandledRejection', (e) => log('unhandledRejection', e));
if (typeof fetch === 'undefined') { console.log('Node เก่าเกินไป ให้รัน: pkg upgrade nodejs'); process.exit(1); }

// ================= ติดตั้ง: โหลด release -> แตกไฟล์ -> แตก app.asar =================
const run = (cmd, args, opts) => cp.spawnSync(cmd, args, Object.assign({ stdio: 'inherit' }, opts || {}));
const have = (cmd) => { const r = cp.spawnSync('sh', ['-c', 'command -v ' + cmd], { encoding: 'utf8' }); return r.status === 0; };
function walkFiles(root, pred, out = [], depth = 0) {
  if (depth > 12) return out;
  let ents; try { ents = fs.readdirSync(root, { withFileTypes: true }); } catch { return out; }
  for (const e of ents) { const p = path.join(root, e.name); if (pred(p, e)) out.push(p); if (e.isDirectory() && !e.isSymbolicLink()) walkFiles(p, pred, out, depth + 1); }
  return out;
}
function extractAsar(file, dest) {
  const fd = fs.openSync(file, 'r'); const h = Buffer.alloc(16); fs.readSync(fd, h, 0, 16, 0);
  const headerSize = h.readUInt32LE(4), jsonLen = h.readUInt32LE(12);
  const jb = Buffer.alloc(jsonLen); fs.readSync(fd, jb, 0, jsonLen, 16);
  const header = JSON.parse(jb.toString('utf8')), base = 8 + headerSize, unpacked = file + '.unpacked';
  let n = 0;
  (function walk(node, dir, rel) {
    for (const [name, e] of Object.entries(node.files || {})) {
      const out = path.join(dir, name), r = rel ? rel + '/' + name : name;
      if (e.files) { fs.mkdirSync(out, { recursive: true }); walk(e, out, r); }
      else if (e.link) { try { fs.symlinkSync(e.link, out); } catch {} }
      else if (e.unpacked) { const src = path.join(unpacked, r); if (fs.existsSync(src)) { fs.copyFileSync(src, out); n++; } }
      else { const buf = Buffer.alloc(e.size); if (e.size) fs.readSync(fd, buf, 0, e.size, base + Number(e.offset)); fs.writeFileSync(out, buf); if (e.executable) { try { fs.chmodSync(out, 0o755); } catch {} } n++; }
    }
  })(header, dest, '');
  fs.closeSync(fd); return n;
}
function squashOffset(file) {
  const fd = fs.openSync(file, 'r'); const buf = Buffer.alloc(8 * 1024 * 1024); const len = fs.readSync(fd, buf, 0, buf.length, 0); fs.closeSync(fd);
  let i = -1; while ((i = buf.indexOf('hsqs', i + 1)) !== -1 && i + 32 <= len) { if (buf.readUInt16LE(i + 28) === 4 && buf.readUInt16LE(i + 30) === 0) return i; }
  return -1;
}
function need(pkgName, why) { throw new Error('ต้องใช้ ' + why + ' ให้รัน: pkg install ' + pkgName + ' -y แล้วรัน node dbclient.js --setup อีกครั้ง'); }
function extractArchive(file, out) {
  fs.mkdirSync(out, { recursive: true }); const n = file.toLowerCase();
  if (/\.(tar\.gz|tgz)$/.test(n)) { if (run('tar', ['-xzf', file, '-C', out]).status) throw new Error('แตก tar.gz ไม่สำเร็จ'); }
  else if (/\.zip$/.test(n)) { if (have('unzip')) { if (run('unzip', ['-q', '-o', file, '-d', out]).status) throw new Error('แตก zip ไม่สำเร็จ'); } else if (have('7z')) run('7z', ['x', '-y', '-o' + out, file]); else need('unzip', 'unzip'); }
  else if (/\.appimage$/.test(n)) {
    if (!have('unsquashfs')) need('squashfs-tools', 'unsquashfs');
    const off = squashOffset(file); if (off < 0) throw new Error('หา squashfs ใน AppImage ไม่เจอ');
    let r = run('unsquashfs', ['-f', '-d', path.join(out, 'sq'), '-o', String(off), file, 'resources']);
    if (!fs.existsSync(path.join(out, 'sq', 'resources'))) { log('ดึงเฉพาะ resources ไม่ได้ ลองแตกทั้งหมด…'); r = run('unsquashfs', ['-f', '-d', path.join(out, 'sq'), '-o', String(off), file]); if (r.status && !fs.existsSync(path.join(out, 'sq', 'resources'))) throw new Error('unsquashfs ล้มเหลว'); }
  } else if (/\.deb$/.test(n)) {
    if (!have('ar')) need('binutils', 'ar'); const d = path.join(out, 'deb'); fs.mkdirSync(d, { recursive: true });
    if (run('ar', ['x', path.resolve(file)], { cwd: d }).status) throw new Error('ar แตก deb ไม่ได้');
    const data = fs.readdirSync(d).find((x) => /^data\.tar/.test(x)); if (!data) throw new Error('ไม่พบ data.tar ใน deb');
    if (/\.xz$/.test(data) && !have('xz')) need('xz-utils', 'xz'); if (/\.zst$/.test(data) && !have('zstd')) need('zstd', 'zstd');
    if (run('tar', ['-xf', path.join(d, data), '-C', out]).status) throw new Error('แตก data.tar ไม่สำเร็จ');
  } else if (/\.(exe|7z)$/.test(n)) {
    const z = ['7z', '7za', '7zr'].find(have); if (!z) need('p7zip', '7z');
    run(z, ['x', '-y', '-o' + out, file]);
    for (const p of walkFiles(out, (p, e) => e.isFile() && /app-(64|arm64|32)\.7z$/i.test(p))) run(z, ['x', '-y', '-o' + path.join(out, 'inner'), p]);
  } else throw new Error('ไม่รู้จักชนิดไฟล์ ' + file);
}
function pickAsset(assets) {
  const bad = /\.(blockmap|yml|yaml|sha\d*|sig|txt|md)$|^latest|mac|darwin|\.dmg$|\.pkg$|\.snap$|\.rpm$|\.msi$/i;
  const cands = assets.filter((a) => !bad.test(a.name));
  const score = (a) => { const n = a.name.toLowerCase(); let s = 0; if (/linux/.test(n)) s += 30; else if (/win/.test(n)) s += 10; if (/\.(tar\.gz|tgz)$/.test(n)) s += 50; else if (/\.zip$/.test(n)) s += 45; else if (/\.7z$/.test(n)) s += 40; else if (/\.appimage$/.test(n)) s += 35; else if (/\.deb$/.test(n)) s += 30; else if (/\.exe$/.test(n)) s += 20; if (/arm64|aarch64/.test(n)) s += 3; return s; };
  return cands.map((a) => [score(a), a]).filter((x) => x[0] > 0).sort((a, b) => b[0] - a[0]).map((x) => x[1]);
}
async function download(url, file) {
  const r = await fetch(url, { redirect: 'follow', headers: { 'User-Agent': 'dbclient' } }); if (!r.ok) throw new Error('โหลดไม่ได้ HTTP ' + r.status);
  const total = Number(r.headers.get('content-length')) || 0; const ws = fs.createWriteStream(file); let got = 0, last = -1;
  for await (const c of r.body) { ws.write(c); got += c.length; const p = total ? Math.floor((got / total) * 20) : Math.floor(got / 5e6); if (p !== last) { last = p; process.stdout.write('\r  โหลด ' + (got / 1048576).toFixed(0) + (total ? '/' + (total / 1048576).toFixed(0) : '') + ' MB   '); } }
  await new Promise((ok) => ws.end(ok)); process.stdout.write('\n');
}
function ensureTls() {
  if (process.env.DC_TLS_CERT && process.env.DC_TLS_KEY) {
    if (!fs.existsSync(process.env.DC_TLS_CERT) || !fs.existsSync(process.env.DC_TLS_KEY)) { log('DC_TLS_CERT/DC_TLS_KEY ชี้ไปที่ไฟล์ที่ไม่มีจริง จะใช้ใบรับรองสร้างเองแทน'); }
    else return 'real';
  }
  if (fs.existsSync(TLSKEY) && fs.existsSync(TLSCERT)) return true;
  if (!have('openssl')) { log('ไม่พบ openssl จะเสิร์ฟเป็น http ธรรมดาแทน (ติดตั้งด้วย: pkg install openssl-tool -y แล้วรันใหม่ เพื่อเปิด https)'); return false; }
  fs.mkdirSync(TLSDIR, { recursive: true });
  log('กำลังสร้างใบรับรอง https สำหรับ 127.0.0.1 (ครั้งเดียว)…');
  const r = run('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-keyout', TLSKEY, '-out', TLSCERT, '-days', '3650', '-nodes', '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1']);
  if (r.status || !fs.existsSync(TLSKEY) || !fs.existsSync(TLSCERT)) { log('สร้างใบรับรองไม่สำเร็จ จะเสิร์ฟเป็น http ธรรมดาแทน'); return false; }
  return true;
}
const appOk = () => fs.existsSync(path.join(APP, 'build', 'AppCore', 'APIServer.js')) && fs.existsSync(path.join(APP, 'assets', 'snapshot', 'index.html')) && !!findExt();
function findExt() {
  const direct = path.join(APP, 'VencordExtension'); if (fs.existsSync(path.join(direct, 'manifest.json'))) return direct;
  const hit = walkFiles(APP, (p, e) => e.isDirectory() && e.name === 'VencordExtension' && !p.includes('node_modules')); return hit.find((p) => fs.existsSync(path.join(p, 'manifest.json'))) || null;
}
async function setup(force) {
  if (!force && appOk()) return;
  if (process.env.DBC_SRC) throw new Error('DBC_SRC=' + APP + ' ไม่ครบ (ต้องมี build/AppCore/APIServer.js, assets/snapshot/index.html, VencordExtension/manifest.json)');
  log('ติดตั้งครั้งแรก: กำลังหาไฟล์ release ของ DiscordBotClient…');
  fs.rmSync(TMP, { recursive: true, force: true }); fs.mkdirSync(TMP, { recursive: true });
  let url = process.env.DBC_ASSET_URL, name = url && path.basename(url.split('?')[0]);
  let list = [];
  if (!url) {
    const r = await fetch(RELEASE_API, { headers: { 'User-Agent': 'dbclient', Accept: 'application/vnd.github+json' } });
    if (!r.ok) throw new Error('ดึงรายการ release ไม่ได้ (HTTP ' + r.status + ') ถ้าเป็น rate limit รอสักครู่ หรือใส่ DBC_ASSET_URL=ลิงก์ไฟล์ เอง');
    const j = await r.json(); log('release ' + j.tag_name + ' มีไฟล์: ' + (j.assets || []).map((a) => a.name).join(', '));
    if (ARGV.includes('--info')) process.exit(0);
    list = pickAsset(j.assets || []).map((a) => ({ name: a.name, url: a.browser_download_url }));
    if (!list.length) throw new Error('ไม่มีไฟล์ที่ใช้ได้ใน release (ดูรายการด้านบน แล้วใส่ DBC_ASSET_URL เอง)');
  } else list = [{ name, url }];
  let lastErr;
  for (const a of list) {
    try {
      log('ใช้ไฟล์ ' + a.name); const file = path.join(TMP, a.name); await download(a.url, file);
      const raw = path.join(TMP, 'raw'); log('กำลังแตกไฟล์…'); extractArchive(file, raw); fs.rmSync(file, { force: true });
      const asars = walkFiles(raw, (p, e) => e.isFile() && e.name === 'app.asar');
      const next = path.join(DATA, 'app.new'); fs.rmSync(next, { recursive: true, force: true }); fs.mkdirSync(next, { recursive: true });
      if (asars.length) { log('แตก app.asar…'); const n = extractAsar(asars[0], next); log('แตกแล้ว ' + n + ' ไฟล์'); }
      else { const dirs = walkFiles(raw, (p, e) => e.isDirectory() && fs.existsSync(path.join(p, 'build', 'AppCore')) && fs.existsSync(path.join(p, 'package.json'))); if (!dirs.length) throw new Error('ไม่พบ app.asar หรือโฟลเดอร์แอปในไฟล์นี้'); fs.cpSync(dirs[0], next, { recursive: true }); }
      // assets/VencordExtension อาจอยู่นอก asar (extraResources)
      for (const nm of ['assets', 'VencordExtension']) { if (!fs.existsSync(path.join(next, nm))) { const f = walkFiles(raw, (p, e) => e.isDirectory() && e.name === nm && !p.includes('node_modules'))[0]; if (f) fs.cpSync(f, path.join(next, nm), { recursive: true }); } }
      fs.rmSync(APP, { recursive: true, force: true }); fs.renameSync(next, APP);
      fs.rmSync(TMP, { recursive: true, force: true });
      if (!appOk()) throw new Error('แตกแล้วแต่ไฟล์ไม่ครบ (ต้องมี build/AppCore/APIServer.js, assets/snapshot/index.html, VencordExtension/manifest.json)');
      log('ติดตั้งเสร็จ ✔'); return;
    } catch (e) { lastErr = e; log('ใช้ไฟล์ ' + a.name + ' ไม่สำเร็จ: ' + e.message); fs.rmSync(path.join(TMP, 'raw'), { recursive: true, force: true }); }
  }
  throw lastErr;
}

// ================= ตัวจำลอง electron (ให้ซอร์สจริงของ repo รันนอก Electron ได้) =================
const pkgInfo = () => { try { return JSON.parse(fs.readFileSync(path.join(APP, 'package.json'), 'utf8')); } catch { return { version: '0.0.0', productName: 'DiscordBotClient' }; } };
const cookieJar = new Map();
class ClientRequest extends stream.Writable {
  constructor(o) { super(); this.o = o; this.h = {}; this.chunks = []; }
  setHeader(k, v) { this.h[String(k).toLowerCase()] = v; }
  _write(c, e, cb) { this.chunks.push(Buffer.from(c)); cb(); }
  _final(cb) { this.go(this.o.url, this.o.method, Buffer.concat(this.chunks), 0); cb(); }
  go(urlStr, method, body, hop) {
    const u = new URL(urlStr), headers = Object.assign({}, this.h);
    headers['accept-encoding'] = 'identity'; delete headers['content-length']; if (body.length) headers['content-length'] = body.length;
    const ck = cookieJar.get(u.hostname); if (ck && !headers.cookie) headers.cookie = [...ck].map(([k, v]) => k + '=' + v).join('; ');
    const rq = https.request({ hostname: u.hostname, port: u.port || 443, path: u.pathname + u.search, method, headers }, (res) => {
      (res.headers['set-cookie'] || []).forEach((c) => { const m = c.match(/^([^=;]+)=([^;]*)/); if (m) { if (!cookieJar.has(u.hostname)) cookieJar.set(u.hostname, new Map()); cookieJar.get(u.hostname).set(m[1], m[2]); } });
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location && hop < 5) { res.resume(); const nm = res.statusCode === 303 || ((res.statusCode === 301 || res.statusCode === 302) && method === 'POST') ? 'GET' : method; return this.go(new URL(res.headers.location, u).toString(), nm, nm === 'GET' ? Buffer.alloc(0) : body, hop + 1); }
      this.emit('response', res);
    });
    rq.on('error', (e) => this.emit('error', e)); rq.setTimeout(60000, () => rq.destroy(new Error('timeout'))); rq.end(body);
  }
}
const electronShim = () => ({
  app: { getAppPath: () => APP, getVersion: () => pkgInfo().version, getName: () => pkgInfo().productName || 'DiscordBotClient', getPath: () => USERDATA, isPackaged: true, isReady: () => true, on() {}, commandLine: { appendSwitch() {}, getSwitchValue: () => '' } },
  nativeImage: { createFromPath: () => ({ resize() { return this; } }) },
  net: { isOnline: () => true, request: (o) => new ClientRequest(o) },
  ipcMain: new EventEmitter(), dialog: { showErrorBox() {} },
});
const logScope = (name) => { const mk = (lv, show) => (...a) => { const s = '[' + name + '] ' + a.map((x) => (typeof x === 'string' ? x : x && x.stack ? x.stack : JSON.stringify(x))).join(' '); if (show(s)) log(s); else dlog(s); }; return { log: mk('log', () => false), info: mk('info', (s) => / [45]\d\d /.test(s) && !/\/(assets|science)/.test(s)), warn: mk('warn', () => true), error: mk('error', () => true), debug: mk('debug', () => false) }; };

// ================= หน้าเว็บ: ฉีด shim + Vencord เข้า index.html =================
function dbcShim(CFG) {
  var T0 = Date.now();
  function L(t, m) { try { var b = JSON.stringify({ t: t, m: '+' + (Date.now() - T0) + 'ms ' + String(m).slice(0, 1200) }); if (navigator.sendBeacon) navigator.sendBeacon('/__dbc/log', b); else fetch('/__dbc/log', { method: 'POST', body: b, keepalive: true }); } catch (e) {} }
  function stk() { try { return String(new Error().stack).split('\n').slice(3, 9).map(function (x) { return x.trim().replace(/https?:\/\/[^/]+/, ''); }).join(' | '); } catch (e) { return ''; } }
  function xhr(method, url, body) {
    try { var x = new XMLHttpRequest(); x.open(method, url, false); if (body !== undefined) { x.setRequestHeader('Content-Type', 'application/json'); x.send(JSON.stringify(body)); } else x.send(); if (x.status >= 200 && x.status < 300 && x.responseText) return JSON.parse(x.responseText); } catch (e) { L('xhr-fail', url + ' ' + e); } return null;
  }
  function post(url, body) { return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(function (r) { return r.json(); }); }
  var ver = xhr('GET', '/__dbc/native/version') || { name: 'DiscordBotClient', version: '0.0.0' };
  var defUser = xhr('GET', '/__dbc/native/defaultuser') || {};
  var N = function () {};
  window.BotClientNative = {
    getBotInfo: function (token) { return post('/__dbc/native/botinfo', { token: token }); },
    getBotClientVersion: function () { return ver.version; }, getBotClientName: function () { return ver.name; },
    getPrivateChannelDefault: function () { return { type: 1, recipients: [defUser], last_message_id: '1000000000000000000', is_spam: false, id: '1000000000000000000', flags: 0 }; },
    getUserExperiments: function (allData, botId) { return xhr('POST', '/__dbc/native/exp', { type: 'user', botId: botId, allData: allData }); },
    getGuildExperiments: function () { return xhr('POST', '/__dbc/native/exp', { type: 'guild' }); },
    getApexExperiments: function (botId) { return xhr('POST', '/__dbc/native/exp', { type: 'apex', botId: botId }); },
    closeWindow: N, close: N, minimize: N, maximize: N, focus: N, flashFrame: N, requestOpenMessageEditorWindow: function () { return Promise.resolve(); }
  };
  var CH = { gp: 'app:preload:get_preloaded_user_settings', gpr: 'app:preload:get_preloaded_user_settings_response', sp: 'app:preload:set_preloaded_user_settings', gf: 'app:preload:get_frecency_user_settings', gfr: 'app:preload:get_frecency_user_settings_response', sf: 'app:preload:set_frecency_user_settings' };
  var LS = {}; function reg(ch) { return function (l) { LS[ch] = l; }; } function resp(ch) { return function (botId, settings) { post('/__dbc/ipc', { channel: ch, args: [botId, settings] }); }; }
  window.protoAPI = { GetPreloadedUserSettings: reg(CH.gp), GetPreloadedUserSettingsResponse: resp(CH.gpr), SetPreloadedUserSettings: reg(CH.sp), GetFrecencyUserSettings: reg(CH.gf), GetFrecencyUserSettingsResponse: resp(CH.gfr), SetFrecencyUserSettings: reg(CH.sf) };
  try {
    var es = new EventSource('/__dbc/events');
    es.onmessage = function (e) { var m; try { m = JSON.parse(e.data); } catch (x) { return; } var l = LS[m.channel]; if (l) { try { l.apply(null, m.args || []); } catch (err) { L('ipc-listener', m.channel + ' ' + (err && err.message)); } } else if (m.channel !== 'app:main:log') L('ipc-nolistener', m.channel); };
  } catch (e) {}
  // ลิงก์แบบ absolute ของ discord.com (api/assets) ให้ชี้มาที่เซิร์ฟเวอร์ในเครื่อง (แทน host-rules ของ Electron)
  var RX = /^(?:https?:)?\/\/(?:canary\.|ptb\.)?discord(?:app)?\.com(\/(?:api|assets)\/.*)$/;
  function fix(u) { if (typeof u !== 'string') return u; var m = u.match(RX); return m ? location.origin + m[1] : u; }
  try {
    var of = window.fetch; window.fetch = function (i, o) { if (typeof i === 'string') i = fix(i); else if (i && i.url && RX.test(i.url)) i = new Request(fix(i.url), i); return of.call(this, i, o); };
    var xo = XMLHttpRequest.prototype.open; XMLHttpRequest.prototype.open = function (m, u) { arguments[1] = fix(String(u)); return xo.apply(this, arguments); };
  } catch (e) {}
  // chrome.* จำลอง สำหรับ content script ของส่วนเสริม Vencord
  var mf = CFG.manifest || {}, store = function () { try { return JSON.parse(localStorage.getItem('__dbc_ext') || '{}'); } catch (e) { return {}; } };
  var getURL = function (p) { return '/__ext/' + String(p || '').replace(/^\//, ''); };
  var pick = function (o, k) { var r = {}; if (k == null) return Object.assign(r, o); if (typeof k === 'string') k = [k]; if (Array.isArray(k)) k.forEach(function (x) { if (x in o) r[x] = o[x]; }); else for (var x in k) r[x] = x in o ? o[x] : k[x]; return r; };
  var area = { get: function (k, cb) { var r = pick(store(), k); if (cb) cb(r); return Promise.resolve(r); }, set: function (v, cb) { var o = store(); Object.assign(o, v); localStorage.setItem('__dbc_ext', JSON.stringify(o)); if (cb) cb(); return Promise.resolve(); }, remove: function (k, cb) { var o = store(); [].concat(k).forEach(function (x) { delete o[x]; }); localStorage.setItem('__dbc_ext', JSON.stringify(o)); if (cb) cb(); return Promise.resolve(); } };
  var ev = { addListener: N, removeListener: N, hasListener: function () { return false; } };
  window.__dbcChrome = { runtime: { id: 'dbc', getURL: getURL, getManifest: function () { return mf; }, sendMessage: function () { return Promise.resolve(); }, onMessage: ev, onConnect: ev, connect: function () { return { postMessage: N, onMessage: ev, onDisconnect: ev, disconnect: N }; } }, storage: { local: area, sync: area, onChanged: ev }, extension: { getURL: getURL }, i18n: { getMessage: function () { return ''; } } };
  // ตัวช่วยดีบัก: ส่ง error/warn และการเด้งไปหน้า login พร้อม stack กลับมาแสดงใน Termux
  var seen = {}, n = 0;
  ['error', 'warn'].forEach(function (k) { var o = console[k]; console[k] = function () { try { var s = [].slice.call(arguments).map(function (x) { return typeof x === 'string' ? x : x && x.stack ? x.stack : (x && typeof x === 'object' ? '{' + Object.keys(x).slice(0, 6).join(',') + '}' : String(x)); }).join(' ').replace(/%c/g, '').replace(/\s+/g, ' ').slice(0, 500); if (!seen[s] && n++ < 120) { seen[s] = 1; L('console.' + k, s); } } catch (e) {} return o.apply(console, arguments); }; });
  window.addEventListener('error', function (e) { L('error', e.message + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno); });
  window.addEventListener('unhandledrejection', function (e) { L('reject', (e.reason && (e.reason.stack || e.reason.message)) || e.reason); });
  var hp = history.pushState, hr = history.replaceState; function nav(w) {
    if (!/^\/(login|register)/.test(location.pathname) || window.__navLog) return; window.__navLog = 1;
    var fast = (Date.now() - T0) < 20000;
    L('nav', 'ไปหน้า ' + location.pathname + ' (' + w + ')' + (fast ? ' [หลุดเร็วผิดปกติ]' : '') + ' @ ' + stk());
    if (fast && CFG.live && !location.search.includes('dbcsafe')) {
      post('/__dbc/livefail', {}).then(function (r) { location.replace('/channels/@me?dbcsafe=1' + (r && r.forced ? '&forcedfrozen=1' : '')); }).catch(function () { location.replace('/channels/@me?dbcsafe=1'); });
    } else location.replace('/?e=1');
  }
  history.pushState = function () { var r = hp.apply(this, arguments); nav('pushState'); return r; }; history.replaceState = function () { var r = hr.apply(this, arguments); nav('replaceState'); return r; };
  var W = window.WebSocket; function F(u, p) { var s = p === undefined ? new W(u) : new W(u, p); try { if (/gateway/.test(String(u))) { var oc = s.close; s.close = function (c, r) { L('ws', 'หน้าเว็บสั่งปิด gateway close(' + c + ',' + (r || '') + ') @ ' + stk()); return oc.apply(this, arguments); }; s.addEventListener('close', function (e) { L('ws', 'gateway ปิด code=' + e.code + ' reason=' + e.reason); }); } } catch (e) {} return s; }
  F.prototype = W.prototype; F.CONNECTING = 0; F.OPEN = 1; F.CLOSING = 2; F.CLOSED = 3; window.WebSocket = F;
  L('shim', 'พร้อม ' + ver.name + ' ' + ver.version + (CFG.live ? ' (โหมดสด)' : ''));
}
const MIME = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.html': 'text/html', '.png': 'image/png', '.svg': 'image/svg+xml', '.map': 'application/json', '.wasm': 'application/wasm', '.woff2': 'font/woff2' };
let extDir = null, extInfo = null;
function loadExtInfo() {
  extDir = findExt(); const mf = JSON.parse(fs.readFileSync(path.join(extDir, 'manifest.json'), 'utf8'));
  const iso = [], mainJs = [], css = [];
  for (const cs of mf.content_scripts || []) {
    for (const f of cs.js || []) { if (cs.world === 'MAIN') mainJs.push(f); else iso.push(f); }
    for (const f of cs.css || []) css.push(f);
  }
  extInfo = { mf, iso, mainJs, css };
  log('ส่วนเสริม Vencord v' + mf.version + ' | content script: ' + iso.join(',') + ' | MAIN: ' + mainJs.join(',') + ' | css: ' + css.join(','));
}
function shimSource() {
  let s = '(' + dbcShim.toString() + ')(' + JSON.stringify({ manifest: extInfo.mf, live: LIVE }) + ');\n';
  for (const f of extInfo.iso) { let t = ''; try { t = fs.readFileSync(path.join(extDir, f), 'utf8'); } catch {} s += ';(function(chrome,browser){try{\n' + t + '\n}catch(e){console.error("[dbc] content script ' + f + ' พลาด: "+(e&&e.stack||e))}})(window.__dbcChrome,window.__dbcChrome);\n'; }
  return s;
}
const ENV_REWRITES = (host) => ({ API_PROTOCOL: 'http:', API_ENDPOINT: '//' + host + '/api', ASSET_ENDPOINT: '//' + host, WEBAPP_ENDPOINT: '//' + host, DEVELOPERS_ENDPOINT: '//' + host, MARKETING_ENDPOINT: '//' + host, WIDGET_ENDPOINT: '//' + host + '/widget', MIGRATION_DESTINATION_ORIGIN: 'http://' + host });
let liveHtml = null;
let liveFailTimes = []; // เวลาที่หน้าเว็บโหมดสดหลุดเร็วผิดปกติ ไว้ตัดสินใจสลับไปโหมดสำรองอัตโนมัติ
let forceFrozenUntil = 0;
function liveIsShaky() { const now = Date.now(); liveFailTimes = liveFailTimes.filter((t) => now - t < 10 * 60 * 1000); return liveFailTimes.length >= 2; }
async function getHtml(host, safeMode) {
  let html;
  const wantLive = LIVE && !safeMode && Date.now() > forceFrozenUntil;
  if (wantLive) { if (!liveHtml) { try { const r = await fetch(process.env.DC_LIVE_URL || 'https://discord.com/channels/@me', { headers: { 'User-Agent': UA } }); liveHtml = await r.text(); log('โหมดสด: โหลดหน้า Discord ล่าสุดแล้ว'); } catch (e) { log('โหมดสด: โหลดไม่ได้ ใช้รุ่นแช่แข็งแทน', e.message); LIVE_FAIL = true; } } html = liveHtml; }
  if (!html) { if (LIVE && safeMode) log('โหมดสด: สลับไปใช้รุ่นสำรองชั่วคราว เพราะเพิ่งหลุดเร็วผิดปกติหลายครั้ง'); html = fs.readFileSync(path.join(APP, 'assets', 'snapshot', 'index.html'), 'utf8'); }
  const rw = ENV_REWRITES(host);
  for (const k of Object.keys(rw)) html = html.replace(new RegExp('("' + k + '"\\s*:\\s*)"[^"]*"'), (m, a) => a + JSON.stringify(rw[k]));
  html = html.replace(/<script[^>]*>[^<]*cdn-cgi\/challenge-platform[\s\S]*?<\/script>/g, '');
  let inj = '<script src="/__dbc/shim.js"></script>';
  for (const f of extInfo.css) inj += '<link rel="stylesheet" href="/__ext/' + f + '">';
  for (const f of extInfo.mainJs) inj += '<script src="/__ext/' + f + '"></script>';
  return /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, (m) => m + inj) : inj + html;
}
let LIVE_FAIL = false;

// ================= เซิร์ฟเวอร์ด้านนอก (รับเบราว์เซอร์) + ซอร์สจริงของ repo ด้านใน =================
function botInfo(token) {
  token = String(token || '').replace(/Bot/g, '').trim();
  const { ApplicationFlagsBitField, IntentsBitField } = require(path.join(APP, 'build', 'AppUtils', 'DiscordBitField'));
  const { ApplicationFlags, GatewayIntentBits } = require(require.resolve('discord-api-types/v10', { paths: [APP] }));
  const cfg = require(path.join(APP, 'build', 'AppCore', 'Config')).default.config;
  return fetch('https://canary.discord.com/api/v9/applications/@me?with_counts=true', { headers: { Authorization: 'Bot ' + token, 'User-Agent': 'DiscordBot (https://github.com/aiko-chan-ai/DiscordBotClient, v' + pkgInfo().version + ')' } })
    .then((r) => { if (!r.ok) throw new Error(r.statusText || 'HTTP ' + r.status); return r.json(); })
    .then((data) => {
      const f = new ApplicationFlagsBitField(data.flags), skip = new Set([GatewayIntentBits.GuildPresences, GatewayIntentBits.GuildMembers, GatewayIntentBits.MessageContent]);
      if (f.has(ApplicationFlags.GatewayPresence) || f.has(ApplicationFlags.GatewayPresenceLimited)) skip.delete(GatewayIntentBits.GuildPresences);
      if (f.has(ApplicationFlags.GatewayGuildMembers) || f.has(ApplicationFlags.GatewayGuildMembersLimited)) skip.delete(GatewayIntentBits.GuildMembers);
      if (f.has(ApplicationFlags.GatewayMessageContent) || f.has(ApplicationFlags.GatewayMessageContentLimited)) skip.delete(GatewayIntentBits.MessageContent);
      if (skip.has(GatewayIntentBits.MessageContent) && !cfg.suppress_intent_warning) throw new Error('MESSAGE_CONTENT is required. เปิด Message Content Intent ใน Developer Portal > Bot (หรือตั้ง suppress_intent_warning=true ใน dbc-data/userdata/config.ini)');
      return { success: true, data, intents: IntentsBitField.getIntents(...Array.from(skip)), allShards: Math.ceil((data.bot_approximate_guild_count ?? data.approximate_guild_count ?? 0) / Number(cfg.guilds_per_shard)) || 1 };
    }).catch((e) => { log('getBotInfo ไม่ผ่าน:', e.message); return { success: false, message: e.message }; });
}
const sseClients = new Set();
function toRenderer(channel, ...args) { const s = 'data: ' + JSON.stringify({ channel, args }) + '\n\n'; sseClients.forEach((c) => { try { c.write(s); } catch {} }); }
const readBody = (req) => new Promise((ok) => { const c = []; req.on('data', (d) => c.push(d)); req.on('end', () => ok(Buffer.concat(c).toString('utf8'))); });
const sendJson = (res, o, code) => { res.writeHead(code || 200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(o === undefined ? null : o)); };
function ensureSnapshotFiles() {
  const d = path.join(APP, 'assets', 'snapshot'); fs.mkdirSync(d, { recursive: true });
  const defs = { 'user_experiments.json': '{}', 'apex_experiments.json': '{"evaluation_id":"","assignments":[]}', 'guild_experiments.json': '[]' };
  for (const [f, v] of Object.entries(defs)) if (!fs.existsSync(path.join(d, f))) { log('เตือน: ไม่พบ ' + f + ' ใน release ใช้ค่าว่างแทน (ฟีเจอร์ทดลองบางอย่างอาจไม่ครบ)'); fs.writeFileSync(path.join(d, f), v); }
}
async function startInner() {
  ensureSnapshotFiles();
  const shims = { electron: electronShim(), 'electron-log': Object.assign(logScope('main'), { scope: logScope, default: { scope: logScope } }), selfsigned: { generate: () => ({ private: '', cert: '' }) }, 'electron-updater': {}, 'electron-context-menu': () => {} };
  const orig = Module._load;
  Module._load = function (request, parent, isMain) {
    if (Object.prototype.hasOwnProperty.call(shims, request)) return shims[request];
    if (request.startsWith('src/')) request = path.join(APP, 'build', request.slice(4));
    return orig.call(this, request, parent, isMain);
  };
  https.createServer = (o, app) => http.createServer(app); // ของ repo เดิมใช้ https ในเครื่อง Electron ที่นี่ (เฉพาะเซิร์ฟเวอร์ภายในของ repo) ใช้ http ธรรมดาแทน
  const ipcMain = shims.electron.ipcMain;
  globalThis.botClient = { ipcMain, app: shims.electron.app, win: { webContents: { send: (ch, ...a) => toRenderer(ch, ...a) }, isDestroyed: () => false }, config: null };
  let mod;
  try { mod = require(path.join(APP, 'build', 'AppCore', 'APIServer.js')); }
  catch (e) {
    if (e.code !== 'MODULE_NOT_FOUND' || !/Cannot find module '[^./]/.test(e.message) || fs.existsSync(path.join(APP, '.npm-done'))) throw e;
    log('ขาดโมดูล (' + e.message.split('\n')[0] + ') กำลังติดตั้ง dependencies ด้วย npm (ครั้งเดียว)…');
    const r = run('npm', ['install', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund'], { cwd: APP }); if (r.status) throw e;
    fs.writeFileSync(path.join(APP, '.npm-done'), '1');
    for (const k of Object.keys(require.cache)) if (k.startsWith(APP)) delete require.cache[k];
    mod = require(path.join(APP, 'build', 'AppCore', 'APIServer.js'));
  }
  const start = mod.default || mod;
  const port = await start(); log('เซิร์ฟเวอร์จริงของ repo พร้อมแล้ว (ภายในพอร์ต ' + port + ')'); return port;
}
async function main() {
  if (ARGV.includes('--info')) { const r = await fetch(RELEASE_API, { headers: { 'User-Agent': 'dbclient', Accept: 'application/vnd.github+json' } }); const j = await r.json(); log('release ' + j.tag_name + ': ' + (j.assets || []).map((a) => a.name + ' (' + Math.round(a.size / 1048576) + 'MB)').join(', ')); process.exit(0); }
  await setup(ARGV.includes('--setup'));
  loadExtInfo();
  const innerPort = await startInner();
  const Exp = require(path.join(APP, 'build', 'AppUtils', 'Experiments.js'));
  const Constants = require(path.join(APP, 'build', 'AppCore', 'Constants.js')).default;
  const PAGE = (p) => ['/', '/app', '/login'].includes(p) || p.startsWith('/channels/');
  const server = (req, res) => { (async () => {
    try {
      const url = new URL(req.url, 'http://x'), p = url.pathname, host = req.headers.host || ('127.0.0.1:' + PORT);
      const hostOk = /^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/.test(host) || ALLOWED_HOSTS.includes(host.split(':')[0]);
      if (!hostOk) { res.writeHead(403); return res.end('forbidden'); }
      if (ACCESS_KEY) {
        const cookies = Object.fromEntries((req.headers.cookie || '').split(';').map((x) => x.trim().split('=')).filter((x) => x[0]));
        const given = url.searchParams.get('key') || cookies.dbckey;
        if (given !== ACCESS_KEY) {
          res.writeHead(401, { 'Content-Type': 'text/html; charset=utf-8' });
          return res.end('<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><body style="font:16px system-ui;background:#1e1f22;color:#dbdee1;display:flex;align-items:center;justify-content:center;height:100vh;margin:0"><form style="text-align:center" method=GET><input name=key placeholder="รหัสผ่าน" style="padding:10px;border-radius:6px;border:0;font-size:16px"><button style="padding:10px 16px;border-radius:6px;border:0;background:#5865f2;color:#fff;margin-left:6px;font-size:16px">เข้า</button></form></body>');
        } else if (url.searchParams.get('key')) {
          res.setHeader('Set-Cookie', 'dbckey=' + ACCESS_KEY + '; Max-Age=31536000; Path=/; HttpOnly; SameSite=Lax' + (useTls ? '; Secure' : ''));
        }
      }
      if (p === '/__dbc/shim.js') { res.writeHead(200, { 'Content-Type': 'text/javascript', 'Cache-Control': 'no-store' }); return res.end(shimSource()); }
      if (p === '/__dbc/livefail' && req.method === 'POST') {
        liveFailTimes.push(Date.now());
        let forced = false;
        if (liveIsShaky() && Date.now() > forceFrozenUntil) { forceFrozenUntil = Date.now() + 15 * 60 * 1000; forced = true; log('โหมดสดหลุดเร็วผิดปกติซ้ำหลายครั้งในเวลาสั้นๆ สลับไปใช้รุ่นสำรองให้ก่อน 15 นาที (ลองโหมดสดใหม่เองได้ด้วยการปิดเปิดแอปใหม่หลังจากนั้น)'); }
        return sendJson(res, { ok: 1, forced });
      }
      if (p === '/__dbc/log' && req.method === 'POST') { try { const j = JSON.parse(await readBody(req)); log('หน้าเว็บ> [' + j.t + '] ' + j.m); } catch {} res.writeHead(204); return res.end(); }
      if (p === '/__dbc/events') { res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' }); res.write('retry: 1500\n\n'); sseClients.add(res); const ka = setInterval(() => { try { res.write(': ka\n\n'); } catch {} }, 20000); req.on('close', () => { clearInterval(ka); sseClients.delete(res); }); return; }
      if (p === '/__dbc/ipc' && req.method === 'POST') { const j = JSON.parse(await readBody(req)); globalThis.botClient.ipcMain.emit(j.channel, { sender: null }, ...(j.args || [])); return sendJson(res, { ok: 1 }); }
      if (p === '/__dbc/native/version') return sendJson(res, { name: pkgInfo().productName || 'DiscordBotClient', version: pkgInfo().version });
      if (p === '/__dbc/native/defaultuser') return sendJson(res, Constants.UserDefaultPatch);
      if (p === '/__dbc/native/exp' && req.method === 'POST') { const j = JSON.parse(await readBody(req)); return sendJson(res, j.type === 'user' ? Exp.UserExperiment(j.allData || [], j.botId) : j.type === 'guild' ? Exp.GuildExperiment() : Exp.ApexExperiment(j.botId)); }
      if (p === '/__dbc/native/botinfo' && req.method === 'POST') { const j = JSON.parse(await readBody(req)); return sendJson(res, await botInfo(j.token)); }
      if (p.startsWith('/__ext/')) {
        const rel = decodeURIComponent(p.slice(7)), f = path.resolve(extDir, rel);
        if (!f.startsWith(extDir + path.sep) || !fs.existsSync(f) || !fs.statSync(f).isFile()) { res.writeHead(404); return res.end(); }
        res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); return fs.createReadStream(f).pipe(res);
      }
      if (req.method === 'GET' && PAGE(p)) { const safeMode = url.searchParams.has('dbcsafe') || liveIsShaky(); const html = await getHtml(host, safeMode); res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' }); return res.end(html); }
      const pr = http.request({ host: '127.0.0.1', port: innerPort, method: req.method, path: req.url, headers: req.headers }, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
      pr.on('error', (e) => { if (!res.headersSent) res.writeHead(502); res.end('inner error ' + e.message); });
      req.pipe(pr);
    } catch (e) { log('ผิดพลาด', req.url.split('?')[0], e); if (!res.headersSent) res.writeHead(500); res.end(String(e.message)); }
  })(); };
  const tlsMode = process.env.DC_NO_TLS ? false : ensureTls(); // false | true(self-signed) | 'real'(เช่น Let's Encrypt)
  const useTls = !!tlsMode;
  const tlsOpts = tlsMode === 'real' ? { key: fs.readFileSync(process.env.DC_TLS_KEY), cert: fs.readFileSync(process.env.DC_TLS_CERT) } : { key: fs.readFileSync(TLSKEY), cert: fs.readFileSync(TLSCERT) };
  const realServer = useTls ? realHttpsCreateServer(tlsOpts, server) : http.createServer(server);
  realServer.on('upgrade', (req, sock) => sock.destroy());
  realServer.on('error', (e) => { log(e.code === 'EADDRINUSE' ? 'พอร์ต ' + PORT + ' ถูกใช้อยู่ ปิดตัวเก่าด้วย Ctrl+C หรือรัน PORT=9000 node dbclient.js' : e); process.exit(1); });
  realServer.listen(PORT, BIND, () => {
    const scheme = useTls ? 'https' : 'http'; const showHost = BIND === '0.0.0.0' ? (ALLOWED_HOSTS[0] || '<โดเมนหรือ IP ของเครื่องนี้>') : '127.0.0.1';
    log('พร้อมแล้ว เปิด ' + scheme + '://' + showHost + (PORT === (useTls ? 443 : 80) ? '' : ':' + PORT) + ' ในเบราว์เซอร์ แล้วใส่ Bot Token'
      + (tlsMode === true ? ' (ใบรับรองสร้างเอง เบราว์เซอร์จะเตือนครั้งแรก กด Advanced > Proceed)' : tlsMode === 'real' ? ' (ใบรับรองของจริง ไม่มีคำเตือน)' : '')
      + (ACCESS_KEY ? ' | ต้องใส่ ?key=... ครั้งแรก (ดูรหัสผ่านที่ตั้งไว้)' : '')
      + (LIVE ? '  [โหมดสด]' : '  [รุ่นแช่แข็ง build ' + (fs.readFileSync(path.join(APP, 'assets', 'snapshot', 'index.html'), 'utf8').match(/"BUILD_NUMBER":\s*"(\d+)"/) || [])[1] + ']'));
    if (BIND === '0.0.0.0' && !ACCESS_KEY) log('⚠ คำเตือน: เปิดรับจากอินเทอร์เน็ตสาธารณะโดยไม่ได้ตั้งรหัสผ่าน (DC_ACCESS_KEY) ใครก็เข้าหน้านี้ได้ แนะนำให้ตั้งรหัสผ่านไว้เสมอ');
  });
}
main().catch((e) => { log('ผิดพลาดตอนเริ่ม:', e.message || e); log('ส่งบรรทัดด้านบนมาให้ผมดู หรือดูไฟล์ dbc-data/debug.log'); process.exit(1); });
