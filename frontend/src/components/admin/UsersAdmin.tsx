import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  adminDeleteUser,
  adminListUsers,
  adminResetUserPassword,
  type AdminUserRow,
} from '../../utils/api';

import { AdminCatalogToolbar } from './AdminCatalogToolbar';
import { IconTrash, IconUnlock } from './AdminIcons';
import { DeleteConfirmDialog } from './DeleteConfirmDialog';
import {
  startDeleteTarget,
  type AdminDeleteTarget,
} from './deleteDialogHelpers';
import './admin-shared.css';

type ResetTarget = {
  id: number;
  label: string;
};

type TempPasswordResult = {
  username: string;
  tempPassword: string;
};

function formatJoined(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function UsersAdmin() {
  const [rows, setRows] = useState<AdminUserRow[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [pageMsg, setPageMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(
    null,
  );
  const [search, setSearch] = useState('');

  const [deleteTarget, setDeleteTarget] = useState<AdminDeleteTarget | null>(
    null,
  );
  const [deleteBusy, setDeleteBusy] = useState(false);

  const [resetTarget, setResetTarget] = useState<ResetTarget | null>(null);
  const [resetBusy, setResetBusy] = useState(false);
  const [tempPasswordResult, setTempPasswordResult] =
    useState<TempPasswordResult | null>(null);

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const data = await adminListUsers();
      setRows(data.users);
    } catch (e) {
      setLoadErr(e instanceof ApiError ? e.message : 'Unable to load users.');
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((u) => u.username.toLowerCase().includes(q));
  }, [rows, search]);

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setPageMsg(null);
    try {
      await adminDeleteUser(deleteTarget.id);
      setDeleteTarget(null);
      setPageMsg({ type: 'ok', text: 'User deleted.' });
      await reload();
    } catch (e) {
      setPageMsg({
        type: 'err',
        text: e instanceof ApiError ? e.message : 'Delete failed.',
      });
    } finally {
      setDeleteBusy(false);
    }
  }

  async function confirmReset() {
    if (!resetTarget) return;
    setResetBusy(true);
    setPageMsg(null);
    try {
      const { temp_password } = await adminResetUserPassword(resetTarget.id);
      setResetTarget(null);
      setTempPasswordResult({
        username: resetTarget.label,
        tempPassword: temp_password,
      });
      await reload();
    } catch (e) {
      setPageMsg({
        type: 'err',
        text: e instanceof ApiError ? e.message : 'Password reset failed.',
      });
    } finally {
      setResetBusy(false);
    }
  }

  async function copyTempPassword() {
    if (!tempPasswordResult) return;
    try {
      await navigator.clipboard.writeText(tempPasswordResult.tempPassword);
      setPageMsg({ type: 'ok', text: 'Temporary password copied.' });
    } catch {
      setPageMsg({ type: 'err', text: 'Could not copy to clipboard.' });
    }
  }

  return (
    <section className="admin-page">
      <div className="card catalog-card">
        <AdminCatalogToolbar
          title="Users"
          countLabel={
            filtered.length === rows.length
              ? `${rows.length} account${rows.length === 1 ? '' : 's'}`
              : `${filtered.length} of ${rows.length} accounts`
          }
          search={search}
          onSearchChange={setSearch}
          searchLabel="Search users"
        />

        <div className="card__body catalog-card__body">
          {pageMsg ? (
            <div
              className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
              role="status"
            >
              {pageMsg.text}
            </div>
          ) : null}
          {loadErr ? <div className="alert alert--error">{loadErr}</div> : null}
          {filtered.length === 0 && !loadErr ? (
            <p className="empty-state empty-state--compact">
              <strong>{rows.length === 0 ? 'No users yet' : 'No matches'}</strong>
              {rows.length === 0
                ? 'Accounts appear here after people sign up.'
                : 'Try a different search.'}
            </p>
          ) : (
            <ul className="catalog-list">
              {filtered.map((u) => (
                <li key={u.id} className="catalog-list__row catalog-shelf__row">
                  <div className="catalog-shelf__main">
                    <span className="catalog-list__avatar catalog-list__avatar--ph">
                      {u.username.charAt(0).toUpperCase()}
                    </span>
                    <span className="catalog-list__main">
                      <span className="catalog-list__name">{u.username}</span>
                      <span className="catalog-list__id">
                        {u.is_staff ? 'Admin' : 'Member'}
                        {u.must_change_password ? ' · Must change password' : ''}
                        {u.date_joined ? ` · Joined ${formatJoined(u.date_joined)}` : ''}
                      </span>
                    </span>
                  </div>
                  <div className="catalog-shelf__actions">
                    <button
                      type="button"
                      className="btn-icon btn-icon--unlock"
                      title="Reset Password"
                      aria-label={`Reset password for ${u.username}`}
                      onClick={() =>
                        setResetTarget({ id: u.id, label: u.username })
                      }
                    >
                      <IconUnlock />
                    </button>
                    <button
                      type="button"
                      className="btn-icon btn-icon--danger"
                      title="Delete"
                      aria-label={`Delete ${u.username}`}
                      onClick={() =>
                        startDeleteTarget('user', u.id, u.username, setDeleteTarget)
                      }
                    >
                      <IconTrash />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <DeleteConfirmDialog
        open={deleteTarget != null}
        title="Delete User?"
        label={deleteTarget?.label ?? ''}
        intro={`“${deleteTarget?.label ?? ''}” and their related picks, entries, and created content will be permanently removed.`}
        relatedRecords={deleteTarget?.relatedRecords}
        loadingRelated={deleteTarget?.loadingRelated}
        busy={deleteBusy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      />

      <DeleteConfirmDialog
        open={resetTarget != null}
        title="Reset Password?"
        label={resetTarget?.label ?? ''}
        intro={`A temporary password will be generated for “${resetTarget?.label ?? ''}”. They must choose a new password at next sign-in.`}
        confirmWord="reset"
        confirmLabel="Reset Password"
        busyLabel="Resetting…"
        confirmButtonClass="btn--primary"
        busy={resetBusy}
        onConfirm={() => void confirmReset()}
        onCancel={() => setResetTarget(null)}
      />

      {tempPasswordResult ? (
        <div
          className="delete-dialog-backdrop"
          role="presentation"
          onClick={() => setTempPasswordResult(null)}
        >
          <div
            className="delete-dialog card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="temp-password-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="temp-password-title" className="delete-dialog__title">
              Temporary Password
            </h2>
            <div className="delete-dialog__message">
              <p>
                Share this password with <strong>{tempPasswordResult.username}</strong>{' '}
                privately. They will be asked to set a new password after signing in.
              </p>
              <p className="users-admin__temp-password">
                <code>{tempPasswordResult.tempPassword}</code>
              </p>
            </div>
            <div className="delete-dialog__actions">
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setTempPasswordResult(null)}
              >
                Close
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void copyTempPassword()}
              >
                Copy Password
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
