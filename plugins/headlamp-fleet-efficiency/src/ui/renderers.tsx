import type { ReactNode } from 'react';
import type { OptimizationRecommendation } from '../models/review';
import { Badge, Notice, Section } from './primitives';
import { timestamp } from '../utils/safety';

export type RelatedKubernetesResource = NonNullable<
  OptimizationRecommendation['spec']['relatedResources']
>[number];
export interface RecommendationRenderer {
  supports(recommendation: OptimizationRecommendation): boolean;
  renderSummary(recommendation: OptimizationRecommendation): ReactNode;
  renderEvidence(recommendation: OptimizationRecommendation): ReactNode;
  getRelatedResources(recommendation: OptimizationRecommendation): RelatedKubernetesResource[];
}
export function AiAnalysisPanel({ record }: { record: OptimizationRecommendation }) {
  const ai = record.spec.ai;
  return (
    <Section title="AI interpretation" label="ASSISTED ANALYSIS · NOT A POLICY FINDING">
      <Notice>
        AI analysis supports investigation and planning. Approval must be based on the underlying
        metrics, policy checks, and workload-owner judgment.
      </Notice>
      {ai ? (
        <>
          <div className="fe-ai-heading">
            <Badge tone="violet">AI-generated explanation</Badge>
            <span className="fe-small fe-muted">{timestamp(ai.analyzedAt)}</span>
          </div>
          <p className="fe-prose">{ai.explanation}</p>
          <dl className="fe-facts">
            <div>
              <dt>Generator</dt>
              <dd>{ai.generator}</dd>
            </div>
            <div>
              <dt>Model / agent</dt>
              <dd>{ai.model}</dd>
            </div>
            <div>
              <dt>Policy version</dt>
              <dd>{ai.policyVersion}</dd>
            </div>
            <div>
              <dt>Evidence version</dt>
              <dd className="fe-mono">{ai.evidenceVersion}</dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{ai.confidence}</dd>
            </div>
          </dl>
          <div className="fe-two-col">
            <div>
              <h3>Alternatives considered</h3>
              <ul>
                {ai.alternatives.map((text, index) => (
                  <li key={index}>{text}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Known limitations</h3>
              <ul>
                {ai.limitations.map((text, index) => (
                  <li key={index}>{text}</li>
                ))}
              </ul>
            </div>
          </div>
          <h3>Required human validation</h3>
          <ul>
            {ai.humanValidation.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        </>
      ) : (
        <p className="fe-muted">
          No AI analysis supplied. Deterministic evidence remains available.
        </p>
      )}
    </Section>
  );
}
export const VpaResourceRecommendationRenderer: RecommendationRenderer = {
  supports: (record) => record.spec.source === 'VPA',
  renderSummary: (record) => (
    <span>VPA evidence · {record.spec.vpa?.name ?? 'Source unavailable'}</span>
  ),
  renderEvidence: () => null,
  getRelatedResources: (record) => record.spec.relatedResources ?? [],
};
export const AiRecommendationRenderer: RecommendationRenderer = {
  supports: (record) => Boolean(record.spec.ai),
  renderSummary: () => <Badge tone="violet">AI-assisted investigation</Badge>,
  renderEvidence: (record) => <AiAnalysisPanel record={record} />,
  getRelatedResources: (record) => record.spec.relatedResources ?? [],
};
export const GenericRecommendationRenderer: RecommendationRenderer = {
  supports: () => true,
  renderSummary: (record) => <span>{record.spec.type}</span>,
  renderEvidence: () => null,
  getRelatedResources: (record) => record.spec.relatedResources ?? [],
};
export const renderers: RecommendationRenderer[] = [
  AiRecommendationRenderer,
  VpaResourceRecommendationRenderer,
  GenericRecommendationRenderer,
];
