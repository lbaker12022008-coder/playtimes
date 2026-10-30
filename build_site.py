"""Reads data.db and writes a static site to docs/ (deploy on Cloudflare Pages / GitHub Pages)."""
import sqlite3, json, re, os, html, time
from datetime import datetime, timezone

SITE = "Best Time To Play"          # change me (don't put 'Roblox' in your domain)
MIN_SAMPLES = 200                   # ~1.5 days at 10-min intervals
ADS = ""                            # paste your AdSense <script> here
OUT = "docs"

CSS = """:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--card:#f3f4f6}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#eee;--mut:#9aa;--card:#23262b}}
body{font:16px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:860px;margin:0 auto;padding:16px}
a{color:#3b82f6}.card{background:var(--card);padding:12px 16px;border-radius:10px;margin:12px 0}
.grid{display:grid;grid-template-columns:40px repeat(24,1fr);gap:2px;font-size:11px;overflow-x:auto;min-width:640px}
.cell{height:22px;border-radius:3px}.mut{color:var(--mut)}.wrap{overflow-x:auto}"""

def page(title, body, desc=""):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}"><style>{CSS}</style>{ADS}</head><body>
<p><a href="/">{SITE}</a></p>{body}
<p class="mut"><small>Not affiliated with or endorsed by Roblox Corporation. Data is sampled from public player counts.</small></p>
</body></html>"""

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def analyze(rows):
    sums = [[0] * 24 for _ in range(7)]; cnt = [[0] * 24 for _ in range(7)]
    now = rows[-1][0]; recent = []; prior = []
    for ts, p in rows:
        d = datetime.fromtimestamp(ts, timezone.utc)
        sums[d.weekday()][d.hour] += p; cnt[d.weekday()][d.hour] += 1
        if ts > now - 7 * 86400: recent.append(p)
        elif ts > now - 14 * 86400: prior.append(p)
    m = [[round(sums[d][h] / cnt[d][h]) if cnt[d][h] else None for h in range(24)] for d in range(7)]
    avg = lambda l: sum(l) / len(l) if l else None
    a, b = avg(recent), avg(prior)
    trend = round((a - b) / b * 100, 1) if a and b else None
    return m, trend, round(a or 0), max(p for _, p in rows)

SCRIPT = """const M=%s;const days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const off=-new Date().getTimezoneOffset()/60;// local hours from UTC (current offset)
const L=days.map(()=>Array(24).fill(null));
for(let d=0;d<7;d++)for(let h=0;h<24;h++){let t=h+off,dd=d;while(t<0){t+=24;dd=(dd+6)%%7}while(t>=24){t-=24;dd=(dd+1)%%7}L[dd][Math.floor(t)]=M[d][h]}
const vals=L.flat().filter(v=>v!=null),mn=Math.min(...vals),mx=Math.max(...vals);
let g='<div class="grid"><div></div>';for(let h=0;h<24;h++)g+='<div class="mut">'+h+'</div>';
let best=[0,0,1e18],worst=[0,0,-1];
for(let d=0;d<7;d++){g+='<div class="mut">'+days[d]+'</div>';for(let h=0;h<24;h++){const v=L[d][h];
if(v==null){g+='<div class="cell"></div>';continue}
if(v<best[2])best=[d,h,v];if(v>worst[2])worst=[d,h,v];
const a=(v-mn)/(mx-mn||1);g+='<div class="cell" title="'+days[d]+' '+h+':00 \\u2013 ~'+v.toLocaleString()+' players" style="background:rgba(59,130,246,'+(0.1+a*0.9).toFixed(2)+')"></div>'}}
document.getElementById('hm').innerHTML=g+'</div>';
const f=(x)=>days[x[0]]+' around '+x[1]+':00';
document.getElementById('sum').textContent='In your timezone, it is quietest '+f(best)+' and busiest '+f(worst)+'.';"""

def main():
    db = sqlite3.connect("data.db"); os.makedirs(OUT + "/game", exist_ok=True)
    cards = []
    for uid, name, genre, place in db.execute("SELECT * FROM games"):
        rows = db.execute("SELECT ts,playing FROM samples WHERE universe_id=? ORDER BY ts", (uid,)).fetchall()
        if len(rows) < MIN_SAMPLES: continue
        m, trend, avg7, peak = analyze(rows)
        s = slug(name); n = html.escape(name)
        t = "n/a yet" if trend is None else f"{trend:+}% vs. previous week"
        body = f"""<h1>Best Time to Play {n}</h1>
<p id="sum" class="card"></p><div class="wrap"><div id="hm"></div></div>
<p class="mut">Darker = more players. Times shown in your local timezone. Based on {len(rows):,} samples.</p>
<div class="card"><b>Average players (7 days):</b> {avg7:,}<br><b>Peak seen:</b> {peak:,}<br><b>Trend:</b> {t}</div>
<p>Want fewer crowded servers? Play in the lighter squares. Want company or events? Aim for the darkest.</p>
<script>{SCRIPT % json.dumps(m)}</script>"""
        open(f"{OUT}/game/{s}.html", "w").write(page(f"Best Time to Play {name} (Player Count Heatmap)", body,
              f"When is {name} busiest and quietest? Hour-by-hour player heatmap."))
        cards.append((avg7, trend, name, s))
    cards.sort(reverse=True)
    li = "".join(f'<li><a href="/game/{s}.html">{html.escape(n)}</a> <span class="mut">~{a:,} players'
                 f'{"" if t is None else f", {t:+}%"}</span></li>' for a, t, n, s in cards)
    open(f"{OUT}/index.html", "w").write(page(f"{SITE}: Player Count Heatmaps",
        f"<h1>{SITE}</h1><p>See when your favorite games are busiest and quietest.</p><ul>{li}</ul>"))
    open(f"{OUT}/sitemap.txt", "w").write("\n".join(f"/game/{s}.html" for *_, s in cards))
    print(f"Built {len(cards)} game pages in {OUT}/")

if __name__ == "__main__": main()
