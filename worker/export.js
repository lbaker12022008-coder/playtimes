/**
 * CSV downloads of whatever the dashboard is showing.
 *
 * Admin-only, and every export honours the date window the dashboard is on, so a file
 * matches the screen it was taken from rather than silently covering some other period.
 * The window is named in the filename for the same reason.
 *
 * ONE THING HERE IS A SECURITY MEASURE, not formatting. Game names, page addresses and
 * event titles come from Roblox creators, and a spreadsheet treats a field beginning
 * with =, +, - or @ as a FORMULA. A game called "=HYPERLINK(...)" would execute when
 * the owner opened the file. cell() neutralises that, and must keep doing so: this is
 * the one place untrusted text leaves the site in a format that executes things.
 */

import { windowFor } from "./analytics.js";
import { WORKFLOWS } from "./ops.js";

/** What can be exported, and what each one is called to somebody reading a filename. */
export const EXPORTS = {
  traffic: "page-views-by-day",
  pages: "page-views-by-page",
  games: "games",
  runs: "collection-runs",
  errors: "failed-runs"
};

/**
 * Turns one value into one CSV field.
 *
 * Quoting rules are RFC 4180: wrap in quotes when the value holds a comma, a quote, or
 * a line break, and double any quote inside. The leading apostrophe is the formula
 * guard described above - it is what a spreadsheet reads as "this is text".
 */
function cell(v) {
  if (v === null || v === undefined) return "";
  /* A real number goes through untouched. This is not an optimisation: the formula
     guard below matches a leading minus, so running it over numbers turned all 112
     negative trend values into TEXT in the spreadsheet and nothing could be charted.
     A number cannot carry a formula, so there is nothing here to defend against. */
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  let s = String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  if (/[",\n\r]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
  return s;
}

const rows = (header, body) =>
  [header.map(cell).join(","), ...body.map((r) => r.map(cell).join(","))].join("\r\n") + "\r\n";

/**
 * Builds one CSV. Returns { name, body } or null when `what` is not a known export.
 *
 * `d` is the payload /admin/data already assembled, so an export can never disagree
 * with the screen: both read the same numbers from the same request.
 */
export async function buildExport(env, what, qs, d) {
  const win = windowFor(qs.get("from"), qs.get("to"));
  const stamp = win.from + "_to_" + win.to;
  const name = (base) => "playtime-" + base + "-" + stamp + ".csv";

  if (what === "traffic") {
    const series = ((d.range || {}).views || {}).series || [];
    /* Reading time is per day as well, so the two columns line up and a spreadsheet
       can chart them together. */
    const dw = await safeAll(env,
      "SELECT day, SUM(seconds) AS seconds, SUM(hits) AS reads FROM dwell " +
      "WHERE day >= ?1 AND day <= ?2 GROUP BY day", [win.from, win.to]);
    const byDay = new Map(dw.map((r) => [r.day, r]));
    return {
      name: name(EXPORTS.traffic),
      body: rows(
        ["date", "page_views", "reading_seconds", "completed_reads", "average_seconds_per_read"],
        series.map((s) => {
          const t = byDay.get(s.day) || {};
          const secs = Number(t.seconds) || 0;
          const reads = Number(t.reads) || 0;
          return [s.day, s.n, secs, reads,
            /* Empty, not 0: no readings is not an average of zero seconds. */
            reads ? (secs / reads).toFixed(1) : ""];
        }))
    };
  }

  if (what === "pages") {
    const ps = (d.range || {}).pages || [];
    return {
      name: name(EXPORTS.pages),
      body: rows(["page", "page_views", "reading_seconds", "completed_reads", "average_seconds"],
        ps.map((p) => [p.path, p.n, p.seconds, p.reads,
          p.average === null ? "" : p.average.toFixed(1)]))
    };
  }

  if (what === "games") {
    /* The Roblox side comes from the build, so it is as of the last build rather than
       the chosen window - the header says so by naming the column. */
    const games = ((d.stats || {}).games) || [];
    const live = new Map((((d.live || {}).games) || []).map((g) => [String(g.id), g]));
    const views = new Map((d.gameViews || []).map((v) => [v.path, Number(v.n) || 0]));
    const time = new Map((d.gameTime || []).map((t) => [t.path, t]));
    return {
      name: name(EXPORTS.games),
      body: rows(
        ["universe_id", "name", "slug", "genre", "readings_taken", "days_of_history",
         "average_players_7d", "trend_percent", "verdict", "events_total", "events_upcoming",
         "page_views_in_window", "reading_seconds_in_window", "last_reading_utc"],
        games.map((g) => {
          const path = "/game/" + g.slug;
          const t = time.get(path) || {};
          const l = live.get(String(g.id));
          return [g.id, g.name, g.slug, g.genre, g.samples,
            typeof g.days === "number" ? g.days.toFixed(1) : "",
            g.avg7, typeof g.trend === "number" ? g.trend : "", g.verdict,
            g.events, g.upcoming,
            views.get(path) || 0, Number(t.seconds) || 0,
            l && l.last ? new Date(l.last * 1000).toISOString().replace(".000Z", "Z") : ""];
        }))
    };
  }

  if (what === "runs" || what === "errors") {
    const onlyBad = what === "errors";
    const since = Math.floor(Date.parse(win.from + "T00:00:00Z") / 1000);
    const until = Math.floor(Date.parse(win.to + "T23:59:59Z") / 1000);
    const list = await safeAll(env,
      "SELECT wf, run_no, ok, concl, started, ended, secs, event FROM ops_runs " +
      "WHERE started >= ?1 AND started <= ?2 " + (onlyBad ? "AND ok = 0 " : "") +
      "ORDER BY started DESC", [since, until]);
    const label = new Map(WORKFLOWS.map((w) => [w.key, w.label]));
    return {
      name: name(onlyBad ? EXPORTS.errors : EXPORTS.runs),
      body: rows(["job", "job_name", "run_number", "result", "github_conclusion",
                  "started_utc", "finished_utc", "duration_seconds", "triggered_by"],
        list.map((r) => [r.wf, label.get(r.wf) || r.wf, r.run_no,
          /* Three states again: a run still going is not a failure. */
          r.ok === 1 ? "success" : (r.ok === 0 ? "failed" : "still running"),
          r.concl, iso(r.started), iso(r.ended), r.secs, r.event]))
    };
  }

  return null;
}

const iso = (unix) => (unix ? new Date(unix * 1000).toISOString().replace(".000Z", "Z") : "");

/** A query whose failure costs an empty column rather than the whole download. */
async function safeAll(env, sql, binds) {
  try {
    const r = await env.DB.prepare(sql).bind(...binds).all();
    return r.results || [];
  } catch (e) {
    return [];
  }
}

/** The response, with the headers that make a browser save it rather than show it. */
export function csvResponse(name, body) {
  return new Response("﻿" + body, {
    headers: {
      /* The byte-order mark above is for Excel: without it, a game name with an emoji
         or an accent in it opens as mojibake. */
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="' + name + '"',
      "cache-control": "no-store",
      "x-robots-tag": "noindex, nofollow"
    }
  });
}
