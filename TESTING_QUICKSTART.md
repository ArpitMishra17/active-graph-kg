# Testing Quickstart - Active Graph KG

**TL;DR:** Tests now support running **without database** using `ACTIVEKG_TEST_NO_DB=true`

---

## ✅ Run Tests Without Database (New!)

```bash
# Set test mode flag
export ACTIVEKG_TEST_NO_DB=true
export JWT_ENABLED=false

# Create venv and install deps
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run unit tests (no DB needed!)
pytest tests/test_security_limits.py -v
```

**What gets tested:**
- ✅ Security limits endpoint (`/_admin/security/limits`)
- ✅ Pydantic validation for connector configs
- ✅ Route name extraction (low-cardinality metrics)
- ✅ Error categorization logic

**Execution time:** ~1-2 seconds

---

## 🐘 Run Tests With Database (Full Integration)

```bash
# Start Postgres + pgvector
docker run -d --name activekg-pg \
  -e POSTGRES_USER=activekg \
  -e POSTGRES_PASSWORD=activekg \
  -e POSTGRES_DB=activekg \
  -p 5432:5432 \
  ankane/pgvector

# Initialize schema
psql postgresql://activekg:activekg@localhost:5432/activekg \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql postgresql://activekg:activekg@localhost:5432/activekg \
  -f db/init.sql

# Set DSN and run tests
export ACTIVEKG_DSN=postgresql://activekg:activekg@localhost:5432/activekg
unset ACTIVEKG_TEST_NO_DB  # Important: disable test mode

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run full test suite
pytest -v
```

**Execution time:** ~30-60 seconds

---

## 🎯 What Changed

### 1. **Lazy DB Initialization** (`activekg/api/main.py`)

```python
# Before: Eager connection at import (fails without DB)
repo = GraphRepository(DSN, ...)

# After: Conditional initialization
TEST_MODE = os.getenv("ACTIVEKG_TEST_NO_DB", "false").lower() == "true"

if TEST_MODE:
    repo = None  # Defer until needed
else:
    repo = GraphRepository(DSN, ...)  # Normal mode
```

### 2. **Test File Updates** (`tests/test_security_limits.py`)

```python
# Set flag BEFORE importing app
os.environ["ACTIVEKG_TEST_NO_DB"] = "true"
os.environ["JWT_ENABLED"] = "false"

from activekg.api.main import app  # Now safe to import
```

### 3. **Comprehensive Testing Guide** (`docs/development/testing.md`)

- Test modes (unit vs integration)
- Troubleshooting guide
- CI/CD examples
- Best practices

---

## 💡 Use Cases

| Scenario | Test Mode | Database | Speed |
|----------|-----------|----------|-------|
| **Local dev (no Docker)** | `ACTIVEKG_TEST_NO_DB=true` | ❌ Not needed | ⚡ Fast (1-2s) |
| **Pre-commit validation** | Normal | ✅ Required | 🐢 Slow (30-60s) |
| **CI/CD (unit tests)** | `ACTIVEKG_TEST_NO_DB=true` | ❌ Not needed | ⚡ Fast |
| **CI/CD (integration)** | Normal | ✅ Required (service) | 🐢 Slow |

---

## 🐛 Troubleshooting

### Issue: Import hangs/times out

**Cause:** Repository trying to connect to DB at import

**Fix:**
```bash
export ACTIVEKG_TEST_NO_DB=true  # Set BEFORE running tests
```

### Issue: Tests pass locally but fail in CI

**Cause:** Test mode still enabled in CI

**Fix:** Ensure CI doesn't set `ACTIVEKG_TEST_NO_DB=true` for integration tests

---

## 📚 Full Documentation

See [docs/development/testing.md](docs/development/testing.md) for comprehensive guide.

---

## 🎉 Summary

- ✅ **Unit tests** now run without DB (set `ACTIVEKG_TEST_NO_DB=true`)
- ✅ **Integration tests** work as before (unset flag, provide `ACTIVEKG_DSN`)
- ✅ **Backward compatible** (existing tests unchanged)
- ✅ **Documented** (testing guide + troubleshooting)

**Test the new unit tests:**
```bash
export ACTIVEKG_TEST_NO_DB=true JWT_ENABLED=false
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/test_security_limits.py -v
```

Expected: **17 passed in ~1-2 seconds** ⚡
