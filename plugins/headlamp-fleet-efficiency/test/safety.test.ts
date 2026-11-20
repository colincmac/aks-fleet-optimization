import { describe, expect, it } from 'vitest';
import { approvalBlockers, percentageChange, parseQuantity } from '../src/utils/safety';
import { makeRecommendation } from '../src/demo/fixtures';

describe('approval safety boundary', () => {
  const now = new Date('2026-10-30T12:00:00Z');

  it('allows only fresh, complete, generation-bound proposals', () => {
    expect(approvalBlockers(makeRecommendation(now), now)).toEqual([]);
  });

  it.each(['expired', 'stale', 'superseded', 'partial', 'drifted', 'generation'])(
    'blocks %s evidence',
    (reason) => {
      const recommendation = makeRecommendation(now);
      if (reason === 'expired') recommendation.spec.expiresAt = now.toISOString();
      if (reason === 'stale') recommendation.spec.evidenceCollectedAt = '2026-10-28T00:00:00Z';
      if (reason === 'superseded') recommendation.status.supersededBy = 'new-generation';
      if (reason === 'partial') recommendation.spec.completeness = 'partial';
      if (reason === 'drifted') recommendation.status.sourceConfiguration = 'Changed';
      if (reason === 'generation') recommendation.status.observedGeneration = 0;
      expect(approvalBlockers(recommendation, now).length).toBeGreaterThan(0);
    }
  );

  it('does not turn absent values or a zero baseline into savings', () => {
    expect(percentageChange(null, 500)).toBeNull();
    expect(percentageChange(0, 500)).toBeNull();
    expect(percentageChange(1000, 650)).toBe(-35);
  });

  it('blocks absent proposals, unknown baselines and mutating VPA modes', () => {
    const record = makeRecommendation(now);
    record.spec.finding.proposed_requests = { cpu_mcores: null, memory_mib: null };
    expect(approvalBlockers(record, now)).toContain(
      'No valid deterministic resource proposal and baseline'
    );
    record.spec.finding.proposed_requests = { cpu_mcores: 650 };
    record.spec.finding.current_requests = null;
    expect(approvalBlockers(record, now)).toContain(
      'No valid deterministic resource proposal and baseline'
    );
    record.spec.vpa!.updateMode = 'Auto';
    expect(approvalBlockers(record, now)).toContain('VPA mode is mutating or unknown');
  });

  it('parses Kubernetes quantities and rejects invalid/nonfinite/negative values', () => {
    expect(parseQuantity('650m', 'cpu')).toBe(650);
    expect(parseQuantity('1.5', 'cpu')).toBe(1500);
    expect(parseQuantity('1Gi', 'memory')).toBe(1024);
    expect(parseQuantity('1e3', 'cpu')).toBe(1000000);
    for (const value of ['NaN', 'Infinity', '-1', '1oops']) {
      expect(parseQuantity(value, 'cpu')).toBeNull();
    }
  });
  it('does not approve replica-floor proposals through the resource-request workflow', () => {
    const record = makeRecommendation(now);
    record.spec.finding.current_replica_floor = 2;
    record.spec.finding.proposed_replica_floor = 1;
    expect(approvalBlockers(record, now)).toContain(
      'Replica-floor approval is not supported by this review workflow'
    );
  });
  it('does not approve memory-limit proposals through the resource-request workflow', () => {
    const record = makeRecommendation(now);
    record.spec.finding.current_limits = { memory_mib: 1024 };
    record.spec.finding.proposed_limits = { memory_mib: 600 };
    expect(approvalBlockers(record, now)).toContain(
      'Memory-limit approval is not supported by this review workflow'
    );
  });
});
