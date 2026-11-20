import type { ReactNode } from 'react';
import { AlertCircle, Check, ChevronRight, Clock3, ShieldCheck } from 'lucide-react';
import { phaseLabel } from '../utils/safety';

export function Badge({
  children,
  tone = 'neutral',
  dot = false,
}: {
  children: ReactNode;
  tone?: string;
  dot?: boolean;
}) {
  return (
    <span className={`fe-badge fe-${tone}`}>
      {dot && <span className="fe-dot" />}
      {children}
    </span>
  );
}
export function Status({ value }: { value: string }) {
  const tone = ['Healthy', 'Approved', 'Pass', 'complete'].includes(value)
    ? 'green'
    : ['Failed', 'RolledBack', 'Fail', 'Rejected', 'Expired'].includes(value)
      ? 'red'
      : ['AwaitingApproval', 'Warning', 'Deferred', 'Unknown', 'partial'].includes(value)
        ? 'amber'
        : ['Open', 'PullRequestOpen', 'Collecting', 'Validating'].includes(value)
          ? 'blue'
          : 'neutral';
  return (
    <Badge tone={tone} dot>
      {phaseLabel(value)}
    </Badge>
  );
}
export function Notice({ children, danger = false }: { children: ReactNode; danger?: boolean }) {
  return (
    <div
      className={`fe-notice ${danger ? 'fe-notice-danger' : ''}`}
      role={danger ? 'alert' : 'status'}
    >
      <AlertCircle size={17} />
      <div>{children}</div>
    </div>
  );
}
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="fe-empty">
      <ShieldCheck size={30} />
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}
export function Section({
  title,
  label,
  action,
  children,
}: {
  title: string;
  label?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="fe-section">
      <div className="fe-section-heading">
        <div>
          {label && <div className="fe-eyebrow">{label}</div>}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Metric({
  title,
  value,
  note,
  children,
}: {
  title: string;
  value: ReactNode;
  note?: string;
  children?: ReactNode;
}) {
  return (
    <div className="fe-metric">
      <span className="fe-muted">{title}</span>
      <div className="fe-metric-value">
        {value}
        {children}
      </div>
      {note && <span className="fe-small fe-muted">{note}</span>}
    </div>
  );
}
export function StepIcon({ state }: { state: 'done' | 'current' | 'pending' }) {
  return (
    <span className={`fe-step-icon fe-step-${state}`}>
      {state === 'done' ? (
        <Check size={14} />
      ) : state === 'current' ? (
        <Clock3 size={14} />
      ) : (
        <ChevronRight size={14} />
      )}
    </span>
  );
}
