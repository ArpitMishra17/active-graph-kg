-- Migration: Add full-text search for hybrid BM25+vector retrieval
-- Version: 1.0
-- Date: 2025-11-05
--
-- Usage:
--   psql -h localhost -U activekg -d activekg -f db/migrations/add_text_search.sql
--
-- Rollback:
--   psql -h localhost -U activekg -d activekg -f db/migrations/rollback_text_search.sql

-- Add tsvector column for full-text search (PostgreSQL ts_rank, not strictly BM25)
ALTER TABLE nodes
ADD COLUMN IF NOT EXISTS text_search_vector tsvector;

-- Create function to populate text_search_vector from props
CREATE OR REPLACE FUNCTION update_text_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    -- Extract text from props JSONB and convert to tsvector
    -- Weighted: title=A (highest), text=B, metadata=C (lowest)
    NEW.text_search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.props->>'title', '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.props->>'text', '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.metadata::text, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update text_search_vector
DROP TRIGGER IF EXISTS nodes_text_search_update ON nodes;
CREATE TRIGGER nodes_text_search_update
    BEFORE INSERT OR UPDATE OF props, metadata ON nodes
    FOR EACH ROW
    EXECUTE FUNCTION update_text_search_vector();

-- Backfill existing nodes (use direct expression, not trigger function)
UPDATE nodes
SET text_search_vector =
    setweight(to_tsvector('english', COALESCE(props->>'title', '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(props->>'text', '')), 'B') ||
    setweight(to_tsvector('english', COALESCE(metadata::text, '')), 'C')
WHERE text_search_vector IS NULL;

-- Create GIN index for fast text search
CREATE INDEX IF NOT EXISTS idx_nodes_text_search
    ON nodes USING GIN (text_search_vector);

-- Add comment
COMMENT ON COLUMN nodes.text_search_vector IS 'Full-text search vector using PostgreSQL ts_rank (weighted: title=A, text=B, metadata=C)';

-- Verify migration
DO $$
DECLARE
    total_nodes INTEGER;
    indexed_nodes INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_nodes FROM nodes;
    SELECT COUNT(*) INTO indexed_nodes FROM nodes WHERE text_search_vector IS NOT NULL;

    RAISE NOTICE 'Migration complete: % of % nodes have text_search_vector populated', indexed_nodes, total_nodes;

    IF total_nodes > 0 AND indexed_nodes = 0 THEN
        RAISE WARNING 'No nodes were indexed. Check if props contain text/title fields.';
    END IF;
END $$;
