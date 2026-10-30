"""Turns the CSV data into data.db, then builds the site into docs/."""
import csv, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collector import init
import build_site

def main(d="datarepo"):
    if os.path.exists("data.db"): os.remove("data.db")
    db = sqlite3.connect("data.db"); init(db)
    db.executemany("INSERT OR REPLACE INTO games VALUES(?,?,?,?)", csv.reader(open(f"{d}/games.csv", newline="", encoding="utf-8")))
    db.executemany("INSERT INTO samples VALUES(?,?,?)", csv.reader(open(f"{d}/samples.csv", newline="")))
    db.commit(); db.close(); build_site.main()

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "datarepo")
