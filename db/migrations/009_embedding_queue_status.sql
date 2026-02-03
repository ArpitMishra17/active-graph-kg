-- Migration 009: Add embedding queue status tracking columns
-- Date: 2026-02-03
-- Purpose: Track async embedding lifecycle (queued/processing/ready/failed)

ALTER TABLE nodes
ADD COLUMN IF NOT EXISTS embedding_status TEXT NOT NULL DEFAULT 'queued';

ALTER TABLE nodes
ADD COLUMN IF NOT EXISTS embedding_error TEXT;

ALTER TABLE nodes
ADD COLUMN IF NOT EXISTS embedding_attempts INT NOT NULL DEFAULT 0;

ALTER TABLE nodes
ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;

-- Initialize status for existing rows
UPDATE nodes
SET embedding_status = CASE WHEN embedding IS NULL THEN 'queued' ELSE 'ready' END
WHERE embedding_status IS NULL OR embedding_status = '';

UPDATE nodes
SET embedding_updated_at = COALESCE(embedding_updated_at, updated_at, now());

-- Indexes for status monitoring and queue visibility
CREATE INDEX IF NOT EXISTS idx_nodes_embedding_status ON nodes(embedding_status);
CREATE INDEX IF NOT EXISTS idx_nodes_embedding_updated_at ON nodes(embedding_updated_at);
