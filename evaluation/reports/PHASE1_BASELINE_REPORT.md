# Phase 1 Baseline Report: Structured Fields in Embedding + Hybrid Text Search

**Date:** 2026-02-05
**Tenant:** `gold_eval_phase1_20260205_0729`
**Nodes:** 172 indexed
**Queries:** 20 gold queries from screening CSV

---

## Summary

Phase 1 delivered **+171% Recall@10** and **+95% MRR** over baseline by:
1. Extending BM25 text_search_vector to include `resume_text`, `required_skills`, `good_to_have_skills`, `job_title`
2. Adding embedding prefix for resume/job nodes with structured fields
3. Indexing nodes with proper structured props from screening CSV

---

## Results Comparison

| Metric | Baseline | BM25 Only | Phase 1 Full | vs Baseline |
|--------|----------|-----------|--------------|-------------|
| **Recall@1** | 2.9% | 6.2% | 10.7% | +271% |
| **Recall@5** | 8.7% | 10.5% | 28.4% | +227% |
| **Recall@10** | 12.0% | 13.1% | 32.5% | +171% |
| **Recall@20** | 12.9% | 14.0% | 38.1% | +196% |
| **Recall@50** | 14.3% | 14.3% | 40.5% | +183% |
| **Precision@1** | 25.0% | 40.0% | 60.0% | +140% |
| **Precision@5** | 16.0% | 19.0% | 37.0% | +131% |
| **Precision@10** | 13.0% | 14.5% | 26.5% | +104% |
| **MRR** | 31.6% | 43.8% | 61.7% | +95% |
| **NDCG@10** | 17.9% | 22.6% | 43.9% | +145% |

---

## Configuration

### Environment Variables
```
EMBEDDING_PREFIX_ENABLED=true
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_ASYNC=true
```

### Migration Applied
- `db/migrations/010_update_text_search_vector.sql`
  - Added `jsonb_text_value()` helper for JSON array handling
  - Extended trigger: `title`, `job_title`, `required_skills` (weight A); `text`, `resume_text`, `good_to_have_skills` (weight B)

### Code Changes
- `activekg/graph/repository.py`: Added `build_embedding_text()` method
- `activekg/embedding/worker.py`: Uses `build_embedding_text()`
- `activekg/api/main.py`: `_background_embed()` uses `build_embedding_text()`

---

## Embedding Prefix Format

When `EMBEDDING_PREFIX_ENABLED=true` and node has `Resume`/`Job` class or `resume_text`/`job_title` in props:

```
JOB_TITLE: <job_title>
PRIMARY_SKILLS: <required_skills>
GOOD_TO_HAVE: <good_to_have_skills>
EXPERIENCE: <experience_years>
EDUCATION: <education_requirement>

<resume_text>
```

---

## Node Schema (indexed with structured fields)

```json
{
  "classes": ["Candidate", "Resume"],
  "props": {
    "external_id": "<app_id>",
    "resume_text": "<extracted text>",
    "job_title": "<job_title>",
    "required_skills": "<skills>",
    "good_to_have_skills": "<skills>",
    "experience_years": "<years>",
    "education_requirement": "<education>"
  },
  "metadata": {
    "csv_id": "<app_id>"
  }
}
```

---

## Performance

- **Re-embed time:** ~60s for 170 nodes (~2.8 nodes/sec)
- **Eval time:** ~34s for 20 queries

---

## Files

- Eval results: `/tmp/search_gold_phase1_full.json`
- Index summary: `/tmp/phase1_index_summary.json`
- Queries: `/tmp/queries_gold_phase1.jsonl`

---

## Commits

- `66bbce5` - feat(embedding): add structured prefix for resume/job embeddings + BM25 fields
- `395bb6f` - fix(db): add migration 010 to Railway init script

---

## Next Steps

1. **Phase 2:** Consider reranker tuning, query expansion, or hybrid weight adjustments
2. **Production:** Apply same indexing pattern with structured props for all resume data
3. **Monitoring:** Track MRR/Recall metrics in production
