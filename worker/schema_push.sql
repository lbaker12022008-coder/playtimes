-- Tables for browser notifications ("tell me when to get on"). Run once:
--   npx wrangler d1 execute playtime-admin --remote --file worker/schema_push.sql
--
-- Offered ONLY to people signed in with Roblox, who are 13 or over by Roblox's own
-- rule. A push subscription is a permanent per-device identifier, so storing one for
-- a visitor who has not signed in would be holding personal data about someone who
-- might be nine years old. That is the whole reason this is behind sign-in, and it is
-- not a detail to relax later.

-- One row per device a person has turned notifications on for. The endpoint IS the
-- identifier the browser's push service gave us; there is nothing else in here that
-- a person did not ask us to keep.
CREATE TABLE IF NOT EXISTS push_subs (
  id       TEXT    PRIMARY KEY,        -- SHA-256 of the endpoint, so re-subscribing the
                                       -- same device replaces its row instead of adding one
  rbx_id   TEXT    NOT NULL,           -- whose device it is
  endpoint TEXT    NOT NULL,           -- where the browser's push service listens
  p256dh   TEXT    NOT NULL,           -- the browser's public key, for encrypting to it
  auth     TEXT    NOT NULL,           -- the browser's shared secret, same purpose
  tz       INTEGER NOT NULL DEFAULT 0, -- hours ahead of UTC, so a message can name a local time
  created  INTEGER NOT NULL,
  fails    INTEGER NOT NULL DEFAULT 0, -- consecutive send failures; the row is dropped at 5
  -- What the push service said last time, and when. `fails` cannot answer the
  -- question that actually comes up - "it said it sent one and nothing appeared" -
  -- because it stays 0 both when the send succeeded and when it was never tried.
  -- 0 means we could not build the message, -1 means the service was unreachable,
  -- anything else is its real HTTP status (201 is a normal success).
  last_status INTEGER,
  last_try    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_push_user ON push_subs (rbx_id);

-- Which games a person wants telling about, and whether they mean quiet or busy.
-- Per person rather than per device, so turning a game on on a phone turns it on
-- everywhere, which is the same promise saved games already make.
CREATE TABLE IF NOT EXISTS push_watch (
  rbx_id  TEXT    NOT NULL,
  slug    TEXT    NOT NULL,            -- the game page, e.g. blox-fruits
  mode    TEXT    NOT NULL,            -- 'quiet' or 'busy'
  lead    INTEGER NOT NULL DEFAULT 15, -- how many minutes before the window to say so
  added   INTEGER NOT NULL,
  PRIMARY KEY (rbx_id, slug)
);

-- What has already been sent, so a run that happens twice, or a cron that fires late,
-- cannot send the same notification again. A slot is one hour of one day in UTC
-- ("2026-11-16T14"), which is exactly as fine-grained as the data is.
--
-- Keyed on the DEVICE, not the person. Keying it on the person looked tidier and was
-- wrong: somebody with a phone and a laptop had the phone claim the hour and the
-- laptop silently skipped, so half their devices never rang. A person with two
-- devices is meant to be told on both, the way every other notification works.
-- rbx_id is kept alongside so that deleting an account can clear these too.
-- Rows older than two days are deleted on every run.
CREATE TABLE IF NOT EXISTS push_sent (
  sub_id TEXT    NOT NULL,          -- which device, matching push_subs.id
  rbx_id TEXT    NOT NULL,
  slug   TEXT    NOT NULL,
  slot   TEXT    NOT NULL,
  at     INTEGER NOT NULL,
  PRIMARY KEY (sub_id, slug, slot)
);
CREATE INDEX IF NOT EXISTS idx_push_sent_user ON push_sent (rbx_id);
CREATE INDEX IF NOT EXISTS idx_push_sent_at ON push_sent (at);
