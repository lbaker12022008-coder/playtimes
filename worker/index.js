/**
 * PlayTime backend.
 *
 * The public site is static files in docs/, served by Cloudflare before this
 * code runs. This worker only answers two things:
 *   POST /api/hit  - counts one page view (no cookies, no IP stored)
 *   /admin...      - the owner's dashboard, behind an admin code
 *   /auth, /api/me, /api/favs - Sign in with Roblox (see auth.js)
 *   /api/push/*    - browser notifications (see push.js), plus a cron that sends them
 *
 * Secrets (set with `wrangler secret put`, never in this repo):
 *   ADMIN_CODE      the code you type to get in
 *   SESSION_SECRET  random string used to sign the "you are logged in" cookie
 *   ROBLOX_CLIENT_ID, ROBLOX_CLIENT_SECRET  for Sign in with Roblox
 */
import STATS from "./stats.js";
import { LIGHT, DARK } from "./theme.js";
import { handleAuth } from "./auth.js";
import { handlePush, runPushCron } from "./push.js";
import { readOps, syncOps } from "./ops.js";

const COOKIE = "pt_admin";
const SESSION_HOURS = 8;
const MAX_TRIES = 5;            // failed logins allowed...
const WINDOW_MINUTES = 15;      // ...within this many minutes, per visitor
const SAFE_PATH = /^\/[A-Za-z0-9/._-]*$/;

// The one address sign-in may run on: the only /auth/callback Roblox has registered.
// Written down rather than derived, unlike the cookie's Domain, because the whole
// point is to name the right host when the request arrived on a wrong one.
const SITE_HOST = "playtimestats.com";
// ...except on a computer running `wrangler dev`, which is nobody's wrong address.
const LOCAL_HOST = /^(localhost|127\.0\.0\.1|\[::1\])$/;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    // One address, one session. The sign-in cookie carries no Domain, so it belongs
    // to the exact host it was set on: someone who signed in on playtimestats.com and
    // then opened a www link arrived with no cookie at all and read as signed out,
    // which looked like being logged out at random. Sending www to the bare name
    // before anything else means there is only ever one host to be signed in on, and
    // it is the one every canonical tag and the whole sitemap already name.
    if (url.hostname.startsWith("www.")) {
      url.hostname = url.hostname.slice(4);
      return Response.redirect(url.toString(), 301);
    }

    // Sign-in may only START on the real site. redirectUri() in auth.js builds the
    // address Roblox is asked to send people back to out of the address the request
    // came in on, so a sign-in begun on the workers.dev test copy asks Roblox to
    // return to workers.dev - an address Roblox refuses, and will not let anybody
    // register, because it is a domain anyone can take a subdomain on. The result is
    // Roblox's red "Redirect URI is invalid for this application" page, which is
    // exactly what the installed PC app hit on 18 Nov 2026 after being installed from
    // that address while an ordinary tab signed in perfectly.
    //
    // Nothing is lost by sending it home: sign-in has never worked on the test copy
    // and cannot be made to. This is deliberately only /auth/login - the rest of the
    // test copy stays browsable, which is what it is for - and it cannot rescue an app
    // already installed on the wrong host, since that app is scoped to that origin and
    // an out-of-scope address opens in a browser tab instead. Only reinstalling moves
    // an app. What it does is turn a dead end into a working sign-in on the real site.
    if (path === "/auth/login" && url.hostname !== SITE_HOST
        && !LOCAL_HOST.test(url.hostname)) {
      url.protocol = "https:";
      url.hostname = SITE_HOST;
      url.port = "";
      // 302, not 301: a browser keeps a 301 for good, and this names a domain that
      // could one day change.
      return Response.redirect(url.toString(), 302);
    }

    try {
      if (path === "/api/hit" && request.method === "POST") return await recordHit(request, env);
      if (path === "/api/time" && request.method === "POST") return await recordTime(request, env);
      if (path === "/admin/todo" && request.method === "POST") return await setTodo(request, env);
      if (path === "/admin") return await adminPage(request, env);
      if (path === "/admin/login" && request.method === "POST") return await login(request, env);
      if (path === "/admin/logout" && request.method === "POST") return await logout(env);
      if (path === "/admin/data") return await adminData(request, env);
      if (path === "/admin/sync" && request.method === "POST") return await syncNow(request, env);
      const signIn = await handleAuth(request, env, path);
      if (signIn) return signIn;
      const notify = await handlePush(request, env, path);
      if (notify) return notify;
    } catch (err) {
      // Log the detail for us (Cloudflare observability), but never show visitors the
      // internals: these errors now cover sign-in and the database too.
      console.error("request failed", path, err && err.stack || err);
      return text("Something went wrong. Please try again.", 500);
    }
    return await notFound(request, env);
  },

  /**
   * The notification job, run by the cron in wrangler.jsonc.
   *
   * A scheduled run has no request to take an origin from, and the ASSETS binding
   * needs an absolute address to look /data.json up by, so the site's own name is
   * used. SITE_ORIGIN can override it, which is what makes this testable against a
   * local `wrangler dev` without editing code.
   *
   * It never throws: an error here would be retried by Cloudflare and logged as a
   * failure, and a notification missed by ten minutes is not worth that. The detail
   * goes to the log instead, where observability will show it.
   */
  async scheduled(event, env, ctx) {
    try {
      const origin = env.SITE_ORIGIN || "https://playtimestats.com";
      const out = await runPushCron(env, origin);
      console.log("notification run", JSON.stringify(out));
    } catch (err) {
      console.error("notification run failed", err && err.stack || err);
    }
    /* Recording whether the back end ran is a separate job in its own try: it talks to
       GitHub, which can be rate limited or simply down, and a notification must never
       be lost because a status panel could not be updated. Second rather than first
       for the same reason - the notifications are what somebody is waiting for. */
    try {
      const ops = await syncOps(env);
      if (ops.failed.length) console.warn("ops sync partial", JSON.stringify(ops));
    } catch (err) {
      console.error("ops sync failed", err && err.stack || err);
    }
  }
};

/**
 * Anything that is not a file in docs/ and not one of our own addresses.
 *
 * Cloudflare serves the real pages before this code runs, so getting here means the
 * address does not exist. We hand back the site's own 404 page with a 404 status, so
 * a visitor gets somewhere useful and a search engine is told plainly that the page
 * is gone rather than being shown a page that looks fine. ASSETS is the binding set
 * in wrangler.jsonc; if it is ever missing we fall back to plain text rather than
 * failing the request.
 */
async function notFound(request, env) {
  try {
    const url = new URL(request.url);
    const res = await env.ASSETS.fetch(new URL("/404.html", url.origin));
    if (res.ok) {
      return new Response(res.body, {
        status: 404,
        headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" }
      });
    }
  } catch (err) {
    console.error("could not load /404.html", err && err.message);
  }
  return text("Not found", 404);
}

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

/**
 * "Refresh system status": fetch the back end's run history from GitHub now rather
 * than waiting for the ten-minute cron.
 *
 * Admin-only and POST-only, with the same cross-site check setTodo uses, because it
 * spends from a rate limit that is shared with every other Cloudflare customer on
 * this egress IP - six GitHub calls a press. It reports what came back rather than
 * answering a bare ok, so a partial failure (GitHub up, one workflow unreadable) is
 * visible instead of looking like a success.
 */
