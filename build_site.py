"""Reads data.db and writes the whole PlayTime website into a folder (docs/ by default).

Everything about how the pages look and read lives in this one file.
The settings you are most likely to change are right below.

Preview your changes without touching the live site:
    set SITE_OUT=preview
    python seed_demo.py
    python build_site.py
    cd preview
    python -m http.server
Then open http://localhost:8000
"""
import html, json, os, re, sqlite3, statistics, time
from datetime import datetime, timezone

import roblox_api

SITE = "PlayTime"          # the site's name (don't put "Roblox" in your domain name)
MIN_SAMPLES = 2            # how many player counts a game needs before it gets a page
ADS = ""                   # paste your AdSense <script> here
NOINDEX = True             # True = ask Google NOT to list the site (set False when you launch)
OUT = os.environ.get("SITE_OUT") or "docs"   # which folder to write the site into
DOMAIN = ""                # your web address once you buy it, e.g. "https://playtime.gg"
ROBUX_USD = 0.0125         # rough dollars per Robux (800 Robux costs $9.99)
CONTACT = ""               # a contact email for the site (NOT your personal one)
POLICY_DATE = "October 30, 2026"   # change this whenever you edit the Privacy Policy

SPIKE = 1.5                # a day this much busier than normal is "likely an update or event"

CSS = """:root{--bg:#f3f6fc;--card:#fff;--ink:#101a33;--mut:#5b6478;--line:#e3e8f1;--acc:#2563eb;--acc2:#7c3aed;
--glass:rgba(243,246,252,.82);--sh:0 1px 2px rgba(16,26,51,.05),0 10px 30px rgba(16,26,51,.07);
--l1:#86e3d0;--l2:#b9e8a8;--l3:#f6e27a;--l4:#f7b267;--l5:#f28482;--up:#15803d;--down:#b91c1c;
--soft:#eef3ff}
@media(prefers-color-scheme:dark){:root{--bg:#0d1420;--card:#172033;--ink:#eef2fb;--mut:#a3aec4;--line:#283550;
--acc:#7aa7ff;--acc2:#b48cff;--glass:rgba(13,20,32,.82);--sh:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35);
--up:#4ade80;--down:#f87171;--soft:#1d2942}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:18px/1.6 ui-rounded,"SF Pro Rounded",Nunito,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}
.w{max-width:780px;margin:0 auto;padding:8px 16px 56px}
.w.wide{max-width:1120px}
a{color:var(--acc)}
h1{font-size:clamp(1.7rem,5vw,2.5rem);line-height:1.15;margin:.4em 0 .3em;letter-spacing:-.02em}
h2{font-size:1.15rem;margin:0 0 6px}
h3{font-size:1rem;margin:1.3em 0 .2em}
.lede{font-size:1.05rem;color:var(--mut);margin:.2em 0 1em}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px 20px;margin:16px 0;box-shadow:var(--sh)}
.mut{color:var(--mut)}.small{font-size:.9rem}
.up{color:var(--up)}.down{color:var(--down)}
.wrap{overflow-x:auto}
button,.btn,.chip,select{font:inherit}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
.ans p{margin:.35em 0;font-size:1.1rem}

/* top bar, with the sections across the top */
.hdr{position:sticky;top:0;z-index:9;background:var(--glass);backdrop-filter:saturate(1.4) blur(12px);border-bottom:1px solid var(--line);margin-bottom:6px}
.hdr .in{max-width:1120px;margin:0 auto;padding:6px 16px 0}
.hrow{display:flex;align-items:center;justify-content:space-between;gap:12px}
.acct{display:flex;align-items:center;gap:8px;font-size:.88rem;min-height:30px}
.acct form{margin:0}
.acct .who{color:var(--mut);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.acct .signin{padding:6px 13px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;font-weight:600;white-space:nowrap}
.acct .signin:hover{border-color:var(--acc)}
.acct .linkish{font:inherit;background:none;border:0;color:var(--mut);cursor:pointer;text-decoration:underline;padding:4px}
.logo{font-weight:800;font-size:1.25rem;color:var(--ink);text-decoration:none;letter-spacing:-.02em;white-space:nowrap}
.logo span{background:linear-gradient(95deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.tabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding:8px 16px;margin:0 -16px}
.tabs::-webkit-scrollbar{display:none}
.tabs a{flex:none;padding:7px 14px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;font-size:.92rem;font-weight:600;white-space:nowrap;transition:transform .12s,border-color .12s}
.tabs a:hover{border-color:var(--acc);transform:translateY(-1px)}
.tabs a[aria-current=page]{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.pills{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.pills a{padding:6px 14px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;font-size:.9rem}
.pills a:hover{border-color:var(--acc)}
.hero h1 em{font-style:normal;background:linear-gradient(95deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}

/* "what are you looking for?" */
.ask{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));margin:14px 0}
.chip{display:block;width:100%;text-align:left;padding:13px 16px;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;box-shadow:var(--sh);transition:transform .12s,border-color .12s}
.chip:hover{transform:translateY(-2px);border-color:var(--acc)}
.chip[aria-pressed=true]{border-color:var(--acc);box-shadow:inset 0 0 0 2px var(--acc)}
.chip b{display:block;font-size:1rem}
.chip i{display:block;font-style:normal;font-size:.85rem;color:var(--mut);line-height:1.35}

/* game tiles */
.grid{list-style:none;padding:0;margin:14px 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:22px 14px}
.grid>li{animation:up .45s cubic-bezier(.2,.75,.3,1) both;animation-delay:calc(var(--i,0)*28ms)}
.tile{display:block;text-decoration:none;color:var(--ink)}
.thumb{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:cover;border-radius:14px;background:var(--line);transition:transform .15s,box-shadow .15s}
.ph{display:grid;place-items:center;font-size:2.6rem;font-weight:800;color:var(--mut)}
.tile:hover .thumb{transform:translateY(-4px) scale(1.015);box-shadow:0 10px 24px rgba(0,0,0,.2)}
.tname{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-weight:700;font-size:.95rem;line-height:1.3;margin-top:8px}
.tmeta{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;font-size:.82rem;color:var(--mut);margin-top:3px}
.tmeta svg{width:14px;height:14px;vertical-align:-2px;fill:currentColor}

/* charts */
.days{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.days button{font-size:.95rem;padding:6px 14px;min-height:44px;border-radius:999px;border:1px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
.days button[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:700}
.bars{display:grid;grid-template-columns:repeat(24,1fr);gap:3px;align-items:end;height:160px;margin-top:12px}
.bar{border-radius:5px 5px 0 0;min-height:4px;transform-origin:bottom;animation:grow .5s cubic-bezier(.2,.8,.3,1) both;animation-delay:calc(var(--i,0)*11ms)}
.bar.b2{opacity:.72}
.axis{display:grid;grid-template-columns:repeat(24,1fr);font-size:.8rem;color:var(--mut);margin-top:4px}
.axis span{grid-column:span 6}
.hm{display:grid;grid-template-columns:44px repeat(24,minmax(0,1fr));gap:2px;font-size:.8rem;color:var(--mut);align-items:center}
.hm .c{height:26px;border-radius:4px}
.hm .now{outline:3px solid var(--ink);outline-offset:-1px}
.legend{display:flex;align-items:center;gap:4px;font-size:.85rem;color:var(--mut);margin-top:10px;flex-wrap:wrap}
.legend i{width:26px;height:12px;border-radius:3px;display:inline-block}
.spark{width:100%;height:80px;display:block}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}
.stats b{display:block;font-size:1.5rem}
.key{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:4px}

/* game page */
.ghead{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;margin:14px 0}
.ghead .thumb{width:150px;flex:none}
.ghead>div{flex:1 1 280px}
.ghead h1{margin:0 0 .2em}.ghead p{margin:.2em 0}
.btn{display:inline-block;background:linear-gradient(95deg,var(--acc),var(--acc2));color:#fff;padding:11px 20px;border-radius:13px;text-decoration:none;font-weight:700;box-shadow:var(--sh)}
.actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:10px}
.fav{font-weight:700;padding:10px 17px;border-radius:13px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.fav[aria-pressed=true]{border-color:#e0a800;color:#8a6500;background:#fff8e1}
@media(prefers-color-scheme:dark){.fav[aria-pressed=true]{background:#2a2410;color:#f3c653}}
.verdict{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.vbadge{font-size:1.05rem;font-weight:800;padding:8px 16px;border-radius:999px;white-space:nowrap;color:#15233f}
.tbl{width:100%;border-collapse:collapse;font-size:.95rem}
.tbl td,.tbl th{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.tbl td:last-child,.tbl th:last-child{text-align:right;white-space:nowrap}
details summary{cursor:pointer;color:var(--acc);font-weight:700;margin:6px 0}
.desc{white-space:pre-line;margin:.3em 0}
.evt{list-style:none;padding:0;margin:8px 0}
.evt li{border-left:3px solid var(--line);padding:2px 0 2px 14px;margin:16px 0}
.evt li.soon{border-left-color:var(--acc2);background:var(--soft);border-radius:0 10px 10px 0;padding:8px 12px 8px 14px}
.evt li.live{border-left-color:var(--up)}
.evt b{display:block}
.evt .d{font-size:.85rem;color:var(--mut)}
.evt p{margin:.3em 0;font-size:.95rem;white-space:pre-line}
.cd{font-size:1.4rem;font-weight:800;display:block;margin:.1em 0}
.sel{padding:10px 13px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--ink);max-width:100%}
.two{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
input[type=search]{width:100%;padding:13px 17px;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--ink);box-shadow:var(--sh);font:inherit}
.foot{border-top:1px solid var(--line);margin-top:36px;padding-top:12px}
.foot nav{display:flex;flex-wrap:wrap;gap:6px 18px;margin-bottom:6px}
.doc h2{margin-top:1.4em}.doc ul{padding-left:1.2em}
.none{color:var(--mut)}

/* the gentle opening effects */
@keyframes up{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes grow{from{transform:scaleY(.02)}to{transform:scaleY(1)}}
@keyframes fade{from{opacity:0}to{opacity:1}}
.rise{animation:up .5s cubic-bezier(.2,.75,.3,1) both}
.rise2{animation:up .5s cubic-bezier(.2,.75,.3,1) .08s both}
.rise3{animation:up .5s cubic-bezier(.2,.75,.3,1) .16s both}
.card{animation:fade .7s both}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}"""

