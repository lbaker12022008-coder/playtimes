/**
 * One place where every visitor number on the dashboard is worked out.
 *
 * The point of this file is consistency. A KPI card and the chart under it must not
 * each compute "views this month" their own way, or they will disagree the first time
 * a boundary moves, and the person reading them has no way to tell which is wrong. So
 * every window, every comparison and every percentage comes from here.
 *
 * WHAT CAN AND CANNOT BE MEASURED, and why. The `views` table is (day, path, count)
 * and `dwell` is (day, path, seconds, hits). There is no visitor identifier, no
 * timestamp, no referrer and no user agent, because the Privacy Policy promises the
 * site records "the page address, the date, and that number of seconds, and nothing
 * else" - on a site much of whose audience is nine years old. That promise is worth
 * more than the metrics it costs, and it costs real ones:
 *
 *   * unique visitors, sessions, bounce rate, pages per session and new-vs-returning
 *     all need to tell one person from another, which nothing here can do;
 *   * traffic sources, referrers and organic-search splits need the referrer;
 *   * device, browser and mobile-vs-desktop need the user agent;
 *   * anything per hour, or "online now", needs a timestamp. A day is the finest
 *     grain there is, so a 24-hour window is not offered.
 *
 * None of those are estimated here. An unmeasurable metric is left out rather than
 * guessed, which is also what the dashboard says in its place.
 */

/* Views recorded before this day include our own automated test browsers: one day in
   November logged 156 views across 114 different pages, which is a test sweep and not
   a person, and hundreds of one-second loads had dragged the homepage's average
   reading time to 19 seconds while pages real people read sat at 35-70. The beacons
   have skipped automated browsers since. Any window reaching back past this has to
   say so rather than present the difference as growth. */
export const CLEAN_FROM = "2026-11-22";

const DAY = 86400e3;
const isDay = (s) => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s);
const toDay = (ms) => new Date(ms).toISOString().slice(0, 10);
const dayMs = (s) => Date.parse(s + "T00:00:00Z");

/** Today in UTC. Every day boundary on the dashboard is UTC, because that is what
    the two beacons write, and mixing in a local midnight would double-count one day
    and lose another. */
export const today = () => toDay(Date.now());

/**
 * Works out the window to report on, and the window to compare it against.
 *
 * `from` and `to` are inclusive YYYY-MM-DD. Anything missing or malformed falls back
 * to the last 30 days rather than erroring, so a hand-typed address cannot break the
 * page. The comparison window is the same number of days immediately before it, which
 * is the only comparison that is fair: a 7-day window against a 30-day one would
 * report a collapse every time.
 */
export function windowFor(from, to) {
  const end = isDay(to) ? to : today();
  let start = isDay(from) ? from : toDay(dayMs(end) - 29 * DAY);
  if (dayMs(start) > dayMs(end)) start = end;            // swapped or nonsense dates
  const days = Math.round((dayMs(end) - dayMs(start)) / DAY) + 1;
  const prevEnd = toDay(dayMs(start) - DAY);
  const prevStart = toDay(dayMs(start) - days * DAY);
  return {
    from: start, to: end, days,
    prev_from: prevStart, prev_to: prevEnd,
    /* True when the window reaches back into the period that still counted our own
       test browsers, so the UI can caveat it instead of the reader trusting it. */
    includes_test_traffic: dayMs(start) < dayMs(CLEAN_FROM)
  };
}

/**
 * Percentage change, or null when there is nothing to compare against.
 *
 * null rather than 0 and never Infinity: going from no views to some views is not
 * "up 100%", and dividing by zero is not "no change". The dashboard prints nothing at
 * all in that case, which is the honest answer in a site's first weeks.
 */
export function change(current, previous) {
  if (!previous || previous <= 0) return null;
  return ((current - previous) / previous) * 100;
}

/* A window with no rows must come back as a run of zeroes rather than a short array,
   or a chart silently redraws a 30-day line as a 3-day one and reads as a cliff. */
