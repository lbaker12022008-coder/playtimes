# PlayTime: project notes for Claude Code

## About the owner
Beginner with almost no coding knowledge. Explain every step in plain language, give exact click-by-click or copy-paste instructions, and say what they should see when it works. Never assume they know Git or terminal commands.

## What this is
A website called **PlayTime** that shows when popular Roblox games are busiest and quietest (hourly heatmaps from public player counts). Goal: grow search traffic, then earn money from ads. Not affiliated with Roblox: keep the disclaimer in the footer and never use "Roblox" in the domain name. Many visitors may be kids, so do not collect personal data or add accounts or sign-ups (COPPA).

## How it works
1. `cloud/collector_cloud.py` (uses `collector.py`) reads universe IDs from `games.txt`, calls Roblox public APIs, and appends rows to `games.csv` and `samples.csv` on the **`data` branch**. (Icons are not stored: `build_site.py` fetches them fresh from `thumbnails.roblox.com` at build time.)
2. `.github/workflows/collect.yml` runs it every ~30 minutes, 3 samples 10 minutes apart per run.
3. `cloud/build_cloud.py` turns the CSVs into `data.db`, then `build_site.py` writes the static site to `docs/` on **`main`**.
4. `.github/workflows/build.yml` runs nightly, by hand, and automatically on any push to `main` that changes `build_site.py`, `cloud/build_cloud.py` or `collector.py`. It commits `docs/`.
5. Cloudflare Workers (project `playtimes`) auto-deploys from `main` within seconds of each push. Its deploy command must be plain `npx wrangler deploy`; settings now come from `wrangler.jsonc`.

## Admin dashboard (owner only)
- `worker/index.js` is a Cloudflare Worker deployed alongside the static site. It serves `/admin` (behind an admin code) and `POST /api/hit` (counts page views). Everything else is still plain files from `docs/`.
- Secrets live in Cloudflare, never in the repo: `ADMIN_CODE` and `SESSION_SECRET` (set with `npx wrangler secret put NAME`).
- Analytics are stored in the D1 database `playtime-admin` (`worker/schema.sql`). Page views only: path + date, no cookies, no IPs. Login attempts store a salted one-way hash for rate limiting and are deleted after 24h.
- `build_site.py` writes `worker/stats.js` on every `docs` build; the dashboard reads it. Preview builds skip it.
- Deploy with `npx wrangler deploy` (no `--assets` flag: `wrangler.jsonc` sets it, and passing both is an error).
- Never commit `.dev.vars` or `.wrangler/`.

## Files
- `build_site.py`: all page design (CSS, HTML, JS) lives here. Settings at the top: `SITE`, `MIN_SAMPLES`, `ADS`, `NOINDEX`, `OUT`.
- `collector.py`, `cloud/collector_cloud.py`, `cloud/build_cloud.py`: data pipeline. They import each other, so change them together.
- `seed_demo.py`: fake data for local previews. `lookup_ids.py` turns game links into universe IDs. `check_missing.py` lists IDs Roblox does not return.
- `games.txt`: one universe ID per line (not place IDs).

## Rules
- The Roblox endpoints are unofficial and can change. Use only public endpoints. Never ask for logins, never add Robux generators or gambling.
- Local preview: `set SITE_OUT=preview`, `python seed_demo.py`, `python build_site.py`, then serve the `preview` folder with `python -m http.server`. Never overwrite `docs/` with demo data.
- `data` branch changes constantly. Do not merge it into `main`. Cloudflare must not build it.
- Before editing, pull the latest (the build job commits to `docs/` on `main`).
- The owner buys domains and creates Cloudflare/AdSense accounts and accepts terms themselves.
- Past mistake to avoid: pasting one file's contents into another (for example workflow text into `collector.py`). Check the first line of each file after any edit.

## Current status
- Collecting data (51 games in `games.txt`, all Roblox maturity "Minimal" or "Mild"). Site live on a `workers.dev` address with `NOINDEX = True` (hidden from Google while designing).
- `MIN_SAMPLES` may be lowered for design work. Set it back to 200 and `NOINDEX = False` before launch.
- Done: About + Privacy pages, game thumbnails, parent section (game passes, fetched at build time from `apis.roblox.com/game-passes/v1/universes/{id}/game-passes`; the old `games.roblox.com` one is dead), Trending page, Save/favorites (browser localStorage only), category pages (from Roblox `genre_l1`, saved in the `genre` column; categories need 2+ games).
- Sitemap uses full URLs once `DOMAIN` is set in `build_site.py`.

## To do
1. Launch: buy domain, set `DOMAIN` and `CONTACT`, `MIN_SAMPLES = 200`, `NOINDEX = False`; add to Google Search Console; AdSense once 20+ pages have real data (mark site as child-directed).
2. Trending page fills in after ~2 weeks of data for each game.
