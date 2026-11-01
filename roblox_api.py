"""Every call PlayTime makes to Roblox's public APIs while building the site.

build_site.py uses this for things that are not worth storing in our own database
because they change on their own: game pictures, descriptions, game passes and events.

Answers are cached in a .cache folder so building the site twice in a row is fast
and we are polite to Roblox. The cache is never committed (see .gitignore).

All of these are unofficial endpoints. If one stops working, the matching function
returns None or an empty result and the site simply leaves that section out.
"""
import colorsys, hashlib, json, math, os, time, urllib.error, urllib.request, zlib
from datetime import datetime

CACHE_DIR = ".cache"
HEADERS = {"User-Agent": "playtime/1.0 (+static site builder)"}

GAMES_API = "https://games.roblox.com/v1/games?universeIds="
ICON_API = ("https://thumbnails.roblox.com/v1/games/icons"
            "?size=256x256&format=Webp&isCircular=false&universeIds=")
# The wide picture Roblox shows on a game's own page. We use it faded out behind the
# heading, so a game page feels like that game.
BANNER_API = ("https://thumbnails.roblox.com/v1/games/multiget/thumbnails"
              "?countPerUniverse=1&defaults=true&size=768x432&format=Webp&isCircular=false"
              "&universeIds=")
ASSET_API = ("https://thumbnails.roblox.com/v1/assets"
             "?size=150x150&format=Png&isCircular=false&assetIds=")
PASS_API = "https://apis.roblox.com/game-passes/v1/universes/{}/game-passes?passView=Full&pageSize=100"
EVENT_API = "https://apis.roblox.com/virtual-events/v1/universes/{}/virtual-events"

HOUR = 3600
DAY = 24 * HOUR


def get_json(url, tries=3):
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (404, 400):
                raise
            time.sleep(4 * (attempt + 1) if e.code == 429 else 2)
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"gave up on {url}")


def cached(key, ttl, make):
    """Returns make() but remembers the answer on disk for ttl seconds."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.sha1(key.encode()).hexdigest()[:20] + ".json")
    try:
        if time.time() - os.path.getmtime(path) < ttl:
            with open(path, encoding="utf-8") as f:
                return json.load(f)["v"]
    except (OSError, ValueError, KeyError):
        pass
    value = make()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"key": key, "v": value}, f)
    except OSError:
        pass
    return value


def _iso(s):
    """Roblox time text -> unix seconds (or None)."""
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        if "." in s:                      # trim fractions of a second
            head, _, tail = s.partition(".")
            s = head + ("+" + tail.split("+", 1)[1] if "+" in tail else "+00:00")
        return int(datetime.fromisoformat(s).timestamp())
    except ValueError:
        return None


def fetch_icons(ids):
    """{universe_id: picture url} for each game, skipping any Roblox has no picture for."""
    def pull(batch):
        out = {}
        try:
            for t in get_json(ICON_API + ",".join(map(str, batch))).get("data", []):
                if t.get("state") == "Completed" and t.get("imageUrl"):
                    out[str(t["targetId"])] = t["imageUrl"]
        except Exception as e:
            print("  ! could not load icons (those games show a letter instead):", e)
        return out

    out = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        out.update(cached("icons:" + ",".join(map(str, batch)), 7 * DAY, lambda b=batch: pull(b)))
    return {int(k): v for k, v in out.items()}


def fetch_banners(ids):
    """{universe_id: wide picture url} for the art behind each game's heading."""
    def pull(batch):
        out = {}
        try:
            for g in get_json(BANNER_API + ",".join(map(str, batch))).get("data", []):
                for t in g.get("thumbnails") or []:
                    if t.get("state") == "Completed" and t.get("imageUrl"):
                        out[str(g["universeId"])] = t["imageUrl"]
                        break
        except Exception as e:
            print("  ! could not load game artwork (those pages get a plain heading):", e)
        return out

    out = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        out.update(cached("banners:" + ",".join(map(str, batch)), 7 * DAY, lambda b=batch: pull(b)))
    return {int(k): v for k, v in out.items()}


def fetch_meta(ids):
    """{universe_id: {description, updated, created, visits, max_players, favorites}}."""
    def pull(batch):
        out = {}
        try:
            for g in get_json(GAMES_API + ",".join(map(str, batch))).get("data", []):
                out[str(g["id"])] = {
                    "description": (g.get("description") or "").strip(),
                    "updated": _iso(g.get("updated")),
                    "created": _iso(g.get("created")),
                    "visits": g.get("visits") or 0,
                    "max_players": g.get("maxPlayers") or 0,
                    "favorites": g.get("favoritedCount") or 0,
                    "creator": ((g.get("creator") or {}).get("name") or "").strip(),
                }
        except Exception as e:
            print("  ! could not load game details:", e)
        return out

    out = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        out.update(cached("meta:" + ",".join(map(str, batch)), 6 * HOUR, lambda b=batch: pull(b)))
    return {int(k): v for k, v in out.items()}


