/**
 * Is the back end working?
 *
 * Collecting player counts, building the site and discovering new games all happen in
 * GitHub Actions. This worker cannot see any of it directly, so the dashboard used to
 * infer "the collector has stalled" from how old the data looked - which is a symptom,
 * not the fault, and says nothing about whether a run failed or simply never started.
 *
 * The repo is public, so GitHub's REST API answers with no token at all. What it will
 * not do is remember: only the last 100 runs of a workflow are served, and `collect`
 * runs 48 times a day. So the cron copies them into D1 as they happen and the
 * dashboard reads our own copy - see worker/schema_ops.sql for why that is a table
 * rather than a cached fetch.
 *
 * Nothing in here is allowed to break anything. Every entry point returns a shape the
 * dashboard can render even when GitHub is unreachable, the tables were never created
 * or the rate limit has been spent, because a dashboard that will not load is a worse
 * answer than a panel saying it does not know yet.
 */

const REPO = "lbaker12022008-coder/playtimes";

/* The workflows worth recording, and what to call them to somebody who did not write
   them. `staging` is deliberately absent: it deploys the test copy, it has nothing to
   do with whether the live site works, and listing it would put a fourth status light
   on the page that nobody should ever act on.

   `every` is how many minutes apart the schedule in .github/workflows puts them, and
   it is what "overdue" is measured against. If a cron in those files changes, this
   number has to change with it. */
export const WORKFLOWS = [
  { file: "collect.yml", key: "collect", label: "Collecting player counts", every: 30 },
  { file: "build.yml", key: "build", label: "Rebuilding the site", every: 360 },
  { file: "discover.yml", key: "discover", label: "Finding new games", every: 1440 }
];

/* GitHub refuses a request with no User-Agent. It names the site, which is public,
   and never the owner: a header is the last place a personal address belongs. */
const HEADERS = {
  "user-agent": "PlayTime-Admin/1.0 (+https://playtimestats.com)",
  "accept": "application/vnd.github+json",
  "x-github-api-version": "2022-11-28"
};

const now = () => Math.floor(Date.now() / 1000);
const unix = (iso) => (iso ? Math.floor(new Date(iso).getTime() / 1000) : null);

async function ghJson(path) {
  const r = await fetch("https://api.github.com/repos/" + REPO + path, { headers: HEADERS });
  if (!r.ok) {
    /* GitHub answers 403 rather than 429 when the budget is spent, so the remaining
       header is the only way to tell "wait a while" from "that address is wrong". */
    const left = r.headers.get("x-ratelimit-remaining");
    throw new Error("github " + r.status + (left === "0" ? " (rate limited)" : ""));
  }
  return await r.json();
}

/* ------------------------------------------------------------------- writing */

/**
 * Copies recent runs into D1. Called from the cron every ten minutes.
 *
 * Two calls per workflow, six in all: the recent runs (whose envelope also carries the
 * all-time total) and a count of every failure there has ever been, which
 * status=failure with per_page=1 answers in one go without listing them.
 *
 * On the very first sync it asks for 100 runs each, to backfill what GitHub still
 * holds; after that 30 is plenty, since the busiest workflow adds one run per half
 * hour and the cron runs three times in that period.
 */
export async function syncOps(env) {
  const out = { ok: [], failed: [] };
  let known = 0;
  try {
    const r = await env.DB.prepare("SELECT COUNT(*) AS n FROM ops_runs").first();
    known = (r && r.n) || 0;
  } catch (e) { /* table missing: treat as a cold start and let the insert report it */ }
  const want = known ? 30 : 100;

  for (const wf of WORKFLOWS) {
    try {
      const base = "/actions/workflows/" + wf.file + "/runs";
      const [list, fails] = await Promise.all([
        ghJson(base + "?per_page=" + want),
        ghJson(base + "?status=failure&per_page=1")
      ]);
      const runs = list.workflow_runs || [];
      const stmts = [];
      for (const r of runs) {
        const started = unix(r.run_started_at || r.created_at);
        if (!started) continue;
        const ended = r.status === "completed" ? unix(r.updated_at) : null;
        /* NULL while it is still going. Three states, not two: a run with no answer
           yet must never be drawn as a failure, and "0 or 1" cannot say that. */
        const ok = r.status === "completed" ? (r.conclusion === "success" ? 1 : 0) : null;
        stmts.push(env.DB.prepare(
          "INSERT INTO ops_runs (id, wf, run_no, ok, concl, started, ended, secs, event) " +
          "VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9) ON CONFLICT (id) DO UPDATE SET " +
          "ok = ?4, concl = ?5, ended = ?7, secs = ?8"
        ).bind(r.id, wf.key, r.run_number || null, ok, r.conclusion || null,
          started, ended, ended ? ended - started : null, r.event || null));
      }
      /* Chunked: D1 takes a batch of statements, not an unbounded one. */
      for (let i = 0; i < stmts.length; i += 50) await env.DB.batch(stmts.slice(i, i + 50));
      await setMeta(env, "gh_" + wf.key, JSON.stringify({
        total: list.total_count || 0, failures: fails.total_count || 0
      }));
      out.ok.push(wf.key + ":" + runs.length);
    } catch (err) {
      out.failed.push(wf.key + ":" + (err && err.message));
    }
  }

  /* 48 collect runs a day is about 17,000 rows a year. Ninety days is far more history
     than any panel shows, and keeps the table small enough to scan. */
  try {
    await env.DB.prepare("DELETE FROM ops_runs WHERE started < ?1").bind(now() - 90 * 86400).run();
  } catch (e) { /* nothing to prune on a cold start */ }

  if (out.ok.length) await setMeta(env, "ops_synced", String(now()));
  return out;
}

