import { expect, test } from '@playwright/test';

const dashboard = '/fleet-efficiency/assessments';
const endpoint = '/assessment-preview/assessments.json';

test('opens the published assessment and drills into findings, discovery and gaps', async ({
  page,
}, testInfo) => {
  await page.goto(dashboard);
  await expect(page.getByRole('heading', { name: 'Assessments', exact: true })).toBeVisible();
  await expect(page.getByText('Partial assessment.', { exact: false })).toBeVisible();
  await page.getByText('Review CPU request for synthetic/api', { exact: true }).click();
  await expect(page.getByText('Guarded suggestion (not approved)', { exact: true })).toBeVisible();
  await expect(page.getByText('500 mCPU', { exact: true })).toBeVisible();
  await expect(page.getByText('cpu_p95_to_request_ratio', { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('assessment.png'), fullPage: true });
  await page.getByRole('button', { name: 'Discovery', exact: true }).click();
  await expect(
    page.getByRole('table', { name: 'Namespaces retained in the assessment' })
  ).toContainText('synthetic');
  await page.getByRole('button', { name: 'synthetic', exact: true }).click();
  await expect(page.getByLabel('Namespace', { exact: true })).toHaveValue('synthetic');
  await expect(
    page.getByRole('table', { name: 'Workloads retained in the assessment' })
  ).toContainText('workload-uid');
  await page.getByRole('searchbox').fill('no matching workload');
  await expect(page.getByText('No matching workload identities were retained.')).toBeVisible();
  await page.getByRole('searchbox').clear();
  await page.getByRole('button', { name: 'Evidence gaps', exact: true }).click();
  await expect(page.getByText('unsupported-pool-evidence')).toBeVisible();
  await page.getByText('AKS-AS-005', { exact: true }).click();
  await expect(page.getByText('missing_replica_safety_policy', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    await page.evaluate(() => innerWidth)
  );
});

test('switches exact cluster scope and removes results after a denied refresh', async ({
  page,
  request,
}) => {
  const original = await (await request.get(endpoint)).json();
  const first = original.clusters[0];
  let deny = false;
  await page.route(`**${endpoint}`, (route) =>
    deny
      ? route.fulfill({ status: 403 })
      : route.fulfill({
          json: {
            ...original,
            clusters: [
              first,
              {
                ...first,
                id: 'other-id',
                uid: 'other-uid',
                name: 'other-cluster',
                findings: [],
                namespaces: [],
                issues: [],
              },
            ],
          },
        })
  );
  await page.goto(dashboard);
  await expect(
    page.getByText('Review CPU request for synthetic/api', { exact: true })
  ).toBeVisible();
  await page.getByRole('button', { name: /other-cluster/ }).click();
  await expect(page.getByRole('heading', { name: 'other-cluster', exact: true })).toBeVisible();
  await expect(page.getByText('No matching records', { exact: true })).toBeVisible();
  deny = true;
  await page.getByRole('button', { name: 'Refresh assessments', exact: true }).click();
  await expect(
    page.getByText('Assessment feed unavailable or invalid.', { exact: false })
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'other-cluster', exact: true })).toHaveCount(0);
});

test('picks up a replaced assessment feed without a page reload', async ({ page, request }) => {
  const original = await (await request.get(endpoint)).json();
  let published = original;
  await page.clock.install();
  await page.route(`**${endpoint}`, (route) => route.fulfill({ json: published }));
  await page.goto(dashboard);
  await expect(page.getByRole('heading', { name: 'aks-synthetic', exact: true })).toBeVisible();
  published = {
    ...original,
    clusters: [{ ...original.clusters[0], windowEnd: '2026-10-29T05:00:00Z' }],
  };
  await page.clock.fastForward(61000);
  await expect(page.locator('time[datetime="2026-10-29T05:00:00Z"]')).toBeVisible();
});

test('keeps retained and unassessed targets visible and supports keyboard drill-down', async ({
  page,
  request,
}) => {
  const original = await (await request.get(endpoint)).json();
  const first = original.clusters[0];
  const attemptedAt = '2026-10-31T12:00:00Z';
  await page.clock.setFixedTime(new Date(attemptedAt));
  await page.route(`**${endpoint}`, (route) =>
    route.fulfill({
      json: {
        ...original,
        clusters: [
          first,
          {
            ...first,
            id: 'reporting-id',
            uid: 'reporting-uid',
            name: 'Reporting',
            evaluatedAt: attemptedAt,
          },
        ],
        failedClusters: [first.id, 'missing-target'],
      },
    })
  );
  await page.goto(dashboard);
  const roster = page.getByRole('region', { name: 'Fleet assessments' });
  await expect(roster.getByText('Targets in published roster')).toBeVisible();
  await expect(roster.getByText('Reporting status unknown', { exact: true })).toBeVisible();
  const retained = roster.getByRole('button', { name: /aks-synthetic/ });
  await expect(retained).toContainText('Prior results');
  const missing = roster.getByRole('listitem').filter({ hasText: 'missing-target' });
  await expect(missing).toContainText('No saved result');
  await expect(missing.getByRole('button')).toHaveCount(0);

  const reporting = roster.getByRole('button', { name: /Reporting/ });
  await reporting.focus();
  await reporting.press('Enter');
  const jump = roster.getByRole('button', { name: 'Jump to selected assessment' });
  await jump.focus();
  await jump.press('Enter');
  await expect(page.getByRole('heading', { name: 'Reporting', exact: true })).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    await page.evaluate(() => innerWidth)
  );
});
