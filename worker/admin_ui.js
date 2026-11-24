/**
 * The admin dashboard: styles, skeleton and the script that fills it.
 *
 * It lives in its own module because index.js is a router and this is a small
 * application. The login page still uses index.js's own SHELL and bar(), so nothing
 * here can break the way in.
 *
 * TWO RULES THAT WILL TAKE THE WHOLE WORKER DOWN IF BROKEN, both learned the hard way:
 *
 *   1. NO BACKTICK may appear anywhere in the content below - not in the CSS, not in
 *      the script, not in a comment. The whole thing is inside backtick template
 *      literals, so one ends the string early. The inline script is therefore written
 *      with single quotes and concatenation, and must stay that way.
 *   2. NO CSS ESCAPE may be written either: a backslash followed by a digit reads as
 *      an octal escape, which is a syntax error in a module and takes the worker off
 *      the air. Where a glyph is needed, use the character itself or a browser
 *      default. Describe such escapes in words, never in symbols.
 *
 * The colours come from worker/theme.js, which build_site.py writes on every build, so
 * a palette change on the public site reaches this page on the next build and the two
 * cannot drift. Only the colours travel: the layout is this page's own, because the
 * site is for a visitor reading about one game and this is for one person reading
 * numbers.
 */

/* ------------------------------------------------------------------------ styles */

const CSS = `<style>
/* ---- how wide the page is allowed to be
   SHELL caps everything at 1100px, which is right for the sign-in form and far too
   narrow here: measured at 1100, 1500, 2000 and 2600px the reading column stayed 838px
   at every one, so the games table (1057px) could never fit and a 2560px monitor
   showed two thirds empty. This rule only reaches the dashboard, because this
   stylesheet is only emitted by dashboardBody() - the sign-in page keeps its 1100. */
.w{max-width:min(1560px,100%)}

/* ---- the frame: a sidebar on a wide screen, a scrolling strip on a narrow one */
.adm{display:grid;grid-template-columns:208px minmax(0,1fr);gap:22px;align-items:start}
@media(max-width:860px){.adm{grid-template-columns:minmax(0,1fr);gap:12px}}
.side{position:sticky;top:64px;display:flex;flex-direction:column;gap:2px}
@media(max-width:860px){
  .side{position:static;display:block;white-space:nowrap;overflow-x:auto;
  scrollbar-width:none;margin:0 -16px;padding:0 16px 4px}
  .side::-webkit-scrollbar{display:none}
  .side button{display:inline-flex;width:auto;margin-right:6px}
}
.side button{display:flex;align-items:center;gap:9px;width:100%;text-align:left;
border:1px solid transparent;background:none;color:var(--mut);cursor:pointer;
padding:9px 11px;border-radius:11px;font-size:.95rem;font-weight:600;line-height:1.2}
.side button:hover{color:var(--ink);background:var(--card)}
.side button[aria-selected=true]{color:var(--ink);background:var(--card);
border-color:var(--line);box-shadow:0 0 0 1px var(--line)}
.side .cnt{margin-left:auto;font-size:.72rem;font-weight:800;padding:1px 6px;
border-radius:999px;background:var(--acc);color:var(--btnink)}
@media(max-width:860px){.side .cnt{margin-left:6px}}

/* ---- cards and the grid they sit in */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(230px,100%),1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 16px}
.card.pad0{padding:0;overflow:hidden}
.card h2{font-size:1rem;margin:0 0 10px}
.sec{margin:0 0 16px}
.sec>h2{font-size:1.05rem;margin:22px 0 10px}
.row2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr));gap:12px}

/* ---- a KPI card */
.kpi{position:relative;background:var(--card);border:1px solid var(--line);
border-radius:16px;padding:13px 15px 11px;min-width:0}
.kpi .lbl{display:flex;align-items:center;gap:5px;color:var(--mut);font-size:.82rem;
font-weight:600;letter-spacing:.01em}
.kpi .big{font-size:1.75rem;font-weight:800;letter-spacing:-.02em;line-height:1.15;
margin:3px 0 0;overflow-wrap:anywhere}
.kpi .sub{color:var(--mut);font-size:.8rem;margin-top:2px}
.kpi .spk{margin-top:7px;height:28px}
.kpi .spk svg{display:block;width:100%;height:28px}
.delta{display:inline-flex;align-items:center;gap:3px;font-size:.8rem;font-weight:700;
padding:1px 7px;border-radius:999px;white-space:nowrap}
.delta.up{background:color-mix(in srgb,var(--l1) 42%,transparent);color:var(--ink)}
.delta.down{background:color-mix(in srgb,var(--l5) 42%,transparent);color:var(--ink)}
.delta.flat{background:var(--chip);color:var(--mut)}

/* ---- the little question mark that explains a number */
.why{width:15px;height:15px;flex:none;display:inline-grid;place-items:center;
border-radius:50%;border:1px solid var(--line);background:var(--chip);color:var(--mut);
font-size:.62rem;font-weight:800;cursor:help;line-height:1}
.tip{position:fixed;z-index:40;max-width:300px;padding:9px 11px;border-radius:11px;
background:var(--solid);border:1px solid var(--line);color:var(--ink);font-size:.82rem;
line-height:1.45;box-shadow:0 10px 34px rgba(0,0,0,.3);pointer-events:none;opacity:0;
transition:opacity .12s}
.tip.on{opacity:1}

/* ---- the insights list */
.ins{display:flex;flex-direction:column;gap:9px}
.ins .it{display:flex;gap:11px;padding:12px 14px;border-radius:14px;
background:var(--card);border:1px solid var(--line)}
.ins .dot{width:9px;height:9px;flex:none;margin-top:7px;border-radius:50%}
.ins .fault .dot{background:var(--l5)}
.ins .warn .dot{background:var(--l3)}
.ins .note .dot{background:var(--acc)}
.ins .todo .dot{background:var(--mut)}
.ins .fault{border-color:color-mix(in srgb,var(--l5) 55%,var(--line))}
.ins .warn{border-color:color-mix(in srgb,var(--l3) 45%,var(--line))}
.ins b{display:block;font-size:.95rem;margin-bottom:2px}
.ins p{margin:0;color:var(--mut);font-size:.87rem;line-height:1.5}
.ins .do{margin-top:5px;font-size:.84rem;color:var(--acc);font-weight:600}
.allclear{display:flex;gap:10px;align-items:center;padding:14px 16px;border-radius:14px;
background:var(--card);border:1px solid color-mix(in srgb,var(--l1) 50%,var(--line))}

/* ---- the date range picker */
.range{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0 0 14px}
.range button{border:1px solid var(--line);background:var(--card);color:var(--mut);
cursor:pointer;padding:6px 11px;border-radius:999px;font-size:.85rem;font-weight:600}
.range button:hover{color:var(--ink)}
.range button[aria-pressed=true]{background:var(--acc);border-color:var(--acc);
color:var(--btnink)}
.range input[type=date]{border:1px solid var(--line);background:var(--card);
color:var(--ink);border-radius:10px;padding:5px 9px;font-size:.85rem}
.range .gap{flex:1}

/* ---- notices */
.note-bar{display:flex;gap:10px;padding:11px 14px;border-radius:13px;font-size:.87rem;
line-height:1.5;background:color-mix(in srgb,var(--l3) 18%,var(--card));
border:1px solid color-mix(in srgb,var(--l3) 45%,var(--line));margin:0 0 14px}
.note-bar b{display:block}

/* ---- charts */
.chart{width:100%;height:auto;display:block;touch-action:none;border-radius:12px}
.chart:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.readout{min-height:1.4em;color:var(--mut);font-size:.85rem;margin:6px 0 0}
.cols{display:flex;align-items:flex-end;gap:6px;height:110px;margin-top:6px}
.cols .c{flex:1;min-width:0;display:flex;flex-direction:column;justify-content:flex-end;
align-items:center;gap:4px;height:100%}
.cols .bar2{width:100%;border-radius:6px 6px 2px 2px;
background:linear-gradient(180deg,var(--acc),color-mix(in srgb,var(--acc) 45%,transparent))}
.cols .bar2.dim{background:var(--chip)}
.cols .cl{color:var(--mut);font-size:.68rem;white-space:nowrap}
.brow{display:flex;flex-direction:column;gap:7px;margin-top:4px}
.brow .b{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;align-items:center}
.brow .bn{font-size:.86rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.brow .bv{font-size:.86rem;font-weight:700;text-align:right;white-space:nowrap}
.brow .bt{grid-column:1/-1;height:7px;border-radius:999px;background:var(--chip);overflow:hidden}
.brow .bf{height:100%;border-radius:999px;background:var(--acc)}
.brow .bf.alt{background:var(--alt)}
.stk{display:flex;align-items:flex-end;gap:3px;height:76px;margin-top:6px}
.stk .s{flex:1;min-width:0;display:flex;flex-direction:column;justify-content:flex-end;height:100%}
.stk .g{background:var(--l1)}
.stk .b{background:var(--l5)}
.stk .e{background:var(--chip);height:2px}

/* ---- status lights */
.lights{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(250px,100%),1fr));gap:12px}
.light{display:flex;gap:11px;align-items:flex-start;background:var(--card);
border:1px solid var(--line);border-radius:16px;padding:13px 15px}
.light .led{width:11px;height:11px;flex:none;margin-top:6px;border-radius:50%;
box-shadow:0 0 0 4px color-mix(in srgb,currentColor 22%,transparent)}
.light.ok .led{background:var(--l1);color:var(--l1)}
.light.bad .led{background:var(--l5);color:var(--l5)}
.light.warn .led{background:var(--l3);color:var(--l3)}
.light.idle .led{background:var(--mut);color:var(--mut)}
.light b{display:block;font-size:.95rem}
.light .ls{color:var(--mut);font-size:.82rem;line-height:1.5;margin-top:2px}

/* ---- tables */
.tw{overflow-x:auto;margin:0 -1px}
/* A sideways scroll control ABOVE a wide table. The games table is 200 rows deep, so
   the real scrollbar at the bottom is a screen and a half from the column headings you
   are trying to line something up with.

   It is DRAWN, not a second native scrollbar, and that is not decoration. Chrome here
   uses overlay scrollbars - measured, the strip and the table both report zero gutter
   (offsetHeight === clientHeight) - so a native bar is invisible until you are already
   scrolling. A control you cannot see is worse than no control: it is there, it works,
   and nobody can find it. This one is always visible, and works the same whatever the
   operating system does with scrollbars.

   Hidden by script when the table already fits, so it never takes space it has not
   earned. */
.tscroll{position:relative;height:9px;margin:0 0 3px;border-radius:999px;
background:var(--chip);cursor:pointer;touch-action:none}
.tscroll .th{position:absolute;top:0;bottom:0;left:0;min-width:30px;border-radius:999px;
background:var(--mut);transition:background .12s}
.tscroll:hover .th,.tscroll.drag .th{background:var(--acc)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;padding:9px 11px;border-bottom:1px solid var(--line);
white-space:nowrap}
th{color:var(--mut);font-size:.78rem;font-weight:700;text-transform:uppercase;
letter-spacing:.04em;position:sticky;top:0;background:var(--card);z-index:1}
th.s{cursor:pointer;user-select:none}
th.s:hover{color:var(--ink)}
th[aria-sort] .ar{opacity:1}
th .ar{opacity:0;font-size:.7rem;margin-left:3px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:color-mix(in srgb,var(--acc) 7%,transparent)}
tbody tr.clickable{cursor:pointer}
td .nm{max-width:230px;overflow:hidden;text-overflow:ellipsis;display:block}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.76rem;
font-weight:700;background:var(--chip);color:var(--mut)}
.pill.g{background:color-mix(in srgb,var(--l1) 40%,transparent);color:var(--ink)}
.pill.r{background:color-mix(in srgb,var(--l5) 40%,transparent);color:var(--ink)}
.pill.a{background:color-mix(in srgb,var(--l3) 40%,transparent);color:var(--ink)}

/* ---- controls */
.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 11px}
.tools input[type=search],.tools select{border:1px solid var(--line);background:var(--card);
color:var(--ink);border-radius:11px;padding:7px 11px;font-size:.88rem;min-width:0}
.tools input[type=search]{flex:1 1 180px}
.btn{border:1px solid var(--acc);background:var(--acc);color:var(--btnink);cursor:pointer;
padding:7px 13px;border-radius:11px;font-size:.87rem;font-weight:700;
text-decoration:none;display:inline-block}
.btn.ghost{background:var(--card);color:var(--ink);border-color:var(--line)}
.btn:disabled{opacity:.55;cursor:default}
.dl{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}

/* ---- the panel that opens for one game */
.sheet2{position:fixed;inset:0;z-index:35;display:none}
.sheet2.on{display:block}
.sheet2 .scrim2{position:absolute;inset:0;background:rgba(0,0,0,.45)}
.sheet2 .box{position:absolute;right:0;top:0;bottom:0;width:min(560px,100%);
background:var(--bg);border-left:1px solid var(--line);overflow-y:auto;padding:18px 18px 60px}
@media(max-width:620px){.sheet2 .box{width:100%}}
.sheet2 .x{position:absolute;right:14px;top:14px;width:34px;height:34px;display:grid;
place-items:center;border-radius:10px;border:1px solid var(--line);background:var(--card);
color:var(--ink);cursor:pointer;font-size:1.1rem;line-height:1}

/* ---- misc */
.kv{display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:.88rem;margin:0}
.kv dt{color:var(--mut)}
.kv dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
.empty{color:var(--mut);font-size:.88rem;padding:14px 2px;line-height:1.5}
.steps{counter-reset:s;list-style:none;padding:0;margin:8px 0 0}
.steps li{counter-increment:s;position:relative;padding:0 0 11px 32px;font-size:.89rem;
line-height:1.55;color:var(--mut)}
.steps li:before{content:counter(s);position:absolute;left:0;top:0;width:22px;height:22px;
display:grid;place-items:center;border-radius:50%;background:var(--acc);color:var(--btnink);
font-size:.75rem;font-weight:800}
.steps code{background:var(--chip);padding:1px 5px;border-radius:5px;font-size:.84em;
overflow-wrap:anywhere}
.ids{display:inline-block;margin-top:6px;background:var(--chip);padding:5px 9px;
border-radius:8px;font-size:.78rem;line-height:1.7;overflow-wrap:anywhere;
font-variant-numeric:tabular-nums}
.cmds{display:flex;flex-direction:column;gap:7px;margin:0 0 10px}
.cmds code{display:block;background:var(--chip);border:1px solid var(--line);
padding:9px 11px;border-radius:9px;font-size:.8rem;line-height:1.5;
overflow-wrap:anywhere;user-select:all}
.flag{font-size:.78rem;color:var(--mut);margin-top:3px}
.donelist{margin-top:14px}
.donelist summary{cursor:pointer;color:var(--mut);font-size:.88rem}
.todo{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--line)}
.todo input{margin-top:4px;width:18px;height:18px;flex:none;accent-color:var(--acc)}
.todo .tl{font-size:.93rem}
.todo .tn{color:var(--mut);font-size:.83rem;line-height:1.45}
</style>`;

