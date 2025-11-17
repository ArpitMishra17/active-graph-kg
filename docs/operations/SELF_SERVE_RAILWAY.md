# Self‑Serve Demo on Railway (One‑Click Friendly)

This guide packages Active Graph KG for Railway as a self‑serve demo: API app on Railway + managed Postgres with pgvector. Two options:

- Option A (Recommended): Railway app + Neon/Aiven Postgres (pgvector supported)
- Option B (Advanced): Two Railway services (API + Postgres service using `pgvector/pgvector:pg16` image)

Both support “near one‑click” via the Deploy button and minimal env setup.

---

## Prerequisites
- Railway account (paid 32 GB plan recommended for larger embedding models)
- Postgres with pgvector (`CREATE EXTENSION vector;`). Neon or Aiven support this.
- Optional: Redis for rate limiting (only if you enable it)

---

## One‑Click Style Deploy (API)

Add this badge to your repo README (already included in the main README section if you choose to):

```md
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?templateUrl=<your-repo-url>)
```

When Railway imports the repo, it will use Nixpacks or the provided Dockerfile/Procfile to build the API.

### Configure Environment Variables
Set these variables in Railway → Variables for the API service (note: the app will also accept `DATABASE_URL` as a fallback DSN when using the Railway Postgres plugin):

Required
- `ACTIVEKG_DSN` — e.g., `postgresql://USER:PASSWORD@HOST:5432/DBNAME`
- `EMBEDDING_BACKEND=sentence-transformers`
- `EMBEDDING_MODEL=all-MiniLM-L6-v2` (or a larger model like `all-mpnet-base-v2`)
- `SEARCH_DISTANCE=cosine` (or `l2` to match your index opclass)

Recommended
- `PGVECTOR_INDEXES=ivfflat,hnsw` (coexist for migration)
- `AUTO_INDEX_ON_STARTUP=false` (prod-like; manage via admin endpoint)
- `RUN_SCHEDULER=true` (exactly one instance)
- `WORKERS=2` (tune up/down based on CPU)
- `TRANSFORMERS_CACHE=/workspace/cache` + attach a persistent volume to avoid re-downloading models

Security
- Dev: `JWT_SECRET_KEY=<dev-secret>` and `JWT_ALGORITHM=HS256`
- Prod: `JWT_PUBLIC_KEY=<RS256 public>` (preferred) and disable HS256
- If using /ask, set your LLM provider key (e.g., `GROQ_API_KEY`)

Rate Limiting (optional)
- `RATE_LIMIT_ENABLED=true`
- `REDIS_URL=redis://<host>:6379/0`

### Initialize the Database
Option 1 (recommended): run the bootstrap helper (uses ACTIVEKG_DSN or DATABASE_URL automatically):
```bash
make db-bootstrap
```

Option 2: run these once from your laptop or any psql client:
```bash
export ACTIVEKG_DSN='postgresql://USER:PASSWORD@HOST:5432/DBNAME'
psql $ACTIVEKG_DSN -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql $ACTIVEKG_DSN -f db/init.sql
psql $ACTIVEKG_DSN -f enable_rls_policies.sql
# Optional: text search
psql $ACTIVEKG_DSN -f db/migrations/add_text_search.sql
```

Build ANN indexes (non-blocking, concurrent):
```bash
curl -X POST "$API/admin/indexes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"ensure","types":["ivfflat","hnsw"],"metric":"cosine"}'
```

### Validate the Demo
```bash
export API=https://<your-railway-domain>
export TOKEN='<admin JWT>'
make demo-run
make open-grafana  # if you have Grafana connected
```

---

## Option B: Postgres as a Railway Service (Advanced)

Create a new Railway service with Docker image:
- Image: `pgvector/pgvector:pg16`
- Expose port 5432
- Set env: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- Use a persistent volume

Configure the API service’s `ACTIVEKG_DSN` to point to the DB service hostname inside Railway.

Initialize and index as above (`db/init.sql`, `enable_rls_policies.sql`, `/admin/indexes`).

---

## Notes & Limits
- Railway Postgres plugin may not support `vector` extension; use Neon/Aiven if needed.
- Keep `AUTO_INDEX_ON_STARTUP=false` if your DB role is limited; use the admin endpoint for index ops.
- Run only one API instance with `RUN_SCHEDULER=true`.
- Larger embedding models (mpnet/e5) fit within 32 GB RAM; expect slower CPU embedding vs GPU.

---

## Quick Demo Checklist
- [ ] API deployed on Railway
- [ ] pgvector DB provisioned and initialized
- [ ] JWT configured; token generated
- [ ] Indexes ensured via admin endpoint
- [ ] `make demo-run` executed
- [ ] Grafana dashboards connected (optional)
