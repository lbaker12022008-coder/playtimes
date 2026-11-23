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
import html, json, math, os, re, sqlite3, statistics, struct, time, unicodedata, zlib
from datetime import datetime, timedelta, timezone

import roblox_api

SITE = "PlayTime"          # the site's name (don't put "Roblox" in your domain name)
MIN_SAMPLES = 200          # how many player counts a game needs before it gets a page
# Set to the launch value on 2 Nov 2026. A game below this keeps no page at all and
# prune() deletes any it had, so lowering it back to 2 is the undo and the pages
# come straight back on the next build - nothing is lost, the readings live on the
# data branch. Each game gains about 71 a day at the current collection rate.
ADS = ""                   # paste your AdSense <script> here
NOINDEX = False            # True = ask Google NOT to list the site (set False when you launch)
OUT = os.environ.get("SITE_OUT") or "docs"   # which folder to write the site into
DOMAIN = "https://playtimestats.com"   # no slash on the end; this is what makes the sitemap real
ROBUX_USD = 0.0125         # rough dollars per Robux (800 Robux costs $9.99)
CONTACT = "contact@playtimestats.com"  # forwarded to the owner by Cloudflare Email Routing
POLICY_DATE = "November 19, 2026"  # change this whenever you edit the Privacy Policy

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
#   draws the second game on /compare, the second set of bars in the hourly
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
/* The light a control wears when it is pointed at: a ring that follows its border
   and a short glow beyond it. It lived on .chip,.pills a and nowhere else, so every
   other box-shadow:var(--rim) in this sheet - the bells, the notification switches -
   resolved to an invalid value and drew NOTHING, which is not a thing you notice
   unless you measure it. On :root it reaches every control, and it still reads off
   --glowh and --glowa, so it stays in step with the tiles in both themes. */
:root{--rim:0 0 0 1px hsl(var(--glowh) 92% 62%/.5),0 0 12px hsl(var(--glowh) 92% 62%/var(--glowa))}
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
/* The three ways in appear in the bar here. They used to be hidden out of the
   panel at this width by three identical copies of a `.dtop .hnavrow` rule, all
   in this one block; the rows are gone from the panel at every width now, so the
   rule has nothing left to hide.
   `.hdr .hnav`, not `.hnav`: the base `.hnav{display:none}` is a one-class rule
   written further down the sheet, a media query adds no specificity, and a plain
   `.hnav` here simply lost to it - the bar stayed empty at every width. Same trap
   as `.hdr .nots`, `.acct .acctb` and `.shell>.w` before it. */
.hdr .hnav{display:block}
/* From 900px the bar carries the name, the bell and the magnifier, so the panel
   stops offering the same two things a second time.
   Written `.hdr .nots`, not `.nots`: the base `.nots,.acctbar{display:none}` is a
   one-class rule written FURTHER DOWN this stylesheet, and a media query adds no
   specificity at all, so a single class here simply loses to it and the bar stays
   empty at every width. Same trap as .w vs .shell>*, and .acctb vs .iconb. */
.hdr .nots,.hdr .acctbar{display:block}
.hdr .nots:empty,.hdr .acctbar:empty{display:none}
.notsrow{display:none}
/* The name is in the bar here and its own menu holds Sign out, so the panel stops
   offering the same person a second time. `.dtop .acct`, not `.acct`: the base
   rule is display:flex, one class, written further down - the same trap again.
   THIS RULE DEPENDS ON THE BAR OFFERING SIGN-IN. For a few hours on 17 Nov 2026
   the pill was drawn only for somebody already signed in, and hiding this block
   left a signed-out visitor on a computer with no way to sign in anywhere on the
   site - the page looked perfectly normal, there was simply nothing there. If the
   signed-out pill is ever taken out of the bar, this has to go back to hiding only
   the signed-in half. acct.js walks all three states at ten widths and is what
   caught it. */
.dtop .acct{display:none}
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
/* width:100% is not spare. .w is a grid item with auto side margins, and an item
   with auto margins is not stretched to its track - it is sized to its contents
   and centred in whatever is left. So a page whose contents happened to be narrow
   drew a narrow column and centred that: /popular came out 1024px wide and
   /trending 1001px inside the same 1400px band, each centred on its own, so
   every one of them started at a different distance from the logo (475px, 464px,
   446px, 404px at 1920px). Asking for the full width and capping it with max-width
   makes every page the same width and lines them all up under the header. */
.w{width:100%;max-width:min(820px,100%);margin:0 auto;padding:8px 16px 56px}
.w.wide{max-width:min(1200px,100%)}
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
/* ...and that max-width:100% is one class, exactly like a plain .w, so it beat
   .w's own max-width on source order and the reading pages ran the full width of
   the window: Privacy, Terms, About, Events, Compare and Plan measured 1920px
   across on a 1920px screen, flush to the left edge, while the logo above them
   sat 280px in. .w.wide was never affected because two classes outrank one, which
   is why only the reading pages looked wrong. Re-stating both clamps as children
   of .shell gives them the weight to survive, the same trick the wide pages got
   for free. Keep them after .shell>*, and keep the min(...,100%) form. */
.shell>.w{max-width:min(820px,100%)}
.shell>.w.wide{max-width:min(1200px,100%)}
.rail{display:none}
.shell.ads{gap:20px}
/* The rails belong beside the words, not out at the edges of the screen. A 1fr
   middle track eats every spare pixel, so on a 2560px monitor the reading column
   stayed 820px in the middle and the ads sat nearly 700px away from it, reading as
   two stray boxes rather than a page. Capping the middle track at the width the
   page actually uses lets justify-content centre all three together instead.
   minmax rather than a flat width, so a screen between 1480 and 1776px shrinks the
   wide pages instead of scrolling sideways. */
@media(min-width:1380px){.shell.ads{grid-template-columns:168px minmax(0,820px) 168px}
.shell.ads.wideads{grid-template-columns:168px minmax(0,1200px) 168px}
.shell.ads .rail{display:block;position:sticky;top:112px;align-self:start;height:600px;overflow:hidden}}
/* The ad rails used to shrink the bar as well, so the logo kept sitting above the
   first word: 376px (two 168px rails and two 20px gaps) came off the band between
   1380 and 1576px. That is 196px at 1440px - the commonest laptop width there is -
   and it pushed the last two links in the bar off the edge of it. The band holds
   at 1200px now whatever else is on the page. See the note by .hdr .in. */
/* The strip along the bottom only exists at all when ads are switched on, and it is
   the ONLY ad slot a phone or a tablet ever sees: the side rails need 1480px. It used
   to start at 900px, which meant every phone and an iPad held upright showed no ads
   at all - and this audience is overwhelmingly on phones, so that was most of the
   site's income switched off. It is deliberately short at 66px (about a 50px banner
   once the padding and rule are taken off), because a bar on a 844px-tall phone is
   spending screen the visitor came for; the laptop strip keeps its 98px.
   z-index 8 is below the header (9), the scrim (25) and the drawer and search sheet
   (30), so an open menu covers the ad rather than fighting it.
   position:sticky, not fixed: a sticky element still takes its space at the end of
   the page, so the footer is never left permanently hidden underneath it - and a
   fixed one would be trapped by the backdrop-filter above it anyway. */
/* The bar across the bottom of a phone. Fixed, so it is there wherever the page
   has been scrolled to - the point of it is that a thumb reaches the bottom of a
   phone and not the top corner.
   z-index 9 matches the header: above the page and above the bottom ad strip (8),
   below the scrim (25) and the drawer and sheet (30), so an open menu still covers
   it. The ad strip is pushed up by exactly this bar's height rather than being
   covered, and .shell gets the same padding so the footer is not hidden under it
   either - the two were the things that broke when this was first tried. */
/* The three ways in, as buttons across the homepage, under the search box. They
   are in the bar across the top on a computer and there is no room for them there
   on a phone, so on a phone they come back to the one page everybody starts on.
   The base rule and the media query are written NEXT TO EACH OTHER on purpose:
   both are one class, a media query adds no specificity, and source order is all
   that decides it - the trap this stylesheet keeps setting. */
.homenav{display:none}
@media(max-width:899px){.homenav{display:grid;
grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:12px 0 2px}}
.homenav a{display:flex;align-items:center;justify-content:center;text-align:center;
min-height:46px;padding:9px 6px;border:1px solid var(--line);border-radius:12px;
background:var(--card);color:var(--ink);text-decoration:none;font-weight:700;
font-size:.9rem;line-height:1.2}
.homenav a:hover,.homenav a:focus-visible{border-color:var(--acc);box-shadow:var(--rim)}
.homenav a.on{border-color:var(--acc);color:var(--acc)}

.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:9;display:grid;
grid-template-columns:repeat(4,minmax(0,1fr));background:var(--glass);
backdrop-filter:saturate(1.4) blur(12px);border-top:1px solid var(--line);
padding-bottom:env(safe-area-inset-bottom)}
.tabbar .tbb{display:flex;flex-direction:column;align-items:center;justify-content:center;
gap:3px;min-height:56px;padding:7px 4px 8px;border:0;background:none;cursor:pointer;
color:var(--mut);font:inherit;font-size:.72rem;font-weight:700;text-decoration:none;
position:relative}
.tabbar .tbb svg{width:21px;height:21px;fill:currentColor}
.tabbar .tbb:hover,.tabbar .tbb:focus-visible{color:var(--ink)}
.tabbar .tbb.on{color:var(--acc)}
/* The same underline the tabs across a game's pages wear, so the two read as one
   idea: here is where you are. */
.tabbar .tbb.on::after{content:'';position:absolute;left:28%;right:28%;top:0;height:3px;
border-radius:0 0 3px 3px;background:hsl(var(--glowh) 92% 72%);
box-shadow:0 0 6px hsl(var(--glowh) 92% 72%/.95),0 0 15px 2px hsl(var(--glowh) 92% 72%/.6)}
@media(min-width:900px){.tabbar{display:none}}
.shell{padding-bottom:62px}
@media(min-width:900px){.shell{padding-bottom:0}}
.railb{display:block;position:sticky;bottom:62px;z-index:8;
background:var(--glass);backdrop-filter:blur(10px);border-top:1px solid var(--line);
padding:6px;text-align:center;height:66px}
@media(min-width:900px){.railb{height:98px;bottom:0}}
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
/* scroll-margin-top keeps a jumped-to heading clear of the sticky header,
   which is about 65px tall here and 57px on a phone. */
.bento>*{grid-column:1/-1;margin:0;min-width:0;scroll-margin-top:78px}   /* full width by default; the grid owns the spacing */
/* Two short cards sharing one column, so the tall card beside them has something
   to sit against. The grid cannot do this by itself: its rows are rigid, so a card
   shorter than the one next to it simply leaves the space under it empty - "The
   short answer" is 239px tall and "Plan my session" is 735px, which left a 496px
   hole on every game page. A nested column is used rather than grid-row:span 2
   because spanning splits the slack evenly between the rows, which would open an
   arbitrary gap BETWEEN the two cards instead of closing it. Its gap has to be
   kept level with the bento's own, both here and in the wide block above. */
.lstack{display:flex;flex-direction:column;gap:14px}
.lstack>.card{margin:0;min-width:0;scroll-margin-top:78px}
.mut{color:var(--mut)}.small{font-size:.9rem}
.up{color:var(--up)}.down{color:var(--down)}
.wrap{overflow-x:auto}
button,.btn,.chip,select{font:inherit}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
.ans p{margin:.35em 0;font-size:1.1rem}
/* The how-much-it-matters line sits under the busiest and quietest hours and is
   a remark on them rather than a third fact of the same weight, so it is smaller
   and muted. Two classes, because .ans p above is one and so is anything later
   that might claim a plain .swing. */
.ans p.swing{font-size:.95rem;color:var(--mut);margin-top:.6em}

/* top bar, with the sections across the top */
.hdr{position:sticky;top:0;z-index:9;background:var(--glass);backdrop-filter:saturate(1.4) blur(12px);border-bottom:1px solid var(--line);margin-bottom:6px}
/* One slim bar, about 52px tall, holding four things. */
.hdr .in{max-width:min(1200px,100%);margin:0 auto;padding:7px 16px}
/* 16px, not 20px, because .w uses 16px: the logo is meant to start exactly where
   the words below it start, and the phone block already pairs them at 14px. */
/* The band is the SAME on every page, and that is the point of it. It used to
   follow the column underneath - 820px on a reading page so the logo sat exactly
   above the first word - which meant that clicking Events, Compare or Plan in the
   bar shrank the bar itself by 244px, slid the logo 122px to the right and squeezed
   the eight links into a scrolling strip. A cap being respected, and it read as the
   page breaking. The logo now sits left of the words on a reading page, which is
   what most sites do and what nobody notices, and the bar never changes shape. */
/* The spacing of the bar, in one place (19 Nov 2026, owner's call: "the spacing
   is off, some things are really close to each other"). It had grown four
   different gaps with no system behind them - 12px after the logo, 16px before
   the sections, 24px after them and 12px between the controls at the right end -
   so a row of 42px squares 12px apart read as neither a group nor four separate
   buttons. It is three groups now, and the gaps say so:
     8px   INSIDE a group - the bell, the magnifier and the three lines
     14px  between the person and those tools
     18px  between groups - the logo, the game picker, the sections
     16px  to the edge of the bar, which is what the page below it uses
   The 8px base is the smallest of them and every wider gap is a margin added on
   top, so a new control dropped into the bar joins the tools group by default. */
.hrow{display:flex;align-items:center;gap:8px}
/* The same shape as the tabs across a game's pages, because they do the same job:
   here is where you are, here is what else there is. Hidden below 900px, where the
   bar has room for the logo, the game picker and two buttons and nothing else -
   the panel behind the three lines carries the same three links at that width, the
   trick the search magnifier and the bell already use. */
/* min-width:0 and the overflow are the net under all of this: .hnav is a flex item
   in a nowrap row, and a flex item is sized to its contents unless told it may
   shrink - so a link too many pushed the whole bar wider than the phone it was on.
   It can scroll inside itself now and the page never moves. */
/* flex:0 0 auto - the sections do not shrink. They used to (0 1 auto), which is
   what let a long name squeeze them; the overflow is kept as a last net rather
   than as the usual case. */
.hnav{display:none;margin-left:10px;white-space:nowrap;min-width:0;flex:0 0 auto;
overflow-x:auto;scrollbar-width:none}
.hnav::-webkit-scrollbar{display:none}
/* Three links at 900px, all eight once there is room for them. Eight at 900 was
   measured dragging a 900px window sideways; the panel keeps the other five until
   the bar can really hold them. */
.hnav a.more{display:none}
@media(min-width:1200px){.hdr .hnav a.more{display:inline-block}}
/* 11px and .9rem are measured, not chosen: at 12px and .93rem the eight links came
   to 606px and the bar could spare 595 with somebody signed in, so Plan sat over the
   edge and the whole strip scrolled. */
.hnav a{display:inline-block;margin:0 11px 0 0;padding:6px 1px 7px;color:var(--mut);
text-decoration:none;font-weight:700;font-size:.9rem;position:relative}
.hnav a:hover,.hnav a:focus-visible{color:var(--ink)}
.hnav a.on{color:var(--ink)}
/* Half the height and about a third of the glow of the one on a game's tabs. The
   same mark at the same size among eight small links read as a highlighter pen. */
.hnav a.on::after{content:'';position:absolute;left:1px;right:1px;bottom:1px;height:2px;
border-radius:2px;background:hsl(var(--glowh) 92% 72%);
box-shadow:0 0 4px hsl(var(--glowh) 92% 72%/.8),0 0 8px hsl(var(--glowh) 92% 72%/.4)}
.hrow .gap{flex:1 1 auto}
/* The account lives in the bar, beside the search, rather than inside the panel
   behind the three lines: it is the one control that says something about the
   person rather than about the page, and buried in a menu nobody found it.
   Signed out it is a round button that leads to Roblox; signed in, the person's
   own picture takes its place and their name and Sign out move into a small menu
   underneath - the bar has room for a face, not for a name and a verb.
   From 900px up both forms widen into a pill and say what they are, because an
   unlabelled glyph is the one kind of button up here whose meaning cannot be
   guessed, which is why the bell is the only thing in the bar that is new: it is
   drawn for signed-in people, who have already met notifications on a game page.
   :empty is what keeps the bar tidy when the Roblox keys are missing - ptPaint()
   writes nothing at all then, and an empty div would hold a gap open. */
/* THE ACCOUNT IS IN THE PANEL, NOT THE BAR. It was moved into the bar in Nov 2026
   on the grounds that a face is easier to find than a menu item, and moved back out
   in Nov 2026 when the owner wanted the bar down to icons so the notification bell
   could live there. The name and Sign out were already in a menu hanging off the
   bar, so this is the same two things in a place with room for them.
   :empty is what keeps the panel tidy when the Roblox keys are missing - ptPaint()
   writes nothing at all then, and an empty div would hold a gap open. */
.acct{display:flex;flex-direction:column;gap:2px;margin-bottom:8px;padding-bottom:8px;
border-bottom:1px solid var(--line)}
.acct:empty{display:none}
.acct form{margin:0}
.acct .drow,.dtop a.drow{text-decoration:none}
.acct svg{width:18px;height:18px;flex:none;fill:currentColor}
/* The account row in the panel, on a phone: the name, and Sign out folded inside.
   The arrow is two borders rather than a picture, the way .gdesc and .howto do it. */
