import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../src/ui/App';
import { AiAnalysisPanel } from '../src/ui/renderers';
import { VpaEvidencePanel, ValidationPanel } from '../src/ui/Details';
import { SimulatorProvider, deniedCapabilities } from '../src/api/provider';
import { demoRecommendations, makeRecommendation } from '../src/demo/fixtures';
import type { RecommendationProvider } from '../src/models/review';

afterEach(cleanup);
function app(provider: RecommendationProvider, path = '/fleet-efficiency') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App provider={provider} basePath="/fleet-efficiency" standalone />
    </MemoryRouter>
  );
}
describe('shared review screens', () => {
  it('renders overview, deep links, search and namespace filters', async () => {
    app(
      new SimulatorProvider(demoRecommendations()),
      '/fleet-efficiency/recommendations?namespace=storefront'
    );
    await screen.findByText('catalog-api');
    expect(screen.queryByText('order-worker')).toBeNull();
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Search recommendations' }),
      'catalog'
    );
    expect(screen.queryByText('inventory-sync')).toBeNull();
    expect(screen.getByRole('link', { name: 'catalog-api' }).getAttribute('href')).toBe(
      '/fleet-efficiency/recommendations/fleet-efficiency-system/rec-001'
    );
  });
  it('shows empty API and errors without claiming a healthy fleet', async () => {
    app({
      list: async () => {
        throw new Error('Recommendation CRD is missing');
      },
      capabilities: async () => deniedCapabilities,
      act: vi.fn(),
    });
    await screen.findByRole('alert');
    expect(screen.getByText('Recommendation CRD is missing')).toBeDefined();
    expect(screen.getByText(/denied API is not an empty healthy fleet/)).toBeDefined();
  });
  it('prevents viewer and expired recommendation approvals', async () => {
    const provider = new SimulatorProvider([makeRecommendation()]);
    provider.role = 'Viewer';
    app(provider, '/fleet-efficiency/recommendations/fleet-efficiency-system/rec-001');
    await screen.findByRole('heading', { name: 'catalog-api' });
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: 'Approve recommendation' }) as HTMLButtonElement)
          .disabled
      ).toBe(true)
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  it('collects a generation-bound approval reason and acknowledgements', async () => {
    const provider = new SimulatorProvider([makeRecommendation()]);
    app(provider, '/fleet-efficiency/recommendations/fleet-efficiency-system/rec-001');
    const button = await screen.findByRole('button', { name: 'Approve recommendation' });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    await userEvent.click(button);
    expect(screen.getByRole('dialog')).toBeDefined();
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Decision reason' }),
      'Reviewed representative load and canary plan.'
    );
    for (const checkbox of screen.getAllByRole('checkbox')) await userEvent.click(checkbox);
    await userEvent.click(screen.getByRole('button', { name: 'Confirm decision' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect((await provider.list())[0].status.approvals).toHaveLength(1);
    expect((await provider.list())[0].status.phase).toBe('AwaitingApproval');
  });
});
describe('evidence presentation', () => {
  it('shows memory limits as a separate dimension and refuses request-workflow approval', async () => {
    const record = makeRecommendation();
    record.spec.finding.rule_id = 'AKS-MEM-005';
    record.spec.finding.current_requests = null;
    record.spec.finding.proposed_requests = null;
    record.spec.finding.current_limits = { memory_mib: 1024 };
    record.spec.finding.proposed_limits = { memory_mib: 600 };
    app(
      new SimulatorProvider([record]),
      '/fleet-efficiency/recommendations/fleet-efficiency-system/rec-001'
    );
    await screen.findByRole('heading', { name: 'Memory limit' });
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: 'Approve recommendation' }) as HTMLButtonElement)
          .disabled
      ).toBe(true)
    );
  });
  it('displays replica-floor proposals without enabling resource-request approval', async () => {
    const record = makeRecommendation();
    record.spec.finding.rule_id = 'AKS-AS-005';
    record.spec.finding.current_requests = null;
    record.spec.finding.proposed_requests = null;
    record.spec.finding.current_replica_floor = 2;
    record.spec.finding.proposed_replica_floor = 1;
    app(
      new SimulatorProvider([record]),
      '/fleet-efficiency/recommendations/fleet-efficiency-system/rec-001'
    );
    await screen.findByRole('heading', { name: 'HPA minimum replicas' });
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: 'Approve recommendation' }) as HTMLButtonElement)
          .disabled
      ).toBe(true)
    );
  });
  it('renders malicious AI text as inert text, never executable HTML', () => {
    const record = demoRecommendations()[1];
    record.spec.ai!.explanation =
      '<img src=x onerror="window.compromised=true"><script>alert(1)</script>';
    const { container } = render(<AiAnalysisPanel record={record} />);
    expect(screen.getByText(record.spec.ai!.explanation)).toBeDefined();
    expect(container.querySelector('img, script')).toBeNull();
    expect(screen.getByText(/AI analysis supports investigation/)).toBeDefined();
  });
  it('shows VPA bounds and absence explicitly', () => {
    const record = makeRecommendation();
    const { rerender } = render(<VpaEvidencePanel record={record} />);
    expect(screen.getByText('650m')).toBeDefined();
    expect(screen.getByText('1400Mi')).toBeDefined();
    delete record.spec.vpa;
    rerender(<VpaEvidencePanel record={record} />);
    expect(screen.getByText('No source VPA supplied')).toBeDefined();
  });
  it('does not infer validation success from merge', () => {
    const record = makeRecommendation();
    record.status.pullRequest.state = 'Merged';
    render(<ValidationPanel record={record} />);
    expect(screen.getByText('Not Started')).toBeDefined();
    expect(screen.getByText('Validation has not started')).toBeDefined();
  });
});
