import type {
  Action,
  ActionRequest,
  Capabilities,
  OptimizationRecommendation,
  VpaRecord,
} from '../models/review';

export const acknowledgementLabels = [
  'Target workload and container',
  'Current and proposed requests',
  'Restart or eviction implications',
  'Risk classification and policy checks',
  'Required owner approvals',
  'Evidence freshness and generation',
  'Source configuration has not changed',
];

export function parseQuantity(
  value: string | undefined,
  resource: 'cpu' | 'memory'
): number | null {
  const match = value?.match(/^(\d+(?:\.\d*)?|\.\d+)([eE][+-]?\d+|[numkKMGTPE]|[KMGTPE]i)?$/);
  if (!match) return null;
  const suffix = match[2] ?? '';
  const decimal: Record<string, number> = {
    '': 1,
    n: 1e-9,
    u: 1e-6,
    m: 1e-3,
    k: 1e3,
    K: 1e3,
    M: 1e6,
    G: 1e9,
    T: 1e12,
    P: 1e15,
    E: 1e18,
  };
  const binary = ['Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei'].indexOf(suffix);
  const factor =
    binary >= 0
      ? 1024 ** (binary + 1)
      : /^[eE][+-]?\d+$/.test(suffix)
        ? 10 ** Number(suffix.slice(1))
        : decimal[suffix];
  const parsed = Number(match[1]) * factor;
  const normalized = resource === 'cpu' ? parsed * 1000 : parsed / (1024 * 1024);
  return Number.isFinite(normalized) &&
    normalized >= 0 &&
    !(Number(match[1]) > 0 && normalized === 0)
    ? normalized
    : null;
}

export function percentageChange(
  current: number | null | undefined,
  proposed: number | null | undefined
): number | null {
  if (
    current == null ||
    proposed == null ||
    !Number.isFinite(current) ||
    !Number.isFinite(proposed) ||
    current <= 0 ||
    proposed < 0
  )
    return null;
  return Math.round(((proposed - current) / current) * 1000) / 10;
}

export function freshness(record: OptimizationRecommendation, now = new Date()): string[] {
  const { spec, status, metadata } = record;
  const reasons: string[] = [];
  const generated = Date.parse(spec.generatedAt);
  const collected = Date.parse(spec.evidenceCollectedAt);
  const expires = Date.parse(spec.expiresAt);
  const age = now.getTime() - collected;
  if (
    ![generated, collected, expires, now.getTime()].every(Number.isFinite) ||
    generated > now.getTime() ||
    collected > generated ||
    expires <= generated
  )
    reasons.push('Invalid evidence timestamps');
  if (expires <= now.getTime()) reasons.push('Expired');
  if (
    !Number.isFinite(spec.maxEvidenceAgeHours) ||
    spec.maxEvidenceAgeHours <= 0 ||
    age > spec.maxEvidenceAgeHours * 3600000 ||
    age < 0
  )
    reasons.push('Stale evidence');
  if (status.supersededBy) reasons.push('Superseded');
  if (status.observedGeneration !== metadata.generation) reasons.push('Generation not observed');
  if (!spec.evidenceVersion || spec.evidenceVersion !== status.evidenceVersion)
    reasons.push('Evidence version changed');
  return reasons;
}

export function approvalBlockers(record: OptimizationRecommendation, now = new Date()): string[] {
  const reasons = freshness(record, now);
  const inspection = record.spec.inspection;
  if (inspection) {
    if (inspection.mode !== 'guarded')
      reasons.push('Baseline assessment cannot authorize a proposal');
    if (
      inspection.card.manifest.evidence_kind === 'metrics' &&
      (!inspection.capabilities.length ||
        inspection.capabilities.some(
          (capability) =>
            capability.status !== 'available' ||
            capability.checks.some((check) => check.status !== 'available')
        ))
    )
      reasons.push('Pack source capability is not available');
  }
  if (record.spec.completeness !== 'complete') reasons.push('Incomplete evidence');
  if (record.spec.vpa && record.spec.vpa.updateMode !== 'Off')
    reasons.push('VPA mode is mutating or unknown');
  if (record.status.sourceConfiguration !== 'Unchanged' || !record.spec.sourceRevision)
    reasons.push('Source configuration changed or unknown');
  if (
    record.spec.checks.length === 0 ||
    record.spec.checks.some((check) => check.state !== 'Pass') ||
    record.spec.risk.requiredChecks.some(
      (name) => !record.spec.checks.some((check) => check.name === name && check.state === 'Pass')
    )
  )
    reasons.push('Required checks not satisfied');
  const proposed = record.spec.finding.proposed_requests;
  const current = record.spec.finding.current_requests;
  if (
    record.spec.finding.current_replica_floor != null ||
    record.spec.finding.proposed_replica_floor != null
  )
    reasons.push('Replica-floor approval is not supported by this review workflow');
  if (record.spec.finding.current_limits != null || record.spec.finding.proposed_limits != null)
    reasons.push('Memory-limit approval is not supported by this review workflow');
  const fields = ['cpu_mcores', 'memory_mib'] as const;
  if (
    !proposed ||
    !fields.some(
      (field) => proposed[field] != null && Number.isFinite(proposed[field]) && proposed[field]! > 0
    ) ||
    fields.some(
      (field) =>
        proposed[field] != null &&
        (!Number.isFinite(proposed[field]) ||
          proposed[field]! <= 0 ||
          current?.[field] == null ||
          !Number.isFinite(current[field]) ||
          current[field]! <= 0)
    )
  )
    reasons.push('No valid deterministic resource proposal and baseline');
  if (
    !record.metadata.resourceVersion ||
    !record.metadata.uid ||
    !record.spec.target.uid ||
    !Number.isInteger(record.metadata.generation) ||
    record.metadata.generation < 1
  )
    reasons.push('Missing concurrency or workload identity');
  if (!record.spec.approvalsRequired.length) reasons.push('Approval policy unavailable');
  return [...new Set(reasons)];
}

