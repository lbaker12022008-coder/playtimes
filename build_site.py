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
from datetime import datetime, timedelta, timezone

import roblox_api

SITE = "PlayTime"          # the site's name (don't put "Roblox" in your domain name)
MIN_SAMPLES = 200          # how many player counts a game needs before it gets a page
# Set to the launch value on 2 Nov 2026. A game below this keeps no page at all and
# prune() deletes any it had, so lowering it back to 2 is the undo and the pages
# come straight back on the next build - nothing is lost, the readings live on the
# data branch. Each game gains about 71 a day at the current collection rate.
ADS = ""                   # paste your AdSense <script> here
NOINDEX = True             # True = ask Google NOT to list the site (set False when you launch)
OUT = os.environ.get("SITE_OUT") or "docs"   # which folder to write the site into
DOMAIN = ""                # your web address once you buy it, e.g. "https://playtime.gg"
ROBUX_USD = 0.0125         # rough dollars per Robux (800 Robux costs $9.99)
CONTACT = ""               # a contact email for the site (NOT your personal one)
POLICY_DATE = "October 31, 2026"   # change this whenever you edit the Privacy Policy

SPIKE = 1.5                # a day this much busier than normal is "likely an update or event"

# The dark palette, written once and used twice below: once for people whose device
# is set to dark, and once for people who pressed the theme button themselves.
# Colours: the owner's black and neon purple palette. Dark mode is it exactly,
# as supplied: background #0A0A0F, cards #171521, accent #A855F7, secondary
# #C084FC, text #F5F3FF. Light mode is the same idea turned over, so the toggle
# still works: #0A0A0F ink on a faintly purple near-white. Every pair was
# measured against the surface it sits on, not guessed, and all body text clears
# the 4.5 it needs.
#   --acc2 is the supplied secondary, a lighter purple, and it is DECORATIVE:
#   gradients and the edge of a soon-starting event. It is not a data colour.
#   --alt is the data colour, a cyan, and it is a different hue ON PURPOSE. It
#   draws the second game on /compare.html, the second set of bars in the hourly
#   chart and the spike dots on the 45-day line, so it has to be tellable from
#   --acc at a glance. Two purples would make those unreadable, which is exactly
#   why the second series cannot just be the supplied secondary.
#   --btnink is the text on a filled accent button: white in light mode, near
#   black in dark, because white on #A855F7 only reaches 3.96.
#   --l1..--l5 are the heatmap, and they now mean crowding rather than depth:
#   green is quiet, amber is middling, red is busy. Hue alone would not be enough
#   (red-green colourblindness is common, and much of this audience is children),
#   so the perceived lightness ALSO falls in even 7-point steps, L* 88 81 74 67 60.
#   That keeps the bands tellable apart in greyscale. Keep both properties if you
#   ever retune them: scratch a hue and you must re-check the lightness as well.
DARK = """--bg:#0A0A0F;--card:rgba(23,21,33,.82);--solid:#171521;--ink:#F5F3FF;--mut:#A09AB5;--line:#2A2735;
--acc:#A855F7;--acc2:#C084FC;--alt:#22D3EE;--sky:#E9D5FF;--glass:rgba(10,10,15,.86);--btnink:#0A0A0F;
--sh:0 1px 2px rgba(0,0,0,.5),0 10px 30px rgba(0,0,0,.62);
--up:#34D399;--down:#FF7A8A;--soft:#150F24;--favbg:#241739;--favink:#D8B4FE;
--shade:rgba(255,255,255,.06);--bannerop:.3;--glowa:.5"""

# The light palette, named for the same reason DARK is: the admin dashboard is
# served by the worker rather than written here, and theme.js hands it both of
# these so a colour changed here reaches the dashboard too.
LIGHT = """--bg:#F6F4FB;--card:rgba(255,255,255,.8);--solid:#fff;--ink:#0A0A0F;--mut:#595068;
--line:#DDD6E8;--acc:#7E22CE;--acc2:#9333EA;--alt:#0E7490;--sky:#E9D5FF;--btnink:#fff;
--glass:rgba(246,244,251,.86);--sh:0 1px 2px rgba(10,10,15,.07),0 10px 30px rgba(10,10,15,.11);
--l1:#A8EBCB;--l2:#A4D967;--l3:#EEA830;--l4:#EC8A58;--l5:#E26D68;--up:#047857;--down:#B3203F;
--soft:#F3E8FF;--favbg:#F3E8FF;--favink:#6B21A8;--shade:rgba(10,10,15,.05);--bannerop:.14;
--glowh:272;--glowa:.32"""


