import type {
  ActionRequest,
  Capabilities,
  OptimizationRecommendation,
  Phase,
  RecommendationProvider,
} from '../models/review';
import { approvalsSatisfied, validateAction } from '../utils/safety';

export const deniedCapabilities: Capabilities = {
  identity: 'Unavailable',
  allowed: [],
  backend: 'unavailable',
  github: false,
  metrics: false,
  installedPlugins: [],
};

export class SimulatorProvider implements RecommendationProvider {
  private records: OptimizationRecommendation[];
  private results = new Map<string, { fingerprint: string; record: OptimizationRecommendation }>();
  role = 'ApplicationOwner';
  constructor(
    records: OptimizationRecommendation[],
    private clock = () => new Date()
  ) {
    this.records = structuredClone(records);
  }
  async list() {
    return structuredClone(this.records);
  }
  async capabilities(): Promise<Capabilities> {
    return {
      identity: `synthetic:${this.role}`,
      approvalRole: this.role,
      allowed:
        this.role === 'Viewer'
          ? []
          : [
              'approve',
              'reject',
              'defer',
              'request-observation',
              'exception',
              ...(this.role === 'PlatformOwner' ? ['cancel' as const] : []),
              'create-pull-request',
            ],
      backend: 'simulator',
      github: true,
      metrics: false,
      installedPlugins: [],
    };
  }
  async act(recommendation: OptimizationRecommendation, request: ActionRequest) {
    const capabilities = await this.capabilities();
    const record = this.records.find((item) => item.metadata.uid === recommendation.metadata.uid);
    if (!record) throw new Error('Recommendation not found.');
    if (!capabilities.allowed.includes(request.action)) throw new Error('Permission denied');
    const key = `${record.metadata.uid}:${capabilities.identity}:${request.idempotencyKey}`;
    const fingerprint = JSON.stringify(request);
    const existing = this.results.get(key);
    if (existing) {
      if (existing.fingerprint !== fingerprint)
        throw new Error('Idempotency key was reused with different content.');
      return structuredClone(existing.record);
    }
    validateAction(record, request, capabilities, this.clock());
    const next = structuredClone(record);
    const phases: Partial<Record<ActionRequest['action'], Phase>> = {
      reject: 'Rejected',
      defer: 'Deferred',
      'request-observation': 'Observing',
      exception: 'Exception',
      cancel: 'Cancelled',
    };
    if (request.action === 'approve') {
      next.status.approvals.push({
        role: capabilities.approvalRole!,
        actor: capabilities.identity,
        generation: request.generation,
        evidenceVersion: request.evidenceVersion,
        sourceRevision: request.sourceRevision,
      });
      next.status.phase = approvalsSatisfied(next) ? 'Approved' : 'AwaitingApproval';
    } else if (request.action === 'create-pull-request') {
      next.status.phase = 'PullRequestOpen';
      next.status.pullRequest = {
        state: 'Open',
        number: 900 + this.results.size,
        message: 'Simulated pull request. No repository was contacted.',
      };
    } else next.status.phase = phases[request.action]!;
    next.status.timeline.push({
      id: request.idempotencyKey,
      actor: capabilities.identity,
      timestamp: this.clock().toISOString(),
      action: request.action,
      reason: request.reason.trim(),
      generation: request.generation,
      evidenceVersion: request.evidenceVersion,
      ...(request.deferUntil ? { deferUntil: request.deferUntil } : {}),
    });
    next.metadata.resourceVersion = String(Number(next.metadata.resourceVersion) + 1);
    this.records = this.records.map((item) =>
      item.metadata.uid === next.metadata.uid ? next : item
    );
    this.results.set(key, { fingerprint, record: structuredClone(next) });
    return structuredClone(next);
  }
}

export type JsonRequest = (path: string, init?: RequestInit) => Promise<unknown>;

export class BackendProvider implements RecommendationProvider {
  constructor(
    private read: RecommendationProvider['list'],
    private request: JsonRequest | undefined,
    private parse: (data: unknown) => OptimizationRecommendation
  ) {}
  list(signal?: AbortSignal) {
    return this.read(signal);
  }
  private path(record: OptimizationRecommendation) {
    return `/api/v1/namespaces/${encodeURIComponent(record.metadata.namespace)}/recommendations/${encodeURIComponent(record.metadata.name)}`;
  }
  async capabilities(
    record?: OptimizationRecommendation,
    signal?: AbortSignal
  ): Promise<Capabilities> {
    if (!this.request || !record) return deniedCapabilities;
    const result = (await this.request(`${this.path(record)}/capabilities`, {
      signal,
    })) as Partial<Capabilities>;
    if (
      typeof result.identity !== 'string' ||
      !Array.isArray(result.allowed) ||
      !result.allowed.every((action) =>
        [
          'approve',
          'reject',
          'defer',
          'request-observation',
          'exception',
          'cancel',
          'create-pull-request',
        ].includes(action)
      )
    )
      return deniedCapabilities;
    return {
      identity: result.identity,
      allowed: result.allowed,
      approvalRole: typeof result.approvalRole === 'string' ? result.approvalRole : undefined,
      backend: 'connected',
      github: result.github === true,
      metrics: result.metrics === true,
      installedPlugins: [],
    };
  }
  async act(record: OptimizationRecommendation, request: ActionRequest) {
    if (!this.request) throw new Error('Approval backend is not configured.');
    validateAction(record, request, await this.capabilities(record));
    const suffix = request.action === 'create-pull-request' ? 'pull-request' : 'decisions';
    return this.parse(
      await this.request(`${this.path(record)}/${suffix}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'If-Match': record.metadata.resourceVersion,
          'Idempotency-Key': request.idempotencyKey,
        },
        body: JSON.stringify(request),
      })
    );
  }
}