function fillDays(rows, from, to) {
  const got = new Map((rows || []).map((r) => [r.day, Number(r.n) || 0]));
  const out = [];
  for (let t = dayMs(from); t <= dayMs(to); t += DAY) {
    const d = toDay(t);
    out.push({ day: d, n: got.get(d) || 0 });
  }
  return out;
}

/**
 * Every visitor figure for one window, plus the same figures for the window before it.
 *
 * One batch of queries rather than one per card: the dashboard is a single request and
 * must stay so, since it runs against the same database the public site writes to on
 * every page view.
 */
export async function readAnalytics(env, win) {
  const q = (sql, binds) => env.DB.prepare(sql).bind(...binds).all();

  const [daily, totals, timeNow, timePrev, pages, kinds, movers] = await Promise.all([
    /* The line chart. Grouped in SQL, gap-filled in JS. */
    q("SELECT day, SUM(n) AS n FROM views WHERE day >= ?1 AND day <= ?2 " +
      "GROUP BY day ORDER BY day", [win.from, win.to]),

    /* This window and the one before it in a single pass, so the two can never be
       read a second apart and disagree. */
    q("SELECT " +
      "SUM(CASE WHEN day >= ?1 AND day <= ?2 THEN n ELSE 0 END) AS now, " +
      "SUM(CASE WHEN day >= ?3 AND day <= ?4 THEN n ELSE 0 END) AS prev, " +
      "SUM(n) AS all_time, " +
      "COUNT(DISTINCT CASE WHEN day >= ?1 AND day <= ?2 THEN day END) AS days_seen, " +
      "COUNT(DISTINCT CASE WHEN day >= ?1 AND day <= ?2 THEN path END) AS paths_seen " +
      "FROM views", [win.from, win.to, win.prev_from, win.prev_to]),

    /* Reading time. `hits` is how many visits made up the total, so seconds/hits is a
       mean per visit - the only average these two columns can honestly support. */
    q("SELECT SUM(seconds) AS seconds, SUM(hits) AS reads FROM dwell " +
      "WHERE day >= ?1 AND day <= ?2", [win.from, win.to]),
    q("SELECT SUM(seconds) AS seconds, SUM(hits) AS reads FROM dwell " +
      "WHERE day >= ?1 AND day <= ?2", [win.prev_from, win.prev_to]),

    /* Top pages, with reading time beside each. The join is on an indexed path now
       (idx_dwell_path), where it used to scan dwell once per page listed. */
    q("SELECT v.path AS path, SUM(v.n) AS n, " +
      "COALESCE((SELECT SUM(d.seconds) FROM dwell d " +
      " WHERE d.path = v.path AND d.day >= ?1 AND d.day <= ?2), 0) AS seconds, " +
      "COALESCE((SELECT SUM(d.hits) FROM dwell d " +
      " WHERE d.path = v.path AND d.day >= ?1 AND d.day <= ?2), 0) AS reads " +
      "FROM views v WHERE v.day >= ?1 AND v.day <= ?2 " +
      "GROUP BY v.path ORDER BY n DESC LIMIT 25", [win.from, win.to]),

    /* What KIND of page people open. The November split gave every game four more
       pages and nothing said whether anybody reads them. */
    q("SELECT CASE WHEN path = '/' THEN 'Home page' " +
      "WHEN path LIKE '/game/%' THEN 'Game pages' " +
      "WHEN path LIKE '/questions/%' THEN 'Questions pages' " +
      "WHEN path LIKE '/events/%' THEN 'Event pages' " +
      "WHEN path LIKE '/passes/%' THEN 'What costs money pages' " +
      "WHEN path LIKE '/updates/%' THEN 'Update pages' " +
      "WHEN path LIKE '/category/%' THEN 'Category pages' " +
      "ELSE 'Everything else' END AS kind, SUM(n) AS n " +
      "FROM views WHERE day >= ?1 AND day <= ?2 GROUP BY kind ORDER BY n DESC",
      [win.from, win.to]),

    /* Which game pages are climbing: this window against the one before. Column
       names avoid `before`, which SQLite keeps for triggers. */
    q("SELECT path, " +
      "SUM(CASE WHEN day >= ?1 AND day <= ?2 THEN n ELSE 0 END) AS recent, " +
      "SUM(CASE WHEN day >= ?3 AND day <= ?4 THEN n ELSE 0 END) AS earlier " +
      "FROM views WHERE path LIKE '/game/%' AND day >= ?3 AND day <= ?2 " +
      "GROUP BY path", [win.from, win.to, win.prev_from, win.prev_to])
  ]);

  const t = totals.results?.[0] || {};
  const nowViews = Number(t.now) || 0;
  const prevViews = Number(t.prev) || 0;
  const tn = timeNow.results?.[0] || {};
  const tp = timePrev.results?.[0] || {};
  const readsNow = Number(tn.reads) || 0;
  const readsPrev = Number(tp.reads) || 0;
  const secsNow = Number(tn.seconds) || 0;
  const secsPrev = Number(tp.seconds) || 0;

  /* Average seconds per visit. null when nothing was recorded, so the card can say
     "no readings yet" instead of printing a confident 0s. */
  const avgNow = readsNow ? secsNow / readsNow : null;
  const avgPrev = readsPrev ? secsPrev / readsPrev : null;

  const series = fillDays(daily.results, win.from, win.to);

  return {
    window: win,
    views: {
      value: nowViews, prev: prevViews, change: change(nowViews, prevViews),
      all_time: Number(t.all_time) || 0,
      /* Views per day across the window, which is the figure that survives the window
         being a different length from the one before it. */
      per_day: win.days ? nowViews / win.days : null,
      days_with_data: Number(t.days_seen) || 0,
      pages_touched: Number(t.paths_seen) || 0,
      series
    },
    reading: {
      /* Total time anybody spent on the site, in seconds, and the mean per visit. */
      seconds: secsNow, prev_seconds: secsPrev, change_seconds: change(secsNow, secsPrev),
      reads: readsNow, prev_reads: readsPrev,
      average: avgNow, prev_average: avgPrev, change_average: change(avgNow, avgPrev)
    },
    weekday: byWeekday(series),
    pages: (pages.results || []).map((p) => ({
      path: p.path, n: Number(p.n) || 0,
      seconds: Number(p.seconds) || 0, reads: Number(p.reads) || 0,
      /* Per page, again a mean per visit, and null rather than 0 when this page has
         views but no completed reading time - which is what an exit looks like. */
      average: Number(p.reads) ? Number(p.seconds) / Number(p.reads) : null
    })),
    kinds: (kinds.results || []).map((k) => ({ kind: k.kind, n: Number(k.n) || 0 })),
    movers: (movers.results || [])
      .map((m) => ({
        path: m.path, recent: Number(m.recent) || 0, earlier: Number(m.earlier) || 0,
        change: change(Number(m.recent) || 0, Number(m.earlier) || 0)
      }))
      /* A page with no history has no trend. Sorting it as zero would rank every brand
         new page as "flat" among real movers, so it is excluded from the ranking and
         counted separately. */
      .filter((m) => m.recent || m.earlier)
  };
}

/**
 * Views by day of the week, summed across the window.
 *
 * Each bucket carries how many of that weekday the window actually contained, because
 * a 10-day window holds two Mondays and one Thursday - comparing their totals without
 * saying so would invent a pattern. `average` is the fair number; `n` is the honest
 * total.
 */
function byWeekday(series) {
  const names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const out = names.map((label) => ({ label, n: 0, days: 0, average: null }));
  for (const d of series) {
    const i = new Date(d.day + "T00:00:00Z").getUTCDay();
    out[i].n += d.n;
    out[i].days += 1;
  }
  for (const b of out) b.average = b.days ? b.n / b.days : null;
  return out;
}