.apop{margin:0}
.apop>summary{cursor:pointer;list-style:none}
.apop>summary::-webkit-details-marker{display:none}
.apop>summary::after{content:"";margin-left:auto;flex:none;width:8px;height:8px;
border-right:2px solid var(--mut);border-bottom:2px solid var(--mut);
transform:translateY(-2px) rotate(45deg);transition:transform .2s}
.apop[open]>summary::after{transform:translateY(2px) rotate(225deg)}
.aname{font-weight:700;min-width:0;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
.asub2{display:block;padding:2px 13px 7px;color:var(--mut);font-size:.78rem;
font-style:normal}
.apop form{margin:0}
/* Width and height are on the tag too, so the panel does not jump when the picture
   arrives. flex:0 0 auto stops a long display name squeezing it. */
.acct .pfp{width:34px;height:34px;border-radius:50%;flex:0 0 auto;object-fit:cover;
border:1px solid var(--line);background:var(--shade)}

/* The notification bell, at the right end of the bar, and the list it opens.
   Drawn only for somebody signed in: notifications are only offered to signed-in
   people, so for anybody else there is nothing it could ever list. */
/* Both of these are computer-only. Written as display:none first and turned on
   inside the 900px block, the same way .deskonly works, so the phone case is the
   default and a new width cannot accidentally reveal them. */
.nots,.acctbar{display:none;flex:none}
/* A long Roblox display name made the pill 182px instead of 94px and pushed
   Compare and Plan off the end of the bar - at EVERY width, 1920px included,
   because the band is capped at 1200px however wide the screen is. The bar is
   navigation first, so the sections hold their width (.hnav is flex:0 0 auto
   below) and the NAME gives way instead: min-width:0 all the way down to .albl,
   which already has the ellipsis. The whole name is still one press away, written
   across the button the menu hangs from. */
/* 14px, so the person is not jammed against the sections on a narrow window.
   This is the only extra margin left at this end of the bar: the four controls
   themselves are evenly spaced on .hrow's own 8px. */
.acctbar{flex:0 1 auto;min-width:0;margin-left:14px}
/* The bell used to carry a further 6px, to hold the tools off the account at 14
   while they sat at 8 from each other - which was right while the account was a
   pill with a name across it and a different shape from everything beside it.
   Signed in it is now the same 42px square as the bell, the magnifier and the
   three lines, and one wider gap among four identical squares reads as a mistake
   rather than as a grouping. They are all 8px apart. The signed-out button still
   carries its words, but it is the same height and corner radius and sits in the
   same place, so an even row is right there too. */
.acctb{display:flex;align-items:center;gap:8px;max-width:210px;min-width:0;height:42px;
padding:0 13px;border:1px solid var(--line);border-radius:12px;background:var(--card);
color:var(--ink);font:inherit;font-weight:700;cursor:pointer}
.acctb:hover,.acctb:focus-visible{border-color:var(--acc)}
/* Signed out this is an <a>, not a <button>, and it keeps its words: a lone
   person-glyph with no label is not an invitation to sign in. Signed in it is the
   picture alone, the same 42px square as the bell, the magnifier and the three
   lines beside it - four squares in a row rather than three and a pill. Two
   classes, because .acctb above and .iconb further down are both one class and a
   later one-class rule would win. */
.acctb{text-decoration:none}
.acctbar .acctb.onlypic{width:42px;padding:0;gap:0;justify-content:center}
.acctbar .acctb.onlypic .pfp{width:30px;height:30px}
.acctb svg{width:18px;height:18px;flex:none;fill:currentColor}
.acctbar .pfp{width:26px;height:26px;border-radius:50%;flex:0 0 auto;object-fit:cover;
border:1px solid var(--line);background:var(--shade)}
.albl{max-width:128px;min-width:0;flex:0 1 auto;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap;font-size:.9rem}
/* The menu under the name in the bar (17 Nov 2026). It holds what the panel used to
   hold for a signed-in person on a computer - who you are and the way out - so the
   panel drops its own copy from 900px up and there is still only ever one of each.
   Below 900px there is no name in the bar, so the panel keeps it and this is never
   drawn.
   It is written OUTSIDE <header> with the drawer and the sheet, and for the same
   reason: .hdr has backdrop-filter, which makes the header the containing block for
   anything position:fixed inside it. Script puts it under the pill. */
.amenu{position:fixed;z-index:30;width:218px;max-width:calc(100vw - 24px);padding:6px;
background:var(--solid);border:1px solid var(--line);border-radius:14px;
box-shadow:var(--sh);animation:dropin .15s ease both}
.amenu[hidden]{display:none}
.amenu .asub{display:block;padding:8px 12px 9px;margin:0 0 4px;color:var(--mut);
font-size:.78rem;border-bottom:1px solid var(--line)}
/* The name, first line of the menu, since the bar no longer carries it. The
   ellipsis is here for the same reason it was on the pill: Roblox display names
   run long, and this box is 218px wide. */
.amenu .aname{display:block;margin-bottom:2px;color:var(--ink);font-size:.95rem;
font-weight:800;font-style:normal;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
.amenu form{margin:0}
/* The panel's Notifications row is the other half of the same arrangement: it shows
   on a phone, where the bell is not in the bar, and hides where the bell is. */
.notsrow:empty{display:none}
.notsrow svg{width:18px;height:18px;flex:none;fill:currentColor}
/* One game on /notifications: its name, then its three switches. The switches drop
   onto their own line on a narrow screen rather than squeezing the name out. */
.nlist{list-style:none;margin:0;padding:0}
.nrow{display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap;
padding:12px 0;border-bottom:1px solid var(--line)}
.nrow>a{display:flex;align-items:center;gap:11px;flex:1 1 170px;min-width:0;
text-decoration:none;color:var(--ink)}
.nrow img{width:34px;height:34px;border-radius:9px;flex:none;object-fit:cover}
.nrow>a span{flex:1 1 auto;min-width:0;font-weight:700;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* The events tickbox in the notification panel. A real checkbox rather than a third
   pill beside Quiet and Busy: those two are a choice between one and the other, and
   this is an extra on top of whichever was picked. */
/* The numbered steps on /install, each with a screenshot under it. The picture is
   capped well below its own width: these are phone screenshots, tall and narrow, and
   at full size one step would fill the screen and hide the fact that there are four.
   width and height are on the tag so the page does not jump as each one loads. */
.shots{padding-left:22px}
.shots>li{margin:0 0 22px}
.shots>li>p{margin:0 0 10px}
.shots img{display:block;width:100%;max-width:min(270px,100%);height:auto;
border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh)}
/* The computer screenshots are a browser window rather than a phone: landscape, and
   the thing being pointed at is a few pixels of address bar, so 270px would be
   unreadable. Two classes, so it wins over the rule above whatever the order. */
.shots.wide img{max-width:min(520px,100%)}
/* The two-line history chart, and the key under it. The key uses a coloured block
   rather than naming the colours in words: a colour named in text goes stale on the
   next palette change, which the 45-day caption did once already. */
.hist{display:block;width:100%;height:150px;margin:4px 0 2px}
/* A build-time chart that can be dragged (scrub() and SCRUB_JS). The dots are HTML
   rather than SVG circles because these charts stretch to fit with
   preserveAspectRatio none, which would squash a circle into an oval. */
.scrub{position:relative;margin:4px 0 2px;touch-action:pan-y;cursor:crosshair;outline-offset:4px}
/* The verdict sits right on top of this one, so it gets air above it as well as a
   taller box - squeezed between two blocks of text it read as a smudge. */
#dead .scrub{margin:12px 0 4px}
#dead .verdict{margin-top:12px}
.scrub>svg{margin:0}
/* The box that follows the pointer across a chart. Fixed to the window and put on
   <body>, so no card can clip it and no stacking context can bury it. Mouse only:
   under a finger it would be behind the finger, which is why the line of text
   under the chart stays on a phone and this takes its place on a computer. */
.chtip{position:fixed;z-index:40;pointer-events:none;opacity:0;transition:opacity .08s;
background:var(--solid);border:1px solid var(--line);border-radius:12px;
padding:8px 12px;font-size:.88rem;line-height:1.45;box-shadow:var(--sh);
width:max-content;max-width:calc(100vw - 16px)}
.chtip.on{opacity:1}
@media(min-width:900px){.readout.chartout{display:none}}
/* The same glow the HTML cursor dot wears, for the one drawn inside an SVG. */
.graph .lockdot{filter:drop-shadow(0 0 4px hsl(var(--glowh) 92% 66%/.9))}
.scrub .sline{position:absolute;top:0;bottom:0;width:0;border-left:1.5px dashed var(--ink);
pointer-events:none;transform:translateX(-.75px)}
/* Every reading on the line, so the chart shows what it is made of rather than
   only the shape of it. Purple like the line it belongs to, with a thin ring in
   the page's ink so one dot is still tellable from the next where they crowd. */
.scrub .pdot{position:absolute;width:8px;height:8px;border-radius:50%;
border:1.5px solid var(--ink);transform:translate(-50%,-50%);pointer-events:none;
opacity:.95}
/* The one being read is the other way round - ink filled, ringed in the line's own
   colour, with a little glow - so it reads as "this one" and never as another
   point that happens to be bigger. */
.scrub .sdot{position:absolute;width:13px;height:13px;border-radius:50%;
background:var(--ink);border:2.5px solid var(--acc);transform:translate(-50%,-50%);
pointer-events:none;display:none;
box-shadow:0 0 7px hsl(var(--glowh) 92% 66%/.85),0 0 16px hsl(var(--glowh) 92% 66%/.5)}
.scrub.on .sdot{display:block}
.hleg{margin:0 0 6px;font-size:.85rem;line-height:1.6;color:var(--mut)}
.hleg .k{display:inline-block;width:13px;height:3px;border-radius:2px;
margin:0 6px 3px 0;vertical-align:middle}
.hleg .k.acc{background:var(--acc)}
.hleg .k.alt{background:var(--alt)}
.nevt{display:flex;align-items:flex-start;gap:9px;margin:10px 0 2px;
font-size:.9rem;font-weight:600;cursor:pointer;line-height:1.45}
.nevt input{width:18px;height:18px;margin:1px 0 0;flex:none;accent-color:var(--acc);cursor:pointer}
/* The three switches. Each is on or off by itself - they were one Quiet-or-Busy
   choice until 16 Nov 2026, which made two perfectly compatible things exclusive.
   aria-pressed carries the state, so the styling and the screen reader cannot
   disagree about which are on. */
/* A bell sits under the heading of the section it belongs to, or in the row of
   buttons at the top of a game page. Same object in both places. */
.bellb{display:inline-flex;align-items:center;gap:8px;margin:0 0 10px;
padding:8px 15px;border:1px solid var(--line);border-radius:999px;background:var(--card);
color:var(--mut);font:inherit;font-size:.86rem;font-weight:700;cursor:pointer}
.bellb svg{width:15px;height:15px;flex:none;fill:currentColor}
.bellb:hover:not([disabled]),.bellb:focus-visible{color:var(--ink);box-shadow:var(--rim)}
.bellb[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:var(--btnink)}
.bellb[disabled]{opacity:.55;cursor:default}
a.bellb{text-decoration:none}
/* "Next event in 2d 4h 11m" - the one line somebody opening these cards is after. */
.nextline{margin:0 0 10px;font-size:.95rem;font-weight:600}
.nextline:empty{display:none}
.nextline .cd{font-variant-numeric:tabular-nums;color:var(--acc)}
.actions .bellb{margin:0}
/* A bell on a calendar row: smaller than one under a heading, because it is one of
   forty and the row above it is the thing being read. :empty is what keeps a row
   that cannot offer one from holding a gap open - the same trick .acct uses. */
.evt .evbell{display:block}
.evt .evbell .bellb{margin:9px 0 2px;padding:5px 12px;font-size:.78rem}
.evt .evbell .bellb svg{width:13px;height:13px}
#planbell{margin:12px 0 2px}
#planbell:empty{display:none}
.togs{display:flex;gap:7px;flex-wrap:wrap}
.tog{padding:8px 15px;border:1px solid var(--line);border-radius:999px;
background:var(--card);color:var(--mut);font:inherit;font-size:.88rem;font-weight:700;
cursor:pointer}
.tog:hover:not([disabled]),.tog:focus-visible{color:var(--ink);box-shadow:var(--rim)}
.tog[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:var(--btnink)}
.tog[disabled]{opacity:.55;cursor:default}
.saidit{margin:12px 0;padding:11px 13px;border:1px solid var(--line);
border-radius:12px;background:var(--shade);font-size:.92rem}
/* A game that is only on this list because it was saved, so the row reads as an
   offer rather than as something already switched on. */
.svd{display:block;font-style:normal;font-size:.72rem;font-weight:700;
letter-spacing:.04em;text-transform:uppercase;color:var(--mut)}
.logo{display:flex;align-items:center;gap:9px;font-weight:800;font-size:1.35rem;color:var(--ink);text-decoration:none;letter-spacing:-.02em;white-space:nowrap;margin-right:10px}
.logo .mark{width:32px;height:32px;flex:none}
.logo b{background:linear-gradient(95deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
/* The header is logo, name and game picker on the left, then the account, the
   search magnifier and the three-line button on the right. Light and dark is the
   one control still kept in the panel that button opens; search joins it below
   900px, where the bar has no room to offer both. */
/* the game switcher, top left */
/* The box is ONE size, the size it is when it says "Pick a game", whatever game is
   picked (owner's call, 20 Nov 2026). It used to grow with the name up to 240px,
   and signed in - with the person's name taking room at the other end of the bar -
   the bar squeezed .gpick narrower than the button inside it, so the button spilled
   out over Busy now. A fixed width cannot grow and flex:none stops the bar
   squeezing it; the name ends in an ellipsis inside it instead. 134px is the
   measured "Pick a game" box (133px in WebKit and Chrome) with a pixel spare, so
   those words never get an ellipsis of their own; the phone rule below is 130. */
.gpick{position:relative;min-width:0;flex:none}
.gpick>button{display:flex;align-items:center;gap:8px;width:134px;max-width:134px;min-width:0;padding:8px 13px;border-radius:12px;
border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;font-size:.95rem;font-weight:700}
.gpick>button:hover{border-color:var(--acc)}
.gpick img,.gpick .ph{width:24px;height:24px;border-radius:7px;flex:none;object-fit:cover;background:var(--line);font-size:.8rem}
.gpick .nm{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gpick .caret{color:var(--mut);flex:none;font-size:.7rem}
.gmenu{position:absolute;left:0;top:calc(100% + 6px);min-width:252px;max-width:84vw;background:var(--solid);
border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);padding:6px;z-index:20}
.gmenu[hidden]{display:none}
.gmenu p{margin:7px 10px 4px;font-size:.74rem;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.gmenu a{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:10px;text-decoration:none;color:var(--ink);font-size:.92rem}
.gmenu a:hover,.gmenu a:focus-visible{background:var(--shade)}
.gmenu a img,.gmenu a .ph{width:26px;height:26px;border-radius:7px;flex:none;object-fit:cover;background:var(--line);font-size:.9rem}
.gmenu .all{border-top:1px solid var(--line);margin-top:4px;padding-top:9px;font-weight:700;color:var(--acc)}
/* A long name in the list ends in an ellipsis rather than stretching it: sized to
   its longest name the list reached 387px. On a computer it is capped at 300px.
   It was briefly held to the box's own width, but the box is now a fixed 134px
   (see .gpick), which would leave a few letters per name - and an open dropdown
   covering the links beside it is what a dropdown does. Two classes throughout,
   because .gmenu's own rules are one class, and so is the overflow-wrap rule
   further down that would otherwise break a name over two lines instead of
   cutting it. The full name is in the row's title, for a mouse to hover. */
.gpick .gmenu a .nm{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap;overflow-wrap:normal}
@media(min-width:900px){.gpick .gmenu{max-width:300px}}
/* round icon button on the right of the header */
.iconb{display:grid;place-items:center;width:42px;height:42px;flex:none;border-radius:12px;
border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;padding:0}
.iconb:hover{border-color:var(--acc)}
/* The bell is an anchor, so it needs saying that it is not an underlined link. */
.iconb{text-decoration:none}
/* Shown only inside the min-width:900px block near the top of this stylesheet. */
.deskonly{display:none}
.iconb svg{width:19px;height:19px;fill:currentColor}
.themeic .moon{display:none}
:root[data-theme=dark] .themeic .moon{display:block}
:root[data-theme=dark] .themeic .sun{display:none}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]) .themeic .moon{display:block}
:root:not([data-theme=light]) .themeic .sun{display:none}}
/* the side drawer and the search sheet, used on the pages about one game */
/* It drops straight down from the three-line button with a gap at the side and
   rounded corners, rather than sliding in from the edge of the screen as a
   full-height drawer (17 Nov 2026, owner's call, after demand.gg). top clears the
   bar - about 65px, 57px on a phone - and max-height keeps a long list scrolling
   inside the card instead of running off the bottom of the window. */
/* top/right here are only a sane starting point: script places the card under the
   three-line button before it is ever shown, because the bar's band is capped and
   centred and the button is not at the window edge on a wide screen. */
.drawer{position:fixed;top:72px;right:16px;width:262px;max-width:calc(100vw - 32px);
z-index:30;background:var(--solid);border:1px solid var(--line);border-radius:16px;
box-shadow:var(--sh);padding:8px;max-height:calc(100vh - 88px);overflow-y:auto;
animation:dropin .15s ease both}
.drawer[hidden]{display:none}
/* The panel's top section: the controls that are in the header on a wide screen. */
/* The panel never offers search: the bar across the top carries a magnifier from
   900px up, and the bar across the bottom of a phone carries one below that. Two
   buttons for one sheet in one menu is the thing this header keeps avoiding. */
.dtop .drow[data-search]{display:none}
/* Same for the event calendar and Plan a session, which are in that bottom bar -
   but only on a phone, since the bottom bar is not there on a computer. */
@media(max-width:899px){.drawer nav a[data-sec=events],
.drawer nav a[data-sec=plan]{display:none}}
/* The sections leave the panel only once the bar is wide enough to show all of
   them, which is 1200px - not 900, where only the first three fit. */
@media(min-width:1200px){.drawer nav a[data-sec]{display:none}}
.dtop{display:flex;flex-direction:column;gap:2px;margin-bottom:10px;padding-bottom:10px;
border-bottom:1px solid var(--line)}
/* The theme button, under the sections. Its own block so the rule above it stays
   whether or not anything else is in there. */
.dbot{margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}
.dbot .drow{text-decoration:none}
.drow{display:flex;align-items:center;gap:11px;width:100%;padding:11px 13px;border:0;
border-radius:11px;background:none;color:var(--ink);font:inherit;font-weight:600;
text-align:left;cursor:pointer}
.drow:hover,.drow:focus-visible{background:var(--shade)}
.drow svg{width:18px;height:18px;flex:none;fill:currentColor}
.drawer nav{display:flex;flex-direction:column;gap:2px}
.drawer a{padding:11px 13px;border-radius:11px;text-decoration:none;color:var(--ink);font-weight:600}
.drawer a:hover,.drawer a:focus-visible{background:var(--shade)}
.scrim{position:fixed;inset:0;z-index:25}
.scrim[hidden]{display:none}
@keyframes dropin{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}
.sheet{position:fixed;inset:0;z-index:30;display:grid;place-items:start center;
padding:76px 16px 16px;background:rgba(0,0,0,.45)}
.sheet[hidden]{display:none}
/* The device sections on /install, collapsed so nobody scrolls past two
   platforms to reach their own. Built like .gdesc: the <h2> stays inside the
   <summary> so the page keeps its headings for search engines and for
   heading-by-heading navigation, and the arrow is two borders rather than a
   picture. */
.howto{background:var(--card);border:1px solid var(--line);border-radius:14px;
margin:0 0 12px}
.howto>summary{cursor:pointer;list-style:none;display:flex;align-items:center;
gap:10px;padding:14px 16px}
.howto>summary::-webkit-details-marker{display:none}
.howto>summary h2{margin:0;font-size:1.05rem}
.howto>summary:hover h2,.howto[open]>summary h2{color:var(--acc)}
.howto>summary::after{content:"";margin-left:auto;flex:none;width:9px;height:9px;
border-right:2.5px solid var(--acc);border-bottom:2.5px solid var(--acc);
transform:translateY(-3px) rotate(45deg);transition:transform .2s}
.howto[open]>summary::after{transform:translateY(2px) rotate(225deg)}
.howto-in{padding:0 16px 14px}
.howto-in>:first-child{margin-top:0}
/* "I have already added it". A <details> rather than a button because it needs no
   JavaScript and so cannot be thrown away when the notifications page redraws. */
.already{margin:12px 0 0;font-size:.9rem}
.already>summary{cursor:pointer;color:var(--acc);font-weight:600;
list-style:none;padding:4px 0}
.already>summary::-webkit-details-marker{display:none}
.already p{margin:8px 0 0;color:var(--mut)}
/* Asked for: a phone or tablet is told how to add it by hand instead. The button
   only ever appeared where the browser had actually offered, so it was never shown
   on an iPhone anyway - this takes it off Android and small tablets. Two parts to
   the selector because .remind is a single class written further down. */
@media(max-width:899px){.doc [data-install]{display:none}}
.phonetip{display:none;margin:9px 0 0;font-size:.82rem;line-height:1.45;
color:var(--mut)}
@media(max-width:899px){.phonetip{display:block}}
.ipop{position:fixed;inset:0;z-index:31;display:grid;place-items:center;padding:16px;
background:rgba(0,0,0,.45)}
.ipop[hidden]{display:none}
/* --solid, not --card: --card is translucent for the glass look, which is right for
   a card sitting on the page and wrong for a popup, where the words behind it showed
   straight through the instructions. */
.ipop .ibox{position:relative;background:var(--solid);border:1px solid var(--line);
border-radius:18px;padding:22px 20px 20px;max-width:min(430px,100%);box-shadow:var(--sh)}
.ipop h2{margin:0 36px 8px 0;font-size:1.15rem}
.ipop ol{margin:12px 0 20px;padding-left:22px}
.ipop ol li{margin:7px 0}
.ipop .ix{position:absolute;top:10px;right:10px;width:34px;height:34px;display:grid;
place-items:center;border-radius:10px;border:1px solid var(--line);background:var(--bg);
color:var(--ink);font-size:1.1rem;line-height:1;cursor:pointer}
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
/* The chooser reads as one question with two answers, instead of a label on one
   row and two buttons on another. */
.planpick{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0 2px}
.planpick .days{margin:0}
#session .cd{font-size:1.5rem}
#session #plantxt{margin:6px 0 2px}
/* The bell is the last thing in this card now, so its margin belongs above it.
   .bellb carries a bottom margin for the bells that sit UNDER a heading, which
   left this one jammed against the sentence and hanging off the bottom. */
#session .bellb{margin:14px 0 2px}
.days{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.days button{font-size:.95rem;padding:6px 14px;min-height:44px;border-radius:999px;border:1px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
.days button[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:var(--btnink);font-weight:700}
/* Quiet/Busy in Plan my session and the days of the week under the hourly graph are
   the same control, so one rule covers both. The rim follows the border and stops
   there, the way the chips and the category pills do, rather than the tile glow
   that sits behind a whole card. The chosen one keeps its filled accent and only
   gains the glow, so hovering cannot be mistaken for choosing. */
.days button:hover,.days button:focus-visible{border-color:var(--acc);box-shadow:var(--rim)}
.days button:not([aria-pressed=true]):hover,
.days button:not([aria-pressed=true]):focus-visible{color:var(--ink);font-weight:700}
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
/* Every square answers when it is pointed at or pressed. The ring is the ACCENT
   and sits outside the square, where .now's is white and inside it - drawn the
   same way the two were indistinguishable on the grid, and "right now" and "the
   one you picked" are different answers to different questions. It is a ring and
   never a fill, so it cannot be mistaken for a sixth band of the traffic light. */
.hm .c[data-d]{cursor:pointer}
/* padding:0 is NOT spare. `.sel` is also the class on every <select> on the site
   (.sel{padding:10px 13px}, further down and one class), and a one-class rule that
   declares something this one does not simply applies - so the square you tapped
   picked up a dropdown's padding and went from 11x17 to 28x22 on a phone. It was
   hidden for as long as the tapped square was scaled up anyway. */
.hm .c.sel{outline:2.5px solid var(--acc);outline-offset:2px;border-radius:5px;padding:0}
.legend{display:flex;align-items:center;gap:4px;font-size:.85rem;color:var(--mut);margin-top:10px;flex-wrap:wrap}
.legend i{width:26px;height:12px;border-radius:3px;display:inline-block}
.spark{width:100%;height:190px;display:block}
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
/* The three at the top of a game page are one set of buttons and are sized as one.
   Two classes, so this beats the single-class rules for each of them wherever they
   fall in the sheet - including the phone block, which shrinks .btn and .fav by
   different amounts and so would pull them apart again. The transparent border on
   .btn is not spare: a 1px border adds 2px of height, so without it the filled
   button would sit 2px shorter than the two outlined ones. */
.actions .btn,.actions .fav,.actions .bellb{display:inline-flex;align-items:center;
justify-content:center;gap:8px;margin:0;padding:10px 18px;border-radius:13px;
border:1px solid transparent;font-size:.95rem;font-weight:700;line-height:1.3;
min-height:46px}
.actions .fav,.actions .bellb{border-color:var(--line);background:var(--card);color:var(--ink)}
.actions .bellb svg{width:16px;height:16px}
.gcat{margin:8px 0 0;font-size:.92rem}
.gcat a{color:var(--acc);font-weight:600;text-decoration:underline;text-underline-offset:3px}
.actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:10px}
/* The tabs across a game's pages. Written as a BLOCK with nowrap, never a nowrap
   flex row: a nowrap flex container reports the full width of its items as its own
   max-content width and drags its parent out with it, even while it scrolls - which
   is what the category pills did to the homepage on a phone. The rule sits under the
   whole row and the chosen tab covers its own inch of it, so the two must stay on
   the same pixel: hence the -1px bottom margin against the row's 1px border. */
.gtabs{display:block;white-space:nowrap;overflow-x:auto;overflow-y:hidden;
margin:14px 0 0;border-bottom:1px solid var(--line);scrollbar-width:none}
.gtabs::-webkit-scrollbar{display:none}
.gtab{position:relative;display:inline-block;margin:0 20px -1px 0;padding:9px 1px 12px;
color:var(--mut);text-decoration:none;font-weight:700;font-size:.97rem}
.gtab:hover,.gtab:focus-visible{color:var(--ink)}
.gtab.on{color:var(--ink)}
/* hsl off --glowh rather than --acc, because the bar wants to be LIGHTER than the
   accent in both themes - light mode's accent is a deep purple that reads as a
   shadow here, not a glow. --glowh is set in the light palette and never
   overridden, so it is the one hue both themes share. */
/* The glow is thrown UPWARDS, and that is not a style choice - it is the only
   direction anybody can see it. .gtabs scrolls sideways, and a box that scrolls on
   one axis clips the other whatever you write, so every pixel of halo below the
   line is cut off; the game's heading panel sits under the row as well, above it
   in the stacking order, so it would cover that half even unclipped. Measured on a
   real page before this: the column of pixels under the line went straight from
   the bar to the flat page colour, which is a glow with half of itself missing.
   Offsetting it up puts all of it where it shows. If the row is ever made to not
   scroll, this can go back to an even halo. */
.gtab.on::after{content:'';position:absolute;left:0;right:0;bottom:-1px;height:3px;
border-radius:3px;background:hsl(var(--glowh) 92% 72%);
box-shadow:0 -2px 7px hsl(var(--glowh) 92% 72%/.95),
0 -5px 18px 3px hsl(var(--glowh) 92% 72%/.6)}
.fav{font-weight:700;padding:10px 17px;border-radius:13px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;text-decoration:none}
.fav:hover,.fav:focus-visible{border-color:var(--acc);box-shadow:var(--rim)}
.btn:hover,.btn:focus-visible{box-shadow:var(--sh),var(--rim)}
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
/* Kept: the notification panel sits in this same spot under the countdown, where
   the calendar day-picker used to be. */
.rem{border-top:1px solid var(--line);margin-top:18px;padding-top:14px}
.rem>p:first-child{margin:0 0 8px}
.rem .days{margin:0}
.remind{display:inline-flex;align-items:center;gap:6px;margin-top:8px;padding:8px 14px;
font-size:.85rem;font-weight:600;border-radius:999px;border:1px solid var(--line);
background:var(--card);color:var(--mut);cursor:pointer;text-decoration:none;min-height:40px}
.remind:hover{border-color:var(--acc);color:var(--ink)}
.evt li{border-left:3px solid var(--line);padding:2px 0 2px 14px;margin:16px 0}
.evt li.soon{border-left-color:var(--acc2);background:var(--soft);border-radius:0 10px 10px 0;padding:8px 12px 8px 14px}
.evt li.live{border-left-color:var(--up)}
.evt b{display:block}
.evt .d{font-size:.85rem;color:var(--mut)}
.evt .esub{display:block}
.evt .nb{white-space:nowrap}
.evt p{margin:.3em 0;font-size:.95rem;white-space:pre-line}
.habits{margin:10px 0 0;padding-left:20px}
.habits li{margin:.4em 0}
/* The changelog list on /updates/<game>. Every selector is written under .chg
   so it is two classes deep: a bare .cnum or .ctitle would be one class and, in
   this stylesheet, a later one-class rule elsewhere would quietly beat it. */
.chg{list-style:none;padding:0;margin:10px 0}
.chg li{border-top:1px solid var(--line)}
.chg li:last-child{border-bottom:1px solid var(--line)}
.chg summary,.chg .cflat{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;
  padding:9px 2px}
.chg summary{cursor:pointer;color:inherit;font-weight:400;margin:0}
.chg summary:hover{background:var(--soft)}
.chg summary:hover .ctitle,.chg details[open] .ctitle{color:var(--acc)}
/* The little triangle, drawn as two rotated borders the way .gdesc and .howto
   draw theirs - no character and no escape, because this CSS lives inside an
   ordinary Python string and a backslash would be eaten before the browser saw
   it. Giving a <summary> a display of flex REMOVES the browser's own marker, so
   without this the rows look like plain text: the intro promised a triangle and
   nothing on the page was clickable-looking. Caught in a screenshot, not in the
   markup. It leads rather than trails, so on a phone, where the row wraps, it
   stays next to the number instead of stranding itself on a line of its own. */
.chg summary::-webkit-details-marker{display:none}
.chg summary{list-style:none}
.chg summary::before{content:"";flex:none;align-self:center;width:7px;height:7px;
  border-right:2px solid var(--acc);border-bottom:2px solid var(--acc);
  transform:translateX(-1px) rotate(-45deg);transition:transform .2s}
.chg details[open]>summary::before{transform:translateY(-2px) rotate(45deg)}
.chg .cflat{padding-left:19px}
.chg .cnum{color:var(--mut);font-size:.85rem;min-width:2.4em;
  font-variant-numeric:tabular-nums}
.chg .ctitle{flex:1 1 200px;min-width:0;font-weight:600;overflow-wrap:anywhere}
.chg .cdate{color:var(--mut);font-size:.85rem}
.chg p{margin:0 0 10px;padding:0 2px 0 calc(2.4em + 27px);font-size:.95rem;
  color:var(--mut);white-space:pre-line;overflow-wrap:anywhere}
.chg .csub{font-weight:600;color:var(--ink)}
@media(max-width:620px){.chg p{padding-left:2px}}
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
/* Written in the graph itself, so it needs no room under it. */
.gsc{fill:var(--mut);font-size:15px;font-weight:700;opacity:.75}
/* One row per fact: what it is on the left, the number on the right, a hairline
   between. It used to be a grid of auto-fitting columns, each holding a label, a
   number and a note stacked three deep - so at two or three columns wide nothing
   lined up with anything and you could not tell which number belonged to which
   label. A list reads down; that is the whole fix. */
.facts{display:block;margin:12px 0 0}
.facts div{display:flex;justify-content:space-between;align-items:baseline;gap:14px;
padding:9px 0;border-bottom:1px solid var(--line);min-width:0}
.facts div:last-child{border-bottom:0;padding-bottom:0}
.facts dt{font-size:.95rem;color:var(--ink);font-weight:600;min-width:0}
.facts dt span{display:block;font-size:.8rem;color:var(--mut);font-weight:400;margin-top:1px}
.facts dd{margin:0;font-weight:800;font-size:1.12rem;white-space:nowrap;text-align:right}
/* Below 900px the stats card is full width and about a screen tall, so only its
   first three rows show and the rest open behind "More stats". GAME_JS adds .fold,
   so with no script every row simply shows. The base display:none and the media
   query sit together because .fold+.morestats must beat .morestats on weight,
   not on order. From 900px up the card fills its column beside the stack, so
   nothing folds. */
.morestats{display:none}
@media(max-width:899.98px){
.facts.fold:not(.open)>div.x{display:none}
.facts.fold:not(.open)>div:nth-child(3){border-bottom:0;padding-bottom:0}
.facts.fold+.morestats{display:inline-block;margin-top:12px;padding:8px 16px;font:inherit;
font-size:.92rem;font-weight:700;color:var(--acc);background:none;border:1px solid var(--line);
border-radius:999px;cursor:pointer}
}
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
/* The bar is shorter here - about 57px - so the panel starts higher, and its gap
   follows the bar's own 14px padding rather than the 16px a computer uses. */
.drawer{top:63px;right:14px;max-width:calc(100vw - 28px);max-height:calc(100vh - 79px)}
.iconb{width:38px;height:38px}
.hrow{gap:9px}
.logo{font-size:1.2rem;margin-right:0}
.logo .mark{width:29px;height:29px}
.gpick>button{width:130px;max-width:130px;padding:7px 11px}
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
.bento>*,.lstack>.card{scroll-margin-top:68px}
/* all seven days fit across, so the chart below does not jump when you change day */
.days{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px;margin:10px 0}
.days button{padding:6px 0;font-size:.82rem}
/* ...but Plan my session has two buttons, not seven, and the seven-column grid
   left each of them about 48px wide on a phone - a target smaller than a
   fingertip, carrying a word that did not fit in it. */
/* width:100% is not spare. #planbtns is a grid INSIDE a flex row, and a flex item
   is sized to its contents unless told otherwise - so 1fr resolved to the width of
   the word in the button and the two stayed 43px wide, exactly as before. */
#planbtns{grid-template-columns:1fr 1fr;gap:8px;width:100%;flex:1 1 100%}
#planbtns button{padding:11px 0;font-size:1rem;min-height:48px}
/* the week grid: 24 columns on a phone, so the squares have to be small */
.hm{grid-template-columns:30px repeat(24,minmax(0,1fr));gap:1.5px;font-size:.68rem}
.hm .c{height:17px;border-radius:3px;transition:transform .12s}
/* The square that was tapped is RINGED, not grown (19 Nov 2026, owner's call). It
   used to scale to 2.2 so there was something finger-sized to tap again, and the
   owner would rather the grid held still: a square that jumps out from under the
   finger that pressed it reads as the page moving about. z-index keeps the ring
   above its neighbours, since the squares are only 1.5px apart. Every other square
   stays live - a chart that stops answering because one square is open would be a
   fault, not a feature. */
.hm .c.sel{position:relative;z-index:3;border-radius:4px;
outline:2px solid var(--acc);outline-offset:1px}
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
.gtab{margin-right:16px;font-size:.92rem}
.btn{padding:10px 16px}
.fav{padding:9px 13px;font-size:.92rem;border-radius:11px}
.stats{gap:9px}
.stats b{font-size:1.3rem}
.foot nav{gap:4px 14px}
/* the trail wraps onto three lines at this width, and Back already covers leaving */
.crumbs{display:none}
}

/* A 320px phone cannot hold the bar at the phone sizes above, and the thing that
   fell off the end was the three-line button - measured 11px of it past the right
   edge of the window on the live site. 14+122(logo)+9+130(picker)+9+38(button)+14
   comes to 336 inside 320. The picker is left alone on purpose: it was fixed at one
   width on 20 Nov 2026 so "Pick a game" never gets an ellipsis of its own, and the
   brand is the one thing here that can give up a few pixels without losing anything
   it has to say. Written AFTER the 620px block, because both are one class and a
   media query adds no specificity - source order is all that decides it, the trap
   this stylesheet keeps setting.
   320px is the narrowest screen the site is measured at, so this is the floor
   rather than a width nobody has. */
@media(max-width:360px){
.hdr .in{padding:8px 10px}
.hrow{gap:7px}
.logo{font-size:1.05rem;gap:7px}
.logo .mark{width:26px;height:26px}
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
    """A full web address for a page, e.g. "/game/doors" -> "https://.../game/doors".

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
    # Every block needs "@context", including a lone one. Without it this is just a
    # JSON object that happens to use schema.org words, and Google ignores the whole
    # script - it parses as valid JSON, so nothing anywhere complains. A single block
    # used to be written out bare, which silently threw away the structured data on
    # 147 pages, the homepage among them. That is the page carrying the WebSite block
    # Google reads a site's NAME from, which is why results said "playtimestats.com"
    # where other sites show their name. check_seo.py now fails a page missing it.
    for b in items:
        b.pop("@context", None)
    data = ({"@context": "https://schema.org", **items[0]} if len(items) == 1
            else {"@context": "https://schema.org", "@graph": items})
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


# ----------------------------------------------------------------- app icons
# The same logo drawn as PNG, for the three jobs an SVG cannot do: the icon a phone
# shows when the site is added to its home screen, the one Android puts on a splash
# screen, and the one that rides along with a notification.
#
# Drawn here with zlib rather than by installing Pillow, for the same reason
# roblox_api.py reads PNGs by hand: the build server installs nothing. It is also
# why the icons are generated instead of being checked in as binaries - the logo is
# defined once, in logo_svg(), and these cannot drift away from it.
#
# A notification icon especially has to be a PNG. Android draws it at about 24px and
# ignores an SVG entirely, so without this a notification would carry a blank square.

def _png(width, height, pixels):
    """Writes a PNG. pixels is RGBA bytes, width*height*4 of them.

    Colour type 6 is RGBA at 8 bits. Each row is preceded by a zero byte, which is
    PNG's way of saying "this row is stored as-is" rather than as a difference from
    the row above; the pictures are small and simple enough that filtering them
    properly would save little and is one more thing to get wrong.
    """
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    rows = b"".join(b"\x00" + bytes(pixels[y * width * 4:(y + 1) * width * 4])
                    for y in range(height))
    return (b"\x89PNG\r\n\x1a\x0a" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows, 9)) +
            chunk(b"IEND", b""))


# The ring is an arc, not a full circle: logo_svg draws it with a dash of 52 over a
# circumference of about 69, starting at the top, which comes to roughly 271 degrees
# and is what makes it read as a timer running down.
_ARC = 360.0 * 52.0 / (2 * math.pi * 11.0)
_TRI = ((13.4, 11.2), (21.6, 16.0), (13.4, 20.8))


def _inside_triangle(x, y):
    (ax, ay), (bx, by), (cx, cy) = _TRI
    d1 = (x - bx) * (ay - by) - (ax - bx) * (y - by)
    d2 = (x - cx) * (by - cy) - (bx - cx) * (y - cy)
    d3 = (x - ax) * (cy - ay) - (cx - ax) * (y - ay)
    return (d1 <= 0 and d2 <= 0 and d3 <= 0) or (d1 >= 0 and d2 >= 0 and d3 >= 0)


def app_icon(size, supersample=3):
    """The logo as a square PNG of the given size.

    Full-bleed rather than a circle on transparency: both iOS and Android mask the
    icon to their own shape, and a transparent corner under that mask shows up as a
    grey notch. Edges are smoothed by sampling each pixel several times across,
    which is all the anti-aliasing a shape this simple needs.
    """
    scale = 32.0 / size
    step = 1.0 / (supersample + 1)
    offsets = [(i + 1) * step for i in range(supersample)]
    pixels = bytearray(size * size * 4)
    at = 0
    for py in range(size):
        for px in range(size):
            r = g = b = 0.0
            for oy in offsets:
                v = (py + oy) * scale
                dy = v - 16.0
                for ox in offsets:
                    u = (px + ox) * scale
                    dx = u - 16.0
                    # The background gradient, corner to corner, as in logo_svg.
                    t = (u + v) / 64.0
                    cr = 216 + (168 - 216) * t
                    cg = 180 + (85 - 180) * t
                    cb = 254 + (247 - 254) * t
                    if _inside_triangle(u, v):
                        cr = cg = 10.0
                        cb = 15.0
                    else:
                        dist = math.hypot(dx, dy)
                        if abs(dist - 11.0) <= 1.0:
                            ang = (math.degrees(math.atan2(dy, dx)) + 90.0) % 360.0
                            if ang <= _ARC:
                                # #0A0A0F at 45%, over whatever is behind it.
                                cr += (10 - cr) * 0.45
                                cg += (10 - cg) * 0.45
                                cb += (15 - cb) * 0.45
                    r += cr
                    g += cg
                    b += cb
            n = float(len(offsets) ** 2)
            pixels[at] = int(r / n + 0.5)
            pixels[at + 1] = int(g / n + 0.5)
            pixels[at + 2] = int(b / n + 0.5)
            pixels[at + 3] = 255
            at += 4
    return _png(size, size, pixels)


# ------------------------------------------------------- the home-screen manifest
# What lets a phone add the site to its home screen and open it without browser
# furniture. On an iPhone or iPad that is not a nicety: Apple only allows web
# notifications for a site that has been added to the home screen, so without this
# file notifications could never work on an Apple device at all.
def manifest_json():
    return json.dumps({
        # What the installed app is called: its title bar, the Windows taskbar and
        # Start menu, and the box a browser shows when it offers to install. It is
        # NOT a search engine's business - nothing crawls a manifest - so this is
        # free to say whatever reads best, while the page titles keep "player count"
        # where Google can see it. It said "when Roblox games are busiest" until
        # 18 Nov 2026, which named only half of what the site is for: most people
        # come here for the quiet hours. This matches the homepage's own heading.
        "name": SITE + " - the best times to play Roblox games",
        "short_name": SITE,
        "description": "See when popular Roblox games are busiest and quietest.",
        "start_url": "/?from=app",
        "scope": "/",
        "display": "standalone",
        # Matches the dark palette, because that is what the splash screen uses and a
        # white flash before a near-black page is the one thing people notice.
        "background_color": "#0A0A0F",
        "theme_color": "#0A0A0F",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"}
        ]
    }, indent=1)


# ---------------------------------------------------------------- service worker
# The small script a browser keeps even when the site is closed. It is the only way
# a notification can be shown at all: the page itself is long gone by the time one
# arrives.
#
# Deliberately NOT a cache or an offline mode. A service worker that serves pages
# from its own copy would hand people yesterday's player counts, which on this site
# is the one thing that must never happen. This one only listens for notifications.
PUSH_SW = """/* PlayTime notifications. Nothing is cached: a cached page here would
   mean stale player counts, which is worse than no page. */
self.addEventListener('install',function(e){self.skipWaiting()});
self.addEventListener('activate',function(e){e.waitUntil(self.clients.claim())});
self.addEventListener('push',function(e){
var d={};try{d=e.data.json()}catch(err){}
e.waitUntil(self.registration.showNotification(d.title||'PlayTime',{
body:d.body||'',icon:'/icon-192.png',badge:'/icon-192.png',
tag:d.tag||'playtime',data:{url:d.url||'/'}}))});
/* Tapping it should land on the game's page, and should re-use a tab that is
   already open on it rather than piling up windows. */
self.addEventListener('notificationclick',function(e){
e.notification.close();
var want=(e.notification.data&&e.notification.data.url)||'/';
e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true})
.then(function(list){
for(var i=0;i<list.length;i++){
if(list[i].url.indexOf(want)>-1&&'focus' in list[i])return list[i].focus()}
if(self.clients.openWindow)return self.clients.openWindow(want)}))});
"""

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
# An arrow coming down onto a tray: the one glyph every app store and download
# button has settled on, so it needs no label to be understood.
ICON_BELL = ('<svg viewBox="0 0 16 16" aria-hidden="true">'
             '<path d="M8 1.3a4.2 4.2 0 0 0-4.2 4.2v2.3L2.4 10a1 1 0 0 0 .85 1.5h9.5A1 1 0 0 0 '
             '13.6 10l-1.4-2.2V5.5A4.2 4.2 0 0 0 8 1.3z"/>'
             '<path d="M6.2 12.6a1.9 1.9 0 0 0 3.6 0z"/></svg>')
ICON_INSTALL = ('<svg viewBox="0 0 16 16" aria-hidden="true">'
                '<path d="M7 1.4h2v5.2l1.9-1.9 1.4 1.4L8 10.4 3.7 6.1l1.4-1.4L7 6.6z"/>'
                '<path d="M2.6 12h10.8a1 1 0 0 1 0 2H2.6a1 1 0 0 1 0-2z"/></svg>')
ICON_STAR = ('<svg viewBox="0 0 16 16" aria-hidden="true">'
             '<path d="M8 1.6l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.4l-3.8 2 .7-4.3-3.1-3 '
             '4.3-.6z" fill="none" stroke="currentColor" stroke-width="1.6" '
             'stroke-linejoin="round"/></svg>')
ICON_CAL = ('<svg viewBox="0 0 16 16" aria-hidden="true">'
            '<rect x="1.3" y="2.8" width="13.4" height="11.9" rx="2" fill="none" '
            'stroke="currentColor" stroke-width="1.6"/>'
            '<path d="M1.3 6.4h13.4M5 1.3v2.8M11 1.3v2.8" fill="none" '
            'stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>')
ICON_CLOCK = ('<svg viewBox="0 0 16 16" aria-hidden="true">'
              '<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.6"/>'
              '<path d="M8 4.3v4l2.6 1.6" fill="none" stroke="currentColor" '
              'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')
ICON_LIST = ('<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="2" width="14" height="3" rx="1.4"/>'
             '<rect x="1" y="6.5" width="14" height="3" rx="1.4"/><rect x="1" y="11" width="14" height="3" rx="1.4"/></svg>')

# Runs before anything is drawn, so the page never flashes the wrong theme or view.
BOOT = ("<script>try{var d=document.documentElement,t=localStorage.getItem('pt_theme');"
        "if(t)d.setAttribute('data-theme',t);"
        "d.setAttribute('data-view',localStorage.getItem('pt_view')==='list'?'list':'grid')}"
        "catch(e){document.documentElement.setAttribute('data-view','grid')}</script>")

# Counts one page view. No cookies, no login, nothing about the visitor is stored.
#
# A browser being driven by a test script is not a visitor, and counting one makes
# the whole dashboard say nothing. On 22 Nov 2026 the figures were mostly us: the
# site recorded 156 views across 114 DIFFERENT pages in a day, which is a sweep
# rather than a person, and hundreds of one-second loads had dragged the homepage's
# average reading time down to 19 seconds while the pages real people had read sat
# at 35-70. `navigator.webdriver` is the browser's own flag, set by Puppeteer,
# Selenium and Playwright and false in an ordinary browser, so one check keeps our
# sweeps out of the numbers. It is read and thrown away: nothing further is
# collected about anybody, and a visitor who is not a robot is unaffected.
#
# It is not proof against a robot that wants to hide - the flag can be switched off,
# and a crawler that runs no JavaScript was never counted in the first place. It is
# aimed at our own testing, which is what the numbers were actually full of.
HIT = ('<script>if(!navigator.webdriver){'
       'try{fetch("/api/hit",{method:"POST",headers:{"content-type":"text/plain"},'
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
       '}</script>')

# The sections along the top of every page: (key, label, address)
TABS = [("home", "All games", "/"),
        ("popular", "Most popular", "/popular"),
        ("trending", "Trending", "/trending"),
        ("growing", "Growing", "/growing"),
        ("shrinking", "Shrinking", "/shrinking"),
        ("events", "Event calendar", "/events"),
        ("compare", "Compare games", "/compare"),
        ("plan", "Plan a session", "/plan")]

# TABS is still the whole section list - sitemap.xml is built from it, and a page
# left out here is a page we never ask Google to look at. This is what the panel
# behind the three-line button leaves out (17 Nov 2026, owner's call). Growing and
# Shrinking were taken out with these two and put back the same day, so do not
# assume the grouping means anything: it is the two the owner did not want listed.
# Both of these are still reachable from the footer, which is what stops them
# becoming pages we ask Google to crawl and then link from nowhere.
PANEL_HIDE = {"popular", "trending"}

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
      canon     this page's one true address, e.g. "/game/doors". Addresses have no
                ".html" on the end: Cloudflare serves the file "game/doors.html" at
                "/game/doors" and bounces "/game/doors.html" to it with a 307. The
                page a visitor actually lands on is therefore the one without it, so
                that is the one the canonical tag, the breadcrumbs, the links and the
                sitemap all have to name. They used to say ".html", which pointed
                every canonical tag at an address that redirected somewhere else -
                conflicting advice to Google on all 304 pages. The file written to
                disk still keeps its ".html"; only the address drops it.
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
    drawer = "".join(f'<a href="{u}" data-sec="{k}"'
                     f'{" aria-current=page" if k == nav else ""}>{html.escape(t)}</a>'
                     for k, t, u in TABS if k not in PANEL_HIDE)
    # The same shape at every width: logo, name, game picker, then the buttons on
    # the right. The account is the first of those buttons, next to the search, at
    # every width - it is about the person rather than about the page, and while it
    # sat inside the panel it went unfound. It is written EMPTY here: ptPaint() in
    # FAVJS fills it once /api/me has answered, because only the worker knows
    # whether anybody is signed in and a built page is the same file for everyone.
    # Light/dark stays in the panel. Search is in both: a wide screen has room, so
    # the magnifier sits in the bar from 900px up (.deskonly) and the panel hides
    # its own search row to match. Nothing in the scripts had to change for that
    # second copy, because they bind every [data-search] and [data-themebtn]
    # rather than an id - keep it that way.
    # The account used to be here and is now the first thing in the panel: the owner
    # wanted the bar down to icons so the notification bell could have a place in it.
    # Both are written EMPTY - ptPaint() fills them once /api/me has answered, because
    # a built page is the same file for everyone and only the worker knows who is
    # signed in. :empty collapses whichever of them has nothing to say.
    # The name and the bell are BOTH computer-only, and the stylesheet is what does
    # it: a phone's bar has room for the logo, the game picker and two buttons, and
    # a name in there pushed the picker down to a stub. Everything they lead to is
    # still reachable on a phone - the account and a Notifications row both sit in
    # the panel behind the three lines, which is where a phone was always going.
    buttons = (f'<div class="acctbar"></div>'
               f'<div class="nots"></div>'
               f'<button class="iconb deskonly" data-search type="button" '
               f'aria-label="Search for a game">{ICON_SEARCH}</button>'
               f'<button class="iconb" id="menubtn" type="button" aria-expanded="false" '
               f'aria-controls="drawer" aria-label="Menu">{ICON_MENU}</button>')
    # These two are position:fixed and must be written OUTSIDE <header>. The header
    # has backdrop-filter, and that makes it the containing block for any fixed
    # descendant: inside it, the side menu was 88px tall instead of the height of
    # the screen, and the search panel was pinned to the header's own box rather
    # than the page. They sit after </header> as siblings instead.
    # The panel, in order: who you are and the controls that are in the bar on a
    # computer, then Get the app, then the sections, then the theme at the very
    # bottom. On a computer the first three collapse, so Get the app is the first
    # thing in the panel and Light mode the last - which is the order asked for at
    # both widths, out of one piece of markup rather than two.
    extras = (f'<div class="drawer" id="drawer" hidden>'
              f'<div class="dtop">'
              f'<div class="acct"></div>'
              # Filled by ptPaint only for somebody signed in, and hidden from 900px
              # up where the bell is in the bar - the same trick the search row uses,
              # so the one control is never offered twice on the same screen.
              f'<div class="notsrow"></div>'
              f'<button class="drow" data-search type="button">{ICON_SEARCH}'
              f'<span>Search for a game</span></button>'
              # Busy, Quiet and Popular are NOT here (19 Nov 2026, owner's call:
              # "remove them from the side menu since it's on the home page").
              # They only ever showed below 900px - from 900 up the bar carries
              # them - and below 900px they are three buttons under the homepage
              # search box, which is the page everybody starts on. Nothing is cut
              # off: Popular is in the footer, and busy and quiet are the homepage
              # asked a question rather than pages of their own, so they are also
              # the chips the homepage already offers.
              # The footer has linked /install since it was built, but the footer is
              # at the bottom of a long page and this menu is how people actually get
              # about: without a row here the page could only be reached by typing it.
              # It sits with the controls rather than among the sections because it is
              # a thing to do, not a part of the site to go and read.
              f'<a class="drow" href="/install">{ICON_INSTALL}'
              f'<span>Get the app</span></a>'
              f'</div>'
              f'<nav aria-label="Sections">{drawer}'
              f'<a href="/busiest-hours">When is Roblox busiest?</a>'
              f'<a href="/about">About</a></nav>'
              # Last of all, under its own rule: it is the one row nobody comes to the
              # menu for, and it was sitting above every section.
              f'<div class="dbot">'
              f'<button class="drow themeic" data-themebtn type="button">{SUN}{MOON}'
              f'<span class="tlab">Dark mode</span></button>'
              f'</div></div>'
              f'<div class="amenu" id="amenu" hidden></div>'
              f'<div class="sheet" id="sheet" hidden><div class="sheetbox">'
              f'<input id="q" type="search" placeholder="Search for a game" aria-label="Search for a game">'
              f'<div id="qout" class="qout"></div></div></div>'
              # Outside <header>, like the drawer and the sheet: .hdr carries
              # backdrop-filter, which makes it the containing block for anything
              # fixed inside it, and this is fixed to the window.
              f'<nav class="tabbar" aria-label="Quick links">'
              f'<button class="tbb" data-search type="button">{ICON_SEARCH}'
              f'<span>Search</span></button>'
              f'<a class="tbb" href="/#favs" data-tb="favs">{ICON_STAR}'
              f'<span>Saved</span></a>'
              f'<a class="tbb" href="/events" data-tb="events">{ICON_CAL}'
              f'<span>Events</span></a>'
              f'<a class="tbb" href="/plan" data-tb="plan">{ICON_CLOCK}'
              f'<span>Plan</span></a></nav>')
    # The bar is the same shape on every page of the site and at every width -
    # see the note by `.hdr .in` in the stylesheet for why it stopped following the
    # column of words underneath it.
    crumb_html, crumb_data = crumbs(trail or [])
    # Back and the trail are both "where am I and how do I leave", so they share one
    # line instead of taking a line each. The trail is the one that goes on a phone:
    # it wraps onto three lines there, and the copy Google reads is the structured
    # data below, not this, so hiding it costs nothing.
    topnav = ((f'<div class="topnav">{back_link(*back) if back else ""}{crumb_html}</div>')
              if (back or crumb_html) else "")
    blocks = jsonld(*([crumb_data] + list(schema or [])))
    # Where the page lives. This is the address a visitor really ends up on (no
    # ".html"), which is the only one worth telling Google about.
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
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{html.escape(SITE)}">
<link rel="preconnect" href="https://tr.rbxcdn.com" crossorigin>
{BOOT}<style>{CSS}</style>{blocks}<script>{FAVJS}</script>{ADS}</head><body>
{banner_html(banner)}<header class="hdr"><div class="in"><div class="hrow">
<a class="logo" href="/">{logo_svg()}<span class="wordmark">Play<b>Time</b></span></a>
<div class="gpick" id="gpick"></div>
<nav class="hnav" aria-label="Find games"><a href="/?for=busy" data-hn="busy">Busy now</a>
<a href="/?for=quiet" data-hn="quiet">Quiet now</a>
<a href="/popular" data-hn="popular">Popular</a>
<a class="more" href="/growing" data-hn="growing">Growing</a>
<a class="more" href="/shrinking" data-hn="shrinking">Shrinking</a>
<a class="more" href="/events" data-hn="events">Events</a>
<a class="more" href="/compare" data-hn="compare">Compare</a>
<a class="more" href="/plan" data-hn="plan">Plan</a></nav><div class="gap"></div>
{buttons}</div></div></header>{extras}
<div class="shell{' ads' if SHOW_RAILS else ''}{' wideads' if SHOW_RAILS and wide else ''}">{ad_rail('left')}
<div class="w{' wide' if wide else ''}">{topnav}{body}
<footer class="foot"><nav class="small"><a href="/">All games</a>
<a href="/popular">Most played</a><a href="/trending">Trending</a>
<a href="/growing">Growing</a><a href="/shrinking">Shrinking</a>
<a href="/busiest-hours">When is Roblox busiest?</a>
<a href="/events">Event calendar</a><a href="/compare">Compare games</a>
<a href="/plan">Plan a session</a>
<a href="/about">About</a><a href="/install">Get the app</a><a href="/privacy">Privacy Policy</a>
<a href="/terms">Terms of Service</a></nav>
<p class="mut small">Not affiliated with or endorsed by Roblox Corporation. Based on public player counts, so it
shows when people play, not whether a game is good or safe.{foot_contact()}</p></footer>
</div>{ad_rail('right')}</div>{ad_rail('bottom')}
{tail}<script>{CHROME_JS}</script>{HIT}</body></html>"""


