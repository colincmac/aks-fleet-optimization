import { expect, test } from '@playwright/test';

const detail = '/fleet-efficiency/recommendations/fleet-efficiency-system/rec-001';

test('overview and filters preserve deep links and fit the viewport', async ({
  page,
}, testInfo) => {
  await page.goto('/fleet-efficiency');
  await expect(page.getByRole('heading', { name: 'Fleet efficiency', exact: true })).toBeVisible();
  await expect(page.locator('.fe-kpis')).toContainText('Active recommendations');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (testInfo.project.name === 'desktop')
    await page.screenshot({ path: 'docs/overview-desktop.png', animations: 'disabled' });
  else await page.screenshot({ path: 'docs/overview-mobile.png', animations: 'disabled' });
  await page.getByRole('link', { name: 'Review recommendations' }).click();
  await page.getByRole('combobox', { name: 'Namespace', exact: true }).selectOption('storefront');
  await page.getByRole('textbox', { name: 'Search recommendations' }).fill('catalog');
  await expect(page.getByRole('link', { name: 'catalog-api', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'order-worker', exact: true })).toHaveCount(0);
  expect(page.url()).toContain('namespace=storefront');
  await page.getByRole('link', { name: 'catalog-api', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Current vs. proposed' })).toBeVisible();
  await expect(page.locator('.fe-bounds')).toContainText('650m');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('independent approvals, simulated PR and validation are separate states', async ({ page }) => {
  const writes: string[] = [];
  page.on('request', (request) => {
    if (!['GET', 'HEAD'].includes(request.method())) writes.push(request.url());
  });
  await page.goto(detail);
  await expect(
    page.getByRole('button', { name: 'Approve recommendation', exact: true })
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Approve recommendation', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog
    .getByRole('textbox', { name: 'Decision reason' })
    .fill('Representative evidence reviewed; canary and rollback agreed.');
  for (const checkbox of await dialog.getByRole('checkbox').all()) await checkbox.check();
  await dialog.getByRole('button', { name: 'Confirm decision' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Request pull request', exact: true })
  ).toBeDisabled();
  await page.getByRole('combobox', { name: 'Preview reviewer role' }).selectOption('PlatformOwner');
  await expect(
    page.getByRole('button', { name: 'Approve recommendation', exact: true })
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Approve recommendation', exact: true }).click();
  await dialog
    .getByRole('textbox', { name: 'Decision reason' })
    .fill('Independent platform review complete.');
  for (const checkbox of await dialog.getByRole('checkbox').all()) await checkbox.check();
  await dialog.getByRole('button', { name: 'Confirm decision' }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole('button', { name: 'Request pull request', exact: true }).click();
  await dialog
    .getByRole('textbox', { name: 'Decision reason' })
    .fill('Request the bounded configuration proposal.');
  await dialog.getByRole('button', { name: 'Confirm decision' }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole('tab', { name: 'Delivery & validation' }).click();
  await expect(
    page.getByText('Simulated pull request. No repository was contacted.')
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Validation has not started' })).toBeVisible();
  expect(writes).toEqual([]);
  await page.getByRole('tab', { name: 'Timeline' }).click();
  await expect(page.getByText('Independent platform review complete.')).toBeVisible();
});

test('viewer, expiry, supersession, partial and stale evidence fail closed', async ({ page }) => {
  await page.goto(detail);
  await page.getByRole('combobox', { name: 'Preview reviewer role' }).selectOption('Viewer');
  await expect(
    page.getByRole('button', { name: 'Approve recommendation', exact: true })
  ).toBeDisabled();
  for (const id of ['rec-009', 'rec-010', 'rec-011', 'rec-012']) {
    await page.goto(`/fleet-efficiency/recommendations/fleet-efficiency-system/${id}`);
    await expect(
      page.getByRole('button', { name: 'Approve recommendation', exact: true })
    ).toBeDisabled();
    await expect(
      page.getByRole('button', { name: 'Request pull request', exact: true })
    ).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true
    );
  }
});

test('reject, defer and observation decisions record a reason without changing resources', async ({
  page,
}) => {
  for (const label of ['Reject', 'Defer', 'Request more observation']) {
    await page.goto(detail);
    await expect(page.getByRole('button', { name: label, exact: true })).toBeEnabled();
    await page.getByRole('button', { name: label, exact: true }).click();
    const dialog = page.getByRole('dialog');
    if (label === 'Defer') {
      const tomorrow = new Date(Date.now() + 86400000);
      const local = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16);
      await dialog.getByLabel('Defer until').fill(local);
    }
    await dialog
      .getByRole('textbox', { name: 'Decision reason' })
      .fill(`Synthetic ${label} review reason.`);
    await dialog.getByRole('button', { name: 'Confirm decision' }).click();
    await expect(dialog).toHaveCount(0);
    await page.getByRole('tab', { name: 'Timeline' }).click();
    await expect(page.getByText(`Synthetic ${label} review reason.`)).toBeVisible();
  }
});

test('catalog is inspectable without evidence and denied/empty states are explicit', async ({
  page,
}) => {
  await page.goto('/fleet-efficiency/catalog?scenario=denied');
  await expect(
    page.getByRole('heading', { name: 'Recommendation catalog', exact: true })
  ).toBeVisible();
  await expect(page.getByRole('heading', { level: 2 })).toHaveCount(21);
  await expect(
    page.getByRole('heading', { name: /Investigate current placement constraints/ })
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: /Review capacity management and NAP prerequisites/ })
  ).toBeVisible();
  await page.goto('/fleet-efficiency?scenario=denied');
  await expect(page.getByRole('heading', { name: 'Recommendations unavailable' })).toBeVisible();
  await expect(page.getByText(/denied API is not an empty healthy fleet/)).toBeVisible();
  await page.goto('/fleet-efficiency/recommendations?scenario=empty');
  await expect(page.getByText('No matching recommendations')).toBeVisible();
  await expect(page.getByText(/This does not establish fleet health/)).toBeVisible();
});

for (const scenario of ['baseline', 'guarded', 'unsupported', 'limit', 'floor']) {
  test(`pack inspection preserves ${scenario} boundaries without writes`, async ({ page }) => {
    const writes: string[] = [];
    page.on('request', (request) => {
      if (!['GET', 'HEAD'].includes(request.method())) writes.push(request.url());
    });
    await page.goto(`${detail}?scenario=${scenario}`);
    await expect(
      page.getByRole('heading', { name: 'Pack, queries & capability gaps' })
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Approve recommendation', exact: true })
    ).toBeDisabled();
    await expect(
      page.getByRole('button', { name: 'Request pull request', exact: true })
    ).toBeDisabled();
    await page
      .getByText('Query templates (not executable; export with approved source/scope)', {
        exact: true,
      })
      .click();
    await expect(page.getByText(/not executable exports/)).toBeVisible();
    if (scenario === 'unsupported')
      await expect(page.getByText(/unsupported_source_shape/)).toBeVisible();
    if (scenario === 'baseline')
      await expect(page.getByText(/No change proposed/).first()).toBeVisible();
    if (scenario === 'limit')
      await expect(page.getByRole('heading', { name: 'Memory limit', exact: true })).toBeVisible();
    if (scenario === 'floor')
      await expect(
        page.getByRole('heading', { name: 'HPA minimum replicas', exact: true })
      ).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true
    );
    expect(writes).toEqual([]);
  });
}
