# Testing Guide - Active Graph KG

**Last Updated:** 2025-11-19

---

## Overview

Active Graph KG has a comprehensive test suite covering unit tests, integration tests, and end-to-end scenarios. Tests are designed to run both locally (with or without database) and in CI/CD pipelines.

---

## Test Modes

### Mode 1: Unit Tests (No Database Required)

Run lightweight unit tests without needing Postgres/pgvector:

```bash
# Set test mode flag to defer DB connections
export ACTIVEKG_TEST_NO_DB=true
export JWT_ENABLED=false  # Optional: disable JWT for simpler testing

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run unit tests
pytest tests/test_security_limits.py -v
pytest tests/test_connector_config_validation.py -v
```

**What this does:**
- Defers repository initialization at app import time
- Allows testing of validation logic, error handling, route extraction
- Tests use mocks for database-dependent components
- Fast execution (~1-2 seconds)

**Best for:**
- Local development without Docker
- Quick validation of logic changes
- CI jobs that don't need full integration testing

---

### Mode 2: Integration Tests (Database Required)

Run full integration tests with real Postgres + pgvector:

```bash
# Start Postgres with pgvector
docker run -d \
  --name activekg-pg \
  -e POSTGRES_USER=activekg \
  -e POSTGRES_PASSWORD=activekg \
  -e POSTGRES_DB=activekg \
  -p 5432:5432 \
  ankane/pgvector

# Enable vector extension
psql postgresql://activekg:activekg@localhost:5432/activekg \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Initialize schema
psql postgresql://activekg:activekg@localhost:5432/activekg \
  -f db/init.sql

# Set DSN (disables test mode automatically)
export ACTIVEKG_DSN=postgresql://activekg:activekg@localhost:5432/activekg
unset ACTIVEKG_TEST_NO_DB  # Ensure test mode is off

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run all tests
pytest -v

# Or run specific test suites
pytest tests/test_phase1_complete.py -v
pytest tests/test_jwt_rls_complete.py -v
pytest tests/test_golden_queries.py -v
```

**What this does:**
- Initializes full repository with real database connection
- Tests actual database operations (vector search, RLS, lineage)
- Validates end-to-end workflows
- Slower execution (~30-60 seconds)

**Best for:**
- Pre-commit validation
- CI/CD pipelines with services
- Testing database-specific features (RLS, vector search, triggers)

---

### Mode 3: Lightweight Wrapper

Use the provided test runner script:

```bash
# Runs basic smoke tests with gating logic
./run_tests.sh

# Or use pytest directly
pytest -q  # Quiet mode, full suite
```

---

## Quick Test (No Database)

For rapid local testing without any infrastructure:

```bash
# In your terminal
export ACTIVEKG_TEST_NO_DB=true
export JWT_ENABLED=false

# Install minimal deps in venv
python3 -m venv venv && source venv/bin/activate
pip install pytest fastapi starlette pydantic

# Run unit tests
pytest tests/test_security_limits.py -v
```

This will test:
- Security limits endpoint (mocked)
- Pydantic validation logic
- Route name extraction
- Error categorization

**Expected output:**
```
tests/test_security_limits.py::TestSecurityLimitsEndpoint::test_security_limits_default_config PASSED
tests/test_security_limits.py::TestPydanticValidation::test_s3_config_validation_valid PASSED
...
================== 17 passed in 1.23s ==================
```

---

## Test Organization

### Directory Structure

```
tests/
├── test_security_limits.py          # Unit: Security endpoints, validation
├── test_phase1_complete.py           # Integration: Core MVP features
├── test_phase1_plus.py               # Integration: Phase 1+ improvements
├── test_jwt_rls_complete.py          # Integration: JWT + RLS end-to-end
├── test_golden_queries.py            # Integration: Retrieval quality
├── test_drive_connector_smoke.py     # Integration: Drive connector
├── test_scoring_modes.py             # Integration: Hybrid search scoring
└── conftest.py                       # Shared fixtures
```

---

## Troubleshooting

### Issue: Import hangs or times out

**Cause:** Repository trying to connect to database at import time

