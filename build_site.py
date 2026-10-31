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
import html, json, math, os, re, sqlite3, statistics, time
from datetime import datetime, timezone

import roblox_api

SITE = "PlayTime"          # the site's name (don't put "Roblox" in your domain name)
MIN_SAMPLES = 2            # how many player counts a game needs before it gets a page
# Raise this to 200 only once the games actually have that many, or every page
# disappears. Check the admin dashboard: each game gains about 144 a day.
ADS = ""                   # paste your AdSense <script> here
NOINDEX = True             # True = ask Google NOT to list the site (set False when you launch)
OUT = os.environ.get("SITE_OUT") or "docs"   # which folder to write the site into
DOMAIN = ""                # your web address once you buy it, e.g. "https://playtime.gg"
ROBUX_USD = 0.0125         # rough dollars per Robux (800 Robux costs $9.99)
CONTACT = ""               # a contact email for the site (NOT your personal one)
POLICY_DATE = "October 30, 2026"   # change this whenever you edit the Privacy Policy

SPIKE = 1.5                # a day this much busier than normal is "likely an update or event"

# The dark palette, written once and used twice below: once for people whose device
# is set to dark, and once for people who pressed the theme button themselves.
DARK = """--bg:#0d1420;--card:#172033;--ink:#eef2fb;--mut:#a3aec4;--line:#283550;
--acc:#7aa7ff;--acc2:#b48cff;--glass:rgba(13,20,32,.86);--sh:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35);
--up:#4ade80;--down:#f87171;--soft:#1d2942;--favbg:#2a2410;--favink:#f3c653;--shade:rgba(255,255,255,.06);
--bannerop:.3"""

