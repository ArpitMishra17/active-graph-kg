-- Migration: Add external_id index for connector deduplication
-- Date: 2025-11-11
-- Purpose: Optimize external_id lookups in connector ingestion

-- Create GIN index on external_id in props JSONB for fast dedup checks
-- This index is critical for IngestionProcessor._get_existing_node()
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nodes_external_id
ON nodes ((props->>'external_id'));

-- Optional: Add composite index for external_id + is_parent for parent node lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nodes_external_id_parent
ON nodes ((props->>'external_id'), (props->>'is_parent'))
WHERE props->>'is_parent' = 'true';

-- Analyze table to update planner statistics
ANALYZE nodes;

-- Verify index created
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'nodes'
  AND indexname IN ('idx_nodes_external_id', 'idx_nodes_external_id_parent');