ROBOTS = '<meta name="robots" content="noindex,nofollow">' if NOINDEX else ""

# Counts one page view. No cookies, no login, nothing about the visitor is stored.
HIT = ('<script>try{fetch("/api/hit",{method:"POST",headers:{"content-type":"text/plain"},'
       'body:location.pathname,keepalive:true})}catch(e){}</script>')

# The sections along the top of every page: (key, label, address)
TABS = [("home", "All games", "/"),
        ("popular", "Most popular", "/popular.html"),
        ("trending", "Trending", "/trending.html"),
        ("growing", "Growing", "/growing.html"),
        ("shrinking", "Shrinking", "/shrinking.html"),
        ("events", "Events", "/events.html"),
        ("compare", "Compare", "/compare.html"),
        ("plan", "Plan a session", "/plan.html")]

# Words for the five busy-ness levels, used all over the site.
WORDS = ["no data", "very quiet", "quiet", "average", "busy", "very busy"]


def page(title, body, desc="", wide=False, nav="", tail=""):
    tabs = "".join(f'<a href="{u}"{" aria-current=page" if k == nav else ""}>{html.escape(t)}</a>'
                   for k, t, u in TABS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}"><meta name="theme-color" content="#2563eb">{ROBOTS}
<style>{CSS}</style><script>{FAVJS}</script>{ADS}</head><body>
<header class="hdr"><div class="in"><div class="hrow"><a class="logo" href="/">Play<span>Time</span></a>
<div class="acct" id="acct"></div></div>
<nav class="tabs" aria-label="Sections">{tabs}</nav></div></header>
<div class="w{' wide' if wide else ''}">{body}
<footer class="foot"><nav class="small"><a href="/">All games</a><a href="/trending.html">Trending</a>
<a href="/events.html">Events</a><a href="/compare.html">Compare</a><a href="/plan.html">Plan a session</a>
<a href="/about.html">About</a><a href="/privacy.html">Privacy Policy</a><a href="/terms.html">Terms</a></nav>
<p class="mut small">Not affiliated with or endorsed by Roblox Corporation. Based on public player counts, so it
shows when people play, not whether a game is good or safe.</p></footer>
</div>{tail}{HIT}</body></html>"""


# ---------------------------------------------------------------- small helpers

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "game"


def short(n):
    """9400 -> '9.4K', so big numbers still fit on a phone."""
    n = n or 0
    for div, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            return f"{n / div:.1f}".rstrip("0").rstrip(".") + unit
    return str(int(n))


def ago(ts, now=None):
    """A point in time -> 'today', '3 days ago', '2 months ago'."""
    if not ts:
        return ""
    d = ((now or time.time()) - ts) / 86400
    if d < 0:
        return "soon"
    if d < 1:
        return "today"
    if d < 2:
        return "yesterday"
    if d < 31:
        return f"{int(d)} days ago"
    if d < 365:
        m = max(1, int(d / 30.4))
        return f"{m} month{'s' if m > 1 else ''} ago"
    y = d / 365
    return f"{y:.0f} year{'s' if y >= 2 else ''} ago"


def when(ts):
    """A point in time -> 'Sat 14 Nov' (plus the year if it is not this year)."""
    d = datetime.fromtimestamp(ts, timezone.utc)
    s = f"{d:%a} {d.day} {d:%b}"
    if d.year != datetime.now(timezone.utc).year:
        s += f" {d.year}"
    return s


def thumb(name, url, alt="", cls="thumb"):
    if url:
        return (f'<img class="{cls}" src="{html.escape(url)}" alt="{html.escape(alt)}" '
                f'width="256" height="256" loading="lazy" decoding="async">')
    letter = next((c for c in name if c.isalnum()), "?").upper()
    return f'<div class="{cls} ph" aria-hidden="true">{html.escape(letter)}</div>'


PERSON = ('<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="5" r="3"/>'
          '<path d="M2 15c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5z"/></svg>')


def trend_short(t):
    if t is None:
        return ""
    if t >= 5:
        return f'<span class="up">&#9650; {t:.0f}%</span>'
    if t <= -5:
        return f'<span class="down">&#9660; {-t:.0f}%</span>'
    return ""


def trend_html(t):
    if t is None:
        return '<span class="mut">Not enough history yet</span>'
    if t >= 5:
        return f'<span class="up">Growing ({t:+.0f}%)</span>'
    if t <= -5:
        return f'<span class="down">Shrinking ({t:+.0f}%)</span>'
    return '<span class="mut">Steady</span>'


def tile(c, i=0):
    return (f'<li style="--i:{min(i, 14)}" data-n="{html.escape(c["name"].lower())}" data-s="{c["slug"]}">'
            f'<a class="tile" href="/game/{c["slug"]}.html">{thumb(c["name"], c["icon"], c["name"] + " icon")}'
            f'<span class="tname">{html.escape(c["name"])}</span>'
            f'<span class="tmeta"><span title="Typical players over the last 7 days">{PERSON} {short(c["avg"])}</span>'
            f'{trend_short(c["trend"])}</span></a></li>')


def grid(cards, gid=""):
    idattr = f' id="{gid}"' if gid else ""
    return f'<ul class="grid"{idattr}>{"".join(tile(c, i) for i, c in enumerate(cards))}</ul>'


def jsdata(obj):
    """JSON that is safe to drop inside a <script> tag."""
    return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")


def contact_html():
    if not CONTACT:
        return ""
    e = html.escape(CONTACT)
    return f'<h2>Contact</h2><p>Questions or problems? Email <a href="mailto:{e}">{e}</a>.</p>'


# ---------------------------------------------------------------- the maths

def analyze(rows):
    """Turns a game's player counts into everything the pages need.

    rows is [(time, players)] oldest first. Returns a dictionary with:
      week    7x24 table of typical players (Monday first, UTC hours)
      daily   [(midnight, typical players)] one entry per day, oldest first
      trend   % change, last 7 days against the 7 days before
      month   % change, last 14 days against the 14 days before
      avg7    typical players over the last 7 days
      peak    the most players we have ever seen
      spikes  days that were much busier than usual
    """
    sums = [[0] * 24 for _ in range(7)]
    cnt = [[0] * 24 for _ in range(7)]
    by_day = {}
    now = rows[-1][0]
    buckets = {7: [], 14: [], 28: []}
    for ts, p in rows:
        d = datetime.fromtimestamp(ts, timezone.utc)
        sums[d.weekday()][d.hour] += p
        cnt[d.weekday()][d.hour] += 1
        by_day.setdefault(ts // 86400, []).append(p)
        age = (now - ts) / 86400
        for span in buckets:
            if age <= span:
                buckets[span].append((age, p))

    week = [[round(sums[d][h] / cnt[d][h]) if cnt[d][h] else None for h in range(24)] for d in range(7)]
    daily = [(day * 86400, round(sum(v) / len(v))) for day, v in sorted(by_day.items())]

    def mean(vals):
        return sum(vals) / len(vals) if vals else None

    def change(span):
        """% difference between the last `span` days and the `span` days before them."""
        pts = buckets[span * 2] if span * 2 in buckets else []
        a = mean([p for age, p in pts if age <= span])
        b = mean([p for age, p in pts if span < age <= span * 2])
        return round((a - b) / b * 100, 1) if a and b else None

    return {"week": week, "daily": daily,
            "trend": change(7), "month": change(14),
            "avg7": round(mean([p for age, p in buckets[7]]) or 0),
            "peak": max(p for _, p in rows),
            "spikes": find_spikes(daily),
            "days": round((rows[-1][0] - rows[0][0]) / 86400, 1)}


def find_spikes(daily):
    """Days that were much busier than the week before them: [(day, how many times busier)].

    These are almost always an update, a seasonal event, or a popular video about the game.
    """
    out = []
    for i, (day, v) in enumerate(daily):
        before = [x for _, x in daily[max(0, i - 7):i]]
        if len(before) < 4:
            continue
        normal = statistics.median(before)
        if normal > 0 and v / normal >= SPIKE:
            out.append((day, round(v / normal, 2)))
    # If a spike lasted several days, keep only the biggest day of that run.
    best = []
    for day, ratio in out:
        if best and day - best[-1][0] <= 2 * 86400:
            if ratio > best[-1][1]:
                best[-1] = (day, ratio)
        else:
            best.append((day, ratio))
    return best


def verdict(a):
    """Answers "is this game dead?" in plain English. Returns (label, colour, sentence)."""
    t, m, days = a["trend"], a["month"], a["days"]
    if days < 10 or t is None:
        return ("Too new to say", "var(--l3)",
                "We have not been watching this game long enough to say which way it is going. "
                "Check back in a week or two.")
    # The last two weeks matter most; the longer view stops one odd week fooling us.
    score = t if m is None else t * 0.65 + m * 0.35
    players = short(a["avg7"])
    if score >= 15:
        return ("Growing", "var(--l2)",
                f"No, the opposite. More people are playing than a week ago, with about {players} "
                f"in the game at a typical moment.")
    if score >= 5:
        return ("Slowly growing", "var(--l2)",
                f"No. It is picking up a little, with about {players} players at a typical moment.")
    if score > -5:
        return ("Steady", "var(--l1)",
                f"No. It has about the same number of players as last week: roughly {players} "
                f"at a typical moment.")
    if score > -20:
        return ("Getting quieter", "var(--l4)",
                f"Not dead, but it is sliding. Fewer people are playing than a week ago, though about "
                f"{players} are still in the game at a typical moment.")
    return ("Losing players fast", "var(--l5)",
            f"It is dropping quickly: a lot fewer people than a week ago. About {players} players "
            f"are still there at a typical moment, so it is quiet rather than empty.")


def sparkline(daily, spikes):
    """A small line chart of the last 45 days, with a dot on each spike day."""
    pts = daily[-45:]
    if len(pts) < 3:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    w, h = 600, 80
    x = lambda i: round(i / (len(pts) - 1) * w, 1)
    y = lambda v: round(h - 6 - (v - lo) / span * (h - 14), 1)
    line = " ".join(f"{x(i)},{y(v)}" for i, (_, v) in enumerate(pts))
    spike_days = {d for d, _ in spikes}
    dots = "".join(f'<circle cx="{x(i)}" cy="{y(v)}" r="4" fill="var(--acc2)"><title>'
                   f'{when(d)}: about {v:,} players, much busier than usual</title></circle>'
                   for i, (d, v) in enumerate(pts) if d in spike_days)
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" '
            f'aria-label="Typical players each day over the last {len(pts)} days">'
            f'<polygon points="0,{h} {line} {w},{h}" fill="var(--acc)" opacity=".13"/>'
            f'<polyline points="{line}" fill="none" stroke="var(--acc)" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round"/>{dots}</svg>'
            f'<p class="mut small">{when(pts[0][0])} to {when(pts[-1][0])}. '
            f'Each point is a day. Purple dots are days that were much busier than usual.</p>')


def levels_string(week):
    """Squashes a game's 7x24 table into 168 digits (0 = no data, 1 = very quiet, 5 = very busy).

    The homepage needs every game's shape to work out what is quiet *right now* in the
    visitor's own timezone, and 168 digits per game is small enough to put straight in the page.
    """
    vals = sorted(v for row in week for v in row if v is not None)
    if not vals:
        return "0" * 168
    q = [vals[int(p * (len(vals) - 1))] for p in (.2, .4, .6, .8)]
    out = []
    for row in week:
        for v in row:
            out.append("0" if v is None else str(1 + sum(1 for t in q if v > t)))
    return "".join(out)


# ---------------------------------------------------------------- page sections

def clean_desc(text):
    """Tidies a game's Roblox description: drops link-only lines and huge gaps."""
    keep = []
    for line in text.splitlines():
        line = line.strip()
        if re.fullmatch(r"(https?://\S+|www\.\S+|discord(\.gg)?[:/]?\s*\S*)", line, re.I):
            continue
        keep.append(line)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()
    return out


