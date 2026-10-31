"""Reads data.db and writes a static site to docs/ (deploy on Cloudflare Pages / GitHub Pages)."""
import sqlite3, json, re, os, html, urllib.request
from datetime import datetime, timezone

SITE = "PlayTime"          # change me (don't put 'Roblox' in your domain name)
MIN_SAMPLES = 2          # ~2 days at 15-min intervals
ADS = ""                   # paste your AdSense <script> here
NOINDEX = True             # True = ask Google NOT to list the site (set False when you launch)
OUT = "docs"
CONTACT = ""               # a contact email for the site (NOT your personal one), e.g. hello@yourdomain.com
POLICY_DATE = "October 30, 2026"   # change this whenever you edit the Privacy Policy

CSS = """:root{--bg:#f6f8fb;--card:#fff;--ink:#14213d;--mut:#5b6478;--line:#e1e6ef;--acc:#2563eb;--l1:#86e3d0;--l2:#b9e8a8;--l3:#f6e27a;--l4:#f7b267;--l5:#f28482}
@media(prefers-color-scheme:dark){:root{--bg:#0f1724;--card:#182235;--ink:#eef2fb;--mut:#a3aec4;--line:#2a3750;--acc:#7aa7ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:18px/1.6 ui-rounded,"SF Pro Rounded",Nunito,system-ui,-apple-system,"Segoe UI",sans-serif}
.w{max-width:760px;margin:0 auto;padding:16px 16px 48px}
.top{display:flex;justify-content:space-between;align-items:center;padding:8px 0}
.logo{font-weight:800;font-size:1.3rem;color:var(--ink);text-decoration:none}
a{color:var(--acc)}
h1{font-size:clamp(1.7rem,5vw,2.4rem);line-height:1.2;margin:.5em 0 .3em}
h2{font-size:1.15rem;margin:0 0 6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin:16px 0}
.mut{color:var(--mut)}.small{font-size:.9rem}
.ans p{margin:.35em 0;font-size:1.1rem}
.days{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.days button{font:inherit;font-size:.95rem;padding:6px 14px;min-height:44px;border-radius:999px;border:1px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
.days button[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:700}
button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
.bars{display:grid;grid-template-columns:repeat(24,1fr);gap:3px;align-items:end;height:150px;margin-top:12px}
.bar{border-radius:5px 5px 0 0;min-height:4px}
.axis{display:grid;grid-template-columns:repeat(24,1fr);font-size:.8rem;color:var(--mut);margin-top:4px}
.axis span{grid-column:span 6}
.hm{display:grid;grid-template-columns:44px repeat(24,minmax(0,1fr));gap:2px;font-size:.8rem;color:var(--mut);align-items:center}
.hm .c{height:26px;border-radius:4px}.hm .now{outline:3px solid var(--ink);outline-offset:-1px}
.legend{display:flex;align-items:center;gap:4px;font-size:.85rem;color:var(--mut);margin-top:10px}
.legend i{width:26px;height:12px;border-radius:3px;display:inline-block}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.stats b{display:block;font-size:1.5rem}
.btn{display:inline-block;background:var(--acc);color:#fff;padding:10px 18px;border-radius:12px;text-decoration:none;font-weight:700}
input[type=search]{width:100%;font:inherit;padding:12px 16px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.list{list-style:none;padding:0;margin:0}
.list a{display:flex;justify-content:space-between;gap:12px;padding:14px 18px;margin:8px 0;background:var(--card);border:1px solid var(--line);border-radius:14px;text-decoration:none;color:var(--ink)}
.list a:hover{border-color:var(--acc)}
.up{color:#15803d}.down{color:#b91c1c}
@media(prefers-color-scheme:dark){.up{color:#4ade80}.down{color:#f87171}}
.wrap{overflow-x:auto}
.foot{border-top:1px solid var(--line);margin-top:32px;padding-top:12px}
.foot nav{display:flex;flex-wrap:wrap;gap:6px 18px;margin-bottom:6px}
.doc h2{margin-top:1.4em}.doc ul{padding-left:1.2em}
.w.wide{max-width:1100px}
.grid{list-style:none;padding:0;margin:16px 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:20px 14px}
.tile{display:block;text-decoration:none;color:var(--ink)}
.thumb{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:cover;border-radius:14px;background:var(--line);transition:transform .15s}
.ph{display:grid;place-items:center;font-size:2.6rem;font-weight:800;color:var(--mut)}
.tile:hover .thumb{transform:translateY(-3px);box-shadow:0 6px 16px rgba(0,0,0,.18)}
.tname{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-weight:700;font-size:.95rem;line-height:1.3;margin-top:8px}
.tmeta{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;font-size:.82rem;color:var(--mut);margin-top:3px}
.tmeta svg{width:14px;height:14px;vertical-align:-2px;fill:currentColor}
.ghead{display:flex;gap:20px;align-items:center;flex-wrap:wrap;margin:16px 0}
.ghead .thumb{width:150px;flex:none}.ghead>div{flex:1 1 260px}
.ghead h1{margin:0 0 .2em}.ghead p{margin:.2em 0}"""

