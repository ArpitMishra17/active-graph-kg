# Ground Truth Seeding Guide

## Overview

Ground truth seeding is the process of mapping evaluation queries to relevant node IDs in your corpus. This enables accurate measurement of retrieval quality metrics (Recall@k, MRR, NDCG) and Q&A benchmark metrics (citation precision/recall).

---

## Quick Start

```bash
export API=http://localhost:8000
export TOKEN='<your-jwt>'

# 1. Ensure you have test data
make live-smoke  # Creates sample nodes

# 2. Seed ground truth from queries
make seed-ground-truth

# 3. Run retrieval quality evaluation
make retrieval-quality

# 4. Run Q&A benchmark
make qa-benchmark

# 5. Generate proof report (includes metrics)
make proof-report
```

---

## Ground Truth Seeding Script

### Script: `scripts/seed_ground_truth.sh`

**Purpose**: Automatically populate `evaluation/datasets/ground_truth.json` by querying the live API.

**How It Works**:
1. Reads queries from `evaluation/datasets/test_queries.json`
2. For each query, calls `/search` endpoint
3. Filters results based on similarity threshold or top-k
4. Writes `{query: [node_ids]}` mapping to ground truth file
5. Optionally seeds `qa_questions.json` relevant_node_ids

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API` | `http://localhost:8000` | API endpoint URL |
| `QUERIES` | `evaluation/datasets/test_queries.json` | Input queries file |
| `GROUND` | `evaluation/datasets/ground_truth.json` | Output ground truth file |
| `MODE` | `threshold` | Filtering mode: `threshold` or `topk` |
| `THRESH` | `0.20` | Similarity threshold (0..1) for `threshold` mode |
| `TOPK` | `10` | Number of top results for `topk` mode |
| `HYBRID` | `false` | Use hybrid search (true/false) |
| `QA_FILE` | `evaluation/datasets/qa_questions.json` | Optional Q&A file to seed |

---

## Modes

### 1. Threshold Mode (Default)

**Description**: Include all results with similarity >= threshold

**Best For**:
- High-precision ground truth (only include truly relevant results)
- When you want to filter out low-similarity noise
- Conservative evaluation (fewer false positives)

**Example**:
```bash
# Include only results with similarity >= 0.25
export MODE=threshold
export THRESH=0.25
make seed-ground-truth
```

**Typical Thresholds**:
- `0.15-0.20`: Permissive (broader recall)
- `0.20-0.30`: Balanced (recommended default)
- `0.30-0.40`: Strict (high precision)
- `0.40+`: Very strict (only very similar results)

---

### 2. Top-K Mode

**Description**: Include top K results regardless of similarity

**Best For**:
- Fixed-size ground truth sets
- When you want consistent evaluation across queries
- Ranking-focused metrics (MRR, NDCG)

**Example**:
```bash
# Include top 10 results per query
export MODE=topk
export TOPK=10
make seed-ground-truth
```

**Typical Top-K Values**:
- `5`: Small, high-precision set
- `10`: Standard evaluation (Recall@10, NDCG@10)
- `20`: Larger recall measurement
- `50+`: Comprehensive coverage

---

## Input Files

### test_queries.json

**Format**:
```json
[
  { "text": "machine learning" },
  { "text": "graph rag" },
  "postgres vector search"  // String also supported
]
```

**Guidelines**:
- Include 10-50 diverse queries for robust evaluation
- Cover different query types (broad, specific, multi-word)
- Include domain-specific terminology
- Mix common and rare queries

---

### qa_questions.json (Optional)

**Format**:
```json
[
  {
    "question": "What is machine learning?",
    "answer": "Machine learning is a field of AI...",
    "relevant_node_ids": []  // Will be populated by seed script
  }
]
```

**Guidelines**:
- Questions should be answerable from corpus
- Include 20-100 Q&A pairs for statistical significance
- Mix factual, conceptual, and procedural questions
- Answers should be 1-3 sentences

---

## Output Files

### ground_truth.json

**Format**:
```json
{
  "machine learning": ["node-uuid-1", "node-uuid-2", "node-uuid-3"],
  "graph rag": ["node-uuid-4", "node-uuid-5"],
  "postgres vector search": []  // No results met threshold
}
```

**Interpretation**:
- Each query maps to array of relevant node IDs
- Empty arrays indicate no results met criteria
- Node IDs used for computing Recall@k, MRR, NDCG

---

## Evaluation Metrics

### Once Ground Truth is Seeded

**1. Retrieval Quality**
```bash
make retrieval-quality
# Output: evaluation/weighted_search_results.json
# Metrics: Recall@10, MRR, NDCG@10
```

**2. Q&A Benchmark**
```bash
make qa-benchmark
# Output: evaluation/llm_qa_results.json
# Metrics: Accuracy, Citation Precision/Recall, Ask Latency
```

**3. Proof Report**
```bash
make proof-report
# Automatically includes above metrics when files exist
```

---

## Examples

### Example 1: Quick Seeding (Defaults)

```bash
# Use defaults: threshold mode, 0.20 cutoff
make seed-ground-truth
```

**Result**: Conservative ground truth with similarity >= 0.20

---

### Example 2: Permissive Threshold

```bash
# Include more results (similarity >= 0.15)
export THRESH=0.15
make seed-ground-truth
```

**Use Case**: When you want higher recall in ground truth (catch more potential matches)

---

### Example 3: Top-10 Fixed

```bash
# Always take top 10 results
export MODE=topk
export TOPK=10
make seed-ground-truth
```

**Use Case**: Consistent evaluation set size across all queries

---

### Example 4: Hybrid Search Seeding