def about_game_html(name, meta):
    """The "what is this game?" card, using the description Roblox shows on the game's page."""
    if not meta:
        return ""
    desc = clean_desc(meta.get("description") or "")
    bits = []
    if meta.get("creator"):
        bits.append(f"Made by {html.escape(meta['creator'])}")
    if meta.get("created"):
        bits.append(f"first released {ago(meta['created'])}")
    if meta.get("visits"):
        bits.append(f"{short(meta['visits'])} total visits")
    if meta.get("max_players"):
        bits.append(f"up to {meta['max_players']} players per server")
    if not desc and not bits:
        return ""
    line = f'<p class="mut small">{". ".join(bits).capitalize()}.</p>' if bits else ""
    if len(desc) > 600:
        head, rest = desc[:600].rsplit(" ", 1)[0], desc[len(desc[:600].rsplit(" ", 1)[0]):]
        body = (f'<p class="desc">{html.escape(head)}&hellip;</p>'
                f'<details><summary>Read the rest</summary>'
                f'<p class="desc">{html.escape(rest.strip())}</p></details>')
    else:
        body = f'<p class="desc">{html.escape(desc)}</p>' if desc else ""
    return (f'<div class="card"><h2>What is {html.escape(name)}?</h2>{body}{line}'
            f'<p class="mut small">Description written by the game\'s own creators and shown on Roblox.</p></div>')


def event_item(e, now, cls=""):
    """One event in a list: title, when it runs, and what the creators said about it."""
    live = e["start"] <= now <= (e["end"] or e["start"] + 86400)
    soon = e["start"] > now
    klass = cls or ("live" if live else "soon" if soon else "")
    if live:
        label = f"Happening now &middot; ends {when(e['end'] or e['start'])}"
    elif soon:
        label = f"Starts {when(e['start'])}"
    else:
        label = f"{when(e['start'])} &middot; {ago(e['start'], now)}"
    desc = clean_desc(e.get("description") or "")
    if len(desc) > 420:
        desc = desc[:420].rsplit(" ", 1)[0] + "…"
    sub = f'<span class="d">{html.escape(e["subtitle"])}</span>' if e.get("subtitle") else ""
    body = f"<p>{html.escape(desc)}</p>" if desc else ""
    return (f'<li class="{klass}"><b>{html.escape(e["title"])}</b>{sub}'
            f'<span class="d">{label}</span>{body}</li>')


def calendar_html(name, events, now):
    """Upcoming and currently running events for one game."""
    if events is None:
        return ""
    soon = [e for e in events if (e["end"] or e["start"] + 86400) >= now]
    soon.sort(key=lambda e: e["start"])
    if not soon:
        return (f'<div class="card"><h2>Event calendar</h2><p class="none">{html.escape(name)} has no '
                f'events planned on Roblox right now. When the creators announce one it will show up here.</p></div>')
    items = "".join(event_item(e, now) for e in soon[:8])
    return (f'<div class="card"><h2>Event calendar</h2>'
            f'<p class="mut small">Events the creators have put on the Roblox calendar. Expect these hours to be busy.</p>'
            f'<ul class="evt">{items}</ul></div>')


def updates_html(name, events, meta, spikes, now):
    """Recent updates and changes: finished events (creators use them as a changelog) plus spikes.

    Anything still running or still to come belongs on the calendar instead, so the
    two sections never show the same event twice.
    """
    past = [e for e in (events or []) if (e["end"] or e["start"] + 86400) < now]
    past.sort(key=lambda e: -e["start"])
    parts = []
    if meta and meta.get("updated"):
        parts.append(f'<p>The creators last changed something in the game <b>{ago(meta["updated"], now)}</b> '
                     f'({when(meta["updated"])}).</p>')
    if past:
        parts.append(f'<ul class="evt">{"".join(event_item(e, now, cls="") for e in past[:6])}</ul>')
        if len(past) > 6:
            rest = "".join(f'<tr><td>{html.escape(e["title"])}</td><td>{when(e["start"])}</td></tr>'
                           for e in past[6:30])
            parts.append(f'<details><summary>Older updates and events</summary><div class="wrap">'
                         f'<table class="tbl"><tr><th>Update or event</th><th>When</th></tr>{rest}'
                         f'</table></div></details>')
    elif events is not None:
        parts.append('<p class="none">The creators have not posted any updates to the Roblox event '
                     'calendar, so we only know the date above.</p>')
    if spikes:
        rows = []
        for day, ratio in sorted(spikes, key=lambda s: -s[0])[:6]:
            near = [e for e in (events or []) if abs(e["start"] - day) <= 36 * 3600]
            why = (f'lines up with &ldquo;{html.escape(near[0]["title"])}&rdquo;' if near
                   else "no event was listed, so it was probably an update or a popular video")
            rows.append(f'<tr><td>{when(day)}</td><td>{ratio:.1f}&times; busier &ndash; {why}</td></tr>')
        parts.append(f'<h3>Days the player count jumped</h3><p class="mut small">We flag any day that was '
                     f'at least {SPIKE:g} times busier than the week before it.</p><div class="wrap">'
                     f'<table class="tbl"><tr><th>Day</th><th>What we think happened</th></tr>'
                     f'{"".join(rows)}</table></div>')
    if not parts:
        return ""
    return f'<div class="card"><h2>Recent updates and changes</h2>{"".join(parts)}</div>'


