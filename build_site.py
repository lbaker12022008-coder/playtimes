"""Reads data.db and writes a static site to docs/ (deploy on Cloudflare Pages / GitHub Pages)."""
import sqlite3, json, re, os, html
from datetime import datetime, timezone

SITE = "PlayTimes"          # change me (don't put 'Roblox' in your domain name)
MIN_SAMPLES = 200          # ~2 days at 15-min intervals
ADS = ""                   # paste your AdSense <script> here
OUT = "docs"

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
.wrap{overflow-x:auto}"""

def page(title, body, desc=""):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}"><style>{CSS}</style>{ADS}</head><body><div class="w">
<div class="top"><a class="logo" href="/">{html.escape(SITE)}</a></div>{body}
<p class="mut small">Not affiliated with or endorsed by Roblox Corporation. Based on public player counts, so it shows when people play, not whether a game is good or safe.</p>
</div></body></html>"""

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "game"

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

GAME = """<h1>When is __NAME__ busiest?</h1>
<p class="mut">Times are shown in your timezone. Based on __N__ player counts.</p>
<div class="card ans"><h2>The short answer</h2><p id="now"></p><p id="best"></p><p id="quiet"></p>__PLAY__</div>
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
document.querySelectorAll('.list li').forEach(li=>li.hidden=!li.dataset.n.includes(t))}</script>"""

def main():
    db = sqlite3.connect("data.db"); os.makedirs(OUT + "/game", exist_ok=True)
    cards = []
    for uid, name, genre, place in db.execute("SELECT * FROM games"):
        rows = db.execute("SELECT ts,playing FROM samples WHERE universe_id=? ORDER BY ts", (uid,)).fetchall()
        if len(rows) < MIN_SAMPLES: continue
        m, trend, avg7, peak = analyze(rows)
        s = slug(name)
        play = f'<p><a class="btn" href="https://www.roblox.com/games/{place}">Play {html.escape(name)}</a></p>' if place and place > 1 else ""
        body = (GAME.replace("__NAME__", html.escape(name)).replace("__N__", f"{len(rows):,}")
                .replace("__PLAY__", play).replace("__AVG__", f"{avg7:,}").replace("__PEAK__", f"{peak:,}")
                .replace("__TREND__", trend_html(trend)).replace("__JS__", JS.replace("__DATA__", json.dumps(m))))
        open(f"{OUT}/game/{s}.html", "w", encoding="utf-8").write(page(
            f"Best Time to Play {name}: Busy and Quiet Hours", body,
            f"When is {name} busiest and quietest? See the hours and days with the most and fewest players."))
        cards.append((avg7, trend, name, s))
    cards.sort(reverse=True)
    li = "".join(f'<li data-n="{html.escape(n.lower())}"><a href="/game/{s}.html"><span><b>{html.escape(n)}</b><br>'
                 f'<span class="mut small">About {a:,} players</span></span><span class="small">{trend_html(t)}</span></a></li>'
                 for a, t, n, s in cards)
    body = (f"<h1>When is your game busiest?</h1><p class=\"mut\">Find the quiet hours for less crowding, or the busy "
            f"hours for more players and events. Pick a game to see its week.</p>"
            f'<input id="s" type="search" placeholder="Search for a game" aria-label="Search for a game">'
            f'<ul class="list">{li}</ul>{SEARCH}')
    open(f"{OUT}/index.html", "w", encoding="utf-8").write(page(f"{SITE}: Best Times to Play Popular Games", body,
        "See when popular games are busiest and quietest, hour by hour."))
    open(f"{OUT}/sitemap.txt", "w").write("\n".join(f"/game/{s}.html" for *_, s in cards))
    print(f"Built {len(cards)} game pages in {OUT}/")

if __name__ == "__main__": main()
