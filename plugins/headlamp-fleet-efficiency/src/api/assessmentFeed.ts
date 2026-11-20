import Ajv from 'ajv';
import addFormats from 'ajv-formats';

export interface AssessedNamespace {
  name: string;
  workloads: { uid: string; name: string; kind: string }[];
}

interface FindingScope {
  id: string;
  rule: string;
  version: string;
  namespace: string | null;
  workload: string | null;
}

export type AssessedFinding = FindingScope &
  (
    | { state: 'blocked'; reasons: string[] }
    | {
        state: 'finding';
        title: string;
        summary: string;
        category: string;
        severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
        confidence: 'high' | 'medium' | 'low';
        evidence: {
          metric: string;
          value: string | number | boolean | null;
          unit: string | null;
        }[];
        comparisons: {
          dimension: string;
          current: number | null;
          proposed: number;
          unit: string;
        }[];
        checks: string[];
        risks: string[];
      }
  );

export interface AssessedCluster {
  id: string;
  uid: string;
  name: string;
  status: 'complete' | 'partial';
  mode: 'baseline' | 'guarded';
  evaluatedAt: string;
  windowStart: string;
  windowEnd: string;
  namespaces: AssessedNamespace[];
  unboundWorkloads: number;
  issues: string[];
  findings: AssessedFinding[];
}

export interface AssessmentFeed {
  schemaVersion: '1';
  clusters: AssessedCluster[];
  failedClusters?: string[];
}

interface RunStatus {
  attemptedAt: string;
  outcome: 'complete' | 'partial' | 'failed';
  staleAfterHours: number;
}

export interface AssessmentViewFeed extends AssessmentFeed {
  scheduled?: true;
  runStatus?: RunStatus;
}

const text = { type: 'string', minLength: 1, maxLength: 4096 };
const nullableText = { anyOf: [text, { type: 'null' }] };
const clock = { type: 'string', format: 'date-time', pattern: '(Z|\\+00:00)$' };
const number = { type: 'number' };
const array = (items: object, maxItems: number) => ({ type: 'array', items, maxItems });
const record = (properties: Record<string, object>) => ({
  type: 'object',
  additionalProperties: false,
  required: Object.keys(properties),
  properties,
});
const scope = {
  id: text,
  rule: text,
  version: text,
  namespace: nullableText,
  workload: nullableText,
};
const ajv = new Ajv();
addFormats(ajv);
const validateRunStatus = ajv.compile<RunStatus>(
  record({
    schemaVersion: { const: '1' },
    attemptedAt: clock,
    outcome: { enum: ['complete', 'partial', 'failed'] },
    staleAfterHours: { type: 'integer', minimum: 1, maximum: 720 },
  })
);
const feedSchema = record({
  schemaVersion: { const: '1' },
  failedClusters: array(text, 32),
  clusters: array(
    record({
      id: text,
      uid: text,
      name: text,
      status: { enum: ['complete', 'partial'] },
      mode: { enum: ['baseline', 'guarded'] },
      evaluatedAt: clock,
      windowStart: clock,
      windowEnd: clock,
      namespaces: array(
        record({
          name: text,
          workloads: array(record({ uid: text, name: text, kind: text }), 10000),
        }),
        10000
      ),
      unboundWorkloads: { type: 'integer', minimum: 0 },
      issues: array(text, 1000),
      findings: array(
        {
          oneOf: [
            record({
              ...scope,
              state: { const: 'blocked' },
              reasons: { ...array(text, 100), minItems: 1 },
            }),
            record({
              ...scope,
              state: { const: 'finding' },
              title: text,
              summary: text,
              category: text,
              severity: { enum: ['critical', 'high', 'medium', 'low', 'info'] },
              confidence: { enum: ['high', 'medium', 'low'] },
              evidence: array(
                record({
                  metric: text,
                  value: {
                    anyOf: [{ type: 'string' }, number, { type: 'boolean' }, { type: 'null' }],
                  },
                  unit: nullableText,
                }),
                1000
              ),
              comparisons: array(
                record({
                  dimension: text,
                  current: { anyOf: [number, { type: 'null' }] },
                  proposed: number,
                  unit: text,
                }),
                5
              ),
              checks: array(text, 100),
              risks: array(text, 100),
            }),
          ],
        },
        10000
      ),
    }),
    32
  ),
});
const validate = ajv.compile<AssessmentFeed>({
  ...feedSchema,
  required: ['schemaVersion', 'clusters'],
});

function unique(values: string[]) {
  return new Set(values).size === values.length;
}