async function syncNow(request, env) {
  if (!(await loggedIn(request, env))) return json({ error: "Not logged in" }, 401);
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(request.url).host) return json({ error: "Blocked" }, 403);
  try {
    const out = await syncOps(env);
    return json({ ok: out.failed.length === 0, synced: out.ok, failed: out.failed });
  } catch (err) {
    return json({ ok: false, error: (err && err.message) || "that did not work" }, 502);
  }
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

  // Sign-ins, saved games and notifications are three live features with rows in
  // this same database, and until 18 Nov 2026 the dashboard mentioned none of them -
  // so "it said it sent one and nothing appeared" meant going and typing a wrangler
  // command, which is exactly the sort of thing this page exists to save.
  //
  // Every one goes through soft(): `users`, `favourites` and the three push tables
  // are created by their own schema files, and a dashboard that will not load at all
  // is a far worse answer than a tile that says nothing yet.
  const soft = async (sql, binds, fallback) => {
    try {
      const st = env.DB.prepare(sql);
      const r = await (binds && binds.length ? st.bind(...binds) : st).all();
      return (r.results && r.results.length) ? r.results : fallback;
    } catch { return fallback; }
  };
  const weekAgo = Date.now() - 7 * 86400e3;
  const [accounts, favs, favTop, devices, devList, watches, watchTop, sent, kinds, climb] =
    await Promise.all([
      soft("SELECT COUNT(*) AS n, SUM(CASE WHEN seen >= ?1 THEN 1 ELSE 0 END) AS active, " +
           "SUM(CASE WHEN created >= ?1 THEN 1 ELSE 0 END) AS joined, MAX(seen) AS last " +
           "FROM users", [weekAgo], [{}]),
      soft("SELECT COUNT(*) AS n, COUNT(DISTINCT rbx_id) AS people FROM favourites", [], [{}]),
      soft("SELECT slug, COUNT(*) AS n FROM favourites GROUP BY slug " +
           "ORDER BY n DESC, slug LIMIT 8", [], []),
      soft("SELECT COUNT(*) AS n, COUNT(DISTINCT rbx_id) AS people, " +
           "SUM(CASE WHEN fails > 0 THEN 1 ELSE 0 END) AS failing, " +
           "SUM(CASE WHEN last_status IS NULL THEN 1 ELSE 0 END) AS untried, " +
           "MAX(last_try) AS last_try FROM push_subs", [], [{}]),
      // Deliberately NOT endpoint, p256dh or auth: those are the device's own address
      // and its keys, nothing here needs them, and a screen is a place things get
      // photographed. Nor rbx_id - this page answers "is it working", not "who".
      soft("SELECT tz, fails, last_status, last_try, created FROM push_subs " +
           "ORDER BY created DESC LIMIT 20", [], []),
      soft("SELECT COUNT(*) AS n, COUNT(DISTINCT rbx_id) AS people, SUM(quiet) AS quiet, " +
           "SUM(busy) AS busy, SUM(events) AS events, SUM(updates) AS updates " +
           "FROM push_watch", [], [{}]),
      soft("SELECT slug, COUNT(*) AS n FROM push_watch GROUP BY slug " +
           "ORDER BY n DESC, slug LIMIT 8", [], []),
      // push_sent is cleared down to two days by runPushCron, so this is a recent
      // count and never a running total. The panel says so rather than implying one.
      soft("SELECT COUNT(*) AS n, MAX(at) AS last FROM push_sent", [], [{}]),
      // What kind of page people open. The Nov 2026 split gave every game four more
      // pages, and nothing said whether anybody reads them.
      soft("SELECT CASE WHEN path = '/' THEN 'The home page' " +
           "WHEN path LIKE '/game/%' THEN 'Game pages' " +
           "WHEN path LIKE '/questions/%' THEN 'Questions pages' " +
           "WHEN path LIKE '/events/%' THEN 'Event pages' " +
           "WHEN path LIKE '/passes/%' THEN 'What costs money pages' " +
           "WHEN path LIKE '/updates/%' THEN 'Update pages' " +
           "WHEN path LIKE '/category/%' THEN 'Category pages' " +
           "ELSE 'Everything else' END AS kind, SUM(n) AS n " +
           "FROM views WHERE day >= ?1 GROUP BY kind ORDER BY n DESC", [dayBefore(29)], []),
      // This week against the week before, per game page. Column names avoid `before`,
      // which SQLite keeps for triggers.
      soft("SELECT path, SUM(CASE WHEN day >= ?1 THEN n ELSE 0 END) AS recent, " +
           "SUM(CASE WHEN day < ?1 THEN n ELSE 0 END) AS earlier FROM views " +
           "WHERE day >= ?2 AND path LIKE '/game/%' GROUP BY path", [dayBefore(6), dayBefore(13)], [])
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
    people: {
      accounts: accounts[0] || {}, favs: favs[0] || {}, favTop,
      devices: devices[0] || {}, devList, watches: watches[0] || {}, watchTop,
      sent: sent[0] || {}
    },
    kinds, climb,
    stats: STATS,
    live: await liveCounts(),
    /* Whether collecting, building and discovering actually ran. Read from our own
       copy in D1, never from GitHub at page-load time: see worker/ops.js. It answers
       available:false rather than throwing if the tables were never created. */
    ops: await readOps(env, 30),
    /* Visitor numbers before this day include our own automated test browsers - one
       day in November recorded 156 views across 114 different pages, which is a sweep
       and not a person. The beacons have skipped automated browsers since, so any
       chart crossing this line has to say so rather than draw it as growth. */
    clean_from: "2026-11-22"
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

/**
 * The dashboard's look. Colours come from theme.js, which build_site.py writes on
 * every build out of the same LIGHT and DARK it uses for the public site, so the two
 * cannot drift apart. The layout is this file's own: the site is for visitors reading
 * about one game, the dashboard is for one person reading numbers.
 *
 * It follows the device's light/dark setting unless the owner pressed the theme
 * button, which is saved under the same pt_theme key the site uses, so a choice made
 * on the site carries over here.
 */
const SHELL = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#724C9A"><title>PlayTime admin</title>
<script>try{var t=localStorage.getItem('pt_theme');if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>
<style>
:root{${LIGHT};color-scheme:light}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){${DARK};color-scheme:dark}}
:root[data-theme=dark]{${DARK};color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:17px/1.6 ui-rounded,"SF Pro Rounded",Nunito,system-ui,-apple-system,"Segoe UI",sans-serif;
-webkit-text-size-adjust:100%}
.w{max-width:1100px;margin:0 auto;padding:0 16px 80px}
a{color:var(--acc)}
h1{font-size:1.5rem;margin:0;letter-spacing:-.02em}
h2{font-size:1.1rem;margin:0 0 4px}
h3{font-size:.95rem;margin:18px 0 2px}
.mut{color:var(--mut)}.small{font-size:.86rem}
.vh{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
input,button,select{font:inherit}

/* ---- the bar across the top, see-through like the site's own header */
.bar{position:sticky;top:0;z-index:9;display:flex;align-items:center;gap:12px;
padding:11px 16px;margin:0 -16px 6px;background:var(--glass);
backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.bar .mark{width:30px;height:30px;flex:none}
.bar b{background:linear-gradient(95deg,var(--acc),var(--acc2));-webkit-background-clip:text;
background-clip:text;-webkit-text-fill-color:transparent;font-size:1.15rem;letter-spacing:-.02em}
.bar .sp{flex:1}
.iconb{width:38px;height:38px;flex:none;display:grid;place-items:center;border-radius:11px;
border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;padding:0}
.iconb:hover{border-color:var(--acc)}
.iconb svg{width:18px;height:18px;fill:currentColor}
/* Exactly the swap the site uses: the moon is hidden by default, and the attribute
   rule is written before the media query so a visitor who chose light keeps the sun
   on a device set to dark. */
.iconb .moon{display:none}
:root[data-theme=dark] .iconb .moon{display:block}
:root[data-theme=dark] .iconb .sun{display:none}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]) .iconb .moon{display:block}
:root:not([data-theme=light]) .iconb .sun{display:none}}

/* ---- tabs: four short pages instead of one very long one */
.tabs{display:flex;gap:6px;overflow-x:auto;padding:6px 0 10px;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs button{white-space:nowrap;background:var(--card);border:1px solid var(--line);
color:var(--ink);padding:9px 16px;border-radius:12px;cursor:pointer;font-weight:600}
.tabs button:hover{border-color:var(--acc)}
.tabs button[aria-selected=true]{background:linear-gradient(95deg,var(--acc),var(--acc2));
border-color:transparent;color:var(--btnink);font-weight:700}
[hidden]{display:none !important}

/* ---- cards and the numbers on them */
.card{background:var(--card);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
border:1px solid var(--line);border-radius:18px;padding:16px 18px;margin:14px 0;box-shadow:var(--sh)}
.pair{display:grid;gap:14px;margin:14px 0}
@media(min-width:760px){.pair{grid-template-columns:1fr 1fr}.pair>.card{margin:0}}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px;margin:14px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:13px 15px;
box-shadow:var(--sh);position:relative;overflow:hidden}
.tile b{display:block;font-size:1.8rem;line-height:1.15;letter-spacing:-.02em;margin-top:1px}
.tile .spark{display:block;width:100%;height:26px;margin-top:4px}
.delta{display:inline-block;font-size:.78rem;font-weight:700;border-radius:8px;padding:1px 7px;
background:var(--shade)}
.delta.up{color:var(--up)}.delta.down{color:var(--down)}
.ok{color:var(--up)}.bad{color:var(--down)}

/* ---- graphs. Drawn as svg so they stay sharp and cost no extra request. */
.graph{display:block;width:100%;height:auto;touch-action:none;border-radius:12px}
.graph:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
.readout{min-height:1.5em;margin:6px 0 0;font-size:.9rem;color:var(--mut)}
.ring{display:block;width:124px;height:124px;margin:2px auto 0}
.range{display:flex;gap:6px;margin-left:auto}
.range button{background:transparent;border:1px solid var(--line);color:var(--mut);
border-radius:9px;padding:4px 10px;font-size:.82rem;cursor:pointer}
.range button[aria-pressed=true]{background:var(--acc);border-color:var(--acc);
color:var(--btnink);font-weight:700}
.head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}

/* vertical bars, used for the days of the week */
.bars{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;align-items:end;gap:6px;height:130px}
.bars i{background:linear-gradient(to top,var(--acc),var(--acc2));border-radius:6px 6px 0 0;
min-height:3px;display:block}
.bars i.dim{background:var(--line)}
.blabel{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:6px;margin-top:5px;
font-size:.74rem;color:var(--mut);text-align:center}

