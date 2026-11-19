# PlayTime: project notes for Claude Code

## About the owner
Beginner with almost no coding knowledge. Explain every step in plain language, give exact click-by-click or copy-paste instructions, and say what they should see when it works. Never assume they know Git or terminal commands.

## What this is
A website called **PlayTime** that shows when popular Roblox games are busiest and quietest (hourly heatmaps from public player counts). Goal: grow search traffic, then earn money from ads. Not affiliated with Roblox: keep the disclaimer in the footer and never use "Roblox" in the domain name. Many visitors may be kids, so the site must work fully without signing in, and must never collect personal data from anyone who has not signed in (COPPA). The one exception is the optional "Sign in with Roblox" described below; do not add any other account, sign-up or data collection.

## How it works
1. `cloud/collector_cloud.py` (uses `collector.py`) reads universe IDs from `games.txt`, calls Roblox public APIs, and appends rows to `games.csv` and `samples.csv` on the **`data` branch**. (Icons are not stored: `build_site.py` fetches them fresh from `thumbnails.roblox.com` at build time.)
2. `.github/workflows/collect.yml` runs it every ~30 minutes, 3 samples 10 minutes apart per run.
3. `cloud/build_cloud.py` turns the CSVs into `data.db`, then `build_site.py` writes the static site to `docs/` on **`main`**. While building, `roblox_api.py` also fetches the things that change on their own and are not worth storing: icons, descriptions, game passes and the creators' event calendars.
4. `.github/workflows/build.yml` runs **four times a day (04:30, 10:30, 16:30 and 22:30 UTC)**, by hand, and automatically on any push to `main` that changes `build_site.py`, `roblox_api.py`, `cloud/build_cloud.py`, `collector.py` or `games.txt`. It commits `docs/`. **It was once a night, and the thing that moved it was a game's own picture**: creators repaint an icon to advertise an update, often a countdown that is wrong within hours, and on 14 Nov 2026 34 of the 140 icons on the live site had changed within half a day of the build that fetched them - two more within the half hour after the next build. Six hours is the cap on how wrong a picture can be, and it cannot be zero while the site is built as files rather than fetched per visitor. The admin dashboard's "has not rebuilt" warning is tuned to the same number (8 hours, in `worker/index.js`) and must move with it. **Its last step stages the built pages onto whatever `main` is now rather than replaying anything, and that matters**: `main` moves while a build is running - a second commit right after the one that triggered it is enough - and a plain `git push` is then rejected as not-a-fast-forward, while a rebase cannot replay the commit either (the checkout is shallow and both sides touch `docs/`). The site is already built and checked by then, so anything that fails at that step throws a perfectly good site away with no sign on the site that anything happened. That is exactly how `NOINDEX = False` built cleanly on 14 Nov 2026 and never reached anybody. **Changing the workflow file does not trigger a build** (it is not in `paths`), so after editing it, start one by hand: GitHub -> Actions -> "build site" -> Run workflow. **If a change to `build_site.py` ever seems not to have reached the site, check Actions before touching the code** - the build failing is far likelier than the code being wrong.
5. Cloudflare Workers (project `playtimes`) auto-deploys from `main` within seconds of each push. Its deploy command must be plain `npx wrangler deploy`; settings now come from `wrangler.jsonc`.

## Finding new games (`discover.py`)
Roblox's front page turns over in weeks. A game can go from nothing to 50,000 players
in days, and nobody searching for its quiet hours would find us. `discover.py` reads
Roblox's own charts once a day and appends what is missing to `games.txt`, so the site
keeps up without anyone remembering to check.

- **The charts endpoint is `apis.roblox.com/explore-api/v1/get-sorts?sessionId=<uuid>`**,
  and like omni-search it returns nothing at all without a `sessionId`. Page one holds
  Top Trending, Up-and-Coming, Top Playing Now, Fun with Friends and Top Revisited;
  `nextSortsPageToken` leads to Top Earning, Top Rated and Most Popular. Two pages is
  about 540 unique games. Each game arrives with `universeId`, `playerCount`,
  `genreL1` **and `contentMaturity`**, so one call does most of the work. Every sort on
  the page is used rather than a chosen few, so a sort Roblox adds later is picked up
  with no change here.
- **Three gates, and silence always counts as no.** A game must be labelled `minimal`
  or `mild`, have at least `MIN_PLAYERS` (2,000, which is where the quietest games
  already on the site sit), and be answered for by the player-count API. The maturity
  label is then **read a second time** from the endpoint the rule is written against
  (`experience-guidelines/get-age-recommendation`, under
  `ageRecommendationDetails.summary.ageRecommendation.contentMaturity`) rather than
  trusted from the charts. The two agreed on all 15 games spot-checked on 15 Nov 2026,
  including Murder Mystery 2, Dead Rails and BlockSpin all coming back `moderate` as
  the notes above say they should - but a lookup that *fails* returns `None` and the
  game is skipped, because the one thing this script must never do is add a game it
  could not check. There are tests for every one of those gates.
- **`MAX_ADD` (10) paces it and `MAX_TOTAL` (400) bounds it.** There were about 180
  eligible games waiting the day this was written, and adding them at once would more
  than double the site in one build with every new page saying "too new to say". The
  ceiling exists because nothing else limits the total: both jobs scale with the game
  count (a cold build is ~40s per 51 games), so an unattended job that only ever adds
  needs a stop.
- **It only ever adds.** Removing a game deletes its page through `prune()` and kills
  every link to it, so that stays a human decision.
- **A new ID has no page for about a day and a half**, until the collector reaches
  `MIN_SAMPLES`. That is `index_ok()` working, not a fault, so do not go looking for a
  bug on the day you add one.
- `.github/workflows/discover.yml` runs it at **04:00 UTC**, half an hour before the
  04:30 build. **Its commit message ends with `[skip ci]` on purpose**: `games.txt` is
  in `build.yml`'s `paths`, but a game added at 04:00 has no samples yet, so that
  build would produce a byte-identical site. The 04:30 build picks the IDs up anyway.
- **A run started by hand defaults to a dry run** (the `dry_run` input is `true`), so
  pressing the button cannot change the site by accident; the daily schedule passes no
  inputs and so runs for real. `python discover.py --dry-run` does the same locally.
- **Game names are untrusted and are treated as such.** They are written by Roblox
  creators, and the workflow puts them in a commit message, so `safe_name()` reduces a
  name to letters, digits and simple punctuation before it is written to
  `GITHUB_OUTPUT` - a newline there would let a name pose as another workflow output -
  and the workflow passes it through an environment variable in double quotes instead
  of letting the template paste it into the script.
- The push can be rejected if `main` moved, so the step retries with
  `git pull --rebase` (and the checkout uses `fetch-depth: 0`, since a shallow one
  cannot rebase). Unlike `build.yml`, a failure here costs nothing - no stale site,
  and tomorrow's run finds the same games - which is why it does not need that job's
  more careful dance.

## Admin dashboard (owner only)
- `worker/index.js` is a Cloudflare Worker deployed alongside the static site. It serves `/admin` (behind an admin code) and `POST /api/hit` (counts page views). Everything else is still plain files from `docs/`.
- Secrets live in Cloudflare, never in the repo: `ADMIN_CODE` and `SESSION_SECRET` (set with `npx wrangler secret put NAME`).
- Analytics are stored in the D1 database `playtime-admin` (`worker/schema.sql`). Page views only: path + date, no cookies, no IPs. Login attempts store a salted one-way hash for rate limiting and are deleted after 24h.
- `build_site.py` writes `worker/stats.js` on every `docs` build; the dashboard reads it. Preview builds skip it.
- **It looks like the public site, and the colours are not copied by hand.** `build_site.py` also writes `worker/theme.js` on every `docs` build, holding the `LIGHT` and `DARK` palettes as strings, and `worker/index.js` imports them into its `:root` rules. So a colour changed in `build_site.py` reaches the dashboard on the next build and the two cannot drift apart. **Only the colours travel**: the layout is the dashboard's own, because the site is for a visitor reading about one game and the dashboard is for one person reading numbers. The theme button saves to the same `pt_theme` key the site uses, so a choice made on either carries to the other. Preview builds skip `theme.js` as well, and the build workflow commits it alongside `stats.js`.
- **Four tabs, not one long page** (`Overview`, `Visitors`, `Games & data`, `Launch checklist`). Which one is open is kept in `pt_admin_tab`. The panels are four `<div>`s filled by `render()`, and only the visible one is not `hidden`, so everything is built once from a single `/admin/data` call.
- **The Overview opens with "Needs doing"**, built from real conditions only: an overdue build, a stalled collector, IDs Roblox did not return, `NOINDEX` still on, `MIN_SAMPLES` below 200, no domain, no page views yet. When the list is empty it says so rather than showing nothing. **Do not pad it with advice that is always true**: the point is that anything on it is something to go and do.
- **Numbers are drawn, not listed.** `lineChart`/`chartCursor` are the page-views line and its drag-to-read crosshair, built the same way as the site's `dayGraph` and `graphCursor` (a wash under the line, and a gap in the days breaks the line rather than being drawn as a zero we never recorded). `spark` is the tiny line inside a tile, `ring` the progress circle, `colBars` the days of the week, and `barRows` the sideways bars for pages and games. `lineChart` takes an `id` because its wash gradient needs a unique name on the page.
- **The Launch checklist shows only what is left.** Ticked items fold into a `<details class="donelist">` below the open ones, counted in its summary ("8 finished items"). They are **folded, not deleted** - the rows stay in `todos` in D1, because "did I ever do Search Console?" is a real question months later. Ticking a box moves that row between the two lists *after* the save lands (`settleTodo`), never before: a row that jumped before the server agreed would have to jump back on a failure and would read as the page glitching. `paintRings()` then redraws **both** progress rings, the Launch tab's and the Overview card's, which until Nov 2026 sat at their load-time number while the list beside them moved.
- **No CSS escape may be written anywhere in `worker/index.js`,** not even inside a comment. The dashboard lives in a backtick template literal, and a backslash followed by a digit (`content:'\25B8'`) is read as an octal escape, which is a **syntax error in a module and takes the whole worker down**. Writing that very warning out with an example is what caused it once. Describe such escapes in words, never in symbols - and the summary marker is therefore the browser's own triangle.
- **Five tabs, and the fifth is People** (18 Nov 2026). Sign-ins, saved games and
  notifications had been live for days with nothing anywhere to say whether any of
  them worked - the rows were in the same D1 database the dashboard was already
  reading. It shows how many have signed in and come back, how many games are saved
  and followed, which switches people choose, and **what the push service last
  answered for each device**, which until then was only readable by typing a
  `wrangler d1 execute` at a terminal. The overview raises a warning when any device
  is failing, because a notification that silently does not arrive is the one fault
  this site cannot otherwise notice.
  - **Counts and game names only: no display names, no Roblox IDs, no endpoints, no
    keys.** Knowing whether the feature works does not need to know who, and a
    dashboard is a screen that gets photographed and shared. `devList` selects five
    columns and none of them identify a person.
  - **Every people query goes through `soft()`**, which returns a fallback on any
    error. `users`, `favourites` and the three push tables are each created by their
    own schema file, so one that was never run must leave a quiet tile rather than
    take the whole dashboard down.
  - **`push_sent` is cleared to two days by `runPushCron`**, so the sends figure is
    a recent count and never a running total. The panel says so; do not reword it
    into "sent all time".
- **The launch framing is retired** (18 Nov 2026). The checklist is 8 of 9 done -
  only AdSense is left - so the tab is "Checklist" now and the all-clear line talks
  about the site running rather than being launch-ready. The three settled
  conditions (no domain, `NOINDEX` on, `MIN_SAMPLES` under 200) are **kept in the
  code** even though they can no longer fire: they are regression alarms now, not
  to-do items, and they cost nothing while silent.
- **Where visitors came from is deliberately NOT recorded.** It was asked for and
  turned down on 18 Nov 2026 for one reason: the Privacy Policy says we record "the
  page address, the date, and that number of seconds, and nothing else". That is a
  clean promise on a site read by nine-year-olds, and a referrer column would make
  it false - so it would mean rewriting the policy and moving `POLICY_DATE` to buy
  something Search Console already gives for nothing. What the dashboard shows
  instead comes out of the `views` table it already had: **what kind of page** people
  open (the Nov 2026 split gave every game four more pages and nothing said whether
  anyone read them) and **which games are climbing**, this week against last.
- The "Every game" table sorts and filters in the browser (`wireTable`), since all 100 rows are already on the page. Sorting falls back to the name so rows do not jump about between clicks, and a game with no trend yet sorts to the bottom instead of counting as zero.
- `worker/index.js` holds the dashboard inside backtick template literals, so **a backtick anywhere in the dashboard's own CSS or JavaScript ends the string early** - including in a comment. Keep its inline script on single quotes and concatenation, the way it is written now.
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

### Unblocked by the domain, 13 Nov 2026
`playtimestats.com` is registered and attached to the worker, so the redirect URL Roblox kept
refusing is now a real address. A **second OAuth app** was made at that point: the live client id
is `5479373624062556036`, and the old app (`5285601446665495033`) should be deleted. Both secrets
were re-put with `wrangler secret put`, which takes effect immediately with no deploy.
**The client secret was rotated on 14 Nov 2026** and the new one is live; the test below was
repeated against it and came back `invalid_grant`, so the pair Roblox holds is the pair we hold.
A secret pasted into a chat ends up in that chat's transcript, so set the next one by running
`npx wrangler secret put ROBLOX_CLIENT_SECRET` and typing it at the prompt, where it reaches
Cloudflare without passing through anything else. Only `https://playtimestats.com/auth/callback` needs registering now: the worker 301s
every `www` request to the bare name before anything else runs, so `/auth/login` is never reached
on `www` and a second redirect URL would never be used.

