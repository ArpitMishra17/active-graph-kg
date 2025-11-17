#!/usr/bin/env python3
"""
Generate test_queries.json, ground_truth.json, and qa_questions.json from id_map.json and seed_nodes.json.

Usage:
  python3 evaluation/generate_test_data.py
"""

import json
from pathlib import Path

EVAL_DIR = Path(__file__).parent
DATASETS_DIR = EVAL_DIR / "datasets"


def load_json(file_path: Path) -> dict | list:
    with open(file_path) as f:
        return json.load(f)


def save_json(data, file_path: Path):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def generate_test_queries_and_ground_truth():
    """Generate test queries and ground truth based on seed data."""

    # Load seed nodes and id_map
    _seed_nodes = load_json(DATASETS_DIR / "seed_nodes.json")
    id_map = load_json(DATASETS_DIR / "id_map.json")

    # Define queries based on our diverse seed data
    queries_and_truth = [
        # Product queries
        ("wireless headphones noise canceling", ["product-001"]),
        ("4K television OLED smart TV", ["product-002"]),
        ("ergonomic office chair lumbar support", ["product-003"]),
        # Article queries
        ("transformer attention mechanism NLP", ["article-001"]),
        ("vector database semantic search pgvector", ["article-002"]),
        ("kubernetes autoscaling microservices", ["article-003"]),
        # Support ticket queries
        ("slow page load performance issue", ["ticket-001"]),
        ("payment failure stripe timeout", ["ticket-002"]),
        ("password reset email not received", ["ticket-003"]),
        # Resume queries (job matching)
        ("Senior Java engineer Spring Boot microservices", ["resume-001", "resume-007"]),
        ("Data scientist machine learning PyTorch", ["resume-002", "resume-006"]),
        ("Backend engineer Go microservices PostgreSQL", ["resume-007", "resume-003"]),
        ("DevOps Kubernetes Docker cloud infrastructure", ["resume-004"]),
        ("SRE observability Prometheus Grafana", ["resume-005"]),
        ("Machine learning vector database pgvector", ["resume-006"]),
        ("Full-stack React Node.js JavaScript", ["resume-003"]),
        ("Product manager B2B SaaS enterprise", ["resume-008"]),
        ("UX designer mobile app Figma", ["resume-009"]),
        ("Security engineer penetration testing OWASP", ["resume-010"]),
        # Job queries (candidate matching)
        ("hiring senior java engineer AWS cloud", ["job-001", "job-007"]),
        ("ML engineer NLP LLM transformer models", ["job-002"]),
        ("backend go kafka event-driven systems", ["job-003"]),
        ("SRE position metrics alerting on-call", ["job-004"]),
        ("data platform vector search embeddings RAG", ["job-005"]),
        ("full-stack react typescript GraphQL", ["job-006"]),
        ("devops terraform kubernetes CI/CD", ["job-007"]),
        ("product manager API data analytics", ["job-008"]),
        ("UX designer mobile accessibility", ["job-009"]),
        ("security application pentesting automation", ["job-010"]),
    ]

    # Generate test_queries.json
    test_queries = [q for q, _ in queries_and_truth]
    save_json(test_queries, DATASETS_DIR / "test_queries.json")
    print(f"✓ Generated {len(test_queries)} test queries")

    # Generate ground_truth.json with UUIDs
    ground_truth = {}
    for query, external_ids in queries_and_truth:
        # Map external IDs to UUIDs
        uuids = [id_map[ext_id] for ext_id in external_ids if ext_id in id_map]
        if uuids:  # Only include if we have mapped UUIDs
            ground_truth[query] = uuids

    save_json(ground_truth, DATASETS_DIR / "ground_truth.json")
    print(f"✓ Generated ground truth for {len(ground_truth)} queries")


def generate_qa_questions():
    """Generate QA questions based on seed data."""

    id_map = load_json(DATASETS_DIR / "id_map.json")

    # Define QA questions spanning all domains
    qa_questions = [
        {
            "question": "What wireless headphones products are available?",
            "answer": "Wireless Noise-Canceling Headphones with 30-hour battery life, Bluetooth 5.0, and Active Noise Cancellation technology.",
            "relevant_node_ids": [id_map.get("product-001", "")],
        },
        {
            "question": "Tell me about recent advances in transformer architectures.",
            "answer": "Recent advances cover attention mechanisms, positional encodings, and scaling laws. Major architectures include BERT, GPT, and T5.",
            "relevant_node_ids": [id_map.get("article-001", "")],
        },
        {
            "question": "What are the current payment processing issues?",
            "answer": "Payment processing failures with error code PAYMENT_GATEWAY_TIMEOUT affecting 2% of checkout attempts using Stripe.",
            "relevant_node_ids": [id_map.get("ticket-002", "")],
        },
        {
            "question": "Who has Java and Spring Boot experience?",
            "answer": "Senior Java Engineer with 8+ years building microservices using Spring Boot, Hibernate, and AWS.",
            "relevant_node_ids": [id_map.get("resume-001", "")],
        },
        {
            "question": "What ML engineer positions are open?",
            "answer": "Looking for ML Engineer to improve NLP pipelines and LLM-based features with PyTorch and transformer models.",
            "relevant_node_ids": [id_map.get("job-002", "")],
        },
        {
            "question": "What vector database technologies are discussed?",
            "answer": "Comprehensive guide covering pgvector, FAISS, Pinecone, and Weaviate with performance benchmarks for RAG applications.",
            "relevant_node_ids": [id_map.get("article-002", "")],
        },
        {
            "question": "Who specializes in Kubernetes and cloud infrastructure?",
            "answer": "DevOps Engineer with expertise in Kubernetes, Docker, Terraform, and multi-cloud deployments on AWS and GCP.",
            "relevant_node_ids": [id_map.get("resume-004", "")],
        },
        {
            "question": "What are the main performance issues reported?",
            "answer": "Slow page load times during peak hours (2-4 PM EST) with 5-10 second delays when filtering search results.",
            "relevant_node_ids": [id_map.get("ticket-001", "")],
        },
        {
            "question": "What SRE positions need metrics and monitoring experience?",
            "answer": "SRE position building metrics and alerting infrastructure with Prometheus and Grafana, including on-call rotations.",
            "relevant_node_ids": [id_map.get("job-004", "")],
        },
        {
            "question": "What products support voice control?",
            "answer": "4K Ultra HD Smart Television with voice control via Alexa and Google Assistant, plus built-in streaming apps.",
            "relevant_node_ids": [id_map.get("product-002", "")],
        },
    ]

    # Filter out questions with missing node IDs
    qa_questions = [q for q in qa_questions if all(q["relevant_node_ids"])]

    save_json(qa_questions, DATASETS_DIR / "qa_questions.json")
    print(f"✓ Generated {len(qa_questions)} QA questions")


def main():
    print("Generating test data from seed_nodes.json and id_map.json...")
    print()

    # Check if id_map exists
    if not (DATASETS_DIR / "id_map.json").exists():
        print("ERROR: id_map.json not found. Run seed_demo.py with --from-file first.")
        return 1

    generate_test_queries_and_ground_truth()
    generate_qa_questions()

    print()
    print("✅ Test data generation complete!")
    print("   - evaluation/datasets/test_queries.json")
    print("   - evaluation/datasets/ground_truth.json")
    print("   - evaluation/datasets/qa_questions.json")

    return 0


if __name__ == "__main__":
    exit(main())