/* horizontal bars, used for pages and games */
.rows{display:grid;gap:11px;margin-top:10px}
.row{display:grid;grid-template-columns:minmax(0,1fr) 72px;gap:3px 10px;align-items:center}
.row .lbl{grid-column:1/-1;font-size:.86rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .barwrap{background:var(--shade);border-radius:7px;overflow:hidden;height:20px}
.row .bar{background:linear-gradient(95deg,var(--acc),var(--acc2));height:20px;
border-radius:7px;min-width:3px}
.row .bar.alt{background:var(--alt)}
.row .val{text-align:right;font-variant-numeric:tabular-nums;color:var(--mut);font-size:.88rem}

/* ---- tables */
table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:var(--shade)}
.wrap{overflow-x:auto;margin-top:8px}
th.sortable{cursor:pointer;user-select:none}
th.sortable:hover{color:var(--acc)}
th[aria-sort] .ar::after{content:"";display:inline-block;margin-left:4px;border:4px solid transparent}
th[aria-sort=ascending] .ar::after{border-bottom-color:var(--acc);margin-bottom:4px}
th[aria-sort=descending] .ar::after{border-top-color:var(--acc);margin-top:4px}
.filter{width:100%;max-width:260px;padding:9px 12px;border-radius:11px;border:1px solid var(--line);
background:var(--solid);color:var(--ink)}

/* ---- the "games that hold attention" boxes */
.cats{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:10px}
.catbox{border:1px solid var(--line);border-radius:14px;padding:10px 13px;background:var(--shade)}
.catbox>b{display:block;margin-bottom:3px;font-size:.92rem}
.catbox table{font-size:.84rem;table-layout:fixed}
.catbox th,.catbox td{padding:5px 4px;border-bottom:0}
.catbox td:nth-child(2){overflow:hidden;text-overflow:ellipsis}
.catbox th:first-child,.catbox td:first-child{width:22px;color:var(--mut)}
.catbox th:nth-child(3),.catbox td:nth-child(3){width:72px}
.catbox th:nth-child(4),.catbox td:nth-child(4){width:50px}

/* ---- "needs doing": the whole point of the overview. Real problems only. */
.alerts{display:grid;gap:9px;margin-top:4px}
.alert{display:flex;gap:11px;align-items:flex-start;border:1px solid var(--line);
border-left:4px solid var(--acc);border-radius:12px;padding:10px 13px;background:var(--shade)}
.alert.warn{border-left-color:var(--down)}
.alert.good{border-left-color:var(--up)}
.alert b{display:block;font-size:.93rem}
.alert i{font-style:normal;color:var(--mut);font-size:.84rem}

/* ---- the checklist */
.todo{display:flex;gap:11px;align-items:flex-start;padding:11px 2px;
border-top:1px solid var(--line);cursor:pointer}
.todo:first-of-type{border-top:0}
.todo input{margin:3px 0 0;width:19px;height:19px;flex:none;accent-color:var(--acc);cursor:pointer}
.todo i{display:block;font-style:normal;margin-top:2px}
.todo.done b{text-decoration:line-through;color:var(--mut);font-weight:600}
/* Finished work is folded away rather than deleted: the list is for what is
   LEFT, but "did I ever do Search Console?" is a real question months later and
   the answer should still be here. The summary keeps the browser's own triangle
   and gets no custom marker: a CSS content escape starts with a backslash, and a
   backslash followed by a digit, inside the template literal this whole dashboard
   lives in, is read as an octal escape - a syntax error in a module, which takes
   the entire worker down. Writing that warning out WITH an example is what caused
   it the first time. Say it in words here, never in symbols. */
.donelist{margin-top:12px;border-top:1px solid var(--line)}
.donelist>summary{cursor:pointer;padding:11px 2px;color:var(--mut);font-size:.9rem}
.donelist>summary:hover{color:var(--ink)}
.donelist .todo:first-of-type{border-top:0}

/* ---- the login form */
input[type=password]{width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--line);
background:var(--solid);color:var(--ink)}
.btn{background:linear-gradient(95deg,var(--acc),var(--acc2));color:var(--btnink);border:0;
padding:11px 20px;border-radius:13px;font-weight:700;cursor:pointer;box-shadow:var(--sh)}
.ghost{background:transparent;color:var(--mut);border:1px solid var(--line);
padding:9px 15px;border-radius:11px;cursor:pointer}
.ghost:hover{border-color:var(--acc);color:var(--ink)}
.err{border:1px solid var(--down);border-radius:12px;padding:10px 13px;margin:12px 0;
color:var(--down);background:var(--shade)}
</style></head><body><div class="w">`;

/** The timer-ring logo, drawn inline exactly as the site draws it. */
const MARK = '<svg class="mark" viewBox="0 0 32 32" aria-hidden="true">' +
  '<defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">' +
  '<stop offset="0" stop-color="#D8B4FE"/><stop offset="1" stop-color="#A855F7"/>' +
  '</linearGradient></defs><circle cx="16" cy="16" r="15" fill="url(#lg)"/>' +
  '<circle cx="16" cy="16" r="11" fill="none" stroke="#0A0A0F" stroke-opacity=".45" ' +
  'stroke-width="2" stroke-linecap="round" stroke-dasharray="52 69" transform="rotate(-90 16 16)"/>' +
  '<path d="M13.4 11.2 21.6 16l-8.2 4.8z" fill="#0A0A0F"/></svg>';

const SUN = '<svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.6"/>' +
  '<path d="M12 1.6v3.1m0 14.6v3.1M4.6 4.6l2.2 2.2m10.4 10.4 2.2 2.2M1.6 12h3.1m14.6 0h3.1' +
  'M4.6 19.4l2.2-2.2M17.2 6.8l2.2-2.2" stroke="currentColor" stroke-width="2" ' +
  'stroke-linecap="round" fill="none"/></svg>';
const MOON = '<svg class="moon" viewBox="0 0 24 24" aria-hidden="true">' +
  '<path d="M21 14.2A9.2 9.2 0 1 1 9.8 3 7.4 7.4 0 0 0 21 14.2z"/></svg>';

/** The bar across the top of both pages. `right` is whatever buttons belong on it. */
function bar(right = "") {
  return `<div class="bar">${MARK}<b>PlayTime</b> <span class="mut small">admin</span>