# ---------------------------------------------------------------- small helpers

def slug(s, fallback="game"):
    """A name -> the form that goes in an address: "Break In (Story)" -> break-in-story.

    Accents are folded to the plain letter first ("Pokemon" rather than "pok-mon"),
    because an address is read by people typing it and by Google matching it, and a
    name's accents carry none of that. NFKD splits an accented letter into the letter
    plus its mark, and the marks are then dropped. It is stdlib, so the build server
    still installs nothing.

    Folding does not reach a name written in another script: Arabic, Chinese, Korean
    and Cyrillic have no ASCII to fall back to, so nothing survives and the caller's
    fallback is used. Pass one that is unique to the game - see name_slugs(), which
    passes the universe id. The bare default would put two such games at the same
    address.
    """
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or fallback


# Pictures and symbols that creators sprinkle through a game's name.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF"
                   "\u2190-\u21FF\u2300-\u27BF\u2B00-\u2BFF\uFE0F\u20E3]+")
# Anything in square brackets. On Roblox that is nearly always an advert:
# [UPD], [ALPHA], [HALLOWEEN PT 3], [X3 LUCK].
BRACKET = re.compile(r"\[[^\]]*\]")
# A round bracket group at the START of a name is an advert too:
# "(TOWING x LIMITED UPDATE Halloween-pumpkin) Drag Drive Simulator". One at the
# END is usually part of the real name, so it stays - of the five games on the
# site whose names carry round brackets, four are "BEAR (Alpha)",
# "Break In (Story)" and two "(Anomaly)"s, and only the leading one is promo.
LEAD_PAREN = re.compile(r"^\s*(?:\([^)]*\)\s*)+")


def clean_name(name):
    """The core of a Roblox game's name, with the seasonal advertising taken off.

    "[HALLOWEEN PT 3] Grand Piece Online" -> "Grand Piece Online"
    "DOORS 🍬🍭"                           -> "DOORS"
    "3008 [2.75]"                         -> "3008"

    This is what goes in the heading, the page title and the address, because it is
    what people actually type into Google and because it does not change when the
    creators swap one event banner for the next. The full name is still shown on the
    game's own page.

    Deliberately cautious. Square brackets and symbols always go. A round bracket
    group goes only when it is at the FRONT, where creators put promo tags; one at
    the end is left alone, because for a lot of games it is part of the real name
    ("Clone Baby Care (Anomaly)", "BEAR (Alpha)", "Break In (Story)").

    That matters for the address rather than just the heading: while the promo tag
    was in the name, this game's page lived at
    /game/towing-x-limited-update-drag-drive-simulator, so the day the creators
    took the tag off, prune() would delete that page and build a new one at a new
    address - losing every link to it and its standing in Google. Which is the
    whole reason this function exists.
    """
    out = EMOJI.sub(" ", BRACKET.sub(" ", name))
    # Only if there is still a real name left afterwards: a game called nothing
    # but "(Anomaly)" keeps it rather than ending up blank.
    lead = LEAD_PAREN.sub("", out)
    if says_something(lead):
        out = lead
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
        # The fallback carries the universe id because a name in a non-Latin script
        # leaves nothing to build an address from. A shared literal ("game") would be
        # taken by whichever such game sorts first, and the next one to be added would
        # take it instead - moving a live page to a new address, which prune() then
        # deletes. The whole point of clean_name() is that an address does not move.
        key = slug(nice, f"game-{uid}")
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
    y = max(1, round(d / 365))
    return f"{y} year{'s' if y > 1 else ''} ago"


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


# The short names players actually type into Google for a few games - "jjs player
# count", "tsb player count", "bss player count", "aotr likes" all turned up in
# Search Console. Written by hand, by slug, because nothing in Roblox's data says
# what a game is nicknamed. Add one only when people really search for it.
ALIASES = {
    "jujutsu-shenanigans": "JJS",
    "the-strongest-battlegrounds": "TSB",
    "bee-swarm-simulator": "BSS",
    "attack-on-titan-revolution": "AOTR",
    "bubble-gum-simulator-infinity": "BGSI",
    # The rest are the standard short names these games go by on their own wikis,
    # Discords and Reddit. Only ones the players themselves use - never invented.
    "tower-defense-simulator": "TDS",
    "toilet-tower-defense": "TTD",
    "pet-simulator-99": "PS99",
    "grow-a-garden": "GAG",
    "steal-a-brainrot": "SAB",
    "dress-to-impress": "DTI",
    "grand-piece-online": "GPO",
    "natural-disaster-survival": "NDS",
    "build-a-boat-for-treasure": "BABFT",
    "car-dealership-tycoon": "CDT",
    "lumber-tycoon-2": "LT2",
    "theme-park-tycoon-2": "TPT2",
    "tower-of-hell": "TOH",
    "murderers-vs-sheriffs": "MVS",
    "untitled-boxing-game": "UBG",
    "fling-things-and-people": "FTAP",
    "warrior-cats-ultimate-edition": "WCUE",
    "wild-horse-islands": "WHI",
    "flee-the-facility": "FTF",
    "survive-the-killer": "STK",
    "creatures-of-sonaria-survive-kaiju-animals": "CoS",
}


def search_key(c):
    """What the search boxes match against: the name plus its nickname, lower case,
    with apostrophes taken out so "sols rng" finds Sol's RNG. The browser strips the
    same characters from what was typed, so the two always compare like with like."""
    k = f'{c["name"]} {ALIASES.get(c["slug"], "")}'.lower().strip()
    return k.replace("'", "").replace("’", "")


def stamp(ts):
    """A reading's exact time -> '4:30 PM UTC on Wed 18 Nov'."""
    d = datetime.fromtimestamp(ts, timezone.utc)
    return f"{d.hour % 12 or 12}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'} UTC on {when(ts)}"


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


def iso_moment(ts):
    """A point in time -> '2026-11-16T14:00:00Z'.

    What structured data wants for a moment, as opposed to iso_day() which is only
    the date. Always UTC and always says so with the Z, because the builder cannot
    know where the reader is and a time without a zone is a time nobody can place.
    """
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def tile(c, i=0, href=None, meta=None):
    """One game as a tile.

    href and meta exist so a row of tiles can point somewhere other than the game
    page and say something other than the player count - the updates pages use
    both. They default to what every other row on the site shows, so a caller that
    does not care about either writes nothing.
    """
    # --glow is the hue of this game's own picture, so the glow behind the tile is
    # the game's colour. Left off entirely when the picture has no colour in it, so
    # that the stylesheet's fallback (the site accent) takes over.
    glow = "" if c.get("hue") is None else f';--glow:{c["hue"]}'
    if meta is None:
        meta = (f'<span title="Typical players over the last 7 days">{PERSON} '
                f'{short(c["avg"])}</span>{trend_short(c["trend"])}')
    return (f'<li style="--i:{min(i, 14)}{glow}" data-n="{html.escape(search_key(c))}" data-s="{c["slug"]}">'
            f'<a class="tile" href="{href or "/game/" + c["slug"]}">'
            f'{thumb(c["name"], c["icon"], icon_alt(c["name"]))}'
            f'<span class="tname">{html.escape(c["name"])}</span>'
            f'<span class="tmeta">{meta}</span></a></li>')


