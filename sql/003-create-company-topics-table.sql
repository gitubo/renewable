-- 003: Create `company_topics` table for company-topic associations.
-- Each company can be linked to multiple topics with independent CRM status and scoring.
-- ON DELETE CASCADE on company_id: removing a company removes all its topic associations.
-- ON DELETE RESTRICT on topic_id: prevents deleting a topic that has company associations.
-- UNIQUE(company_id, topic_id) ensures one association per company-topic pair.

-- 1. Create the company_topics table
CREATE TABLE company_topics (
    id          SERIAL PRIMARY KEY,
    company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    topic_id    INTEGER NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    crm_status  TEXT NOT NULL DEFAULT 'new',
    score       INTEGER,
    confidence  NUMERIC,
    reasoning   TEXT,
    model_used  TEXT,
    scored_at   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, topic_id)
);

-- 2. Enable Row Level Security
ALTER TABLE company_topics ENABLE ROW LEVEL SECURITY;

-- 3. RLS policy: full access for authenticated and service_role users
CREATE POLICY "ct_all" ON company_topics FOR ALL USING (auth.role() IN ('authenticated', 'service_role'));