```bash
# Use hybrid search (RRF) for ground truth
export HYBRID=true
make seed-ground-truth
```

**Use Case**: Evaluate hybrid search performance using hybrid ground truth

---

### Example 5: Custom Paths

```bash
# Use custom query/ground truth files
export QUERIES=evaluation/datasets/custom_queries.json
export GROUND=evaluation/datasets/custom_ground_truth.json
make seed-ground-truth
```

**Use Case**: Multiple evaluation sets (e.g., domain-specific, language-specific)

---

## Best Practices

### 1. Corpus Preparation

**Before Seeding**:
- Ensure corpus has diverse, high-quality nodes
- Run `make live-smoke` or seed real data
- Verify embeddings generated: `curl $API/_admin/embed_info`
- Check coverage >= 90%

### 2. Threshold Selection

**Guidelines**:
- Start with `THRESH=0.20` (balanced)
- Review sample results: `cat evaluation/datasets/ground_truth.json`
- Adjust based on domain:
  - Technical/specific domains: 0.25-0.30 (higher threshold)
  - General/broad domains: 0.15-0.20 (lower threshold)

### 3. Query Quality

**Good Queries**:
- Specific: "PostgreSQL vector index optimization"
- Answerable: "How to configure HNSW parameters"
- Varied: Mix short (2-3 words) and long (5-10 words)

**Poor Queries**:
- Too broad: "database"
- Too rare: "obscure-technical-jargon-12345"
- Unanswerable: "What is the meaning of life?"

### 4. Manual Review

**Recommended**:
1. Run seeding script
2. Review sample mappings:
   ```bash
   cat evaluation/datasets/ground_truth.json | jq '.'
   ```
3. Spot-check node IDs are relevant:
   ```bash
   curl "$API/nodes/<node-id>" -H "Authorization: Bearer $TOKEN"
   ```
4. Adjust `THRESH` or `TOPK` if needed
5. Re-run seeding

### 5. Iteration

**Process**:
1. Seed → Evaluate → Review Metrics
2. If Recall too low: Lower `THRESH` or increase `TOPK`
3. If Precision too low: Raise `THRESH` or reduce `TOPK`
4. If MRR/NDCG low: Improve corpus quality or query specificity

---

## Troubleshooting

### Issue: Empty Ground Truth

**Symptom**:
```json
{
  "query1": [],
  "query2": []
}
```

**Causes**:
- Threshold too high (`THRESH > 0.30`)
- Corpus lacks relevant content
- Embeddings not generated

**Fixes**:
```bash
# Lower threshold
export THRESH=0.10
make seed-ground-truth

# Check embedding coverage
curl "$API/_admin/embed_info" -H "Authorization: Bearer $TOKEN"

# Verify search works
curl -X POST "$API/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"test","top_k":5}' | jq .
```

---

### Issue: Too Many Results

**Symptom**: Every query returns 50+ node IDs

**Causes**:
- Threshold too low (`THRESH < 0.10`)
- Corpus too homogeneous
- Query too generic

**Fixes**:
```bash
# Raise threshold
export THRESH=0.25
make seed-ground-truth

# Or switch to top-k mode
export MODE=topk
export TOPK=10
make seed-ground-truth
```

---

### Issue: Inconsistent Results

**Symptom**: Different results on re-runs

**Causes**:
- Corpus changed (nodes added/deleted/updated)
- Embeddings refreshed
- Non-deterministic ranking (rare)

**Fixes**:
- Seed ground truth once and commit to version control
- Re-seed only when corpus significantly changes
- Use `git diff` to track ground truth changes

---

## Advanced Usage

### Multi-Stage Seeding

```bash
# 1. Broad seeding (threshold mode)
export THRESH=0.20
make seed-ground-truth

# 2. Manual curation (review and edit ground_truth.json)

# 3. Re-evaluate
make retrieval-quality
```

### Cross-Validation Sets

```bash
# Training set
export QUERIES=evaluation/datasets/train_queries.json
export GROUND=evaluation/datasets/train_ground_truth.json
make seed-ground-truth

# Test set
export QUERIES=evaluation/datasets/test_queries.json
export GROUND=evaluation/datasets/test_ground_truth.json
make seed-ground-truth
```

### Hybrid vs Vector Comparison

```bash
# Seed with vector search
export HYBRID=false
export GROUND=evaluation/datasets/ground_truth_vector.json
make seed-ground-truth

# Seed with hybrid search
export HYBRID=true
export GROUND=evaluation/datasets/ground_truth_hybrid.json
make seed-ground-truth

# Compare: Are hybrid results more comprehensive?
diff <(jq '.' evaluation/datasets/ground_truth_vector.json) \
     <(jq '.' evaluation/datasets/ground_truth_hybrid.json)
```

---

## Integration with CI/CD

### Nightly Re-Seeding

```yaml
# .github/workflows/nightly-eval.yml
- name: Seed Ground Truth
  run: |
    export API=http://localhost:8000
    export TOKEN=${{ secrets.E2E_ADMIN_TOKEN }}
    make seed-ground-truth

- name: Run Evaluations
  run: |
    make retrieval-quality
    make qa-benchmark
    make proof-report

- name: Upload Results
  uses: actions/upload-artifact@v4
  with:
    name: evaluation-results
    path: evaluation/*.json
```

---

## References

- **Retrieval Quality Evaluation**: `docs/operations/PROOF_POINTS_MATRIX.md`
- **Q&A Benchmark Guide**: `docs/operations/PROOF_POINTS_GUIDE.md`
- **Script Source**: `scripts/seed_ground_truth.sh`
- **Evaluation Scripts**: `evaluation/weighted_search_eval.py`, `evaluation/llm_qa_eval.py`
