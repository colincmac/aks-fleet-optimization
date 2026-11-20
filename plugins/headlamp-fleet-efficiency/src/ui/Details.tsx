import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  FileCode2,
  GitPullRequest,
  Info,
  ShieldAlert,
} from 'lucide-react';
import type {
  ActionRequest,
  Capabilities,
  OptimizationRecommendation,
  VpaRecord,
} from '../models/review';
import {
  freshness,
  matchingVpas,
  parseQuantity,
  percentageChange,
  phaseLabel,
  safeGithubUrl,
  timestamp,
  vpaMode,
} from '../utils/safety';
import { ApprovalPanel } from './ApprovalPanel';
import { Badge, EmptyState, Notice, Section, Status, StepIcon } from './primitives';
import { AiAnalysisPanel, renderers } from './renderers';
import { PackInspectionPanel } from './Catalog';

export function VpaEvidencePanel({
  record,
  vpas = [],
  vpaError,
}: {
  record: OptimizationRecommendation;
  vpas?: VpaRecord[];
  vpaError?: string;
}) {
  const source = record.spec.vpa;
  const matches = matchingVpas(vpas, record);
  const bounds = source?.bounds;
  return (
    <div id="fe-vpa-evidence">
      <Section
        title="Vertical Pod Autoscaler"
        label="VPA-GENERATED VALUES"
        action={
          <Badge tone="neutral">
            {source?.updateMode === 'Off'
              ? 'Recommendation only'
              : source?.updateMode
                ? `Mutating (${source.updateMode})`
                : 'Mode unknown'}
          </Badge>
        }
      >
        {!source ? (
          <EmptyState title="No source VPA supplied">
            The recommendation remains available without VPA evidence.
          </EmptyState>
        ) : (
          <>
            <div className="fe-vpa-reference">
              <span className="fe-mono">
                {source.namespace} / {source.name}
              </span>
              <span className="fe-small fe-muted">
                Embedded source evidence · {timestamp(record.spec.evidenceCollectedAt)}
              </span>
            </div>
            {source.updateMode !== 'Off' && (
              <Notice danger>
                VPA update mode is mutating or unknown. Review autoscaler interaction before
                approval.
              </Notice>
            )}
            {!bounds ? (
              <Notice>No container recommendation is available from the source VPA.</Notice>
            ) : (
              <div className="fe-table-wrap">
                <table className="fe-table fe-bounds">
                  <caption className="fe-sr-only">VPA bounds for {bounds.containerName}</caption>
                  <thead>
                    <tr>
                      <th>Resource / container</th>
                      <th>Lower bound</th>
                      <th>Target</th>
                      <th>Upper bound</th>
                      <th>Uncapped target</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(['cpu', 'memory'] as const).map((resource) => (
                      <tr key={resource}>
                        <td>
                          <strong>{resource === 'cpu' ? 'CPU' : 'Memory'}</strong>
                          <span className="fe-cell-sub">{bounds.containerName}</span>
                        </td>
                        {(['lowerBound', 'target', 'upperBound', 'uncappedTarget'] as const).map(
                          (bound) => (
                            <td key={bound} className={bound === 'target' ? 'fe-target-cell' : ''}>
                              <span className="fe-mono">
                                {bounds[bound]?.[resource] ?? 'Unavailable'}
                              </span>
                              <span className="fe-cell-sub">
                                {bounds[bound]?.[resource] &&
                                parseQuantity(bounds[bound]?.[resource], resource) === null
                                  ? 'Unsupported quantity'
                                  : ''}
                              </span>
                            </td>
                          )
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="fe-small fe-muted">
              <Info size={13} className="fe-inline-icon" />
              VPA values are evidence, not the approved proposal. Memory is unchanged unless the
              deterministic finding proposes it.
            </p>
          </>
        )}
        {vpaError && <Notice>{vpaError} Embedded VPA evidence is retained.</Notice>}
        {matches.length > 1 && (
          <Notice danger>
            Multiple VPAs target this workload in the current management context. Resolve the
            conflict before using live evidence.
          </Notice>
        )}
        {matches.length > 0 && (
          <details className="fe-disclosure">
            <summary>Current management-context VPA objects ({matches.length})</summary>
            <p className="fe-small fe-muted">
              Name matches do not establish source-cluster identity or current evidence freshness.
            </p>
            {matches.map((vpa, index) => (
              <div key={index}>
                <span className="fe-mono">{vpa.metadata.name}</span> · {vpaMode(vpa)}
                <pre>
                  {JSON.stringify(
                    {
                      targetRef: vpa.spec.targetRef,
                      updatePolicy: vpa.spec.updatePolicy ?? 'Unknown',
                      resourcePolicy: vpa.spec.resourcePolicy ?? 'Not supplied',
                      recommendation: vpa.status?.recommendation ?? 'No recommendation',
                    },
                    null,
                    2
                  )}
                </pre>
              </div>
            ))}
          </details>
        )}
      </Section>
    </div>
  );
}

function CurrentVsProposed({ record }: { record: OptimizationRecommendation }) {
  const finding = record.spec.finding;
  const resources = [
    {
      label: 'CPU request',
      current: finding.current_requests?.cpu_mcores,
      proposed: finding.proposed_requests?.cpu_mcores,
      unit: 'mCPU',
    },
    {
      label: 'Memory request',
      current: finding.current_requests?.memory_mib,
      proposed: finding.proposed_requests?.memory_mib,
      unit: 'MiB',
    },
  ];
  if (finding.current_replica_floor != null || finding.proposed_replica_floor != null)
    resources.push({
      label: 'HPA minimum replicas',
      current: finding.current_replica_floor,
      proposed: finding.proposed_replica_floor,
      unit: 'replicas',
    });
  if (finding.current_limits != null || finding.proposed_limits != null)
    resources.push({
      label: 'Memory limit',
      current: finding.current_limits?.memory_mib,
      proposed: finding.proposed_limits?.memory_mib,
      unit: 'MiB',
    });
  return (
    <Section title="Current vs. proposed" label="DETERMINISTIC PROPOSAL">
      <div className="fe-resource-comparison">
        {resources.map((resource) => {
          const change = percentageChange(resource.current, resource.proposed);
          const largest = Math.max(resource.current ?? 0, resource.proposed ?? 0, 1);
          return (
            <div className="fe-resource-compare" key={resource.label}>
              <div className="fe-section-heading">
                <h3>{resource.label}</h3>
                <Badge tone={change !== null ? 'green' : 'neutral'}>
                  {change === null ? 'No change proposed' : `${change > 0 ? '+' : ''}${change}%`}
                </Badge>
              </div>
              <div className="fe-resource-numbers">
                <div>
                  <span className="fe-small fe-muted">Current</span>
                  <strong>
                    {resource.current ?? '?'}
                    <small>{resource.unit}</small>
                  </strong>
                </div>
                <ArrowRight size={19} className="fe-muted" />
                <div>
                  <span className="fe-small fe-muted">Proposed</span>
                  <strong>
                    {resource.proposed ?? 'Unchanged'}
                    {resource.proposed != null && <small>{resource.unit}</small>}
                  </strong>
                </div>
              </div>
              <div className="fe-compare-bars">
                <div>
                  <span style={{ width: `${((resource.current ?? 0) / largest) * 100}%` }} />
                </div>
                {resource.proposed != null && (
                  <div>
                    <span
                      className="fe-proposed-bar"
                      style={{ width: `${(resource.proposed / largest) * 100}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

export function PullRequestPanel({ record }: { record: OptimizationRecommendation }) {
  const implementation = record.spec.implementation;
  const pr = record.status.pullRequest;
  const url = safeGithubUrl(pr.url);
  return (
    <Section
      title="GitHub pull request"
      label="IMPLEMENTATION STATE"
      action={<Status value={pr.state} />}
    >
      <div className="fe-delivery-step">
        <GitPullRequest size={26} />
        <div>
          <h3>{pr.number ? `Pull request #${pr.number}` : 'No pull request created'}</h3>
          <p className="fe-muted">
            {pr.message ??
              'A reviewed configuration change is proposed through the backend integration.'}
          </p>
          {url && (
            <a className="fe-text-button" href={url} target="_blank" rel="noopener noreferrer">
              Open on GitHub
              <ArrowUpRight size={15} />
            </a>
          )}
        </div>
      </div>
      {implementation ? (
        <dl className="fe-facts">
          <div>
            <dt>Repository</dt>
            <dd>
              {implementation.owner}/{implementation.repository}
            </dd>
          </div>
          <div>
            <dt>Configuration</dt>
            <dd className="fe-mono">
              <FileCode2 size={14} className="fe-inline-icon" />
              {implementation.configurationPath}
            </dd>
          </div>
          <div>
            <dt>Base branch</dt>
            <dd>{implementation.baseBranch}</dd>
          </div>
          <div>
            <dt>Source revision</dt>
            <dd className="fe-mono">{record.spec.sourceRevision}</dd>
          </div>
        </dl>
      ) : (
        <Notice>Repository mapping is unavailable. PR creation is disabled.</Notice>
      )}
      <Notice>PR merge or GitOps synchronization does not establish a healthy outcome.</Notice>
    </Section>
  );
}
export function ValidationPanel({ record }: { record: OptimizationRecommendation }) {
  const validation = record.status.validation;
  return (
    <Section
      title="Post-change validation"
      label="OBSERVED OUTCOME"
      action={<Status value={validation.state} />}
    >
      <dl className="fe-facts">
        <div>
          <dt>Deployed at</dt>
          <dd>{timestamp(validation.deployedAt)}</dd>
        </div>
        <div>
          <dt>Validation window</dt>
          <dd>{validation.window ?? 'Not supplied'}</dd>
        </div>
        <div>
          <dt>Rollback state</dt>
          <dd>{validation.rollback ?? 'Not supplied'}</dd>
        </div>
      </dl>
      {validation.metrics?.length ? (
        <div className="fe-table-wrap">
          <table className="fe-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Baseline</th>
                <th>Current</th>
                <th>Unit</th>
              </tr>
            </thead>
            <tbody>
              {validation.metrics.map((metric) => (
                <tr key={metric.name}>
                  <td>{metric.name}</td>
                  <td>{metric.baseline ?? 'Unavailable'}</td>
                  <td>{metric.current ?? 'Collecting'}</td>
                  <td>{metric.unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="Validation has not started">
          Baseline and post-deployment observations will appear when supplied by the validation
          service.
        </EmptyState>
      )}
      <p className="fe-small fe-muted">
        Request changes, availability, packing and node-count impact are unknown unless explicitly
        supplied.
      </p>
    </Section>
  );
}

export function Details({
  record,
  basePath,
  capabilities,
  submit,
  vpas,
  vpaError,
  relatedLinks = {},
}: {
  record: OptimizationRecommendation;
  basePath: string;
  capabilities: Capabilities;
  submit: (request: ActionRequest) => Promise<void>;
  vpas?: VpaRecord[];
  vpaError?: string;
  relatedLinks?: Partial<
    Record<
      'keda' | 'karpenter',
      (
        resource: NonNullable<OptimizationRecommendation['spec']['relatedResources']>[number]
      ) => string
    >
  >;
}) {
  const [tab, setTab] = useState('Evidence');
  const flags = freshness(record);
  const renderer = renderers.find((item) => item.supports(record))!;
  return (
    <>
      <Link className="fe-text-button fe-back" to={`${basePath}/recommendations`}>
        <ArrowLeft size={15} />
        Recommendations
      </Link>
      <div className="fe-detail-heading">
        <div>
          <div className="fe-eyebrow">
            {record.spec.finding.id} · {record.spec.finding.rule_id} /{' '}
            {record.spec.finding.rule_version}
          </div>
          <h1>{record.spec.target.name}</h1>
          <p className="fe-page-subtitle">{record.spec.finding.title}</p>
        </div>
        <Badge tone={record.spec.risk.level === 'high' ? 'red' : 'amber'} dot>
          {phaseLabel(record.spec.risk.level)} risk
        </Badge>
      </div>
      {flags.length > 0 && (
        <Notice danger>{flags.join(' · ')}. Approval and PR creation are blocked.</Notice>
      )}
      {record.spec.completeness !== 'complete' && (
        <Notice danger>
          Evidence is {record.spec.completeness}. Missing observations are not zero and do not
          establish safety.
        </Notice>
      )}
      <div className="fe-detail-layout">
        <div className="fe-detail-main">
          <div className="fe-detail-metadata">
            <div>
              <span>Cluster</span>
              <strong>{record.spec.finding.cluster_name}</strong>
            </div>
            <div>
              <span>Namespace</span>
              <strong>{record.spec.target.namespace}</strong>
            </div>
            <div>
              <span>Workload</span>
              <strong>
                {record.spec.target.kind} / {record.spec.target.container}
              </strong>
            </div>
            <div>
              <span>Owner</span>
              <strong>{record.spec.finding.owner ?? 'Unknown'}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <strong>{phaseLabel(record.spec.finding.confidence)}</strong>
            </div>
          </div>
          <div className="fe-detail-tabs" role="tablist" aria-label="Recommendation detail views">
            {['Evidence', 'Delivery & validation', 'Timeline'].map((label) => (
              <button
                role="tab"
                key={label}
                aria-selected={tab === label}
                onClick={() => setTab(label)}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === 'Evidence' && (
            <div role="tabpanel" aria-label="Evidence">
              <Section title="Recommendation summary" label="INVESTIGATION">
                <p className="fe-prose">{record.spec.finding.summary}</p>
                <div className="fe-inline-badges">
                  <Badge>{record.spec.type}</Badge>
                  <Badge>{record.spec.source}</Badge>
                  {renderer.renderSummary(record)}
                </div>
                <dl className="fe-facts">
                  <div>
                    <dt>Generated</dt>
                    <dd>{timestamp(record.spec.generatedAt)}</dd>
                  </div>
                  <div>
                    <dt>Expires</dt>
                    <dd>{timestamp(record.spec.expiresAt)}</dd>
                  </div>
                  <div>
                    <dt>Source VPA</dt>
                    <dd>
                      {record.spec.vpa ? (
                        <a href="#fe-vpa-evidence">
                          {record.spec.vpa.namespace}/{record.spec.vpa.name}
                        </a>
                      ) : (
                        'Not supplied'
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Workload UID</dt>
                    <dd className="fe-mono">{record.spec.target.uid}</dd>
                  </div>
                </dl>
                <details className="fe-disclosure">
                  <summary>Exact cluster identity</summary>
                  <pre>{record.spec.target.clusterResourceId}</pre>
                </details>
              </Section>
              <PackInspectionPanel record={record} />
              <CurrentVsProposed record={record} />
              <Section
                title="Observation evidence"
                label="MEASURED FACTS"
                action={<Status value={record.spec.completeness} />}
              >
                <div className="fe-evidence-window">
                  <div>
                    <span className="fe-small fe-muted">Observation window</span>
                    <strong>
                      {timestamp(record.spec.observationWindow.start)} →{' '}
                      {timestamp(record.spec.observationWindow.end)}
                    </strong>
                  </div>
                  <div>
                    <span className="fe-small fe-muted">Coverage</span>
                    <strong>
                      {record.spec.observationWindow.coverageRatio == null
                        ? 'Unknown'
                        : `${(record.spec.observationWindow.coverageRatio * 100).toFixed(1)}%`}
                    </strong>
                  </div>
                </div>
                {record.spec.finding.evidence.length > 0 ? (
                  <div className="fe-table-wrap">
                    <table className="fe-table">
                      <thead>
                        <tr>
                          <th>Metric</th>
                          <th>Value</th>
                          <th>Unit</th>
                          <th>Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {record.spec.finding.evidence.map((evidence, index) => (
                          <tr key={index}>
                            <td className="fe-mono fe-small">{evidence.metric}</td>
                            <td>{evidence.value == null ? 'Unknown' : String(evidence.value)}</td>
                            <td>{evidence.unit ?? 'Not supplied'}</td>
                            <td>{evidence.source}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState title="No measured evidence supplied" />
                )}
                <p className="fe-small fe-muted">
                  Last collection: {timestamp(record.spec.evidenceCollectedAt)}. Historical charts
                  unavailable; no live metrics API is configured.
                </p>
              </Section>
              <VpaEvidencePanel record={record} vpas={vpas} vpaError={vpaError} />
              <Section title="Policy & operational risk" label="DETERMINISTIC CHECKS">
                <div className="fe-checks">
                  {record.spec.checks.map((check) => (
                    <div key={check.name}>
                      <span
                        className={check.state === 'Pass' ? 'fe-check-icon' : 'fe-warning-text'}
                      >
                        {check.state === 'Pass' ? (
                          <CheckCircle2 size={18} />
                        ) : (
                          <ShieldAlert size={18} />
                        )}
                      </span>
                      <div>
                        <h3>{phaseLabel(check.name)}</h3>
                        <p>{check.detail}</p>
                      </div>
                      <Status value={check.state} />
                    </div>
                  ))}
                </div>
                <h3>Disruption & restart</h3>
                <p className="fe-prose">{record.spec.risk.restart}</p>
                <ul>
                  {record.spec.risk.reasons.map((reason, index) => (
                    <li key={index}>{reason}</li>
                  ))}
                </ul>
                <h3>Validation plan</h3>
                <ul>
                  {record.spec.finding.validation_steps?.map((step, index) => (
                    <li key={index}>{step}</li>
                  ))}
                </ul>
                <h3>Rollback guidance</h3>
                <ul>
                  {record.spec.finding.rollback_steps?.map((step, index) => (
                    <li key={index}>{step}</li>
                  ))}
                </ul>
              </Section>
              {record.spec.ai ? (
                renderer.renderEvidence(record)
              ) : (
                <AiAnalysisPanel record={record} />
              )}
              {renderer
                .getRelatedResources(record)
                .some((resource) => relatedLinks[resource.plugin]) && (
                <Section title="Related resources">
                  {renderer
                    .getRelatedResources(record)
                    .filter((resource) => relatedLinks[resource.plugin])
                    .map((resource) => (
                      <Link
                        className="fe-text-button"
                        key={`${resource.kind}/${resource.name}`}
                        to={relatedLinks[resource.plugin]!(resource)}
                      >
                        {resource.kind} / {resource.name}
                        <ArrowUpRight size={14} />
                      </Link>
                    ))}
                </Section>
              )}
            </div>
          )}
          {tab === 'Delivery & validation' && (
            <div role="tabpanel" aria-label="Delivery and validation">
              <div className="fe-delivery-flow">
                {['Owner approval', 'Pull request', 'GitOps deploy', 'Validate'].map(
                  (step, index) => (
                    <div key={step}>
                      <StepIcon
                        state={
                          index === 0 && record.status.phase !== 'AwaitingApproval'
                            ? 'done'
                            : index === 1 && record.status.pullRequest.state === 'Open'
                              ? 'current'
                              : 'pending'
                        }
                      />
                      <span>{step}</span>
                    </div>
                  )
                )}
              </div>
              <PullRequestPanel record={record} />
              <ValidationPanel record={record} />
            </div>
          )}
          {tab === 'Timeline' && (
            <div role="tabpanel" aria-label="Timeline">
              <Section title="Recommendation timeline" label="HUMAN DECISIONS & WORKFLOW EVENTS">
                <ol className="fe-timeline">
                  {[...record.status.timeline].reverse().map((event) => (
                    <li key={event.id}>
                      <span className="fe-timeline-dot" />
                      <div className="fe-section-heading">
                        <h3>{phaseLabel(event.action)}</h3>
                        <time>{timestamp(event.timestamp)}</time>
                      </div>
                      <p>{event.reason}</p>
                      <div className="fe-small fe-muted">
                        {event.actor} · generation {event.generation} · {event.evidenceVersion}
                        {event.deferUntil ? ` · deferred until ${timestamp(event.deferUntil)}` : ''}
                      </div>
                    </li>
                  ))}
                </ol>
              </Section>
            </div>
          )}
        </div>
        <ApprovalPanel
          key={record.metadata.uid}
          record={record}
          capabilities={capabilities}
          submit={submit}
        />
      </div>
    </>
  );
}
