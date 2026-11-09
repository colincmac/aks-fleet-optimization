import type { OptimizationRecommendation, VpaRecord } from '../models/review';
import inspectionData from '../../../../examples/operator-inspection.json';
import catalogData from '../../../../examples/operator-catalog.json';
import { parseOperatorCatalog, parseOperatorInspection } from '../api/contracts';

export function packPreviewRecommendation(
  scenario: string,
  now = new Date()
): OptimizationRecommendation {
  const record = makeRecommendation(now);
  const inspection = parseOperatorInspection(structuredClone(inspectionData));
  record.spec.inspection = inspection;
  record.spec.finding.rule_id = inspection.card.manifest.id;
  record.spec.finding.rule_version = inspection.card.manifest.version;
  record.spec.target.clusterResourceId = inspection.capabilities[0].cluster_resource_id;
  record.spec.finding.resource_id = record.spec.target.clusterResourceId;
  if (scenario === 'baseline') {
    inspection.mode = 'baseline';
    inspection.capabilities.forEach((capability) => {
      capability.mode = 'baseline';
    });
    record.spec.finding.proposed_requests = null;
    record.spec.finding.summary = inspection.card.manifest.baseline_summary;
  }
  if (scenario === 'unsupported') {
    inspection.capabilities[0].status = 'unsupported';
    inspection.capabilities[0].checks[0] = {
      code: 'synthetic.unsupported',
      status: 'unsupported',
      reason_codes: ['unsupported_source_shape'],
    };
  }
  if (scenario === 'limit' || scenario === 'floor') {
    const id = scenario === 'limit' ? 'AKS-MEM-005' : 'AKS-AS-005';
    inspection.card = parseOperatorCatalog(catalogData).cards.find(
      (card) => card.manifest.id === id
    )!;
    inspection.capabilities = [];
    record.spec.finding.rule_id = id;
    record.spec.finding.rule_version = inspection.card.manifest.version;
    record.spec.finding.proposed_requests = null;
    if (scenario === 'limit') {
      record.spec.finding.current_limits = { memory_mib: 1024 };
      record.spec.finding.proposed_limits = { memory_mib: 600 };
    } else {
      record.spec.finding.current_requests = null;
      record.spec.finding.current_replica_floor = 2;
      record.spec.finding.proposed_replica_floor = 1;
    }
  }
  return record;
}

