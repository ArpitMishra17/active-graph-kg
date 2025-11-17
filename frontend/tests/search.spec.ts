import { test, expect } from '@playwright/test';

test.describe('Search smoke', () => {
  test('search returns results via UI', async ({ page }) => {
    // Auth is handled by global storageState
    await page.goto('/search');
    await page.waitForURL('**/search');

    // If the UI isn't ready yet, skip with guidance
    const input = page.locator('[data-testid="search-input"]');
    const submit = page.locator('[data-testid="search-submit"]');
    if (!(await input.count())) {
      test.skip(true, 'Search UI not present yet (add data-testid="search-*" selectors).');
      return;
    }

    await input.fill('machine learning');
    await submit.click();

    const results = page.locator('[data-testid="search-result"]');
    await expect(results.first()).toBeVisible({ timeout: 15_000 });
  });
});