CSS = """:root{--bg:#f3f6fc;--card:#fff;--ink:#101a33;--mut:#5b6478;--line:#e3e8f1;--acc:#2563eb;--acc2:#7c3aed;
--glass:rgba(243,246,252,.86);--sh:0 1px 2px rgba(16,26,51,.05),0 10px 30px rgba(16,26,51,.07);
--l1:#86e3d0;--l2:#b9e8a8;--l3:#f6e27a;--l4:#f7b267;--l5:#f28482;--up:#15803d;--down:#b91c1c;
--soft:#eef3ff;--favbg:#fff8e1;--favink:#8a6500;--shade:rgba(16,26,51,.04);--bannerop:.17}
/* Follow the device unless the visitor picked a theme themselves. */
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){__DARK__}}
:root[data-theme=dark]{__DARK__}
*{box-sizing:border-box}
body{margin:0;position:relative;background:var(--bg);color:var(--ink);font:18px/1.6 ui-rounded,"SF Pro Rounded",Nunito,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}
/* The game's own artwork, faded out behind the top of the page. Decorative only:
   it sits under everything and fades into the page colour, so text stays readable
   in both themes. The sticky header is see-through, so it picks the colour up too. */
.banner{position:absolute;top:0;left:0;right:0;height:360px;z-index:0;overflow:hidden;pointer-events:none}
.banner img{width:100%;height:100%;object-fit:cover;object-position:center 32%;
filter:blur(7px) saturate(1.2);transform:scale(1.1);opacity:var(--bannerop)}
.banner::after{content:"";position:absolute;inset:0;
background:linear-gradient(to bottom,transparent 0,transparent 32%,var(--bg) 97%)}
.shell{position:relative;z-index:1}   /* keep the page content above the artwork */
.w{max-width:820px;margin:0 auto;padding:8px 16px 56px}
.w.wide{max-width:1400px}
/* The page sits in the middle with a column either side kept for ads, the way most
   game-value sites lay out. The side columns only appear on wide screens, and only
   when there is something to put in them. */
.shell{display:grid;grid-template-columns:minmax(0,1fr);justify-content:center}
.rail{display:none}
.railb{display:none}
.shell.ads{gap:20px}
@media(min-width:1480px){.shell.ads{grid-template-columns:168px minmax(0,1fr) 168px}
.shell.ads .rail{display:block;position:sticky;top:124px;align-self:start;height:600px;overflow:hidden}}
/* The strip along the bottom only exists at all when ads are switched on. */
@media(min-width:900px){.railb{display:block;position:sticky;bottom:0;z-index:8;
background:var(--glass);backdrop-filter:blur(10px);border-top:1px solid var(--line);
padding:6px;text-align:center;height:98px}}
.adbox{width:100%;height:100%;border:1px dashed var(--line);border-radius:12px;color:var(--mut);
display:grid;place-items:center;font-size:.8rem;background:var(--shade);text-align:center;padding:8px}
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
.hdr .in{max-width:1400px;margin:0 auto;padding:6px 16px 0}
.hrow{display:flex;align-items:center;gap:10px}
.hrow .gap{flex:1 1 auto}
.acct{display:flex;align-items:center;gap:8px;font-size:.88rem;min-height:30px}
.acct form{margin:0}
.acct .who{color:var(--mut);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.acct .signin{padding:6px 13px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;font-weight:600;white-space:nowrap}
.acct .signin:hover{border-color:var(--acc)}
.acct .linkish{font:inherit;background:none;border:0;color:var(--mut);cursor:pointer;text-decoration:underline;padding:4px}
.logo{display:flex;align-items:center;gap:8px;font-weight:800;font-size:1.2rem;color:var(--ink);text-decoration:none;letter-spacing:-.02em;white-space:nowrap}
.logo .mark{width:30px;height:30px;flex:none}
.logo b{background:linear-gradient(95deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
@media(max-width:560px){.logo .wordmark{display:none}}
/* the game switcher, top left */
.gpick{position:relative}
.gpick>button{display:flex;align-items:center;gap:7px;max-width:210px;padding:5px 10px;border-radius:999px;
border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;font-size:.9rem;font-weight:700}
.gpick>button:hover{border-color:var(--acc)}
.gpick img,.gpick .ph{width:22px;height:22px;border-radius:6px;flex:none;object-fit:cover;background:var(--line);font-size:.8rem}
.gpick .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gpick .caret{color:var(--mut);flex:none;font-size:.7rem}
.gmenu{position:absolute;left:0;top:calc(100% + 6px);min-width:252px;max-width:84vw;background:var(--card);
border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);padding:6px;z-index:20}
.gmenu[hidden]{display:none}
.gmenu p{margin:7px 10px 4px;font-size:.74rem;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.gmenu a{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:10px;text-decoration:none;color:var(--ink);font-size:.92rem}
.gmenu a:hover,.gmenu a:focus-visible{background:var(--shade)}
.gmenu a img,.gmenu a .ph{width:26px;height:26px;border-radius:7px;flex:none;object-fit:cover;background:var(--line);font-size:.9rem}
.gmenu .all{border-top:1px solid var(--line);margin-top:4px;padding-top:9px;font-weight:700;color:var(--acc)}
/* round icon button on the right of the header */
.iconb{display:grid;place-items:center;width:38px;height:38px;flex:none;border-radius:999px;
border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;padding:0}
.iconb:hover{border-color:var(--acc)}
.iconb svg{width:18px;height:18px;fill:currentColor}
.iconb .moon{display:none}
:root[data-theme=dark] .iconb .moon{display:block}
:root[data-theme=dark] .iconb .sun{display:none}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]) .iconb .moon{display:block}
:root:not([data-theme=light]) .iconb .sun{display:none}}
/* grid or list */
.vtog{display:inline-flex;gap:2px;padding:3px;border:1px solid var(--line);border-radius:11px;background:var(--card)}
.vtog button{display:grid;place-items:center;width:34px;height:30px;border:0;border-radius:8px;background:none;color:var(--mut);cursor:pointer;padding:0}
.vtog button svg{width:16px;height:16px;fill:currentColor}
.vtog button[aria-pressed=true]{background:var(--acc);color:#fff}
.rowhead{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:24px}
.rowhead h2{margin:0}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
:root[data-view=list] .grid{grid-template-columns:minmax(0,1fr);gap:8px}
:root[data-view=list] .tile{display:flex;align-items:center;gap:14px;padding:8px 12px;background:var(--card);
border:1px solid var(--line);border-radius:13px}
:root[data-view=list] .tile:hover{border-color:var(--acc)}
:root[data-view=list] .thumb{width:52px;height:52px;flex:none;border-radius:10px}
:root[data-view=list] .tile:hover .thumb{transform:none;box-shadow:none}
:root[data-view=list] .ph{font-size:1.4rem}
:root[data-view=list] .tname{-webkit-line-clamp:1;margin:0;flex:1 1 auto;min-width:0}
:root[data-view=list] .tmeta{margin:0;flex:none}
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
.note{border:1px solid var(--acc);border-radius:14px;padding:12px 15px;margin:12px 0;
background:var(--card);font-size:.95rem;line-height:1.5;box-shadow:var(--sh)}
.back{display:inline-flex;align-items:center;gap:6px;margin:4px 0 2px;padding:7px 13px;border-radius:999px;
border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;
font-size:.9rem;font-weight:600}
.back:hover{border-color:var(--acc)}
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
.fav[aria-pressed=true]{border-color:#e0a800;color:var(--favink);background:var(--favbg)}
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

CSS = CSS.replace("__DARK__", DARK)

ROBOTS = '<meta name="robots" content="noindex,nofollow">' if NOINDEX else ""

# The logo: a timer ring with a play button inside. Drawn in the page rather than
# loaded as a picture, so it is sharp at any size and needs no extra request.
# favicon.svg is the same drawing on its own.
def logo_svg(cls="mark", ident="lg"):
    return (f'<svg class="{cls}" viewBox="0 0 32 32" aria-hidden="true">'
            f'<defs><linearGradient id="{ident}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="#2563eb"/><stop offset="1" stop-color="#7c3aed"/>'
            f'</linearGradient></defs>'
            f'<circle cx="16" cy="16" r="15" fill="url(#{ident})"/>'
            f'<circle cx="16" cy="16" r="11" fill="none" stroke="#fff" stroke-opacity=".55" '
            f'stroke-width="2" stroke-linecap="round" stroke-dasharray="52 69" '
            f'transform="rotate(-90 16 16)"/>'
            f'<path d="M13.4 11.2 21.6 16l-8.2 4.8z" fill="#fff"/></svg>')


FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           + logo_svg(cls="", ident="f").split(">", 1)[1])

SUN = ('<svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.6"/>'
       '<path d="M12 1.6v3.1m0 14.6v3.1M4.6 4.6l2.2 2.2m10.4 10.4 2.2 2.2M1.6 12h3.1m14.6 0h3.1'
       'M4.6 19.4l2.2-2.2M17.2 6.8l2.2-2.2" stroke="currentColor" stroke-width="2" '
       'stroke-linecap="round" fill="none"/></svg>')
MOON = ('<svg class="moon" viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M21 14.2A9.2 9.2 0 1 1 9.8 3 7.4 7.4 0 0 0 21 14.2z"/></svg>')
ICON_GRID = ('<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="1" width="6" height="6" rx="1.6"/>'
             '<rect x="9" y="1" width="6" height="6" rx="1.6"/><rect x="1" y="9" width="6" height="6" rx="1.6"/>'
             '<rect x="9" y="9" width="6" height="6" rx="1.6"/></svg>')
ICON_LIST = ('<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="2" width="14" height="3" rx="1.4"/>'
             '<rect x="1" y="6.5" width="14" height="3" rx="1.4"/><rect x="1" y="11" width="14" height="3" rx="1.4"/></svg>')

# Runs before anything is drawn, so the page never flashes the wrong theme or view.
BOOT = ("<script>try{var d=document.documentElement,t=localStorage.getItem('pt_theme');"
        "if(t)d.setAttribute('data-theme',t);"
        "d.setAttribute('data-view',localStorage.getItem('pt_view')==='list'?'list':'grid')}"
        "catch(e){document.documentElement.setAttribute('data-view','grid')}</script>")

# Counts one page view. No cookies, no login, nothing about the visitor is stored.
HIT = ('<script>try{fetch("/api/hit",{method:"POST",headers:{"content-type":"text/plain"},'
       'body:location.pathname,keepalive:true})}catch(e){}'
       # Then measure how long the page is actually being looked at, and send the
       # total once, as the visitor leaves. Nothing identifying is sent.
       '(function(){var seen=0,since=document.hidden?0:Date.now(),sent=false;'
       'function stop(){if(since){seen+=Date.now()-since;since=0}}'
       'function start(){if(!since)since=Date.now()}'
       'document.addEventListener("visibilitychange",function(){document.hidden?stop():start()});'
       'function send(){if(sent)return;stop();var s=Math.round(seen/1000);'
       'if(s<1||s>3600)return;sent=true;'
       'try{navigator.sendBeacon("/api/time",location.pathname+"|"+s)}catch(e){}}'
       'addEventListener("pagehide",send);'
       'document.addEventListener("visibilitychange",function(){if(document.hidden)send()})})();'
       '</script>')

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


# Where ads go once AdSense is approved. The side columns and the strip along the
# bottom only exist when ADS is filled in, so the live site is not covered in empty
# boxes while we wait. A preview build shows them outlined, so the shape is visible.
SHOW_RAILS = bool(ADS) or OUT != "docs"


def ad_rail(where):
    """An empty, correctly sized box for an ad. The AdSense loader goes in the page head
    once (the ADS setting); these are only the places an ad may appear, so the script is
    never repeated here. Until ADS is filled in, previews outline them and the live site
    leaves them out entirely."""
    if not SHOW_RAILS:
        return ""
    cls = "railb" if where == "bottom" else "rail"
    inner = "" if ADS else f'<div class="adbox">Ad space<br>({where})</div>'
    return f'<aside class="{cls}" id="ad-{where}" aria-hidden="true">{inner}</aside>'


def banner_html(url, name=""):
    """The game's wide artwork, faded out behind the top of the page. Decorative, so it
    is hidden from screen readers and left out entirely when Roblox has no picture."""
    if not url:
        return ""
    return (f'<div class="banner" aria-hidden="true"><img src="{html.escape(url)}" alt="" '
            f'decoding="async" fetchpriority="low"></div>')


def back_link(href="/", label="All games"):
    """A back button at the top of a page. It just says "Back"; the label only
    describes where it lands, for screen readers and the hover tooltip.

    The href is a real link, so it works without JavaScript and gives someone
    arriving from Google somewhere to go; if the visitor came from elsewhere on
    the site, a small script turns it into a true Back instead, returning them
    to their place in the list."""
    where = f"Back to {html.escape(label.lower())}"
    return f'<a class="back" href="{href}" data-back aria-label="{where}" title="{where}">&larr; Back</a>'


def page(title, body, desc="", wide=False, nav="", tail="", banner="", back=("/", "All games")):
    tabs = "".join(f'<a href="{u}"{" aria-current=page" if k == nav else ""}>{html.escape(t)}</a>'
                   for k, t, u in TABS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}"><meta name="theme-color" content="#2563eb">{ROBOTS}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
{BOOT}<style>{CSS}</style><script>{FAVJS}</script>{ADS}</head><body>
{banner_html(banner)}<header class="hdr"><div class="in"><div class="hrow">
<a class="logo" href="/">{logo_svg()}<span class="wordmark">Play<b>Time</b></span></a>
<div class="gpick" id="gpick"></div><div class="gap"></div>
<button class="iconb" id="themebtn" type="button" aria-label="Switch between light and dark">{SUN}{MOON}</button>
<div class="acct" id="acct"></div></div>
<nav class="tabs" aria-label="Sections">{tabs}</nav></div></header>
<div class="shell{' ads' if SHOW_RAILS else ''}">{ad_rail('left')}
<div class="w{' wide' if wide else ''}">{back_link(*back) if back else ''}{body}
<footer class="foot"><nav class="small"><a href="/">All games</a><a href="/trending.html">Trending</a>
<a href="/events.html">Events</a><a href="/compare.html">Compare</a><a href="/plan.html">Plan a session</a>
<a href="/about.html">About</a><a href="/privacy.html">Privacy Policy</a><a href="/terms.html">Terms</a></nav>
<p class="mut small">Not affiliated with or endorsed by Roblox Corporation. Based on public player counts, so it
shows when people play, not whether a game is good or safe.</p></footer>
</div>{ad_rail('right')}</div>{ad_rail('bottom')}
{tail}<script>{CHROME_JS}</script>{HIT}</body></html>"""


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