async function setMeta(env, k, v) {
  try {
    await env.DB.prepare(
      "INSERT INTO admin_meta (k, v, at) VALUES (?1,?2,?3) " +
      "ON CONFLICT (k) DO UPDATE SET v = ?2, at = ?3"
    ).bind(k, v, now()).run();
  } catch (e) { /* the dashboard copes with a missing value; the cron must not die of one */ }
}

/* ------------------------------------------------------------------- reading */

/**
 * What the dashboard shows about the back end.
 *
 * `days` bounds the per-run detail only. The all-time totals come from GitHub's own
 * counts, which reach back further than our copy does, so they are reported as what
 * they are rather than quietly mixed in with the window.
 */
export async function readOps(env, days = 30) {
  const since = now() - days * 86400;
  let rows = [];
  const meta = {};
  try {
    const r = await env.DB.prepare(
      "SELECT wf, ok, concl, started, ended, secs, event, run_no FROM ops_runs " +
      "WHERE started >= ?1 ORDER BY started DESC").bind(since).all();
    rows = r.results || [];
  } catch (e) {
    return { available: false, workflows: [], synced: null };
  }
  try {
    const r = await env.DB.prepare("SELECT k, v, at FROM admin_meta").all();
    for (const m of (r.results || [])) meta[m.k] = m;
  } catch (e) { /* totals are a bonus; the runs are the point */ }

  const workflows = WORKFLOWS.map((wf) => {
    const mine = rows.filter((r) => r.wf === wf.key);
    const done = mine.filter((r) => r.ok !== null);
    const good = done.filter((r) => r.ok === 1);
    const bad = done.filter((r) => r.ok === 0);
    const secs = good.filter((r) => r.secs > 0).map((r) => r.secs).sort((a, b) => a - b);
    let all = null;
    try { all = meta["gh_" + wf.key] ? JSON.parse(meta["gh_" + wf.key].v) : null; } catch (e) { }

    const lastGood = good[0] || null;      // rows arrive newest first
    const lastRun = mine[0] || null;
    const running = mine.filter((r) => r.ok === null).length;

    /* HOW OFTEN IT REALLY RUNS, measured rather than taken from the cron expression.
       collect.yml says every 30 minutes; the gaps between real runs are about 76,
       because each run takes some 21 minutes, the concurrency group stops two
       overlapping, and GitHub throttles scheduled jobs on a free account. Trusting
       the cron string made "overdue" fire permanently, which is the worst kind of
       alarm: one that is always on and therefore never read. */
    const gaps = [];
    for (let i = 0; i + 1 < mine.length; i++) {
      const g = mine[i].started - mine[i + 1].started;
      if (g > 0 && g < 7 * 86400) gaps.push(g);
    }
    gaps.sort((a, b) => a - b);
    const typical = gaps.length >= 3 ? gaps[Math.floor(gaps.length / 2)] : null;

    /* Late means late against whichever is longer: the schedule it asks for, or the
       cadence it actually keeps. Twice the usual gap, so one skipped turn is not an
       alarm but a genuine stop is. */
    const expected = Math.max(wf.every * 60, typical || 0);
    const slack = expected * 2 + 600;

    return {
      key: wf.key, label: wf.label, every: wf.every,
      window: { runs: done.length, ok: good.length, failed: bad.length, running },
      /* The middle value, not the mean: one twenty-minute run waiting on a Roblox
         timeout would drag an average and say nothing about a normal run. */
      median_secs: secs.length ? secs[Math.floor(secs.length / 2)] : null,
      slowest_secs: secs.length ? secs[secs.length - 1] : null,
      last_run: lastRun
        ? { at: lastRun.started, ok: lastRun.ok, concl: lastRun.concl, secs: lastRun.secs,
            event: lastRun.event, n: lastRun.run_no }
        : null,
      last_success: lastGood ? lastGood.started : null,
      /* What the schedule asks for, and what it actually achieves. Both are reported,
         because the gap between them is itself worth knowing: it is how somebody finds
         out the collector manages about 19 runs a day rather than the 48 its cron
         implies, and therefore why a game gathers fewer readings than expected. */
      every_real: typical,
      /* A run that has only just started may not be in our copy yet - the sync is
         every ten minutes - which is part of why the slack is generous. */
      overdue: lastGood ? (now() - lastGood.started) > slack : null,
      all_time: all,
      recent: mine.slice(0, 40).map((r) => ({ at: r.started, ok: r.ok, secs: r.secs })),
      /* One entry per day, for the reliability-over-time chart. */
      daily: byDay(mine, days)
    };
  });

  return {
    available: true,
    synced: meta.ops_synced ? Number(meta.ops_synced.v) : null,
    workflows
  };
}

/** Runs grouped into UTC days, oldest first, with empty days present as zeroes. */
function byDay(runs, days) {
  const out = [];
  const today = Math.floor(now() / 86400);
  const seen = new Map();
  for (const r of runs) {
    const d = Math.floor(r.started / 86400);
    if (!seen.has(d)) seen.set(d, { ok: 0, failed: 0 });
    const s = seen.get(d);
    if (r.ok === 1) s.ok++;
    else if (r.ok === 0) s.failed++;
  }
  for (let d = today - days + 1; d <= today; d++) {
    const s = seen.get(d) || { ok: 0, failed: 0 };
    out.push({ day: new Date(d * 86400e3).toISOString().slice(0, 10), ok: s.ok, failed: s.failed });
  }
  return out;
}
