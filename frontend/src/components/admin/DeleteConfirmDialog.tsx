import { useEffect, useState } from 'react';

import type { DeleteImpactRecord } from '../../utils/api';

import './admin-shared.css';

type Props = {
  open: boolean;
  title: string;
  label: string;
  relatedRecords?: DeleteImpactRecord[];
  loadingRelated?: boolean;
  busy?: boolean;
  intro?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function DeleteConfirmDialog({
  open,
  title,
  label,
  relatedRecords = [],
  loadingRelated = false,
  busy = false,
  intro,
  onConfirm,
  onCancel,
}: Props) {
  const [typed, setTyped] = useState('');

  useEffect(() => {
    if (!open) setTyped('');
  }, [open]);

  if (!open) return null;

  const canConfirm = typed === 'delete' && !busy && !loadingRelated;
  const related = relatedRecords.filter((r) => r.count > 0);
  const lead =
    intro ?? `“${label}” will be permanently removed.`;

  return (
    <div
      className="delete-dialog-backdrop"
      role="presentation"
      onClick={busy ? undefined : onCancel}
    >
      <div
        className="delete-dialog card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="delete-dialog-title" className="delete-dialog__title">
          {title}
        </h2>
        <div className="delete-dialog__message">
          <p>{lead}</p>
          {loadingRelated ? (
            <p className="delete-dialog__related-loading">
              Counting related records…
            </p>
          ) : related.length > 0 ? (
            <>
              <p className="delete-dialog__related-lead">
                This will also delete:
              </p>
              <ul className="delete-dialog__related">
                {related.map((row) => (
                  <li key={row.label}>
                    <strong>{row.count}</strong> {row.label}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
        <div className="field">
          <label htmlFor="delete-confirm-input">
            Type <strong>delete</strong> to confirm
          </label>
          <input
            id="delete-confirm-input"
            className="input"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            disabled={busy || loadingRelated}
            autoFocus
          />
        </div>
        <div className="delete-dialog__actions">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={onConfirm}
            disabled={!canConfirm}
          >
            {busy ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}
