-- 007: Update v_companies_full to JOIN on company_topics instead of company_scores
-- The view now exposes topic-specific columns so the frontend can filter by topic_id.
-- Requirements: 8.5, 9.4

-- 1. Drop the existing view (currently joins on company_scores)
DROP VIEW IF EXISTS v_companies_full;

-- 2. Recreate with LEFT JOIN on company_topics
CREATE OR REPLACE VIEW v_companies_full AS
SELECT
    c.id,
    c.vat_number,
    c.name,
    c.ateco_code,
    c.region,
    c.county,
    c.city,
    c.address,
    c.notes,
    c.crm_status,
    c.starred,
    c.created_at,
    c.updated_at,
    c.employees_min,
    c.employees_max,
    c.state_id,
    c.latest_revenue,
    c.latest_profit,
    c.latest_personnel_cost,
    c.founding_date,
    ct.topic_id,
    ct.crm_status        AS topic_crm_status,
    ct.score             AS relevance_score,
    ct.confidence        AS relevance_confidence,
    ct.scored_at,
    (SELECT count(*) FROM company_data cd WHERE cd.company_id = c.id) AS data_count
FROM companies c
LEFT JOIN company_topics ct ON ct.company_id = c.id;
