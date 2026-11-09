import { Link } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUpRight,
  GitPullRequest,
  Layers3,
  ShieldCheck,
  Timer,
} from 'lucide-react';
import type { OptimizationRecommendation } from '../models/review';
import { freshness, phaseLabel } from '../utils/safety';
import { Badge, Metric, Section } from './primitives';
import { RecommendationTable } from './RecommendationTable';

export function Overview({
  records,
  basePath,
}: {
  records: OptimizationRecommendation[];
  basePath: string;
}) {
  const active = records.filter(
    (record) => !['Completed', 'Rejected', 'Cancelled'].includes(record.status.phase)
  );
  const awaiting = records.filter(
    (record) => record.status.phase === 'AwaitingApproval' && freshness(record).length === 0
  );
  const open = records.filter((record) => record.status.pullRequest.state === 'Open');
  const collecting = records.filter((record) => record.status.validation.state === 'Collecting');
  const healthy = records.filter((record) => record.status.validation.state === 'Healthy');
  const failed = records.filter((record) =>
    ['Failed', 'RolledBack'].includes(record.status.validation.state)
  );
  const stale = records.filter((record) => freshness(record).length > 0);
  const approved = records.filter((record) => record.status.phase === 'Approved');
  const dimensions: {
    label: string;
    filter: string;
    get: (record: OptimizationRecommendation) => string;
  }[] = [
    { label: 'Cluster', filter: 'cluster', get: (record) => record.spec.finding.cluster_name },
    { label: 'Namespace', filter: 'namespace', get: (record) => record.spec.target.namespace },
    { label: 'Owner', filter: 'q', get: (record) => record.spec.finding.owner || 'Unknown' },
    { label: 'Type', filter: 'type', get: (record) => record.spec.type },
    { label: 'Source', filter: 'source', get: (record) => record.spec.source },
    { label: 'Risk', filter: 'risk', get: (record) => record.spec.risk.level },
    { label: 'Confidence', filter: 'confidence', get: (record) => record.spec.finding.confidence },
    { label: 'Workflow', filter: 'phase', get: (record) => record.status.phase },
  ];
  return (
    <>
      <div className="fe-overview-top">
        <div>
          <div className="fe-eyebrow">
            <span className="fe-live-dot" />
            FLEET OPERATIONS
          </div>
          <h1>Fleet efficiency</h1>
          <p className="fe-page-subtitle">Evidence first. Every change reviewed.</p>
        </div>
        <Link className="fe-button" to={`${basePath}/recommendations`}>
          Review recommendations
          <ArrowRight size={16} />
        </Link>
      </div>
      <div className="fe-kpis">
        <Metric
          title="Active recommendations"
          value={active.length}
          note={`${new Set(records.map((record) => record.spec.target.clusterResourceId)).size} clusters in this view`}
        >
          <Layers3 className="fe-kpi-icon" size={23} />
        </Metric>
        <Metric
          title="Awaiting review"
          value={awaiting.length}
          note="Fresh evidence · owner review needed"
        >
          <ShieldCheck className="fe-kpi-icon" size={23} />
        </Metric>
        <Metric
          title="Open pull requests"
          value={open.length}
          note="Proposed changes · not yet validated"
        >
          <GitPullRequest className="fe-kpi-icon" size={23} />
        </Metric>
        <Metric
          title="Under validation"
          value={collecting.length}
          note="Post-change observation in progress"
        >
          <Timer className="fe-kpi-icon" size={23} />
        </Metric>
      </div>
      <div className="fe-workflow-strip">
        <div>
          <span className="fe-live-dot" />
          <strong>{healthy.length}</strong> healthy changes
        </div>
        <div>
          <span className="fe-state-dot fe-bg-red" />
          <strong>{failed.length}</strong> failed / rolled back
        </div>
        <div>
          <span className="fe-state-dot fe-bg-amber" />
          <strong>{stale.length}</strong> stale / expired / superseded
        </div>
        <div>
          <span className="fe-state-dot fe-bg-blue" />
          <strong>{approved.length}</strong> approved, awaiting PR
        </div>
      </div>
      <Section
        title="Review queue"
        label="HUMAN IN THE LOOP"
        action={
          <Link className="fe-text-button" to={`${basePath}/recommendations`}>
            View all {records.length}
            <ArrowUpRight size={15} />
          </Link>
        }
      >
        <RecommendationTable
          records={records.filter((record) =>
            ['AwaitingApproval', 'Deferred', 'Observing'].includes(record.status.phase)
          )}
          basePath={basePath}
          compact
        />
      </Section>
      <div className="fe-overview-lower">
        <Section title="Fleet distribution" label="CURRENT REVIEW RECORDS">
          <div className="fe-distributions">
            {dimensions.map((dimension) => {
              const groups = new Map<string, number>();
              records.forEach((record) =>
                groups.set(dimension.get(record), (groups.get(dimension.get(record)) ?? 0) + 1)
              );
              return (
                <div className="fe-distribution" key={dimension.label}>
                  <h3>{dimension.label}</h3>
                  {[...groups.entries()]
                    .sort((left, right) => right[1] - left[1])
                    .map(([value, count]) => (
                      <Link
                        key={value}
                        to={`${basePath}/recommendations?${dimension.filter}=${encodeURIComponent(value)}`}
                        className="fe-distribution-row"
                      >
                        <div>
                          <span>{phaseLabel(value)}</span>
                          <span className="fe-mono">{count}</span>
                        </div>
                        <div className="fe-bar-track">
                          <span
                            style={{
                              width: `${records.length ? (count / records.length) * 100 : 0}%`,
                            }}
                          />
                        </div>
                      </Link>
                    ))}
                </div>
              );
            })}
          </div>
        </Section>
        <Section title="Evidence & delivery" label="OPERATING BOUNDARIES">
          <div className="fe-boundary-list">
            <div>
              <Badge tone="green">Read-only</Badge>
              <h3>No workload mutations</h3>
            </div>
            <div>
              <Badge tone="blue">GitOps</Badge>
              <h3>Implementation through pull requests</h3>
            </div>
            <div>
              <Badge tone="neutral">Unreconciled</Badge>
              <h3>Verified savings unavailable</h3>
              <span className="fe-small fe-muted">No period-aligned amortized cost evidence.</span>
            </div>
            <div className="fe-evidence-count">
              <strong>
                {records.filter((record) => record.spec.completeness === 'complete').length} /{' '}
                {records.length}
              </strong>
              <span>records with complete evidence</span>
            </div>
          </div>
        </Section>
      </div>
    </>
  );
}