def fetch_passes(uid):
    """Game passes on sale, newest Roblox details first.

    Each one is {name, price, description, icon_id, created, discounted}, or None if
    Roblox did not answer. The description is what the creators say the pass contains.
    """
    def pull():
        out, token = [], ""
        try:
            for _ in range(10):
                d = get_json(PASS_API.format(uid) + (f"&pageToken={token}" if token else ""))
                for p in d.get("gamePasses", []):
                    if not (p.get("isForSale") and p.get("price")):
                        continue
                    out.append({
                        "name": p.get("displayName") or p.get("name") or "Game pass",
                        "price": p["price"],
                        "description": (p.get("displayDescription") or "").strip(),
                        "icon_id": p.get("displayIconImageAssetId") or 0,
                        "created": _iso(p.get("created")),
                        # Roblox lists a discount here when a pass is on offer.
                        "discounted": bool(p.get("priceDiscountDetails")),
                    })
                token = d.get("nextPageToken")
                if not token:
                    break
                time.sleep(0.3)
            return out
        except Exception as e:
            print(f"  ! could not load game passes for {uid}:", e)
            return None

    return cached(f"passes2:{uid}", DAY, pull)


def fetch_asset_icons(asset_ids):
    """{asset id: picture url} for game pass icons."""
    ids = [int(a) for a in asset_ids if a]
    def pull(batch):
        out = {}
        try:
            for t in get_json(ASSET_API + ",".join(map(str, batch))).get("data", []):
                if t.get("state") == "Completed" and t.get("imageUrl"):
                    out[str(t["targetId"])] = t["imageUrl"]
        except Exception as e:
            print("  ! could not load game pass pictures:", e)
        return out

    out = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        out.update(cached("assets:" + ",".join(map(str, batch)), 7 * DAY, lambda b=batch: pull(b)))
    return {int(k): v for k, v in out.items()}


# ------------------------------------------------------------- icon colours
# The glow behind a game tile is that game's own colour. It is worked out here,
# once, while the site is being built, so the browser downloads nothing extra and
# does no work for it: each page simply carries one number per game, the hue.
#
# Roblox serves icons as WebP, which Python cannot read without installing
# something. So we ask the same endpoint for a small PNG instead and unpack that
# with the zlib that comes with Python, which keeps this file free of libraries
# the build server would have to install. Anything unusual in the file and we
# give up and return None, and that game's tile glows in the site colour.

PNG_ICON_API = ("https://thumbnails.roblox.com/v1/games/icons"
                "?size=50x50&format=Png&isCircular=false&universeIds=")


