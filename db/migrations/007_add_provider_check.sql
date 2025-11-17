-- Migration 007: Add provider validation constraint
-- Date: 2025-11-11
-- Purpose: Prevent typos in provider names (optional constraint - can be removed for extensibility)

-- Add CHECK constraint to validate provider names
-- Comment: This helps catch typos early. Remove if you need to support arbitrary provider names.
ALTER TABLE connector_configs
ADD CONSTRAINT chk_provider_valid
CHECK (provider IN ('s3', 'gcs', 'azure', 'postgres', 'mysql', 'redis'));

-- Add comment explaining the constraint
COMMENT ON CONSTRAINT chk_provider_valid ON connector_configs IS
'Validates provider names to prevent typos. Supported: s3, gcs, azure, postgres, mysql, redis. Remove constraint if custom providers needed.';
