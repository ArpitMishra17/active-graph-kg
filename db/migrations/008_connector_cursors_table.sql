-- Migration: Add connector_cursors table for Drive Changes API cursor persistence
-- Date: 2025-11-12
-- Purpose: Store Drive pageToken cursors for resumable incremental sync per tenant

-- Create connector_cursors table
-- Stores connector sync cursors (e.g., Drive Changes API pageToken) per tenant+provider
CREATE TABLE IF NOT EXISTS connector_cursors (
    tenant_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    cursor TEXT NOT NULL,  -- Drive pageToken, S3 timestamp, etc.
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    PRIMARY KEY (tenant_id, provider)
);

-- Index on provider for efficient filtering by connector type
CREATE INDEX IF NOT EXISTS idx_connector_cursors_provider
ON connector_cursors(provider);

-- Index on tenant_id for fast tenant lookups
CREATE INDEX IF NOT EXISTS idx_connector_cursors_tenant
ON connector_cursors(tenant_id);

-- Index on updated_at for monitoring stale cursors
CREATE INDEX IF NOT EXISTS idx_connector_cursors_updated_at
ON connector_cursors(updated_at DESC);

-- Add trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_connector_cursors_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER connector_cursors_updated_at
    BEFORE UPDATE ON connector_cursors
    FOR EACH ROW
    EXECUTE FUNCTION update_connector_cursors_updated_at();

-- Verify table created
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'connector_cursors'
ORDER BY ordinal_position;

-- Verify indexes created
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'connector_cursors';