def _unfilter(f, line, prev, bpp):
    """Undo one PNG scanline filter, in place. False if the filter is not a real one."""
    if f == 0:
        return True
    if f > 4:
        return False
    for i in range(len(line)):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        if f == 1:
            line[i] = (line[i] + a) & 255
        elif f == 2:
            line[i] = (line[i] + b) & 255
        elif f == 3:
            line[i] = (line[i] + (a + b) // 2) & 255
        else:                                    # 4: "Paeth", pick the nearest neighbour
            c = prev[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
    return True


def _png_rgba(data):
    """A PNG's pixels as [(r,g,b,a), ...], or None if it is not one we can read."""
    if not data or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, plte, trns, hdr = 8, [], b"", b"", None
    while pos + 8 <= len(data):
        n = int.from_bytes(data[pos:pos + 4], "big")
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            hdr = body
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if not hdr or len(hdr) < 13 or not idat:
        return None
    w = int.from_bytes(hdr[0:4], "big")
    h = int.from_bytes(hdr[4:8], "big")
    depth, colour, interlace = hdr[8], hdr[9], hdr[12]
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    # 8 bits a channel and no interlacing covers everything Roblox sends. Anything
    # else is rare enough that reading it wrong would be worse than not reading it.
    if depth != 8 or interlace or not channels or not (0 < w <= 512) or not (0 < h <= 512):
        return None
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error:
        return None
    stride = w * channels
    if len(raw) < (stride + 1) * h:
        return None
    out, prev, at = [], bytearray(stride), 0
    for _ in range(h):
        line = bytearray(raw[at + 1:at + 1 + stride])
        if not _unfilter(raw[at], line, prev, channels):
            return None
        at += 1 + stride
        prev = line
        for x in range(0, stride, channels):
            px = line[x:x + channels]
            if colour == 2:
                out.append((px[0], px[1], px[2], 255))
            elif colour == 6:
                out.append((px[0], px[1], px[2], px[3]))
            elif colour == 0:
                out.append((px[0], px[0], px[0], 255))
            elif colour == 4:
                out.append((px[0], px[0], px[0], px[1]))
            else:                                # 3: a palette of up to 256 colours
                i = px[0] * 3
                if i + 3 > len(plte):
                    return None
                out.append((plte[i], plte[i + 1], plte[i + 2],
                            trns[px[0]] if px[0] < len(trns) else 255))
    return out


def dominant_hue(pixels):
    """The hue (0-359) a picture reads as, or None if it has no real colour in it.

    See-through, near-black, near-white and washed-out pixels are skipped, so an
    icon that is mostly a dark background still glows in whatever colour it does
    have. Every pixel that is left counts for how colourful and how bright it is,
    so a small vivid logo beats a large dull area, which is what the eye does too.
    Hues are averaged the way angles have to be (through sin and cos), or colours
    either side of red would average to the cyan opposite them.
    """
    if not pixels:
        return None
    buckets = [[0.0, 0.0, 0.0] for _ in range(36)]      # weight, sum of sin, sum of cos
    for r, g, b, a in pixels:
        hi, lo = max(r, g, b), min(r, g, b)
        if a < 128 or hi < 30 or lo > 242 or (hi - lo) / hi < 0.28:
            continue
        hue = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 360
        weight = ((hi - lo) / hi) * (hi / 255)
        slot, rad = int(hue // 10) % 36, math.radians(hue)
        buckets[slot][0] += weight
        buckets[slot][1] += weight * math.sin(rad)
        buckets[slot][2] += weight * math.cos(rad)
    # Colour runs in a ring, so the heaviest single slice can be a peak split down
    # the middle: a red picture puts half its weight at 358 degrees and half at 2.
    # Scoring every slice together with its two neighbours closes that seam, and
    # those same three are then averaged to get the answer.
    def around(i):
        return (buckets[(i - 1) % 36], buckets[i], buckets[(i + 1) % 36])

    trio = around(max(range(36), key=lambda i: sum(x[0] for x in around(i))))
    # A handful of stray colourful pixels in a grey picture is not a colour. Asking
    # for roughly 1% of the picture keeps a small logo but rejects noise.
    if sum(x[0] for x in trio) < max(1.0, 0.01 * len(pixels)):
        return None
    return int(round(math.degrees(math.atan2(sum(x[1] for x in trio),
                                             sum(x[2] for x in trio))) % 360))


def fetch_icon_hues(ids):
    """{universe_id: hue} - the colour each game's picture reads as.

    Games whose picture is grey, or that Roblox has no picture for, are simply
    left out, and build_site.py falls back to the site's own accent for those.
    """
    def pull(batch):
        out = {}
        try:
            for t in get_json(PNG_ICON_API + ",".join(map(str, batch))).get("data", []):
                if t.get("state") == "Completed" and t.get("imageUrl"):
                    out[str(t["targetId"])] = t["imageUrl"]
        except Exception as e:
            print("  ! could not load icon colours (those tiles glow in the site colour):", e)
        return out

    def hue_of(url):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                return dominant_hue(_png_rgba(r.read(400000)))
        except Exception:
            return None

    urls = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        urls.update(cached("pngicons:" + ",".join(map(str, batch)), 7 * DAY,
                           lambda b=batch: pull(b)))
    out = {}
    for uid, url in urls.items():
        # Keyed on the picture, not the game, so a game that changes its icon gets a
        # new colour and one that does not is never downloaded twice.
        hue = cached("hue:" + url, 7 * DAY, lambda u=url: hue_of(u))
        if hue is not None:
            out[int(uid)] = hue
    return out


def fetch_events(uid):
    """Roblox events for one game, oldest first.

    Each event is {title, subtitle, description, start, end, host}. Developers use these
    for updates and seasonal events, so the list doubles as a rough changelog.
    Returns [] if the game has none and None if Roblox did not answer.
    """
    def pull():
        out, cursor = [], ""
        try:
            for _ in range(6):
                d = get_json(EVENT_API.format(uid) + (f"?cursor={cursor}" if cursor else ""))
                for e in d.get("data", []):
                    if e.get("eventVisibility") != "public":
                        continue
                    t = e.get("eventTime") or {}
                    start = _iso(t.get("startUtc"))
                    if not start:
                        continue
                    out.append({
                        "title": (e.get("displayTitle") or e.get("title") or "Event").strip(),
                        "subtitle": (e.get("displaySubtitle") or e.get("subtitle") or "").strip(),
                        "description": (e.get("displayDescription") or e.get("description") or "").strip(),
                        "start": start,
                        "end": _iso(t.get("endUtc")),
                        "host": ((e.get("host") or {}).get("hostName") or "").strip(),
                    })
                cursor = d.get("nextPageCursor")
                if not cursor:
                    break
                time.sleep(0.3)
            out.sort(key=lambda e: e["start"])
            return out
        except urllib.error.HTTPError:
            return []
        except Exception as e:
            print(f"  ! could not load events for {uid}:", e)
            return None

    return cached(f"events:{uid}", 3 * HOUR, pull)
