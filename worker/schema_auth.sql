-- Tables for "Sign in with Roblox" and saved games. Run once:
--   npx wrangler d1 execute playtime-admin --remote --file worker/schema_auth.sql
--
-- Only what the feature needs: who you are on Roblox, and which games you saved.
-- No email, no password, no age, no browsing history.
CREATE TABLE IF NOT EXISTS users (
  rbx_id  TEXT PRIMARY KEY,     -- Roblox user ID
  name    TEXT,                 -- Roblox display name, shown back to them
  created INTEGER NOT NULL,
  seen    INTEGER NOT NULL      -- last sign-in, so stale accounts can be cleared later
);

CREATE TABLE IF NOT EXISTS favourites (
  rbx_id TEXT    NOT NULL,
  slug   TEXT    NOT NULL,      -- the game page, e.g. blox-fruits
  added  INTEGER NOT NULL,
  PRIMARY KEY (rbx_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_fav_user ON favourites (rbx_id, added);