export function approvalsSatisfied(record: OptimizationRecommendation): boolean {
  const valid = record.status.approvals.filter(
    (approval) =>
      approval.generation === record.metadata.generation &&
      approval.evidenceVersion === record.spec.evidenceVersion &&
      approval.sourceRevision === record.spec.sourceRevision
  );
  return (
    record.spec.approvalsRequired.length > 0 &&
    record.spec.approvalsRequired.every((role) =>
      valid.some((approval) => approval.role === role)
    ) &&
    new Set(valid.map((approval) => approval.actor)).size >= record.spec.approvalsRequired.length
  );
}

export function actionBlockers(
  record: OptimizationRecommendation,
  action: Action,
  capabilities: Capabilities,
  now = new Date()
): string[] {
  const reasons: string[] = [];
  if (capabilities.backend === 'unavailable') reasons.push('Approval backend is not configured');
  if (!capabilities.allowed.includes(action)) reasons.push('Permission denied');
  if (action === 'approve' || action === 'create-pull-request')
    reasons.push(...approvalBlockers(record, now));
  if (
    ['Rejected', 'Cancelled', 'Completed', 'PullRequestOpen', 'Validating'].includes(
      record.status.phase
    )
  )
    reasons.push('Recommendation is not open for decisions');
  if (
    action === 'approve' &&
    (!['AwaitingApproval', 'Deferred', 'Observing'].includes(record.status.phase) ||
      !capabilities.approvalRole ||
      !record.spec.approvalsRequired.includes(capabilities.approvalRole) ||
      record.status.approvals.some(
        (approval) =>
          approval.actor === capabilities.identity || approval.role === capabilities.approvalRole
      ))
  )
    reasons.push('Approval already recorded or role not required');
  if (action === 'create-pull-request') {
    if (!capabilities.github || !record.spec.implementation)
      reasons.push('GitHub integration unavailable');
    if (record.status.phase !== 'Approved' || !approvalsSatisfied(record))
      reasons.push('Required approvals are missing');
    if (record.status.pullRequest.state === 'Open' || record.status.pullRequest.state === 'Merged')
      reasons.push('Pull request already exists');
  }
  return [...new Set(reasons)];
}

export function validateAction(
  record: OptimizationRecommendation,
  request: ActionRequest,
  capabilities: Capabilities,
  now = new Date()
): void {
  if (
    request.uid !== record.metadata.uid ||
    request.resourceVersion !== record.metadata.resourceVersion ||
    request.generation !== record.metadata.generation ||
    request.evidenceVersion !== record.spec.evidenceVersion ||
    request.sourceRevision !== record.spec.sourceRevision
  )
    throw new Error('Recommendation changed. Refresh and review the latest evidence.');
  const blockers = actionBlockers(record, request.action, capabilities, now);
  if (blockers.length) throw new Error(blockers.join('. '));
  if (!request.reason.trim() || request.reason.length > 2000)
    throw new Error('A reason of 1 to 2000 characters is required.');
  if (!request.idempotencyKey) throw new Error('Missing idempotency key.');
  if (
    request.action === 'approve' &&
    acknowledgementLabels.some((label) => !request.acknowledgements.includes(label))
  )
    throw new Error('Review and acknowledge every approval requirement.');
  if (
    request.action === 'defer' &&
    (!request.deferUntil ||
      !Number.isFinite(Date.parse(request.deferUntil)) ||
      Date.parse(request.deferUntil) <= now.getTime() ||
      Date.parse(request.deferUntil) >= Date.parse(record.spec.expiresAt))
  )
    throw new Error('Defer until a future time before recommendation expiration.');
}

export function matchingVpas(
  records: VpaRecord[],
  recommendation: OptimizationRecommendation
): VpaRecord[] {
  const target = recommendation.spec.target;
  return records.filter(
    (record) =>
      record.metadata.namespace === target.namespace &&
      record.spec.targetRef.apiVersion === target.apiVersion &&
      record.spec.targetRef.kind === target.kind &&
      record.spec.targetRef.name === target.name
  );
}

export function vpaMode(record: VpaRecord): string {
  const mode = record.spec.updatePolicy?.updateMode;
  return mode === 'Off'
    ? 'Recommendation only'
    : mode
      ? `Mutating (${mode})`
      : 'Unknown (potentially mutating)';
}

export function safeGithubUrl(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' &&
      url.hostname === 'github.com' &&
      !url.username &&
      !url.password &&
      /^\/[\w.-]+\/[\w.-]+\/pull\/\d+$/.test(url.pathname)
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}

export function timestamp(value?: string): string {
  return value && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : 'Unknown';
}

export function phaseLabel(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/-/g, ' ');
}