**`www` only redirects for addresses the worker actually answers, and the notes used to claim
otherwise.** Measured 15 Nov 2026: `www/auth/login`, `www/api/me`, `www/admin` and
`www/reminder.ics` all 301 to the bare name as intended, but `www/`, `www/privacy`,
`www/game/doors` and `www/sitemap.xml` answer **200** - a complete live duplicate of the static
site on a second hostname. The reason is `wrangler.jsonc`: `assets` has no `run_worker_first`, so
Cloudflare serves any request matching a file in `docs/` straight from the asset layer and the
worker's redirect never runs. What keeps Google straight is that **every canonical tag names the
bare domain**, including the ones www itself serves, so do not remove those. If the duplicate is
ever to be closed properly, a Cloudflare **Redirect Rule** (dashboard, runs ahead of assets) is
the way; `run_worker_first: true` would also do it but puts every static request through the
worker. The sign-in half is unaffected either way, since `/auth/login` is a worker route.

**The session cookie names the bare domain**, so one sign-in covers the site and its `www`
alias. It used to be host-only, which is why signing in on one host and opening a link on the
other read as being signed out. If sign-in ever starts "forgetting" people again, check what
hostnames answer before suspecting the cookie.

**Signing out clears both forms of the cookie, and must keep doing so.** A cookie set with a
`Domain` and one set without it are two different cookies to a browser, so the first real
sign-out deleted the domain one, left the host-only one from before the change in place, and
sent the person back to the homepage still signed in with no way out but clearing their browser
data. `clearSession()` returns both lines and `clearedHeaders()` appends them, because a
`Response` takes only one value per header name in a plain object. Signing in drops the
host-only form too, so a stale cookie cannot sit in front of a new session.

The history below is kept because it explains why things are shaped this way.

**Roblox will not accept a `workers.dev` address as a redirect URL.** The Creator Hub refuses to
save it ("the link is invalid"), and an authorize attempt against an app without it saved ends on
Roblox's own red "Authorization Error - Redirect URI is invalid for this application" page.
`workers.dev` is a shared domain anyone can take a subdomain on, which is the usual reason an
OAuth provider blocks one. **So step 1 cannot be finished until `DOMAIN` is bought**, and buying
it is now a blocker for sign-in rather than only for the sitemap. Do not spend time re-testing
the `workers.dev` address: it has been tried on two different Roblox accounts.

Everything on our side is done and verified: `ROBLOX_CLIENT_ID`, `ROBLOX_CLIENT_SECRET`,
`ADMIN_CODE` and `SESSION_SECRET` are all set in Cloudflare, `users` and `favourites` exist in
D1, and the client id and secret are known-good - a token request with a deliberately invalid
code comes back `invalid_grant` (the code), not `invalid_client` (the credentials). That test is
worth repeating whenever sign-in misbehaves, because it separates our half from Roblox's half in
one call.

**While it is blocked, the button should not be on the live site.** `configured()` is true as
long as the three secrets exist, so the button renders and leads straight to Roblox's red error
page. Deleting `ROBLOX_CLIENT_ID` (`npx wrangler secret delete ROBLOX_CLIENT_ID`) is the switch:
`/api/me` then answers `available:false` and no button is drawn. Put it back once the domain is
registered as a redirect URL.

**The OAuth app belongs to the Roblox account `gp_isweird`.** It was moved there in Nov 2026
from an earlier account; the old app should be deleted. Moving it again means redoing steps 1
and 2 only - nothing in the repo names an account, and D1 keys people by their own Roblox user
id (`info.sub`), which is global rather than per-app, so saved games survive an app change.

1. Create the OAuth app at `create.roblox.com/dashboard/credentials?activeTab=OAuthTab`. App
   Category **Account Linking Tools** (the category decides which scopes are offered), scopes
   `openid` + `profile`, redirect URL `<site>/auth/callback` - register every address the site
   answers on, including the `workers.dev` one. Max 10 URLs, 256 characters each.
2. `npx wrangler secret put ROBLOX_CLIENT_ID` and `npx wrangler secret put ROBLOX_CLIENT_SECRET`.
   Secrets apply to the running Worker immediately; **no deploy is needed** for a credential swap.
3. `npx wrangler d1 execute playtime-admin --remote --file worker/schema_auth.sql` (creates
   `users` and `favourites`).
4. `npx wrangler deploy`.
5. Submit the Roblox app for review. Until it passes, Roblox caps the app at 10 signed-in users,
   so sign-in works for testing but not for the public. Needs a demo video under a minute that
   starts signed out and shows the whole flow, plus the privacy and terms URLs (`/privacy` and
   `/terms`, which the site already serves).

**On a phone, signing in can open the Roblox app instead of the login page - and
that is Roblox's doing, not ours.** Diagnosed 17 Nov 2026 after it was reported, and
measured rather than guessed:

- `/auth/login` sends people to `apis.roblox.com/oauth/v1/authorize`, which is
  **identical on mobile and desktop** (checked against the live site with both user
  agents) and which the Roblox app does **not** claim - there is no
  `apple-app-site-association` or `assetlinks.json` on that host at all.
- If the person is **not already signed in to roblox.com in that browser**, Roblox
  then 302s to `www.roblox.com/login?returnUrl=...`, and that host **is** claimed:
  `www.roblox.com/.well-known/assetlinks.json` declares
  `delegate_permission/common.handle_all_urls` for `com.roblox.client`, so the Android
  app claims **every URL on the domain**, login included. Android hands the page over,
  the app has nothing to do with it, and the person lands on the app's home screen or
  a game. On iOS the app claims only `/games/*`, `/share/*`, `/join/*`, `/catalog/*`,
  `/bundles/*` and `/communities/*` - **not** `/login` - but Roblox's login page
  carries `<meta name="apple-itunes-app">`, so Safari offers the "Open in the app"
  banner.
- **There is nothing to change on our side.** The `prompt` parameter Roblox documents
  (`none`, `login`, `consent`, `select_account`) does not avoid the login page for
  somebody who is signed out, and we cannot alter Roblox's app or their assetlinks.
- **Already signed in to roblox.com in that browser and it never happens**, because
  the login hop never occurs - authorize goes straight to consent on `apis.roblox.com`.
  That is why it works on a computer and why the first report of it turned out to be
  **an incognito tab**.
- **It is still the normal case for a first-time visitor on a phone**, who has no
  more signed in to roblox.com in that browser than an incognito tab has. So
  `PHONETIP` says so next to every sign-in button: *"If the Roblox app opens instead
  of the sign-in page, open roblox.com in your browser and sign in there first, then
  come back and tap this again."* It appears under the button in the side panel, in
  Plan my session and on `/notifications`.
  - **Shown below 900px only**, by CSS rather than by sniffing the user agent. It is
    really about having the Roblox app installed, and a small screen is the best
    proxy; 900 rather than the 620px mobile stylesheet because an iPad held upright
    is 768px and has the app too. The base `display:none` and the media query are
    written **next to each other**, because both are one class and a media query adds
    no specificity - source order is all that decides it.
  - It is wording, not a fix. Nothing in our code can stop Roblox's app claiming
    Roblox's own URLs; this turns a dead end into a short detour.
  - The 110-character rule on the Plan my session control does **not** cover it. The
    test measures that control with `.phonetip` removed, because the rule is about
    the control staying bare and this is a separate, deliberate warning.

**"Redirect URI is invalid" in the INSTALLED app, while the website signs in fine, means
the app is on the wrong address.** Diagnosed 18 Nov 2026 after it was reported on the PC
app. `redirectUri()` in `worker/auth.js` builds the return address out of the address the
request arrived on, and the manifest's `start_url` and `scope` are relative - so an
installed app is glued to whatever host it was installed from, for every page inside it,
for ever. This one had been installed from the `workers.dev` address, which still answers;
sign-in there asks Roblox to return to `<something>.workers.dev/auth/callback`, which is
not registered and which Roblox will not let anybody register. Hence Roblox's red page in
the app and a working sign-in in an ordinary tab, at the same moment, on the same machine.
- **The fix is to install it again from the real domain**, not a code change. Redirecting
  the wrong host to the right one does not rescue an app already installed on it: the app
  is scoped to that origin, so the redirect pops out into a browser tab, and the cookie is
  then set on a domain the app cannot read. Nothing but reinstalling moves an app's origin.
- **`/auth/login` on any host but `playtimestats.com` now 302s there** (`worker/index.js`,
  18 Nov 2026), carrying `?back=` with it, so a sign-in can never again start on an address
  Roblox will refuse. Only `/auth/login`, so the test copy stays browsable, which is what it
  is for; `localhost` is left alone so `wrangler dev` can still be signed in to. Nothing was
  lost by it, since sign-in has never worked on the test copy and cannot be made to. It turns
  the red page into a working sign-in on the real site; it does not move an installed app.
- **It is not only `workers.dev`.** `wrangler.jsonc` sets `preview_urls: true` and
  `.github/workflows/staging.yml` deploys a second copy, so there are several live hosts
  to install the wrong one from. Only `www` is redirected to the bare name
  (`worker/index.js`), and that is a 301 of the request, not of an installed app.
- **Uninstalling with "also delete data" ticked takes the sign-in cookie with it**, which
  reads as the site forgetting you on restart. The cookie itself is a 60-day `Max-Age`
  one (`worker/auth.js`), so a sign-in that does not survive a restart is the browser
  clearing it - Chrome's "Clear cookies and site data when you close all windows", or an
  uninstall - rather than anything here.

**You cannot check the app's own settings from outside.** Roblox's `/oauth/v1/authorize` redirects
to its login page whatever you send it - a wrong `redirect_uri`, or a client id that does not exist
at all, both come back as the same 302. So a bad redirect URL only shows up as a failure *after*
someone signs in. Test by actually signing in; do not read a 302 as proof the app is configured.

## Reading age
**Much of this audience is nine years old, and the words are written for them.**
Measured on 17 Nov 2026 rather than guessed at: every page type's visible text was
pulled out and scored, and the site already sat at about a US grade 4-6, so this is a
standing rule rather than a rewrite waiting to happen.

- **Short sentences do more than short words.** The pass that moved the numbers
  mostly split sentences in two - the homepage's "Where the numbers come from" was
  three sentences, one of them 35 words long with a colon in the middle, and is now
  five. Afterwards no page but the game pages had a sentence over 24 words, and that
  one is the hours table's own header row, not prose.
- **Where it still reads high, check whose words they are.** `/events` scores a grade
  9, and every bit of that is Roblox creators' own event titles. Nothing on that page
  that we wrote is hard.
- Things that were changed and are worth not changing back: "it is deliberate, not an
  oversight" (now "we leave them out on purpose"), "Estimates and observations" (now
  "Our guesses, and what we really saw"), "we try never to muddle them", "The fine
  print" as a heading, and a 45-word sentence on `/notifications` listing the four
  things we store, which is now four list items.
- **The estimate/observation distinction survives the plain words.** "Typical" and
  "average" are still our guess, "highest seen" is still one real reading, and the
  two are still never blurred - see "Estimate vs observation" under Search engines.
  Simpler words, same promise.
- The scorer is in the scratchpad, not the repo: it reads a built folder, prints a
  Flesch-Kincaid grade and words-per-sentence per page type, and lists every sentence
  over 24 words so they can be read rather than trusted to a number.

