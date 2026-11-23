-- Indexes for the admin dashboard's analytics queries. Safe to run again.
--   npx wrangler d1 execute playtime-admin --remote --file worker/schema_index.sql
--
-- `views` and `dwell` are both PRIMARY KEY (day, path), so "WHERE day >= ?" already
-- rides the primary key. What had nothing behind it was the other direction:
--
--   * the per-page panel runs a correlated subquery per path
--     ("SELECT SUM(seconds) FROM dwell WHERE path = ? AND day >= ?"), which was a
--     full scan of dwell for every page in the list;
--   * every "WHERE path LIKE '/game/%'" aggregate scans the whole table.
--
-- path first, then day: that order serves both an exact path with a date range and
-- a prefix match, while (day, path) cannot serve a path lookup at all.
CREATE INDEX IF NOT EXISTS idx_dwell_path ON dwell (path, day);
CREATE INDEX IF NOT EXISTS idx_views_path ON views (path, day);
