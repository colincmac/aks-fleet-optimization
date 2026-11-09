import { describe, expect, it, vi } from 'vitest';
import { parseRecommendation, parseRecommendationList, parseVpa } from '../src/api/contracts';
import { boundedList } from '../src/api/kubernetes';
import { demoRecommendations, demoVpas, makeRecommendation } from '../src/demo/fixtures';
import { SimulatorProvider } from '../src/api/provider';
import { acknowledgementLabels } from '../src/utils/safety';

describe('management Kubernetes API integration', () => {
  it('accepts existing findings, Kubernetes metadata and all workflow phases', () => {
    const records = demoRecommendations();
    records[0].metadata.creationTimestamp = new Date().toISOString();
    records[0].metadata.managedFields = [];
    expect(parseRecommendationList(records, 'fleet-efficiency-system')).toHaveLength(12);
    expect(parseVpa(demoVpas(records)[0]).spec.updatePolicy?.updateMode).toBe('Off');
  });
  it('rejects invalid findings, unknown phases, duplicate identities and foreign namespaces', () => {
    const record = makeRecommendation();
    expect(() =>
      parseRecommendation({ ...record, status: { ...record.status, phase: 'AutoApplied' } })
    ).toThrow('Unsupported');
    expect(() =>
      parseRecommendation({
        ...record,
        spec: {
          ...record.spec,
          finding: { ...record.spec.finding, estimated_monthly_savings: -1 },
        },
      })
    ).toThrow('schema');
    expect(() => parseRecommendationList([record, record], record.metadata.namespace)).toThrow(
      'Duplicate'
    );
    expect(() => parseRecommendationList([record], 'foreign')).toThrow('outside');
  });
  it('pages a consistent list and never makes a write request', async () => {
    const records = demoRecommendations();
    const request = vi
      .fn()
      .mockResolvedValueOnce({
        items: records.slice(0, 5),
        metadata: { resourceVersion: '7', continue: 'next' },
      })
      .mockResolvedValueOnce({ items: records.slice(5), metadata: { resourceVersion: '7' } });
    const items = await boundedList(
      request,
      '/apis/optimization.aks.io/v1alpha1/namespaces/fleet-efficiency-system/optimizationrecommendations'
    );
    expect(parseRecommendationList(items, 'fleet-efficiency-system')).toHaveLength(12);
    expect(request.mock.calls[1][0]).toContain('continue=next');
    expect(request.mock.calls.every((call) => call[1].method === 'GET')).toBe(true);
  });
  it('rejects incomplete pages, changed snapshots, repeating cursors and denied APIs', async () => {
    await expect(boundedList(async () => ({ items: [] }), '/read')).rejects.toThrow('Incomplete');
    const changed = vi
      .fn()
      .mockResolvedValueOnce({ items: [], metadata: { resourceVersion: '1', continue: 'next' } })
      .mockResolvedValueOnce({ items: [], metadata: { resourceVersion: '2' } });
    await expect(boundedList(changed, '/read')).rejects.toThrow('changed');
    await expect(
      boundedList(
        async () => ({ items: [], metadata: { resourceVersion: '1', continue: 'repeat' } }),
        '/read'
      )
    ).rejects.toThrow('repeated');
    await expect(
      boundedList(async () => {
        throw { status: 403 };
      }, '/read')
    ).rejects.toThrow('Permission denied');
    await expect(
      boundedList(async () => {
        throw { status: 404 };
      }, '/read')
    ).rejects.toThrow('not found');
  });
  it('does not lose audit events when concurrent decisions race', async () => {
    const now = new Date();
    const provider = new SimulatorProvider([makeRecommendation(now)], () => now);
    const record = (await provider.list())[0];
    const request = {
      uid: record.metadata.uid,
      resourceVersion: record.metadata.resourceVersion,
      generation: 1,
      evidenceVersion: record.spec.evidenceVersion,
      sourceRevision: record.spec.sourceRevision,
      idempotencyKey: 'first',
      action: 'approve' as const,
      reason: 'Reviewed',
      acknowledgements: acknowledgementLabels,
    };
    const results = await Promise.allSettled([
      provider.act(record, request),
      provider.act(record, { ...request, idempotencyKey: 'second', action: 'reject' as const }),
    ]);
    expect(results.filter((result) => result.status === 'fulfilled')).toHaveLength(1);
    expect((await provider.list())[0].status.timeline).toHaveLength(2);
  });
});
