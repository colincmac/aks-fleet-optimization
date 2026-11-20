import { useDeferredValue, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowDownUp, ArrowUpRight, Search, SlidersHorizontal, X } from 'lucide-react';
import type { OptimizationRecommendation } from '../models/review';
import { freshness, percentageChange, phaseLabel, timestamp } from '../utils/safety';
import { Badge, EmptyState, Status } from './primitives';

export function recordPath(base: string, record: OptimizationRecommendation) {
  return `${base}/recommendations/${encodeURIComponent(record.metadata.namespace)}/${encodeURIComponent(record.metadata.name)}`;
}
export function RecommendationTable({
  records,
  basePath,
  compact = false,
}: {
  records: OptimizationRecommendation[];
  basePath: string;
  compact?: boolean;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const [expanded, setExpanded] = useState(false);
  const [sort, setSort] = useState('risk');
  const [descending, setDescending] = useState(true);
  const [page, setPage] = useState(0);
  const search = useDeferredValue(params.get('q') ?? '');
  function filter(key: string, value: string) {
    const next = new URLSearchParams(location.search);
    if (value) next.set(key, value);
    else next.delete(key);
    navigate({ pathname: location.pathname, search: next.toString() }, { replace: true });
    setPage(0);
  }
  const definitions = [
    {
      key: 'cluster',
      label: 'Cluster',
      values: records.map((item) => item.spec.finding.cluster_name),
    },
    {
      key: 'namespace',
      label: 'Namespace',
      values: records.map((item) => item.spec.target.namespace),
    },
    { key: 'risk', label: 'Risk', values: ['low', 'medium', 'high'] },
    { key: 'phase', label: 'Workflow', values: records.map((item) => item.status.phase) },
    { key: 'kind', label: 'Workload kind', values: records.map((item) => item.spec.target.kind) },
    { key: 'type', label: 'Type', values: records.map((item) => item.spec.type) },
    { key: 'source', label: 'Source', values: records.map((item) => item.spec.source) },
    { key: 'confidence', label: 'Confidence', values: ['low', 'medium', 'high'] },
    {
      key: 'freshness',
      label: 'Freshness',
      values: ['Fresh', 'Expired', 'Stale evidence', 'Superseded', 'Generation not observed'],
    },
    { key: 'pr', label: 'Pull request', values: ['Present', 'Not created'] },
  ];
  const filtered = records
    .filter((record) => {
      const values: Record<string, string> = {
        cluster: record.spec.finding.cluster_name,
        namespace: record.spec.target.namespace,
        risk: record.spec.risk.level,
        phase: record.status.phase,
        kind: record.spec.target.kind,
        type: record.spec.type,
        source: record.spec.source,
        confidence: record.spec.finding.confidence,
        pr: record.status.pullRequest.state === 'NotCreated' ? 'Not created' : 'Present',
      };
      const fresh = freshness(record);
      return (
        (!search ||
          `${record.spec.finding.id} ${record.spec.target.name} ${record.spec.target.container} ${record.spec.finding.owner ?? ''}`
            .toLowerCase()
            .includes(search.toLowerCase())) &&
        Object.entries(values).every(
          ([key, value]) => !params.get(key) || params.get(key) === value
        ) &&
        (!params.get('freshness') ||
          (params.get('freshness') === 'Fresh'
            ? fresh.length === 0
            : fresh.includes(params.get('freshness')!)))
      );
    })
    .sort((left, right) => {
      const weight = { low: 0, medium: 1, high: 2 };
      const compare =
        sort === 'risk'
          ? weight[left.spec.risk.level] - weight[right.spec.risk.level]
          : sort === 'age'
            ? Date.parse(left.spec.generatedAt) - Date.parse(right.spec.generatedAt)
            : sort === 'workload'
              ? left.spec.target.name.localeCompare(right.spec.target.name)
              : left.spec.finding.id.localeCompare(right.spec.finding.id);
      return (descending ? -1 : 1) * compare;
    });
  const maxPage = Math.max(0, Math.ceil(filtered.length / 10) - 1);
  const currentPage = Math.min(page, maxPage);
  const visible = compact
    ? filtered.slice(0, 5)
    : filtered.slice(currentPage * 10, currentPage * 10 + 10);
  const sortBy = (key: string) => {
    setSort(key);
    setDescending(sort === key ? !descending : false);
  };
  return (
    <>
      {!compact && (
        <div className="fe-filters">
          <div className="fe-filter-main">
            <label className="fe-search">
              <Search size={17} />
              <input
                aria-label="Search recommendations"
                placeholder="Search workload, owner, or ID"
                value={params.get('q') ?? ''}
                onChange={(event) => filter('q', event.target.value)}
              />
            </label>
            {definitions.slice(0, 4).map(({ key, label, values }) => (
              <label className="fe-select-label" key={key}>
                <span className="fe-sr-only">{label}</span>
                <select
                  aria-label={label}
                  value={params.get(key) ?? ''}
                  onChange={(event) => filter(key, event.target.value)}
                >
                  <option value="">
                    All {label.toLowerCase()}
                    {label === 'Workflow' ? ' states' : 's'}
                  </option>
                  {[...new Set(values)].sort().map((value) => (
                    <option key={value} value={value}>
                      {phaseLabel(value)}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <button
              className={`fe-icon-button ${expanded ? 'fe-selected' : ''}`}
              title="More filters"
              aria-label="More filters"
              aria-expanded={expanded}
              onClick={() => setExpanded(!expanded)}
            >
              <SlidersHorizontal size={18} />
            </button>
          </div>
          {expanded && (
            <div className="fe-filter-extra">
              {definitions.slice(4).map(({ key, label, values }) => (
                <label className="fe-field" key={key}>
                  {label}
                  <select
                    aria-label={label}
                    value={params.get(key) ?? ''}
                    onChange={(event) => filter(key, event.target.value)}
                  >
                    <option value="">All</option>
                    {[...new Set(values)].sort().map((value) => (
                      <option key={value} value={value}>
                        {phaseLabel(value)}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          )}
          {location.search && (
            <div className="fe-active-filters">
              <span>{filtered.length} matching recommendations</span>
              <button
                className="fe-text-button"
                onClick={() => {
                  navigate(location.pathname, { replace: true });
                  setPage(0);
                }}
              >
                <X size={13} />
                Clear filters
              </button>
            </div>
          )}
        </div>
      )}
      {visible.length === 0 ? (
        <EmptyState title="No matching recommendations">
          No findings match this view. This does not establish fleet health.
        </EmptyState>
      ) : (
        <div className="fe-table-wrap">
          <table className="fe-table">
            <thead>
              <tr>
                <th>
                  <button onClick={() => sortBy('workload')}>
                    Workload <ArrowDownUp size={12} />
                  </button>
                </th>
                <th>Recommendation</th>
                <th>Proposed change</th>
                <th>
                  <button onClick={() => sortBy('risk')}>
                    Risk <ArrowDownUp size={12} />
                  </button>
                </th>
                <th>Workflow</th>
                {!compact && (
                  <>
                    <th>Confidence</th>
                    <th>
                      <button onClick={() => sortBy('age')}>
                        Age / expiration <ArrowDownUp size={12} />
                      </button>
                    </th>
                    <th>PR / validation</th>
                  </>
                )}
                <th>
                  <span className="fe-sr-only">Open</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((record) => {
                const current = record.spec.finding.current_requests;
                const proposed = record.spec.finding.proposed_requests;
                const replicaFloor =
                  record.spec.finding.current_replica_floor != null ||
                  record.spec.finding.proposed_replica_floor != null;
                const memoryLimit =
                  record.spec.finding.current_limits != null ||
                  record.spec.finding.proposed_limits != null;
                const delta = percentageChange(current?.cpu_mcores, proposed?.cpu_mcores);
                const flags = freshness(record);
                const age = Math.max(
                  0,
                  Math.floor((Date.now() - Date.parse(record.spec.generatedAt)) / 3600000)
                );
                return (
                  <tr key={record.metadata.uid}>
                    <td>
                      <Link className="fe-workload-link" to={recordPath(basePath, record)}>
                        {record.spec.target.name}
                      </Link>
                      <span className="fe-cell-sub">
                        {record.spec.finding.cluster_name} <span className="fe-divider-dot">/</span>{' '}
                        {record.spec.target.namespace}
                      </span>
                      {!compact && (
                        <span className="fe-cell-sub">
                          {record.spec.target.kind} · {record.spec.target.container}
                        </span>
                      )}
                    </td>
                    <td>
                      <span className="fe-mono fe-small">{record.spec.finding.id}</span>
                      <span className="fe-cell-sub">
                        {record.spec.source === 'VPA'
                          ? 'VPA resource review'
                          : record.spec.type === 'CpuRequestReview'
                            ? 'CPU request review'
                            : record.spec.type}
                      </span>
                      <Badge tone={record.spec.source === 'AI-assisted' ? 'violet' : 'neutral'}>
                        {record.spec.source}
                      </Badge>
                    </td>
                    <td>
                      {replicaFloor ? (
                        <>
                          <span className="fe-mono fe-resource-line">
                            {record.spec.finding.current_replica_floor ?? '?'}{' '}
                            <span className="fe-muted">→</span>{' '}
                            {record.spec.finding.proposed_replica_floor ?? '?'}{' '}
                            <small>replicas</small>
                          </span>
                          <span className="fe-cell-sub">
                            HPA minimum; resource requests unchanged
                          </span>
                        </>
                      ) : memoryLimit ? (
                        <>
                          <span className="fe-mono fe-resource-line">
                            {record.spec.finding.current_limits?.memory_mib ?? '?'}{' '}
                            <span className="fe-muted">→</span>{' '}
                            {record.spec.finding.proposed_limits?.memory_mib ?? '?'}{' '}
                            <small>MiB</small>
                          </span>
                          <span className="fe-cell-sub">
                            Memory limit; separate review required
                          </span>
                        </>
                      ) : (
                        <>
                          <span className="fe-mono fe-resource-line">
                            {current?.cpu_mcores ?? '?'} <span className="fe-muted">→</span>{' '}
                            {proposed?.cpu_mcores ?? '?'} <small>mCPU</small>
                          </span>
                          <span className="fe-cell-sub">
                            {delta === null
                              ? 'CPU change unavailable'
                              : `${delta > 0 ? '+' : ''}${delta}% CPU requests`}
                          </span>
                          {!compact && (
                            <span className="fe-cell-sub">
                              Memory {current?.memory_mib ?? '?'} →{' '}
                              {proposed?.memory_mib ?? 'unchanged'} MiB
                            </span>
                          )}
                        </>
                      )}
                    </td>
                    <td>
                      <Badge
                        tone={
                          record.spec.risk.level === 'high'
                            ? 'red'
                            : record.spec.risk.level === 'medium'
                              ? 'amber'
                              : 'green'
                        }
                        dot
                      >
                        {phaseLabel(record.spec.risk.level)}
                      </Badge>
                    </td>
                    <td>
                      <Status value={record.status.phase} />
                      {flags.length > 0 && (
                        <span className="fe-cell-sub fe-warning-text">{flags.join(' · ')}</span>
                      )}
                    </td>
                    {!compact && (
                      <>
                        <td>
                          <Badge tone="neutral">{phaseLabel(record.spec.finding.confidence)}</Badge>
                        </td>
                        <td>
                          <span>{Number.isFinite(age) ? `${age}h old` : 'Age unknown'}</span>
                          <span className="fe-cell-sub">{timestamp(record.spec.expiresAt)}</span>
                        </td>
                        <td>
                          <span className="fe-cell-sub">
                            PR: {phaseLabel(record.status.pullRequest.state)}
                          </span>
                          <Status value={record.status.validation.state} />
                        </td>
                      </>
                    )}
                    <td>
                      <Link
                        aria-label={`Open ${record.spec.target.name}`}
                        className="fe-icon-button"
                        to={recordPath(basePath, record)}
                      >
                        <ArrowUpRight size={17} />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {!compact && (
        <div className="fe-pagination">
          <span>
            {filtered.length ? currentPage * 10 + 1 : 0}–
            {Math.min(currentPage * 10 + 10, filtered.length)} of {filtered.length} recommendations
          </span>
          <div>
            <button
              className="fe-button"
              disabled={currentPage === 0}
              onClick={() => setPage(currentPage - 1)}
            >
              Previous
            </button>
            <button
              className="fe-button"
              disabled={currentPage >= maxPage}
              onClick={() => setPage(currentPage + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </>
  );
}
