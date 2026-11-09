import type { Recommendation } from './advisor.generated';
import type { InspectionOperatorInspection as OperatorInspection } from './operator-inspection.generated';

export type Decision =
  'approve' | 'reject' | 'defer' | 'request-observation' | 'exception' | 'cancel';
export const decisions: Decision[] = [
  'approve',
  'reject',
  'defer',
  'request-observation',
  'exception',
  'cancel',
];
export type Action = Decision | 'create-pull-request';
export type Phase =
  | 'AwaitingApproval'
  | 'Approved'
  | 'Rejected'
  | 'Deferred'
  | 'Observing'
  | 'Exception'
  | 'Cancelled'
  | 'PullRequestOpen'
  | 'Validating'
  | 'Completed';
export type ValidationState =
  'NotStarted' | 'Collecting' | 'Healthy' | 'Warning' | 'Failed' | 'RolledBack' | 'Inconclusive';
export interface Requests {
  cpu?: string;
  memory?: string;
}
export interface VpaBounds {
  containerName: string;
  lowerBound?: Requests;
  target?: Requests;
  upperBound?: Requests;
  uncappedTarget?: Requests;
}
export interface VpaRecord {
  apiVersion: 'autoscaling.k8s.io/v1';
  kind: 'VerticalPodAutoscaler';
  metadata: { name: string; namespace: string; uid?: string };
  spec: {
    targetRef: { apiVersion: string; kind: string; name: string };
    updatePolicy?: { updateMode?: string };
    resourcePolicy?: {
      containerPolicies?: {
        containerName: string;
        mode?: string;
        minAllowed?: Requests;
        maxAllowed?: Requests;
        controlledResources?: string[];
      }[];
    };
  };
  status?: { recommendation?: { containerRecommendations: VpaBounds[] } };
}
export interface AuditEvent {
  id: string;
  actor: string;
  timestamp: string;
  action: string;
  reason: string;
  generation: number;
  evidenceVersion: string;
  deferUntil?: string;
}
export interface OptimizationRecommendation {
  apiVersion: 'optimization.aks.io/v1alpha1';
  kind: 'OptimizationRecommendation';
  metadata: {
    name: string;
    namespace: string;
    uid: string;
    resourceVersion: string;
    generation: number;
    [key: string]: unknown;
  };
  spec: {
    finding: Recommendation;
    inspection?: OperatorInspection;
    type: string;
    source: 'VPA' | 'Deterministic' | 'AI-assisted';
    target: {
      clusterResourceId: string;
      namespace: string;
      apiVersion: string;
      kind: string;
      name: string;
      uid: string;
      container: string;
    };
    generatedAt: string;
    expiresAt: string;
    evidenceCollectedAt: string;
    evidenceVersion: string;
    maxEvidenceAgeHours: number;
    completeness: 'complete' | 'partial' | 'unknown';
    observationWindow: { start: string; end: string; coverageRatio: number | null };
    risk: {
      level: 'low' | 'medium' | 'high';
      reasons: string[];
      requiredChecks: string[];
      restart: string;
    };
    checks: { name: string; state: 'Pass' | 'Fail' | 'Unknown'; detail: string }[];
    approvalsRequired: string[];
    sourceRevision: string;
    implementation?: {
      owner: string;
      repository: string;
      configurationPath: string;
      baseBranch: string;
    };
    vpa?: { name: string; namespace: string; bounds?: VpaBounds; updateMode?: string };
    ai?: {
      generator: string;
      model: string;
      analyzedAt: string;
      evidenceVersion: string;
      policyVersion: string;
      explanation: string;
      alternatives: string[];
      limitations: string[];
      humanValidation: string[];
      confidence: string;
    };
    relatedResources?: {
      apiVersion: string;
      kind: string;
      namespace?: string;
      name: string;
      plugin: 'keda' | 'karpenter';
    }[];
  };
  status: {
    phase: Phase;
    observedGeneration: number;
    evidenceVersion: string;
    sourceConfiguration: 'Unchanged' | 'Changed' | 'Unknown';
    supersededBy?: string;
    approvals: {
      role: string;
      actor: string;
      generation: number;
      evidenceVersion: string;
      sourceRevision: string;
    }[];
    pullRequest: {
      state: 'NotCreated' | 'Open' | 'Merged' | 'Closed' | 'Failed';
      number?: number;
      url?: string;
      message?: string;
    };
    validation: {
      state: ValidationState;
      deployedAt?: string;
      window?: string;
      rollback?: string;
      metrics?: { name: string; baseline: number | null; current: number | null; unit: string }[];
    };
    timeline: AuditEvent[];
  };
}
export interface Capabilities {
  identity: string;
  allowed: Action[];
  approvalRole?: string;
  backend: 'unavailable' | 'simulator' | 'connected';
  github: boolean;
  metrics: boolean;
  installedPlugins: string[];
}
export interface ActionRequest {
  uid: string;
  resourceVersion: string;
  generation: number;
  evidenceVersion: string;
  sourceRevision: string;
  idempotencyKey: string;
  action: Action;
  reason: string;
  acknowledgements: string[];
  deferUntil?: string;
}
export interface RecommendationProvider {
  list(signal?: AbortSignal): Promise<OptimizationRecommendation[]>;
  capabilities(
    recommendation?: OptimizationRecommendation,
    signal?: AbortSignal
  ): Promise<Capabilities>;
  act(
    recommendation: OptimizationRecommendation,
    request: ActionRequest
  ): Promise<OptimizationRecommendation>;
}