def parents_html(passes):
    """What the game sells, for parents. Hidden if Roblox did not answer."""
    if passes is None:
        return ""
    h = '<div class="card"><h2>For parents: what costs money</h2>'
    if not passes:
        h += "<p>This game sells <b>no game passes</b> right now.</p>"
    else:
        ps = sorted(passes, key=lambda p: p[1])
        total = sum(p for _, p in ps)
        n = len(ps)
        h += (f"<p>This game sells <b>{n} game pass{'es' if n != 1 else ''}</b>, from "
              f"<b>{ps[0][1]:,} to {ps[-1][1]:,} Robux</b>. Buying every one would cost "
              f"<b>{total:,} Robux</b> (roughly ${total * ROBUX_USD:,.0f} USD).</p>")
        rows = "".join(f"<tr><td>{html.escape(nm)}</td><td>{p:,}</td></tr>" for nm, p in reversed(ps))
        h += (f'<details><summary>See every game pass</summary><div class="wrap"><table class="tbl">'
              f'<tr><th>Game pass</th><th>Robux</th></tr>{rows}</table></div></details>')
    h += ('<p class="mut small">Games can also sell one-time items inside the game, which are not listed here. '
          'Roblox Parental Controls let you set a monthly spending limit and get alerts about purchases.</p></div>')
    return h


# ---------------------------------------------------------------- browser code

# Saved games live only in this browser's localStorage and are never sent anywhere.
# Saved games. Signed out, the list lives only in this browser. Signed in with
# Roblox, it also follows the person to their other devices.
FAVJS = """var PT={name:null,available:false,favs:null,cbs:[]};
function getFavs(){if(PT.favs)return PT.favs;
try{return JSON.parse(localStorage.getItem('pt_favs'))||[]}catch(e){return[]}}
function setFavs(f){PT.favs=f;try{localStorage.setItem('pt_favs',JSON.stringify(f))}catch(e){}
if(PT.name)fetch('/api/favs',{method:'PUT',headers:{'content-type':'application/json'},
body:JSON.stringify({favs:f})}).catch(function(){})}
PT.ready=function(fn){PT.cbs.push(fn);fn()};
function ptEsc(s){return String(s).replace(/[&<>"]/g,function(c){
return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function ptPaint(){var el=document.getElementById('acct');
if(el){el.innerHTML=!PT.available?'':PT.name
?'<span class="who">'+ptEsc(PT.name)+'</span><form method="POST" action="/auth/logout">'
+'<button class="linkish" type="submit">Sign out</button></form>'
:'<a class="signin" href="/auth/login">Sign in with Roblox</a>'}
PT.cbs.forEach(function(fn){try{fn()}catch(e){}})}
fetch('/api/me').then(function(r){return r.json()}).then(function(d){
PT.available=!!d.available;PT.name=d.signedIn?d.name:null;
if(d.signedIn){var mine=getFavs(),all=(d.favs||[]).slice();
mine.forEach(function(s){if(all.indexOf(s)<0)all.push(s)});
PT.favs=all;try{localStorage.setItem('pt_favs',JSON.stringify(all))}catch(e){}
if(all.length!==(d.favs||[]).length)setFavs(all)}
ptPaint()}).catch(function(){});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ptPaint);"""

FAV_GAME = """
(function(){var b=document.getElementById('fav'),k=b.dataset.s;
function draw(){var on=getFavs().indexOf(k)>-1;b.setAttribute('aria-pressed',on);
b.innerHTML=on?'&#9733; Saved':'&#9734; Save'}
b.onclick=function(){var f=getFavs();f=f.indexOf(k)>-1?f.filter(function(x){return x!==k}):f.concat(k);
setFavs(f);draw()};PT.ready(draw)})();"""

# Shared by every page that draws a week of player counts.
SHARED_JS = """var DAY=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
var W=['no data','very quiet','quiet','average','busy','very busy'];
function $(id){return document.getElementById(id)}
function fmt(h){return (h%12||12)+(h<12?' AM':' PM')}
/* Game names and picture addresses come from Roblox, so make them safe before they
   go anywhere near innerHTML. A name with a quote or an angle bracket in it would
   otherwise break the page. */
var ESCMAP={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return ESCMAP[c]})}
/* How many whole hours ahead of UTC the visitor is. Rounded, because our buckets are
   whole hours and places like India are half an hour off. Every page must use this one
   function, or the homepage and the game pages would disagree by an hour. */
function tzOff(){return Math.round(-new Date().getTimezoneOffset()/60)}
/* Our numbers are in UTC; shift them into whatever timezone the visitor is in. */
function toLocal(M){var off=tzOff(),L=[[],[],[],[],[],[],[]];
for(var d=0;d<7;d++)for(var h=0;h<24;h++)L[d][h]=null;
for(var d=0;d<7;d++)for(var h=0;h<24;h++){var t=h+off,dd=d;
while(t<0){t+=24;dd=(dd+6)%7}while(t>=24){t-=24;dd=(dd+1)%7}L[dd][Math.floor(t)]=M[d][h]}
return L}
/* Splits the numbers into five bands so "busy" means busy *for this game*. */
function bands(L){var v=[];for(var d=0;d<7;d++)for(var h=0;h<24;h++)if(L[d][h]!=null)v.push(L[d][h]);
v.sort(function(a,b){return a-b});
var q=[.2,.4,.6,.8].map(function(p){return v[Math.floor(p*(v.length-1))]});
return {max:v[v.length-1]||1,level:function(x){if(x==null)return 0;var n=1;
for(var i=0;i<4;i++)if(x>q[i])n++;return n}}}
function nowDay(){return (new Date().getDay()+6)%7}
/* The next good time to play: looks at the next 48 hours in the visitor's own timezone. */
function nextBlock(L,mode){var now=new Date(),list=[];
for(var i=0;i<48;i++){var t=new Date(now.getTime()+(i+1)*3600000);
var v=L[(t.getDay()+6)%7][t.getHours()];if(v!=null)list.push({i:i+1,v:v,t:t})}
if(!list.length)return null;
var pick=list[0];for(var j=1;j<list.length;j++){
if(mode==='quiet'?list[j].v<pick.v:list[j].v>pick.v)pick=list[j]}
var at=list.indexOf(pick),len=1;
for(var k=at+1;k<list.length;k++){var ok=mode==='quiet'?list[k].v<=pick.v*1.25:list[k].v>=pick.v*.8;
if(!ok)break;len++}
pick.len=len;return pick}
function countdown(ms){if(ms<=0)return 'right now';
var m=Math.round(ms/60000),h=Math.floor(m/60);m=m%60;
if(h>=24){var d=Math.floor(h/24);return 'in '+d+' day'+(d>1?'s':'')+' '+(h%24)+'h'}
if(h)return 'in '+h+'h '+m+'m';return 'in '+m+' min'}"""

GAME_JS = """var M=__DATA__,L=toLocal(M),B=bands(L),nd=nowDay(),nh=new Date().getHours();
var best=null,worst=null,dayq=null;
for(var d=0;d<7;d++)for(var h=0;h<24;h++){var v=L[d][h];if(v==null)continue;
if(!best||v<best[2])best=[d,h,v];if(!worst||v>worst[2])worst=[d,h,v];
if(h>=8&&h<=21&&(!dayq||v<dayq[2]))dayq=[d,h,v]}
var nl=B.level(L[nd][nh]);
$('now').innerHTML=nl?'Right now it is usually <b>'+W[nl]+'</b>.':'';
$('best').innerHTML='Busiest: <b>'+DAY[worst[0]]+' around '+fmt(worst[1])+'</b>.';
$('quiet').innerHTML='Quietest: <b>'+DAY[best[0]]+' around '+fmt(best[1])+'</b>'+
(dayq&&(dayq[0]+':'+dayq[1])!=(best[0]+':'+best[1])?' (or <b>'+DAY[dayq[0]]+' around '+fmt(dayq[1])+
'</b> if you play during the day).':'.');

/* Plan my session */
var mode='quiet';
function plan(){
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.setAttribute('aria-pressed',b.dataset.m===mode)});
var p=nextBlock(L,mode);
if(!p){$('plantxt').textContent='Not enough player counts yet to plan ahead.';return}
var top=new Date(p.t);top.setMinutes(0,0,0);
$('cd').textContent=countdown(top-new Date());
$('plantxt').innerHTML='The next '+(mode==='quiet'?'quiet':'busy')+' stretch is <b>'+DAY[(top.getDay()+6)%7]+
' at '+fmt(top.getHours())+'</b> your time, when it is usually <b>'+W[B.level(p.v)]+
'</b> with about '+p.v.toLocaleString()+' players. It stays that way for about <b>'+p.len+
' hour'+(p.len>1?'s':'')+'</b>.';
$('cdw').hidden=false}
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.onclick=function(){mode=b.dataset.m;plan()}});
plan();setInterval(plan,30000);

/* One day at a time */
function show(d){
Array.prototype.forEach.call($('days').querySelectorAll('button'),function(b,i){
b.setAttribute('aria-pressed',i==d)});
var lo=null,hi=null,out='';
for(var h=0;h<24;h++){var v=L[d][h];if(v==null)continue;
if(!lo||v<lo[1])lo=[h,v];if(!hi||v>hi[1])hi=[h,v]}
for(var h=0;h<24;h++){var v=L[d][h];
out+='<div class="bar" style="--i:'+h+';height:'+Math.max(3,(v||0)/B.max*100)+
'%;background:var(--l'+(B.level(v)||1)+')" title="'+fmt(h)+': about '+(v||0).toLocaleString()+' players"></div>'}
$('bars').innerHTML=out;
$('dtxt').textContent=lo?'On '+DAY[d]+' it is quietest around '+fmt(lo[0])+' and busiest around '+fmt(hi[0])+
'. Hover or tap a bar for numbers.':'No player counts for this day yet.'}
DAY.forEach(function(n,i){var b=document.createElement('button');b.textContent=n.slice(0,3);
b.setAttribute('aria-label',n);b.onclick=function(){show(i)};$('days').appendChild(b)});

/* The whole week */
var g='<div></div>';['12 AM','6 AM','12 PM','6 PM'].forEach(function(t){
g+='<span style="grid-column:span 6">'+t+'</span>'});
for(var d=0;d<7;d++){g+='<div>'+DAY[d].slice(0,3)+'</div>';
for(var h=0;h<24;h++){var v=L[d][h];
g+='<div class="c'+(d==nd&&h==nh?' now':'')+'" title="'+DAY[d]+' '+fmt(h)+': about '+
(v||0).toLocaleString()+' players" style="background:'+(v==null?'transparent':'var(--l'+B.level(v)+')')+'"></div>'}}
$('hm').innerHTML=g;show(nd);"""

