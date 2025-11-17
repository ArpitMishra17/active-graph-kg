-- Migration: Add connector_configs table for persistent connector configuration
-- Date: 2025-11-11
-- Purpose: Replace in-memory connector config storage with encrypted DB persistence

-- Create connector_configs table
-- Stores connector configurations per tenant with encrypted secrets
CREATE TABLE IF NOT EXISTS connector_configs (
    tenant_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    config_json JSONB NOT NULL,  -- Encrypted secrets stored here
    enabled BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    PRIMARY KEY (tenant_id, provider)
);

-- Index on enabled for efficient filtering of active connectors
CREATE INDEX IF NOT EXISTS idx_connector_configs_enabled
ON connector_configs(enabled);

-- Index on tenant_id for fast tenant lookups
CREATE INDEX IF NOT EXISTS idx_connector_configs_tenant
ON connector_configs(tenant_id);

-- Add trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_connector_configs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER connector_configs_updated_at
    BEFORE UPDATE ON connector_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_connector_configs_updated_at();

-- Verify table created
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'connector_configs'
ORDER BY ordinal_position;

-- Verify indexes created
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'connector_configs';