def view_toggle():
    """The grid/list switch. Grid is the default; the choice is remembered per browser
    and applies to every list of games on the site, because it only sets an attribute
    on the page that the stylesheet reads."""
    return ('<div class="vtog" role="group" aria-label="How to show the games">'
            f'<button type="button" data-v="grid" aria-pressed="true" title="Grid">{ICON_GRID}'
            '<span class="sr">Grid</span></button>'
            f'<button type="button" data-v="list" aria-pressed="false" title="List">{ICON_LIST}'
            '<span class="sr">List</span></button></div>')


def ask_html(lede="Showing the most popular games first."):
    """The busy / quiet / just-browsing chooser. Used on the homepage and on every
    category page, where it narrows that category only."""
    return ('<h2 style="margin-top:22px">What are you looking for?</h2>'
            '<div class="ask" id="ask">'
            '<button class="chip" data-w="busy" aria-pressed="false"><b>Busy right now</b>'
            '<i>Trading, full servers, live events</i></button>'
            '<button class="chip" data-w="quiet" aria-pressed="false"><b>Quiet right now</b>'
            '<i>Claim events, no queues, less lag</i></button>'
            '<button class="chip" data-w="" aria-pressed="true"><b>Just browsing</b>'
            '<i>Show the most popular games</i></button></div>'
            '<div id="asknote" class="note" hidden></div>'
            f'<p id="asktxt" class="mut small">{lede}</p>')


def ask_js(cards, grid_id="all"):
    """The script behind ask_html(), pointed at one grid of games."""
    data = [{"s": c["slug"], "n": c["name"], "i": c["icon"] or "", "a": c["avg"], "l": c["levels"]}
            for c in cards]
    return (f'<script>{SHARED_JS}</script><script>'
            + HOME_JS.replace("__GAMES__", jsdata(data)).replace("__GRID__", grid_id)
            + '</script>')