HOME_JS = """var G=__GAMES__;
/* Each game carries 168 digits: one busy-ness level per hour of the week, in UTC.
   Work out which of those digits is "now" by going from local time back to UTC. */
var off=tzOff();
var now=new Date(),nd=(now.getDay()+6)%7,nh=now.getHours();
var ut=nh-off,ud=nd;
while(ut<0){ut+=24;ud=(ud+6)%7}while(ut>=24){ut-=24;ud=(ud+1)%7}
var cell=ud*24+ut;
G.forEach(function(g){g.lv=+g.l.charAt(cell)});

/* "What are you looking for?" sorts the list and labels every game. */
var all=$('all'),original=Array.prototype.slice.call(all.children),want='';
function apply(w){
want=(want===w?'':w);
Array.prototype.forEach.call(document.querySelectorAll('#ask button'),function(b){
b.setAttribute('aria-pressed',b.dataset.w===want)});
var order=original.slice();
if(want){var by={};G.forEach(function(g){by[g.s]=g});
order.sort(function(x,y){var a=by[x.dataset.s],b=by[y.dataset.s];
if(!a||!b||!a.lv||!b.lv)return (b&&b.lv?1:0)-(a&&a.lv?1:0);
return want==='quiet'?a.lv-b.lv||b.a-a.a:b.lv-a.lv||b.a-a.a})}
order.forEach(function(li,i){li.style.setProperty('--i',Math.min(i,14));all.appendChild(li)});
Array.prototype.forEach.call(all.children,function(li){
var g=null;G.forEach(function(x){if(x.s===li.dataset.s)g=x});
var old=li.querySelector('.rnow');if(old)old.remove();
if(want&&g&&g.lv){var s=document.createElement('span');s.className='rnow';
s.style.cssText='font-weight:700;color:var(--ink)';s.textContent=W[g.lv]+' now';
li.querySelector('.tmeta').appendChild(s)}});
$('asktxt').textContent=want==='quiet'?
'Quietest first, for right now in your timezone. Good for claiming event items and avoiding queues.':
want==='busy'?'Busiest first, for right now in your timezone. Good for trading, full servers and events.':
'Showing the most popular games first.'}
Array.prototype.forEach.call(document.querySelectorAll('#ask button'),function(b){
b.onclick=function(){apply(b.dataset.w)}});

/* Search */
var s=$('s');s.oninput=function(){var t=s.value.toLowerCase();
Array.prototype.forEach.call(document.querySelectorAll('.grid li'),function(li){
li.hidden=li.dataset.n.indexOf(t)<0})};

/* Saved games, pinned to the top. Redrawn if signing in brings more in. */
PT.ready(function(){var fg=$('favgrid');if(!fg)return;fg.innerHTML='';
getFavs().forEach(function(k){
var li=null;Array.prototype.forEach.call(all.children,function(x){if(x.dataset.s===k)li=x});
if(li)fg.appendChild(li.cloneNode(true))});
$('favs').hidden=!fg.children.length});"""

COMPARE_JS = """var A=null,B=null,day=nowDay(),DATA=null;
function opts(sel,pick){DATA.games.forEach(function(g){var o=document.createElement('option');
o.value=g.s;o.textContent=g.n;sel.appendChild(o)});sel.value=pick}
function find(s){var r=null;DATA.games.forEach(function(g){if(g.s===s)r=g});return r}
function draw(){
var a=find($('ga').value),b=find($('gb').value);
if(!a||!b)return;
var La=toLocal(a.m),Lb=toLocal(b.m),Ba=bands(La),Bb=bands(Lb);
Array.prototype.forEach.call($('days').querySelectorAll('button'),function(x,i){
x.setAttribute('aria-pressed',i==day)});
var out='';
for(var h=0;h<24;h++){
var va=La[day][h],vb=Lb[day][h];
out+='<div style="display:flex;gap:1px;align-items:flex-end;align-self:stretch">'+
'<div class="bar" style="--i:'+h+';flex:1;height:'+Math.max(3,(va||0)/Ba.max*100)+'%;background:var(--acc)" '+
'title="'+esc(a.n)+' '+fmt(h)+': about '+(va||0).toLocaleString()+' players"></div>'+
'<div class="bar b2" style="--i:'+h+';flex:1;height:'+Math.max(3,(vb||0)/Bb.max*100)+'%;background:var(--acc2)" '+
'title="'+esc(b.n)+' '+fmt(h)+': about '+(vb||0).toLocaleString()+' players"></div></div>'}
$('bars').innerHTML=out;
/* Each game is measured against its own week, so a small game can still be "busy". */
var qa=0,qb=0,best=null;
for(var h=0;h<24;h++){var la=Ba.level(La[day][h]),lb=Bb.level(Lb[day][h]);
if(la&&lb){if(la<lb)qa++;else if(lb<la)qb++;
if(!best||la+lb<best[1])best=[h,la+lb]}}
var verdict=qa===qb?'They are about the same on '+DAY[day]+'.':
'<b>'+esc(qa>qb?a.n:b.n)+'</b> is the quieter one on '+DAY[day]+', for '+Math.max(qa,qb)+' of the 24 hours.';
$('verdict').innerHTML=verdict+(best?' Both are at their calmest around <b>'+fmt(best[0])+'</b>.':'')+
'<br><span class="mut small">Bar heights compare each game against its own normal week, '+
'so the taller bar means "busy for that game", not "more players".</span>';
$('alab').textContent=a.n;$('blab').textContent=b.n;
$('nums').innerHTML='<div><span class="mut small">'+esc(a.n)+'</span><b>'+a.a.toLocaleString()+
'</b><span class="mut small">typical players</span></div><div><span class="mut small">'+esc(b.n)+
'</span><b>'+b.a.toLocaleString()+'</b><span class="mut small">typical players</span></div>'}
fetch('/data.json').then(function(r){return r.json()}).then(function(d){
DATA=d;if(DATA.games.length<2){$('load').innerHTML='<p class="none">We need at least two games with '+
'enough player counts before you can compare them.</p>';return}
var p=new URLSearchParams(location.search);
opts($('ga'),p.get('a')||DATA.games[0].s);opts($('gb'),p.get('b')||DATA.games[1].s);
if($('ga').value===$('gb').value)$('gb').selectedIndex=($('ga').selectedIndex+1)%DATA.games.length;
DAY.forEach(function(n,i){var b=document.createElement('button');b.textContent=n.slice(0,3);
b.setAttribute('aria-label',n);b.onclick=function(){day=i;draw()};$('days').appendChild(b)});
$('ga').onchange=$('gb').onchange=draw;$('load').hidden=true;$('cmp').hidden=false;draw()})
.catch(function(){$('load').innerHTML='<p class="none">Could not load the game data. Please reload the page.</p>'});"""

PLAN_JS = """var DATA=null,mode='quiet';
function find(s){var r=null;DATA.games.forEach(function(g){if(g.s===s)r=g});return r}
function draw(){
var g=find($('g').value);if(!g)return;
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.setAttribute('aria-pressed',b.dataset.m===mode)});
var L=toLocal(g.m),B=bands(L),p=nextBlock(L,mode);
if(!p){$('out').innerHTML='<p class="none">Not enough player counts for this game yet.</p>';return}
var top=new Date(p.t);top.setMinutes(0,0,0);
var rows='';for(var i=0;i<12;i++){var t=new Date(new Date().getTime()+i*3600000);
var v=L[(t.getDay()+6)%7][t.getHours()],lv=B.level(v);
rows+='<tr><td><span class="key" style="background:var(--l'+(lv||1)+')"></span>'+
(i?fmt(t.getHours()):'now')+'</td><td>'+(lv?W[lv]:'no data')+'</td></tr>'}
$('out').innerHTML='<span class="mut small">Next '+(mode==='quiet'?'quiet':'busy')+' stretch for '+esc(g.n)+
'</span><span class="cd">'+countdown(top-new Date())+'</span><p>'+DAY[(top.getDay()+6)%7]+' at <b>'+
fmt(top.getHours())+'</b> your time &ndash; usually <b>'+W[B.level(p.v)]+'</b> with about '+
p.v.toLocaleString()+' players, lasting about <b>'+p.len+' hour'+(p.len>1?'s':'')+'</b>.</p>'+
'<p><a class="btn" href="/game/'+esc(g.s)+'.html">See '+esc(g.n)+'\\u2019s whole week</a></p>'+
'<h3>The next 12 hours</h3><div class="wrap"><table class="tbl"><tr><th>Your time</th>'+
'<th>How busy</th></tr>'+rows+'</table></div>'}
fetch('/data.json').then(function(r){return r.json()}).then(function(d){
DATA=d;if(!DATA.games.length){$('load').innerHTML='<p class="none">No games have enough player counts yet.</p>';return}
DATA.games.forEach(function(g){var o=document.createElement('option');o.value=g.s;o.textContent=g.n;
$('g').appendChild(o)});
var p=new URLSearchParams(location.search);if(p.get('g')&&find(p.get('g')))$('g').value=p.get('g');
if(p.get('want')==='busy')mode='busy';
$('g').onchange=draw;
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.onclick=function(){mode=b.dataset.m;draw()}});
$('load').hidden=true;$('plan').hidden=false;draw();setInterval(draw,30000)})
.catch(function(){$('load').innerHTML='<p class="none">Could not load the game data. Please reload the page.</p>'});"""


