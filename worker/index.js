/**
 * PlayTime backend.
 *
 * The public site is static files in docs/, served by Cloudflare before this
 * code runs. This worker only answers two things:
 *   POST /api/hit  - counts one page view (no cookies, no IP stored)
 *   /admin...      - the owner's dashboard, behind an admin code
 *   /auth, /api/me, /api/favs - Sign in with Roblox (see auth.js)
 *
 * Secrets (set with `wrangler secret put`, never in this repo):
 *   ADMIN_CODE      the code you type to get in
 *   SESSION_SECRET  random string used to sign the "you are logged in" cookie
 *   ROBLOX_CLIENT_ID, ROBLOX_CLIENT_SECRET  for Sign in with Roblox
 */
import STATS from "./stats.js";
import { handleAuth } from "./auth.js";

const COOKIE = "pt_admin";
const SESSION_HOURS = 8;
const MAX_TRIES = 5;            // failed logins allowed...
const WINDOW_MINUTES = 15;      // ...within this many minutes, per visitor
const SAFE_PATH = /^\/[A-Za-z0-9/._-]*$/;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    try {
      if (path === "/api/hit" && request.method === "POST") return await recordHit(request, env);
      if (path === "/api/time" && request.method === "POST") return await recordTime(request, env);
      if (path === "/admin/todo" && request.method === "POST") return await setTodo(request, env);
      if (path === "/admin") return await adminPage(request, env);
      if (path === "/admin/login" && request.method === "POST") return await login(request, env);
      if (path === "/admin/logout" && request.method === "POST") return await logout(env);
      if (path === "/admin/data") return await adminData(request, env);
      const signIn = await handleAuth(request, env, path);
      if (signIn) return signIn;
    } catch (err) {
      // Log the detail for us (Cloudflare observability), but never show visitors the
      // internals: these errors now cover sign-in and the database too.
      console.error("request failed", path, err && err.stack || err);
      return text("Something went wrong. Please try again.", 500);
    }
    return text("Not found", 404);
  }
};

/* ---------------------------------------------------------------- counting */

