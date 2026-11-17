/**
 * Browser notifications: "tell me when to get on".
 *
 * A signed-in person picks a game and whether they mean quiet or busy, and their
 * browser is woken up about fifteen minutes before that game's next best hour.
 *
 * WHO CAN HAVE IT, AND WHY IT IS NOT EVERYONE
 * A push subscription is a permanent per-device identifier. Storing one for a
 * visitor who has not signed in would be holding personal data about someone who
 * might be nine years old, which this site does not do. Roblox blocks under-13s from
 * authorising outside apps, so everyone who can sign in here is 13 or over. That is
 * the only reason this feature is allowed to exist, so do not "simplify" it by
 * offering it to signed-out visitors.
 *
 * WHAT IT STORES
 * Per device: the push endpoint the browser's own push service handed out, the two
 * keys needed to encrypt to it, and how many hours ahead of UTC they are so a
 * message can name a local time. Per person: which games, quiet or busy, and how
 * many minutes' warning. Nothing else - see schema_push.sql.
 *
 * SECRETS (set with `wrangler secret put`, never in this repo):
 *   VAPID_PUBLIC_KEY   base64url, 65 bytes uncompressed P-256 point
 *   VAPID_PRIVATE_KEY  base64url, the 32-byte private scalar
 *   VAPID_SUBJECT      optional; a mailto: address push services can complain to
 * If any of the first two is missing, available() is false, the page draws no
 * notification controls at all, and the cron does nothing. So the site is safe to
 * deploy before the keys exist.
 *
 * THE TWO STANDARDS THIS HAS TO GET RIGHT
 * VAPID (RFC 8292) is how we prove to a push service that the message is from us: a
 * JWT signed with ES256. Message encryption (RFC 8291) is how the body is kept from
 * the push service itself - Google and Mozilla relay these and must not be able to
 * read them. Both are implemented here with WebCrypto, because the usual Node
 * `web-push` package does not run on Workers. There is a round-trip test that
 * decrypts our own output; if you change encrypt(), run it.
 */
import { currentUserId } from "./auth.js";

const MAX_WATCH = 20;             // games one person may follow; bounds the cron's work
const MAX_DEVICES = 10;           // devices one person may have notifications on
const MAX_FAILS = 5;              // consecutive failures before a device is forgotten
const DEFAULT_LEAD = 15;          // minutes of warning
const CRON_MINUTES = 10;          // must match the cron in wrangler.jsonc
const TTL = 1800;                 // how long a push service should hold the message
const SAFE_SLUG = /^[a-z0-9][a-z0-9-]{0,80}$/;

const enc = s => new TextEncoder().encode(s);
const json = (data, status = 200) => new Response(JSON.stringify(data),
  { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

/** Notifications need the VAPID pair AND sign-in, since only signed-in people get them. */
export const pushReady = env => Boolean(
  env.VAPID_PUBLIC_KEY && env.VAPID_PRIVATE_KEY && env.SESSION_SECRET && env.ROBLOX_CLIENT_ID);

/** Requests that change data must come from our own pages. */
function sameSite(request) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try { return new URL(origin).host === new URL(request.url).host; } catch { return false; }
}

/* ------------------------------------------------------------- base64url bytes */

function b64urlToBytes(text) {
  const padded = String(text).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded + "=".repeat((4 - padded.length % 4) % 4));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

function bytesToB64url(bytes) {
  let raw = "";
  for (const b of bytes) raw += String.fromCharCode(b);
  return btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function concat(...parts) {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}

const sha256hex = async text => [...new Uint8Array(
  await crypto.subtle.digest("SHA-256", enc(text)))]
  .map(b => b.toString(16).padStart(2, "0")).join("");

/* ------------------------------------------------------------------- the crypto */

/** HKDF-SHA256, which both standards below use to stretch a secret into a key. */
async function hkdf(salt, ikm, info, bytes) {
  const key = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt, info }, key, bytes * 8));
}

/**
 * The VAPID signing key, rebuilt from the two secrets.
 *
 * WebCrypto will only import a private EC key as a JWK, which needs x and y as well
 * as d - so the public point is split up to supply them rather than being stored
 * twice. It also means a mismatched pair fails here, loudly, instead of producing
 * signatures every push service quietly rejects.
 */
