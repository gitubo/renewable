-- 001: Drop legacy `employees` TEXT column from companies
-- The column is replaced by employees_min / employees_max (integer range).
-- The view v_companies_full must be dropped first because it references `employees`.

-- 1. Drop the view that depends on the column
DROP VIEW IF EXISTS v_companies_full;

-- 2. Drop the column
ALTER TABLE companies DROP COLUMN IF EXISTS employees;

-- 3. Recreate the view without `employees`, keeping the same LEFT JOIN on company_scores
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
    cs.score       AS relevance_score,
    cs.confidence  AS relevance_confidence,
    (SELECT count(*) FROM company_data cd WHERE cd.company_id = c.id) AS data_count
FROM companies c
LEFT JOIN company_scores cs ON cs.company_id = c.id;
