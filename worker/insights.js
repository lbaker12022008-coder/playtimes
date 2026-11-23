/**
 * Things worth knowing without being asked.
 *
 * The old "Needs doing" list was built from a handful of fixed conditions. This does
 * the same job properly: it looks at the back end, the visitor numbers, the Roblox
 * data and the notification devices, and reports only what somebody would actually
 * act on - ranked, with the figures that support it, and a suggested next step where
 * one exists.
 *
 * THE RULE THAT MATTERS: ordinary wobble is not an event. This site gets about ninety
 * page views a day, so a quiet Tuesday can be "down 40%" and mean nothing whatever.
 * Every traffic claim therefore has to clear a floor on the ABSOLUTE numbers before
 * its percentage is allowed to speak, and anything drawn from a window that still
 * contains our own test browsers is suppressed entirely rather than caveated - a
 * caveat on an alert is an alert nobody can trust.
 *
 * Severity decides the order: "fault" is something broken now, "warn" is something
 * heading that way, "note" is worth knowing, "todo" is a job outstanding.
 */

const RANK = { fault: 0, warn: 1, note: 2, todo: 3 };

/* Below these the percentage is noise, whatever it says. The floor is on the previous
   period, because that is the denominator doing the exaggerating: 1 view becoming 5 is
   "up 400%" and means nothing. */
const TRAFFIC_FLOOR = 40;     // views in the comparison window
const TRAFFIC_MOVE = 25;      // per cent before it is worth a line
const PAGE_FLOOR = 15;        // views on a single page before it can be called a riser
const PAGE_MOVE = 60;

const mins = (s) => Math.round(s / 60);
/* "1 hours ago" appeared on the live overview and read as a bug in everything beside
   it, which is roughly what a grammar slip on an alarm does. */
const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");
const pc = (n) => (n > 0 ? "+" : "") + Math.round(n) + "%";
const num = (n) => Number(n || 0).toLocaleString("en-GB");
const agoHours = (unix) => (Date.now() / 1000 - unix) / 3600;

/**
 * @param d  everything /admin/data already gathered: range, ops, stats, live, people, todos
 * @returns  a ranked array of { severity, title, why, data, action }
 */
export function buildInsights(d) {
  const out = [];
  const add = (severity, title, why, data, action) =>
    out.push({ severity, title, why, data: data || null, action: action || null });

  backEnd(d, add);
  freshness(d, add);
  notifications(d, add);
  traffic(d, add);
  pages(d, add);
  games(d, add);
  settings(d, add);

  out.sort((a, b) => RANK[a.severity] - RANK[b.severity]);
  return out;
}

/* ------------------------------------------------------- is the back end alive */

