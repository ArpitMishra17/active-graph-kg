-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Nodes table
CREATE TABLE IF NOT EXISTS nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT,
  classes TEXT[] NOT NULL DEFAULT '{}',
  props JSONB NOT NULL DEFAULT '{}',
  payload_ref TEXT,
  embedding VECTOR(384),
  embedding_status TEXT NOT NULL DEFAULT 'queued',
  embedding_error TEXT,
  embedding_attempts INT NOT NULL DEFAULT 0,
  embedding_updated_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}',
  refresh_policy JSONB NOT NULL DEFAULT '{}',
  triggers JSONB NOT NULL DEFAULT '[]',
  version INT NOT NULL DEFAULT 1,
  -- Active refresh fields (explicit, queryable)
  last_refreshed TIMESTAMPTZ,
  drift_score DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Edges table
-- Lineage Strategy: Use edges with rel='DERIVED_FROM' to model provenance.
-- Why edges vs JSONB: Enables recursive graph queries, standardizes traversal,
-- and allows props to capture derivation metadata (transform, confidence, timestamp).
CREATE TABLE IF NOT EXISTS edges (
  src UUID NOT NULL,
  rel TEXT NOT NULL,
  dst UUID NOT NULL,
  props JSONB NOT NULL DEFAULT '{}',
  tenant_id TEXT,  -- For multi-tenant isolation via RLS
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (src, rel, dst)
);

-- Node versions
CREATE TABLE IF NOT EXISTS node_versions (
  node_id UUID NOT NULL,
  version INT NOT NULL,
  snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (node_id, version)
);

-- Events
CREATE TABLE IF NOT EXISTS events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id UUID,
  type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  tenant_id TEXT,  -- For multi-tenant isolation via RLS
  actor_id TEXT,   -- Who triggered this event (user, api_key, scheduler, trigger)
  actor_type TEXT, -- Type of actor: 'user', 'api_key', 'scheduler', 'trigger', 'system'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Optional embedding history
CREATE TABLE IF NOT EXISTS embedding_history (
  node_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  drift_score DOUBLE PRECISION,
  embedding_ref TEXT,
  PRIMARY KEY (node_id, created_at)
);

-- Trigger patterns
CREATE TABLE IF NOT EXISTS patterns (
  name TEXT PRIMARY KEY,
  embedding VECTOR(384) NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_nodes_tenant ON nodes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_nodes_classes ON nodes USING GIN (classes);
CREATE INDEX IF NOT EXISTS idx_nodes_props ON nodes USING GIN (props);
CREATE INDEX IF NOT EXISTS idx_nodes_metadata ON nodes USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_nodes_triggers ON nodes USING GIN (triggers);
CREATE INDEX IF NOT EXISTS idx_nodes_last_refreshed ON nodes(last_refreshed);
CREATE INDEX IF NOT EXISTS idx_nodes_drift_score ON nodes(drift_score) WHERE drift_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_nodes_embedding_status ON nodes(embedding_status);
CREATE INDEX IF NOT EXISTS idx_nodes_embedding_updated_at ON nodes(embedding_updated_at);

-- Edge indexes for lineage traversal
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src, rel);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst, rel);
CREATE INDEX IF NOT EXISTS idx_edges_lineage ON edges(dst, rel) WHERE rel = 'DERIVED_FROM';
CREATE INDEX IF NOT EXISTS idx_edges_tenant ON edges(tenant_id);

-- Vector index (choose IVFFLAT/HNSW depending on pgvector version)
-- For IVFFLAT (recommended for <1M vectors):
-- CREATE INDEX IF NOT EXISTS idx_nodes_embedding_ivf ON nodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- For HNSW (pgvector >= 0.7, better for reads):
-- CREATE INDEX IF NOT EXISTS idx_nodes_embedding_hnsw ON nodes USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Event indexes
CREATE INDEX IF NOT EXISTS idx_events_node_id ON events(node_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_tenant ON events(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id, created_at DESC);

-- Embedding history indexes (note: PRIMARY KEY (node_id, created_at) already creates composite index)
-- Additional index on created_at for cross-node drift spike detection
CREATE INDEX IF NOT EXISTS idx_embedding_history_created_at ON embedding_history(created_at DESC);
