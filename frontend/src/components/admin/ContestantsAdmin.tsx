import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  adminCreateContestant,
  adminDeleteContestant,
  adminListContestants,
  adminUpdateContestant,
  type ContestantCatalog,
} from '../../utils/api';

import { IconPencil, IconTrash } from './AdminIcons';
import { DeleteConfirmDialog } from './DeleteConfirmDialog';
import './admin-shared.css';

const IDENT_RE = /^[a-zA-Z0-9_-]+$/;

export function ContestantsAdmin() {
  const [rows, setRows] = useState<ContestantCatalog[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');

  const [identifier, setIdentifier] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [formMsg, setFormMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(
    null,
  );
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editPhoto, setEditPhoto] = useState<File | null>(null);
  const [editPhotoPreview, setEditPhotoPreview] = useState<string | null>(null);
  const [editExistingPhotoUrl, setEditExistingPhotoUrl] = useState<string | null>(
    null,
  );
  const [editBusy, setEditBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: number;
    label: string;
  } | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const { contestants } = await adminListContestants();
      setRows(contestants);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load contestants.',
      );
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!photo) {
      setPhotoPreview(null);
      return;
    }
    const url = URL.createObjectURL(photo);
    setPhotoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  useEffect(() => {
    if (!editPhoto) {
      setEditPhotoPreview(editExistingPhotoUrl);
      return;
    }
    const url = URL.createObjectURL(editPhoto);
    setEditPhotoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [editPhoto, editExistingPhotoUrl]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.identifier.toLowerCase().includes(q) ||
        (c.description && c.description.toLowerCase().includes(q)),
    );
  }, [rows, search]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormMsg(null);
    const ident = identifier.trim();
    const displayName = name.trim();
    if (!ident) {
      setFormMsg({ type: 'err', text: 'Identifier is required.' });
      return;
    }
    if (!IDENT_RE.test(ident)) {
      setFormMsg({
        type: 'err',
        text: 'Identifier can only use letters, numbers, underscores, and hyphens.',
      });
      return;
    }
    if (!displayName) {
      setFormMsg({ type: 'err', text: 'Display name is required.' });
      return;
    }
    setBusy(true);
    try {
      const desc = description.trim();
      const fd = new FormData();
      fd.append('identifier', ident);
      fd.append('name', displayName);
      if (desc) fd.append('description', desc);
      if (photo) fd.append('photo', photo);
      const res = await adminCreateContestant(fd);
      setRows((prev) => [res.contestant, ...prev]);
      setIdentifier('');
      setName('');
      setDescription('');
      setPhoto(null);
      setFormMsg({ type: 'ok', text: `Added ${res.contestant.name}.` });
    } catch (err) {
      setFormMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not add contestant.',
      });
    } finally {
      setBusy(false);
    }
  }

  function startEdit(c: ContestantCatalog) {
    setEditId(c.id);
    setEditName(c.name);
    setEditDesc(c.description);
    setEditPhoto(null);
    setEditExistingPhotoUrl(c.photo_url ?? null);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await adminDeleteContestant(deleteTarget.id);
      setRows((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      if (editId === deleteTarget.id) setEditId(null);
      setDeleteTarget(null);
    } catch (err) {
      setFormMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not delete contestant.',
      });
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (editId == null) return;
    setEditBusy(true);
    try {
      const fd = new FormData();
      fd.append('name', editName.trim());
      fd.append('description', editDesc.trim());
      if (editPhoto) fd.append('photo', editPhoto);
      const { contestant } = await adminUpdateContestant(editId, fd);
      setRows((prev) =>
        prev.map((r) => (r.id === contestant.id ? contestant : r)),
      );
      setEditId(null);
      setEditPhoto(null);
      setEditExistingPhotoUrl(null);
    } catch (err) {
      setFormMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not save changes.',
      });
    } finally {
      setEditBusy(false);
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page__grid admin-page__grid--split">
        <section className="card">
          <header className="card__header">
            <h2>Add contestant</h2>
            <p>
              Identifier is unique and has no spaces. Display name is what players
              see in the bracket.
            </p>
          </header>
          <div className="card__body">
            <form onSubmit={onSubmit}>
              {formMsg ? (
                <div
                  className={`alert alert--${formMsg.type === 'ok' ? 'success' : 'error'}`}
                  role="status"
                >
                  {formMsg.text}
                </div>
              ) : null}

              <div className="field">
                <label htmlFor="contestant-identifier">Identifier</label>
                <input
                  id="contestant-identifier"
                  className="input"
                  value={identifier}
                  onChange={(e) =>
                    setIdentifier(e.target.value.replace(/\s/g, ''))
                  }
                  maxLength={64}
                  required
                  disabled={busy}
                  placeholder="e.g. brazil-2026"
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>

              <div className="field">
                <label htmlFor="contestant-name">Display name</label>
                <input
                  id="contestant-name"
                  className="input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={100}
                  required
                  disabled={busy}
                />
              </div>

              <div className="field">
                <label htmlFor="contestant-desc">Description</label>
                <textarea
                  id="contestant-desc"
                  className="textarea"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  disabled={busy}
                  placeholder="Optional"
                />
              </div>

              <div className="field">
                <label htmlFor="contestant-photo">Photo</label>
                <input
                  id="contestant-photo"
                  className="input"
                  type="file"
                  accept="image/*"
                  disabled={busy}
                  onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
                />
                {photoPreview ? (
                  <div className="photo-preview">
                    <img src={photoPreview} alt="" />
                    <span className="photo-preview__label">{photo?.name}</span>
                  </div>
                ) : null}
              </div>

              <button type="submit" className="btn btn--primary" disabled={busy}>
                {busy ? 'Saving…' : 'Add contestant'}
              </button>
            </form>
          </div>
        </section>

        <section className="card catalog-card">
          <header className="card__header catalog-card__header">
            <div>
              <h2>Contestants</h2>
              <p className="catalog-card__count">
                {filtered.length === rows.length
                  ? `${rows.length} in catalog`
                  : `${filtered.length} of ${rows.length}`}
              </p>
            </div>
            <input
              type="search"
              className="input catalog-card__search"
              placeholder="Search…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search contestants"
            />
          </header>
          <div className="card__body catalog-card__body">
            {loadErr ? (
              <div className="alert alert--error">{loadErr}</div>
            ) : null}
            {filtered.length === 0 && !loadErr ? (
              <p className="empty-state empty-state--compact">
                <strong>
                  {rows.length === 0 ? 'No contestants yet' : 'No matches'}
                </strong>
                {rows.length === 0
                  ? 'Add your first contestant using the form.'
                  : 'Try a different search.'}
              </p>
            ) : (
              <ul className="catalog-list">
                {filtered.map((c) => (
                  <li key={c.id} className="catalog-list__row catalog-shelf__row">
                    <div className="catalog-shelf__main">
                      {c.photo_url ? (
                        <img className="catalog-list__avatar" src={c.photo_url} alt="" />
                      ) : (
                        <span className="catalog-list__avatar catalog-list__avatar--ph">
                          {c.name.charAt(0)}
                        </span>
                      )}
                      <span className="catalog-list__main">
                        <span className="catalog-list__name">{c.name}</span>
                        <span className="catalog-list__id">{c.identifier}</span>
                      </span>
                      {c.description ? (
                        <span className="catalog-list__desc">{c.description}</span>
                      ) : null}
                    </div>
                    <div className="catalog-shelf__actions">
                      <button
                        type="button"
                        className="btn-icon"
                        title="Edit"
                        aria-label={`Edit ${c.name}`}
                        onClick={() => startEdit(c)}
                      >
                        <IconPencil />
                      </button>
                      <button
                        type="button"
                        className="btn-icon btn-icon--danger"
                        title="Delete"
                        aria-label={`Delete ${c.name}`}
                        onClick={() =>
                          setDeleteTarget({ id: c.id, label: c.name })
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
        </section>
      </div>

      {editId != null ? (
        <section className="card" style={{ marginTop: '1rem' }}>
          <header className="card__header">
            <h2>Edit contestant</h2>
          </header>
          <div className="card__body">
            <form onSubmit={saveEdit}>
              <div className="field">
                <label htmlFor="edit-name">Display name</label>
                <input
                  id="edit-name"
                  className="input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  required
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-desc">Description</label>
                <textarea
                  id="edit-desc"
                  className="textarea"
                  rows={2}
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-photo">Photo</label>
                <input
                  id="edit-photo"
                  className="input"
                  type="file"
                  accept="image/*"
                  disabled={editBusy}
                  onChange={(e) => setEditPhoto(e.target.files?.[0] ?? null)}
                />
                {editPhotoPreview ? (
                  <div className="photo-preview">
                    <img src={editPhotoPreview} alt="" />
                    {editPhoto ? (
                      <span className="photo-preview__label">{editPhoto.name}</span>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button type="submit" className="btn btn--primary" disabled={editBusy}>
                  {editBusy ? 'Saving…' : 'Save'}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setEditId(null)}
                  disabled={editBusy}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </section>
      ) : null}

      <DeleteConfirmDialog
        open={deleteTarget != null}
        title="Delete contestant?"
        message={
          deleteTarget
            ? `“${deleteTarget.label}” will be removed from the catalog.`
            : ''
        }
        busy={deleteBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
