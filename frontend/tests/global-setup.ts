import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  const rawToken = process.env.E2E_ADMIN_TOKEN;

  if (!rawToken) {
    console.warn('⚠️  E2E_ADMIN_TOKEN not set; tests will fail authentication');
    return;
  }

  // Sanitize: remove all whitespace (newlines, spaces, tabs)
  // This is critical for CI environments where secrets may have trailing newlines
  const token = rawToken.replace(/\s/g, '').trim();

  // Validate: JWT format must be header.payload.signature
  const JWT_REGEX = /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$/;
  if (!JWT_REGEX.test(token)) {
    console.error('❌ Invalid JWT format in E2E_ADMIN_TOKEN');
    console.error('   Expected: header.payload.signature (no whitespace)');
    return;
  }

  // Launch browser and create context
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  // Navigate to about:blank and inject auth token
  await page.goto('about:blank');

  // Inject JWT token into localStorage
  await page.evaluate((tkn) => {
    try {
      // Decode JWT payload to extract claims
      const payload = JSON.parse(atob(tkn.split('.')[1]));

      const authState = {
        state: {
          token: tkn,
          claims: payload,
          isAuthenticated: true,
        },
        version: 0,
      };

      localStorage.setItem('auth-storage', JSON.stringify(authState));
      console.log('✅ Auth token injected into localStorage');
    } catch (err) {
      console.error('❌ Failed to inject auth token:', err);
    }
  }, token);

  // Save storage state for all tests
  await context.storageState({ path: 'storageState.json' });

  await browser.close();

  console.log('✅ Global setup complete: storageState.json created');
}

export default globalSetup;
