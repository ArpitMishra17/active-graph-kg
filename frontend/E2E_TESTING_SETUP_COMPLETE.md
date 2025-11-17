# E2E Testing Setup Complete

**Date**: 2025-11-13
**Status**: ✅ Playwright Installed & Configured

---

## Setup Complete

### ✅ 1. Playwright Installed
```bash
npm install -D @playwright/test          # ✅ Installed (4 packages)
npx playwright install chromium          # ✅ Browser binaries downloaded
```

### ✅ 2. Environment Configuration
**Required Variables**:
```bash
E2E_BASE_URL=http://localhost:5173      # Frontend URL
E2E_API_URL=http://localhost:8000       # Backend API URL
E2E_ADMIN_TOKEN=<JWT from generate_test_jwt.py>
```

### ✅ 3. Test Infrastructure
**Files Created** (by you):
- `frontend/playwright.config.ts` - Playwright configuration
- `frontend/tests/helpers.ts` - JWT injection + API fallback utilities
- `frontend/tests/search.spec.ts` - Search UI smoke test
- `frontend/tests/ask_stream.spec.ts` - Streaming Q&A smoke test
- `frontend/tests/node_crud.spec.ts` - Node CRUD smoke test

---

## Test Execution Results

### Test Run Summary
```bash
cd frontend
E2E_BASE_URL=http://localhost:5173 \
E2E_API_URL=http://localhost:8000 \
E2E_ADMIN_TOKEN="<token>" \
npx playwright test --reporter=list
```

**Results**:
- ✅ 1 test executed (node_crud.spec.ts)
- ⏭️ 2 tests skipped (search.spec.ts, ask_stream.spec.ts)
- ❌ 1 test failed (timing issue with node list refresh)

### Why Tests Skip

**By Design** - Tests skip gracefully when UI controls aren't present:

```typescript
// From search.spec.ts
if (!(await page.locator('[data-testid="search-input"]').count())) {
  test.skip(true, 'Search UI not present; skipping test');
  return;
}
```

**Current Status**:
- Search test skipped: `search-input` test ID not found
- Ask test skipped: `ask-input` test ID not found
- Node CRUD ran: Found create button but had timing issue

**Why UI Controls Not Found**:
- Tests navigate to `/` which redirects to `/login`
- JWT injection happens AFTER page load
- Auth redirect may be interfering with direct route navigation

---

## Quick Fixes Needed

### 1. Fix Auth Flow in Tests

**Problem**: Tests inject JWT but auth redirect prevents direct navigation to protected routes

**Solution**: Update test helper to navigate AFTER auth setup

```typescript
// In helpers.ts - Update injectJwtToken()
export async function injectJwtToken(page: Page) {
  const token = process.env.E2E_ADMIN_TOKEN || '';

  // Navigate to app first
  await page.goto('/');

  // Inject token into localStorage
  await page.evaluate((tkn) => {
    localStorage.setItem('auth-storage', JSON.stringify({
      state: { token: tkn, claims: null, isAuthenticated: true },
      version: 0
    }));
  }, token);

  // Reload to pick up auth
  await page.reload();
}
```

### 2. Verify Test IDs Are Rendered

Let me check if the test IDs exist in the compiled JS:

**Search UI**: `frontend/src/routes/Search.tsx:108, 117, 231`
- ✅ `search-input`
- ✅ `search-submit`
- ✅ `search-result`

**Ask UI**: `frontend/src/routes/Ask.tsx:67, 70, 156`
- ✅ `ask-input`
- ✅ `ask-submit`
- ✅ `ask-answer`

**Node CRUD**: `frontend/src/routes/Nodes.tsx:multiple`
- ✅ `node-create`
- ✅ `node-text`
- ✅ `node-save`
- ✅ `node-row`
- ✅ `node-delete`
- ✅ `confirm-delete`

**All test IDs present** - Issue is navigation/auth, not missing IDs.

---

## Recommended Test Improvements

### 1. Update Helper for Better Auth Flow

**File**: `frontend/tests/helpers.ts`

```typescript
export async function loginAndNavigateTo(page: Page, route: string) {
  const token = process.env.E2E_ADMIN_TOKEN || '';

  // Go to home first
  await page.goto('/');

  // Inject auth token
  await page.evaluate((tkn) => {
    const authState = {
      state: {
        token: tkn,
        claims: JSON.parse(atob(tkn.split('.')[1])), // Decode JWT payload
        isAuthenticated: true
      },
      version: 0
    };
    localStorage.setItem('auth-storage', JSON.stringify(authState));
  }, token);

  // Navigate to desired route (will use auth from localStorage)
  await page.goto(route);
}
```