function backEnd(d, add) {
  const ops = d.ops;
  if (!ops || !ops.available) {
    add("warn", "System monitoring is not recording yet",
      "Nothing is keeping a record of whether collecting and building actually run, so a "
      + "stall would go unnoticed until the numbers looked old.",
      null, "Run worker/schema_ops.sql against the database.");
    return;
  }
  for (const w of ops.workflows) {
    const lr = w.last_run;

    /* Overdue is the one that matters: the job is not running at all. */
    if (w.overdue) {
      const h = w.last_success ? agoHours(w.last_success) : null;
      const when = h === null ? "has never worked"
        : (h < 24 ? "was " + plural(Math.round(h), "hour") + " ago"
          : "was " + plural(Math.round(h / 24), "day") + " ago");
      /* The cadence it actually keeps, not the one its cron asks for. Saying "every
         30 minutes" when it manages 76 sends somebody hunting for a fault that is
         really GitHub throttling a scheduled job. */
      const usual = w.every_real
        ? "It normally manages one about every " + Math.round(w.every_real / 60)
          + " minutes (its schedule asks for every " + w.every + ")"
        : "It should run every " + friendlyEvery(w.every);
      add("fault", w.label + " has stopped running",
        usual + ", and the last one that worked " + when
        + ". While it is stopped the site keeps serving the data it already has, so nothing "
        + "looks broken to a visitor.",
        { last_success: w.last_success, every: w.every, every_real: w.every_real },
        "Open GitHub, then Actions, and look at the most recent run for the reason.");
    }

    /* A failed most-recent run, even if the schedule is being kept. */
    if (lr && lr.ok === 0 && !w.overdue) {
      add("warn", "The last " + w.label.toLowerCase() + " run failed",
        "A later run may well have put it right - the window shows " + w.window.ok + " of "
        + w.window.runs + " succeeding - but the most recent one did not finish.",
        { conclusion: lr.concl, at: lr.at },
        "Check that run in GitHub Actions.");
    }

    /* A failure RATE worth noticing, rather than one blip. Needs enough runs behind it
       to mean anything, which is why ten is the floor. */
    if (w.window.runs >= 10 && w.window.failed > 0) {
      const rate = (w.window.failed / w.window.runs) * 100;
      if (rate >= 10) {
        add(rate >= 25 ? "fault" : "warn",
          w.label + " is failing often",
          w.window.failed + " of the last " + w.window.runs + " runs failed, which is "
          + Math.round(rate) + "%. One failure is a blip; this is a pattern.",
          { failed: w.window.failed, runs: w.window.runs },
          "Look for the same error across several runs in GitHub Actions.");
      }
    }

    /* Taking longer than its own schedule allows is a real risk and not obvious:
       collecting already uses 20 of its 30 minutes. */
    if (w.median_secs && w.median_secs > w.every * 60 * 0.8) {
      add("warn", w.label + " is using most of its time slot",
        "A typical run takes " + mins(w.median_secs) + " minutes of the "
        + w.every + " it has before the next one is due"
        + (w.slowest_secs ? ", and the slowest took " + mins(w.slowest_secs) : "")
        + ". If it grows much further the runs will start overlapping.",
        { median_secs: w.median_secs, every_mins: w.every }, null);
    }
  }
}

function friendlyEvery(m) {
  if (m >= 1440) return "day";
  if (m >= 60) return m / 60 + " hours";
  return m + " minutes";
}

/* ------------------------------------------------------------- is the data fresh */

function freshness(d, add) {
  const stats = d.stats || {};
  const live = d.live || null;

  /* IDs in games.txt that Roblox would not answer for. These are usually games that
     have been deleted or made private, and they stay in the file for ever otherwise. */
  const missing = stats.missing_ids || [];
  if (missing.length) {
    add("warn", num(missing.length) + " tracked game"
      + (missing.length === 1 ? "" : "s") + " Roblox no longer answers for",
      "They are still listed in games.txt, so every collection run asks about them and gets "
      + "nothing back. Usually it means the game was deleted or made private.",
      { ids: missing.slice(0, 12), total: missing.length },
      "Remove those IDs from games.txt if they are gone for good.");
  }

  /* The build is what puts fresh numbers on the site; the collector only gathers them.
     Six hours is the designed cap, so eight is the point of concern. */
  if (stats.built_at) {
    const h = (Date.now() - Date.parse(stats.built_at)) / 3.6e6;
    if (h > 8) {
      add(h > 24 ? "fault" : "warn", "The site has not rebuilt for " + Math.round(h) + " hours",
        "Builds are scheduled four times a day, so the pages a visitor sees - including every "
        + "game picture - are older than they should be.",
        { built_at: stats.built_at },
        "GitHub, then Actions, then the build site workflow, then Run workflow.");
    }
  }

  /* summary.json is written by the collector itself every half hour, so it is the one
     number that is current even when the site has not rebuilt. */
  if (live && live.updated) {
    const h = agoHours(live.updated);
    if (h > 1.5) {
      add(h > 6 ? "fault" : "warn", "No new player counts for " + Math.round(h) + " hours",
        "The collector writes a summary every half hour. When that stops, every chart on the "
        + "site slowly goes stale even though the pages still load.",
        { updated: live.updated }, "Check the collect workflow in GitHub Actions.");
    }
  }
}

/* ---------------------------------------------------------- do notifications work */