# ---------------------------------------------------------------- page bodies

GAME = """<div class="ghead rise">__ICON__<div><h1>When is __NAME__ busiest?</h1>
<p class="mut">Times are shown in your timezone. Based on __N__ player counts.__CAT__</p>
<div class="actions">__PLAY__<button class="fav" id="fav" data-s="__SLUG__" aria-pressed="false">&#9734; Save</button>
<a class="fav" href="/compare.html?a=__SLUG__">Compare</a></div></div></div>
<div class="card ans rise2"><h2>The short answer</h2><p id="now"></p><p id="best"></p><p id="quiet"></p></div>
<div class="card rise3"><h2>Plan my session</h2>
<p class="mut small">What do you want?</p>
<div class="days" id="planbtns"><button data-m="quiet" aria-pressed="true">Quiet</button>
<button data-m="busy" aria-pressed="false">Busy</button></div>
<div id="cdw" hidden><span class="cd" id="cd"></span></div><p id="plantxt"></p></div>
<div class="card"><h2>Pick a day</h2><div class="days" id="days"></div>
<p id="dtxt" class="mut small"></p><div class="bars" id="bars"></div>
<div class="axis"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span></div></div>
<div class="card"><h2>The whole week</h2><div class="wrap"><div class="hm" id="hm"></div></div>
<div class="legend">Quiet <i style="background:var(--l1)"></i><i style="background:var(--l2)"></i>
<i style="background:var(--l3)"></i><i style="background:var(--l4)"></i><i style="background:var(--l5)"></i> Busy</div>
<p class="mut small">The outlined square is right now.</p></div>
<div class="card stats"><div><span class="mut small">Typical players (last 7 days)</span><b>__AVG__</b></div>
<div><span class="mut small">Highest seen</span><b>__PEAK__</b></div>
<div><span class="mut small">Compared to last week</span><b>__TREND__</b></div></div>
<div class="card"><h2>Is __NAME__ dead?</h2><div class="verdict">
<span class="vbadge" style="background:__VCOL__">__VLABEL__</span><p style="margin:0;flex:1 1 240px">__VTEXT__</p></div>
__SPARK__</div>
__UPDATES__
__CALENDAR__
__ABOUT__
__PARENTS__
<p><a href="/">&larr; All games</a> &middot; <a href="/plan.html?g=__SLUG__">Plan a session</a></p>
<script>__SHARED__</script><script>__JS__</script><script>__FAVJS__</script>"""


def about_body():
    return f"""<div class="doc"><h1>About {html.escape(SITE)}</h1>
<p>{html.escape(SITE)} shows when popular Roblox games are busiest and quietest, hour by hour, so you can pick a good time to play.</p>
<h2>How it works</h2>
<p>About every 30 minutes, we check how many people are playing each game, using the player counts Roblox shows publicly.
Over days and weeks, those counts add up to a picture of each game's week: which hours are packed and which are quiet.
Times are shown in your own timezone.</p>
<h2>Why use it?</h2>
<ul><li><b>Quiet hours</b> are good for shorter queues, less lag, claiming event items, and learning a game without a crowd.</li>
<li><b>Busy hours</b> are good for full servers, trading, and events.</li></ul>
<h2>Where the extra details come from</h2>
<ul><li><b>Event calendars and updates</b> come from the events the game's own creators post on Roblox.</li>
<li><b>Descriptions, pictures and game passes</b> are the public ones Roblox shows on each game's page.</li>
<li><b>"Days the player count jumped"</b> is worked out by us: any day at least {SPIKE:g} times busier than the
week before it usually means an update, a seasonal event, or a popular video about the game.</li></ul>
<h2>What it does not tell you</h2>
<p>Player counts show when people play. They do not say whether a game is good, fair, or safe for children.
Parents should still check a game themselves and use Roblox's parental controls.</p>
<h2>The fine print</h2>
<p>{html.escape(SITE)} is an independent fan project. It is not affiliated with, endorsed by, or sponsored by Roblox Corporation.
Game names belong to their creators. Numbers are averages and can be off, especially for games we started tracking recently.</p>
<p>We never ask for your Roblox password. You can sign in with Roblox if you want your saved games on more than
one device, but everything works without it. See our <a href="/privacy.html">Privacy Policy</a>.</p>
{contact_html()}</div>"""


def privacy_body():
    if ADS:
        ads = """<h2>Ads</h2>
<p>This site shows ads from Google AdSense to pay for running it. Google and its partners may use cookies or similar
technology to show ads and to measure them. You can learn how Google uses this information at
<a href="https://policies.google.com/technologies/partner-sites">policies.google.com/technologies/partner-sites</a>
and turn off personalized ads at <a href="https://adssettings.google.com">adssettings.google.com</a>.
We do not control these cookies, and we never pass Google any personal information about you.</p>"""
    else:
        ads = """<h2>Ads</h2>
<p>This site does not show ads right now. If we add ads later (for example from Google AdSense), we will update this
page first to explain what the ad provider collects and how to turn off personalized ads.</p>"""
    return f"""<div class="doc"><h1>Privacy Policy</h1>
<p class="mut">Last updated: {POLICY_DATE}</p>
<p>The short version: you can use all of {html.escape(SITE)} without telling us anything about yourself.
Signing in is optional and only saves which games you picked.</p>
<h2>What we never collect</h2>
<ul><li>We never ask for your Roblox password. Signing in happens on Roblox's own website, and we never see it.</li>
<li>No forms, comments, or chat.</li>
<li>No emails, home addresses, or locations.</li></ul>
<h2>If you sign in with Roblox</h2>
<p>Signing in is optional. The whole site works without it. If you choose to sign in, Roblox tells us two things:
your Roblox user ID and your display name. We store those, plus the list of games you saved, so your saved games
appear on your phone as well as your computer. That is everything we keep.</p>
<p>We do not receive or store your password, your email, your age, your friends, or anything about what you play
on Roblox. You can press <b>Delete my data</b> on this page at any time and everything we hold about you is erased
straight away. Signing out just ends the session and leaves your saved games in place.</p>
<h2>Children</h2>
<p>Many visitors are kids, so the site is built to work without accounts. Roblox does not allow accounts under 13
to sign in to outside sites like this one, so everyone who signs in here is 13 or older. We do not knowingly
collect personal information from children under 13. If you believe a child has, contact us and we will delete it.</p>
<h2>Things that stay on your device</h2>
<p>To show times in your timezone, the page reads your device's clock. That happens only in your browser and is never sent to us.</p>
<p>If you tap <b>Save</b> on a game, the list of games you saved is kept in your browser's storage on your device.
It is never sent to us. Clearing your browser data removes it.</p>
<h2>Counting visits</h2>
<p>We count how many times each page is opened, so we know which pages people find useful. We count the page
address and the date, and nothing else: no cookies, no names, no accounts, and nothing that identifies you or
your device. We cannot tell one visitor from another.</p>
<h2>Our hosting provider</h2>
<p>The site is hosted by Cloudflare. Like any website host, Cloudflare automatically handles basic technical information
(such as IP addresses and browser type) to deliver pages and protect the site from attacks. See
<a href="https://www.cloudflare.com/privacypolicy/">Cloudflare's privacy policy</a>.</p>
{ads}
<h2>Game data</h2>
<p>The player counts on this site are public numbers about games, not about people. We do not track individual players.</p>
<h2>Changes</h2>
<p>If this policy changes, we will update this page and the date at the top.</p>
<h2>Delete my data</h2>
<p>If you signed in with Roblox, this erases your saved games and your record on this site. It cannot be undone,
and it does not affect your Roblox account in any way.</p>
<p><button class="fav" id="delme">Delete my data</button> <span id="delmsg" class="mut small"></span></p>
<script>(function(){{var b=document.getElementById('delme'),m=document.getElementById('delmsg'),armed=false;
b.onclick=function(){{
if(!PT.name){{m.textContent='You are not signed in, so we hold nothing to delete.';return}}
if(!armed){{armed=true;b.textContent='Tap again to confirm';m.textContent='This cannot be undone.';return}}
b.disabled=true;fetch('/api/delete-me',{{method:'POST'}}).then(function(r){{
if(!r.ok)throw 0;try{{localStorage.removeItem('pt_favs')}}catch(e){{}}
b.textContent='Deleted';m.textContent='Everything we held about you has been erased.'}})
.catch(function(){{b.disabled=false;armed=false;b.textContent='Delete my data';
m.textContent='That did not work. Please try again.'}})}}}})();</script>
{contact_html()}</div>"""