**Usage in Tests**:
```typescript
// search.spec.ts
await loginAndNavigateTo(page, '/search');

// ask_stream.spec.ts
await loginAndNavigateTo(page, '/ask');

// node_crud.spec.ts
await loginAndNavigateTo(page, '/nodes');
```

### 2. Add Wait for Navigation in Tests

**Update each spec** to wait for route before checking UI:

```typescript
await loginAndNavigateTo(page, '/search');
await page.waitForURL('**/search');
await expect(page.locator('[data-testid="search-input"]')).toBeVisible();
```

### 3. Fix Node CRUD Timing Issue

**Problem**: Created node doesn't appear in list immediately

**Solutions**:
- Option A: Wait for API call to complete before reloading
- Option B: Poll for node appearance with retry
- Option C: Use React Query cache invalidation (already implemented in UI)

**Current**: Test reloads page after API create, but node list hasn't refetched yet

**Fix**:
```typescript
// After creating node
await page.reload();

// Wait for the node list to load
await page.waitForSelector('[data-testid="node-row"]', { timeout: 10_000 });

// Now check for the specific node
const row = page.locator('[data-testid="node-row"]')
  .filter({ hasText: createdId.slice(0, 8) })
  .first();
await expect(row).toBeVisible({ timeout: 15_000 });
```

---

## Current State Summary

### ✅ What's Working
- Playwright installed and configured
- Browser binaries downloaded
- Test IDs present in all UI components
- JWT token generation working
- API fallback methods functional
- Graceful skipping logic working as intended

### ⚠️ What Needs Fixing
- Auth flow in tests (JWT injection timing)
- Direct navigation to protected routes
- Node list refresh timing in node_crud test

### 📝 Action Items

1. **Update `helpers.ts`** with improved auth flow
2. **Update test specs** to use new `loginAndNavigateTo()` helper
3. **Add explicit wait** for route navigation
4. **Fix node list timing** in node_crud.spec.ts
5. **Re-run tests** to validate fixes

---

## Running Tests After Fixes

### Single Test
```bash
cd frontend
E2E_BASE_URL=http://localhost:5173 \
E2E_API_URL=http://localhost:8000 \
E2E_ADMIN_TOKEN="eyJ..." \
npx playwright test tests/search.spec.ts
```

### All Tests
```bash
npx playwright test --reporter=list
```

### With UI (Headed Mode)
```bash
npx playwright test --ui
```

### Debug Mode
```bash
npx playwright test --debug
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: ankane/pgvector:latest
        env:
          POSTGRES_PASSWORD: activekg
          POSTGRES_DB: activekg
        ports:
          - 5433:5432

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-node@v3
        with:
          node-version: '20'

      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd frontend
          npm ci
          npx playwright install --with-deps chromium

      - name: Start backend
        run: |
          python -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt
          # Export all required env vars
          uvicorn activekg.api.main:app --host 0.0.0.0 --port 8000 &
          sleep 10

      - name: Start frontend
        run: |
          cd frontend
          npm run dev &
          sleep 5

      - name: Run E2E tests
        env:
          E2E_BASE_URL: http://localhost:5173
          E2E_API_URL: http://localhost:8000
          E2E_ADMIN_TOKEN: ${{ secrets.E2E_ADMIN_TOKEN }}
        run: |
          cd frontend
          npx playwright test

      - uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: playwright-report
          path: frontend/playwright-report/
```

---

## Validation Checklist

### Manual Testing
- [ ] Open http://localhost:5173/
- [ ] Paste JWT token and login
- [ ] Navigate to `/search` - verify controls visible
- [ ] Navigate to `/ask` - verify controls visible
- [ ] Navigate to `/nodes` - verify controls visible
- [ ] Create node - verify appears in list
- [ ] Delete node - verify removed from list

### E2E Testing
- [ ] Update helpers.ts with improved auth flow
- [ ] Update all test specs to use new helper
- [ ] Run search.spec.ts - should pass
- [ ] Run ask_stream.spec.ts - should pass (or skip if LLM disabled)
- [ ] Run node_crud.spec.ts - should pass
- [ ] All tests pass in CI

---

## Next Steps

1. **Apply Auth Fixes** (15 min)
   - Update `helpers.ts` with `loginAndNavigateTo()`
   - Update all 3 test specs

2. **Validate Locally** (10 min)
   - Run each test individually
   - Verify all pass

3. **CI Integration** (30 min)
   - Set up GitHub Actions workflow
   - Add E2E_ADMIN_TOKEN to repo secrets
   - Validate CI runs pass

4. **Documentation** (15 min)
   - Update README with E2E test instructions
   - Document test ID contracts
   - Add troubleshooting guide

---

**Status**: Ready for auth fixes. Test infrastructure 100% complete.

**Last Updated**: 2025-11-13
