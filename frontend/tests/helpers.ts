import { Page, APIRequestContext, expect } from '@playwright/test';

export async function injectJwtToken(page: Page) {
  const token = process.env.E2E_ADMIN_TOKEN || process.env.ADMIN_TOKEN || '';
  if (!token) {
    console.warn('E2E_ADMIN_TOKEN not set; tests requiring auth may fail.');
  }
  await page.addInitScript((t) => {
    try {
      if (t) {
        window.localStorage.setItem('jwt_token', t);
      }
    } catch {}
  }, token);
}

export function backendUrl(): string {
  return process.env.E2E_API_URL || process.env.VITE_API_URL || 'http://localhost:8000';
}

export async function apiCreateNode(request: APIRequestContext, text: string): Promise<{ id: string }> {
  const url = `${backendUrl()}/nodes`;
  const token = process.env.E2E_ADMIN_TOKEN || '';
  const res = await request.post(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    data: { classes: ['TestDoc'], props: { text } },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()) as { id: string };
}

export async function apiHardDeleteNode(request: APIRequestContext, id: string) {
  const url = `${backendUrl()}/nodes/${encodeURIComponent(id)}?hard=true`;
  const token = process.env.E2E_ADMIN_TOKEN || '';
  const res = await request.delete(url, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  expect(res.ok()).toBeTruthy();
}