def terms_body():
    return f"""<div class="doc"><h1>Terms of Service</h1>
<p class="mut">Last updated: {POLICY_DATE}</p>
<p>These are the rules for using {html.escape(SITE)}. They are meant to be read, so we have kept them short.</p>
<h2>What this site is</h2>
<p>{html.escape(SITE)} shows when Roblox games are usually busy or quiet, worked out from player counts that
Roblox publishes. It is a free, independent fan site. It is not affiliated with, endorsed by, or sponsored by
Roblox Corporation, and game names and pictures belong to their creators.</p>
<h2>Using the site</h2>
<p>You may use {html.escape(SITE)} for your own personal use, for free. Please do not try to break the site,
copy it wholesale, or use automated tools to hammer it with requests. We may change or remove any part of the
site at any time, including stopping it altogether.</p>
<h2>Signing in</h2>
<p>Signing in with Roblox is optional. You must be 13 or over, which Roblox enforces. Keep your Roblox account
secure, and remember we never ask for your Roblox password. You can sign out or delete your data whenever you
like from our <a href="/privacy.html">Privacy Policy</a> page. We may end access for anyone misusing the site.</p>
<h2>The numbers are estimates</h2>
<p>Everything here is an average worked out from samples, so it can be wrong, out of date, or missing. Busy and
quiet times change. Player counts say nothing about whether a game is good, fair, or suitable for a child.
Please treat the site as a helpful guess, not a promise.</p>
<h2>No warranty, and limits</h2>
<p>{html.escape(SITE)} is provided "as is", without warranties of any kind. We are not liable for any loss
arising from using the site or relying on its numbers.</p>
<h2>Changes to these terms</h2>
<p>If these terms change, we will update this page and the date at the top.</p>
{contact_html()}</div>"""


# ---------------------------------------------------------------- writing files

def write(path, text):
    os.makedirs(os.path.dirname(f"{OUT}/{path}") or OUT, exist_ok=True)
    with open(f"{OUT}/{path}", "w", encoding="utf-8") as f:
        f.write(text)


def write_stats(db, games, cards, waiting):
    """Saves the numbers the admin dashboard shows. Baked into the worker, not a public file."""
    if OUT != "docs":
        return                      # previews must not touch the real worker
    try:
        wanted = [x for x in open("games.txt").read().split() if x.strip().isdigit()]
    except OSError:
        wanted = []
    have = {str(g[0]) for g in games}
    stats = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "site": {"noindex": NOINDEX, "min_samples": MIN_SAMPLES, "domain": DOMAIN,
                 "contact": CONTACT, "ads": bool(ADS)},
        "totals": {"games_tracked": len(games), "pages_built": len(cards),
                   "samples": db.execute("SELECT COUNT(*) FROM samples").fetchone()[0],
                   "trend_ready": sum(1 for c in cards if c["days"] >= 14),
                   "with_events": sum(1 for c in cards if c["events"]),
                   "upcoming_events": sum(c["upcoming"] for c in cards)},
        "games": [{"name": c["name"], "genre": c["genre"], "samples": c["samples"], "days": c["days"],
                   "avg7": c["avg"], "trend": c["trend"], "verdict": c["verdict"],
                   "events": c["events"], "upcoming": c["upcoming"]} for c in cards],
        "waiting": waiting,
        "missing_ids": [i for i in wanted if i not in have],
    }
    os.makedirs("worker", exist_ok=True)
    with open("worker/stats.js", "w", encoding="utf-8") as f:
        f.write("// Written by build_site.py on every build. Do not edit by hand.\n"
                "export default " + json.dumps(stats, indent=1) + ";\n")


def list_page(key, title, h1, lede, cards, desc, extra=""):
    """One of the "across the top" pages: a heading and a grid of games."""
    body = (f'<div class="hero"><h1>{h1}</h1><p class="lede">{lede}</p></div>{extra}'
            + (grid(cards) if cards else
               '<p class="none">Nothing here yet. We need about two weeks of player counts for each game '
               'before this page fills in.</p>')
            + '<p><a href="/">&larr; All games</a></p>')
    write(f"{key}.html", page(title, body, desc, wide=True, nav=key))


