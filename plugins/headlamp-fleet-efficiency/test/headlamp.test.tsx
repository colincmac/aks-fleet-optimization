import type { ComponentType } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { makeRecommendation } from '../src/demo/fixtures';

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
import '../src/index';
import { OptimizationRecommendation } from '../src/resources/OptimizationRecommendation';
import { VerticalPodAutoscaler } from '../src/resources/VerticalPodAutoscaler';

afterEach(cleanup);
describe('Headlamp registration and management context', () => {
  it('registers five routes and typed API resources', () => {
    expect(host.routes.map((route) => route.path)).toEqual([
      '/fleet-efficiency',
      '/fleet-efficiency/catalog',
      '/fleet-efficiency/recommendations',
      '/fleet-efficiency/recommendations/:namespace/:name',
      '/fleet-efficiency/settings',
    ]);
    expect(OptimizationRecommendation.apiVersion).toBe('optimization.aks.io/v1alpha1');
    expect(VerticalPodAutoscaler.apiVersion).toBe('autoscaling.k8s.io/v1');
  });
  it('recreates GET-only readers when the selected management context changes', async () => {
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
