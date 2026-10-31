"""Checks a built site for the mistakes that quietly cost search traffic.

Run it after a build. It never changes anything; it only reads the folder and prints
what it finds.

    python build_site.py
    python check_seo.py docs

    set SITE_OUT=preview
    python seed_demo.py
    python build_site.py
    python check_seo.py preview

It looks for:
  * links that point at a page which is not there (broken links)
  * pages missing a title, a description or a canonical address
  * two pages sharing the same title or description, which makes Google pick one
  * headings that skip a level, or a page with no <h1> or more than one
  * pictures with no alt text
  * structured data that is not valid JSON
  * addresses in sitemap.xml that do not exist, or pages missing from it
  * pages asking to be left out of Google, so you can see they are the ones you meant

"FAIL" is something to fix. "note" is something to be aware of. The last line says
whether anything failed, so you can see at a glance.
"""
import html as html_mod
import json
import os
import re
import sys
from urllib.parse import unquote, urlparse

OUT = (sys.argv[1] if len(sys.argv) > 1 else "docs").rstrip("/\\")

fails, notes = [], []


def fail(page, msg):
    fails.append(f"{page}: {msg}")


def note(page, msg):
    notes.append(f"{page}: {msg}")


def pages():
    """Every .html file in the folder, as paths like 'game/doors.html'."""
    for root, _, files in os.walk(OUT):
        for f in sorted(files):
            if f.endswith(".html"):
                full = os.path.join(root, f)
                yield os.path.relpath(full, OUT).replace("\\", "/"), full


def strip_scripts(doc):
    return re.sub(r"<(script|style)\b.*?</\1>", " ", doc, flags=re.S | re.I)


def one(pattern, doc, group=1):
    m = re.search(pattern, doc, re.S | re.I)
    return m.group(group) if m else None


def exists(path):
    """Does this address lead to a real file? Mirrors how Cloudflare serves the site."""
    path = unquote(path.split("#")[0].split("?")[0])
    if not path.startswith("/"):
        return True                      # relative links: nothing on this site uses them
    local = os.path.join(OUT, path.lstrip("/"))
    if path.endswith("/"):
        return os.path.isfile(os.path.join(local, "index.html"))
    if os.path.isfile(local):
        return True
    # Cloudflare also serves /game/doors as /game/doors.html, so that counts too.
    return os.path.isfile(local + ".html")


