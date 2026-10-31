-- Tables for the admin dashboard. Run once:
--   npx wrangler d1 execute playtime-admin --remote --file worker/schema.sql
CREATE TABLE IF NOT EXISTS views (
  day  TEXT    NOT NULL,          -- YYYY-MM-DD (UTC)
  path TEXT    NOT NULL,          -- page address, e.g. /game/blox-fruits.html
  n    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, path)
);

-- Only used to slow down someone guessing the admin code.
-- ip_hash is one-way and salted; rows are deleted after 24 hours.
CREATE TABLE IF NOT EXISTS login_attempts (
  ip_hash TEXT    NOT NULL,
  ts      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_ip ON login_attempts (ip_hash, ts);
