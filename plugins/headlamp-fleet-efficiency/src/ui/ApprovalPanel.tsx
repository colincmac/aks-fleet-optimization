import { useState } from 'react';
import { Check, GitPullRequest, LoaderCircle, ShieldCheck, X } from 'lucide-react';
import type {
  Action,
  ActionRequest,
  Capabilities,
  OptimizationRecommendation,
} from '../models/review';
import { acknowledgementLabels, actionBlockers, phaseLabel, validateAction } from '../utils/safety';
import { Badge, Notice, Status } from './primitives';

export function ApprovalPanel({
  record,
  capabilities,
  submit,
}: {
  record: OptimizationRecommendation;
  capabilities: Capabilities;
  submit: (request: ActionRequest) => Promise<void>;
}) {
  const [dialog, setDialog] = useState<Action | null>(null);
  const [reason, setReason] = useState('');
  const [deferUntil, setDeferUntil] = useState('');
  const [checked, setChecked] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const actions: { action: Action; label: string }[] = [
    { action: 'approve', label: 'Approve recommendation' },
    { action: 'reject', label: 'Reject' },
    { action: 'defer', label: 'Defer' },
    { action: 'request-observation', label: 'Request more observation' },
    { action: 'exception', label: 'Mark as exception' },
    { action: 'cancel', label: 'Cancel recommendation' },
  ];
  const open = (action: Action) => {
    setDialog(action);
    setChecked([]);
    setReason('');
    setError('');
    setDeferUntil('');
    setSuccess('');
  };
  const blockers = actionBlockers(record, 'approve', capabilities);
  async function send() {
    if (!dialog || pending) return;
    setPending(true);
    setError('');
    try {
      const request: ActionRequest = {
        uid: record.metadata.uid,
        resourceVersion: record.metadata.resourceVersion,
        generation: record.metadata.generation,
        evidenceVersion: record.spec.evidenceVersion,
        sourceRevision: record.spec.sourceRevision,
        idempotencyKey: crypto.randomUUID(),
        action: dialog,
        reason,
        acknowledgements: checked,
        ...(deferUntil ? { deferUntil: new Date(deferUntil).toISOString() } : {}),
      };
      validateAction(record, request, capabilities);
      await submit(request);
      setSuccess(
        dialog === 'create-pull-request' ? 'Pull request request recorded.' : 'Decision recorded.'
      );
      setDialog(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : 'Action failed. Refresh before retrying.'
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <aside className="fe-approval" aria-label="Recommendation decisions">
      <div className="fe-approval-title">
        <ShieldCheck size={19} />
        <h2>Review & decision</h2>
      </div>
      <Status value={record.status.phase} />
      <div className="fe-approvers">
        {record.spec.approvalsRequired.map((role) => {
          const approval = record.status.approvals.find((item) => item.role === role);
          return (
            <div key={role}>
              <span className={approval ? 'fe-check-icon' : 'fe-pending-icon'}>
                {approval ? <Check size={15} /> : <ShieldCheck size={15} />}
              </span>
              <div>
                <strong>{phaseLabel(role)}</strong>
                <small>{approval ? approval.actor : 'Approval pending'}</small>
              </div>
            </div>
          );
        })}
      </div>
      <div className="fe-small fe-muted">Reviewing as</div>
      <div className="fe-identity">{capabilities.identity}</div>
      {blockers.length > 0 && (
        <div className="fe-blockers">
          {blockers.map((blocker) => (
            <div key={blocker}>{blocker}</div>
          ))}
        </div>
      )}
      <div className="fe-action-stack">
        {actions.map(({ action, label }, index) => {
          const reasons = actionBlockers(record, action, capabilities);
          return (
            <button
              key={action}
              className={index === 0 ? 'fe-button fe-primary' : 'fe-button'}
              disabled={pending || reasons.length > 0}
              title={reasons.join('. ') || label}
              onClick={() => open(action)}
            >
              {index === 0 && <Check size={16} />}
              {label}
            </button>
          );
        })}
      </div>
      <div className="fe-pr-action">
        <div className="fe-small fe-muted">Implementation</div>
        <button
          className="fe-button"
          disabled={
            pending || actionBlockers(record, 'create-pull-request', capabilities).length > 0
          }
          title={
            actionBlockers(record, 'create-pull-request', capabilities).join('. ') ||
            'Request pull request'
          }
          onClick={() => open('create-pull-request')}
        >
          <GitPullRequest size={16} />
          Request pull request
        </button>
      </div>
      {success && <Notice>{success}</Notice>}
      {capabilities.backend === 'simulator' && <Badge tone="amber">Synthetic decisions only</Badge>}
      {dialog && (
        <div className="fe-modal-backdrop" onClick={() => !pending && setDialog(null)}>
          <div
            className="fe-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="fe-dialog-title"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === 'Escape' && !pending) setDialog(null);
              if (event.key === 'Tab') {
                const controls = Array.from(
                  event.currentTarget.querySelectorAll<HTMLElement>(
                    'button:not(:disabled), textarea, input'
                  )
                );
                const first = controls[0];
                const last = controls[controls.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                  event.preventDefault();
                  last?.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                  event.preventDefault();
                  first?.focus();
                }
              }
            }}
          >
            <div className="fe-section-heading">
              <h2 id="fe-dialog-title">
                {dialog === 'approve'
                  ? 'Approve recommendation'
                  : dialog === 'create-pull-request'
                    ? 'Request pull request'
                    : phaseLabel(dialog)}
              </h2>
              <button
                className="fe-icon-button"
                aria-label="Close dialog"
                disabled={pending}
                onClick={() => setDialog(null)}
              >
                <X size={20} />
              </button>
            </div>
            <p className="fe-muted">
              {record.spec.target.namespace} / {record.spec.target.name} /{' '}
              {record.spec.target.container}
            </p>
            <div className="fe-modal-binding">
              Generation {record.metadata.generation} · {record.spec.evidenceVersion}
            </div>
            {dialog === 'approve' && (
              <fieldset className="fe-acknowledgements">
                <legend>Confirm your review</legend>
                {acknowledgementLabels.map((label) => (
                  <label key={label}>
                    <input
                      type="checkbox"
                      checked={checked.includes(label)}
                      onChange={(event) =>
                        setChecked(
                          event.target.checked
                            ? [...checked, label]
                            : checked.filter((item) => item !== label)
                        )
                      }
                    />
                    {label}
                  </label>
                ))}
              </fieldset>
            )}
            {dialog === 'defer' && (
              <label className="fe-field">
                Defer until
                <input
                  type="datetime-local"
                  value={deferUntil}
                  onChange={(event) => setDeferUntil(event.target.value)}
                  required
                />
              </label>
            )}
            <label className="fe-field">
              Decision reason
              <textarea
                autoFocus
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="Record the rationale for this decision"
              />
            </label>
            {error && <Notice danger>{error}</Notice>}
            <div className="fe-dialog-footer">
              <button className="fe-button" disabled={pending} onClick={() => setDialog(null)}>
                Back to review
              </button>
              <button
                className="fe-button fe-primary"
                disabled={
                  pending ||
                  !reason.trim() ||
                  (dialog === 'approve' && checked.length !== acknowledgementLabels.length)
                }
                onClick={send}
              >
                {pending ? <LoaderCircle className="fe-spin" size={16} /> : <Check size={16} />}
                {pending ? 'Recording...' : 'Confirm decision'}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
