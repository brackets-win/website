import { useEffect, useState } from 'react';

import './admin-shared.css';

type Props = {
  open: boolean;
  title: string;
  message: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function DeleteConfirmDialog({
  open,
  title,
  message,
  busy = false,
  onCancel,
  onConfirm,
}: Props) {
  const [typed, setTyped] = useState('');

  useEffect(() => {
    if (!open) setTyped('');
  }, [open]);

  if (!open) return null;

  const canConfirm = typed === 'delete' && !busy;

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
        <p className="delete-dialog__message">{message}</p>
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
            disabled={busy}
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
