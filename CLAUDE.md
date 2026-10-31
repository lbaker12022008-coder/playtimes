# PlayTime: project notes for Claude Code

## About the owner
Beginner with almost no coding knowledge. Explain every step in plain language, give exact click-by-click or copy-paste instructions, and say what they should see when it works. Never assume they know Git or terminal commands.

## What this is
A website called **PlayTime** that shows when popular Roblox games are busiest and quietest (hourly heatmaps from public player counts). Goal: grow search traffic, then earn money from ads. Not affiliated with Roblox: keep the disclaimer in the footer and never use "Roblox" in the domain name. Many visitors may be kids, so the site must work fully without signing in, and must never collect personal data from anyone who has not signed in (COPPA). The one exception is the optional "Sign in with Roblox" described below; do not add any other account, sign-up or data collection.

## How it works
1. `cloud/collector_cloud.py` (uses `collector.py`) reads universe IDs from `games.txt`, calls Roblox public APIs, and appends rows to `games.csv` and `samples.csv` on the **`data` branch**. (Icons are not stored: `build_site.py` fetches them fresh from `thumbnails.roblox.com` at build time.)
2. `.github/workflows/collect.yml` runs it every ~30 minutes, 3 samples 10 minutes apart per run.
3. `cloud/build_cloud.py` turns the CSVs into `data.db`, then `build_site.py` writes the static site to `docs/` on **`main`**. While building, `roblox_api.py` also fetches the things that change on their own and are not worth storing: icons, descriptions, game passes and the creators' event calendars.
4. `.github/workflows/build.yml` runs nightly, by hand, and automatically on any push to `main` that changes `build_site.py`, `roblox_api.py`, `cloud/build_cloud.py`, `collector.py` or `games.txt`. It commits `docs/`.
5. Cloudflare Workers (project `playtimes`) auto-deploys from `main` within seconds of each push. Its deploy command must be plain `npx wrangler deploy`; settings now come from `wrangler.jsonc`.

## Admin dashboard (owner only)
- `worker/index.js` is a Cloudflare Worker deployed alongside the static site. It serves `/admin` (behind an admin code) and `POST /api/hit` (counts page views). Everything else is still plain files from `docs/`.
- Secrets live in Cloudflare, never in the repo: `ADMIN_CODE` and `SESSION_SECRET` (set with `npx wrangler secret put NAME`).
- Analytics are stored in the D1 database `playtime-admin` (`worker/schema.sql`). Page views only: path + date, no cookies, no IPs. Login attempts store a salted one-way hash for rate limiting and are deleted after 24h.
- `build_site.py` writes `worker/stats.js` on every `docs` build; the dashboard reads it. Preview builds skip it.
- Deploy with `npx wrangler deploy` (no `--assets` flag: `wrangler.jsonc` sets it, and passing both is an error).
- Never commit `.dev.vars` or `.wrangler/`.

## Sign in with Roblox (optional, 13+)
- `worker/auth.js` serves `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/me`, `/api/favs` and `/api/delete-me`. `worker/index.js` calls `handleAuth()` and does nothing else with it.
- Purpose: saved games follow a person between devices. **Everything on the site still works signed out**, and a signed-out visitor gets no cookies at all.
- We store only: Roblox user ID, display name, and saved game slugs (`worker/schema_auth.sql`). No email, password, age or browsing history. Roblox blocks under-13s from authorising outside apps, so signers-in are 13+.
- OAuth is the plain authorization-code flow with `client_secret`. That is correct for a confidential client like a Worker; Roblox only *requires* PKCE for public clients that cannot keep a secret. Do not "fix" this by adding PKCE without testing, since Roblox's docs say to send either the secret or a verifier, not both.
- If `ROBLOX_CLIENT_ID`, `ROBLOX_CLIENT_SECRET` or `SESSION_SECRET` is missing, `configured()` is false, `/api/me` answers `available:false`, and **no sign-in button is rendered**. So the site is safe to deploy before the setup below is done.
- `MAX_FAVS` in `worker/auth.js` and `MAXFAVS` in `FAVJS` must stay equal.
- Saved-game merging: the first time a device signs in to an account it hands over anything saved locally, and records that account's id in `pt_joined`. After that the server wins, so un-saving a game on one device is not undone by another device's older list.