def main():
    if not os.path.isdir(OUT):
        print(f"There is no folder called {OUT}. Build the site first.")
        return 1

    titles, descs, all_pages = {}, {}, []
    noindexed, canons = [], {}

    for name, full in pages():
        all_pages.append(name)
        with open(full, encoding="utf-8") as f:
            doc = f.read()
        body = strip_scripts(doc)

        # ---- the three tags every page needs
        title = one(r"<title>(.*?)</title>", doc)
        if not title:
            fail(name, "no <title>")
        else:
            title = html_mod.unescape(title).strip()
            titles.setdefault(title, []).append(name)
            if len(title) > 70:
                note(name, f"title is {len(title)} characters; Google shows about 60")

        desc = one(r'<meta name="description" content="(.*?)"', doc)
        if not desc:
            fail(name, "no meta description")
        else:
            desc = html_mod.unescape(desc).strip()
            descs.setdefault(desc, []).append(name)
            if len(desc) > 165:
                note(name, f"description is {len(desc)} characters; Google shows about 155")
            elif len(desc) < 50:
                note(name, f"description is only {len(desc)} characters")

        canon = one(r'<link rel="canonical" href="(.*?)"', doc)
        if not canon:
            fail(name, "no canonical address")
        else:
            canons.setdefault(html_mod.unescape(canon), []).append(name)
            # A canonical that does not point at this very page is nearly always a slip.
            want = "/" if name == "index.html" else "/" + name
            path = urlparse(html_mod.unescape(canon)).path or "/"
            if path != want:
                fail(name, f"canonical says {path} but the file is at {want}")

        robots = one(r'<meta name="robots" content="(.*?)"', doc) or ""
        if "noindex" in robots:
            noindexed.append(name)

        # ---- headings
        heads = [(int(h), re.sub(r"<[^>]+>", "", t).strip())
                 for h, t in re.findall(r"<h([1-6])\b[^>]*>(.*?)</h\1>", body, re.S | re.I)]
        h1s = [t for lvl, t in heads if lvl == 1]
        if not h1s:
            fail(name, "no <h1>")
        elif len(h1s) > 1:
            fail(name, f"{len(h1s)} <h1> headings: {h1s[:3]}")
        last = 0
        for lvl, txt in heads:
            if last and lvl > last + 1:
                note(name, f"heading jumps from h{last} to h{lvl} at {txt[:40]!r}")
            last = lvl

        # ---- pictures
        for img in re.findall(r"<img\b[^>]*>", body, re.I):
            if not re.search(r'\balt\s*=', img, re.I):
                fail(name, f"picture with no alt text: {img[:80]}")

        # ---- structured data
        for blob in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                               doc, re.S):
            try:
                json.loads(blob.replace("<\\/", "</"))
            except ValueError as e:
                fail(name, f"structured data is not valid JSON: {e}")

        # ---- links
        for href in re.findall(r'<a\b[^>]*\bhref="([^"]+)"', body, re.I):
            if href.startswith(("http://", "https://", "mailto:", "#", "javascript:")):
                continue
            if not exists(href):
                fail(name, f"link to a page that is not there: {href}")

    # ---- things that only show up across the whole site
    for t, where in titles.items():
        if len(where) > 1:
            fail(where[0], f"{len(where)} pages share the title {t!r}: {where[:3]}")
    for d, where in descs.items():
        if len(where) > 1:
            fail(where[0], f"{len(where)} pages share the description {d[:50]!r}: {where[:3]}")
    for c, where in canons.items():
        if len(where) > 1:
            fail(where[0], f"{len(where)} pages claim the same canonical {c!r}")

    # ---- the sitemap
    smap = os.path.join(OUT, "sitemap.xml")
    if not os.path.isfile(smap):
        fail("sitemap.xml", "missing")
    else:
        with open(smap, encoding="utf-8") as f:
            xml = f.read()
        locs = [html_mod.unescape(u) for u in re.findall(r"<loc>(.*?)</loc>", xml)]
        if not locs:
            fail("sitemap.xml", "no addresses in it")
        listed = set()
        for loc in locs:
            path = urlparse(loc).path or "/"
            listed.add("index.html" if path == "/" else path.lstrip("/"))
            if not exists(path):
                fail("sitemap.xml", f"lists a page that is not there: {path}")
            if not loc.startswith("http"):
                note("sitemap.xml", f"{loc} is not a full web address (set DOMAIN)")
                break
        missing = [p for p in all_pages
                   if p not in listed and p not in noindexed and p != "404.html"]
        for p in sorted(missing)[:10]:
            note(p, "is in the site but not in sitemap.xml, and is not noindexed")

    # ---- robots.txt
    robots_file = os.path.join(OUT, "robots.txt")
    if not os.path.isfile(robots_file):
        fail("robots.txt", "missing")
    else:
        with open(robots_file, encoding="utf-8") as f:
            txt = f.read()
        if re.search(r"^Disallow:\s*/\s*$", txt, re.M):
            note("robots.txt", "blocks the whole site (NOINDEX is still True)")
        elif "Sitemap:" not in txt:
            note("robots.txt", "does not point at the sitemap (set DOMAIN)")

    # ---- say what happened
    print(f"Checked {len(all_pages)} pages in {OUT}/\n")
    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails[:60]:
            print("  -", f)
        if len(fails) > 60:
            print(f"  ... and {len(fails) - 60} more")
        print()
    if notes:
        print(f"notes ({len(notes)}):")
        for n in notes[:30]:
            print("  -", n)
        if len(notes) > 30:
            print(f"  ... and {len(notes) - 30} more")
        print()
    if noindexed:
        print(f"{len(noindexed)} page(s) ask to stay out of Google.")
    print("Everything passed." if not fails else f"{len(fails)} thing(s) to fix.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