<span class="sp"></span>
<button class="iconb" id="theme" type="button" title="Light or dark"
 aria-label="Switch between light and dark">${SUN}${MOON}</button>${right}</div>`;
}

/* The theme button, and the closing tags. The button saves the choice under the same
   name the public site uses, so picking dark on one picks it on the other. */
const TAIL = `<script>
(function(){
  var btn = document.getElementById('theme');
  if (!btn) return;
  var root = document.documentElement;
  /* Whatever the page is showing right now: the owner's own choice if they made
     one, otherwise whatever the device asked for. Written the same guarded way the
     public site writes it, so a browser without matchMedia falls back to light
     rather than throwing. */
  function theme() {
    return root.getAttribute('data-theme') ||
      (window.matchMedia && matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light');
  }
  btn.onclick = function () {
    var next = theme() === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('pt_theme', next); } catch (e) {}
    btn.setAttribute('aria-label', next === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
  };
})();
</script></div></body></html>`;

function loginHtml(error = "") {
  return SHELL + bar() + `<h1 style="margin:22px 0 6px">Sign in</h1>
<p class="mut small">Private page. Not listed on the site and not in Google.</p>
${error ? `<div class="err">${error}</div>` : ""}
<form method="POST" action="/admin/login" class="card" style="max-width:420px">
<label for="code"><b>Admin code</b></label>
<p><input id="code" name="code" type="password" autocomplete="current-password" autofocus required></p>
<button class="btn" type="submit">Sign in</button></form>` + TAIL;
}

/**
 * The dashboard. Four short tabs rather than one very long page: what needs doing,
 * who visited, how the data collection is going, and the launch checklist. Every
 * number still comes from /admin/data; nothing is worked out twice.
 */
function dashboardHtml() {
  return SHELL + bar(
    `<form method="POST" action="/admin/logout" style="margin:0">` +
    `<button class="ghost" type="submit">Sign out</button></form>`) + `
<h1 class="vh">PlayTime admin dashboard</h1>
<div class="tabs" role="tablist" id="tabs">
<button role="tab" data-tab="overview" aria-selected="true">Overview</button>
<button role="tab" data-tab="visitors" aria-selected="false">Visitors</button>
<button role="tab" data-tab="people" aria-selected="false">People</button>
<button role="tab" data-tab="games" aria-selected="false">Games &amp; data</button>
<button role="tab" data-tab="launch" aria-selected="false">Checklist</button>
</div>
<div id="p-overview" role="tabpanel"><p class="mut">Loading&hellip;</p></div>
<div id="p-visitors" role="tabpanel" hidden></div>
<div id="p-people" role="tabpanel" hidden></div>
<div id="p-games" role="tabpanel" hidden></div>
<div id="p-launch" role="tabpanel" hidden></div>
<script>
/* ------------------------------------------------------------ small helpers */
const $ = (s) => document.querySelector(s);
const num = (n) => (n || 0).toLocaleString();
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct = (a, b) => b ? (a - b) / b * 100 : null;
/* 1,240 reads better as 1.2k on a cramped axis label. */
const kfmt = (n) => n >= 1e6 ? (n / 1e6).toFixed(n < 1e7 ? 1 : 0) + 'm'
  : n >= 1000 ? (n / 1000).toFixed(n < 1e4 ? 1 : 0) + 'k' : String(Math.round(n));
const ago = (iso) => { if (!iso) return 'never'; const h = (Date.now() - new Date(iso)) / 3.6e6;
  return h < 1 ? Math.round(h * 60) + ' min ago' : h < 48 ? Math.round(h) + ' hours ago'
    : Math.round(h / 24) + ' days ago'; };
const mins = (s) => { s = Math.round(s || 0); return s < 60 ? s + 's'
  : Math.floor(s / 60) + 'm ' + (s % 60) + 's'; };
const agoSecs = (unix) => { if (!unix) return 'unknown'; const m = (Date.now() / 1000 - unix) / 60;
  return m < 2 ? 'just now' : m < 90 ? Math.round(m) + ' min ago' : Math.round(m / 60) + ' hours ago'; };
/* The collector saves about 144 player counts per game per day. */
const hoursLeft = (needed) => { const h = needed / 6;
  return h < 1 ? 'under an hour' : h < 48 ? Math.round(h) + ' hours' : Math.round(h / 24) + ' days'; };
/* "1 thing left", not "1 thing(s) left". */
const plural = (n, word) => n + ' ' + word + (n === 1 ? '' : 's');
const dayName = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const isoDay = (back) => new Date(Date.now() - back * 864e5).toISOString().slice(0, 10);

/* ------------------------------------------------------------------- graphs */

/* A run of daily numbers as a line with a see-through wash under it, the same shape
   the public site uses for a game's day. A gap in the days breaks the line instead
   of being drawn as zero, which would invent a day with no visitors.
   The id only has to be unique on the page, because the wash gradient needs a name. */
function lineChart(id, pts, hue) {
  const W = 720, H = 230, L = 40, R = 12, top = 16, bot = H - 28, span = bot - top;
  const vals = pts.map(p => p.value);
  const max = Math.max(1, ...vals);
  const n = pts.length;
  const x = (i) => n < 2 ? (L + W - R) / 2 : L + i * (W - L - R) / (n - 1);
  const y = (v) => bot - (v / max) * span;

  // Three faint lines across, so a height can be read off without dragging.
  let grid = '';
  [0, 0.5, 1].forEach(f => {
    const gy = bot - f * span;
    grid += '<line x1="' + L + '" y1="' + gy.toFixed(1) + '" x2="' + (W - R) + '" y2="' + gy.toFixed(1) +
      '" stroke="var(--line)" stroke-width="1"/>' +
      '<text x="' + (L - 6) + '" y="' + (gy + 4).toFixed(1) + '" text-anchor="end" font-size="11" ' +
      'fill="var(--mut)">' + kfmt(max * f) + '</text>';
  });

  // Unbroken stretches of days, so the line stops where we have nothing.
  const runs = []; let cur = [];
  for (let i = 0; i < n; i++) {
    if (pts[i].value == null) { if (cur.length) runs.push(cur); cur = []; } else cur.push(i);
  }
  if (cur.length) runs.push(cur);

  let line = '', wash = '', dots = '';
  runs.forEach(r => {
    const d = r.map((i, k) => (k ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(pts[i].value).toFixed(1)).join(' ');
    line += d + ' ';
    if (r.length > 1) {
      wash += d + ' L' + x(r[r.length - 1]).toFixed(1) + ' ' + bot +
        ' L' + x(r[0]).toFixed(1) + ' ' + bot + ' Z ';
    }
    // On a long stretch the dots crowd together, so only draw them when there is room.
    if (n <= 16) r.forEach(i => {
      dots += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(pts[i].value).toFixed(1) +
        '" r="3.5" fill="var(--' + hue + ')"/>';
    });
  });

  // Date labels, thinned out so they never overlap.
  const every = Math.ceil(n / 7);
  let ticks = '';
  pts.forEach((p, i) => {
    if (i % every && i !== n - 1) return;
    ticks += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" ' +
      'font-size="11" fill="var(--mut)">' + esc(p.label) + '</text>';
  });

  return '<svg class="graph" id="' + id + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" ' +
    'tabindex="0" aria-label="' + esc(pts.length + ' days of page views, highest ' + max) + '">' +
    '<defs><linearGradient id="' + id + '-wash" x1="0" y1="0" x2="0" y2="1">' +
    '<stop offset="0" stop-color="var(--' + hue + ')" stop-opacity=".40"/>' +
    '<stop offset="1" stop-color="var(--' + hue + ')" stop-opacity=".02"/></linearGradient></defs>' +
    grid + '<path d="' + wash + '" fill="url(#' + id + '-wash)"/>' +
    '<path d="' + line + '" fill="none" stroke="var(--' + hue + ')" stroke-width="3" ' +
    'stroke-linejoin="round" stroke-linecap="round"/>' + dots + ticks +
    '<g class="cursor" opacity="0"><line y1="' + top + '" y2="' + bot + '" stroke="var(--ink)" ' +
    'stroke-width="1.5" stroke-dasharray="4 4"/><circle r="6" fill="var(--' + hue + ')" ' +
    'stroke="var(--solid)" stroke-width="2.5"/></g></svg>';
}

/* Lets the owner drag, click, hover or arrow along a line chart and read any day off
   it. Same idea as the public site's graph cursor, and it does nothing at all if the
   browser cannot measure the svg. */
function chartCursor(svg, out, pts) {
  if (!svg) return;
  const W = 720, H = 230, L = 40, R = 12, top = 16, bot = H - 28, span = bot - top;
  const max = Math.max(1, ...pts.map(p => p.value));
  const n = pts.length;
  const g = svg.querySelector('.cursor');
  const ln = g.querySelector('line'), dot = g.querySelector('circle');
  let at = -1;

  function show(i) {
    if (i < 0 || i >= n || pts[i].value == null) {
      g.setAttribute('opacity', '0'); at = -1;
      if (out) out.innerHTML = '&nbsp;';
      return;
    }
    at = i;
    const px = n < 2 ? (L + W - R) / 2 : L + i * (W - L - R) / (n - 1);
    const py = bot - (pts[i].value / max) * span;
    ln.setAttribute('x1', px); ln.setAttribute('x2', px);
    dot.setAttribute('cx', px); dot.setAttribute('cy', py);
    g.setAttribute('opacity', '1');
    if (out) out.innerHTML = '<b>' + esc(pts[i].full || pts[i].label) + '</b> &middot; ' +
      '<b>' + num(pts[i].value) + '</b> ' + (pts[i].unit || 'page views');
  }
  function fromX(clientX) {
    const r = svg.getBoundingClientRect();
    if (!r.width || n < 2) return n < 2 ? 0 : -1;
    const vx = (clientX - r.left) / r.width * W;
    return Math.max(0, Math.min(n - 1, Math.round((vx - L) / ((W - L - R) / (n - 1)))));
  }
  function move(e) {
    const t = e.touches && e.touches[0];
    const cx = t ? t.clientX : e.clientX;
    if (cx == null) return;
    if (t) e.preventDefault();      // stop the page scrolling while dragging the graph
    show(fromX(cx));
  }
  let down = false;
  svg.addEventListener('mousedown', e => { down = true; move(e); });
  svg.addEventListener('mousemove', e => { if (down || e.buttons === 0) move(e); });
  window.addEventListener('mouseup', () => { down = false; });
  svg.addEventListener('mouseleave', () => { if (!down) show(-1); });
  svg.addEventListener('touchstart', move, { passive: false });
  svg.addEventListener('touchmove', move, { passive: false });
  svg.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault();
      show(at < 0 ? n - 1 : at + (e.key === 'ArrowRight' ? 1 : -1));
    } else if (e.key === 'Escape') show(-1);
  });
}

/* A tiny line with no axes, to sit inside a tile and show the shape of the last
   fortnight without taking any room. */
function spark(vals, hue) {
  const W = 160, H = 26, max = Math.max(1, ...vals), n = vals.length;
  if (n < 2) return '';
  const x = (i) => i * W / (n - 1);
  const y = (v) => H - 2 - (v / max) * (H - 5);
  const d = vals.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ');
  return '<svg class="spark" viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true" ' +
    'preserveAspectRatio="none"><path d="' + d + ' L' + W + ' ' + H + ' L0 ' + H + ' Z" ' +
    'fill="var(--' + hue + ')" opacity=".16"/><path d="' + d + '" fill="none" ' +
    'stroke="var(--' + hue + ')" stroke-width="2" stroke-linejoin="round" ' +
    'stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>';
}

/* A ring showing how far through something we are. Used for the launch checklist and
   for how many games have collected enough data. */
function ring(done, total, label) {
  const share = total ? done / total : 0;
  const r = 46, c = 2 * Math.PI * r;
  return '<svg class="ring" viewBox="0 0 120 120" role="img" aria-label="' +
    esc(done + ' of ' + total + ' ' + label) + '">' +
    '<circle cx="60" cy="60" r="' + r + '" fill="none" stroke="var(--line)" stroke-width="11"/>' +
    '<circle cx="60" cy="60" r="' + r + '" fill="none" stroke="var(--acc)" stroke-width="11" ' +
    'stroke-linecap="round" transform="rotate(-90 60 60)" stroke-dasharray="' +
    (c * share).toFixed(1) + ' ' + c.toFixed(1) + '"/>' +
    '<text x="60" y="57" text-anchor="middle" font-size="25" font-weight="700" ' +
    'fill="var(--ink)">' + done + '/' + total + '</text>' +
    '<text x="60" y="76" text-anchor="middle" font-size="11" fill="var(--mut)">' +
    esc(label) + '</text></svg>';
}

