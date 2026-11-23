"""Records live player counts for games listed in games.txt (one universe ID per line).
Run every 10 min via cron:  */10 * * * * cd /path/rbx-timing && python3 collector.py
"""
import json, sqlite3, time, urllib.request, urllib.error

DB = "data.db"
API = "https://games.roblox.com/v1/games?universeIds="

def init(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS games(universe_id INTEGER PRIMARY KEY, name TEXT, genre TEXT, place_id INTEGER);
    CREATE TABLE IF NOT EXISTS samples(universe_id INTEGER, ts INTEGER, playing INTEGER);
    CREATE UNIQUE INDEX IF NOT EXISTS idx ON samples(universe_id, ts);""")
# UNIQUE, and every insert below is OR IGNORE, because the same reading can reach
# us twice: samples.csv on the data branch is append-only, so a collector run that
# repeats writes the row again and it can never be taken back out - the same rule
# the "[TITLE UNAVAILABLE]" guard follows. Measured 23 Nov 2026: 60 such pairs, 70
# extra rows in 183,924, and all 60 carried an IDENTICAL player count, so ignoring
# the repeat loses nothing and OR IGNORE needs no tie-break.
#
# An existing database keeps whatever index it already has, because IF NOT EXISTS
# matches on the name alone. That is fine: cloud/build_cloud.py deletes data.db and
# rebuilds it from the CSVs on every run, so the live site is always built against
# the unique one.

def fetch(ids):
    req = urllib.request.Request(API + ",".join(map(str, ids)),
                                 headers={"User-Agent": "rbx-timing/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r).get("data", [])
        except urllib.error.HTTPError as e:
            time.sleep(5 * (attempt + 1) if e.code == 429 else 2)
        except Exception:
            time.sleep(2)
    return []

def main():
    ids = [int(x) for x in open("games.txt").read().split() if x.strip().isdigit()]
    db = sqlite3.connect(DB); init(db)
    now = int(time.time())
    for i in range(0, len(ids), 50):
        for g in fetch(ids[i:i + 50]):
            # Roblox answers for an id it will not talk about any more with a
            # placeholder whose id is 0, not by leaving it out. Recording that
            # builds up a game called "[TITLE UNAVAILABLE]" out of every
            # deleted game at once. See cloud/collector_cloud.py, same guard.
            if not g.get("id"):
                continue
            db.execute("INSERT OR REPLACE INTO games VALUES(?,?,?,?)",
                       (g["id"], g.get("name"), g.get("genre_l1") or g.get("genre"), g.get("rootPlaceId")))
            db.execute("INSERT OR IGNORE INTO samples VALUES(?,?,?)", (g["id"], now, g.get("playing", 0)))
        db.commit(); time.sleep(1.5)

if __name__ == "__main__":
    main()
