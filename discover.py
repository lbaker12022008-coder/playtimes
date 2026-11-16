"""Finds popular Roblox games that are not on PlayTime yet, and adds them to games.txt.

WHY THIS EXISTS
Roblox's front page turns over fast. A game can go from nothing to 50,000 players in
a week, and anybody searching "<that game> busiest time" would find nothing here.
Checking by hand means remembering to check, so this does it on a schedule instead.

WHAT IT DOES, IN ORDER
  1. Reads Roblox's own charts (the "Top Trending", "Up-and-Coming" and "Most
     Popular" lists you see on the Roblox home page).
  2. Throws away every game already in games.txt.
  3. Throws away anything quieter than MIN_PLAYERS, and anything Roblox does not
     label Minimal or Mild.
  4. For the biggest few that are left, asks Roblox a second time - through the
     proper content-maturity endpoint - what that game's label really is, and
     confirms the ID is one the player-count API actually answers for.
  5. Appends the survivors to games.txt and prints what it did.

Nothing is ever removed. Taking a game off the site has consequences (build_site.py's
prune() deletes its page, and any link to it dies), so that stays a human job.

A new ID appears on the site about a day and a half later, not straight away: the
collector has to gather MIN_SAMPLES readings before build_site.py will write a page
for it. That is working as intended, not a fault.

Run it yourself any time:
    python discover.py --dry-run      # show what it would add, change nothing
    python discover.py                # actually add them

Stdlib only, on purpose: the build server installs nothing.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# ----------------------------------------------------------------- settings

GAMES_FILE = "games.txt"

# Roblox's maturity label, read back from Roblox rather than guessed from the name.
# This is the site's one hard rule: much of the audience is children. Several of the
# biggest games on Roblox are "moderate" (Murder Mystery 2, Dead Rails, BlockSpin,
# Da Hood, Deepwoken, Pressure), so the gap in games.txt is deliberate, not an
# oversight, and this script must not quietly close it.
ALLOWED_MATURITY = ("minimal", "mild")

# How many players a game needs on the charts before it is worth a page. The quietest
# game already on the site sits around 1,200 and the fifth-quietest around 2,900, so
# 2,000 keeps new arrivals in line with what is already here. A game below this that
# is genuinely taking off will clear the bar on a later run, and nothing is lost by
# waiting a day: its page cannot appear for a day and a half anyway.
MIN_PLAYERS = 2000

# The most games one run may add. There is usually a backlog of a couple of hundred
# eligible games, and adding them all at once would more than double the site in a
# single build - every one of them with no history, so every one a page saying "too
# new to say". A trickle also keeps the collector's run time steady.
MAX_ADD = 10

# A ceiling on how big games.txt may get. Nothing else in this script limits the
# total: MAX_ADD only paces it, so left alone it would keep adding every day for
# years. That matters because both jobs scale with the number of games - a cold build
# is about 40 seconds for 51 games, so 400 games is a five-minute build and 1,500
# would be twenty - and because every page added is another page competing for the
# same search traffic.
#
# In practice the charts hold about 540 games, of which roughly 180 are eligible
# today, so the backlog drains in a couple of weeks and after that only genuinely new
# arrivals are added - a few a week at most. This ceiling is therefore not expected to
# bite; it is here so that a change at Roblox's end cannot quietly grow the site to a
# thousand pages while nobody is watching. Raise it on purpose, not by accident.
MAX_TOTAL = 400

# How many pages of Roblox's chart list to read. Page one is Top Trending,
# Up-and-Coming, Top Playing Now, Fun with Friends and Top Revisited; page two adds
# Top Earning, Top Rated and Most Popular. Two pages is about 420 games, far more
# than MAX_ADD can use, and taking every sort on the page means a sort Roblox adds
# later is picked up without changing anything here.
SORT_PAGES = 2

HEADERS = {"User-Agent": "playtime/1.0 (+static site builder)"}
SORTS_API = "https://apis.roblox.com/explore-api/v1/get-sorts"
MATURITY_API = ("https://apis.roblox.com/experience-guidelines-api"
                "/experience-guidelines/get-age-recommendation")
GAMES_API = "https://games.roblox.com/v1/games?universeIds="


# ----------------------------------------------------------------- plumbing

def get_json(url, tries=3, data=None):
    """Same shape as roblox_api.get_json: retry a few times, then give up loudly."""
    headers = dict(HEADERS)
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(tries):
        req = urllib.request.Request(url, headers=headers, data=data)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                raise
            time.sleep(4 * (attempt + 1) if e.code == 429 else 2)
        except Exception:
            time.sleep(2)
    raise RuntimeError("gave up on " + url)


def read_ids(path):
    """The IDs already on the site.

    Parsed exactly the way collector.py, cloud/collector_cloud.py, build_site.py and
    seed_demo.py all parse it, so this file cannot disagree with them about what is
    in it. Note what that idiom means: ANY bare number in this file is read as a game
    ID, so games.txt must stay one plain ID per line with no comments. A line reading
    "# 140 games" would quietly become a request for universe 140.
    """
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [int(x) for x in f.read().split() if x.strip().isdigit()]


# ----------------------------------------------------------------- the charts

def chart_games(pages=SORT_PAGES):
    """Every game on Roblox's own charts: {universe_id: {...game..., "sorts": [...]}}.

    The sessionId is required - the endpoint returns nothing at all without one - but
    it identifies this request, not a person, and a fresh one is made every run.
    """
    session = str(uuid.uuid4())
    found, token = {}, ""
    for _ in range(max(1, pages)):
        url = SORTS_API + "?sessionId=" + session
        if token:
            url += "&sortsPageToken=" + urllib.parse.quote(token)
        payload = get_json(url)
        for sort in payload.get("sorts") or []:
            for game in sort.get("games") or []:
                uid = game.get("universeId")
                if not uid:
                    continue
                row = found.setdefault(int(uid), dict(game, sorts=[]))
                row["sorts"].append(sort.get("sortId"))
        token = payload.get("nextSortsPageToken") or ""
        if not token:
            break
        time.sleep(1)
    return found


def real_maturity(uid):
    """Roblox's content maturity for one game, or None if it could not be read.

    The charts already carry a contentMaturity field, and the two agreed on all 15
    games spot-checked on 15 Nov 2026, but this is the endpoint the rule is written
    against, so it gets the last word. Returning None on any failure is the point:
    confirm() treats "could not tell" as "do not add".
    """
    try:
        body = json.dumps({"universeId": int(uid)}).encode()
        data = get_json(MATURITY_API, data=body)
    except Exception:
        return None
    summary = (data.get("ageRecommendationDetails") or {}).get("summary") or {}
    label = (summary.get("ageRecommendation") or {}).get("contentMaturity")
    return label.lower() if isinstance(label, str) else None


def answers_to_player_api(ids):
    """The subset of ids that games.roblox.com actually returns a game for.

    An ID the charts know but this endpoint does not would sit in games.txt
    collecting nothing, and show up on the admin dashboard as a game ID that
    returned nothing. Cheaper to find out now, and it is one call per fifty games.
    """
    live = set()
    ids = [int(x) for x in ids]
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        try:
            data = get_json(GAMES_API + ",".join(str(x) for x in batch))
        except Exception:
            continue                      # cannot confirm this batch: add none of it
        for game in data.get("data") or []:
            if game.get("id"):
                live.add(int(game["id"]))
        time.sleep(1)
    return live


# ----------------------------------------------------------------- the decision

def shortlist(found, have, min_players=MIN_PLAYERS):
    """Chart games we do not have, big enough to bother with, labelled Minimal/Mild.

    Ranked by live player count, biggest first, because that is what the site is for:
    a game with more players has more people wondering when it is quiet. A game that
    "becomes the new thing" earns its place here through its player count, which is
    the same thing that question is really asking.
    """
    out = []
    for uid, game in found.items():
        if uid in have:
            continue
        if (game.get("playerCount") or 0) < min_players:
            continue
        if str(game.get("contentMaturity") or "").lower() not in ALLOWED_MATURITY:
            continue
        out.append(game)
    out.sort(key=lambda g: -(g.get("playerCount") or 0))
    return out


def confirm(candidates, limit=MAX_ADD):
    """Checks the shortlist in order and returns the first `limit` that pass.

    Two gates, both of which must say yes, and silence counts as no:
      - Roblox's own maturity endpoint says minimal or mild
      - the player-count API answers for that universe id
    """
    picked, rejected = [], []
    # One batch call up front tells us which IDs the player-count API knows. Only the
    # ones we might actually reach are checked, so this stays a call or two.
    maybe = candidates[:max(limit * 4, limit)]
    live = answers_to_player_api(g["universeId"] for g in maybe)
    for game in maybe:
        if len(picked) >= limit:
            break
        uid = int(game["universeId"])
        name = game.get("name") or str(uid)
        if uid not in live:
            rejected.append((name, uid, "the player-count API does not answer for this ID"))
            continue
        label = real_maturity(uid)
        if label is None:
            rejected.append((name, uid, "could not read its maturity label - skipped to be safe"))
            continue
        if label not in ALLOWED_MATURITY:
            rejected.append((name, uid, "Roblox labels it " + label))
            continue
        game["checked_maturity"] = label
        picked.append(game)
        time.sleep(0.5)
    return picked, rejected


def append_ids(path, ids):
    """Adds IDs to the end of games.txt without touching a single existing byte.

    Done in binary, appending, and that is not fussiness. games.txt is checked in with
    mixed line endings (111 CRLF lines and 29 LF ones as of 15 Nov 2026, which is what
    a file edited on Windows and on the server for a year looks like). Reading it as
    text and writing it back turns every line into whichever ending Python picks, so
    adding 10 games produced a diff of 121 insertions and 111 deletions - the ten new
    IDs completely hidden among 111 lines that only changed their invisible ending, and
    a fight with git's autocrlf on every single run.

    So: append only, and give the new lines whichever ending the file mostly already
    uses, so it does not get more mixed than it already is.
    """
    if not ids:
        return
    raw = b""
    if os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read()
    crlf = raw.count(b"\r\n")
    eol = b"\r\n" if crlf * 2 >= raw.count(b"\n") else b"\n"
    # A file not ending in a newline would otherwise join its last ID to our first.
    pad = b"" if (not raw or raw.endswith(b"\n")) else eol
    blob = pad + b"".join(str(int(i)).encode() + eol for i in ids)
    with open(path, "ab") as f:
        f.write(blob)


# ----------------------------------------------------------------- reporting

def safe_name(name):
    """A game's name, made safe to hand to a shell step through GITHUB_OUTPUT.

    These names are written by Roblox creators, so they are not ours to trust. Two
    separate hazards, and both are real rather than theoretical:
      - a newline would end the `names=` line early and let the rest of the name
        pose as another workflow output,
      - and the workflow puts this in a commit message, so a name like
        "$(something)" or a backtick must not survive into a shell.
    The workflow also passes it through an environment variable and quotes it, which
    is the actual defence; this keeps a daft name from reaching that point at all.
    Everything outside a small safe set becomes a space.
    """
    keep = " .,:'!?&+#@%*/()[]-_"
    name = "".join(c if (c.isalnum() or c in keep) else " " for c in (name or "?"))
    return " ".join(name.split())[:40] or "?"


def report(picked, rejected, counts, dry):
    """A summary that reads the same in a terminal and on the Actions run page.

    counts is (games on the charts, how many of those we already had, how many were
    eligible). Each is counted from a different population, so they are passed in
    rather than worked out from each other here - an earlier version added two of
    them together and printed a chart total that was not the chart total.
    """
    lines = []
    add = lines.append
    if picked:
        add("Adding %d game%s to games.txt:" % (len(picked), "" if len(picked) == 1 else "s"))
        add("")
        add("| Game | Universe ID | Players now | Maturity | Found on |")
        add("| --- | --- | --- | --- | --- |")
        for g in picked:
            add("| %s | %s | %s | %s | %s |" % (
                (g.get("name") or "?").replace("|", "/"),
                g["universeId"],
                "{:,}".format(g.get("playerCount") or 0),
                g.get("checked_maturity"),
                ", ".join(dict.fromkeys(g.get("sorts") or []))))
        add("")
    else:
        add("Nothing to add: no game on the charts passed every check this time.")
        add("")
    on_charts, already, eligible = counts
    add("Read %d games off Roblox's charts. %d are already on the site, %d were "
        "eligible to add, %d added%s." % (
            on_charts, already, eligible, len(picked),
            " (dry run, nothing written)" if dry else ""))
    if rejected:
        add("")
        add("Turned down:")
        for name, uid, why in rejected:
            add("  - %s (%s): %s" % (name, uid, why))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Add newly popular Roblox games to games.txt")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be added and change nothing")
    ap.add_argument("--max", type=int, default=MAX_ADD,
                    help="most games to add in one run (default %d)" % MAX_ADD)
    ap.add_argument("--min-players", type=int, default=MIN_PLAYERS,
                    help="ignore games quieter than this (default %d)" % MIN_PLAYERS)
    ap.add_argument("--max-total", type=int, default=MAX_TOTAL,
                    help="never let games.txt grow past this (default %d)" % MAX_TOTAL)
    args = ap.parse_args()

    have = read_ids(GAMES_FILE)
    if not have:
        print("games.txt is empty or missing - refusing to run, in case this is the "
              "wrong folder.", file=sys.stderr)
        return 1

    try:
        found = chart_games()
    except Exception as e:
        # An unofficial endpoint being down is not worth a red cross on the repo:
        # there is simply nothing new today, and tomorrow's run will try again.
        print("Could not read Roblox's charts (%s). Nothing added." % e)
        return 0

    owned = set(have)
    candidates = shortlist(found, owned, args.min_players)

    # Never take games.txt past the ceiling, even if today's allowance would.
    room = max(0, args.max_total - len(have))
    allowance = min(args.max, room)
    if room == 0:
        print("games.txt already holds %d games, which is the MAX_TOTAL ceiling in "
              "discover.py. Nothing added. Raise MAX_TOTAL if you want more."
              % len(have))
        return 0

    picked, rejected = confirm(candidates, allowance)
    if allowance < args.max and picked:
        print("Note: only %d more game(s) fit under the MAX_TOTAL ceiling of %d."
              % (room, args.max_total))

    if picked and not args.dry_run:
        append_ids(GAMES_FILE, [g["universeId"] for g in picked])

    counts = (len(found), len([u for u in found if u in owned]), len(candidates))
    text = report(picked, rejected, counts, args.dry_run)
    print(text)

    # The Actions run page renders this, so the result is readable without digging
    # through a log.
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## New games found\n\n" + text + "\n")
    # Tells the workflow whether there is anything to commit, and what to call it.
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("added=%d\n" % (0 if args.dry_run else len(picked)))
            f.write("names=%s\n" % ", ".join(
                safe_name(g.get("name")) for g in picked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