/* Upright bars. Used for the days of the week, where seven labels fit along the
   bottom and the comparison between them is the whole point. */
function colBars(items, dimIf) {
  const max = Math.max(1, ...items.map(i => i.value));
  const bars = items.map(i => '<i class="' + (dimIf && dimIf(i) ? 'dim' : '') + '" style="height:' +
    Math.max(3, i.value / max * 100) + '%" title="' + esc(i.label + ': ' + num(i.value)) +
    '"></i>').join('');
  const labels = items.map(i => '<span>' + esc(i.short) + '</span>').join('');
  return '<div class="bars">' + bars + '</div><div class="blabel">' + labels + '</div>';
}

/* Bars lying on their side, for lists where the label is long: page addresses and
   game names. Labels must already be escaped by the caller. */
function barRows(items, cls) {
  if (!items.length) return '';
  const max = Math.max(1, ...items.map(i => i.value));
  return '<div class="rows">' + items.map(i =>
    '<div class="row"><div class="lbl">' + i.label +
    (i.note ? ' <span class="mut">&middot; ' + i.note + '</span>' : '') + '</div>' +
    '<div class="barwrap"><div class="bar ' + (cls || '') + '" style="width:' +
    (i.value / max * 100).toFixed(1) + '%"></div></div>' +
    '<div class="val">' + (i.valText || num(i.value)) + '</div></div>').join('') + '</div>';
}

const tile = (label, value, extra) => '<div class="tile"><span class="mut small">' + label +
  '</span><b>' + value + '</b>' + (extra || '') + '</div>';

/* ------------------------------------------------------------------- render */

fetch('/admin/data').then(r => {
  if (!r.ok) throw new Error('the server said no (' + r.status + ')');
  return r.json();
}).then(render).catch(e => {
  $('#p-overview').innerHTML = '<div class="card"><b>Could not load the numbers.</b>' +
    '<p class="mut small">' + esc(e.message) + '. Try reloading the page.</p></div>';
});

function render(d) {
  const v = d.views, s = d.stats || {}, t = s.totals || {}, site = s.site || {};
  // Id 0 is Roblox's placeholder for a deleted or private game. summary.json leaves it
  // out now, but this keeps an old copy of that file from listing it as a game that
  // is nearly ready for a page, which the site build would never give it.
  const live = d.live ? Object.assign({}, d.live, {
    games: (d.live.games || []).filter(g => g.id && String(g.id) !== '0')
  }) : null;
  const todos = d.todos || [];

  // One place that knows the page views for any day, so every panel agrees.
  const byDay = {};
  (v.daily || []).forEach(r => { byDay[r.day] = r.n; });
  const dayVal = (back) => byDay[isoDay(back)] || 0;
  const sumBack = (from, to) => { let n = 0; for (let i = from; i <= to; i++) n += dayVal(i); return n; };

  overview(d, v, s, t, site, live, todos, dayVal, sumBack);
  visitors(d, v, s, byDay);
  people(d, s);
  gamesPanel(d, s, t, site, live);
  launch(d, t, site, todos);
  wireTabs();
  wireTodos();
}

/* ---- a chart plus its range buttons, built once and switchable in place */
function dailyChart(holder, make) {
  const el = document.getElementById(holder);
  if (!el) return;
  const draw = (days) => {
    const pts = make(days);
    el.innerHTML = lineChart(holder + '-g', pts, 'acc') +
      '<p class="readout" id="' + holder + '-out">&nbsp;</p>';
    chartCursor(document.getElementById(holder + '-g'),
      document.getElementById(holder + '-out'), pts);
  };
  const btns = document.querySelectorAll('[data-range="' + holder + '"] button');
  Array.prototype.forEach.call(btns, b => {
    b.onclick = () => {
      Array.prototype.forEach.call(btns, o => o.setAttribute('aria-pressed', o === b));
      draw(Number(b.dataset.days));
    };
  });
  const on = document.querySelector('[data-range="' + holder + '"] button[aria-pressed=true]');
  draw(on ? Number(on.dataset.days) : 14);
}

/* ============================================================== 1. overview */
function overview(d, v, s, t, site, live, todos, dayVal, sumBack) {
  const builtHours = s.built_at ? (Date.now() - new Date(s.built_at)) / 3.6e6 : 999;

  // Only real problems, each with the one thing to do about it. When the list is
  // empty that is worth saying too, so the panel never looks broken.
  const todo = [];
  // Builds run every six hours, so eight is a late one rather than a missed one.
  // Keep this in step with the cron in .github/workflows/build.yml: set it too low
  // and the panel cries wolf every day, too high and a dead build sits unnoticed.
  if (builtHours > 8) todo.push(['warn', 'The site has not rebuilt for ' + Math.round(builtHours) +
    ' hours', 'It should rebuild every six hours. Check the Actions tab on GitHub for a failed build.']);
  if (live && live.updated && (Date.now() / 1000 - live.updated) > 7200)
    todo.push(['warn', 'The collector last saved player counts ' + agoSecs(live.updated),
      'It normally runs every 30 minutes. Check the collect workflow on GitHub.']);
  if ((s.missing_ids || []).length) todo.push(['warn',
    plural((s.missing_ids || []).length, 'game ID') + ' in games.txt returned nothing',
    'Usually a wrong ID, or a game that has been taken down. See Games and data.']);
  // Notifications fail silently by their nature: a browser that cannot decrypt a
  // message simply ignores it, and a dead push service says nothing. This is the
  // only place that would ever tell you.
  const pdev = (d.people && d.people.devices) || {};
  if (pdev.failing) todo.push(['warn',
    'Notifications are failing on ' + plural(pdev.failing, 'device'),
    'See the People tab for what the push service last said. Five failures in a row ' +
    'and a device is dropped for good.']);
  if (site.noindex) todo.push(['', 'Google cannot see the site yet',
    'NOINDEX is still True in build_site.py. Turn it off once the pages have real data.']);
  if ((site.min_samples || 0) < 200) todo.push(['', 'MIN_SAMPLES is ' + num(site.min_samples) +
    ', not 200', 'It is lowered while designing. Put it back before launch.']);
  if (!site.domain) todo.push(['', 'No domain set',
    'Buy one, then set DOMAIN in build_site.py. The sitemap needs it to work.']);
  if (!v.totals.all_time) todo.push(['', 'No page views counted yet',
    'Expected while the site is hidden from Google and nobody has the address.']);
  const left = todos.filter(x => !x.done).length;

  const alerts = todo.length
    ? todo.map(a => '<div class="alert ' + a[0] + '"><span><b>' + a[1] + '</b><i>' + a[2] +
        '</i></span></div>').join('')
    : '<div class="alert good"><span><b>Nothing needs your attention.</b>' +
      '<i>The site is building, the collector is running, every game ID answers, ' +
      'and nothing is failing to send.</i>' +
      '</span></div>';

  const d1 = dayVal(0), d2 = dayVal(1);
  const w1 = sumBack(0, 6), w2 = sumBack(7, 13);
  const fortnight = [];
  for (let i = 13; i >= 0; i--) fortnight.push(dayVal(i));

  document.getElementById('p-overview').innerHTML = [
    '<div class="card"><h2>Needs doing</h2>',
    '<p class="mut small">Worked out from the last build and the live collector, ',
    'so this is what is actually true right now.</p>',
    '<div class="alerts">', alerts, '</div></div>',

    '<div class="tiles">',
    tile('Page views today', num(d1), delta(d1, d2, 'vs yesterday')),
    tile('Last 7 days', num(w1), delta(w1, w2, 'vs the week before') + spark(fortnight.slice(7), 'acc')),
    tile('Last 30 days', num(v.totals.month), spark(fortnight, 'acc')),
    tile('All time', num(v.totals.all_time)),
    '</div>',

    '<div class="card"><div class="head"><div><h2>Page views per day</h2>',
    '<p class="mut small" style="margin:0">Counted without cookies, so one person ',
    'opening five pages counts as five.</p></div>',
    range('ov-chart'), '</div><div id="ov-chart"></div></div>',

    '<div class="pair">',
    '<div class="card"><h2>Checklist</h2>',
    /* Wrapped in an id so ticking a box on the other tab can repaint it. Both
       rings used to be drawn once and then go quietly stale until a reload. */
    '<div id="ring-ov">',
    ring(todos.length - left, todos.length, 'done'),
    '<p class="mut small" style="text-align:center;margin:8px 0 0">',
    left ? plural(left, 'thing') + ' left. See the Checklist tab.' : 'All ticked off.',
    '</p></div></div>',
    '<div class="card"><h2>How long people stay</h2>',
    '<p style="font-size:2rem;margin:.1em 0;letter-spacing:-.02em">',
    (v.time && v.time.week_reads) ? mins(v.time.week_seconds / v.time.week_reads) : '&ndash;',
    '</p><p class="mut small" style="margin:0">Average time a page stays open, last 7 days. ',
    'All time: ', (v.time && v.time.reads) ? mins(v.time.seconds / v.time.reads) : 'nothing yet',
    '.</p></div></div>',

    '<p class="mut small">Site last built ', ago(s.built_at),
    s.built_at ? ' (' + s.built_at.replace('T', ' ').slice(0, 16) + ' UTC). ' : '. ',
    live ? 'Player counts updated ' + agoSecs(live.updated) + '.' : 'Live player counts unavailable.',
    ' <a href="/" target="_blank" rel="noopener">Open the site</a></p>'
  ].join('');

  dailyChart('ov-chart', (days) => {
    const pts = [];
    for (let i = days - 1; i >= 0; i--) {
      const day = isoDay(i), dt = new Date(day);
      pts.push({
        label: day.slice(8) + '/' + day.slice(5, 7),
        full: dayName[dt.getUTCDay()] + ' ' + day,
        value: dayVal(i)
      });
    }
    return pts;
  });
}

