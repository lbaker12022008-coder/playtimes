/**
 * What has happened lately, newest first.
 *
 * Only things that carry a time. That rules out the biggest one somebody would expect
 * to see here: **page views are not in this feed and cannot be**, because the `views`
 * table stores a day and a path and no clock. Putting "someone opened /game/doors" in
 * a live feed would need a timestamp per visit, and a timestamp per visit is a step
 * towards being able to follow one person around the site - which is the thing this
 * site has promised not to do. The panel says so rather than leaving a gap that looks
 * like a bug.
 *
 * WHAT IS NAMED AND WHAT IS NOT. Game names and slugs appear; people never do. No
 * display name, no Roblox ID, not even a shortened one. "Somebody signed in" is the
 * whole of what a sign-in event says, because knowing the feature works does not need
 * to know who, and a dashboard is a screen that gets photographed and shared.
 */

import { WORKFLOWS } from "./ops.js";

const now = () => Math.floor(Date.now() / 1000);

/** A query whose failure costs one kind of event rather than the whole feed. */
async function soft(env, sql, binds) {
  try {
    const r = await env.DB.prepare(sql).bind(...(binds || [])).all();
    return r.results || [];
  } catch (e) {
    return [];
  }
}

/**
 * @param limit how many events to return, newest first
 * @returns { events: [{ at, kind, text }], covers }
 */
export async function readFeed(env, limit = 40) {
  const since = now() - 7 * 86400;
  const sinceMs = (now() - 7 * 86400) * 1000;
  const label = new Map(WORKFLOWS.map((w) => [w.key, w.label]));

  const [runs, joined, seen, saved, sent] = await Promise.all([
    soft(env, "SELECT wf, ok, concl, started, secs, event FROM ops_runs " +
      "WHERE started >= ?1 ORDER BY started DESC LIMIT 60", [since]),
    /* UNITS, and this is the trap in this file. Every table written by the site itself
       stores Date.now(), which is MILLISECONDS: users.created, users.seen,
       favourites.added and push_sent.at. Only ops_runs.started is seconds, because
       that one is ours and GitHub reports seconds. Mixing them does not throw - a
       millisecond value compared against a second value is simply always greater - so
       the filter silently passes everything and the feed sorts rows into the year
       58,000. Checked against the real database rather than assumed; push_sent.at was
       the one this got wrong first time. */
    soft(env, "SELECT created FROM users WHERE created >= ?1 ORDER BY created DESC LIMIT 15",
      [sinceMs]),
    soft(env, "SELECT seen, created FROM users WHERE seen >= ?1 AND seen > created + 60000 " +
      "ORDER BY seen DESC LIMIT 15", [sinceMs]),
    soft(env, "SELECT slug, added FROM favourites WHERE added >= ?1 ORDER BY added DESC LIMIT 15",
      [sinceMs]),
    soft(env, "SELECT slug, at FROM push_sent WHERE at >= ?1 ORDER BY at DESC LIMIT 15",
      [sinceMs])
  ]);

  const ev = [];
  const push = (at, kind, text) => {
    if (at && Number.isFinite(at)) ev.push({ at: Math.floor(at), kind, text });
  };

  for (const r of runs) {
    const name = label.get(r.wf) || r.wf;
    if (r.ok === 0) push(r.started, "fault", name + " FAILED" + (r.concl ? " (" + r.concl + ")" : ""));
    else if (r.ok === null) push(r.started, "run", name + " started");
    else push(r.started, "ok", name + " finished" + (r.secs ? " in " + mmss(r.secs) : "") +
      (r.event === "workflow_dispatch" ? ", started by hand" : ""));
  }
  for (const u of joined) push(u.created / 1000, "person", "Somebody signed in for the first time");
  for (const u of seen) push(u.seen / 1000, "person", "Somebody came back and signed in");
  for (const f of saved) push(f.added / 1000, "save", "A game was saved: " + f.slug);
  for (const s of sent) push(s.at / 1000, "bell", "A notification was sent about " + s.slug);

  ev.sort((a, b) => b.at - a.at);
  return {
    events: ev.slice(0, limit),
    /* Said plainly on the panel. See the note at the top of this file. */
    covers: "Collection and build runs, sign-ins, saved games and notifications sent, " +
      "over the last seven days. Page views are not here: they are recorded against a " +
      "day rather than a moment, deliberately, so there is no timestamp to show."
  };
}

const mmss = (s) => (s >= 60 ? Math.floor(s / 60) + "m " + ("0" + (s % 60)).slice(-2) + "s" : s + "s");