/* ----------------------------------------------------------------------- skeleton */

const TABS = [
  ["overview", "Overview"],
  ["traffic", "Traffic"],
  ["games", "Games"],
  ["system", "System"],
  ["search", "Search"],
  ["people", "People"],
  ["checklist", "Checklist"]
];

const BODY = `
<h1 class="vh">PlayTime admin dashboard</h1>
<div class="adm">
  <nav class="side" role="tablist" aria-label="Sections">` +
  TABS.map((t, i) =>
    '<button role="tab" data-tab="' + t[0] + '" aria-selected="' + (i === 0) + '">' +
    '<span>' + t[1] + '</span><span class="cnt" id="cnt-' + t[0] + '" hidden></span></button>'
  ).join("") + `
  </nav>
  <main>` +
  TABS.map((t, i) =>
    '<div id="p-' + t[0] + '" role="tabpanel"' + (i ? " hidden" : "") + '>' +
    (i ? "" : '<p class="mut">Loading the numbers&hellip;</p>') + '</div>'
  ).join("") + `
  </main>
</div>
<div class="sheet2" id="gsheet" aria-hidden="true">
  <div class="scrim2" data-close></div>
  <div class="box" role="dialog" aria-label="Game detail">
    <button class="x" type="button" data-close aria-label="Close">&times;</button>
    <div id="gbox"></div>
  </div>
</div>
<div class="tip" id="tip" role="tooltip"></div>
<div class="tip" id="ctip" role="tooltip"></div>`;

/* ------------------------------------------------------------------------- script */

