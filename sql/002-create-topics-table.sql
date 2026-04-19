-- 002: Create `topics` table for business verticals (topic-based segmentation)
-- Supports hierarchical structure via self-referencing parent_id.
-- ON DELETE RESTRICT prevents deleting a parent topic that has children.

-- 1. Create the topics table
CREATE TABLE topics (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    parent_id   INTEGER REFERENCES topics(id) ON DELETE RESTRICT,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- 2. Enable Row Level Security
ALTER TABLE topics ENABLE ROW LEVEL SECURITY;

-- 3. RLS policies: read for all authenticated users, write for service_role only
CREATE POLICY "topics_read" ON topics FOR SELECT USING (true);
CREATE POLICY "topics_write" ON topics FOR ALL USING (auth.role() = 'service_role');
