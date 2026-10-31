"""Every call PlayTime makes to Roblox's public APIs while building the site.

build_site.py uses this for things that are not worth storing in our own database
because they change on their own: game pictures, descriptions, game passes and events.

Answers are cached in a .cache folder so building the site twice in a row is fast
and we are polite to Roblox. The cache is never committed (see .gitignore).

All of these are unofficial endpoints. If one stops working, the matching function
returns None or an empty result and the site simply leaves that section out.
"""
import hashlib, json, os, time, urllib.error, urllib.request
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