## Look and layout
- **Logo**: `logo_svg()` draws a timer ring with a play button inside, inline in the page so it stays sharp and costs no request. `FAVICON` is the same drawing written out as `favicon.svg`.
- **Light/dark**: the dark palette is written once as `DARK` and dropped into the stylesheet twice, for `@media(prefers-color-scheme:dark)` on `:root:not([data-theme=light])` and for `:root[data-theme=dark]`. The site follows the device until the visitor presses the button, after which their choice is kept in `pt_theme` and wins. **Any new dark-mode rule must use a variable, not its own `prefers-color-scheme` block**, or the manual toggle will not reach it.
- **Grid or list**: the toggle only sets `data-view` on `<html>` (kept in `pt_view`), and the stylesheet does the rest, so one button anywhere changes every list of games on the site. Grid is the default. `view_toggle()` / `row_head()` place it.
- `BOOT` runs in the head before anything is drawn, so neither the theme nor the view flashes the wrong way round.
- **Game switcher** (top left, `CHROME_JS`): the last 8 games viewed, kept in `pt_recent`. Each game page sets `window.PT_GAME` near the end of its body, which must stay *before* the `CHROME_JS` tag at the end of the page. `CHROME_JS` is on every page, so it may only use helpers from `FAVJS` (which is in the head) such as `ptEsc` - not `esc` from `SHARED_JS`, which only chart pages load.
- **Ads**: `ad_rail()` gives a left rail, a right rail and a sticky bottom strip, sized but empty, with ids `ad-left`, `ad-right`, `ad-bottom`. The AdSense loader belongs in `ADS` and goes in the page head **once**; the rails must never repeat it. `SHOW_RAILS` means the slots show dashed outlines in previews and are left out of the live site until `ADS` is filled in, so visitors never see empty grey boxes. Rails need 1480px of screen. **The bottom strip runs at every width**, 66px on a phone or a tablet and 98px from 900px up, and it is the only slot a phone ever sees. It used to start at 900px too, on the reasoning that phones should stay clean - which meant every phone and an iPad held upright carried no advertising at all, and since this audience is overwhelmingly on phones that was most of the site's income switched off. It would have shown up only after AdSense was live and the earnings made no sense. 66px is about a 50px banner once the padding and the rule are taken off: a bar on an 844px-tall phone is spending screen the visitor came for, so it takes as little as an ad can take and still be one. `z-index:8` keeps it under the header (9), the scrim (25) and the drawer and sheet (30), so an open menu covers it; `position:sticky` rather than `fixed` means it still takes its space at the end of the page, so the footer is never left hidden underneath it. Measured on emulated devices at 390, 768, 1024, 1280 and 1920 across four page types: present at all twenty, rails still only from 1480, nothing scrolls sideways. **The middle track is capped at the width the page actually uses** - 820px, or 1400px when `page()` adds `wideads` alongside `ads` - rather than `1fr`. A `1fr` middle track swallows every spare pixel, so on a 2560px monitor the reading column stayed 820px in the centre while the ads sat nearly 700px out at the edges, reading as two stray boxes instead of a page; capping it lets `justify-content:center` centre all three together. It must stay `minmax(0,Npx)` and never a flat width, or a screen between 1480 and 1776px scrolls sideways on the wide pages.
- **The bar is ONE width, 1200px, on every page and at every screen size** (19 Nov
  2026, owner's call: "why does the header get smooshed when i go to a new tab").
  It used to be written to match the column underneath it - `.hdr.narrow` at 820px
  on a reading page, `.hdr.wideads` following the middle track when the ad rails
  squeezed it - so that the logo sat exactly above the first word. That is right on
  any one page and wrong across five of them: clicking Events, Compare or Plan in
  the bar shrank the bar itself by 244px, slid the logo 122px sideways and squeezed
  the eight links into a scrolling strip, which reads as the page breaking rather
  than as a cap being respected. **Both classes are gone** and `page()` writes a
  plain `<header class="hdr">`. The price is paid on a reading page, where the logo
  now sits left of the words, and on a wide page between 1380 and 1576px, where the
  rails pull the column 52px off the logo - which is what most sites look like and
  what nobody notices. Measured after at 1200/1440/1920/2560 across nine page types:
  the band is 1200px and the logo is in the same place on every one.
  - **The rails were the last thing moving it, and they moved it furthest at 1440px**
    - the commonest laptop width there is - because `calc(100% - 376px)` bottoms out
    around there. That is what pushed Compare and Plan off the end of the bar.
  - **Eight links fit with 12px to spare, and that was measured.** At `.93rem` and a
    14px gap they came to 606px and the bar could spare 595 with somebody signed in,
    so Plan sat over the edge and the strip scrolled. `.9rem` and 11px is 583.
    `navfit.js` walks seven widths signed in and signed out; if a ninth link is ever
    added, run it before believing it fits.
- Content is 1400px wide (`.w.wide`), 820px for reading pages. The logo used to sit exactly above the first word under it; both use the same 16px side padding, which is what made that land on the pixel. **The 820px cap has to out-rank `.shell>*{max-width:100%}`**, which is also one class and comes later in the stylesheet: a plain `.w` lost to it and every reading page (Privacy, Terms, About, Events, Compare, Plan) ran the full width of the window - measured 1920px across on a 1920px screen, flush left, with the logo 280px further in. `.w.wide` was never affected, because two classes beat one, so only the reading pages looked wrong. They are re-stated as `.shell>.w` and `.shell>.w.wide` for the weight. **`.w` also carries `width:100%`, and that is not spare either**: it is a grid item with auto side margins, and an item with auto margins is sized to its contents rather than stretched to its track, so a wide page whose contents happened to be narrow drew a narrow column and centred *that* - `/popular.html` came out 1024px, `/trending.html` 1001px, `/growing.html` 1060px, `/404.html` 1001px, each starting at a different distance from the logo. Measured after: all 16 page types start and end exactly level with the header at 320, 390, 430, 620, 768, 1024, 1280, 1500, 1600, 1920 and 2560px, with and without the ad rails.
- **Phones**: the mobile stylesheet is `@media(max-width:620px)`. The site used to scroll sideways on a phone, and these rules are what stop it. **Measure before changing any of them** (see the note below): every one was found by measuring, and several things that looked like the cause were not.
  - **A sideways-scrolling strip must be `display:block` + `white-space:nowrap`, never a `flex-wrap:nowrap` flex row.** A nowrap flex container reports the total width of its items as its max-content width and its parent grows to fit, even though the strip has `overflow-x:auto` and scrolls. The category pills (1347px of them) dragged the whole homepage to 1094px inside a 390px phone. `.tabs` and `.pills` are both written this way now; `.wrap` is fine because it is a plain block.
  - **Any design width is written `max-width:min(Npx,100%)`**, never a bare `max-width:Npx`. `.w.wide`'s `max-width:1400px` beat `.shell>*{max-width:100%}` on specificity, so the clamp has to live on the width itself. Same for `.hdr .in`.
  - **`.shell>*` carries `min-width:0` AND `max-width:100%`.** `min-width:0` alone is not enough: `.shell` centres its track with `justify-content`, and an item in a centred track may grow past the track to fit its contents.
  - **Every grid floor is `minmax(min(Npx,100%),1fr)`**, never `minmax(Npx,1fr)`, which is a hard minimum (`.passes` at 290px was wider than a card on a small phone).
  - **`body` carries `overflow-wrap:break-word`**, with `overflow-wrap:anywhere` on anything holding Roblox text (`.desc`, `.gdesc-in`, `.evt`, `.pass`, `.tname`). Creators paste group links into descriptions and a 61-character URL is about 430px. `anywhere` rather than `break-word` there because only `anywhere` shrinks the min-content width, which is what lets a grid or flex item give way.
  - `.grid` clips sideways (`overflow-x:clip`, `overflow-y:visible`) because `.tile::before` is meant to spill 25% past each tile. Clip, not hidden, and x only, so the hover lift still shows.
  - `body{overflow-x:clip}` is the net under all of it. **Clip, not hidden**: `hidden` would make the body a scrolling box and the sticky header would stop sticking.
  - On a phone `.ghead` puts the picture on its own line (`.ghead>div{flex:1 1 100%}`) so the words get the full width, and `h1` drops to 1.5rem.
- **One header, at every width**: logo, the PlayTime wordmark, the game picker, then the notifications bell, the search magnifier and the three-line button on the right. The panel that button opens holds the account, search and light/dark (`.dtop`, above the section links). **Search is the one thing that differs**: a wide screen has room for it, so from 900px up a magnifier sits in the bar (`.iconb.deskonly`, hidden by default and shown only inside the `@media(min-width:900px)` block) and the panel hides its own search row so the same control is not offered twice. **The row of section pills under the header is gone**: it was a second navigation that only ever showed on a wide screen, and the panel holds the same links plus two more. The footer still lists them as plain visible links, so none of the site's navigation is hidden from a search engine. Every control is bound by attribute, not id (`[data-search]`, `[data-themebtn]`), and the scripts bind **every** match - that is why the second magnifier needed no JavaScript at all, and why any further copy will not either. `ptPaint()` fills every `.acct` for the same reason, and `paintTheme()` keeps each labelled so a control cannot offer "Dark mode" on an already dark page. The sun/moon swap is keyed off `.themeic`. The bar is about 65px tall, 57px on a phone.
- **Installing the site is a page, `/install`** (`install_body()`), not a row in a menu. Every game page links to it under the notification panel (`[data-installlink]`, hidden by `CHROME_JS` once `ptInstalled()` is true, since there is then nothing left to explain), and the footer links to it so it is not hidden from a search engine.
  - **It is also a row in the panel behind the three-line button** ("Get the app",
    added 17 Nov 2026). It was reachable only from the footer and from the
    notification panels for a week, and the owner reported there was **no way to get
    there without typing the address** - which was very nearly true, because the
    footer is at the bottom of a long page and the panel is how people actually move
    around this site. It is written straight into the panel's `<nav>` rather than
    into `TABS`, because `TABS` is also the footer's list and the section pills, and
    this is not a section of the site. It is a page because the steps differ on every platform and **Apple's cannot be automated at all** - no API lets a website install itself on an iPhone - so the only thing that works there is clear instructions, and instructions do not belong behind a toggle in a menu.
  - `/install` also carries `[data-install]`, a **real** install button that `CHROME_JS` reveals only where the browser has actually offered. **The offer arrives before `CHROME_JS` runs**, which is why it is caught in `FAVJS` (in the head) and kept on `PT.prompt`, with `preventDefault()` so the browser does not also throw its own bar across the page; `CHROME_JS` sets `PT.onprompt` so it can repaint if the offer lands later. An offer may be used **once**, so pressing the button takes it (`PT.prompt = null`) rather than copying it.
  - **The iPhone steps have the owner's own screenshots on them** (16 Nov 2026), one per step, each with a red arrow drawn on it: the three lines in Safari's address bar, Share, Add to Home Screen, then Add. The steps are written to match those pictures exactly, so **if the pictures are ever replaced the wording has to move with them** - Safari's own route to Add to Home Screen has changed before.
  - **The three device sections are drawers** (`.howto`, `data-dev`), and the one
    matching the device opens itself - `ptIOS()`, then Android in the user agent,
    else a computer. The page ran 4,419px on a phone with everything laid out one
    after another, so somebody on Android scrolled past four Apple screenshots to
    reach four lines that applied to them; collapsed it is 1,438px. They are **all
    shut in the markup** and opened by script, so somebody without JavaScript gets
    three closed drawers with readable headings rather than one opened at random,
    and the `<h2>` stays inside the `<summary>` the way `.gdesc` does it, so the
    page keeps its headings for search engines.
  - **The one-tap install button is hidden below 900px** (17 Nov 2026), at the
    owner's request: on a phone it is done by hand. Worth knowing before putting it
    back - it only ever appeared where the browser had **actually offered**, so it
    was never shown on an iPhone at all, and what this really removes is the
    shortcut on Android and small tablets. One media query, `.doc [data-install]`,
    two parts because `.remind` is a single class written further down.
  - **It says "add", not "install", wherever the Apple steps are meant.** Apple's own
    wording is Add to Home Screen, and the screenshots say Add, so calling it
    installing sent people looking for something that is not there.
  - **"I have already added it" exists because we cannot tell.** `ptInstalled()`
    reads `display-mode: standalone`, which is only true **inside** the added app -
    in a Safari tab it answers "not added" whether they have added it or not. So the
    line does not unlock anything, because Apple still refuses push from a tab: it
    says to open the site from the home screen and turn the bell on there. It is a
    plain `<details>` (`.already`), which is why it needs no JavaScript and survives
    the notifications page redrawing itself. It appears on `/notifications`, in the
    Plan my session card and inside the install popup.
  - **The computer section has its own four screenshots** (17 Nov 2026). Three are
    about *notifications* rather than adding the site, because on a computer nothing
    has to be added - web push works in an ordinary tab: the browser's Allow box, the
    settings icon to the left of the address (the way back in after pressing Block),
    and the Notifications switch behind it. The fourth, `pc4`, is the **install** icon
    at the other end of the address bar, on the Adding it steps.
  - **The Adding it steps name the buttons Chrome actually shows**: open it in your
    browser, click the install icon, then **Next** and **Install**. They used to say
    "look for the small add or install icon... or open the browser menu", then
    "Confirm", which described the shape of the thing rather than what it says.
    Chrome's wording has changed before and will again, so **if these go stale, the
    screenshot has to move with them** - the same rule the Apple steps follow.
  - **It says the icon is Chrome and Edge only.** Firefox on a computer cannot add a
    website at all, so somebody in Firefox would otherwise hunt for an icon that is
    not there. Notifications still work in it, and the line says so, because that is
    the thing they actually came for.
  - **A browser screenshot needs a different width cap from a phone one.** `.shots
    img` caps at 270px, which is right for a tall phone picture and unreadable for a
    browser window; `.shots.wide img` caps at 520px, the pictures' own width, so they
    are never upscaled. Two classes, so it beats the rule above whatever the order -
    the same trap as everywhere else in this stylesheet.
  - **Each one is cropped to the part being talked about before the arrow is drawn.**
    The first two were whole 1834px browser windows, and at 520px the Allow button
    was illegible; cropped to 550px and 560px of real screen the words can be read.
    The arrow is sized as a fraction of the picture (5% head, 1.6% shaft) rather than
    in fixed pixels, because the site-settings panel is only 330px wide and the phone
    shots' 54px arrowhead would have been a third of it.
  - **"If they still do not appear" is about Windows, not us.** Windows holds a
    notification switch on top of the browser's, and it is usually the one in the
    way: Settings, System, Notifications; Do not disturb off; then the browser itself
    in the list of apps underneath. There is nothing in our code that can read or set
    any of that, so it is written as instructions and always will be.
  - They live in **`brand/install/step1..4.webp`** (the Apple steps) and
    **`pc1..3.webp`** (the computer ones), and the build copies every `.webp` in that
    folder byte for byte into `img/install/`, so a new picture needs no change to
    `build_site.py`. The arrows were drawn once with Pillow in a scratch script, not
    at build time: `build_site.py` needs no image library and the build server
    installs nothing, which is the same rule `roblox_api.py` follows. They are all
    520px wide, 4-45KB each. **`prune()` does not cover them** - it only deletes
    `.html` and `.ics` - so a renamed picture would linger and has to be removed by
    hand.
  - `ptIOS()` and `ptInstalled()` live in `FAVJS` because both this and the notification panel on game pages ask the same two questions, and two copies would drift. iPadOS reports itself as a Mac, so a Mac with a touch screen is an iPad.
  - Its own IIFE **after** `CHROME_JS`'s main one, because that gives up early on any page without the game switcher and this is on every page.
  - **Testing this needs the offer suppressed, not simulated.** Chrome fires `beforeinstallprompt` for this site for real - a manifest with the right icons is now enough, no service-worker fetch handler needed - and **claiming to be Safari in the user-agent does not stop it**, because the UA string is not what Chrome's installability check reads. So `installui.js` throws the real offer away to test the Apple path; without that it is only ever testing Chrome, which is exactly how three tests "failed" misleadingly the first time.
- **The name and the bell are in the bar on a computer only, and nowhere on a phone** (16 Nov 2026). A phone's bar has room for the logo, the game picker and two buttons; a name in there squeezed the picker to a stub. Nothing becomes unreachable: below 900px the panel carries both the account block and a **Notifications** row, and from 900px up the panel drops that row because the bell is in the bar - the same trick the search magnifier already used. **The 900px rules are written `.hdr .nots`, not `.nots`**, because the base `display:none` is a one-class rule further down the stylesheet and a media query adds no specificity; a single class lost to it and the bar stayed empty at every width. That is the third time this trap has bitten here.
- **Signed out on a computer, the bar carries "Sign in"** in the same slot the name
  occupies when signed in (17 Nov 2026) - a plain `<a>` to `ptLogin()`, not a button.
  The delegated handler checks `tagName !== 'BUTTON'` and leaves it alone, because
  intercepting it would swallow the click and open an empty `#amenu`. Below 900px
  there is no room in the bar, so the panel keeps the sign-in link.
- **On a phone the account is a row that opens** (`.apop`, a plain `<details>`):
  the name, with "Signed in with Roblox" and Sign out folded inside, which is the
  same shape as the menu the name drops on a computer. A `<details>` rather than a
  bound handler for the reason `.already` is one - `ptPaint()` replaces this markup
  every time `/api/me` answers, and a handler put on the row would be thrown away
  with it. **A closed `<details>` keeps its contents out of `innerText`**, which is
  what three tests had to learn.
- **The name in the bar opens its own menu, and the panel then drops the account**
  (17 Nov 2026, owner's call, replacing the rule that the name should open the
  panel). The old rule was right while the panel held the name and Sign out: a
  second menu with the same two things is one more place for them to disagree. The
  fix was not to keep them in one place but to **move them**, so from 900px up
  `.dtop .acct.signedin{display:none}` and the bar's pill carries a small `#amenu`
  holding "Signed in with Roblox" and Sign out. Below 900px there is no pill, so the
  panel keeps the account and `#amenu` is never drawn. One of each at every width.
  - **The sections hold their width and the NAME gives way** (19 Nov 2026). A long
    Roblox display name made the pill 182px instead of 94px and pushed Compare and
    Plan off the end of the bar - at **every** width, 1920px included, because the
    band is capped at 1200px however wide the screen is. `.hnav` is `flex:0 0 auto`
    now, and `min-width:0` runs down through `.acctbar` and `.acctb` to `.albl`,
    which already had the ellipsis. The bar is navigation first, and the whole name
    is one press away on the button the menu hangs from. `longname.js` measures it
    at four widths with a 30-character name.
  - **The name is NOT repeated inside the menu.** It is written across the button
    the menu hangs from, and that was the whole complaint about the old
    arrangement.
  - **`.dtop .acct{display:none}` depends on the bar offering sign-in.** For a few
    hours on 17 Nov 2026 the pill was drawn only for somebody already signed in, and
    hiding this block left a signed-out visitor on a computer with **no way to sign
    in anywhere on the site** - the page looked perfectly normal, there was simply
    nothing there. It was briefly `.acct.signedin`; the signed-out pill is what made
    the plain rule safe again. **If that pill is ever taken out of the bar, this has
    to go back to hiding only the signed-in half.** Caught by `acct.js`, which walks
    three `/api/me` states across ten widths; nothing a screenshot would have
    shown.
  - `#amenu` is written **outside `<header>`** with `.drawer`, `.sheet` and `.ipop`,
    for the same reason they are: `.hdr` has `backdrop-filter`, which makes the
    header the containing block for anything `position:fixed` inside it.
  - It is bound by **delegation from `document`**, because `ptPaint()` replaces the
    pill every time `/api/me` answers and a handler on the button itself would be
    thrown away with the old markup.
- **The account is in the panel, and the bell is in the bar** (16 Nov 2026). The account spent two weeks in the bar on the grounds that a face is easier to find than a menu item; the owner wanted the bar down to icons so the notifications bell could live there, and the name and Sign out were already in a menu hanging off the bar, so this is the same two things in a place with room for them. **Both are written EMPTY** - `<div class="acct">` in the panel and `<div class="nots">` in the bar - and `ptPaint()` in `FAVJS` fills them once `/api/me` has answered, because a built page is the same file for everyone and only the worker knows who is signed in. `:empty{display:none}` on each is what stops an unfilled one holding a gap open, which is also the whole behaviour when the Roblox keys are missing: nothing is written and the header reads as though sign-in never existed.
- **The bell is drawn only for somebody signed in**, because notifications are offered to signed-in people only and for anybody else it would lead to a page explaining why it is empty. **It is a plain link to `/notifications`, not a dropdown** (16 Nov 2026): three switches per game plus a device to turn on outgrew the corner of a phone screen, and a menu that size quietly becomes its own little application. It is an `<a class="iconb">`, which is why `.iconb` carries `text-decoration:none`.
- **Every `.acctb` rule is written `.acct .acctb`, and that is not tidiness.** `.iconb` sets `display:grid` and `width:42px` and is written *further down* the same stylesheet, and `.gmenu` sets `left:0` for the game picker at the other end of the bar. A media query adds no specificity, so each one-class rule simply lost to the later one: the pill came out as a 42px square with the glyph stacked **on top of** the word, and the menu opened rightwards off the screen (measured 252px wide ending at 473px inside a 390px phone). Two classes settle all three whatever the order. This is the same trap as `.w` vs `.shell>*` above - **in this stylesheet, assume a later single-class rule will beat yours.**
- **The account button is bound by delegation from `document`, never directly.** `ptPaint()` replaces that markup every time it runs, so a handler put on the button itself is thrown away with the old markup and the menu quietly stops opening. `e.target.closest` is guarded (`e.target.closest&&...`) because on iOS a click that has bubbled to the document can arrive at a text node, which has no `closest` - the same thing that once stopped the reminder links working.
- **Both cards drop straight down from the bar with rounded edges** (17 Nov 2026,
  owner's call, after demand.gg). `.drawer` was a full-height drawer sliding in from
  the right edge; it is a 262px rounded card now, and `#amenu` is the same shape at
  218px. `max-height` plus `overflow-y:auto` is what keeps a long list scrolling
  inside the card rather than running off the bottom of the window.
  - **Script places them, CSS does not, and that is not tidiness.** Pinned 16px from
    the window edge the panel sat **260px to the right of the three-line button** on
    a 1920px screen, because the bar's own band is capped and centred - and the cap
    is not one number (1400px wide, 820px reading, narrower again with the ad rails
    up), so no CSS value can follow it. `drop(el, btn, edge)` reads the button and
    places the card: **sideways from the button, down from the bar**. Measured after
    at 320/390/620/768/1024/1500/1920/2560 on both a wide page and a reading page -
    the right edge lines up with the button to the pixel at every one.
  - **Down from the BAR, not from the button**: the button is inset inside the bar by
    its padding, so hanging the card off the button put its top 5px above the bar's
    own bottom border, and the card is above the bar in the stacking order, so it
    drew over it.
  - **The scrim no longer dims.** A full-page dim behind a small rounded card reads
    as a modal, which it is not; `.scrim` is now an invisible click-catcher and
    `.sheet`, which really does take the screen over, carries its own dimming.
- **`.drawer` and `.sheet` are written after `</header>`, not inside it, and must stay there.** Both are `position:fixed`, and `.hdr` has `backdrop-filter`, which makes the header the containing block for any fixed descendant. Inside the header the side menu was 88px tall instead of the height of the screen, and the search panel was pinned to the header's own box, so it read as sitting under the game picker. **Anything `position:fixed` that should cover the page belongs outside any element with `backdrop-filter`, `filter` or `transform`.**
- **Checking a layout on a phone**: do not reason about it, and do not trust a headless screenshot — Chrome on Windows will not open a window under about 500px, so a 390px screenshot is really a 500px page cropped, which looks broken when it is not. Use real device emulation (`puppeteer-core` driving the installed Chrome, `page.emulate` with a 390x844 viewport). The test that matters is whether the page can actually be dragged sideways: `window.scrollTo(9999,0)` and read back `window.scrollX`. To find a culprit, walk down from `body` into the widest child repeatedly, then hide each child of the offender in turn and watch the width.
- **The glow behind a tile** is that game's own colour. `roblox_api.fetch_icon_hues` reads each game's icon while the site is built and works out the one hue it reads as; `tile()` writes that onto the tile as `--glow`, a bare number, and the stylesheet does the rest on `:hover` and `:focus-visible`. **Only the hue is stored.** Saturation and lightness are fixed in the CSS, because left to themselves some icons would glow in a muddy brown and others in a glare. A game whose icon has no real colour in it (3008, for instance, which is grey on purpose) gets no `--glow` at all and falls back to `--glowh`, the accent's own hue. `--glowa` is the strength, weaker on a light page (.32) than a dark one (.5), where a bright colour spreads further and would wash the words out. The glow is half as wide again as the tile and `z-index:-1` inside an `isolation:isolate` stack: the icon is not see-through, so a glow the size of the tile would be entirely hidden behind it. **The two rows of controls above the games get a rim, not a glow.** The chips ("What are you looking for?") and the category pills light up on `:hover`/`:focus-visible` with a `box-shadow` that follows the border and stops there - `--rim`, one line, shared by both - rather than the tile's blob behind the whole control, which read as the chip changing colour. **They are all the accent, deliberately.** A tile borrows its own icon's hue because it has one; a category and a question do not, and a hue per category was tried and read as decoration pretending to mean something. They still use `--glowh` and `--glowa`, so a palette change moves the tiles and these together. **The chosen chip does not glow on its own** - it is marked by its inset ring - because a light that is always on stops reading as a response; it does light up while it is the one being pointed at, which needs its own rule since `[aria-pressed=true]` and `:hover` have equal specificity. The mobile block drops `.chip`'s shadow, so it re-states the hover as rim-only: a tap leaves `:hover` stuck on in most phone browsers and would otherwise hand the shadow back.
- **Bento grid (`.bento`)**: a page's sections laid out as a grid instead of one tall column, so several are on screen at once. `.bento` is a 12-column grid and a card says how wide it is with `sp4`..`sp8`; with no class it is full width. **Below 900px every card goes back to full width**, and the spans only exist inside that media query. **The grid never reorders anything** (no `grid-auto-flow:dense`), so the HTML order stays the reading order for screen readers and `check_seo.py`. Cards use `align-items:start` and keep their own height rather than stretching: what goes in them varies far too much, and stretching turns a short card into a mostly empty box. `span(block, n)` adds the class to a section that builds its own card (`history_html`, `faq_html`, `calendar_html`, `about_game_html`, `parents_html`), and returns "" untouched for a section that had nothing to say. Used by the game pages and `/busiest-hours.html`; **a game page is `wide=True` because of it**. **`.lstack` is the one place two cards share a column.** A grid row is rigid, so a card shorter than the one beside it just leaves the space under it empty: "The short answer" is 239px and "Plan my session" is 735px, which left a 496px hole on every game page. The short answer and "Is X dead?" are now stacked inside one `sp7` column next to it, which also freed the 45-day history chart to run full width and closed a second 767px gap further down. It is a nested flex column rather than `grid-row:span 2` because spanning splits the slack evenly between the rows, opening an arbitrary gap *between* the two cards instead of closing it. **`.lstack`'s gap must stay level with `.bento`'s** - 14px, and 18px again inside the 900px block - or the column reads as loose beside the card next to it. Measured before and after: the page's empty space went from about 1,615px to 586px. `similar_html` is deliberately left outside the grid, since it is already a full-width row of tiles and is not a card.
- **The game's description is a drawer** (`.gdesc`), directly under the heading rather than a card further down: it is the first thing a visitor wonders and the longest thing to re-read, so it opens on demand. The `<h2>` lives inside the `<summary>` so the page keeps its heading for search engines and for heading-by-heading navigation. The arrow is two CSS borders, not a picture. Because it is already behind a click, the old 600-character truncation is gone and the whole description goes in. The common-questions card is last in the grid and full width, so the page ends on them.
- **The game heading is a panel** (`.ghead`): a glass card over the game's artwork with the icon lifted out of its top on a negative margin, and the first row of the bento pulled up underneath it (`margin-top:-30px`) so the page opens with layers rather than stacked boxes. `.ghead` carries `z-index:2` to stay above the cards tucking under it; if you remove that, the cards will cover it.
- **Colours** are the owner's black and neon purple palette. **Dark mode is it exactly, as supplied**: background `#0A0A0F`, cards `#171521`, accent `#A855F7`, secondary `#C084FC`, text `#F5F3FF`. Light mode is the same idea turned over (`#0A0A0F` ink on a faintly purple near-white `#F6F4FB`, accent `#7E22CE`), because the same purple cannot be readable on both a light and a dark page. **`--acc2` is decorative and `--alt` is the data colour, and they are different hues on purpose.** `--acc2` is the supplied secondary purple and only ever appears in gradients and on the edge of a soon-starting event. `--alt` is a cyan, and it draws the second game on `/compare.html`, the second set of bars in the hourly chart, and the spike dots on the 45-day line. Those have to be tellable from `--acc` at a glance, so **never give `--alt` a purple**, or those three stop working. `--btnink` is the text colour on a filled accent button (white light / `#0A0A0F` dark); **a filled button must use `var(--btnink)`, never `#fff`**, since white on `#A855F7` is only 3.96. The logo's ring and play button are drawn in `#0A0A0F` for the same reason. **The heatmap `--l1`..`--l5` means crowding, not depth: green `#A8EBCB` is quiet, amber `#EEA830` is middling, red `#E26D68` is busy.** It is deliberately independent of the site palette, because it is a traffic light, not decoration; a palette change should leave it alone. Hue alone would not carry it, since red-green colourblindness is common and much of this audience is children, so the perceived lightness also falls in even steps (L* 88, 81, 74, 67, 60) and the bands stay tellable apart in greyscale. **If you ever retune a band, re-check both its hue and its lightness.** `verdict()` borrows the same ramp as a good-to-bad scale, which only works while `--l1` is the green end. The heatmap's "right now" marker carries two rings, a dark one for the bands (always light) and a light one for an hour with no samples (transparent, so in dark mode it sits on the near-black page). Every value here was measured against the surface it sits on rather than picked by eye; all body text clears 4.5:1 in both themes. The amber `.ptag.sale` tag also sits outside the palette on purpose. **Do not write a colour's name into page text** (the 45-day chart caption used to say "Purple dots"): it goes stale on every palette change.
- **The search panel** (`#sheet`, opened from the panel's first row) searches every game. It fetches `/games.json` the first time it is opened, so a visitor who never searches never downloads it. Both it and the side panel guard for their own absence, since `CHROME_JS` runs on every page.
- **Player count history is a two-line graph** (`history_lines`): the typical count
  and the highest seen, on **one shared scale**. The shared scale is the point - the
  gap between the lines is how far a game's quiet moments sit below its peak, and two
  charts each scaled to themselves would hide exactly that. Drawn at build time, not in
  the browser, because a day is a day in any timezone. The table is still written
  underneath inside a `<details>`: every number a page claims should be readable as
  text, and nothing can read an SVG. **The key uses coloured blocks, never colour
  names** - a colour named in text goes stale on the next palette change, which the
  45-day caption did once already.
- **The homepage does not list the site's own sections** (17 Nov 2026). "What you
  can do here" was a card of eight links - the same ones the panel holds - sitting on
  the one page where the menu button is nearest to hand, and it had already gone
  stale once (it was still advertising the deleted calendar reminders). The homepage
  now runs games, then "Where the numbers come from", then the footer. **The footer
  is what keeps every section linked for a search engine**, so it is not optional
  and nothing should be taken out of it.
- **The homepage lede is one sentence.** It was four lines saying the same thing three
  ways. The two numbers that make it believable - games tracked and readings taken -
  are still there, in small type underneath, because they are the reason to trust the
  rest of the site and not what somebody arriving needs to read first.
- **Graphs, not bars.** `dayGraph(vals,R,label,hue)` in `SHARED_JS` draws an SVG line with a translucent wash under it, so a visitor sees the shape of a day rather than 24 separate columns. **Two things decide whether a day reads as a day or as a gentle curve, and both were measured.** (1) The box is **720x320**, not 720x250: at 250 it drew 865x300 on a laptop, nearly three times wider than tall, and a day's entire rise and fall came to 126 real pixels spread over 865 - a slope that looks flat however the numbers are scaled. (2) `graphRange(B)` runs the axis from the week's quietest hour to its busiest instead of from zero; across the live site one day's line used only 39% of the height on a zero axis, and about 52% on this one. Together the swing went from 115 to 169 real pixels, about 1.5x. **It is the WEEK's range, not the day's** - scale each day to itself and a quiet Tuesday looks identical to a heaving Saturday, which is the one thing this chart exists to tell apart. **An axis that does not start at zero must say so**, and `#scalenote` under the graph names both end numbers in words. `graphCursor` repeats `H` and the same mapping, so change one and the crosshair floats off the line; there is a test that reads the dot's position back against the path. The line *breaks* where an hour has no samples instead of joining across the gap, which would invent data we never collected. `graphCursor(svg,out,vals,max)` adds the crosshair: drag, click, hover, touch-drag, or arrow keys, and the readout under the graph names the hour and the player count. Touch drags call `preventDefault` so the page does not scroll out from under the finger, and the graph is `tabindex="0"` so a keyboard reaches it.
- **The week grid answers in the same box the graphs use** (19 Nov 2026). It had a
  line of text under it while the hourly graph beside it answered under the pointer,
  which is two places to look for the same kind of fact on the same card. `hmSay`
  fills both and `tipShow` is only ever called for a mouse; the line is hidden from
  900px up by `.readout.chartout` rather than deleted, because **on a touch screen a
  finger covers the square it is pointing at**. It needs a `pointermove` handler as
  well as `pointerover`: the squares are 26px apart, so moving along a day without
  one left the box behind on the first square.
  - **On a phone the tapped square is RINGED, not grown** (19 Nov 2026, owner's
    call). It used to scale to 2.2 so there was something finger-sized to tap
    again; the owner would rather the grid held still, since a square that jumps
    out from under the finger that pressed it reads as the page moving about.
    Every other square stays live either way.
  - **`.hm .c.sel` has to say `padding:0`, and that is not tidiness.** `.sel` is
    also the class on every `<select>` on the site (`.sel{padding:10px 13px}`,
    further down and one class), and a one-class rule that declares something a
    two-class rule does not simply applies - so the tapped square picked up a
    dropdown's padding and went from 11x17 to 28x22. It had been doing that for as
    long as the square was being scaled up anyway, which is what hid it.
- **The row of buttons under the game's heading is the page's navigation** (`.actions`, `jump_html`): Play, Game updates, Save, and then a jump link for each section far enough down the page to be worth one - Events and the common questions. A visitor arriving from Google lands on a long page and the row says where everything is, in one place rather than as a second strip of links. **Compare was removed from it in Nov 2026** to make room; `/compare` is still reached from the panel and the footer, but no longer arrives with this game already chosen. **A jump link is only drawn when its section exists** - `anchor()` puts the id on the card and `jump_html` is handed only the blocks that came back non-empty, so a game whose creators have announced no events cannot offer a link to an id that is not on the page. Plain anchors, no JavaScript, which is also what lets Google offer the same sections underneath our own search result. **`.bento>*` and `.lstack>.card` carry `scroll-margin-top`** (78px, 68px on a phone): the header is sticky and about 65px tall, so without it every jump lands with the heading hidden underneath the bar. Measured on a real emulated phone and at 1024/1440: every jump clears the header by 26px or more and nothing scrolls sideways.
- **`/updates/<game>.html`** holds everything about one game's updates: the recent-changes list, the update rhythm and the spike days. Game pages link to it with a "Game updates" button near the top rather than carrying the whole section themselves. `prune()` cleans this folder too, and `c["has_updates"]` is what puts the page in the sitemap.
- **Game passes** (`pass_card`, `parents_html`, `roblox_api.fetch_passes` with `passView=Full`): picture, name, what the creators say it contains, and the price in Robux and dollars. The only labels are ones the data supports: `Cheapest`, `Newest` and `On sale now` (Roblox's own `priceDiscountDetails`). **Never add a "recommended" or "best" badge**: the game-pass API returns no sales, ratings or popularity of any kind, so a ranking would be invented, and the people reading it are often children about to spend real money. The page says so in as many words.
- **Game artwork behind the heading** (`banner_html`, `roblox_api.fetch_banners`): the wide 768x432 picture from Roblox's `multiget/thumbnails`, blurred and faded into the page colour behind the top 360px. Game pages use their own, category pages use their biggest game's, and the homepage has none on purpose (picking one game there would read as an endorsement). It is decorative, so it is `aria-hidden` and simply absent when Roblox has no picture. Opacity is `--bannerop`, weaker in light mode (.17) than dark (.3), because dark heading text on a light page needs the art to stay faint. The banner is the first thing in `<body>` at `z-index:0` with `.shell` above it at `z-index:1`; the sticky header is see-through, so it picks the colour up.

## Calendar reminders: removed 16 Nov 2026
The site used to hand out calendar files - a day-picker on each game page that built
a `.ics` for the days you ticked, plus one file per upcoming event. **All of it is
gone**, at the owner's instruction: "I only want the app and browser notifications,
none that you have to go and add it to your calendar."

What went: the `Remind me` block, `/reminder.ics`, `worker/ics.js`, the `ics/` folder,
`write_event_ics`, `remind_btn`, `ics_file`, `ics_fold` and the day-picker styling and
JavaScript. `prune()` still covers `ics/`, which is what deleted the 88 stale files on
the next build; leave it covering that folder.

**The homepage went on advertising it for a day** - "Remind me - on any game's page,
tick the days you want and add them straight to your phone's calendar" sat in "What
you can do here" until 17 Nov 2026, describing a control that no longer existed
anywhere on the site. Deleting a feature means searching the prose for it, not only
the code: that bullet is nowhere near `remind_btn` and no test could have caught it.
It now offers notifications and a link to `/install`.

`bestHour()` **survived and moved into `worker/push.js`**, because notifications ask
the same question the calendar files did. The `.rem` and `.remind` CSS also survived:
the notification panel sits in the same place under the countdown and uses the same
button styling.

Worth keeping in mind rather than regretting: the calendar worked for **everyone**,
with no account and nothing stored, while notifications reach only people who sign in,
and need an install first on Apple devices. That was the owner's call, made with the
trade spelled out, and it got a good deal easier to live with on the same day: the
Roblox app passed review, so signing in is open to everybody rather than the first ten.
If reminders for signed-out visitors are ever wanted again, this is in the git history.

## Browser notifications ("tell me when to get on")
Built 16 Nov 2026. A signed-in person turns on any of **three independent switches**
per game - Quiet, Busy, Events - and their browser is woken about fifteen minutes
before whichever of those is next.

- **Three switches, not one choice.** They were a single `mode` column holding
  `'quiet'` or `'busy'` for the first few hours of their life, which made two
  perfectly compatible things mutually exclusive for no reason anybody could defend:
  plenty of people want telling about both, and an event is a different question
  again. `push_watch` now has `quiet`, `busy` and `events` columns, the `mode` column
  is **dropped**, and **all three off deletes the row** rather than leaving it sitting
  there looking switched on and sending nothing.
- **`/api/push/watch` replaces the whole row**, so anything that changes one switch
  must send the other two back as they are. Both the game page and the notifications
  page read the current row first and post all three; there is a test that catches a
  switch sending only itself.
- **`/notifications` is where they are managed** (`notifications_body()`), reached
  from the bell. Every game being followed, with its four switches, plus a test
  button. It is `noindex`: it is one person's own settings and is empty until the
  browser fills it in.
  - **Its prose said "three" over a list of four for a day** (fixed 17 Nov 2026):
    "What the three mean" headed four bullets, and "turning all three off" sat under
    four switches. Updates was added as a fourth switch and the words around it were
    not. Anything that counts the switches in prose has to move when `KINDS` does -
    there are two such phrases on this page and nothing enforces them.
- **The game page's own control is deliberately bare**: a line, three switches, and a
  link to the page. It had grown to a paragraph of explanation around a button, and
  the explanation belongs on the page that exists for it. Measured at 68 characters of
  wording, and there is a test that fails if it grows past about 110.
- **`PUSH_JS` drives both** rather than being written twice: it looks for `#notif`
  (the game page) or `#notifpage` (the page) and draws whichever it finds. The
  subscribe-this-device flow, the switch handler and the state cache are therefore
  shared and cannot drift apart.
- **The device is subscribed on the first switch anybody presses**, never on load: a
  browser only grants permission in response to a real gesture, and a site that asks
  on arrival is why browsers now bury the prompt. `ensureDevice()` is safe to call
  again - an existing subscription is reused and the server upserts - so no switch has
  to know whether it is the first.

- **Signed-in only, and that is not negotiable.** A push subscription is a permanent
  per-device identifier. Keeping one for a visitor who has not signed in would be
  holding personal data about someone who might be nine. Roblox blocks under-13s from
  authorising outside apps, so everyone who can turn this on is 13+. `worker/push.js`
  enforces it in `handlePush()`, not merely by hiding the button.
- **The notification titles are short, and the short part is the END.** Measured on
  17 Nov 2026 against all 158 real game names: **every single title was over 30
  characters, 99% over 40, and the longest was 81** -
  `"+1 Speed Keyboard Escape | Candy & Chocolate is usually quiet in about 15 minutes"`.
  A phone shows about one line of title, so what got cut was the tail, which is
  exactly where the useful part was: you were left with a game name and no idea why
  your phone had buzzed. The fixed wording is now `"<game>: quiet in 15 min"`,
  `"<game>: event in 15 min"`, `"<game>: new update"`, and `shortName()` caps the name
  at 26 characters with an ellipsis. Worst case went from 81 to 43, and there is a
  test that fails if any title across every real name passes 48. **The cap is how we
  choose what survives** - the phone truncates either way; cutting it ourselves is
  what keeps the ending. The detail stays in the body, which phones show when a
  notification is opened.
- **Tapping a notification lands on the game it is about**, through `data.url` in
  `docs/sw.js`, which also re-uses an already-open tab rather than piling up windows.
  The **test** notification is the exception and goes to `/notifications`: it is not
  about a game, and since it is the only one anybody can set off on purpose it was
  the only one whose landing place ever got noticed. It used to go to the homepage.
- **`worker/push.js`** serves `/api/push/state|subscribe|unsubscribe|watch|test` and
  exports `runPushCron()`. `worker/index.js` calls `handlePush()` and has a
  `scheduled()` handler; `wrangler.jsonc` runs it every ten minutes. **`CRON_MINUTES`
  in `push.js` must stay level with that cron**: the send window is the person's lead
  time *plus one interval*, so a late run still fires, and if the two disagree a
  notification is sent twice or skipped.
- **Two standards, both implemented by hand with WebCrypto**, because Node's
  `web-push` package does not run on Workers. VAPID (RFC 8292) is an ES256 JWT whose
  `aud` must be the push service's **origin**; WebCrypto's ECDSA signature is already
  the raw `r||s` a JWT wants. Message encryption (RFC 8291, `aes128gcm`) keeps the body
  from Google's and Mozilla's relays: body is
  `salt(16) | record size(4) | key length(1) | our public key(65) | ciphertext`, and the
  plaintext must end in a `0x02` delimiter or browsers reject it. **There is a test
  that plays the browser and decrypts our own output** - run it if you touch
  `encrypt()`, because a browser that cannot decrypt a message simply ignores it and
  nothing anywhere reports an error.
- **`push_sent` is keyed on the DEVICE, not the person,** and that was a bug found by
  testing: keyed on the person, somebody with a phone and a laptop had the phone claim
  the hour and the laptop skip silently, so half their devices never rang. A success
  must also **reset `fails` to 0** - devices are retired after five *consecutive*
  failures, and without the reset one that blipped monthly would be deleted after five
  good months.
- **A failed send takes its `push_sent` claim back** so the next run retries, rather
  than losing the day to one blip. A 404 or 410 means that subscription is dead for
  good and the row is deleted instead of retried for ever.
- **`nextWindow()` and `bestHour()` now both live in `push.js`.** `bestHour()` was in
  `worker/ics.js` and shared with the calendar files; those are gone, so it moved to
  the one place left that asks the question. There are tests for all 27 timezone
  offsets checking that the local hour the message names is really the local hour of
  the moment it was aimed at - get that backwards and every notification is an hour or
  a day out for half the world.
- **`/api/delete-me` deletes the three push tables too** (`worker/auth.js`). The
  Privacy Policy promises it, so the promise has to be true; the deletes are listed
  there rather than in `push.js` because that is the one place that promises to erase
  a person, and a feature added later must not escape it.
- **Apple only allows web push for an installed site.** A visitor in a Safari tab
  cannot subscribe at all, so the site now ships a **web app manifest** and the panel
  explains Share then Add to Home Screen instead of offering a button that cannot
  work. `manifest_json()`, and `app_icon()` draws **PNG** icons with `zlib` - no
  Pillow, same rule as `roblox_api.py`, since the build server installs nothing. They
  are generated rather than checked in so they cannot drift from `logo_svg()`; Android
  draws a notification icon at about 24px and ignores an SVG entirely.
- **`docs/sw.js` deliberately caches nothing.** A service worker serving pages from
  its own copy would hand people yesterday's player counts, which is the one thing
  this site must never do. It only listens for notifications.
- **Set up and live since 16 Nov 2026.** `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY`
  are in Cloudflare and the three tables exist in D1, so `/api/push/state` answers
  `available:true` and the panel renders. The pair was generated and piped straight
  into `wrangler secret put` through its stdin, so the private key never went through
  a file, a command line or a chat - the same rule the Roblox client secret follows,
  kept by piping rather than by typing at a prompt. The public key is **not** secret:
  it is handed to every browser that subscribes, and `/api/push/state` returns it.
  `worker/make_vapid_keys.mjs` remains for generating a fresh pair by hand.
- **Rotating the VAPID key is not free once people have subscribed.** A browser ties
  its subscription to the `applicationServerKey` it was given, so a new pair silently
  orphans every existing subscription and each person has to turn notifications on
  again. Rotating cost nothing on day one because nobody had subscribed yet.
- **Proven end to end on 16 Nov 2026**: a real notification reached a real Chrome on
  Windows, so the stored private key signs correctly and the whole chain works. The
  first attempt looked like a failure and was not - Google answered **201** and the
  computer simply did not show the notification, which is why the status is now
  recorded (below).
- **"It said it sent one and nothing appeared" is the complaint to expect, and
  `fails` cannot answer it** - it counts failures only, so it stays 0 both when the
  send succeeded and when it was never attempted. `push_subs.last_status` and
  `last_try` are written on every attempt for exactly this: 0 means the message could
  not be built, -1 means the push service was unreachable, anything else is its real
  HTTP status, and **201 is a normal success**. Read it with
  `npx wrangler d1 execute playtime-admin --remote --command "SELECT fails, last_status, last_try FROM push_subs;"`
  before suspecting the code. Accepted sends are logged as well as refused ones.
- **Before suspecting the encryption, cross-check it against the reference.** The
  `web-push` npm package will not run in a Worker but runs fine in Node: have it
  encrypt a message and decrypt that with our own test's browser-side code, then
  compare the byte layout, headers and JWT claims. Done 16 Nov 2026 and they agree
  exactly, which is what ruled the crypto out in minutes.
- **Four switches, and a bell in each section they belong to.** Quiet, Busy, Events
  and Updates, all independent. On a game page they are not a row of switches in one
  card but a **bell per section**: one at the top of the page (a master), one in Plan
  my session, one on the event calendar, and one on the game's updates page. `KINDS`
  in `PUSH_JS` is the single list of them, read by the game page, the notifications
  page and the bells alike, so a fifth would be added in one place.
  - **A bell may carry its own game in `data-s`, and the page need not have one**
    (19 Nov 2026). Until then a bell meant "this page's game": `PT_GAME` said which,
    and `drawBells()` gave up when there was none - so the two pages that list every
    game, which is where somebody actually is when they decide they want telling,
    had nothing to press. `bellSlug(el)` reads the element's own `data-s` and falls
    back to the page's, `bellBtn()` writes it onto the button, and the click handler
    flips that game rather than `slug`. Every bell for the same game redraws
    together, so three rows of the same game's events cannot disagree.
    - **The site-wide event calendar gives every row a bell** (`.evt .evbell`,
      `data-short`), because that is the moment somebody wants it. `data-short` is
      what turns "Remind me before events" into "Remind me": the row above it has
      already said which game and which event.
    - **Plan my session has one under its Quiet/Busy buttons**, pointed at whichever
      game the dropdown is on. It lives OUTSIDE `#out`, which `draw()` rewrites from
      scratch every five minutes, and above the countdown rather than under the
      twelve-hour table - which is most of a screen further down and nowhere near
      the choice it belongs to. `PT.bells` is the redraw hook `PLAN_JS` calls when
      the game changes; nothing else uses it.
    - Both pages load `PUSH_JS` now. Neither has a `#notif` or a `#notifpage`, so
      nothing explains a failure there the way a game page does - the explanations
      stay on the pages built for them.
  - **The Plan my session bell follows the countdown beside it.** That card already has
    a Quiet/Busy chooser, and a bell next to it means "tell me before THIS window", so
    a third opinion of its own would have been one toggle too many in one card.
  - **The top bell is a LINK to the settings, not a switch** (17 Nov 2026). It was a
    master - on turned the quiet one on, off turned all four off - which is a blunt
    thing to put at the top of a page when the four switches it stood for are one tap
    away. It is `masterLink()` now, an `<a>` to `/notifications?game=<slug>`, and it
    still says "Notifications on" or "Notify me" so it reports the state it no longer
    sets. **It carries the game on purpose**: `/notifications` otherwise lists only
    games already followed or saved, so arriving from a game that is neither would
    land on a page that does not mention it, which reads as a broken link. `cameFor()`
    reads the parameter and `listed()` puts that game first, adding a row for it with
    all four off if it has none.
  - **Every bell label comes from `bellLabel()`.** It was written out in three places
    (the signed-out bell, the real one, and the one on an uninstalled Apple device)
    and they had already started to drift.
  - **Three say "before" and one says "about", and that is not a slip.** Quiet, busy
    and events all aim at a moment still to come, so "Remind me before quiet". An
    **update is already done** by the time Roblox reports it - see the fourth switch
    below - so "Remind me about updates" is the only honest wording; "before" would be
    a promise broken every single time one arrived.
  - **Signed out, a bell is a link into sign-in rather than nothing.** It was an
    empty slot until 17 Nov 2026, on the grounds that a control that cannot work
    should not be drawn; a bell is the clearest thing on the page to say what
    signing in is *for*, so it is now drawn as an `<a>` to
    `/auth/login?back=<this page>` and the visitor is returned here afterwards. It
    is never a toggle when signed out: a push subscription is a permanent
    per-device identifier, and keeping one for somebody who has not signed in
    would be holding personal data about someone who might be nine. The one
    explanation in Plan my session stays, since that is the only place with room
    for the 13+ note.
  - **With no keys set, or in a Safari tab on an iPhone, the slots do stay empty.**
    Those are cases where signing in would not help, so there is nothing to offer.
  - **`PUSH_JS` gave up on any page without `#notif` or `#notifpage`**, so the updates
    page - which has neither, only a bell - drew an empty slot until that test learned
    about `[data-bell]`. Caught by testing the real page rather than the game page
    twice.
- **Event notifications** are the third switch: something the creators have put on the
  game's Roblox calendar is about to start. **Updates** is the fourth, and the odd one:
  it looks *backwards*, because a change has already happened by the time Roblox
  reports it. `build_site.py` writes each game's last-changed timestamp into
  `events.json` beside the events, the dedupe key is that timestamp, and a change more
  than **12 hours** old is left alone - builds are six hours apart, so that is the
  staleness allowance with room to spare.
- **Saved games get a row on `/notifications`** with all four switches off, ready to
  turn on: saving a game is already somebody saying they care about it, and making them
  find it again to switch something on was a step with no purpose. The row says
  "saved", so it reads as an offer rather than as something already on.
- **Pressing a switch sends nothing.** It used to fire a sample notification off the
  first one anybody turned on; the "only once" guard was a flag on the state object,
  and `refresh()` replaces that object with a fresh answer from the server moments
  earlier, so the flag was never there and **every** switch sent one. Seeing what a
  notification looks like is what the **Send me a test** button on `/notifications` is
  for, pressed on purpose. There is a test that fails if a switch ever sends one again.
- **The first switch turned on without the site installed says so once**, with a link
  to `/install`. A note beside the switch, not a wall in front of it - outside Apple's
  world installing is an improvement rather than a requirement.
- **On an iPhone or iPad in a tab, pressing a bell opens a popup instead** (`.ipop`,
  `buildPop`/`openPop`/`closePop` in `PUSH_JS`, 17 Nov 2026). Apple allows no web push
  at all until a site is on the home screen, so there the bells used to render as an
  **empty slot**, which reads as the site being broken rather than as one step away
  from working. They are drawn as ordinary bells now and pressing one explains Share
  then Add to Home Screen, with a link to `/install` and its screenshots. It closes on
  the X, on Escape and on a tap outside the box, and **it enables nothing** - there is
  a test that fails if a watch is ever posted from an uninstalled Apple device.
  - **It is Apple-only, and that is deliberate.** Web push works in an ordinary
    browser tab on Android, Windows and Mac with no install at all, and that is the
    proven path - the first real notification reached a real Chrome on Windows. Gating
    those would switch off a working feature, and a browser that never offers an
    install button (Firefox has none on desktop, so `ptInstalled()` can never become
    true there) would be locked out for good with nothing to press. The owner asked
    for a gate everywhere, was shown that trade, and settled on this.
  - **The box is `var(--solid)`, never `var(--card)`.** `--card` is translucent for
    the glass look, which is right for a card on the page and wrong for a popup: the
    heading behind it read straight through the instructions. Caught in a screenshot,
    not in the markup.
  - It is appended to `<body>`, not written inside the header, for the same reason
    `.drawer` and `.sheet` are - `.hdr` has `backdrop-filter`, which would make the
    header the containing block for anything `position:fixed` inside it. `z-index:31`
    puts it above the drawer and the search sheet, which are both 30.
  - It is built once and kept, because `draw()` replaces the bells on every change and
    a popup living inside that markup would be torn down while it was open.
  - **The switches on `/notifications` go through it too.** They were drawn and
    clickable on an iPhone tab and simply threw an error, so the interception sits at
    the top of the delegated click handler and covers the bells, the switches and the
    test button at once.
  - The worker cannot call Roblox, so `build_site.py` writes **`docs/events.json`**
    (`{games: {slug: [{t, s}]}}`, upcoming only, 12 per game) from the `all_events` it
    already collects. Its own small file rather than part of `data.json`, which carries
    a week of player counts per game and is downloaded by visitors on two pages. About
    6KB. Freshness is one build (up to six hours), which is fine for events announced
    days ahead; an event announced *and* starting inside six hours is the one case this
    misses.
  - **The dedupe slot is the event's own start time** (`evt<unix>`), not the hour, so
    two events in the same hour are two notifications and neither silences the other.
    There is a test for exactly that.
  - `claimAndSend()` holds the claim-send-and-tidy bookkeeping that the window path and
    the event path both need, so the two cannot drift.
- **The 10-person cap is gone**: the Roblox app passed review on the morning of
  16 Nov 2026, so anybody can sign in and anybody can have notifications.
- Tests live in the scratchpad, not the repo: crypto round-trip, 27 timezone offsets,
  the cron's decisions against real SQLite, the HTTP routes against `wrangler dev`,
  and the whole UI in a real browser. About 226 checks. **If `wrangler dev` seems to
  ignore `.dev.vars`, look for a stale `workerd`**: `TaskStop` kills wrangler's parent
  but leaves `workerd` holding the port, and the old process then hot-reloads new code
  with its old environment - which looks exactly like the secrets being wrong. Kill
  the whole `wrangler dev` process tree, not just `workerd`, or it respawns.

## Countdowns, and events Google can read
- **`ptCountdowns()` in `SHARED_JS`** drives anything carrying `data-at` (a moment in
  unix seconds): "Next event in 2d 4h 11m" on the event calendar, and "Next update
  expected in ..." on an updates page. It **re-queries every tick** rather than caching
  the elements, because the next-update line does not exist until `PATTERN_JS` has
  worked out when that is.
- **Under an hour it shows seconds; days out it shows days and hours.** That is why it
  looks frozen for a minute at a time, and why the test for it injects a target a
  minute away rather than watching the real one - the first version of that test
  "failed" against perfectly good code for exactly this reason.
- **The next-update countdown is only drawn when an hour is known.** `update_pattern`
  sometimes knows the weekday and not the hour, and "some time on Friday" is not
  something to count seconds down to; saying otherwise would claim a precision the data
  does not have.
- **The quiet-window countdown on a game page keeps its own ticker** and is not part of
  this, because it also has to re-decide *which* hour it is aiming at every five
  minutes.
- **`event_schema()` writes upcoming events as schema.org `Event`**, which is the form
  Google reads for rich results. Roblox events happen inside a game rather than
  anywhere on a map, so they are a `VirtualLocation` pointing at the game and the
  attendance mode says online. Nothing is invented: name, start and end are the
  creators' own, and an event with no end is left without one rather than given a
  guess. `iso_moment()` writes the times, always UTC with the Z.

## Search engines (SEO)
All of this lives in `build_site.py`. Nothing here is a trick: every number a page claims is one it worked out from our own samples, and nothing is hidden from visitors to feed Google something different.

- **`page()` writes the head for every page.** It takes `canon` (this page's one real address), `image` (the picture for Discord/WhatsApp previews), `trail` (breadcrumbs), `schema` (structured data), `noindex` (keep this one page out of Google) and `modified`. **Every new page must pass `canon`,** or `check_seo.py` fails it.
- **Addresses carry no `.html`; files on disk still do.** Cloudflare serves the file `game/doors.html` at `/game/doors` and **307s `/game/doors.html` to it**, so the short form is the one every visitor actually lands on - the page-view table proves it, as every row recorded since launch is `/game/steal-an-egg`, never `/game/steal-an-egg.html`. Until 14 Nov 2026 the links, the canonical tags and all 304 sitemap entries said `.html`, which pointed Google at an address that redirects somewhere else on every page of the site, and left the admin dashboard's per-game reading times looking up a path that could never match. `write()` still takes a file name (`privacy.html`); `canon`, `trail`, `href`, `abs_url()` and the sitemap take an address (`/privacy`). The regex sweep that did this keyed on the leading slash, since a file path never has one.
- **Three separate switches decide what Google sees**: `NOINDEX` for the whole site while designing, `noindex=True` for one page, and `sitemap.xml` for the list we actually ask Google to look at. `index_ok(card)` is the gate: a game needs 3+ days of history and to have been seen in 48+ of the week's 168 hours. Below that it keeps its page (it still works and is still linked) but is noindexed and left out of the sitemap, so the site never fills up with "too new to say" pages.
- **The facts are in the HTML, not only in the charts.** Everything from `DAYS` down to `game_schema()` in the "page sections" part of `build_site.py` writes a game's numbers out as text: the opening paragraph, `facts_html`, `short_answer`, `hours_table_html` (all 168 hours as a real table, inside a `<details>`), `history_html` (the day-by-day player count history) and `faq_html`. The charts, the heatmap and the countdown are still drawn by the browser, because only the browser knows the visitor's timezone. **Anything the builder writes is in UTC and says so**; the browser replaces `#best` and `#quiet` with the same fact on the reader's own clock.
- **Every answer on a questions page links to the part of the game page that
  shows it**, since the questions became a page of their own on 17 Nov 2026 and the
  charts stayed behind. `links` in `faq_html` maps a question to its address: the
  key numbers, the day-by-day history graph, the hourly graph, the 45-day trend
  under "Is it dead?", or the updates page. Visits has none, because nothing on the
  site shows more than the answer already does.
  - **The link is in the HTML only, never in the plain answer.** The same answers
    are handed to Google as `FAQPage` text, and link words in there would arrive as
    stray sentences. That is what `more(q)` is for.
  - **Only a card that exists is linked**, the rule `jump_html()` follows. The
    history card is dropped below three days of readings, so its links fall back to
    the key numbers rather than naming an id that is not on the page.
  - **Say "the game page", not "this page".** The best-time answer went on saying
    "the charts on this page show those times on your own clock" after the split,
    on a page with no charts on it - the same trap as the homepage advertising the
    deleted calendar reminders. Deleting or moving a section means searching the
    prose for it.
  - **An answer may only answer the question above it.** "Do people still play X?"
    opens "Yes" with a live count and then used to paste on the whole of
    `verdict()`, whose own first word answers "Is X dead?" - so 42 of the 140 live
    pages said "Yes. 263,503 people were playing Adopt Me... **No.** It is picking
    up a little." `verdict()` returns a fourth item now, the same sentence without
    its leading yes or no, and the questions page takes that one. The card on the
    game page still takes `[2]`, where "No." is the answer to the question it
    really asks. Both halves are written out in `verdict()` rather than cut apart
    by a regex at the other end, so rewording one cannot quietly stop the other
    working - and anything unpacking `verdict()` takes four values.
- **Estimate vs observation.** "Typical"/"about"/"average" is an average of our samples. "Highest seen"/"recorded" is a single reading we really took. Never blur the two, and never add a rating or review to the structured data: we do not collect either.
- **Structured data** is `jsonld()`: `VideoGame` + `Dataset` + `FAQPage` + `BreadcrumbList` on game pages, `ItemList` on the ranked lists, `WebSite` on the homepage, `Dataset` on `/busiest-hours.html`. **Both `Dataset` blocks carry `license`, pointing at our own `/terms`** - Search Console warned "Missing field license" on 14 Nov 2026 (non-critical) once it had crawled three pages. It is deliberately not an open licence such as CC BY: Terms says personal use and asks people not to copy the site wholesale, and publishing a licence that contradicts our own terms would be worse than the warning. **If the numbers are ever meant to be reusable, change both `Dataset` blocks and the "Using the site" section of Terms together**, and move `POLICY_DATE`.
- **`clean_name()` and `name_slugs()`**: Roblox creators rename games for every holiday (`[HALLOWEEN PT 3] Grand Piece Online`). The site uses the **core name** for headings, titles and addresses, so `/game/grand-piece-online.html` survives the rename instead of being pruned and rebuilt under a new address every few weeks, losing its links and its standing in Google. Square brackets and emoji are stripped; round brackets are left alone because they are often part of the real name. Ties are broken with the universe id so an address never changes build to build. `c["name"]` is the tidy name, `c["full"]` is what Roblox calls it today, and the game page says so in its opening paragraph.
- **`/busiest-hours.html`** (`busy_page()`) answers "when is Roblox busiest?" across every game at once. Each game counts as a share of its own peak hour, so one huge game cannot drown out forty small ones. It is linked from the footer, the homepage and every game page, not from `TABS`, which is already full.
- **`sitemap.xml`** is the real sitemap, with `lastmod` per page. `sitemap.txt` is still written so an address already given to Google keeps working. **Sitemaps need full web addresses**, so they are useless until `DOMAIN` is set; the build prints a warning when it is empty.
- **`docs/404.html`** is a real page, and `worker/index.js` hands it back with a 404 status through the `ASSETS` binding in `wrangler.jsonc`. Do **not** set `not_found_handling` in `wrangler.jsonc`: Cloudflare would then answer every unmatched address itself and the worker would never run, breaking `/admin`, `/api/*` and sign-in.
- **`check_seo.py`** skips `/admin` and `/api/*`, because the worker answers those and there is no file to find. It reads a built folder and reports broken links, missing or duplicated titles and descriptions, a canonical that points at the wrong page, skipped heading levels, pictures with no alt text, structured data that is not valid JSON, and sitemap entries that do not exist. `python check_seo.py preview` after a preview build, `python check_seo.py docs` after a real one. The build workflow runs it and prints the report, but never fails the build on it.

## Files
- `build_site.py`: all page design (CSS, HTML, JS) lives here. Settings at the top: `SITE`, `MIN_SAMPLES`, `ADS`, `NOINDEX`, `OUT` (reads `SITE_OUT`), `DOMAIN`, `CONTACT`, `SPIKE`.
- `roblox_api.py`: every Roblox call made while building (icons, descriptions, game passes, events, and the colour each icon reads as). It reads PNGs itself, with the `zlib` that comes with Python, rather than pulling in Pillow: the build server installs nothing, so it must stay dependency-free. Icons are asked for as PNG only for the colour; the pages still use the WebP ones. Answers are cached in `.cache/` (gitignored) so a rebuild is instant; a cold build takes about 40 seconds for 51 games. If an endpoint dies, the function returns `None` and the page quietly leaves that section out.
- `collector.py`, `cloud/collector_cloud.py`, `cloud/build_cloud.py`: data pipeline. They import each other, so change them together.
  - **Roblox does not leave out an id it will not talk about: it sends a placeholder.**
    A deleted or newly-private game comes back as
    `{"id": 0, "name": "[TITLE UNAVAILABLE]", "rootPlaceId": 0, "created": "0001-01-01T00:00:00Z"}`.
    Both collectors used to take `g["id"]` from the answer rather than the id they
    asked about, so every dead game in `games.txt` was being collected into **one
    shared phantom game**. By 17 Nov 2026 it had 166 samples on the `data` branch and
    was gaining three every half hour, so it was about six hours from passing
    `MIN_SAMPLES` and being given a page and a sitemap entry; it had already built
    one in `preview/`. Both collectors now skip an entry with no id, and
    `build_site.py` drops a row with no id or no name as a net, **because the samples
    already on the `data` branch cannot be un-collected** - that guard is load-bearing
    for ever, not a transitional one.
  - **`0001-01-01` is .NET's `DateTime.MinValue`, and it is how Roblox says "no date".**
    Left alone `_iso` turned it into `-62135575740`, which is **truthy**, so every
    `if meta.get("updated")` guard passed it and the page claimed the creators last
    touched the game in the year 1. On Windows `datetime.fromtimestamp()` then raises
    `OverflowError` (the FILETIME floor is 1601) and takes the **whole build** down;
    on Linux it does not crash, so the build server would have published the year-1
    date quietly. `ROBLOX_EPOCH` in `roblox_api.py` is the floor: a date before 2003
    reads as no date. **Any new date Roblox hands us goes through `_iso`**, never
    `fromisoformat` directly.
- `seed_demo.py`: invents player counts for local previews, using the real IDs in `games.txt` so names, pictures, descriptions and events are real. It refuses to run if `SITE_OUT=docs`.
- `games.txt`: one universe ID per line (not place IDs), **and nothing else - no comments**. All four readers (`collector.py`, `cloud/collector_cloud.py`, `build_site.py`, `seed_demo.py`, and now `discover.py`) parse it as `open(...).read().split()` filtered by `isdigit()`, so *any* bare number in the file is read as a game ID: a line reading `# 140 games` would quietly become a request for universe 140. `discover.py` appends to it on a schedule (see "Finding new games"). **Every game in it is Roblox maturity "Minimal" or "Mild", and that is a rule, not a coincidence** - much of the audience is children. Before adding a game, read its label back from Roblox rather than judging it by the name: `POST https://apis.roblox.com/experience-guidelines-api/experience-guidelines/get-age-recommendation` with `{"universeId": N}` answers `contentMaturity`. Several of the biggest games on Roblox are "Moderate" (Murder Mystery 2, Dead Rails, BlockSpin, Da Hood, Deepwoken, Pressure), so the gap is not an oversight. To find a game's universe ID by name, `https://apis.roblox.com/search-api/omni-search?searchQuery=<name>&pageToken=&sessionId=<any uuid>&pageType=all` - it returns nothing at all without a `sessionId`.
- `check_seo.py`: reads a built site and reports search-engine mistakes. Changes nothing.
- `discover.py`: finds newly popular games and appends them to `games.txt`. See "Finding new games" below.
- `worker/theme.js`: the site's two palettes, written by `build_site.py` so the admin dashboard matches the public site. Do not edit by hand; change `LIGHT` or `DARK` in `build_site.py`.
- `worker/push.js`, `worker/schema_push.sql`, `worker/make_vapid_keys.mjs`: browser notifications. See "Browser notifications" above. `worker/ics.js` is **gone** (16 Nov 2026) along with the calendar files; `bestHour()` moved into `push.js`.
- `build_site.py` ends by pruning `docs/game/` and `docs/category/`: any page this build did not write is deleted, so a renamed game, an ID removed from `games.txt`, or a game dropping below `MIN_SAMPLES` cannot leave an orphan page live for ever. It runs last, so a build that fails part way deletes nothing, and it never touches top-level files you add by hand (`ads.txt`, a favicon, `CNAME`). The build job uses `git add -A docs` so those deletions are committed.
- Browser code lives in `build_site.py` as `SHARED_JS` (timezone shifting, busy-ness bands, "next good block", escaping) plus one block per page. Anything that puts a game name into HTML in the browser must pass it through `esc()`: names come from Roblox and can contain quotes and angle brackets.
- **Never write a backslash escape in those JavaScript blocks.** They are ordinary (non-raw) Python triple-quoted strings, so Python eats the backslash before the browser ever sees it: `'your device\'s '` reached the page as `'your device's '`, which ends the JavaScript string early and threw "missing ) after argument list" on every game page. Reword to avoid the apostrophe rather than doubling the backslash - `\\'` works but reads as a typo and the next person will "tidy" it. The escapes Python interprets are `\' \" \n \t \r \b \f \0 \x \u \U \N` and `\\`. **Checking this needs a browser, not a reading**: `PUSH_JS`'s *source* in the file looks correct, and extracting it with a regex also looks correct - only the built page has the value Python actually produced, which is why `notifui.js` loads real pages and collects `pageerror`. This is the same family of trap as the backtick and octal-escape rules in `worker/index.js`.

## Rules
- The Roblox endpoints are unofficial and can change. Use only public endpoints. Never ask for a Roblox password (sign-in happens on Roblox's own site), never add Robux generators or gambling.
- Local preview: `set SITE_OUT=preview`, `python seed_demo.py`, `python build_site.py`, then serve the `preview` folder with `python -m http.server`. Never overwrite `docs/` with demo data.
- `data` branch changes constantly. Do not merge it into `main`. Cloudflare must not build it.
- Before editing, pull the latest (the build job commits to `docs/` on `main`).
- The owner buys domains and creates Cloudflare/AdSense accounts and accepts terms themselves.
- Past mistake to avoid: pasting one file's contents into another (for example workflow text into `collector.py`). Check the first line of each file after any edit.
- **`build_site.py` was silently rewritten back to its committed state once** (16 Nov 2026), losing about an hour of edits that had already been built and checked. The cause was never proved - OneDrive was not running, and an editor saving a stale buffer is the likeliest explanation - but the lesson is cheap: **commit as soon as a change builds, before the long tail of testing**, and if a change seems to have vanished, check the file against `git show HEAD:<file>` before assuming the code is wrong. Writing each patch to a file in the scratchpad rather than piping a heredoc is what made it re-appliable in two minutes.

## Current status
- Collecting data (140 games in `games.txt`, all Roblox maturity "Minimal" or "Mild"). **The domain is bought and live: `playtimestats.com`** (Nov 2026), on Cloudflare's own nameservers, answering on both the apex and `www`, with the `workers.dev` address still working too. `DOMAIN` and `CONTACT` are set, so `sitemap.xml` finally carries full web addresses. **`NOINDEX = False` since 13 Nov 2026**, so the site is open to Google: `robots.txt` allows everything but `/admin` and `/api/` and names the sitemap by its full address, and the only page still carrying `noindex` is `404.html`, deliberately.
- **`contact@playtimestats.com` is the site's contact address**, a Cloudflare Email Routing rule that forwards to the owner's own inbox; no mailbox is hosted. It prints at the **foot of every page** through `foot_contact()` (19 Nov 2026, owner's call: it had been a section inside the Terms of Service, which is the last place somebody with a question would think to look), and as a Contact heading on About and Privacy through `contact_html()`. **Terms no longer carries one** - the foot of the page is on that page too. Privacy keeps its own, because a privacy policy that cannot be replied to is not much of one. Setting the address in the first place moved `POLICY_DATE` to 13 Nov 2026; taking it out of Terms moved it again, to 19 Nov 2026. Email Routing only **receives**: replying from the forwarding inbox sends from the owner's personal address, which defeats the point of a non-personal contact, so set up Gmail "Send mail as" before replying to anyone.
- **Browser notifications are live and open to everybody** (16 Nov 2026): VAPID keys set in Cloudflare, the three push tables in D1, three switches per game, and `/notifications` to manage them. The Roblox review passed that morning, so the 10-user cap is gone. See "Browser notifications" above.
- **Sign in with Roblox works.** The domain unblocked it, the redirect URL is registered, and people have signed in and out for real since 14 Nov 2026 - which is how the sign-out bug above was found. The OAuth app is on the Roblox account `gp_isweird`, client id `5479373624062556036`, secret rotated 14 Nov 2026, and it **passed Roblox's review on 16 Nov 2026** - the 10-user cap is lifted. **Still to do:** delete the old app `5285601446665495033`.
- In Cloudflare, **Settings -> Builds -> Previews Base -> "Builds for Preview branches" is off**. It has to stay off: with it on, Cloudflare tried to deploy the `data` branch every ten minutes and failed every time, because that branch holds only the CSVs. The Production tab's deploy command is plain `npx wrangler deploy`; a `--assets ./docs` flag there would point at the right folder but create no `ASSETS` binding, and the 404 page would stop working.
- **`MIN_SAMPLES` is at its launch value of 200** (set 2 Nov 2026) and **all 140 games clear it now**, so the dip it caused is over: the site builds 140 game pages and every one also passes `index_ok()`, so all 140 are in the sitemap. There is no reason to touch it again - it has stopped being a brake on the existing games and is now only a gate on *new* ones added to `games.txt`, which simply have no page for about a day and a half. Lowering it to 2 is still the undo if design work ever needs every game present.
- Sitemap uses full URLs once `DOMAIN` is set in `build_site.py`.

### Done
- About + Privacy pages, game thumbnails, Save/favorites (browser localStorage only). The About page carries a **Reminders** section and a **"Which games are on here"** section saying we only list games Roblox labels Minimal or Mild and that we read that label back from Roblox rather than guessing - worded as a rule about the label, not a promise about the game, with the caveat kept below it. **Every count on the site is computed** (`len(cards)`, `total_samples`), so adding games to `games.txt` updates the wording on its own; nothing anywhere types a number of games in. **It will not match `games.txt`, and that is correct**: `cards` is games with enough readings to have a page, so a game `discover.py` added yesterday is in the file and not yet in the count. On 16 Nov 2026 the file held 160 and the site said 140, which is twenty games still collecting. Do not "fix" this by counting the file - the site would then claim pages it does not have. The collector runs every 30 minutes and takes three readings ten minutes apart inside each run, so the pages say **"about every 10 minutes"** - the old "every 30 minutes" on About and "every few minutes" on the homepage were both wrong and disagreed with each other.
- For-parents game-pass section, fetched from `apis.roblox.com/game-passes/v1/universes/{id}/game-passes` (the old `games.roblox.com` one is dead).
- Category pages from Roblox `genre_l1` (saved in the `genre` column; a category needs 2+ games).
- `TABS` in `build_site.py` is the site's section list (All games, Most popular, Trending, Growing, Shrinking, Event calendar, Compare games, Plan a session). **`sitemap.xml` is built from it**, so a section left out of `TABS` is a section we never ask Google to look at. The row of pills that used to sit across the top of every page was removed in Nov 2026. Genres are pills on the homepage.
  - **`PANEL_HIDE` is what the panel leaves out**, not `TABS` itself (17 Nov 2026,
    owner's call): **Most popular and Trending**. Growing and Shrinking went with
    them for a few hours the same day and were put back, so do not read the pair as
    a category - it is simply the two the owner did not want listed. `TABS` fills
    the panel's `<nav>` only: All games, Growing, Shrinking, Event calendar, Compare
    games, Plan a session, When is Roblox busiest?, About.
  - **The panel's order is one piece of markup that reads correctly at both widths**
    (17 Nov 2026). Top to bottom: `.dtop` (the account, Notifications and Search -
    all three phone-only - then **Get the app**), then the sections, then `.dbot`
    holding **Light mode** under its own rule. On a computer the first three
    collapse, so Get the app is the first thing in the panel and the theme the last,
    which is what was asked for at each width without writing two panels.
    **Get the app is a `.drow` in `.dtop`, not a row in `TABS`**: it is a thing to
    do rather than a part of the site to go and read, and `TABS` also feeds the
    sitemap. It uses `ICON_INSTALL`, which had been defined and unused since the old
    "Install app" row.
  - **The footer is what stops that becoming four orphan pages.** Growing and
    Shrinking were never in the footer, and the homepage card that linked them went
    at the same time, so for a moment nothing on the site linked to either while both
    stayed in the sitemap. They were added to the footer in the same change. **Before
    taking anything out of the panel, check the footer carries it** - that is the
    footer's whole job here, and it is why the pills could be deleted safely.
  - **On a phone the three ways in are buttons on the homepage** (`.homenav`,
    19 Nov 2026), directly under the search box: three in a row, Busy now / Quiet
    now / Popular. They are in the bar across the top on a computer and a phone's
    bar has no room for them, so on a phone they go back to the one page everybody
    starts on. `CHROME_JS` marks the one you are on in **every** copy - the
    selector is `[data-hn]`, not `.hnav a[data-hn]` - and it uses
    `classList.add('on')` rather than `className='on'`, because five of the links
    in the bar also carry `more`, the class that keeps them out of a narrow bar,
    and overwriting it put the one you were on back on screen at widths with no
    room for it.
  - **All EIGHT links wear the mark, not the first three** (19 Nov 2026, owner's
    call). The stylesheet had treated them alike from the start - one `.hnav a.on`
    rule with the underline and its glow - but `hkey` in `CHROME_JS` could only
    ever come out `busy`, `quiet` or `popular`, so standing on Growing,
    Shrinking, Events, Compare or Plan the bar said nothing about where you were.
    Each of those five is a page of its own, so the file name is the answer
    (`hseg`); busy and quiet are the homepage asked a question, so they still come
    off the query string. **`hseg` is read once and the bottom bar's `tkey` uses
    the same value** - it had its own identical copy as `hseg2`. If a ninth
    section is ever added to `TABS`, its name goes in that list or it will be the
    one page in the bar that never lights up.
  - **The bar across the bottom of a phone is four now: Search, Saved, Events,
    Plan** (19 Nov 2026). Anything in that bar is hidden from the panel below
    900px (`.drawer nav a[data-sec=events]`, `[data-sec=plan]`), because the
    panel is not where somebody on a phone goes looking for them. On a computer
    there is no bottom bar, so the panel keeps both.
  - The labels in `TABS` are read by the panel and nowhere else (the footer's are
    written out), so renaming one is safe. Events and Compare became **Event
    calendar** and **Compare games** because one word each was doing too much work.
- Homepage: "What are you looking for?" (busy / quiet / browsing) narrows the list to the games that are quiet or busy at the visitor's current hour, off a 168-digit busy-ness string per game baked into the page, so there is no extra request. Order stays player-count descending whether filtered or not. **Every game follows roughly the same daily rhythm, so a fixed test ("quiet" = the bottom two of a game's own five levels) came up empty for 85 of the week's 168 hours, and 67 for "busy".** `strict()` is still what the words mean; `fits()` is what is filtered on, and it widens to the quietest (or busiest) level any game is actually at this hour, so there is always an answer. `band.relaxed` says the widening happened and the note then admits it ("No game is properly quiet right now... these are the quietest of them"). When some games really are quiet, nothing widens and the behaviour is unchanged. `nextGood()` must keep using `strict()`, not `fits()`: it answers "when will games really be quiet", about a different hour than the band describes. A third case, no readings at all for this hour, is a different message again. Search goes through the same `refresh()` so the two cannot fight over which tiles are hidden.
- Per-game pages: event calendar, recent updates and changes, game description, "Is X dead?" verdict with a 45-day chart, "Days the player count jumped" (any day `SPIKE`x busier than the week before, matched against the creators' events), and "Plan my session".
- **Live countdown**: "Quietest window starts in 2h 14m 07s", ticking every second, on each game page and on `/plan.html`. `plan()`/`draw()` works out the hour being aimed at and `tick()` only rewrites the clock, so the digits move every second without redoing the maths. The block is recomputed every 5 minutes, and straight away once the countdown reaches zero.
- **Update rhythm** (`update_pattern`): "Updates usually arrive on a Friday around 2 PM your time, about every 7 days." Worked out from the start times of the creators' past events, plus spike days for the weekday only (a spike is measured over a whole day, so its hour means nothing). Deliberately cautious: needs 8+ dates, a weekday holding 30%+ of them, a repeating hour before it names one, and 4+ gaps with a median under 32 days before it claims an interval. 34 of 51 games currently qualify. Stored in UTC and converted in the browser, like every other time on the site.
- **Search engines**: canonical addresses, Open Graph pictures, breadcrumbs, structured data, `sitemap.xml` with dates, a real 404 page, and every game's numbers written into the HTML rather than drawn only by the browser. Game addresses now come from the game's core name, so a holiday rename no longer breaks every link to it. See the "Search engines (SEO)" section above.
- **Redesign (Oct 2026)**: owner's palette, one game's page stripped back to a side menu plus search, hourly data drawn as line graphs with a draggable readout, a separate `/updates/<game>.html` page behind a "Game updates" button, and game passes shown with pictures and contents. See "Look and layout" above.
- **Tile glow**: hovering a game lights it up in a colour taken from its own icon. Worked out at build time, so the browser downloads nothing extra and does no work for it. 99 of 100 games get a colour; the spread is mostly reds and oranges, which is what Roblox icons actually are.
- **Admin dashboard redesign**: four tabs instead of one long page, the site's own black-and-purple palette fed in from `worker/theme.js`, a "Needs doing" list at the top worked out from real conditions, and the numbers drawn as graphs (a drag-to-read line for page views, rings for progress, bars for the days of the week and for pages and games). See "Admin dashboard" above.
- **Notifications**: three switches per game (Quiet, Busy, Events), managed on `/notifications` and reachable from the bell in the header. The calendar reminders they replaced are described under "Calendar reminders: removed".
- **Jump links in the game page's button row** (Nov 2026): Events and Questions sit beside Play, Game updates and Save, so the sections furthest down a long page are one tap away. Compare left that row to make space. See "Look and layout" above.
- **Similar games** row at the foot of each game page (`similar`): same category first, then closest in typical player count on a log scale, so 1K vs 2K counts like 100K vs 200K. The wording changes to "games with about as many players" when the category could not fill the row.
- `main()` runs in **two passes**: pass one works out every game's numbers, pass two writes the pages. It has to be this way round because the "Similar games" row on each page needs to know about all the others. The empty-site guard sits between them, so it fires before anything is written.
- `/events.html` site-wide calendar, `/compare.html` (two games overlaid, loads `/data.json`), `/plan.html`.
- Events and updates come from `apis.roblox.com/virtual-events/v1/universes/{id}/virtual-events`. Creators use these as a changelog, so past ones are the "recent updates" list and unfinished ones are the calendar. Unofficial endpoint: if it dies, both sections disappear on their own.
- Timezones: `tzOff()` in `SHARED_JS` rounds the visitor's offset to whole hours. Every page must use it. The homepage and the game pages convert between local and UTC in opposite directions, and they disagreed by an hour for half-hour timezones (India) until this was shared.

## To do
Launch checklist, in order:
1. ~~**Buy the domain**~~ **done Nov 2026** - `playtimestats.com`, with `DOMAIN` and `CONTACT` set and the sitemap carrying full addresses.
2. ~~**`MIN_SAMPLES = 200`**~~ **done 2 Nov 2026.** If it ever needs lowering again for design work, remember the trade: below 200 the site shows every game, at 200 it shows only the ones with enough readings to be worth believing, and `prune()` deletes the pages of any that drop out.
3. ~~**Finish Sign in with Roblox**~~ **done, and the app passed review on 16 Nov 2026**, so the 10-person cap is lifted and sign-in - and therefore notifications - is open to everybody. The only loose end is deleting the old OAuth app `5285601446665495033`.
4. ~~**`NOINDEX = False`**~~ **done 13 Nov 2026**, with all 140 games in the sitemap and `check_seo` clean. **Search Console is connected and `sitemap.xml` is submitted** - it sent a "Missing field license" warning on 14 Nov after crawling, which only happens for a verified property.
   - **But on 17 Nov 2026 it still showed 304 Discovered URLs, and that is the stale pre-14-Nov count** - the version where every entry ended in `.html`. So Google's list for this site was 304 addresses that each **307-redirect**, rather than the 671 real pages the live sitemap now holds. Nothing was broken on our side: both `sitemap.xml` and `sitemap.txt` serve 671 entries, none carrying `.html`, all on the live domain. Google simply had not re-read the file.
   - **Re-submitted on 17 Nov 2026**, which is what this needed; Discovered URLs should
     settle near the live count rather than the old 304.
   - **Re-submitting the same address in Search Console -> Sitemaps is what forces a fresh fetch.** Worth doing after any change that moves the page count a long way - the Nov 2026 split, which gave every game its own Events, Questions, What-costs-money and Updates pages, more than doubled the site and none of those were in the list Google held.
   - Still worth checking which property is being looked at: **`www` serves a complete live duplicate of the site** (see the `www` note under Sign in with Roblox), so numbers read from a `www` property are the duplicate's.
5. **AdSense** once 20+ pages have real data. Mark the site as child-directed. Paste the script into `ADS`; the Privacy Policy changes its ad wording on its own when `ADS` is set, so re-read it afterwards.
6. Check `POLICY_DATE` is right whenever the Privacy Policy or Terms change.

Waiting on data, nothing to do:
- Trending / Growing / Shrinking need ~2 weeks per game, the "Is X dead?" verdict needs 10 days, and "Days the player count jumped" needs about 2 weeks.
- As of 31 Oct 2026 collection had only just started (~600 player counts), so no game met `MIN_SAMPLES = 200` yet and the site showed only its section pages. This is expected and clears itself.
