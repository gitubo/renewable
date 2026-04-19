-- 004: Create `company_topic_statuses` table for tracking CRM status history per company-topic pair.
-- Each record represents a status change event with optional note.
-- ON DELETE CASCADE on company_topic_id: removing an association removes its status history.
-- FK to statuses(id) ensures only valid statuses can be recorded.

-- 1. Create the company_topic_statuses table
CREATE TABLE company_topic_statuses (
    id                SERIAL PRIMARY KEY,
    company_topic_id  INTEGER NOT NULL REFERENCES company_topics(id) ON DELETE CASCADE,
    status_id         INTEGER NOT NULL REFERENCES statuses(id),
    note              TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);

-- 2. Enable Row Level Security
ALTER TABLE company_topic_statuses ENABLE ROW LEVEL SECURITY;

-- 3. RLS policy: full access for authenticated and service_role users
CREATE POLICY "cts_all" ON company_topic_statuses FOR ALL USING (auth.role() IN ('authenticated', 'service_role'));