### Setup still needed before sign-in works (owner does these)
1. Create the OAuth app at create.roblox.com → Credentials, scopes `openid profile`, redirect URI `<site>/auth/callback` (register every address the site answers on, including the `workers.dev` one).
2. `npx wrangler secret put ROBLOX_CLIENT_ID` and `npx wrangler secret put ROBLOX_CLIENT_SECRET`.
3. `npx wrangler d1 execute playtime-admin --remote --file worker/schema_auth.sql` (creates `users` and `favourites`).
4. `npx wrangler deploy`.
5. Submit the Roblox app for review. Until it passes, Roblox caps the app at 10 signed-in users, so sign-in works for testing but not for the public. Needs a demo video under a minute.

## Files
- `build_site.py`: all page design (CSS, HTML, JS) lives here. Settings at the top: `SITE`, `MIN_SAMPLES`, `ADS`, `NOINDEX`, `OUT` (reads `SITE_OUT`), `DOMAIN`, `CONTACT`, `SPIKE`.
- `roblox_api.py`: every Roblox call made while building (icons, descriptions, game passes, events). Answers are cached in `.cache/` (gitignored) so a rebuild is instant; a cold build takes about 40 seconds for 51 games. If an endpoint dies, the function returns `None` and the page quietly leaves that section out.
- `collector.py`, `cloud/collector_cloud.py`, `cloud/build_cloud.py`: data pipeline. They import each other, so change them together.
- `seed_demo.py`: invents player counts for local previews, using the real IDs in `games.txt` so names, pictures, descriptions and events are real. It refuses to run if `SITE_OUT=docs`.
- `games.txt`: one universe ID per line (not place IDs).
- `build_site.py` ends by pruning `docs/game/` and `docs/category/`: any page this build did not write is deleted, so a renamed game, an ID removed from `games.txt`, or a game dropping below `MIN_SAMPLES` cannot leave an orphan page live for ever. It runs last, so a build that fails part way deletes nothing, and it never touches top-level files you add by hand (`ads.txt`, a favicon, `CNAME`). The build job uses `git add -A docs` so those deletions are committed.
- Browser code lives in `build_site.py` as `SHARED_JS` (timezone shifting, busy-ness bands, "next good block", escaping) plus one block per page. Anything that puts a game name into HTML in the browser must pass it through `esc()`: names come from Roblox and can contain quotes and angle brackets.

