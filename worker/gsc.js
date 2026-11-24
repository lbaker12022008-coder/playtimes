/**
 * Google Search Console: what people actually searched for to reach the site.
 *
 * This is the only honest source for search queries, impressions, click-through rate
 * and average position. It needs no privacy change at all, which is why it was worth
 * doing: Google reports its own aggregate about the SITE, never anything about a
 * visitor, so nothing here touches the promise that the site records only the page
 * address, the date and a number of seconds.
 *
 * AUTHENTICATION is a service-account JWT, signed here with WebCrypto, because a
 * Worker cannot run Google's Node libraries - the same approach push.js already uses
 * for VAPID, with RS256 in place of ES256. The flow is: sign a JWT asserting who we
 * are and what we want, swap it at Google's token endpoint for an access token, then
 * call the Search Console API with that. Access tokens last an hour and are cached.
 *
 * WHAT IS STORED AND WHY. Search Console data lags two to three days and barely moves
 * once settled, and the API has a daily quota, so the cron fetches it once a day and
 * the dashboard reads our copy out of D1. That also means a reader never waits on
 * Google, and a Google outage leaves yesterday's figures on screen rather than an
 * error.
 *
 * Every entry point answers with a shape the dashboard can render when the secrets are
 * absent, so the site is safe to deploy before any of the setup is done - exactly the
 * rule the Roblox sign-in keys follow.
 */

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const API = "https://searchconsole.googleapis.com/webmasters/v3/sites/";
const SCOPE = "https://www.googleapis.com/auth/webmasters.readonly";

/* Which property to ask about. A domain property is written sc-domain:example.com; a
   URL-prefix property is the address with its trailing slash. The owner's is whichever
   they verified, so it is overridable without a code change. */
const SITE = "sc-domain:playtimestats.com";

const now = () => Math.floor(Date.now() / 1000);
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const utf8 = (s) => new TextEncoder().encode(s);

/** True once both secrets exist. Nothing is attempted, and no panel is drawn, before. */
export function gscConfigured(env) {
  return !!(env.GSC_CLIENT_EMAIL && env.GSC_PRIVATE_KEY);
}

function siteFor(env) {
  return env.GSC_SITE || SITE;
}

/* --------------------------------------------------------------------- the token */

/**
 * The service account's private key, imported for RS256.
 *
 * A service-account JSON file holds the key as one line with the newlines written as
 * the two characters backslash-n. Depending on how it reached `wrangler secret put` it
 * may arrive either way, so both are accepted - this is the single likeliest thing to
 * go wrong in the whole setup, and it fails as an unhelpful "invalid key" otherwise.
 */
async function importKey(pem) {
  const body = String(pem)
    .replace(/\\n/g, "\n")
    .replace(/-----BEGIN [^-]+-----/, "")
    .replace(/-----END [^-]+-----/, "")
    .replace(/\s+/g, "");
  const raw = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
  return await crypto.subtle.importKey(
    "pkcs8", raw,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false, ["sign"]
  );
}

async function accessToken(env) {
  const head = b64url(utf8(JSON.stringify({ alg: "RS256", typ: "JWT" })));
  const iat = now();
  const claims = b64url(utf8(JSON.stringify({
    iss: env.GSC_CLIENT_EMAIL,
    scope: SCOPE,
    aud: TOKEN_URL,
    /* Google rejects anything over an hour. Fifty minutes leaves room for clock skew
       at both ends. */
    exp: iat + 3000,
    iat
  })));
  const key = await importKey(env.GSC_PRIVATE_KEY);
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, utf8(head + "." + claims));
  const jwt = head + "." + claims + "." + b64url(sig);

  const r = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: jwt
    })
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.access_token) {
    /* Google's own message is the useful part here and is about our credentials, not
       about a person, so it is safe to carry into the log and the admin panel. */
    throw new Error("token " + r.status + ": " + (j.error_description || j.error || "no token"));
  }
  return j.access_token;
}

/* ---------------------------------------------------------------------- the query */