def row_head(title, extra=""):
    """The bar that sits above every grid of games: a heading on the left, the
    count and the grid/list switch on the right. Pass an empty title on pages
    whose <h1> already names the list, so it is not said twice."""
    return (f'<div class="rowhead">{f"<h2>{title}</h2>" if title else "<span></span>"}'
            f'<div class="actions" style="margin:0">{extra}{view_toggle()}</div></div>')


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
    # The rhythm line is filled in by the page itself, in the visitor's timezone.
    return (f'<div class="card"><h2>Recent updates and changes</h2>'
            f'<p id="pattern" class="mut small"></p>{"".join(parts)}</div>')


def update_pattern(events, spikes, now):
    """When this game's updates usually land, or None if there is not enough history.

    Creators put their updates on Roblox's own event calendar, so the start times of
    past events show each game's rhythm: plenty of them ship every week on the same
    afternoon. Days we spotted a jump in players count too, but only towards the
    weekday, because a jump is measured over a whole day and has no useful hour.

    Returns the weekday and hour in UTC. The page turns them into the visitor's own
    timezone, the same as every other time on the site.
    """
    past = sorted(e["start"] for e in (events or []) if e["start"] < now)
    at = lambda t: datetime.fromtimestamp(t, timezone.utc)
    weekdays = [at(t).weekday() for t in past] + [at(d).weekday() for d, _ in spikes]
    if len(weekdays) < 8:                 # too little history to call it a habit
        return None
    wd = max(set(weekdays), key=weekdays.count)
    if weekdays.count(wd) / len(weekdays) < 0.3:    # no day stands out, so claim nothing
        return None

    # Only name an hour if one really repeats, instead of whichever happened most by luck.
    hours = [at(t).hour for t in past if at(t).weekday() == wd]
    hour = max(set(hours), key=hours.count) if hours else None
    if hour is not None and hours.count(hour) < max(3, 0.3 * len(hours)):
        hour = None

    # Only claim "every N days" from several gaps that are short enough to be a schedule.
    gaps = [g for g in (round((b - a) / 86400) for a, b in zip(past, past[1:])) if g > 0]
    every = None
    if len(gaps) >= 4:
        med = statistics.median(gaps)
        if med <= 31:
            every = int(med)
    return {"wd": wd, "hour": hour, "every": every, "n": len(weekdays)}


def similar(card, cards, n=6):
    """The games most like this one: same category first, then closest in size.

    "Similar" means somewhere else you might go instead, so category matters most and
    size second: a game with a million players and one with a thousand feel nothing
    alike even when they are both tycoons. Size is compared on a log scale, so 1K
    against 2K counts as the same sort of gap as 100K against 200K.
    """
    others = [c for c in cards if c["slug"] != card["slug"]]
    mine = max(card["avg"], 1)

    def rank(c):
        same_genre = not (card["genre"] and c["genre"] == card["genre"])
        return (same_genre, abs(math.log(max(c["avg"], 1)) - math.log(mine)))

    return sorted(others, key=rank)[:n]


def similar_html(card, cards):
    picks = similar(card, cards)
    if len(picks) < 2:
        return ""                         # one lonely suggestion is not worth a heading
    same = sum(1 for c in picks if card["genre"] and c["genre"] == card["genre"])
    note = (f'Other {html.escape(card["genre"].lower())} games with about as many players.'
            if same >= len(picks) - 1 else
            "Games with about as many players, so they feel similar to play.")
    # Deliberately not inside a card: a padded box would make these tiles smaller
    # than the same tiles everywhere else on the site.
    return (row_head("Similar games") +
            f'<p class="mut small" style="margin-top:-4px">{note}</p>{grid(picks)}')


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
var MAXFAVS=200;   /* must match MAX_FAVS in worker/auth.js, or the two drift apart */
function getFavs(){if(PT.favs)return PT.favs;
try{return JSON.parse(localStorage.getItem('pt_favs'))||[]}catch(e){return[]}}
function setFavs(f){f=f.slice(0,MAXFAVS);PT.favs=f;
try{localStorage.setItem('pt_favs',JSON.stringify(f))}catch(e){}
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
if(d.signedIn){var server=(d.favs||[]).slice(),joined=null;
/* who is null if an older worker is still answering, which just means we merge again. */
var who=d.id?String(d.id):null;
try{joined=localStorage.getItem('pt_joined')}catch(e){}
if(who&&joined===who){
/* This device has already given its list to this account, so the account wins.
   Otherwise un-saving a game here would come back from an older list elsewhere. */
PT.favs=server;try{localStorage.setItem('pt_favs',JSON.stringify(server))}catch(e){}}
else{
/* First sign-in on this device: keep anything saved before signing in. */
var all=server.slice();
getFavs().forEach(function(s){if(all.indexOf(s)<0)all.push(s)});
all=all.slice(0,MAXFAVS);PT.favs=all;
try{localStorage.setItem('pt_favs',JSON.stringify(all));
if(who)localStorage.setItem('pt_joined',who)}catch(e){}
if(all.length!==server.length)setFavs(all)}}
ptPaint()}).catch(function(){});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ptPaint);
/* Back buttons: a real link, but if the visitor came from one of our own pages,
   go back properly so they land where they were in the list. */
