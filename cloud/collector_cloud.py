"""Cloud version of the collector: appends to CSV files (kept on the 'data' branch)."""
import csv, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from collector import fetch
except ImportError:
    from ..collector import fetch  # noqa

def main(d="datarepo"):
    os.makedirs(d, exist_ok=True)
    ids = [int(x) for x in open("games.txt").read().split() if x.strip().isdigit()]
    now = int(time.time()); games, rows = {}, []
    for i in range(0, len(ids), 50):
        for g in fetch(ids[i:i + 50]):
            games[str(g["id"])] = [g["id"], g.get("name"), g.get("genre_l1") or g.get("genre"), g.get("rootPlaceId")]
            rows.append([g["id"], now, g.get("playing", 0)])
        time.sleep(1.5)
    gp = f"{d}/games.csv"; known = {}
    if os.path.exists(gp):
        known = {r[0]: r for r in csv.reader(open(gp, newline="", encoding="utf-8"))}
    known.update(games)
    with open(gp, "w", newline="", encoding="utf-8") as f: csv.writer(f).writerows(known.values())
    with open(f"{d}/samples.csv", "a", newline="") as f: csv.writer(f).writerows(rows)
    write_summary(d, known)
    print(f"Saved {len(rows)} samples")


def write_summary(d, known):
    """A few KB the admin dashboard reads straight from GitHub, so its numbers are
    as fresh as the last collection instead of the last site build. samples.csv
    itself grows to megabytes, which is far too much to fetch on every page load."""
    counts, first, last = {}, {}, {}
    try:
        with open(f"{d}/samples.csv", newline="") as f:
            for row in csv.reader(f):
                if len(row) < 2 or not row[0].isdigit(): continue
                gid = row[0]
                try: ts = int(row[1])
                except ValueError: continue
                counts[gid] = counts.get(gid, 0) + 1
                if gid not in first or ts < first[gid]: first[gid] = ts
                if gid not in last or ts > last[gid]: last[gid] = ts
    except OSError:
        return
    summary = {
        "updated": int(time.time()),
        "total_samples": sum(counts.values()),
        "games": sorted(
            ({"id": gid, "name": (known.get(gid) or [None, gid])[1], "samples": n,
              "first": first.get(gid), "last": last.get(gid)} for gid, n in counts.items()),
            key=lambda g: -g["samples"]),
    }
    with open(f"{d}/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, separators=(",", ":"))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "datarepo")