const JS = `<script>
/* Single quotes and concatenation throughout: this file is inside a template literal,
   so a backtick here would end it and take the worker down. */

var $ = function (s) { return document.querySelector(s); };
var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
var num = function (n) { return (Number(n) || 0).toLocaleString('en-GB'); };
var esc = function (s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
  });
};
/* 1,240 reads better as 1.2k on a cramped axis label. */
var kfmt = function (n) {
  n = Number(n) || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(n < 1e7 ? 1 : 0) + 'm';
  if (n >= 1e4) return Math.round(n / 1e3) + 'k';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
  return String(Math.round(n));
};
var secs = function (s) {
  s = Math.round(Number(s) || 0);
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm ' + ('0' + (s % 60)).slice(-2) + 's';
  return Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
};
/* Defined before ago(), which uses it. */
var plural = function (n, w) { return n + ' ' + w + (n === 1 ? '' : 's'); };
var ago = function (unix) {
  if (!unix) return 'never';
  var m = (Date.now() / 1000 - unix) / 60;
  if (m < 1) return 'just now';
  if (m < 60) return Math.round(m) + ' min ago';
  if (m < 48 * 60) return plural(Math.round(m / 60), 'hour') + ' ago';
  return plural(Math.round(m / 1440), 'day') + ' ago';
};
var agoIso = function (iso) { return iso ? ago(Date.parse(iso) / 1000) : 'never'; };

/* Every date the dashboard PRINTS is month/day/year, at the owner's request.
   Only the printing changes: the values themselves stay ISO everywhere they are
   stored, compared, put in a date input or sent to the server, because those
   have to sort and round-trip. Pass a date through usDate at the moment it is
   written into the page and nowhere earlier. */
var usDate = function (iso) {
  if (!iso) return '';
  var p = String(iso).slice(0, 10).split('-');
  return p.length === 3 ? p[1] + '/' + p[2] + '/' + p[0] : String(iso);
};
/* The same, with the clock, for the rows that list when something ran. UTC, as
   their column headings already say. */
var usWhen = function (ms, withYear) {
  var d = new Date(ms), z = function (n) { return (n < 10 ? '0' : '') + n; };
  return z(d.getUTCMonth() + 1) + '/' + z(d.getUTCDate()) +
    (withYear === false ? '' : '/' + d.getUTCFullYear()) +
    ' ' + z(d.getUTCHours()) + ':' + z(d.getUTCMinutes());
};
var day10 = function (back) {
  return new Date(Date.now() - back * 864e5).toISOString().slice(0, 10);
};

/* ------------------------------------------------------- what the page is showing */
var D = null;                      /* the last payload */
var RANGE = { from: day10(29), to: day10(0), key: '30' };
try {
  var saved = JSON.parse(localStorage.getItem('pt_admin_range') || 'null');
  if (saved && saved.from && saved.to) RANGE = saved;
} catch (e) {}
var TAB = 'overview';
try { TAB = localStorage.getItem('pt_admin_tab') || 'overview'; } catch (e) {}

/* ---------------------------------------------------------------------- the tooltip
   One floating box moved about, rather than a title attribute: a title does not
   appear on a touch screen and cannot hold a sentence comfortably. */
(function () {
  var tip = $('#tip'), shown = null;
  function place(el) {
    var t = el.getAttribute('data-why');
    if (!t) return;
    tip.textContent = t;
    tip.classList.add('on');
    var r = el.getBoundingClientRect();
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
    var top = r.top - h - 9;
    if (top < 8) top = r.bottom + 9;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
    shown = el;
  }
  function hide() { tip.classList.remove('on'); shown = null; }
  document.addEventListener('pointerover', function (e) {
    var el = e.target.closest && e.target.closest('[data-why]');
    if (el) place(el); else if (shown) hide();
  });
  document.addEventListener('pointerdown', function (e) {
    var el = e.target.closest && e.target.closest('[data-why]');
    if (el) { place(el); e.preventDefault(); } else hide();
  });
  addEventListener('scroll', hide, true);
  addEventListener('keydown', function (e) { if (e.key === 'Escape') hide(); });
})();

/* The floating box the charts use, placed at the POINTER rather than over an
   element, which is what the public site's graphs do and what was asked for.
   It is a second box rather than the one the question marks use: that one is
   positioned against an element and hides itself the moment the pointer is not
   over one, so a chart would have had to fight it on every move.

   Ported from tipShow() in build_site.py, including the two things that
   function learned the hard way. It is measured parked at the top left, because
   a fixed box near the right edge is squeezed by the edge and reports itself
   narrower than it is. And it flips to the left of the pointer once the pointer
   is past the middle of the chart, not merely at the edge of the screen - on a
   wide monitor the chart ends long before the screen does, and the box would
   otherwise sit over the very part of the line being read. */
function chartTip(html, cx, cy, box) {
  var t = $('#ctip');
  if (!t) return;
  t.innerHTML = html;
  t.style.left = '0px';
  t.style.top = '0px';
  t.classList.add('on');
  var de = document.documentElement, vw = de.clientWidth, vh = de.clientHeight;
  var w = t.offsetWidth, h = t.offsetHeight, pad = 14, edge = 8;
  var r = box && box.getBoundingClientRect ? box.getBoundingClientRect() : null;
  var flip = r && r.width ? cx > r.left + r.width / 2 : false;
  var x = flip ? cx - w - pad : cx + pad, y = cy - h - pad;
  if (x + w > vw - edge) x = cx - w - pad;
  if (x < edge) x = edge;
  if (y < edge) y = cy + pad;
  if (y + h > vh - edge) y = vh - h - edge;
  t.style.left = x + 'px';
  t.style.top = y + 'px';
}
function chartTipOff() { var t = $('#ctip'); if (t) t.classList.remove('on'); }

/* -------------------------------------------------------------------------- charts
   Built the same way the public site builds its day graph: an SVG line with a
   translucent wash under it, and a gap in the data BREAKS the line rather than being
   drawn as a zero we never recorded. */
var W = 720, H = 240, PAD = 26;
function lineChart(id, pts, hue, dots) {
  if (!pts.length) return '<p class="empty">Nothing recorded in this period.</p>';
  var vals = pts.map(function (p) { return p.n; });
  var max = Math.max.apply(null, vals.concat([1]));
  var step = pts.length > 1 ? (W - PAD * 2) / (pts.length - 1) : 0;
  var x = function (i) { return PAD + i * step; };
  var y = function (v) { return H - PAD - (v / max) * (H - PAD * 2); };
  /* Built run by run, exactly as dayGraph does it on the public site. A day we
     recorded nothing for ends the run, so the line AND the wash under it both
     break there. The wash used to be drawn in one sweep across every point,
     nulls included, which put solid colour under days we never recorded - the
     one thing the broken line was there to avoid. */
  var runs = [], cur = [];
  for (var i = 0; i < pts.length; i++) {
    if (pts[i].n === null || pts[i].n === undefined) {
      if (cur.length) runs.push(cur);
      cur = [];
    } else cur.push(i);
  }
  if (cur.length) runs.push(cur);
  /* A dot per reading, like the site. The site draws 24 of them across this
     width and has room; this chart can be asked for 90 days, where dots 8px
     apart stop being dots and become a bar. So they shrink, and below 11px of
     spacing they are left off and the line speaks for itself. */
  /* dots === false turns them off outright. The clicks chart asks for that: its
     numbers are small whole counts and most days are zero, so a dot per day came
     out as a scatter of specks along the bottom rather than as points on a line. */
  var dotr = dots === false ? 0 : (step >= 20 ? 4 : step >= 11 ? 3 : 0);
  var d = '', wash = '', dots = '';
  runs.forEach(function (r) {
    var seg = r.map(function (i, n) {
      return (n ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(pts[i].n).toFixed(1);
    }).join(' ');
    d += seg + ' ';
    if (r.length > 1) {
      wash += seg + ' L' + x(r[r.length - 1]).toFixed(1) + ' ' + (H - PAD) +
        ' L' + x(r[0]).toFixed(1) + ' ' + (H - PAD) + ' Z ';
    }
    if (dotr) r.forEach(function (i) {
      dots += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(pts[i].n).toFixed(1) +
        '" r="' + dotr + '" fill="var(--' + hue + ')" stroke="var(--ink)" ' +
        'stroke-width="1.5" vector-effect="non-scaling-stroke"/>';
    });
  });
  var gid = 'g-' + id;
  var ticks = '';
  [0, 0.5, 1].forEach(function (f) {
    var v = max * f, yy = y(v);
    ticks += '<line x1="' + PAD + '" y1="' + yy.toFixed(1) + '" x2="' + (W - PAD) +
      '" y2="' + yy.toFixed(1) + '" stroke="var(--line)" stroke-width="1"/>' +
      '<text x="' + (PAD - 5) + '" y="' + (yy + 4).toFixed(1) + '" text-anchor="end" ' +
      'fill="var(--mut)" font-size="11">' + kfmt(v) + '</text>';
  });
  var first = usDate(pts[0].day), last = usDate(pts[pts.length - 1].day);
  return '<svg class="chart" id="' + id + '" viewBox="0 0 ' + W + ' ' + H +
    '" tabindex="0" role="img" aria-label="Page views over time">' +
    '<defs><linearGradient id="' + gid + '" x1="0" x2="0" y1="0" y2="1">' +
    '<stop offset="0" stop-color="var(--' + hue + ')" stop-opacity=".42"/>' +
    '<stop offset="1" stop-color="var(--' + hue + ')" stop-opacity=".02"/></linearGradient></defs>' +
    ticks +
    (wash ? '<path d="' + wash + '" fill="url(#' + gid + ')"/>' : '') +
    '<path d="' + d + '" fill="none" stroke="var(--' + hue + ')" stroke-width="2.5" ' +
    'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>' + dots +
    '<text x="' + PAD + '" y="' + (H - 6) + '" fill="var(--mut)" font-size="11">' + first + '</text>' +
    '<text x="' + (W - PAD) + '" y="' + (H - 6) + '" text-anchor="end" fill="var(--mut)" ' +
    'font-size="11">' + last + '</text>' +
    '<line class="cz" x1="0" y1="' + PAD + '" x2="0" y2="' + (H - PAD) +
    '" stroke="var(--ink)" stroke-width="1.5" stroke-dasharray="4 4" opacity="0"/>' +
    '<circle class="cd" r="6.5" fill="var(--ink)" stroke="var(--' + hue + ')" ' +
    'stroke-width="2.5" vector-effect="non-scaling-stroke" opacity="0"/></svg>';
}

/* Drag, click, hover, touch-drag or arrow keys. The readout names the day and the
   number, because an SVG cannot be read by anything that reads text. */
function chartCursor(svg, out, pts, noun) {
  if (!svg || !pts.length) return;
  var zl = svg.querySelector('.cz'), dot = svg.querySelector('.cd');
  var step = pts.length > 1 ? (W - PAD * 2) / (pts.length - 1) : 0;
  var vals = pts.map(function (p) { return p.n; });
  var max = Math.max.apply(null, vals.concat([1]));
  var at = -1;
  var word = noun || 'page view';
  function show(i, e) {
    i = Math.max(0, Math.min(pts.length - 1, i));
    at = i;
    var p = pts[i];
    var x = PAD + i * step, y = H - PAD - (p.n / max) * (H - PAD * 2);
    zl.setAttribute('x1', x); zl.setAttribute('x2', x); zl.setAttribute('opacity', '.5');
    dot.setAttribute('cx', x); dot.setAttribute('cy', y); dot.setAttribute('opacity', '1');
    var dt = new Date(p.day + 'T00:00:00Z');
    var nm = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][dt.getUTCDay()];
    /* The line under the chart stays, and is the only readout a finger or the
       arrow keys get: on a touch screen the hand covers the point it is on, and
       a box under it would be behind the hand. */
    out.textContent = nm + ', ' + usDate(p.day) + ' (UTC): ' + plural(p.n, word);
    if (e && e.pointerType === 'mouse') {
      chartTip(nm + ', ' + usDate(p.day) + ' (UTC)<br><b>' + num(p.n) + '</b> ' +
        word + (p.n === 1 ? '' : 's'), e.clientX, e.clientY, svg);
    }
  }
  function fromEvent(e) {
    var r = svg.getBoundingClientRect();
    var cx = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
    return Math.round(((cx / r.width) * W - PAD) / (step || 1));
  }
  var down = false;
  svg.addEventListener('pointerdown', function (e) { down = true; show(fromEvent(e), e); });
  svg.addEventListener('pointermove', function (e) { if (down || e.pointerType === 'mouse') show(fromEvent(e), e); });
  addEventListener('pointerup', function () { down = false; });
  svg.addEventListener('pointerleave', chartTipOff);
  addEventListener('scroll', chartTipOff, true);
  svg.addEventListener('touchmove', function (e) { e.preventDefault(); show(fromEvent(e), e); }, { passive: false });
  svg.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight') { show(at + 1); e.preventDefault(); }
    if (e.key === 'ArrowLeft') { show(at < 0 ? pts.length - 1 : at - 1); e.preventDefault(); }
  });
}

/* The tiny line inside a KPI card. No axis, no labels: it is there for shape only. */
function spark(vals, hue) {
  vals = (vals || []).map(function (v) { return Number(v) || 0; });
  if (vals.length < 2) return '';
  var max = Math.max.apply(null, vals.concat([1]));
  var w = 120, h = 28, st = w / (vals.length - 1);
  var d = '';
  vals.forEach(function (v, i) {
    d += (i ? 'L' : 'M') + (i * st).toFixed(1) + ' ' + (h - 2 - (v / max) * (h - 5)).toFixed(1) + ' ';
  });
  return '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true">' +
    '<path d="' + d + '" fill="none" stroke="var(--' + hue + ')" stroke-width="2" ' +
    'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>';
}

function colBars(items) {
  if (!items.length) return '<p class="empty">Nothing to show yet.</p>';
  var max = Math.max.apply(null, items.map(function (i) { return i.v; }).concat([1]));
  return '<div class="cols">' + items.map(function (i) {
    var pc = Math.max(2, (i.v / max) * 100);
    return '<div class="c" data-why="' + esc(i.why || '') + '">' +
      '<div class="bar2' + (i.v ? '' : ' dim') + '" style="height:' + pc.toFixed(1) + '%"></div>' +
      '<span class="cl">' + esc(i.label) + '</span></div>';
  }).join('') + '</div>';
}

function barRows(items, cls) {
  if (!items.length) return '<p class="empty">Nothing to show yet.</p>';
  var max = Math.max.apply(null, items.map(function (i) { return i.v; }).concat([1]));
  return '<div class="brow">' + items.map(function (i) {
    return '<div class="b"><span class="bn" title="' + esc(i.label) + '">' + esc(i.label) +
      '</span><span class="bv">' + esc(i.right != null ? i.right : num(i.v)) + '</span>' +
      '<span class="bt"><span class="bf' + (cls ? ' ' + cls : '') + '" style="width:' +
      ((i.v / max) * 100).toFixed(1) + '%"></span></span></div>';
  }).join('') + '</div>';
}

/* Successes and failures per day, stacked. An empty day is a thin grey line rather
   than nothing, so the gap is visibly a day with no runs. */
function stackBars(days) {
  if (!days.length) return '';
  var max = Math.max.apply(null, days.map(function (d) { return d.ok + d.failed; }).concat([1]));
  return '<div class="stk">' + days.map(function (d) {
    var t = d.ok + d.failed;
    if (!t) return '<div class="s" data-why="' + usDate(d.day) + ': no runs"><div class="e"></div></div>';
    return '<div class="s" data-why="' + usDate(d.day) + ': ' + d.ok + ' ok, ' + d.failed + ' failed">' +
      (d.failed ? '<div class="b" style="height:' + ((d.failed / max) * 100).toFixed(1) + '%"></div>' : '') +
      '<div class="g" style="height:' + ((d.ok / max) * 100).toFixed(1) + '%"></div></div>';
  }).join('') + '</div>';
}

function ring(done, total, label) {
  var f = total ? done / total : 0, r = 34, c = 2 * Math.PI * r;
  return '<svg viewBox="0 0 90 90" style="width:90px;height:90px;display:block;margin:0 auto" ' +
    'role="img" aria-label="' + done + ' of ' + total + ' ' + label + '">' +
    '<circle cx="45" cy="45" r="' + r + '" fill="none" stroke="var(--chip)" stroke-width="9"/>' +
    '<circle cx="45" cy="45" r="' + r + '" fill="none" stroke="var(--acc)" stroke-width="9" ' +
    'stroke-linecap="round" stroke-dasharray="' + c.toFixed(1) + '" stroke-dashoffset="' +
    (c * (1 - f)).toFixed(1) + '" transform="rotate(-90 45 45)"/>' +
    '<text x="45" y="50" text-anchor="middle" font-size="17" font-weight="800" ' +
    'fill="var(--ink)">' + done + '/' + total + '</text></svg>';
}

/* ---------------------------------------------------------------------- a KPI card
   Every one carries the same four things: what it is, the number, how it compares
   with the period before, and a plain explanation of how it was worked out. */
function kpi(o) {
  var d = '';
  if (o.change === null || o.change === undefined) {
    /* Deliberately not "0%" and never an arrow: with nothing to compare against,
       any symbol here would be a claim we cannot support. */
    d = o.prevLabel ? '<span class="delta flat">no comparison</span>' : '';
  } else {
    var up = o.change > 0, flat = Math.abs(o.change) < 0.5;
    var good = o.lowerIsBetter ? !up : up;
    d = '<span class="delta ' + (flat ? 'flat' : (good ? 'up' : 'down')) + '">' +
      (flat ? 'level' : (up ? '+' : '') + Math.round(o.change) + '%') + '</span>';
  }
  return '<div class="kpi"><span class="lbl">' + esc(o.label) +
    (o.why ? '<span class="why" data-why="' + esc(o.why) + '" tabindex="0">?</span>' : '') +
    '</span><p class="big">' + esc(o.value) + '</p>' +
    '<p class="sub">' + d + (o.prevLabel ? ' <span>' + esc(o.prevLabel) + '</span>' : '') +
    (o.sub ? (d || o.prevLabel ? '<br>' : '') + esc(o.sub) : '') + '</p>' +
    (o.spark ? '<div class="spk">' + o.spark + '</div>' : '') + '</div>';
}

/* --------------------------------------------------------------------- the fetching */
function url() {
  return '/admin/data?from=' + RANGE.from + '&to=' + RANGE.to;
}
function load() {
  return fetch(url(), { headers: { accept: 'application/json' } })
    .then(function (r) {
      if (r.status === 401) { location.href = '/admin'; throw new Error('signed out'); }
      return r.json();
    })
    .then(function (d) { D = d; paint(); })
    .catch(function (e) {
      var p = $('#p-' + TAB);
      if (p) p.innerHTML = '<p class="empty">Could not load the numbers. ' + esc(e.message) + '</p>';
    });
}

/* ------------------------------------------------------------------- the date range */
var PRESETS = [
  ['7', 'Last 7 days', 6],
  ['30', 'Last 30 days', 29],
  ['90', 'Last 90 days', 89],
  ['365', 'Last 12 months', 364],
  ['all', 'All time', null]
];
function rangeBar() {
  var btns = PRESETS.map(function (p) {
    return '<button type="button" data-preset="' + p[0] + '" aria-pressed="' +
      (RANGE.key === p[0]) + '">' + p[1] + '</button>';
  }).join('');
  return '<div class="range">' + btns +
    '<span class="gap"></span>' +
    '<input type="date" id="rf" value="' + RANGE.from + '" aria-label="From" max="' + day10(0) + '">' +
    '<input type="date" id="rt" value="' + RANGE.to + '" aria-label="To" max="' + day10(0) + '">' +
    '<button type="button" id="rgo">Apply</button></div>';
}
/* A 24-hour option is deliberately absent: page views are recorded against a DAY, so
   an hourly figure would have to be invented. */
function wireRange() {
  $$('.range [data-preset]').forEach(function (b) {
    b.onclick = function () {
      var p = PRESETS.filter(function (x) { return x[0] === b.dataset.preset; })[0];
      RANGE = p[2] === null
        ? { from: (D && D.range && D.range.views && D.range.views.all_time ? '2026-10-01' : day10(400)), to: day10(0), key: 'all' }
        : { from: day10(p[2]), to: day10(0), key: p[0] };
      save(); load();
    };
  });
  var go = $('#rgo');
  if (go) go.onclick = function () {
    var f = $('#rf').value, t = $('#rt').value;
    if (!f || !t) return;
    RANGE = { from: f, to: t, key: 'custom' };
    save(); load();
  };
  function save() { try { localStorage.setItem('pt_admin_range', JSON.stringify(RANGE)); } catch (e) {} }
}
function windowWords() {
  var w = D.range.window;
  return w.days === 1 ? usDate(w.from)
    : (usDate(w.from) + ' to ' + usDate(w.to) + ', ' + w.days + ' days');
}
</script>`;

