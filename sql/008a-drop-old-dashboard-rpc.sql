-- 008a: Drop old get_dashboard_stats function(s)
-- Run this FIRST, then run 008b.
DROP FUNCTION IF EXISTS get_dashboard_stats();
DROP FUNCTION IF EXISTS get_dashboard_stats(INTEGER);