document.addEventListener('click',function(e){
var a=e.target.closest&&e.target.closest('[data-back]');if(!a)return;
if(history.length>1&&document.referrer.indexOf(location.origin+'/')===0){
e.preventDefault();history.back()}});"""

FAV_GAME = """
(function(){var b=document.getElementById('fav'),k=b.dataset.s;
function draw(){var on=getFavs().indexOf(k)>-1;b.setAttribute('aria-pressed',on);
b.innerHTML=on?'&#9733; Saved':'&#9734; Save'}
b.onclick=function(){var f=getFavs();f=f.indexOf(k)>-1?f.filter(function(x){return x!==k}):f.concat(k);
setFavs(f);draw()};PT.ready(draw)})();"""

# The header controls: theme, grid/list, and the game switcher. On every page.
# Everything it remembers lives only in this browser and is never sent anywhere.
CHROME_JS = """(function(){
var d=document.documentElement;

/* Light and dark. Starts on whatever the device prefers; once the button is pressed
   that choice is remembered and wins from then on. */
function theme(){return d.getAttribute('data-theme')||
(window.matchMedia&&matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light')}
var tb=document.getElementById('themebtn');
if(tb){tb.onclick=function(){var next=theme()==='dark'?'light':'dark';
d.setAttribute('data-theme',next);try{localStorage.setItem('pt_theme',next)}catch(e){}
tb.setAttribute('aria-label',next==='dark'?'Switch to light mode':'Switch to dark mode')}}

/* Grid or list. One attribute on the page, so every list of games follows it. */
window.ptView=function(v){d.setAttribute('data-view',v);
try{localStorage.setItem('pt_view',v)}catch(e){}
Array.prototype.forEach.call(document.querySelectorAll('.vtog button'),function(b){
b.setAttribute('aria-pressed',b.dataset.v===v)})};
Array.prototype.forEach.call(document.querySelectorAll('.vtog button'),function(b){
b.setAttribute('aria-pressed',b.dataset.v===d.getAttribute('data-view'));
b.onclick=function(){ptView(b.dataset.v)}});

/* Games you looked at recently, so you can hop between them from any page. */
function recent(){try{return JSON.parse(localStorage.getItem('pt_recent'))||[]}catch(e){return[]}}
window.ptSeen=function(g){if(!g||!g.s)return;
var list=recent().filter(function(x){return x&&x.s!==g.s});
list.unshift(g);try{localStorage.setItem('pt_recent',JSON.stringify(list.slice(0,8)))}catch(e){}};

var box=document.getElementById('gpick');if(!box)return;
function pic(g,cls){return g.i?'<img src="'+ptEsc(g.i)+'" alt="" width="26" height="26" loading="lazy">'
:'<span class="ph '+(cls||'')+'" aria-hidden="true">'+ptEsc((g.n||'?').charAt(0).toUpperCase())+'</span>'}
var here=window.PT_GAME||null,list=recent();
if(here){ptSeen(here);list=recent()}
var others=list.filter(function(g){return !here||g.s!==here.s});
var label=here?pic(here)+'<span class="nm">'+ptEsc(here.n)+'</span>':
'<span class="nm">Pick a game</span>';
box.innerHTML='<button type="button" id="gbtn" aria-expanded="false" aria-haspopup="true">'+
label+'<span class="caret">&#9660;</span></button><div class="gmenu" id="gmenu" hidden></div>';
var btn=document.getElementById('gbtn'),menu=document.getElementById('gmenu');
menu.innerHTML=(others.length?'<p>Recently viewed</p>'+others.map(function(g){
return '<a href="/game/'+ptEsc(g.s)+'.html">'+pic(g)+'<span class="nm">'+ptEsc(g.n)+'</span></a>'}).join(''):
'<p>No games opened yet</p>')+'<a class="all" href="/">Browse all games</a>';
function open(on){menu.hidden=!on;btn.setAttribute('aria-expanded',on?'true':'false')}
btn.onclick=function(e){e.stopPropagation();open(menu.hidden)};
document.addEventListener('click',function(e){if(!box.contains(e.target))open(false)});
document.addEventListener('keydown',function(e){if(e.key==='Escape')open(false)});
})();"""

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
/* A gap in time for a ticking clock, e.g. "2h 14m 07s". Seconds are only padded when
   a bigger unit is next to them, so a short wait reads as "9s" and not "09s". */
function ticker(ms){var s=Math.max(0,Math.round(ms/1000));
var d=Math.floor(s/86400);
if(d)return d+' day'+(d>1?'s':'')+' '+Math.floor(s%86400/3600)+'h';
var h=Math.floor(s/3600),m=Math.floor(s%3600/60),ss=s%60;
if(h)return h+'h '+(m<10?'0':'')+m+'m '+(ss<10?'0':'')+ss+'s';
if(m)return m+'m '+(ss<10?'0':'')+ss+'s';
return ss+'s'}"""

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

/* Plan my session: a live countdown to the next quiet or busy stretch.
   plan() works out which hour we are aiming at; tick() only rewrites the clock, so the
   digits can move every second without redoing the maths. */
var mode='quiet',aim=null;
function plan(){
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.setAttribute('aria-pressed',b.dataset.m===mode)});
var p=nextBlock(L,mode);
if(!p){aim=null;$('cdw').hidden=true;
$('plantxt').textContent='Not enough player counts yet to work out the next '+
(mode==='quiet'?'quiet':'busy')+' stretch.';return}
aim=new Date(p.t);aim.setMinutes(0,0,0);
$('cdlab').textContent=(mode==='quiet'?'Quietest':'Busiest')+' window starts in';
$('plantxt').innerHTML='That is <b>'+DAY[(aim.getDay()+6)%7]+' at '+fmt(aim.getHours())+
'</b> your time, when it is usually <b>'+W[B.level(p.v)]+'</b> with about '+
p.v.toLocaleString()+' players. It stays that way for about <b>'+p.len+
' hour'+(p.len>1?'s':'')+'</b>.';
$('cdw').hidden=false;tick()}
function tick(){if(!aim)return;
var ms=aim-new Date();
if(ms<=0){plan();return}      /* the window has arrived: work out the one after it */
$('cd').textContent=ticker(ms)}
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.onclick=function(){mode=b.dataset.m;plan()}});
plan();setInterval(tick,1000);setInterval(plan,300000);

/* When this game's updates usually land, worked out from the creators' own event
   dates. Written here rather than on the server so it reads in the visitor's timezone. */
