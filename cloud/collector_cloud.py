"""Cloud version of the collector: appends to CSV files (kept on the 'data' branch)."""
import csv, os, sys, time
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
            games[str(g["id"])] = [g["id"], g.get("name"), g.get("genre"), g.get("rootPlaceId")]
            rows.append([g["id"], now, g.get("playing", 0)])
        time.sleep(1.5)
    gp = f"{d}/games.csv"; known = {}
    if os.path.exists(gp):
        known = {r[0]: r for r in csv.reader(open(gp, newline="", encoding="utf-8"))}
    known.update(games)
    with open(gp, "w", newline="", encoding="utf-8") as f: csv.writer(f).writerows(known.values())
    with open(f"{d}/samples.csv", "a", newline="") as f: csv.writer(f).writerows(rows)
    print(f"Saved {len(rows)} samples")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "datarepo")