async function vapidKey(env) {
  const pub = b64urlToBytes(env.VAPID_PUBLIC_KEY);
  if (pub.length !== 65 || pub[0] !== 4) {
    throw new Error("VAPID_PUBLIC_KEY should be 65 bytes of base64url starting with 0x04");
  }
  const d = b64urlToBytes(env.VAPID_PRIVATE_KEY);
  if (d.length !== 32) throw new Error("VAPID_PRIVATE_KEY should be 32 bytes of base64url");
  return crypto.subtle.importKey("jwk", {
    kty: "EC", crv: "P-256", ext: true,
    x: bytesToB64url(pub.slice(1, 33)),
    y: bytesToB64url(pub.slice(33, 65)),
    d: bytesToB64url(d)
  }, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
}

/**
 * The Authorization header that tells a push service this message is really ours.
 *
 * `aud` is the push service's own origin, not ours, and it must be exactly that or
 * the message is refused. WebCrypto's ECDSA signature is already the raw r||s pair a
 * JWT wants, so it needs no re-encoding.
 */
export async function vapidAuth(env, endpoint) {
  const head = bytesToB64url(enc(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const body = bytesToB64url(enc(JSON.stringify({
    aud: new URL(endpoint).origin,
    exp: Math.floor(Date.now() / 1000) + 12 * 3600,
    sub: env.VAPID_SUBJECT || "mailto:contact@playtimestats.com"
  })));
  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" }, await vapidKey(env), enc(head + "." + body));
  return "vapid t=" + head + "." + body + "." + bytesToB64url(new Uint8Array(signature)) +
    ", k=" + env.VAPID_PUBLIC_KEY;
}

/**
 * Encrypts a message so that only this one browser can read it (RFC 8291, aes128gcm).
 *
 * The push service in the middle - Google's, Mozilla's, Apple's - relays this without
 * being able to read it, which is the point: what somebody plays and when is not
 * theirs to see. A fresh keypair is made for every message, so one message cannot be
 * used to read another.
 *
 * The body that goes on the wire is laid out exactly as the standard says:
 *   salt (16) | record size (4) | key length (1) | our public key (65) | ciphertext
 * Every length here is fixed by the standard, which is why they are written out as
 * numbers and checked in the test rather than being computed.
 */
export async function encrypt(plaintext, p256dh, authSecret) {
  const uaPublic = b64urlToBytes(p256dh);
  const auth = b64urlToBytes(authSecret);
  if (uaPublic.length !== 65) throw new Error("the browser's p256dh key should be 65 bytes");
  if (auth.length !== 16) throw new Error("the browser's auth secret should be 16 bytes");

  const ours = await crypto.subtle.generateKey(
    { name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const ourPublic = new Uint8Array(await crypto.subtle.exportKey("raw", ours.publicKey));
  const theirKey = await crypto.subtle.importKey(
    "raw", uaPublic, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits(
    { name: "ECDH", public: theirKey }, ours.privateKey, 256));

  // The browser's auth secret is the salt here, and the two public keys go into the
  // info, which is what ties the result to this exact pair of parties.
  const prk = await hkdf(auth, shared,
    concat(enc("WebPush: info\0"), uaPublic, ourPublic), 32);

  const salt = crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, prk, enc("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hkdf(salt, prk, enc("Content-Encoding: nonce\0"), 12);

  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  // 0x02 marks the last (and here only) record. Without it a browser rejects the lot.
  const padded = concat(plaintext, new Uint8Array([2]));
  const sealed = new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce }, key, padded));

  const recordSize = new Uint8Array(4);
  new DataView(recordSize.buffer).setUint32(0, 4096);
  return concat(salt, recordSize, new Uint8Array([65]), ourPublic, sealed);
}

/* --------------------------------------------------------------- sending one push */

/**
 * Sends one notification to one device. Returns "ok", "gone" or "failed".
 *
 * "gone" is a 404 or 410 from the push service, which means that subscription will
 * never work again - the browser was uninstalled, or the person revoked permission.
 * Those rows are deleted rather than retried, because a dead endpoint retried every
 * ten minutes for ever is both useless and rude to the push service.
 */
async function sendOne(env, sub, message) {
  /* Every attempt records what the push service said, because the hard part of
     diagnosing this feature is that a push which is accepted and then not shown
     looks exactly like one that was never sent. `fails` alone cannot tell those
     apart: it stays 0 in both cases. 0 here means we could not even build the
     message and -1 means the push service could not be reached; anything else is
     its real HTTP status. */
  const record = async status => {
    try {
      await env.DB.prepare(
        "UPDATE push_subs SET last_status = ?1, last_try = ?2 WHERE id = ?3"
      ).bind(status, Date.now(), sub.id).run();
    } catch (err) {
      // Never let bookkeeping sink the send itself.
    }
  };

  let body, auth;
  try {
    body = await encrypt(enc(JSON.stringify(message)), sub.p256dh, sub.auth);
    auth = await vapidAuth(env, sub.endpoint);
  } catch (err) {
    console.error("could not build a notification", err && err.stack || err);
    await record(0);
    return "failed";
  }
  let res;
  try {
    res = await fetch(sub.endpoint, {
      method: "POST",
      headers: {
        authorization: auth,
        "content-encoding": "aes128gcm",
        "content-type": "application/octet-stream",
        ttl: String(TTL),
        urgency: "normal"
      },
      body
    });
  } catch (err) {
    console.error("push service unreachable", err && err.stack || err);
    await record(-1);
    return "failed";
  }
  await record(res.status);
  if (res.status === 404 || res.status === 410) return "gone";
  if (!res.ok) {
    console.error("push service refused", res.status, (await res.text().catch(() => "")).slice(0, 200));
    return "failed";
  }
  // Logged on success too: "it was accepted and still did not appear" is the
  // commonest complaint, and without this there is no way to tell it apart from
  // "it was never sent".
  console.log("push accepted", res.status, new URL(sub.endpoint).host);
  return "ok";
}

/** Sends to every device a person has, and tidies up the ones that have died. */
async function sendToUser(env, userId, message) {
  const { results } = await env.DB.prepare(
    "SELECT id, endpoint, p256dh, auth, tz, fails FROM push_subs WHERE rbx_id = ?1"
  ).bind(userId).all();
  const subs = results || [];
  let sent = 0;
  for (const sub of subs) {
    const how = await sendOne(env, sub, typeof message === "function" ? message(sub) : message);
    if (how === "ok") {
      sent++;
      if (sub.fails) await env.DB.prepare("UPDATE push_subs SET fails = 0 WHERE id = ?1").bind(sub.id).run();
    } else if (how === "gone") {
      await env.DB.prepare("DELETE FROM push_subs WHERE id = ?1").bind(sub.id).run();
    } else if (sub.fails + 1 >= MAX_FAILS) {
      await env.DB.prepare("DELETE FROM push_subs WHERE id = ?1").bind(sub.id).run();
    } else {
      await env.DB.prepare("UPDATE push_subs SET fails = fails + 1 WHERE id = ?1").bind(sub.id).run();
    }
  }
  return { devices: subs.length, sent };
}

/* ------------------------------------------------------- deciding what to say */

const HOURS = ["12 AM", "1 AM", "2 AM", "3 AM", "4 AM", "5 AM", "6 AM", "7 AM", "8 AM",
  "9 AM", "10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "6 PM",
  "7 PM", "8 PM", "9 PM", "10 PM", "11 PM"];

/**
 * The best hour of one day of somebody's own week, and how long it stays that way.
 *
 * Our player counts are in UTC and a page shifts them by the reader's offset to show
 * them, so this undoes that shift to look the hour up: somebody's Saturday evening
 * may well be Sunday morning in UTC. Get it backwards and every notification is out
 * by a day for half the world, which is why there are tests for all 27 offsets.
 *
 * This used to live in worker/ics.js and was shared with the calendar files. Those
 * are gone - the site offers notifications only now - so it has moved here, to the
 * one place left that asks the question.
 */
export function bestHour(week, day, mode, z) {
  const at = (localHour) => {
    const i = (((day * 24 + localHour - z) % 168) + 168) % 168;
    return week[Math.floor(i / 24)][i % 24];
  };
  let hour = null, value = null;
  for (let h = 0; h < 24; h++) {
    const v = at(h);
    if (v == null) continue;
    if (value == null || (mode === "quiet" ? v < value : v > value)) { hour = h; value = v; }
  }
  if (hour == null) return null;
  // How long it stays that way, counted the way the countdown on the page counts it.
  let length = 1;
  for (let step = 1; step < 6; step++) {
    const v = at((hour + step) % 24);
    if (v == null || (mode === "quiet" ? v > value * 1.25 : v < value * 0.8)) break;
    length++;
  }
  const i = (((day * 24 + hour - z) % 168) + 168) % 168;
  return { hour, value, length, utcDay: Math.floor(i / 24), utcHour: i % 24 };
}

/**
 * The next time this game is at its best, as a moment in UTC.
 *
 * Walks forward hour by hour and asks, for each one, whether it is the chosen hour of
 * the local day it falls in - the same question bestHour() answers for the calendar
 * file, with the same function, so the two can never disagree about a game.
 *
 * It looks 48 hours ahead because one local day's best hour can sit either side of
 * midnight UTC once a timezone is applied, so "today and tomorrow" is not enough.
 */
export function nextWindow(week, mode, tz) {
  const now = new Date();
  const top = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(),
    now.getUTCHours(), 0, 0);
  for (let step = 0; step <= 48; step++) {
    const at = new Date(top + step * 3600000);
    if (at <= now) continue;
    // Which day of the person's own week this UTC hour belongs to, Monday first.
    const localMs = at.getTime() + tz * 3600000;
    const local = new Date(localMs);
    const localDay = (local.getUTCDay() + 6) % 7;
    const best = bestHour(week, localDay, mode, tz);
    if (!best) return null;
    if (best.utcDay === (at.getUTCDay() + 6) % 7 && best.utcHour === at.getUTCHours()) {
      return { at, localHour: best.hour, players: best.value, length: best.length };
    }
  }
  return null;
}

function wording(game, mode, win, minutes) {
  const word = mode === "quiet" ? "quiet" : "busy";
  const soon = minutes <= 1 ? "now" : "in about " + minutes + " minutes";
  return {
    title: game.n + " is usually " + word + " " + soon,
    body: "Around " + HOURS[win.localHour] + " your time, with about " +
      Math.round(win.players).toLocaleString("en-US") + " players, for about " +
      win.length + (win.length > 1 ? " hours" : " hour") + ".",
    url: "/game/" + game.s,
    tag: "pt-" + game.s
  };
}

/**
 * What to say about an event that is about to start.
 *
 * The title is written by the game's creators, so it is somebody else's words in our
 * notification. It is capped to 80 characters where events.json is written, and it
 * only ever goes into a notification's text - never into HTML - so there is nothing
 * it can do beyond read oddly.
 */
function eventWording(game, ev, minutes, tz) {
  const local = new Date(ev.s * 1000 + tz * 3600000);
  const soon = minutes <= 1 ? "is starting now" : "starts in about " + minutes + " minutes";
  return {
    title: game.n + ": an event " + soon,
    body: ev.t + " - around " + HOURS[local.getUTCHours()] + " your time.",
    url: "/game/" + game.s,
    tag: "pt-event-" + game.s
  };
}

/** The games and their hours, from the same file the compare page already loads. */
async function loadGames(env, origin) {
  const res = await env.ASSETS.fetch(new URL("/data.json", origin));
  if (!res.ok) return [];
  return (await res.json()).games || [];
}

/**
 * The creators' upcoming events, per game slug, written by build_site.py.
 *
 * Its own small file rather than part of data.json, which carries a whole week of
 * player counts for every game and is downloaded by visitors on two pages. Returns
 * an empty object on any failure, so a missing file means no event notifications
 * rather than no notifications at all.
 */
async function loadEvents(env, origin) {
  try {
    const res = await env.ASSETS.fetch(new URL("/events.json", origin));
    if (!res.ok) return {};
    return (await res.json()).games || {};
  } catch (err) {
    return {};
  }
}

/**
 * Claims one notification and sends it. Returns what happened.
 *
 * The claim comes first and is taken back if the send fails, so a blip costs a retry
 * next run rather than the whole window. Claimed per DEVICE, not per person: keyed on
 * the person, somebody with a phone and a laptop had the phone take the hour and the
 * laptop skip it silently.
 *
 * Shared by the quiet/busy window and the event paths, because the bookkeeping either
 * one needs is identical and two copies of it would drift.
 */
async function claimAndSend(env, sub, rbxId, slug, slot, message, now) {
  const claim = await env.DB.prepare(
    "INSERT OR IGNORE INTO push_sent (sub_id, rbx_id, slug, slot, at) " +
    "VALUES (?1, ?2, ?3, ?4, ?5)"
  ).bind(sub.id, rbxId, slug, slot, now).run();
  // Nothing inserted means this device was already told about this one.
  if (!claim.meta || claim.meta.changes === 0) return "already";

  const how = await sendOne(env, sub, message);
  if (how === "ok") {
    // Consecutive failures are what retire a device, so a success clears the count.
    if (sub.fails) {
      await env.DB.prepare("UPDATE push_subs SET fails = 0 WHERE id = ?1").bind(sub.id).run();
      sub.fails = 0;
    }
    return "sent";
  }
  if (how === "gone") {
    await env.DB.prepare("DELETE FROM push_subs WHERE id = ?1").bind(sub.id).run();
    return "gone";
  }
  // Let it be tried again next run rather than losing it to one blip.
  await env.DB.prepare("DELETE FROM push_sent WHERE sub_id = ?1 AND slug = ?2 AND slot = ?3")
    .bind(sub.id, slug, slot).run();
  if (sub.fails + 1 >= MAX_FAILS) {
    await env.DB.prepare("DELETE FROM push_subs WHERE id = ?1").bind(sub.id).run();
  } else {
    await env.DB.prepare("UPDATE push_subs SET fails = fails + 1 WHERE id = ?1").bind(sub.id).run();
    sub.fails++;
  }
  return "failed";
}

/* ------------------------------------------------------------------ the cron job */

/**
 * Runs every CRON_MINUTES. For each game somebody is following, works out when it is
 * next at its best and sends a notification if that is close enough.
 *
 * The window is the person's lead time plus one whole cron interval, so a run that
 * fires late still sends rather than skipping the day silently. push_sent is what
 * keeps that from turning into two notifications: the hour being aimed at is the key,
 * so the same window can only ever be announced once per person per game.
 */
export async function runPushCron(env, origin) {
  if (!pushReady(env)) return { skipped: "no VAPID keys" };
  const { results } = await env.DB.prepare(
    "SELECT w.rbx_id, w.slug, w.quiet, w.busy, w.lead, w.events FROM push_watch w " +
    "WHERE EXISTS (SELECT 1 FROM push_subs s WHERE s.rbx_id = w.rbx_id)").all();
  const watches = results || [];
  if (!watches.length) return { watches: 0, sent: 0 };

  const [games, events] = await Promise.all([
    loadGames(env, origin), loadEvents(env, origin)
  ]);
  const byslug = new Map(games.map(g => [g.s, g]));
  const now = Date.now();
  let sent = 0, considered = 0, eventsSent = 0;

  // Devices are read once per person rather than once per game: somebody following
  // ten games on two devices would otherwise be twenty of the same query.
  const devices = new Map();
  for (const w of watches) {
    const game = byslug.get(w.slug);
    if (!game || !game.m) continue;
    if (!devices.has(w.rbx_id)) {
      const got = await env.DB.prepare(
        "SELECT id, endpoint, p256dh, auth, tz, fails FROM push_subs WHERE rbx_id = ?1"
      ).bind(w.rbx_id).all();
      devices.set(w.rbx_id, got.results || []);
    }
    const subs = devices.get(w.rbx_id);
    if (!subs.length) continue;
    considered++;

    // Each device may be in a different timezone, so the window is worked out per
    // device. Usually that is one device and one answer.
    for (const sub of subs) {
      const tz = sub.tz || 0;

      // 1. The quiet and busy windows, each only if asked for. Independent, so
      //    somebody can have both: they are different hours of the day.
      let deviceGone = false;
      for (const kind of ["quiet", "busy"]) {
        if (!w[kind]) continue;
        const win = nextWindow(game.m, kind, tz);
        if (!win) continue;
        const minutes = Math.round((win.at.getTime() - now) / 60000);
        if (minutes < 0 || minutes > w.lead + CRON_MINUTES) continue;
        // The slot carries the kind, so a quiet notification cannot claim the hour a
        // busy one wanted. They fall on different hours in practice, but relying on
        // that would be relying on the data rather than on the key.
        const how = await claimAndSend(env, sub, w.rbx_id, w.slug,
          kind[0] + win.at.toISOString().slice(0, 13),
          wording(game, kind, win, minutes), now);
        if (how === "sent") sent++;
        if (how === "gone") { deviceGone = true; break; }
      }
      if (deviceGone) continue;

      // 2. The creators' own events, if they asked for those as well. Keyed on the
      //    event's start time rather than an hour, so two events in the same hour
      //    are two notifications and neither silences the other.
      if (!w.events) continue;
      for (const ev of (events[w.slug] || [])) {
        const minutes = Math.round((ev.s * 1000 - now) / 60000);
        if (minutes < 0 || minutes > w.lead + CRON_MINUTES) continue;
        const how = await claimAndSend(env, sub, w.rbx_id, w.slug, "evt" + ev.s,
          eventWording(game, ev, minutes, tz), now);
        if (how === "sent") { sent++; eventsSent++; }
        if (how === "gone") break;
      }
    }
  }

  // Two days is well past any window still worth remembering.
  await env.DB.prepare("DELETE FROM push_sent WHERE at < ?1").bind(now - 2 * 86400e3).run();
  return { watches: watches.length, considered, sent, events: eventsSent };
}

/* -------------------------------------------------------------------- the router */

async function subscribe(request, env, userId) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "Bad request" }, 400); }
  const endpoint = String(body?.endpoint || "");
  const p256dh = String(body?.keys?.p256dh || "");
  const auth = String(body?.keys?.auth || "");
  // Only a real https push endpoint, so this cannot be turned into a way of making
  // the worker fetch arbitrary addresses.
  let host;
  try {
    const parsed = new URL(endpoint);
    if (parsed.protocol !== "https:") throw new Error("not https");
    host = parsed.host;
  } catch { return json({ error: "Bad request" }, 400); }
  if (!p256dh || !auth || endpoint.length > 1000) return json({ error: "Bad request" }, 400);
  try {
    if (b64urlToBytes(p256dh).length !== 65 || b64urlToBytes(auth).length !== 16) throw new Error("bad keys");
  } catch { return json({ error: "Bad request" }, 400); }

  const tz = Math.max(-14, Math.min(14, Math.round(Number(body?.tz) || 0)));
  const id = await sha256hex(endpoint);
  const now = Date.now();

  const mine = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM push_subs WHERE rbx_id = ?1 AND id <> ?2").bind(userId, id).first();
  if ((mine?.n || 0) >= MAX_DEVICES) {
    return json({ error: "That is as many devices as one account can have notifications on." }, 409);
  }
  await env.DB.prepare(
    "INSERT INTO push_subs (id, rbx_id, endpoint, p256dh, auth, tz, created, fails) " +
    "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0) " +
    "ON CONFLICT (id) DO UPDATE SET rbx_id = ?2, p256dh = ?4, auth = ?5, tz = ?6, fails = 0"
  ).bind(id, userId, endpoint, p256dh, auth, tz, now).run();
  console.log("push device registered via", host);
  return json({ subscribed: true });
}

