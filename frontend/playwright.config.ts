import { defineConfig, devices } from '@playwright/test';

// Base UI URL; auto-started by webServer if not running
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:5173';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],

  // Global setup: inject auth token into storageState
  globalSetup: './tests/global-setup.ts',

  use: {
    baseURL,
    trace: 'retain-on-failure',
    // Use shared storageState with auth token
    storageState: 'storageState.json',
  },

  // Auto-start dev server if not running
  webServer: {
    command: 'npm run dev',
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
  },

  // Opt into one desktop browser for smoke coverage
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});

