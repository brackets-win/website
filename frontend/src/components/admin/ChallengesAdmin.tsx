import { useCallback, useEffect, useMemo, useState } from 'react';

import { BracketFill } from '../bracket/BracketFill';
import {
  ApiError,
  adminCreateChallenge,
  adminCreateChallengeEntry,
  adminDeleteChallenge,
  adminListChallengeEntries,
  adminListChallenges,
  adminListUsers,
  adminUpdateChallenge,
  adminUpdateChallengeEntry,
  listBrackets,
  type AdminChallengeEntry,
  type AdminChallengeRow,
  type AdminUserRow,
  type BracketSummary,
} from '../../utils/api';
import {
  estLocalInputToIso,
  formatDeadlineEst,
  isoToEstLocalInput,
} from '../../utils/est';

import { AdminBackBar } from './AdminBackBar';
import { AdminCatalogToolbar } from './AdminCatalogToolbar';
import { IconPencil, IconTrash, IconUser } from './AdminIcons';
import { DeleteConfirmDialog } from './DeleteConfirmDialog';
import {
  startDeleteTarget,
  type AdminDeleteTarget,
} from './deleteDialogHelpers';
import './admin-shared.css';

type View =
  | 'list'
  | 'create'
  | 'edit'
  | 'entries'
  | 'add-entry'
  | 'rename-entry'
  | 'fill';