## Rules
- The Roblox endpoints are unofficial and can change. Use only public endpoints. Never ask for a Roblox password (sign-in happens on Roblox's own site), never add Robux generators or gambling.
- Local preview: `set SITE_OUT=preview`, `python seed_demo.py`, `python build_site.py`, then serve the `preview` folder with `python -m http.server`. Never overwrite `docs/` with demo data.
- `data` branch changes constantly. Do not merge it into `main`. Cloudflare must not build it.
- Before editing, pull the latest (the build job commits to `docs/` on `main`).
- The owner buys domains and creates Cloudflare/AdSense accounts and accepts terms themselves.
- Past mistake to avoid: pasting one file's contents into another (for example workflow text into `collector.py`). Check the first line of each file after any edit.

## Current status
- Collecting data (51 games in `games.txt`, all Roblox maturity "Minimal" or "Mild"). Site live on a `workers.dev` address with `NOINDEX = True` (hidden from Google while designing).
- `MIN_SAMPLES` may be lowered for design work. Set it back to 200 and `NOINDEX = False` before launch.
- Sitemap uses full URLs once `DOMAIN` is set in `build_site.py`.

### Done
- About + Privacy pages, game thumbnails, Save/favorites (browser localStorage only).
- For-parents game-pass section, fetched from `apis.roblox.com/game-passes/v1/universes/{id}/game-passes` (the old `games.roblox.com` one is dead).
- Category pages from Roblox `genre_l1` (saved in the `genre` column; a category needs 2+ games).
- Sections across the top of every page (`TABS` in `build_site.py`): All games, Most popular, Trending, Growing, Shrinking, Events, Compare, Plan a session. Genres are pills on the homepage.
- Homepage: "What are you looking for?" (busy / quiet / browsing) hides the games that are not quiet or busy at the visitor's current hour and puts the best first, off a 168-digit busy-ness string per game baked into the page, so there is no extra request. Games mostly get busy at the same times, so at some hours nothing matches; it then shows everything in order and says why, rather than an empty page. Search goes through the same `refresh()` so the two cannot fight over which tiles are hidden.
- Per-game pages: event calendar, recent updates and changes, game description, "Is X dead?" verdict with a 45-day chart, "Days the player count jumped" (any day `SPIKE`x busier than the week before, matched against the creators' events), and "Plan my session".
- **Live countdown**: "Quietest window starts in 2h 14m 07s", ticking every second, on each game page and on `/plan.html`. `plan()`/`draw()` works out the hour being aimed at and `tick()` only rewrites the clock, so the digits move every second without redoing the maths. The block is recomputed every 5 minutes, and straight away once the countdown reaches zero.
- **Update rhythm** (`update_pattern`): "Updates usually arrive on a Friday around 2 PM your time, about every 7 days." Worked out from the start times of the creators' past events, plus spike days for the weekday only (a spike is measured over a whole day, so its hour means nothing). Deliberately cautious: needs 8+ dates, a weekday holding 30%+ of them, a repeating hour before it names one, and 4+ gaps with a median under 32 days before it claims an interval. 34 of 51 games currently qualify. Stored in UTC and converted in the browser, like every other time on the site.
- **Similar games** row at the foot of each game page (`similar`): same category first, then closest in typical player count on a log scale, so 1K vs 2K counts like 100K vs 200K. The wording changes to "games with about as many players" when the category could not fill the row.
- `main()` runs in **two passes**: pass one works out every game's numbers, pass two writes the pages. It has to be this way round because the "Similar games" row on each page needs to know about all the others. The empty-site guard sits between them, so it fires before anything is written.
- `/events.html` site-wide calendar, `/compare.html` (two games overlaid, loads `/data.json`), `/plan.html`.
- Events and updates come from `apis.roblox.com/virtual-events/v1/universes/{id}/virtual-events`. Creators use these as a changelog, so past ones are the "recent updates" list and unfinished ones are the calendar. Unofficial endpoint: if it dies, both sections disappear on their own.
- Timezones: `tzOff()` in `SHARED_JS` rounds the visitor's offset to whole hours. Every page must use it. The homepage and the game pages convert between local and UTC in opposite directions, and they disagreed by an hour for half-hour timezones (India) until this was shared.

## To do
Launch checklist, in order:
1. **Buy the domain**, then set `DOMAIN` and `CONTACT` at the top of `build_site.py`. `CONTACT` must not be a personal address. Setting `DOMAIN` is what turns the sitemap into full web addresses.
2. **`MIN_SAMPLES = 200`** - done (31 Oct 2026). A game needs about a day and a half of collecting to reach it.
3. **Switch on Sign in with Roblox** when ready: the four `wrangler` steps under "Sign in with Roblox" above. Do them in that order; setting the secrets without creating the D1 tables makes the button appear and then fail.
4. **`NOINDEX = False`**, then add the site to Google Search Console and submit `sitemap.txt`. Do this only once the pages have real data in them, so Google's first look is a good one.
5. **AdSense** once 20+ pages have real data. Mark the site as child-directed. Paste the script into `ADS`; the Privacy Policy changes its ad wording on its own when `ADS` is set, so re-read it afterwards.
6. Check `POLICY_DATE` is right whenever the Privacy Policy or Terms change.

Waiting on data, nothing to do:
- Trending / Growing / Shrinking need ~2 weeks per game, the "Is X dead?" verdict needs 10 days, and "Days the player count jumped" needs about 2 weeks.
- As of 31 Oct 2026 collection had only just started (~600 player counts), so no game met `MIN_SAMPLES = 200` yet and the site showed only its section pages. This is expected and clears itself.