/* A small up or down chip next to a number. Returns nothing when there is no
   earlier figure to compare against, rather than claiming a change of 0%. */
function delta(now, before, label) {
  if (!before) return '<span class="mut small">' + esc(label) + ': nothing yet</span>';
  const change = Math.round(pct(now, before));
  const cls = change >= 0 ? 'up' : 'down';
  return '<span class="delta ' + cls + '">' + (change >= 0 ? '&uarr; ' : '&darr; ') +
    Math.abs(change) + '%</span> <span class="mut small">' + esc(label) + '</span>';
}

const range = (holder) => '<div class="range" data-range="' + holder + '">' +
  '<button type="button" data-days="7">7 days</button>' +
  '<button type="button" data-days="14" aria-pressed="true">14 days</button>' +
  '<button type="button" data-days="30">30 days</button></div>';

/* ============================================================== 2. visitors */
function visitors(d, v, s, byDay) {
  // Which days of the week people actually come. Averaged, so a Monday is not
  // ahead simply because the last 30 days held five of them and four Sundays.
  const sums = [0, 0, 0, 0, 0, 0, 0], counts = [0, 0, 0, 0, 0, 0, 0];
  for (let i = 0; i < 28; i++) {
    const day = isoDay(i), w = new Date(day).getUTCDay();
    sums[w] += byDay[day] || 0; counts[w]++;
  }
  const week = [1, 2, 3, 4, 5, 6, 0].map(w => ({
    label: dayName[w], short: dayName[w].slice(0, 3),
    value: counts[w] ? Math.round(sums[w] / counts[w]) : 0
  }));
  const anyWeek = week.some(x => x.value);

  const pages = (v.pages || []).map(p => {
    const avg = p.reads ? mins(p.seconds / p.reads) : 'no reading time yet';
    return { label: esc(p.path), note: avg, value: p.n, valText: num(p.n) };
  });

  const kindRows = (d.kinds || []).map(k =>
    ({ label: esc(k.kind), value: k.n, valText: num(k.n) }));

  // Which games are being found more than they were. Slugs are turned back into
  // names, because a row of addresses is not something anybody reads for pleasure.
  const slugName = {};
  (s.games || []).forEach(g => { if (g.slug) slugName[g.slug] = g.name; });
  const climbRows = (d.climb || [])
    .map(r => {
      const slug = r.path.replace('/game/', '');
      return { name: slugName[slug] || slug, now: r.recent || 0, was: r.earlier || 0 };
    })
    .filter(r => r.now >= 3 && r.now > r.was)
    .sort((a, b) => (b.now - b.was) - (a.now - a.was))
    .slice(0, 10)
    .map(r => ({
      label: esc(r.name),
      note: r.was ? r.was + ' then, ' + r.now + ' now' : 'new this week',
      value: r.now, valText: r.was ? '+' + Math.round((r.now - r.was) / r.was * 100) + '%'
        : '+' + r.now
    }));

  // Which games hold attention, best three in each category.
  const timeByPath = {}, viewsByPath = {};
  (d.gameTime || []).forEach(r => { timeByPath[r.path] = r; });
  (d.gameViews || []).forEach(r => { viewsByPath[r.path] = r.n; });
  const byCategory = {};
  (s.games || []).forEach(g => {
    if (!g.slug) return;                        // older builds did not record it
    // Visitors land on /game/<slug> - Cloudflare redirects the .html form - so that
    // is the path recorded against a page view. Looking one up by '.html' matched
    // nothing, and this whole section sat empty.
    const row = timeByPath['/game/' + g.slug];
    if (!row || !row.reads) return;             // nobody has read it yet
    const cat = g.genre || 'Uncategorised';
    (byCategory[cat] = byCategory[cat] || []).push({
      name: g.name, avg: row.seconds / row.reads, reads: row.reads,
      views: viewsByPath['/game/' + g.slug] || 0
    });
  });
  const catBlocks = Object.keys(byCategory).sort().map(cat => {
    const rows = byCategory[cat].sort((a, b) => b.avg - a.avg).slice(0, 3).map((g, i) =>
      '<tr><td>' + (i + 1) + '</td><td title="' + esc(g.name) + '">' + esc(g.name) + '</td>' +
      '<td class="num">' + mins(g.avg) + '</td>' +
      '<td class="num mut">' + num(g.views) + '</td></tr>').join('');
    return '<div class="catbox"><b>' + esc(cat) + '</b><table>' +
      '<tr><th></th><th>Game</th><th class="num">Avg time</th><th class="num">Views</th></tr>' +
      rows + '</table></div>';
  }).join('');

  document.getElementById('p-visitors').innerHTML = [
    '<div class="tiles">',
    tile('Average time on a page', (v.time && v.time.week_reads)
      ? mins(v.time.week_seconds / v.time.week_reads) : '&ndash;',
      '<span class="mut small">last 7 days</span>'),
    tile('Average time, all time', (v.time && v.time.reads)
      ? mins(v.time.seconds / v.time.reads) : '&ndash;'),
    tile('Total time spent reading', v.time
      ? Math.round((v.time.seconds || 0) / 60).toLocaleString() + ' min' : '&ndash;'),
    tile('Visits timed', v.time ? num(v.time.reads) : '0',
      '<span class="mut small">visits lasting a second or more</span>'),
    '</div>',

    '<div class="card"><h2>Which days people visit</h2>',
    '<p class="mut small">Average page views per day of the week, last 4 weeks (UTC).</p>',
    anyWeek ? colBars(week, (x) => !x.value)
      : '<p class="mut small">Nothing to show yet. This fills in once visitors arrive.</p>',
    '</div>',

    '<div class="card"><h2>Most visited pages</h2>',
    '<p class="mut small">Last 30 days, with how long each page stays open on average.</p>',
    pages.length ? barRows(pages) : '<p class="mut small">No page views recorded yet.</p>',
    '</div>',

    '<div class="card"><h2>What kind of page people open</h2>',
    '<p class="mut small">Last 30 days. Every game gained four pages of its own in ',
    'November - events, questions, what costs money, updates - and this says whether ',
    'anybody reads them.</p>',
    kindRows.length ? barRows(kindRows, 'alt')
      : '<p class="mut small">No page views recorded yet.</p>',
    '</div>',

    '<div class="card"><h2>Games climbing this week</h2>',
    '<p class="mut small">The last 7 days against the 7 before them. A game needs ',
    'three views this week to appear, so one curious afternoon does not top the list.</p>',
    climbRows.length ? barRows(climbRows)
      : '<p class="mut small">Nothing has moved enough to show yet. This needs two ' +
        'weeks of views on the same game.</p>',
    '</div>',

    '<div class="card"><h2>Games that hold attention</h2>',
    '<p class="mut small">Top 3 in each category, last 30 days, ranked by how long the page ',
    'stays open. A game read by a handful of people can top its category on luck, ',
    'so check the views column.</p>',
    catBlocks ? '<div class="cats">' + catBlocks + '</div>'
      : '<p class="mut small">No reading time recorded on game pages yet. Each game needs ' +
        'at least one visit lasting a second or more.</p>',
    '</div>'
  ].join('');
}

/* ================================================================ 3. people */
/* Sign-ins, saved games and notifications - three features that had been live for
   days with nothing anywhere to say whether they worked.

   Counts and game names only: no display names, no Roblox IDs, no push addresses
   and no keys. Knowing whether the thing is working does not need to know who, and
   a dashboard is a screen that gets photographed and shared. The Privacy Policy
   promises that what we hold about a person is their Roblox ID, their name and
   their saved games, and nothing here widens that by a single column. */
