#!/usr/bin/env python3
"""
Freshness SLA Monitor - Track % of nodes refreshed within their SLA.

Metrics:
- % nodes refreshed on time (within 1.0x interval)
- % nodes at risk (1.0-1.5x interval)
- % nodes overdue (>1.5x interval)
- Average lag ratio (actual_lag / expected_interval)

SLA Target:
- >95% nodes refreshed on time
- <2% nodes overdue
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Any

import requests


def monitor_freshness_sla(api_url: str) -> dict[str, Any]:
    """Monitor freshness SLA for all nodes with refresh policies.

    Args:
        api_url: Base API URL

    Returns:
        Dict with SLA metrics
    """
    print("=" * 70)
    print("FRESHNESS SLA MONITOR")
    print("=" * 70)
    print(f"API URL: {api_url}")
    print()

    # Use scheduler_lag anomaly detector to find overdue nodes
    print("Querying scheduler lag anomalies...")
    resp = requests.get(
        f"{api_url}/admin/anomalies",
        params={
            "types": "scheduler_lag",
            "scheduler_lag_multiplier": 1.0,  # Find all nodes, even slightly late
        },
    )
    resp.raise_for_status()
    data = resp.json()

    scheduler_lag_anomalies = data.get("anomalies", {}).get("scheduler_lag", [])

    # Categorize nodes by lag ratio
    on_time = []
    at_risk = []
    overdue = []

    for anomaly in scheduler_lag_anomalies:
        lag_ratio = anomaly["lag_ratio"]

        if lag_ratio < 1.0:
            on_time.append(anomaly)
        elif lag_ratio < 1.5:
            at_risk.append(anomaly)
        else:
            overdue.append(anomaly)

    # Calculate totals
    # Note: This only includes nodes with refresh_policy that are tracked
    total_nodes = len(scheduler_lag_anomalies)

    # If no anomalies detected with multiplier=1.0, all nodes are on time
    # But we don't know the actual total count without querying all nodes
    # So we use the anomaly count as a proxy

    if total_nodes == 0:
        print("⚠ No nodes with refresh_policy found or all are perfectly on time.\n")
        on_time_pct = 100.0
        at_risk_pct = 0.0
        overdue_pct = 0.0
    else:
        on_time_pct = len(on_time) / total_nodes * 100
        at_risk_pct = len(at_risk) / total_nodes * 100
        overdue_pct = len(overdue) / total_nodes * 100

    # Calculate average lag ratio
    if scheduler_lag_anomalies:
        lag_ratios = [
            a["lag_ratio"]
            for a in scheduler_lag_anomalies
            if isinstance(a["lag_ratio"], (int, float))
        ]
        avg_lag_ratio = sum(lag_ratios) / len(lag_ratios) if lag_ratios else 0.0
    else:
        avg_lag_ratio = 1.0  # Assume on time if no data

    # Report results
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total nodes tracked: {total_nodes}")
    print()
    print(f"On-time (lag < 1.0x):  {len(on_time):4d} ({on_time_pct:.1f}%)")
    print(f"At-risk (1.0x-1.5x):   {len(at_risk):4d} ({at_risk_pct:.1f}%)")
    print(f"Overdue (> 1.5x):      {len(overdue):4d} ({overdue_pct:.1f}%)")
    print()
    print(f"Average lag ratio:     {avg_lag_ratio:.2f}x")
    print()

    # Check against SLA targets
    meets_on_time_target = on_time_pct >= 95.0
    meets_overdue_target = overdue_pct <= 2.0

    on_time_status = "✅" if meets_on_time_target else "⚠"
    overdue_status = "✅" if meets_overdue_target else "⚠"

    print("SLA Targets:")
    print(f"{on_time_status} On-time rate:  {on_time_pct:.1f}% (target: >95%)")
    print(f"{overdue_status} Overdue rate:  {overdue_pct:.1f}% (target: <2%)")
    print("=" * 70)

    # List worst offenders (top 10 most overdue)
    if overdue:
        print("\nTop 10 Most Overdue Nodes:")
        overdue_sorted = sorted(overdue, key=lambda x: x["lag_ratio"], reverse=True)
        for i, node in enumerate(overdue_sorted[:10], 1):
            node_id = node["node_id"][:20]  # Truncate ID
            lag_ratio = node["lag_ratio"]
            expected = node.get("expected_interval_seconds", 0) / 60  # Convert to minutes
            print(f"  {i}. {node_id}... (lag: {lag_ratio:.2f}x, interval: {expected:.0f}m)")

    return {
        "total_nodes": total_nodes,
        "on_time": len(on_time),
        "at_risk": len(at_risk),
        "overdue": len(overdue),
        "on_time_percent": on_time_pct,
        "at_risk_percent": at_risk_pct,
        "overdue_percent": overdue_pct,
        "avg_lag_ratio": avg_lag_ratio,
        "meets_sla": {
            "on_time_target": meets_on_time_target,
            "overdue_target": meets_overdue_target,
        },
        "worst_offenders": [
            {
                "node_id": n["node_id"],
                "lag_ratio": n["lag_ratio"],
                "expected_interval_seconds": n.get("expected_interval_seconds"),
                "last_refreshed": n.get("last_refreshed"),
            }
            for n in sorted(overdue, key=lambda x: x["lag_ratio"], reverse=True)[:10]
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Freshness SLA Monitor")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument(
        "--output", default="evaluation/freshness_results.json", help="Output JSON file"
    )
    args = parser.parse_args()

    try:
        # Run monitoring
        results = monitor_freshness_sla(args.api_url)

        # Save results
        output = {
            "results": results,
            "timestamp": datetime.now().isoformat(),
            "config": {"api_url": args.api_url},
        }

        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n✓ Results saved to {args.output}")

        # Exit with appropriate code (all SLAs met)
        meets_all = all(results.get("meets_sla", {}).values())
        sys.exit(0 if meets_all else 1)

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