async function query(site, token, body) {
  const r = await fetch(API + encodeURIComponent(site) + "/searchAnalytics/query", {
    method: "POST",
    headers: { authorization: "Bearer " + token, "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = (j.error && j.error.message) || ("status " + r.status);
    /* 403 here almost always means the service account was never added as a user on
       the property, which is the one setup step that happens outside this repo. */
    throw new Error(r.status === 403
      ? "Google refused access to " + site + ". Has the service account been added as a " +
        "user on that property? (" + msg + ")"
      : msg);
  }
  return j.rows || [];
}

/**
 * Which properties this service account can actually see.
 *
 * Search Console has two kinds of property and they are named differently - a domain
 * property is sc-domain:example.com, a URL-prefix one is https://example.com/ - and
 * asking about the wrong one fails in exactly the same way as not being given access
 * at all. Rather than make somebody guess, we ask Google what it will answer for and
 * say so. If there is exactly one, that is the answer and we use it.
 */
async function listSites(env, token) {
  try {
    const r = await fetch("https://searchconsole.googleapis.com/webmasters/v3/sites", {
      headers: { authorization: "Bearer " + token }
    });
    if (!r.ok) return [];
    const j = await r.json();
    return (j.siteEntry || [])
      .filter((s) => s.permissionLevel && s.permissionLevel !== "siteUnverifiedUser")
      .map((s) => s.siteUrl);
  } catch (e) {
    return [];
  }
}

const day = (back) => new Date(Date.now() - back * 86400e3).toISOString().slice(0, 10);

/**
 * Fetches the three views worth keeping and stores them. Called from the cron.
 *
 * Search Console data is finalised two to three days late, so the window ends three
 * days ago: asking for yesterday returns partial figures that then change, which would
 * read as a collapse and recovery every single day.
 */
export async function syncGsc(env) {
  if (!gscConfigured(env)) return { skipped: "not configured" };
  const token = await accessToken(env);

  /* Ask Google which property it will answer for before asking it anything else. One
     property means no guessing; several means use the configured name; none means the
     service account was never added as a user, which is the one setup step that
     happens outside this repo and the one most likely to be missed. */
  const sites = await listSites(env, token);
  if (!sites.length) {
    throw new Error("This service account cannot see any Search Console property yet. " +
      "In Search Console open Settings, then Users and permissions, then Add user, and " +
      "paste the service account email (the client_email from the JSON key file).");
  }
  let site = siteFor(env);
  if (!sites.includes(site)) {
    if (sites.length === 1) site = sites[0];
    else {
      throw new Error("The property " + site + " is not one this service account can see. " +
        "It can see: " + sites.join(", ") + ". Set the right one with " +
        "npx wrangler secret put GSC_SITE");
    }
  }

  /* Ask right up to yesterday and let Google decide how much of it is settled.
     dataState "final" means it returns nothing at all for a day it has not
     finalised, so a too-recent endDate costs nothing and never yields a partial
     figure - the worry that originally fixed this at three days ago. Asking for
     three meant the dashboard was always a day behind what Search Console's own
     screen shows, for no gain: Google usually finalises in two. */
  const startDate = day(31);
  const endDate = day(1);
  const base = { startDate, endDate, dataState: "final" };

  const [daily, queries, pages, devices] = await Promise.all([
    query(site, token, { ...base, dimensions: ["date"], rowLimit: 60 }),
    query(site, token, { ...base, dimensions: ["query"], rowLimit: 100 }),
    query(site, token, { ...base, dimensions: ["page"], rowLimit: 100 }),
    /* Google's own aggregate split, which is not visitor data of ours and costs
       nothing extra: it is the one honest answer we can give to "mobile or desktop". */
    query(site, token, { ...base, dimensions: ["device"], rowLimit: 10 })
  ]);

  const tidy = (rows, keyName) => rows.map((r) => ({
    [keyName]: (r.keys || [])[0] || "",
    clicks: r.clicks || 0,
    impressions: r.impressions || 0,
    ctr: r.ctr || 0,
    position: r.position || 0
  }));

  /* `to` is the last day Google actually ANSWERED for, not the last day asked
     about. Everything downstream reads it: the panel prints "from to to", and
     the clicks chart fills every day in that span with zero where Google
     reported nothing. That gap-fill is right in the middle of the window - a day
     Google has finalised and left out really did have no clicks - and wrong at
     the end, where a day it simply has not finalised yet would be drawn as a
     zero the site had invented. Ending at the real last row means the chart is
     as fresh as Google's settled data allows and never one day further. */
  const rows = tidy(daily, "date");
  const lastDay = rows.length
    ? rows.map((r) => r.date).sort().slice(-1)[0]
    : endDate;

  const payload = {
    site, from: startDate, to: lastDay, fetched: now(),
    daily: rows,
    queries: tidy(queries, "query"),
    pages: tidy(pages, "page"),
    devices: tidy(devices, "device")
  };
  await put(env, "gsc_data", JSON.stringify(payload));
  await put(env, "gsc_error", "");
  return { ok: true, queries: payload.queries.length, pages: payload.pages.length };
}

async function put(env, k, v) {
  try {
    await env.DB.prepare(
      "INSERT INTO admin_meta (k, v, at) VALUES (?1,?2,?3) " +
      "ON CONFLICT (k) DO UPDATE SET v = ?2, at = ?3"
    ).bind(k, v, now()).run();
  } catch (e) { /* the dashboard copes; the cron must not die of it */ }
}

/**
 * What the dashboard shows.
 *
 * Four states, and they are deliberately distinct, because "nothing here" has four
 * very different meanings and only one of them is a fault:
 *   not configured  - the secrets are absent, so show the setup steps
 *   never fetched   - configured but the cron has not run yet
 *   error           - it tried and Google said no, with Google's reason
 *   ok              - real figures, with the day they were fetched
 */
export async function readGsc(env) {
  if (!gscConfigured(env)) {
    return {
      state: "not_configured",
      site: siteFor(env),
      /* Written here rather than in the UI so the steps and the code that needs them
         cannot drift apart. */
      setup: [
        "At console.cloud.google.com, create a project (any name will do). It is free.",
        "In that project, search for Google Search Console API and press Enable.",
        "Go to Credentials, then Create credentials, then Service account. Give it any name and press Done - it needs no roles and no user access.",
        "Open the service account, go to its Keys tab, then Add key, then Create new key, and choose JSON. A file downloads.",
        "Open that file in a text editor and copy the client_email value. It ends in gserviceaccount.com.",
        "At search.google.com/search-console, open Settings, then Users and permissions, then Add user. Paste that email and choose Full.",
        "Set the two secrets from a terminal in the project folder (see the note below - do not paste the private key into a chat).",
        "Come back here and press Fetch now. Google finalises its figures two to three days late, so the newest day shown is usually the day before yesterday."
      ],
      /* Named here rather than in the UI so the wording and the code that needs it
         cannot drift. Piping beats pasting: the key never reaches the clipboard, the
         terminal history or a chat transcript - the same rule the VAPID keys and the
         Roblox client secret follow. */
      secrets: [
        "npx wrangler secret put GSC_CLIENT_EMAIL",
        "node -e \"process.stdout.write(require('./the-file-you-downloaded.json').private_key)\" | npx wrangler secret put GSC_PRIVATE_KEY"
      ],
      /* The property is discovered rather than configured: Google is asked what this
         service account can see, and if there is exactly one that is the one used. */
      note: "You do not need to tell it which site: it asks Google which properties the " +
        "service account can see. Delete the downloaded JSON file afterwards, and never " +
        "commit it."
    };
  }
  let row = null;
  try {
    row = await env.DB.prepare("SELECT v, at FROM admin_meta WHERE k = ?1").bind("gsc_data").first();
  } catch (e) { /* table missing: handled as never fetched */ }
  let err = null;
  try {
    const e = await env.DB.prepare("SELECT v FROM admin_meta WHERE k = ?1").bind("gsc_error").first();
    err = e && e.v ? e.v : null;
  } catch (e) { /* ignore */ }

  if (!row || !row.v) {
    return { state: err ? "error" : "never_fetched", site: siteFor(env), error: err };
  }
  let data = null;
  try { data = JSON.parse(row.v); } catch (e) { return { state: "error", error: "stored data unreadable" }; }

  const totals = (data.daily || []).reduce((a, r) => ({
    clicks: a.clicks + r.clicks, impressions: a.impressions + r.impressions
  }), { clicks: 0, impressions: 0 });

  return {
    state: "ok",
    site: siteFor(env),
    from: data.from, to: data.to, fetched: data.fetched,
    /* Recomputed from the daily rows rather than averaged from the per-query rows:
       averaging an average would be wrong, and CTR is clicks over impressions. */
    totals: {
      clicks: totals.clicks,
      impressions: totals.impressions,
      ctr: totals.impressions ? totals.clicks / totals.impressions : null,
      /* Position cannot be summed, so it is impression-weighted across the queries,
         which is what Google's own site-wide figure means. */
      position: weightedPosition(data.queries || [])
    },
    daily: data.daily || [],
    queries: data.queries || [],
    pages: data.pages || [],
    devices: data.devices || [],
    error: err
  };
}

function weightedPosition(rows) {
  let imp = 0, sum = 0;
  for (const r of rows) { imp += r.impressions; sum += r.position * r.impressions; }
  return imp ? sum / imp : null;
}

/**
 * Called from the ten-minute cron, but only actually fetches every six hours.
 *
 * Search Console finalises its figures two to three days late and has a daily request
 * quota, so asking every ten minutes would spend the quota to receive the same numbers
 * 144 times.
 *
 * It was twenty hours, which meant a new day of figures could sit at Google for the
 * best part of a day before this copy noticed. Six is still four syncs a day against
 * a quota measured in tens of thousands - one sync is four queries - and it cuts the
 * worst case from twenty hours to six. Not less than that: the numbers only change
 * when Google finalises another day, which happens once.
 */
export async function maybeSyncGsc(env) {
  if (!gscConfigured(env)) return { skipped: "not configured" };
  let age = Infinity;
  try {
    const row = await env.DB.prepare("SELECT at FROM admin_meta WHERE k = ?1")
      .bind("gsc_data").first();
    if (row && row.at) age = now() - Number(row.at);
  } catch (e) { /* no table yet: treated as never fetched, so it syncs */ }
  if (age < 6 * 3600) return { skipped: "fetched " + Math.round(age / 3600) + "h ago" };
  return await refreshGsc(env);
}

/** Admin-pressed refresh. Records Google's reason on failure so the panel can show it. */
export async function refreshGsc(env) {
  if (!gscConfigured(env)) return { ok: false, error: "not configured" };
  try {
    const out = await syncGsc(env);
    return { ok: true, ...out };
  } catch (err) {
    const msg = (err && err.message) || "that did not work";
    await put(env, "gsc_error", msg);
    return { ok: false, error: msg };
  }
}