function people(d, s) {
  const p = d.people || {};
  const acc = p.accounts || {}, fav = p.favs || {}, dev = p.devices || {};
  const w = p.watches || {}, sent = p.sent || {};

  // Slugs back into names: a column of addresses is not something anybody reads.
  const slugName = {};
  (s.games || []).forEach(g => { if (g.slug) slugName[g.slug] = g.name; });
  const gname = (slug) => esc(slugName[slug] || slug);
  const agoMs = (ms) => ms ? ago(new Date(Number(ms)).toISOString()) : 'never';

  /* What the push service said last time. This is the whole reason the panel
     exists: fails counts failures only, so it sits at 0 both when a send worked
     and when one was never tried, and the real answer was only ever readable by
     typing a wrangler command at a terminal. 201 is a normal success. */
  const statusWord = (c) => c == null ? 'No send tried yet'
    : (c >= 200 && c < 300) ? 'Delivered (' + c + ')'
    : c === 0 ? 'Could not build the message'
    : c === -1 ? 'Could not reach the push service'
    : (c === 404 || c === 410) ? 'This device is gone for good'
    : 'The push service refused it (' + c + ')';
  const statusCls = (c) => c == null ? '' : (c >= 200 && c < 300) ? 'good' : 'warn';

  const devRows = (p.devList || []).map(r =>
    '<div class="alert ' + statusCls(r.last_status) + '"><span><b>' +
    statusWord(r.last_status) + '</b><i>' +
    (r.last_try ? 'Last tried ' + agoMs(r.last_try) : 'Nothing sent to it yet') +
    ' &middot; turned on ' + agoMs(r.created) +
    ' &middot; clock UTC' + ((r.tz || 0) >= 0 ? '+' : '') + (r.tz || 0) +
    (r.fails ? ' &middot; ' + plural(r.fails, 'failure') + ' in a row, dropped at 5' : '') +
    '</i></span></div>').join('');

  const kindRows = [
    { label: 'Quiet', value: w.quiet || 0 },
    { label: 'Busy', value: w.busy || 0 },
    { label: 'Events', value: w.events || 0 },
    { label: 'Updates', value: w.updates || 0 }
  ].map(k => ({ label: k.label, value: k.value, valText: num(k.value) }));
  const anyKind = kindRows.some(k => k.value);

  const savedRows = (p.favTop || []).map(r =>
    ({ label: gname(r.slug), value: r.n, valText: num(r.n) }));
  const watchRows = (p.watchTop || []).map(r =>
    ({ label: gname(r.slug), value: r.n, valText: num(r.n) }));

  document.getElementById('p-people').innerHTML = [
    '<div class="tiles">',
    tile('Signed in with Roblox', num(acc.n),
      '<span class="mut small">' + (acc.joined ? plural(acc.joined, 'new one') + ' this week'
        : 'none new this week') + '</span>'),
    tile('Back in the last 7 days', num(acc.active),
      '<span class="mut small">' + (acc.last ? 'last sign-in ' + agoMs(acc.last)
        : 'nobody yet') + '</span>'),
    tile('Games saved', num(fav.n),
      '<span class="mut small">by ' + plural(fav.people || 0, 'person') + '</span>'),
    tile('Devices with notifications on', num(dev.n),
      '<span class="mut small">' + plural(dev.people || 0, 'person') + '</span>'),
    '</div>',

    '<div class="card"><h2>Are notifications arriving?</h2>',
    '<p class="mut small">One line per device, newest first. A browser that cannot ',
    'read a message simply ignores it and nothing anywhere reports an error, so what ',
    'the push service answered is the only honest signal there is.</p>',
    devRows || '<p class="mut small">Nobody has turned notifications on yet. The ' +
      'switches are on every game page and on the notifications page.</p>',
    (sent.n ? '<p class="mut small">' + plural(sent.n, 'notification') + ' sent in the ' +
      'last two days' + (sent.last ? ', the most recent ' + agoMs(sent.last) : '') +
      '. Older records are cleared every run, so this is never a running total.</p>' : ''),
    '</div>',

    '<div class="pair">',
    '<div class="card"><h2>Which alerts people choose</h2>',
    '<p class="mut small">Four independent switches, counted across every game ',
    'anybody follows.</p>',
    anyKind ? barRows(kindRows, 'alt')
      : '<p class="mut small">No alerts switched on yet.</p>',
    '<p class="mut small">', num(w.n), ' game ', (w.n === 1 ? 'alert' : 'alerts'),
    ' in all, set by ', plural(w.people || 0, 'person'), '.</p></div>',
    '<div class="card"><h2>Most followed games</h2>',
    '<p class="mut small">Games people asked to be told about.</p>',
    watchRows.length ? barRows(watchRows)
      : '<p class="mut small">Nothing followed yet.</p>',
    '</div></div>',

    '<div class="card"><h2>Most saved games</h2>',
    '<p class="mut small">Saving a game is somebody saying they care about it, which ',
    'is why a saved game gets a row on the notifications page with every switch off, ',
    'ready to turn on.</p>',
    savedRows.length ? barRows(savedRows)
      : '<p class="mut small">Nothing saved by a signed-in person yet. Saves made ' +
        'without signing in stay in that browser and never reach us.</p>',
    '</div>',

    '<p class="mut small">Counts only. No names, no Roblox IDs, no push addresses ' +
    'and no keys are read for this page.</p>'
  ].join('');
}

/* ========================================================= 4. games and data */
function gamesPanel(d, s, t, site, live) {
  // Counts come from the collector, so they are current. Anything that needs a full
  // rebuild to work out - typical players, trend, verdict - is from the last build.
  const byId = {}, byName = {};
  (live && live.games || []).forEach(g => { byId[String(g.id)] = g; if (g.name) byName[g.name] = g; });
  const fresh = (g) => byId[String(g.id)] || byName[g.name] || null;
  const spanDays = (g) => (g.first && g.last) ? Math.round((g.last - g.first) / 864) / 100 : null;

  // One row per game, with the freshest figure available for each column.
  window.GAMES = (s.games || []).map(g => {
    const f = fresh(g);
    return {
      name: g.name, genre: g.genre || '',
      samples: f ? f.samples : g.samples,
      days: (f && spanDays(f) !== null) ? spanDays(f) : g.days,
      avg7: g.avg7, trend: g.trend, verdict: g.verdict,
      events: g.events, upcoming: g.upcoming
    };
  });

  const min = site.min_samples || 0;
  const waitingList = live
    ? live.games.filter(g => g.samples < min).sort((a, b) => b.samples - a.samples)
        .map(g => ({ name: g.name || g.id, samples: g.samples }))
    : (s.waiting || []);
  const waitBars = waitingList.slice(0, 20).map(w => ({
    label: esc(w.name), note: w.samples >= min ? 'ready' : hoursLeft(min - w.samples) + ' to go',
    value: w.samples, valText: num(w.samples) + '/' + num(min)
  }));

  const ready = (s.games || []).length;
  const tracked = live ? live.games.length : (t.games_tracked || 0);

  const top = window.GAMES.slice().sort((a, b) => b.avg7 - a.avg7).slice(0, 12).map(g => ({
    label: esc(g.name), note: esc(g.genre), value: g.avg7, valText: num(g.avg7)
  }));

  const missing = (s.missing_ids || []).map(id => '<li>' + esc(id) + '</li>').join('');

  document.getElementById('p-games').innerHTML = [
    '<p class="mut small">', live
      ? 'Player counts updated ' + agoSecs(live.updated) + ', straight from the collector. ' +
        'Typical players and trends come from the last site build.'
      : 'Live counts unavailable, so every figure here is from the last site build.',
    '</p>',
    '<div class="tiles">',
    tile('Games tracked', num(tracked)),
    tile('Player counts saved', num(live ? live.total_samples : t.samples)),
    tile('Pages built', num(t.pages_built)),
    tile('Ready for trends', num(t.trend_ready), '<span class="mut small">needs 14 days</span>'),
    tile('Games with events', num(t.with_events)),
    tile('Events coming up', num(t.upcoming_events)),
    '</div>',

    '<div class="pair">',
    '<div class="card"><h2>Games with enough data</h2>',
    ring(ready, tracked, 'have a page'),
    '<p class="mut small" style="text-align:center;margin:8px 0 0">A game needs ',
    num(min), ' player counts before it gets a page.</p></div>',
    '<div class="card"><h2>Waiting for enough data</h2>',
    waitBars.length
      ? '<p class="mut small">Still short of MIN_SAMPLES, so they have no page yet.</p>' +
        barRows(waitBars, 'alt') +
        (waitingList.length > 20 ? '<p class="mut small">and ' +
          plural(waitingList.length - 20, 'other') + '.</p>' : '')
      : '<p class="mut small">Every game has enough data. Nothing is waiting.</p>',
    '</div></div>',

    '<div class="card"><h2>Biggest games</h2>',
    '<p class="mut small">Typical players at any moment, from the last build.</p>',
    top.length ? barRows(top) : '<p class="mut small">No games with a page yet.</p>',
    '</div>',

    '<div class="card"><div class="head"><div><h2>Every game</h2>',
    '<p class="mut small" style="margin:0">Click a column heading to sort.</p></div>',
    '<span class="sp" style="flex:1"></span>',
    '<input class="filter" id="gfilter" type="search" placeholder="Find a game or category">',
    '</div><div class="wrap"><table id="gtable"><thead><tr>',
    '<th class="sortable" data-k="name">Game<span class="ar"></span></th>',
    '<th class="sortable" data-k="genre">Category<span class="ar"></span></th>',
    '<th class="sortable num" data-k="samples">Counts<span class="ar"></span></th>',
    '<th class="sortable num" data-k="days">Days<span class="ar"></span></th>',
    '<th class="sortable num" data-k="avg7">Typical players<span class="ar"></span></th>',
    '<th class="sortable num" data-k="trend">vs last week<span class="ar"></span></th>',
    '</tr></thead><tbody></tbody></table></div></div>',

    missing ? '<div class="card"><h2>IDs Roblox did not return</h2>' +
      '<p class="mut small">In games.txt, but Roblox sent nothing back. Usually a wrong ID ' +
      'or a game that has been taken down.</p><ul>' + missing + '</ul></div>' : ''
  ].join('');

  wireTable();
}

