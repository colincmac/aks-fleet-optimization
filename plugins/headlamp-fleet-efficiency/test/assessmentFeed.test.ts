import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  assessmentRunHealth,
  parseAssessmentFeed,
  readAssessmentFeed,
  readScheduledAssessmentFeed,
} from '../src/api/assessmentFeed';

const clock = '2026-10-29T12:00:00Z';
const cluster = {
  id: 'synthetic-id',
  uid: 'synthetic-uid',
  name: 'aks-synthetic',
  status: 'partial',
  mode: 'baseline',
  evaluatedAt: clock,
  windowStart: clock,
  windowEnd: clock,
  namespaces: [
    { name: 'example', workloads: [{ uid: 'api-uid', name: 'api', kind: 'Deployment' }] },
  ],
  unboundWorkloads: 0,
  issues: ['missing-metrics'],
  findings: [
    {
      id: 'blocked-example',
      rule: 'AKS-RQ-002',
      version: '1.0.0',
      namespace: 'example',
      workload: 'api',
      state: 'blocked',
      reasons: ['missing_history'],
    },
  ],
};

describe('saved assessment feed', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('distinguishes a newer failed attempt from the last publication and its age', () => {
    const data = parseAssessmentFeed({ schemaVersion: '1', clusters: [cluster] });
    const later = '2026-10-30T12:00:00Z';
    const status = { attemptedAt: later, outcome: 'failed' as const, staleAfterHours: 26 };
    const atLimit = Date.parse(clock) + 26 * 3600000;
    expect(assessmentRunHealth(data, status, atLimit)).toEqual({
      attemptedAt: later,
      publishedEvaluationAt: '2026-10-29T12:00:00.000Z',
      outcome: 'failed',
      stale: false,
      staleClusters: [],
    });
    expect(assessmentRunHealth(data, status, atLimit + 1)?.staleClusters).toEqual([cluster.id]);
    expect(assessmentRunHealth(data, { ...status, outcome: 'complete' }, atLimit)).toBeUndefined();
  });

  it('does not request status for a denied feed or accept malformed status', async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 403 }))
      .mockResolvedValueOnce(Response.json({ schemaVersion: '1', clusters: [cluster] }))
      .mockResolvedValueOnce(
        Response.json({
          schemaVersion: '1',
          outcome: 'failed',
          attemptedAt: clock,
          staleAfterHours: 0,
        })
      );
    vi.stubGlobal('fetch', request);
    const signal = new AbortController().signal;
    await expect(readScheduledAssessmentFeed('/data/assessments.json', signal)).rejects.toThrow();
    expect(request).toHaveBeenCalledTimes(1);
    const result = await readScheduledAssessmentFeed('/data/assessments.json', signal);
    expect(result.clusters).toHaveLength(1);
    expect(result.runStatus).toBeUndefined();
    expect(request).toHaveBeenLastCalledWith('/data/assessments-status.json', expect.anything());
  });
  it('keeps blocked findings and partial status distinct from observed workloads', () => {
    const data = parseAssessmentFeed({ schemaVersion: '1', clusters: [cluster] });
    expect(data.clusters[0].status).toBe('partial');
    expect(data.clusters[0].findings[0].state).toBe('blocked');
    expect(data.clusters[0].namespaces[0].workloads[0].uid).toBe('api-uid');
  });

  it('admits a mixed-age feed and matches the attempt against current clusters only', () => {
    const later = '2026-10-30T12:00:00Z';
    const data = parseAssessmentFeed({
      schemaVersion: '1',
      clusters: [cluster, { ...cluster, id: 'current', evaluatedAt: later }],
      failedClusters: [cluster.id, 'missing'],
    });
    expect(
      assessmentRunHealth(
        data,
        { attemptedAt: later, outcome: 'partial', staleAfterHours: 26 },
        Date.parse(later)
      )?.outcome
    ).toBe('partial');
    expect(() =>
      parseAssessmentFeed({ ...data, failedClusters: [cluster.id, 'current'] })
    ).toThrow();
  });

  it('rejects duplicate clusters and findings, invalid windows, and extra fields', () => {
    for (const clusters of [
      [cluster, { ...cluster, uid: 'new-incarnation' }],
      [{ ...cluster, findings: [...cluster.findings, ...cluster.findings] }],
      [{ ...cluster, windowStart: '2026-10-30T12:00:00Z' }],
      [{ ...cluster, savings: 400 }],
    ]) {
      expect(() => parseAssessmentFeed({ schemaVersion: '1', clusters })).toThrow();
    }
  });

  it('refuses cross-origin, dynamic and ambiguous feed paths before fetching', async () => {
    for (const path of [
      'https://other.invalid/example.json',
      '//other.invalid/example.json',
      '/a/../example.json',
      '/a/example.json?redirect=true',
    ]) {
      await expect(readAssessmentFeed(path, new AbortController().signal)).rejects.toThrow(
        'fixed same-origin JSON path'
      );
    }
  });
});
