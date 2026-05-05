import { test, expect } from '@playwright/test';

test('Dashboard smoke test: renders correctly without JS errors', async ({ page }) => {
  const errors: string[] = [];
  
  // Listen for uncaught UI exceptions
  page.on('pageerror', error => {
    errors.push(`PageError: ${error.message}`);
  });
  
  // Listen for console errors (like the React map/slice errors we had)
  page.on('console', msg => {
    if (msg.type() === 'error') {
      // Ignore normal dev server / favicon network errors, catch logical ones
      if (!msg.text().includes('favicon') && !msg.text().includes('Failed to load resource')) {
        errors.push(`ConsoleError: ${msg.text()}`);
      }
    }
  });

  // --- MOCK BACKEND DATA ---
  // Intercept the stats API
  await page.route('**/api/stats', async route => {
    await route.fulfill({
      json: { total_days: 99, total_picks: 42, avg_margin: 66.66, avg_roe: 18.5 }
    });
  });

  // Intercept the picks API (Mocking one perfect data point and one with nulls)
  await page.route('**/api/picks', async route => {
    await route.fulfill({
      json: {
        data: [
          { code: '000001.SZ', trade_date: '20260430', price: 10, graham: 20, margin: 50, roe: 15, debt_to_assets: 80, pe: 5, pb: 0.8, reasoning: 'Mock safe' },
          { code: 'BANK.SH', trade_date: '20260430', price: 5, graham: 10, margin: null, roe: null, debt_to_assets: null, pe: 4, pb: 0.5, reasoning: 'Mock nulls' }
        ]
      }
    });
  });

  // --- EXECUTE UI ACTIONS ---
  await page.goto('/');

  // 1. Verify static titles
  await expect(page.locator('text=量化推荐看板')).toBeVisible();

  // 2. Verify Stats cards parsed and rendered the mock data
  await expect(page.locator('text=99')).toBeVisible(); // total_days
  await expect(page.locator('text=66.66%')).toBeVisible(); // avg_margin

  // 3. Verify Charts are rendered without crashing
  await expect(page.locator('.recharts-responsive-container').first()).toBeVisible({ timeout: 10000 });

  // 4. Verify Table rendered our mocked rows
  await expect(page.locator('td', { hasText: '000001.SZ' })).toBeVisible();
  await expect(page.locator('td', { hasText: 'BANK.SH' })).toBeVisible();

  // --- THE GATING ASSERTION ---
  // If there are ANY runtime JS errors recorded, the test will fail here!
  expect(errors).toEqual([]);
});
