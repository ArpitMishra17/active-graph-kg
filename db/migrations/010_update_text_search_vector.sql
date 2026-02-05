-- Migration: Update text_search_vector to minimal resume/job fields
-- Version: 1.0
-- Date: 2026-02-05
--
-- Purpose:
--   Keep BM25/ts_rank focused on high-signal fields only:
--   title/job_title and main text (text/resume_text), plus metadata.
--
-- Usage:
--   psql -h localhost -U activekg -d activekg -f db/migrations/010_update_text_search_vector.sql
--
-- Rollback:
--   Re-run db/migrations/add_text_search.sql to restore original trigger

-- Update trigger function to include minimal resume/job fields
CREATE OR REPLACE FUNCTION update_text_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    -- Build text_search_vector with minimal weighted fields:
    -- Weight A (highest): title/job_title/current_title
    -- Weight B (medium): text/resume_text
    -- Weight C (lowest): metadata
    NEW.text_search_vector :=
        setweight(
            to_tsvector(
                'english',
                COALESCE(NEW.props->>'title', NEW.props->>'job_title', NEW.props->>'current_title', '')
            ),
            'A'
        ) ||
        setweight(
            to_tsvector(
                'english',
                COALESCE(NEW.props->>'text', NEW.props->>'resume_text', '')
            ),
            'B'
        ) ||
        setweight(to_tsvector('english', COALESCE(NEW.metadata::text, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Backfill existing rows for minimal fields
-- Direct computation (not UPDATE props=props) to avoid unnecessary row churn
UPDATE nodes
SET text_search_vector =
    setweight(
        to_tsvector(
            'english',
            COALESCE(props->>'title', props->>'job_title', props->>'current_title', '')
        ),
        'A'
    ) ||
    setweight(
        to_tsvector(
            'english',
            COALESCE(props->>'text', props->>'resume_text', '')
        ),
        'B'
    ) ||
    setweight(to_tsvector('english', COALESCE(metadata::text, '')), 'C')
WHERE
    text_search_vector IS NULL
    OR props ? 'resume_text'
    OR props ? 'text'
    OR props ? 'job_title'
    OR props ? 'title'
    OR props ? 'current_title';

-- Update comment
COMMENT ON COLUMN nodes.text_search_vector IS 'Full-text search vector (weighted: title/job_title/current_title=A, text/resume_text=B, metadata=C)';

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
