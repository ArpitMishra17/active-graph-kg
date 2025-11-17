# Active Graph KG - Production Optimization & Tuning Guide

**Complete implementation guide for content quality, retrieval optimization, and end-to-end reliability**

Version: 1.0  
Last Updated: 2025-11-09  
Status: ✅ Implemented

---

## Table of Contents

1. [Overview](#overview)
2. [Phase 1: Seed & Coverage](#phase-1-seed--coverage)
3. [Phase 2: Retrieval Tuning](#phase-2-retrieval-tuning)
4. [Phase 3: LLM Prompt & Routing](#phase-3-llm-prompt--routing)
5. [Phase 4: Observability & Guardrails](#phase-4-observability--guardrails)
6. [Phase 5: E2E & Evaluation](#phase-5-e2e--evaluation)
7. [Phase 6: CI/CD Integration](#phase-6-cicd-integration)
8. [Phase 7: Production Hardening](#phase-7-production-hardening)
9. [Success Criteria](#success-criteria)
10. [Troubleshooting](#troubleshooting)

---

## Overview

### Objectives

- **Achieve strong retrieval + citation accuracy** for evaluation questions
- **Keep latency within targets** and ensure reliability under load
- **Bake confidence into CI** so regressions are caught early

### Implementation Status

| Phase | Status | Files |
|-------|--------|-------|
| Phase 1: Seed & Coverage | ✅ Complete | `evaluation/datasets/seed_with_jwt.py` |
| Phase 2: Retrieval Tuning | ✅ Complete | `.env.eval` |
| Phase 3: LLM Prompt & Routing | ✅ Complete | `activekg/engine/llm_provider.py` |
| Phase 4: Observability | ✅ Complete | `activekg/api/main.py` (debug endpoints) |
| Phase 5: E2E & Evaluation | ✅ Complete | `tests/test_e2e_retrieval.py`, `scripts/e2e_api_smoke.py` |
| Phase 6: CI/CD Integration | ✅ Complete | `.github/workflows/ci.yml` |
| Phase 7: Production Hardening | ✅ Complete | This document |

---

## Phase 1: Seed & Coverage (Data Quality)

### Objective

Curate seed nodes so each evaluation question maps to ≥1 node with rich, unambiguous content.

### Implementation

#### 1.1 Seed Dataset

**File**: `evaluation/datasets/seed_nodes.json`

**Content Requirements**:
- ✅ Each node has rich `text` field (title + summary + key facts)
- ✅ Synonyms/keywords in metadata (e.g., "spring-boot", "observability", "vector-database")
- ✅ External IDs for ground truth mapping
- ✅ Coverage for all 6 evaluation questions

**Example Node Structure**:
```json
{
  "external_id": "resume_java_1",
  "classes": ["Resume", "Profile"],
  "text": "Sarah Chen - Senior Java Engineer. 10+ years of Java development...",
  "props": {
    "name": "Sarah Chen",
    "title": "Senior Java Engineer",
    "summary": "10+ years of Java development experience..."
  },
  "metadata": {
    "skills": ["java", "spring-boot", "hibernate"],
    "level": "senior",
    "topic": "java-developer"
  }
}
```

#### 1.2 Seed Script

**File**: `evaluation/datasets/seed_with_jwt.py`

**Features**:
- ✅ JWT authentication
- ✅ Idempotent seeding via external_id
- ✅ Admin refresh to populate embeddings
- ✅ Coverage verification via `/debug/search_sanity`
- ✅ Retrieval validation against ground truth

**Usage**:
```bash
# Load environment from .env.eval
set -a; source .env.eval; set +a

# Run seeding
python3 evaluation/datasets/seed_with_jwt.py

# Verify coverage only (no seeding)
python3 evaluation/datasets/seed_with_jwt.py --verify-only
```

#### 1.3 Post-Seeding Verification

**Required Actions**:

1. **Admin refresh** to populate embeddings:
   ```bash
   curl -X POST http://localhost:8000/admin/refresh \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '["node_id_1", "node_id_2", ...]'
   ```

2. **Re-run text search migration** if `text_search_vector` not populated:
   ```bash
   psql $ACTIVEKG_DSN -f db/migrations/add_text_search.sql
   ```

3. **Verify via `/debug/search_sanity`** (admin scope required):
   ```bash
   curl http://localhost:8000/debug/search_sanity \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

**Target Metrics**:
- ✅ Embedding coverage ≥ 95%
- ✅ Text search coverage = 100%
- ✅ Sample nodes show `has_text=true`

---

## Phase 2: Retrieval Tuning

### Objective

Optimize search parameters for high recall while maintaining precision.

### Implementation

#### 2.1 Configuration File

**File**: `.env.eval`

**Key Settings**:

```bash
# Retrieval Thresholds (Optimized for high recall)
ASK_SIM_THRESHOLD=0.20              # Lower threshold for more candidates
ASK_MAX_SNIPPETS=5                  # More context for LLM
ASK_SNIPPET_LEN=500                 # Longer snippets
HYBRID_RERANKER_CANDIDATES=50       # Larger candidate pool

# Hybrid Search & Routing
HYBRID_ROUTING_ENABLED=true         # Enable hybrid routing
ASK_USE_RERANKER=true               # Enable cross-encoder reranking

# LLM Configuration
GROQ_API_KEY=gsk_...                # Fast model for evaluation
ASK_FAST_MODEL=llama-3.1-70b-versatile
ASK_FALLBACK_MODEL=llama-3.1-8b-instant
ASK_FALLBACK_BACKEND=groq

# Token Budgets
ASK_FAST_MAX_TOKENS=200             # Moderate budget for fast model
ASK_FALLBACK_MAX_TOKENS=400         # Higher budget for complex queries

# Caching
ASK_CACHE_TTL=0                     # Disable during tuning

# Rate Limiting (Relaxed for CI/eval)
RATE_LIMIT_SEARCH_RATE=1000
RATE_LIMIT_SEARCH_BURST=2000
RATE_LIMIT_ASK_RATE=100
RATE_LIMIT_ASK_BURST=200

# Concurrency
CONCURRENCY_ASK=20                  # Higher concurrency for eval
CONCURRENCY_ASK_STREAM=10
```

#### 2.2 Validation Steps

1. **Vector-only search** returns >0 results:
   ```bash
   curl -X POST http://localhost:8000/search \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"query": "python developer", "use_hybrid": false, "top_k": 10}'
   ```

2. **Hybrid search** returns >0 results:
   ```bash
   curl -X POST http://localhost:8000/search \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"query": "python developer", "use_hybrid": true, "top_k": 10}'
   ```

3. **Fallback mechanism** engaged when hybrid returns empty:
   - Check logs for `"fallback_to_vector": true`
   - `/ask` endpoint automatically falls back to vector-only

#### 2.3 Tuning Workflow

If recall remains low for specific queries:

1. **Check embedding coverage**: Use `/debug/search_sanity`
2. **Verify text content**: Ensure `props.text` is populated
3. **Adjust similarity threshold**: Lower `ASK_SIM_THRESHOLD` (min: 0.15)
4. **Increase candidate pool**: Raise `HYBRID_RERANKER_CANDIDATES` (max: 100)
5. **Iterate on content**: Add synonyms to metadata, enrich props.text

---

## Phase 3: LLM Prompt & Routing

### Objective

Ensure strict citation enforcement and optimal model routing for accuracy and speed.

### Implementation

#### 3.1 Strict Citation Prompt

**File**: `activekg/engine/llm_provider.py:439`

**Citation Rules** (already implemented):
```
1. ALWAYS cite sources using [0], [1], [2] format for EVERY factual claim
2. ONLY cite the highest-similarity contexts that directly support your claim
3. Prefer citing [0] over [1], [1] over [2], etc. (higher similarity = more relevant)
4. If multiple sources equally support a claim, cite all [0][1]
```

**Accuracy Rules**:
```
5. Answer directly based on the context provided
6. If context is insufficient or ambiguous, say "I don't have enough information"
7. Never make assumptions or add information not in the context
8. Be concise and specific - focus on answering the question
```

**Examples Included**: ✅ 2 examples showing proper citation format

#### 3.2 Token Budgets

**Configuration**:
- `ASK_FAST_MAX_TOKENS=200` (fast model: llama-3.1-70b)
- `ASK_FALLBACK_MAX_TOKENS=400` (fallback model: llama-3.1-8b or gpt-4o-mini)

**Routing Logic** (`activekg/engine/llm_provider.py`):
```python
if hybrid_routing_enabled:
    if top_similarity >= ASK_ROUTER_TOPSIM (0.70):
        use fast_model
    elif confidence < ASK_ROUTER_MINCONF (0.60):
        use fallback_model
    else:
        use fast_model
```

#### 3.3 Cache Configuration

**During Tuning**: `ASK_CACHE_TTL=0` (disabled)  
**Production**: `ASK_CACHE_TTL=600` (10 minutes)

**Cache Key**: `(tenant_id, question, max_results)`

---

## Phase 4: Observability & Guardrails

### Objective

Monitor system health, search coverage, and tenant context via debug endpoints.

### Implementation

#### 4.1 Debug Endpoints

##### `/debug/dbinfo` (Admin)

**Purpose**: Verify database connection and tenant context

**Security**: Requires `admin:refresh` scope

**Response**:
```json
{
  "database": "activekg",
  "tenant_context": "eval_tenant",
  "server_host": "10.0.1.45",
  "server_port": 5432
}
```

**Usage**:
```bash
curl http://localhost:8000/debug/dbinfo \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

##### `/debug/search_sanity` (Admin)

**Purpose**: Monitor embedding coverage, text search population, and sample nodes

**Security**: Requires `admin:refresh` scope

**Response**:
```json
{
  "tenant_id": "eval_tenant",
  "total_nodes": 12,
  "nodes_with_embeddings": 12,
  "nodes_with_text_search": 12,
  "embedding_coverage_pct": 100.0,
  "text_search_coverage_pct": 100.0,
  "sample_nodes_with_embedding": [
    {"id": "uuid", "classes": ["Resume"], "has_text": true}
  ],
  "sample_nodes_without_embedding": []
}
```

**Usage**:
```bash
curl http://localhost:8000/debug/search_sanity \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

#### 4.2 Rate Limit Headers

**All endpoints** include rate limit headers:
- `X-RateLimit-Limit`: Requests allowed per window
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Unix timestamp when limit resets

#### 4.3 Logging & Debugging

**Enable RLS debugging**:
```bash
export ACTIVEKG_DEBUG_RLS=true
```

**Watch logs for**:
- `"RLS context set"`: Confirms tenant_id applied
- `"result_count"`: Vector/hybrid search result counts
- `"fallback_to_vector"`: Hybrid fallback usage

---

## Phase 5: E2E & Evaluation

### Objective

Validate end-to-end functionality with comprehensive test suite and evaluation harness.

### Implementation

#### 5.1 E2E Smoke Test

**File**: `scripts/e2e_api_smoke.py`

**Coverage**:
- Health check
- Node creation (tenant-scoped)
- Admin refresh
- Vector search
- Hybrid search
- `/ask` endpoint (with LLM)
- Events endpoint
- Node versions
- Triggers (register, list, delete)

**Usage**:
```bash
export API_URL=http://localhost:8000
export TENANT=eval_tenant
export JWT_SECRET=test-secret-key-min-32-chars-long
python3 scripts/e2e_api_smoke.py
```

#### 5.2 E2E Retrieval Tests

**File**: `tests/test_e2e_retrieval.py`

**Test Coverage**:
1. ✅ `test_vector_search_returns_results`: Vector-only search
2. ✅ `test_hybrid_search_returns_results`: Hybrid search
3. ✅ `test_ask_includes_citations`: Citation presence validation
4. ✅ `test_search_sanity_endpoint`: Debug endpoint shape
5. ✅ `test_search_modes` (parametrized): Both search modes

**Usage**:
```bash
pytest tests/test_e2e_retrieval.py -v
```

#### 5.3 Evaluation Harness

**File**: `evaluation/run_all.sh`

**Dimensions**:
1. **Latency Benchmark** (`latency_benchmark.py`)
   - p50, p95, p99 percentiles per endpoint
   - SLA compliance: <100ms (/search), <2s (/ask)

2. **Weighted Search Eval** (`weighted_search_eval.py`)
   - Recall@10, MRR, NDCG
   - Age decay + drift penalty impact

3. **Drift Cohort Analysis** (`drift_cohort_analysis.py`)
   - Before/after embedding comparison
   - High-drift node identification

4. **Freshness Monitor** (`freshness_monitor.py`)
   - SLA compliance (on-time, at-risk, overdue)
   - Refresh policy adherence

5. **LLM Q&A Eval** (`llm_qa_eval.py`)
   - Answer accuracy (ROUGE-L)
   - Citation precision/recall
   - Latency p95

**Usage**:
```bash
set -a; source .env.eval; set +a
bash evaluation/run_all.sh
```

---

## Phase 6: CI/CD Integration

### Objective

Automated testing pipeline with pass/fail gates for retrieval accuracy and latency.

### Implementation

#### 6.1 Pipeline Configuration

**File**: `.github/workflows/ci.yml`

**Jobs**:
1. **Lint**: Ruff + mypy type checking
2. **Unit Tests**: pytest on test_phase1_*.py files
3. **Integration Tests**: Full E2E with PostgreSQL + Redis
4. **Benchmarks**: Latency benchmarks (main branch only)
5. **Security**: Safety + Bandit scanning
6. **Build Summary**: Aggregate status

#### 6.2 Integration Test Steps

```yaml
1. Start PostgreSQL (pgvector) + Redis services
2. Initialize DB schema (init.sql, RLS policies, text search)
3. Start API server in background
4. Seed evaluation dataset (seed_with_jwt.py)
5. Run E2E retrieval tests (test_e2e_retrieval.py)
6. Run E2E smoke test (e2e_api_smoke.py)
7. Verify search coverage (--verify-only)
```

#### 6.3 Pass/Fail Criteria

**Required for Green Build**:
- ✅ `/search` vector-only + hybrid return results for seeded queries
- ✅ `/ask` citation presence ≥ 80% when context available
- ✅ Latency p95 within target (<100ms search; <2s ask)
- ✅ No 401/429 in auth/liveness tests (with relaxed limits)

#### 6.4 Secrets Configuration

**GitHub Secrets** (for production CI):
- `GROQ_API_KEY`: For LLM evaluation tests
- `POSTGRES_PASSWORD`: For managed DB
- `REDIS_URL`: For rate limiting

**Dev CI** (this implementation):
- Uses service containers (no secrets needed)
- LLM tests skipped (503 handled gracefully)

---

## Phase 7: Production Hardening

### Objective

Secure, scalable, and reliable deployment configuration.

### Implementation

#### 7.1 JWT Authentication

**Configuration**:
```bash
# Production (RS256 with public key)
JWT_ENABLED=true
JWT_SECRET_KEY=<RS256-public-key-PEM>
JWT_ALGORITHM=RS256
JWT_AUDIENCE=activekg
JWT_ISSUER=https://auth.yourcompany.com

# Development (HS256 with shared secret)
JWT_ENABLED=true
JWT_SECRET_KEY=dev-secret-key-min-32-chars-long
JWT_ALGORITHM=HS256
```

**Key Rotation**:
- Store keys in environment variables (never commit)
- Use key management service (AWS KMS, Azure Key Vault)
- Rotate keys every 90 days
- Support multiple valid public keys during rotation window

#### 7.2 Redis Configuration

**Persistence** (AOF - Append-Only File):
```bash
# redis.conf
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

**Health Alerts**:
- Monitor Redis memory usage (< 80% capacity)
- Alert on connection failures (impacts rate limiting)
- Track rate limit hit rate (high = need capacity increase)

**Deployment**:
- Single Redis instance for dev
- Redis Sentinel for HA in production
- Redis Cluster for high throughput (>100K req/s)

#### 7.3 Scheduler Configuration

**Single Instance Constraint**:
```bash
# Only ONE worker should run scheduler
RUN_SCHEDULER=true   # On dedicated scheduler instance
RUN_SCHEDULER=false  # On all API worker instances
```

**Multi-Worker Deployments**:
- Deploy scheduler as separate service (e.g., systemd, Kubernetes CronJob)
- Or use external scheduler (Airflow, Temporal, Prefect)
- Ensure only one scheduler runs per tenant/database

#### 7.4 Database Indexes

**Post-Ingest Maintenance**:
```sql
-- Rebuild statistics
VACUUM ANALYZE nodes;
VACUUM ANALYZE edges;
VACUUM ANALYZE events;

-- Rebuild vector index (if needed)
REINDEX INDEX CONCURRENTLY idx_nodes_embedding_ivfflat;
```

**Vector Index Tuning**:

**Current** (IVFFLAT for <1M nodes):
```sql
CREATE INDEX idx_nodes_embedding_ivfflat
ON nodes USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

**High Scale** (HNSW for >1M nodes):
```sql
CREATE INDEX idx_nodes_embedding_hnsw
ON nodes USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**HNSW Parameters**:
- `m = 16`: Good balance of speed/recall
- `ef_construction = 64`: Higher = better recall, slower build
- `ef_search = 40`: Set per query (higher = more accurate, slower)

#### 7.5 Connection Pooling

**Current Configuration**:
```python
ConnectionPool(
    dsn,
    min_size=2,   # Keep 2 warm connections
    max_size=10,  # Allow up to 10 concurrent
    timeout=30.0  # Wait 30s for connection
)
```

**Production Tuning**:
- `max_size` = (num_workers * 2) + scheduler_connections
- Monitor pool exhaustion: `psycopg_pool.PoolTimeout` errors
- Use pgBouncer for >50 concurrent connections

#### 7.6 Security Checklist

**Environment Isolation**:
- ✅ Never commit `.env` files
- ✅ Use separate databases per environment (dev, staging, prod)
- ✅ Rotate JWT secrets every 90 days
- ✅ Enable RLS on all tenant-scoped tables

**Input Validation**:
- ✅ Pydantic models on all request bodies
- ✅ Path traversal protection for file:// payloads
- ✅ Size limits: 10MB files, 5MB HTTP payloads

**Rate Limiting**:
- ✅ Per-tenant, per-endpoint limits
- ✅ Concurrency caps for expensive ops (/ask: 3, /ask/stream: 2)
- ✅ Response headers for client throttling

**Monitoring**:
- ✅ Prometheus metrics on `/prometheus`
- ✅ JSON metrics on `/metrics`
- ✅ Health check on `/health`

---

## Success Criteria

### Retrieval Quality

| Metric | Target | Measurement |
|--------|--------|-------------|
| Recall@10 | ≥ 0.90 | `evaluation/weighted_search_eval.py` |
| MRR | ≥ 0.80 | `evaluation/weighted_search_eval.py` |
| NDCG@10 | ≥ 0.85 | `evaluation/weighted_search_eval.py` |

### Citation Accuracy

| Metric | Target | Measurement |
|--------|--------|-------------|
| Citation presence | ≥ 80% | `evaluation/llm_qa_eval.py` |
| Citation precision | ≥ 0.90 | `evaluation/llm_qa_eval.py` |
| Citation recall | ≥ 0.85 | `evaluation/llm_qa_eval.py` |

### Latency

| Endpoint | p95 Target | Measurement |
|----------|------------|-------------|
| /search (vector) | < 100ms | `evaluation/latency_benchmark.py` |
| /search (hybrid) | < 200ms | `evaluation/latency_benchmark.py` |
| /ask | < 2s | `evaluation/latency_benchmark.py` |
| /ask/stream (TTFB) | < 500ms | `evaluation/latency_benchmark.py` |

### Stability

| Check | Target | Measurement |
|-------|--------|-------------|
| E2E tests | 100% pass | `pytest tests/test_e2e_retrieval.py` |
| Smoke test | All checks ✅ | `scripts/e2e_api_smoke.py` |
| Coverage | Embedding ≥95%, Text=100% | `/debug/search_sanity` |
| CI Build | Green | `.github/workflows/ci.yml` |

---

## Troubleshooting

### Issue: Zero Search Results

**Symptoms**: `/search` returns `{"count": 0, "results": []}`

**Diagnostics**:
1. Check embedding coverage:
   ```bash
   curl http://localhost:8000/debug/search_sanity -H "Authorization: Bearer $ADMIN_TOKEN"
   ```
2. Verify `embedding_coverage_pct >= 95%`

**Solutions**:
- **If coverage < 95%**: Run admin refresh
  ```bash
  curl -X POST http://localhost:8000/admin/refresh \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d '[]'  # Empty array = refresh all due nodes
  ```
- **If no text content**: Check `props.text` is populated in seed data
- **If RLS issue**: Verify `tenant_id` matches between JWT and data

---

### Issue: No Citations in /ask Response

**Symptoms**: Answer returned but `citations: []`

**Diagnostics**:
1. Check if search returns results:
   ```bash
   curl -X POST http://localhost:8000/search \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"query": "your question", "use_hybrid": true, "top_k": 10}'
   ```
2. Check similarity scores (should be > `ASK_SIM_THRESHOLD`)

**Solutions**:
- **If search returns 0 results**: See "Zero Search Results" above
- **If similarity too low**: Lower `ASK_SIM_THRESHOLD` (e.g., 0.20 → 0.15)
- **If content mismatch**: Enrich seed data with synonyms, keywords in metadata

---

### Issue: Text Search Not Populated

**Symptoms**: `text_search_coverage_pct = 0.0` in `/debug/search_sanity`

**Diagnostics**:
1. Check if text search columns exist:
   ```sql
   SELECT column_name FROM information_schema.columns
   WHERE table_name = 'nodes' AND column_name = 'text_search_vector';
   ```

**Solutions**:
- **If column missing**: Run migration
  ```bash
  psql $ACTIVEKG_DSN -f db/migrations/add_text_search.sql
  ```
- **If column exists but empty**: Backfill existing nodes
  ```sql
  UPDATE nodes SET text_search_vector = to_tsvector('english', props->>'text')
  WHERE props->>'text' IS NOT NULL;
  ```

---

### Issue: RLS Context Missing

**Symptoms**: Logs show `current_setting('app.current_tenant_id') = NULL`

**Diagnostics**:
1. Enable RLS debugging:
   ```bash
   export ACTIVEKG_DEBUG_RLS=true
   ```
2. Check logs for `"RLS context set"`

**Solutions**:
- **If JWT enabled**: Verify `tenant_id` claim in JWT payload
- **If JWT disabled (dev)**: Pass `tenant_id` in request body (dev mode only)
- **If multi-tenant isolation broken**: Check RLS policies enabled:
  ```sql
  SELECT tablename, policyname FROM pg_policies WHERE tablename = 'nodes';
  ```

---

### Issue: High Latency (p95 > Target)

**Symptoms**: `/search` p95 > 100ms or `/ask` p95 > 2s

**Diagnostics**:
1. Run latency benchmark:
   ```bash
   python3 evaluation/latency_benchmark.py
   ```
2. Check vector index exists:
   ```sql
   SELECT indexname FROM pg_indexes
   WHERE tablename = 'nodes' AND indexname LIKE '%embedding%';
   ```

**Solutions**:
- **If no vector index**: Create IVFFLAT index
  ```bash
  psql $ACTIVEKG_DSN -f enable_vector_index.sql
  ```
- **If >1M nodes**: Upgrade to HNSW index (see Phase 7.4)
- **If LLM slow**: Check `ASK_FAST_MAX_TOKENS` (lower = faster)
- **If reranker slow**: Disable reranking for high-confidence results
  ```bash
  export RERANK_SKIP_TOPSIM=0.80
  ```

---

### Issue: Rate Limit 429 Errors

**Symptoms**: Requests return `429 Too Many Requests`

**Diagnostics**:
1. Check rate limit headers in response:
   ```
   X-RateLimit-Limit: 50
   X-RateLimit-Remaining: 0
   X-RateLimit-Reset: 1699999999
   ```

**Solutions**:
- **For evaluation**: Use relaxed limits from `.env.eval`
- **For production**: Increase tenant-specific limits in Redis
- **For CI**: Set higher burst limits:
  ```bash
  RATE_LIMIT_SEARCH_BURST=2000
  RATE_LIMIT_ASK_BURST=200
  ```

---

## Quick Reference

### Start API with Eval Config

```bash
set -a; source .env.eval; set +a
uvicorn activekg.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Seed Evaluation Data

```bash
python3 evaluation/datasets/seed_with_jwt.py
```

### Run E2E Tests

```bash
pytest tests/test_e2e_retrieval.py -v
python3 scripts/e2e_api_smoke.py
```

### Run Evaluation Harness

```bash
bash evaluation/run_all.sh
```

### Check Coverage

```bash
curl http://localhost:8000/debug/search_sanity \
  -H "Authorization: Bearer $(python3 -c 'from evaluation.datasets.seed_with_jwt import make_token; print(make_token("eval_tenant", ["admin:refresh"]))')"
```

### Force Refresh All Nodes

```bash
curl -X POST http://localhost:8000/admin/refresh \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[]'
```

---

## Additional Resources

- **Deployment Guide**: `docs/operations/deployment.md`
- **Security Best Practices**: `docs/operations/security.md`
- **Integration Examples**: `INTEGRATION_EXAMPLE.md`
- **Roadmap**: `ROADMAP.md`
- **API Documentation**: Postman collection in `postman/`

---

## Changelog

### v1.0 (2025-11-09)

- ✅ Complete implementation of all 7 phases
- ✅ Comprehensive seed script with verification
- ✅ CI/CD pipeline with PostgreSQL + Redis services
- ✅ Debug endpoints for observability
- ✅ Production hardening checklist
- ✅ Troubleshooting guide