CSS = """:root{__LIGHT__}
/* Widths only apply once there is room for them. Below 900px every card is full
   width again, because two columns of this on a phone is unreadable. */
@media(min-width:900px){
.bento{gap:18px;margin-top:-30px}   /* pulls the first row up under the heading panel */
.lstack{gap:18px}                   /* must match .bento's gap, or the column looks loose */
.bento>.sp4{grid-column:span 4}.bento>.sp5{grid-column:span 5}
.bento>.sp6{grid-column:span 6}.bento>.sp7{grid-column:span 7}.bento>.sp8{grid-column:span 8}
/* The week grid gets a lot wider on a wide page, so the squares grow with it rather
   than stretching into letterboxes, and it stops short of the full width. */
.hm{max-width:1120px;margin-left:auto;margin-right:auto}
.hm .c{height:32px}
/* The magnifier goes back in the bar once there is room for it, and the panel
   then drops its own search row so the same control is not offered twice. */
.iconb.deskonly{display:grid}
.dtop .drow[data-search]{display:none}
}
/* Follow the device unless the visitor picked a theme themselves. */
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){__DARK__}}
:root[data-theme=dark]{__DARK__}
*{box-sizing:border-box}
body{margin:0;position:relative;background:var(--bg);color:var(--ink);font:18px/1.6 ui-rounded,"SF Pro Rounded",Nunito,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%;overflow-wrap:break-word;overflow-x:clip}
/* overflow-wrap stops one long word dragging the page wider than the phone. The
   text is not ours: creators paste group links into a game's description, and a
   61-character URL is about 430px, which is wider than a card on any phone.
   overflow-x:clip is the net under all of this, in case something new overflows
   one day. It must be clip and not hidden: hidden makes the body a scrolling box,
   which would stop the sticky header sticking. */
/* The game's own artwork, faded out behind the top of the page. Decorative only:
   it sits under everything and fades into the page colour, so text stays readable
   in both themes. The sticky header is see-through, so it picks the colour up too. */
.banner{position:absolute;top:0;left:0;right:0;height:360px;z-index:0;overflow:hidden;pointer-events:none}
.banner img{width:100%;height:100%;object-fit:cover;object-position:center 32%;
filter:blur(7px) saturate(1.2);transform:scale(1.1);opacity:var(--bannerop)}
.banner::after{content:"";position:absolute;inset:0;
background:linear-gradient(to bottom,transparent 0,transparent 32%,var(--bg) 97%)}
.shell{position:relative;z-index:1}   /* keep the page content above the artwork */
.w{max-width:min(820px,100%);margin:0 auto;padding:8px 16px 56px}
.w.wide{max-width:min(1400px,100%)}
/* The page sits in the middle with a column either side kept for ads, the way most
   game-value sites lay out. The side columns only appear on wide screens, and only
   when there is something to put in them. */
.shell{display:grid;grid-template-columns:minmax(0,1fr);justify-content:center}
/* A grid item defaults to min-width:auto, which means it refuses to shrink below
   the widest thing inside it. On a phone that let one wide child drag .w to 1094px
   inside a 390px track, and every page then scrolled sideways. The track is already
   minmax(0,1fr); this is the other half of the same fix. */
/* max-width is the half that actually does the work. .shell centres its track with
   justify-content, and a grid item in a centred track is allowed to grow past the
   track to fit its contents, so one wide child dragged .w to 1347px inside a 390px
   phone and every page scrolled sideways. min-width:0 alone does not stop that. */
.shell>*{min-width:0;max-width:100%}
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
.card,.ghead>div{min-width:0}
.card{background:var(--card);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:18px;padding:18px 20px;margin:16px 0;box-shadow:var(--sh)}
/* The description drawer under the game heading. Its arrow is drawn with two
   borders rather than loaded as a picture, and turns over when the drawer opens. */
.gdesc{position:relative;z-index:2;background:var(--card);backdrop-filter:blur(10px);
-webkit-backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:16px;
box-shadow:var(--sh);margin:0 0 14px}
.gdesc>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:10px;padding:13px 18px}
.gdesc>summary::-webkit-details-marker{display:none}
.gdesc>summary h2{margin:0;font-size:1.03rem}
.gdesc>summary:hover h2,.gdesc[open]>summary h2{color:var(--acc)}
.gdesc>summary::after{content:"";margin-left:auto;flex:none;width:9px;height:9px;
border-right:2.5px solid var(--acc);border-bottom:2.5px solid var(--acc);
transform:translateY(-3px) rotate(45deg);transition:transform .2s}
.gdesc[open]>summary::after{transform:translateY(2px) rotate(225deg)}
.gdesc-in{padding:0 18px 16px}
.gdesc-in>:first-child{margin-top:0}
/* ---- Bento: a page as a grid, not one tall column ---------------------------
   A game page has a dozen sections. Stacked one per row, the last of them is a very
   long way down. Laid out two and three across, a visitor sees several at once.
   Each card keeps its place in the HTML and only its WIDTH changes, so the reading
   order, screen readers and check_seo.py all see exactly what they saw before: the
   grid never reorders anything, which is why there is no grid-auto-flow:dense here.
   Cards keep their own height (align-items:start) rather than stretching to match the
   tallest in the row. What goes in them varies far too much for that: a game with no
   events sits next to a long FAQ, a 7-row table next to a 24-row one, and stretching
   turns the short one into a mostly empty box. The even gaps hold the grid together. */
.bento{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px;margin:0 0 16px;align-items:start}
/* min-width:0 matters: a grid item defaults to min-width:auto, so one wide table
   or long word inside a card could otherwise force the whole grid wider. */
.bento>*{grid-column:1/-1;margin:0;min-width:0}   /* full width by default; the grid owns the spacing */
/* Two short cards sharing one column, so the tall card beside them has something
   to sit against. The grid cannot do this by itself: its rows are rigid, so a card
   shorter than the one next to it simply leaves the space under it empty - "The
   short answer" is 239px tall and "Plan my session" is 735px, which left a 496px
   hole on every game page. A nested column is used rather than grid-row:span 2
   because spanning splits the slack evenly between the rows, which would open an
   arbitrary gap BETWEEN the two cards instead of closing it. Its gap has to be
   kept level with the bento's own, both here and in the wide block above. */
.lstack{display:flex;flex-direction:column;gap:14px}
.lstack>.card{margin:0;min-width:0}
.mut{color:var(--mut)}.small{font-size:.9rem}
.up{color:var(--up)}.down{color:var(--down)}
.wrap{overflow-x:auto}
button,.btn,.chip,select{font:inherit}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
.ans p{margin:.35em 0;font-size:1.1rem}

/* top bar, with the sections across the top */
.hdr{position:sticky;top:0;z-index:9;background:var(--glass);backdrop-filter:saturate(1.4) blur(12px);border-bottom:1px solid var(--line);margin-bottom:6px}
/* One slim bar, about 62px tall, holding four things. */
.hdr .in{max-width:min(1400px,100%);margin:0 auto;padding:11px 20px}
.hrow{display:flex;align-items:center;gap:12px}
.hrow .gap{flex:1 1 auto}
.acct{display:flex;align-items:center;gap:8px;font-size:.88rem;min-height:30px}
.acct form{margin:0}
.acct .who{color:var(--mut);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.acct .signin{padding:6px 13px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;font-weight:600;white-space:nowrap}
.acct .signin:hover{border-color:var(--acc)}
.acct .linkish{font:inherit;background:none;border:0;color:var(--mut);cursor:pointer;text-decoration:underline;padding:4px}
.logo{display:flex;align-items:center;gap:9px;font-weight:800;font-size:1.35rem;color:var(--ink);text-decoration:none;letter-spacing:-.02em;white-space:nowrap}
.logo .mark{width:32px;height:32px;flex:none}
.logo b{background:linear-gradient(95deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
/* Below the width where the row of sections fits, the header is logo, name and
   game picker on the left and the three-line button on the right. Search, theme
   and the account are in the panel that button opens, so they are hidden here
   rather than fighting for the same row. */
/* the game switcher, top left */
.gpick{position:relative;min-width:0}
.gpick>button{display:flex;align-items:center;gap:8px;max-width:240px;min-width:0;padding:8px 13px;border-radius:12px;
border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;font-size:.95rem;font-weight:700}
.gpick>button:hover{border-color:var(--acc)}
.gpick img,.gpick .ph{width:24px;height:24px;border-radius:7px;flex:none;object-fit:cover;background:var(--line);font-size:.8rem}
.gpick .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gpick .caret{color:var(--mut);flex:none;font-size:.7rem}
.gmenu{position:absolute;left:0;top:calc(100% + 6px);min-width:252px;max-width:84vw;background:var(--solid);
border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);padding:6px;z-index:20}
.gmenu[hidden]{display:none}
.gmenu p{margin:7px 10px 4px;font-size:.74rem;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.gmenu a{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:10px;text-decoration:none;color:var(--ink);font-size:.92rem}
.gmenu a:hover,.gmenu a:focus-visible{background:var(--shade)}
.gmenu a img,.gmenu a .ph{width:26px;height:26px;border-radius:7px;flex:none;object-fit:cover;background:var(--line);font-size:.9rem}
.gmenu .all{border-top:1px solid var(--line);margin-top:4px;padding-top:9px;font-weight:700;color:var(--acc)}
/* round icon button on the right of the header */
.iconb{display:grid;place-items:center;width:42px;height:42px;flex:none;border-radius:12px;
border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;padding:0}
.iconb:hover{border-color:var(--acc)}
/* Shown only inside the min-width:900px block near the top of this stylesheet. */
.deskonly{display:none}
.iconb svg{width:19px;height:19px;fill:currentColor}
.themeic .moon{display:none}
:root[data-theme=dark] .themeic .moon{display:block}
:root[data-theme=dark] .themeic .sun{display:none}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]) .themeic .moon{display:block}
:root:not([data-theme=light]) .themeic .sun{display:none}}
/* the side drawer and the search sheet, used on the pages about one game */
.drawer{position:fixed;top:0;right:0;bottom:0;width:260px;max-width:82vw;z-index:30;
background:var(--solid);border-left:1px solid var(--line);box-shadow:var(--sh);
padding:72px 12px 16px;overflow-y:auto;animation:slidein .22s ease both}
.drawer[hidden]{display:none}
/* The panel's top section: the controls that are in the header on a wide screen. */
.dtop{display:flex;flex-direction:column;gap:2px;margin-bottom:10px;padding-bottom:10px;
border-bottom:1px solid var(--line)}
.drow{display:flex;align-items:center;gap:11px;width:100%;padding:11px 13px;border:0;
border-radius:11px;background:none;color:var(--ink);font:inherit;font-weight:600;
text-align:left;cursor:pointer}
.drow:hover,.drow:focus-visible{background:var(--shade)}
.drow svg{width:18px;height:18px;flex:none;fill:currentColor}
.dacct{padding:6px 13px;min-height:0}
.drawer nav{display:flex;flex-direction:column;gap:2px}
.drawer a{padding:11px 13px;border-radius:11px;text-decoration:none;color:var(--ink);font-weight:600}
.drawer a:hover,.drawer a:focus-visible{background:var(--shade)}
.scrim{position:fixed;inset:0;z-index:25;background:rgba(0,0,0,.35)}
.scrim[hidden]{display:none}
@keyframes slidein{from{transform:translateX(100%)}to{transform:none}}
.sheet{position:fixed;inset:0;z-index:30;display:grid;place-items:start center;padding:76px 16px 16px}
.sheet[hidden]{display:none}
.sheetbox{width:min(560px,100%);background:var(--solid);border:1px solid var(--line);
border-radius:16px;box-shadow:var(--sh);padding:12px}
.qout{max-height:50vh;overflow-y:auto;margin-top:8px}
.qout a{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;
text-decoration:none;color:var(--ink)}
.qout a:hover,.qout a:focus-visible{background:var(--shade)}
.qout img,.qout .ph{width:30px;height:30px;border-radius:8px;flex:none;object-fit:cover;background:var(--line)}
.qout p{margin:8px 10px;color:var(--mut);font-size:.9rem}
/* game passes: picture, what it contains, what it costs */
.passes{list-style:none;padding:0;margin:14px 0 6px;display:grid;gap:10px;
grid-template-columns:repeat(auto-fill,minmax(min(290px,100%),1fr))}
.pass{display:flex;gap:12px;padding:11px 13px;border:1px solid var(--line);border-radius:14px;background:var(--shade)}
.pass img,.pass .ph{width:64px;height:64px;flex:none;border-radius:12px;object-fit:cover;
background:var(--line);display:grid;place-items:center;font-weight:800;color:var(--mut);font-size:.95rem}
.pass>div{min-width:0}
.pass b{display:block;line-height:1.25}
.pass p{margin:.3em 0;font-size:.9rem;color:var(--mut);line-height:1.4}
.pass .price{font-weight:700;font-size:.92rem}
.ptag{display:inline-block;font-size:.7rem;font-weight:700;padding:2px 7px;border-radius:999px;
margin:3px 4px 0 0;vertical-align:1px;background:var(--soft);color:var(--acc)}
.ptag.sale{background:#E5AD2A;color:#10131c}
.ptag.cheap{background:var(--sky);color:#10131c}
/* grid or list */
.vtog{display:inline-flex;gap:2px;padding:3px;border:1px solid var(--line);border-radius:11px;background:var(--card)}
.vtog button{display:grid;place-items:center;width:34px;height:30px;border:0;border-radius:8px;background:none;color:var(--mut);cursor:pointer;padding:0}
.vtog button svg{width:16px;height:16px;fill:currentColor}
.vtog button[aria-pressed=true]{background:var(--acc);color:var(--btnink)}
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
/* A scrolling strip is written as a block with nowrap text, never as a nowrap
   flex row: a nowrap flex container hands its parent the total width of its
   items, so the page grows to fit a strip that was supposed to scroll. */
.drawer a[aria-current=page]{background:var(--soft);color:var(--acc)}
.pills{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.pills a{padding:6px 14px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;font-size:.9rem;transition:border-color .12s,box-shadow .18s}
.pills a:hover{border-color:var(--acc)}
.hero h1 em{font-style:normal;background:linear-gradient(95deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}

/* "what are you looking for?" */
.ask{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(min(215px,100%),1fr));margin:14px 0}
.chip{display:block;width:100%;text-align:left;padding:13px 16px;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;box-shadow:var(--sh);transition:transform .12s,border-color .12s,box-shadow .18s}
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

/* A thin rim of light around the two rows of controls above the games, so they
   answer a hover the way a game tile does without being painted like one.
   Deliberately different from the tile glow on both counts:
   - It is a box-shadow, not a blob behind the control, so the light follows the
     border and stops there. A halo the size of the whole chip read as the chip
     changing colour rather than as it lighting up.
   - Every one of them is the accent. A tile borrows the hue of its own icon
     because it HAS one; a category and a question do not, and a different
     colour per category read as decoration pretending to mean something.
   --glowh is the accent's hue and --glowa the strength, both already tuned per
   theme for the tiles, so this stays in step with them. z-index lifts the one
   being pointed at, or the next pill along paints over its light. */
.chip,.pills a{position:relative;
--rim:0 0 0 1px hsl(var(--glowh) 92% 62%/.5),0 0 12px hsl(var(--glowh) 92% 62%/var(--glowa))}
.chip:hover,.chip:focus-visible,.pills a:hover,.pills a:focus-visible{z-index:1}
.chip:hover,.chip:focus-visible{box-shadow:var(--sh),var(--rim)}
.pills a:hover,.pills a:focus-visible{box-shadow:var(--rim)}
/* The chosen chip is marked by its inset ring and does NOT glow on its own: a
   light that is always on stops reading as a response to anything. It still
   lights up while it is the one being pointed at, which needs a rule of its own
   because [aria-pressed=true] and :hover have equal specificity. */
.chip[aria-pressed=true]:hover,.chip[aria-pressed=true]:focus-visible{
box-shadow:inset 0 0 0 2px var(--acc),var(--rim)}

/* game tiles */
.grid{list-style:none;padding:0;margin:14px 0;overflow-x:clip;overflow-y:visible;display:grid;grid-template-columns:repeat(auto-fill,minmax(min(150px,100%),1fr));gap:22px 14px}
.grid>li{animation:up .45s cubic-bezier(.2,.75,.3,1) both;animation-delay:calc(var(--i,0)*28ms)}
.tile{display:block;text-decoration:none;color:var(--ink);position:relative;isolation:isolate}
.thumb{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:cover;border-radius:14px;background:var(--line);transition:transform .15s,box-shadow .15s}
.ph{display:grid;place-items:center;font-size:2.6rem;font-weight:800;color:var(--mut)}
.tile:hover .thumb{transform:translateY(-4px) scale(1.015);
box-shadow:0 10px 24px hsl(var(--glow,var(--glowh)) 75% 38%/.45)}
/* The glow behind a tile is that game's own colour. --glow is the hue of its
   picture, worked out while the site is built (roblox_api.fetch_icon_hues) and
   written onto the tile as a single number; a game whose picture has no colour
   in it never gets one, and falls back to --glowh, the site accent's hue. Only
   the hue is stored, because the saturation and lightness are fixed here: left
   to themselves some icons would glow in a muddy brown and others in a glare.
   isolation:isolate keeps the glow inside the tile's own stack, so z-index:-1
   puts it behind the picture and the words without dropping it behind the page.
   The picture itself is not see-through, so a glow the size of the tile would be
   hidden behind it: this one is half as wide again, centred on the picture, and
   holds full strength to 35% of its radius so that what spills past the edge is
   still bright. :hover lifts the whole tile so its glow is not painted under the
   next tile along. */
.tile:hover,.tile:focus-visible{z-index:2}
.tile::before{content:"";position:absolute;left:50%;top:-25%;width:150%;aspect-ratio:1;
transform:translateX(-50%);z-index:-1;pointer-events:none;border-radius:50%;opacity:0;
transition:opacity .22s ease;
background:radial-gradient(closest-side,hsl(var(--glow,var(--glowh)) 92% 62%/var(--glowa)) 35%,transparent)}
.tile:hover::before,.tile:focus-visible::before{opacity:1}
/* In a list a tile is a wide card, so the glow spreads out of the picture on the
   left rather than sitting as a circle on top of the words. */
:root[data-view=list] .tile::before{left:0;top:0;width:100%;height:100%;aspect-ratio:auto;
transform:none;border-radius:13px;
background:radial-gradient(44% 150% at 38px 50%,hsl(var(--glow,var(--glowh)) 92% 62%/var(--glowa)),transparent 74%)}
.tname{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-weight:700;font-size:.95rem;line-height:1.3;margin-top:8px}
.tmeta{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;font-size:.82rem;color:var(--mut);margin-top:3px}
.tmeta svg{width:14px;height:14px;vertical-align:-2px;fill:currentColor}

/* charts */
.days{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.days button{font-size:.95rem;padding:6px 14px;min-height:44px;border-radius:999px;border:1px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
.days button[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:var(--btnink);font-weight:700}
.bars{margin-top:12px}
/* The compare page still puts two games side by side as columns. */
.bars.cols{display:grid;grid-template-columns:repeat(24,1fr);gap:3px;align-items:end;height:170px}
.graph{width:100%;height:auto;display:block;overflow:visible}
.graph{touch-action:pan-y;cursor:crosshair}
.graph .cursor{transition:opacity .12s}
.readout{min-height:1.6em;margin:.2em 0 0;font-size:1.05rem}
/* Roblox text: names, descriptions, event blurbs, game-pass names. Any of it can
   be a pasted link or an unbroken run of characters, so it may break anywhere. */
.desc,.gdesc-in,.evt b,.evt p,.pass b,.pass p,.tname,.qout a,.gmenu a{overflow-wrap:anywhere}
.bar{border-radius:5px 5px 0 0;min-height:4px;transform-origin:bottom;animation:grow .5s cubic-bezier(.2,.8,.3,1) both;animation-delay:calc(var(--i,0)*11ms)}
.bar.b2{opacity:.72}
.axis{display:grid;grid-template-columns:repeat(24,1fr);font-size:.8rem;color:var(--mut);margin-top:4px}
.axis span{grid-column:span 6}
.hm{display:grid;grid-template-columns:44px repeat(24,minmax(0,1fr));gap:2px;font-size:.8rem;color:var(--mut);align-items:center}
.hm .c{height:26px;border-radius:4px}
.hm .now{outline:2px solid #10131c;outline-offset:-1px;box-shadow:inset 0 0 0 4px rgba(255,255,255,.82)}
.legend{display:flex;align-items:center;gap:4px;font-size:.85rem;color:var(--mut);margin-top:10px;flex-wrap:wrap}
.legend i{width:26px;height:12px;border-radius:3px;display:inline-block}
.spark{width:100%;height:80px;display:block}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(165px,100%),1fr));gap:12px}
.stats b{display:block;font-size:1.5rem}
.key{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:4px}

/* game page */
/* The heading sits on its own glass panel over the game's artwork, and the picture
   lifts out of the top of it, so the page opens with depth instead of two flat things
   stacked. z-index keeps the panel above the cards that tuck up underneath it. */
.ghead{position:relative;z-index:2;display:flex;gap:20px;align-items:center;flex-wrap:wrap;
background:var(--card);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
border:1px solid var(--line);border-radius:20px;box-shadow:var(--sh);padding:20px 22px;margin:48px 0 12px}
.ghead .thumb{width:132px;flex:none;margin-top:-40px;border:3px solid var(--solid);box-shadow:var(--sh)}
.ghead>div{flex:1 1 280px}
.ghead h1{margin:0 0 .2em}.ghead p{margin:.2em 0}
.btn{display:inline-block;background:linear-gradient(95deg,var(--acc),var(--acc2));color:var(--btnink);padding:11px 20px;border-radius:13px;text-decoration:none;font-weight:700;box-shadow:var(--sh)}
.actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:10px}
.fav{font-weight:700;padding:10px 17px;border-radius:13px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.fav[aria-pressed=true]{border-color:var(--acc);color:var(--favink);background:var(--favbg)}
.verdict{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.vbadge{font-size:1.05rem;font-weight:800;padding:8px 16px;border-radius:999px;white-space:nowrap;color:#10131c}
.tbl{width:100%;border-collapse:collapse;font-size:.95rem}
.tbl td,.tbl th{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.tbl td:last-child,.tbl th:last-child{text-align:right;white-space:nowrap}
details summary{cursor:pointer;color:var(--acc);font-weight:700;margin:6px 0}
.desc{white-space:pre-line;margin:.3em 0}
.evt{list-style:none;padding:0;margin:8px 0}
/* "Remind me" is a quiet offer, not a call to action: it sits under the thing it
   is about and only picks up the accent when the pointer is on it. */
/* The day picker: seven boxes that look like the pills elsewhere on the site. The
   real checkbox stays where it is for screen readers and the keyboard and is simply
   not drawn, and the pill beside it follows its state.
   Deliberately "input:checked + span" and not ":has()": a lot of this audience is on
   a handed-down iPad, and :has needs Safari 15.4 while the sibling selector has
   worked for as long as anyone here has been alive. The fieldset stays a block for
   the same sort of reason - a legend inside a flex container lands differently in
   different browsers - and the labels flow as inline blocks instead. */
/* The reminder is its own question, so it is ruled off from the countdown above it
   rather than running on from it. */
.rem{border-top:1px solid var(--line);margin-top:18px;padding-top:14px}
.rem>p:first-child{margin:0 0 8px}
.rem .days{margin:0}
.daypick{border:0;padding:0;margin:12px 0 4px;display:block}
.daypick legend{padding:0;margin-bottom:6px}
.daypick label{cursor:pointer;display:inline-block;margin:0 6px 6px 0}
.daypick input{position:absolute;opacity:0;width:0;height:0}
.daypick span{display:inline-flex;align-items:center;justify-content:center;min-width:46px;
min-height:38px;padding:0 10px;border-radius:999px;border:1px solid var(--line);
background:var(--card);color:var(--mut);font-size:.84rem;font-weight:600}
.daypick input:checked+span{background:var(--acc);border-color:var(--acc);color:var(--btnink)}
.daypick input:focus-visible+span{outline:2px solid var(--acc);outline-offset:2px}
.remind[aria-disabled=true]{opacity:.5;pointer-events:none}
.remind{display:inline-flex;align-items:center;gap:6px;margin-top:8px;padding:8px 14px;
font-size:.85rem;font-weight:600;border-radius:999px;border:1px solid var(--line);
background:var(--card);color:var(--mut);cursor:pointer;text-decoration:none;min-height:40px}
.remind:hover{border-color:var(--acc);color:var(--ink)}
.evt li{border-left:3px solid var(--line);padding:2px 0 2px 14px;margin:16px 0}
.evt li.soon{border-left-color:var(--acc2);background:var(--soft);border-radius:0 10px 10px 0;padding:8px 12px 8px 14px}
.evt li.live{border-left-color:var(--up)}
.evt b{display:block}
.evt .d{font-size:.85rem;color:var(--mut)}
.evt p{margin:.3em 0;font-size:.95rem;white-space:pre-line}
.cd{font-size:1.4rem;font-weight:800;display:block;margin:.1em 0}
.sel{padding:10px 13px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--ink);max-width:100%}
.two{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr))}
input[type=search]{width:100%;padding:13px 17px;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--ink);box-shadow:var(--sh);font:inherit}
.foot{border-top:1px solid var(--line);margin-top:36px;padding-top:12px}
.foot nav{display:flex;flex-wrap:wrap;gap:6px 18px;margin-bottom:6px}
.doc h2{margin-top:1.4em}.doc ul{padding-left:1.2em}
.none{color:var(--mut)}
/* The breadcrumb trail. Small and muted, so it tells search engines (and anyone
   who landed from Google) where the page sits without shouting. */
.topnav{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:4px 0 2px}
.topnav .back{margin:0}
.crumbs{font-size:.84rem;color:var(--mut);margin:0;display:flex;flex-wrap:wrap;gap:4px 7px;align-items:center;min-width:0}
.crumbs a{color:var(--mut);text-decoration:none;border-bottom:1px solid var(--line)}
.crumbs a:hover{color:var(--acc);border-bottom-color:var(--acc)}
.crumbs span[aria-current]{color:var(--ink);font-weight:600}
/* The facts list under each game's heading. Written into the page by the builder,
   not by the browser, so a search engine reads the numbers without running any code. */
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(190px,100%),1fr));gap:12px 18px;margin:10px 0 0}
.facts div{min-width:0}
.facts dt{font-size:.85rem;color:var(--mut)}
.facts dd{margin:1px 0 0;font-weight:700;font-size:1.1rem}
/* The hour-by-hour table, kept inside a <details> so it does not crowd the page.
   Collapsed text is still read by search engines, and it works with no JavaScript. */
.hourtbl{font-size:.8rem;border-collapse:collapse;min-width:620px}
.hourtbl th,.hourtbl td{padding:3px 5px;border:1px solid var(--line);text-align:right;white-space:nowrap}
.hourtbl th:first-child,.hourtbl td:first-child{text-align:left;font-weight:700}
.hourtbl thead th{color:var(--mut);font-weight:600}
.faq h3{margin:1.1em 0 .1em;font-size:1.02rem}
.faq p{margin:.2em 0 .7em}

/* ---- phones ---------------------------------------------------------------
   Everything above is written as though there is room. A phone has about a
   quarter of the width, so anything that sat side by side stacks up and the page
   becomes a long column of half-empty boxes, which is what made it feel
   cluttered. These rules do not hide anything: they tighten the padding and put
   the rows of buttons back into single rows, so more of the screen is the answer
   the visitor came for. Add new phone rules here rather than in a new block, so
   there is one place to look. */
@media(max-width:620px){
body{font-size:17px}
.w{padding:6px 14px 48px}
.card{padding:14px 15px;margin:12px 0;border-radius:15px}
h2{font-size:1.06rem}
.lede{font-size:1rem}
.rowhead{margin-top:18px}
/* the same four things, a little tighter, so the bar is not a third of the screen */
.hdr .in{padding:8px 14px}
.iconb{width:38px;height:38px}
.hrow{gap:9px}
.logo{font-size:1.2rem}
.logo .mark{width:29px;height:29px}
.gpick>button{max-width:150px;padding:7px 11px}
/* two games across even on the narrowest phone, with less air between them */
.grid{gap:15px 10px;grid-template-columns:repeat(auto-fill,minmax(min(132px,100%),1fr));margin:12px 0}
/* busy / quiet / browsing becomes one row of three. The line under each one goes:
   there is no room for it, and the heading above already asks the question. */
.ask{grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0}
.chip{padding:9px 7px;text-align:center;border-radius:12px;box-shadow:none}
/* The chips drop their shadow on a phone, so the rim must not quietly hand it
   back on a tap - a tap leaves :hover stuck on in most mobile browsers. */
.chip:hover,.chip:focus-visible{box-shadow:var(--rim)}
.chip i{display:none}
.chip b{font-size:.84rem;line-height:1.25}
/* the categories become one sideways row instead of five stacked ones */
.pills{display:block;white-space:nowrap;overflow-x:auto;scrollbar-width:none;margin:0 -14px;padding:12px 14px}
.pills::-webkit-scrollbar{display:none}
.pills a{display:inline-block;margin-right:8px}
.pills a:last-child{margin-right:0}
/* all seven days fit across, so the chart below does not jump when you change day */
.days{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px;margin:10px 0}
.days button{padding:6px 0;font-size:.82rem}
/* the week grid: 24 columns on a phone, so the squares have to be small */
.hm{grid-template-columns:30px repeat(24,minmax(0,1fr));gap:1.5px;font-size:.68rem}
.hm .c{height:17px;border-radius:3px}
.axis{font-size:.72rem}
/* a game's icon beside its name, instead of a 150px square pushing the name down */
.ghead{gap:13px;margin:38px 0 12px;padding:14px 15px;border-radius:16px}
.ghead .thumb{width:72px;border-radius:12px;margin-top:-30px;border-width:2px}
/* On a phone the picture goes on its own line and the words get the full width.
   Beside a 72px picture the text column was about 250px, which broke a heading
   into three lines and the opening paragraph into eleven. */
.ghead>div{flex:1 1 100%}
h1{font-size:1.5rem}
.actions{gap:7px}
.btn{padding:10px 16px}
.fav{padding:9px 13px;font-size:.92rem;border-radius:11px}
.stats{gap:9px}
.stats b{font-size:1.3rem}
.foot nav{gap:4px 14px}
/* the trail wraps onto three lines at this width, and Back already covers leaving */
.crumbs{display:none}
}

/* the gentle opening effects */
@keyframes up{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes grow{from{transform:scaleY(.02)}to{transform:scaleY(1)}}
@keyframes fade{from{opacity:0}to{opacity:1}}
.rise{animation:up .5s cubic-bezier(.2,.75,.3,1) both}
.rise2{animation:up .5s cubic-bezier(.2,.75,.3,1) .08s both}
.rise3{animation:up .5s cubic-bezier(.2,.75,.3,1) .16s both}
.card{animation:fade .7s both}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}"""