var P=__PATTERN__;
if(P&&$('pattern')){var pd=P.wd,ph=P.hour,every=P.every?
', about every '+P.every+' day'+(P.every>1?'s':''):'';
if(ph!=null){var pt=ph+tzOff();
while(pt<0){pt+=24;pd=(pd+6)%7}while(pt>=24){pt-=24;pd=(pd+1)%7}
$('pattern').innerHTML='Updates usually arrive on a <b>'+DAY[pd]+'</b> around <b>'+fmt(pt)+
'</b> your time'+every+'. Worked out from the last '+P.n+' updates and busy days.'}
else $('pattern').innerHTML='Updates usually arrive on a <b>'+DAY[pd]+'</b>'+every+
'. Worked out from the last '+P.n+' updates and busy days.'}

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

/* "What are you looking for?" really does narrow the list: it hides the games that
   are not quiet (or not busy) at this moment in the visitor's timezone, puts the
   best ones first, and tags each with how busy it is now.

   Every game's five levels are worked out from its own week, so "busy" means busy
   for that game. Games mostly get busy at the same times of day, though, so at
   8pm nothing is quiet and at 5am nothing is busy. When nothing matches we show
   the whole list in order instead of an empty page, and say why. */
var all=$('__GRID__'),original=Array.prototype.slice.call(all.children);
var by={};G.forEach(function(g){by[g.s]=g});
var want='',term='';
function lv(li){var g=by[li.dataset.s];return g?g.lv:0}
function fits(l){if(!want)return true;return want==='quiet'?(l>0&&l<=2):(l>=4)}

/* The next hour in the next day when a few games would match, in the visitor's
   own clock. cell is an hour of the week in UTC, so +1 is simply the next hour. */
function nextGood(){
var best=null;
for(var k=1;k<=24;k++){
var c=(cell+k)%168,n=0;
G.forEach(function(g){var l=+g.l.charAt(c);if(l&&fits(l))n++});
/* Three is a decent spread; one is still worth saying while most of the week
   has no readings yet, so take the first of either. */
if(n>=3||(n>=1&&!best)){
var t=new Date(now.getTime()+k*3600000);
var hit={n:n,when:(k<=1?'in about an hour':'around '+fmt(t.getHours())+
(t.getDate()!==now.getDate()?' tomorrow':''))};
if(n>=3)return hit;
best=hit}}
return best}

function refresh(){
Array.prototype.forEach.call(document.querySelectorAll('#ask button'),function(b){
b.setAttribute('aria-pressed',b.dataset.w===want)});

/* Order never changes: biggest player counts first, filtered or not. The grid is
   built in that order, so we only refresh the fade-in stagger. */
original.forEach(function(li,i){li.style.setProperty('--i',Math.min(i,14))});

var fitting=0;
original.forEach(function(li){if(fits(lv(li)))fitting++});
var loose=want&&!fitting;        /* nothing is quiet/busy right now: show them all */

var shown=0;
original.forEach(function(li){
var l=lv(li),ok=(!want||loose||fits(l))&&li.dataset.n.indexOf(term)>-1;
li.hidden=!ok;if(ok)shown++;
var old=li.querySelector('.rnow');if(old)old.remove();
if(want&&l&&ok){var s=document.createElement('span');s.className='rnow';
s.style.cssText='font-weight:700;color:var(--ink)';s.textContent=W[l]+' now';
li.querySelector('.tmeta').appendChild(s)}});

var word=want==='quiet'?'quiet':'busy';

/* Nothing matching is a real answer, not a broken page, so say so clearly and
   say when it changes. Games get busy at roughly the same times, so at 8pm
   nothing is quiet and at 5am nothing is busy. */
var note=$('asknote');
if(note){
if(loose){
var nx=nextGood();
note.innerHTML='<b>Nothing is '+word+' right now.</b> '+
(nx?('Try again <b>'+nx.when+'</b>, when about '+nx.n+' game'+(nx.n===1?'':'s')+
' should be '+word+'. Meanwhile here is '):
('At this hour nearly every game is '+(want==='quiet'?'busy':'quiet')+
'. Here is '))+
'every game we track, most popular first.';
note.hidden=false}
else note.hidden=true}

$('asktxt').textContent=!want?'Showing the most popular games first.':
loose?'':
term?(shown+' of the '+fitting+' games that are '+word+' right now match your search.'):
(fitting+' game'+(fitting===1?' is':'s are')+' '+word+' right now, most popular first. '+
(want==='quiet'?'Good for claiming event items and avoiding queues.':
'Good for trading, full servers and events.'));
favs()}

Array.prototype.forEach.call(document.querySelectorAll('#ask button'),function(b){
b.onclick=function(){want=(want===b.dataset.w?'':b.dataset.w);refresh()}});

/* Search. Goes through refresh() so searching and filtering cannot fight over
   which games are hidden. */
var s=$('s');if(s)s.oninput=function(){term=s.value.toLowerCase();refresh()};

/* Saved games, pinned to the top. Copies of the tiles, so they must not inherit
   being hidden by a filter. */