/* The game table sorts and filters in the browser, because all 100 rows are already
   here. Sorting is stable on the name, so two games with the same figure keep a
   sensible order instead of jumping about between clicks. */
function wireTable() {
  const table = document.getElementById('gtable');
  if (!table) return;
  let key = 'avg7', dir = -1;

  function paint() {
    const q = (document.getElementById('gfilter').value || '').toLowerCase().trim();
    const rows = window.GAMES
      .filter(g => !q || (g.name + ' ' + g.genre).toLowerCase().indexOf(q) >= 0)
      .sort((a, b) => {
        const x = a[key], y = b[key];
        if (x === y) return a.name.localeCompare(b.name);
        if (x == null) return 1;                 // no trend yet sorts to the bottom
        if (y == null) return -1;
        return (typeof x === 'string' ? x.localeCompare(y) : x - y) * dir;
      });
    table.tBodies[0].innerHTML = rows.map(g =>
      '<tr><td>' + esc(g.name) + '</td><td class="mut">' + esc(g.genre) + '</td>' +
      '<td class="num">' + num(g.samples) + '</td><td class="num">' + g.days + '</td>' +
      '<td class="num">' + num(g.avg7) + '</td><td class="num">' +
      (g.trend == null ? '<span class="mut">&ndash;</span>'
        : '<span class="' + (g.trend >= 0 ? 'ok">&uarr; +' : 'bad">&darr; ') + g.trend + '%</span>') +
      '</td></tr>').join('') ||
      '<tr><td colspan="6" class="mut">Nothing matches that.</td></tr>';
    Array.prototype.forEach.call(table.querySelectorAll('th.sortable'), th => {
      if (th.dataset.k === key) th.setAttribute('aria-sort', dir > 0 ? 'ascending' : 'descending');
      else th.removeAttribute('aria-sort');
    });
  }

  Array.prototype.forEach.call(table.querySelectorAll('th.sortable'), th => {
    th.onclick = () => {
      if (key === th.dataset.k) dir = -dir;
      else { key = th.dataset.k; dir = key === 'name' || key === 'genre' ? 1 : -1; }
      paint();
    };
  });
  document.getElementById('gfilter').oninput = paint;
  paint();
}

/* ================================================================ 4. launch */
function launch(d, t, site, todos) {
  const check = (done, label, note) =>
    '<div class="alert ' + (done ? 'good' : '') + '"><span><b>' +
    (done ? '&#10003; ' : '') + label + '</b>' + (note ? '<i>' + note + '</i>' : '') +
    '</span></div>';
  const left = todos.filter(x => !x.done).length;
  /* Two lists off one array. The order inside each is still the sort column, so
     the steps stay in the order they are meant to be done in. */
  const open = todos.filter(x => !x.done);
  const finished = todos.filter(x => x.done);
  const allDone = 'Everything is ticked off.';
  const row = x => '<label class="todo' + (x.done ? ' done' : '') + '">' +
    '<input type="checkbox" data-key="' + esc(x.key) + '"' + (x.done ? ' checked' : '') + '>' +
    '<span><b>' + esc(x.label) + '</b>' +
    (x.note ? '<i class="mut small">' + esc(x.note) + '</i>' : '') + '</span></label>';

  document.getElementById('p-launch').innerHTML = [
    '<div class="pair"><div class="card"><h2>How far through</h2>',
    '<div id="ring-launch">',
    ring(todos.length - left, todos.length, 'done'),
    '<p class="mut small" style="text-align:center;margin:8px 0 0">',
    left ? plural(left, 'thing') + ' left to do.' : 'Everything is ticked off.', '</p></div></div>',
    '<div class="card"><h2>Settings the site checks itself</h2>',
    '<p class="mut small">Read from the last build, so these are the real settings.</p>',
    '<div class="alerts">',
    check(!site.noindex, 'Google may list the site', 'NOINDEX = False in build_site.py'),
    check((site.min_samples || 0) >= 200, 'MIN_SAMPLES is 200',
      'Now ' + num(site.min_samples) + '. It is lowered while designing.'),
    check(!!site.domain, 'Domain set in build_site.py',
      site.domain ? esc(site.domain) : 'The sitemap needs it to use full web addresses.'),
    check(!!site.contact, 'Contact email set', 'AdSense expects a way to reach you.'),
    check(!!site.ads, 'AdSense code pasted in', 'Paste it into ADS in build_site.py.'),
    check((t.pages_built || 0) >= 20, '20+ game pages with real data',
      'Now ' + num(t.pages_built) + '. AdSense wants real content first.'),
    '</div></div></div>',

    '<div class="card"><h2>Your checklist</h2>',
    '<p class="mut small">Only what is still to do. Ticked items fold away below. ',
    'Saved here, so it looks the same on any device you sign in from.</p>',
    '<div id="todo-open">',
    open.map(row).join('') || '<p class="mut small" id="todo-none">' + allDone + '</p>',
    '</div>',
    finished.length
      ? '<details class="donelist"><summary><span id="todo-done-n">' +
        plural(finished.length, 'finished item') + '</span></summary>' +
        '<div id="todo-done">' + finished.map(row).join('') + '</div></details>'
      : '<details class="donelist" hidden><summary><span id="todo-done-n"></span></summary>' +
        '<div id="todo-done"></div></details>',
    '</div>'
  ].join('');
}

/* ------------------------------------------------------------------ wiring */

/* Which tab is open is remembered, so a reload does not throw you back to the
   start while you are working through one list. */
function wireTabs() {
  const btns = document.querySelectorAll('#tabs button');
  const open = (name) => {
    Array.prototype.forEach.call(btns, b => {
      const on = b.dataset.tab === name;
      b.setAttribute('aria-selected', on);
      document.getElementById('p-' + b.dataset.tab).hidden = !on;
    });
    try { localStorage.setItem('pt_admin_tab', name); } catch (e) {}
  };
  Array.prototype.forEach.call(btns, b => { b.onclick = () => open(b.dataset.tab); });
  let saved = null;
  try { saved = localStorage.getItem('pt_admin_tab'); } catch (e) {}
  open(document.getElementById('p-' + saved) ? saved : 'overview');
}

/* Ticking a box saves straight away, and puts itself back if the save fails.
   A saved tick also moves the row into the folded-away list (and an untick moves
   it back), so the page matches what a reload would draw. The move happens only
   AFTER the save lands: a row that jumped before the server agreed would have to
   jump back on failure, which reads as the page glitching. */
function wireTodos() {
  Array.prototype.forEach.call(document.querySelectorAll('.todo input'), box => {
    box.onchange = () => {
      const row = box.closest('.todo');
      row.classList.toggle('done', box.checked);
      fetch('/admin/todo', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ key: box.dataset.key, done: box.checked })
      }).then(r => { if (!r.ok) throw 0; settleTodo(row, box.checked); }).catch(() => {
        box.checked = !box.checked;
        row.classList.toggle('done', box.checked);
        alert('Could not save that. Check your connection and try again.');
      });
    };
  });
}

/* Moves one row between the two lists and keeps the counts honest. */
function settleTodo(row, done) {
  const openList = document.getElementById('todo-open');
  const doneList = document.getElementById('todo-done');
  const fold = doneList && doneList.closest('.donelist');
  const count = document.getElementById('todo-done-n');
  if (!openList || !doneList || !fold || !count) return;
  (done ? doneList : openList).appendChild(row);
  const n = doneList.children.length;
  fold.hidden = !n;
  count.textContent = plural(n, 'finished item');
  /* The "nothing left" line appears and disappears with the open list. */
  const none = document.getElementById('todo-none');
  if (openList.children.length === 0 && !none) {
    const p = document.createElement('p');
    p.className = 'mut small';
    p.id = 'todo-none';
    p.textContent = 'Everything is ticked off.';
    openList.appendChild(p);
  } else if (openList.children.length > 1 && none) {
    none.remove();
  }
  paintRings();
}

/* Redraws both progress rings from what is on the page now. Without this the
   ring sat at its load-time number while the list beside it moved, which reads
   as the page being broken rather than as one number being a moment behind. */
function paintRings() {
  const total = document.querySelectorAll('#p-launch .todo').length;
  const doneN = document.querySelectorAll('#todo-done .todo').length;
  const left = total - doneN;
  const caption = (id, text) => {
    const box = document.getElementById(id);
    if (!box) return;
    box.innerHTML = ring(doneN, total, 'done') +
      '<p class="mut small" style="text-align:center;margin:8px 0 0">' + text + '</p>';
  };
  caption('ring-launch', left ? plural(left, 'thing') + ' left to do.' : 'Everything is ticked off.');
  caption('ring-ov', left ? plural(left, 'thing') + ' left. See the Launch checklist tab.'
                          : 'All ticked off.');
}
</script>` + TAIL;
}
