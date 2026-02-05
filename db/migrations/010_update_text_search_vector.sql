-- Migration: Update text_search_vector to include resume/job fields
-- Version: 1.0
-- Date: 2026-02-05
--
-- Purpose:
--   Extend BM25/ts_rank search to include resume_text, skills, and job fields
--   for better hybrid search relevance in job/resume matching.
--
-- Usage:
--   psql -h localhost -U activekg -d activekg -f db/migrations/010_update_text_search_vector.sql
--
-- Rollback:
--   Re-run db/migrations/add_text_search.sql to restore original trigger

-- Helper function to extract text from JSONB (handles both string and array)
CREATE OR REPLACE FUNCTION jsonb_text_value(data jsonb, key text)
RETURNS text AS $$
DECLARE
    val jsonb;
BEGIN
    val := data->key;
    IF val IS NULL THEN
        RETURN '';
    ELSIF jsonb_typeof(val) = 'array' THEN
        -- Convert array to comma-separated string
        RETURN array_to_string(ARRAY(SELECT jsonb_array_elements_text(val)), ', ');
    ELSIF jsonb_typeof(val) = 'string' THEN
        RETURN val#>>'{}';
    ELSE
        RETURN val::text;
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Update trigger function to include resume/job fields
CREATE OR REPLACE FUNCTION update_text_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    -- Build text_search_vector with weighted fields:
    -- Weight A (highest): title, job_title, required_skills
    -- Weight B (medium): text, resume_text, good_to_have_skills
    -- Weight C (lowest): metadata
    NEW.text_search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.props->>'title', '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.props->>'job_title', '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(jsonb_text_value(NEW.props, 'required_skills'), '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.props->>'text', '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.props->>'resume_text', '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(jsonb_text_value(NEW.props, 'good_to_have_skills'), '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.metadata::text, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Backfill existing rows that have resume/job fields
-- Direct computation (not UPDATE props=props) to avoid unnecessary row churn
UPDATE nodes
SET text_search_vector =
    setweight(to_tsvector('english', COALESCE(props->>'title', '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(props->>'job_title', '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(jsonb_text_value(props, 'required_skills'), '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(props->>'text', '')), 'B') ||
    setweight(to_tsvector('english', COALESCE(props->>'resume_text', '')), 'B') ||
    setweight(to_tsvector('english', COALESCE(jsonb_text_value(props, 'good_to_have_skills'), '')), 'B') ||
    setweight(to_tsvector('english', COALESCE(metadata::text, '')), 'C')
WHERE
    text_search_vector IS NULL
    OR props ? 'resume_text'
    OR props ? 'required_skills'
    OR props ? 'good_to_have_skills'
    OR props ? 'job_title';

-- Update comment
COMMENT ON COLUMN nodes.text_search_vector IS 'Full-text search vector (weighted: title/job_title/required_skills=A, text/resume_text/good_to_have_skills=B, metadata=C)';

-- Verify migration
DO $$
DECLARE
    total_nodes INTEGER;
    resume_nodes INTEGER;
    job_nodes INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_nodes FROM nodes;
    SELECT COUNT(*) INTO resume_nodes FROM nodes WHERE props ? 'resume_text';
    SELECT COUNT(*) INTO job_nodes FROM nodes WHERE props ? 'job_title';

    RAISE NOTICE 'Migration complete: % total nodes, % with resume_text, % with job_title',
        total_nodes, resume_nodes, job_nodes;
END $$;
