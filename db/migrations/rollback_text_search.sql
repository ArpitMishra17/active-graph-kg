-- Rollback: Remove full-text search columns and functions
-- Version: 1.0
-- Date: 2025-11-05
--
-- Usage:
--   psql -h localhost -U activekg -d activekg -f db/migrations/rollback_text_search.sql

-- Drop index
DROP INDEX IF EXISTS idx_nodes_text_search;

-- Drop trigger
DROP TRIGGER IF EXISTS nodes_text_search_update ON nodes;

-- Drop function
DROP FUNCTION IF EXISTS update_text_search_vector();

-- Drop column
ALTER TABLE nodes DROP COLUMN IF EXISTS text_search_vector;

-- Verify rollback
DO $$
BEGIN
    RAISE NOTICE 'Rollback complete: text_search_vector column and related objects removed';
END $$;