export function ChallengesAdmin() {
  const [view, setView] = useState<View>('list');
  const [rows, setRows] = useState<AdminChallengeRow[]>([]);
  const [brackets, setBrackets] = useState<BracketSummary[]>([]);
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [pageMsg, setPageMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(
    null,
  );
  const [search, setSearch] = useState('');

  const [createName, setCreateName] = useState('');
  const [createBracketId, setCreateBracketId] = useState<number | ''>('');
  const [createDeadline, setCreateDeadline] = useState('');
  const [createMaxEntries, setCreateMaxEntries] = useState('1');
  const [createPrivate, setCreatePrivate] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);

  const [editRow, setEditRow] = useState<AdminChallengeRow | null>(null);
  const [editName, setEditName] = useState('');
  const [editDeadline, setEditDeadline] = useState('');
  const [editMaxEntries, setEditMaxEntries] = useState('1');
  const [editPrivate, setEditPrivate] = useState(false);
  const [editBusy, setEditBusy] = useState(false);

  const [entriesChallenge, setEntriesChallenge] =
    useState<AdminChallengeRow | null>(null);
  const [entries, setEntries] = useState<AdminChallengeEntry[]>([]);
  const [entriesBusy, setEntriesBusy] = useState(false);
  const [entriesSearch, setEntriesSearch] = useState('');

  const [addUserId, setAddUserId] = useState<number | ''>('');
  const [addUserSearch, setAddUserSearch] = useState('');
  const [addDisplayName, setAddDisplayName] = useState('');
  const [addBusy, setAddBusy] = useState(false);

  const [renameEntry, setRenameEntry] = useState<AdminChallengeEntry | null>(
    null,
  );
  const [renameName, setRenameName] = useState('');
  const [renameBusy, setRenameBusy] = useState(false);

  const [fillUbId, setFillUbId] = useState<number | null>(null);
  const [fillTitle, setFillTitle] = useState('');
  const [fillSubmitted, setFillSubmitted] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<AdminDeleteTarget | null>(
    null,
  );
  const [deleteBusy, setDeleteBusy] = useState(false);

  const reloadList = useCallback(async () => {
    setLoadErr('');
    try {
      const { challenges } = await adminListChallenges();
      setRows(challenges);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load challenges.',
      );
    }
  }, []);

  const reloadEntries = useCallback(async (challengeId: number) => {
    setEntriesBusy(true);
    try {
      const { entries: list } = await adminListChallengeEntries(challengeId);
      setEntries(list);
    } catch (e) {
      setPageMsg({
        type: 'err',
        text: e instanceof ApiError ? e.message : 'Unable to load entries.',
      });
    } finally {
      setEntriesBusy(false);
    }
  }, []);

  useEffect(() => {
    void reloadList();
  }, [reloadList]);

  useEffect(() => {
    if (view !== 'create') return;
    void listBrackets()
      .then(({ brackets: list }) => {
        setBrackets(list);
        setCreateBracketId((prev) => prev || list[0]?.id || '');
      })
      .catch(() => {
        setBrackets([]);
      });
  }, [view]);

  useEffect(() => {
    if (view !== 'add-entry') return;
    void adminListUsers()
      .then(({ users: list }) => setUsers(list))
      .catch(() => setUsers([]));
  }, [view]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.bracket_name.toLowerCase().includes(q) ||
        r.created_by_username.toLowerCase().includes(q),
    );
  }, [rows, search]);

  const filteredEntries = useMemo(() => {
    const q = entriesSearch.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) =>
        e.display_name.toLowerCase().includes(q) ||
        e.username.toLowerCase().includes(q),
    );
  }, [entries, entriesSearch]);

  const filteredUsers = useMemo(() => {
    const q = addUserSearch.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) => u.username.toLowerCase().includes(q));
  }, [users, addUserSearch]);

  function goList() {
    setView('list');
    setEditRow(null);
    setEntriesChallenge(null);
    setEntries([]);
    setFillUbId(null);
    setRenameEntry(null);
    setPageMsg(null);
  }

  function goEntries() {
    if (!entriesChallenge) {
      goList();
      return;
    }
    setView('entries');
    setFillUbId(null);
    setRenameEntry(null);
    setPageMsg(null);
    void reloadEntries(entriesChallenge.id);
  }

  function openCreate() {
    setCreateName('');
    setCreateDeadline('');
    setCreateMaxEntries('1');
    setCreatePrivate(false);
    setCreateBracketId(brackets[0]?.id ?? '');
    setView('create');
    setPageMsg(null);
  }

  function openEdit(row: AdminChallengeRow) {
    if (row.instance_type !== 'CHALLENGE') {
      setPageMsg({
        type: 'err',
        text: 'Only bracket challenges can be edited here.',
      });
      return;
    }
    setEditRow(row);
    setEditName(row.name);
    setEditDeadline(
      row.submission_deadline
        ? isoToEstLocalInput(row.submission_deadline)
        : '',
    );
    setEditMaxEntries(String(row.max_entries));
    setEditPrivate(row.is_private);
    setView('edit');
    setPageMsg(null);
  }

  function openEntries(row: AdminChallengeRow) {
    if (!row.needs_user_bracket) {
      setPageMsg({
        type: 'err',
        text: 'This activity does not support bracket entries.',
      });
      return;
    }
    setEntriesChallenge(row);
    setEntriesSearch('');
    setView('entries');
    setPageMsg(null);
    void reloadEntries(row.id);
  }

  function openAddEntry() {
    setAddUserId('');
    setAddUserSearch('');
    setAddDisplayName('');
    setView('add-entry');
    setPageMsg(null);
  }

  function openRename(entry: AdminChallengeEntry) {
    setRenameEntry(entry);
    setRenameName(entry.display_name);
    setView('rename-entry');
    setPageMsg(null);
  }

  function openFill(entry: AdminChallengeEntry) {
    if (!entriesChallenge) return;
    setFillUbId(entry.user_bracket_id);
    setFillTitle(
      `${entriesChallenge.name} — ${entry.display_name || entry.username}`,
    );
    setFillSubmitted(entry.is_submitted);
    setView('fill');
    setPageMsg(null);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = createName.trim();
    if (!name) return;
    if (createBracketId === '' || !Number.isFinite(createBracketId)) {
      setPageMsg({ type: 'err', text: 'Choose a bracket.' });
      return;
    }
    const deadlineIso = estLocalInputToIso(createDeadline);
    if (createDeadline.trim() && !deadlineIso) {
      setPageMsg({ type: 'err', text: 'Invalid submission deadline.' });
      return;
    }
    setCreateBusy(true);
    setPageMsg(null);
    try {
      const { challenge } = await adminCreateChallenge({
        name,
        bracket_id: createBracketId,
        submission_deadline: deadlineIso ?? null,
        max_entries: Math.max(1, parseInt(createMaxEntries, 10) || 1),
        is_private: createPrivate,
      });
      await reloadList();
      setView('list');
      setPageMsg({ type: 'ok', text: `Created “${challenge.name}”.` });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not create.',
      });
    } finally {
      setCreateBusy(false);
    }
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editRow) return;
    const name = editName.trim();
    if (!name) return;
    const deadlineIso = estLocalInputToIso(editDeadline);
    if (editDeadline.trim() && !deadlineIso) {
      setPageMsg({ type: 'err', text: 'Invalid submission deadline.' });
      return;
    }
    setEditBusy(true);
    setPageMsg(null);
    try {
      const { challenge } = await adminUpdateChallenge(editRow.id, {
        name,
        submission_deadline: editDeadline.trim() ? deadlineIso : null,
        max_entries: Math.max(1, parseInt(editMaxEntries, 10) || 1),
        is_private: editPrivate,
      });
      await reloadList();
      setView('list');
      setPageMsg({ type: 'ok', text: `Saved “${challenge.name}”.` });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not save.',
      });
    } finally {
      setEditBusy(false);
    }
  }

  async function handleAddEntry(e: React.FormEvent) {
    e.preventDefault();
    if (!entriesChallenge) return;
    if (addUserId === '' || !Number.isFinite(addUserId)) {
      setPageMsg({ type: 'err', text: 'Choose a user.' });
      return;
    }
    setAddBusy(true);
    setPageMsg(null);
    try {
      await adminCreateChallengeEntry(entriesChallenge.id, {
        user_id: addUserId,
        display_name: addDisplayName.trim() || undefined,
      });
      await reloadEntries(entriesChallenge.id);
      await reloadList();
      setView('entries');
      setPageMsg({ type: 'ok', text: 'Entry added to challenge.' });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not add entry.',
      });
    } finally {
      setAddBusy(false);
    }
  }

  async function handleRename(e: React.FormEvent) {
    e.preventDefault();
    if (!entriesChallenge || !renameEntry) return;
    const name = renameName.trim();
    if (!name) {
      setPageMsg({ type: 'err', text: 'Display name is required.' });
      return;
    }
    setRenameBusy(true);
    setPageMsg(null);
    try {
      await adminUpdateChallengeEntry(
        entriesChallenge.id,
        renameEntry.user_bracket_id,
        { display_name: name },
      );
      await reloadEntries(entriesChallenge.id);
      setView('entries');
      setRenameEntry(null);
      setPageMsg({ type: 'ok', text: 'Entry name updated.' });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not rename.',
      });
    } finally {
      setRenameBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setPageMsg(null);
    try {
      await adminDeleteChallenge(deleteTarget.id);
      setDeleteTarget(null);
      setPageMsg({ type: 'ok', text: 'Challenge deleted.' });
      await reloadList();
    } catch (e) {
      setPageMsg({
        type: 'err',
        text: e instanceof ApiError ? e.message : 'Delete failed.',
      });
    } finally {
      setDeleteBusy(false);
    }
  }

  if (view === 'create') {
    return (
      <div className="admin-page">
        <AdminBackBar label="Challenges" onBack={goList} />
        <section className="card">
          <header className="card__header">
            <h2>Create Challenge</h2>
          </header>
          <div className="card__body">
            <form onSubmit={(e) => void handleCreate(e)}>
              {pageMsg ? (
                <div
                  className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                >
                  {pageMsg.text}
                </div>
              ) : null}
              <div className="field">
                <label htmlFor="admin-ch-name">Challenge name</label>
                <input
                  id="admin-ch-name"
                  className="input"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  required
                  disabled={createBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="admin-ch-bracket">Bracket</label>
                <select
                  id="admin-ch-bracket"
                  className="select"
                  value={createBracketId === '' ? '' : String(createBracketId)}
                  onChange={(e) =>
                    setCreateBracketId(
                      e.target.value ? parseInt(e.target.value, 10) : '',
                    )
                  }
                  required
                  disabled={createBusy || brackets.length === 0}
                >
                  {brackets.length === 0 ? (
                    <option value="">No brackets available</option>
                  ) : (
                    brackets.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))
                  )}
                </select>
              </div>
              <div className="field">
                <label htmlFor="admin-ch-deadline">
                  Submission deadline (US Eastern)
                </label>
                <input
                  id="admin-ch-deadline"
                  className="input"
                  type="datetime-local"
                  value={createDeadline}
                  onChange={(e) => setCreateDeadline(e.target.value)}
                  disabled={createBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="admin-ch-max">Entries per person</label>
                <input
                  id="admin-ch-max"
                  className="input"
                  type="number"
                  min={1}
                  max={50}
                  value={createMaxEntries}
                  onChange={(e) => setCreateMaxEntries(e.target.value)}
                  disabled={createBusy}
                />
              </div>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={createPrivate}
                  onChange={(e) => setCreatePrivate(e.target.checked)}
                  disabled={createBusy}
                />
                Private (join code)
              </label>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={createBusy || brackets.length === 0}
                style={{ marginTop: '1rem' }}
              >
                {createBusy ? 'Creating…' : 'Create Challenge'}
              </button>
            </form>
          </div>
        </section>
      </div>
    );
  }

  if (view === 'edit' && editRow) {
    const minEntries = editRow.max_entries_minimum ?? 1;
    return (
      <div className="admin-page">
        <AdminBackBar label="Challenges" onBack={goList} />
        <section className="card">
          <header className="card__header">
            <h2>Edit Challenge</h2>
          </header>
          <div className="card__body">
            <form onSubmit={(e) => void handleEditSave(e)}>
              {pageMsg ? (
                <div
                  className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                >
                  {pageMsg.text}
                </div>
              ) : null}
              <p className="field__hint">
                Bracket: {editRow.bracket_name}
                {editRow.join_code ? ` · Code ${editRow.join_code}` : ''}
              </p>
              <div className="field">
                <label htmlFor="admin-ch-edit-name">Challenge name</label>
                <input
                  id="admin-ch-edit-name"
                  className="input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  required
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="admin-ch-edit-deadline">
                  Submission deadline (US Eastern)
                </label>
                <input
                  id="admin-ch-edit-deadline"
                  className="input"
                  type="datetime-local"
                  value={editDeadline}
                  onChange={(e) => setEditDeadline(e.target.value)}
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="admin-ch-edit-max">Entries per person</label>
                <input
                  id="admin-ch-edit-max"
                  className="input"
                  type="number"
                  min={minEntries}
                  max={50}
                  value={editMaxEntries}
                  onChange={(e) => setEditMaxEntries(e.target.value)}
                  disabled={editBusy}
                />
              </div>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={editPrivate}
                  onChange={(e) => setEditPrivate(e.target.checked)}
                  disabled={editBusy}
                />
                Private (join code)
              </label>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={editBusy}
                style={{ marginTop: '1rem' }}
              >
                {editBusy ? 'Saving…' : 'Save Challenge'}
              </button>
            </form>
          </div>
        </section>
      </div>
    );
  }

  if (view === 'add-entry' && entriesChallenge) {
    return (
      <div className="admin-page">
        <AdminBackBar label={entriesChallenge.name} onBack={goEntries} />
        <section className="card">
          <header className="card__header">
            <h2>Add Entry</h2>
          </header>
          <div className="card__body">
            <form onSubmit={(e) => void handleAddEntry(e)}>
              {pageMsg ? (
                <div
                  className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                >
                  {pageMsg.text}
                </div>
              ) : null}
              <div className="field">
                <label htmlFor="admin-ch-add-search">Find user</label>
                <input
                  id="admin-ch-add-search"
                  className="input"
                  type="search"
                  value={addUserSearch}
                  onChange={(e) => setAddUserSearch(e.target.value)}
                  placeholder="Search usernames…"
                  disabled={addBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="admin-ch-add-user">User</label>
                <select
                  id="admin-ch-add-user"
                  className="select"
                  value={addUserId === '' ? '' : String(addUserId)}
                  onChange={(e) => {
                    const id = e.target.value
                      ? parseInt(e.target.value, 10)
                      : '';
                    setAddUserId(id);
                    if (typeof id === 'number') {
                      const u = users.find((row) => row.id === id);
                      if (u && !addDisplayName.trim()) {
                        setAddDisplayName(u.username);
                      }
                    }
                  }}
                  required
                  disabled={addBusy || filteredUsers.length === 0}
                >
                  <option value="">Select a user…</option>
                  {filteredUsers.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.username}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="admin-ch-add-display">Entry name</label>
                <input
                  id="admin-ch-add-display"
                  className="input"
                  value={addDisplayName}
                  onChange={(e) => setAddDisplayName(e.target.value)}
                  disabled={addBusy}
                />
              </div>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={addBusy || addUserId === ''}
                style={{ marginTop: '1rem' }}
              >
                {addBusy ? 'Adding…' : 'Add Entry'}
              </button>
            </form>
          </div>
        </section>
      </div>
    );
  }

  if (view === 'rename-entry' && renameEntry && entriesChallenge) {
    return (
      <div className="admin-page">
        <AdminBackBar label={entriesChallenge.name} onBack={goEntries} />
        <section className="card">
          <header className="card__header">
            <h2>Rename Entry</h2>
          </header>
          <div className="card__body">
            <form onSubmit={(e) => void handleRename(e)}>
              {pageMsg ? (
                <div
                  className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                >
                  {pageMsg.text}
                </div>
              ) : null}
              <p className="field__hint">Account: {renameEntry.username}</p>
              <div className="field">
                <label htmlFor="admin-ch-rename">Entry name</label>
                <input
                  id="admin-ch-rename"
                  className="input"
                  value={renameName}
                  onChange={(e) => setRenameName(e.target.value)}
                  required
                  disabled={renameBusy}
                  autoFocus
                />
              </div>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={renameBusy}
                style={{ marginTop: '1rem' }}
              >
                {renameBusy ? 'Saving…' : 'Save Name'}
              </button>
            </form>
          </div>
        </section>
      </div>
    );
  }

  if (view === 'fill' && fillUbId != null && entriesChallenge) {
    return (
      <div className="admin-page">
        <AdminBackBar label={entriesChallenge.name} onBack={goEntries} />
        <section className="card">
          <header className="card__header">
            <h2>{fillTitle}</h2>
          </header>
          <div className="card__body">
            <BracketFill
              userBracketId={fillUbId}
              showSubmit={!fillSubmitted}
              onSubmitted={() => {
                void reloadEntries(entriesChallenge.id);
                void reloadList();
                setView('entries');
                setFillUbId(null);
                setPageMsg({
                  type: 'ok',
                  text: 'Bracket submitted for user.',
                });
              }}
            />
          </div>
        </section>
      </div>
    );
  }

  if (view === 'entries' && entriesChallenge) {
    return (
      <div className="admin-page">
        <AdminBackBar label="Challenges" onBack={goList} />
        <section className="card catalog-card">
          <AdminCatalogToolbar
            title={entriesChallenge.name}
            countLabel={
              filteredEntries.length === entries.length
                ? `${entries.length} entr${entries.length === 1 ? 'y' : 'ies'}`
                : `${filteredEntries.length} of ${entries.length} entries`
            }
            search={entriesSearch}
            onSearchChange={setEntriesSearch}
            searchLabel="Search entries"
            createLabel="Add Entry"
            onCreate={openAddEntry}
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
            {entriesBusy && entries.length === 0 ? (
              <p className="empty-state empty-state--compact">Loading…</p>
            ) : filteredEntries.length === 0 ? (
              <p className="empty-state empty-state--compact">
                <strong>
                  {entries.length === 0 ? 'No entries yet' : 'No matches'}
                </strong>
                {entries.length === 0
                  ? 'Add an entry to fill their bracket.'
                  : 'Try a different search.'}
              </p>
            ) : (
              <ul className="catalog-list">
                {filteredEntries.map((entry) => (
                  <li
                    key={entry.user_bracket_id}
                    className="catalog-list__row catalog-shelf__row"
                  >
                    <div className="catalog-shelf__main">
                      <span className="catalog-list__avatar catalog-list__avatar--ph">
                        {(entry.display_name || entry.username)
                          .charAt(0)
                          .toUpperCase()}
                      </span>
                      <span className="catalog-list__main">
                        <span className="catalog-list__name">
                          {entry.display_name || entry.username}
                        </span>
                        <span className="catalog-list__id">
                          {entry.username}
                          {entry.is_submitted
                            ? ' · Submitted'
                            : entry.is_complete
                              ? ' · Complete'
                              : ' · Incomplete'}
                        </span>
                      </span>
                    </div>
                    <div className="catalog-shelf__actions">
                      <button
                        type="button"
                        className="btn-icon"
                        title="Rename"
                        aria-label={`Rename ${entry.display_name || entry.username}`}
                        onClick={() => openRename(entry)}
                      >
                        <IconPencil />
                      </button>
                      <button
                        type="button"
                        className="btn-icon btn-icon--bracket"
                        title="Fill Bracket"
                        aria-label={`Fill bracket for ${entry.display_name || entry.username}`}
                        onClick={() => openFill(entry)}
                      >
                        {'}'} {'{'}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="admin-page">
      {loadErr ? <div className="alert alert--error">{loadErr}</div> : null}

      <section className="card catalog-card">
        <AdminCatalogToolbar
          title="Challenges"
          countLabel={
            filtered.length === rows.length
              ? `${rows.length} challenge${rows.length === 1 ? '' : 's'}`
              : `${filtered.length} of ${rows.length} challenges`
          }
          search={search}
          onSearchChange={setSearch}
          searchLabel="Search challenges"
          createLabel="Create Challenge"
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
          {filtered.length === 0 && !loadErr ? (
            <p className="empty-state empty-state--compact">
              <strong>
                {rows.length === 0 ? 'No challenges yet' : 'No matches'}
              </strong>
              {rows.length === 0
                ? 'Create a challenge to import historical brackets.'
                : 'Try a different search.'}
            </p>
          ) : (
            <ul className="catalog-list">
              {filtered.map((c) => (
                <li key={c.id} className="catalog-list__row catalog-shelf__row">
                  <div className="catalog-shelf__main">
                    {c.bracket_image_url ? (
                      <img
                        className="catalog-list__avatar"
                        src={c.bracket_image_url}
                        alt=""
                      />
                    ) : (
                      <span className="catalog-list__avatar catalog-list__avatar--ph">
                        {c.name.charAt(0)}
                      </span>
                    )}
                    <span className="catalog-list__main">
                      <span className="catalog-list__name">{c.name}</span>
                      <span className="catalog-list__id">
                        {c.bracket_name}
                        {c.is_private ? ' · Private' : ''}
                        {c.submission_deadline
                          ? ` · ${c.deadline_passed ? 'Closed' : 'Due'} ${formatDeadlineEst(c.submission_deadline)}`
                          : ''}
                        {` · ${c.entry_count} entr${c.entry_count === 1 ? 'y' : 'ies'}`}
                      </span>
                    </span>
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
                      className="btn-icon btn-icon--user"
                      title="Entries"
                      aria-label={`Manage entries for ${c.name}`}
                      disabled={!c.needs_user_bracket}
                      onClick={() => openEntries(c)}
                    >
                      <IconUser />
                    </button>
                    <button
                      type="button"
                      className="btn-icon btn-icon--danger"
                      title="Delete"
                      aria-label={`Delete ${c.name}`}
                      onClick={() =>
                        startDeleteTarget(
                          'challenge',
                          c.id,
                          c.name,
                          setDeleteTarget,
                        )
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
        title="Delete Challenge?"
        label={deleteTarget?.label ?? ''}
        relatedRecords={deleteTarget?.relatedRecords}
        loadingRelated={deleteTarget?.loadingRelated}
        busy={deleteBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
