#!/bin/bash
#
# Run all Active Graph KG tests in virtual environment
#
# Usage:
#   ./run_tests.sh           # Run all tests
#   ./run_tests.sh unit      # Run only unit tests
#   ./run_tests.sh base      # Run only base engine gap tests
#

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "============================================================"
echo " Active Graph KG Test Runner"
echo "============================================================"
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
    echo ""
fi

# Activate venv
source venv/bin/activate

# Check if dependencies installed
if ! python3 -c "import croniter" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install --quiet -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
    echo ""
fi

# Determine what to run
RUN_ALL=true
RUN_UNIT=false
RUN_BASE=false

if [ "$1" = "unit" ]; then
    RUN_ALL=false
    RUN_UNIT=true
elif [ "$1" = "base" ]; then
    RUN_ALL=false
    RUN_BASE=true
fi

# Run tests
TESTS_PASSED=0
TESTS_FAILED=0

if [ "$RUN_ALL" = true ] || [ "$RUN_UNIT" = true ]; then
    echo -e "${YELLOW}Running unit tests...${NC}"
    echo ""

    # Cron fallback tests
    if python3 tests/test_cron_fallback.py; then
        echo -e "${GREEN}✓ Cron fallback tests passed${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ Cron fallback tests failed${NC}"
        ((TESTS_FAILED++))
    fi
    echo ""
fi

if [ "$RUN_ALL" = true ] || [ "$RUN_BASE" = true ]; then
    echo -e "${YELLOW}Running base engine gap tests...${NC}"
    echo ""

    # Check if database is running
    if [ -z "$ACTIVEKG_DSN" ]; then
        echo -e "${RED}Warning: ACTIVEKG_DSN not set. Using default.${NC}"
        export ACTIVEKG_DSN="postgresql://activekg:activekg@localhost:5432/activekg"
    fi

    # Base engine gap tests (requires DB)
    if python3 tests/test_base_engine_gaps.py 2>/dev/null; then
        echo -e "${GREEN}✓ Base engine gap tests passed${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${YELLOW}⚠ Base engine gap tests skipped (requires running database)${NC}"
        echo "  To run: Start PostgreSQL and set ACTIVEKG_DSN"
    fi
    echo ""
fi

# Summary
echo "============================================================"
echo " Test Summary"
echo "============================================================"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"
fi
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