async function unsubscribe(request, env, userId) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "Bad request" }, 400); }
  const endpoint = String(body?.endpoint || "");
  if (endpoint) {
    await env.DB.prepare("DELETE FROM push_subs WHERE id = ?1 AND rbx_id = ?2")
      .bind(await sha256hex(endpoint), userId).run();
  } else {
    // No endpoint means "this account, everywhere" - the switch on the account menu.
    await env.DB.prepare("DELETE FROM push_subs WHERE rbx_id = ?1").bind(userId).run();
  }
  return json({ subscribed: false });
}

async function setWatch(request, env, userId) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "Bad request" }, 400); }
  const slug = String(body?.slug || "");
  if (!SAFE_SLUG.test(slug)) return json({ error: "Bad request" }, 400);
  if (body?.on === false) {
    await env.DB.prepare("DELETE FROM push_watch WHERE rbx_id = ?1 AND slug = ?2")
      .bind(userId, slug).run();
    return json({ watching: false, slug });
  }
  // Three independent switches. All three off is not a watch at all, so the row goes
  // - otherwise it would sit there looking switched on and never send anything.
  const quiet = body?.quiet ? 1 : 0;
  const busy = body?.busy ? 1 : 0;
  const events = body?.events ? 1 : 0;
  if (!quiet && !busy && !events) {
    await env.DB.prepare("DELETE FROM push_watch WHERE rbx_id = ?1 AND slug = ?2")
      .bind(userId, slug).run();
    return json({ watching: false, slug });
  }
  const lead = Math.max(5, Math.min(120, Math.round(Number(body?.lead) || DEFAULT_LEAD)));
  const have = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM push_watch WHERE rbx_id = ?1 AND slug <> ?2").bind(userId, slug).first();
  if ((have?.n || 0) >= MAX_WATCH) {
    return json({ error: "That is as many games as one account can follow." }, 409);
  }
  await env.DB.prepare(
    "INSERT INTO push_watch (rbx_id, slug, quiet, busy, events, lead, added) " +
    "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7) " +
    "ON CONFLICT (rbx_id, slug) DO UPDATE SET quiet = ?3, busy = ?4, events = ?5, lead = ?6"
  ).bind(userId, slug, quiet, busy, events, lead, Date.now()).run();
  return json({ watching: true, slug, quiet, busy, events, lead });
}