function notifications(d, add) {
  const p = (d.people || {}).devices || {};
  if (!p.n) return;

  /* The one fault this site cannot otherwise notice: a notification that silently
     never arrives. fails counts CONSECUTIVE failures, so any non-zero is live. */
  if (p.failing > 0) {
    add("warn", p.failing + " of " + p.n + " notification device"
      + (p.n === 1 ? "" : "s") + " cannot be reached",
      "The push service is refusing them. A device is dropped after five failures in a row, so "
      + "somebody is quietly getting nothing. Nothing else on the site would ever report this.",
      { failing: p.failing, total: p.n },
      "Open the People tab for what the push service last answered for each one.");
  }
  if (p.untried > 0 && p.untried === p.n) {
    add("note", "No notification has been attempted yet",
      "Devices are subscribed but nothing has been sent to them, so the chain is unproven.",
      { devices: p.n }, "Use Send me a test on the notifications page.");
  }
}

/* ----------------------------------------------------------------- is it growing */

function traffic(d, add) {
  const r = d.range;
  if (!r || !r.views) return;
  const v = r.views;

  /* Suppressed outright, not caveated. Until 22 Nov the figures include our own
     automated test sweeps - one day logged 156 views across 114 pages - so a growth
     claim from such a window would be measuring me. An alert that cannot be trusted
     is worse than no alert. */
  if (r.window.includes_test_traffic) {
    add("note", "Visitor figures for this period include our own testing",
      "Automated test browsers were counted as visitors until 22 November 2026, so growth "
      + "cannot be read from any window reaching back past it. Choose a later start date for "
      + "a figure you can trust.",
      { clean_from: "2026-11-22" }, null);
    return;
  }

  if (v.prev >= TRAFFIC_FLOOR && v.change !== null && Math.abs(v.change) >= TRAFFIC_MOVE) {
    const up = v.change > 0;
    add(up ? "note" : "warn",
      "Page views are " + (up ? "up" : "down") + " " + Math.abs(Math.round(v.change)) + "%",
      num(v.value) + " views this period against " + num(v.prev) + " in the "
      + r.window.days + " days before it."
      + (up ? " Worth seeing which pages did it." : " Worth checking nothing has broken."),
      { now: v.value, prev: v.prev, change: v.change },
      up ? "Open the Traffic tab to see where it came from." : null);
  }

  /* Not enough data to say anything at all is itself worth saying, so the empty
     dashboard explains itself instead of looking broken. */
  if (v.prev < TRAFFIC_FLOOR && v.value < TRAFFIC_FLOOR) {
    add("note", "Too few visits yet to spot a trend",
      "There are " + num(v.value) + " views in this period. Below about " + TRAFFIC_FLOOR
      + " a percentage swing is noise rather than news, so growth comparisons stay hidden "
      + "until there is enough to compare.",
      { now: v.value }, null);
  }
}

function pages(d, add) {
  const r = d.range;
  if (!r || r.window.includes_test_traffic) return;

  const risers = (r.movers || [])
    .filter((m) => m.earlier >= PAGE_FLOOR && m.change !== null && m.change >= PAGE_MOVE)
    .sort((a, b) => b.change - a.change);
  if (risers.length) {
    const t = risers[0];
    add("note", "One game page is climbing fast",
      t.path + " went from " + num(t.earlier) + " views to " + num(t.recent) + ", "
      + pc(t.change) + ". If that is coming from Google it is worth knowing which search found it.",
      { path: t.path, recent: t.recent, earlier: t.earlier },
      "Check the Search tab for the queries reaching that page.");
  }

  /* A page type nobody reads. The November split gave every game four extra pages and
     nothing has ever said whether they are worth their place in the sitemap. */
  const kinds = r.kinds || [];
  const total = kinds.reduce((a, k) => a + k.n, 0);
  if (total >= 200) {
    const dead = kinds.filter((k) => k.n === 0 || (k.n / total) < 0.01);
    if (dead.length) {
      add("note", "Some page types are barely opened",
        dead.map((k) => k.kind).join(", ") + " together account for under 1% of views. They each "
        + "cost a place in the sitemap and some of Google's attention.",
        { kinds: dead }, null);
    }
  }
}

/* --------------------------------------------------------------- the Roblox side */