def grid(cards, gid="", href=None, meta=None):
    """A row of game tiles. href and meta, when given, are functions of the card."""
    idattr = f' id="{gid}"' if gid else ""
    return (f'<ul class="grid"{idattr}>'
            + "".join(tile(c, i,
                           href(c) if href else None,
                           meta(c) if meta else None)
                      for i, c in enumerate(cards))
            + '</ul>')


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
    # The three chips became Busy now / Quiet now / Popular in the header bar, where
    # they are on every page instead of halfway down one. What is left is the two
    # lines the filter writes into: which games are being shown, and the admission
    # when nothing is properly quiet and the band had to be widened to find any.
    return ('<div id="asknote" class="note" hidden></div>'
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


def foot_contact():
    """The same address at the very bottom of every page (19 Nov 2026, owner's
    call: it was a section inside the Terms of Service, which is the last place
    somebody with a question would think to look). About and the Privacy Policy
    keep their own Contact heading - a privacy policy that cannot be replied to is
    not much of one - but the Terms no longer carry one, because the foot of the
    page is on that page too."""
    if not CONTACT:
        return ""
    e = html.escape(CONTACT)
    return f' Questions or problems? Email <a href="mailto:{e}">{e}</a>.'


# ---------------------------------------------------------------- the maths

# A day counts in the day-by-day figures only if we have readings in at least this
# many of its 24 hours.
#
# Those figures bucket samples by calendar day, so the newest bucket is always a day
# still in progress - and the hours it is missing are the LATE ones, which are the
# busy ones. Measured 23 Nov 2026 across every game with 500+ readings: a complete
# day holds readings in 20-24 of its hours (median 24), the newest day holds 14-19
# (median 14), and the first day we ever saw a game holds 1-24 (median 8). Every one
# of 57 games tested ended on a partial day reading LOWER than the day before -
# 2,232 against 2,602 on Work at a Pizza Place, 6,083 against 6,547 on Natural
# Disaster Survival - so every history chart on the site showed every game dipping
# today. An artefact, universal, and quietly undercutting the trends this site
# exists to report.
#
# 18 sits in the gap between those two groups: it keeps 100% of complete days and
# drops 99% of partial ones. It tests COVERAGE rather than how many samples arrived,
# because gaps in collection are normal - a third of the gaps between readings run
# over 25 minutes - while missing whole hours is not.
#
# It does NOT reach index_ok(), which reads the span of our samples and the 168-hour
# coverage, so no page can appear or disappear because of this.
DAY_HOURS_MIN = 18

# How quickly an old reading stops counting towards the week grid, in days. A
# reading a fortnight old pulls half as hard as one from today, one a month old a
# quarter as hard. The shape of a game's week is not fixed - creators add a weekend
# event, a school holiday ends - so the recent shape should win, but slowly enough
# that a quiet hour is still drawn from several weeks of readings rather than one.
#
# Chosen by backtest, not by eye (23 Nov 2026): the last 7 days of all 140 games
# were held back, the grid built from what came before, and each hour's prediction
# scored against what really happened. Dividing the trend out took the median error
# from 18.9% to 16.3% and the worst tenth from 120% to 88%; adding this on top took
# them to 15.9% and 87.2%. Every alternative tried was worse, including using only
# the last 14 days of readings.
HALF_LIFE = 14


def analyze(rows):
    """Turns a game's player counts into everything the pages need.

    rows is [(time, players)] oldest first. Returns a dictionary with:
      week    7x24 table of typical players (Monday first, UTC hours), scaled to
              the size the game is now - the rhythm of a week with the game's own
              rise or fall divided out of it
      daily   [(midnight, typical players)] one entry per WHOLE day, oldest
              first - a day still in progress is left out, see DAY_HOURS_MIN
      trend   % change, last 7 days against the 7 days before
      month   % change, last 14 days against the 14 days before
      avg7    typical players over the last 7 days
      peak    the most players we have ever seen
      spikes  days that were much busier than usual
      peaks   [(midnight, typical players, highest seen that day)] oldest first
      first   the time of our oldest player count for this game
      last    the time of our newest player count
      hours   how many of the week's 168 hours we have ever seen this game in
      latest  (time, players) of our newest player count
      low7    (time, players) the lowest single count in the last 7 days
      high7   (time, players) the highest single count in the last 7 days
      peak_at the time we saw `peak`
    """
    def mean(vals):
        return sum(vals) / len(vals) if vals else None

    by_day = {}
    day_hrs = {}
    stamps = []
    now = rows[-1][0]
    buckets = {7: [], 14: [], 28: []}
    for ts, p in rows:
        d = datetime.fromtimestamp(ts, timezone.utc)
        day = ts // 86400
        # Kept so the week grid can be built below without converting every
        # reading's clock a second time.
        stamps.append((d.weekday(), d.hour, day, p))
        by_day.setdefault(day, []).append(p)
        day_hrs.setdefault(day, set()).add(d.hour)
        age = (now - ts) / 86400
        for span in buckets:
            if age <= span:
                buckets[span].append((age, p))
    # Whole days only - see DAY_HOURS_MIN. A game we have never yet watched through
    # a full day keeps what it has rather than being left with an empty chart.
    whole = [d for d in sorted(by_day) if len(day_hrs[d]) >= DAY_HOURS_MIN]
    if not whole:
        whole = sorted(by_day)
    daily = [(d * 86400, round(sum(by_day[d]) / len(by_day[d]))) for d in whole]
    # The same days again, with the highest count we actually saw on each one. The
    # average is our estimate of a typical moment; the maximum is a real observation,
    # and the pages are careful to say which is which.
    peaks = [(d * 86400, round(sum(by_day[d]) / len(by_day[d])), max(by_day[d])) for d in whole]

    # The week grid: what a typical moment at each hour looks like, AT THE SIZE THE
    # GAME IS NOW.
    #
    # It used to be the plain average of every reading we had ever taken at that
    # hour, which quietly mixed two different things: the daily rhythm, which is
    # what this grid is for, and the game's own rise or fall, which is not. For a
    # game that has not moved the two are the same answer. For one that has, the
    # grid was a memory. Measured on 23 Nov 2026 across 148 games: 106 were within
    # 20% of the game as it is now, 19 were out by half or more, and The Hollow -
    # which fell from 96,000 players a day to 209 in the three weeks we watched -
    # had a grid 43 times its real size. Its page said "Busiest: Saturday around
    # 5 PM, about 134,407 players" of a game with about 200 in it. That is not a
    # busy hour, it is a game that died, and the whole point of this site is
    # telling somebody when to turn up.
    #
    # So each reading is divided by the game's level at the time, the hours are
    # averaged as ratios, and the ratios are scaled back up by what the game is
    # doing now. What survives is the shape of a week; what is divided out is the
    # trend.
    #
    # The level is a SEVEN-DAY centred mean, and the seven matters: a level taken
    # from each day on its own would divide out Saturday being busier than Tuesday,
    # which is a real part of the rhythm and one of the things people come here to
    # see. A week-wide window holds every weekday once, so it carries the trend and
    # nothing else.
    #
    # Only whole days set the level (see DAY_HOURS_MIN) - a day we only saw the
    # small hours of would read as a quiet day rather than a short one. Readings on
    # a part-day borrow the nearest whole day's level.
    #
    # Nothing observed is touched by any of this. "Highest seen", "lowest this
    # week" and the peak are single readings we really took and are still reported
    # exactly as they came in: the estimate and the observation stay apart, as they
    # must everywhere on this site.
    dmean = {d: sum(by_day[d]) / len(by_day[d]) for d in whole}
    known = sorted(dmean)
    level = {}
    for d in known:
        win = [dmean[x] for x in known if abs(x - d) <= 3]
        level[d] = sum(win) / len(win)
    # Every day we hold a reading for, including the part-days at each end.
    lv = {}
    for d in by_day:
        if d in level:
            lv[d] = level[d]
        elif known:
            lv[d] = level[min(known, key=lambda x: abs(x - d))]
    avg7 = round(mean([p for age, p in buckets[7]]) or 0)
    # A reading counts for half as much as it would have done a fortnight earlier.
    # The shape of a week really does change - a game adds a weekend event, a school
    # holiday ends - and fourteen days was not picked by eye: see HALF_LIFE.
    rsum = [[0.0] * 24 for _ in range(7)]
    rcnt = [[0.0] * 24 for _ in range(7)]
    sums = [[0] * 24 for _ in range(7)]
    cnt = [[0] * 24 for _ in range(7)]
    newest = rows[-1][0] // 86400
    for wd, hr, day, p in stamps:
        sums[wd][hr] += p
        cnt[wd][hr] += 1
        L = lv.get(day)
        if L:
            w = 0.5 ** ((newest - day) / HALF_LIFE)
            rsum[wd][hr] += w * p / L
            rcnt[wd][hr] += w
    if len(level) >= 3 and avg7:
        week = [[round(rsum[d][h] / rcnt[d][h] * avg7) if rcnt[d][h] else None
                 for h in range(24)] for d in range(7)]
    else:
        # Too new to know what its level even is. The plain average is all there is,
        # and a game this new has no page yet anyway (see index_ok).
        week = [[round(sums[d][h] / cnt[d][h]) if cnt[d][h] else None
                 for h in range(24)] for d in range(7)]

    def change(span):
        """% difference between the last `span` days and the `span` days before them."""
        pts = buckets[span * 2] if span * 2 in buckets else []
        a = mean([p for age, p in pts if age <= span])
        b = mean([p for age, p in pts if span < age <= span * 2])
        return round((a - b) / b * 100, 1) if a and b else None

    peak_at = max(rows, key=lambda r: r[1])[0]
    return {"week": week, "daily": daily, "peaks": peaks,
            "trend": change(7), "month": change(14),
            "avg7": avg7,
            "peak": max(p for _, p in rows),
            "spikes": find_spikes(daily),
            "first": rows[0][0], "last": rows[-1][0],
            "hours": sum(1 for row in week for v in row if v is not None),
            # Searchers ask for "player count right now", "lowest" and "highest" in
            # those words, so the pages answer with real single readings - each with
            # the moment we took it, since an observation without a time is a guess.
            # A zero is left out of the lowest: it is far likelier a failed reading
            # than a game with nobody in it.
            "latest": rows[-1],
            "low7": min(((ts, p) for ts, p in rows if now - ts <= 7 * 86400 and p > 0),
                        key=lambda r: r[1], default=None),
            "high7": max(((ts, p) for ts, p in rows if now - ts <= 7 * 86400),
                         key=lambda r: r[1], default=None),
            "peak_at": peak_at,
            # What a typical moment looked like on the day we saw that peak.
            #
            # The key numbers put the all-time peak directly under today's typical
            # count, and on a game that has since shrunk the pair reads as nonsense:
            # The Hollow says 507,606 against 286, which is 1,775x. Measured across
            # all 140 games on 23 Nov 2026, that gap is almost never the peak being
            # strange - within a single day no game's peak reached even 10x that
            # day's own average, and only 12% reached 3x - it is the game having
            # been a different size then. The Hollow was typically running 96,173
            # the day it peaked. So the honest context is the level at the time,
            # not a multiple of a level from weeks later.
            #
            # None when the peak fell on a day we did not watch all the way through
            # (see DAY_HOURS_MIN), because there is then no whole-day figure to
            # quote and a partial one would be the very artefact we just removed.
            "peak_day": next((v for t, v in daily if t // 86400 == peak_at // 86400), None),
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
    """Answers "is this game dead?" in plain English.

    Returns (label, colour, sentence, trend). The sentence opens by answering the
    question the "Is X dead?" card asks - "No.", "Not dead, but it is sliding." -
    and `trend` is the rest of it without that answer, for anywhere the question
    being asked is a different one.

    That split exists because the questions page asks "Do people still play X?",
    answers it "Yes" with a live count, and then glued this whole sentence on after
    it: on 18 Nov 2026, 42 of the 140 live pages read "Yes. 263,503 people were
    playing Adopt Me at our last check... No. It is picking up a little." Both
    halves are written out here rather than cut apart with a regex at the other
    end, so rewording one cannot quietly stop the other from working.
    """
    t, m, days = a["trend"], a["month"], a["days"]
    if days < 10 or t is None:
        # No lead to strip: this one does not answer yes or no in the first place.
        rest = ("We have not been watching this game long enough to say which way it is "
                "going. Check back in a week or two.")
        return ("Too new to say", "var(--l3)", rest, rest)
    # The last two weeks matter most; the longer view stops one odd week fooling us.
    score = t if m is None else t * 0.65 + m * 0.35
    players = short(a["avg7"])
    if score >= 15:
        rest = (f"More people are playing than a week ago, with about {players} "
                f"in the game at a typical moment.")
        return ("Growing", "var(--l1)", "No, the opposite. " + rest, rest)
    if score >= 5:
        rest = f"It is picking up a little, with about {players} players at a typical moment."
        return ("Slowly growing", "var(--l1)", "No. " + rest, rest)
    if score > -5:
        rest = (f"It has about the same number of players as last week: roughly {players} "
                f"at a typical moment.")
        return ("Steady", "var(--l2)", "No. " + rest, rest)
    if score > -20:
        rest = (f"Fewer people are playing than a week ago, though about "
                f"{players} are still in the game at a typical moment.")
        return ("Getting quieter", "var(--l4)", "Not dead, but it is sliding. " + rest, rest)
    rest = (f"It is dropping quickly: a lot fewer people than a week ago. About {players} "
            f"players are still there at a typical moment, so it is quiet rather than empty.")
    return ("Losing players fast", "var(--l5)", rest, rest)


def scrub(svg, h, labels, ys, texts, hues):
    """Wraps a chart drawn here at build time so it can be dragged like the hourly graph.

    The chart itself stays a plain SVG, so a search engine and anybody with
    JavaScript off still see it. On top go a dashed line and one dot per series,
    which SCRUB_JS in SHARED_JS slides along as somebody drags, hovers, taps or
    presses the arrow keys, writing that point's numbers into the readout below.

    Every position is worked out HERE, from the same x()/y() that drew the line,
    and handed over as percentages of the box - so the browser does no maths of its
    own and the dot cannot drift off the line the way graphCursor would if its H
    stopped matching dayGraph's. Percentages also matter because these charts use
    preserveAspectRatio="none": a circle drawn inside the SVG would be squashed
    into an oval, so the dots are HTML on top instead.

    labels: one per point. ys: per point, one viewBox y per series. texts: per
    point, the readout's HTML. hues: one CSS colour name per series ("acc", "alt").
    """
    n = len(labels)
    pts = [[round(i / (n - 1) * 100, 2), [round(y / h * 100, 2) for y in ys[i]], texts[i]]
           for i in range(n)]
    dots = "".join(f'<b class="sdot" style="border-color:var(--{c})"></b>' for c in hues)
    pdots = "".join(
        f'<b class="pdot" style="left:{pt[0]}%;top:{pt[1][k]}%;'
        f'background:var(--{c})"></b>'
        for pt in pts for k, c in enumerate(hues))
    return (f'<div class="scrub" tabindex="0" role="group" aria-label="Drag across the '
            f'graph, or use the arrow keys, to read any day" '
            f'data-scrub="{html.escape(json.dumps(pts, separators=(",", ":")))}">{svg}'
            f'<i class="sline" hidden></i>{pdots}{dots}</div>'
            f'<p class="readout chartout" aria-live="polite"></p>')


def sparkline(daily, spikes):
    """A small line chart of the last 45 days, with a dot on each spike day."""
    pts = daily[-45:]
    if len(pts) < 3:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    # Kept level with .spark's CSS height: preserveAspectRatio is none, so a
    # coordinate space taller than the box drawn on screen only thins the line.
    w, h = 600, 190
    x = lambda i: round(i / (len(pts) - 1) * w, 1)
    y = lambda v: round(h - 6 - (v - lo) / span * (h - 14), 1)
    line = " ".join(f"{x(i)},{y(v)}" for i, (_, v) in enumerate(pts))
    spike_days = {d for d, _ in spikes}
    dots = "".join(f'<circle cx="{x(i)}" cy="{y(v)}" r="4" fill="var(--alt)"><title>'
                   f'{when(d)}: about {v:,} players, much busier than usual</title></circle>'
                   for i, (d, v) in enumerate(pts) if d in spike_days)
    svg = (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" '
           f'aria-label="Typical players each day over the last {len(pts)} days">'
           f'<polygon points="0,{h} {line} {w},{h}" fill="var(--acc)" opacity=".13"/>'
           f'<polyline points="{line}" fill="none" stroke="var(--acc)" stroke-width="2.5" '
           f'vector-effect="non-scaling-stroke" '
           f'stroke-linejoin="round" stroke-linecap="round"/>{dots}</svg>')
    texts = [f'<b>{when(d)}</b> &middot; about <b>{v:,}</b> players'
             + (' &middot; much busier than usual' if d in spike_days else '')
             for d, v in pts]
    return (scrub(svg, h, [d for d, _ in pts], [[y(v)] for _, v in pts], texts, ["acc"])
            + '<p class="mut small">The dots are days that were much busier than usual.</p>')


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


def swing_text(name, f):
    """How much the time of day actually matters for this game.

    The whole site answers "when should I play", and until now no page anywhere
    said whether the answer was worth acting on. Some games are five times busier
    at their peak than at their lowest point; others barely move all week, and
    somebody reading about one of those deserves to be told that picking a moment
    will not change much.

    It is arithmetic on the two numbers printed directly above it, nothing more,
    so it cannot disagree with them and it claims nothing new. Both are averages,
    so the wording keeps "about" and "typical" on it - see "Estimate vs
    observation". The quietest hour can be zero on a game we have barely seen, so
    a ratio is only drawn when there is something to divide by.
    """
    if not f:
        return ""
    bv, qv = f["busy"][2], f["quiet"][2]
    if qv < 1 or bv <= qv:
        return ""
    r = bv / qv
    if r >= 3:
        verdict = "so picking your moment makes a big difference"
    elif r >= 1.8:
        verdict = "so it is worth picking your moment"
    else:
        verdict = f"so {html.escape(name)} is fairly steady whenever you play"
    how = f"{r:.0f}" if r >= 10 else f"{r:.1f}"
    return (f'At its busiest there are about <b>{how} times</b> as many players as '
            f'at its quietest, {verdict}.')


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


def peak_note(a):
    """", when a typical moment was about 96,000" - or "" when that adds nothing.

    Only written where the all-time peak towers over today's typical count (3x or
    more, which is 45% of games), because that is the pairing a reader cannot make
    sense of on its own. Below that the two numbers already sit together sensibly
    and the extra clause would be noise.
    """
    if not a.get("peak_day") or not a["avg7"] or a["peak"] < a["avg7"] * 3:
        return ""
    return f', when a typical moment was about {a["peak_day"]:,}'


def stale_note(a):
    """" - older than usual; we have had no newer count since".

    It names no cause on purpose. A reading can go stale because Roblox stopped
    answering for that one game, or because our own collector stalled, and from
    inside the build those look identical - blaming Roblox would be a guess, and
    on a general outage it would be a guess that is wrong on every page at once.
    The sentence states only what we know: nothing newer has arrived.

    The collector really runs about every 62 minutes (its cron asks for 30, but a
    run takes some 21 and scheduled jobs are throttled on a free plan), so at build
    time the newest reading is normally well under two hours old. Measured 23 Nov
    2026 across 148 games: the median game was level with the newest reading in the
    database and exactly ONE sat more than six hours behind, at 42 hours - a game
    Roblox had quietly stopped answering for.

    Six hours is therefore a wide margin rather than a hair trigger. It is measured
    from the moment of the BUILD, which can be six hours before the page is read, so
    a page may understate how old a reading is by one build. It can never overstate
    it, because the gap only ever grows.
    """
    if time.time() - a["latest"][0] < 6 * 3600:
        return ""
    return " &ndash; older than usual; we have had no newer count since"


def facts_html(c, a, f, meta=None):
    """The key numbers as a list, so they are in the page itself and not only in a chart."""
    rows = [("Latest player count", f'{a["latest"][1]:,}',
             f'at {stamp(a["latest"][0])}{stale_note(a)}'),
            ("Players at a typical moment", f'{a["avg7"]:,}', "average over the last 7 days"),
            ("Highest player count ever seen", f'{a["peak"]:,}',
             f'the most we have recorded, on {when(a["peak_at"])}{peak_note(a)}')]
    if a["high7"] and a["low7"]:
        rows += [("Highest this week", f'{a["high7"][1]:,}', f'at {stamp(a["high7"][0])}'),
                 ("Lowest this week", f'{a["low7"][1]:,}', f'at {stamp(a["low7"][0])}')]
    meta = meta or {}
    if meta.get("visits"):
        rows.append(("Total visits", short(meta["visits"]), f'{meta["visits"]:,}, as Roblox reports it'))
    if meta.get("likes"):
        votes = meta["likes"] + (meta.get("dislikes") or 0)
        rows.append(("Likes", short(meta["likes"]),
                     f'{meta["likes"] / votes:.0%} of {short(votes)} votes are likes'
                     if votes else "as Roblox reports it"))
    if meta.get("created"):
        rows.append(("Came out", when(meta["created"]), f'first released {ago(meta["created"])}'))
    rows += [("Compared to last week", trend_html(a["trend"]), "last 7 days against the 7 before")]
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
    # Only when the picture has holes in it. 95% of games have been seen in all 168
    # hours of the week (measured 23 Nov 2026), so printing "168 of 168" on every
    # page would be noise on 140 of them and would train people to skip the row -
    # the same reason the dashboard's "Needs doing" list refuses advice that is
    # always true. The eight that fall short are new games still filling in, and on
    # those it is the honest caveat beside a half-empty heatmap.
    if a["hours"] < 168:
        rows.append(("How much of the week we have seen", f'{a["hours"]} of 168 hours',
                     "an hour we have no reading for shows a dash, not a zero"))
    # On a phone this card is a whole screen tall, so only the first three rows show
    # there and the rest open behind "More stats" (see .facts.fold). Everything stays
    # in the HTML, so search engines read every row.
    return ('<dl class="facts" id="facts">'
            + "".join(f'<div{" class=x" if i >= 3 else ""}><dt>{k}<span>{note}</span></dt>'
                      f'<dd>{v}</dd></div>'
                      for i, (k, v, note) in enumerate(rows))
            + "</dl>"
            + ('<button class="morestats" type="button" aria-controls="facts" '
               'aria-expanded="false">More stats</button>' if len(rows) > 3 else ""))


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
            f'hour by hour, in UTC. The shape comes from every reading we have taken; '
            f'the size is what the game is now, so a game that has grown or shrunk is '
            f'not still showing you last month. A dash means we have not collected a '
            f'player count in that hour yet.</p><div class="wrap"><table class="hourtbl">'
            f'<thead><tr><th>Day (UTC)</th>{head}</tr></thead><tbody>{body}</tbody>'
            f'</table></div></details>')


def history_lines(pts):
    """Two lines over the same days: the typical count and the highest seen.

    Drawn here rather than in the browser because it needs no timezone - a day is a
    day - so a search engine and anybody with JavaScript off see the same picture.

    Both lines share one scale, which is the point of putting them together: the gap
    between them is how much a game's quiet moments differ from its peak, and two
    charts each scaled to themselves would hide exactly that.
    """
    avgs = [avg for _, avg, _ in pts]
    his = [hi for _, _, hi in pts]
    lo, top = min(avgs), max(his)
    span = (top - lo) or 1
    w, h = 600, 150
    x = lambda i: round(i / (len(pts) - 1) * w, 1)
    y = lambda v: round(h - 8 - (v - lo) / span * (h - 20), 1)
    hiline = " ".join(f"{x(i)},{y(v)}" for i, v in enumerate(his))
    avline = " ".join(f"{x(i)},{y(v)}" for i, v in enumerate(avgs))
    svg = (f'<svg class="hist" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" '
            f'aria-label="Typical and highest player counts for each of the last '
            f'{len(pts)} days">'
            # The highest line is drawn first and sits above, so the wash under it
            # reads as the whole range rather than as a second solid shape.
            f'<polygon points="0,{h} {hiline} {w},{h}" fill="var(--alt)" opacity=".10"/>'
            f'<polyline points="{hiline}" fill="none" stroke="var(--alt)" stroke-width="2.5" '
            f'vector-effect="non-scaling-stroke" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<polyline points="{avline}" fill="none" stroke="var(--acc)" stroke-width="2.5" '
            f'vector-effect="non-scaling-stroke" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')
    texts = [f'<b>{when(d)}</b> &middot; typical <b>{av:,}</b> &middot; highest seen '
             f'<b>{hi:,}</b>' for d, av, hi in pts]
    return scrub(svg, h, [d for d, _, _ in pts], [[y(av), y(hi)] for _, av, hi in pts],
                 texts, ["acc", "alt"])


def history_html(name, a, days=21):
    """The last few weeks day by day: the heart of "player count history".

    Two numbers that must not be muddled, which is why they are two lines and two
    columns and never one. The typical count is an average of the samples we took
    that day, so it is an estimate. The highest is a single number we really saw, so
    it is an observation.

    The graph is the thing to look at; the table is still written out underneath,
    inside a <details>, because every number a page claims should be readable as text
    and a search engine cannot read an SVG.
    """
    pts = a["peaks"][-days:]
    if len(pts) < 3:
        return ""
    rows = "".join(f'<tr><td>{when(day)}</td><td>{avg:,}</td><td>{hi:,}</td></tr>'
                   for day, avg, hi in reversed(pts))
    return (f'<div class="card"><h2>{html.escape(name)} player count graph</h2>'
            + history_lines(pts) +
            # Short, but the two still cannot be mixed up: one is an average we
            # worked out, the other a number we really saw. That distinction is the
            # point of drawing two lines at all.
            f'<p class="hleg"><span class="k acc"></span>Typical &mdash; the day&rsquo;s '
            f'average. <span class="k alt"></span>Highest &mdash; the biggest count we '
            f'actually saw.</p>'
            f'<details><summary>Every day as a table</summary>'
            f'<div class="wrap"><table class="tbl"><thead><tr><th>Day</th>'
            f'<th>Typical players</th><th>Highest seen</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></details></div>')


def faq_html(c, a, f, meta, pattern):
    """The questions people type into Google, answered with our own numbers.

    Returns (html, [(question, plain answer)]) so the same answers can go into the
    page's structured data without being written out twice.
    """
    name = c["name"]
    lt, lp = a["latest"]
    qa = [(f"How many people are playing {name} right now?",
           f"At our most recent check, at {stamp(lt)}, {lp:,} people were playing {name}. "
           f"We read Roblox's public player count about every ten minutes and refresh this "
           f"page four times a day, so that number can be a few hours old. At a typical "
           f"moment over the last week there were about {a['avg7']:,}.")]
    qa.append((f"What is the highest player count {name} has had?",
               f"The most people we have seen in {name} at once is {a['peak']:,}, on "
               f"{when(a['peak_at'])}."
               + (f" This week the highest was {a['high7'][1]:,}, at {stamp(a['high7'][0])}."
                  if a["high7"] else "")
               + f" We have been counting since {when(a['first'])}, so a record from before "
               f"then would not show here."))
    if a["low7"]:
        qa.append((f"What is the lowest player count {name} has?",
                   f"The fewest people we saw in {name} over the last 7 days was "
                   f"{a['low7'][1]:,}, at {stamp(a['low7'][0])}. That is everybody in the "
                   f"game at that moment, across every server."))
    qa.append((f"How many people play {name}?",
           f"About {a['avg7']:,} people are in {name} at a typical moment, averaged over "
           f"the last 7 days. The most we have ever recorded at once is {a['peak']:,}. "
           f"These are our own readings of Roblox's public player count, taken roughly "
           f"every ten minutes."))
    if f:
        bd, bh, bv = f["busy"]
        qd, qh, qv = f["quiet"]
        qa.append((f"What is the best time to play {name}?",
                   f"For quiet servers, aim for {DAYS[qd]} around {hour12(qh)} UTC, when "
                   f"there are usually about {qv:,} players. For full servers and trading, "
                   f"{DAYS[bd]} around {hour12(bh)} UTC is the busiest hour we see, at "
                   f"roughly {bv:,} players. Those hours are UTC. The graph on the game "
                   f"page shows them on your own clock."))
        extra = (f" {DAYS[f['busy_day']]} is its busiest day overall."
                 if f["busy_day"] is not None else "")
        qa.append((f"When is {name} busiest?",
                   f"{DAYS[bd]} around {hour12(bh)} UTC is its busiest hour in a typical "
                   f"week, with about {bv:,} players.{extra}"))
    # verdict()[3], never [2]: this question has already been answered "Yes" by the
    # live count in front of it, and [2] opens by answering "Is X dead?" instead.
    qa.append((f"Do people still play {name}?",
               f"Yes. {lp:,} people were playing {name} at our last check, at {stamp(lt)}. "
               + re.sub(r"</?b>", "", verdict(a)[3])
               if a["avg7"] else re.sub(r"</?b>", "", verdict(a)[3])))
    if pattern:
        every = f", roughly every {pattern['every']} days" if pattern.get("every") else ""
        hour = f" at about {hour12(pattern['hour'])} UTC" if pattern.get("hour") is not None else ""
        qa.append((f"When does {name} update?",
                   f"Updates and events usually land on a {DAYS[pattern['wd']]}{hour}{every}. "
                   f"That comes from the last {pattern['n']} updates the creators announced "
                   f"on Roblox plus the days we saw the player count jump."))
    if meta and meta.get("likes"):
        votes = meta["likes"] + (meta.get("dislikes") or 0)
        qa.append((f"How many likes does {name} have?",
                   f"Roblox reports {meta['likes']:,} likes for {name}"
                   + (f", which is {meta['likes'] / votes:.0%} of the {votes:,} people who "
                      f"voted on it." if votes else ".")))
    if meta and meta.get("created"):
        qa.append((f"When did {name} come out?",
                   f"{name} was first released on Roblox on {when(meta['created'])}, "
                   f"{ago(meta['created'])}."))
    if meta and meta.get("visits"):
        qa.append((f"How many visits does {name} have?",
                   f"Roblox reports {meta['visits']:,} total visits for {name} so far"
                   + (f", and it was first released {ago(meta['created'])}."
                      if meta.get("created") else ".")))
    # Each answer ends with a link to the part of the game page that shows it - the
    # graphs and the key numbers live there, and Google may send a search to either
    # page. Only the HTML gets the links; qa stays plain text for the structured data.
    # The history card only exists with 3+ days of readings (history_html), so its
    # links fall back to the key numbers rather than pointing at an id that is absent.
    g = f'/game/{c["slug"]}'
    hist = f"{g}#history" if len(a["peaks"]) >= 3 else f"{g}#stats"
    links = {
        f"How many people are playing {name} right now?":
            (f"{g}#stats", "See the latest count and this week&rsquo;s highs and lows"),
        f"What is the highest player count {name} has had?":
            (hist, "See the highest count for each day on a graph"),
        f"What is the lowest player count {name} has?":
            (f"{g}#stats", "See this week&rsquo;s lowest and highest"),
        f"How many people play {name}?":
            (hist, "See the player count day by day"),
        f"What is the best time to play {name}?": (f"{g}#byhour", "See every hour on a graph"),
        f"When is {name} busiest?": (f"{g}#byhour", "See every hour on a graph"),
        f"Do people still play {name}?": (f"{g}#dead", "See the 45-day trend"),
        f"When does {name} update?":
            (f'/updates/{c["slug"]}', "See every update in order and when the next is due"),
        f"How many visits does {name} have?": (f"{g}#stats", "See all its numbers"),
        f"How many likes does {name} have?": (f"{g}#stats", "See all its numbers"),
    }
    def more(q):
        if q not in links:
            return ""
        href, text = links[q]
        return f'<p class="small"><a href="{href}">{text} &rarr;</a></p>'
    body = "".join(f"<h3>{html.escape(q)}</h3><p>{html.escape(ans)}</p>{more(q)}"
                   for q, ans in qa)
    return (f'<div class="card faq"><h2>{html.escape(name)}: common questions</h2>{body}'
            f'<p class="mut small">Answers come from our own player counts, which are '
            f'estimates built from samples, not official Roblox figures.</p></div>'), qa


def event_schema(c, events, now):
    """The creators' upcoming events, in the form Google reads.

    Roblox events happen inside the game rather than anywhere on a map, so they are
    VirtualLocation pointing at the game on Roblox, and the attendance mode says
    online. Nothing here is invented: the name, the start and the end are the
    creators' own, and an event with no end is left without one rather than being
    given a guess.
    """
    out = []
    for e in sorted(events or [], key=lambda e: e["start"]):
        if e["start"] <= now or len(out) >= 10:
            continue
        ev = {
            "@type": "Event",
            "name": e["title"][:110],
            "startDate": iso_moment(e["start"]),
            "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
            "eventStatus": "https://schema.org/EventScheduled",
            "location": {"@type": "VirtualLocation",
                         "url": f'https://www.roblox.com/games/{c["place"]}'},
            "organizer": {"@type": "Organization", "name": c["name"]},
            "url": abs_url(f'/game/{c["slug"]}'),
        }
        if e.get("end"):
            ev["endDate"] = iso_moment(e["end"])
        desc = clean_desc(e.get("description") or "")[:300]
        if desc:
            ev["description"] = desc
        if c["icon"]:
            ev["image"] = c["icon"]
        out.append(ev)
    return out


def faq_schema(qa):
    """The questions and answers, in the form Google reads.

    It belongs wherever the questions themselves are written out, which is now a page
    of its own: a FAQPage block on a page that does not show the questions would be
    telling Google about content that is not there.
    """
    return [{"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q,
         "acceptedAnswer": {"@type": "Answer", "text": ans}} for q, ans in qa]}] if qa else []


def game_schema(c, a, meta, qa):
    """Structured data for one game page: what the game is, and what our data covers.

    Only facts already written on the page go in here. There is deliberately no rating
    and no review: we do not collect either, and inventing them would be lying to
    Google as well as to visitors.
    """
    url = abs_url(f'/game/{c["slug"]}')
    game = {"@type": "VideoGame", "name": c["name"], "url": url, "gamePlatform": "Roblox",
            "playMode": "MultiPlayer", "applicationCategory": "Game"}
    if ALIASES.get(c["slug"]):
        game["alternateName"] = ALIASES[c["slug"]]
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
            # Google asks every Dataset for a license and warns when one is missing
            # (Search Console, 14 Nov 2026, non-critical). It is our own Terms page
            # rather than an open licence such as CC BY, because Terms says personal
            # use and asks people not to copy the site wholesale - publishing a
            # licence that contradicts our own terms would be worse than the warning.
            # If the numbers are ever meant to be reusable, change BOTH Datasets and
            # the "Using the site" section of terms_page() together.
            "license": abs_url("/terms"),
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


def says_something(t):
    """Is there any actual word in this, or is it a row of punctuation?

    Roblox creators use the subtitle as a hype line, and a good number of them
    are '????' or '!!!!!!!!' or a string of emoji. Measured 16 Nov 2026: 95 of
    the 985 subtitles on the site had no letter or digit anywhere in them, and
    they read as broken encoding rather than as something a person wrote.

    `isalnum()` per character rather than a Latin range on purpose, so a
    subtitle written in Japanese or Cyrillic still counts as saying something.
    """
    return any(ch.isalnum() for ch in str(t))


# Roblox's own name for each kind of update, in words this audience can read.
# The classification is theirs, not ours, and that is the whole point: a tag saying
# what WE thought an update was would be a guess, and the rule on this site is that
# nothing is claimed that the data does not say. Measured 22 Nov 2026 across 388
# public events - all 14 of these appeared, every event carried one, and only 4%
# carried a second, which is why only the first is shown.
#
# The list is not closed, and that has already been proved rather than guessed at:
# building the whole site turned up "earlyAccess", which is not in this table, and
# event_kind() un-camelled it to "Early access" with nothing to fix. Add a name here
# only when the fallback reads badly.
EVENT_KIND = {
    "newContent": "New content",
    "contentUpdate": "Content update",
    "newFeature": "New feature",
    "newMap": "New map",
    "newLocation": "New place",
    "locationUpdate": "Place update",
    "newSeason": "New season",
    "itemDrop": "New items",
    "festival": "Festival",
    "challenge": "Challenge",
    "quest": "Quest",
    "activity": "Activity",
    "expansion": "Expansion",
    "systemUpdate": "Behind the scenes",
}


def event_kind(cat):
    """A Roblox event category -> the words that go on the tag.

    One Roblox adds later is un-camelled rather than dropped ("newBiome" becomes
    "New biome"): their labels are all plain English words stuck together, so this
    reads properly, and a tag that silently vanished would be far harder to notice
    than one that reads a little stiffly.
    """
    if not cat:
        return ""
    if cat in EVENT_KIND:
        return EVENT_KIND[cat]
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", cat).strip().lower()
    return words[:1].upper() + words[1:]


def event_notice(e):
    """"announced 3 days before" - how much warning the creators gave.

    Roblox records when the event was created as well as when it runs, and the gap
    is the one genuinely new fact in that pair. Only whole days, and only when it
    looks sane: an event created after it started says nothing worth printing, and
    a gap of years is a date we should not be repeating.
    """
    made = e.get("created")
    if not made:
        return ""
    days = int((e["start"] - made) // 86400)
    if not 1 <= days <= 120:
        return ""
    # Held together with .nb so a phone breaks the line BEFORE the phrase rather
    # than through the middle of it ("announced / 11 days before"). It is about
    # 150px at this size, well inside the narrowest card the site has, so it
    # cannot be the thing that makes a page scroll sideways.
    # The separator travels INSIDE the span, so a line that wraps ends on the date
    # and the next one opens with the dot, rather than leaving a dangling "&middot;"
    # at the end of the first line.
    return (f' <span class="nb">&middot; announced {days} '
            f"day{'s' if days != 1 else ''} before</span>")


def event_item(e, now, cls=""):
    """One event in a list: what kind it is, when it ran, and what the creators said."""
    live = e["start"] <= now <= (e["end"] or e["start"] + 86400)
    soon = e["start"] > now
    klass = cls or ("live" if live else "soon" if soon else "")
    if live:
        label = f"Happening now &middot; ends {when(e['end'] or e['start'])}"
    elif soon:
        label = f"Starts {when(e['start'])}"
    else:
        label = f"{when(e['start'])} &middot; {ago(e['start'], now)}"
    # 900, not 420. Measured across 388 real events: the median description is 177
    # characters and the longest is 975, so this keeps nearly all of them whole
    # while still refusing to let one run away with the page.
    desc = clean_desc(e.get("description") or "")
    if len(desc) > 900:
        desc = desc[:900].rsplit(" ", 1)[0] + "…"
    # .esub makes this its own line. Without it the subtitle and the date ran
    # together with nothing between them - "BOSS FIGHT + WORLD 5Fri 30 Oct".
    sub = (f'<span class="d esub">{html.escape(e["subtitle"])}</span>'
           if says_something(e.get("subtitle") or "") else "")
    kind = event_kind(e.get("category"))
    tag = f'<span class="ptag">{html.escape(kind)}</span>' if kind else ""
    body = f"<p>{html.escape(desc)}</p>" if says_something(desc) else ""
    return (f'<li class="{klass}"><b>{html.escape(e["title"])}</b>{sub}'
            f'{tag}<span class="d">{label}{event_notice(e)}</span>{body}</li>')


# ----------------------------------------------------------------- notifications
# The site used to hand out calendar files - a day-picker that built a .ics, plus one
# file per upcoming event. Both are gone: the only reminders now are app and browser
# notifications (see worker/push.js), which is what the owner asked for.
#
# The .ics files themselves are deleted by prune() on the next build, because it
# still covers the ics/ folder and nothing writes into it any more.
#
# The format is iCalendar (RFC 5545), and it is picky in three ways that lose the
# whole file rather than one line: every line ends CRLF, text escapes \ ; , and
# newlines, and no line may exceed 75 OCTETS. Nearly a quarter of Roblox's event
# titles carry an emoji, which is four octets on its own, so the folding below
# counts bytes rather than characters and never splits a character in half.
def ics_text(value):
    return (str(value).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))



def ics_stamp(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y%m%dT%H%M%SZ")






def calendar_html(name, events, now):
    """Upcoming and currently running events for one game."""
    if events is None:
        return ""
    soon = [e for e in events if (e["end"] or e["start"] + 86400) >= now]
    soon.sort(key=lambda e: e["start"])
    if not soon:
        # The bell belongs here too: "tell me when they announce one" is exactly what
        # somebody reading an empty calendar wants.
        return (f'<div class="card"><h2>Event calendar</h2>'
                f'<span data-bell="events"></span><p class="none">{html.escape(name)} has no '
                f'events planned on Roblox right now. When the creators announce one it will show up here.</p></div>')
    items = "".join(event_item(e, now) for e in soon[:8])
    # The soonest one that has not started yet gets a live countdown. It is the
    # question anybody opening this card is actually asking, and it was previously
    # answerable only by reading a date and doing the arithmetic yourself.
    ahead = [e for e in soon if e["start"] > now]
    nxt = (f'<p class="nextline">Next event in <span class="cd" data-at="{int(ahead[0]["start"])}" '
           f'data-done="moments"></span></p>') if ahead else ""
    return (f'<div class="card"><h2>Event calendar</h2>'
            f'<span data-bell="events"></span>{nxt}'
            f'<p class="mut small">Events the creators have put on the Roblox calendar. Expect these hours to be busy.</p>'
            f'<ul class="evt">{items}</ul></div>')


def event_habits(name, events, now):
    """What this game's creators usually do about events.

    An events page with one event on it was about 108 words - measured across all
    83 of them on 23 Nov 2026, median 128 - which is a page that answers one
    question and then stops. "How often does this game have events", "how much
    warning do you get" and "how long do they last" are the questions people
    actually bring to a calendar, and every one of them is answerable from the
    dates Roblox already gives us.

    Nothing here is on the updates page, so the two do not repeat each other: that
    one lists what happened, this one describes the habit.

    Cautious in the same way update_pattern is. Five gaps before it will name a
    rhythm, four measurements before it will name a length or a notice period, and
    a kind only when the creators really do lean one way. A game that does not
    clear a bar simply has that sentence left out, and a game that clears none
    gets no card at all rather than a card of hedges. Measured across the site:
    64 of the 113 games with an events page can show a rhythm and 67 a notice.
    """
    past = sorted((e for e in (events or []) if (e["end"] or e["start"] + 86400) < now),
                  key=lambda e: e["start"])
    if len(past) < 4:
        return ""
    bits = []

    starts = [e["start"] for e in past]
    # A gap of more than three months is a game that stopped and started again
    # rather than a rhythm, so it is left out of the median instead of dragging it.
    gaps = sorted((b - a) / 86400 for a, b in zip(starts, starts[1:])
                  if 0 < b - a < 90 * 86400)
    if len(gaps) >= 5:
        g = gaps[len(gaps) // 2]
        every = ("about every week" if 6 <= g <= 8 else
                 "about twice a week" if 3 <= g < 6 else
                 "most days" if g < 3 else
                 "about every two weeks" if 12 <= g <= 16 else
                 f"about every {round(g)} days")
        bits.append(f'The creators put on a new event <b>{every}</b>.')

    dur = sorted((e["end"] - e["start"]) / 3600 for e in past
                 if e.get("end") and 0 < e["end"] - e["start"] <= 60 * 86400)
    if len(dur) >= 4:
        h = dur[len(dur) // 2]
        how = (f"about {round(h)} hours" if h < 36 else
               "about a week" if 6 * 24 <= h <= 8 * 24 else
               f"about {round(h / 24)} days")
        bits.append(f'Each one usually runs for <b>{how}</b>.')

    notice = sorted((e["start"] - e["created"]) / 86400 for e in past
                    if e.get("created")
                    and 1 <= (e["start"] - e["created"]) / 86400 <= 120)
    if len(notice) >= 4:
        d = notice[len(notice) // 2]
        when_ = ("about a week before" if 6 <= d <= 8 else
                 "a day or two before" if d < 3 else
                 "about two weeks before" if 12 <= d <= 16 else
                 f"about {round(d)} days before")
        bits.append(f'They normally announce one <b>{when_}</b> it starts.')

    kinds = [event_kind(e.get("category")) for e in past if e.get("category")]
    if len(kinds) >= 4:
        top = max(set(kinds), key=kinds.count)
        share = kinds.count(top) / len(kinds)
        if share >= 0.4:
            word = "Almost all" if share >= 0.8 else "Most" if share >= 0.6 else "Many"
            bits.append(f'{word} of them are the kind Roblox calls '
                        f'<b>{html.escape(top.lower())}</b>.')

    if not bits:
        return ""
    seen = (f'<p class="mut small">We have seen {len(past)} finished '
            f'{"event" if len(past) == 1 else "events"} for {html.escape(name)}, '
            f'the first on {when(past[0]["start"])}. These are what they add up to. '
            f'They are what usually happens, not a promise: the creators can change '
            f'their minds at any time.</p>')
    return (f'<div class="card"><h2>How often does {html.escape(name)} have events?</h2>'
            f'{seen}<ul class="habits">'
            + "".join(f"<li>{b}</li>" for b in bits) + '</ul></div>')


def next_update_line():
    """An empty line PATTERN_JS fills with a countdown, when it can predict one.

    Left empty rather than written out by the builder, because the moment has to be
    shown on the reader's own clock and only the browser knows which that is.
    """
    return '<p class="nextline" id="nextupd"></p>'


def updates_bell():
    """The slot for the Updates bell, filled by PUSH_JS on the updates page."""
    return '<span data-bell="updates"></span>'


def next_update(pattern, now):
    """When the next update is most likely, as a UTC timestamp, or None.

    The same rule the page's countdown uses: the next time the usual weekday (and
    hour, when there is one) comes round. Without an hour it aims at midday, and the
    words that use it then name only the day."""
    if not pattern:
        return None
    d = datetime.fromtimestamp(now, timezone.utc)
    hour = pattern.get("hour") if pattern.get("hour") is not None else 12
    t = d.replace(hour=hour, minute=0, second=0, microsecond=0)
    t += timedelta(days=(pattern["wd"] - d.weekday()) % 7)
    if t.timestamp() <= now:
        t += timedelta(days=7)
    return t.timestamp()


def updates_html(name, events, meta, spikes, now, pattern=None):
    """A game's changelog: finished events (creators use them as one) plus spikes.

    Anything still running or still to come belongs on the calendar instead, so the
    two sections never show the same event twice.

    Worded for what people search (Search Console, Nov 2026): "updates in order",
    "changelog", "update log", "patch notes", "when is the next update". So the
    next update is answered in plain text at the top, and every past update is
    listed numbered from the first, rather than only the latest handful.
    """
    past = [e for e in (events or []) if (e["end"] or e["start"] + 86400) < now]
    past.sort(key=lambda e: -e["start"])
    parts = []
    nxt = next_update(pattern, now)
    if nxt:
        at = (f'{when(nxt)} around {hour12(pattern["hour"])} UTC'
              if pattern.get("hour") is not None else when(nxt))
        parts.append(f'<h3>When is the next {html.escape(name)} update?</h3>'
                     f'<p>Most likely <b>{at}</b>. Its updates usually land on a '
                     f'{DAYS[pattern["wd"]]}'
                     + (f', roughly every {pattern["every"]} days' if pattern.get("every") else '')
                     + f', going by the last {pattern["n"]} updates and busy days. That is a '
                     f'pattern, not an announcement: the creators can always change it.</p>')
    if meta and meta.get("updated"):
        parts.append(f'<p>The creators last changed something in the game <b>{ago(meta["updated"], now)}</b> '
                     f'({when(meta["updated"])}).</p>')
    if past:
        # ONE list, not two. Until the list below carried the creators' own words
        # this section was preceded by "Latest <game> updates", the newest six laid
        # out in full - which is now the same six entries, with the same title,
        # kind, date and description, printed twice on one page a few hundred
        # pixels apart. The list below says everything it said and 141 more, so it
        # is the one that stays, with its newest three already open so the page
        # still starts with something to read rather than a wall of shut rows.
        #
        # Numbered from the first one we know of, so "update 1" stays update 1 as
        # new ones arrive. Newest at the top, because that is what most people want.
        # Each one opens to what the creators actually wrote.
        #
        # It used to be a bare table of number, title and date, which told somebody
        # searching "patch notes" nothing about what had changed. The text was
        # there all along - 87% of the site's 2,913 past updates carry a real
        # description, median 143 characters - but only the newest six were ever
        # shown. Putting it behind a <details> per entry keeps the list as
        # scannable as the table was while getting all of that writing onto the
        # page, where Google reads it as well: the same trick the 168-hour table
        # uses. Measured cost: nothing at all on half the pages (they have six
        # updates or fewer) and 32KB on the heaviest, Adopt Me and Car Crushers 2.
        #
        # An entry with nothing to say is a plain row rather than a <details> that
        # opens on emptiness, so the little triangle always means there is more.
        #
        # The Kind pill is Roblox's own label. Without one a long game's list is
        # unreadable - Adopt Me's 147 are 97 Festivals and 44 New content, the
        # same weekly party announced over and over - and a reader after real new
        # content had to read every title. We print their word and never decide
        # for ourselves what an update was.
        items = []
        opened = 0
        for i, e in enumerate(past):
            kind = event_kind(e.get("category"))
            tag = f'<span class="ptag">{html.escape(kind)}</span>' if kind else ""
            # The date AND how long ago it was, which is what the six-item list
            # above used to give and the table never did: a reader scanning for
            # "is this game still being worked on" should not have to do date
            # arithmetic against today.
            head = (f'<span class="cnum">{len(past) - i}</span>'
                    f'<span class="ctitle">{html.escape(e["title"])}</span>{tag}'
                    f'<span class="cdate">{when(e["start"])} &middot; '
                    f'{ago(e["start"], now)}{event_notice(e)}</span>')
            desc = clean_desc(e.get("description") or "")
            if len(desc) > 900:
                desc = desc[:900].rsplit(" ", 1)[0] + "\u2026"
            body = ""
            if says_something(e.get("subtitle") or ""):
                body += f'<p class="csub">{html.escape(e["subtitle"])}</p>'
            if says_something(desc):
                body += f"<p>{html.escape(desc)}</p>"
            op = " open" if i < 3 else ""
            if op and body:
                opened += 1
            items.append(f'<li><details{op}><summary>{head}</summary>{body}</details></li>'
                         if body else f'<li><div class="cflat">{head}</div></li>')
        kinds = len({event_kind(e.get("category")) for e in past if e.get("category")})
        mix = (f' Roblox sorts them into {kinds} kinds, shown beside each one.'
               if kinds > 1 else '')
        told = sum(1 for e in past if says_something(clean_desc(e.get("description") or ""))
                   or says_something(e.get("subtitle") or ""))
        opens = (f' The newest are open already; press the triangle on any of the '
                 f'other {told - opened} to read what the creators said.'
                 if told > opened > 0 else
                 f' Open any of the {told} with a triangle to read what the creators said.'
                 if told else '')
        parts.append(f'<h3>Every {html.escape(name)} update in order</h3>'
                     f'<p class="mut small">All {len(past)} updates and events the creators '
                     f'have put on Roblox, newest first. Number 1 is the first we know of, from '
                     f'{when(past[-1]["start"])}.{mix}{opens}</p>'
                     f'<ol class="chg">{"".join(items)}</ol>')
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
    return (f'<div class="card"><h2>{html.escape(name)} changelog</h2>'
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


def similar_updates_html(card, cards, latest, now):
    """Other games' changelogs, at the foot of a game's updates page.

    Search Console, Nov 2026: the /updates/ pages are what actually brings people
    to this site - /updates/dandy-s-world alone had 3,356 impressions in 29 days,
    more than six times the homepage - and until now the body of one linked to
    nothing but the game it was already about. Somebody who arrived from "dandy's
    world updates in order" had to go back to Google to read another game's.

    Same category first and closest in size second, which is the ranking the game
    pages' "Similar games" row already uses, so this is somewhere else you might
    go rather than a list of whatever happens to be newest. Only a game we have an
    update to show for is offered, so no tile leads to an empty page, and each one
    says when that game last changed - which is the question somebody on this page
    is asking.
    """
    picks = [c for c in similar(card, cards, n=len(cards)) if latest.get(c["slug"])][:6]
    if len(picks) < 2:
        return ""                         # one lonely suggestion is not worth a heading
    same = sum(1 for c in picks if card["genre"] and c["genre"] == card["genre"])
    note = (f'Other {html.escape(card["genre"].lower())} games of about the same size, '
            f'and when their creators last announced something.'
            if same >= len(picks) - 1 else
            'Games with about as many players, and when their creators last '
            'announced something.')
    return (row_head("Updates for similar games") +
            f'<p class="mut small" style="margin-top:-4px">{note}</p>'
            + grid(picks,
                   href=lambda c: f'/updates/{c["slug"]}',
                   meta=lambda c: f'<span>{ago(latest[c["slug"]], now)}</span>'))


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
/* The sign-in address, carrying the page somebody is on, so Roblox sends them back
   here rather than to the homepage. worker/auth.js checks it is one of our own
   paths before it will redirect there. */
function ptLogin(){return '/auth/login?back='+encodeURIComponent(location.pathname)}
var PTPERSON='__PERSON__';
var PTBELL='__BELL__';
var PTSITE='__SITE__';
var MAXFAVS=200;   /* must match MAX_FAVS in worker/auth.js, or the two drift apart */
function getFavs(){if(PT.favs)return PT.favs;
try{return JSON.parse(localStorage.getItem('pt_favs'))||[]}catch(e){return[]}}
function setFavs(f){f=f.slice(0,MAXFAVS);PT.favs=f;
try{localStorage.setItem('pt_favs',JSON.stringify(f))}catch(e){}
if(PT.name)fetch('/api/favs',{method:'PUT',headers:{'content-type':'application/json'},
body:JSON.stringify({favs:f})}).catch(function(){})}
PT.ready=function(fn){PT.cbs.push(fn);fn()};
/* Coming BACK to a page does not re-run its scripts. The browser keeps the whole
   page alive and hands it back exactly as it was, so a game un-saved on its own
   page was still sitting in the saved section of the page behind it until somebody
   reloaded. PT.again() throws the in-memory list away, so getFavs() reads
   localStorage afresh, then redraws everything that asked to be kept up to date:
   the saved grid on the homepage, the saved rows on the event calendar, the Save
   button itself and the rows on the notifications page.
   pageshow with persisted is the back button. storage is the same thing done in
   another tab, and it fires only in the tabs that did not do it, which is exactly
   the ones holding a stale list. */
PT.again=function(){PT.favs=null;PT.cbs.forEach(function(fn){try{fn()}catch(e){}})};
window.addEventListener('pageshow',function(e){if(e.persisted)PT.again()});
window.addEventListener('storage',function(e){if(!e||!e.key||e.key==='pt_favs')PT.again()});
/* Is this page running as an installed app, and is this an Apple device? Both
   questions are asked in two places - the Install option in the header panel, and
   the notification panel on a game page - so they are answered here rather than
   written twice and left to drift. It is also the only place they can live: this
   block is in the head and CHROME_JS may use nothing else.
   iPadOS reports itself as a Mac, so a Mac with a touch screen is an iPad. */
function ptIOS(){return /iPad|iPhone|iPod/.test(navigator.userAgent)||
(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1)}
function ptInstalled(){try{return (window.matchMedia&&
window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true}
catch(e){return false}}
/* A browser offers to install the site once per page load, and it does so before
   CHROME_JS has run - so the offer has to be caught up here and kept. Calling
   preventDefault stops the browser showing its own bar across the page, which means
   the option in the panel is the only place it is ever offered, rather than a second
   thing appearing over the games. */
PT.prompt=null;
window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();
PT.prompt=e;if(PT.onprompt)try{PT.onprompt()}catch(err){}});
function ptEsc(s){return String(s).replace(/[&<>"]/g,function(c){
return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
/* Signed out, one button that leads to Roblox. Signed in, the person's own
   picture takes that same button's place, and their name and Sign out move into a
   menu under it. Not available at all - no Roblox keys set - and this writes
   nothing, so the empty .acct collapses and the bar reads as though sign-in had
   never existed.
   The bar shows the PICTURE AND NOTHING ELSE (19 Nov 2026, owner's call). It
   carried the name beside it, which made the one control in the bar whose width
   nobody could predict - a long Roblox name ran it to 182px against the 42px it
   is now - and it was the only item up there that was not a neat square. The name
   is not lost: it is the first line of the menu the picture opens, and it is in
   the panel on a phone, where there is no picture in the bar at all.
   alt is empty on purpose: the button's own aria-label carries the name, so a
   screen reader announcing the picture as well would say it twice. */
function ptPaint(){
/* The account, in the panel behind the three lines. Nothing at all when the Roblox
   keys are missing, so .acct:empty collapses and the panel reads as though signing
   in had never existed. */
/* A row with the name on it, and Sign out folded inside until it is asked for -
   the same shape as the menu the name drops on a computer, so the two widths behave
   alike. A plain <details>, so it needs no JavaScript and cannot be torn down by a
   later ptPaint the way a bound handler would be. */
var acct=!PT.available?'':PT.name
?'<details class="apop"><summary class="drow">'
+(PT.pic?'<img class="pfp" src="'+ptEsc(PT.pic)+'" alt="" width="34" height="34">':PTPERSON)
+'<b class="aname">'+ptEsc(PT.name)+'</b></summary>'
+'<i class="asub2">Signed in with Roblox</i>'
+'<form method="POST" action="/auth/logout">'
+'<button class="drow" type="submit">Sign out</button></form></details>'
:'<a class="drow" href="'+ptLogin()+'">'+PTPERSON
+'<span>Sign in with Roblox</span></a>'
/* The same warning as the one beside the other two buttons. It is written out
   here rather than shared because PUSH_JS is not loaded on every page and this
   block is in FAVJS, which is. */
+'<p class="phonetip">If the Roblox app opens instead of the sign-in page, open '
+'roblox.com in your browser and sign in there first, then come back and tap this '
+'again.</p>';
Array.prototype.forEach.call(document.querySelectorAll('.acct'),function(el){
el.innerHTML=acct});
/* The bell, in the bar. Only for somebody signed in: notifications are offered to
   signed-in people only, so for anybody else it would open on an explanation of why
   it is empty, which is not worth a button in the bar. The list inside is left
   empty and filled when it is first opened, so a visitor who never presses it costs
   no extra requests. */
/* A link to a page, not a menu that opens in the bar. There are three switches
   per game and a device to turn on, which is more than a dropdown off the corner
   of a phone screen can hold without becoming its own little application. */
var bell=(PT.available&&PT.name)
?'<a class="iconb" href="/notifications" aria-label="Your notifications">'
+PTBELL+'</a>'
:'';
Array.prototype.forEach.call(document.querySelectorAll('.nots'),function(el){
el.innerHTML=bell});
/* The same two things again, for the other width. The bar pill carries the name and
   opens the panel rather than a menu of its own: everything it would have held -
   the name, Sign out - is already in that panel, and a second menu holding the same
   two things is one more place for them to disagree. */
/* Signed in it is a button that drops its own menu; signed OUT it is a plain link
   to Roblox, in the same place. The panel no longer offers signing in on a computer,
   so this link is the only one there is at that width - see the .dtop .acct rule. */
var pill=!PT.available?''
:PT.name
?'<button class="acctb onlypic" id="acctbar" type="button" aria-controls="amenu" '
+'aria-expanded="false" aria-label="Your account, '+ptEsc(PT.name)+'">'
+(PT.pic?'<img class="pfp" src="'+ptEsc(PT.pic)+'" alt="" width="30" height="30">':PTPERSON)
+'</button>'
:'<a class="acctb" id="acctbar" href="'+ptLogin()+'" '
+'aria-label="Sign in with Roblox">'+PTPERSON
+'<span class="albl">Sign in</span></a>';
Array.prototype.forEach.call(document.querySelectorAll('.acctbar'),function(el){
el.innerHTML=pill});
/* What drops out of that picture, and the ONE place on a computer the name is
   written. It used to be across the button and deliberately not repeated here;
   the button is a bare picture now, so the name moved in rather than vanishing -
   still said once, just in the other half of the same control. */
var amenu=document.getElementById('amenu');
if(amenu)amenu.innerHTML=(PT.available&&PT.name)
?'<i class="asub"><b class="aname">'+ptEsc(PT.name)+'</b>Signed in with Roblox</i>'
+'<form method="POST" action="/auth/logout">'
+'<button class="drow" type="submit">Sign out</button></form>'
:'';
var nrow=(PT.available&&PT.name)
?'<a class="drow" href="/notifications">'+PTBELL+'<span>Notifications</span></a>'
:'';
Array.prototype.forEach.call(document.querySelectorAll('.notsrow'),function(el){
el.innerHTML=nrow});
PT.cbs.forEach(function(fn){try{fn()}catch(e){}})}
fetch('/api/me').then(function(r){return r.json()}).then(function(d){
PT.available=!!d.available;PT.name=d.signedIn?d.name:null;
PT.pic=d.signedIn?(d.pic||null):null;
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

# The account button in the header draws the same person glyph the player counts
# use, so it is dropped in rather than drawn a second time by hand. PERSON quotes
# its attributes with " and holds no ', which is what makes it safe inside the
# single-quoted JavaScript string above.
FAVJS = (FAVJS.replace("__PERSON__", PERSON).replace("__BELL__", ICON_BELL)
         .replace("__SITE__", SITE))

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

/* Which of the three ways in the bar offers is the page being looked at, so that
   one wears the underline. Worked out from the address rather than written into
   each page, because the bar is one piece of markup shared by all 670 of them.
   Plain string tests and no regex: these blocks are ordinary Python strings, so a
   backslash in one is eaten before the browser ever sees it. */
var hp=location.pathname,hs=location.search;
var hseg=hp.substring(hp.lastIndexOf('/')+1).replace('.html','');
/* All EIGHT of them, not the first three (19 Nov 2026). Busy, quiet and popular
   were marked and Growing, Shrinking, Events, Compare and Plan were not, so
   standing on one of those five the bar said nothing about where you were - the
   stylesheet had treated all eight alike from the start and only this knew about
   three. Each of the five is its own page, so the name of the file is the answer;
   busy and quiet are the homepage asked a question, so they come off the query. */
var hkey=hs.indexOf('for=busy')>-1?'busy'
:hs.indexOf('for=quiet')>-1?'quiet'
:(hseg==='popular'||hseg==='growing'||hseg==='shrinking'||hseg==='events'
||hseg==='compare'||hseg==='plan')?hseg:'';
/* Every copy of them: the bar on a computer and the three buttons on the phone's
   homepage. classList.add, not className=, because five of the links in the bar
   also carry "more" - the class that keeps them out of a narrow bar - and
   overwriting it put the one you were on back on screen at widths with no room. */
if(hkey)Array.prototype.forEach.call(document.querySelectorAll('[data-hn]'),
function(a){if(a.getAttribute('data-hn')===hkey)a.classList.add('on')});
/* The bar across the bottom of a phone marks itself the same way. Saved games are
   a block on the homepage rather than a page of their own, so that one lights up
   on the homepage when the address names it. */
var tkey=(hseg==='events')?'events'
:(hseg==='plan')?'plan'
:((hseg===''||hseg==='index')&&location.hash==='#favs')?'favs':'';
if(tkey)Array.prototype.forEach.call(document.querySelectorAll('.tabbar a[data-tb]'),
function(a){if(a.getAttribute('data-tb')===tkey)a.className='tbb on'});

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
mb=document.getElementById('menubtn'),am=document.getElementById('amenu'),
ab=document.getElementById('acctbar');
if(dr)dr.hidden=true;if(sh)sh.hidden=true;if(am)am.hidden=true;
if(mb)mb.setAttribute('aria-expanded','false');
if(ab)ab.setAttribute('aria-expanded','false');shade(false)}
var mb=document.getElementById('menubtn'),dr=document.getElementById('drawer');
if(mb&&dr)mb.onclick=function(e){e.stopPropagation();var show=dr.hidden;shut();
dr.hidden=!show;mb.setAttribute('aria-expanded',show?'true':'false');shade(show);
if(show){placePanel();var a=dr.querySelector('a');if(a)a.focus()}};
/* The name in the bar opens its own small menu under itself (17 Nov 2026). It used
   to open the whole panel, on the grounds that the panel already held the name and
   Sign out - and from 900px up the panel no longer does, so there is nothing left to
   disagree with. Delegated from the document, since ptPaint replaces this button
   every time /api/me answers and a handler put on the button itself would be thrown
   away with the old markup.
   e.target.closest is guarded because on iOS a click that has bubbled this far can
   arrive at a text node, which has no closest. */
var am=document.getElementById('amenu');
/* Put a card under the button it belongs to. Both of these are position:fixed, and
   pinning either to the window edge is wrong on a wide screen: the bar's own band is
   capped - 1200px, narrower again with the ad rails up - so the three-line button
   can sit hundreds of pixels inside the window.
   Measured at 1920px before this existed: 260px adrift. `edge` is which side of the
   card lines up with which side of the button. */
function drop(el,btn,edge){
if(!el||!btn)return;
var r=btn.getBoundingClientRect(),W=document.documentElement.clientWidth;
var gap=W<900?14:16;
/* Sideways from the button, but DOWN from the bar. The button is inset inside the
   bar by its padding, so hanging the card off the button put its top 5px above the
   bar's own bottom border - and the card is above the bar in the stacking order, so
   it drew over it. */
var hdr=document.querySelector('.hdr');
var below=(hdr?hdr.getBoundingClientRect().bottom:r.bottom)+(W<900?6:7);
el.style.top=Math.round(below)+'px';
var w=el.offsetWidth||240;
var x=edge==='right'?r.right-w:r.left;
/* Never off either edge, whatever a long display name does to the pill. */
x=Math.min(x,W-w-gap);
el.style.left=Math.round(Math.max(gap,x))+'px';
el.style.right='auto'}
/* Right edge to right edge, like the panel off the three lines. It used to hang
   from the button's LEFT edge, which was fine while the button was a 119px pill
   and is not now it is a 42px picture: a 218px card hung off the left of it ran
   out past the three-line button and was then shoved back by the keep-it-on-screen
   clamp, so it lined up with nothing at all. */
function placeMenu(){drop(am,document.getElementById('acctbar'),'right')}
function placePanel(){drop(dr,document.getElementById('menubtn'),'right')}
document.addEventListener('click',function(e){
var hit=e.target.closest&&e.target.closest('#acctbar');
/* Signed out the pill is a link to Roblox, not a button, and the menu is empty:
   intercepting it would swallow the click and open a blank card. */
if(!hit||hit.tagName!=='BUTTON')return;
e.stopPropagation();
if(!am)return;
var show=am.hidden;shut();
am.hidden=!show;
var btn=document.getElementById('acctbar');
if(btn)btn.setAttribute('aria-expanded',show?'true':'false');
if(show){placeMenu();shade(true);
var f=am.querySelector('button,a');if(f)f.focus()}});
/* A card pinned to the viewport has to follow the thing it points at. The bar is
   sticky, so its box only moves until the page has scrolled past the top of it. */
window.addEventListener('resize',function(){
if((am&&!am.hidden)||(dr&&!dr.hidden))shut()});
window.addEventListener('scroll',function(){
if(am&&!am.hidden)placeMenu();
if(dr&&!dr.hidden)placePanel()},{passive:true});

/* Search. The list of games is only fetched the first time it is opened. */
var sheet=document.getElementById('sheet'),GAMES=null;
if(sheet){
var q=document.getElementById('q'),qout=document.getElementById('qout');
function draw(){
var t=q.value.trim().toLowerCase().replace(/['’]/g,'');
if(!GAMES){qout.innerHTML='<p>Loading the list of games&hellip;</p>';return}
var hits=GAMES.filter(function(g){return (g.k||g.n.toLowerCase()).indexOf(t)>-1}).slice(0,25);
qout.innerHTML=hits.length?hits.map(function(g){
return '<a href="/game/'+ptEsc(g.s)+'">'+(g.i?'<img src="'+ptEsc(g.i)+
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

/* The account menu, under the picture in the bar. ptPaint() rewrites that markup
   whenever /api/me answers, which can happen after this script has run and happens
   again on every repaint, so the button is reached by delegation from the document
   rather than held in a variable: a handler put on the button itself would be
   thrown away with the old markup and the menu would quietly stop opening.
   e.target.closest is guarded because on iOS a click that has bubbled this far can
   arrive at a text node, which has no closest and would throw - the same thing that
   once stopped the calendar links working. */
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
return '<a href="/game/'+ptEsc(g.s)+'" title="'+ptEsc(g.n)+'">'+pic(g)+'<span class="nm">'+ptEsc(g.n)+'</span></a>'}).join(''):
'<p>No games opened yet</p>')+'<a class="all" href="/">Browse all games</a>';
/* Below 900px the list keeps its own width (see .gpick .gmenu), but it hangs from a
   box that starts about 145px in, so at 252px or more it ran off the right of a
   390px phone. It is held inside the screen here, because how far in the box
   starts depends on the logo and is not a number CSS can know. */
function fit(){if(!window.matchMedia||!matchMedia('(max-width:899px)').matches){
menu.style.maxWidth=menu.style.minWidth='';return}
var room=document.documentElement.clientWidth-box.getBoundingClientRect().left-10;
menu.style.maxWidth=room+'px';menu.style.minWidth=Math.min(252,room)+'px'}
function open(on){if(on)fit();menu.hidden=!on;btn.setAttribute('aria-expanded',on?'true':'false')}
btn.onclick=function(e){e.stopPropagation();open(menu.hidden)};
document.addEventListener('click',function(e){if(!box.contains(e.target))open(false)});
document.addEventListener('keydown',function(e){if(e.key==='Escape')open(false)});
})();

/* The Install app parts. Its own function because the block above gives up early on
   any page without the game switcher, and these are on other pages.

   Two things, and neither is the old panel row:
     [data-install]     a real install button, shown ONLY where the browser has
                        actually offered. It lives on /install, which explains the
                        steps in words for every browser that never offers - so
                        there is no longer any need to hide instructions behind a
                        toggle, and nothing to show where nothing can be done.
     [data-installlink] the link to /install from a game page, hidden once the site
                        IS installed, because there is nothing left to explain. */
(function(){
var btns=document.querySelectorAll('[data-install]');
var links=document.querySelectorAll('[data-installlink]');
if(!btns.length&&!links.length)return;
function paint(){
var inst=ptInstalled();
Array.prototype.forEach.call(btns,function(b){b.hidden=inst||!PT.prompt});
Array.prototype.forEach.call(links,function(a){a.hidden=inst})}
/* Called again if the browser makes its offer after this has already run. */
PT.onprompt=paint;
paint();
/* Delegated, because paint may hide and show these at any time and because a tap on
   iOS can arrive at a text node, which has no closest. */
document.addEventListener('click',function(e){
var b=e.target.closest&&e.target.closest('[data-install]');
if(!b||!PT.prompt)return;
/* An offer can only be used once, so it is taken rather than copied. */
var offer=PT.prompt;PT.prompt=null;
offer.prompt();
if(offer.userChoice)offer.userChoice.then(paint,paint)});
/* Installed while the page was open: there is nothing left to offer or explain. */
window.addEventListener('appinstalled',function(){PT.prompt=null;paint()});
/* On /install, open the section for the device being used. They are all shut in the
   markup, so somebody with no JavaScript gets three closed drawers with readable
   headings rather than one opened at random. */
var devs=document.querySelectorAll('.howto[data-dev]');
if(devs.length){
var want=ptIOS()?'ios'
:/Android/i.test(navigator.userAgent)?'android':'desktop';
Array.prototype.forEach.call(devs,function(d){
if(d.dataset.dev===want)d.open=true})}
})();"""

# Shared by every page that draws a week of player counts.
SHARED_JS = """var DAY=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
/* A live countdown on anything carrying data-at, a moment in unix seconds. Used by
   the next-event and next-update lines; the quiet-window countdown on a game page
   predates it and keeps its own ticker, because that one also has to work out WHICH
   hour it is aiming at every five minutes.
   The elements are looked up on every tick rather than once, because the next-update
   one does not exist until PATTERN_JS has worked out when that is. */
function ptCountdowns(){ /* see the note above */
function gap(s){
if(s<=0)return null;
var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),x=Math.floor(s%60);
if(d)return d+'d '+h+'h '+m+'m';
if(h)return h+'h '+m+'m '+(x<10?'0':'')+x+'s';
return m+'m '+(x<10?'0':'')+x+'s'}
function tick(){
Array.prototype.forEach.call(document.querySelectorAll('[data-at]'),function(el){
var left=gap(+el.dataset.at-Math.floor(Date.now()/1000));
el.textContent=left?(el.dataset.pre||'')+left:(el.dataset.done||'happening now')})}
tick();setInterval(tick,1000)}
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
'" r="4" fill="var(--'+hue+')" stroke="var(--ink)" stroke-width="1.5" '+
'vector-effect="non-scaling-stroke"/>'})});
return '<svg class="graph" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+label+'" '+
'tabindex="0">'+
'<defs><linearGradient id="wash" x1="0" y1="0" x2="0" y2="1">'+
'<stop offset="0" stop-color="var(--'+hue+')" stop-opacity=".42"/>'+
'<stop offset="1" stop-color="var(--'+hue+')" stop-opacity=".02"/></linearGradient></defs>'+
'<line x1="'+P+'" y1="'+bot+'" x2="'+(W-P)+'" y2="'+bot+'" stroke="var(--line)" stroke-width="1.5"/>'+
/* What the top and the bottom of this box stand for. The axis runs from the week's
   quietest hour to its busiest rather than from zero, so without these two numbers
   the shape of a day claims a bigger swing than it has. They are on the graph
   because a sentence under it was one more thing to read. */
'<text class="gsc" x="'+(W-P)+'" y="'+(top+12)+'" text-anchor="end">'+
Math.round(R.c).toLocaleString()+'</text>'+
/* The floor goes UNDER the baseline, not above it: a quiet late evening drops the
   line into that corner and the two sat on top of each other. There is room,
   because the box is 26px taller than the axis it draws. */
'<text class="gsc" x="'+(W-P)+'" y="'+(bot+17)+'" text-anchor="end">'+
Math.round(R.f).toLocaleString()+'</text>'+
'<path d="'+wash+'" fill="url(#wash)"/>'+
'<path d="'+line+'" fill="none" stroke="var(--'+hue+')" stroke-width="2.5" '+
'vector-effect="non-scaling-stroke" '+
'stroke-linejoin="round" stroke-linecap="round"/>'+dots+
'<g class="cursor" opacity="0"><line y1="'+top+'" y2="'+bot+'" stroke="var(--ink)" '+
'stroke-width="1.5" stroke-dasharray="4 4"/><circle r="6.5" fill="var(--ink)" '+
'stroke="var(--'+hue+')" stroke-width="2.5" class="lockdot"/></g></svg>'}

/* Lets people drag or click along a graph to read off any hour. Works with a mouse,
   a finger, and the arrow keys, and falls back to doing nothing if the browser
   cannot measure the svg. The readout element is optional. */
function graphCursor(svg,out,vals,R){
if(!svg)return;
/* H must match dayGraph's, or the crosshair floats off the line. */
var W=720,H=320,P=14,top=16,bot=H-26,span=bot-top,rng=(R.c-R.f)||1;
var g=svg.querySelector('.cursor'),line=g.querySelector('line'),dot=g.querySelector('circle');
var at=-1;
/* What the readout says when nobody is dragging. It used to say nothing, which
   left a hole under the graph that read as something failing to load rather than
   as a space waiting to be used. The latest hour we have a reading for is the one
   worth resting on. */
var last=-1;
for(var li=23;li>=0;li--){if(vals[li]!=null){last=li;break}}
function rest(){
if(!out)return;
out.innerHTML=last<0?'':'<b>'+fmt(last)+'</b> &middot; about <b>'+
vals[last].toLocaleString()+'</b> players'}
var gLastMouse=null;
function show(i){
if(i<0||i>23||vals[i]==null){g.setAttribute('opacity','0');at=-1;rest();tipHide();return}
at=i;
var x=P+i*(W-P*2)/23,y=bot-((vals[i]-R.f)/rng)*span;
line.setAttribute('x1',x);line.setAttribute('x2',x);
dot.setAttribute('cx',x);dot.setAttribute('cy',y);
g.setAttribute('opacity','1');
var txt='<b>'+fmt(i)+'</b> &middot; about <b>'+vals[i].toLocaleString()+'</b> players';
if(out)out.innerHTML=txt;
if(gLastMouse)tipShow(txt,gLastMouse[0],gLastMouse[1],svg)}
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
svg.addEventListener('mousedown',function(e){gLastMouse=[e.clientX,e.clientY];
down=true;move(e)});
svg.addEventListener('mousemove',function(e){gLastMouse=[e.clientX,e.clientY];
if(down||e.buttons===0)move(e)});
window.addEventListener('mouseup',function(){down=false});
svg.addEventListener('mouseleave',function(){gLastMouse=null;tipHide();
if(!down)show(-1)});
svg.addEventListener('touchstart',move,{passive:false});
svg.addEventListener('touchmove',move,{passive:false});
svg.addEventListener('keydown',function(e){
if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();
var i=at<0?0:at+(e.key==='ArrowRight'?1:-1);
while(i>=0&&i<=23&&vals[i]==null)i+=(e.key==='ArrowRight'?1:-1);
if(i>=0&&i<=23)show(i)}
else if(e.key==='Escape')show(-1)});
/* The resting state has to be written once at the start too, not only when a
   drag ends: show() is never called on load, so without this the line under the
   graph sat empty until somebody had hovered over it and come away again. */
rest();
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
return ss+'s'}
/* The box that follows the pointer on a computer, in place of the line of text
   under the chart. One box for every chart on the page: it is moved and refilled
   rather than made again, so a page with four charts still has one of them.
   It is only ever shown for a mouse. A finger covers the thing it is pointing at,
   so on a touch screen the readout under the chart is still the answer - which is
   why that line is hidden by CSS at 900px and not deleted. */
var chtip=null;
function tipEl(){
if(!chtip){chtip=document.createElement('div');chtip.className='chtip';
chtip.setAttribute('aria-hidden','true');document.body.appendChild(chtip)}
return chtip}
/* Sits to the right of the pointer, and flips to the LEFT of it once there is not
   room on the right - so near the right edge of the screen it is never cut off.
   It is measured parked at the top left, because a fixed box near the right edge
   is squeezed by the edge itself and would report itself narrower than it is.
   It used to be capped at 260px with nowrap, which let a long readout spill out of
   the box: the box was measured at 260 while the words ran on past it, so the flip
   came too late and the end of the line was cut off. The window is measured
   without its scrollbar (clientWidth), which innerWidth includes. */
/* box is the chart being read. Once the pointer is over its RIGHT HALF the box
   goes on the left of the pointer (owner's call, 20 Nov 2026): flipping only at
   the edge of the screen never happened on a wide monitor, where the chart ends
   long before the screen does, and the box then sat over the right-hand end of
   the line - the part being read. */
function tipShow(html,cx,cy,box){
var t=tipEl();t.innerHTML=html;t.style.left='0px';t.style.top='0px';t.className='chtip on';
var de=document.documentElement,vw=de.clientWidth,vh=de.clientHeight;
var w=t.offsetWidth,h=t.offsetHeight,pad=14,edge=8;
var r=box&&box.getBoundingClientRect?box.getBoundingClientRect():null;
var left=r&&r.width?cx>r.left+r.width/2:false;
var x=left?cx-w-pad:cx+pad,y=cy-h-pad;
if(x+w>vw-edge)x=cx-w-pad;
if(x<edge)x=edge;
if(y<edge)y=cy+pad;
if(y+h>vh-edge)y=vh-h-edge;
t.style.left=x+'px';t.style.top=y+'px'}
function tipHide(){if(chtip)chtip.className='chtip'}

/* Makes a chart drawn at build time draggable, the way graphCursor does for the
   hourly graph: drag, hover, tap, touch-drag sideways, or the arrow keys. The
   positions come ready-made from scrub() in build_site.py as percentages of the
   box, so nothing here has to repeat the chart's own maths. A sideways drag reads
   the chart and an up-down one still scrolls the page (touch-action pan-y). */
function scrubChart(el){
var P;try{P=JSON.parse(el.getAttribute('data-scrub'))}catch(e){return}
if(!P||!P.length)return;
var ln=el.querySelector('.sline'),dots=el.querySelectorAll('.sdot'),
out=el.nextElementSibling,at=-1,down=false;
/* The same rule as the hourly graph: at rest this says the most recent point
   rather than nothing, so the line under the chart is never an unexplained gap. */
var lastMouse=null;
function rest(){if(out)out.innerHTML=P[P.length-1][2];tipHide()}
function show(i){
if(i<0||i>=P.length){el.classList.remove('on');ln.hidden=true;at=-1;rest();return}
at=i;var p=P[i];ln.style.left=p[0]+'%';ln.hidden=false;
for(var k=0;k<dots.length;k++){dots[k].style.left=p[0]+'%';dots[k].style.top=p[1][k]+'%'}
el.classList.add('on');if(out)out.innerHTML=p[2];
if(lastMouse)tipShow(p[2],lastMouse[0],lastMouse[1],el)}
function fromX(cx){var r=el.getBoundingClientRect();if(!r.width)return -1;
return Math.max(0,Math.min(P.length-1,Math.round((cx-r.left)/r.width*(P.length-1))))}
el.addEventListener('pointerdown',function(e){down=true;
lastMouse=e.pointerType==='mouse'?[e.clientX,e.clientY]:null;show(fromX(e.clientX))});
el.addEventListener('pointermove',function(e){
lastMouse=e.pointerType==='mouse'?[e.clientX,e.clientY]:null;
if(down||e.pointerType==='mouse')show(fromX(e.clientX))});
window.addEventListener('pointerup',function(){down=false});
el.addEventListener('pointercancel',function(){down=false});
el.addEventListener('pointerleave',function(e){lastMouse=null;tipHide();
if(e.pointerType==='mouse'&&!down)show(-1)});
el.addEventListener('keydown',function(e){
if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();
show(at<0?(e.key==='ArrowRight'?0:P.length-1):
Math.max(0,Math.min(P.length-1,at+(e.key==='ArrowRight'?1:-1))))}
else if(e.key==='Escape')show(-1)});
rest()}
"""

# Writes the "updates usually arrive on a Friday around 2 PM" line. The page that
# uses it defines P first, so the same code serves any game.
PATTERN_JS = """
/* When the next update is predicted to land, as a live countdown.
   P.wd and P.hour are UTC, so the moment is worked out in UTC and the browser shows
   it in local time by itself - the same rule every other time on this site follows.
   Only drawn when an hour is known: a prediction of "some time on Friday" is not
   something to count seconds down to, and saying so would be pretending to a
   precision the data does not have. */
if(P&&P.hour!=null&&$('nextupd')){
var now=new Date();
var at=Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate(),P.hour,0,0);
var want=(P.wd+1)%7;
at+=((want-new Date(at).getUTCDay()+7)%7)*86400000;
if(at<=now.getTime())at+=7*86400000;
$('nextupd').innerHTML='Next update expected in <span class="cd" data-at="'+
Math.floor(at/1000)+'" data-done="any time now"></span>';}
if(P&&$('pattern')){var pd=P.wd,ph=P.hour,every=P.every?
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
/* The axis does not start at zero, and that still has to be said or the shape
   overstates the swing - it is said ON the graph now, as the two numbers its top
   and bottom stand for, rather than as a sentence underneath it. */
$('dtxt').textContent=lo?'On '+DAY[d]+' it is quietest around '+fmt(lo[0])+' and busiest around '+fmt(hi[0])+
'.':'No player counts for this day yet.'}
DAY.forEach(function(n,i){var b=document.createElement('button');b.textContent=n.slice(0,3);
b.setAttribute('aria-label',n);b.onclick=function(){show(i)};$('days').appendChild(b)});

/* The whole week */
var g='<div></div>';['12 AM','6 AM','12 PM','6 PM'].forEach(function(t){
g+='<span style="grid-column:span 6">'+t+'</span>'});
for(var d=0;d<7;d++){g+='<div>'+DAY[d].slice(0,3)+'</div>';
for(var h=0;h<24;h++){var v=L[d][h];
g+='<div class="c'+(d==nd&&h==nh?' now':'')+'" data-d="'+d+'" data-h="'+h+'" title="'+
DAY[d]+' '+fmt(h)+': about '+(v||0).toLocaleString()+' players" style="background:'+
(v==null?'transparent':'var(--l'+B.level(v)+')')+'"></div>'}}
$('hm').innerHTML=g;show(nd);

/* A square says what it is worth when it is pointed at or pressed. The title
   attribute said the same thing, but a tooltip takes a second of hovering, never
   appears on a phone at all, and cannot be read out - so on a touch screen the
   whole grid was a picture with no numbers in it. Hover follows the pointer and a
   tap holds, which is why the selected one keeps its ring. */
var hmo=$('hmout'),hmSel=null;
function hmText(c){
var d=+c.dataset.d,h=+c.dataset.h,v=L[d][h];
return v==null
?'<b>'+DAY[d]+' '+fmt(h)+'</b> &middot; no readings for this hour yet'
:'<b>'+DAY[d]+' '+fmt(h)+'</b> &middot; about <b>'+v.toLocaleString()+'</b> players'}
/* The same answer in two places, for the same reason the graphs do it: on a computer
   it rides beside the pointer, and on a touch screen it stays in the line under the
   grid, because a finger covers the square it is pointing at. The line is hidden by
   CSS from 900px up rather than deleted - see .readout.chartout. */
function hmSay(c,e){
var txt=hmText(c);hmo.innerHTML=txt;
if(e&&e.pointerType==='mouse')tipShow(txt,e.clientX,e.clientY,$('hm'))}
function hmPick(c){
if(hmSel)hmSel.classList.remove('sel');
hmSel=c;c.classList.add('sel');hmSay(c)}
$('hm').addEventListener('pointerover',function(e){
var c=e.target&&e.target.closest&&e.target.closest('.c[data-d]');
if(c&&e.pointerType==='mouse')hmSay(c,e)});
/* Following the pointer, not just appearing once: the squares are 26px apart, so
   moving along a day without this left the box behind on the first one. */
$('hm').addEventListener('pointermove',function(e){
if(e.pointerType!=='mouse')return;
var c=e.target&&e.target.closest&&e.target.closest('.c[data-d]');
if(c)hmSay(c,e);else tipHide()});
$('hm').addEventListener('pointerleave',function(e){
if(e.pointerType!=='mouse')return;tipHide();
hmSel?hmSay(hmSel):hmo.textContent='Pick a box to see how many play then.'});
$('hm').addEventListener('click',function(e){
var c=e.target&&e.target.closest&&e.target.closest('.c[data-d]');
if(c)hmPick(c)});
Array.prototype.forEach.call(document.querySelectorAll('[data-scrub]'),scrubChart);
(function(){var fl=$('facts'),mb=document.querySelector('.morestats');if(!fl||!mb)return;
fl.classList.add('fold');mb.onclick=function(){var o=fl.classList.toggle('open');
mb.setAttribute('aria-expanded',o);mb.textContent=o?'Fewer stats':'More stats'}})();"""

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
/* Set by the Busy now / Quiet now links in the bar. Anything else is ignored, so
   a made-up address cannot put the page into a state it has no button for. */
var want=(function(){try{var m=/[?&]for=(busy|quiet)/.exec(location.search);
return m?m[1]:''}catch(e){return ''}})(),term='';
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
   nothing is quiet and at 5am nothing is busy.
   Both branches are gated on `want`: band.relaxed is worked out whether or not
   anybody has asked for busy or quiet, so without that gate the plain homepage
   announced "No game is properly busy right now" to somebody who had not asked
   about busy and was only looking at the list. */
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
else if(want&&band.relaxed){
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
var s=$('s');if(s)s.oninput=function(){term=s.value.trim().toLowerCase().replace(/['’]/g,'');refresh()};

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

# The saved-games block at the top of the event calendar. Copies of the rows that
# are already on the page rather than a second list built from scratch, so the two
# can never disagree about when something starts.
#
# PT.ready runs this now AND again once /api/me has answered, which is what makes a
# signed-in person's games appear without a reload: their list arrives from the
# server a moment after the page does.
MYEVTS_JS = """<script>(function(){
var box=document.getElementById('myevts');if(!box)return;
var ul=box.querySelector('ul');
function draw(){
var favs=getFavs(),out=[];
Array.prototype.forEach.call(document.querySelectorAll('.evt li[data-s]'),function(li){
if(li.closest('#myevts'))return;
if(favs.indexOf(li.getAttribute('data-s'))>-1)out.push(li.cloneNode(true))});
ul.innerHTML='';
out.forEach(function(li){ul.appendChild(li)});
box.hidden=!out.length}
PT.ready(draw)})();</script>"""


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
/* The bell is for whichever game is chosen, and it has to be told each time that
   changes. It is drawn by PUSH_JS, which may not have answered the server yet; it
   redraws itself when it does. */
var bp=document.querySelector('#planbell [data-bell]');
if(bp){bp.setAttribute('data-s',g.s);if(PT.bells)PT.bells()}
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
'<p><a class="btn" href="/game/'+esc(g.s)+'">See '+esc(g.n)+'\\u2019s whole week</a></p>'+
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


def anchor(block, sid):
    """Gives a section's own card an id, so the "On this page" row can link to it.

    Runs after span(), which is why it keys on the opening tag rather than on the
    class list. A section that decided it had nothing to say stays empty, and
    jump_html() then offers no link to it either."""
    return block.replace("<div ", f'<div id="{sid}" ', 1) if block else ""


def side_page(c, slug_folder, h1, intro, body, play, trail, extra_schema=None,
              noindex=False, modified="", tail="", have=None):
    """One of a game's sections, as a page of its own.

    Game updates has worked this way for a while and the other three now match it.
    The reason is search: a page about one thing, with that thing in its title, its
    heading and its address, is what somebody typing "blox fruits game passes" is
    looking for - and on the game page those sections were three cards a long way
    down a long page, competing with everything above them.

    The shell is shared so the four of them cannot drift into four slightly
    different-looking pages: the same heading panel, the same way back, the same
    wording for the link to the game itself.
    """
    name = c["name"]
    s_ = c["slug"]
    return page(
        h1[0], (f'<div class="ghead rise">{thumb(name, c["icon"], icon_alt(name), eager=True)}'
                f'<div><h1>{html.escape(h1[1])}</h1>'
                f'<p class="mut">{intro}</p>'
                f'<div class="actions">{play}<span data-bell="all"></span>'
                f'<button class="fav" id="fav" data-s="{s_}" aria-pressed="false">'
                f'&#9734; Save</button></div>'
                f'{game_tabs(s_, have or {}, slug_folder)}</div></div>'
                + body
                + f'<p><a href="/game/{s_}">&larr; Back to {html.escape(name)}</a></p>'),
        h1[2], wide=True, banner=c["banner"], tail=tail,
        canon=f"/{slug_folder}/{s_}", image=c["banner"] or c["icon"] or "",
        trail=trail + [(f"{name} player count", f"/game/{s_}"), (h1[3], f"/{slug_folder}/{s_}")],
        schema=extra_schema, noindex=noindex, modified=modified)


# The order is the order they are offered in, and "Overview" is the game's own page.
SIDE_TABS = (("updates", "Updates"), ("events", "Events"),
             ("questions", "Questions"), ("passes", "Costs"))


def game_tabs(s_, have, current=""):
    """The row of tabs across a game's five pages, the one you are on underlined.

    It replaced a row of buttons that only existed on the game page itself, so the
    four side pages could be reached from it and not from each other - and getting
    back meant finding a small arrow link. Every one of the five now carries this
    same row, so any page is one tap from any other.

    `current` is the folder of the page being drawn, or "" for the game page.
    Only the sections that exist are offered, which is the rule jump_html() followed:
    a game whose creators have announced nothing must not be given a tab to a page
    saying so. One tab on its own is not a row of tabs, so nothing is drawn.
    """
    tabs = [("", "Overview")] + [(f, label) for f, label in SIDE_TABS if have.get(f)]
    if len(tabs) < 2:
        return ""
    out = []
    for folder, label in tabs:
        on = folder == current
        href = f"/game/{s_}" if not folder else f"/{folder}/{s_}"
        out.append(f'<a class="gtab{" on" if on else ""}" href="{href}"'
                   + (' aria-current="page"' if on else "")
                   + f">{label}</a>")
    return f'<nav class="gtabs" aria-label="This game">{"".join(out)}</nav>'


def jump_html(items):
    """The jump links that sit in the row of buttons under the game's heading.

    They look and behave like the Game updates and Save buttons beside them, which
    is the point: a visitor arriving from Google sees one row of places to go, not
    a row of buttons and a separate strip of links. Only the sections this page
    really has are listed - a game whose creators have announced no events would
    otherwise offer a link to an id that is not on the page. Plain anchors and no
    JavaScript, so they work before the page has finished loading, and Google can
    follow them to offer the same sections under our own search result."""
    return "".join(f'<a class="fav" href="#{i}">{ic} {html.escape(t)}</a>'
                   for i, ic, t in items)


# The order here is the order a visitor reads in, and the grid never reorders it.
# It is also the order Google reads, and Google indexes the phone layout, where every
# card is full width and simply follows the one before. So the HTML runs from what
# people search for most to least, going by Search Console (Nov 2026): the player
# count itself (right now, peak, lowest, visits, likes), when it is busiest, the
# hourly graph, "is it dead", then the day-by-day graph, and planning last. The
# hourly graph sits above the day-by-day one (19 Nov 2026, owner's call): somebody
# asking for a player count wants today, and the hourly graph opens on today and
# answers "how busy around now"; three weeks of daily points answer a later question.
# On a computer the numbers sit alone in the left column and the next three are
# stacked in a .lstack beside them; measured with real data the two columns come out
# within about 40px of each other, where pairing the numbers with "when is it busiest"
# left a 350px hole under the graphs.
GAME = """<div class="ghead rise">__ICON__<div><h1>__NAME__ player count and best times to play</h1>
<p class="mut">__LEAD__</p>__CAT__
<div class="actions">__PLAY__<span data-bell="all"></span>
<button class="fav" id="fav" data-s="__SLUG__" aria-pressed="false">&#9734; Save</button>
</div>__GTABS__</div></div>
__ABOUT__
<div class="bento">
<div id="stats" class="sp5 card rise2"><h2>__NAME__ player count stats</h2>__FACTS__</div>
<div class="sp7 lstack">
<div id="answer" class="card ans rise2"><h2>When is __NAME__ busiest?</h2><p id="now"></p><p id="best">__BEST__</p>
<p id="quiet">__QUIET__</p>__SWING__</div>
<div id="byhour" class="card"><h2>__NAME__ player numbers by hour</h2><div class="days" id="days"></div>
<p id="dtxt" class="mut small"></p><div class="bars" id="bars"></div>
<div class="axis"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span></div>
<p class="readout" id="readout"></p></div>
<div id="dead" class="card rise3"><h2>Is __NAME__ dead?</h2>
__SPARK__<div class="verdict">
<span class="vbadge" style="background:__VCOL__">__VLABEL__</span><p style="margin:0;flex:1 1 240px">__VTEXT__</p></div></div>
</div>
__HISTORY__
<div id="session" class="__SESSSPAN__ card rise3"><h2>Plan my session</h2>
<div class="planpick">
<div class="days" id="planbtns"><button data-m="quiet" aria-pressed="true">Quiet</button>
<button data-m="busy" aria-pressed="false">Busy</button></div></div>
<div id="cdw" hidden><span class="mut small" id="cdlab"></span><span class="cd" id="cd"></span></div>
<p id="plantxt"></p>
<span data-bell="plan"></span>
__NOTIFY__</div>
<div id="week" class="card"><h2>__NAME__ busiest hours, the whole week</h2><div class="wrap"><div class="hm" id="hm"></div></div>
<p class="readout chartout" id="hmout">Pick a box to see how many play then.</p>
<div class="legend">Quiet <i style="background:var(--l1)"></i><i style="background:var(--l2)"></i>
<i style="background:var(--l3)"></i><i style="background:var(--l4)"></i><i style="background:var(--l5)"></i> Busy</div>
<p class="mut small">The outlined square is right now.</p>
__HOURS__</div>
</div>
__SIMILAR__
<p><a href="/">&larr; All Roblox player counts</a> &middot; <a href="/plan?g=__SLUG__">Plan a session</a>
&middot; <a href="/busiest-hours">When is Roblox busiest?</a></p>
<script>window.PT_GAME=__GAMEINFO__;</script>
<script>__SHARED__</script><script>__JS__</script><script>__FAVJS__</script>
<script>__PUSHJS__</script>"""


# The notification controls. Written into every game page but hidden, because a
# built page is the same file for everyone and only the worker knows whether anybody
# is signed in - the same reason the account button in the header starts empty.
# ptNotify() in PUSH_JS fills it in and unhides it, and on most visits it stays
# hidden and the card looks exactly as it did before this feature existed.
NOTIFY_HTML = """<div class="notif" id="notif" hidden></div>"""


# The browser half of notifications. Only on game pages, since that is the only
# place there is a game to follow.
#
# Three things here are not obvious and all three were deliberate:
#  - It asks the worker what is possible (/api/push/state) rather than deciding for
#    itself, because whether notifications exist at all depends on secrets that only
#    the worker can see.
#  - Permission is requested from the click, never on load. A browser only grants it
#    in response to a real gesture, and a site that asks the moment you arrive is the
#    reason browsers now hide the prompt entirely.
#  - On an iPhone or iPad it explains Add to Home Screen instead of offering a button
#    that cannot work. Apple only allows notifications for an installed site, so the
#    button would fail silently and look broken.
PUSH_JS = """(function(){
var gameBox=document.getElementById('notif');
var pageBox=document.getElementById('notifpage');
/* Three kinds of page use this: a game page (#notif), the notifications page
   (#notifpage) and the updates page, which has neither and only a bell. Leaving the
   bells out of this test is what made the updates page draw an empty slot. */
if(!gameBox&&!pageBox&&!document.querySelector('[data-bell]'))return;
var slug=window.PT_GAME?PT_GAME.s:null;
var S=null,names=null,busy=false,note='',deviceReady=false,told=false;

function urlKey(text){
var pad=text.replace(/-/g,'+').replace(/_/g,'/');
pad=pad+'='.repeat((4-pad.length%4)%4);
var raw=atob(pad),out=new Uint8Array(raw.length);
for(var i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out}

function post(where,data){return fetch('/api/push/'+where,{method:'POST',
headers:{'content-type':'application/json'},body:JSON.stringify(data||{})})
.then(function(r){return r.json().then(function(j){
if(!r.ok)throw new Error(j&&j.error||'that did not work');return j})})}

var ios=ptIOS();
function usable(){return 'serviceWorker' in navigator&&'PushManager' in window
&&'Notification' in window&&!(ios&&!ptInstalled())}

function watchFor(s){for(var i=0;i<((S&&S.watching)||[]).length;i++)
if(S.watching[i].slug===s)return S.watching[i];return null}

/* Turning this device on. Safe to call again: an existing subscription is reused and
   the server upserts, so every switch does not have to know whether it is the first.
   Asked for only when a switch is actually pressed - a browser only grants permission
   in response to a real gesture, and a site that asks the moment you arrive is the
   reason browsers now bury the prompt. */
/* Said once, the first time somebody switches something on without having installed
   the site. On an iPhone it is not advice but the whole story - Apple allows no
   notifications at all to a site in a tab - and drawGame() stops before the switches
   there for that reason. Everywhere else it is a real improvement rather than a
   requirement, so it is a note beside the switch and not a wall in front of it. */
function installNote(){
if(ptInstalled())return '';
return 'Notifications work best with ' + PTSITE + ' installed on your device. ';
}

/* Apple is the one platform where a browser tab cannot do this at all, so it is the
   one platform that gets a wall. Everywhere else web push works in a tab and the
   note above is advice rather than a requirement. */
function needInstall(){return ios&&!ptInstalled()}

/* Built once and kept, because draw() replaces the bells on every change and a popup
   living inside that markup would be torn down while it was open. Appended to the
   body so it is not inside anything with backdrop-filter. */
var pop=null,popFrom=null;
function buildPop(){
if(pop)return pop;
pop=document.createElement('div');
pop.className='ipop';pop.hidden=true;
pop.setAttribute('role','dialog');pop.setAttribute('aria-modal','true');
pop.setAttribute('aria-labelledby','ipoph');
pop.innerHTML='<div class="ibox"><button class="ix" type="button" data-ipx '
+'aria-label="Close">&times;</button>'
+'<h2 id="ipoph">Add '+ptEsc(PTSITE)+' to your home screen</h2>'
+'<p class="mut small">On an iPhone or iPad, Apple only allows notifications once a '
+'site has been added to the home screen. It takes about ten seconds, and it is '
+'free.</p>'
+'<ol><li>Press the Share button in Safari.</li>'
+'<li>Choose <b>Add to Home Screen</b>.</li>'
+'<li>Press <b>Add</b>.</li>'
+'<li>Open '+ptEsc(PTSITE)+' from your home screen, then turn the bell on there.</li></ol>'
+'<a class="fav" href="/install">See it with pictures</a>'
+'<details class="already"><summary>I have already added it</summary>'
+'<p>Then open '+ptEsc(PTSITE)+' from your home screen rather than in this browser '
+'tab, and turn the bell on there. Apple does not allow a browser tab to send '
+'notifications even once the site has been added.</p></details></div>';
document.body.appendChild(pop);
/* Tapping the dark area outside the box closes it, the same as the X. */
pop.addEventListener('click',function(e){
if(e.target===pop||(e.target.closest&&e.target.closest('[data-ipx]')))closePop()});
return pop}

function openPop(from){
var el=buildPop();popFrom=from||null;
el.hidden=false;document.documentElement.style.overflow='hidden';
var x=el.querySelector('[data-ipx]');if(x)x.focus()}

function closePop(){
if(!pop||pop.hidden)return;
pop.hidden=true;document.documentElement.style.overflow='';
/* Back to the bell they pressed, so a keyboard or a screen reader is not dropped at
   the top of the page. */
if(popFrom&&popFrom.focus)try{popFrom.focus()}catch(e){}
popFrom=null}

document.addEventListener('keydown',function(e){
if(e.key==='Escape'&&pop&&!pop.hidden)closePop()});

function ensureDevice(){
if(deviceReady)return Promise.resolve();
return Promise.resolve().then(function(){
if(Notification.permission==='granted')return 'granted';
return Notification.requestPermission()})
.then(function(answer){
if(answer!=='granted')throw new Error('Your browser did not allow notifications.');
return navigator.serviceWorker.register('/sw.js')})
.then(function(){return navigator.serviceWorker.ready})
.then(function(reg){return reg.pushManager.getSubscription().then(function(have){
return have||reg.pushManager.subscribe({userVisibleOnly:true,
applicationServerKey:urlKey(S.key)})})})
.then(function(sub){var j=sub.toJSON();
return post('subscribe',{endpoint:j.endpoint,keys:j.keys,
tz:-new Date().getTimezoneOffset()/60})})
.then(function(){deviceReady=true})}

/* One switch, for one game. The other two are sent back as they are, because
   /api/push/watch replaces the whole row. All three off deletes it. */
function flip(forSlug,key,on){
var w=watchFor(forSlug)||{};
var next={quiet:!!w.quiet,busy:!!w.busy,events:!!w.events,updates:!!w.updates};
next[key]=on;
busy=true;note='';draw();
ensureDevice()
.then(function(){return post('watch',{slug:forSlug,quiet:next.quiet,
busy:next.busy,events:next.events,updates:next.updates,lead:15})})
.then(function(){busy=false;
/* Said once per page, on the first switch anybody turns on, and only when the site
   is not installed. It is a note, not a notification: nothing is sent. */
if(on&&!told&&!ptInstalled()){told=true;
note=installNote()+'Open the install page for the steps.'}
return refresh()})
/* Pressing a switch sends NOTHING. It used to fire a sample notification off the
   first switch anybody turned on, so they could see what one looked like; the guard
   for "first" was a flag on S, and refresh() on the line above replaces S with a
   fresh answer from the server that has no such flag, so it was never true and every
   single switch sent one. The owner wanted none of them anyway: a notification should
   arrive at the hour or the event it is about, and nothing else should ever push one.
   Seeing what one looks like is what the "Send me a test" button on /notifications
   is for, pressed on purpose. */
.catch(function(err){busy=false;
note=(err&&err.message)||'That did not work.';refresh()})}

function refresh(){return fetch('/api/push/state').then(function(r){return r.json()})
.then(function(d){S=d;draw()}).catch(function(){if(gameBox)gameBox.hidden=true})}

/* A bell for one section. The same object everywhere: the glyph, a short label and
   aria-pressed carrying the state, so the styling and a screen reader cannot
   disagree about whether it is on. */
/* Every bell label, in one place. It was written out in three (the signed-out
   bell, the real one and the one on an uninstalled Apple device) and they had
   already started to drift. "before" for the three that aim at a moment still to
   come; "about" for updates, which is the odd one - Roblox only tells us a game
   changed after it has changed, so a notification about an update can never arrive
   before it, and saying otherwise would be a promise broken every single time. */
function bellLabel(kind,on){
if(kind==='all')return on?'Notifications on':'Notify me';
if(kind==='events')return 'Remind me before events';
if(kind==='updates')return 'Remind me about updates';
return kind==='busy'?'Remind me before busy':'Remind me before quiet';
}

function signBell(el,kind){
return '<a class="bellb" href="'+ptLogin()+'" title="Sign in with Roblox to get '
+'notifications (13+)">'+PTBELL+'<span>'+bellWords(el,kind,false)+'</span></a>'}
/* The bell at the top of a game page goes to the settings rather than toggling
   everything at once. It used to be a master switch - on turned the quiet one on,
   off turned all four off - which is a blunt thing to put at the top of a page when
   the four switches it stands for are one tap away. It carries the game it came
   from, because /notifications otherwise lists only games already followed or saved
   and arriving at a page that does not mention the game you just left reads as a
   broken link. */
function masterLink(on,forSlug){
return '<a class="bellb" href="/notifications?game='+encodeURIComponent(forSlug||'')+'">'
+PTBELL+'<span>'+bellLabel('all',on)+'</span></a>'}

function bellBtn(kind,label,on,forSlug){
return '<button class="bellb" type="button" data-bk="'+kind+'" '
+'data-s="'+ptEsc(forSlug||'')+'" '
+'aria-pressed="'+(on?'true':'false')+'"'+(busy?' disabled':'')+'>'
+PTBELL+'<span>'+label+'</span></button>'}

/* Which game a bell belongs to. Nearly always the page's own - but the event
   calendar lists every game and Plan my session lets somebody pick one, so a bell
   may carry its own, and those two pages have no game of their own at all. */
function bellSlug(el){return el.getAttribute('data-s')||slug}
/* A bell inside a list has no room for "Remind me before events", and the row it
   sits in has already said which game and which event it is about. */
function bellWords(el,kind,on){
if(el.hasAttribute('data-short'))return on?'Reminder on':'Remind me';
return bellLabel(kind,on)}

/* Which quiet-or-busy window the countdown in this card is showing. The bell beside
   it means "tell me before THIS window", so it follows that choice rather than
   keeping a third one of its own. */
function planKind(){
var b=document.querySelector('#planbtns button[aria-pressed=true]');
return (b&&b.dataset.m==='busy')?'busy':'quiet'}

function tog(forSlug,key,label,on){
return '<button class="tog" type="button" data-s="'+ptEsc(forSlug)+'" data-k="'+key+'" '
+'aria-pressed="'+(on?'true':'false')+'"'+(busy?' disabled':'')+'>'+label+'</button>'}

/* The four kinds, in the order they are worth having: the two about the crowd,
   then the two about the creators. KINDS is the only list of them - the game page,
   the notifications page and the per-section bells all read it, so a fifth would be
   added here once. */
var KINDS=[['quiet','Quiet'],['busy','Busy'],['events','Events'],['updates','Updates']];
function switches(forSlug,only){
var w=watchFor(forSlug)||{};
var want=only||KINDS.map(function(k){return k[0]});
if(!w.slug)w={};
return '<div class="togs">'+KINDS.filter(function(k){return want.indexOf(k[0])>-1})
.map(function(k){return tog(forSlug,k[0],k[1],w[k[0]])}).join('')+'</div>'}

/* Said once, in one place, so the three buttons cannot drift apart. */
var PHONETIP='<p class="phonetip">If the Roblox app opens instead of the sign-in '
+'page, open roblox.com in your browser and sign in there first, then come back '
+'and tap this again.</p>';
var SIGNIN='<a class="fav" href="'+ptLogin()+'">Sign in with Roblox</a>'+PHONETIP;
var INSTALL='<a class="fav" href="/install">How to add it</a>';
/* We cannot tell whether somebody has added the site: ptInstalled() reads
   display-mode standalone, which is only true INSIDE the added app, so in a tab it
   says no either way. So this does not unlock anything - Apple still will not allow
   push from a tab - it says where the switch they want actually is. */
var ALREADY='<details class="already"><summary>I have already added it</summary>'
+'<p>Then open '+ptEsc(PTSITE)+' from your home screen rather than in this browser '
+'tab, and turn the bell on there. Apple does not allow a browser tab to send '
+'notifications even once the site has been added.</p></details>';

/* ----------------------------------------------------------- the game page */
/* The bells, one per section, each filled only when it can do something. A section
   whose bell cannot work shows nothing at all rather than a button that does not:
   the one explanation lives in the Plan my session card, which every game page has. */
function drawBells(){
var ok=S&&S.available&&S.signedIn&&usable();
/* Signed out, the bells are still drawn, as links to sign in: a feature nobody can
   see is a feature nobody asks for. Nothing is stored and nothing is asked of the
   browser until they have signed in - the bell is only an address. */
var out=S&&S.available&&!S.signedIn;
Array.prototype.forEach.call(document.querySelectorAll('[data-bell]'),function(el){
var s2=bellSlug(el);
/* Plan my session before a game has been picked, and nothing else. */
if(!s2){el.innerHTML='';return}
/* "plan" means the bell beside a countdown: it follows that card's own Quiet or
   Busy chooser rather than keeping a third opinion of its own. */
var kind=el.dataset.bell;
if(kind==='plan')kind=planKind();
if(out){el.innerHTML=signBell(el,kind);return}
/* On an iPhone or iPad in a tab the bells used to be left EMPTY, which reads as the
   site being broken rather than as one step away from working. They are drawn as
   normal now and the click handler opens the install popup instead of switching
   anything on, because on Apple nothing can be switched on until the site is on the
   home screen. */
if(!ok&&needInstall()&&S&&S.signedIn){
if(kind==='all')el.innerHTML=masterLink(false,s2);
else el.innerHTML=bellBtn(kind,bellWords(el,kind,false),false,s2);
return}
if(!ok){el.innerHTML='';return}
var w=watchFor(s2)||{};
if(kind==='all'){
var any=!!(w.quiet||w.busy||w.events||w.updates);
el.innerHTML=masterLink(any,s2)}
else el.innerHTML=bellBtn(kind,bellWords(el,kind,w[kind]),w[kind],s2)})}

function drawGame(){
drawBells();
if(!gameBox)return;
if(!S||!S.available||!slug){gameBox.hidden=true;return}
var html;
if(!S.signedIn){
html='<p class="mut small">The bell above needs a Roblox sign-in. 13+.</p>'}
else if(!usable()){
html='<p class="mut small">'+(ios
?'Add '+ptEsc(PTSITE)+' to your home screen first.'
:'This browser cannot do notifications.')+'</p>'+(ios?INSTALL+ALREADY:'')}
else{
html=(note?'<p class="mut small">'+ptEsc(note)
+' <a href="/install">How to add it</a></p>':'')
+'<p class="mut small"><a href="/notifications">All four kinds</a></p>'}
gameBox.innerHTML=html;gameBox.hidden=false}

/* ------------------------------------------------- the notifications page */
function row(w){
var g=(names&&names[w.slug])||{n:w.slug,i:''};
return '<li class="nrow"><a href="/game/'+ptEsc(w.slug)+'">'
+(g.i?'<img src="'+ptEsc(g.i)+'" alt="" width="34" height="34">':'')
+'<span>'+ptEsc(g.n)+(w.saved?'<i class="svd">saved</i>':'')+'</span></a>'
+switches(w.slug)+'</li>'}

/* Every game worth a row: the ones being notified about, then any saved game that
   is not already there, with all four switches off. Saved games earn their place
   because saving one is already somebody saying they care about it - having to go
   and find it again to turn a notification on was a step with no purpose. */
/* Which game the bell that sent us here belonged to. */
function cameFor(){
try{var m=/[?&]game=([^&]+)/.exec(location.search);
return m?decodeURIComponent(m[1]):null}catch(e){return null}}

function listed(){
var out=(S.watching||[]).slice();
var have={};out.forEach(function(w){have[w.slug]=true});
(PT.favs||[]).forEach(function(f){
if(!have[f]){have[f]=true;
out.push({slug:f,quiet:0,busy:0,events:0,updates:0,saved:true})}});
/* The game whose bell was pressed goes to the top, and gets a row even if nothing
   is on for it and it has never been saved. */
var want=cameFor();
if(want){
var at=-1;
for(var i=0;i<out.length;i++)if(out[i].slug===want){at=i;break}
if(at>-1)out.unshift(out.splice(at,1)[0]);
else out.unshift({slug:want,quiet:0,busy:0,events:0,updates:0})}
return out}

function drawPage(){
if(!pageBox)return;
if(!S){pageBox.innerHTML='<p class="mut">Loading&hellip;</p>';return}
if(!S.available){
pageBox.innerHTML='<p class="mut">Notifications are not switched on for this site yet.</p>';return}
if(!S.signedIn){
pageBox.innerHTML='<p>Notifications need you to be signed in with Roblox, because we '
+'have to remember your device to send one. Roblox does not let under-13s sign in to '
+'other sites, so this part of '+ptEsc(PTSITE)+' is 13 and over.</p>'+SIGNIN;return}
var head='';
if(!usable()){
head='<div class="card"><h2>This device cannot receive them</h2><p class="mut small">'
+(ios?'On an iPhone or iPad, notifications only work once '+ptEsc(PTSITE)
+' has been added to your home screen.':'This browser does not support notifications.')
+'</p>'+(ios?INSTALL+ALREADY:'')+'</div>'}
else if(Notification.permission==='denied'){
head='<div class="card"><h2>Your browser is blocking them</h2><p class="mut small">'
+'Allow notifications for this site in your browser settings, next to the address '
+'bar, then come back.</p></div>'}
var list=listed();
pageBox.innerHTML=head
+(note?'<p class="saidit">'+ptEsc(note)+'</p>':'')
+(list.length
?'<ul class="nlist">'+list.map(row).join('')+'</ul>'
:'<p class="mut">Nothing here yet. Save a game, or turn a notification on from a '
+'game page, and it will appear here.</p>')
+(list.length?'<p class="mut small">Up to '+(S.maxGames||20)+' games can be switched '
+'on. <button class="fav" id="notiftest" type="button">Send me a test</button></p>':'')}

function draw(){drawGame();drawPage()}

/* Delegated from the document: draw() replaces this markup on every change, so a
   handler put on a switch itself would be thrown away with it. e.target.closest is
   guarded because on iOS a tap that has bubbled this far can arrive at a text node. */
document.addEventListener('click',function(e){
if(!e.target.closest||busy)return;
/* Before anything else: on an uninstalled Apple device a bell, a switch or the test
   button cannot do what it says, so pressing one explains how to make it work rather
   than failing. This covers the notifications page too, where the switches were drawn
   and clickable and simply threw an error. */
if(needInstall()){
var nd=e.target.closest('.tog')||e.target.closest('button.bellb')
||e.target.closest('#notiftest');
if(nd){e.preventDefault();openPop(nd);return}}
var t=e.target.closest('.tog');
if(t){flip(t.dataset.s,t.dataset.k,t.getAttribute('aria-pressed')!=='true');return}
var bb=e.target.closest('button.bellb');
/* The bell says which game it is for: on the calendar and on the planner that is
   not the page's own game, because those pages have none. */
if(bb){flip(bb.dataset.s||slug,bb.dataset.bk,
bb.getAttribute('aria-pressed')!=='true');return}
/* Changing the countdown between quiet and busy changes what the bell beside it is
   offering, so it has to be redrawn. */
if(e.target.closest('#planbtns')){setTimeout(drawBells,0);return}
if(e.target.closest('#notiftest')){
busy=true;note='Sending&hellip;';draw();
post('test',{}).then(function(){busy=false;
note='Sent. If nothing appears, your computer is hiding it rather than this site '
+'failing: check your notification centre and your system settings.';draw()})
.catch(function(err){busy=false;note=(err&&err.message)||'That did not work.';draw()})}});

/* The names and pictures for the list, from the file search already uses. */
if(pageBox){fetch('/games.json').then(function(r){return r.json()}).then(function(all){
names={};all.forEach(function(g){names[g.s]=g});draw()}).catch(function(){})}

/* The planner changes which game its bell is for every time the dropdown moves, so
   it needs a way to ask for a redraw. Nothing else uses it. */
PT.bells=drawBells;
PT.ready(function(){refresh()});
})();"""


def notifications_body():
    """Everything somebody is being told about, in one place.

    A page rather than a menu hanging off the bell: three switches per game and a
    device to turn on is more than a dropdown in the corner of a phone can hold
    without quietly becoming its own little application. The list itself is drawn by
    PUSH_JS, because it is different for every person and a built page is the same
    file for everyone.
    """
    site = html.escape(SITE)
    return f"""<div class="doc"><h1>Your notifications</h1>
<p class="mut">Each switch takes effect as you press it.</p>
<div id="notifpage"><p class="mut">Loading&hellip;</p></div>
<h2>What the four mean</h2>
<ul>
<li><b>Quiet</b> &mdash; shortly before that game is usually at its emptiest, which is
when queues are short and servers are calm.</li>
<li><b>Busy</b> &mdash; shortly before it is usually at its fullest, which is when
trading and events are easiest to find.</li>
<li><b>Events</b> &mdash; shortly before something the creators have put on the game's
Roblox calendar starts.</li>
<li><b>Updates</b> &mdash; when the creators change the game. This one is the other way
round: the update has already happened by the time Roblox tells anyone. So it can turn up
a few hours late, and the message says how long ago.</li>
</ul>
<p>You get about fifteen minutes' warning, and at most one of each per game per day.
Turning all four off for a game stops it completely.</p>
<h2>What we keep</h2>
<p>Four things, and nothing else:</p>
<ul><li>The address your browser gives us for each device you turn on.</li>
<li>Two keys that lock each message, so only your device can open it.</li>
<li>How many hours ahead of UTC you are.</li>
<li>Which games you picked.</li></ul>
<p><b>Delete my data</b> on the <a href="/privacy">Privacy Policy</a> removes all of it,
and so does turning every switch off.</p>
<p class="mut small">You have to be signed in with Roblox to use this, so everyone who
can is 13 or over &mdash; that is Roblox's own rule. We ask because sending a
notification means remembering your device.</p></div>"""


def install_body():
    """How to add the site to a phone or computer.

    A page rather than a line of help in a menu, because the steps differ on every
    platform and Apple's are the ones people cannot guess: there is no API that lets
    a website install itself on an iPhone, so the only thing that can be offered
    there is clear instructions. Browsers that CAN do it get a real button at the
    top, drawn by CHROME_JS only when the browser has actually offered.
    """
    site = html.escape(SITE)
    return f"""<div class="doc"><h1>Get {site} as an app</h1>
<p>{site} can sit on your home screen with its own icon and open like an app, with no
browser bar around it. It is the same website &mdash; there is nothing to download from
an app store, and it takes no space worth worrying about.</p>
<button class="remind" data-install type="button" hidden>&#128229; Install it now</button>
<p class="mut small" data-install hidden>One tap. Your browser will ask you to confirm.</p>
<h2>Why install?</h2>
<ul><li>It opens from your home screen instead of you having to find the address.</li>
<li>It fills the whole screen, so there is more room for the charts.</li>
<li><b>On an iPhone or iPad it is the only way notifications can work.</b> Apple only
allows a website to send notifications once it has been added to the home screen.</li></ul>
<p class="mut small">Three ways to do it, one per kind of device. Open the one you
are on &mdash; we open it for you where we can tell.</p>
<details class="howto" data-dev="ios"><summary><h2>On an iPhone or iPad</h2></summary>
<div class="howto-in">
<p>This has to be done in <b>Safari</b>. Other browsers on an iPhone cannot add it.
Each picture below shows what to tap, with a red arrow on it.</p>
<ol class="shots">
<li><p>Open <b>{site}</b> in Safari and tap the <b>three lines</b> at the left-hand end
of the address bar, at the bottom of the screen.</p>
<img src="/img/install/step1.webp" width="520" height="1049" loading="lazy"
alt="A game page in Safari, with a red arrow pointing at the three-lines button at the left of the address bar."></li>
<li><p>Tap <b>Share</b>.</p>
<img src="/img/install/step2.webp" width="520" height="1127" loading="lazy"
alt="The Safari menu open, with a red arrow pointing at Share."></li>
<li><p>Scroll down the list and tap <b>Add to Home Screen</b>.</p>
<img src="/img/install/step3.webp" width="520" height="1127" loading="lazy"
alt="The share sheet, with a red arrow pointing at Add to Home Screen."></li>
<li><p>Tap <b>Add</b> in the top right. Leave <b>Open as Web App</b> switched on
&mdash; that is the part that makes notifications work.</p>
<img src="/img/install/step4.webp" width="520" height="421" loading="lazy"
alt="The Add to Home Screen box, with a red arrow pointing at the Add button in the top right."></li>
</ol>
<p>The icon appears on your home screen. Open {site} from there from now on, and the
notification button on any game page will work.</p>
</div></details>
<details class="howto" data-dev="android"><summary><h2>On an Android phone</h2></summary>
<div class="howto-in">
<ol><li>Open <b>{site}</b> in Chrome.</li>
<li>Tap the <b>menu</b> button &mdash; three lines or three dots, depending on your browser.</li>
<li>Tap <b>Add to Home screen</b>, or <b>Install app</b> if that is what it says.</li>
<li>Confirm.</li></ol>
</div></details>
<details class="howto" data-dev="desktop"><summary><h2>On a computer</h2></summary>
<div class="howto-in">
<h3>Adding it</h3>
<ol class="shots wide">
<li><p>Open <b>{site}</b> in your browser.</p></li>
<li><p>Click the small <b>install</b> icon at the right-hand end of the address bar
&mdash; a little screen with an arrow in it.</p>
<img src="/img/install/pc4.webp" width="520" height="176" loading="lazy"
alt="The right-hand end of a browser address bar, with a red arrow pointing at the install icon, a small screen with an arrow in it."></li>
<li><p>Choose <b>Next</b>, then <b>Install</b>.</p></li>
</ol>
<p class="mut small">That icon only appears in Chrome and Edge. Firefox on a computer
cannot add a website this way, but notifications still work in it.</p>
<h3>Turning notifications on</h3>
<p>On a computer you do not have to add {site} first &mdash; notifications work in an
ordinary browser tab. The first time you press a bell, your browser asks.</p>
<ol class="shots wide">
<li><p>Press <b>Allow</b> when the box appears.</p>
<img src="/img/install/pc1.webp" width="520" height="269" loading="lazy"
alt="A browser asking whether {site} may show notifications, with a red arrow pointing at the Allow button."></li>
<li><p>Missed it, or pressed Block by mistake? Click the <b>small icon just to the
left of the address</b>.</p>
<img src="/img/install/pc2.webp" width="520" height="158" loading="lazy"
alt="A browser address bar, with a red arrow pointing at the site settings icon to the left of the address."></li>
<li><p>Turn <b>Notifications</b> on. If it offers <b>Reset permission</b> instead,
click that, reload the page and press the bell again.</p>
<img src="/img/install/pc3.webp" width="520" height="548" loading="lazy"
alt="The site settings panel, with a red arrow pointing at the Notifications switch."></li>
</ol>
<h3>If they still do not appear</h3>
<p>Windows has a switch of its own on top of the browser's, and that is usually the
one in the way.</p>
<ol><li>Open <b>Settings</b>, then <b>System</b>, then <b>Notifications</b>.</li>
<li>Turn <b>Notifications</b> on.</li>
<li>Check that <b>Do not disturb</b> is <b>off</b>.</li>
<li>Scroll down to the list of apps underneath and turn on the one for your browser
&mdash; <b>Google Chrome</b>, <b>Microsoft Edge</b>, <b>Firefox</b>, whichever you
opened {site} in.</li></ol>
<p class="mut small">On a Mac the same two switches are in <b>System Settings</b>,
then <b>Notifications</b>.</p>
</div></details>
<h2>Getting rid of it</h2>
<p>Hold the icon and remove it, the same as any other app. Nothing is left behind on
your device, and nothing about you is kept here &mdash; see our
<a href="/privacy">Privacy Policy</a>.</p></div>"""


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
<h2>Notifications</h2>
<p>If you sign in with Roblox, any game page can send you a notification shortly before that game usually
gets quiet or busy, and before its events start. It is off until you turn it on, your browser asks your
permission first, and you can turn it off again on the same page at any time. On an iPhone or iPad you
have to add {html.escape(SITE)} to your home screen first &mdash; <a href="/install">here is how</a> &mdash;
because Apple only allows notifications for a site that has been added.</p>
<p>You have to be signed in with Roblox. To send a notification we have to remember your device, and we
will not remember anything at all about somebody who has not signed in. Roblox does not let under-13s sign
in to other sites, so everyone who can turn this on is 13 or over.</p>
<h2>Which games are on here</h2>
<p>We only list games that Roblox itself labels <b>Minimal</b> or <b>Mild</b> for content, and we read that
label back from Roblox before adding a game rather than guessing from its name. That is why some of the
biggest games on Roblox are not here. We leave them out on purpose. It is a rule about the label, though,
not a promise about the game &mdash; see &ldquo;What it does not tell you&rdquo; below.</p>
<h2>Where the extra details come from</h2>
<ul><li><b>Event calendars and updates</b> come from the events the game's own creators post on Roblox.</li>
<li><b>Descriptions, pictures and game passes</b> are the public ones Roblox shows on each game's page.</li>
<li><b>"Days the player count jumped"</b> is ours: any day at least {SPIKE:g} times busier than the week
before. That usually means an update, a holiday event, or a popular video about the game.</li></ul>
<h2>Our guesses, and what we really saw</h2>
<p>These are two different things, and we try never to mix them up. A <b>typical</b> or <b>average</b> player
count is a guess: we add up the readings we took in that hour and divide. A <b>highest seen</b> number is not a
guess &mdash; it is one real reading we took. A guess made from only a few readings can be a long way out, so
every game page tells you how many readings it used and how long we have been watching.</p>
<h2>Game names</h2>
<p>Creators rename their games for every holiday and update, so the same game might be called
&ldquo;Grand Piece Online&rdquo; one week and &ldquo;[&#127875;HALLOWEEN PT 3] Grand Piece Online&rdquo; the next.
We use the game's core name for headings and web addresses so links keep working, and each game page says what
Roblox is calling it today.</p>
<h2>What it does not tell you</h2>
<p>Player counts show when people play. They do not say whether a game is good, fair, or safe for children,
and neither does Roblox's content label on its own. Parents should still check a game themselves and use
Roblox's parental controls.</p>
<h2>A few last things</h2>
<p>{html.escape(SITE)} is an independent fan project. It is not affiliated with, endorsed by, or sponsored by Roblox Corporation.
Game names belong to their creators. Numbers are averages and can be off, especially for games we started tracking recently.</p>
<p>We never ask for your Roblox password. You can sign in with Roblox if you want your saved games on more than
one device, but everything works without it. See our <a href="/privacy">Privacy Policy</a>.</p>
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
<h2>Browser notifications</h2>
<p>If you are signed in with Roblox, you can ask us to send a notification shortly before a game you follow
usually gets quiet or busy. This is <b>off unless you turn it on</b>, your browser asks your permission first,
and you can turn it off on the game's page at any time.</p>
<p>If you turn it on, we store the notification address your browser gives us for that device, the two keys
needed to lock the message so only your device can read it, how many hours ahead of UTC you are so a message
can name the right time, and which games you chose. We do not store the notifications themselves, and we
cannot read anything on your device.</p>
<p>We only offer this to people signed in with Roblox, and the reason is this page's whole point: a notification
address identifies a particular device, and we will not keep one for a visitor who has not signed in and might
be a child. Roblox does not let under-13s sign in to other sites, so everyone who can turn this on is 13 or
over. <b>Delete my data</b> below removes your notification settings along with everything else, and so does
signing out of Roblox on your account.</p>
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
like from our <a href="/privacy">Privacy Policy</a> page. We may end access for anyone misusing the site.</p>
<h2>The numbers are estimates</h2>
<p>Everything here is an average worked out from samples, so it can be wrong, out of date, or missing. Busy and
quiet times change. Player counts say nothing about whether a game is good, fair, or suitable for a child.
Please treat the site as a helpful guess, not a promise.</p>
<h2>No warranty, and limits</h2>
<p>{html.escape(SITE)} is provided "as is", without warranties of any kind. We are not liable for any loss
arising from using the site or relying on its numbers.</p>
<h2>Changes to these terms</h2>
<p>If these terms change, we will update this page and the date at the top.</p>
</div>"""


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


def write_bytes(path, data):
    """Same as write(), for a file that is not text (the PNG app icons)."""
    os.makedirs(os.path.dirname(f"{OUT}/{path}") or OUT, exist_ok=True)
    with open(f"{OUT}/{path}", "wb") as f:
        f.write(data)
    WRITTEN.add(path.replace("\\", "/"))


def prune(folders=("game", "category", "updates", "ics",
                   "events", "passes", "questions")):
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
                 "url": abs_url(f'/game/{c["slug"]}')}
                for i, c in enumerate(cards[:50])]}