export function makeRecommendation(now = new Date()): OptimizationRecommendation {
  const ago = (hours: number) => new Date(now.getTime() - hours * 3600000).toISOString();
  const cluster =
    '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/synthetic-fleet/providers/Microsoft.ContainerService/managedClusters/cedar-east';
  return {
    apiVersion: 'optimization.aks.io/v1alpha1',
    kind: 'OptimizationRecommendation',
    metadata: {
      name: 'rec-001',
      namespace: 'fleet-efficiency-system',
      uid: 'synthetic-rec-001',
      resourceVersion: '1',
      generation: 1,
    },
    spec: {
      finding: {
        id: 'rec-001',
        rule_id: 'cpu-request-overprovisioned',
        rule_version: '1.0.0',
        title: 'Review API container CPU requests',
        summary:
          'Observed CPU peaks remain below the policy-bounded proposal. Validate with the workload owner before changing requests.',
        resource_id: cluster,
        cluster_name: 'cedar-east',
        namespace: 'storefront',
        workload: 'catalog-api',
        severity: 'medium',
        confidence: 'high',
        category: 'workload-rightsizing',
        estimated_monthly_savings: null,
        currency: null,
        current_requests: { cpu_mcores: 1000, memory_mib: 2048 },
        proposed_requests: { cpu_mcores: 650, memory_mib: null },
        evidence: [
          {
            metric: 'cpu_usage_p95',
            value: 320,
            unit: 'mCPU',
            source: 'synthetic Prometheus export',
          },
          {
            metric: 'cpu_usage_p99',
            value: 460,
            unit: 'mCPU',
            source: 'synthetic Prometheus export',
          },
          {
            metric: 'cpu_usage_peak',
            value: 520,
            unit: 'mCPU',
            source: 'synthetic Prometheus export',
          },
          {
            metric: 'cpu_throttling_max',
            value: 0.002,
            unit: 'ratio',
            source: 'synthetic Prometheus export',
          },
          { metric: 'oom_kills', value: 0, unit: 'events', source: 'synthetic Prometheus export' },
        ],
        prerequisites: ['Owner SLO review', 'Canary deployment approved'],
        risks: ['Rolling restart required'],
        validation_steps: [
          'Observe throttling, readiness, OOM events and latency over the validation window.',
        ],
        proposed_actions: ['Propose a CPU request update through the configuration repository.'],
        rollback_steps: ['Revert the configuration pull request if the workload SLO regresses.'],
        owner: 'Commerce platform',
        metadata: {},
      },
      type: 'VPAResourceRecommendation',
      source: 'VPA',
      target: {
        clusterResourceId: cluster,
        namespace: 'storefront',
        apiVersion: 'apps/v1',
        kind: 'Deployment',
        name: 'catalog-api',
        uid: 'synthetic-workload-001',
        container: 'api',
      },
      generatedAt: ago(2),
      expiresAt: ago(-14 * 24),
      evidenceCollectedAt: ago(3),
      evidenceVersion: 'sha256:synthetic-evidence-001',
      maxEvidenceAgeHours: 24,
      completeness: 'complete',
      observationWindow: { start: ago(30 * 24 + 3), end: ago(3), coverageRatio: 0.994 },
      risk: {
        level: 'medium',
        reasons: [
          'A resource request change triggers a rolling restart.',
          'CPU proposal only; memory remains unchanged.',
        ],
        requiredChecks: ['PodDisruptionBudget', 'AutoscalerInteraction', 'OwnerPolicy'],
        restart: 'Rolling restart; respect the disruption budget and canary policy.',
      },
      checks: [
        {
          name: 'PodDisruptionBudget',
          state: 'Pass',
          detail: 'Synthetic owner review confirms one available disruption.',
        },
        {
          name: 'AutoscalerInteraction',
          state: 'Pass',
          detail: 'HPA and KEDA explicitly absent; VPA is recommendation-only.',
        },
        {
          name: 'OwnerPolicy',
          state: 'Pass',
          detail: 'Minimum 500 mCPU; maximum CPU reduction 40%; reviewed SLO policy.',
        },
      ],
      approvalsRequired: ['ApplicationOwner', 'PlatformOwner'],
      sourceRevision: 'synthetic-commit-001',
      implementation: {
        owner: 'example',
        repository: 'synthetic-workloads',
        configurationPath: 'deploy/catalog/values.yaml',
        baseBranch: 'main',
      },
      vpa: {
        name: 'catalog-api',
        namespace: 'storefront',
        updateMode: 'Off',
        bounds: {
          containerName: 'api',
          lowerBound: { cpu: '400m', memory: '1Gi' },
          target: { cpu: '650m', memory: '1536Mi' },
          upperBound: { cpu: '900m', memory: '2Gi' },
          uncappedTarget: { cpu: '600m', memory: '1400Mi' },
        },
      },
    },
    status: {
      phase: 'AwaitingApproval',
      observedGeneration: 1,
      evidenceVersion: 'sha256:synthetic-evidence-001',
      sourceConfiguration: 'Unchanged',
      approvals: [],
      pullRequest: { state: 'NotCreated' },
      validation: { state: 'NotStarted' },
      timeline: [
        {
          id: 'generated-001',
          actor: 'Deterministic advisor',
          timestamp: ago(2),
          action: 'Recommendation generated',
          reason: 'Policy-bounded CPU proposal; VPA retained as separate evidence.',
          generation: 1,
          evidenceVersion: 'sha256:synthetic-evidence-001',
        },
      ],
    },
  };
}