ROBOTS = '<meta name="robots" content="noindex,nofollow">' if NOINDEX else ""

def page(title, body, desc="", wide=False):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">{ROBOTS}<style>{CSS}</style>{ADS}</head><body><div class="w{' wide' if wide else ''}">
<div class="top"><a class="logo" href="/">{html.escape(SITE)}</a></div>{body}
<footer class="foot"><nav class="small"><a href="/">All games</a><a href="/about.html">About</a><a href="/privacy.html">Privacy Policy</a></nav>
<p class="mut small">Not affiliated with or endorsed by Roblox Corporation. Based on public player counts, so it shows when people play, not whether a game is good or safe.</p></footer>
</div></body></html>"""

def contact_html():
    if not CONTACT: return ""
    e = html.escape(CONTACT)
    return f'<h2>Contact</h2><p>Questions or problems? Email <a href="mailto:{e}">{e}</a>.</p>'

def about_body():
    return f"""<div class="doc"><h1>About {html.escape(SITE)}</h1>
<p>{html.escape(SITE)} shows when popular Roblox games are busiest and quietest, hour by hour, so you can pick a good time to play.</p>
<h2>How it works</h2>
<p>About every 30 minutes, we check how many people are playing each game, using the player counts Roblox shows publicly.
Over days and weeks, those counts add up to a picture of each game's week: which hours are packed and which are quiet.
Times are shown in your own timezone.</p>
<h2>Why use it?</h2>
<ul><li><b>Quiet hours</b> are good for shorter queues, less lag, and learning a game without a crowd.</li>
<li><b>Busy hours</b> are good for full servers, trading, and events.</li></ul>
<h2>What it does not tell you</h2>
<p>Player counts show when people play. They do not say whether a game is good, fair, or safe for children.
Parents should still check a game themselves and use Roblox's parental controls.</p>
<h2>The fine print</h2>
<p>{html.escape(SITE)} is an independent fan project. It is not affiliated with, endorsed by, or sponsored by Roblox Corporation.
Game names belong to their creators. Numbers are averages and can be off, especially for games we started tracking recently.</p>
<p>We never ask for a Roblox login, and there are no accounts or sign-ups here. See our <a href="/privacy.html">Privacy Policy</a>.</p>
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
<p>The short version: {html.escape(SITE)} does not ask for, collect, or store personal information about you.</p>
<h2>What we do not collect</h2>
<ul><li>No accounts, sign-ups, or logins. We will never ask for your Roblox username or password.</li>
<li>No forms, comments, or chat.</li>
<li>No names, emails, ages, or locations from visitors.</li></ul>
<h2>Children</h2>
<p>Many visitors are kids, so we keep it that way on purpose. We do not knowingly collect personal information from
anyone, including children under 13. If you think a child has sent us personal information, contact us and we will delete it.</p>
<h2>Things that stay on your device</h2>
<p>To show times in your timezone, the page reads your device's clock. That happens only in your browser and is never sent to us.</p>
<h2>Our hosting provider</h2>
<p>The site is hosted by Cloudflare. Like any website host, Cloudflare automatically handles basic technical information
(such as IP addresses and browser type) to deliver pages and protect the site from attacks. See
<a href="https://www.cloudflare.com/privacypolicy/">Cloudflare's privacy policy</a>.</p>
{ads}
<h2>Game data</h2>
<p>The player counts on this site are public numbers about games, not about people. We do not track individual players.</p>
<h2>Changes</h2>
<p>If this policy changes, we will update this page and the date at the top.</p>
{contact_html()}</div>"""

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "game"

ICON_API = "https://thumbnails.roblox.com/v1/games/icons?size=256x256&format=Webp&isCircular=false&universeIds="

def fetch_icons(ids):
    """Asks Roblox's public thumbnail service for each game's square icon. Returns {universe_id: url}."""
    out = {}
    for i in range(0, len(ids), 50):
        try:
            req = urllib.request.Request(ICON_API + ",".join(map(str, ids[i:i + 50])), headers={"User-Agent": "playtime/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                for t in json.load(r).get("data", []):
                    if t.get("state") == "Completed" and t.get("imageUrl"): out[t["targetId"]] = t["imageUrl"]
        except Exception as e:
            print("Could not load icons (pages will show a letter instead):", e)
    return out

def thumb(name, url, alt=""):
    if url: return f'<img class="thumb" src="{html.escape(url)}" alt="{html.escape(alt)}" width="256" height="256" loading="lazy">'
    letter = next((c for c in name if c.isalnum()), "?").upper()
    return f'<div class="thumb ph" aria-hidden="true">{html.escape(letter)}</div>'

def short(n):
    for div, unit in ((1e6, "M"), (1e3, "K")):
        if n >= div: return f"{n / div:.1f}".rstrip("0").rstrip(".") + unit
    return str(n)

PERSON = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="5" r="3"/><path d="M2 15c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5z"/></svg>'

def trend_short(t):
    if t is None: return ""
    if t >= 5: return f'<span class="up">&#9650; {t:.0f}%</span>'
    if t <= -5: return f'<span class="down">&#9660; {-t:.0f}%</span>'
    return ""

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

def trend_html(t):
    if t is None: return '<span class="mut">Not enough history yet</span>'
    if t >= 5: return f'<span class="up">Growing ({t:+.0f}%)</span>'
    if t <= -5: return f'<span class="down">Shrinking ({t:+.0f}%)</span>'
    return '<span class="mut">Steady</span>'

GAME = """<div class="ghead">__ICON__<div><h1>When is __NAME__ busiest?</h1>
<p class="mut">Times are shown in your timezone. Based on __N__ player counts.</p>__PLAY__</div></div>
<div class="card ans"><h2>The short answer</h2><p id="now"></p><p id="best"></p><p id="quiet"></p></div>
<div class="card"><h2>Pick a day</h2><div class="days" id="days"></div>
<p id="dtxt" class="mut small"></p><div class="bars" id="bars"></div><div class="axis"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span></div></div>
<div class="card"><h2>The whole week</h2><div class="wrap"><div class="hm" id="hm"></div></div>
<div class="legend">Quiet <i style="background:var(--l1)"></i><i style="background:var(--l2)"></i><i style="background:var(--l3)"></i><i style="background:var(--l4)"></i><i style="background:var(--l5)"></i> Busy</div>
<p class="mut small">The outlined square is right now.</p></div>
<div class="card stats"><div><span class="mut small">Typical players (last 7 days)</span><b>__AVG__</b></div>
<div><span class="mut small">Highest seen</span><b>__PEAK__</b></div>
<div><span class="mut small">Compared to last week</span><b>__TREND__</b></div></div>
<p><a href="/">&larr; All games</a></p>
<script>__JS__</script>"""

JS = """const M=__DATA__,D=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const off=-new Date().getTimezoneOffset()/60,L=D.map(()=>Array(24).fill(null));
for(let d=0;d<7;d++)for(let h=0;h<24;h++){let t=h+off,dd=d;while(t<0){t+=24;dd=(dd+6)%7}while(t>=24){t-=24;dd=(dd+1)%7}L[dd][Math.floor(t)]=M[d][h]}
const vals=L.flat().filter(v=>v!=null).sort((a,b)=>a-b),mx=vals[vals.length-1]||1;
const q=p=>vals[Math.floor(p*(vals.length-1))],T=[q(.2),q(.4),q(.6),q(.8)];
const lv=v=>v==null?0:1+T.filter(t=>v>t).length,W=['','very quiet','quiet','average','busy','very busy'];
const fmt=h=>(h%12||12)+(h<12?' AM':' PM'),$=id=>document.getElementById(id);
const nd=(new Date().getDay()+6)%7,nh=new Date().getHours();
let best=null,worst=null,qd=null;
for(let d=0;d<7;d++)for(let h=0;h<24;h++){const v=L[d][h];if(v==null)continue;
if(!best||v<best[2])best=[d,h,v];if(!worst||v>worst[2])worst=[d,h,v];
if(h>=8&&h<=21&&(!qd||v<qd[2]))qd=[d,h,v]}
const nl=lv(L[nd][nh]);
$('now').innerHTML=nl?'Right now it is usually <b>'+W[nl]+'</b>.':'';
$('best').innerHTML='Busiest: <b>'+D[worst[0]]+' around '+fmt(worst[1])+'</b>.';
$('quiet').innerHTML='Quietest: <b>'+D[best[0]]+' around '+fmt(best[1])+'</b>'+(qd&&qd[0]+':'+qd[1]!=best[0]+':'+best[1]?' (or <b>'+D[qd[0]]+' around '+fmt(qd[1])+'</b> if you play during the day).':'.');
function show(d){
$('days').querySelectorAll('button').forEach((b,i)=>b.setAttribute('aria-pressed',i==d));
let a=null,z=null,html='';
for(let h=0;h<24;h++){const v=L[d][h];if(v==null)continue;if(!a||v<a[1])a=[h,v];if(!z||v>z[1])z=[h,v]}
for(let h=0;h<24;h++){const v=L[d][h];html+='<div class="bar" title="'+fmt(h)+': about '+(v||0).toLocaleString()+' players" style="height:'+Math.max(3,(v||0)/mx*100)+'%;background:var(--l'+(lv(v)||1)+')"></div>'}
$('bars').innerHTML=html;
$('dtxt').textContent=a?'On '+D[d]+', it is quietest around '+fmt(a[0])+' and busiest around '+fmt(z[0])+'. Hover or tap a bar for numbers.':''}
D.forEach((n,i)=>{const b=document.createElement('button');b.textContent=n.slice(0,3);b.setAttribute('aria-label',n);b.onclick=()=>show(i);$('days').appendChild(b)});
let g='<div></div>';['12 AM','6 AM','12 PM','6 PM'].forEach(t=>g+='<span style="grid-column:span 6">'+t+'</span>');
for(let d=0;d<7;d++){g+='<div>'+D[d].slice(0,3)+'</div>';for(let h=0;h<24;h++){const v=L[d][h];
g+='<div class="c'+(d==nd&&h==nh?' now':'')+'" title="'+D[d]+' '+fmt(h)+': about '+(v||0).toLocaleString()+' players" style="background:'+(v==null?'transparent':'var(--l'+lv(v)+')')+'"></div>'}}
$('hm').innerHTML=g;show(nd);"""

SEARCH = """<script>const s=document.getElementById('s');s.oninput=()=>{const t=s.value.toLowerCase();
document.querySelectorAll('.grid li').forEach(li=>li.hidden=!li.dataset.n.includes(t))}</script>"""

def main():
    db = sqlite3.connect("data.db"); os.makedirs(OUT + "/game", exist_ok=True)
    cards = []
    games = db.execute("SELECT * FROM games").fetchall()
    icons = fetch_icons([g[0] for g in games])
    for uid, name, genre, place in games:
        rows = db.execute("SELECT ts,playing FROM samples WHERE universe_id=? ORDER BY ts", (uid,)).fetchall()
        if len(rows) < MIN_SAMPLES: continue
        m, trend, avg7, peak = analyze(rows)
        s = slug(name)
        play = f'<p><a class="btn" href="https://www.roblox.com/games/{place}">Play {html.escape(name)}</a></p>' if place and place > 1 else ""
        body = (GAME.replace("__ICON__", thumb(name, icons.get(uid), f"{name} icon"))
                .replace("__NAME__", html.escape(name)).replace("__N__", f"{len(rows):,}")
                .replace("__PLAY__", play).replace("__AVG__", f"{avg7:,}").replace("__PEAK__", f"{peak:,}")
                .replace("__TREND__", trend_html(trend)).replace("__JS__", JS.replace("__DATA__", json.dumps(m))))
        open(f"{OUT}/game/{s}.html", "w", encoding="utf-8").write(page(
            f"Best Time to Play {name}: Busy and Quiet Hours", body,
            f"When is {name} busiest and quietest? See the hours and days with the most and fewest players."))
        cards.append((avg7, trend, name, s, icons.get(uid)))
    cards.sort(key=lambda c: c[0], reverse=True)
    li = "".join(f'<li data-n="{html.escape(n.lower())}"><a class="tile" href="/game/{s}.html">{thumb(n, ic)}'
                 f'<span class="tname">{html.escape(n)}</span>'
                 f'<span class="tmeta"><span title="Typical players over the last 7 days">{PERSON} {short(a)}</span>{trend_short(t)}</span></a></li>'
                 for a, t, n, s, ic in cards)
    body = (f"<h1>When is your game busiest?</h1><p class=\"mut\">Find the quiet hours for less crowding, or the busy "
            f"hours for more players and events. Pick a game to see its week.</p>"
            f'<input id="s" type="search" placeholder="Search for a game" aria-label="Search for a game">'
            f'<h2 style="margin-top:24px">Popular games</h2><ul class="grid">{li}</ul>{SEARCH}')
    open(f"{OUT}/index.html", "w", encoding="utf-8").write(page(f"{SITE}: Best Times to Play Popular Games", body,
        "See when popular games are busiest and quietest, hour by hour.", wide=True))
    open(f"{OUT}/about.html", "w", encoding="utf-8").write(page(f"About {SITE}", about_body(),
        f"What {SITE} is, how it measures when games are busy, and what it does not tell you."))
    open(f"{OUT}/privacy.html", "w", encoding="utf-8").write(page(f"Privacy Policy - {SITE}", privacy_body(),
        f"{SITE} does not collect personal information. No accounts, no sign-ups, no logins."))
    open(f"{OUT}/sitemap.txt", "w").write("\n".join(["/about.html", "/privacy.html"] + [f"/game/{c[3]}.html" for c in cards]))
    open(f"{OUT}/robots.txt", "w").write("User-agent: *\nDisallow: /\n" if NOINDEX else "User-agent: *\nAllow: /\n")
    print(f"Built {len(cards)} game pages in {OUT}/")

if __name__ == "__main__": main()
