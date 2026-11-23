-- Whether the back end is actually working. Run once:
--   npx wrangler d1 execute playtime-admin --remote --file worker/schema_ops.sql
--
-- Collecting and building happen in GitHub Actions, not in this worker, so until now
-- nothing on the dashboard could say whether either had run. The repo is public, so
-- GitHub's API answers without a token - but it only serves the most recent 100 runs
-- of a workflow, and `collect` runs 48 times a day, so that is about two days of
-- history. Anything longer has to be kept here.
--
-- Three further reasons this is a table and not a live fetch per page load:
--   * unauthenticated GitHub allows 60 requests an hour PER IP, and a Worker's egress
--     IPs are shared with every other Cloudflare customer, so the budget is not ours
--     alone and must not be spent on page loads;
--   * the Cache API is per data centre, so a cached copy warmed by the cron is not
--     the copy a dashboard in another city would read. D1 is one database everywhere;
--   * a run that is still going gets written again when it finishes, which needs a
--     row to update rather than a response to re-read.
CREATE TABLE IF NOT EXISTS ops_runs (
  id      INTEGER PRIMARY KEY,      -- GitHub's own run id, so syncing twice is harmless
  wf      TEXT    NOT NULL,         -- collect | build | discover | staging
  run_no  INTEGER,
  -- 1 success, 0 failed or cancelled, NULL still running. Three states, not two:
  -- "no answer yet" must never be drawn as a failure.
  ok      INTEGER,
  concl   TEXT,                     -- GitHub's own word, kept so a cancelled run can be told from a broken one
  started INTEGER NOT NULL,         -- unix seconds
  ended   INTEGER,
  secs    INTEGER,                  -- how long it took, once it has finished
  event   TEXT                      -- schedule | push | workflow_dispatch
);
CREATE INDEX IF NOT EXISTS idx_ops_wf ON ops_runs (wf, started);

-- Small named values the dashboard needs but that are not worth a table each:
-- GitHub's all-time run and failure counts, when each sync last succeeded, and
-- later the Search Console cursor. `at` is when it was written, so the dashboard
-- can say how old a number is instead of implying it is live.
CREATE TABLE IF NOT EXISTS admin_meta (
  k  TEXT    PRIMARY KEY,
  v  TEXT,
  at INTEGER NOT NULL
);
