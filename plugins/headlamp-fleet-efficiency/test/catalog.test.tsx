import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { OperatorCatalogPanel, PackInspectionPanel } from '../src/ui/Catalog';
import { makeRecommendation, packPreviewRecommendation } from '../src/demo/fixtures';
import { parseRecommendation } from '../src/api/contracts';
import { approvalBlockers } from '../src/utils/safety';

afterEach(cleanup);

it('discovers all 21 cards, limitations, query templates and parameter units', () => {
  render(<OperatorCatalogPanel />);
  expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(21);
  expect(
    screen.getByRole('heading', { name: /Investigate current placement constraints/ })
  ).toBeDefined();
  expect(
    screen.getByRole('heading', { name: /Review capacity management and NAP prerequisites/ })
  ).toBeDefined();
  expect(screen.getAllByText(/review_ratio/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/not executable/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/owner/).length).toBeGreaterThan(0);
});

it('shows missing inspection as unknown without substituting current catalog facts', () => {
  render(<PackInspectionPanel record={makeRecommendation()} />);
  expect(screen.getByText(/Pack inspection was not supplied/)).toBeDefined();
});

it('renders original pack, queries, policies and capability gaps as inert text', () => {
  const record = packPreviewRecommendation('guarded');
  record.spec.inspection!.card.manifest.limitations = ['<script>alert(1)</script>'];
  const { container } = render(<PackInspectionPanel record={record} />);
  expect(screen.getByText('<script>alert(1)</script>')).toBeDefined();
  expect(container.querySelector('script')).toBeNull();
  expect(screen.getByText(/2.1.0/)).toBeDefined();
  expect(screen.getAllByText(/unknown/i).length).toBeGreaterThan(0);
  expect(approvalBlockers(record)).toContain('Pack source capability is not available');
});

it('rejects mismatched pack/version, baseline numeric proposals and foreign capabilities', () => {
  for (const defect of ['pack', 'version', 'baseline', 'scope', 'status']) {
    const record = packPreviewRecommendation('guarded');
    if (defect === 'pack') record.spec.finding.rule_id = 'AKS-MEM-005';
    if (defect === 'version') record.spec.finding.rule_version = '0.0.0';
    if (defect === 'baseline') record.spec.inspection!.mode = 'baseline';
    if (defect === 'scope')
      record.spec.inspection!.capabilities[0].cluster_resource_id += '-foreign';
    if (defect === 'status') record.spec.inspection!.capabilities[0].status = 'available';
    expect(() => parseRecommendation(record)).toThrow(/inspection|Baseline/);
  }
});