**Solution:** Set test mode flag **before** importing:
```python
import os
os.environ["ACTIVEKG_TEST_NO_DB"] = "true"

# Now safe to import
from activekg.api.main import app
```

### Issue: Tests fail with "connection refused"

**Cause:** Postgres not running or wrong DSN

**Solution:**
```bash
# Check if Postgres is running
docker ps | grep activekg-pg

# Verify connection
psql $ACTIVEKG_DSN -c "SELECT 1;"

# Start Postgres if needed
docker run -d --name activekg-pg -e POSTGRES_USER=activekg \
  -e POSTGRES_PASSWORD=activekg -e POSTGRES_DB=activekg \
  -p 5432:5432 ankane/pgvector
```

### Issue: Module not found errors

**Cause:** Missing dependencies

**Solution:**
```bash
# Install all requirements
pip install -r requirements.txt

# Or minimal for unit tests
pip install pytest fastapi starlette pydantic prometheus-client
```

---

## Running in CI/CD

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
jobs:
  unit-tests:
    name: Unit Tests (No DB)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: 3.11
          cache: 'pip'
      - run: pip install -r requirements.txt
      - name: Run unit tests
        env:
          ACTIVEKG_TEST_NO_DB: "true"
          JWT_ENABLED: "false"
        run: pytest tests/test_security_limits.py -v

  integration-tests:
    name: Integration Tests (With DB)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: activekg
          POSTGRES_PASSWORD: activekg
          POSTGRES_DB: activekg
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - name: Initialize DB
        run: |
          psql -h localhost -U activekg -d activekg \
            -c "CREATE EXTENSION IF NOT EXISTS vector;"
          psql -h localhost -U activekg -d activekg -f db/init.sql
        env:
          PGPASSWORD: activekg
      - name: Run integration tests
        env:
          ACTIVEKG_DSN: postgresql://activekg:activekg@localhost:5432/activekg
        run: pytest tests/ -v
```

---

## Writing New Tests

### Unit Test Template (No DB)

```python
"""test_my_feature.py"""
import os

# Set test mode BEFORE importing app
os.environ["ACTIVEKG_TEST_NO_DB"] = "true"

import pytest
from activekg.my_module import my_function


def test_my_function_valid():
    """Test function with valid input."""
    assert my_function("valid") == "expected"


def test_my_function_invalid():
    """Test function with invalid input."""
    with pytest.raises(ValueError):
        my_function("invalid")
```

### Integration Test Template (Requires DB)

```python
"""test_my_integration.py"""
import pytest
from activekg.graph.repository import GraphRepository


@pytest.fixture
def repo():
    """Provide repository instance."""
    import os
    dsn = os.getenv("ACTIVEKG_DSN")
    if not dsn:
        pytest.skip("ACTIVEKG_DSN not set")
    return GraphRepository(dsn)


def test_database_operation(repo):
    """Test actual DB operation."""
    node = repo.create_node(
        classes=["Test"],
        props={"value": 42},
        tenant_id="test"
    )
    assert node.id is not None
```

---

## Best Practices

### 1. Set Test Mode Early
```python
# ✅ Good: Before any imports
import os
os.environ["ACTIVEKG_TEST_NO_DB"] = "true"
from activekg.api.main import app

# ❌ Bad: After imports (too late!)
from activekg.api.main import app
os.environ["ACTIVEKG_TEST_NO_DB"] = "true"
```

### 2. Use Descriptive Names
```python
# ✅ Good
def test_s3_config_validation_rejects_short_access_key():
    ...

# ❌ Bad
def test_config():
    ...
```

### 3. Test Both Paths
```python
def test_valid_config_accepted():
    """Happy path."""
    ...

def test_invalid_config_rejected():
    """Error path."""
    ...
```

---

## Test Coverage

| Category | Target | Status |
|----------|--------|--------|
| Unit Tests | 90%+ | ✅ ~85% |
| Integration | 80%+ | ✅ ~80% |
| API Endpoints | 100% | ✅ ~95% |
| Critical Paths | 100% | ✅ 100% |

---

## References

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
