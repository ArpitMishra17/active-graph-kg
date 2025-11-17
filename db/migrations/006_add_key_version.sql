-- Migration 006: Add key versioning for KEK rotation
-- This enables zero-downtime key rotation for connector secrets

-- Add key_version column to track which KEK encrypted each row
ALTER TABLE connector_configs
ADD COLUMN key_version INT NOT NULL DEFAULT 1;

-- Index for rotation queries (find rows needing re-encryption)
CREATE INDEX IF NOT EXISTS idx_connector_configs_key_version
ON connector_configs(key_version);

-- Index for efficient filtering during rotation (provider + version)
CREATE INDEX IF NOT EXISTS idx_connector_configs_provider_key_version
ON connector_configs(provider, key_version);

-- Comments
COMMENT ON COLUMN connector_configs.key_version IS 'KEK version used to encrypt secrets in config_json. Used for key rotation.';
