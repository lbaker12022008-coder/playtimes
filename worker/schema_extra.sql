-- How long pages are left open, and the owner's launch checklist. Run once:
--   npx wrangler d1 execute playtime-admin --remote --file worker/schema_extra.sql

-- Time spent reading. Counts seconds only, with no cookies and nothing that
-- identifies a visitor: we cannot tell one person from another.
CREATE TABLE IF NOT EXISTS dwell (
  day     TEXT    NOT NULL,       -- YYYY-MM-DD (UTC)
  path    TEXT    NOT NULL,
  seconds INTEGER NOT NULL DEFAULT 0,   -- total across every visit that day
  hits    INTEGER NOT NULL DEFAULT 0,   -- how many visits made up that total
  PRIMARY KEY (day, path)
);

-- The to-do list shown on the admin dashboard. Ticking a box is saved here.
CREATE TABLE IF NOT EXISTS todos (
  key   TEXT    PRIMARY KEY,
  label TEXT    NOT NULL,
  note  TEXT,
  done  INTEGER NOT NULL DEFAULT 0,
  sort  INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO todos (key, label, note, sort) VALUES
 ('domain_buy',   'Buy playtimestats.com at Cloudflare',
  'Dashboard > Domain Registration > Register Domains. About $10-11 a year.', 10),
 ('domain_point', 'Point the domain at the site',
  'Claude does this once the domain is bought.', 20),
 ('roblox_redirect', 'Add https://playtimestats.com/auth/callback to the Roblox app',
  'Creator Dashboard > Credentials > OAuth 2.0 Apps. Needs your Roblox login.', 30),
 ('roblox_review', 'Submit the Roblox app for review',
  'Lifts the 10-user sign-in cap. Needs a demo video under a minute.', 40),
 ('min_samples',  'Set MIN_SAMPLES back to 200',
  'It is lowered while designing so pages appear early.', 50),
 ('noindex_off',  'Let Google list the site (NOINDEX = False)',
  'Do this only once the pages have real data.', 60),
 ('search_console', 'Add the site to Google Search Console',
  'Tells Google the site exists and shows what people search for.', 70),
 ('adsense',      'Apply to AdSense',
  'Needs 20+ pages with real data. Tick the child-directed setting.', 80),
 ('contact_email', 'Set up a contact email for the site',
  'Not your personal address. AdSense expects a way to reach you.', 90);
