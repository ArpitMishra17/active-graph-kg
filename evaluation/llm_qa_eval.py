#!/usr/bin/env python3
"""
LLM Q&A Evaluation - Validate /ask endpoint accuracy, citations, and confidence.

Validates Zhu 2023 + custom claims: LLM answers are accurate and well-cited.

Metrics:
- Answer accuracy (semantic similarity to ground truth)
- Citation precision (% of citations that are relevant)
- Citation recall (% of relevant nodes cited)
- Confidence calibration (correlation between confidence and accuracy)
- Latency (p50, p95, p99)

Expected Results:
- Answer accuracy: >75% (semantic similarity > 0.75)
- Citation precision: >80% (most citations are relevant)
- Citation recall: >60% (misses some relevant nodes)
- Confidence calibration: Pearson r > 0.6 (well-calibrated)
- Latency p95: <2s (with Groq ultra-fast inference)
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any

import numpy as np
import requests


def semantic_similarity(text1: str, text2: str) -> float:
    """Calculate semantic similarity between two texts.

    Simple word overlap baseline. For production, use sentence-transformers.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity score (0.0-1.0)
    """
    # Simple word-level overlap (replace with sentence-transformers in production)
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union if union > 0 else 0.0


def evaluate_llm_qa(
    api_url: str, qa_dataset: list[dict[str, Any]], timeout: int = 30
) -> dict[str, Any]:
    """Evaluate LLM Q&A endpoint.

    Args:
        api_url: Base API URL
        qa_dataset: List of QA items with question, answer, relevant_node_ids
        timeout: Request timeout in seconds

    Returns:
        Dict with evaluation metrics
    """
    print("=" * 70)
    print("LLM Q&A EVALUATION")
    print("=" * 70)
    print(f"API URL: {api_url}")
    print(f"Test questions: {len(qa_dataset)}")
    print()

    results = []
    latencies = []

    for idx, item in enumerate(qa_dataset, 1):
        question = item["question"]
        ground_truth_answer = item.get("answer", "")
        relevant_nodes = set(item.get("relevant_node_ids", []))

        print(f"[{idx}/{len(qa_dataset)}] {question[:60]}...")

        try:
            # Call /ask endpoint
            start_time = time.time()
            resp = requests.post(
                f"{api_url}/ask",
                json={"question": question, "max_results": 5, "use_weighted_score": True},
                timeout=timeout,
            )
            latency = time.time() - start_time
            latencies.append(latency)

            if resp.status_code != 200:
                print(f"  ⚠ Error: HTTP {resp.status_code}")
                continue

            data = resp.json()
            answer = data.get("answer", "")
            citations = data.get("citations", [])
            confidence = data.get("confidence", 0.0)

            # Measure answer accuracy (semantic similarity to ground truth)
            accuracy = (
                semantic_similarity(answer, ground_truth_answer) if ground_truth_answer else None
            )

            # Extract cited node IDs
            cited_nodes = {c["node_id"] for c in citations}

            # Calculate citation precision and recall
            if cited_nodes and relevant_nodes:
                true_positives = len(cited_nodes & relevant_nodes)
                precision = true_positives / len(cited_nodes) if cited_nodes else 0.0
                recall = true_positives / len(relevant_nodes) if relevant_nodes else 0.0
            else:
                precision = None
                recall = None

            results.append(
                {
                    "question": question,
                    "answer": answer[:100] + "..." if len(answer) > 100 else answer,
                    "accuracy": accuracy,
                    "citation_precision": precision,
                    "citation_recall": recall,
                    "confidence": confidence,
                    "latency": latency,
                    "num_citations": len(citations),
                    "cited_nodes": list(cited_nodes),
                    "relevant_nodes": list(relevant_nodes),
                }
            )

            # Print summary
            acc_str = f"{accuracy:.2f}" if accuracy is not None else "N/A"
            prec_str = f"{precision:.2f}" if precision is not None else "N/A"
            rec_str = f"{recall:.2f}" if recall is not None else "N/A"
            print(
                f"  ✓ Acc: {acc_str}, Prec: {prec_str}, Rec: {rec_str}, Conf: {confidence:.2f}, Lat: {latency:.2f}s"
            )

        except requests.Timeout:
            print(f"  ⚠ Timeout after {timeout}s")
            continue
        except Exception as e:
            print(f"  ⚠ Error: {e}")
            continue

    print()

    # Aggregate metrics
    accuracies = [r["accuracy"] for r in results if r["accuracy"] is not None]
    precisions = [r["citation_precision"] for r in results if r["citation_precision"] is not None]
    recalls = [r["citation_recall"] for r in results if r["citation_recall"] is not None]
    confidences = [r["confidence"] for r in results]

    # Calculate confidence calibration (Pearson correlation)
    if len(accuracies) > 3 and len(confidences) > 3:
        corr_pairs = [
            (results[i]["accuracy"], results[i]["confidence"])
            for i in range(len(results))
            if results[i]["accuracy"] is not None
        ]
        if len(corr_pairs) > 3:
            accs, confs = zip(*corr_pairs, strict=False)
            confidence_calibration = np.corrcoef(accs, confs)[0, 1]
        else:
            confidence_calibration = None
    else:
        confidence_calibration = None

    # Calculate latency percentiles
    if latencies:
        p50 = np.percentile(latencies, 50)
        p95 = np.percentile(latencies, 95)
        p99 = np.percentile(latencies, 99)
    else:
        p50 = p95 = p99 = None

    # Report results
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"Questions evaluated: {len(results)}")
    print()
    print("Answer Accuracy:")
    print(f"  Mean:   {np.mean(accuracies):.3f}" if accuracies else "  Mean:   N/A")
    print(f"  Median: {np.median(accuracies):.3f}" if accuracies else "  Median: N/A")
    print(f"  Std:    {np.std(accuracies):.3f}" if accuracies else "  Std:    N/A")
    print()
    print("Citation Metrics:")
    print(f"  Precision: {np.mean(precisions):.3f}" if precisions else "  Precision: N/A")
    print(f"  Recall:    {np.mean(recalls):.3f}" if recalls else "  Recall:    N/A")
    print()
    print("Confidence:")
    print(f"  Mean:        {np.mean(confidences):.3f}" if confidences else "  Mean:        N/A")
    print(
        f"  Calibration: {confidence_calibration:.3f}"
        if confidence_calibration is not None
        else "  Calibration: N/A"
    )
    print()
    print("Latency:")
    print(f"  p50: {p50:.2f}s" if p50 else "  p50: N/A")
    print(f"  p95: {p95:.2f}s" if p95 else "  p95: N/A")
    print(f"  p99: {p99:.2f}s" if p99 else "  p99: N/A")
    print()

    # Check against expected results
    avg_accuracy = np.mean(accuracies) if accuracies else 0.0
    avg_precision = np.mean(precisions) if precisions else 0.0
    avg_recall = np.mean(recalls) if recalls else 0.0

    accuracy_good = avg_accuracy >= 0.75
    precision_good = avg_precision >= 0.80
    recall_good = avg_recall >= 0.60
    calibration_good = confidence_calibration is not None and confidence_calibration >= 0.6
    latency_good = p95 is not None and p95 <= 2.0

    accuracy_status = "✅" if accuracy_good else "⚠"
    precision_status = "✅" if precision_good else "⚠"
    recall_status = "✅" if recall_good else "⚠"
    calibration_status = "✅" if calibration_good else "⚠"
    latency_status = "✅" if latency_good else "⚠"

    print("Expected vs Actual (Zhu 2023 + Custom):")
    print(f"{accuracy_status} Answer accuracy:    {avg_accuracy:.1%} (target: >75%)")
    print(f"{precision_status} Citation precision: {avg_precision:.1%} (target: >80%)")
    print(f"{recall_status} Citation recall:    {avg_recall:.1%} (target: >60%)")
    if confidence_calibration is not None:
        print(
            f"{calibration_status} Confidence calib:   {confidence_calibration:.3f} (target: >0.6)"
        )
    if p95 is not None:
        print(f"{latency_status} Latency p95:        {p95:.2f}s (target: <2s)")
    print("=" * 70)

    return {
        "results": results,
        "summary": {
            "num_questions": len(results),
            "accuracy": {
                "mean": float(np.mean(accuracies)) if accuracies else None,
                "median": float(np.median(accuracies)) if accuracies else None,
                "std": float(np.std(accuracies)) if accuracies else None,
            },
            "citation_precision": {"mean": float(np.mean(precisions)) if precisions else None},
            "citation_recall": {"mean": float(np.mean(recalls)) if recalls else None},
            "confidence": {
                "mean": float(np.mean(confidences)) if confidences else None,
                "calibration": float(confidence_calibration)
                if confidence_calibration is not None
                else None,
            },
            "latency": {
                "p50": float(p50) if p50 else None,
                "p95": float(p95) if p95 else None,
                "p99": float(p99) if p99 else None,
            },
        },
        "meets_expectations": {
            "accuracy": accuracy_good,
            "precision": precision_good,
            "recall": recall_good,
            "calibration": calibration_good,
            "latency": latency_good,
        },
    }


def load_qa_dataset(filepath: str) -> list[dict[str, Any]]:
    """Load Q&A dataset from JSON or JSONL file."""
    qa_items = []

    with open(filepath) as f:
        # Try JSON first
        try:
            data = json.load(f)
            if isinstance(data, list):
                qa_items = data
            else:
                qa_items = [data]
        except json.JSONDecodeError:
            # Try JSONL
            f.seek(0)
            for line in f:
                line = line.strip()
                if line:
                    qa_items.append(json.loads(line))

    return qa_items


def main():
    parser = argparse.ArgumentParser(description="LLM Q&A Evaluation")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument(
        "--dataset",
        default="evaluation/datasets/qa_questions.json",
        help="Q&A dataset (JSON or JSONL)",
    )
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds")
    parser.add_argument(
        "--output", default="evaluation/llm_qa_results.json", help="Output JSON file"
    )
    args = parser.parse_args()

    try:
        # Check if /ask endpoint is available
        resp = requests.get(f"{args.api_url}/health", timeout=5)
        if resp.status_code != 200:
            print(f"⚠ Warning: API health check failed (HTTP {resp.status_code})")

        # Load Q&A dataset
        qa_dataset = load_qa_dataset(args.dataset)
        print(f"Loaded {len(qa_dataset)} Q&A items from {args.dataset}\n")

        # Run evaluation
        results = evaluate_llm_qa(args.api_url, qa_dataset, timeout=args.timeout)

        # Save results
        results["timestamp"] = datetime.now().isoformat()
        results["config"] = {
            "api_url": args.api_url,
            "dataset": args.dataset,
            "timeout": args.timeout,
        }

        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Results saved to {args.output}")

        # Exit with appropriate code
        meets_all = all(results.get("meets_expectations", {}).values())
        sys.exit(0 if meets_all else 1)

    except FileNotFoundError as e:
        print(f"❌ Error: Dataset file not found: {e}")
        print(f"\nCreate dataset file: {args.dataset}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Cannot connect to API at {args.api_url}")
        print("\nMake sure the API server is running.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
