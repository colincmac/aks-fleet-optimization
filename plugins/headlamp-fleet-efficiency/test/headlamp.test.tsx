import type { ComponentType } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { makeRecommendation } from '../src/demo/fixtures';
import published from '../preview-public/assessment-preview/assessments.json';

const host = vi.hoisted(() => ({
  cluster: 'management-a',
  request: vi.fn(),
  routes: [] as { path: string; component: ComponentType }[],
  sidebar: vi.fn(),
}));
vi.mock('@kinvolk/headlamp-plugin/lib', () => ({
  ApiProxy: { request: host.request },
  K8s: {
    cluster: {
      KubeObject: class {
        jsonData: unknown;
        constructor(data: unknown) {
          this.jsonData = data;
        }
      },
    },
  },
  registerRoute: (route: { path: string; component: ComponentType }) => host.routes.push(route),
  registerSidebarEntry: host.sidebar,
}));
vi.mock('@kinvolk/headlamp-plugin/lib/Utils', () => ({ getCluster: () => host.cluster }));
vi.mock('@mui/material', () => ({ useTheme: () => ({ palette: { mode: 'light' } }) }));
import { configureFleetAdvisor } from '../src/index';
import { OptimizationRecommendation } from '../src/resources/OptimizationRecommendation';
import { VerticalPodAutoscaler } from '../src/resources/VerticalPodAutoscaler';

afterEach(() => {
  cleanup();
  configureFleetAdvisor({});
  vi.unstubAllGlobals();
});
describe('Headlamp registration and management context', () => {
  it('registers the assessment and review routes and typed API resources', () => {
    expect(host.routes.map((route) => route.path)).toEqual([
      '/fleet-efficiency',
      '/fleet-efficiency/assessments',
      '/fleet-efficiency/catalog',
      '/fleet-efficiency/recommendations',
      '/fleet-efficiency/recommendations/:namespace/:name',
      '/fleet-efficiency/settings',
    ]);
    expect(OptimizationRecommendation.apiVersion).toBe('optimization.aks.io/v1alpha1');
    expect(VerticalPodAutoscaler.apiVersion).toBe('autoscaling.k8s.io/v1');
  });
  it.each(['', '/assessments', '/recommendations/team/old-record', '/settings'])(
    'uses the assessment feed without reading Kubernetes APIs at %s',
    async (suffix) => {
      host.cluster = 'management-a';
      host.request.mockClear();
      const fetchFeed = vi.fn(async () => Response.json({ schemaVersion: '1', clusters: [] }));
      vi.stubGlobal('fetch', fetchFeed);
      const Route = host.routes[0].component;
      render(
        <MemoryRouter initialEntries={[`/c/management-a/fleet-efficiency${suffix}`]}>
          <Route />
        </MemoryRouter>
      );
      await screen.findByText('No published assessments');
      expect(fetchFeed).toHaveBeenCalledWith(
        '/advisor-data/assessments.json',
        expect.objectContaining({ credentials: 'same-origin', cache: 'no-store', method: 'GET' })
      );
      expect(screen.queryByRole('link', { name: 'Recommendations' })).toBeNull();
      expect(host.request).not.toHaveBeenCalled();
    }
  );
  it('keeps the catalog available without contacting the feed or Kubernetes', async () => {
    host.cluster = 'management-a';
    host.request.mockClear();
    const fetchFeed = vi.fn();
    vi.stubGlobal('fetch', fetchFeed);
    const Route = host.routes[0].component;
    render(
      <MemoryRouter initialEntries={['/c/management-a/fleet-efficiency/catalog']}>
        <Route />
      </MemoryRouter>
    );
    await screen.findByRole('heading', { name: 'Recommendation catalog' });
    expect(fetchFeed).not.toHaveBeenCalled();
    expect(host.request).not.toHaveBeenCalled();
  });
  it('shows a denied custom feed as unavailable without falling back to review APIs', async () => {
    configureFleetAdvisor({ assessmentFeedPath: '/private/fleet.json' });
    host.request.mockClear();
    const fetchFeed = vi.fn(async () => new Response(null, { status: 403 }));
    vi.stubGlobal('fetch', fetchFeed);
    const Route = host.routes[0].component;
    render(
      <MemoryRouter initialEntries={['/c/management-a/fleet-efficiency']}>
        <Route />
      </MemoryRouter>
    );
    await screen.findByText(/Assessment feed unavailable or invalid/);
    expect(fetchFeed).toHaveBeenCalledWith('/private/fleet.json', expect.anything());
    expect(host.request).not.toHaveBeenCalled();
  });
  it('shows stale retained evidence alongside a newer recorded failure', async () => {
    host.cluster = 'management-a';
    host.request.mockClear();
    const evaluated = Date.parse(published.clusters[0].evaluatedAt);
    const failure = new Date(evaluated + 27 * 3600000).toISOString();
    const fetchFeed = vi
      .fn()
      .mockResolvedValueOnce(Response.json(published))
      .mockResolvedValueOnce(
        Response.json({
          schemaVersion: '1',
          attemptedAt: failure,
          outcome: 'failed',
          staleAfterHours: 26,
        })
      );
    vi.stubGlobal('fetch', fetchFeed);
    const now = vi.spyOn(Date, 'now').mockReturnValue(evaluated + 28 * 3600000);
    try {
      const Route = host.routes[0].component;
      render(
        <MemoryRouter initialEntries={['/c/management-a/fleet-efficiency']}>
          <Route />
        </MemoryRouter>
      );
      await screen.findByText(/Latest recorded attempt failed/);
      expect(screen.getByText(/Published results are stale/)).toBeDefined();
      expect(screen.getByText(published.clusters[0].name, { selector: 'strong' })).toBeDefined();
      const roster = screen.getByRole('region', { name: 'Fleet assessments' });
      expect(within(roster).getByText('0 reporting')).toBeDefined();
      expect(within(roster).getByText('Prior results')).toBeDefined();
      expect(within(roster).getByText('Stale evaluation')).toBeDefined();
      expect(host.request).not.toHaveBeenCalled();
    } finally {
      now.mockRestore();
    }
  });
  it('recreates GET-only readers when the selected management context changes', async () => {
    configureFleetAdvisor({ enableReview: true });
    host.cluster = 'management-a';
    host.request.mockReset();
    host.request.mockImplementation(async (path: string) => ({
      items: path.includes('verticalpodautoscalers') ? [] : [makeRecommendation()],
      metadata: { resourceVersion: '1' },
    }));
    const Route = host.routes[0].component;
    const { rerender } = render(
      <MemoryRouter initialEntries={['/c/management-a/fleet-efficiency']}>
        <Route />
      </MemoryRouter>
    );
    await screen.findByRole('heading', { name: 'Fleet efficiency' });
    await waitFor(() =>
      expect(host.request.mock.calls.some((call) => call[1].cluster === 'management-a')).toBe(true)
    );
    host.request.mockClear();
    host.cluster = 'management-b';
    rerender(
      <MemoryRouter initialEntries={['/c/management-a/fleet-efficiency']}>
        <Route />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(
        host.request.mock.calls.some(
          (call) =>
            call[0].includes('optimizationrecommendations') && call[1].cluster === 'management-b'
        )
      ).toBe(true)
    );
    expect(
      host.request.mock.calls.every(
        (call) => call[1].method === 'GET' && call[1].cluster === 'management-b'
      )
    ).toBe(true);
  });
});
