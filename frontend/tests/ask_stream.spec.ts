import { test, expect } from '@playwright/test';

test.describe('Ask (streaming) smoke', () => {
  test('streams an answer via UI', async ({ page }) => {
    // Auth is handled by global storageState
    await page.goto('/ask');
    await page.waitForURL('**/ask');

    const input = page.locator('[data-testid="ask-input"]');
    const submit = page.locator('[data-testid="ask-submit"]');
    const answer = page.locator('[data-testid="ask-answer"]');

    if (!(await input.count())) {
      test.skip(true, 'Ask UI not present yet (add data-testid="ask-*" selectors).');
      return;
    }

    // Gate test if LLM backend not configured
    // Note: Consider adding LLM_ENABLED check in future iterations

    await input.fill('What is a knowledge graph?');
    await submit.click();

    // Expect the answer area to receive content within a reasonable window
    await expect(answer).toHaveText(/.+/, { timeout: 20_000 });
  });
});

