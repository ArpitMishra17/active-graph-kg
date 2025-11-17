-- Migration: Add performance index for embedding_history queries
-- Date: 2025-11-05
-- Reason: Optimize drift spike detection across all nodes

-- Add index on created_at for fast time-range queries
-- (PRIMARY KEY already covers node_id + created_at for single-node queries)
CREATE INDEX IF NOT EXISTS idx_embedding_history_created_at
ON embedding_history(created_at DESC);

-- Verify index was created
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'embedding_history'
ORDER BY indexname;
