-- ============================================================
-- ⚠️  WARNING: DESTRUCTIVE OPERATION — IRREVERSIBLE  ⚠️
-- ============================================================
-- This script permanently drops legacy tables that have been
-- replaced by the new topic-based segmentation schema
-- (company_topics, company_topic_statuses, topics).
--
-- DO NOT RUN THIS SCRIPT unless you have fully verified that:
--   1. The data migration (006-migrate-data.sql) completed successfully
--   2. All records from company_scores exist in company_topics
--   3. All records from company_statuses exist in company_topic_statuses
--   4. The updated v_companies_full view works correctly
--   5. All frontend views (dashboard, companies, detail, cross-selling)
--      function properly with the new schema
--   6. You have a recent database backup
--
-- These tables will be permanently deleted:
--   - company_tags  (unused)
--   - tags          (unused)
--   - company_scores (migrated to company_topics)
-- ============================================================

DROP TABLE IF EXISTS company_tags CASCADE;
DROP TABLE IF EXISTS tags CASCADE;
DROP TABLE IF EXISTS company_scores CASCADE;
