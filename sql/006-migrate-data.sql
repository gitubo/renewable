-- 006-migrate-data.sql
-- Migrates existing data into the new topic-based structure.
-- Idempotent: safe to run multiple times (ON CONFLICT DO NOTHING).

BEGIN;

-- 1. Insert initial topics
INSERT INTO topics (name, parent_id, description) VALUES
    ('Bioenergy', NULL, 'Bioenergia')
ON CONFLICT (name) DO NOTHING;

INSERT INTO topics (name, parent_id, description) VALUES
    ('Feedstock Optimization',
     (SELECT id FROM topics WHERE name = 'Bioenergy'),
     'Ottimizzazione feedstock')
ON CONFLICT (name) DO NOTHING;

INSERT INTO topics (name, parent_id, description) VALUES
    ('Photovoltaic', NULL, 'Fotovoltaico')
ON CONFLICT (name) DO NOTHING;

-- 2. Migrate company_scores → company_topics (Feedstock Optimization)
INSERT INTO company_topics (company_id, topic_id, crm_status, score, confidence, reasoning, model_used, scored_at)
SELECT
    cs.company_id,
    (SELECT id FROM topics WHERE name = 'Feedstock Optimization'),
    COALESCE(c.crm_status, 'new'),
    cs.score,
    cs.confidence,
    cs.reasoning,
    cs.model_used,
    cs.scored_at
FROM company_scores cs
JOIN companies c ON c.id = cs.company_id
ON CONFLICT (company_id, topic_id) DO NOTHING;

-- 3. Migrate status history → company_topic_statuses
INSERT INTO company_topic_statuses (company_topic_id, status_id, note, created_at)
SELECT
    ct.id,
    cs.status_id,
    cs.note,
    cs.created_at
FROM company_statuses cs
JOIN company_topics ct ON ct.company_id = cs.company_id
    AND ct.topic_id = (SELECT id FROM topics WHERE name = 'Feedstock Optimization')
ON CONFLICT DO NOTHING;

COMMIT;
