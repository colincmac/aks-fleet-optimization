import {
  AlertCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Layers3,
  LoaderCircle,
  RefreshCw,
  Search,
  Server,
} from 'lucide-react';
import { useEffect, useRef, useState, type Ref } from 'react';
import {
  assessmentRunHealth,
  type AssessedCluster,
  type AssessedFinding,
  type AssessmentViewFeed,
} from '../api/assessmentFeed';
import { Badge, EmptyState, Notice } from './primitives';

export type LoadAssessments = (signal: AbortSignal) => Promise<AssessmentViewFeed>;
const refreshMs = 60000;
const pageSize = 20;
const clockFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'UTC',
});

function Clock({ value }: { value: string }) {
  return <time dateTime={value}>{clockFormat.format(new Date(value))} UTC</time>;
}

export function Assessments({ load }: { load?: LoadAssessments }) {
  const [epoch, setEpoch] = useState(0);
  const [feed, setFeed] = useState<AssessmentViewFeed>();
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [selection, setSelection] = useState('');
  const selectedHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const request = load;
    if (!request) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const next = await request(controller.signal);
        if (!controller.signal.aborted) {
          setFeed(next);
          setState('ready');
        }
      } catch {
        if (!controller.signal.aborted) {
          setFeed(undefined);
          setState('error');
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, refreshMs);
      }
    };
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, epoch]);

  const clusters = feed?.clusters ?? [];
  const failed = new Set(feed?.failedClusters);
  const unavailable = [...failed].filter((id) => !clusters.some((cluster) => cluster.id === id));
  const selected = clusters.find((cluster) => cluster.id === selection) ?? clusters[0];
  const run = feed?.runStatus && assessmentRunHealth(feed, feed.runStatus, Date.now());
  const retained = new Set(
    clusters
      .filter((cluster) => run?.outcome === 'failed' || failed.has(cluster.id))
      .map((cluster) => cluster.id)
  );
  const stale = new Set(run?.staleClusters);
  return (
    <div className="fe-assessments">
      <div className="fe-page-heading">
        <div>
          <div className="fe-eyebrow">FLEET EVIDENCE</div>
          <h1>Assessments</h1>
          <p>Saved advisor evaluations</p>
        </div>
        {load && (
          <button
            className="fe-icon-button"
            type="button"
            title="Refresh assessments"
            aria-label="Refresh assessments"
            disabled={state === 'loading'}
            onClick={() => {
              setState('loading');
              setEpoch((value) => value + 1);
            }}
          >
            <RefreshCw className={state === 'loading' ? 'fe-spin' : ''} size={17} />
          </button>
        )}
      </div>
      {!load ? (
        <EmptyState title="No assessment feed configured">
          Saved assessments are not connected in this Headlamp installation.
        </EmptyState>
      ) : state === 'error' ? (
        <Notice danger>
          Assessment feed unavailable or invalid. No results are displayed. Ask your platform
          operator to check the published feed and your access to it.
        </Notice>
      ) : !feed ? (
        <div className="fe-loading" role="status">
          <LoaderCircle className="fe-spin" size={24} /> Loading assessments...
        </div>
      ) : !selected ? (
        <EmptyState title="No published assessments">
          No cluster conclusions are available.
        </EmptyState>
      ) : (
        <>
          {run ? (
            <section aria-label="Scheduled assessment status">
              <dl className="fe-assessment-clock">
                <div>
                  <dt>Latest recorded batch attempt</dt>
                  <dd>
                    <Clock value={run.attemptedAt} />{' '}
                    <Badge tone={run.outcome === 'complete' ? 'neutral' : 'amber'}>
                      {run.outcome}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt>Published assessment evaluated</dt>
                  <dd>
                    <Clock value={run.publishedEvaluationAt} />
                  </dd>
                </div>
              </dl>
              {run.outcome === 'failed' && (
                <Notice danger>
                  Latest recorded attempt failed. Showing previously published results.
                </Notice>
              )}
              {run.stale && (
                <Notice>Published results are stale. Check your assessment scheduler.</Notice>
              )}
            </section>
          ) : feed.scheduled ? (
            <Notice>Scheduled status is unavailable. Check the evaluation times below.</Notice>
          ) : null}
          <section aria-label="Fleet assessments">
            <div className="fe-assessment-band">
              <h2>Targets in published roster</h2>
              <Badge tone="neutral">{clusters.length + unavailable.length} recorded</Badge>
              <Badge tone="neutral">
                {run ? `${clusters.length - retained.size} reporting` : 'Reporting status unknown'}
              </Badge>
              <Badge tone={retained.size ? 'amber' : 'neutral'}>
                {retained.size} with prior results
              </Badge>
              <Badge tone={unavailable.length ? 'amber' : 'neutral'}>
                {unavailable.length} without a saved result
              </Badge>
            </div>
            <p className="fe-assessment-roster-note">
              This roster comes from the saved feed. Reporting refers to the last matched batch
              attempt, not live cluster health.
            </p>
            <ul className="fe-assessment-clusters" role="list">
              {clusters.map((cluster) => {
                const blocked = cluster.findings.filter(
                  (finding) => finding.state === 'blocked'
                ).length;
                const findings = cluster.findings.length - blocked;
                const duplicateName = clusters.some(
                  (other) => other.id !== cluster.id && other.name === cluster.name
                );
                return (
                  <li key={cluster.id}>
                    <button
                      type="button"
                      className="fe-assessment-cluster"
                      aria-pressed={selected.id === cluster.id}
                      onClick={() => setSelection(cluster.id)}
                    >
                      <span className="fe-assessment-cluster-name">
                        <Server size={17} />
                        <strong>{cluster.name}</strong>
                        <Badge tone={cluster.status === 'partial' ? 'amber' : 'neutral'}>
                          {cluster.status}
                        </Badge>
                        {retained.has(cluster.id) && <Badge tone="amber">Prior results</Badge>}
                        {stale.has(cluster.id) && <Badge tone="amber">Stale evaluation</Badge>}
                      </span>
                      {duplicateName && <small>{cluster.id}</small>}
                      <small>
                        Evaluated <Clock value={cluster.evaluatedAt} />
                      </small>
                      <small>
                        {findings} findings · {blocked} blocked checks
                      </small>
                    </button>
                  </li>
                );
              })}
              {unavailable.map((id) => (
                <li className="fe-assessment-cluster" key={id}>
                  <strong>{id}</strong>
                  <span>
                    <Badge tone="amber">No saved result</Badge>
                  </span>
                  <small>Input failed for this target.</small>
                </li>
              ))}
            </ul>
            <button
              className="fe-text-button"
              type="button"
              onClick={() => selectedHeading.current?.focus()}
            >
              Jump to selected assessment <ChevronDown size={14} />
            </button>
          </section>
          {retained.has(selected.id) && (
            <Notice>
              Showing a prior evaluation for this cluster, not a result of the latest attempt.
            </Notice>
          )}
          <ClusterAssessment
            key={`${selected.id}:${selected.uid}`}
            cluster={selected}
            headingRef={selectedHeading}
          />
        </>
      )}
    </div>
  );
}