export function dashboardBody() {
  return CSS + BODY + JS + PANELS;
}

/* The panel renderers are a second script block purely to keep each file section a
   readable length; they share the same global scope as the one above. */
const PANELS = `<script>
/* ===================================================================== OVERVIEW */
function pOverview() {
  var r = D.range, v = r.views, rd = r.reading, st = D.stats || {}, t = st.totals || {};
  var ops = D.ops || {};
  var cards = [];

  cards.push(kpi({
    label: 'Page views', value: num(v.value),
    change: v.change, prevLabel: 'vs ' + num(v.prev) + ' before',
    sub: num(Math.round(v.per_day || 0)) + ' a day on average',
    spark: spark(v.series.map(function (s) { return s.n; }), 'acc'),
    why: 'Every page opened in this period, counted once per load. There is no visitor ' +
      'identifier anywhere on this site, so this counts VIEWS and never people. ' +
      'Compared against the ' + r.window.days + ' days immediately before.'
  }));

  cards.push(kpi({
    label: 'Average time on a page',
    value: rd.average === null ? 'no readings' : secs(rd.average),
    change: rd.change_average,
    prevLabel: rd.prev_average === null ? '' : 'vs ' + secs(rd.prev_average),
    sub: num(rd.reads) + ' completed reads',
    why: 'Total seconds pages were open and being looked at, divided by the number of ' +
      'visits that reported a time. A visit that leaves instantly reports nothing, so ' +
      'this is the average of real reads rather than of all views.'
  }));

  cards.push(kpi({
    label: 'Games tracked', value: num(t.games_tracked || 0),
    change: null,
    sub: num(t.pages_built || 0) + ' have enough data for a page',
    why: 'Universe IDs in games.txt that Roblox answered for at the last build. A game ' +
      'needs ' + num((st.site || {}).min_samples || 200) + ' readings before it gets a ' +
      'page, which takes about a day and a half, so this is always a little ahead.'
  }));

  cards.push(kpi({
    label: 'Player readings taken', value: kfmt(t.samples || 0),
    change: null,
    sub: D.live && D.live.updated ? 'last ' + ago(D.live.updated) : 'from the last build',
    spark: '',
    why: 'Individual player-count samples in the database. The collector takes three ' +
      'readings ten minutes apart every half hour, so about 48 a day per game.'
  }));

  var g = D.gsc || {};
  if (g.state === 'ok') {
    cards.push(kpi({
      label: 'Google clicks', value: num(g.totals.clicks),
      change: null,
      sub: num(g.totals.impressions) + ' times shown in results',
      why: 'From Google Search Console, for ' + esc(usDate(g.from)) + ' to ' + esc(usDate(g.to)) +
        '. Google finalises these two to three days late, so the window ends three days ago.'
    }));
  }

  var coll = (ops.workflows || []).filter(function (w) { return w.key === 'collect'; })[0];
  if (coll) {
    cards.push(kpi({
      label: 'Collector', value: coll.overdue ? 'stopped' : 'running',
      change: null,
      sub: 'last ran ' + ago(coll.last_run && coll.last_run.at),
      why: 'Whether the job that gathers player counts is keeping to its schedule of ' +
        'every ' + coll.every + ' minutes. Read from GitHub Actions, which is where it runs.'
    }));
  }

  return '<h2 class="vh">Overview</h2>' + rangeBar() +
    insightsHtml() +
    '<div class="sec"><h2>' + esc(windowWords()) + '</h2>' +
    '<div class="cards">' + cards.join('') + '</div></div>' +
    '<div class="sec"><h2>Page views over time</h2><div class="card">' +
    lineChart('ovchart', v.series, 'acc') +
    '<p class="readout" id="ovread">Drag across the chart, or use the arrow keys, to read a day.</p>' +
    '</div></div>' + lightsHtml();
}

function insightsHtml() {
  var list = D.insights || [];
  if (!list.length) {
    return '<div class="sec"><div class="allclear"><span>&#10003;</span><span>' +
      '<b>Nothing needs doing.</b> <span class="mut">The back end is keeping to its ' +
      'schedule, the data is fresh and no setting is out of place.</span></span></div></div>';
  }
  return '<div class="sec"><h2>Needs attention</h2><div class="ins">' +
    list.map(function (i) {
      return '<div class="it ' + i.severity + '"><span class="dot"></span><div>' +
        '<b>' + esc(i.title) + '</b><p>' + esc(i.why) + '</p>' +
        (i.action ? '<p class="do">' + esc(i.action) + '</p>' : '') + '</div></div>';
    }).join('') + '</div></div>';
}

function lightsHtml() {
  var ops = D.ops || {};
  if (!ops.available) return '';
  return '<div class="sec"><h2>Back end</h2><div class="lights">' +
    (ops.workflows || []).map(function (w) {
      var cls = w.overdue ? 'bad'
        : (w.last_run && w.last_run.ok === 0 ? 'warn'
        : (w.last_run ? 'ok' : 'idle'));
      return '<div class="light ' + cls + '"><span class="led"></span><div>' +
        '<b>' + esc(w.label) + '</b><div class="ls">' +
        (w.last_run ? 'Ran ' + ago(w.last_run.at) +
          (w.last_run.ok === 0 ? ' and failed' : '') : 'No run recorded') +
        '<br>' + w.window.ok + ' of ' + w.window.runs + ' ok in 30 days' +
        (w.median_secs ? '<br>Takes about ' + secs(w.median_secs) : '') +
        '</div></div></div>';
    }).join('') + '</div></div>';
}

/* ====================================================================== TRAFFIC */
function pTraffic() {
  var r = D.range, v = r.views, rd = r.reading;
  var wk = (r.weekday || []).map(function (b) {
    return {
      label: b.label.slice(0, 3), v: b.average === null ? 0 : b.average,
      why: b.label + ': ' + num(b.n) + ' views across ' + plural(b.days, 'day') +
        (b.average === null ? '' : ', averaging ' + (Math.round(b.average * 10) / 10) + ' a day')
    };
  });
  var kinds = (r.kinds || []).map(function (k) { return { label: k.kind, v: k.n }; });
  var top = (r.pages || []).slice(0, 12).map(function (p) {
    return {
      label: p.path, v: p.n,
      right: num(p.n) + (p.average === null ? '' : '  (' + secs(p.average) + ')')
    };
  });

  var movers = '';
  {
    var ms = (r.movers || []).filter(function (m) { return m.change !== null; });
    var up = ms.slice().sort(function (a, b) { return b.change - a.change; }).slice(0, 8);
    var dn = ms.slice().sort(function (a, b) { return a.change - b.change; }).slice(0, 8);
    var newOnes = (r.movers || []).filter(function (m) { return m.change === null && m.recent > 0; });
    movers = '<div class="row2">' +
      '<div class="card"><h2>Climbing</h2>' + barRows(up.map(function (m) {
        return { label: m.path, v: m.recent, right: '+' + Math.round(m.change) + '%' };
      })) + '</div>' +
      '<div class="card"><h2>Falling</h2>' + barRows(dn.map(function (m) {
        return { label: m.path, v: m.recent, right: Math.round(m.change) + '%' };
      }), 'alt') + '</div></div>' +
      (newOnes.length ? '<p class="flag">' + plural(newOnes.length, 'page') +
        ' had views this period and none before, so they have no percentage to show: ' +
        esc(newOnes.slice(0, 5).map(function (m) { return m.path; }).join(', ')) +
        (newOnes.length > 5 ? ' and more' : '') + '.</p>' : '');
  }

  return '<h2 class="vh">Traffic</h2>' + rangeBar() +
    '<div class="cards">' +
    kpi({ label: 'Page views', value: num(v.value), change: v.change,
      prevLabel: 'vs ' + num(v.prev) + ' before',
      why: 'Page loads in this period. Not people: nothing here can tell one visitor from another.' }) +
    kpi({ label: 'Different pages opened', value: num(v.pages_touched), change: null,
      sub: 'of ' + num(((D.stats || {}).totals || {}).pages_built || 0) + ' built',
      why: 'How many distinct addresses were opened at least once. A low number against the ' +
        'pages built means most of the site is never reached.' }) +
    kpi({ label: 'Total time spent reading', value: secs(rd.seconds), change: rd.change_seconds,
      prevLabel: 'vs ' + secs(rd.prev_seconds),
      why: 'Every second a page was open and in front of somebody, added up. Sent when a ' +
        'visitor leaves the page; capped at an hour so a tab left open all day is ignored.' }) +
    kpi({ label: 'Average read', value: rd.average === null ? 'no readings' : secs(rd.average),
      change: rd.change_average,
      why: 'Total reading seconds divided by completed reads.' }) +
    '</div>' +
    '<div class="sec"><h2>Page views over time</h2><div class="card">' +
    lineChart('trchart', v.series, 'acc') +
    '<p class="readout" id="trread">Drag across the chart to read a day.</p></div></div>' +
    '<div class="row2">' +
    '<div class="card"><h2>By day of the week</h2>' + colBars(wk) +
    '<p class="flag">Average views per day, so a period holding two Mondays and one ' +
    'Tuesday does not read as Monday being busier.</p></div>' +
    '<div class="card"><h2>What kind of page</h2>' + barRows(kinds) + '</div></div>' +
    '<div class="sec"><h2>Most opened pages</h2><div class="card">' + barRows(top) +
    '<p class="flag">Reading time in brackets, where any was recorded.</p></div></div>' +
    '<div class="sec"><h2>Rising and falling game pages</h2>' + movers + '</div>' +
    dl([['traffic', 'Page views by day'], ['pages', 'Page views by page']]);
}

/* ======================================================================== GAMES */
var GSORT = { by: 'avg7', dir: -1 }, GQ = '', GFILTER = '';
function pGames() {
  var st = D.stats || {}, t = st.totals || {};
  var views = {}, time = {};
  (D.gameViews || []).forEach(function (v) { views[v.path] = Number(v.n) || 0; });
  (D.gameTime || []).forEach(function (v) { time[v.path] = v; });
  var live = {};
  ((D.live || {}).games || []).forEach(function (g) { live[String(g.id)] = g; });

  var rows = (st.games || []).map(function (g) {
    var path = '/game/' + g.slug, l = live[String(g.id)];
    return {
      id: g.id, name: g.name, slug: g.slug, genre: g.genre || '',
      samples: g.samples || 0, days: g.days || 0, avg7: g.avg7 || 0,
      trend: (typeof g.trend === 'number') ? g.trend : null,
      verdict: g.verdict || '', events: g.events || 0, upcoming: g.upcoming || 0,
      views: views[path] || 0,
      seconds: (time[path] || {}).seconds || 0,
      last: l && l.last ? l.last : null
    };
  });

  var genres = {};
  rows.forEach(function (r) { if (r.genre) genres[r.genre] = 1; });

  var shown = rows.filter(function (r) {
    if (GFILTER === 'stale' && r.last && (Date.now() / 1000 - r.last) < 7200) return false;
    if (GFILTER === 'stale' && !r.last) return true;
    if (GFILTER && GFILTER !== 'stale' && r.genre !== GFILTER) return false;
    if (!GQ) return true;
    return (r.name + ' ' + r.slug + ' ' + r.id).toLowerCase().indexOf(GQ) > -1;
  });
  shown.sort(function (a, b) {
    var x = a[GSORT.by], y = b[GSORT.by];
    /* A game with no trend yet sorts to the BOTTOM rather than counting as zero, which
       would rank it among the flat ones as though we knew it was flat. */
    if (x === null && y === null) return a.name.localeCompare(b.name);
    if (x === null) return 1;
    if (y === null) return -1;
    if (typeof x === 'string') return GSORT.dir * x.localeCompare(y) || a.name.localeCompare(b.name);
    return GSORT.dir * (x - y) || a.name.localeCompare(b.name);
  });

  var cols = [
    ['name', 'Game', ''], ['genre', 'Category', ''], ['avg7', 'Players (avg)', 'n'],
    ['trend', 'Trend', 'n'], ['views', 'Page views', 'n'], ['samples', 'Readings', 'n'],
    ['days', 'Days', 'n'], ['last', 'Last reading', 'n']
  ];
  var head = cols.map(function (c) {
    return '<th class="s ' + c[2] + '" data-sort="' + c[0] + '"' +
      (GSORT.by === c[0] ? ' aria-sort="' + (GSORT.dir < 0 ? 'descending' : 'ascending') + '"' : '') +
      '>' + c[1] + '<span class="ar">' + (GSORT.dir < 0 ? '▼' : '▲') + '</span></th>';
  }).join('');

  var body = shown.map(function (r) {
    var stale = !r.last || (Date.now() / 1000 - r.last) > 7200;
    return '<tr class="clickable" data-game="' + esc(r.slug) + '">' +
      '<td><span class="nm">' + esc(r.name) + '</span></td>' +
      '<td>' + esc(r.genre || '-') + '</td>' +
      '<td class="n">' + kfmt(r.avg7) + '</td>' +
      '<td class="n">' + (r.trend === null ? '<span class="mut">too new</span>' :
        '<span class="pill ' + (r.trend > 3 ? 'g' : (r.trend < -3 ? 'r' : '')) + '">' +
        (r.trend > 0 ? '+' : '') + r.trend.toFixed(1) + '%</span>') + '</td>' +
      '<td class="n">' + num(r.views) + '</td>' +
      '<td class="n">' + num(r.samples) + '</td>' +
      '<td class="n">' + (r.days ? r.days.toFixed(1) : '-') + '</td>' +
      '<td class="n">' + (stale ? '<span class="pill a">' + ago(r.last) + '</span>' : ago(r.last)) +
      '</td></tr>';
  }).join('');

  return '<h2 class="vh">Games</h2>' +
    '<div class="cards">' +
    kpi({ label: 'Tracked', value: num(t.games_tracked || 0), change: null,
      sub: num(t.pages_built || 0) + ' with pages',
      why: 'IDs in games.txt that Roblox answered for at the last build.' }) +
    kpi({ label: 'Ready for a trend', value: num(t.trend_ready || 0), change: null,
      sub: 'need 14 days of history',
      why: 'Games with at least fourteen days of readings, which is the minimum before ' +
        'a rising or falling trend means anything.' }) +
    kpi({ label: 'With an event calendar', value: num(t.with_events || 0), change: null,
      sub: num(t.upcoming_events || 0) + ' events still to come',
      why: 'Games whose creators publish events on Roblox. We show their calendar; we do ' +
        'not invent one.' }) +
    kpi({ label: 'Readings', value: kfmt(t.samples || 0), change: null,
      why: 'Total player-count samples across every tracked game.' }) +
    '</div>' +
    deadIds() +
    '<div class="sec"><h2>Every tracked game</h2>' +
    '<div class="tools">' +
    '<input type="search" id="gq" placeholder="Search by name or ID" value="' + esc(GQ) + '">' +
    '<select id="gf"><option value="">All categories</option>' +
    '<option value="stale"' + (GFILTER === 'stale' ? ' selected' : '') + '>Needs attention (no recent reading)</option>' +
    Object.keys(genres).sort().map(function (x) {
      return '<option' + (GFILTER === x ? ' selected' : '') + '>' + esc(x) + '</option>';
    }).join('') + '</select>' +
    '<span class="mut small">' + num(shown.length) + ' shown</span></div>' +
    '<div class="card pad0">' +
    '<div class="tscroll" id="gtop" aria-hidden="true" hidden><span class="th"></span></div>' +
    '<div class="tw"><table><thead><tr>' + head + '</tr></thead>' +
    '<tbody id="gbody">' + (body || '<tr><td colspan="8" class="empty">No game matches that.</td></tr>') +
    '</tbody></table></div></div>' +
    '<p class="flag">Click any row for that game on its own. Players (avg) is the mean ' +
    'over the last seven days; a game with under fourteen days of history shows no trend ' +
    'rather than a number we do not trust.</p></div>' +
    dl([['games', 'Every game']]);
}

/* Game IDs Roblox will not answer for.

   They are deliberately LEFT in games.txt rather than removed: a game made private can
   be made public again, and because the collector keeps asking, such a game simply
   starts recording again by itself with nobody doing anything. The only cost is one
   lookup a run. So the owner can hide the ones they already know about, and hiding is
   PER ID rather than a switch for the whole warning - a game that dies next month is
   still news, and a warning turned off wholesale would never say so. */
function deadIds() {
  var hid = (D.hidden_ids || []).map(String);
  var m = D.missing || {};
  var confirmed = (m.confirmed || ((D.stats || {}).missing_ids || [])).map(String);
  var waiting = (m.waiting || []).map(String);
  var open = confirmed.filter(function (id) { return hid.indexOf(id) < 0; });
  var parts = '';

  /* Games added in the last day that the collector has not reached yet. This is the
     normal state every morning after discover.py runs and is NOT a fault, so it is a
     plain note rather than a warning - see trackMissing() in index.js. */
  if (waiting.length) {
    parts += '<p class="flag" style="margin-top:14px">' + plural(waiting.length, 'newly added game') +
      ' not collected yet. That is normal for a day or so after they are found, and ' +
      'resolves on its own.</p>';
  }

  if (open.length) {
    parts += '<div class="note-bar" style="margin-top:14px"><span>&#9888;</span><span>' +
      '<b>' + plural(open.length, 'ID') + ' Roblox will not answer for.</b> ' +
      'Usually the game was deleted or made private. They stay in games.txt on purpose: ' +
      'if the game comes back, it starts recording again on its own.<br>' +
      '<code class="ids">' + esc(open.join('  ')) + '</code><br>' +
      '<button class="btn ghost" id="hideids" type="button" style="margin-top:8px">' +
      'Hide these</button> <span class="mut small" id="hidemsg">They will keep being ' +
      'tracked - this only stops the warning.</span></span></div>';
  }

  if (hid.length) {
    parts += '<details class="donelist" style="margin-top:10px"><summary>' +
      plural(hid.length, 'hidden ID') + ', still tracked in case the game comes back' +
      '</summary><p class="mut small" style="margin:8px 0 6px">Nothing was removed from ' +
      'games.txt. Each is still asked about on every run, so one that goes public again ' +
      'will start recording with no action from you.</p>' +
      '<code class="ids">' + esc(hid.join('  ')) + '</code><br>' +
      '<button class="btn ghost" id="showids" type="button" style="margin-top:8px">' +
      'Show them again</button></details>';
  }
  /* Everything confirmed is hidden: say so, rather than leaving the section blank and
     looking as though the check never ran.
     This line referred to a variable that the rewrite above had removed, which threw a
     ReferenceError and lost the whole Games tab - but ONLY when nothing was left
     unhidden, because the condition short-circuits before reaching it otherwise. Three
     browser checks caught it; reading the code did not. */
  if (!open.length && hid.length) {
    parts += '<p class="flag">No new dead IDs since you last looked.</p>';
  }
  return parts;
}

/* One game on its own, in a panel rather than a page: it is a detail of the table and
   going somewhere else would lose the sort and the search. */
function openGame(slug) {
  var st = D.stats || {};
  var g = (st.games || []).filter(function (x) { return x.slug === slug; })[0];
  if (!g) return;
  var path = '/game/' + slug;
  var views = ((D.gameViews || []).filter(function (v) { return v.path === path; })[0] || {}).n || 0;
  var tm = (D.gameTime || []).filter(function (v) { return v.path === path; })[0] || {};
  var l = ((D.live || {}).games || []).filter(function (x) { return String(x.id) === String(g.id); })[0];
  var sub = ['questions', 'events', 'passes', 'updates'].map(function (k) {
    var p = '/' + k + '/' + slug;
    var n = ((D.gameViews || []).filter(function (v) { return v.path === p; })[0] || {}).n || 0;
    return { label: p, v: n };
  });
  /* The sub-page views are not in gameViews (which is only /game/), so they come back
     as zero here. Said plainly rather than drawn as a real zero. */
  $('#gbox').innerHTML =
    '<h2 style="margin:0 36px 2px 0">' + esc(g.name) + '</h2>' +
    '<p class="mut small" style="margin:0 0 14px">' + esc(g.genre || 'no category') +
    ' &middot; universe ' + esc(g.id) + ' &middot; <a href="https://playtimestats.com' +
    esc(path) + '" target="_blank" rel="noopener">open the page</a></p>' +
    '<div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(min(150px,100%),1fr))">' +
    kpi({ label: 'Players (7-day avg)', value: kfmt(g.avg7), change: null,
      why: 'Mean player count across our readings for the last seven days.' }) +
    kpi({ label: 'Trend', value: (typeof g.trend === 'number' ? (g.trend > 0 ? '+' : '') + g.trend.toFixed(1) + '%' : 'too new'),
      change: null, sub: esc(g.verdict || ''),
      why: 'Change over the last 45 days. Needs fourteen days of history before it is shown.' }) +
    kpi({ label: 'Page views', value: num(views), change: null,
      sub: (tm.seconds ? secs(tm.seconds) + ' read' : 'no reading time yet'),
      why: 'Views of this game page in the period the dashboard is set to.' }) +
    '</div>' +
    '<h3>The numbers behind it</h3><dl class="kv">' +
    '<dt>Readings taken</dt><dd>' + num(g.samples) + '</dd>' +
    '<dt>Days of history</dt><dd>' + (g.days ? g.days.toFixed(1) : '-') + '</dd>' +
    '<dt>Last reading</dt><dd>' + (l && l.last ? ago(l.last) : 'unknown') + '</dd>' +
    '<dt>First reading</dt><dd>' + (l && l.first ? usDate(new Date(l.first * 1000).toISOString()) : 'unknown') + '</dd>' +
    '<dt>Events published</dt><dd>' + num(g.events) + '</dd>' +
    '<dt>Still to come</dt><dd>' + num(g.upcoming) + '</dd>' +
    '<dt>Slug</dt><dd>' + esc(g.slug) + '</dd></dl>' +
    '<h3>Its other pages</h3>' + barRows(sub) +
    '<p class="flag">Views for the four sub-pages are counted in the Traffic tab’s page ' +
    'list; this panel reads only the main game page, so a zero here means not measured ' +
    'rather than not visited.</p>';
  var sh = $('#gsheet');
  sh.classList.add('on');
  sh.setAttribute('aria-hidden', 'false');
}

/* ======================================================================= SYSTEM */
function pSystem() {
  var ops = D.ops || {};
  if (!ops.available) {
    return '<h2 class="vh">System</h2><p class="empty">Nothing is recording the back end yet. ' +
      'Run worker/schema_ops.sql against the database and press Refresh.</p>';
  }
  var st = D.stats || {}, live = D.live || {};
  var cards = (ops.workflows || []).map(function (w) {
    var a = w.all_time || {};
    var rate = w.window.runs ? Math.round((w.window.ok / w.window.runs) * 100) : null;
    var cls = w.overdue ? 'bad' : (w.last_run && w.last_run.ok === 0 ? 'warn' : (w.last_run ? 'ok' : 'idle'));
    return '<div class="card"><div class="light ' + cls +
      '" style="border:0;background:none;padding:0;margin-bottom:10px">' +
      '<span class="led"></span><div><b>' + esc(w.label) + '</b>' +
      '<div class="ls">' + (w.every_real
        ? 'Runs about every ' + Math.round(w.every_real / 60) + ' minutes'
        : 'Scheduled every ' + w.every + ' minutes') +
      (w.overdue ? ' &middot; <strong>overdue</strong>' : '') + '</div></div></div>' +
      '<dl class="kv">' +
      '<dt>Last run</dt><dd>' + (w.last_run ? ago(w.last_run.at) : 'never') + '</dd>' +
      '<dt>Result</dt><dd>' + (w.last_run
        ? (w.last_run.ok === 1 ? '<span class="pill g">ok</span>'
          : (w.last_run.ok === 0 ? '<span class="pill r">failed</span>'
            : '<span class="pill">running</span>'))
        : '-') + '</dd>' +
      '<dt>Last success</dt><dd>' + ago(w.last_success) + '</dd>' +
      '<dt>Asks to run</dt><dd>every ' + w.every + ' min</dd>' +
      '<dt>Actually runs</dt><dd>' + (w.every_real
        ? 'every ' + Math.round(w.every_real / 60) + ' min' : 'not enough runs yet') + '</dd>' +
      '<dt>Next expected</dt><dd>' + (function () {
        if (!w.last_run) return '-';
        var due = (w.last_run.at + (w.every_real || w.every * 60)) * 1000;
        /* A time already past reads as a fault when it usually is not: these jobs
           drift, which is the whole reason the cadence is measured rather than
           assumed. Say "any time now" instead of naming an hour that has gone. */
        if (due <= Date.now()) return 'any time now';
        return new Date(due).toISOString().slice(11, 16) + ' UTC';
      })() + '</dd>' +
      '<dt>30-day success</dt><dd>' + (rate === null ? '-' : rate + '% (' + w.window.ok + '/' + w.window.runs + ')') + '</dd>' +
      '<dt>All time</dt><dd>' + num(a.total || 0) + ' runs, ' + num(a.failures || 0) + ' failed</dd>' +
      '<dt>Typical length</dt><dd>' + (w.median_secs ? secs(w.median_secs) : '-') + '</dd>' +
      '<dt>Slowest seen</dt><dd>' + (w.slowest_secs ? secs(w.slowest_secs) : '-') + '</dd>' +
      '</dl>' + stackBars(w.daily || []) +
      '<p class="flag">Successes in green, failures in red, one column a day. A thin grey ' +
      'line is a day with no runs.</p></div>';
  }).join('');

  var recent = [];
  (ops.workflows || []).forEach(function (w) {
    (w.recent || []).forEach(function (r) { recent.push({ wf: w.label, at: r.at, ok: r.ok, secs: r.secs }); });
  });
  recent.sort(function (a, b) { return b.at - a.at; });
  recent = recent.slice(0, 40);

  return '<h2 class="vh">System</h2>' +
    '<div class="tools"><button class="btn" id="resync" type="button">Refresh system status</button>' +
    '<span class="mut small" id="resyncmsg">Last read from GitHub ' + ago(ops.synced) + '.</span></div>' +
    '<div class="sec"><div class="row2">' + cards + '</div></div>' +
    '<div class="sec"><h2>Data freshness</h2><div class="cards">' +
    kpi({ label: 'Newest player reading', value: live.updated ? ago(live.updated) : 'unknown',
      change: null, sub: live.total_samples ? num(live.total_samples) + ' in total' : '',
      why: 'From summary.json, which the collector writes on every run. This is current even ' +
        'when the site itself has not rebuilt.' }) +
    kpi({ label: 'Site last rebuilt', value: agoIso(st.built_at), change: null,
      sub: 'four builds a day',
      why: 'When the static pages were last written. Game pictures and descriptions are ' +
        'fetched at build time, so this is also how stale a game icon can be.' }) +
    kpi({ label: 'Pages on the site', value: num((st.totals || {}).pages_built || 0), change: null,
      why: 'Game pages built at the last build. Each also has four sub-pages.' }) +
    '</div></div>' +
    '<div class="sec"><h2>Recent runs</h2><div class="card pad0"><div class="tw"><table>' +
    '<thead><tr><th>Job</th><th>When (UTC)</th><th>Result</th><th class="n">Took</th></tr></thead><tbody>' +
    (recent.length ? recent.map(function (r) {
      return '<tr><td>' + esc(r.wf) + '</td><td>' +
        usWhen(r.at * 1000) + '</td><td>' +
        (r.ok === 1 ? '<span class="pill g">ok</span>'
          : (r.ok === 0 ? '<span class="pill r">failed</span>' : '<span class="pill">running</span>')) +
        '</td><td class="n">' + (r.secs ? secs(r.secs) : '-') + '</td></tr>';
    }).join('') : '<tr><td colspan="4" class="empty">No runs recorded yet.</td></tr>') +
    '</tbody></table></div></div></div>' +
    feedHtml() +
    dl([['runs', 'All runs'], ['errors', 'Failed runs only']]);
}

/* Recent events, newest first. Deliberately plain rows rather than anything animated:
   it is a log, and a log that moves is harder to read than one that does not. */
function feedHtml() {
  var f = D.feed || {};
  var ev = f.events || [];
  var mark = { fault: 'r', ok: 'g', run: '', person: 'a', save: '', bell: '' };
  return '<div class="sec"><h2>Recent activity</h2><div class="card pad0"><div class="tw">' +
    '<table><thead><tr><th>When (UTC)</th><th>Ago</th><th>What</th></tr></thead><tbody>' +
    (ev.length ? ev.map(function (e) {
      return '<tr><td>' + usWhen(e.at * 1000, false) +
        '</td><td>' + ago(e.at) + '</td><td><span class="pill ' + (mark[e.kind] || '') + '">' +
        esc(e.kind) + '</span> ' + esc(e.text) + '</td></tr>';
    }).join('') : '<tr><td colspan="3" class="empty">Nothing in the last seven days.</td></tr>') +
    '</tbody></table></div></div>' +
    '<p class="flag">' + esc(f.covers || '') + '</p></div>';
}

/* ======================================================================= SEARCH */
function pSearch() {
  var g = D.gsc || {};
  var head = '<h2 class="vh">Search</h2>';

  if (g.state === 'not_configured') {
    return head + '<div class="card"><h2>Connect Google Search Console</h2>' +
      '<p class="mut small" style="margin:0 0 4px">This is the only way to see what people ' +
      'actually searched for to reach the site. It costs nothing, and it needs no change to ' +
      'the privacy policy: Google reports its own totals about the site, never anything ' +
      'about a visitor.</p><ol class="steps">' +
      (g.setup || []).map(function (s) {
        return '<li>' + esc(s).replace(/(npx wrangler secret put [A-Z_]+)/g, '<code>$1</code>') + '</li>';
      }).join('') +
      '</ol>' +
      (g.secrets ? '<h3>The two commands</h3><p class="mut small" style="margin:0 0 6px">' +
        'Run these in a terminal in the project folder. The second one reads the key ' +
        'straight out of the file, so it never reaches your clipboard or this screen.</p>' +
        '<div class="cmds">' + g.secrets.map(function (c) {
          return '<code>' + esc(c) + '</code>';
        }).join('') + '</div>' : '') +
      (g.note ? '<p class="flag">' + esc(g.note) + '</p>' : '') + '</div>';
  }
  if (g.state === 'never_fetched' || g.state === 'error') {
    return head + '<div class="tools"><button class="btn" id="gscgo" type="button">Fetch now</button>' +
      '<span class="mut small" id="gscmsg"></span></div>' +
      '<div class="card"><h2>' + (g.state === 'error' ? 'Google refused' : 'Not fetched yet') + '</h2>' +
      '<p class="mut small">' + (g.error ? esc(g.error)
        : 'The keys are set. Figures arrive on the next daily sync, or press Fetch now.') +
      '</p></div>';
  }

  var t = g.totals || {};
  /* Google returns only the days that had something, so a 29-day window can come back
     as 10 rows. Drawn straight that way the chart would join them up as if they were
     consecutive. Filling the gaps with zero is honest here, unlike with our own page
     views: a day Google reports nothing for is a day with no clicks, which really is
     zero, rather than a day we failed to record. */
  var daily = (function () {
    var got = {}, out = [];
    (g.daily || []).forEach(function (r) { got[r.date] = r.clicks; });
    var from = Date.parse(g.from + 'T00:00:00Z'), to = Date.parse(g.to + 'T00:00:00Z');
    if (!from || !to || to < from) {
      return (g.daily || []).map(function (r) { return { day: r.date, n: r.clicks }; });
    }
    for (var d = from; d <= to; d += 864e5) {
      var k = new Date(d).toISOString().slice(0, 10);
      out.push({ day: k, n: got[k] || 0 });
    }
    return out;
  })();
  /* Kept for wirePanel, so the crosshair reads the SAME array the line was drawn
     from. It used to be handed g.daily, which is only the days Google reported
     something for - 10 rows where the chart drew 29 - so the cursor worked out
     its spacing from a different number of points and pointed at the wrong day
     everywhere but the left edge. */
  GSCSERIES = daily;
  var withClicks = (g.daily || []).length;
  return head +
    '<div class="tools"><button class="btn ghost" id="gscgo" type="button">Fetch again</button>' +
    '<span class="mut small" id="gscmsg">' + esc(usDate(g.from)) + ' to ' + esc(usDate(g.to)) +
    ', read ' + ago(g.fetched) + '.</span></div>' +
    '<div class="cards">' +
    kpi({ label: 'Clicks', value: num(t.clicks), change: null,
      why: 'Times somebody clicked through to the site from a Google results page.' }) +
    kpi({ label: 'Impressions', value: num(t.impressions), change: null,
      why: 'Times a page of ours appeared in a results page, whether or not anybody clicked.' }) +
    kpi({ label: 'Click-through rate',
      value: t.ctr === null ? 'no data' : (t.ctr * 100).toFixed(1) + '%', change: null,
      why: 'Clicks divided by impressions, worked out from the daily totals rather than ' +
        'averaging per-query rates, which would be an average of averages.' }) +
    kpi({ label: 'Average position',
      value: t.position === null ? 'no data' : t.position.toFixed(1), change: null,
      lowerIsBetter: true,
      why: 'Where the site typically appears in results, weighted by impressions. Lower is ' +
        'better: 1 is the top result.' }) +
    '</div>' +
    '<div class="sec"><h2>Clicks over time</h2><div class="card">' +
    lineChart('gschart', daily, 'alt', false) +
    '<p class="readout" id="gsread">Drag across the chart to read a day.</p>' +
    '<p class="flag">' + plural(withClicks, 'day') + ' of the ' + daily.length +
    ' had at least one click. The rest are drawn as zero, which is what they were.</p>' +
    '</div></div>' +
    '<div class="row2">' +
    '<div class="card"><h2>What people searched for</h2>' +
    barRows((g.queries || []).slice(0, 15).map(function (q) {
      return { label: q.query, v: q.impressions,
        right: num(q.clicks) + ' / ' + num(q.impressions) };
    })) + '<p class="flag">Clicks / impressions. Sorted by impressions.</p></div>' +
    '<div class="card"><h2>Pages Google sends people to</h2>' +
    barRows((g.pages || []).slice(0, 15).map(function (p) {
      return { label: String(p.page).replace('https://playtimestats.com', ''), v: p.impressions,
        right: num(p.clicks) + ' / ' + num(p.impressions) };
    }), 'alt') + '</div></div>' +
    ((g.devices || []).length ? '<div class="sec"><h2>Device, as Google reports it</h2>' +
      '<div class="card">' + barRows((g.devices || []).map(function (d) {
        return { label: d.device, v: d.clicks, right: num(d.clicks) + ' clicks' };
      })) + '<p class="flag">This is Google telling us about its own search traffic. We do ' +
      'not record a device for anybody, and this does not come from our visitors.</p></div></div>' : '');
}

/* ======================================================================= PEOPLE */
function pPeople() {
  var p = D.people || {};
  var a = p.accounts || {}, f = p.favs || {}, dv = p.devices || {}, w = p.watches || {};
  return '<h2 class="vh">People</h2>' +
    '<p class="mut small" style="margin:0 0 12px">Counts and game names only. No display ' +
    'names, no Roblox IDs, no device addresses: knowing whether a feature works does not ' +
    'need to know who, and a dashboard is a screen that gets photographed.</p>' +
    '<div class="cards">' +
    kpi({ label: 'Signed in', value: num(a.n || 0), change: null,
      sub: num(a.active || 0) + ' back in the last week',
      why: 'Roblox accounts that have signed in at least once. Everything on the site works ' +
        'signed out, so this is never the visitor count.' }) +
    kpi({ label: 'New this week', value: num(a.joined || 0), change: null,
      why: 'Accounts whose first sign-in was in the last seven days.' }) +
    kpi({ label: 'Saved games', value: num(f.n || 0), change: null,
      sub: 'by ' + plural(f.people || 0, 'person'),
      why: 'Rows in the favourites table. A signed-out visitor saves to their own browser ' +
        'instead, which we cannot see.' }) +
    kpi({ label: 'Notification devices', value: num(dv.n || 0), change: null,
      sub: (dv.failing ? dv.failing + ' failing' : 'all reachable'),
      why: 'Browsers that have turned notifications on. Signed-in only, because a push ' +
        'subscription is a permanent per-device identifier.' }) +
    '</div>' +
    '<div class="row2" style="margin-top:14px">' +
    '<div class="card"><h2>Most saved games</h2>' + barRows((p.favTop || []).map(function (x) {
      return { label: x.slug, v: x.n };
    })) + '</div>' +
    '<div class="card"><h2>Most followed for notifications</h2>' +
    barRows((p.watchTop || []).map(function (x) { return { label: x.slug, v: x.n }; }), 'alt') +
    '</div></div>' +
    '<div class="sec"><h2>Which switches people choose</h2><div class="card">' +
    barRows([
      { label: 'Quiet', v: w.quiet || 0 }, { label: 'Busy', v: w.busy || 0 },
      { label: 'Events', v: w.events || 0 }, { label: 'Updates', v: w.updates || 0 }
    ]) + '<p class="flag">' + plural(w.n || 0, 'game') + ' followed by ' +
    plural(w.people || 0, 'person') + '. The four are independent, so these do not add up ' +
    'to the number of games.</p></div></div>' +
    '<div class="sec"><h2>What the push service last said</h2><div class="card pad0"><div class="tw">' +
    '<table><thead><tr><th>Added</th><th class="n">Offset</th><th class="n">Fails</th>' +
    '<th class="n">Last status</th><th>Last try</th></tr></thead><tbody>' +
    ((p.devList || []).length ? (p.devList || []).map(function (d) {
      return '<tr><td>' + (d.created ? usDate(new Date(d.created).toISOString()) : '-') +
        '</td><td class="n">' + (d.tz > 0 ? '+' : '') + (d.tz || 0) + '</td>' +
        '<td class="n">' + (d.fails || 0) + '</td><td class="n">' +
        (d.last_status === null || d.last_status === undefined ? '<span class="mut">not tried</span>'
          : '<span class="pill ' + (d.last_status === 201 ? 'g' : (d.last_status > 0 ? 'r' : 'a')) + '">' +
            d.last_status + '</span>') + '</td><td>' +
        (d.last_try ? ago(Math.floor(d.last_try / 1000)) : '-') + '</td></tr>';
    }).join('') : '<tr><td colspan="5" class="empty">No devices yet.</td></tr>') +
    '</tbody></table></div></div>' +
    '<p class="flag">201 is a normal success. 0 means the message could not be built and -1 ' +
    'means the push service was unreachable. Recent sends: ' + num((p.sent || {}).n || 0) +
    ' (cleared down to two days on every run, so never a running total).</p></div>';
}

/* ==================================================================== CHECKLIST */
function pChecklist() {
  var all = D.todos || [];
  var open = all.filter(function (t) { return !t.done; });
  var done = all.filter(function (t) { return t.done; });
  var row = function (t) {
    return '<div class="todo"><input type="checkbox" id="t-' + esc(t.key) + '" data-todo="' +
      esc(t.key) + '"' + (t.done ? ' checked' : '') + '><div><label class="tl" for="t-' +
      esc(t.key) + '">' + esc(t.label) + '</label>' +
      (t.note ? '<div class="tn">' + esc(t.note) + '</div>' : '') + '</div></div>';
  };
  return '<h2 class="vh">Checklist</h2>' +
    '<div class="row2"><div class="card">' +
    (open.length ? open.map(row).join('')
      : '<p class="empty">Everything is ticked off. The site is running on its own.</p>') +
    (done.length ? '<details class="donelist"><summary>' + plural(done.length, 'finished item') +
      '</summary>' + done.map(row).join('') + '</details>' : '') +
    '</div><div class="card" style="align-self:start"><div id="ring-box">' +
    ring(done.length, all.length, 'done') +
    '<p class="mut small" style="text-align:center;margin:8px 0 0">' +
    (open.length ? plural(open.length, 'thing') + ' left to do.' : 'All ticked off.') +
    '</p></div></div></div>';
}

/* ===================================================================== plumbing */
function dl(list) {
  return '<div class="sec"><h2>Download</h2><div class="dl">' +
    list.map(function (x) {
      return '<a class="btn ghost" href="/admin/export?what=' + x[0] + '&from=' + RANGE.from +
        '&to=' + RANGE.to + '">' + esc(x[1]) + ' (CSV)</a>';
    }).join('') +
    '</div><p class="flag">Each file covers the period this page is set to, and says so in ' +
    'its name.</p></div>';
}

/* The gap-filled clicks series, set when the Search tab draws and read when its
   cursor is wired a moment later. */
var GSCSERIES = [];

var RENDER = {
  overview: pOverview, traffic: pTraffic, games: pGames,
  system: pSystem, search: pSearch, people: pPeople, checklist: pChecklist
};

function paint() {
  if (!D) return;
  var el = $('#p-' + TAB);
  if (!el) { TAB = 'overview'; el = $('#p-overview'); }
  try {
    el.innerHTML = RENDER[TAB]();
  } catch (e) {
    el.innerHTML = '<p class="empty">Something went wrong drawing this tab: ' + esc(e.message) + '</p>';
  }
  wireRange();
  wirePanel();
  badges();
}

/* The count beside a tab name, so a fault is visible without opening it. */
function badges() {
  var faults = (D.insights || []).filter(function (i) {
    return i.severity === 'fault' || i.severity === 'warn';
  }).length;
  var set = function (tab, n) {
    var b = $('#cnt-' + tab);
    if (!b) return;
    if (n > 0) { b.textContent = n; b.hidden = false; } else { b.hidden = true; }
  };
  set('overview', faults);
  var open = (D.todos || []).filter(function (t) { return !t.done; }).length;
  set('checklist', open);
}

function wirePanel() {
  /* Charts. Each needs its cursor bound after the markup exists. */
  [['ovchart', 'ovread', D.range.views.series],
   ['trchart', 'trread', D.range.views.series],
   ['gschart', 'gsread', GSCSERIES, 'click']
  ].forEach(function (x) {
    var svg = document.getElementById(x[0]), out = document.getElementById(x[1]);
    if (svg && out && x[2] && x[2].length) chartCursor(svg, out, x[2], x[3]);
  });

  var q = $('#gq');
  if (q) q.oninput = function () { GQ = q.value.trim().toLowerCase(); paint(); setTimeout(function () {
    var n = $('#gq'); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); }
  }, 0); };
  var f = $('#gf');
  if (f) f.onchange = function () { GFILTER = f.value; paint(); };

  $$('th[data-sort]').forEach(function (th) {
    th.onclick = function () {
      var by = th.dataset.sort;
      if (GSORT.by === by) GSORT.dir *= -1;
      else GSORT = { by: by, dir: (by === 'name' || by === 'genre') ? 1 : -1 };
      paint();
    };
  });
  $$('tr[data-game]').forEach(function (tr) {
    tr.onclick = function () { openGame(tr.dataset.game); };
  });

  /* The drawn scroll control above the games table. It reads the table's own
     scrollLeft, so the two can never disagree, and writing to scrollLeft is what moves
     the table - no second scrollable box to keep in step. */
  (function () {
    var track = $('#gtop');
    if (!track) return;
    var tw = track.nextElementSibling;
    var tbl = tw && tw.querySelector('table');
    if (!tbl) return;
    var th = track.firstElementChild;

    function paintBar() {
      var total = tbl.scrollWidth, box = tw.clientWidth;
      /* Nothing to scroll means no control: a strip above a table that already fits
         is clutter pretending to be one. */
      if (total <= box + 1) { track.hidden = true; return; }
      track.hidden = false;
      var tw2 = track.clientWidth;
      var w = Math.max(30, (box / total) * tw2);
      var room = tw2 - w;
      var scrollable = total - box;
      th.style.width = w + 'px';
      th.style.left = (scrollable ? (tw.scrollLeft / scrollable) * room : 0) + 'px';
    }

    function moveTo(clientX, grab) {
      var r = track.getBoundingClientRect();
      var w = th.offsetWidth;
      var room = track.clientWidth - w;
      var left = Math.max(0, Math.min(room, clientX - r.left - grab));
      var scrollable = tbl.scrollWidth - tw.clientWidth;
      tw.scrollLeft = room ? (left / room) * scrollable : 0;
    }

    var dragging = false, grab = 0;
    track.addEventListener('pointerdown', function (e) {
      var r = th.getBoundingClientRect();
      /* Grabbing the thumb keeps it under the finger; pressing the bare track jumps,
         centring the thumb where it was pressed. */
      grab = (e.clientX >= r.left && e.clientX <= r.right) ? (e.clientX - r.left) : th.offsetWidth / 2;
      dragging = true;
      track.classList.add('drag');
      try { track.setPointerCapture(e.pointerId); } catch (err) { }
      moveTo(e.clientX, grab);
      e.preventDefault();
    });
    track.addEventListener('pointermove', function (e) { if (dragging) moveTo(e.clientX, grab); });
    var stop = function (e) {
      dragging = false;
      track.classList.remove('drag');
      if (e && e.pointerId !== undefined) { try { track.releasePointerCapture(e.pointerId); } catch (err) { } }
    };
    track.addEventListener('pointerup', stop);
    track.addEventListener('pointercancel', stop);

    tw.addEventListener('scroll', paintBar);
    addEventListener('resize', paintBar);
    paintBar();
  })();

  /* Hiding and unhiding dead game IDs. Neither touches games.txt. */
  var saveIds = function (ids, btn, msgId) {
    if (btn) btn.disabled = true;
    var msg = msgId ? $(msgId) : null;
    if (msg) msg.textContent = 'Saving' + '…';
    fetch('/admin/hide-ids', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ ids: ids })
    }).then(function (r) {
      if (!r.ok) throw new Error('that did not work');
      D.hidden_ids = ids;
      /* The insights list is built on the server from this, so a reload is what makes
         the Overview agree with the Games tab rather than the two disagreeing. */
      return load();
    }).catch(function () {
      if (btn) btn.disabled = false;
      if (msg) msg.textContent = 'That did not work.';
    });
  };
  var hb = $('#hideids');
  if (hb) hb.onclick = function () {
    saveIds(((D.missing || {}).confirmed || []).map(String), hb, '#hidemsg');
  };
  var sb = $('#showids');
  if (sb) sb.onclick = function () { saveIds([], sb, null); };

  var rs = $('#resync');
  if (rs) rs.onclick = function () {
    rs.disabled = true;
    var msg = $('#resyncmsg');
    if (msg) msg.textContent = 'Reading GitHub' + '…';
    fetch('/admin/sync', { method: 'POST' }).then(function (r) { return r.json(); })
      .then(function (j) {
        if (msg) msg.textContent = j.ok ? 'Up to date.' : 'Partly failed: ' + (j.failed || []).join(', ');
        return load();
      })
      .catch(function () { if (msg) msg.textContent = 'That did not work.'; rs.disabled = false; });
  };

  var gg = $('#gscgo');
  if (gg) gg.onclick = function () {
    gg.disabled = true;
    var msg = $('#gscmsg');
    if (msg) msg.textContent = 'Asking Google' + '…';
    fetch('/admin/gsc', { method: 'POST' }).then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j.ok && msg) msg.textContent = j.error || 'That did not work.';
        return load();
      })
      .catch(function () { if (msg) msg.textContent = 'That did not work.'; gg.disabled = false; });
  };

  $$('[data-todo]').forEach(function (box) {
    box.onchange = function () {
      var key = box.dataset.todo, want = box.checked;
      box.disabled = true;
      fetch('/admin/todo', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ key: key, done: want })
      }).then(function (r) {
        if (!r.ok) throw new Error('no');
        /* Moved between the two lists only AFTER the save lands: a row that jumped
           first would have to jump back on a failure and would read as a glitch. */
        var t = (D.todos || []).filter(function (x) { return x.key === key; })[0];
        if (t) t.done = want ? 1 : 0;
        paint();
      }).catch(function () { box.checked = !want; box.disabled = false; });
    };
  });
}

/* Tabs */
$$('.side button[data-tab]').forEach(function (b) {
  b.setAttribute('aria-selected', String(b.dataset.tab === TAB));
  b.onclick = function () {
    TAB = b.dataset.tab;
    try { localStorage.setItem('pt_admin_tab', TAB); } catch (e) {}
    $$('.side button[data-tab]').forEach(function (x) {
      x.setAttribute('aria-selected', String(x.dataset.tab === TAB));
    });
    $$('[role=tabpanel]').forEach(function (p) { p.hidden = p.id !== 'p-' + TAB; });
    paint();
  };
});
$$('[role=tabpanel]').forEach(function (p) { p.hidden = p.id !== 'p-' + TAB; });

/* The game panel closes on the X, on the scrim and on Escape. */
document.addEventListener('click', function (e) {
  if (e.target.closest && e.target.closest('[data-close]')) {
    var sh = $('#gsheet');
    sh.classList.remove('on');
    sh.setAttribute('aria-hidden', 'true');
  }
});
addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    var sh = $('#gsheet');
    if (sh && sh.classList.contains('on')) {
      sh.classList.remove('on');
      sh.setAttribute('aria-hidden', 'true');
    }
  }
});

load();
</script>`;