/**
 * Sends one notification straight away, so a person can see it work.
 *
 * Worth having for its own sake: permission was granted on a different screen, and
 * "did that actually do anything?" is otherwise unanswerable until the small hours.
 */
async function sendTest(request, env, userId) {
  const out = await sendToUser(env, userId, {
    title: "Notifications are on",
    body: "This is what a PlayTime reminder looks like. We will only send one when a " +
      "game you follow is about to get quiet or busy.",
    url: "/", tag: "pt-test"
  });
  if (!out.devices) return json({ error: "This device is not set up for notifications yet." }, 409);
  if (!out.sent) return json({ error: "Your browser would not accept the notification." }, 502);
  return json({ sent: out.sent });
}

async function state(request, env, userId) {
  const [subs, watch] = await Promise.all([
    env.DB.prepare("SELECT COUNT(*) AS n FROM push_subs WHERE rbx_id = ?1").bind(userId).first(),
    env.DB.prepare("SELECT slug, quiet, busy, events, lead FROM push_watch WHERE rbx_id = ?1 ORDER BY added")
      .bind(userId).all()
  ]);
  return json({
    available: true, signedIn: true,
    key: env.VAPID_PUBLIC_KEY,
    devices: subs?.n || 0,
    watching: watch.results || [],
    maxGames: MAX_WATCH
  });
}

/** Returns a Response for anything notification-related, or null to let others handle it. */
export async function handlePush(request, env, path) {
  if (!path.startsWith("/api/push/")) return null;

  // Nothing here exists until the keys do, and the page asks before drawing anything.
  if (!pushReady(env)) return json({ available: false, signedIn: false });

  const userId = await currentUserId(request, env);
  if (!userId) {
    // Deliberately the same shape as the signed-in answer, so the page has one thing
    // to read. Notifications are for signed-in people, and this is where that is
    // actually enforced rather than merely intended.
    return json({ available: true, signedIn: false, key: env.VAPID_PUBLIC_KEY });
  }

  if (path === "/api/push/state" && request.method === "GET") return state(request, env, userId);

  if (request.method !== "POST") return json({ error: "Not allowed" }, 405);
  if (!sameSite(request)) return json({ error: "Blocked" }, 403);

  if (path === "/api/push/subscribe") return subscribe(request, env, userId);
  if (path === "/api/push/unsubscribe") return unsubscribe(request, env, userId);
  if (path === "/api/push/watch") return setWatch(request, env, userId);
  if (path === "/api/push/test") return sendTest(request, env, userId);
  return json({ error: "Not allowed" }, 405);
}
