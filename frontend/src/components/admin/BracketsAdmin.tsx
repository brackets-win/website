import { useCallback, useEffect, useMemo, useState } from 'react';

import { BracketFill } from '../bracket/BracketFill';
import {
  ApiError,
  adminCreateBracket,
  adminDeleteBracket,
  adminListContestants,
  adminUpdateBracket,
  getBracket,
  listBrackets,
  type BracketStructureType,
  type BracketSummary,
  type ContestantCatalog,
} from '../../utils/api';

import { IconPencil, IconTrash } from './AdminIcons';
import { DeleteConfirmDialog } from './DeleteConfirmDialog';
import './admin-shared.css';

type AssignRow = { seed: string; contestant_id: string };

function buildAssignRows(
  count: number,
  prev: AssignRow[],
): AssignRow[] {
  const rows: AssignRow[] = [];
  for (let i = 0; i < count; i++) {
    rows.push({
      seed: String(i + 1),
      contestant_id: prev[i]?.contestant_id ?? '',
    });
  }
  return rows;
}

export function BracketsAdmin() {
  const [brackets, setBrackets] = useState<BracketSummary[]>([]);
  const [contestants, setContestants] = useState<ContestantCatalog[]>([]);
  const [loadErr, setLoadErr] = useState('');

  const [structureKind, setStructureKind] =
    useState<BracketStructureType>('SINGLE_ELIM');
  const [bIdentifier, setBIdentifier] = useState('');
  const [bName, setBName] = useState('');
  const [bDesc, setBDesc] = useState('');
  const [bN, setBN] = useState(8);
  const [bThird, setBThird] = useState(false);
  const [bRand, setBRand] = useState(false);
  const [bImage, setBImage] = useState<File | null>(null);
  const [bImagePreview, setBImagePreview] = useState<string | null>(null);
  const [assignRows, setAssignRows] = useState<AssignRow[]>(() =>
    buildAssignRows(8, []),
  );
  const [assignSearch, setAssignSearch] = useState('');
  const [createMsg, setCreateMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(
    null,
  );
  const [createBusy, setCreateBusy] = useState(false);
  const [fillMasterUbId, setFillMasterUbId] = useState<number | null>(null);
  const [fillBracketName, setFillBracketName] = useState('');
  const [editBracketId, setEditBracketId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editImage, setEditImage] = useState<File | null>(null);
  const [editImagePreview, setEditImagePreview] = useState<string | null>(null);
  const [editExistingImageUrl, setEditExistingImageUrl] = useState<string | null>(
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
      const [c, b] = await Promise.all([
        adminListContestants(),
        listBrackets(),
      ]);
      setContestants(c.contestants);
      setBrackets(b.brackets);
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
    setAssignRows((prev) => buildAssignRows(bN, prev));
  }, [bN]);

  useEffect(() => {
    if (!bImage) {
      setBImagePreview(null);
      return;
    }
    const url = URL.createObjectURL(bImage);
    setBImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [bImage]);

  useEffect(() => {
    if (!editImage) {
      setEditImagePreview(editExistingImageUrl);
      return;
    }
    const url = URL.createObjectURL(editImage);
    setEditImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [editImage, editExistingImageUrl]);

  const isSingleElim = structureKind === 'SINGLE_ELIM';

  const contestantOptions = useMemo(() => {
    const q = assignSearch.trim().toLowerCase();
    if (!q) return contestants;
    return contestants.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.identifier.toLowerCase().includes(q),
    );
  }, [contestants, assignSearch]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateMsg(null);
    const identifier = bIdentifier.trim();
    if (!identifier) {
      setCreateMsg({ type: 'err', text: 'Identifier is required.' });
      return;
    }
    if (/\s/.test(identifier)) {
      setCreateMsg({
        type: 'err',
        text: 'Identifier cannot contain spaces.',
      });
      return;
    }

    const name = bName.trim();
    if (!name) {
      setCreateMsg({ type: 'err', text: 'Display name is required.' });
      return;
    }
    if (!Number.isFinite(bN) || bN < 2) {
      setCreateMsg({ type: 'err', text: 'Number of contestants must be at least 2.' });
      return;
    }
    if (structureKind === 'GROUP_KNOCKOUT' && bN % 4 !== 0) {
      setCreateMsg({
        type: 'err',
        text: 'For group & knockout, use a multiple of 4 contestants.',
      });
      return;
    }

    const bracket_contestants: { contestant_id: number; seed: number | null }[] =
      [];
    const seen = new Set<number>();
    for (const row of assignRows) {
      const cid = row.contestant_id.trim();
      if (!cid) continue;
      const contestant_id = parseInt(cid, 10);
      if (!Number.isFinite(contestant_id)) {
        setCreateMsg({ type: 'err', text: 'Invalid contestant selection.' });
        return;
      }
      if (seen.has(contestant_id)) {
        setCreateMsg({ type: 'err', text: 'Each contestant can only appear once.' });
        return;
      }
      seen.add(contestant_id);
      const seedRaw = row.seed.trim();
      const seed = seedRaw === '' ? null : parseInt(seedRaw, 10);
      if (seedRaw !== '' && !Number.isFinite(seed)) {
        setCreateMsg({ type: 'err', text: 'Seeds must be numbers.' });
        return;
      }
      bracket_contestants.push({ contestant_id, seed });
    }

    setCreateBusy(true);
    try {
      const fd = new FormData();
      fd.append('structure', structureKind);
      fd.append('identifier', identifier);
      fd.append('name', name);
      if (bDesc.trim()) fd.append('description', bDesc.trim());
      fd.append('number_of_contestants', String(bN));
      if (isSingleElim && bThird) fd.append('has_third_place', 'true');
      if (bRand) fd.append('randomize_seeds_per_challenge', 'true');
      if (bracket_contestants.length > 0) {
        fd.append('bracket_contestants', JSON.stringify(bracket_contestants));
      }
      if (bImage) fd.append('image', bImage);
      const { bracket } = await adminCreateBracket(fd);
      setBrackets((prev) => [bracket, ...prev]);
      setBIdentifier('');
      setBName('');
      setBDesc('');
      setBImage(null);
      setCreateMsg({
        type: 'ok',
        text: `Created bracket “${bracket.name}”.`,
      });
    } catch (err) {
      setCreateMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not create bracket.',
      });
    } finally {
      setCreateBusy(false);
    }
  }

  function startBracketEdit(b: BracketSummary) {
    setEditBracketId(b.id);
    setEditName(b.name);
    setEditDesc(b.description ?? '');
    setEditImage(null);
    setEditExistingImageUrl(b.image_url ?? null);
  }

  async function saveBracketEdit(e: React.FormEvent) {
    e.preventDefault();
    if (editBracketId == null) return;
    setEditBusy(true);
    try {
      const fd = new FormData();
      fd.append('name', editName.trim());
      fd.append('description', editDesc.trim());
      if (editImage) fd.append('image', editImage);
      const { bracket } = await adminUpdateBracket(editBracketId, fd);
      setBrackets((prev) =>
        prev.map((r) =>
          r.id === bracket.id
            ? {
                ...r,
                name: bracket.name,
                description: bracket.description,
                image_url: bracket.image_url,
              }
            : r,
        ),
      );
      setEditBracketId(null);
      setEditImage(null);
      setEditExistingImageUrl(null);
    } catch (err) {
      setCreateMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not save bracket.',
      });
    } finally {
      setEditBusy(false);
    }
  }

  async function confirmDeleteBracket() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await adminDeleteBracket(deleteTarget.id);
      setBrackets((prev) => prev.filter((b) => b.id !== deleteTarget.id));
      if (editBracketId === deleteTarget.id) setEditBracketId(null);
      if (fillMasterUbId != null) {
        const gone = !brackets.some((b) => b.id === deleteTarget.id);
        if (gone) {
          setFillMasterUbId(null);
          setFillBracketName('');
        }
      }
      setDeleteTarget(null);
    } catch (err) {
      setCreateMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not delete bracket.',
      });
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  async function openMasterFill(b: BracketSummary) {
    try {
      const { bracket } = await getBracket(b.id);
      const masterId = bracket.master_user_bracket_id;
      if (masterId == null) {
        setLoadErr('No master bracket found for this tournament.');
        return;
      }
      setFillBracketName(b.name);
      setFillMasterUbId(masterId);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Could not open master bracket.',
      );
    }
  }

  return (
    <div className="admin-page">
      {loadErr ? <div className="alert alert--error">{loadErr}</div> : null}

      <section className="card">
        <header className="card__header">
          <h2>Create bracket</h2>
          <p>
            Identifier is unique and has no spaces. Display name is what players
            see. Players join via challenges on the home page.
          </p>
        </header>
        <div className="card__body">
          <form onSubmit={onCreate}>
            {createMsg ? (
              <div
                className={`alert alert--${createMsg.type === 'ok' ? 'success' : 'error'}`}
              >
                {createMsg.text}
              </div>
            ) : null}

            <div className="field">
              <label htmlFor="bracket-structure">Bracket type</label>
              <select
                id="bracket-structure"
                className="select"
                value={structureKind}
                onChange={(e) =>
                  setStructureKind(e.target.value as BracketStructureType)
                }
                disabled={createBusy}
              >
                <option value="SINGLE_ELIM">Single elimination</option>
                <option value="GROUP_KNOCKOUT">Group stage + knockout</option>
              </select>
            </div>

            <div className="field">
              <label htmlFor="bracket-identifier">Identifier</label>
              <input
                id="bracket-identifier"
                className="input"
                value={bIdentifier}
                onChange={(e) =>
                  setBIdentifier(e.target.value.replace(/\s/g, ''))
                }
                maxLength={64}
                required
                disabled={createBusy}
                placeholder="e.g. fifa-world-cup-2026"
                autoComplete="off"
                spellCheck={false}
              />
            </div>

            <div className="form-grid form-grid--2">
              <div className="field">
                <label htmlFor="bracket-name">Display name</label>
                <input
                  id="bracket-name"
                  className="input"
                  value={bName}
                  onChange={(e) => setBName(e.target.value)}
                  maxLength={100}
                  required
                  disabled={createBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="bracket-n">Number of contestants</label>
                <input
                  id="bracket-n"
                  className="input"
                  type="number"
                  min={2}
                  max={128}
                  value={bN}
                  onChange={(e) => setBN(parseInt(e.target.value, 10) || 2)}
                  disabled={createBusy}
                />
              </div>
            </div>

            <div className="field">
              <label htmlFor="bracket-desc">Description</label>
              <textarea
                id="bracket-desc"
                className="textarea"
                rows={2}
                value={bDesc}
                onChange={(e) => setBDesc(e.target.value)}
                disabled={createBusy}
              />
            </div>

            <div className="field">
              <label htmlFor="bracket-image">Image</label>
              <input
                id="bracket-image"
                className="input"
                type="file"
                accept="image/*"
                disabled={createBusy}
                onChange={(e) => setBImage(e.target.files?.[0] ?? null)}
              />
              {bImagePreview ? (
                <div className="photo-preview">
                  <img src={bImagePreview} alt="" />
                  {bImage ? (
                    <span className="photo-preview__label">{bImage.name}</span>
                  ) : null}
                </div>
              ) : null}
            </div>

            {isSingleElim ? (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={bThird}
                  onChange={(e) => setBThird(e.target.checked)}
                  disabled={createBusy}
                />
                Third-place match
              </label>
            ) : null}
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={bRand}
                onChange={(e) => setBRand(e.target.checked)}
                disabled={createBusy}
              />
              Randomize seeds for each challenge
            </label>

            <div className="assign-section">
              <div className="assign-section__head">
                <h3 className="assign-section__title">Contestants</h3>
                <input
                  type="search"
                  className="input assign-section__search"
                  placeholder="Filter catalog…"
                  value={assignSearch}
                  onChange={(e) => setAssignSearch(e.target.value)}
                  aria-label="Filter contestants"
                  disabled={createBusy}
                />
              </div>
              {contestants.length === 0 ? (
                <p className="field__hint">
                  Add contestants in the Contestants tab first.
                </p>
              ) : (
                <div className="assign-list assign-list--compact">
                  {assignRows.map((row, i) => (
                    <div key={i} className="assign-list__row">
                      <input
                        className="input"
                        type="number"
                        min={1}
                        aria-label={`Seed ${i + 1}`}
                        placeholder="Seed"
                        value={row.seed}
                        onChange={(e) => {
                          const v = e.target.value;
                          setAssignRows((rows) =>
                            rows.map((r, j) => (j === i ? { ...r, seed: v } : r)),
                          );
                        }}
                        disabled={createBusy}
                      />
                      <select
                        className="select"
                        aria-label={`Contestant ${i + 1}`}
                        value={row.contestant_id}
                        onChange={(e) => {
                          const v = e.target.value;
                          setAssignRows((rows) =>
                            rows.map((r, j) =>
                              j === i ? { ...r, contestant_id: v } : r,
                            ),
                          );
                        }}
                        disabled={createBusy}
                      >
                        <option value="">Select…</option>
                        {contestantOptions.map((c) => (
                          <option key={c.id} value={String(c.id)}>
                            {c.name} ({c.identifier})
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button
              type="submit"
              className="btn btn--primary"
              disabled={createBusy}
              style={{ marginTop: '1rem' }}
            >
              {createBusy ? 'Creating…' : 'Create bracket'}
            </button>
          </form>
        </div>
      </section>

      {fillMasterUbId != null ? (
        <section className="card">
          <header className="card__header">
            <h2>Master bracket — {fillBracketName}</h2>
            <p>Official results used for scoring after the deadline.</p>
          </header>
          <div className="card__body">
            <button
              type="button"
              className="btn btn--ghost"
              style={{ marginBottom: '1rem' }}
              onClick={() => {
                setFillMasterUbId(null);
                setFillBracketName('');
              }}
            >
              ← Back to brackets
            </button>
            <BracketFill userBracketId={fillMasterUbId} allowMasterEdit />
          </div>
        </section>
      ) : null}

      {brackets.length > 0 && fillMasterUbId == null ? (
        <section className="card">
          <header className="card__header">
            <h2>Brackets</h2>
          </header>
          <div className="card__body" style={{ paddingTop: 0 }}>
            <ul className="catalog-list">
              {brackets.map((b) => (
                <li key={b.id} className="catalog-list__row catalog-shelf__row">
                  <div className="catalog-shelf__main">
                    {b.image_url ? (
                      <img
                        className="catalog-list__avatar"
                        src={b.image_url}
                        alt=""
                      />
                    ) : (
                      <span className="catalog-list__avatar catalog-list__avatar--ph">
                        {b.name.charAt(0)}
                      </span>
                    )}
                    <span className="catalog-list__main">
                      <span className="catalog-list__name">{b.name}</span>
                      <span className="catalog-list__id">{b.identifier}</span>
                    </span>
                  </div>
                  <div className="catalog-shelf__actions">
                    <button
                      type="button"
                      className="btn-icon"
                      title="Edit"
                      aria-label={`Edit ${b.name}`}
                      onClick={() => startBracketEdit(b)}
                    >
                      <IconPencil />
                    </button>
                    <button
                      type="button"
                      className="btn-icon btn-icon--bracket"
                      title="Fill master"
                      aria-label={`Fill master bracket for ${b.name}`}
                      onClick={() => void openMasterFill(b)}
                    >
                      {'}'} {'{'}
                    </button>
                    <button
                      type="button"
                      className="btn-icon btn-icon--danger"
                      title="Delete"
                      aria-label={`Delete ${b.name}`}
                      onClick={() =>
                        setDeleteTarget({ id: b.id, label: b.name })
                      }
                    >
                      <IconTrash />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {editBracketId != null ? (
        <section className="card">
          <header className="card__header">
            <h2>Edit bracket</h2>
          </header>
          <div className="card__body">
            <form onSubmit={saveBracketEdit}>
              <div className="field">
                <label htmlFor="edit-bracket-name">Display name</label>
                <input
                  id="edit-bracket-name"
                  className="input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  required
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-bracket-desc">Description</label>
                <textarea
                  id="edit-bracket-desc"
                  className="textarea"
                  rows={2}
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-bracket-image">Image</label>
                <input
                  id="edit-bracket-image"
                  className="input"
                  type="file"
                  accept="image/*"
                  disabled={editBusy}
                  onChange={(e) => setEditImage(e.target.files?.[0] ?? null)}
                />
                {editImagePreview ? (
                  <div className="photo-preview">
                    <img src={editImagePreview} alt="" />
                    {editImage ? (
                      <span className="photo-preview__label">{editImage.name}</span>
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
                  onClick={() => setEditBracketId(null)}
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
        title="Delete bracket?"
        message={
          deleteTarget
            ? `“${deleteTarget.label}” and all related challenges will be removed.`
            : ''
        }
        busy={deleteBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDeleteBracket()}
      />
    </div>
  );
}
