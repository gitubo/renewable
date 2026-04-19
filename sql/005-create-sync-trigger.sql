-- 005: Create sync trigger to keep companies.crm_status in sync with company_topics.
-- When a company_topics row is inserted or its crm_status is updated,
-- the corresponding companies.crm_status and updated_at are updated automatically.
-- This maintains backward compatibility (Requirement 9.3).

-- 1. Create the trigger function
CREATE OR REPLACE FUNCTION sync_company_crm_status() RETURNS TRIGGER AS $$
BEGIN
    UPDATE companies SET crm_status = NEW.crm_status, updated_at = now()
    WHERE id = NEW.company_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. Create the trigger on company_topics
CREATE TRIGGER trg_sync_crm_status
AFTER INSERT OR UPDATE OF crm_status ON company_topics
FOR EACH ROW EXECUTE FUNCTION sync_company_crm_status();
