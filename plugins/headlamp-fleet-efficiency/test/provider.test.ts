import { describe, expect, it } from 'vitest';
import { SimulatorProvider, BackendProvider } from '../src/api/provider';
import { makeRecommendation } from '../src/demo/fixtures';
import { acknowledgementLabels, matchingVpas, safeGithubUrl, vpaMode } from '../src/utils/safety';
import { demoVpas } from '../src/demo/fixtures';
import type { ActionRequest, OptimizationRecommendation } from '../src/models/review';

const now = new Date('2026-10-30T12:00:00Z');
function request(
  record: OptimizationRecommendation,
  action: ActionRequest['action'] = 'approve'
): ActionRequest {
  return {
    uid: record.metadata.uid,
    resourceVersion: record.metadata.resourceVersion,
    generation: record.metadata.generation,
    evidenceVersion: record.spec.evidenceVersion,
    sourceRevision: record.spec.sourceRevision,
    idempotencyKey: crypto.randomUUID(),
    action,
    reason: 'Reviewed the synthetic evidence and canary plan.',
    acknowledgements: acknowledgementLabels,
  };
}
describe('mock governance provider', () => {
  it('requires independent roles, then opens one simulated PR without validating deployment', async () => {
    const provider = new SimulatorProvider([makeRecommendation(now)], () => now);
    let record = (await provider.list())[0];
    const first = request(record);
    record = await provider.act(record, first);
    expect(record.status.phase).toBe('AwaitingApproval');
    expect(await provider.act(record, first)).toEqual(record);
    await expect(provider.act(record, request(record))).rejects.toThrow('already recorded');
    await expect(provider.act(record, request(record, 'create-pull-request'))).rejects.toThrow(
      'approvals'
    );
    provider.role = 'PlatformOwner';
    record = await provider.act(record, request(record));
    expect(record.status.phase).toBe('Approved');
    record = await provider.act(record, request(record, 'create-pull-request'));
    expect(record.status.pullRequest.state).toBe('Open');
    expect(record.status.validation.state).toBe('NotStarted');
    expect(record.status.timeline).toHaveLength(4);
    await expect(provider.act(record, request(record, 'create-pull-request'))).rejects.toThrow(
      'already exists'
    );
  });
  it('rejects stale clients and viewers even when actions are submitted directly', async () => {
    const provider = new SimulatorProvider([makeRecommendation(now)], () => now);
    const record = (await provider.list())[0];
    await provider.act(record, request(record, 'request-observation'));
    await expect(provider.act(record, request(record))).rejects.toThrow('changed');
    provider.role = 'Viewer';
    await expect(provider.act(record, request(record, 'reject'))).rejects.toThrow(
      'Permission denied'
    );
  });
  it('defaults the real adapter to read-only when no backend exists', async () => {
    const provider = new BackendProvider(
      async () => [makeRecommendation(now)],
      undefined,
      (data) => data as OptimizationRecommendation
    );
    expect((await provider.capabilities()).allowed).toEqual([]);
    await expect(
      provider.act(makeRecommendation(now), request(makeRecommendation(now)))
    ).rejects.toThrow('not configured');
  });
  it('rejects incomplete acknowledgements, empty comments and unsafe deferral', async () => {
    const provider = new SimulatorProvider([makeRecommendation(now)], () => now);
    const record = (await provider.list())[0];
    await expect(
      provider.act(record, { ...request(record), acknowledgements: [] })
    ).rejects.toThrow('acknowledge');
    await expect(
      provider.act(record, { ...request(record, 'reject'), reason: ' ' })
    ).rejects.toThrow('reason');
    await expect(provider.act(record, request(record, 'defer'))).rejects.toThrow('Defer');
  });
});
describe('VPA and external text', () => {
  it('matches exact workload scope, detects duplicates and preserves missing recommendations', () => {
    const record = makeRecommendation(now);
    const vpa = demoVpas([record])[0];
    expect(matchingVpas([vpa, vpa], record)).toHaveLength(2);
    expect(
      matchingVpas([{ ...vpa, metadata: { ...vpa.metadata, namespace: 'other' } }], record)
    ).toHaveLength(0);
    expect(vpaMode(vpa)).toBe('Recommendation only');
    delete vpa.spec.updatePolicy;
    expect(vpaMode(vpa)).toContain('potentially mutating');
    expect(vpa.status?.recommendation?.containerRecommendations[0].target?.cpu).toBe('650m');
  });
  it('does not trust arbitrary pull-request URLs', () => {
    expect(safeGithubUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeGithubUrl('https://github.com.evil.test/a/b/pull/1')).toBeUndefined();
    expect(safeGithubUrl('https://github.com/example/workload/pull/1')).toBeDefined();
  });
});