const views = [
  { key: 'findings', label: 'Findings', icon: ClipboardList },
  { key: 'discovery', label: 'Discovery', icon: Layers3 },
  { key: 'gaps', label: 'Evidence gaps', icon: AlertCircle },
] as const;

function ClusterAssessment({
  cluster,
  headingRef,
}: {
  cluster: AssessedCluster;
  headingRef: Ref<HTMLHeadingElement>;
}) {
  const [view, setView] = useState<(typeof views)[number]['key']>('findings');
  const [namespace, setNamespace] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const namespaces = [
    ...new Set([
      ...cluster.namespaces.map((item) => item.name),
      ...cluster.findings.flatMap((item) => (item.namespace === null ? [] : [item.namespace])),
    ]),
  ].sort();
  const activeNamespace = namespaces.includes(namespace) ? namespace : '';
  const query = search.trim().toLowerCase();
  const matches = (...values: (string | null)[]) =>
    values.some((value) => value?.toLowerCase().includes(query));
  const findings = cluster.findings.filter(
    (item) =>
      item.state === (view === 'gaps' ? 'blocked' : 'finding') &&
      (!activeNamespace || item.namespace === activeNamespace) &&
      matches(
        item.namespace,
        item.workload,
        item.rule,
        item.state === 'finding' ? item.title : item.reasons.join(' ')
      )
  );
  const workloads = cluster.namespaces.flatMap((item) =>
    activeNamespace && item.name !== activeNamespace
      ? []
      : item.workloads
          .filter((row) => matches(item.name, row.name, row.kind))
          .map((row) => ({ ...row, namespace: item.name }))
  );
  const namespaceRollup = view === 'discovery' && !activeNamespace && !query;
  const total = namespaceRollup
    ? cluster.namespaces.length
    : view === 'discovery'
      ? workloads.length
      : findings.length;
  const activePage = Math.min(page, Math.max(0, Math.ceil(total / pageSize) - 1));
  const start = activePage * pageSize;
  return (
    <section className="fe-assessment-focus" aria-label={`${cluster.name} assessment`}>
      <div className="fe-assessment-band">
        <h2 ref={headingRef} tabIndex={-1}>
          {cluster.name}
        </h2>
        <Badge tone="blue">{cluster.mode}</Badge>
      </div>
      <dl className="fe-assessment-clock">
        <div>
          <dt>Evaluated</dt>
          <dd>
            <Clock value={cluster.evaluatedAt} />
          </dd>
        </div>
        <div>
          <dt>Observation window</dt>
          <dd>
            <Clock value={cluster.windowStart} /> to <Clock value={cluster.windowEnd} />
          </dd>
        </div>
      </dl>
      {cluster.status === 'partial' && (
        <Notice>
          Partial assessment. The displayed records do not represent the entire cluster.
        </Notice>
      )}
      <nav className="fe-host-nav fe-assessment-views" aria-label="Assessment views">
        {views.map(({ key, label, icon: Icon }) => (
          <button
            type="button"
            key={key}
            aria-pressed={view === key}
            className={view === key ? 'fe-nav-active' : ''}
            onClick={() => {
              setView(key);
              setPage(0);
            }}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </nav>
      <div className="fe-assessment-filters">
        <label>
          <span>Namespace</span>
          <select
            aria-label="Namespace"
            value={activeNamespace}
            onChange={(event) => {
              setNamespace(event.target.value);
              setPage(0);
            }}
          >
            <option value="">All namespaces and cluster scope</option>
            {namespaces.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Search {view === 'discovery' ? 'workloads' : 'checks'}</span>
          <span className="fe-assessment-search">
            <Search aria-hidden="true" size={16} />
            <input
              type="search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(0);
              }}
            />
          </span>
        </label>
      </div>
      {view === 'gaps' && cluster.issues.length > 0 && (
        <div className="fe-assessment-issues">
          <h3>Cluster collection issues</h3>
          <div>
            {cluster.issues.map((code) => (
              <Badge key={code} tone="amber">
                {code}
              </Badge>
            ))}
          </div>
        </div>
      )}
      {view === 'discovery' && cluster.unboundWorkloads > 0 && (
        <Notice>
          {cluster.unboundWorkloads} cluster workload records lack a retained UID and are not
          listed.
        </Notice>
      )}
      {namespaceRollup && total > 0 ? (
        <div className="fe-assessment-table">
          <table>
            <caption>Namespaces retained in the assessment</caption>
            <thead>
              <tr>
                <th>Namespace</th>
                <th>Workloads with a retained UID</th>
              </tr>
            </thead>
            <tbody>
              {cluster.namespaces.slice(start, start + pageSize).map((row) => (
                <tr key={row.name}>
                  <td>
                    <button
                      className="fe-text-button"
                      type="button"
                      onClick={() => {
                        setNamespace(row.name);
                        setPage(0);
                      }}
                    >
                      {row.name}
                      <ChevronRight size={14} />
                    </button>
                  </td>
                  <td>{row.workloads.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : view === 'discovery' && total > 0 ? (
        <div className="fe-assessment-table">
          <table>
            <caption>Workloads retained in the assessment</caption>
            <thead>
              <tr>
                <th>Namespace</th>
                <th>Workload</th>
                <th>Kind</th>
                <th>UID</th>
              </tr>
            </thead>
            <tbody>
              {workloads.slice(start, start + pageSize).map((row) => (
                <tr key={row.uid}>
                  <td>{row.namespace}</td>
                  <td>{row.name}</td>
                  <td>{row.kind}</td>
                  <td>
                    <code>{row.uid}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : total > 0 ? (
        <div className="fe-assessment-list">
          {findings.slice(start, start + pageSize).map((finding) => (
            <FindingRow key={finding.id} finding={finding} />
          ))}
        </div>
      ) : (
        <EmptyState title="No matching records">
          {view === 'discovery'
            ? 'No matching workload identities were retained.'
            : 'No matching records were emitted by this assessment.'}
        </EmptyState>
      )}
      {total > 0 && (
        <div className="fe-assessment-pagination">
          <span>
            {start + 1}–{Math.min(start + pageSize, total)} of {total}
          </span>
          <button
            className="fe-icon-button"
            type="button"
            title="Previous page"
            aria-label="Previous page"
            disabled={activePage === 0}
            onClick={() => setPage(activePage - 1)}
          >
            <ChevronLeft size={17} />
          </button>
          <button
            className="fe-icon-button"
            type="button"
            title="Next page"
            aria-label="Next page"
            disabled={start + pageSize >= total}
            onClick={() => setPage(activePage + 1)}
          >
            <ChevronRight size={17} />
          </button>
        </div>
      )}
    </section>
  );
}

function FindingRow({ finding }: { finding: AssessedFinding }) {
  const priority = finding.state === 'blocked' ? 'blocked' : finding.severity;
  const tone =
    priority === 'high' || priority === 'critical'
      ? 'red'
      : priority === 'medium' || priority === 'blocked'
        ? 'amber'
        : 'neutral';
  return (
    <details className="fe-assessment-finding">
      <summary>
        <ChevronDown size={16} />
        <span>
          <strong>{finding.state === 'finding' ? finding.title : finding.rule}</strong>
          <small>
            {finding.namespace ?? 'Cluster scope'}
            {finding.workload ? ` / ${finding.workload}` : ''}
          </small>
        </span>
        <Badge tone={tone}>{priority}</Badge>
      </summary>
      <div className="fe-assessment-detail">
        <code>
          {finding.rule} · v{finding.version} · {finding.id}
        </code>
        {finding.state === 'blocked' ? (
          <ul>
            {finding.reasons.map((reason) => (
              <li key={reason}>
                <code>{reason}</code>
              </li>
            ))}
          </ul>
        ) : (
          <>
            <p>{finding.summary}</p>
            <p>
              <strong>{finding.confidence}</strong> confidence · {finding.category}
            </p>
            {finding.comparisons.length > 0 && (
              <div className="fe-assessment-table">
                <table>
                  <caption>Guarded suggestion (not approved)</caption>
                  <thead>
                    <tr>
                      <th>Dimension</th>
                      <th>Current</th>
                      <th>Proposed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {finding.comparisons.map((row) => (
                      <tr key={row.dimension}>
                        <td>{row.dimension}</td>
                        <td>{row.current === null ? 'Unknown' : `${row.current} ${row.unit}`}</td>
                        <td>
                          {row.proposed} {row.unit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {finding.evidence.length > 0 && (
              <div className="fe-assessment-table">
                <table>
                  <caption>Evidence</caption>
                  <thead>
                    <tr>
                      <th>Measure</th>
                      <th>Value</th>
                      <th>Unit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {finding.evidence.map((row, index) => (
                      <tr key={`${row.metric}:${index}`}>
                        <td>{row.metric}</td>
                        <td>{row.value === null ? 'Unknown' : String(row.value)}</td>
                        <td>{row.unit ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {finding.risks.length > 0 && (
              <div>
                <h3>Risks</h3>
                <ul>
                  {finding.risks.map((risk, index) => (
                    <li key={index}>{risk}</li>
                  ))}
                </ul>
              </div>
            )}
            {finding.checks.length > 0 && (
              <div>
                <h3>Validation before change</h3>
                <ul>
                  {finding.checks.map((check) => (
                    <li key={check}>{check}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </details>
  );
}