export function parseAssessmentFeed(value: unknown): AssessmentFeed {
  if (
    !validate(value) ||
    !unique(value.clusters.map((cluster) => cluster.id)) ||
    (value.failedClusters !== undefined &&
      (!unique(value.failedClusters) ||
        new Set([...value.clusters.map((cluster) => cluster.id), ...value.failedClusters]).size >
          32 ||
        !value.clusters.some((cluster) => !value.failedClusters?.includes(cluster.id)))) ||
    value.clusters.some(
      (cluster) =>
        ![cluster.windowStart, cluster.windowEnd, cluster.evaluatedAt].every((clock) =>
          Number.isFinite(Date.parse(clock))
        ) ||
        Date.parse(cluster.windowStart) > Date.parse(cluster.windowEnd) ||
        Date.parse(cluster.windowEnd) > Date.parse(cluster.evaluatedAt) ||
        !unique(cluster.namespaces.map((namespace) => namespace.name)) ||
        !unique(
          cluster.namespaces.flatMap((namespace) =>
            namespace.workloads.map((workload) => workload.uid)
          )
        ) ||
        !unique(cluster.findings.map((finding) => finding.id)) ||
        (cluster.mode === 'baseline' &&
          cluster.findings.some(
            (finding) => finding.state === 'finding' && finding.comparisons.length > 0
          ))
    )
  ) {
    throw new Error('Unsupported or inconsistent assessment feed.');
  }
  return value;
}

const maxBytes = 4 * 1024 * 1024;

async function readJson(
  path: string,
  signal: AbortSignal,
  limit: number,
  timeoutMs: number
): Promise<unknown> {
  if (!/^\/[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*\/[A-Za-z0-9_-]+\.json$/.test(path)) {
    throw new Error('The assessment feed requires a fixed same-origin JSON path.');
  }
  const response = await fetch(path, {
    method: 'GET',
    credentials: 'same-origin',
    redirect: 'error',
    cache: 'no-store',
    signal: AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]),
    headers: { Accept: 'application/json' },
  });
  if (
    !response.ok ||
    !response.body ||
    !/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type') ?? '')
  ) {
    await response.body?.cancel();
    throw new Error('Assessment feed unavailable.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let bytes = 0;
  let content = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > limit) throw new Error('Assessment feed exceeds the size limit.');
      content += decoder.decode(value, { stream: true });
    }
    return JSON.parse(content + decoder.decode());
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
}

export async function readAssessmentFeed(
  path: string,
  signal: AbortSignal
): Promise<AssessmentFeed> {
  return parseAssessmentFeed(await readJson(path, signal, maxBytes, 10000));
}

export async function readScheduledAssessmentFeed(
  path: string,
  signal: AbortSignal
): Promise<AssessmentViewFeed> {
  const feed = await readAssessmentFeed(path, signal);
  try {
    const status = await readJson(path.replace(/\.json$/, '-status.json'), signal, 4096, 2000);
    if (validateRunStatus(status)) return { ...feed, scheduled: true, runStatus: status };
  } catch (error) {
    if (signal.aborted) throw error;
    // Standalone publications have no run status. The UI shows that status is unavailable.
  }
  return { ...feed, scheduled: true };
}

export function assessmentRunHealth(feed: AssessmentFeed, status: RunStatus, now: number) {
  if (!feed.clusters.length) return undefined;
  const attempt = Date.parse(status.attemptedAt);
  const evaluations = feed.clusters.map((cluster) => Date.parse(cluster.evaluatedAt));
  const latest = Math.max(...evaluations);
  const failed = new Set(feed.failedClusters);
  const partial = failed.size > 0 || feed.clusters.some((cluster) => cluster.status === 'partial');
  if (
    attempt > now ||
    (status.outcome === 'failed'
      ? attempt <= latest
      : feed.clusters.some((cluster) =>
          failed.has(cluster.id)
            ? Date.parse(cluster.evaluatedAt) > attempt
            : Date.parse(cluster.evaluatedAt) !== attempt
        ) || (status.outcome === 'partial') !== partial)
  ) {
    return undefined;
  }
  const staleClusters = feed.clusters
    .filter((cluster) => now - Date.parse(cluster.evaluatedAt) > status.staleAfterHours * 3600000)
    .map((cluster) => cluster.id);
  return {
    attemptedAt: status.attemptedAt,
    publishedEvaluationAt: new Date(latest).toISOString(),
    outcome: status.outcome,
    stale: staleClusters.length > 0,
    staleClusters,
  };
}
