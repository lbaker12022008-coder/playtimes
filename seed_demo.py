"""Makes a fake data.db so you can preview the site design without waiting for real data.

Run it like this (Windows):
    set SITE_OUT=preview
    python seed_demo.py
    python build_site.py
    cd preview
    python -m http.server

Then open http://localhost:8000 in your browser.

It uses the REAL game IDs from games.txt (so names, pictures, descriptions and events
are real) but INVENTS the player counts. Never point this at docs/.
"""
import math, os, random, sqlite3, sys, time

from collector import fetch, init

DB = "data.db"
DAYS = 40          # how many days of pretend history to make
EVERY = 30 * 60    # one pretend player count every 30 minutes

# Used only if Roblox cannot be reached, so the preview still works offline.
FALLBACK = [(6035872082, "RIVALS", "Fighting", 14063407)]


def shape(hour, weekday):
    """A believable daily rhythm: quiet at 5am, busy after school and on weekends."""
    peak = 1 - abs(((hour - 17) % 24 if (hour - 17) % 24 <= 12 else 24 - (hour - 17) % 24) / 12)
    return (0.35 + 0.65 * peak ** 1.6) * (1.25 if weekday >= 5 else 1.0)


def main():
    if os.environ.get("SITE_OUT", "") == "docs":
        sys.exit("Refusing to run: SITE_OUT is 'docs'. Demo data must never go in docs/.")
    ids = [int(x) for x in open("games.txt").read().split() if x.strip().isdigit()]
    rows = []
    for i in range(0, len(ids), 50):
        rows += [(g["id"], g.get("name"), g.get("genre_l1") or g.get("genre"), g.get("rootPlaceId"))
                 for g in fetch(ids[i:i + 50])]
        time.sleep(1)
    if not rows:
        print("Could not reach Roblox, using one made-up game instead.")
        rows = FALLBACK

    if os.path.exists(DB):
        os.remove(DB)
    db = sqlite3.connect(DB)
    init(db)
    db.executemany("INSERT OR REPLACE INTO games VALUES(?,?,?,?)", rows)

    rnd = random.Random(7)
    now = int(time.time())
    samples = []
    for n, (uid, name, _genre, _place) in enumerate(rows):
        base = 400 * 2.2 ** (len(rows) - n) ** 0.35      # a few huge games, many small ones
        drift = rnd.choice([-0.25, -0.08, 0, 0.05, 0.3])  # shrinking ... growing
        spike_day = rnd.randrange(3, DAYS - 2)            # one pretend update spike
        for s in range(DAYS * 86400 // EVERY):
            ts = now - s * EVERY
            t = time.gmtime(ts)
            age = s * EVERY / 86400.0
            v = base * shape(t.tm_hour, (t.tm_wday)) * (1 + drift * (1 - age / DAYS))
            if abs(age - spike_day) < 0.6:
                v *= 2.4
            samples.append((uid, ts, max(1, int(v * rnd.uniform(0.88, 1.12)))))
    db.executemany("INSERT INTO samples VALUES(?,?,?)", samples)
    db.commit()
    print(f"Made fake data: {len(rows)} games, {len(samples):,} player counts over {DAYS} days.")
    print("Now run:  python build_site.py")


if __name__ == "__main__":
    main()