async function recordHit(request, env) {
  let p = (await request.text()).trim().split(/[?#]/)[0];
  if (!p || p.length > 120 || !SAFE_PATH.test(p)) p = "/other";
  const day = new Date().toISOString().slice(0, 10);
  await env.DB.prepare(
    "INSERT INTO views (day, path, n) VALUES (?1, ?2, 1) " +
    "ON CONFLICT (day, path) DO UPDATE SET n = n + 1"
  ).bind(day, p).run();
  return new Response(null, { status: 204, headers: { "cache-control": "no-store" } });
}

/**
 * Records how long a page was open and being looked at, sent as "path|seconds"
 * when the visitor leaves. No cookies and nothing identifying: we only ever add
 * to a running total, so one visit cannot be told apart from another.
 */
async function recordTime(request, env) {
  const [rawPath, rawSeconds] = (await request.text()).split("|");
  const p = (rawPath || "").trim().split(/[?#]/)[0];
  const seconds = Math.round(Number(rawSeconds));
  // Ignore instant bounces and anything silly (a tab left open all day).
  if (!p || p.length > 120 || !SAFE_PATH.test(p)) return noContent();
  if (!Number.isFinite(seconds) || seconds < 1 || seconds > 3600) return noContent();
  const day = new Date().toISOString().slice(0, 10);
  await env.DB.prepare(
    "INSERT INTO dwell (day, path, seconds, hits) VALUES (?1, ?2, ?3, 1) " +
    "ON CONFLICT (day, path) DO UPDATE SET seconds = seconds + ?3, hits = hits + 1"
  ).bind(day, p, seconds).run();
  return noContent();
}

const noContent = () => new Response(null, { status: 204, headers: { "cache-control": "no-store" } });

/* --------------------------------------------------------------- checklist */

async function setTodo(request, env) {
  if (!(await loggedIn(request, env))) return json({ error: "Not logged in" }, 401);
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(request.url).host) return json({ error: "Blocked" }, 403);
  let body;
  try { body = await request.json(); } catch { return json({ error: "Bad request" }, 400); }
  const key = String(body?.key || "");
  if (!/^[a-z0-9_]{1,40}$/.test(key)) return json({ error: "Bad request" }, 400);
  await env.DB.prepare("UPDATE todos SET done = ?2 WHERE key = ?1").bind(key, body.done ? 1 : 0).run();
  return json({ ok: true });
}

/* ------------------------------------------------------------------ login */

/** Compares two strings without leaking which character differed. */
function sameSecret(a, b) {
  const x = new TextEncoder().encode(a), y = new TextEncoder().encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

async function hmac(secret, message) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}

/** One-way, salted fingerprint of a visitor, used only to slow down code guessing. */
async function visitorHash(request, env) {
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  return (await hmac(env.SESSION_SECRET || "unset", "rl:" + ip)).slice(0, 32);
}

async function makeCookie(env) {
  const expires = Date.now() + SESSION_HOURS * 3600e3;
  const value = `${expires}.${await hmac(env.SESSION_SECRET || "unset", String(expires))}`;
  return `${COOKIE}=${value}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${SESSION_HOURS * 3600}`;
}

async function loggedIn(request, env) {
  if (!env.ADMIN_CODE || !env.SESSION_SECRET) return false;
  const raw = (request.headers.get("cookie") || "")
    .split(";").map(c => c.trim()).find(c => c.startsWith(COOKIE + "="));
  if (!raw) return false;
  const [expires, signature] = raw.slice(COOKIE.length + 1).split(".");
  if (!expires || !signature || Number(expires) < Date.now()) return false;
  return sameSecret(signature, await hmac(env.SESSION_SECRET, expires));
}

async function login(request, env) {
  // Only accept the form from our own site (stops other sites posting here).
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(request.url).host) return text("Blocked", 403);
  if (!env.ADMIN_CODE || !env.SESSION_SECRET) return html(loginHtml("The admin code has not been set up yet."), 503);

  const who = await visitorHash(request, env);
  const since = Date.now() - WINDOW_MINUTES * 60e3;
  const { results } = await env.DB.prepare(
    "SELECT COUNT(*) AS tries FROM login_attempts WHERE ip_hash = ?1 AND ts > ?2").bind(who, since).all();
  if ((results?.[0]?.tries ?? 0) >= MAX_TRIES)
    return html(loginHtml(`Too many tries. Wait ${WINDOW_MINUTES} minutes and try again.`), 429);

  const form = await request.formData();
  if (!sameSecret(String(form.get("code") || ""), env.ADMIN_CODE)) {
    await env.DB.batch([
      env.DB.prepare("INSERT INTO login_attempts (ip_hash, ts) VALUES (?1, ?2)").bind(who, Date.now()),
      env.DB.prepare("DELETE FROM login_attempts WHERE ts < ?1").bind(Date.now() - 86400e3)
    ]);
    return html(loginHtml("That code is not right."), 401);
  }
  await env.DB.prepare("DELETE FROM login_attempts WHERE ip_hash = ?1").bind(who).run();
  return new Response(null, { status: 303, headers: { ...noIndex(), location: "/admin", "set-cookie": await makeCookie(env) } });
}

function logout() {
  return new Response(null, {
    status: 303,
    headers: { ...noIndex(), location: "/admin", "set-cookie": `${COOKIE}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0` }
  });
}

/* -------------------------------------------------------------- dashboard */

async function adminPage(request, env) {
  if (!(await loggedIn(request, env))) return html(loginHtml(), 200);
  return html(dashboardHtml(), 200);
}

async function adminData(request, env) {
  if (!(await loggedIn(request, env))) return json({ error: "Not logged in" }, 401);
  const today = new Date().toISOString().slice(0, 10);
  const dayBefore = n => new Date(Date.now() - n * 86400e3).toISOString().slice(0, 10);

  const [daily, pages, totals, time, todos, gameTime, gameViews] = await Promise.all([
    env.DB.prepare("SELECT day, SUM(n) AS n FROM views WHERE day >= ?1 GROUP BY day ORDER BY day").bind(dayBefore(29)).all(),
    // Views and reading time per page, side by side.
    env.DB.prepare(
      "SELECT v.path AS path, SUM(v.n) AS n, " +
      "COALESCE((SELECT SUM(d.seconds) FROM dwell d WHERE d.path = v.path AND d.day >= ?1), 0) AS seconds, " +
      "COALESCE((SELECT SUM(d.hits) FROM dwell d WHERE d.path = v.path AND d.day >= ?1), 0) AS reads " +
      "FROM views v WHERE v.day >= ?1 GROUP BY v.path ORDER BY n DESC LIMIT 15").bind(dayBefore(29)).all(),
    env.DB.prepare("SELECT SUM(n) AS all_time, SUM(CASE WHEN day = ?1 THEN n ELSE 0 END) AS today, " +
                   "SUM(CASE WHEN day >= ?2 THEN n ELSE 0 END) AS week, " +
                   "SUM(CASE WHEN day >= ?3 THEN n ELSE 0 END) AS month FROM views")
      .bind(today, dayBefore(6), dayBefore(29)).all(),
    env.DB.prepare("SELECT SUM(seconds) AS seconds, SUM(hits) AS reads, " +
                   "SUM(CASE WHEN day >= ?1 THEN seconds ELSE 0 END) AS week_seconds, " +
                   "SUM(CASE WHEN day >= ?1 THEN hits ELSE 0 END) AS week_reads FROM dwell").bind(dayBefore(6)).all(),
    env.DB.prepare("SELECT key, label, note, done FROM todos ORDER BY sort").all(),
    // Reading time for every game page, so we can rank games inside each category.
    env.DB.prepare("SELECT path, SUM(seconds) AS seconds, SUM(hits) AS reads FROM dwell " +
                   "WHERE day >= ?1 AND path LIKE '/game/%' GROUP BY path").bind(dayBefore(29)).all(),
    env.DB.prepare("SELECT path, SUM(n) AS n FROM views " +
                   "WHERE day >= ?1 AND path LIKE '/game/%' GROUP BY path").bind(dayBefore(29)).all()
  ]);

  return json({
    views: {
      daily: daily.results || [],
      pages: pages.results || [],
      totals: totals.results?.[0] || { all_time: 0, today: 0, week: 0, month: 0 },
      time: time.results?.[0] || { seconds: 0, reads: 0, week_seconds: 0, week_reads: 0 }
    },
    todos: todos.results || [],
    gameTime: gameTime.results || [],
    gameViews: gameViews.results || [],
    stats: STATS,
    live: await liveCounts()
  });
}

// The collector writes this every ~30 minutes, so these numbers are current even
// when the site has not rebuilt. If it cannot be read, the dashboard quietly
// falls back to the figures baked in at the last build.
const SUMMARY_URL = "https://raw.githubusercontent.com/lbaker12022008-coder/playtimes/data/summary.json";

async function liveCounts() {
  try {
    const res = await fetch(SUMMARY_URL, { cf: { cacheTtl: 120, cacheEverything: true } });
    if (!res.ok) return null;
    const data = await res.json();
    if (!Array.isArray(data?.games)) return null;
    return data;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ pages */

const noIndex = () => ({ "x-robots-tag": "noindex, nofollow", "cache-control": "no-store" });
const text = (body, status) => new Response(body, { status, headers: { ...noIndex(), "content-type": "text/plain; charset=utf-8" } });
const html = (body, status) => new Response(body, { status, headers: { ...noIndex(), "content-type": "text/html; charset=utf-8" } });
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { ...noIndex(), "content-type": "application/json" } });

const SHELL = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>PlayTime admin</title><style>
:root{--bg:#f6f8fb;--card:#fff;--ink:#14213d;--mut:#5b6478;--line:#e1e6ef;--acc:#2563eb;--surface:#fff;color-scheme:light}
@media(prefers-color-scheme:dark){:root{--bg:#0f1724;--card:#182235;--ink:#eef2fb;--mut:#a3aec4;--line:#2a3750;--acc:#7aa7ff;--surface:#182235;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 ui-rounded,"SF Pro Rounded",Nunito,system-ui,-apple-system,"Segoe UI",sans-serif}
.w{max-width:960px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.05rem;margin:28px 0 10px}
a{color:var(--acc)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:12px 0}
.mut{color:var(--mut)}.small{font-size:.86rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.tile b{display:block;font-size:1.9rem;line-height:1.1;letter-spacing:-.01em}
.chart{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;align-items:end;gap:2px;height:140px;margin-top:6px}
.chart div{background:var(--acc);border-radius:4px 4px 0 0;min-height:2px;position:relative}
.chart div:hover{outline:2px solid var(--surface);outline-offset:-2px;filter:brightness(1.12)}
.xaxis{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:2px;font-size:.72rem;color:var(--mut);margin-top:4px}
.xaxis span{text-align:center;overflow:hidden;white-space:nowrap}
.rows{display:grid;gap:12px;margin-top:10px}
.row{display:grid;grid-template-columns:minmax(0,1fr) 64px;gap:2px 10px;align-items:center;font-size:.9rem}
.row .barwrap{background:var(--line);border-radius:4px;overflow:hidden;height:22px;display:flex;align-items:center}
.row .bar{background:var(--acc);height:22px;border-radius:0 4px 4px 0;min-width:2px}
.row .lbl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.84rem}
.row .val{text-align:right;font-variant-numeric:tabular-nums;color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.wrap{overflow-x:auto}
.cats{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px;margin-top:10px}
.catbox{border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.catbox>b{display:block;margin-bottom:4px}
.catbox table{font-size:.85rem;width:100%;table-layout:fixed}
.catbox th,.catbox td{padding:5px 4px}
.catbox td:nth-child(2){overflow:hidden;text-overflow:ellipsis}
.catbox th:nth-child(3),.catbox td:nth-child(3){width:72px}
.catbox th:nth-child(4),.catbox td:nth-child(4){width:46px}
.catbox th:first-child,.catbox td:first-child{width:22px}
.catbox .rank{color:var(--mut)}
.todo{display:flex;gap:11px;align-items:flex-start;padding:10px 2px;border-top:1px solid var(--line);cursor:pointer}
.todo:first-of-type{border-top:0}
.todo input{margin:3px 0 0;width:19px;height:19px;flex:none;accent-color:var(--acc);cursor:pointer}
.todo i{display:block;font-style:normal;margin-top:2px}
.todo.done b{text-decoration:line-through;color:var(--mut);font-weight:600}
input,button{font:inherit}
input[type=password]{width:100%;padding:12px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
button{background:var(--acc);color:#fff;border:0;padding:11px 18px;border-radius:10px;font-weight:700;cursor:pointer}
.ghost{background:transparent;color:var(--mut);border:1px solid var(--line)}
.err{background:#fde8e8;color:#9b1c1c;border-radius:10px;padding:10px 12px;margin:10px 0}
@media(prefers-color-scheme:dark){.err{background:#3b1d1d;color:#fca5a5}}
.ok{color:#15803d}.bad{color:#b91c1c}
@media(prefers-color-scheme:dark){.ok{color:#4ade80}.bad{color:#f87171}}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
</style></head><body><div class="w">`;

function loginHtml(error = "") {
  return SHELL + `<h1>PlayTime admin</h1>
<p class="mut small">Private page. Not listed on the site or in Google.</p>
${error ? `<div class="err">${error}</div>` : ""}
<form method="POST" action="/admin/login" class="card">
<label for="code"><b>Admin code</b></label>
<p><input id="code" name="code" type="password" autocomplete="current-password" autofocus required></p>
<button type="submit">Sign in</button></form>
</div></body></html>`;
}

function dashboardHtml() {
  return SHELL + `<div class="top"><h1>PlayTime admin</h1>
<form method="POST" action="/admin/logout"><button class="ghost" type="submit">Sign out</button></form></div>
<p class="mut small" id="built">Loading&hellip;</p>
<div id="app"></div>
<script>
const $ = (s) => document.querySelector(s);
const num = (n) => (n || 0).toLocaleString();
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ago = (iso) => { if(!iso) return 'never'; const h=(Date.now()-new Date(iso))/3.6e6;
  return h<1 ? Math.round(h*60)+' min ago' : h<48 ? Math.round(h)+' hours ago' : Math.round(h/24)+' days ago'; };
const mins = (s) => { s = Math.round(s || 0); return s < 60 ? s + 's' : Math.floor(s/60) + 'm ' + (s%60) + 's'; };
const agoSecs = (unix) => { if(!unix) return 'unknown'; const m=(Date.now()/1000-unix)/60;
  return m<2 ? 'just now' : m<90 ? Math.round(m)+' min ago' : Math.round(m/60)+' hours ago'; };
// The collector saves about 144 player counts per game per day.
const hoursLeft = (needed) => { const h = needed / 6;
  return h < 1 ? 'under an hour' : h < 48 ? Math.round(h) + ' hours' : Math.round(h/24) + ' days'; };

fetch('/admin/data').then(r => r.json()).then(render).catch(e => { $('#app').textContent = 'Could not load data: ' + e.message; });

function render(d) {
  const v = d.views, s = d.stats || {}, t = s.totals || {}, site = s.site || {};
  const builtHours = s.built_at ? (Date.now() - new Date(s.built_at)) / 3.6e6 : 999;
  $('#built').innerHTML = 'Site last built ' + ago(s.built_at) +
    (s.built_at ? ' (' + s.built_at.replace('T', ' ').slice(0, 16) + ' UTC)' : '') +
    (builtHours > 26 ? ' <b class="bad">&mdash; that is overdue; a build may be failing.</b>' : '');

  // Visitors -------------------------------------------------------------
  const days = [];
  for (let i = 13; i >= 0; i--) {
    const day = new Date(Date.now() - i * 864e5).toISOString().slice(0, 10);
    const hit = (v.daily || []).find(r => r.day === day);
    days.push({ day, n: hit ? hit.n : 0 });
  }
  const peak = Math.max(1, ...days.map(x => x.n));
  const bars = days.map(x => '<div style="height:' + Math.max(2, x.n / peak * 100) + '%" title="' +
    x.day + ': ' + num(x.n) + ' page views"></div>').join('');
  const ticks = days.map((x, i) => '<span>' + (i % 2 === 0 ? x.day.slice(8) + '/' + x.day.slice(5, 7) : '') + '</span>').join('');

  const topMax = Math.max(1, ...(v.pages || []).map(p => p.n));
  const topRows = (v.pages || []).map(p => {
    const avg = p.reads ? mins(p.seconds / p.reads) : '-';
    return '<div class="row">' +
      '<div class="lbl" style="grid-column:1/-1">' + esc(p.path) +
      ' <span class="mut">&middot; ' + avg + ' average</span></div>' +
      '<div class="barwrap"><div class="bar" style="width:' + (p.n / topMax * 100) + '%" title="' +
      esc(p.path) + ': ' + num(p.n) + ' page views, ' + avg + ' average time"></div></div>' +
      '<div class="val">' + num(p.n) + '</div></div>';
  }).join('') || '<p class="mut small">No page views recorded yet.</p>';

  // Which games hold attention, best three in each category ----------------
  const timeByPath = {}, viewsByPath = {};
  (d.gameTime || []).forEach(r => { timeByPath[r.path] = r; });
  (d.gameViews || []).forEach(r => { viewsByPath[r.path] = r.n; });

  const byCategory = {};
  (s.games || []).forEach(g => {
    if (!g.slug) return;                       // older builds did not record it
    const row = timeByPath['/game/' + g.slug + '.html'];
    if (!row || !row.reads) return;            // nobody has read it yet
    const cat = g.genre || 'Uncategorised';
    (byCategory[cat] = byCategory[cat] || []).push({
      name: g.name,
      avg: row.seconds / row.reads,
      reads: row.reads,
      views: viewsByPath['/game/' + g.slug + '.html'] || 0
    });
  });

  const catNames = Object.keys(byCategory).sort();
  const catBlocks = catNames.map(cat => {
    const top = byCategory[cat].sort((a, b) => b.avg - a.avg).slice(0, 3);
    const rows = top.map((g, i) =>
      '<tr><td class="rank">' + (i + 1) + '</td><td title="' + esc(g.name) + '">' + esc(g.name) + '</td>' +
      '<td class="num">' + mins(g.avg) + '</td>' +
      '<td class="num mut">' + num(g.views) + '</td></tr>').join('');
    return '<div class="catbox"><b>' + esc(cat) + '</b><table class="tbl">' +
      '<tr><th></th><th>Game</th><th class="num">Avg time</th><th class="num">Views</th></tr>' +
      rows + '</table></div>';
  }).join('');

  // Games ----------------------------------------------------------------
  // Counts come from the collector (fresh). Everything needing a full rebuild to
  // work out - typical players, trend, verdict - comes from the last build.
  const live = d.live;
  const byId = {}, byName = {};
  (live?.games || []).forEach(g => { byId[String(g.id)] = g; if (g.name) byName[g.name] = g; });
  const fresh = g => byId[String(g.id)] || byName[g.name] || null;
  const spanDays = g => (g.first && g.last) ? Math.round((g.last - g.first) / 864) / 100 : null;

  const games = (s.games || []).slice().sort((a, b) => b.avg7 - a.avg7);
  const gameRows = games.map(g => {
    const f = fresh(g);
    const samples = f ? f.samples : g.samples;
    const days = (f && spanDays(f) !== null) ? spanDays(f) : g.days;
    return '<tr><td>' + esc(g.name) + '</td><td>' + esc(g.genre || '') + '</td>' +
      '<td class="num">' + num(samples) + '</td><td class="num">' + days + '</td>' +
      '<td class="num">' + num(g.avg7) + '</td><td class="num">' +
      (g.trend === null ? '<span class="mut">-</span>' : (g.trend >= 0 ? '<span class="ok">+' : '<span class="bad">') + g.trend + '%</span>') +
      '</td></tr>';
  }).join('');

  // Who is still short of MIN_SAMPLES, worked out from the live counts.
  const min = site.min_samples || 0;
  const waitingList = live
    ? live.games.filter(g => g.samples < min)
        .sort((a, b) => b.samples - a.samples)
        .map(g => ({ name: g.name || g.id, samples: g.samples }))
    : (s.waiting || []);
  const waiting = waitingList.map(w => '<tr><td>' + esc(w.name) + '</td><td class="num">' +
    num(w.samples) + '</td><td class="num">' + num(min) + '</td>' +
    '<td class="num">' + (w.samples >= min ? 'ready' : hoursLeft(min - w.samples)) + '</td></tr>').join('');

  const missing = (s.missing_ids || []).map(id => '<li>' + esc(id) + '</li>').join('');

  const check = (done, label) => '<tr><td>' + (done ? '<span class="ok">Done</span>' : '<span class="bad">To do</span>') +
    '</td><td>' + label + '</td></tr>';

  const tile = (label, value) => '<div class="tile"><span class="mut small">' + label + '</span><b>' + num(value) + '</b></div>';

  const out = [
    '<h2>Visitors</h2><div class="tiles">',
    tile('Today', v.totals.today), tile('Last 7 days', v.totals.week),
    tile('Last 30 days', v.totals.month), tile('All time', v.totals.all_time),
    '</div>',
    '<div class="tiles" style="margin-top:12px">',
    '<div class="tile"><span class="mut small">Time on a page (7 days)</span><b>' +
      ((v.time && v.time.week_reads) ? mins(v.time.week_seconds / v.time.week_reads) : '-') + '</b></div>',
    '<div class="tile"><span class="mut small">Time on a page (all time)</span><b>' +
      ((v.time && v.time.reads) ? mins(v.time.seconds / v.time.reads) : '-') + '</b></div>',
    '<div class="tile"><span class="mut small">Total time read</span><b>' +
      (v.time ? Math.round((v.time.seconds || 0) / 60).toLocaleString() + ' min' : '-') + '</b></div>',
    '</div>',
    '<div class="card"><b>Page views per day</b> <span class="mut small">last 14 days</span>',
    '<div class="chart">', bars, '</div><div class="xaxis">', ticks, '</div>',
    '<p class="mut small">Hover a bar for the exact number. Counted without cookies, so one person ',
    'opening five pages counts as five.</p></div>',
    '<div class="card"><b>Most visited pages</b> <span class="mut small">last 30 days</span>',
    '<div class="rows">', topRows, '</div></div>',

    '<div class="card"><b>Games that hold attention</b> ',
    '<span class="mut small">top 3 in each category, last 30 days</span>',
    catBlocks
      ? '<div class="cats">' + catBlocks + '</div>' +
        '<p class="mut small">Ranked by how long the page stays open on average. ' +
        'A game read by only a handful of people can top its category on luck, so check the views column.</p>'
      : '<p class="mut small">No reading time recorded on game pages yet. This fills in once ' +
        'visitors arrive, and each game needs at least one visit lasting a second or more.</p>',
    '</div>',

    '<h2>Data</h2>',
    '<p class="mut small">' + (live
      ? 'Counts updated ' + agoSecs(live.updated) + ', straight from the collector.'
      : 'Live counts unavailable, so these are from the last site build.') + '</p>',
    '<div class="tiles">',
    tile('Games tracked', live ? live.games.length : t.games_tracked),
    tile('Pages built', t.pages_built),
    tile('Player counts saved', live ? live.total_samples : t.samples),
    tile('Ready for trends', t.trend_ready),
    tile('Games with events', t.with_events), tile('Events coming up', t.upcoming_events),
    '</div>',
    '<div class="card"><b>Every game</b><div class="wrap"><table>',
    '<tr><th>Game</th><th>Category</th><th class="num">Counts</th><th class="num">Days</th>',
    '<th class="num">Typical players</th><th class="num">vs last week</th></tr>',
    gameRows || '<tr><td colspan="6" class="mut">No games yet.</td></tr>',
    '</table></div></div>',
    waiting ? '<div class="card"><b>Waiting for enough data</b>' +
      '<p class="mut small">Still short of MIN_SAMPLES, so they have no page yet. ' +
      (live ? 'Counts are live; the page appears at the next build after a game is ready.'
            : 'From the last build.') + '</p>' +
      '<div class="wrap"><table><tr><th>Game</th><th class="num">Counts so far</th>' +
      '<th class="num">Needed</th><th class="num">Time left</th></tr>' +
      waiting + '</table></div></div>' : '',
    missing ? '<div class="card"><b>IDs Roblox did not return</b>' +
      '<p class="mut small">In games.txt but Roblox sent nothing back. Usually a wrong ID or a removed game.</p>' +
      '<ul>' + missing + '</ul></div>' : '',

    '<h2>To do</h2>',
    '<div class="card"><p class="mut small">Tick these off as you go. Saved here, so it is the same on any device.</p>',
    (d.todos || []).map(function (t) {
      return '<label class="todo' + (t.done ? ' done' : '') + '">' +
        '<input type="checkbox" data-key="' + esc(t.key) + '"' + (t.done ? ' checked' : '') + '>' +
        '<span><b>' + esc(t.label) + '</b>' +
        (t.note ? '<i class="mut small">' + esc(t.note) + '</i>' : '') + '</span></label>';
    }).join('') || '<p class="mut small">Nothing on the list.</p>',
    '</div>',

    '<h2>Settings the site checks itself</h2><div class="card"><table>',
    check(!site.noindex, 'Let Google list the site (NOINDEX = False)'),
    check(site.min_samples >= 200, 'MIN_SAMPLES back to 200 (now ' + num(site.min_samples) + ')'),
    check(!!site.domain, 'Domain set in build_site.py' + (site.domain ? ': ' + esc(site.domain) : '')),
    check(!!site.contact, 'Contact email set (needed for AdSense)'),
    check(!!site.ads, 'AdSense code pasted in'),
    check((t.pages_built || 0) >= 20, '20+ game pages with real data (now ' + num(t.pages_built) + ')'),
    '</table></div>'
  ];
  $('#app').innerHTML = out.join('');

  // Ticking a box saves straight away; it puts itself back if the save fails.
  Array.prototype.forEach.call(document.querySelectorAll('.todo input'), function (box) {
    box.onchange = function () {
      const row = box.closest('.todo');
      row.classList.toggle('done', box.checked);
      fetch('/admin/todo', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ key: box.dataset.key, done: box.checked })
      }).then(function (r) { if (!r.ok) throw 0; }).catch(function () {
        box.checked = !box.checked;
        row.classList.toggle('done', box.checked);
        alert('Could not save that. Check your connection and try again.');
      });
    };
  });
}
</script></div></body></html>`;
}