function favs(){var fg=$('favgrid');if(!fg)return;fg.innerHTML='';
getFavs().forEach(function(k){
var li=null;original.forEach(function(x){if(x.dataset.s===k)li=x});
if(!li)return;
var c=li.cloneNode(true);c.hidden=c.dataset.n.indexOf(term)<0;
c.style.setProperty('--i',Math.min(fg.children.length,14));fg.appendChild(c)});
var any=false;Array.prototype.forEach.call(fg.children,function(c){if(!c.hidden)any=true});
$('favs').hidden=!any}
PT.ready(favs);
refresh();"""

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

PLAN_JS = """var DATA=null,mode='quiet',aim=null;
function find(s){var r=null;DATA.games.forEach(function(g){if(g.s===s)r=g});return r}
function draw(){
var g=find($('g').value);if(!g)return;
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.setAttribute('aria-pressed',b.dataset.m===mode)});
var L=toLocal(g.m),B=bands(L),p=nextBlock(L,mode);
if(!p){aim=null;
$('out').innerHTML='<p class="none">Not enough player counts for this game yet.</p>';return}
aim=new Date(p.t);aim.setMinutes(0,0,0);
var rows='';for(var i=0;i<12;i++){var t=new Date(new Date().getTime()+i*3600000);
var v=L[(t.getDay()+6)%7][t.getHours()],lv=B.level(v);
rows+='<tr><td><span class="key" style="background:var(--l'+(lv||1)+')"></span>'+
(i?fmt(t.getHours()):'now')+'</td><td>'+(lv?W[lv]:'no data')+'</td></tr>'}
$('out').innerHTML='<span class="mut small">'+(mode==='quiet'?'Quietest':'Busiest')+
' window for '+esc(g.n)+' starts in</span><span class="cd" id="cd">'+ticker(aim-new Date())+
'</span><p>That is '+DAY[(aim.getDay()+6)%7]+' at <b>'+
fmt(aim.getHours())+'</b> your time &ndash; usually <b>'+W[B.level(p.v)]+'</b> with about '+
p.v.toLocaleString()+' players, lasting about <b>'+p.len+' hour'+(p.len>1?'s':'')+'</b>.</p>'+
'<p><a class="btn" href="/game/'+esc(g.s)+'.html">See '+esc(g.n)+'\\u2019s whole week</a></p>'+
'<h3>The next 12 hours</h3><div class="wrap"><table class="tbl"><tr><th>Your time</th>'+
'<th>How busy</th></tr>'+rows+'</table></div>'}
/* Only rewrites the clock, so it can move every second without redoing the maths. */
function tick(){if(!aim)return;var el=$('cd');if(!el)return;
var ms=aim-new Date();
if(ms<=0){draw();return}
el.textContent=ticker(ms)}
fetch('/data.json').then(function(r){return r.json()}).then(function(d){
DATA=d;if(!DATA.games.length){$('load').innerHTML='<p class="none">No games have enough player counts yet.</p>';return}
DATA.games.forEach(function(g){var o=document.createElement('option');o.value=g.s;o.textContent=g.n;
$('g').appendChild(o)});
var p=new URLSearchParams(location.search);if(p.get('g')&&find(p.get('g')))$('g').value=p.get('g');
if(p.get('want')==='busy')mode='busy';
$('g').onchange=draw;
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.onclick=function(){mode=b.dataset.m;draw()}});
$('load').hidden=true;$('plan').hidden=false;draw();
setInterval(tick,1000);setInterval(draw,300000)})
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
<div id="cdw" hidden><span class="mut small" id="cdlab"></span><span class="cd" id="cd"></span></div>
<p id="plantxt"></p></div>
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
__SIMILAR__
<p><a href="/">&larr; All games</a> &middot; <a href="/plan.html?g=__SLUG__">Plan a session</a></p>
<script>window.PT_GAME=__GAMEINFO__;</script>
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
If you are not signed in, it stays there and is never sent to us. Clearing your browser data removes it.</p>
<h2>Cookies</h2>
<p>If you never sign in, <b>we give you no cookies at all</b>. Nothing we store recognises you, and we cannot
tell one visitor from another. (Cloudflare, who host the site, may set its own security cookie to block
attacks; see below.)</p>
<p>If you do sign in with Roblox, we set one cookie so the site remembers it is you on your next visit, and a
second short-lived one that lasts a few minutes while you are being sent to Roblox and back. Both are strictly
necessary for signing in: there is no advertising cookie and no tracking cookie, and neither is shared with
anyone else. Signing out or pressing <b>Delete my data</b> removes them.</p>
<h2>Counting visits</h2>
<p>We count how many times each page is opened, and roughly how many seconds it stays open, so we know which
pages people find useful. We record the page address, the date, and that number of seconds, and nothing else:
no names, no accounts, and nothing that identifies you or your device. The seconds go into one running total
per page, so we cannot tell one visitor from another or follow anyone between pages. This counting uses no
cookies and does not know whether you are signed in.</p>
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

WRITTEN = set()            # every file this build wrote, so stale ones can be cleared at the end


def write(path, text):
    os.makedirs(os.path.dirname(f"{OUT}/{path}") or OUT, exist_ok=True)
    with open(f"{OUT}/{path}", "w", encoding="utf-8") as f:
        f.write(text)
    WRITTEN.add(path.replace("\\", "/"))


