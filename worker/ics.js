/**
 * "Remind me": builds a calendar file for the days a visitor picked.
 *
 *   /reminder.ics?g=blox-fruits&m=quiet&d=0,5,6&z=1
 *
 *   g  the game, as it appears in its web address
 *   m  "quiet" or "busy"
 *   d  which days, 0 = Monday, in the visitor's OWN week
 *   z  how many hours the visitor is ahead of UTC (0 if the page could not say)
 *
 * One event per day, each repeating weekly, each at that day's own predicted hour,
 * because the quietest hour of a Tuesday is rarely the quietest hour of a Saturday.
 *
 * Nothing is stored and nothing is logged beyond Cloudflare's ordinary record of
 * files served: the address says which game and which days, and that is all there
 * is to know. No cookies, no account, so a signed-out visitor stays anonymous.
 *
 * It has to be built here rather than written out with the rest of the site because
 * seven days and two kinds of hour make 256 combinations per game. The alternative,
 * building the file inside the page, is what this replaced: it never ran on an
 * iPhone, where a click that has bubbled up arrives at a text node.
 */

const BYDAY = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];
const NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const WEEKS = 13;            // about three months, then the file runs out on purpose

/** Everything iCalendar insists on escaping, or a reader mistakes it for syntax. */
function esc(v) {
  return String(v).replace(/\\/g, "\\\\").replace(/;/g, "\\;")
    .replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

/**
 * No line may be longer than 75 OCTETS, and a game name with an emoji in it spends
 * four of them on one character. Counted in bytes for that reason, and never split
 * down the middle of a character: JavaScript stores an emoji as two halves, so the
 * pair is charged to the first half and the second is free.
 */
function fold(line) {
  let out = "", run = 0;
  for (let i = 0; i < line.length; i++) {
    const c = line.charCodeAt(i);
    const n = c < 128 ? 1 : c < 2048 ? 2
      : (c >= 0xD800 && c < 0xDC00) ? 4 : (c >= 0xDC00 && c < 0xE000) ? 0 : 3;
    if (n && run + n > 74) { out += "\r\n "; run = 1; }
    out += line[i];
    run += n;
  }
  return out;
}

function stamp(date) {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d+/, "");
}

/** The next time it is this UTC weekday (0 = Monday) at this UTC hour. */
function nextAt(utcDay, utcHour) {
  const now = new Date();
  const at = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(),
    utcHour, 0, 0));
  const want = (utcDay + 1) % 7;                       // ours is Monday-first, JS is Sunday-first
  at.setUTCDate(at.getUTCDate() + ((want - at.getUTCDay() + 7) % 7));
  if (at <= now) at.setUTCDate(at.getUTCDate() + 7);
  return at;
}

/**
 * The best hour of one day in the visitor's own week, and how long it lasts.
 *
 * Our numbers are in UTC and the page shifts them by the visitor's offset to show
 * them, so this undoes that shift to look the hour up: the visitor's Saturday
 * evening may well be Sunday morning in UTC.
 */
function bestHour(week, day, mode, z) {
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

function calendar(game, mode, days, z) {
  const word = mode === "quiet" ? "quiet" : "busy";
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PlayTime//EN",
    "CALSCALE:GREGORIAN", `X-WR-CALNAME:${esc(game.n + " – usually " + word)}`];
  const now = stamp(new Date());
  let made = 0;
  for (const day of days) {
    const best = bestHour(game.m, day, mode, z);
    if (!best) continue;
    const start = nextAt(best.utcDay, best.utcHour);
    const end = new Date(start.getTime() + best.length * 3600000);
    lines.push("BEGIN:VEVENT",
      // Steady across visits, so adding the same reminder twice updates it in the
      // calendar instead of leaving two of them behind.
      `UID:pt-${game.s}-${mode}-${day}@playtime`,
      `DTSTAMP:${now}`, `DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`,
      `RRULE:FREQ=WEEKLY;BYDAY=${BYDAY[day]};COUNT=${WEEKS}`,
      "SUMMARY:" + esc(`${game.n} is usually ${word}`),
      "DESCRIPTION:" + esc(
        `${NAMES[day]} is usually at its ${mode === "quiet" ? "quietest" : "busiest"} ` +
        `around now for ${game.n}, with about ${Math.round(best.value).toLocaleString("en-US")} ` +
        `players, for about ${best.length} hour${best.length > 1 ? "s" : ""}. ` +
        `Worked out from the player counts PlayTime collects. Repeats weekly for ` +
        `about three months, so check the site again after that.`),
      "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-PT10M",
      "DESCRIPTION:" + esc(`${game.n} is usually ${word}`),
      "END:VALARM", "END:VEVENT");
    made++;
  }
  lines.push("END:VCALENDAR");
  return made ? lines.map(fold).join("\r\n") + "\r\n" : null;
}

/** The games and their hours, from the same file the compare page already loads. */
async function loadGame(env, origin, slug) {
  const res = await env.ASSETS.fetch(new URL("/data.json", origin));
  if (!res.ok) return null;
  const data = await res.json();
  return (data.games || []).find((g) => g.s === slug) || null;
}

export async function handleIcs(request, env, path) {
  if (path !== "/reminder.ics") return null;
  const url = new URL(request.url);
  const slug = url.searchParams.get("g") || "";
  const mode = url.searchParams.get("m") === "busy" ? "busy" : "quiet";
  const days = [...new Set((url.searchParams.get("d") || "")
    .split(",").map((n) => parseInt(n, 10)))]
    .filter((n) => n >= 0 && n <= 6).sort();
  // Half-hour timezones are rounded to the hour everywhere else on the site, so
  // they are rounded here too rather than disagreeing with the page by an hour.
  const z = Math.max(-14, Math.min(14, Math.round(Number(url.searchParams.get("z")) || 0)));

  if (!/^[a-z0-9][a-z0-9-]{0,80}$/.test(slug) || !days.length) {
    return new Response("That reminder address is not one we recognise.", {
      status: 400, headers: { "content-type": "text/plain; charset=utf-8" }
    });
  }
  let body = null;
  try {
    const game = await loadGame(env, url.origin, slug);
    if (game && game.m) body = calendar(game, mode, days, z);
  } catch (err) {
    console.error("could not build a reminder", slug, err && err.stack || err);
  }
  if (!body) {
    return new Response("We do not have enough player counts for that game yet.", {
      status: 404, headers: { "content-type": "text/plain; charset=utf-8" }
    });
  }
  return new Response(body, {
    headers: {
      // text/calendar is what makes a phone offer to add it rather than showing it
      // as text, and "inline" is what gets iOS's own "Add to Calendar" screen.
      "content-type": "text/calendar; charset=utf-8",
      "content-disposition": `inline; filename="playtime-${slug}-${mode}.ics"`,
      "cache-control": "public, max-age=3600"
    }
  });
}
