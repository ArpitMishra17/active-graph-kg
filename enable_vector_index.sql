-- Enable pgvector index for production performance
-- Choose ONE based on your data size:

-- Option 1: IVFFLAT (recommended for <1M vectors)
-- Fast build, good recall, lower memory
CREATE INDEX IF NOT EXISTS idx_nodes_embedding_ivf ON nodes
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Option 2: HNSW (recommended for >1M vectors, pgvector >= 0.7)
-- Slower build, better recall, higher memory
-- CREATE INDEX IF NOT EXISTS idx_nodes_embedding_hnsw ON nodes
--   USING hnsw (embedding vector_cosine_ops)
--   WITH (m = 16, ef_construction = 64);

-- After index creation, analyze for query planner
ANALYZE nodes;

-- Verify index was created
\di idx_nodes_embedding*
