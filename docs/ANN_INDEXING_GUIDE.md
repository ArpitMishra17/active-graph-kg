# ANN Indexing Guide (pgvector: IVFFLAT vs HNSW)

This guide explains how to configure and operate ANN indexes (IVFFLAT and HNSW) in ActiveKG with pgvector, and when to use each.

## TL;DR

- Small/mid datasets (< ~1M vectors): IVFFLAT is fine; start with `lists=100`, `probes=4–10`.
- Large/latency‑sensitive datasets (≥ ~1–3M vectors): use HNSW; start with `m=16`, `ef_construction=128`, `ef_search=80–200`.
- Keep **metric/operator/opclass** aligned:
  - `SEARCH_DISTANCE=l2` → `ORDER BY embedding <-> %s` and `vector_l2_ops`
  - `SEARCH_DISTANCE=cosine` → `ORDER BY embedding <=> %s` and `vector_cosine_ops`
- You can run both indexes during migration and then drop one to reduce write overhead.

## Configuration (env)

- Single index (recommended):
  - `PGVECTOR_INDEX=ivfflat` or `PGVECTOR_INDEX=hnsw`
- Dual index (staging/migration):
  - `PGVECTOR_INDEXES=ivfflat,hnsw`
- Metric/operator (drives opclass):
  - `SEARCH_DISTANCE=l2|cosine` (default: cosine)
- HNSW tuning:
  - `HNSW_M=16`
  - `HNSW_EF_CONSTRUCTION=128`
  - `HNSW_EF_SEARCH=80` (per query; higher → recall↑, latency↑)
- IVFFLAT tuning:
  - `IVFFLAT_LISTS=100` (start; scale with dataset size)
  - `IVFFLAT_PROBES=4` (per query; higher → recall↑, latency↑)

## How ActiveKG Uses These

- Startup: `ensure_vector_index()` creates requested indexes with metric‑aligned opclasses and distinct names:
  - `idx_nodes_embedding_ivfflat_l2` / `_cos`
  - `idx_nodes_embedding_hnsw_l2` / `_cos`
- Query: vector/hybrid search sets per‑query knobs via `SET LOCAL`:
  - `hnsw.ef_search` and `ivfflat.probes` (best‑effort; ignored if unsupported)
- Operator mapping is automatic based on `SEARCH_DISTANCE`.

## Recommended Settings by Size

| Dataset size | Index   | Metric  | Build params                        | Query params              |
|--------------|---------|---------|-------------------------------------|---------------------------|
| < 100k       | IVFFLAT | l2      | `lists=100`                         | `probes=4–6`             |
| 100k–1M      | IVFFLAT | l2      | `lists=200–500`                     | `probes=6–10`            |
| ≥ 1–3M       | HNSW    | l2      | `m=16`, `ef_construction=128`       | `ef_search=80–150`       |
| ≥ 10M        | HNSW    | l2      | `m=16–32`, `ef_construction=128–256`| `ef_search=120–200`      |

Notes:
- For sentence‑transformers, cosine often performs well; keep operator/opclass aligned if you switch.
- Start modest; observe recall/latency via `/prometheus` and `/debug/search_explain`’s `ann_config`.

## Migration: IVFFLAT → HNSW

1. Set `PGVECTOR_INDEXES=ivfflat,hnsw` and keep current `SEARCH_DISTANCE`.
2. Restart API; the new HNSW index builds concurrently.
3. Verify with `/debug/search_explain` → `ann_config.existing_indexes` contains `idx_nodes_embedding_hnsw_*`.
4. Compare latency/recall; adjust `HNSW_EF_SEARCH`.
5. Switch to `PGVECTOR_INDEX=hnsw` and drop IVFFLAT index when satisfied.

## Troubleshooting

- “Index not used”: metric/operator/opclass mismatch; ensure `SEARCH_DISTANCE` matches the built index opclass.
- “Slow recall”: increase `ef_search` (HNSW) or `probes` (IVFFLAT), or increase candidates before re‑rank.
- “High write overhead”: running both indexes; drop one in production.

## Operator Endpoints (Quick Checks)

Use these API endpoints to manage indexes and verify planner/operator usage in real time.

- Manage ANN indexes (admin scope): `POST /admin/indexes`
  - List:
    ```bash
    curl -s -X POST $API/admin/indexes \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"action":"list"}' | jq
    ```
  - Ensure missing (idempotent):
    ```bash
    curl -s -X POST $API/admin/indexes \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"action":"ensure"}' | jq
    ```
  - Rebuild specific type/metric:
    ```bash
    curl -s -X POST $API/admin/indexes \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"action":"rebuild","types":["hnsw"],"metric":"l2"}' | jq
    ```

- Explain retrieval config: `POST /debug/search_explain`
  - Shows `ann_config` (metric, operator, requested/existing indexes, `hnsw_ef_search`, `ivfflat_probes`) and result score ranges.
  - Example:
    ```bash
    curl -s -X POST $API/debug/search_explain \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"query":"machine learning","use_hybrid":false,"top_k":5}' | jq '.ann_config'
    ```

Tip: Keep `SEARCH_DISTANCE` aligned with the index opclass reported by `ann_config.operator` (`<->` for l2, `<=>` for cosine) to ensure the planner uses the expected index.
