# Roadmap

## Phases

- Phase 1 — Active Nodes + Semantic Triggers (Complete)
  - Refresh policies with drift gating (interval + cron)
  - Semantic triggers with DB-backed patterns
  - Lineage via DERIVED_FROM edges
  - Weighted vector search (recency decay + drift penalty)
  - RLS multi-tenancy, audit events

- Phase 1.5 — Hardening & UX (In Progress)
  - Hybrid BM25 + vector + reranker (db/add_text_search.sql)
  - Q&A endpoints with citations: `/ask`, `/ask/stream`
  - Env-tunable knobs (thresholds, tokens, snippets, candidates)
  - Caching for /ask; streaming SSE; metrics polish

- Phase 2 — Lineage & Polyglot Expansion
  - Versions API (`/nodes/{id}/versions`), richer lineage views
  - Polyglot payloads: more formats, extraction policies
  - WebSocket streaming for events and answers

- Phase 3 — CRDT Graph Replication
  - Multi-writer, conflict-free graph editing
  - Rule DSL for triggers (vector + graph patterns)

- Phase 4 — Adaptive Compression & Cost Optimizations
  - Product quantization / 8-bit embeddings (optional)
  - Index tuning (HNSW/IVF) + predictive refresh windows

## OSS Growth
- CONTRIBUTING, CODEOWNERS, issue templates
- Good-first-issues backlog
- Adapters: LangChain/LlamaIndex
- Postman collection; examples/seed_demo.py

## GTM
- One-pager (GitHub Pages), README polish, screencast
- Benchmarks blog (run_all.sh harness)
- Channels: HN/PH/Reddit/Twitter/LinkedIn; Postgres Weekly