def plan_help():
    """What a quiet window is and where the number comes from.

    The page asks people to trust a countdown. Saying how it was worked out, and
    what it cannot know, is the same promise the rest of the site makes.
    """
    return ('<div class="card"><h2>How we work out a good time</h2>'
            '<p>We take a player count for every game we follow about every ten '
            'minutes, and we keep them. That gives us a picture of each game hour '
            'by hour across the week.</p>'
            '<p>A <b>quiet</b> stretch is one where that game is near the bottom of '
            'its own range, and a <b>busy</b> one is near the top. It is each game '
            'against itself, not against other games: a quiet hour in a huge game '
            'can still hold more people than a busy hour in a small one.</p>'
            '<p>The countdown is on your own clock. Your browser works that out; we '
            'never ask where you are and we do not store it.</p>'
            '<p>It is a guess from what usually happens, not a timetable. A new '
            'update, a video or a school holiday can fill a game at an hour it is '
            'normally empty.</p></div>')


def plan_table(cards, n=24):
    """The quietest and busiest hour of each big game, as a plain table.

    /plan is a tool: a dropdown, two buttons and a countdown, all drawn by script
    once the visitor has chosen something. That leaves 79 words on the page for
    anybody who has not chosen yet - measured 23 Nov 2026, the thinnest indexed
    page on the site, and it is one of the eight sections in TABS and therefore in
    the sitemap. A search engine reading "Best Time to Play" found a heading, one
    sentence and the words "Loading the games".

    So the answer the tool gives one game at a time is also written out for the
    biggest games, in UTC, before any script runs. It is the same two facts their
    own pages carry, which is why each row links to its game rather than trying to
    be that page: this is a contents page for a question, not a copy of the
    answers.

    Not the same as /busiest-hours, which adds every game together into one
    Roblox-wide rhythm. This one is per game, which is what somebody who already
    knows what they want to play is asking.
    """
    rows = []
    for c in sorted(cards, key=lambda c: -c["avg"])[:n]:
        f = c.get("facts")
        if not f:
            continue
        bd, bh, bv = f["busy"]
        qd, qh, qv = f["quiet"]
        rows.append(f'<tr><td><a href="/game/{c["slug"]}">{html.escape(c["name"])}</a></td>'
                    f'<td>{DAYS[qd]} {hour12(qh)}</td><td>{qv:,}</td>'
                    f'<td>{DAYS[bd]} {hour12(bh)}</td><td>{bv:,}</td></tr>')
    if len(rows) < 5:
        return ""
    return (f'<div class="card"><h2>The quietest and busiest hour of each big game</h2>'
            f'<p class="mut small">The {len(rows)} games with the most players, and when '
            f'each one is at its emptiest and its fullest. All times are UTC, because this '
            f'part of the page is written before we know where you are &ndash; the tool '
            f'above puts them on your own clock. The player counts are what a typical '
            f'moment at that hour looks like, at the size the game is now.</p>'
            f'<div class="wrap"><table class="tbl">'
            f'<tr><th>Game</th><th>Quietest hour</th><th>Players then</th>'
            f'<th>Busiest hour</th><th>Players then</th></tr>'
            + "".join(rows) + '</table></div></div>')


