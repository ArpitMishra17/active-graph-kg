#!/usr/bin/env python3
"""
Drift Cohort Analysis - Measure quality improvement from refreshing high-drift nodes.

Validates Chen 2021 claims: Refreshing high-drift nodes improves retrieval quality.

Metrics:
- Recall@10 before/after refresh
- MRR (Mean Reciprocal Rank) before/after refresh
- Average drift score per cohort

Expected Results (Chen 2021):
- Recall@10 improvement: +10-15%
- MRR improvement: +8-12%
- Nodes with drift > 0.3 show biggest gains
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple
import requests
import numpy as np


def get_high_drift_nodes(
    api_url: str,
    drift_threshold: float = 0.2,
    limit: int = 100
) -> List[str]:
    """Find nodes with drift > threshold.

    Args:
        api_url: Base API URL
        drift_threshold: Minimum drift score
        limit: Max number of nodes to return

    Returns:
        List of node IDs with high drift
    """
    # Use anomaly detection endpoint to find drift spikes
    resp = requests.get(
        f"{api_url}/admin/anomalies",
        params={
            "types": "drift_spike",
            "drift_spike_threshold": drift_threshold / 0.1,  # Convert to multiplier
            "lookback_hours": 168  # 1 week
        }
    )
    resp.raise_for_status()
    data = resp.json()

    drift_spikes = data.get("anomalies", {}).get("drift_spike", [])
    node_ids = [anomaly["node_id"] for anomaly in drift_spikes[:limit]]

    print(f"Found {len(node_ids)} high-drift nodes (drift > {drift_threshold})")
    return node_ids


def run_test_queries(
    api_url: str,
    queries: List[str],
    ground_truth: Dict[str, List[str]],
    top_k: int = 10,
    use_weighted: bool = False
) -> Dict[str, Any]:
    """Run queries and measure retrieval quality.

    Args:
        api_url: Base API URL
        queries: List of search queries
        ground_truth: Dict mapping query -> list of relevant node IDs
        top_k: Number of results to retrieve
        use_weighted: Whether to use weighted scoring

    Returns:
        Dict with recall@k and MRR metrics
    """
    recall_scores = []
    reciprocal_ranks = []

    for query in queries:
        # Run search
        resp = requests.post(
            f"{api_url}/search",
            json={
                "query": query,
                "top_k": top_k,
                "use_weighted_score": use_weighted
            }
        )
        resp.raise_for_status()
        results = resp.json()

        # Extract node IDs from results (flat API structure)
        retrieved_ids = [r.get("id") for r in results.get("results", [])]
        relevant_ids = set(ground_truth.get(query, []))

        if not relevant_ids:
            continue  # Skip queries without ground truth

        # Calculate recall@k
        retrieved_set = set(retrieved_ids[:top_k])
        recall = len(retrieved_set & relevant_ids) / len(relevant_ids)
        recall_scores.append(recall)

        # Calculate reciprocal rank
        rr = 0.0
        for idx, node_id in enumerate(retrieved_ids, start=1):
            if node_id in relevant_ids:
                rr = 1.0 / idx
                break
        reciprocal_ranks.append(rr)

    return {
        "recall@10": np.mean(recall_scores) if recall_scores else 0.0,
        "recall@10_std": np.std(recall_scores) if recall_scores else 0.0,
        "mrr": np.mean(reciprocal_ranks) if reciprocal_ranks else 0.0,
        "mrr_std": np.std(reciprocal_ranks) if reciprocal_ranks else 0.0,
        "num_queries": len(recall_scores)
    }


def refresh_nodes(api_url: str, node_ids: List[str]) -> Dict[str, Any]:
    """Force refresh a list of nodes.

    Args:
        api_url: Base API URL
        node_ids: List of node IDs to refresh

    Returns:
        Refresh status
    """
    resp = requests.post(
        f"{api_url}/admin/refresh",
        json=node_ids
    )
    resp.raise_for_status()
    return resp.json()


def measure_drift_cohort_impact(
    api_url: str,
    test_queries: List[str],
    ground_truth: Dict[str, List[str]],
    drift_threshold: float = 0.2,
    wait_after_refresh: int = 5
) -> Dict[str, Any]:
    """Measure impact of refreshing high-drift nodes on retrieval quality.

    Args:
        api_url: Base API URL
        test_queries: List of test queries
        ground_truth: Dict mapping query -> relevant node IDs
        drift_threshold: Minimum drift score for cohort
        wait_after_refresh: Seconds to wait after refresh

    Returns:
        Dict with baseline, post-refresh, and delta metrics
    """
    print("=" * 70)
    print("DRIFT COHORT ANALYSIS")
    print("=" * 70)
    print(f"API URL: {api_url}")
    print(f"Drift threshold: {drift_threshold}")
    print(f"Test queries: {len(test_queries)}")
    print()

    # 1. Find high-drift nodes
    print("Step 1: Identifying high-drift nodes...")
    high_drift_nodes = get_high_drift_nodes(api_url, drift_threshold)

    if not high_drift_nodes:
        print("⚠ No high-drift nodes found. Skipping cohort analysis.")
        return {"error": "No high-drift nodes found"}

    print(f"✓ Found {len(high_drift_nodes)} high-drift nodes\n")

    # 2. Baseline: run queries before refresh
    print("Step 2: Running baseline queries (before refresh)...")
    baseline_start = time.time()
    baseline_metrics = run_test_queries(api_url, test_queries, ground_truth, top_k=10)
    baseline_time = time.time() - baseline_start

    print(f"✓ Baseline Recall@10: {baseline_metrics['recall@10']:.3f}")
    print(f"✓ Baseline MRR: {baseline_metrics['mrr']:.3f}")
    print(f"✓ Queries processed: {baseline_metrics['num_queries']}")
    print(f"✓ Time: {baseline_time:.2f}s\n")

    # 3. Force refresh high-drift nodes
    print("Step 3: Refreshing high-drift nodes...")
    refresh_start = time.time()
    refresh_result = refresh_nodes(api_url, high_drift_nodes)
    refresh_time = time.time() - refresh_start

    print(f"✓ Refreshed: {refresh_result.get('refreshed', 0)} nodes")
    print(f"✓ Time: {refresh_time:.2f}s")
    print(f"Waiting {wait_after_refresh}s for changes to propagate...\n")
    time.sleep(wait_after_refresh)

    # 4. Post-refresh: run queries again
    print("Step 4: Running post-refresh queries...")
    post_refresh_start = time.time()
    post_refresh_metrics = run_test_queries(api_url, test_queries, ground_truth, top_k=10)
    post_refresh_time = time.time() - post_refresh_start

    print(f"✓ Post-refresh Recall@10: {post_refresh_metrics['recall@10']:.3f}")
    print(f"✓ Post-refresh MRR: {post_refresh_metrics['mrr']:.3f}")
    print(f"✓ Time: {post_refresh_time:.2f}s\n")

    # 5. Calculate deltas
    delta_recall = post_refresh_metrics["recall@10"] - baseline_metrics["recall@10"]
    delta_mrr = post_refresh_metrics["mrr"] - baseline_metrics["mrr"]

    # 6. Report results
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"Baseline Recall@10:      {baseline_metrics['recall@10']:.3f} ± {baseline_metrics['recall@10_std']:.3f}")
    print(f"Post-refresh Recall@10:  {post_refresh_metrics['recall@10']:.3f} ± {post_refresh_metrics['recall@10_std']:.3f}")
    print(f"Δ Recall@10:             {delta_recall:+.3f} ({delta_recall/baseline_metrics['recall@10']*100:+.1f}%)")
    print()
    print(f"Baseline MRR:            {baseline_metrics['mrr']:.3f} ± {baseline_metrics['mrr_std']:.3f}")
    print(f"Post-refresh MRR:        {post_refresh_metrics['mrr']:.3f} ± {post_refresh_metrics['mrr_std']:.3f}")
    print(f"Δ MRR:                   {delta_mrr:+.3f} ({delta_mrr/baseline_metrics['mrr']*100:+.1f}%)")
    print()

    # Check against expected results (Chen 2021)
    expected_recall_improvement = 0.10  # +10%
    expected_mrr_improvement = 0.08     # +8%

    recall_percent = delta_recall / baseline_metrics["recall@10"] if baseline_metrics["recall@10"] > 0 else 0
    mrr_percent = delta_mrr / baseline_metrics["mrr"] if baseline_metrics["mrr"] > 0 else 0

    recall_status = "✅" if recall_percent >= expected_recall_improvement else "⚠"
    mrr_status = "✅" if mrr_percent >= expected_mrr_improvement else "⚠"

    print("Expected vs Actual (Chen 2021):")
    print(f"{recall_status} Recall@10 improvement: {recall_percent*100:+.1f}% (target: +10%)")
    print(f"{mrr_status} MRR improvement:       {mrr_percent*100:+.1f}% (target: +8%)")
    print("=" * 70)

    return {
        "baseline": baseline_metrics,
        "post_refresh": post_refresh_metrics,
        "delta": {
            "recall@10": delta_recall,
            "recall@10_percent": recall_percent * 100,
            "mrr": delta_mrr,
            "mrr_percent": mrr_percent * 100
        },
        "high_drift_nodes": len(high_drift_nodes),
        "drift_threshold": drift_threshold,
        "meets_expectations": {
            "recall": recall_percent >= expected_recall_improvement,
            "mrr": mrr_percent >= expected_mrr_improvement
        },
        "timing": {
            "baseline_queries": baseline_time,
            "refresh": refresh_time,
            "post_refresh_queries": post_refresh_time
        }
    }


def load_test_data(queries_file: str, ground_truth_file: str) -> Tuple[List[str], Dict[str, List[str]]]:
    """Load test queries and ground truth from JSON files.

    Args:
        queries_file: Path to queries JSON file
        ground_truth_file: Path to ground truth JSON file

    Returns:
        Tuple of (queries, ground_truth_dict)
    """
    with open(queries_file, 'r') as f:
        queries = json.load(f)

    with open(ground_truth_file, 'r') as f:
        ground_truth = json.load(f)

    return queries, ground_truth


def main():
    parser = argparse.ArgumentParser(description="Drift Cohort Analysis")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--queries", default="evaluation/datasets/test_queries.json", help="Test queries JSON file")
    parser.add_argument("--ground-truth", default="evaluation/datasets/ground_truth.json", help="Ground truth JSON file")
    parser.add_argument("--drift-threshold", type=float, default=0.2, help="Drift threshold for cohort")
    parser.add_argument("--output", default="evaluation/drift_cohort_results.json", help="Output JSON file")
    args = parser.parse_args()

    try:
        # Load test data
        queries, ground_truth = load_test_data(args.queries, args.ground_truth)

        # Run analysis
        results = measure_drift_cohort_impact(
            args.api_url,
            queries,
            ground_truth,
            drift_threshold=args.drift_threshold
        )

        # Save results
        results["timestamp"] = datetime.now().isoformat()
        results["config"] = {
            "api_url": args.api_url,
            "drift_threshold": args.drift_threshold,
            "num_queries": len(queries)
        }

        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Results saved to {args.output}")

        # Exit with appropriate code
        if results.get("meets_expectations", {}).get("recall") and results.get("meets_expectations", {}).get("mrr"):
            sys.exit(0)
        else:
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"❌ Error: Test data file not found: {e}")
        print("\nCreate test data files:")
        print(f"  {args.queries}")
        print(f"  {args.ground_truth}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
