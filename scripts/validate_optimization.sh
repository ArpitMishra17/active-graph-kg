#!/bin/bash
# Validate that all optimization phases are properly implemented

set -e

echo "=================================================================="
echo "Active Graph KG - Optimization Implementation Validator"
echo "=================================================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0
WARNING=0

check_file() {
    local file=$1
    local description=$2
    
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $description"
        echo -e "  Location: $file"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        echo -e "  Expected: $file"
        ((FAILED++))
        return 1
    fi
}

check_function() {
    local file=$1
    local pattern=$2
    local description=$3
    
    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $description"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        echo -e "  Pattern not found: $pattern in $file"
        ((FAILED++))
        return 1
    fi
}

check_env_var() {
    local file=$1
    local var=$2
    local description=$3
    
    if grep -q "^${var}=" "$file" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $description"
        ((PASSED++))
        return 0
    else
        echo -e "${YELLOW}⚠${NC} $description"
        echo -e "  Variable: $var not found in $file"
        ((WARNING++))
        return 1
    fi
}

echo "Phase 1: Seed & Coverage"
echo "-----------------------------------"
check_file "evaluation/datasets/seed_nodes.json" "Seed dataset exists"
check_file "evaluation/datasets/seed_with_jwt.py" "Seed script with JWT auth"
check_function "evaluation/datasets/seed_with_jwt.py" "def verify_search_sanity" "Coverage verification function"
check_function "evaluation/datasets/seed_with_jwt.py" "def verify_retrieval" "Retrieval validation function"
check_function "evaluation/datasets/seed_with_jwt.py" "def admin_refresh" "Admin refresh function"
echo ""

echo "Phase 2: Retrieval Tuning"
echo "-----------------------------------"
check_file ".env.eval" "Evaluation environment configuration"
check_env_var ".env.eval" "ASK_SIM_THRESHOLD" "Similarity threshold configured"
check_env_var ".env.eval" "ASK_MAX_SNIPPETS" "Max snippets configured"
check_env_var ".env.eval" "HYBRID_RERANKER_CANDIDATES" "Reranker candidates configured"
check_env_var ".env.eval" "ASK_USE_RERANKER" "Reranker enabled"
echo ""

echo "Phase 3: LLM Prompt & Routing"
echo "-----------------------------------"
check_file "activekg/engine/llm_provider.py" "LLM provider module"
check_function "activekg/engine/llm_provider.py" "def build_strict_citation_prompt" "Strict citation prompt function"
check_function "activekg/engine/llm_provider.py" "CITATION RULES" "Citation rules in prompt"
check_function "activekg/engine/llm_provider.py" "ACCURACY RULES" "Accuracy rules in prompt"
echo ""

echo "Phase 4: Observability & Guardrails"
echo "-----------------------------------"
check_function "activekg/api/main.py" "@app.get.*debug/dbinfo" "Debug /debug/dbinfo endpoint"
check_function "activekg/api/main.py" "@app.get.*debug/search_sanity" "Debug /debug/search_sanity endpoint"
check_function "activekg/api/main.py" "X-RateLimit-" "Rate limit headers"
echo ""

echo "Phase 5: E2E & Evaluation"
echo "-----------------------------------"
check_file "scripts/e2e_api_smoke.py" "E2E smoke test script"
check_file "tests/test_e2e_retrieval.py" "E2E retrieval tests"
check_function "tests/test_e2e_retrieval.py" "def test_vector_search_returns_results" "Vector search test"
check_function "tests/test_e2e_retrieval.py" "def test_hybrid_search_returns_results" "Hybrid search test"
check_function "tests/test_e2e_retrieval.py" "def test_ask_includes_citations" "Citation validation test"
check_file "evaluation/run_all.sh" "Evaluation harness runner"
echo ""

echo "Phase 6: CI/CD Integration"
echo "-----------------------------------"
check_file ".github/workflows/ci.yml" "CI/CD pipeline configuration"
check_function ".github/workflows/ci.yml" "integration-tests:" "Integration tests job"
check_function ".github/workflows/ci.yml" "postgres:" "PostgreSQL service"
check_function ".github/workflows/ci.yml" "redis:" "Redis service"
check_function ".github/workflows/ci.yml" "seed_with_jwt.py" "Seeding step in CI"
check_function ".github/workflows/ci.yml" "test_e2e_retrieval.py" "E2E test execution"
echo ""

echo "Phase 7: Production Hardening"
echo "-----------------------------------"
check_file "PRODUCTION_OPTIMIZATION_GUIDE.md" "Production optimization guide"
check_function "PRODUCTION_OPTIMIZATION_GUIDE.md" "JWT Authentication" "JWT configuration docs"
check_function "PRODUCTION_OPTIMIZATION_GUIDE.md" "Redis Configuration" "Redis hardening docs"
check_function "PRODUCTION_OPTIMIZATION_GUIDE.md" "Scheduler Configuration" "Scheduler docs"
check_function "PRODUCTION_OPTIMIZATION_GUIDE.md" "Troubleshooting" "Troubleshooting section"
echo ""

echo "Additional Checks"
echo "-----------------------------------"
check_file "evaluation/datasets/ground_truth.json" "Ground truth dataset"
check_file "evaluation/datasets/qa_questions.json" "QA questions dataset"
check_file "db/migrations/add_text_search.sql" "Text search migration"
check_file "enable_rls_policies.sql" "RLS policies"
echo ""

echo "=================================================================="
echo "Validation Summary"
echo "=================================================================="
echo -e "${GREEN}Passed:${NC}  $PASSED"
echo -e "${YELLOW}Warnings:${NC} $WARNING"
echo -e "${RED}Failed:${NC}  $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All critical components implemented successfully!${NC}"
    echo ""
    echo "Next Steps:"
    echo "  1. Load evaluation config: set -a; source .env.eval; set +a"
    echo "  2. Start API: uvicorn activekg.api.main:app --reload"
    echo "  3. Seed data: python3 evaluation/datasets/seed_with_jwt.py"
    echo "  4. Run tests: pytest tests/test_e2e_retrieval.py -v"
    echo "  5. Run CI: git push (triggers .github/workflows/ci.yml)"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some components are missing. Please review the failed checks above.${NC}"
    exit 1
fi