def share_week(cards):
    """7x24 of how busy a set of games is, each counted against its own peak hour.

    A game with two million players must not simply drown out forty smaller ones:
    what is being measured is when games are busy RELATIVE TO THEMSELVES, which is
    what "when is this kind of game busiest" actually means. The number in each
    square is a percentage of a typical game's own busiest hour, so 100 would mean
    every game peaks at that same hour.

    Pulled out of busy_page so the category pages can ask the same question of a
    handful of games and get an answer worked out the same way. Two copies of this
    would be two answers that drift.
    """
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
    return [[round(totals[d][h] / counts[d][h] * 100) if counts[d][h] else None
             for h in range(24)] for d in range(7)]


def peak_of(share):
    """(day, hour) of the busiest square in a share grid, or None."""
    cells = [(d, h, v) for d in range(7) for h, v in enumerate(share[d]) if v is not None]
    if len(cells) < 24:
        return None
    d, h, _ = max(cells, key=lambda c: c[2])
    return d, h


def category_rhythm(name, cg, all_share):
    """When this kind of game is busy, and whether that differs from Roblox at large.

    A category page was a heading, a sentence and a grid of tiles - 99 to 235 words
    on 8 of the 12 of them, and near-identical to each other but for the game names.
    This is the one thing a category page can say that no game page can: these games
    share a rhythm, and it is not always the site's rhythm. Shopping games and
    shooters do not fill up at the same hour.

    The comparison against every game we track is the point. "Busiest Saturday at
    5 PM" on its own is nearly the same sentence on every category; "two hours
    earlier than Roblox as a whole" is what makes the page worth reading.

    Three games minimum. Two games averaged together is not the habit of a kind of
    game, it is two games, and the grid above already shows them.
    """
    if len(cg) < 3:
        return ""
    share = share_week(cg)
    cells = [(d, h, v) for d in range(7) for h, v in enumerate(share[d]) if v is not None]
    if len(cells) < 100:
        return ""
    bd, bh, _ = max(cells, key=lambda c: c[2])
    qd, qh, _ = min(cells, key=lambda c: c[2])
    by_day = {}
    for d, h, v in cells:
        by_day.setdefault(d, []).append(v)
    means = {d: sum(v) / len(v) for d, v in by_day.items() if len(v) >= 12}
    bits = [f'These games are busiest on <b>{DAYS[bd]} around {hour12(bh)} UTC</b> '
            f'and quietest on <b>{DAYS[qd]} around {hour12(qh)} UTC</b>.']
    if means:
        bits.append(f'<b>{DAYS[max(means, key=means.get)]}</b> is the busiest day of the '
                    f'week for them and <b>{DAYS[min(means, key=means.get)]}</b> the quietest.')
    whole = peak_of(all_share)
    if whole:
        wd, wh = whole
        gap = (bh - wh) % 24
        gap = gap - 24 if gap > 12 else gap
        if bd == wd and gap == 0:
            bits.append('That is the same hour Roblox as a whole is busiest.')
        elif bd == wd:
            when_ = (f'{abs(gap)} hour' + ('s' if abs(gap) != 1 else '')
                     + (' later' if gap > 0 else ' earlier'))
            bits.append(f'Roblox as a whole peaks on {DAYS[wd]} too, but these games '
                        f'fill up <b>{when_}</b>.')
        else:
            bits.append(f'Roblox as a whole is busiest on {DAYS[wd]} around '
                        f'{hour12(wh)} UTC, so these games keep their own hours.')
    tot = sum(c["avg"] for c in cg)
    bits.append(f'Added together the {len(cg)} of them hold about <b>{tot:,} players</b> '
                f'at a typical moment.')
    return (f'<div class="card"><h2>When are {html.escape(name.lower())} games busiest?</h2>'
            f'<p class="mut small">Worked out from the {len(cg)} games on this page, each '
            f'one counted against its own busiest hour so the biggest does not speak for '
            f'all of them.</p><ul class="habits">'
            + "".join(f"<li>{b}</li>" for b in bits) + '</ul></div>')


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
    share = share_week(cards)
    cells = [(d, h, v) for d in range(7) for h, v in enumerate(share[d]) if v is not None]
    if len(cells) < 24:
        return page(seo_title("When Is Roblox Busiest?"),
                    '<div class="hero"><h1>When is Roblox busiest?</h1>'
                    '<p class="lede">We need a full week of player counts across the games we '
                    'track before this page can say anything. Check back in a few days.</p></div>'
                    '<p><a href="/">&larr; All Roblox player counts</a></p>',
                    "The busiest and quietest hours across the Roblox games we track.",
                    wide=True, canon="/busiest-hours", noindex=True,
                    trail=[("All games", "/"), ("Busiest hours", "/busiest-hours")])

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
        f'week is <b>{DAYS[busy[0]]} around {hour12(busy[1])} UTC</b>. The quietest is '
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
        f'the games we track. In local time that is late afternoon and evening across '
        f'Europe and the Americas, when most players are out of school.</p>'
        f'<h3>When is the best time to play Roblox games quietly?</h3>'
        f'<p>{DAYS[quiet[0]]} around {hour12(quiet[1])} UTC is the quietest hour overall. '
        f'Quiet hours mean shorter queues, less lag and a better chance at timed or '
        f'limited in-game events. Individual games differ, so check the game\'s own page '
        f'for its quietest hour.</p>'
        f'<h3>Is this the same for every game?</h3>'
        f'<p>No. Most games follow this pattern, because most players are awake and '
        f'asleep at much the same times. A game whose players are mostly in one part of '
        f'the world can be hours out of step. Every game we track has its own '
        f'hour-by-hour page.</p>'
        f'<p class="mut small">Worked out from '
        f'{sum(c["samples"] for c in cards):,} player counts we took ourselves. They are '
        f'averages, so treat them as a good guess rather than an official figure.'
        f'</p></div></div>'
        + row_head("Busiest games right now",
                   f'<span class="mut small">{len(cards)} games</span>')
        + grid(cards[:12])
        + '<p><a href="/popular">Most played Roblox games</a> &middot; '
          '<a href="/plan">Plan a session</a> &middot; '
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
        wide=True, canon="/busiest-hours",
        trail=[("All games", "/"), ("Busiest hours", "/busiest-hours")],
        modified=iso_day(now),
        schema=[{"@type": "Dataset",
                 "name": "Roblox player activity by hour of the week",
                 "description": ("The share of each game's peak player count reached in "
                                 "every hour of the week, averaged across the Roblox games "
                                 f"{SITE} tracks."),
                 "url": abs_url("/busiest-hours"),
                 "measurementTechnique": "Repeated sampling of public Roblox player counts",
                 "variableMeasured": "Concurrent players as a share of each game's peak",
                 "isAccessibleForFree": True,
                 "license": abs_url("/terms"),   # see the note in game_schema()
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
        title, body, desc, wide=True, nav=key, canon=f"/{key}",
        trail=[("All games", "/"), (h1, f"/{key}")],
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
        f'<tr><td>{i + 1}</td><td><a href="/game/{c["slug"]}">{html.escape(c["name"])}</a></td>'
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
    # The net under the collectors. Roblox returns a placeholder with id 0 for a
    # game it will not talk about any more, and both collectors recorded it for a
    # while, so the data branch already holds a "[TITLE UNAVAILABLE]" with
    # hundreds of samples that cannot be un-collected. Without this it gets a page
    # of its own and a line in the sitemap as soon as it passes MIN_SAMPLES.
    games = [g for g in games if g[0] and (g[1] or "").strip()]
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

    # When each game's creators last announced an update, worked out before the
    # loop because a game's updates page offers other games' updates pages and so
    # has to know about games it has not reached yet - the same reason "Similar
    # games" needs two passes. fetch_events() caches on disk, so this spends
    # nothing the loop below was not going to spend anyway.
    latest_update = {}
    for c in cards:
        done = [e["start"] for e in (roblox_api.fetch_events(c["uid"]) or [])
                if (e["end"] or e["start"] + 86400) < now]
        if done:
            latest_update[c["slug"]] = max(done)

    # Second pass: the game pages themselves.
    all_events = []
    last_update = {}
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
        # When the creators last changed this game, for the Updates notification.
        # metas comes from Roblox's own games endpoint, so this is their timestamp
        # rather than anything we worked out.
        if meta and meta.get("updated"):
            last_update[s] = int(meta["updated"])
        upcoming = [e for e in (events or []) if (e["end"] or e["start"] + 86400) >= now]
        for e in upcoming:
            all_events.append(dict(e, game=name, slug=s, icon=c["icon"]))
        # The "Remind me" files. Written before the pages that link to them, and
        # for every upcoming event rather than the handful this game's own page
        # shows, because /events lists far more of them.
        c["events"], c["upcoming"] = len(events or []), len(upcoming)
        vlabel, vcol, vtext, _ = verdict(a)
        pattern = update_pattern(events, a["spikes"], now)
        facts = week_facts(a["week"])
        c["facts"] = facts
        best_txt, quiet_txt = short_answer(name, facts)
        swing = swing_text(name, facts)

        play = (f'<a class="btn" href="https://www.roblox.com/games/{c["place"]}">'
                f'Play {html.escape(name)}</a>' if c["place"] and c["place"] > 1 else "")
        in_cat = c["genre"] in cats
        # At the top with the game rather than in the small print of the short
        # answer, which is where it used to hide.
        cat = (f'<p class="gcat"><a href="/category/{slug(c["genre"])}">'
               f'{html.escape(c["genre"])} games</a></p>' if in_cat else "")

        # The opening paragraph. Every number in it comes from our own samples, and the
        # wording keeps "about"/"typical" on the averages and "seen"/"recorded" on the
        # things we really observed, so an estimate is never dressed up as a fact.
        alias = ALIASES.get(s)
        aka = f' ({html.escape(alias)})' if alias else ''
        lead = (f'At our last check ({stamp(a["latest"][0])}) <b>{a["latest"][1]:,} people</b> '
                f'were playing {html.escape(name)}{aka}. It has about <b>{a["avg7"]:,} players</b> '
                f'at a typical moment, and we have seen as many as <b>{a["peak"]:,}</b> at once. ')
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

        # Back goes to this game's category when it has one, so the button lands
        # somewhere useful even for a visitor who arrived straight from Google.
        where = ((f'/category/{slug(c["genre"])}', f'{c["genre"]} games')
                 if in_cat else ("/", "All games"))
        trail = [("All games", "/")]
        if in_cat:
            trail.append((f'{c["genre"]} games', f'/category/{slug(c["genre"])}'))
        thin = not index_ok(c)

        faq, qa = faq_html(c, a, facts, meta, pattern)
        hist_b = anchor(span(history_html(name, a), 8), "history")

        # Everything about this game's updates gets its own page, reached from the
        # row of buttons at the top of the game page.
        upd = updates_html(name, events, meta, a["spikes"], now, pattern)
        if upd:
            # Right under that page's own heading, where somebody reading about this
            # game's updates is already looking.
            upd = upd.replace(
                "</h2>", "</h2>" + updates_bell() + next_update_line(), 1)

        # ---- the three sections that are now pages of their own.
        # Each is built first so the row of buttons on the game page can link only to
        # the ones that actually have something on them.
        cal_b = calendar_html(name, events, now)
        par_b = parents_html(passes, pass_icons)
        has = {"updates": bool(upd), "events": bool(upcoming), "passes": bool(par_b),
               "questions": bool(faq)}
        # The sitemap only asks Google to look at a page that has something on it.
        for folder, yes in has.items():
            c["has_" + folder] = yes
        # An updates page for a game whose creators have announced no updates at all
        # is about 200 words: the date the game last changed, and perhaps a spike or
        # two. Google crawled several of those in Nov 2026 and declined to index them,
        # and a pile of near-empty pages counts against the whole site. So it stays
        # on the site and in the game's tabs, but is kept out of Google and out of
        # the sitemap until the first update arrives. One or two updates is enough
        # to keep it: /updates/anime-adventures had a single update and was already
        # being found for "when is anime adventures update".
        n_updates = sum(1 for e in (events or []) if (e["end"] or e["start"] + 86400) < now)
        c["no_updates"] = n_updates == 0
        # The same rule, for the same reason, applied to the page that lists what a
        # game sells. A game with no game passes gets a "What costs money" page of
        # three sentences - "This game sells no game passes right now", the note
        # about one-time items and the note about Roblox Parental Controls - and
        # those three sentences are IDENTICAL on every such page: measured on
        # 23 Nov 2026, 23 of the 148 passes pages, all 100 to 120 words, differing
        # only in the game's name. That is a near-duplicate page, which is worse
        # than a thin one. It stays on the site and in the game's tabs, because
        # "nothing to buy here" is a real answer for a parent, but it is not
        # something to ask Google to list 23 copies of.
        c["no_passes"] = not passes

        if has["events"]:
            write(f"events/{s}.html", side_page(
                c, "events",
                (seo_title(f"{name} Events: What Is On and When It Starts",
                           f"{name} Events"),
                 f"{name} events",
                 clip(f"Every event the creators of {name} have announced on Roblox, when "
                      f"each one starts in your own timezone, and how long it runs."),
                 "Events"),
                f"Every event the creators have put on Roblox&rsquo;s calendar for "
                f"{html.escape(name)}, with a live countdown to the next one.",
                cal_b + event_habits(name, events, now), play, trail,
                extra_schema=event_schema(c, upcoming, now),
                # This page has the events bell on it and the countdown to the next
                # one, so it needs what drives both. The other two side pages have
                # neither and stay as plain documents.
                tail=(f'<script>window.PT_GAME='
                      f'{jsdata({"s": s, "n": name, "i": c["icon"] or ""})};</script>'
                      f'<script>{SHARED_JS}ptCountdowns();</script>'
                      f'<script>{PUSH_JS}</script>'),
                noindex=thin, modified=iso_day(a["last"]), have=has))

        if has["passes"]:
            write(f"passes/{s}.html", side_page(
                c, "passes",
                (seo_title(f"{name} Game Passes and Prices in Robux",
                           f"{name} Game Passes"),
                 f"What costs money in {name}",
                 clip(f"Every {name} game pass, what the creators say it contains, and the "
                      f"price in Robux and in dollars. Written for parents."),
                 "What costs money"),
                f"Every game pass the creators sell for {html.escape(name)}, what they say "
                f"each one contains, and the price in Robux and in dollars.",
                par_b, play, trail,
                noindex=thin or c["no_passes"], modified=iso_day(a["last"]), have=has))

        if has["questions"]:
            write(f"questions/{s}.html", side_page(
                c, "questions",
                (seo_title(f"{name} Questions: Player Count, Best Times, Is It Dead",
                           f"{name} Questions"),
                 f"{name} questions",
                 clip(f"The questions people ask about {name}, answered with the player "
                      f"counts we have taken ourselves."),
                 "Questions"),
                f"The things people ask about {html.escape(name)}, answered from the "
                f"player counts we take ourselves.",
                faq, play, trail,
                extra_schema=faq_schema(qa),
                noindex=thin, modified=iso_day(a["last"]), have=has))
        body = (GAME.replace("__ICON__", thumb(name, c["icon"], icon_alt(name), eager=True))
                .replace("__LEAD__", lead)
                .replace("__BEST__", best_txt)
                .replace("__QUIET__", quiet_txt)
                # Not inside #best or #quiet: the browser rewrites both of
                # those in the visitor's own timezone, and this sentence has
                # no clock in it to rewrite.
                .replace("__SWING__",
                         f'<p class="swing">{swing}</p>' if swing else "")
                .replace("__FACTS__", facts_html(c, a, facts, meta))
                .replace("__HOURS__", hours_table_html(name, a["week"]))
                .replace("__HISTORY__", hist_b)
                .replace("__SESSSPAN__", "sp4" if hist_b else "")
                .replace("__GTABS__", game_tabs(s, has))
                .replace("__CAT__", cat)
                .replace("__PLAY__", play)
                .replace("__SLUG__", s)
                .replace("__SITE__", html.escape(SITE))
                .replace("__VLABEL__", vlabel).replace("__VCOL__", vcol).replace("__VTEXT__", vtext)
                .replace("__SPARK__", sparkline(a["daily"], a["spikes"]))
                .replace("__ABOUT__", about_game_html(name, meta))
                .replace("__SIMILAR__", similar_html(c, cards))
                .replace("__GAMEINFO__", jsdata({"s": s, "n": name, "i": c["icon"] or ""}))
                .replace("__SHARED__", SHARED_JS)
                .replace("__FAVJS__", FAV_GAME)
                .replace("__NOTIFY__", NOTIFY_HTML)
                .replace("__PUSHJS__", PUSH_JS)
                # ptCountdowns() drives the "Next event in ..." line on the event
                # calendar. The quiet-window countdown in GAME_JS keeps its own
                # ticker, because that one also re-decides which hour it is
                # aiming at every five minutes.
                .replace("__JS__",
                         GAME_JS.replace("__DATA__", jsdata(a["week"])) + "ptCountdowns();")
                # __NAME__ last: it appears inside several of the blocks above.
                .replace("__NAME__", html.escape(name)))

        # The description leads with what the searches ask: how many updates, the
        # latest one, and when the next is likely.
        past_ev = sorted((e for e in (events or []) if (e["end"] or e["start"] + 86400) < now),
                         key=lambda e: -e["start"])
        nxt = next_update(pattern, now)
        upd_desc = (f"Every {name} update in order"
                    + (f": {len(past_ev)} since {when(past_ev[-1]['start'])}. Latest: "
                       f"{past_ev[0]['title']} ({when(past_ev[0]['start'])})." if past_ev else ".")
                    + (f" Next update likely {when(nxt)}." if nxt else "")
                    + " Changelog, update log and player count jumps.")
        write(f"updates/{s}.html", page(
            seo_title(f"{name} Updates in Order: Changelog & Next Update",
                      f"{name} Updates in Order & Changelog",
                      f"{name} Updates & Changelog",
                      f"{name} Updates"),
            f'<div class="ghead rise">{thumb(name, c["icon"], icon_alt(name), eager=True)}<div>'
            f'<h1>{html.escape(name)} updates in order</h1>'
            f'<p class="mut">The {html.escape(name)} changelog: every update and event the '
            f'creators have announced, when it landed, when the next one is likely, and the '
            f'days {html.escape(name)}&rsquo;s player count jumped.</p>'
            f'<div class="actions">{play}<span data-bell="all"></span>'
            f'<button class="fav" id="fav" data-s="{s}" aria-pressed="false">'
            f'&#9734; Save</button></div>'
            f'{game_tabs(s, has, "updates")}</div></div>'
            + (upd or '<div class="card"><p class="none">The creators have not announced any '
                      'updates on Roblox for this game yet, and we have not been watching long '
                      'enough to spot a jump in players. Check back soon.</p></div>')
            + calendar_html(name, events, now)
            + similar_updates_html(c, cards, latest_update, now)
            + f'<p><a href="/game/{s}">&larr; Back to {html.escape(name)}</a></p>'
            + f'<script>{SHARED_JS}</script>'
            + f'<script>var P={jsdata(pattern)};'
            + PATTERN_JS + 'ptCountdowns();</script>'
            + f'<script>window.PT_GAME={jsdata({"s": s, "n": name, "i": c["icon"] or ""})};</script>'
            # The Updates bell lives on this page, so the notification code has to be
            # here too. PT_GAME above it is what tells it which game it is looking at.
            + f'<script>{PUSH_JS}</script>',
            clip(upd_desc),
            wide=True, banner=c["banner"],
            canon=f"/updates/{s}", image=c["banner"] or c["icon"] or "",
            trail=trail + [(f"{name} player count", f"/game/{s}"),
                           ("Updates in order", f"/updates/{s}")],
            # An update page with nothing on it is a thin page, so we keep it on the
            # site (the button still works) but ask Google not to list it.
            noindex=thin or not upd or c["no_updates"], modified=iso_day(a["last"])))

        write(f"game/{s}.html", page(
            seo_title(*([f"{name} ({alias}) Player Count Today, Peak & Graph",
                         f"{name} ({alias}) Player Count & Peak"] if alias else [])
                      + [f"{name} Player Count Today, Peak & Graph",
                         f"{name} Player Count, Peak & Graph",
                         f"{name} Player Count Today",
                         f"{name} Player Count"]), body,
            # Leads with the numbers people search for in their own words - how many
            # right now, the record, the lowest - so the snippet answers the search.
            clip(f"{a['latest'][1]:,} people were playing {name}"
                 + (f" ({alias})" if alias else "") + " at our last check. "
                 f"Peak: {a['peak']:,}."
                 + (f" Lowest this week: {a['low7'][1]:,}." if a["low7"] else "")
                 + (f" {short(meta['visits'])} visits." if meta and meta.get("visits") else "")
                 + " Player count graph, busiest hours and best time to play."),
            wide=True, banner=c["banner"], back=where, canon=f"/game/{s}",
            image=c["banner"] or c["icon"] or "", trail=trail + [(name, f"/game/{s}")],
            # The questions and the events are written out on their own pages now,
            # so their structured data went with them: a FAQPage block on a page that
            # does not show the questions would be describing content that is not
            # there.
            schema=game_schema(c, a, meta, []),
            noindex=thin, modified=iso_day(a["last"])))

    print(f"Built {len(cards)} game pages.")

    # ---- the short list of games the search button loads. Kept separate from
    # data.json, which also carries a week of player counts per game and is far too
    # big to fetch just to search by name.
    write("games.json", json.dumps(
        [{"s": c["slug"], "n": c["name"], "i": c["icon"] or "", "k": search_key(c)}
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
    # Worked out once: every category page compares its own rhythm against it.
    all_share = share_week(cards)
    for g in sorted(cats):
        cg = [c for c in cards if c["genre"] == g]
        if not cg:
            continue
        cat_pages.append((g, f"/category/{slug(g)}"))
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
            + category_rhythm(g, cg, all_share)
            + '<p><a href="/">&larr; All Roblox player counts</a></p>'
            + ask_js(cg),
            clip(f"Player counts for {len(cg)} {g.lower()} games on Roblox, and when each one "
                 f"is busiest and quietest. Updated four times a day."),
            wide=True, banner=biggest["banner"], canon=f"/category/{slug(g)}",
            image=biggest["banner"] or biggest["icon"] or "",
            trail=[("All games", "/"), (f"{g} games", f"/category/{slug(g)}")],
            schema=[item_list(cg, f"{g} Roblox games by player count")]))
    pills = "".join(f'<a href="{u}">{html.escape(g)}</a>' for g, u in cat_pages)


    # ---- homepage
    # The readings count used to print here as well, as the reason to believe the
    # rest of the site. The owner would rather the page opened on the thing itself,
    # and nothing a search engine ranks on goes with it: the games tracked is still
    # in the lede, and every game page writes its own sample count out in full,
    # which is where anybody checking our working would look.
    top = cards[0] if cards else None
    body = (
        '<div class="hero rise"><h1>Roblox player counts and the <em>best times</em> to play</h1>'
        # One line, then the numbers underneath in small type. It was a four-line
        # paragraph that said the same thing three ways; the two numbers are still
        # here because they are the reason to believe the rest of the site, but they
        # are not what somebody arriving needs to read first.
        f'<p class="lede">The quietest and busiest hours for {len(cards)} Roblox games, '
        f'in your own timezone.</p>'
        f'</div>'
        '<input id="s" type="search" placeholder="Search for a game" aria-label="Search for a game">'
        # Phone only. On a computer these three are in the bar at the top of every
        # page; a phone's bar has no room for them, so on a phone they sit here, on
        # the page everybody starts on, directly under the search box.
        '<nav class="homenav" aria-label="Find games">'
        '<a href="/?for=busy" data-hn="busy">Busy now</a>'
        '<a href="/?for=quiet" data-hn="quiet">Quiet now</a>'
        '<a href="/popular" data-hn="popular">Popular</a></nav>'
        + ask_html()
        # The categories used to be a bare row of pills under the chooser, with nothing
        # saying what they were. On a phone they wrapped onto five lines, which read as
        # clutter rather than as a list you could use.
        + f'<h2 style="margin-top:22px">Browse by category</h2><div class="pills">{pills}</div>'
        '<section id="favs" hidden>' + row_head("Your saved games") +
        '<ul class="grid" id="favgrid"></ul></section>'
        + row_head("All games", f'<span class="mut small">{len(cards)} games</span>')
        + grid(cards, "all")
        # "What you can do here" was a list of the same links the panel holds, on the
        # page that needs them least: somebody on the homepage has the menu button a
        # thumb away. Taken out 17 Nov 2026 at the owner's request. The footer still
        # carries every one of them, so none of it is hidden from a search engine.
        + ('<h2 style="margin-top:30px">Where the numbers come from</h2>'
           '<div class="card"><p>Roblox shows how many people are in each game right now. '
           'We write that number down for every game on our list, about every 10 minutes, and '
           'we keep it. Roblox does not. It only ever shows you right now, never last Tuesday. '
           'Add our readings up by hour and by day and you can see each game\'s week. Compare '
           'one week with the next and you can see whether a game is growing or shrinking.</p>'
           '<p class="mut small">An average is our best guess, worked out from the readings we '
           'took. A highest player count is different: that is one real reading we saw. Nothing '
           'here says whether a game is good, fair or safe for a child.</p></div>')
        + ask_js(cards))
    write("index.html", page(
        f"Roblox Player Counts & Best Times to Play Games | {SITE}", body,
        "Track Roblox game player counts, discover the busiest and quietest times to play, "
        "explore trending games, and compare player activity throughout the day.",
        wide=True, nav="home", back=None, canon="/",
        image=top["icon"] if top else "",
        schema=[{"@type": "WebSite", "name": SITE, "url": abs_url("/"),
                 "description": ("Player counts and best times to play for popular Roblox "
                                 "games, updated four times a day."),
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
              f"typical moment over the last 7 days.",
              cards,
              "Roblox game rankings by live player count: the most played games we track, "
              "with typical and peak players for each. Updated four times a day.",
              listname="Most played Roblox games by typical player count")
    list_page("growing", seo_title("Roblox Games Growing Fastest This Week"),
              "Roblox games that are growing",
              "These games have more players than they did a week ago. We compare the last "
              "7 days of player counts with the 7 days before, four times a day.",
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
        f'<tr><td><a href="/game/{c["slug"]}">{html.escape(c["name"])}</a></td>'
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
        "own player count history and updated four times a day.",
        wide=True, nav="trending", canon="/trending",
        trail=[("All games", "/"), ("Trending", "/trending")],
        schema=[item_list(up[:12], "Roblox games trending up this week")] if up else None,
        noindex=not (up or down), modified=iso_day(now)))

    # ---- site-wide event calendar
    all_events.sort(key=lambda e: e["start"])
    live = [e for e in all_events if e["start"] <= now]
    soon = [e for e in all_events if e["start"] > now]

    def ev_list(items):
        out = []
        for e in items[:40]:
            out.append(f'<li class="{"live" if e["start"] <= now else "soon"}" '
                       f'data-s="{e["slug"]}">'
                       f'<b><a href="/game/{e["slug"]}">{html.escape(e["game"])}</a>: ' 
                       f'{html.escape(e["title"])}</b>'
                       + (f'<span class="d">{html.escape(e["subtitle"])}</span>'
                          if says_something(e["subtitle"]) else "")
                       + f'<span class="d">'
                       + (f'Happening now, ends {when(e["end"] or e["start"])}' if e["start"] <= now
                          else f'Starts {when(e["start"])}')
                       + '</span>'
                       # Filled in by PUSH_JS, and empty for anybody it cannot help.
                       # This is where somebody decides they want telling about a
                       # game: before this, the only bells on the site were on the
                       # game's own pages, which is a place they had to go and find.
                       + f'<span class="evbell" data-bell="events" '
                         f'data-s="{e["slug"]}" data-short></span>'
                       + '</li>')
        return f'<ul class="evt">{"".join(out)}</ul>' if out else ""

    write("events.html", page(
        seo_title("Roblox Events Today & Next: Game Events Calendar",
                  "Roblox Events Today & Next"),
        '<div class="hero"><h1>Roblox events today and coming up</h1><p class="lede">Events and updates the game creators '
        'themselves have put on the Roblox calendar, for every game we track. Expect these hours to be busy.</p></div>'
        '<section id="myevts" hidden><h2 style="margin-top:22px">Your saved games</h2>'
        '<ul class="evt"></ul>'
        '<p class="mut small">The bell on a row tells your browser about that '
        'game&rsquo;s events, about fifteen minutes before one starts. '
        '<a href="/notifications">All of yours are here</a>.</p></section>' 
        + (f'<h2 style="margin-top:22px">Roblox events happening now</h2>{ev_list(live)}' if live else "")
        + (f'<h2 style="margin-top:26px">Next Roblox events</h2>{ev_list(soon)}' if soon else "")
        + ("" if live or soon else '<p class="none">No events are listed right now. Creators usually '
                                   'announce them a few days ahead, so check back soon.</p>')
        + '<p><a href="/">&larr; All Roblox player counts</a></p>',
        clip(f"Roblox events today: {len(live)} happening now and {len(soon)} coming up across "
             f"{len(cards)} games, with the dates they run. The next Roblox events, updated four "
             f"times a day."),
        nav="events", canon="/events",
        tail=MYEVTS_JS + f'<script>{PUSH_JS}</script>',
        trail=[("All games", "/"), ("Events", "/events")],
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
        nav="compare", canon="/compare",
        trail=[("All games", "/"), ("Compare", "/compare")],
        tail=f"<script>{SHARED_JS}</script><script>{COMPARE_JS}</script>"))

    # ---- plan a session
    write("plan.html", page(
        seo_title("Best Time to Play: Next Quiet or Busy Hours"),
        '<div class="hero"><h1>Plan my Roblox session</h1><p class="lede">Pick a game and say whether you want it '
        'quiet or busy. We will count down to the next good stretch of time, on your own clock.</p></div>'
        '<div class="card" id="plan" hidden>'
        '<label>Game<br><select class="sel" id="g"></select></label>'
        '<p class="mut small" style="margin-top:14px">What do you want?</p>'
        '<div class="days" id="planbtns"><button data-m="quiet" aria-pressed="true">Quiet</button>'
        '<button data-m="busy" aria-pressed="false">Busy</button></div>'
        # Outside #out, which draw() rewrites from scratch every five minutes: a bell
        # living in there would be torn down mid-press. PLAN_JS points it at whichever
        # game is chosen, and it follows the Quiet/Busy buttons it sits under, the
        # same way the one on a game page follows that card. It is above the countdown
        # rather than under the twelve-hour table, which is most of a screen further
        # down and nowhere near the choice it belongs to.
        '<div id="planbell"><span data-bell="plan"></span></div>'
        '<div id="out"></div></div>'
        '<p class="mut small" id="load">Loading the games&hellip;</p>'
        + plan_help()
        + plan_table(cards)
        + '<p><a href="/busiest-hours">When is Roblox busiest overall?</a></p>'
        '<p><a href="/">&larr; All Roblox player counts</a></p>',
        "Find the next quiet or busy hours for any Roblox game, counted down in your own "
        "timezone from our hour-by-hour player count history.",
        nav="plan", canon="/plan",
        trail=[("All games", "/"), ("Plan a session", "/plan")],
        tail=f"<script>{SHARED_JS}</script><script>{PLAN_JS}</script>"
             f"<script>{PUSH_JS}</script>"))

    # ---- when is Roblox busiest, across everything we watch
    write("busiest-hours.html", busy_page(cards, now))

    # ---- the plain pages
    write("about.html", page(
        seo_title(f"About {SITE}: How We Measure Player Counts"), about_body(),
        f"What {SITE} is, how it measures when Roblox games are busy, and what it does not "
        f"tell you.", canon="/about",
        trail=[("All games", "/"), ("About", "/about")]))
    # noindex: it is a page about one person's own settings and is empty until the
    # browser fills it in, so there is nothing here for Google to list.
    write("notifications.html", page(
        seo_title(f"Your notifications - {SITE}"), notifications_body(),
        "Choose which games tell you when they are quiet, busy, or about to run an event.",
        canon="/notifications", noindex=True,
        trail=[("All games", "/"), ("Your notifications", "/notifications")],
        tail=f"<script>{PUSH_JS}</script>"))
    write("install.html", page(
        seo_title(f"Get {SITE} as an app on your phone"), install_body(),
        f"How to add {SITE} to your home screen on an iPhone, iPad, Android phone or "
        f"computer, and why notifications need it.", canon="/install",
        trail=[("All games", "/"), ("Get the app", "/install")]))
    write("privacy.html", page(
        seo_title(f"Privacy Policy - {SITE}"), privacy_body(),
        f"What {SITE} stores, what it never asks for, and how to delete your data.",
        canon="/privacy", trail=[("All games", "/"), ("Privacy Policy", "/privacy")]))
    write("terms.html", page(
        seo_title(f"Terms of Service - {SITE}"), terms_body(),
        f"The rules for using {SITE}, written in plain language: what the site is, what the "
        f"numbers mean, and why they are estimates rather than official Roblox figures.",
        canon="/terms",
        trail=[("All games", "/"), ("Terms of Service", "/terms")]))

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
        wide=True, back=None, canon="/404", noindex=True))

    # ---- sitemap and robots
    #
    # The sitemap is the list of pages we are asking Google to look at, so it holds
    # only pages that are worth looking at: a game still waiting for data is left out
    # until index_ok() says it has enough, and so is an empty list page. Addresses in
    # a sitemap have to be absolute, which is why DOMAIN has to be filled in before
    # this is any use at all.
    base = DOMAIN.rstrip("/")
    today = iso_day(now)
    pages = [("/", "1.0", today), ("/popular", "0.9", today)]
    for u in [u for _, _, u in TABS if u not in ("/", "/popular")]:
        pages.append((u, "0.7", today))
    pages.append(("/busiest-hours", "0.8", today))
    pages += [(u, "0.7", today) for _, u in cat_pages]
    for c in cards:
        if not index_ok(c):
            continue
        last = iso_day(c["a"]["last"])
        pages.append((f'/game/{c["slug"]}', "0.9", last))
        for folder in ("updates", "events", "passes", "questions"):
            empty = {"updates": "no_updates", "passes": "no_passes"}.get(folder)
            if c.get("has_" + folder) and not (empty and c.get(empty)):
                pages.append((f'/{folder}/{c["slug"]}', "0.5", last))
    pages += [("/about", "0.3", today), ("/install", "0.3", today),
              ("/privacy", "0.2", today), ("/terms", "0.2", today)]

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
        [{"s": c["slug"], "n": c["name"], "i": c["icon"] or "", "k": search_key(c)}
         for c in sorted(cards, key=lambda c: c["name"].lower())],
        separators=(",", ":")))
    # The events the worker needs to send event notifications. It cannot call Roblox
    # itself - that is a build-time job - and data.json holds a whole week of player
    # counts per game and is fetched by visitors on two pages, so this is its own
    # small file instead of being bolted onto that one. Only events that have not
    # started yet, since a notification about a finished event is noise.
    #
    # Freshness is a build apart (up to six hours). Creators announce events days
    # ahead, so that is comfortably enough; an event announced and starting inside
    # six hours is the one case this will miss.
    coming = {}
    for e in sorted(all_events, key=lambda e: e["start"]):
        if e["start"] <= now:
            continue
        coming.setdefault(e["slug"], [])
        if len(coming[e["slug"]]) < 12:
            coming[e["slug"]].append({"t": e["title"][:80], "s": int(e["start"])})
    # `updated` rides along in the same file: it is the same shape of thing (a per
    # game timestamp the worker cannot look up for itself) and a second request for a
    # few hundred numbers would be silly.
    write("events.json", json.dumps(
        {"built": int(now), "games": coming, "updated": last_update},
        separators=(",", ":")))
    write("favicon.svg", FAVICON)
    # The annotated screenshots for /install. Kept in brand/ and copied out as they
    # are: they were drawn on once, by hand, and nothing about them changes from
    # build to build, so the build needs no image library and the rule that the
    # build server installs nothing stays intact.
    shots = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brand", "install")
    if os.path.isdir(shots):
        for name in sorted(os.listdir(shots)):
            if name.endswith(".webp"):
                with open(os.path.join(shots, name), "rb") as f:
                    write_bytes(f"img/install/{name}", f.read())
    write("manifest.webmanifest", manifest_json())
    write("sw.js", PUSH_SW)
    # The icons are the same drawing at three sizes: two for the manifest, one for
    # Apple, which ignores SVG. Deterministic, so a rebuild leaves git alone.
    write_bytes("icon-192.png", app_icon(192))
    write_bytes("icon-512.png", app_icon(512, supersample=2))
    write_bytes("apple-touch-icon.png", app_icon(180))
    # data.json and games.json are left crawlable on purpose: the Compare and Plan
    # pages fetch them, and a search engine that cannot read them sees those two
    # pages as empty.
    # /auth/ is shut out alongside /admin and /api/, because everything under it is
    # a door rather than a page. Search Console caught Googlebot crawling
    # /auth/login on 14 Nov 2026 and filing it under "Page with redirect", which is
    # exactly what it is: a 302 off to Roblox. Googlebot runs our JavaScript, so the
    # sign-in button ptPaint() draws is a real link to it and being absent from the
    # served HTML protects nothing. Nothing under /auth/ belongs in an index, and a
    # crawler walking in also starts OAuth handshakes that nobody ever finishes.
    write("robots.txt", "User-agent: *\nDisallow: /\n" if NOINDEX else
          "User-agent: *\nDisallow: /admin\nDisallow: /api/\nDisallow: /auth/\nAllow: /\n\n"
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
