#!/usr/bin/env python3
"""
Weighted Search Evaluation - Compare weighted vs baseline search quality.

Validates Gadde 2024 + custom claims: Recency/drift weighting improves freshness
without significantly hurting accuracy.

Metrics:
- Recall@k (k=1,5,10,20)
- MRR (Mean Reciprocal Rank)
- NDCG (Normalized Discounted Cumulative Gain)
- Average age of top-10 results (days)
- Average drift of top-10 results

Expected Results:
- Recall@10 delta: -2% to +5% (minor accuracy trade-off)
- Average age reduction: -30% to -50% (significantly fresher)
- Average drift reduction: -20% to -40% (more stable results)
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any

import numpy as np
import requests


def calculate_metrics(
    results_list: list[dict[str, Any]],
    ground_truth: dict[str, list[str]],
    k_values: list[int] = None,
) -> dict[str, Any]:
    """Calculate retrieval metrics.

    Args:
        results_list: List of search results for each query
        ground_truth: Dict mapping query -> relevant node IDs
        k_values: List of k values for recall@k

    Returns:
        Dict with recall@k, MRR, NDCG, age, and drift metrics
    """
    if k_values is None:
        k_values = [1, 5, 10, 20]
    recall_at_k = {k: [] for k in k_values}
    reciprocal_ranks = []
    ndcg_scores = []
    avg_ages = []
    avg_drifts = []

    for result in results_list:
        query = result["query"]
        retrieved = result["results"]
        relevant_ids = set(ground_truth.get(query, []))

        if not relevant_ids:
            continue  # Skip queries without ground truth

        # Extract node IDs and (optional) freshness metadata
        # API returns flat items: {id, classes, props, payload_ref, metadata, similarity}
        retrieved_ids = [r.get("id") for r in retrieved]
        # Age/drift are not returned by /search; leave None (or fetch per-node if needed)
        retrieved_ages = [None for _ in retrieved]
        retrieved_drifts = [None for _ in retrieved]

        # Calculate recall@k for each k
        for k in k_values:
            retrieved_k = set(retrieved_ids[:k])
            recall = len(retrieved_k & relevant_ids) / len(relevant_ids)
            recall_at_k[k].append(recall)

        # Calculate reciprocal rank
        rr = 0.0
        for idx, node_id in enumerate(retrieved_ids, start=1):
            if node_id in relevant_ids:
                rr = 1.0 / idx
                break
        reciprocal_ranks.append(rr)

        # Calculate NDCG@10
        dcg = 0.0
        idcg = 0.0
        for idx in range(min(10, len(retrieved_ids))):
            rel = 1.0 if retrieved_ids[idx] in relevant_ids else 0.0
            dcg += rel / np.log2(idx + 2)  # +2 because idx starts at 0

        # Ideal DCG (all relevant at top)
        num_relevant = len(relevant_ids)
        for idx in range(min(10, num_relevant)):
            idcg += 1.0 / np.log2(idx + 2)

        ndcg = dcg / idcg if idcg > 0 else 0.0
        ndcg_scores.append(ndcg)

        # Calculate average age and drift of top-10
        top_10_ages = retrieved_ages[:10]
        top_10_drifts = retrieved_drifts[:10]
        ages_nonnull = [a for a in top_10_ages if a is not None]
        drifts_nonnull = [d for d in top_10_drifts if d is not None]
        avg_ages.append(np.mean(ages_nonnull) if ages_nonnull else 0.0)
        avg_drifts.append(np.mean(drifts_nonnull) if drifts_nonnull else 0.0)

    # Aggregate metrics
    metrics = {
        "recall": {
            f"recall@{k}": np.mean(recall_at_k[k]) if recall_at_k[k] else 0.0 for k in k_values
        },
        "mrr": np.mean(reciprocal_ranks) if reciprocal_ranks else 0.0,
        "ndcg@10": np.mean(ndcg_scores) if ndcg_scores else 0.0,
        "avg_age_days": np.mean(avg_ages) if avg_ages else 0.0,
        "avg_drift_score": np.mean(avg_drifts) if avg_drifts else 0.0,
        "num_queries": len(reciprocal_ranks),
    }

    return metrics


def run_search_queries(
    api_url: str, queries: list[str], top_k: int = 20, use_weighted: bool = False
) -> list[dict[str, Any]]:
    """Run search queries and collect results.

    Args:
        api_url: Base API URL
        queries: List of search queries
        top_k: Number of results to retrieve
        use_weighted: Whether to use weighted scoring

    Returns:
        List of results for each query
    """
    results_list = []

    for query in queries:
        try:
            resp = requests.post(
                f"{api_url}/search",
                json={"query": query, "top_k": top_k, "use_weighted_score": use_weighted},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            results_list.append({"query": query, "results": data.get("results", [])})
        except Exception as e:
            print(f"⚠ Query failed: {query[:50]}... ({e})")
            continue

    return results_list


def compare_weighted_vs_baseline(
    api_url: str, test_queries: list[str], ground_truth: dict[str, list[str]], top_k: int = 20
) -> dict[str, Any]:
    """Compare weighted vs baseline search quality.

    Args:
        api_url: Base API URL
        test_queries: List of test queries
        ground_truth: Dict mapping query -> relevant node IDs
        top_k: Number of results to retrieve

    Returns:
        Dict with baseline, weighted, and delta metrics
    """
    print("=" * 70)
    print("WEIGHTED SEARCH EVALUATION")
    print("=" * 70)
    print(f"API URL: {api_url}")
    print(f"Test queries: {len(test_queries)}")
    print(f"Top-k: {top_k}")
    print()

    # 1. Run baseline queries (use_weighted_score=False)
    print("Step 1: Running baseline queries (use_weighted_score=False)...")
    baseline_start = time.time()
    baseline_results = run_search_queries(api_url, test_queries, top_k=top_k, use_weighted=False)
    baseline_time = time.time() - baseline_start

    baseline_metrics = calculate_metrics(baseline_results, ground_truth)
    print(f"✓ Baseline Recall@10: {baseline_metrics['recall']['recall@10']:.3f}")
    print(f"✓ Baseline MRR: {baseline_metrics['mrr']:.3f}")
    print(f"✓ Baseline Avg Age: {baseline_metrics['avg_age_days']:.1f} days")
    print(f"✓ Baseline Avg Drift: {baseline_metrics['avg_drift_score']:.3f}")
    print(f"✓ Time: {baseline_time:.2f}s\n")

    # 2. Run weighted queries (use_weighted_score=True)
    print("Step 2: Running weighted queries (use_weighted_score=True)...")
    weighted_start = time.time()
    weighted_results = run_search_queries(api_url, test_queries, top_k=top_k, use_weighted=True)
    weighted_time = time.time() - weighted_start

    weighted_metrics = calculate_metrics(weighted_results, ground_truth)
    print(f"✓ Weighted Recall@10: {weighted_metrics['recall']['recall@10']:.3f}")
    print(f"✓ Weighted MRR: {weighted_metrics['mrr']:.3f}")
    print(f"✓ Weighted Avg Age: {weighted_metrics['avg_age_days']:.1f} days")
    print(f"✓ Weighted Avg Drift: {weighted_metrics['avg_drift_score']:.3f}")
    print(f"✓ Time: {weighted_time:.2f}s\n")

    # 3. Calculate deltas
    delta_recall10 = (
        weighted_metrics["recall"]["recall@10"] - baseline_metrics["recall"]["recall@10"]
    )
    delta_mrr = weighted_metrics["mrr"] - baseline_metrics["mrr"]
    delta_age = weighted_metrics["avg_age_days"] - baseline_metrics["avg_age_days"]
    delta_drift = weighted_metrics["avg_drift_score"] - baseline_metrics["avg_drift_score"]

    # Percentage changes
    recall10_pct = (
        (delta_recall10 / baseline_metrics["recall"]["recall@10"] * 100)
        if baseline_metrics["recall"]["recall@10"] > 0
        else 0
    )
    mrr_pct = (delta_mrr / baseline_metrics["mrr"] * 100) if baseline_metrics["mrr"] > 0 else 0
    age_pct = (
        (delta_age / baseline_metrics["avg_age_days"] * 100)
        if baseline_metrics["avg_age_days"] > 0
        else 0
    )
    drift_pct = (
        (delta_drift / baseline_metrics["avg_drift_score"] * 100)
        if baseline_metrics["avg_drift_score"] > 0
        else 0
    )

    # 4. Report results
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print("Accuracy Metrics:")
    print(
        f"  Recall@10:  {baseline_metrics['recall']['recall@10']:.3f} → {weighted_metrics['recall']['recall@10']:.3f} ({delta_recall10:+.3f}, {recall10_pct:+.1f}%)"
    )
    print(
        f"  MRR:        {baseline_metrics['mrr']:.3f} → {weighted_metrics['mrr']:.3f} ({delta_mrr:+.3f}, {mrr_pct:+.1f}%)"
    )
    print(f"  NDCG@10:    {baseline_metrics['ndcg@10']:.3f} → {weighted_metrics['ndcg@10']:.3f}")
    print()
    print("Freshness Metrics:")
    print(
        f"  Avg Age:    {baseline_metrics['avg_age_days']:.1f}d → {weighted_metrics['avg_age_days']:.1f}d ({delta_age:+.1f}d, {age_pct:+.1f}%)"
    )
    print(
        f"  Avg Drift:  {baseline_metrics['avg_drift_score']:.3f} → {weighted_metrics['avg_drift_score']:.3f} ({delta_drift:+.3f}, {drift_pct:+.1f}%)"
    )
    print()
    print("Performance:")
    print(f"  Baseline time: {baseline_time:.2f}s")
    print(
        f"  Weighted time: {weighted_time:.2f}s ({(weighted_time - baseline_time):+.2f}s, {((weighted_time / baseline_time - 1) * 100):+.1f}%)"
    )
    print()

    # Check against expected results
    recall_in_range = -0.05 <= delta_recall10 / baseline_metrics["recall"]["recall@10"] <= 0.10
    age_improvement = age_pct <= -30  # At least 30% reduction
    drift_improvement = drift_pct <= -20  # At least 20% reduction

    recall_status = "✅" if recall_in_range else "⚠"
    age_status = "✅" if age_improvement else "⚠"
    drift_status = "✅" if drift_improvement else "⚠"

    print("Expected vs Actual:")
    print(f"{recall_status} Recall@10 delta:   {recall10_pct:+.1f}% (target: -5% to +10%)")
    print(f"{age_status} Age reduction:     {age_pct:+.1f}% (target: ≤-30%)")
    print(f"{drift_status} Drift reduction:   {drift_pct:+.1f}% (target: ≤-20%)")
    print("=" * 70)

    return {
        "baseline": baseline_metrics,
        "weighted": weighted_metrics,
        "deltas": {
            "recall@10": delta_recall10,
            "recall@10_percent": recall10_pct,
            "mrr": delta_mrr,
            "mrr_percent": mrr_pct,
            "avg_age_days": delta_age,
            "avg_age_percent": age_pct,
            "avg_drift": delta_drift,
            "avg_drift_percent": drift_pct,
        },
        "meets_expectations": {
            "recall_in_range": recall_in_range,
            "age_improvement": age_improvement,
            "drift_improvement": drift_improvement,
        },
        "timing": {"baseline": baseline_time, "weighted": weighted_time},
    }


def load_test_data(
    queries_file: str, ground_truth_file: str
) -> tuple[list[str], dict[str, list[str]]]:
    """Load test queries and ground truth from JSON files."""
    with open(queries_file) as f:
        queries = json.load(f)

    with open(ground_truth_file) as f:
        ground_truth = json.load(f)

    return queries, ground_truth


def main():
    parser = argparse.ArgumentParser(description="Weighted Search Evaluation")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument(
        "--queries", default="evaluation/datasets/test_queries.json", help="Test queries JSON file"
    )
    parser.add_argument(
        "--ground-truth",
        default="evaluation/datasets/ground_truth.json",
        help="Ground truth JSON file",
    )
    parser.add_argument("--top-k", type=int, default=20, help="Number of results to retrieve")
    parser.add_argument(
        "--output", default="evaluation/weighted_search_results.json", help="Output JSON file"
    )
    args = parser.parse_args()

    try:
        # Load test data
        queries, ground_truth = load_test_data(args.queries, args.ground_truth)

        # Run evaluation
        results = compare_weighted_vs_baseline(
            args.api_url, queries, ground_truth, top_k=args.top_k
        )

        # Save results
        results["timestamp"] = datetime.now().isoformat()
        results["config"] = {
            "api_url": args.api_url,
            "top_k": args.top_k,
            "num_queries": len(queries),
        }

        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Results saved to {args.output}")

        # Exit with appropriate code
        meets_all = all(results.get("meets_expectations", {}).values())
        sys.exit(0 if meets_all else 1)

    except FileNotFoundError as e:
        print(f"❌ Error: Test data file not found: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