CSS = CSS.replace("__LIGHT__", LIGHT).replace("__DARK__", DARK)

# ---------------------------------------------------------------- search engines
#
# Three separate things decide whether a page can show up in Google:
#   NOINDEX          a master switch for the whole site while we are still designing
#   noindex=True     set per page, for pages that do not yet have enough real data
#   sitemap.xml      the list of pages we actually want Google to look at
# A page left out of the sitemap is still on the site and still works; we are only
# saying it is not worth a search engine's time yet.

# One moment for the whole build, so every page and every calendar file agrees.
BUILT = int(time.time())


def robots_meta(noindex=False):
    """The <meta robots> tag for one page.

    "max-image-preview:large" asks Google to use the game's artwork in search results;
    "max-snippet:-1" lets it quote as much of the page as it likes. Neither has any
    effect while the whole site is on noindex.
    """
    if NOINDEX or noindex:
        return '<meta name="robots" content="noindex,nofollow">'
    return ('<meta name="robots" content="index,follow,max-image-preview:large,'
            'max-snippet:-1,max-video-preview:-1">')


def abs_url(path="/"):
    """A full web address for a page, e.g. "/game/doors.html" -> "https://.../game/doors.html".

    Until DOMAIN is filled in we have no way to know the site's real address, so the
    canonical tag falls back to the path on its own. That is allowed, just weaker.
    """
    if not path.startswith("/"):
        path = "/" + path
    return DOMAIN.rstrip("/") + path if DOMAIN else path


def jsonld(*blocks):
    """Structured data: the same facts the page shows, written out for machines.

    Google reads this to understand what a page is about and can show richer results
    from it. Every number in here must already be on the page: never invent anything,
    and never claim a rating or a review, because we do not have any.
    """
    items = [b for b in blocks if b]
    if not items:
        return ""
    data = items[0] if len(items) == 1 else {"@context": "https://schema.org", "@graph": items}
    if len(items) > 1:
        for b in items:
            b.pop("@context", None)
    return ('<script type="application/ld+json">'
            + json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
            + "</script>")


def crumbs(trail):
    """The small "All games > Simulation > Doors" line, plus the same trail for Google.

    trail is [(label, address)] ending with the page you are on, whose address is
    only used by the structured data. Returns (html, json-ld dictionary).
    """
    if not trail:
        return "", None
    bits, items = [], []
    for i, (label, href) in enumerate(trail):
        last = i == len(trail) - 1
        if i:
            bits.append('<span aria-hidden="true">&rsaquo;</span>')
        bits.append(f'<span aria-current="page">{html.escape(label)}</span>' if last
                    else f'<a href="{href}">{html.escape(label)}</a>')
        items.append({"@type": "ListItem", "position": i + 1, "name": label,
                      "item": abs_url(href)})
    return (f'<nav class="crumbs" aria-label="Breadcrumb">{"".join(bits)}</nav>',
            {"@type": "BreadcrumbList", "itemListElement": items})

# The logo: a timer ring with a play button inside. Drawn in the page rather than
# loaded as a picture, so it is sharp at any size and needs no extra request.
# favicon.svg is the same drawing on its own.
def logo_svg(cls="mark", ident="lg"):
    return (f'<svg class="{cls}" viewBox="0 0 32 32" aria-hidden="true">'
            f'<defs><linearGradient id="{ident}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="#D8B4FE"/><stop offset="1" stop-color="#A855F7"/>'
            f'</linearGradient></defs>'
            f'<circle cx="16" cy="16" r="15" fill="url(#{ident})"/>'
            f'<circle cx="16" cy="16" r="11" fill="none" stroke="#0A0A0F" stroke-opacity=".45" '
            f'stroke-width="2" stroke-linecap="round" stroke-dasharray="52 69" '
            f'transform="rotate(-90 16 16)"/>'
            f'<path d="M13.4 11.2 21.6 16l-8.2 4.8z" fill="#0A0A0F"/></svg>')


FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           + logo_svg(cls="", ident="f").split(">", 1)[1])

SUN = ('<svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.6"/>'
       '<path d="M12 1.6v3.1m0 14.6v3.1M4.6 4.6l2.2 2.2m10.4 10.4 2.2 2.2M1.6 12h3.1m14.6 0h3.1'
       'M4.6 19.4l2.2-2.2M17.2 6.8l2.2-2.2" stroke="currentColor" stroke-width="2" '
       'stroke-linecap="round" fill="none"/></svg>')
MOON = ('<svg class="moon" viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M21 14.2A9.2 9.2 0 1 1 9.8 3 7.4 7.4 0 0 0 21 14.2z"/></svg>')
ICON_MENU = ('<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="2.5" width="14" height="2" rx="1"/>'
             '<rect x="1" y="7" width="14" height="2" rx="1"/><rect x="1" y="11.5" width="14" height="2" rx="1"/></svg>')
ICON_SEARCH = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M7 1.5a5.5 5.5 0 1 0 3.37 9.85l3.14 '
               '3.14a1 1 0 0 0 1.42-1.42l-3.14-3.14A5.5 5.5 0 0 0 7 1.5zm0 2a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7z"/></svg>')
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



def page(title, body, desc="", wide=False, nav="", tail="", banner="",
         back=("/", "All games"), canon="", image="", trail=None,
         schema=None, noindex=False, modified=""):
    """Every page gets the same top bar, and the stylesheet decides how much of it fits.

    The row of sections is eight pills. On a phone they do not fit, and a row you have
    to drag sideways was the most cluttered thing on the page, so there the stylesheet
    hides the row and the menu button holds the same links instead. On a screen wide
    enough for the row it hides the menu button instead. Either way the links are on
    the page exactly once, and every page works the same way, which is the point.

    The search-engine arguments:
      canon     this page's one true address, e.g. "/game/doors.html". Cloudflare also
                serves every page without the ".html", so without this Google would see
                two addresses showing the same thing and have to pick one itself.
      image     a picture for when the page is shared on Discord, WhatsApp or X.
      trail     the breadcrumb trail, [(label, address)], ending with this page.
      schema    extra structured data dictionaries for jsonld().
      noindex   keep this one page out of Google even when the rest of the site is in.
      modified  the date the page's facts last changed, as YYYY-MM-DD.
    """
    # The menu marks the page you are on, so it is clear where you already are
    # without having to read every link.
    # (The row of section pills that used to sit under the header is gone. It was a
    # second navigation that only ever appeared on a wide screen, and the panel
    # already holds the same links plus two more. The footer still lists them as
    # plain visible links, so nothing is hidden from a search engine.)
    drawer = "".join(f'<a href="{u}"{" aria-current=page" if k == nav else ""}>{html.escape(t)}</a>'
                     for k, t, u in TABS)
    # The same shape at every width: logo, name, game picker, then the buttons on
    # the right. Light/dark and the account live inside the panel the three lines
    # open, on a laptop exactly as on a phone. Search is the one exception: a wide
    # screen has room for it, so the magnifier sits in the bar there (.deskonly)
    # and the panel hides its own search row to match. Nothing in the scripts had
    # to change for the second copy, because they bind every [data-search] and
    # [data-themebtn] rather than an id - keep it that way.
    buttons = (f'<button class="iconb deskonly" data-search type="button" '
               f'aria-label="Search for a game">{ICON_SEARCH}</button>'
               f'<button class="iconb" id="menubtn" type="button" aria-expanded="false" '
               f'aria-controls="drawer" aria-label="Menu">{ICON_MENU}</button>')
    # These two are position:fixed and must be written OUTSIDE <header>. The header
    # has backdrop-filter, and that makes it the containing block for any fixed
    # descendant: inside it, the side menu was 88px tall instead of the height of
    # the screen, and the search panel was pinned to the header's own box rather
    # than the page. They sit after </header> as siblings instead.
    extras = (f'<div class="drawer" id="drawer" hidden>'
              f'<div class="dtop">'
              f'<button class="drow" data-search type="button">{ICON_SEARCH}'
              f'<span>Search for a game</span></button>'
              f'<button class="drow themeic" data-themebtn type="button">{SUN}{MOON}'
              f'<span class="tlab">Dark mode</span></button>'
              f'<div class="acct dacct"></div></div>'
              f'<nav aria-label="Sections">{drawer}'
              f'<a href="/busiest-hours.html">When is Roblox busiest?</a>'
              f'<a href="/about.html">About</a></nav></div>'
              f'<div class="sheet" id="sheet" hidden><div class="sheetbox">'
              f'<input id="q" type="search" placeholder="Search for a game" aria-label="Search for a game">'
              f'<div id="qout" class="qout"></div></div></div>')
    crumb_html, crumb_data = crumbs(trail or [])
    # Back and the trail are both "where am I and how do I leave", so they share one
    # line instead of taking a line each. The trail is the one that goes on a phone:
    # it wraps onto three lines there, and the copy Google reads is the structured
    # data below, not this, so hiding it costs nothing.
    topnav = ((f'<div class="topnav">{back_link(*back) if back else ""}{crumb_html}</div>')
              if (back or crumb_html) else "")
    blocks = jsonld(*([crumb_data] + list(schema or [])))
    # Where the page lives. Internal links all end in ".html", so that is the address
    # we tell Google to use; Cloudflare happily serves the same page without it.
    url = abs_url(canon or "/")
    social = ""
    if image:
        social = (f'<meta property="og:image" content="{html.escape(image)}">'
                  f'<meta name="twitter:card" content="summary_large_image">')
    else:
        social = '<meta name="twitter:card" content="summary">'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}"><meta name="theme-color" content="#A855F7">
{robots_meta(noindex)}<link rel="canonical" href="{html.escape(url)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="{html.escape(SITE)}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{html.escape(url)}">{social}
{f'<meta property="article:modified_time" content="{modified}">' if modified else ''}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://tr.rbxcdn.com" crossorigin>
{BOOT}<style>{CSS}</style>{blocks}<script>{FAVJS}</script>{ADS}</head><body>
{banner_html(banner)}<header class="hdr"><div class="in"><div class="hrow">
<a class="logo" href="/">{logo_svg()}<span class="wordmark">Play<b>Time</b></span></a>
<div class="gpick" id="gpick"></div><div class="gap"></div>
{buttons}</div></div></header>{extras}
<div class="shell{' ads' if SHOW_RAILS else ''}">{ad_rail('left')}
<div class="w{' wide' if wide else ''}">{topnav}{body}
<footer class="foot"><nav class="small"><a href="/">All games</a>
<a href="/popular.html">Most played</a><a href="/trending.html">Trending</a>
<a href="/busiest-hours.html">When is Roblox busiest?</a>
<a href="/events.html">Events</a><a href="/compare.html">Compare</a><a href="/plan.html">Plan a session</a>
<a href="/about.html">About</a><a href="/privacy.html">Privacy Policy</a><a href="/terms.html">Terms</a></nav>
<p class="mut small">Not affiliated with or endorsed by Roblox Corporation. Based on public player counts, so it
shows when people play, not whether a game is good or safe.</p></footer>
</div>{ad_rail('right')}</div>{ad_rail('bottom')}
{tail}<script>{CHROME_JS}</script>{HIT}</body></html>"""


# ---------------------------------------------------------------- small helpers

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "game"


# Pictures and symbols that creators sprinkle through a game's name.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF"
                   "\u2190-\u21FF\u2300-\u27BF\u2B00-\u2BFF\uFE0F\u20E3]+")
# Anything in square brackets. On Roblox that is nearly always an advert:
# [UPD], [ALPHA], [HALLOWEEN PT 3], [X3 LUCK].
BRACKET = re.compile(r"\[[^\]]*\]")


def clean_name(name):
    """The core of a Roblox game's name, with the seasonal advertising taken off.

    "[HALLOWEEN PT 3] Grand Piece Online" -> "Grand Piece Online"
    "DOORS 🍬🍭"                           -> "DOORS"
    "3008 [2.75]"                         -> "3008"

    This is what goes in the heading, the page title and the address, because it is
    what people actually type into Google and because it does not change when the
    creators swap one event banner for the next. The full name is still shown on the
    game's own page.

    Deliberately cautious: only square brackets and symbols go. Round brackets are
    left alone, because for a lot of games they are part of the real name
    ("Clone Baby Care (Anomaly)").
    """
    out = EMOJI.sub(" ", BRACKET.sub(" ", name))
    out = re.sub(r"\s+", " ", out).strip(" -\u2013\u2014|,:;!.")
    if out:
        return out
    # The whole name was brackets or symbols; keep whatever letters there were.
    out = re.sub(r"\s+", " ", EMOJI.sub(" ", name)).strip(" -|,:;!.")
    return out or name


def name_slugs(games):
    """{universe_id: (display name, address)} for every game, with no two the same.

    Two games can tidy down to the same name, and two pages cannot share an address.
    Ties are settled by universe id, which never changes, so a given game keeps the
    same address build after build however the list is sorted.
    """
    out, taken = {}, {}
    for uid, name in sorted((g[0], g[1]) for g in games):
        nice = clean_name(name)
        key = slug(nice)
        if key in taken:
            key = f"{key}-{uid}"
        taken[key] = uid
        out[uid] = (nice, key)
    return out


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


def index_ok(c):
    """Is there enough real data on this game's page to be worth a place in Google?

    A page that only says "too new to say" is a thin page: it helps nobody who
    searched for it, and a site full of them makes Google trust the rest of the site
    less. These games still get a page, still appear in every list and still work; we
    simply leave them out of the sitemap and ask Google not to list them until the
    numbers arrive. The test is about how much we have *seen*, not how popular the
    game is:

      days  >= 3    enough history for the week to mean anything
      hours >= 48   we have really seen the game in a third of the week's 168 hours
    """
    a = c["a"]
    return a["days"] >= 3 and a["hours"] >= 48


def seo_title(*headlines):
    """A page title for Google, trimmed to a length it will actually show.

    Google cuts a title off at roughly 60 characters, and a title cut off mid-word
    looks broken in the results. Pass the fullest wording first and shorter fallbacks
    after it; the first one that fits wins, with the site name added if there is still
    room for it. Some Roblox game names are 40 characters on their own, which is why
    the shortest fallback matters.
    """
    for h in headlines:
        if len(f"{h} | {SITE}") <= 62:
            return f"{h} | {SITE}"
    for h in headlines:
        if len(h) <= 66:
            return h
    return headlines[-1]


def clip(text, limit=158):
    """Trims a meta description to the length Google will actually show."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "..."


def icon_alt(name):
    """Alt text for a game's picture. Describes it, and says what kind of thing it is."""
    return f"{name} Roblox game icon"