export function demoRecommendations(now = new Date()): OptimizationRecommendation[] {
  const names = [
    'catalog-api',
    'order-worker',
    'inventory-sync',
    'checkout-api',
    'search-indexer',
    'notification-worker',
    'edge-gateway',
    'session-store',
    'report-worker',
    'billing-api',
    'event-router',
    'image-worker',
  ];
  return names.map((name, index) => {
    const record = makeRecommendation(now);
    const id = `rec-${String(index + 1).padStart(3, '0')}`;
    record.metadata = { ...record.metadata, name: id, uid: `synthetic-${id}` };
    record.spec.finding.id = id;
    record.spec.finding.workload = name;
    record.spec.target.name = name;
    record.spec.target.uid = `synthetic-workload-${index}`;
    record.spec.finding.cluster_name =
      index % 3 === 0 ? 'cedar-east' : index % 3 === 1 ? 'birch-west' : 'maple-central';
    record.spec.target.clusterResourceId = record.spec.target.clusterResourceId.replace(
      'cedar-east',
      record.spec.finding.cluster_name
    );
    record.spec.finding.resource_id = record.spec.target.clusterResourceId;
    record.spec.target.namespace = index % 2 === 0 ? 'storefront' : 'operations';
    record.spec.finding.namespace = record.spec.target.namespace;
    record.spec.finding.owner = index % 2 === 0 ? 'Commerce platform' : 'Core services';
    record.spec.target.kind = index === 7 ? 'StatefulSet' : 'Deployment';
    record.spec.finding.current_requests = {
      cpu_mcores: [1000, 2000, 500, 1000][index % 4],
      memory_mib: 2048,
    };
    record.spec.finding.proposed_requests = {
      cpu_mcores: [650, 1400, 350, 750][index % 4],
      memory_mib: null,
    };
    if (record.spec.vpa)
      record.spec.vpa = {
        ...record.spec.vpa,
        name,
        namespace: record.spec.target.namespace,
        bounds: {
          ...record.spec.vpa.bounds!,
          target: { cpu: `${record.spec.finding.proposed_requests.cpu_mcores}m`, memory: '1536Mi' },
        },
      };
    if (index % 3 === 1) {
      record.spec.source = 'AI-assisted';
      record.spec.type = 'CpuRequestReview';
      record.spec.ai = {
        generator: 'Synthetic explanation fixture',
        model: 'example-model (not invoked)',
        analyzedAt: record.spec.generatedAt,
        evidenceVersion: record.spec.evidenceVersion,
        policyVersion: 'grounded-summary/1',
        explanation:
          'The deterministic CPU proposal retains headroom above the observed peak. VPA values are supporting evidence, not an instruction to apply them. Review burst behavior and the owner SLO before proceeding.',
        alternatives: [
          'Retain current requests for another observation window.',
          'Test the proposed CPU request in a canary.',
        ],
        limitations: [
          'Historic observations do not guarantee future load.',
          'No reconciled cost data is available.',
        ],
        humanValidation: ['Workload owner confirms representative traffic and restart timing.'],
        confidence: 'Interpretation only; not a policy gate',
      };
    }
    if (index === 2) {
      record.status.phase = 'Approved';
      record.status.approvals = record.spec.approvalsRequired.map((role, roleIndex) => ({
        role,
        actor: `synthetic-reviewer-${roleIndex}`,
        generation: 1,
        evidenceVersion: record.spec.evidenceVersion,
        sourceRevision: record.spec.sourceRevision,
      }));
    }
    if (index === 3 || index === 4) {
      record.status.phase = 'PullRequestOpen';
      record.status.pullRequest = {
        state: 'Open',
        number: 142 + index,
        url: `https://github.com/example/synthetic-workloads/pull/${142 + index}`,
      };
    }
    if (index === 5 || index === 6 || index === 7) {
      record.status.phase = index === 5 ? 'Validating' : 'Completed';
      record.status.pullRequest = { state: 'Merged', number: 140 + index };
      record.status.validation = {
        state: index === 5 ? 'Collecting' : index === 6 ? 'Healthy' : 'RolledBack',
        deployedAt: new Date(now.getTime() - 3600000).toISOString(),
        window: '24 hours',
        rollback: index === 7 ? 'Configuration reverted by owner' : 'Not requested',
        metrics: [
          { name: 'CPU throttling', baseline: 0.2, current: index === 5 ? null : 0.3, unit: '%' },
          { name: 'OOM kills', baseline: 0, current: index === 5 ? null : 0, unit: 'events' },
          { name: 'Restarts', baseline: 0, current: index === 5 ? null : 1, unit: 'events' },
          {
            name: 'Ready replicas',
            baseline: 3,
            current: index === 5 ? null : 3,
            unit: 'replicas',
          },
        ],
      };
    }
    if (index === 8) record.spec.expiresAt = new Date(now.getTime() - 3600000).toISOString();
    if (index === 9) record.status.supersededBy = 'rec-013';
    if (index === 10) {
      record.spec.completeness = 'partial';
      record.spec.checks[1].state = 'Unknown';
      record.spec.checks[1].detail = 'KEDA API permission denied; interaction unknown.';
      record.spec.finding.confidence = 'low';
      record.spec.risk.level = 'high';
      const pack = packPreviewRecommendation('unsupported', now);
      record.spec.inspection = pack.spec.inspection;
      record.spec.finding.rule_id = pack.spec.finding.rule_id;
      record.spec.finding.rule_version = pack.spec.finding.rule_version;
      record.spec.target.clusterResourceId = pack.spec.target.clusterResourceId;
      record.spec.finding.resource_id = pack.spec.finding.resource_id;
    }
    if (index === 11) {
      record.spec.evidenceCollectedAt = new Date(now.getTime() - 48 * 3600000).toISOString();
      record.status.phase = 'Deferred';
    }
    return record;
  });
}

export function demoVpas(recommendations: OptimizationRecommendation[]): VpaRecord[] {
  return recommendations.map((record) => ({
    apiVersion: 'autoscaling.k8s.io/v1',
    kind: 'VerticalPodAutoscaler',
    metadata: { name: record.spec.target.name, namespace: record.spec.target.namespace },
    spec: {
      targetRef: {
        apiVersion: record.spec.target.apiVersion,
        kind: record.spec.target.kind,
        name: record.spec.target.name,
      },
      updatePolicy: { updateMode: 'Off' },
    },
    status: {
      recommendation: {
        containerRecommendations: record.spec.vpa?.bounds ? [record.spec.vpa.bounds] : [],
      },
    },
  }));
}