function games(d, add) {
  const list = (d.stats || {}).games || [];
  if (!list.length) return;

  /* A trend is only trustworthy once there is enough history behind it: the site's own
     rule for a verdict is ten days, and fourteen for a trend. */
  const ready = list.filter((g) => g.days >= 14 && typeof g.trend === "number");

  const crashing = ready.filter((g) => g.trend <= -25).sort((a, b) => a.trend - b.trend);
  if (crashing.length) {
    add("note", crashing.length === 1 ? "One tracked game is emptying out"
      : num(crashing.length) + " tracked games are emptying out",
      crashing.slice(0, 3).map((g) => g.name + " " + pc(g.trend)).join(", ")
      + (crashing.length > 3 ? " and " + (crashing.length - 3) + " more" : "")
      + ". A game losing a quarter of its players changes what its page should say.",
      { games: crashing.slice(0, 8).map((g) => ({ name: g.name, trend: g.trend, avg: g.avg7 })) },
      null);
  }

  const booming = ready.filter((g) => g.trend >= 50).sort((a, b) => b.trend - a.trend);
  if (booming.length) {
    add("note", "Unusual player growth on " + (booming.length === 1 ? "a tracked game"
      : num(booming.length) + " tracked games"),
      booming.slice(0, 3).map((g) => g.name + " " + pc(g.trend)).join(", ")
      + ". These are the pages most likely to pick up searches right now.",
      { games: booming.slice(0, 8).map((g) => ({ name: g.name, trend: g.trend, avg: g.avg7 })) },
      null);
  }

  /* Games collected but with no page yet. Expected for about a day and a half after
     discover.py adds one; a large or long-standing pile is not expected. */
  const waiting = (d.stats || {}).waiting;
  const n = typeof waiting === "number" ? waiting : (Array.isArray(waiting) ? waiting.length : 0);
  if (n >= 25) {
    add("note", num(n) + " games are collected but have no page yet",
      "They need " + num((d.stats.site || {}).min_samples || 200)
      + " readings before a page is built, which takes about a day and a half. This many at once "
      + "usually means discover.py has been busy.",
      { waiting: n }, null);
  }
}

/* --------------------------------------------------- settings and jobs outstanding */

function settings(d, add) {
  const site = (d.stats || {}).site || {};

  /* These three are regression alarms rather than to-do items: all were settled long
     ago and can no longer fire in normal use, but they cost nothing while silent and
     each would be a serious, quiet mistake. */
  if (site.noindex) {
    add("fault", "The whole site is hidden from Google",
      "NOINDEX is switched on in build_site.py, so every page asks search engines to ignore it. "
      + "This was turned off in November 2026, so finding it on again means something was reverted.",
      null, "Set NOINDEX = False in build_site.py.");
  }
  if (!site.domain) {
    add("fault", "No domain is set",
      "Without DOMAIN the sitemap cannot carry full web addresses, so Google has nothing to crawl.",
      null, "Set DOMAIN in build_site.py.");
  }
  if (site.min_samples && site.min_samples < 200) {
    add("warn", "MIN_SAMPLES is below its proper value",
      "It is " + site.min_samples + " rather than 200, so pages are being built for games with too "
      + "few readings to be worth believing. It is lowered only for design work.",
      { min_samples: site.min_samples }, "Set MIN_SAMPLES = 200 in build_site.py.");
  }
  if (!site.ads) {
    add("todo", "AdSense is not set up yet",
      "It is the last item on the launch checklist and the site has the pages and the data for it now.",
      null, "Apply to AdSense, tick the child-directed setting, then paste the script into ADS.");
  }

  const all = d.todos || [];
  const open = all.filter((t) => !t.done);
  if (open.length) {
    /* The count of finished ones is not padding: one line reading "Apply to AdSense."
       on its own says nothing about whether that is the last job or the first of ten,
       and that is the whole question somebody is asking when they look. */
    add("todo", open.length === 1 ? "One checklist item is still open"
      : open.length + " checklist items are still open",
      open.slice(0, 4).map((t) => t.label).join("; ")
      + (open.length > 4 ? "; and " + (open.length - 4) + " more" : "")
      + ". That is " + (all.length - open.length) + " of " + all.length + " done.",
      { items: open.map((t) => t.key), done: all.length - open.length, total: all.length },
      "Open the Checklist tab.");
  }
}