def iso_day(ts):
    """A point in time -> '2026-10-31'. The form sitemaps and structured data want."""
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def thumb(name, url, alt="", cls="thumb", eager=False):
    """A game's square picture.

    eager=True is for the big picture at the top of a game page: it is the first thing
    a visitor sees, so letting the browser put it off (the default everywhere else)
    would only make the page feel slower to load.
    """
    if url:
        load = ('loading="eager" fetchpriority="high"' if eager
                else 'loading="lazy" fetchpriority="low"')
        return (f'<img class="{cls}" src="{html.escape(url)}" alt="{html.escape(alt)}" '
                f'width="256" height="256" {load} decoding="async">')
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
    # --glow is the hue of this game's own picture, so the glow behind the tile is
    # the game's colour. Left off entirely when the picture has no colour in it, so
    # that the stylesheet's fallback (the site accent) takes over.
    glow = "" if c.get("hue") is None else f';--glow:{c["hue"]}'
    return (f'<li style="--i:{min(i, 14)}{glow}" data-n="{html.escape(c["name"].lower())}" data-s="{c["slug"]}">'
            f'<a class="tile" href="/game/{c["slug"]}.html">{thumb(c["name"], c["icon"], icon_alt(c["name"]))}'
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
      peaks   [(midnight, typical players, highest seen that day)] oldest first
      first   the time of our oldest player count for this game
      last    the time of our newest player count
      hours   how many of the week's 168 hours we have ever seen this game in
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
    # The same days again, with the highest count we actually saw on each one. The
    # average is our estimate of a typical moment; the maximum is a real observation,
    # and the pages are careful to say which is which.
    peaks = [(day * 86400, round(sum(v) / len(v)), max(v)) for day, v in sorted(by_day.items())]

    def mean(vals):
        return sum(vals) / len(vals) if vals else None

    def change(span):
        """% difference between the last `span` days and the `span` days before them."""
        pts = buckets[span * 2] if span * 2 in buckets else []
        a = mean([p for age, p in pts if age <= span])
        b = mean([p for age, p in pts if span < age <= span * 2])
        return round((a - b) / b * 100, 1) if a and b else None

    return {"week": week, "daily": daily, "peaks": peaks,
            "trend": change(7), "month": change(14),
            "avg7": round(mean([p for age, p in buckets[7]]) or 0),
            "peak": max(p for _, p in rows),
            "spikes": find_spikes(daily),
            "first": rows[0][0], "last": rows[-1][0],
            "hours": sum(1 for row in week for v in row if v is not None),
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
        return ("Growing", "var(--l1)",
                f"No, the opposite. More people are playing than a week ago, with about {players} "
                f"in the game at a typical moment.")
    if score >= 5:
        return ("Slowly growing", "var(--l1)",
                f"No. It is picking up a little, with about {players} players at a typical moment.")
    if score > -5:
        return ("Steady", "var(--l2)",
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
    dots = "".join(f'<circle cx="{x(i)}" cy="{y(v)}" r="4" fill="var(--alt)"><title>'
                   f'{when(d)}: about {v:,} players, much busier than usual</title></circle>'
                   for i, (d, v) in enumerate(pts) if d in spike_days)
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" '
            f'aria-label="Typical players each day over the last {len(pts)} days">'
            f'<polygon points="0,{h} {line} {w},{h}" fill="var(--acc)" opacity=".13"/>'
            f'<polyline points="{line}" fill="none" stroke="var(--acc)" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round"/>{dots}</svg>'
            f'<p class="mut small">{when(pts[0][0])} to {when(pts[-1][0])}. '
            f'Each point is a day. The dots mark days that were much busier than usual.</p>')


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
#
# Everything from here to clean_desc() writes a game's numbers straight into the
# page as plain HTML. The charts and the countdown are still drawn by the browser in
# the visitor's own timezone, but a search engine (or anyone with JavaScript switched
# off) now reads the same facts without running a single line of code.
# Times in this section are always UTC and always labelled as such, because the
# builder cannot know where the reader is.

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def hour12(h):
    """17 -> '5 PM'."""
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


def band_of(week):
    """The five busy-ness thresholds for one game: the same split the browser uses."""
    vals = sorted(v for row in week for v in row if v is not None)
    if not vals:
        return lambda v: 0
    q = [vals[int(p * (len(vals) - 1))] for p in (.2, .4, .6, .8)]
    return lambda v: 0 if v is None else 1 + sum(1 for t in q if v > t)


def week_facts(week):
    """The headline facts about a game's week, worked out here instead of in the browser.

    Returns None when we have not seen enough of the week to say anything, and
    otherwise the busiest and quietest hour, the quietest hour that is still in the
    daytime, and the busiest and quietest whole day. All in UTC.
    """
    cells = [(d, h, v) for d in range(7) for h, v in enumerate(week[d]) if v is not None]
    if len(cells) < 12:
        return None
    busy = max(cells, key=lambda c: c[2])
    quiet = min(cells, key=lambda c: c[2])
    day_cells = [c for c in cells if 8 <= c[1] <= 21]
    by_day = {}
    for d, _, v in cells:
        by_day.setdefault(d, []).append(v)
    means = {d: sum(v) / len(v) for d, v in by_day.items() if len(v) >= 6}
    return {"busy": busy, "quiet": quiet,
            "day_quiet": min(day_cells, key=lambda c: c[2]) if day_cells else None,
            "busy_day": max(means, key=means.get) if means else None,
            "quiet_day": min(means, key=means.get) if means else None,
            "covered": len(cells)}


def short_answer(name, f):
    """The two sentences at the top of a game page, written by the builder.

    The browser rewrites them in the visitor's own timezone a moment later. Writing
    them here first means the page is never blank, never jumps about as it loads, and
    says something real to a search engine that does not run scripts.
    """
    if not f:
        return ('<span class="mut">We have not seen enough of '
                f'{html.escape(name)}&rsquo;s week yet to name its busiest and '
                'quietest hours. Check back in a day or two.</span>', "")
    bd, bh, bv = f["busy"]
    qd, qh, qv = f["quiet"]
    return (f'Busiest: <b>{DAYS[bd]} around {hour12(bh)}</b> '
            f'<span class="mut">UTC</span> &ndash; about {bv:,} players.',
            f'Quietest: <b>{DAYS[qd]} around {hour12(qh)}</b> '
            f'<span class="mut">UTC</span> &ndash; about {qv:,} players.')


def facts_html(c, a, f):
    """The key numbers as a list, so they are in the page itself and not only in a chart."""
    rows = [("Players at a typical moment", f'{a["avg7"]:,}', "average over the last 7 days"),
            ("Highest player count seen", f'{a["peak"]:,}', "the most we have ever recorded"),
            ("Compared to last week", trend_html(a["trend"]), "last 7 days against the 7 before")]
    if f:
        bd, bh, _ = f["busy"]
        qd, qh, _ = f["quiet"]
        rows.append(("Busiest hour", f"{DAYS[bd]}, {hour12(bh)} UTC", "in a typical week"))
        rows.append(("Quietest hour", f"{DAYS[qd]}, {hour12(qh)} UTC", "in a typical week"))
    # A game we only started watching this morning has "0 days" of history, which
    # reads like a mistake, so say when we started instead of for how long.
    span = (f'over {a["days"]:.0f} days, since {when(a["first"])}' if a["days"] >= 1
            else f'since {when(a["first"])}')
    rows.append(("Player counts collected", f'{c["samples"]:,}', span))
    return ('<dl class="facts">'
            + "".join(f'<div><dt>{k}</dt><dd>{v}</dd>'
                      f'<dd class="mut small" style="font-weight:400">{note}</dd></div>'
                      for k, v, note in rows)
            + "</dl>")


def hours_table_html(name, week):
    """Every hour of the week as a real table, folded away inside a <details>.

    The coloured grid above it is drawn by the browser and means nothing to a search
    engine. This is the same information as text, so the numbers are in the page. It
    is collapsed because 168 numbers would bury everything else, and collapsed text
    is still read by search engines and by screen readers.
    """
    level = band_of(week)
    head = "".join(f"<th>{hour12(h)}</th>" for h in range(24))
    body = ""
    for d in range(7):
        cells = "".join(
            f'<td title="{WORDS[level(v)]}">{"&ndash;" if v is None else format(v, ",")}</td>'
            for v in week[d])
        body += f"<tr><th>{DAYS[d]}</th>{cells}</tr>"
    return (f'<details><summary>All 168 hours as numbers</summary>'
            f'<p class="mut small">Players in {html.escape(name)} at a typical moment, '
            f'hour by hour, in UTC. A dash means we have not collected a player count '
            f'in that hour yet.</p><div class="wrap"><table class="hourtbl">'
            f'<thead><tr><th>Day (UTC)</th>{head}</tr></thead><tbody>{body}</tbody>'
            f'</table></div></details>')


def history_html(name, a, days=21):
    """The last few weeks day by day: the heart of "player count history".

    Two columns that must not be muddled. The typical count is an average of the
    samples we took that day, so it is an estimate. The highest is a single number we
    really saw, so it is an observation.
    """
    pts = a["peaks"][-days:]
    if len(pts) < 3:
        return ""
    rows = "".join(f'<tr><td>{when(day)}</td><td>{avg:,}</td><td>{hi:,}</td></tr>'
                   for day, avg, hi in reversed(pts))
    return (f'<div class="card"><h2>{html.escape(name)} player count history</h2>'
            f'<p class="mut small">Every day we have been watching, newest first: '
            f'{when(pts[0][0])} to {when(pts[-1][0])}. &ldquo;Typical&rdquo; is the '
            f'average of the player counts we took that day. &ldquo;Highest&rdquo; is '
            f'the largest single count we recorded, so it is something we observed '
            f'rather than an estimate.</p>'
            f'<div class="wrap"><table class="tbl"><thead><tr><th>Day</th>'
            f'<th>Typical players</th><th>Highest seen</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></div>')


def faq_html(c, a, f, meta, pattern):
    """The questions people type into Google, answered with our own numbers.

    Returns (html, [(question, plain answer)]) so the same answers can go into the
    page's structured data without being written out twice.
    """
    name = c["name"]
    qa = [(f"How many people play {name}?",
           f"About {a['avg7']:,} people are in {name} at a typical moment, averaged over "
           f"the last 7 days. The most we have ever recorded at once is {a['peak']:,}. "
           f"These are our own readings of Roblox's public player count, taken roughly "
           f"every ten minutes.")]
    if f:
        bd, bh, bv = f["busy"]
        qd, qh, qv = f["quiet"]
        qa.append((f"What is the best time to play {name}?",
                   f"For quiet servers, aim for {DAYS[qd]} around {hour12(qh)} UTC, when "
                   f"there are usually about {qv:,} players. For full servers and trading, "
                   f"{DAYS[bd]} around {hour12(bh)} UTC is the busiest hour we see, at "
                   f"roughly {bv:,} players. The charts on this page show those times on "
                   f"your own clock."))
        extra = (f" {DAYS[f['busy_day']]} is its busiest day overall."
                 if f["busy_day"] is not None else "")
        qa.append((f"When is {name} busiest?",
                   f"{DAYS[bd]} around {hour12(bh)} UTC is its busiest hour in a typical "
                   f"week, with about {bv:,} players.{extra}"))
    qa.append((f"Is {name} dying?", re.sub(r"</?b>", "", verdict(a)[2])))
    if pattern:
        every = f", roughly every {pattern['every']} days" if pattern.get("every") else ""
        hour = f" at about {hour12(pattern['hour'])} UTC" if pattern.get("hour") is not None else ""
        qa.append((f"When does {name} update?",
                   f"Updates and events usually land on a {DAYS[pattern['wd']]}{hour}{every}. "
                   f"That comes from the last {pattern['n']} updates the creators announced "
                   f"on Roblox plus the days we saw the player count jump."))
    if meta and meta.get("visits"):
        qa.append((f"How many visits does {name} have?",
                   f"Roblox reports {meta['visits']:,} total visits for {name} so far"
                   + (f", and it was first released {ago(meta['created'])}."
                      if meta.get("created") else ".")))
    body = "".join(f"<h3>{html.escape(q)}</h3><p>{html.escape(ans)}</p>" for q, ans in qa)
    return (f'<div class="card faq"><h2>{html.escape(name)}: common questions</h2>{body}'
            f'<p class="mut small">Answers come from our own player counts, which are '
            f'estimates built from samples, not official Roblox figures.</p></div>'), qa


def game_schema(c, a, meta, qa):
    """Structured data for one game page: what the game is, and what our data covers.

    Only facts already written on the page go in here. There is deliberately no rating
    and no review: we do not collect either, and inventing them would be lying to
    Google as well as to visitors.
    """
    url = abs_url(f'/game/{c["slug"]}.html')
    game = {"@type": "VideoGame", "name": c["name"], "url": url, "gamePlatform": "Roblox",
            "playMode": "MultiPlayer", "applicationCategory": "Game"}
    if c["icon"]:
        game["image"] = c["icon"]
    if c["genre"] and c["genre"] != "All":
        game["genre"] = c["genre"]
    if meta:
        if meta.get("creator"):
            game["author"] = {"@type": "Organization", "name": meta["creator"]}
        if meta.get("description"):
            game["description"] = clean_desc(meta["description"])[:400]
        if meta.get("created"):
            game["datePublished"] = iso_day(meta["created"])
        if meta.get("visits"):
            game["interactionStatistic"] = {
                "@type": "InteractionCounter",
                "interactionType": "https://schema.org/PlayAction",
                "userInteractionCount": meta["visits"]}
    # Our own measurements, described as a dataset. This is the part of the site that
    # is genuinely ours: a record of how many people were in the game, hour by hour.
    data = {"@type": "Dataset",
            "name": f'{c["name"]} player count history',
            "description": (f'Concurrent player counts for the Roblox game {c["name"]}, '
                            f'sampled from the public Roblox player count every few '
                            f'minutes. {c["samples"]:,} readings so far.'),
            "url": url,
            "temporalCoverage": f'{iso_day(a["first"])}/{iso_day(a["last"])}',
            "measurementTechnique": "Repeated sampling of the public Roblox player count",
            "variableMeasured": "Concurrent players",
            "isAccessibleForFree": True,
            "creator": {"@type": "Organization", "name": SITE}}
    out = [game, data]
    if qa:
        out.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": ans}} for q, ans in qa]})
    return out


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
    """The game's own description, as a drawer directly under the heading.

    It is the first thing a visitor wonders ("what IS this game?") but also the
    longest and least re-readable thing on the page, and the creators write it for
    players who have already chosen the game. Under the heading it answers that
    question for someone who has not, and closed by default it costs a reader who
    already knows nothing at all. Being behind a click is also why the 600-character
    truncation went: the whole description can simply go inside."""
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
    # Joined with commas, not full stops. ".".join(...).capitalize() used to turn
    # "Made by LSPLASH. 8B total visits" into "Made by lsplash. 8b total visits",
    # because capitalize() lower-cases everything after the first letter: it was
    # rewriting the creator's own name and our own numbers.
    if bits:
        bits[0] = bits[0][0].upper() + bits[0][1:]
    line = f'<p class="mut small">{", ".join(bits)}.</p>' if bits else ""
    body = f'<p class="desc">{html.escape(desc)}</p>' if desc else ""
    # The h2 stays, inside the summary, so the page keeps its heading for search
    # engines and for anyone moving through the page heading by heading. <summary>
    # is allowed to hold heading content.
    return (f'<details class="gdesc"><summary><h2>What is {html.escape(name)}?</h2></summary>'
            f'<div class="gdesc-in">{body}{line}'
            f'<p class="mut small">Description written by the game\'s own creators and shown on Roblox.</p></div></details>')


def event_item(e, now, cls="", gslug=""):
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
    bell = remind_btn("/" + event_ics_name(gslug, e)) if (soon and gslug) else ""
    return (f'<li class="{klass}"><b>{html.escape(e["title"])}</b>{sub}'
            f'<span class="d">{label}</span>{body}{bell}</li>')


# ----------------------------------------------------------------- reminders
# "Remind me" hands the visitor a calendar file. The files are written here, at
# build time, and served like any other file on the site: a link to one gets iOS's
# own "Add to Calendar" screen, and a file built inside the page never does.
#
# The format is iCalendar (RFC 5545), and it is picky in three ways that lose the
# whole file rather than one line: every line ends CRLF, text escapes \ ; , and
# newlines, and no line may exceed 75 OCTETS. Nearly a quarter of Roblox's event
# titles carry an emoji, which is four octets on its own, so the folding below
# counts bytes rather than characters and never splits a character in half.
def ics_text(value):
    return (str(value).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_fold(line):
    out, run = [], 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if run + n > 74:
            out.append("\r\n ")
            run = 1
        out.append(ch)
        run += n
    return "".join(out)


def ics_stamp(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ics_file(uid, start, end, title, desc="", url="", rrule="", alarm=10):
    """One calendar file, as text. Times are UTC, so it carries no timezone of its
    own and the reader's calendar shows them on their own clock."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PlayTime//EN",
             "CALSCALE:GREGORIAN", "BEGIN:VEVENT", f"UID:{uid}@playtime",
             f"DTSTAMP:{ics_stamp(BUILT)}", f"DTSTART:{ics_stamp(start)}",
             f"DTEND:{ics_stamp(end)}"]
    if rrule:
        lines.append("RRULE:" + rrule)
    lines.append("SUMMARY:" + ics_text(title))
    if desc:
        lines.append("DESCRIPTION:" + ics_text(desc))
    # Only a full web address belongs here. Until DOMAIN is set abs_url() gives a
    # path, and a path on its own is not a valid URL for a calendar to follow.
    if url.startswith("http"):
        lines.append("URL:" + ics_text(url))
    lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:-PT{int(alarm)}M",
              "DESCRIPTION:" + ics_text(title), "END:VALARM", "END:VEVENT",
              "END:VCALENDAR"]
    return "\r\n".join(ics_fold(l) for l in lines) + "\r\n"


def event_ics_name(slug, event):
    return f"ics/{slug}-{int(event['start'])}.ics"


def write_event_ics(slug, game, events, now):
    """A calendar file for every event of this game that has not happened yet."""
    for e in events or []:
        if e["start"] <= now:
            continue
        desc = clean_desc(e.get("description") or "")[:600]
        write(event_ics_name(slug, e), ics_file(
            f"pte-{slug}-{int(e['start'])}", e["start"],
            e["end"] or e["start"] + 3600, f"{game}: {e['title']}",
            desc=desc, url=abs_url(f"/game/{slug}.html"), alarm=15))


def remind_btn(href, label="Remind me"):
    """A link to one of the calendar files written above.

    A plain link on purpose. The browser version of this did the work in the page
    and never ran on an iPhone, where a click arrives at a text node rather than at
    the button; a real address also gets iOS's own "Add to Calendar" screen. There
    is no "download" attribute for the same reason: letting Safari open the file is
    what produces that screen, while desktop browsers save it either way.
    """
    if not href:
        return ""
    return (f'<a class="remind" href="{html.escape(href)}" type="text/calendar">'
            f'&#128276; {html.escape(label)}</a>')


def calendar_html(name, events, now, gslug=""):
    """Upcoming and currently running events for one game."""
    if events is None:
        return ""
    soon = [e for e in events if (e["end"] or e["start"] + 86400) >= now]
    soon.sort(key=lambda e: e["start"])
    if not soon:
        return (f'<div class="card"><h2>Event calendar</h2><p class="none">{html.escape(name)} has no '
                f'events planned on Roblox right now. When the creators announce one it will show up here.</p></div>')
    items = "".join(event_item(e, now, gslug=gslug) for e in soon[:8])
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


def pass_tags(p, cheapest, newest):
    """The honest labels we can put on a game pass.

    Roblox publishes no sales figures, ratings or reviews for game passes, so there is
    no way to know which one people actually rate. Rather than invent a "recommended"
    badge, these say only what the data really supports: the price, whether Roblox has
    it discounted, and whether it is new.
    """
    tags = []
    if p.get("discounted"):
        tags.append(("On sale now", "sale"))
    if p["price"] == cheapest:
        tags.append(("Cheapest", "cheap"))
    if newest and p.get("created") and p["created"] >= newest:
        tags.append(("Newest", "new"))
    return "".join(f'<span class="ptag {k}">{t}</span>' for t, k in tags)


def pass_card(p, icon, cheapest, newest):
    desc = clean_desc(p.get("description") or "")
    if len(desc) > 260:
        desc = desc[:260].rsplit(" ", 1)[0] + "…"
    pic = (f'<img src="{html.escape(icon)}" alt="" width="64" height="64" loading="lazy">'
           if icon else '<span class="ph" aria-hidden="true">R$</span>')
    return (f'<li class="pass">{pic}<div><b>{html.escape(p["name"])}</b>{pass_tags(p, cheapest, newest)}'
            + (f'<p>{html.escape(desc)}</p>' if desc else
               '<p class="mut">The creators did not say what this one contains.</p>')
            + f'<span class="price">{p["price"]:,} Robux '
              f'<span class="mut">&middot; about ${p["price"] * ROBUX_USD:,.2f}</span></span></div></li>')


def parents_html(passes, icons):
    """What the game sells: pictures, what each pass contains, and what it costs.
    Hidden entirely if Roblox did not answer."""
    if passes is None:
        return ""
    h = '<div class="card"><h2>What costs money</h2>'
    if not passes:
        h += "<p>This game sells <b>no game passes</b> right now.</p>"
    else:
        ps = sorted(passes, key=lambda p: p["price"])
        total = sum(p["price"] for p in ps)
        n = len(ps)
        cheapest = ps[0]["price"]
        made = [p["created"] for p in ps if p.get("created")]
        # "Newest" only means something when one pass is clearly more recent.
        newest = max(made) if len(made) > 1 and max(made) > sorted(made)[-2] else None
        h += (f"<p>This game sells <b>{n} game pass{'es' if n != 1 else ''}</b>, from "
              f"<b>{cheapest:,} to {ps[-1]['price']:,} Robux</b>. Buying every one would cost "
              f"<b>{total:,} Robux</b> (roughly ${total * ROBUX_USD:,.0f} USD).</p>"
              f'<ul class="passes">'
              + "".join(pass_card(p, icons.get(p.get("icon_id")), cheapest, newest) for p in ps[:6])
              + "</ul>")
        if n > 6:
            rows = "".join(f'<tr><td>{html.escape(p["name"])}</td><td>{p["price"]:,}</td></tr>'
                           for p in ps[6:])
            h += (f'<details><summary>The other {n - 6} game passes</summary><div class="wrap">'
                  f'<table class="tbl"><tr><th>Game pass</th><th>Robux</th></tr>{rows}'
                  f'</table></div></details>')
        h += ('<p class="mut small">Cheapest and newest come from Roblox\'s own numbers. We do not say '
              'which pass is best: Roblox does not publish how many people buy each one, so anyone '
              'ranking them is guessing.</p>')
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
function ptPaint(){var markup=!PT.available?'':PT.name
?'<span class="who">'+ptEsc(PT.name)+'</span><form method="POST" action="/auth/logout">'
+'<button class="linkish" type="submit">Sign out</button></form>'
:'<a class="signin" href="/auth/login">Sign in with Roblox</a>';
/* Two of these: the one in the header on a wide screen and the one in the phone
   panel. Whichever is hidden costs nothing, and neither can go stale. */
Array.prototype.forEach.call(document.querySelectorAll('.acct'),function(el){
el.innerHTML=markup});
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
/* Both copies are bound and both are relabelled, so the panel row never says
   "Dark mode" while the page is already dark. The row carries a .tlab to write
   into; the header button is an icon and has only its aria-label. */
function paintTheme(){var dark=theme()==='dark';
Array.prototype.forEach.call(document.querySelectorAll('[data-themebtn]'),function(b){
b.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');
var lab=b.querySelector('.tlab');if(lab)lab.textContent=dark?'Light mode':'Dark mode'})}
Array.prototype.forEach.call(document.querySelectorAll('[data-themebtn]'),function(b){
b.onclick=function(){var next=theme()==='dark'?'light':'dark';
d.setAttribute('data-theme',next);try{localStorage.setItem('pt_theme',next)}catch(e){}
paintTheme()}});
paintTheme();

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

/* The side drawer and the search sheet. Both only exist on the pages about one
   game, where the row of sections is hidden to keep the page about the game. */
var scrim=null;
function shade(on){
if(on&&!scrim){scrim=document.createElement('div');scrim.className='scrim';
scrim.onclick=function(){shut()};document.body.appendChild(scrim)}
if(scrim)scrim.hidden=!on}
function shut(){var dr=document.getElementById('drawer'),sh=document.getElementById('sheet'),
mb=document.getElementById('menubtn');
if(dr)dr.hidden=true;if(sh)sh.hidden=true;
if(mb)mb.setAttribute('aria-expanded','false');shade(false)}
var mb=document.getElementById('menubtn'),dr=document.getElementById('drawer');
if(mb&&dr)mb.onclick=function(e){e.stopPropagation();var show=dr.hidden;shut();
dr.hidden=!show;mb.setAttribute('aria-expanded',show?'true':'false');shade(show);
if(show){var a=dr.querySelector('a');if(a)a.focus()}};

/* Search. The list of games is only fetched the first time it is opened. */
var sheet=document.getElementById('sheet'),GAMES=null;
if(sheet){
var q=document.getElementById('q'),qout=document.getElementById('qout');
function draw(){
var t=q.value.trim().toLowerCase();
if(!GAMES){qout.innerHTML='<p>Loading the list of games&hellip;</p>';return}
var hits=GAMES.filter(function(g){return g.n.toLowerCase().indexOf(t)>-1}).slice(0,25);
qout.innerHTML=hits.length?hits.map(function(g){
return '<a href="/game/'+ptEsc(g.s)+'.html">'+(g.i?'<img src="'+ptEsc(g.i)+
'" alt="" width="30" height="30" loading="lazy">':'<span class="ph" aria-hidden="true">'+
ptEsc(g.n.charAt(0).toUpperCase())+'</span>')+'<span>'+ptEsc(g.n)+'</span></a>'}).join(''):
'<p>No game matches that.</p>'}
/* The magnifier on a wide screen, and the first row of the phone panel. shut()
   closes the panel on the way, so opening search from inside it does the right
   thing. The list of games is still only fetched the first time. */
Array.prototype.forEach.call(document.querySelectorAll('[data-search]'),function(b){
b.onclick=function(e){e.stopPropagation();var show=sheet.hidden;shut();
if(!show)return;
sheet.hidden=false;shade(true);q.value='';draw();q.focus();
if(!GAMES)fetch('/games.json').then(function(r){return r.json()}).then(function(d){
GAMES=d;draw()}).catch(function(){qout.innerHTML='<p>Could not load the list. Please reload.</p>'})}});
q.oninput=draw;
sheet.onclick=function(e){if(e.target===sheet)shut()}}
document.addEventListener('keydown',function(e){if(e.key==='Escape')shut()});

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
return {max:v[v.length-1]||1,lo:v[0]||0,level:function(x){if(x==null)return 0;var n=1;
for(var i=0;i<4;i++)if(x>q[i])n++;return n}}}
/* The floor and ceiling the day graph is drawn between. Starting the axis at zero
   wastes the bottom of the chart on space no game ever visits: measured across the
   live site, one day's line used only 39% of the height, which is what makes a day
   read as a gentle curve. Running the axis from the week's quietest hour to its
   busiest lifts that to about 52%. It is the WEEK's range, not the day's, so the
   seven days stay comparable - scale each day to itself and a quiet Tuesday looks
   exactly like a heaving Saturday. The 8% padding keeps the extremes off the edges. */
function graphRange(B){var pad=(B.max-B.lo)*.08||1;
return {f:Math.max(0,B.lo-pad),c:B.max+pad}}
function nowDay(){return (new Date().getDay()+6)%7}
/* Draws one day as a line with a see-through wash underneath, so the shape of the
   day reads as a trend instead of 24 separate bars. Gaps in the data break the line
   rather than being drawn as zero, which would invent a quiet hour that we never saw.
   The box is 720x320. It was 720x250, which drew 865x300 on a laptop - nearly three
   times wider than tall - and a day's entire rise and fall came to 126 real pixels
   spread over 865, which reads as a gentle curve whatever the numbers do. Height is
   half of why a day now looks like a day; graphRange() is the other half. Keep the
   two in step with graphCursor, which repeats H and would float off the line. */
function dayGraph(vals,R,label,hue){
var W=720,H=320,P=14,top=16,bot=H-26,span=bot-top;
var rng=(R.c-R.f)||1;
var x=function(i){return P+i*(W-P*2)/23},y=function(v){return bot-((v-R.f)/rng)*span};
var runs=[],cur=[];
for(var i=0;i<24;i++){if(vals[i]==null){if(cur.length)runs.push(cur);cur=[]}else cur.push(i)}
if(cur.length)runs.push(cur);
var line='',wash='',dots='',hits='';
runs.forEach(function(r){
var d=r.map(function(i,n){return (n?'L':'M')+x(i).toFixed(1)+' '+y(vals[i]).toFixed(1)}).join(' ');
line+=d+' ';
if(r.length>1)wash+=d+' L'+x(r[r.length-1]).toFixed(1)+' '+bot+' L'+x(r[0]).toFixed(1)+' '+bot+' Z ';
r.forEach(function(i){dots+='<circle cx="'+x(i).toFixed(1)+'" cy="'+y(vals[i]).toFixed(1)+
'" r="3.5" fill="var(--'+hue+')"/>'})});
return '<svg class="graph" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+label+'" '+
'tabindex="0">'+
'<defs><linearGradient id="wash" x1="0" y1="0" x2="0" y2="1">'+
'<stop offset="0" stop-color="var(--'+hue+')" stop-opacity=".42"/>'+
'<stop offset="1" stop-color="var(--'+hue+')" stop-opacity=".02"/></linearGradient></defs>'+
'<line x1="'+P+'" y1="'+bot+'" x2="'+(W-P)+'" y2="'+bot+'" stroke="var(--line)" stroke-width="1.5"/>'+
'<path d="'+wash+'" fill="url(#wash)"/>'+
'<path d="'+line+'" fill="none" stroke="var(--'+hue+')" stroke-width="3" '+
'stroke-linejoin="round" stroke-linecap="round"/>'+dots+
'<g class="cursor" opacity="0"><line y1="'+top+'" y2="'+bot+'" stroke="var(--ink)" '+
'stroke-width="1.5" stroke-dasharray="4 4"/><circle r="6" fill="var(--'+hue+')" '+
'stroke="var(--solid)" stroke-width="2.5"/></g></svg>'}

/* Lets people drag or click along a graph to read off any hour. Works with a mouse,
   a finger, and the arrow keys, and falls back to doing nothing if the browser
   cannot measure the svg. The readout element is optional. */
function graphCursor(svg,out,vals,R){
if(!svg)return;
/* H must match dayGraph's, or the crosshair floats off the line. */
var W=720,H=320,P=14,top=16,bot=H-26,span=bot-top,rng=(R.c-R.f)||1;
var g=svg.querySelector('.cursor'),line=g.querySelector('line'),dot=g.querySelector('circle');
var at=-1;
function show(i){
if(i<0||i>23||vals[i]==null){g.setAttribute('opacity','0');at=-1;
if(out)out.textContent='';return}
at=i;
var x=P+i*(W-P*2)/23,y=bot-((vals[i]-R.f)/rng)*span;
line.setAttribute('x1',x);line.setAttribute('x2',x);
dot.setAttribute('cx',x);dot.setAttribute('cy',y);
g.setAttribute('opacity','1');
if(out)out.innerHTML='<b>'+fmt(i)+'</b> &middot; about <b>'+vals[i].toLocaleString()+'</b> players'}
function fromX(clientX){
var r=svg.getBoundingClientRect();
if(!r.width)return -1;
var vx=(clientX-r.left)/r.width*W;
return Math.max(0,Math.min(23,Math.round((vx-P)/((W-P*2)/23))))}
function move(e){
var t=e.touches&&e.touches[0];
var cx=t?t.clientX:e.clientX;
if(cx==null)return;
if(t)e.preventDefault();          /* stop the page scrolling while dragging the graph */
show(fromX(cx))}
var down=false;
svg.addEventListener('mousedown',function(e){down=true;move(e)});
svg.addEventListener('mousemove',function(e){if(down||e.buttons===0)move(e)});
window.addEventListener('mouseup',function(){down=false});
svg.addEventListener('mouseleave',function(){if(!down)show(-1)});
svg.addEventListener('touchstart',move,{passive:false});
svg.addEventListener('touchmove',move,{passive:false});
svg.addEventListener('keydown',function(e){
if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();
var i=at<0?0:at+(e.key==='ArrowRight'?1:-1);
while(i>=0&&i<=23&&vals[i]==null)i+=(e.key==='ArrowRight'?1:-1);
if(i>=0&&i<=23)show(i)}
else if(e.key==='Escape')show(-1)});
}
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

# Writes the "updates usually arrive on a Friday around 2 PM" line. The page that
# uses it defines P first, so the same code serves any game.
PATTERN_JS = """if(P&&$('pattern')){var pd=P.wd,ph=P.hour,every=P.every?
', about every '+P.every+' day'+(P.every>1?'s':''):'';
if(ph!=null){var pt=ph+tzOff();
while(pt<0){pt+=24;pd=(pd+6)%7}while(pt>=24){pt-=24;pd=(pd+1)%7}
$('pattern').innerHTML='Updates usually arrive on a <b>'+DAY[pd]+'</b> around <b>'+fmt(pt)+
'</b> your time'+every+'. Worked out from the last '+P.n+' updates and busy days.'}
else $('pattern').innerHTML='Updates usually arrive on a <b>'+DAY[pd]+'</b>'+every+
'. Worked out from the last '+P.n+' updates and busy days.'}"""

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

/* The reminder. Each day of the week has its own best hour - the quietest hour of a
   Tuesday is rarely the quietest hour of a Saturday - so this shows the hour for
   every day that is ticked and points the link at a file holding exactly those.
   L is already in the visitor's own timezone, and tzOff() goes with the address so
   the file is built around the same days they are looking at. Only the link's
   address is touched: tapping it is then an ordinary link, which is the one thing
   an iPhone was certain to get right. */
/* The reminder keeps its own quiet-or-busy choice, separate from the countdown's
   above. They were one control, and nobody could tell: the buttons sat at the top
   of the card under "What do you want?" and the reminder was at the bottom, so it
   read as being about quiet hours and nothing else. Two questions asked in two
   places now answer themselves, and changing your mind about the countdown no
   longer quietly changes what you are about to put in your calendar. */
var rmode='quiet';
function days(){
var picked=[],shown=[];
Array.prototype.forEach.call(document.querySelectorAll('#rbtns button'),function(b){
b.setAttribute('aria-pressed',b.dataset.r===rmode)});
Array.prototype.forEach.call(document.querySelectorAll('#daypick input'),function(b){
if(b.checked)picked.push(+b.value)});
picked.forEach(function(d){
var at=null,v=null;
for(var h=0;h<24;h++){var x=L[d][h];if(x==null)continue;
if(v==null||(rmode==='quiet'?x<v:x>v)){at=h;v=x}}
if(at!=null)shown.push(DAY[d].slice(0,3)+' '+fmt(at))});
var rb=$('remind');
if(rb)rb.innerHTML='&#128276; Add '+rmode+' times to my calendar';
/* A day can be ticked and still have nothing to say, if we have no readings for it
   yet. Saying so is better than offering a calendar file with holes in it. */
if(!shown.length){$('daylist').textContent=picked.length
?'We have not got enough player counts for those days yet.':'Tick at least one day.';
if(rb){rb.setAttribute('aria-disabled','true');rb.removeAttribute('href')}return}
$('daylist').textContent=(rmode==='quiet'?'Quietest':'Busiest')+': '+shown.join('  \u00b7  ');
if(rb&&window.PT_GAME){rb.setAttribute('aria-disabled','false');
rb.href='/reminder.ics?g='+encodeURIComponent(PT_GAME.s)+'&m='+rmode+
'&z='+tzOff()+'&d='+picked.join(',')}}
Array.prototype.forEach.call(document.querySelectorAll('#daypick input'),function(b){
b.onchange=days});
Array.prototype.forEach.call(document.querySelectorAll('#rbtns button'),function(b){
b.onclick=function(){rmode=b.dataset.r;days()}});
days();
function tick(){if(!aim)return;
var ms=aim-new Date();
if(ms<=0){plan();return}      /* the window has arrived: work out the one after it */
$('cd').textContent=ticker(ms)}
Array.prototype.forEach.call(document.querySelectorAll('#planbtns button'),function(b){
b.onclick=function(){mode=b.dataset.m;plan()}});
plan();setInterval(tick,1000);setInterval(plan,300000);

/* One day at a time */
function show(d){
Array.prototype.forEach.call($('days').querySelectorAll('button'),function(b,i){
b.setAttribute('aria-pressed',i==d)});
var lo=null,hi=null;
for(var h=0;h<24;h++){var v=L[d][h];if(v==null)continue;
if(!lo||v<lo[1])lo=[h,v];if(!hi||v>hi[1])hi=[h,v]}
var R=graphRange(B);
$('bars').innerHTML=dayGraph(L[d],R,DAY[d]+': players through the day','acc');
graphCursor($('bars').querySelector('.graph'),$('readout'),L[d],R);
/* An axis that does not start at zero has to say so, or the shape overstates the
   swing. The numbers are the game's own quietest and busiest hours of the week. */
var sn=$('scalenote');
if(sn)sn.textContent='Drag across the graph, or tap it, to read any hour. '+
'The scale runs from '+Math.round(R.f).toLocaleString()+' to '+
Math.round(R.c).toLocaleString()+' players, not from zero, so the shape of the day is easier to see.';
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
/* strict() is what "quiet" and "busy" really mean: the bottom two of a game's own
   five levels, or the top two. fits() is what we filter on, and it is allowed to
   widen. Every game follows roughly the same daily rhythm, so at 8pm no game is
   quiet by its own standards and at 5am none is busy: filtering on strict() alone
   came up empty for 85 of the week's 168 hours for "quiet" and 67 for "busy", which
   reads as a broken page rather than as an answer. So the band widens only as far as
   it has to -- to the quietest (or busiest) level any game is actually at right now.
   When some games really are quiet, lo is already 1 or 2 and nothing changes. */
function strict(l){return want==='quiet'?(l>0&&l<=2):(l>=4)}
var band={lo:2,hi:4,relaxed:false};
function setBand(){
var seen=[];G.forEach(function(g){if(g.lv)seen.push(g.lv)});
if(!seen.length){band={lo:2,hi:4,relaxed:false};return}
var lo=Math.min.apply(null,seen),hi=Math.max.apply(null,seen);
band={lo:Math.max(2,lo),hi:Math.min(4,hi),relaxed:want==='quiet'?lo>2:hi<4}}
function fits(l){if(!want)return true;
return want==='quiet'?(l>0&&l<=band.lo):(l>=band.hi)}

/* The next hour in the next day when a few games would match, in the visitor's
   own clock. cell is an hour of the week in UTC, so +1 is simply the next hour. */
function nextGood(){
var best=null;
for(var k=1;k<=24;k++){
var c=(cell+k)%168,n=0;
G.forEach(function(g){var l=+g.l.charAt(c);if(l&&strict(l))n++});
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
setBand();
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
/* No game has a reading for this hour at all, which is a different thing from
   no game being quiet, and used to be told to the visitor as the same thing. */
var nx=nextGood();
note.innerHTML='<b>We have no player counts for this hour yet.</b> '+
(nx?('Try again <b>'+nx.when+'</b>. Meanwhile here is '):'Here is ')+
'every game we track, most popular first.';
note.hidden=false}
else if(band.relaxed){
var nx2=nextGood();
note.innerHTML='<b>No game is properly '+word+' right now.</b> Nearly every game we track '+
'is '+(want==='quiet'?'busy':'quiet')+' at this hour, so these are the '+
(want==='quiet'?'quietest':'busiest')+' of them.'+
(nx2?(' For genuinely '+word+' games, try <b>'+nx2.when+'</b>.'):'');
note.hidden=false}
else note.hidden=true}

$('asktxt').textContent=!want?'Showing the most popular games first.':
(loose||band.relaxed)?'':
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
'<div class="bar b2" style="--i:'+h+';flex:1;height:'+Math.max(3,(vb||0)/Bb.max*100)+'%;background:var(--alt)" '+
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

# The page about one game.
#
# Two kinds of content are mixed together here on purpose:
#   __LEAD__, __FACTS__, __BEST__, __QUIET__, __HOURS__, __HISTORY__, __FAQ__
#     are written by the builder, so the facts are in the HTML that Google downloads.
#   #now, #bars, #hm and the countdown are filled in by the browser, because only
#     the browser knows what timezone the visitor is in and what the time is now.
# The browser's version replaces the builder's where they overlap (#best, #quiet),
# which is why those two carry UTC times and say so: nothing is hidden, the same
# fact is simply shown on the reader's own clock once a script can run.
def span(block, n):
    """Gives a section's own <div class="card"> its width in the bento grid, in
    twelfths. The sections below build their own card, so this is the one place that
    card learns how wide it should be, and a section that decided it had nothing to
    say (an empty string) stays empty rather than becoming an empty box."""
    return block.replace('<div class="card', f'<div class="sp{n} card', 1) if block else ""


# The order here is the order a visitor reads in, and the grid never reorders it.
# Sections are paired by how tall they are, not just by subject: the short answer
# next to the session planner, the hourly graph next to the numbers it is drawn
# from. The week grid is the one full-width card, because it is 24 hours across.
GAME = """<div class="ghead rise">__ICON__<div><h1>__NAME__ player count and best times to play</h1>
<p class="mut">__LEAD__</p>
<div class="actions">__PLAY__<a class="fav" href="/updates/__SLUG__.html">&#128221; Game updates</a>
<button class="fav" id="fav" data-s="__SLUG__" aria-pressed="false">&#9734; Save</button>
<a class="fav" href="/compare.html?a=__SLUG__">Compare</a></div></div></div>
__ABOUT__
<div class="bento">
<div class="sp7 lstack">
<div class="card ans rise2"><h2>The short answer</h2><p id="now"></p><p id="best">__BEST__</p>
<p id="quiet">__QUIET__</p>
<p class="mut small">The times above are in UTC until the page loads, then they switch to your
own clock. Based on __N__ player counts we took ourselves.__CAT__</p></div>
<div class="card rise3"><h2>Is __NAME__ dead?</h2><div class="verdict">
<span class="vbadge" style="background:__VCOL__">__VLABEL__</span><p style="margin:0;flex:1 1 240px">__VTEXT__</p></div>
__SPARK__</div></div>
<div class="sp5 card rise3"><h2>Plan my session</h2>
<p class="mut small">What do you want?</p>
<div class="days" id="planbtns"><button data-m="quiet" aria-pressed="true">Quiet</button>
<button data-m="busy" aria-pressed="false">Busy</button></div>
<div id="cdw" hidden><span class="mut small" id="cdlab"></span><span class="cd" id="cd"></span></div>
<p id="plantxt"></p>
<div class="rem"><p class="mut small">Remind me when it is</p>
<div class="days" id="rbtns"><button data-r="quiet" aria-pressed="true">Quiet</button>
<button data-r="busy" aria-pressed="false">Busy</button></div>
<fieldset class="daypick" id="daypick"><legend class="mut small">on these days</legend>
__DAYBOXES__</fieldset>
<p class="mut small" id="daylist"></p>
<a class="remind" id="remind" type="text/calendar"
href="/reminder.ics?g=__SLUG__&amp;m=quiet&amp;d=0,1,2,3,4,5,6">&#128276; Add quiet times to my
calendar</a>
<p class="mut small">Adds it to your own calendar, at the right hour for each day you
picked. No account, and nothing about you is stored.</p></div></div>
<div class="sp8 card"><h2>__NAME__ player numbers by hour</h2><div class="days" id="days"></div>
<p id="dtxt" class="mut small"></p><div class="bars" id="bars"></div><p class="readout" id="readout"></p><p class="mut small" id="scalenote">Drag across the graph, or tap it, to read any hour.</p>
<div class="axis"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span></div></div>
<div class="sp4 card"><h2>__NAME__ statistics</h2>__FACTS__</div>
<div class="card"><h2>__NAME__ busiest hours, the whole week</h2><div class="wrap"><div class="hm" id="hm"></div></div>
<div class="legend">Quiet <i style="background:var(--l1)"></i><i style="background:var(--l2)"></i>
<i style="background:var(--l3)"></i><i style="background:var(--l4)"></i><i style="background:var(--l5)"></i> Busy</div>
<p class="mut small">The outlined square is right now.</p>
__HOURS__</div>
__HISTORY__
__CALENDAR__
__PARENTS__
__FAQ__
</div>
__SIMILAR__
<p><a href="/">&larr; All Roblox player counts</a> &middot; <a href="/plan.html?g=__SLUG__">Plan a session</a>
&middot; <a href="/busiest-hours.html">When is Roblox busiest?</a></p>
<script>window.PT_GAME=__GAMEINFO__;</script>
<script>__SHARED__</script><script>__JS__</script><script>__FAVJS__</script>"""


def about_body():
    return f"""<div class="doc"><h1>About {html.escape(SITE)}</h1>
<p>{html.escape(SITE)} shows when popular Roblox games are busiest and quietest, hour by hour, so you can pick a good time to play.</p>
<h2>How it works</h2>
<p>About every 10 minutes, we check how many people are playing each game, using the player counts Roblox shows publicly.
Over days and weeks, those counts add up to a picture of each game's week: which hours are packed and which are quiet.
Times are shown in your own timezone.</p>
<h2>Why use it?</h2>
<ul><li><b>Quiet hours</b> are good for shorter queues, less lag, claiming event items, and learning a game without a crowd.</li>
<li><b>Busy hours</b> are good for full servers, trading, and events.</li></ul>
<h2>Reminders</h2>
<p>Every game page has a <b>Remind me</b> button. Tick the days you want, choose quiet or busy, and your
device adds them to its own calendar &mdash; each day at that day's own best hour, because the quietest hour
of a Tuesday is rarely the quietest hour of a Saturday. There is no account, no notification to switch on,
and nothing about you is stored. Reminders stop after about three months, because by then a game's pattern
will have moved and a reminder that is quietly wrong is worse than none.</p>
<h2>Which games are on here</h2>
<p>We only list games that Roblox itself labels <b>Minimal</b> or <b>Mild</b> for content, and we read that
label back from Roblox before adding a game rather than guessing from its name. That is why some of the
biggest games on Roblox are missing: it is deliberate, not an oversight. It is a rule about the label, though,
not a promise &mdash; see &ldquo;What it does not tell you&rdquo; below.</p>
<h2>Where the extra details come from</h2>
<ul><li><b>Event calendars and updates</b> come from the events the game's own creators post on Roblox.</li>
<li><b>Descriptions, pictures and game passes</b> are the public ones Roblox shows on each game's page.</li>
<li><b>"Days the player count jumped"</b> is worked out by us: any day at least {SPIKE:g} times busier than the
week before it usually means an update, a seasonal event, or a popular video about the game.</li></ul>
<h2>Estimates and observations</h2>
<p>These are two different things and we try never to muddle them. A <b>typical</b> or <b>average</b> player
count is an estimate: we add up the readings we took in that hour and divide. The <b>highest seen</b> figures are
not estimates at all &mdash; each one is a single reading we really recorded. An estimate built from a handful of
readings can be well out, which is why every game page says how many readings it is based on and how long we have
been watching.</p>
<h2>Game names</h2>
<p>Creators rename their games for every holiday and update, so the same game might be called
&ldquo;Grand Piece Online&rdquo; one week and &ldquo;[&#127875;HALLOWEEN PT 3] Grand Piece Online&rdquo; the next.
We use the game's core name for headings and web addresses so links keep working, and each game page says what
Roblox is calling it today.</p>
<h2>What it does not tell you</h2>
<p>Player counts show when people play. They do not say whether a game is good, fair, or safe for children,
and neither does Roblox's content label on its own. Parents should still check a game themselves and use
Roblox's parental controls.</p>
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
<p>If you tap <b>Remind me</b>, your device downloads a small calendar file from this site, the same way it
downloads a page. We do not store anything about you when you do, you do not need an account, and the reminder
belongs to your own calendar app afterwards, not to this site. We never send notifications and never ask for
permission to.</p>
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
    # newline="" turns off Python's line-ending translation, so a file holds exactly
    # what we put in it. Without it, building on Windows turns the CRLF that calendar
    # files are required to use into CR CR LF, and every calendar app rejects them.
    # It also means a build here and a build on the server produce identical files.
    os.makedirs(os.path.dirname(f"{OUT}/{path}") or OUT, exist_ok=True)
    with open(f"{OUT}/{path}", "w", encoding="utf-8", newline="") as f:
        f.write(text)
    WRITTEN.add(path.replace("\\", "/"))


def prune(folders=("game", "category", "updates", "ics")):
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
            if name.endswith((".html", ".ics")) and f"{folder}/{name}" not in WRITTEN:
                os.remove(f"{d}/{name}")
                gone.append(f"{folder}/{name}")
    if gone:
        print(f"Removed {len(gone)} page(s) left over from an earlier build: "
              + ", ".join(gone[:4]) + (" ..." if len(gone) > 4 else ""))
    return gone


def write_theme():
    """Saves the site's two palettes where the worker can read them.

    The admin dashboard lives in worker/index.js, not here, so it cannot share this
    file's stylesheet. Writing the palettes out means a colour changed in LIGHT or
    DARK above reaches the dashboard on the next build, instead of the two slowly
    drifting apart. Only the colours travel: the dashboard has its own layout.
    """
    if OUT != "docs":
        return                      # previews must not touch the real worker
    os.makedirs("worker", exist_ok=True)
    with open("worker/theme.js", "w", encoding="utf-8") as f:
        f.write("// Written by build_site.py on every build. Do not edit by hand:\n"
                "// change LIGHT or DARK in build_site.py instead.\n"
                "export const LIGHT = " + json.dumps(LIGHT) + ";\n"
                "export const DARK = " + json.dumps(DARK) + ";\n")


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


def item_list(cards, name):
    """The games on a list page, written out for search engines in the order shown.

    An honest description of a ranked list: Google can see what the page ranks and
    in what order, which is the whole point of a "most played games" page.
    """
    return {"@type": "ItemList", "name": name, "numberOfItems": len(cards),
            "itemListOrder": "https://schema.org/ItemListOrderDescending",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": c["name"],
                 "url": abs_url(f'/game/{c["slug"]}.html')}
                for i, c in enumerate(cards[:50])]}


def busy_page(cards, now):
    """"When is Roblox busiest?" for every game we watch, added together.

    This page exists because it is the one question the whole database can answer and
    a single game page cannot. Each game is first turned into a share of its own peak,
    so a game with two million players does not simply drown out forty smaller ones:
    what we are measuring is when games are busy *relative to themselves*, which is
    what someone asking "when is Roblox busiest" actually wants to know.

    Everything is in UTC, written by the builder. The little script at the end puts it
    on the reader's own clock, using the same helpers as every other page.
    """
    # share[d][h] = the average of every game's player count that hour as a fraction
    # of that game's own busiest hour. 1.0 would mean every game peaks at once.
    totals = [[0.0] * 24 for _ in range(7)]
    counts = [[0] * 24 for _ in range(7)]
    for c in cards:
        week = c["a"]["week"]
        peak = max((v for row in week for v in row if v is not None), default=0)
        if not peak:
            continue
        for d in range(7):
            for h in range(24):
                if week[d][h] is not None:
                    totals[d][h] += week[d][h] / peak
                    counts[d][h] += 1
    share = [[round(totals[d][h] / counts[d][h] * 100) if counts[d][h] else None
              for h in range(24)] for d in range(7)]
    cells = [(d, h, v) for d in range(7) for h, v in enumerate(share[d]) if v is not None]
    if len(cells) < 24:
        return page(seo_title("When Is Roblox Busiest?"),
                    '<div class="hero"><h1>When is Roblox busiest?</h1>'
                    '<p class="lede">We need a full week of player counts across the games we '
                    'track before this page can say anything. Check back in a few days.</p></div>'
                    '<p><a href="/">&larr; All Roblox player counts</a></p>',
                    "The busiest and quietest hours across the Roblox games we track.",
                    wide=True, canon="/busiest-hours.html", noindex=True,
                    trail=[("All games", "/"), ("Busiest hours", "/busiest-hours.html")])

    busy = max(cells, key=lambda c: c[2])
    quiet = min(cells, key=lambda c: c[2])
    by_day, by_hour = {}, {}
    for d, h, v in cells:
        by_day.setdefault(d, []).append(v)
        by_hour.setdefault(h, []).append(v)
    day_mean = {d: sum(v) / len(v) for d, v in by_day.items() if len(v) >= 12}
    hour_mean = {h: sum(v) / len(v) for h, v in by_hour.items() if len(v) >= 4}
    busy_day = max(day_mean, key=day_mean.get) if day_mean else None
    quiet_day = min(day_mean, key=day_mean.get) if day_mean else None

    # The same five bands the rest of the site uses, so the colours mean the same thing.
    vals = sorted(v for _, _, v in cells)
    q = [vals[int(p * (len(vals) - 1))] for p in (.2, .4, .6, .8)]
    level = lambda v: 0 if v is None else 1 + sum(1 for t in q if v > t)

    grid_html = '<div class="hm" id="hm"><div></div>'
    for t in ("12 AM", "6 AM", "12 PM", "6 PM"):
        grid_html += f'<span style="grid-column:span 6">{t}</span>'
    for d in range(7):
        grid_html += f"<div>{DAYS[d][:3]}</div>"
        for h in range(24):
            v = share[d][h]
            bg = "transparent" if v is None else f"var(--l{level(v)})"
            grid_html += (f'<div class="c" title="{DAYS[d]} {hour12(h)} UTC: '
                          f'{"no data" if v is None else f"{v}% of peak"}" '
                          f'style="background:{bg}"></div>')
    grid_html += "</div>"

    hours_rows = "".join(
        f"<tr><td>{hour12(h)}</td><td>{round(hour_mean[h])}%</td>"
        f"<td>{WORDS[level(hour_mean[h])]}</td></tr>"
        for h in sorted(hour_mean))
    days_rows = "".join(
        f"<tr><td>{DAYS[d]}</td><td>{round(day_mean[d])}%</td>"
        f"<td>{WORDS[level(day_mean[d])]}</td></tr>"
        for d in sorted(day_mean, key=lambda d: -day_mean[d]))

    body = (
        f'<div class="hero"><h1>When is Roblox busiest?</h1>'
        f'<p class="lede">Across the {len(cards)} games we track, the busiest hour of the '
        f'week is <b>{DAYS[busy[0]]} around {hour12(busy[1])} UTC</b> and the quietest is '
        f'<b>{DAYS[quiet[0]]} around {hour12(quiet[1])} UTC</b>. '
        + (f'{DAYS[busy_day]} is the busiest day overall and {DAYS[quiet_day]} the '
           f'quietest. ' if busy_day is not None else "")
        + 'Each game is counted as a share of its own busiest hour, so the big games '
          'do not drown out the small ones.</p></div><div class="bento">'
        f'<div class="card"><h2>The whole week, every game at once</h2>'
        f'<p class="mut small">Darker means busier. Each square is the average player '
        f'count that hour as a percentage of each game\'s own peak hour.</p>'
        f'<div class="wrap">{grid_html}</div>'
        f'<div class="legend">Quiet <i style="background:var(--l1)"></i>'
        f'<i style="background:var(--l2)"></i><i style="background:var(--l3)"></i>'
        f'<i style="background:var(--l4)"></i><i style="background:var(--l5)"></i> Busy</div>'
        f'<p class="mut small" id="tzn"></p></div>'
        f'<div class="sp6 card"><h2>Roblox busiest hours, hour by hour</h2>'
        f'<p class="mut small">Averaged over the whole week, in UTC.</p><div class="wrap">'
        f'<table class="tbl"><thead><tr><th>Hour (UTC)</th><th>Share of peak</th>'
        f'<th>How busy</th></tr></thead><tbody>{hours_rows}</tbody></table></div></div>'
        f'<div class="sp6 card"><h2>Busiest days of the week on Roblox</h2><div class="wrap">'
        f'<table class="tbl"><thead><tr><th>Day</th><th>Share of peak</th>'
        f'<th>How busy</th></tr></thead><tbody>{days_rows}</tbody></table></div></div>'
        f'<div class="card faq"><h2>Common questions</h2>'
        f'<h3>What time is Roblox busiest?</h3>'
        f'<p>{DAYS[busy[0]]} around {hour12(busy[1])} UTC is the busiest hour we see across '
        f'the games we track. Converted to local time that is the late afternoon and '
        f'evening in most of Europe and the Americas, which is when most players are out '
        f'of school.</p>'
        f'<h3>When is the best time to play Roblox games quietly?</h3>'
        f'<p>{DAYS[quiet[0]]} around {hour12(quiet[1])} UTC is the quietest hour overall. '
        f'Quiet hours mean shorter queues, less lag and a better chance at timed or '
        f'limited in-game events. Individual games differ, so check the game\'s own page '
        f'for its quietest hour.</p>'
        f'<h3>Is this the same for every game?</h3>'
        f'<p>No. Most games follow this rhythm because most players share a daily routine, '
        f'but a game with players mainly in one part of the world can be hours out of step. '
        f'Every game we track has its own hour-by-hour page.</p>'
        f'<p class="mut small">Worked out from '
        f'{sum(c["samples"] for c in cards):,} player counts we took ourselves. These are '
        f'averages of samples, so treat them as a good guess rather than an official '
        f'figure.</p></div></div>'
        + row_head("Busiest games right now",
                   f'<span class="mut small">{len(cards)} games</span>')
        + grid(cards[:12])
        + '<p><a href="/popular.html">Most played Roblox games</a> &middot; '
          '<a href="/plan.html">Plan a session</a> &middot; '
          '<a href="/">All Roblox player counts</a></p>'
        # Puts the two headline hours on the reader's own clock. Everything above stays
        # exactly as written, so nothing depends on this running.
        + f'<script>{SHARED_JS}</script><script>'
          f'var BZ={jsdata([busy[0], busy[1], quiet[0], quiet[1]])};'
          '(function(){var o=tzOff();function loc(d,h){var t=h+o;'
          'while(t<0){t+=24;d=(d+6)%7}while(t>=24){t-=24;d=(d+1)%7}return DAY[d]+" around "+fmt(t)}'
          'var n=$("tzn");if(n)n.innerHTML="In your timezone that is busiest on <b>"+'
          'loc(BZ[0],BZ[1])+"</b> and quietest on <b>"+loc(BZ[2],BZ[3])+"</b>."})();</script>')

    return page(
        seo_title("When Is Roblox Busiest? Busiest Hours by Day"), body,
        clip(f"The busiest hour on Roblox is {DAYS[busy[0]]} around {hour12(busy[1])} UTC and "
             f"the quietest is {DAYS[quiet[0]]} around {hour12(quiet[1])} UTC, across "
             f"{len(cards)} games we track hour by hour."),
        wide=True, canon="/busiest-hours.html",
        trail=[("All games", "/"), ("Busiest hours", "/busiest-hours.html")],
        modified=iso_day(now),
        schema=[{"@type": "Dataset",
                 "name": "Roblox player activity by hour of the week",
                 "description": ("The share of each game's peak player count reached in "
                                 "every hour of the week, averaged across the Roblox games "
                                 f"{SITE} tracks."),
                 "url": abs_url("/busiest-hours.html"),
                 "measurementTechnique": "Repeated sampling of public Roblox player counts",
                 "variableMeasured": "Concurrent players as a share of each game's peak",
                 "isAccessibleForFree": True,
                 "creator": {"@type": "Organization", "name": SITE}}])


def list_page(key, title, h1, lede, cards, desc, extra="", listname=""):
    """One of the "across the top" pages: a heading and a grid of games."""
    body = (f'<div class="hero"><h1>{h1}</h1><p class="lede">{lede}</p></div>{extra}'
            + (row_head("", f'<span class="mut small">{len(cards)} '
                            f'game{"s" if len(cards) != 1 else ""}</span>')
               + grid(cards) if cards else
               '<p class="none">Nothing here yet. We need about two weeks of player counts for each game '
               'before this page fills in.</p>')
            + table_of(cards)
            + '<p><a href="/">&larr; All Roblox player counts</a></p>')
    write(f"{key}.html", page(
        title, body, desc, wide=True, nav=key, canon=f"/{key}.html",
        trail=[("All games", "/"), (h1, f"/{key}.html")],
        schema=[item_list(cards, listname or h1)] if cards else None,
        # A list page with nothing on it yet says so honestly, but there is no reason
        # for Google to hold on to an empty page.
        noindex=not cards))


def table_of(cards, limit=60):
    """A plain table of the games on a list page.

    The tiles above it are links with a picture and a number inside them, which reads
    well but gives a search engine very little. The same games as a table put the
    player counts into the page as text, and give anyone comparing them one place to
    look instead of 50 tiles.
    """
    if len(cards) < 3:
        return ""
    rows = "".join(
        f'<tr><td>{i + 1}</td><td><a href="/game/{c["slug"]}.html">{html.escape(c["name"])}</a></td>'
        f'<td>{c["avg"]:,}</td><td>{c["a"]["peak"]:,}</td>'
        f'<td>{trend_short(c["trend"]) or "<span class=mut>steady</span>"}</td></tr>'
        for i, c in enumerate(cards[:limit]))
    more = (f'<p class="mut small">Showing the first {limit} of {len(cards)} games.</p>'
            if len(cards) > limit else "")
    return (f'<h2 style="margin-top:28px">The player counts</h2>'
            f'<p class="mut small">&ldquo;Typical&rdquo; is the average number of players we '
            f'saw over the last 7 days. &ldquo;Highest seen&rdquo; is the largest single '
            f'player count we have ever recorded for that game.</p><div class="wrap">'
            f'<table class="tbl"><thead><tr><th>#</th><th>Game</th><th>Typical players</th>'
            f'<th>Highest seen</th><th>vs last week</th></tr></thead><tbody>{rows}</tbody>'
            f'</table></div>{more}')


def main():
    started = time.time()
    now = int(time.time())
    db = sqlite3.connect("data.db")
    os.makedirs(OUT + "/game", exist_ok=True)

    games = db.execute("SELECT universe_id,name,genre,place_id FROM games").fetchall()
    # Worked out once for all games, because an address has to be unique across the
    # whole site and because it must not depend on the order the pages are built in.
    naming = name_slugs(games)
    print(f"Looking up pictures and details for {len(games)} games...")
    ids = [g[0] for g in games]
    icons = roblox_api.fetch_icons(ids)
    banners = roblox_api.fetch_banners(ids)
    metas = roblox_api.fetch_meta(ids)
    # One number per game: the hue its picture reads as, for the glow behind its
    # tile. Games whose picture is grey are left out and fall back to the accent.
    hues = roblox_api.fetch_icon_hues(ids)

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
        nice, key = naming[uid]
        cards.append({"name": nice, "full": name, "slug": key,
                      "icon": icons.get(uid), "genre": genre,
                      "avg": a["avg7"], "trend": a["trend"], "month": a["month"],
                      "samples": len(rows), "days": a["days"], "week": a["week"],
                      "levels": levels_string(a["week"]), "verdict": verdict(a)[0],
                      "uid": uid, "place": place, "a": a, "banner": banners.get(uid),
                      "hue": hues.get(uid)})

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
        full = c["full"]
        meta = metas.get(uid)
        events = roblox_api.fetch_events(uid)
        passes = roblox_api.fetch_passes(uid)
        # Pictures for the passes, fetched in one go per game. All of them, not
        # just the first few: the card list shows the cheapest passes, which are
        # not the ones Roblox happens to return first.
        pass_icons = roblox_api.fetch_asset_icons(
            [p.get("icon_id") for p in (passes or [])])
        upcoming = [e for e in (events or []) if (e["end"] or e["start"] + 86400) >= now]
        for e in upcoming:
            all_events.append(dict(e, game=name, slug=s, icon=c["icon"]))
        # The "Remind me" files. Written before the pages that link to them, and
        # for every upcoming event rather than the handful this game's own page
        # shows, because /events.html lists far more of them.
        write_event_ics(s, name, events, now)
        c["events"], c["upcoming"] = len(events or []), len(upcoming)
        vlabel, vcol, vtext = verdict(a)
        pattern = update_pattern(events, a["spikes"], now)
        facts = week_facts(a["week"])
        c["facts"] = facts
        best_txt, quiet_txt = short_answer(name, facts)

        play = (f'<a class="btn" href="https://www.roblox.com/games/{c["place"]}">'
                f'Play {html.escape(name)}</a>' if c["place"] and c["place"] > 1 else "")
        in_cat = c["genre"] in cats
        cat = (f' Category: <a href="/category/{slug(c["genre"])}.html">{html.escape(c["genre"])}</a>.'
               if in_cat else "")

        # The opening paragraph. Every number in it comes from our own samples, and the
        # wording keeps "about"/"typical" on the averages and "seen"/"recorded" on the
        # things we really observed, so an estimate is never dressed up as a fact.
        lead = (f'{html.escape(name)} has about <b>{a["avg7"]:,} players</b> at a typical '
                f'moment, and we have seen as many as <b>{a["peak"]:,}</b> at once. ')
        if facts:
            bd, bh, _ = facts["busy"]
            qd, qh, _ = facts["quiet"]
            lead += (f'Its busiest hour is usually <b>{DAYS[bd]} around {hour12(bh)}</b> and '
                     f'its quietest <b>{DAYS[qd]} around {hour12(qh)}</b> (UTC). ')
        lead += (f'Worked out from {c["samples"]:,} player counts taken since '
                 f'{when(a["first"])}.')
        # Creators rename their games for every holiday. We use the core name so the
        # address and the heading stay put, and say what Roblox is calling it today.
        if full != name:
            lead += (f'<br><span class="small">Listed on Roblox right now as '
                     f'&ldquo;{html.escape(full)}&rdquo;.</span>')

        faq, qa = faq_html(c, a, facts, meta, pattern)
        body = (GAME.replace("__ICON__", thumb(name, c["icon"], icon_alt(name), eager=True))
                .replace("__LEAD__", lead)
                .replace("__BEST__", best_txt)
                .replace("__QUIET__", quiet_txt)
                .replace("__FACTS__", facts_html(c, a, facts))
                .replace("__HOURS__", hours_table_html(name, a["week"]))
                .replace("__HISTORY__", history_html(name, a))
                .replace("__FAQ__", faq)
                .replace("__N__", f'{c["samples"]:,}')
                .replace("__CAT__", cat)
                .replace("__PLAY__", play)
                .replace("__DAYBOXES__", "".join(
                    f'<label><input type="checkbox" value="{i}" checked>'
                    f'<span>{d[:3]}</span></label>' for i, d in enumerate(DAYS)))
                .replace("__SLUG__", s)
                .replace("__VLABEL__", vlabel).replace("__VCOL__", vcol).replace("__VTEXT__", vtext)
                .replace("__SPARK__", sparkline(a["daily"], a["spikes"]))
                .replace("__CALENDAR__", span(calendar_html(name, events, now, gslug=s), 6))
                .replace("__ABOUT__", about_game_html(name, meta))
                .replace("__PARENTS__", span(parents_html(passes, pass_icons), 6))
                .replace("__SIMILAR__", similar_html(c, cards))
                .replace("__GAMEINFO__", jsdata({"s": s, "n": name, "i": c["icon"] or ""}))
                .replace("__SHARED__", SHARED_JS)
                .replace("__FAVJS__", FAV_GAME)
                .replace("__JS__", GAME_JS.replace("__DATA__", jsdata(a["week"])))
                # __NAME__ last: it appears inside several of the blocks above.
                .replace("__NAME__", html.escape(name)))
        # Back goes to this game's category when it has one, so the button lands
        # somewhere useful even for a visitor who arrived straight from Google.
        where = ((f'/category/{slug(c["genre"])}.html', f'{c["genre"]} games')
                 if in_cat else ("/", "All games"))
        trail = [("All games", "/")]
        if in_cat:
            trail.append((f'{c["genre"]} games', f'/category/{slug(c["genre"])}.html'))
        thin = not index_ok(c)

        # Everything about this game's updates gets its own page, reached from the
        # "Game updates" button at the top of the game page.
        upd = updates_html(name, events, meta, a["spikes"], now)
        # The sitemap only asks Google to look at an updates page that has
        # something on it; an empty one is not worth a visit.
        c["has_updates"] = bool(upd)
        write(f"updates/{s}.html", page(
            seo_title(f"{name} Update History and Patch Notes",
                      f"{name} Update History"),
            f'<div class="ghead rise">{thumb(name, c["icon"], icon_alt(name), eager=True)}<div>'
            f'<h1>{html.escape(name)} update history</h1>'
            f'<p class="mut">Every update and event the creators have announced, when they '
            f'landed, and the days {html.escape(name)}&rsquo;s player count jumped.</p>'
            f'<div class="actions"><a class="fav" href="/game/{s}.html">&larr; '
            f'{html.escape(name)} player count</a>{play}</div></div></div>'
            + (upd or '<div class="card"><p class="none">The creators have not announced any '
                      'updates on Roblox for this game yet, and we have not been watching long '
                      'enough to spot a jump in players. Check back soon.</p></div>')
            + calendar_html(name, events, now)
            + f'<p><a href="/game/{s}.html">&larr; Back to {html.escape(name)}</a></p>'
            + f'<script>{SHARED_JS}</script>'
            + f'<script>var P={jsdata(pattern)};'
            + PATTERN_JS + '</script>'
            + f'<script>window.PT_GAME={jsdata({"s": s, "n": name, "i": c["icon"] or ""})};</script>',
            clip(f"When does {name} update? Past updates and events, how often new ones "
                 f"arrive, and the days its player count jumped."),
            wide=True, banner=c["banner"],
            canon=f"/updates/{s}.html", image=c["banner"] or c["icon"] or "",
            trail=trail + [(f"{name} player count", f"/game/{s}.html"),
                           ("Update history", f"/updates/{s}.html")],
            # An update page with nothing on it is a thin page, so we keep it on the
            # site (the button still works) but ask Google not to list it.
            noindex=thin or not upd, modified=iso_day(a["last"])))

        write(f"game/{s}.html", page(
            seo_title(f"{name} Player Count & Best Times to Play",
                      f"{name} Player Count and Best Times",
                      f"{name} Player Count"), body,
            clip(f"{name} has about {a['avg7']:,} players at a typical moment, and we have "
                 f"seen {a['peak']:,} at once. Its player count history, busiest and quietest "
                 f"hours, and the best time to play."),
            wide=True, banner=c["banner"], back=where, canon=f"/game/{s}.html",
            image=c["banner"] or c["icon"] or "", trail=trail + [(name, f"/game/{s}.html")],
            schema=game_schema(c, a, meta, qa), noindex=thin, modified=iso_day(a["last"])))

    print(f"Built {len(cards)} game pages.")

    # ---- the short list of games the search button loads. Kept separate from
    # data.json, which also carries a week of player counts per game and is far too
    # big to fetch just to search by name.
    write("games.json", json.dumps(
        [{"s": c["slug"], "n": c["name"], "i": c["icon"] or ""}
         for c in sorted(cards, key=lambda c: c["name"].lower())],
        separators=(",", ":")))

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
        biggest = cg[0]
        write(f"category/{slug(g)}.html", page(
            seo_title(f"{g} Roblox Games: Player Counts & Best Times",
                      f"{g} Roblox Games by Player Count"),
            f'<div class="hero"><h1>{html.escape(g)} Roblox games: player counts and '
            f'best times to play</h1><p class="lede">Live-tracked player counts for '
            f'{count} popular {html.escape(g.lower())} games on Roblox. '
            f'{html.escape(biggest["name"])} is the busiest, with about '
            f'{biggest["avg"]:,} players at a typical moment. '
            f'Pick a game to see its week, its events and its updates.</p></div>'
            + ask_html(f'Showing all {count}, most popular first.')
            + row_head("", f'<span class="mut small">{count}</span>')
            + grid(cg, "all")
            + table_of(cg)
            + '<p><a href="/">&larr; All Roblox player counts</a></p>'
            + ask_js(cg),
            clip(f"Player counts for {len(cg)} {g.lower()} games on Roblox, and when each one "
                 f"is busiest and quietest. Updated every night."),
            wide=True, banner=biggest["banner"], canon=f"/category/{slug(g)}.html",
            image=biggest["banner"] or biggest["icon"] or "",
            trail=[("All games", "/"), (f"{g} games", f"/category/{slug(g)}.html")],
            schema=[item_list(cg, f"{g} Roblox games by player count")]))
    pills = "".join(f'<a href="{u}">{html.escape(g)}</a>' for g, u in cat_pages)


    # ---- homepage
    # Two numbers worth saying out loud, because they are the reason to trust the rest
    # of the site: how many games we watch and how many readings we have taken.
    total_samples = sum(c["samples"] for c in cards)
    top = cards[0] if cards else None
    body = (
        '<div class="hero rise"><h1>Roblox player counts and the <em>best times</em> to play</h1>'
        f'<p class="lede">We track the player count of {len(cards)} popular Roblox games about every '
        f'10 minutes &ndash; {total_samples:,} readings so far &ndash; and turn them into an '
        'hour-by-hour picture of each game\'s week, in your own timezone. Pick a quiet hour for '
        'easy claims and no queues, or a busy one for trading and events.</p></div>'
        '<input id="s" type="search" placeholder="Search for a game" aria-label="Search for a game">'
        + ask_html()
        # The categories used to be a bare row of pills under the chooser, with nothing
        # saying what they were. On a phone they wrapped onto five lines, which read as
        # clutter rather than as a list you could use.
        + f'<h2 style="margin-top:22px">Browse by category</h2><div class="pills">{pills}</div>'
        '<section id="favs" hidden>' + row_head("Your saved games") +
        '<ul class="grid" id="favgrid"></ul></section>'
        + row_head("All games", f'<span class="mut small">{len(cards)} games</span>')
        + grid(cards, "all")
        + ('<h2 style="margin-top:30px">What you can do here</h2>'
           '<div class="card"><ul>'
           '<li><a href="/popular.html">Most played Roblox games</a> &ndash; every game we '
           'track, ranked by how many people are in it at a typical moment.</li>'
           '<li><a href="/trending.html">Trending games</a> &ndash; the biggest gainers and '
           'losers this week, from two weeks of player counts.</li>'
           '<li><a href="/busiest-hours.html">When is Roblox busiest?</a> &ndash; the busiest '
           'and quietest hours across every game we watch.</li>'
           '<li><a href="/compare.html">Compare two games</a> &ndash; put their weeks side by '
           'side and see which is less crowded.</li>'
           '<li><a href="/plan.html">Plan a session</a> &ndash; a countdown to the next quiet '
           'or busy stretch for any game.</li>'
           '<li><a href="/events.html">Event calendar</a> &ndash; what the creators have '
           'announced, so you know which hours will be packed.</li>'
           '<li><b>Remind me</b> &ndash; on any game\'s page, tick the days you want and add '
           'them straight to your phone\'s calendar, each one at that day\'s own quiet (or '
           'busy) hour. No account, and nothing about you is stored.</li>'
           '</ul></div>'
           '<h2>Where the numbers come from</h2>'
           '<div class="card"><p>Roblox publishes how many people are in each game right now. '
           'We read that figure for every game on our list about every 10 minutes and keep it, '
           'which '
           'is something Roblox itself does not show you: it tells you about now, not about last '
           'Tuesday. Averaging those readings by hour and weekday gives each game\'s rhythm, and '
           'comparing one week with the next shows whether it is growing or shrinking.</p>'
           '<p class="mut small">Averages are estimates built from samples, so treat them as a '
           'good guess rather than an official figure. The highest player counts we quote are '
           'different: those are single readings we really recorded. Nothing here says whether '
           'a game is good, fair or suitable for a child.</p></div>')
        + ask_js(cards))
    write("index.html", page(
        f"Roblox Player Counts & Best Times to Play Games | {SITE}", body,
        "Track Roblox game player counts, discover the busiest and quietest times to play, "
        "explore trending games, and compare player activity throughout the day.",
        wide=True, nav="home", back=None, canon="/",
        image=top["icon"] if top else "",
        schema=[{"@type": "WebSite", "name": SITE, "url": abs_url("/"),
                 "description": ("Player counts and best times to play for popular Roblox "
                                 "games, updated every night."),
                 "inLanguage": "en",
                 "publisher": {"@type": "Organization", "name": SITE, "url": abs_url("/")}}],
        modified=iso_day(now)))   # nowhere to go back to

    # ---- the pages across the top
    up = sorted([c for c in cards if c["trend"] is not None and c["trend"] >= 5],
                key=lambda c: -c["trend"])
    down = sorted([c for c in cards if c["trend"] is not None and c["trend"] <= -5],
                  key=lambda c: c["trend"])
    none = ('<p class="none">None right now. We compare the last 7 days with the 7 days before, so games '
            'need two weeks of player counts first.</p>')

    list_page("popular", seo_title("Most Played Roblox Games by Player Count"),
              "Most played Roblox games right now",
              f"All {len(cards)} games we track, ranked by how many people are in the game at a "
              f"typical moment over the last 7 days. Rebuilt every night.",
              cards,
              "Roblox game rankings by live player count: the most played games we track, "
              "with typical and peak players for each. Updated every night.",
              listname="Most played Roblox games by typical player count")
    list_page("growing", seo_title("Roblox Games Growing Fastest This Week"),
              "Roblox games that are growing",
              "These games have more players than they did a week ago. We compare the last "
              "7 days of player counts with the 7 days before, every night.",
              up,
              "Which Roblox games are gaining players this week, measured from our own "
              "player count history.",
              listname="Roblox games gaining players this week")
    list_page("shrinking", seo_title("Roblox Games Losing Players This Week"),
              "Roblox games that are shrinking",
              "These games have fewer players than they did a week ago. Losing players does "
              "not mean a game is bad, and most of them are still busy at peak times.",
              down,
              "Which Roblox games are losing players this week, measured from our own "
              "player count history.",
              listname="Roblox games losing players this week")

    rows = "".join(
        f'<tr><td><a href="/game/{c["slug"]}.html">{html.escape(c["name"])}</a></td>'
        f'<td>{c["avg"]:,}</td><td>{trend_short(c["trend"]) or "<span class=mut>steady</span>"}</td></tr>'
        for c in up[:10] + down[:10])
    write("trending.html", page(
        seo_title("Trending Roblox Games: Gainers and Losers"),
        '<div class="hero"><h1>Trending Roblox games this week</h1>'
        '<p class="lede">Every night we compare the last 7 days of player counts with the 7 days before. '
        'These are the games that moved the most.</p></div>'
        + row_head("Biggest gainers") + (grid(up[:12]) if up else none) +
        row_head("Biggest losers") + (grid(down[:12]) if down else none)
        + (f'<h2 style="margin-top:28px">The numbers</h2><div class="wrap"><table class="tbl">'
           f'<thead><tr><th>Game</th><th>Typical players</th><th>vs last week</th></tr></thead>'
           f'<tbody>{rows}</tbody></table></div>'
           if rows else "")
        + '<p><a href="/">&larr; All Roblox player counts</a></p>',
        "Which Roblox games gained and lost the most players this week, worked out from our "
        "own player count history and updated every night.",
        wide=True, nav="trending", canon="/trending.html",
        trail=[("All games", "/"), ("Trending", "/trending.html")],
        schema=[item_list(up[:12], "Roblox games trending up this week")] if up else None,
        noindex=not (up or down), modified=iso_day(now)))

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
                       + '</span>'
                       + ("" if e["start"] <= now else
                          remind_btn("/" + event_ics_name(e["slug"], e)))
                       + '</li>')
        return f'<ul class="evt">{"".join(out)}</ul>' if out else ""

    write("events.html", page(
        seo_title("Roblox Game Events Calendar: On Now and Next"),
        '<div class="hero"><h1>Roblox game events calendar</h1><p class="lede">Events and updates the game creators '
        'themselves have put on the Roblox calendar, for every game we track. Expect these hours to be busy.</p></div>'
        + (f'<h2 style="margin-top:22px">Happening now</h2>{ev_list(live)}' if live else "")
        + (f'<h2 style="margin-top:26px">Coming up</h2>{ev_list(soon)}' if soon else "")
        + ("" if live or soon else '<p class="none">No events are listed right now. Creators usually '
                                   'announce them a few days ahead, so check back soon.</p>')
        + '<p><a href="/">&larr; All Roblox player counts</a></p>',
        "Every upcoming Roblox game event and update we know about, with the dates they run "
        "and the games they belong to.",
        nav="events", canon="/events.html",
        trail=[("All games", "/"), ("Events", "/events.html")],
        noindex=not (live or soon), modified=iso_day(now)))

    # ---- compare two games
    write("compare.html", page(
        seo_title("Roblox Game Comparison: Compare Player Counts"),
        '<div class="hero"><h1>Compare two Roblox games</h1><p class="lede">Put two games side by side, hour by hour, '
        'to answer things like &ldquo;which one is less crowded on Saturday?&rdquo;</p></div>'
        '<div class="card" id="cmp" hidden><div class="two">'
        '<label>First game<br><select class="sel" id="ga"></select></label>'
        '<label>Second game<br><select class="sel" id="gb"></select></label></div>'
        '<div class="days" id="days"></div><div class="bars cols" id="bars"></div>'
        '<div class="axis"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span></div>'
        '<div class="legend"><i style="background:var(--acc)"></i><span id="alab"></span>'
        '<i style="background:var(--alt);margin-left:10px"></i><span id="blab"></span></div>'
        '<p id="verdict" style="margin-top:14px"></p>'
        '<div class="stats" id="nums"></div></div>'
        '<p class="mut small" id="load">Loading the games&hellip;</p>'
        + table_of(cards[:20])
        + '<p><a href="/">&larr; All Roblox player counts</a></p>',
        "Compare two Roblox games hour by hour and see which has more players, and which is "
        "quieter, on any day of the week.",
        nav="compare", canon="/compare.html",
        trail=[("All games", "/"), ("Compare", "/compare.html")],
        tail=f"<script>{SHARED_JS}</script><script>{COMPARE_JS}</script>"))

    # ---- plan a session
    write("plan.html", page(
        seo_title("Best Time to Play: Next Quiet or Busy Hours"),
        '<div class="hero"><h1>Plan my Roblox session</h1><p class="lede">Pick a game, say whether you want it quiet '
        'or busy, and we will count down to the next good block of time in your timezone.</p></div>'
        '<div class="card" id="plan" hidden>'
        '<label>Game<br><select class="sel" id="g"></select></label>'
        '<p class="mut small" style="margin-top:14px">What do you want?</p>'
        '<div class="days" id="planbtns"><button data-m="quiet" aria-pressed="true">Quiet</button>'
        '<button data-m="busy" aria-pressed="false">Busy</button></div>'
        '<div id="out"></div></div>'
        '<p class="mut small" id="load">Loading the games&hellip;</p>'
        '<p><a href="/busiest-hours.html">When is Roblox busiest overall?</a></p>'
        '<p><a href="/">&larr; All Roblox player counts</a></p>',
        "Find the next quiet or busy hours for any Roblox game, counted down in your own "
        "timezone from our hour-by-hour player count history.",
        nav="plan", canon="/plan.html",
        trail=[("All games", "/"), ("Plan a session", "/plan.html")],
        tail=f"<script>{SHARED_JS}</script><script>{PLAN_JS}</script>"))

    # ---- when is Roblox busiest, across everything we watch
    write("busiest-hours.html", busy_page(cards, now))

    # ---- the plain pages
    write("about.html", page(
        seo_title(f"About {SITE}: How We Measure Player Counts"), about_body(),
        f"What {SITE} is, how it measures when Roblox games are busy, and what it does not "
        f"tell you.", canon="/about.html",
        trail=[("All games", "/"), ("About", "/about.html")]))
    write("privacy.html", page(
        seo_title(f"Privacy Policy - {SITE}"), privacy_body(),
        f"What {SITE} stores, what it never asks for, and how to delete your data.",
        canon="/privacy.html", trail=[("All games", "/"), ("Privacy Policy", "/privacy.html")]))
    write("terms.html", page(
        seo_title(f"Terms of Service - {SITE}"), terms_body(),
        f"The rules for using {SITE}, written in plain language: what the site is, what the "
        f"numbers mean, and why they are estimates rather than official Roblox figures.",
        canon="/terms.html", trail=[("All games", "/"), ("Terms", "/terms.html")]))

    # A page for addresses that do not exist. The worker hands this back with a 404
    # status, so a search engine knows the page is really gone instead of guessing.
    write("404.html", page(
        f"Page not found - {SITE}",
        '<div class="hero"><h1>We could not find that page</h1>'
        '<p class="lede">The address may be old, or a game may have dropped off our list. '
        'Everything we track is one tap away.</p></div>'
        '<p><a class="btn" href="/">See every Roblox player count</a></p>'
        + row_head("Most popular right now") + grid(cards[:12]),
        "That page does not exist. Browse every Roblox game player count we track instead.",
        wide=True, back=None, canon="/404.html", noindex=True))

    # ---- sitemap and robots
    #
    # The sitemap is the list of pages we are asking Google to look at, so it holds
    # only pages that are worth looking at: a game still waiting for data is left out
    # until index_ok() says it has enough, and so is an empty list page. Addresses in
    # a sitemap have to be absolute, which is why DOMAIN has to be filled in before
    # this is any use at all.
    base = DOMAIN.rstrip("/")
    today = iso_day(now)
    pages = [("/", "1.0", today), ("/popular.html", "0.9", today)]
    for u in [u for _, _, u in TABS if u not in ("/", "/popular.html")]:
        pages.append((u, "0.7", today))
    pages.append(("/busiest-hours.html", "0.8", today))
    pages += [(u, "0.7", today) for _, u in cat_pages]
    for c in cards:
        if not index_ok(c):
            continue
        last = iso_day(c["a"]["last"])
        pages.append((f'/game/{c["slug"]}.html', "0.9", last))
        if c.get("has_updates"):
            pages.append((f'/updates/{c["slug"]}.html', "0.5", last))
    pages += [("/about.html", "0.3", today),
              ("/privacy.html", "0.2", today), ("/terms.html", "0.2", today)]

    def entry(u, pri, mod):
        return (f"<url><loc>{html.escape(base + u)}</loc><lastmod>{mod}</lastmod>"
                f"<changefreq>daily</changefreq><priority>{pri}</priority></url>")

    write("sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "\n".join(entry(*p) for p in pages) + "\n</urlset>\n")
    # The old plain-text sitemap, kept so an address already given to Google still works.
    write("sitemap.txt", "\n".join(base + u for u, _, _ in pages) + "\n")
    if not base:
        print("  ! DOMAIN is empty in build_site.py, so sitemap.xml has no web addresses in it.\n"
              "    Google will reject it. Set DOMAIN once you have bought the domain.")
    skipped = [c["name"] for c in cards if not index_ok(c)]
    if skipped:
        print(f"  {len(skipped)} game page(s) kept out of the sitemap until they have more "
              f"data: " + ", ".join(skipped[:4]) + (" ..." if len(skipped) > 4 else ""))

    # Just enough for the search box. data.json carries every game's whole week
    # and is far too big to fetch just to answer "what is this game called".
    write("games.json", json.dumps(
        [{"s": c["slug"], "n": c["name"], "i": c["icon"] or ""}
         for c in sorted(cards, key=lambda c: c["name"].lower())],
        separators=(",", ":")))
    write("favicon.svg", FAVICON)
    # data.json and games.json are left crawlable on purpose: the Compare and Plan
    # pages fetch them, and a search engine that cannot read them sees those two
    # pages as empty. /admin is the only thing shut out.
    write("robots.txt", "User-agent: *\nDisallow: /\n" if NOINDEX else
          "User-agent: *\nDisallow: /admin\nDisallow: /api/\nAllow: /\n\n"
          + (f"Sitemap: {base}/sitemap.xml\n" if base else
             "# Sitemap: set DOMAIN in build_site.py and this line appears\n"))

    write_stats(db, games, cards, waiting)
    write_theme()
    prune()                        # last, so a build that fails never deletes anything
    db.close()
    print(f"Wrote {len(pages)} addresses into {OUT}/sitemap.xml in "
          f"{time.time() - started:.0f} seconds.")
    if waiting:
        print(f"{len(waiting)} games are still collecting data and have no page yet.")


if __name__ == "__main__":
    main()
