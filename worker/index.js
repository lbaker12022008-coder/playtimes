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
import { CLEAN_FROM, readAnalytics, windowFor } from "./analytics.js";
import { buildInsights } from "./insights.js";
import { buildExport, csvResponse } from "./export.js";
import { maybeSyncGsc, readGsc, refreshGsc } from "./gsc.js";
import { dashboardBody } from "./admin_ui.js";

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
      if (path === "/admin/gsc" && request.method === "POST") return await gscNow(request, env);
      if (path === "/admin/export") return await exportCsv(request, env);
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
    /* Search Console, which decides for itself whether a day has passed: its figures
       are finalised two to three days late and the API has a daily quota, so fetching
       on every ten-minute tick would spend that quota to receive identical numbers.
       Its own try again - a Google outage must not touch notifications or ops. */
    try {
      const g = await maybeSyncGsc(env);
      if (g && g.ok) console.log("search console synced", JSON.stringify(g));
    } catch (err) {
      console.error("search console sync failed", err && err.stack || err);
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

/** Fetch Search Console now rather than waiting for the daily sync. Admin-only. */
async function gscNow(request, env) {
  if (!(await loggedIn(request, env))) return json({ error: "Not logged in" }, 401);
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(request.url).host) return json({ error: "Blocked" }, 403);
  const out = await refreshGsc(env);
  return json(out, out.ok ? 200 : 502);
}

/**
 * A CSV of whatever the dashboard is showing.
 *
 * It reassembles the same payload /admin/data serves rather than querying separately,
 * so a download and the screen it came from cannot disagree. GET rather than POST
 * because a browser has to be able to navigate to it to save the file; it is still
 * behind the admin session, and it only ever reads.
 */
async function exportCsv(request, env) {
  if (!(await loggedIn(request, env))) return json({ error: "Not logged in" }, 401);
  const url = new URL(request.url);
  const what = url.searchParams.get("what") || "";
  if (!/^[a-z]{1,16}$/.test(what)) return json({ error: "Bad request" }, 400);

  /* adminData already assembles everything and is the single source for these numbers,
     so the export borrows its answer instead of growing a second set of queries. */
  const inner = await adminData(request, env);
  if (inner.status !== 200) return inner;
  const data = await inner.json();

  const file = await buildExport(env, what, url.searchParams, data);
  if (!file) return json({ error: "There is no export called that" }, 404);
  return csvResponse(file.name, file.body);
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
  /* The window the dashboard is asking about, defaulting to the last 30 days. Both
     dates are validated in windowFor(), so a hand-typed address cannot break the
     page - it falls back rather than erroring. */
  const qs = new URL(request.url).searchParams;
  const win = windowFor(qs.get("from"), qs.get("to"));
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

  const payload = {
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
    /* Every visitor figure for the chosen window, plus the same figures for the
       window before it, all computed in worker/analytics.js so a card and the chart
       under it cannot work the same number out two different ways. */
    range: await readAnalytics(env, win),
    /* What people searched for to get here. Four distinct states, one of which is
       "the secrets are not set yet" carrying its own setup steps - so the panel can
       explain itself rather than look broken before the owner has done their part. */
    gsc: await readGsc(env),
    /* Visitor numbers before this day include our own automated test browsers - one
       day in November recorded 156 views across 114 different pages, which is a sweep
       and not a person. The beacons have skipped automated browsers since, so any
       chart crossing this line has to say so rather than draw it as growth. */
    clean_from: CLEAN_FROM
  };
  /* Insights read the finished payload rather than querying again, so a line on the
     list can never disagree with the card it is pointing at. */
  payload.insights = buildInsights(payload);
  return json(payload);
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
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
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
  /* The shell, the bar and the sign-out button stay here because loginHtml() uses the
     same two; everything below the bar is worker/admin_ui.js. */
  return SHELL + bar(
    `<form method="POST" action="/admin/logout" style="margin:0">` +
    `<button class="ghost" type="submit">Sign out</button></form>`) +
    dashboardBody() + TAIL;
}
