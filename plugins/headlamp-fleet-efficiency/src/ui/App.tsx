import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowUpRight,
  Bell,
  Boxes,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  LayoutDashboard,
  LoaderCircle,
  Menu,
  Network,
  RefreshCw,
  Settings2,
  ShieldCheck,
  X,
} from 'lucide-react';
import type {
  Capabilities,
  OptimizationRecommendation,
  RecommendationProvider,
  VpaRecord,
} from '../models/review';
import { deniedCapabilities } from '../api/provider';
import { Overview } from './Overview';
import { RecommendationTable } from './RecommendationTable';
import { Details } from './Details';
import { OperatorCatalogPanel } from './Catalog';
import { Badge, EmptyState, Notice, Section } from './primitives';
import { timestamp } from '../utils/safety';
import type { RelatedKubernetesResource } from './renderers';
import './styles.css';

interface AppProps {
  provider: RecommendationProvider;
  basePath: string;
  standalone?: boolean;
  dark?: boolean;
  vpas?: VpaRecord[];
  vpaError?: string;
  onRoleChange?: (role: string) => void;
  namespace?: string;
  hostVersion?: string;
  relatedLinks?: Partial<
    Record<'keda' | 'karpenter', (resource: RelatedKubernetesResource) => string>
  >;
}
export function App({
  provider,
  basePath,
  standalone = false,
  dark = false,
  vpas = [],
  vpaError,
  onRoleChange,
  namespace = 'fleet-efficiency-system',
  hostVersion = 'Runtime version not supplied',
  relatedLinks,
}: AppProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [records, setRecords] = useState<OptimizationRecommendation[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities>(deniedCapabilities);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [epoch, setEpoch] = useState(0);
  const [updated, setUpdated] = useState<string>();
  const [menu, setMenu] = useState(false);
  const suffix = location.pathname.startsWith(basePath)
    ? location.pathname.slice(basePath.length)
    : '';
  const parts = suffix.split('/').filter(Boolean);
  const section =
    parts[0] === 'catalog'
      ? 'catalog'
      : parts[0] === 'settings'
        ? 'settings'
        : parts[0] === 'recommendations'
          ? 'recommendations'
          : 'overview';
  const isDetail = section === 'recommendations' && parts.length >= 3;
  const record = isDetail
    ? records.find(
        (item) =>
          item.metadata.namespace === decodeURIComponent(parts[1]) &&
          item.metadata.name === decodeURIComponent(parts[2])
      )
    : undefined;
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setCapabilities(deniedCapabilities);
    provider
      .list(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setRecords(result);
          setUpdated(new Date().toISOString());
        }
      })
      .catch((caught) => {
        if (!controller.signal.aborted) {
          setError(caught instanceof Error ? caught.message : 'Recommendation API unavailable.');
          setRecords([]);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [provider, epoch]);
  useEffect(() => {
    const controller = new AbortController();
    setCapabilities(deniedCapabilities);
    provider
      .capabilities(record, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setCapabilities(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setCapabilities(deniedCapabilities);
      });
    return () => controller.abort();
  }, [provider, record, epoch]);
  useEffect(() => {
    setMenu(false);
  }, [location.pathname]);
  const nav = [
    { key: 'overview', label: 'Overview', path: basePath, icon: LayoutDashboard },
    { key: 'catalog', label: 'Recommendation catalog', path: `${basePath}/catalog`, icon: Boxes },
    {
      key: 'recommendations',
      label: 'Recommendations',
      path: `${basePath}/recommendations`,
      icon: ClipboardCheck,
    },
    {
      key: 'settings',
      label: 'Settings & diagnostics',
      path: `${basePath}/settings`,
      icon: Settings2,
    },
  ];
  return (
    <div
      className={`fe-root ${standalone ? 'fe-standalone' : 'fe-embedded'} ${dark ? 'fe-dark' : ''}`}
    >
      {standalone && (
        <>
          <aside className={`fe-sidebar ${menu ? 'fe-sidebar-open' : ''}`}>
            <Link className="fe-brand" to={basePath}>
              <div className="fe-brand-icon">
                <Network size={25} />
              </div>
              <div>
                <strong>Fleet Advisor</strong>
                <span>AKS EFFICIENCY</span>
              </div>
            </Link>
            <button
              className="fe-icon-button fe-mobile-close"
              aria-label="Close navigation"
              onClick={() => setMenu(false)}
            >
              <X size={20} />
            </button>
            <div className="fe-workspace">
              <div className="fe-workspace-icon">
                <Boxes size={19} />
              </div>
              <div>
                <strong>Management cluster</strong>
                <span>Synthetic fleet</span>
              </div>
              <ChevronDown size={14} />
            </div>
            <div className="fe-nav-caption">WORKSPACE</div>
            <nav aria-label="Main navigation">
              {nav.map((item) => (
                <Link
                  key={item.key}
                  to={item.path}
                  className={section === item.key ? 'fe-nav-active' : ''}
                >
                  <item.icon size={18} />
                  <span>{item.label}</span>
                  {item.key === 'recommendations' && (
                    <span className="fe-nav-count">{records.length}</span>
                  )}
                </Link>
              ))}
            </nav>
            <div className="fe-sidebar-bottom">
              <div className="fe-sidebar-safety">
                <ShieldCheck size={18} />
                <span>Read-only workloads</span>
                <span className="fe-live-dot" />
              </div>
              <a
                href="https://headlamp.dev/docs/latest/development/plugins/"
                target="_blank"
                rel="noopener noreferrer"
              >
                <CircleHelp size={17} />
                Headlamp documentation
                <ArrowUpRight size={13} />
              </a>
              <div className="fe-sidebar-version">
                FLEET EFFICIENCY ADVISOR <span>v0.1.0</span>
              </div>
            </div>
          </aside>
          {menu && (
            <button
              className="fe-mobile-scrim"
              aria-label="Close navigation overlay"
              onClick={() => setMenu(false)}
            />
          )}
        </>
      )}
      <div className="fe-work-area">
        <header className="fe-topbar">
          {standalone && (
            <button
              className="fe-icon-button fe-mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMenu(true)}
            >
              <Menu size={21} />
            </button>
          )}
          <div className="fe-breadcrumb">
            <span>{standalone ? 'Workspace' : 'Fleet Advisor'}</span>
            <ChevronRight size={13} />
            <strong>{nav.find((item) => item.key === section)?.label}</strong>
            {isDetail && (
              <>
                <ChevronRight size={13} />
                <span>{record?.spec.finding.id ?? 'Recommendation'}</span>
              </>
            )}
          </div>
          <div className="fe-topbar-actions">
            {standalone ? (
              <Badge tone="amber" dot>
                Synthetic preview
              </Badge>
            ) : (
              <Badge tone="green" dot>
                Read-only
              </Badge>
            )}
            <button
              className="fe-icon-button"
              aria-label="Refresh recommendations"
              title="Refresh recommendations"
              disabled={loading}
              onClick={() => setEpoch(epoch + 1)}
            >
              <RefreshCw size={17} className={loading ? 'fe-spin' : ''} />
            </button>
            {onRoleChange && (
              <select
                className="fe-role-select"
                aria-label="Preview reviewer role"
                defaultValue="ApplicationOwner"
                onChange={(event) => {
                  onRoleChange(event.target.value);
                  setEpoch(epoch + 1);
                }}
              >
                <option value="Viewer">Viewer</option>
                <option value="ApplicationOwner">Application owner</option>
                <option value="PlatformOwner">Platform owner</option>
              </select>
            )}
          </div>
        </header>
        {!standalone && (
          <nav className="fe-host-nav" aria-label="Fleet advisor navigation">
            {nav.map((item) => (
              <Link
                key={item.key}
                to={item.path}
                className={section === item.key ? 'fe-nav-active' : ''}
              >
                <item.icon size={16} />
                {item.label}
              </Link>
            ))}
          </nav>
        )}
        <main className="fe-content">
          {section === 'catalog' ? (
            <OperatorCatalogPanel />
          ) : error ? (
            <>
              <div className="fe-page-heading">
                <h1>Recommendations unavailable</h1>
              </div>
              <Notice danger>{error}</Notice>
              <EmptyState title="No evidence loaded">
                Check the recommendation CRD, management context, namespace and read permissions. A
                denied API is not an empty healthy fleet.
              </EmptyState>
              <button className="fe-button" onClick={() => setEpoch(epoch + 1)}>
                <RefreshCw size={15} />
                Retry
              </button>
            </>
          ) : loading && records.length === 0 ? (
            <div className="fe-loading" role="status">
              <LoaderCircle className="fe-spin" size={24} />
              Loading recommendation evidence...
            </div>
          ) : isDetail ? (
            record ? (
              <Details
                key={record.metadata.uid}
                record={record}
                basePath={basePath}
                capabilities={loading ? deniedCapabilities : capabilities}
                vpas={vpas}
                vpaError={vpaError}
                relatedLinks={relatedLinks}
                submit={async (request) => {
                  const next = await provider.act(record, request);
                  if (next.metadata.uid !== record.metadata.uid)
                    throw new Error(
                      'Backend returned a different recommendation. Refresh required.'
                    );
                  setRecords((items) =>
                    items.map((item) => (item.metadata.uid === next.metadata.uid ? next : item))
                  );
                }}
              />
            ) : (
              <EmptyState title="Recommendation not found">
                The record may have been removed or may be outside the configured review namespace.
              </EmptyState>
            )
          ) : section === 'overview' ? (
            <Overview records={records} basePath={basePath} />
          ) : section === 'recommendations' ? (
            <>
              <div className="fe-page-heading">
                <div>
                  <div className="fe-eyebrow">REVIEW WORKSPACE</div>
                  <h1>
                    Recommendations <span className="fe-title-count">{records.length}</span>
                  </h1>
                  <p className="fe-page-subtitle">
                    Measurements, investigations and guarded proposals with their evidence.
                  </p>
                </div>
                <Badge tone="neutral">{namespace}</Badge>
              </div>
              <RecommendationTable records={records} basePath={basePath} />
            </>
          ) : (
            <>
              <div className="fe-page-heading">
                <div>
                  <div className="fe-eyebrow">MANAGEMENT CONTEXT</div>
                  <h1>Settings & diagnostics</h1>
                  <p className="fe-page-subtitle">Integration health and effective access.</p>
                </div>
                <Badge>v0.1.0</Badge>
              </div>
              <Section title="Dependencies & integrations">
                <dl className="fe-diagnostics">
                  <div>
                    <dt>Recommendation API</dt>
                    <dd>
                      <Badge tone="green">Reachable · {records.length} records</Badge>
                    </dd>
                  </div>
                  <div>
                    <dt>Recommendation API version</dt>
                    <dd className="fe-mono">optimization.aks.io/v1alpha1</dd>
                  </div>
                  <div>
                    <dt>Namespace</dt>
                    <dd className="fe-mono">{namespace}</dd>
                  </div>
                  <div>
                    <dt>VPA API</dt>
                    <dd>
                      {vpaError ??
                        (vpas.length
                          ? `autoscaling.k8s.io/v1 · ${vpas.length} current objects`
                          : 'Not detected; embedded evidence only')}
                    </dd>
                  </div>
                  <div>
                    <dt>Governance backend</dt>
                    <dd>
                      <Badge tone={capabilities.backend === 'unavailable' ? 'amber' : 'blue'}>
                        {capabilities.backend}
                      </Badge>
                    </dd>
                  </div>
                  <div>
                    <dt>GitHub integration</dt>
                    <dd>
                      {capabilities.backend === 'simulator'
                        ? 'Mock provider only'
                        : capabilities.github
                          ? 'Backend configured'
                          : 'Unavailable'}
                    </dd>
                  </div>
                  <div>
                    <dt>Live metrics</dt>
                    <dd>
                      {capabilities.metrics
                        ? 'Backend advertises metrics; chart adapter not configured'
                        : 'Unavailable · embedded evidence retained'}
                    </dd>
                  </div>
                  <div>
                    <dt>Plugin version</dt>
                    <dd>0.1.0</dd>
                  </div>
                  <div>
                    <dt>Headlamp SDK</dt>
                    <dd>0.14.0 · React 18.3.1</dd>
                  </div>
                  <div>
                    <dt>Host version</dt>
                    <dd>{hostVersion}</dd>
                  </div>
                  <div>
                    <dt>Compatibility target</dt>
                    <dd>Headlamp ≥0.40 · deployment acceptance required</dd>
                  </div>
                  <div>
                    <dt>KEDA / Karpenter</dt>
                    <dd>Optional; no route adapters configured</dd>
                  </div>
                  <div>
                    <dt>Last evidence read</dt>
                    <dd>{timestamp(updated)}</dd>
                  </div>
                </dl>
              </Section>
              <Section title="Identity & authorization">
                <dl className="fe-diagnostics">
                  <div>
                    <dt>Identity</dt>
                    <dd>{capabilities.identity}</dd>
                  </div>
                  <div>
                    <dt>Effective actions</dt>
                    <dd>{capabilities.allowed.join(', ') || 'None · fails closed'}</dd>
                  </div>
                  <div>
                    <dt>Resource-scoped permissions</dt>
                    <dd>Re-evaluated when a recommendation is opened</dd>
                  </div>
                  <div>
                    <dt>Workload mutations</dt>
                    <dd>Not permitted by this plugin</dd>
                  </div>
                  <div>
                    <dt>Secrets / tokens</dt>
                    <dd>Never stored in plugin settings</dd>
                  </div>
                </dl>
                {capabilities.backend !== 'connected' && (
                  <Notice>
                    Production governance, durable audit, repository mapping and GitHub App
                    integration are not installed. The UI alone cannot authorize a production
                    change.
                  </Notice>
                )}
              </Section>
            </>
          )}
          <footer className="fe-footer">
            <span>
              <ShieldCheck size={13} />
              Evidence-first · No direct workload changes
            </span>
            <span>
              {standalone
                ? 'Synthetic data · In-memory decisions reset on reload'
                : `Management namespace: ${namespace}`}
            </span>
            <button className="fe-text-button" onClick={() => navigate(`${basePath}/settings`)}>
              Diagnostics
              <ChevronRight size={12} />
            </button>
          </footer>
        </main>
      </div>
    </div>
  );
}