def main():
    started = time.time()
    now = int(time.time())
    db = sqlite3.connect("data.db")
    os.makedirs(OUT + "/game", exist_ok=True)

    games = db.execute("SELECT universe_id,name,genre,place_id FROM games").fetchall()
    print(f"Looking up pictures and details for {len(games)} games...")
    ids = [g[0] for g in games]
    icons = roblox_api.fetch_icons(ids)
    metas = roblox_api.fetch_meta(ids)

    # Categories need at least 2 games to be worth a page ("All" is Roblox's "no genre").
    genre_count = {}
    for g in games:
        genre_count[g[2]] = genre_count.get(g[2], 0) + 1
    cats = {g for g, n in genre_count.items() if g and g != "All" and n >= 2}

    cards, waiting, all_events = [], [], []
    for uid, name, genre, place in games:
        rows = db.execute("SELECT ts,playing FROM samples WHERE universe_id=? ORDER BY ts",
                          (uid,)).fetchall()
        if len(rows) < MIN_SAMPLES:
            waiting.append({"name": name, "samples": len(rows)})
            continue
        a = analyze(rows)
        s = slug(name)
        meta = metas.get(uid)
        events = roblox_api.fetch_events(uid)
        passes = roblox_api.fetch_passes(uid)
        upcoming = [e for e in (events or []) if (e["end"] or e["start"] + 86400) >= now]
        for e in upcoming:
            all_events.append(dict(e, game=name, slug=s, icon=icons.get(uid)))
        vlabel, vcol, vtext = verdict(a)

        play = (f'<a class="btn" href="https://www.roblox.com/games/{place}">Play {html.escape(name)}</a>'
                if place and place > 1 else "")
        cat = (f' Category: <a href="/category/{slug(genre)}.html">{html.escape(genre)}</a>.'
               if genre in cats else "")
        body = (GAME.replace("__ICON__", thumb(name, icons.get(uid), f"{name} icon"))
                .replace("__NAME__", html.escape(name))
                .replace("__N__", f"{len(rows):,}")
                .replace("__CAT__", cat)
                .replace("__PLAY__", play)
                .replace("__SLUG__", s)
                .replace("__AVG__", f"{a['avg7']:,}")
                .replace("__PEAK__", f"{a['peak']:,}")
                .replace("__TREND__", trend_html(a["trend"]))
                .replace("__VLABEL__", vlabel).replace("__VCOL__", vcol).replace("__VTEXT__", vtext)
                .replace("__SPARK__", sparkline(a["daily"], a["spikes"]))
                .replace("__UPDATES__", updates_html(name, events, meta, a["spikes"], now))
                .replace("__CALENDAR__", calendar_html(name, events, now))
                .replace("__ABOUT__", about_game_html(name, meta))
                .replace("__PARENTS__", parents_html(passes))
                .replace("__SHARED__", SHARED_JS)
                .replace("__FAVJS__", FAV_GAME)
                .replace("__JS__", GAME_JS.replace("__DATA__", jsdata(a["week"]))))
        write(f"game/{s}.html", page(
            f"Best Time to Play {name}: Busy and Quiet Hours", body,
            f"When is {name} busiest and quietest? Hourly player counts, upcoming events, "
            f"recent updates, and whether it is growing or dying."))

        cards.append({"name": name, "slug": s, "icon": icons.get(uid), "genre": genre,
                      "avg": a["avg7"], "trend": a["trend"], "month": a["month"],
                      "samples": len(rows), "days": a["days"], "week": a["week"],
                      "levels": levels_string(a["week"]), "verdict": vlabel,
                      "events": len(events or []), "upcoming": len(upcoming)})

    cards.sort(key=lambda c: c["avg"], reverse=True)
    print(f"Built {len(cards)} game pages.")

    # ---- the data file the Compare and Plan pages load
    write("data.json", json.dumps({
        "built": now,
        "games": [{"s": c["slug"], "n": c["name"], "i": c["icon"] or "", "a": c["avg"],
                   "t": c["trend"], "g": c["genre"], "m": c["week"]}
                  for c in sorted(cards, key=lambda c: c["name"].lower())]},
        separators=(",", ":")))

    # ---- category pages
    cat_pages = []
    for g in sorted(cats):
        cg = [c for c in cards if c["genre"] == g]
        if not cg:
            continue
        cat_pages.append((g, f"/category/{slug(g)}.html"))
        write(f"category/{slug(g)}.html", page(
            f"Best Times to Play {g} Games - {SITE}",
            f'<div class="hero"><h1>{html.escape(g)} games</h1><p class="lede">When are popular '
            f'{html.escape(g.lower())} games busiest? Pick one to see its week, its events and its updates.</p></div>'
            f'{grid(cg)}<p><a href="/">&larr; All games</a></p>',
            f"See when popular {g} games are busiest and quietest, hour by hour.", wide=True))
    pills = "".join(f'<a href="{u}">{html.escape(g)}</a>' for g, u in cat_pages)

    # ---- homepage
    home_games = [{"s": c["slug"], "n": c["name"], "i": c["icon"] or "", "a": c["avg"], "l": c["levels"]}
                  for c in cards]
    body = (
        '<div class="hero rise"><h1>When is your game <em>busiest</em>?</h1>'
        '<p class="lede">Hour-by-hour player counts for popular Roblox games, in your own timezone. '
        'Find the quiet hours for easy claims and no queues, or the busy hours for trading and events.</p></div>'
        '<input id="s" type="search" placeholder="Search for a game" aria-label="Search for a game">'
        '<h2 style="margin-top:22px">What are you looking for?</h2>'
        '<div class="ask" id="ask">'
        '<button class="chip" data-w="busy" aria-pressed="false"><b>Busy right now</b>'
        '<i>Trading, full servers, live events</i></button>'
        '<button class="chip" data-w="quiet" aria-pressed="false"><b>Quiet right now</b>'
        '<i>Claim events, no queues, less lag</i></button>'
        '<button class="chip" data-w="" aria-pressed="true"><b>Just browsing</b>'
        '<i>Show the most popular games</i></button></div>'
        '<p id="asktxt" class="mut small">Showing the most popular games first.</p>'
        f'<div class="pills">{pills}</div>'
        '<section id="favs" hidden><h2 style="margin-top:24px">Your saved games</h2>'
        '<ul class="grid" id="favgrid"></ul></section>'
        f'<h2 style="margin-top:24px">All games</h2>{grid(cards, "all")}'
        f'<script>{SHARED_JS}</script>'
        f'<script>{HOME_JS.replace("__GAMES__", jsdata(home_games))}</script>')
    write("index.html", page(f"{SITE}: Best Times to Play Popular Games", body,
                             "See when popular games are busiest and quietest, hour by hour, in your timezone.",
                             wide=True, nav="home"))

    # ---- the pages across the top
    up = sorted([c for c in cards if c["trend"] is not None and c["trend"] >= 5],
                key=lambda c: -c["trend"])
    down = sorted([c for c in cards if c["trend"] is not None and c["trend"] <= -5],
                  key=lambda c: c["trend"])
    none = ('<p class="none">None right now. We compare the last 7 days with the 7 days before, so games '
            'need two weeks of player counts first.</p>')

    list_page("popular", f"Most Popular Games Right Now - {SITE}", "Most popular games",
              "Ordered by how many people are in the game at a typical moment over the last 7 days.",
              cards, "The most played games on Roblox by typical player count, updated nightly.")
    list_page("growing", f"Games That Are Growing - {SITE}", "Games that are growing",
              "These games have more players than they did a week ago. Updated every night.",
              up, "Which Roblox games are gaining players this week.")
    list_page("shrinking", f"Games That Are Shrinking - {SITE}", "Games that are shrinking",
              "These games have fewer players than they did a week ago. Updated every night. "
              "Losing players does not mean a game is bad, and most of them are still busy at peak times.",
              down, "Which Roblox games are losing players this week.")

    rows = "".join(
        f'<tr><td><a href="/game/{c["slug"]}.html">{html.escape(c["name"])}</a></td>'
        f'<td>{c["avg"]:,}</td><td>{trend_short(c["trend"]) or "<span class=mut>steady</span>"}</td></tr>'
        for c in up[:10] + down[:10])
    write("trending.html", page(
        f"Trending Games: Biggest Gainers and Losers This Week - {SITE}",
        '<div class="hero"><h1>Biggest gainers and losers this week</h1>'
        '<p class="lede">Every night we compare the last 7 days of player counts with the 7 days before. '
        'These are the games that moved the most.</p></div>'
        f'<h2 style="margin-top:24px">Biggest gainers</h2>{grid(up[:12]) if up else none}'
        f'<h2 style="margin-top:28px">Biggest losers</h2>{grid(down[:12]) if down else none}'
        + (f'<h2 style="margin-top:28px">The numbers</h2><div class="wrap"><table class="tbl">'
           f'<tr><th>Game</th><th>Typical players</th><th>vs last week</th></tr>{rows}</table></div>'
           if rows else "")
        + '<p><a href="/">&larr; All games</a></p>',
        "Which Roblox games gained and lost the most players this week, updated every night.",
        wide=True, nav="trending"))

    # ---- site-wide event calendar
    all_events.sort(key=lambda e: e["start"])
    live = [e for e in all_events if e["start"] <= now]
    soon = [e for e in all_events if e["start"] > now]

    def ev_list(items):
        out = []
        for e in items[:40]:
            out.append(f'<li class="{"live" if e["start"] <= now else "soon"}">'
                       f'<b><a href="/game/{e["slug"]}.html">{html.escape(e["game"])}</a>: '
                       f'{html.escape(e["title"])}</b>'
                       + (f'<span class="d">{html.escape(e["subtitle"])}</span>' if e["subtitle"] else "")
                       + f'<span class="d">'
                       + (f'Happening now, ends {when(e["end"] or e["start"])}' if e["start"] <= now
                          else f'Starts {when(e["start"])}')
                       + '</span></li>')
        return f'<ul class="evt">{"".join(out)}</ul>' if out else ""

    write("events.html", page(
        f"Roblox Game Events Calendar: What Is On Now and Next - {SITE}",
        '<div class="hero"><h1>Event calendar</h1><p class="lede">Events and updates the game creators '
        'themselves have put on the Roblox calendar, for every game we track. Expect these hours to be busy.</p></div>'
        + (f'<h2 style="margin-top:22px">Happening now</h2>{ev_list(live)}' if live else "")
        + (f'<h2 style="margin-top:26px">Coming up</h2>{ev_list(soon)}' if soon else "")
        + ("" if live or soon else '<p class="none">No events are listed right now. Creators usually '
                                   'announce them a few days ahead, so check back soon.</p>')
        + '<p><a href="/">&larr; All games</a></p>',
        "Every upcoming Roblox game event and update we know about, with the dates they run.",
        nav="events"))

    # ---- compare two games
    write("compare.html", page(
        f"Compare Two Games: Which Is Less Crowded? - {SITE}",
        '<div class="hero"><h1>Compare two games</h1><p class="lede">Put two games side by side, hour by hour, '
        'to answer things like &ldquo;which one is less crowded on Saturday?&rdquo;</p></div>'
        '<div class="card" id="cmp" hidden><div class="two">'
        '<label>First game<br><select class="sel" id="ga"></select></label>'
        '<label>Second game<br><select class="sel" id="gb"></select></label></div>'
        '<div class="days" id="days"></div><div class="bars" id="bars"></div>'
        '<div class="axis"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span></div>'
        '<div class="legend"><i style="background:var(--acc)"></i><span id="alab"></span>'
        '<i style="background:var(--acc2);margin-left:10px"></i><span id="blab"></span></div>'
        '<p id="verdict" style="margin-top:14px"></p>'
        '<div class="stats" id="nums"></div></div>'
        '<p class="mut small" id="load">Loading the games&hellip;</p>'
        '<p><a href="/">&larr; All games</a></p>',
        "Compare two Roblox games hour by hour and see which is quieter on any day of the week.",
        nav="compare", tail=f"<script>{SHARED_JS}</script><script>{COMPARE_JS}</script>"))

    # ---- plan a session
    write("plan.html", page(
        f"Plan a Session: The Next Quiet or Busy Hours - {SITE}",
        '<div class="hero"><h1>Plan my session</h1><p class="lede">Pick a game, say whether you want it quiet '
        'or busy, and we will count down to the next good block of time in your timezone.</p></div>'
        '<div class="card" id="plan" hidden>'
        '<label>Game<br><select class="sel" id="g"></select></label>'
        '<p class="mut small" style="margin-top:14px">What do you want?</p>'
        '<div class="days" id="planbtns"><button data-m="quiet" aria-pressed="true">Quiet</button>'
        '<button data-m="busy" aria-pressed="false">Busy</button></div>'
        '<div id="out"></div></div>'
        '<p class="mut small" id="load">Loading the games&hellip;</p>'
        '<p><a href="/">&larr; All games</a></p>',
        "Find the next quiet or busy hours for any Roblox game, as a countdown in your own timezone.",
        nav="plan", tail=f"<script>{SHARED_JS}</script><script>{PLAN_JS}</script>"))

    # ---- the plain pages
    write("about.html", page(f"About {SITE}", about_body(),
                             f"What {SITE} is, how it measures when games are busy, and what it does not tell you."))
    write("privacy.html", page(f"Privacy Policy - {SITE}", privacy_body(),
                               f"What {SITE} stores, what it never asks for, and how to delete your data."))
    write("terms.html", page(f"Terms of Service - {SITE}", terms_body(),
                             f"The rules for using {SITE}, in plain language."))

    # ---- sitemap and robots
    base = DOMAIN.rstrip("/")
    urls = (["/"] + [u for _, _, u in TABS if u != "/"] + ["/about.html", "/privacy.html"]
            + ["/terms.html"] + [u for _, u in cat_pages] + [f"/game/{c['slug']}.html" for c in cards])
    write("sitemap.txt", "\n".join(base + u for u in urls) + "\n")
    write("robots.txt", "User-agent: *\nDisallow: /\n" if NOINDEX else
          "User-agent: *\nDisallow: /admin\nAllow: /\n" + (f"Sitemap: {base}/sitemap.txt\n" if base else ""))

    write_stats(db, games, cards, waiting)
    db.close()
    print(f"Wrote {len(urls)} pages into {OUT}/ in {time.time() - started:.0f} seconds.")
    if waiting:
        print(f"{len(waiting)} games are still collecting data and have no page yet.")


if __name__ == "__main__":
    main()