def prune(folders=("game", "category")):
    """Deletes pages from an earlier build that this build did not write.

    Pages in these folders are named after the game or category, so without this a
    renamed game, an ID removed from games.txt, or a game dropping below MIN_SAMPLES
    would leave its old page on the live site for ever: unlinked and never updated,
    but still there if you knew the address.

    Deliberately runs last and only in these two generated folders, so a build that
    stops half way never deletes anything, and files you added by hand at the top
    level (ads.txt, a favicon, CNAME) are never touched.
    """
    gone = []
    for folder in folders:
        d = f"{OUT}/{folder}"
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".html") and f"{folder}/{name}" not in WRITTEN:
                os.remove(f"{d}/{name}")
                gone.append(f"{folder}/{name}")
    if gone:
        print(f"Removed {len(gone)} page(s) left over from an earlier build: "
              + ", ".join(gone[:4]) + (" ..." if len(gone) > 4 else ""))
    return gone


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
        # "id" lets the dashboard match these against the collector's live counts.
        "games": [{"id": str(c["uid"]), "name": c["name"], "genre": c["genre"],
                   "slug": c["slug"],          # so the dashboard can match page addresses
                   "samples": c["samples"], "days": c["days"],
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
            + (row_head("", f'<span class="mut small">{len(cards)} '
                            f'game{"s" if len(cards) != 1 else ""}</span>')
               + grid(cards) if cards else
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
    banners = roblox_api.fetch_banners(ids)
    metas = roblox_api.fetch_meta(ids)

    # Categories need at least 2 games to be worth a page ("All" is Roblox's "no genre").
    genre_count = {}
    for g in games:
        genre_count[g[2]] = genre_count.get(g[2], 0) + 1
    cats = {g for g, n in genre_count.items() if g and g != "All" and n >= 2}

    # First pass: work out every game's numbers. The pages are written afterwards,
    # because the "Similar games" row on each one needs to know about all the others.
    cards, waiting = [], []
    for uid, name, genre, place in games:
        rows = db.execute("SELECT ts,playing FROM samples WHERE universe_id=? ORDER BY ts",
                          (uid,)).fetchall()
        if len(rows) < MIN_SAMPLES:
            waiting.append({"id": str(uid), "name": name, "samples": len(rows)})
            continue
        a = analyze(rows)
        cards.append({"name": name, "slug": slug(name), "icon": icons.get(uid), "genre": genre,
                      "avg": a["avg7"], "trend": a["trend"], "month": a["month"],
                      "samples": len(rows), "days": a["days"], "week": a["week"],
                      "levels": levels_string(a["week"]), "verdict": verdict(a)[0],
                      "uid": uid, "place": place, "a": a, "banner": banners.get(uid)})

    cards.sort(key=lambda c: c["avg"], reverse=True)

    # Safety net: a site with no games is never what we want, and publishing one
    # would wipe every page. Usually it means MIN_SAMPLES was raised too early.
    if not cards and games:
        most = max((w["samples"] for w in waiting), default=0)
        raise SystemExit(
            f"\nSTOPPED: no game reached MIN_SAMPLES ({MIN_SAMPLES}), so this build would have\n"
            f"published an empty site and deleted every game page.\n"
            f"The best-covered game has {most} player counts so far.\n"
            f"Lower MIN_SAMPLES in build_site.py, or wait until the games catch up.\n")

    # Second pass: the game pages themselves.
    all_events = []
    for c in cards:
        uid, name, s, a = c["uid"], c["name"], c["slug"], c["a"]
        meta = metas.get(uid)
        events = roblox_api.fetch_events(uid)
        passes = roblox_api.fetch_passes(uid)
        upcoming = [e for e in (events or []) if (e["end"] or e["start"] + 86400) >= now]
        for e in upcoming:
            all_events.append(dict(e, game=name, slug=s, icon=c["icon"]))
        c["events"], c["upcoming"] = len(events or []), len(upcoming)
        vlabel, vcol, vtext = verdict(a)

        play = (f'<a class="btn" href="https://www.roblox.com/games/{c["place"]}">'
                f'Play {html.escape(name)}</a>' if c["place"] and c["place"] > 1 else "")
        cat = (f' Category: <a href="/category/{slug(c["genre"])}.html">{html.escape(c["genre"])}</a>.'
               if c["genre"] in cats else "")
        body = (GAME.replace("__ICON__", thumb(name, c["icon"], f"{name} icon"))
                .replace("__NAME__", html.escape(name))
                .replace("__N__", f'{c["samples"]:,}')
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
                .replace("__SIMILAR__", similar_html(c, cards))
                .replace("__GAMEINFO__", jsdata({"s": s, "n": name, "i": c["icon"] or ""}))
                .replace("__SHARED__", SHARED_JS)
                .replace("__FAVJS__", FAV_GAME)
                .replace("__JS__", GAME_JS.replace("__DATA__", jsdata(a["week"]))
                         .replace("__PATTERN__", jsdata(update_pattern(events, a["spikes"], now)))))
        # Back goes to this game's category when it has one, so the button lands
        # somewhere useful even for a visitor who arrived straight from Google.
        where = ((f'/category/{slug(c["genre"])}.html', f'{c["genre"]} games')
                 if c["genre"] in cats else ("/", "All games"))
        write(f"game/{s}.html", page(
            f"Best Time to Play {name}: Busy and Quiet Hours", body,
            f"When is {name} busiest and quietest? Hourly player counts, upcoming events, "
            f"recent updates, and whether it is growing or dying.", banner=c["banner"], back=where))

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
        count = f'{len(cg)} game{"s" if len(cg) != 1 else ""}'
        write(f"category/{slug(g)}.html", page(
            f"Best Times to Play {g} Games - {SITE}",
            f'<div class="hero"><h1>{html.escape(g)} games</h1><p class="lede">When are popular '
            f'{html.escape(g.lower())} games busiest? Pick one to see its week, its events and its updates.</p></div>'
            + ask_html(f'Showing all {count}, most popular first.')
            + row_head("", f'<span class="mut small">{count}</span>')
            + grid(cg, "all")
            + '<p><a href="/">&larr; All games</a></p>'
            + ask_js(cg),
            f"See when popular {g} games are busiest and quietest, hour by hour.",
            wide=True, banner=cg[0]["banner"]))
    pills = "".join(f'<a href="{u}">{html.escape(g)}</a>' for g, u in cat_pages)

    # ---- homepage
    body = (
        '<div class="hero rise"><h1>When is your game <em>busiest</em>?</h1>'
        '<p class="lede">Hour-by-hour player counts for popular Roblox games, in your own timezone. '
        'Find the quiet hours for easy claims and no queues, or the busy hours for trading and events.</p></div>'
        '<input id="s" type="search" placeholder="Search for a game" aria-label="Search for a game">'
        + ask_html()
        + f'<div class="pills">{pills}</div>'
        '<section id="favs" hidden>' + row_head("Your saved games") +
        '<ul class="grid" id="favgrid"></ul></section>'
        + row_head("All games", f'<span class="mut small">{len(cards)} games</span>')
        + grid(cards, "all")
        + ask_js(cards))
    write("index.html", page(f"{SITE}: Best Times to Play Popular Games", body,
                             "See when popular games are busiest and quietest, hour by hour, in your timezone.",
                             wide=True, nav="home", back=None))   # nowhere to go back to

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
        + row_head("Biggest gainers") + (grid(up[:12]) if up else none) +
        row_head("Biggest losers") + (grid(down[:12]) if down else none)
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
    write("favicon.svg", FAVICON)
    write("robots.txt", "User-agent: *\nDisallow: /\n" if NOINDEX else
          "User-agent: *\nDisallow: /admin\nAllow: /\n" + (f"Sitemap: {base}/sitemap.txt\n" if base else ""))

    write_stats(db, games, cards, waiting)
    prune()                        # last, so a build that fails never deletes anything
    db.close()
    print(f"Wrote {len(urls)} pages into {OUT}/ in {time.time() - started:.0f} seconds.")
    if waiting:
        print(f"{len(waiting)} games are still collecting data and have no page yet.")


if __name__ == "__main__":
    main()
