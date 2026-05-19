import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  adminCreateContestant,
  adminDeleteContestant,
  adminListContestants,
  adminUpdateContestant,
  type ContestantCatalog,
  type ContestantTagInfo,
} from '../../utils/api';

import { AdminBackBar } from './AdminBackBar';
import { AdminCatalogToolbar } from './AdminCatalogToolbar';
import { ContestantFormFields } from './ContestantFormFields';
import { IconPencil, IconTrash } from './AdminIcons';
import { DeleteConfirmDialog } from './DeleteConfirmDialog';
import { metadataToText, parseMetadataJson } from './bracketAdminHelpers';
import './admin-shared.css';

const IDENT_RE = /^[a-zA-Z0-9_-]+$/;

type View = 'list' | 'create' | 'edit';

function appendContestantExtras(
  fd: FormData,
  opts: {
    imageUrl: string;
    metadata: string;
    selectedTagIds: number[];
    newTagNames: string;
  },
) {
  fd.append('image_url', opts.imageUrl.trim());
  fd.append('metadata', opts.metadata.trim() || 'null');
  fd.append('tag_ids', JSON.stringify(opts.selectedTagIds));
  if (opts.newTagNames.trim()) {
    fd.append('tag_names', opts.newTagNames.trim());
  }
}

export function ContestantsAdmin() {
  const [view, setView] = useState<View>('list');
  const [rows, setRows] = useState<ContestantCatalog[]>([]);
  const [allTags, setAllTags] = useState<ContestantTagInfo[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [pageMsg, setPageMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(
    null,
  );
  const [search, setSearch] = useState('');

  const [identifier, setIdentifier] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [metadata, setMetadata] = useState('');
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);
  const [newTagNames, setNewTagNames] = useState('');
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [photoInputKey, setPhotoInputKey] = useState(0);

  const [editId, setEditId] = useState<number | null>(null);
  const [editIdentifier, setEditIdentifier] = useState('');
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editImageUrl, setEditImageUrl] = useState('');
  const [editMetadata, setEditMetadata] = useState('');
  const [editTagIds, setEditTagIds] = useState<number[]>([]);
  const [editNewTagNames, setEditNewTagNames] = useState('');
  const [editPhoto, setEditPhoto] = useState<File | null>(null);
  const [editPhotoPreview, setEditPhotoPreview] = useState<string | null>(null);
  const [editExistingPhotoUrl, setEditExistingPhotoUrl] = useState<string | null>(
    null,
  );
  const [editBusy, setEditBusy] = useState(false);
  const [editPhotoInputKey, setEditPhotoInputKey] = useState(0);

  const [deleteTarget, setDeleteTarget] = useState<{
    id: number;
    label: string;
  } | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const data = await adminListContestants();
      setRows(data.contestants);
      setAllTags(data.tags);
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
        (c.description && c.description.toLowerCase().includes(q)) ||
        c.tags.some((t) => t.name.toLowerCase().includes(q)),
    );
  }, [rows, search]);

  function resetFormFields() {
    setIdentifier('');
    setName('');
    setDescription('');
    setImageUrl('');
    setMetadata('');
    setSelectedTagIds([]);
    setNewTagNames('');
    setPhoto(null);
  }

  function goList() {
    setView('list');
    setEditId(null);
    setEditPhoto(null);
  }

  function openCreate() {
    setPageMsg(null);
    resetFormFields();
    setPhotoInputKey((k) => k + 1);
    setView('create');
  }

  function openEdit(c: ContestantCatalog) {
    setPageMsg(null);
    setEditId(c.id);
    setEditIdentifier(c.identifier);
    setEditName(c.name);
    setEditDesc(c.description ?? '');
    setEditImageUrl(c.image_url ?? '');
    setEditMetadata(metadataToText(c.metadata));
    setEditTagIds(c.tags.map((t) => t.id));
    setEditNewTagNames('');
    setEditPhoto(null);
    setEditExistingPhotoUrl(c.photo_url ?? null);
    setEditPhotoInputKey((k) => k + 1);
    setView('edit');
  }

  function toggleTag(id: number, edit: boolean) {
    const setter = edit ? setEditTagIds : setSelectedTagIds;
    setter((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  async function onCreateSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPageMsg(null);
    const ident = identifier.trim();
    const displayName = name.trim();
    if (!ident) {
      setPageMsg({ type: 'err', text: 'Identifier is required.' });
      return;
    }
    if (!IDENT_RE.test(ident)) {
      setPageMsg({
        type: 'err',
        text: 'Identifier can only use letters, numbers, underscores, and hyphens.',
      });
      return;
    }
    if (!displayName) {
      setPageMsg({ type: 'err', text: 'Display name is required.' });
      return;
    }
    try {
      parseMetadataJson(metadata);
    } catch {
      setPageMsg({ type: 'err', text: 'Metadata must be valid JSON.' });
      return;
    }
    setCreateBusy(true);
    try {
      const fd = new FormData();
      fd.append('identifier', ident);
      fd.append('name', displayName);
      fd.append('description', description.trim());
      if (photo) fd.append('photo', photo);
      appendContestantExtras(fd, {
        imageUrl,
        metadata,
        selectedTagIds,
        newTagNames,
      });
      const res = await adminCreateContestant(fd);
      setRows((prev) => [res.contestant, ...prev]);
      if (res.contestant.tags.length) {
        const merged = new Map(allTags.map((t) => [t.id, t]));
        for (const t of res.contestant.tags) merged.set(t.id, t);
        setAllTags([...merged.values()].sort((a, b) => a.name.localeCompare(b.name)));
      }
      goList();
      setPageMsg({ type: 'ok', text: `Added ${res.contestant.name}.` });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not add contestant.',
      });
    } finally {
      setCreateBusy(false);
    }
  }

  async function onEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editId == null) return;
    try {
      parseMetadataJson(editMetadata);
    } catch {
      setPageMsg({ type: 'err', text: 'Metadata must be valid JSON.' });
      return;
    }
    setEditBusy(true);
    setPageMsg(null);
    try {
      const fd = new FormData();
      fd.append('name', editName.trim());
      fd.append('description', editDesc.trim());
      if (editPhoto) fd.append('photo', editPhoto);
      appendContestantExtras(fd, {
        imageUrl: editImageUrl,
        metadata: editMetadata,
        selectedTagIds: editTagIds,
        newTagNames: editNewTagNames,
      });
      const { contestant } = await adminUpdateContestant(editId, fd);
      setRows((prev) =>
        prev.map((r) => (r.id === contestant.id ? contestant : r)),
      );
      const merged = new Map(allTags.map((t) => [t.id, t]));
      for (const t of contestant.tags) merged.set(t.id, t);
      setAllTags([...merged.values()].sort((a, b) => a.name.localeCompare(b.name)));
      goList();
      setPageMsg({ type: 'ok', text: `Saved ${contestant.name}.` });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not save changes.',
      });
    } finally {
      setEditBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await adminDeleteContestant(deleteTarget.id);
      setRows((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      if (editId === deleteTarget.id) goList();
      setDeleteTarget(null);
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not delete contestant.',
      });
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  if (view === 'create') {
    return (
      <div className="admin-page">
        <AdminBackBar label="Contestants" onBack={goList} />
        <section className="card">
          <header className="card__header">
            <h2>Create Contestant</h2>
          </header>
          <div className="card__body">
            <form onSubmit={onCreateSubmit}>
              {pageMsg ? (
                <div
                  className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                  role="status"
                >
                  {pageMsg.text}
                </div>
              ) : null}
              <ContestantFormFields
                showIdentifier
                identifier={identifier}
                onIdentifierChange={setIdentifier}
                name={name}
                onNameChange={setName}
                description={description}
                onDescriptionChange={setDescription}
                imageUrl={imageUrl}
                onImageUrlChange={setImageUrl}
                metadata={metadata}
                onMetadataChange={setMetadata}
                selectedTagIds={selectedTagIds}
                onToggleTag={(id) => toggleTag(id, false)}
                newTagNames={newTagNames}
                onNewTagNamesChange={setNewTagNames}
                allTags={allTags}
                photoInputKey={photoInputKey}
                onPhotoChange={setPhoto}
                photoPreview={photoPreview}
                photoName={photo?.name}
                disabled={createBusy}
              />
              <button type="submit" className="btn btn--primary" disabled={createBusy}>
                {createBusy ? 'Creating…' : 'Create Contestant'}
              </button>
            </form>
          </div>
        </section>
      </div>
    );
  }

  if (view === 'edit' && editId != null) {
    return (
      <div className="admin-page">
        <AdminBackBar label="Contestants" onBack={goList} />
        <section className="card">
          <header className="card__header">
            <h2>Edit Contestant</h2>
          </header>
          <div className="card__body">
            <form onSubmit={onEditSubmit}>
              {pageMsg ? (
                <div
                  className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                  role="status"
                >
                  {pageMsg.text}
                </div>
              ) : null}
              <ContestantFormFields
                showIdentifier
                identifierReadOnly
                identifier={editIdentifier}
                name={editName}
                onNameChange={setEditName}
                description={editDesc}
                onDescriptionChange={setEditDesc}
                imageUrl={editImageUrl}
                onImageUrlChange={setEditImageUrl}
                metadata={editMetadata}
                onMetadataChange={setEditMetadata}
                selectedTagIds={editTagIds}
                onToggleTag={(id) => toggleTag(id, true)}
                newTagNames={editNewTagNames}
                onNewTagNamesChange={setEditNewTagNames}
                allTags={allTags}
                photoInputKey={editPhotoInputKey}
                onPhotoChange={setEditPhoto}
                photoPreview={editPhotoPreview}
                photoName={editPhoto?.name}
                existingPhotoUrl={editExistingPhotoUrl}
                disabled={editBusy}
              />
              <button type="submit" className="btn btn--primary" disabled={editBusy}>
                {editBusy ? 'Saving…' : 'Save Changes'}
              </button>
            </form>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <section className="card catalog-card">
        <AdminCatalogToolbar
          title="Contestants"
          countLabel={
            filtered.length === rows.length
              ? `${rows.length} in catalog`
              : `${filtered.length} of ${rows.length} in catalog`
          }
          search={search}
          onSearchChange={setSearch}
          searchLabel="Search contestants"
          createLabel="Create Contestant"
          onCreate={openCreate}
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
              <strong>
                {rows.length === 0 ? 'No contestants yet' : 'No matches'}
              </strong>
              {rows.length === 0
                ? 'Create your first contestant to use in brackets.'
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
                      {c.tags.length > 0 ? (
                        <span className="tag-list">
                          {c.tags.map((t) => (
                            <span key={t.id} className="tag-list__pill">
                              {t.name}
                            </span>
                          ))}
                        </span>
                      ) : null}
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
                      onClick={() => openEdit(c)}
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
