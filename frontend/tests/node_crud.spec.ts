import { test, expect, request } from '@playwright/test';
import { apiCreateNode, apiHardDeleteNode } from './helpers';

test.describe('Node CRUD smoke', () => {
  test('create, list, delete node via UI (with API fallback)', async ({ page }) => {
    // Auth is handled by global storageState
    await page.goto('/nodes');
    await page.waitForURL('**/nodes');

    const createBtn = page.locator('[data-testid="node-create"]');
    const textInput = page.locator('[data-testid="node-text"]');
    const saveBtn = page.locator('[data-testid="node-save"]');

    let createdId = '';

    if (await createBtn.count()) {
      // Use UI flow if present
      await createBtn.click();
      await textInput.fill('Playwright smoke test node');
      await saveBtn.click();

      // Wait for React Query to refetch the list
      await page.waitForTimeout(1000);

      const row = page.locator('[data-testid="node-row"]').filter({ hasText: 'Playwright smoke test node' });
      await expect(row.first()).toBeVisible({ timeout: 15_000 });
    } else {
      // Fallback: create via API, then verify list shows it
      const api = await request.newContext();
      const res = await apiCreateNode(api, 'Playwright smoke test node');
      createdId = res.id;

      await page.reload();

      // Wait for node list to load
      await page.waitForSelector('[data-testid="node-row"]', { timeout: 10_000 });

      const row = page.locator('[data-testid="node-row"]').filter({ hasText: createdId.slice(0, 8) }).first();
      await expect(row).toBeVisible({ timeout: 15_000 });
    }

    // Attempt delete via UI if delete buttons exist, else cleanup via API if we created via API
    const deleteBtn = page.locator('[data-testid="node-delete"]').first();
    if (await deleteBtn.count()) {
      await deleteBtn.click();
      const confirm = page.locator('[data-testid="confirm-delete"]').first();
      if (await confirm.count()) await confirm.click();
      await expect(page.locator('[data-testid="node-row"]').filter({ hasText: 'Playwright smoke test node' }).first()).toBeHidden({ timeout: 15_000 });
    } else if (createdId) {
      const api = await request.newContext();
      await apiHardDeleteNode(api, createdId);
    }
  });
});

