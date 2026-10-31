# PlayTime: project notes for Claude Code

## About the owner
Beginner with almost no coding knowledge. Explain every step in plain language, give exact click-by-click or copy-paste instructions, and say what they should see when it works. Never assume they know Git or terminal commands.

## What this is
A website called **PlayTime** that shows when popular Roblox games are busiest and quietest (hourly heatmaps from public player counts). Goal: grow search traffic, then earn money from ads. Not affiliated with Roblox: keep the disclaimer in the footer and never use "Roblox" in the domain name. Many visitors may be kids, so do not collect personal data or add accounts or sign-ups (COPPA).

## How it works
1. `cloud/collector_cloud.py` (uses `collector.py`) reads universe IDs from `games.txt`, calls Roblox public APIs, and appends rows to `games.csv` and `samples.csv` on the **`data` branch**. It also saves each game's icon URL.
2. `.github/workflows/collect.yml` runs it every ~30 minutes, 3 samples 10 minutes apart per run.
3. `cloud/build_cloud.py` turns the CSVs into `data.db`, then `build_site.py` writes the static site to `docs/` on **`main`**.
4. `.github/workflows/build.yml` runs nightly (and by hand) and commits `docs/`.
5. Cloudflare Workers (project `playtimes`) serves `docs/` from `main` via `npx wrangler deploy --assets ./docs --name playtimes --compatibility-date 2025-09-09`.

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
- Collecting data (22 games). Site live on a `workers.dev` address with `NOINDEX = True` (hidden from Google while designing).
- `MIN_SAMPLES` may be lowered for design work. Set it back to 200 and `NOINDEX = False` before launch.

## To do
1. Privacy Policy and About pages (needed before AdSense).
2. Sitemap with full URLs once the domain exists (`sitemap.txt` currently has relative paths).
3. Parent safety section (gamepass counts and prices from `games.roblox.com/v1/games/{universeId}/game-passes`).
4. Trending / dying games page, favorites saved on the device (no accounts), category pages.
5. Raise the game list to 50+ with real data; check `games.csv` for missing IDs.
6. Launch: domain, Google Search Console, then AdSense once 20+ pages have real data.
