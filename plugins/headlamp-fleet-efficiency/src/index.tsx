import { ApiProxy, registerRoute, registerSidebarEntry } from '@kinvolk/headlamp-plugin/lib';
import { getCluster } from '@kinvolk/headlamp-plugin/lib/Utils';
import { useTheme } from '@mui/material';
import { useEffect, useState } from 'react';
import { App } from './ui/App';
import { BackendProvider, type JsonRequest } from './api/provider';
import { boundedList } from './api/kubernetes';
import { parseRecommendation, parseRecommendationList, parseVpa } from './api/contracts';
import { OptimizationRecommendation } from './resources/OptimizationRecommendation';
import { VerticalPodAutoscaler } from './resources/VerticalPodAutoscaler';
import type { VpaRecord } from './models/review';
import type { RelatedKubernetesResource } from './ui/renderers';

export interface FleetAdvisorIntegration {
  namespace?: string;
  governanceRequest?: JsonRequest;
  relatedLinks?: Partial<
    Record<'keda' | 'karpenter', (resource: RelatedKubernetesResource) => string>
  >;
}
let integration: FleetAdvisorIntegration = {};
export function configureFleetAdvisor(configuration: FleetAdvisorIntegration) {
  integration = configuration;
}

function FleetAdvisorRoutes() {
  const cluster = getCluster();
  const namespace = integration.namespace ?? 'fleet-efficiency-system';
  return (
    <FleetAdvisorContext key={`${cluster}:${namespace}`} cluster={cluster} namespace={namespace} />
  );
}

function FleetAdvisorContext({
  cluster,
  namespace,
}: {
  cluster: string | null;
  namespace: string;
}) {
  const theme = useTheme();
  const [vpas, setVpas] = useState<VpaRecord[]>([]);
  const [vpaError, setVpaError] = useState<string>();
  const [provider] = useState(
    () =>
      new BackendProvider(
        async (signal) => {
          if (!cluster)
            throw new Error('Select the management cluster before loading fleet recommendations.');
          const records = await boundedList(
            (path, options) => ApiProxy.request(path, { ...options, cluster }),
            `/apis/${OptimizationRecommendation.apiVersion}/namespaces/${encodeURIComponent(namespace)}/${OptimizationRecommendation.apiName}`,
            signal
          );
          return parseRecommendationList(records, namespace);
        },
        integration.governanceRequest,
        parseRecommendation
      )
  );
  useEffect(() => {
    const controller = new AbortController();
    if (cluster)
      boundedList(
        (path, options) => ApiProxy.request(path, { ...options, cluster }),
        `/apis/${VerticalPodAutoscaler.apiVersion}/${VerticalPodAutoscaler.apiName}`,
        controller.signal
      )
        .then((items) => {
          if (!controller.signal.aborted) setVpas(items.map(parseVpa));
        })
        .catch(() => {
          if (!controller.signal.aborted)
            setVpaError('Live VPA API absent, denied or unsupported in this management context.');
        });
    return () => controller.abort();
  }, [cluster]);
  return (
    <App
      provider={provider}
      basePath={`/c/${encodeURIComponent(cluster ?? '')}/fleet-efficiency`}
      namespace={namespace}
      dark={theme.palette.mode === 'dark'}
      vpas={vpas}
      vpaError={vpaError}
      relatedLinks={integration.relatedLinks}
    />
  );
}

registerSidebarEntry({
  parent: null,
  name: 'fleet-efficiency',
  label: 'Fleet Efficiency',
  url: '/fleet-efficiency',
  icon: 'mdi:shield-check-outline',
});
for (const route of [
  { path: '/fleet-efficiency', name: 'fleet-efficiency-overview' },
  { path: '/fleet-efficiency/catalog', name: 'fleet-efficiency-catalog' },
  { path: '/fleet-efficiency/recommendations', name: 'fleet-efficiency-recommendations' },
  { path: '/fleet-efficiency/recommendations/:namespace/:name', name: 'fleet-efficiency-detail' },
  { path: '/fleet-efficiency/settings', name: 'fleet-efficiency-settings' },
])
  registerRoute({
    ...route,
    sidebar: 'fleet-efficiency',
    exact: true,
    component: FleetAdvisorRoutes,
  });
