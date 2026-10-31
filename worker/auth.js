/**
 * "Sign in with Roblox" and saved games that follow a person between devices.
 *
 * Nothing here is reachable until worker/index.js calls handleAuth().
 *
 * What we store about a signed-in person: their Roblox user ID, their display
 * name, and which games they saved. No email, no password, no age, no browsing
 * history. Roblox blocks under-13 accounts from authorising apps, so everyone
 * who can sign in here is 13 or over.
 *
 * Secrets (already set in Cloudflare, never in this repo):
 *   ROBLOX_CLIENT_ID, ROBLOX_CLIENT_SECRET, SESSION_SECRET
 */

const AUTHORIZE = "https://apis.roblox.com/oauth/v1/authorize";
const TOKEN = "https://apis.roblox.com/oauth/v1/token";
const USERINFO = "https://apis.roblox.com/oauth/v1/userinfo";

const USER_COOKIE = "pt_user";
const STATE_COOKIE = "pt_state";
const SESSION_DAYS = 60;
const MAX_FAVS = 200;
const SAFE_SLUG = /^[a-z0-9-]{1,80}$/;

/* ------------------------------------------------------------- small tools */

const enc = s => new TextEncoder().encode(s);

async function hmac(secret, message) {
  const key = await crypto.subtle.importKey("raw", enc(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, enc(message));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}

/** Compares two strings without leaking which character differed. */
function sameSecret(a, b) {
  const x = enc(a), y = enc(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

const randomText = () => [...crypto.getRandomValues(new Uint8Array(24))]
  .map(b => b.toString(16).padStart(2, "0")).join("");

function readCookie(request, name) {
  return (request.headers.get("cookie") || "").split(";").map(c => c.trim())
    .find(c => c.startsWith(name + "="))?.slice(name.length + 1);
}

const json = (data, status = 200) => new Response(JSON.stringify(data),
  { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

/** Requests that change data must come from our own pages. */
function sameSite(request) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try { return new URL(origin).host === new URL(request.url).host; } catch { return false; }
}

const configured = env => Boolean(env.ROBLOX_CLIENT_ID && env.ROBLOX_CLIENT_SECRET && env.SESSION_SECRET);
const redirectUri = request => new URL(request.url).origin + "/auth/callback";

/* -------------------------------------------------------------- the session */

async function makeSession(env, userId) {
  const expires = Date.now() + SESSION_DAYS * 86400e3;
  const body = `${expires}.${userId}`;
  const value = `${body}.${await hmac(env.SESSION_SECRET, body)}`;
  return `${USER_COOKIE}=${value}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${SESSION_DAYS * 86400}`;
}

/** The signed-in person's Roblox ID, or null. */
export async function currentUserId(request, env) {
  if (!configured(env)) return null;
  const raw = readCookie(request, USER_COOKIE);
  if (!raw) return null;
  const parts = raw.split(".");
  if (parts.length !== 3) return null;
  const [expires, userId, signature] = parts;
  if (!/^\d+$/.test(expires) || Number(expires) < Date.now()) return null;
  if (!/^\d{1,25}$/.test(userId)) return null;
  return (await sameSecret(signature, await hmac(env.SESSION_SECRET, `${expires}.${userId}`))) ? userId : null;
}

const clearSession = `${USER_COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;

/* ----------------------------------------------------------------- the flow */

async function startLogin(request, env) {
  const state = randomText();
  const url = new URL(AUTHORIZE);
  url.searchParams.set("client_id", env.ROBLOX_CLIENT_ID);
  url.searchParams.set("redirect_uri", redirectUri(request));
  url.searchParams.set("scope", "openid profile");
  url.searchParams.set("response_type", "code");
  url.searchParams.set("state", state);
  return new Response(null, {
    status: 302,
    headers: {
      location: url.toString(),
      "cache-control": "no-store",
      // Short-lived: only needs to survive the trip to Roblox and back.
      "set-cookie": `${STATE_COOKIE}=${state}; HttpOnly; Secure; SameSite=Lax; Path=/auth; Max-Age=600`
    }
  });
}

async function finishLogin(request, env) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const expected = readCookie(request, STATE_COOKIE);

  if (url.searchParams.get("error")) return signInFailed("You cancelled signing in, or Roblox refused.");
  if (!code || !state || !expected || !sameSecret(state, expected))
    return signInFailed("That sign-in link was not valid. Please try again from the site.");

  const form = new URLSearchParams({
    client_id: env.ROBLOX_CLIENT_ID,
    client_secret: env.ROBLOX_CLIENT_SECRET,
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri(request)
  });
  const tokenRes = await fetch(TOKEN, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: form
  });
  if (!tokenRes.ok) return signInFailed("Roblox would not complete the sign-in. Please try again.");
  const tokens = await tokenRes.json();
  if (!tokens.access_token) return signInFailed("Roblox did not send back a sign-in token.");

  const infoRes = await fetch(USERINFO, { headers: { authorization: "Bearer " + tokens.access_token } });
  if (!infoRes.ok) return signInFailed("Could not read your Roblox profile.");
  const info = await infoRes.json();

  const userId = String(info.sub || "");
  if (!/^\d{1,25}$/.test(userId)) return signInFailed("Roblox sent back an unexpected profile.");
  const name = String(info.preferred_username || info.nickname || info.name || "Roblox user").slice(0, 60);

  const now = Date.now();
  await env.DB.prepare(
    "INSERT INTO users (rbx_id, name, created, seen) VALUES (?1, ?2, ?3, ?3) " +
    "ON CONFLICT (rbx_id) DO UPDATE SET name = ?2, seen = ?3"
  ).bind(userId, name, now).run();

  const headers = new Headers({ location: "/?signedin=1", "cache-control": "no-store" });
  headers.append("set-cookie", await makeSession(env, userId));
  headers.append("set-cookie", `${STATE_COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/auth; Max-Age=0`);
  return new Response(null, { status: 303, headers });
}

function signInFailed(reason) {
  const body = `<!doctype html><meta charset="utf-8"><title>Sign-in problem</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font:18px/1.6 system-ui,sans-serif;margin:0;padding:40px 20px;background:#f6f8fb;color:#14213d}
@media(prefers-color-scheme:dark){body{background:#0f1724;color:#eef2fb}}
.b{max-width:520px;margin:0 auto}a{color:#2563eb}</style>
<div class="b"><h1>Sign-in did not finish</h1><p>${reason}</p>
<p>You can keep using the site without signing in. Your saved games are still on this device.</p>
<p><a href="/">Back to PlayTime</a></p></div>`;
  return new Response(body, { status: 400, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
}

/* ------------------------------------------------------------- saved games */

async function readFavourites(env, userId) {
  const { results } = await env.DB.prepare(
    "SELECT slug FROM favourites WHERE rbx_id = ?1 ORDER BY added").bind(userId).all();
  return (results || []).map(r => r.slug);
}

async function writeFavourites(request, env, userId) {
  if (!sameSite(request)) return json({ error: "Blocked" }, 403);
  let body;
  try { body = await request.json(); } catch { return json({ error: "Bad request" }, 400); }
  const list = Array.isArray(body?.favs) ? body.favs : null;
  if (!list) return json({ error: "Bad request" }, 400);

  const clean = [...new Set(list.map(String).filter(s => SAFE_SLUG.test(s)))].slice(0, MAX_FAVS);
  const now = Date.now();
  const writes = [env.DB.prepare("DELETE FROM favourites WHERE rbx_id = ?1").bind(userId)];
  clean.forEach((slug, i) => writes.push(env.DB.prepare(
    "INSERT OR REPLACE INTO favourites (rbx_id, slug, added) VALUES (?1, ?2, ?3)").bind(userId, slug, now + i)));
  await env.DB.batch(writes);
  return json({ favs: clean });
}

async function deleteEverything(request, env, userId) {
  if (!sameSite(request)) return json({ error: "Blocked" }, 403);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM favourites WHERE rbx_id = ?1").bind(userId),
    env.DB.prepare("DELETE FROM users WHERE rbx_id = ?1").bind(userId)
  ]);
  return new Response(JSON.stringify({ deleted: true }), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store", "set-cookie": clearSession }
  });
}

/* -------------------------------------------------------------- the router */

/** Returns a Response for anything auth-related, or null to let other code handle it. */
export async function handleAuth(request, env, path) {
  if (path === "/api/me") {
    if (!configured(env)) return json({ signedIn: false, available: false });
    const userId = await currentUserId(request, env);
    if (!userId) return json({ signedIn: false, available: true });
    const row = await env.DB.prepare("SELECT name FROM users WHERE rbx_id = ?1").bind(userId).first();
    // id lets the page tell "this device has already handed its saved games to this
    // account" from "a different account just signed in here". Without it, removing a
    // game on one device gets undone by another device's older list.
    return json({
      signedIn: true, available: true, id: userId,
      name: row?.name || "Roblox user", favs: await readFavourites(env, userId)
    });
  }

  if (!configured(env)) {
    if (path.startsWith("/auth/") || path === "/api/favs" || path === "/api/delete-me")
      return json({ error: "Sign-in is not switched on yet." }, 503);
    return null;
  }

  if (path === "/auth/login" && request.method === "GET") return startLogin(request, env);
  if (path === "/auth/callback" && request.method === "GET") return finishLogin(request, env);
  if (path === "/auth/logout" && request.method === "POST") {
    if (!sameSite(request)) return json({ error: "Blocked" }, 403);
    return new Response(null, { status: 303, headers: { location: "/", "set-cookie": clearSession, "cache-control": "no-store" } });
  }

  if (path === "/api/favs" || path === "/api/delete-me") {
    const userId = await currentUserId(request, env);
    if (!userId) return json({ error: "Not signed in" }, 401);
    if (path === "/api/favs" && request.method === "GET") return json({ favs: await readFavourites(env, userId) });
    if (path === "/api/favs" && request.method === "PUT") return writeFavourites(request, env, userId);
    if (path === "/api/delete-me" && request.method === "POST") return deleteEverything(request, env, userId);
    return json({ error: "Not allowed" }, 405);
  }

  return null;
}
