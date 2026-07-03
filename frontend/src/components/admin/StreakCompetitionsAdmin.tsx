import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  adminAddStreakCompetitionQuestion,
  adminCreateStreakCompetition,
  adminDeleteStreakCompetition,
  adminDeleteStreakQuestion,
  adminGetStreakCompetition,
  adminResolveStreakQuestion,
  adminUpdateStreakCompetition,
  adminUpdateStreakQuestion,
  listStreakCompetitions,
  type StreakCompetitionQuestionAdmin,
  type StreakCompetitionSummary,
} from '../../utils/api';
import { invalidateHomeForStreakCompetition } from '../../utils/homeCache';
import {
  estLocalInputToIso,
  formatDeadlineEst,
  isoToEstLocalInput,
} from '../../utils/est';

import { AdminBackBar } from './AdminBackBar';
import { AdminCatalogToolbar } from './AdminCatalogToolbar';
import { IconPencil, IconQuestion, IconTrash } from './AdminIcons';
import { DeleteConfirmDialog } from './DeleteConfirmDialog';
import {
  startDeleteTarget,
  type AdminDeleteTarget,
} from './deleteDialogHelpers';
import './admin-shared.css';

type View = 'list' | 'create' | 'edit' | 'questions';

function isPastDeadline(closesAt: string): boolean {
  return new Date(closesAt).getTime() <= Date.now();
}

function isUnresolvedPast(q: StreakCompetitionQuestionAdmin): boolean {
  return q.resolved_at == null && isPastDeadline(q.closes_at);
}

function sortQuestions(items: StreakCompetitionQuestionAdmin[]) {
  return [...items].sort((a, b) => {
    const aNeedsResolve = isUnresolvedPast(a);
    const bNeedsResolve = isUnresolvedPast(b);
    if (aNeedsResolve !== bNeedsResolve) {
      return aNeedsResolve ? -1 : 1;
    }
    const byClose =
      new Date(b.closes_at).getTime() - new Date(a.closes_at).getTime();
    if (byClose !== 0) return byClose;
    return b.id - a.id;
  });
}

function QuestionTile({
  q,
  busy,
  onEdit,
  onDelete,
  onResolve,
}: {
  q: StreakCompetitionQuestionAdmin;
  busy: boolean;
  onEdit: (question: StreakCompetitionQuestionAdmin) => void;
  onDelete: (question: StreakCompetitionQuestionAdmin) => void;
  onResolve: (questionId: number, choiceId: number | null) => void;
}) {
  const past = isPastDeadline(q.closes_at);
  const resolved = q.resolved_at != null;

  let badge = 'Open';
  if (resolved) badge = 'Resolved';
  else if (past) badge = 'Past deadline';

  return (
    <li
      className={`streak-question-tile${past && !resolved ? ' streak-question-tile--past' : ''}${resolved ? ' streak-question-tile--resolved' : ''}`}
    >
      <div className="streak-question-tile__header">
        <div className="streak-question-tile__status">
          <span className="streak-question-tile__badge">{badge}</span>
          <span
            className={
              q.pick_count > 0
                ? 'streak-question-tile__pick-count streak-question-tile__pick-count--has-picks'
                : 'streak-question-tile__pick-count'
            }
          >
            {q.pick_count} pick{q.pick_count === 1 ? '' : 's'}
          </span>
        </div>
        <div className="streak-question-tile__toolbar">
          <button
            type="button"
            className="btn-icon"
            title="Edit"
            aria-label={`Edit question`}
            disabled={busy}
            onClick={() => onEdit(q)}
          >
            <IconPencil />
          </button>
          <button
            type="button"
            className="btn-icon btn-icon--danger"
            title="Delete"
            aria-label={`Delete question`}
            disabled={busy}
            onClick={() => onDelete(q)}
          >
            <IconTrash />
          </button>
        </div>
      </div>
      <p className="streak-question-tile__text">{q.text}</p>
      <p className="streak-question-tile__meta">
        Closes {formatDeadlineEst(q.closes_at)}
      </p>
      <div className="streak-question-tile__choices">
        {q.choices.map((choice) => (
          <button
            key={choice.id}
            type="button"
            className={
              resolved && q.correct_choice_id === choice.id
                ? 'btn btn--primary streak-question-tile__choice'
                : 'btn btn--ghost streak-question-tile__choice'
            }
            disabled={busy}
            title={
              resolved && q.correct_choice_id === choice.id
                ? 'Click again to clear'
                : undefined
            }
            onClick={() =>
              onResolve(
                q.id,
                resolved && q.correct_choice_id === choice.id ? null : choice.id,
              )
            }
          >
            {choice.label}
          </button>
        ))}
      </div>
    </li>
  );
}

export function StreakCompetitionsAdmin() {
  const [view, setView] = useState<View>('list');
  const [rows, setRows] = useState<StreakCompetitionSummary[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [pageMsg, setPageMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(
    null,
  );
  const [search, setSearch] = useState('');

  const [createName, setCreateName] = useState('');
  const [createImage, setCreateImage] = useState<File | null>(null);
  const [createImagePreview, setCreateImagePreview] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);

  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editImage, setEditImage] = useState<File | null>(null);
  const [editImagePreview, setEditImagePreview] = useState<string | null>(null);
  const [editExistingImageUrl, setEditExistingImageUrl] = useState<string | null>(
    null,
  );
  const [editBusy, setEditBusy] = useState(false);

  const [questionsId, setQuestionsId] = useState<number | null>(null);
  const [questionsName, setQuestionsName] = useState('');
  const [questionsIsOver, setQuestionsIsOver] = useState(false);
  const [questions, setQuestions] = useState<StreakCompetitionQuestionAdmin[]>(
    [],
  );
  const [questionsBusy, setQuestionsBusy] = useState(false);
  const [endCompetitionOpen, setEndCompetitionOpen] = useState(false);
  const [endCompetitionBusy, setEndCompetitionBusy] = useState(false);

  const [addOpen, setAddOpen] = useState(false);
  const [newText, setNewText] = useState('');
  const [newCloses, setNewCloses] = useState('');
  const [newChoices, setNewChoices] = useState(['', '']);
  const [newKnockoutOnly, setNewKnockoutOnly] = useState(false);
  const [questionBusy, setQuestionBusy] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<AdminDeleteTarget | null>(
    null,
  );
  const [deleteBusy, setDeleteBusy] = useState(false);

  const [editQuestion, setEditQuestion] =
    useState<StreakCompetitionQuestionAdmin | null>(null);
  const [editQuestionText, setEditQuestionText] = useState('');
  const [editQuestionCloses, setEditQuestionCloses] = useState('');
  const [editQuestionChoices, setEditQuestionChoices] = useState<
    Array<{ id?: number; label: string }>
  >([]);
  const [editQuestionKnockoutOnly, setEditQuestionKnockoutOnly] = useState(false);
  const [editQuestionBusy, setEditQuestionBusy] = useState(false);

  const [deleteQuestionTarget, setDeleteQuestionTarget] =
    useState<AdminDeleteTarget | null>(null);
  const [deleteQuestionBusy, setDeleteQuestionBusy] = useState(false);

  const reloadList = useCallback(async () => {
    setLoadErr('');
    try {
      const { streak_competitions } = await listStreakCompetitions();
      setRows(streak_competitions);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load competitions.',
      );
    }
  }, []);

  const reloadQuestions = useCallback(async (id: number) => {
    setLoadErr('');
    try {
      const data = await adminGetStreakCompetition(id);
      setQuestionsName(data.streak_competition.name);
      setQuestionsIsOver(data.streak_competition.is_over === true);
      setQuestions(data.questions);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load competition.',
      );
    }
  }, []);

  useEffect(() => {
    void reloadList();
  }, [reloadList]);

  useEffect(() => {
    if (!createImage) {
      setCreateImagePreview(null);
      return;
    }
    const url = URL.createObjectURL(createImage);
    setCreateImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [createImage]);

  useEffect(() => {
    if (!editImage) {
      setEditImagePreview(editExistingImageUrl);
      return;
    }
    const url = URL.createObjectURL(editImage);
    setEditImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [editImage, editExistingImageUrl]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.name.toLowerCase().includes(q));
  }, [rows, search]);

  const sortedQuestions = useMemo(() => sortQuestions(questions), [questions]);

  function openQuestions(id: number) {
    setQuestionsId(id);
    setView('questions');
    setPageMsg(null);
    void reloadQuestions(id);
  }

  function openEdit(row: StreakCompetitionSummary) {
    setEditId(row.id);
    setEditName(row.name);
    setEditImage(null);
    setEditExistingImageUrl(row.image_url ?? null);
    setView('edit');
    setPageMsg(null);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = createName.trim();
    if (!name) return;
    setCreateBusy(true);
    setPageMsg(null);
    try {
      const payload = new FormData();
      payload.append('name', name);
      if (createImage) payload.append('image', createImage);
      const { streak_competition } = await adminCreateStreakCompetition(payload);
      await reloadList();
      setCreateName('');
      setCreateImage(null);
      setView('list');
      setPageMsg({ type: 'ok', text: `Created “${streak_competition.name}”.` });
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
    if (editId == null) return;
    const name = editName.trim();
    if (!name) return;
    setEditBusy(true);
    setPageMsg(null);
    try {
      const payload = new FormData();
      payload.append('name', name);
      if (editImage) payload.append('image', editImage);
      const { streak_competition } = await adminUpdateStreakCompetition(
        editId,
        payload,
      );
      await reloadList();
      setView('list');
      setPageMsg({ type: 'ok', text: `Saved “${streak_competition.name}”.` });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not save.',
      });
    } finally {
      setEditBusy(false);
    }
  }

  async function handleEndCompetition() {
    if (questionsId == null) return;
    setEndCompetitionBusy(true);
    setPageMsg(null);
    try {
      await adminUpdateStreakCompetition(questionsId, { end_competition: true });
      invalidateHomeForStreakCompetition(questionsId);
      await reloadQuestions(questionsId);
      await reloadList();
      setEndCompetitionOpen(false);
      setPageMsg({
        type: 'ok',
        text: 'Competition ended. Awards are now visible in streak challenges.',
      });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not end competition.',
      });
    } finally {
      setEndCompetitionBusy(false);
    }
  }

  function resetAddForm() {
    setNewText('');
    setNewCloses('');
    setNewChoices(['', '']);
    setNewKnockoutOnly(false);
  }

  function updateNewChoice(index: number, value: string) {
    setNewChoices((prev) =>
      prev.map((choice, i) => (i === index ? value : choice)),
    );
  }

  function addNewChoiceRow() {
    setNewChoices((prev) => [...prev, '']);
  }

  function removeNewChoiceRow(index: number) {
    setNewChoices((prev) =>
      prev.length <= 2 ? prev : prev.filter((_, i) => i !== index),
    );
  }

  async function handleAddQuestion(e: React.FormEvent) {
    e.preventDefault();
    if (questionsId == null) return;
    const text = newText.trim();
    const closesIso = estLocalInputToIso(newCloses);
    const choices = newChoices.map((c) => c.trim()).filter(Boolean);
    if (!text || !closesIso) return;
    if (choices.length < 2) {
      setPageMsg({
        type: 'err',
        text: 'Add at least two answer choices.',
      });
      return;
    }
    setQuestionBusy(true);
    setPageMsg(null);
    try {
      await adminAddStreakCompetitionQuestion(questionsId, {
        text,
        closes_at: closesIso,
        choices,
        knockout_only: newKnockoutOnly,
      });
      resetAddForm();
      setAddOpen(false);
      await reloadQuestions(questionsId);
      await reloadList();
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not add question.',
      });
    } finally {
      setQuestionBusy(false);
    }
  }

  async function handleResolve(questionId: number, choiceId: number | null) {
    if (questionsId == null) return;
    setQuestionsBusy(true);
    setPageMsg(null);
    try {
      await adminResolveStreakQuestion(questionId, choiceId);
      invalidateHomeForStreakCompetition(questionsId);
      await reloadQuestions(questionsId);
      await reloadList();
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not save answer.',
      });
    } finally {
      setQuestionsBusy(false);
    }
  }

  function openEditQuestion(q: StreakCompetitionQuestionAdmin) {
    setEditQuestion(q);
    setEditQuestionText(q.text);
    setEditQuestionCloses(isoToEstLocalInput(q.closes_at));
    setEditQuestionChoices(
      q.choices.map((choice) => ({ id: choice.id, label: choice.label })),
    );
    setEditQuestionKnockoutOnly(q.knockout_only === true);
    setPageMsg(null);
  }

  function updateEditChoice(index: number, value: string) {
    setEditQuestionChoices((prev) =>
      prev.map((choice, i) =>
        i === index ? { ...choice, label: value } : choice,
      ),
    );
  }

  function addEditChoiceRow() {
    setEditQuestionChoices((prev) => [...prev, { label: '' }]);
  }

  function removeEditChoiceRow(index: number) {
    setEditQuestionChoices((prev) =>
      prev.length <= 2 ? prev : prev.filter((_, i) => i !== index),
    );
  }

  async function handleEditQuestionSave(e: React.FormEvent) {
    e.preventDefault();
    if (editQuestion == null || questionsId == null) return;
    const text = editQuestionText.trim();
    const closesIso = estLocalInputToIso(editQuestionCloses);
    const choices = editQuestionChoices
      .map((choice) => ({
        id: choice.id,
        label: choice.label.trim(),
      }))
      .filter((choice) => choice.label);
    if (!text || !closesIso) return;
    if (choices.length < 2) {
      setPageMsg({
        type: 'err',
        text: 'Add at least two answer choices.',
      });
      return;
    }
    setEditQuestionBusy(true);
    setPageMsg(null);
    try {
      await adminUpdateStreakQuestion(editQuestion.id, {
        text,
        closes_at: closesIso,
        choices,
        knockout_only: editQuestionKnockoutOnly,
      });
      setEditQuestion(null);
      await reloadQuestions(questionsId);
      await reloadList();
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not save question.',
      });
    } finally {
      setEditQuestionBusy(false);
    }
  }

  async function confirmDeleteQuestion() {
    if (deleteQuestionTarget == null || questionsId == null) return;
    setDeleteQuestionBusy(true);
    setPageMsg(null);
    try {
      await adminDeleteStreakQuestion(deleteQuestionTarget.id);
      setDeleteQuestionTarget(null);
      await reloadQuestions(questionsId);
      await reloadList();
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not delete question.',
      });
    } finally {
      setDeleteQuestionBusy(false);
    }
  }

  async function confirmDelete() {
    if (deleteTarget == null) return;
    setDeleteBusy(true);
    setPageMsg(null);
    try {
      await adminDeleteStreakCompetition(deleteTarget.id);
      const label = deleteTarget.label;
      setDeleteTarget(null);
      await reloadList();
      setPageMsg({ type: 'ok', text: `Deleted “${label}”.` });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not delete.',
      });
    } finally {
      setDeleteBusy(false);
    }
  }

  if (view === 'create') {
    return (
      <div className="admin-page">
        <AdminBackBar label="Competitions" onBack={() => setView('list')} />
        <section className="card">
          <header className="card__header">
            <h2>Create Competition</h2>
          </header>
          <div className="card__body">
            <form onSubmit={(e) => void handleCreate(e)}>
              <div className="field">
                <label htmlFor="streak-comp-name">Name</label>
                <input
                  id="streak-comp-name"
                  className="input"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  required
                  disabled={createBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="streak-comp-image">Image</label>
                <input
                  id="streak-comp-image"
                  className="input"
                  type="file"
                  accept="image/*"
                  disabled={createBusy}
                  onChange={(e) => setCreateImage(e.target.files?.[0] ?? null)}
                />
                {createImagePreview ? (
                  <div className="photo-preview">
                    <img src={createImagePreview} alt="" />
                    {createImage ? (
                      <span className="photo-preview__label">{createImage.name}</span>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="form-actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setView('list')}
                  disabled={createBusy}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={createBusy}
                >
                  {createBusy ? 'Creating…' : 'Create Competition'}
                </button>
              </div>
            </form>
          </div>
        </section>
      </div>
    );
  }

  if (view === 'edit' && editId != null) {
    return (
      <div className="admin-page">
        <AdminBackBar label="Competitions" onBack={() => setView('list')} />
        <section className="card">
          <header className="card__header">
            <h2>Edit Competition</h2>
          </header>
          <div className="card__body">
            {pageMsg ? (
              <div
                className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                role="status"
              >
                {pageMsg.text}
              </div>
            ) : null}
            <form onSubmit={(e) => void handleEditSave(e)}>
              <div className="field">
                <label htmlFor="streak-edit-name">Name</label>
                <input
                  id="streak-edit-name"
                  className="input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  required
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="streak-edit-image">Image</label>
                <input
                  id="streak-edit-image"
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
              <div className="form-actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setView('list')}
                  disabled={editBusy}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={editBusy}
                >
                  {editBusy ? 'Saving…' : 'Save'}
                </button>
              </div>
            </form>
          </div>
        </section>
      </div>
    );
  }

  if (view === 'questions' && questionsId != null) {
    return (
      <div className="admin-page">
        <AdminBackBar label="Competitions" onBack={() => setView('list')} />
        <section className="card">
          <header className="card__header">
            <h2>{questionsName || 'Competition'}</h2>
          </header>
          <div className="card__body">
            {loadErr ? <div className="alert alert--error">{loadErr}</div> : null}
            {pageMsg ? (
              <div
                className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                role="status"
              >
                {pageMsg.text}
              </div>
            ) : null}

            <div className="streak-competition-status">
              <label className="field__label" htmlFor="streak-competition-status">
                Competition status
              </label>
              <div className="streak-competition-status__row">
                <select
                  id="streak-competition-status"
                  className="select streak-competition-status__select"
                  value={questionsIsOver ? 'ended' : 'active'}
                  disabled={questionsIsOver || endCompetitionBusy}
                  onChange={(e) => {
                    if (e.target.value === 'ended' && !questionsIsOver) {
                      setEndCompetitionOpen(true);
                    }
                  }}
                >
                  <option value="active">Active</option>
                  <option value="ended">Ended</option>
                </select>
                {questionsIsOver ? (
                  <span className="streak-competition-status__note">
                    This competition is over. Picks are locked and awards are shown.
                  </span>
                ) : null}
              </div>
            </div>

            <ul className="streak-question-grid">
              <li>
                <button
                  type="button"
                  className="streak-question-tile streak-question-tile--add"
                  aria-label="Add question"
                  disabled={questionBusy}
                  onClick={() => {
                    setPageMsg(null);
                    resetAddForm();
                    setAddOpen(true);
                  }}
                >
                  <span className="streak-question-tile__plus" aria-hidden>
                    +
                  </span>
                </button>
              </li>
              {sortedQuestions.map((q) => (
                <QuestionTile
                  key={q.id}
                  q={q}
                  busy={questionsBusy || editQuestionBusy || deleteQuestionBusy}
                  onEdit={openEditQuestion}
                  onDelete={(question) =>
                    startDeleteTarget(
                      'streak-question',
                      question.id,
                      question.text.slice(0, 80),
                      setDeleteQuestionTarget,
                    )
                  }
                  onResolve={(id, choiceId) => void handleResolve(id, choiceId)}
                />
              ))}
            </ul>
          </div>
        </section>

        {editQuestion ? (
          <div
            className="delete-dialog-backdrop"
            role="presentation"
            onClick={editQuestionBusy ? undefined : () => setEditQuestion(null)}
          >
            <div
              className="delete-dialog streak-add-dialog card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="streak-edit-dialog-title"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 id="streak-edit-dialog-title" className="streak-add-dialog__title">
                Edit Question
              </h2>
              <form onSubmit={(e) => void handleEditQuestionSave(e)}>
                <div className="field">
                  <label htmlFor="streak-edit-q-text">Question</label>
                  <input
                    id="streak-edit-q-text"
                    className="input"
                    value={editQuestionText}
                    onChange={(e) => setEditQuestionText(e.target.value)}
                    disabled={editQuestionBusy}
                    required
                    autoFocus
                  />
                </div>
                <div className="field">
                  <label htmlFor="streak-edit-q-closes">Closes (US Eastern)</label>
                  <input
                    id="streak-edit-q-closes"
                    className="input"
                    type="datetime-local"
                    value={editQuestionCloses}
                    onChange={(e) => setEditQuestionCloses(e.target.value)}
                    disabled={editQuestionBusy}
                    required
                  />
                </div>
                <div className="field">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={editQuestionKnockoutOnly}
                      onChange={(e) => setEditQuestionKnockoutOnly(e.target.checked)}
                      disabled={editQuestionBusy}
                    />
                    Knockout Mode Only
                  </label>
                </div>
                <fieldset className="streak-add-dialog__choices">
                  <legend>Answers</legend>
                  {editQuestionChoices.map((choice, index) => (
                    <div key={choice.id ?? `new-${index}`} className="streak-add-dialog__choice-row">
                      <input
                        className="input"
                        value={choice.label}
                        onChange={(e) => updateEditChoice(index, e.target.value)}
                        disabled={editQuestionBusy}
                        placeholder={`Answer ${index + 1}`}
                        required={index < 2}
                        aria-label={`Answer ${index + 1}`}
                      />
                      {editQuestionChoices.length > 2 ? (
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => removeEditChoiceRow(index)}
                          disabled={editQuestionBusy}
                          aria-label={`Remove answer ${index + 1}`}
                        >
                          Remove
                        </button>
                      ) : null}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={addEditChoiceRow}
                    disabled={editQuestionBusy || editQuestionChoices.length >= 12}
                  >
                    Add Answer
                  </button>
                </fieldset>
                <div className="delete-dialog__actions">
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => setEditQuestion(null)}
                    disabled={editQuestionBusy}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn--primary"
                    disabled={editQuestionBusy}
                  >
                    {editQuestionBusy ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : null}

        {addOpen ? (
          <div
            className="delete-dialog-backdrop"
            role="presentation"
            onClick={questionBusy ? undefined : () => setAddOpen(false)}
          >
            <div
              className="delete-dialog streak-add-dialog card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="streak-add-dialog-title"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 id="streak-add-dialog-title" className="streak-add-dialog__title">
                Add Question
              </h2>
              <form onSubmit={(e) => void handleAddQuestion(e)}>
                <div className="field">
                  <label htmlFor="streak-q-text">Question</label>
                  <input
                    id="streak-q-text"
                    className="input"
                    value={newText}
                    onChange={(e) => setNewText(e.target.value)}
                    disabled={questionBusy}
                    required
                    autoFocus
                  />
                </div>
                <div className="field">
                  <label htmlFor="streak-q-closes">Closes (US Eastern)</label>
                  <input
                    id="streak-q-closes"
                    className="input"
                    type="datetime-local"
                    value={newCloses}
                    onChange={(e) => setNewCloses(e.target.value)}
                    disabled={questionBusy}
                    required
                  />
                </div>
                <div className="field">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={newKnockoutOnly}
                      onChange={(e) => setNewKnockoutOnly(e.target.checked)}
                      disabled={questionBusy}
                    />
                    Knockout Mode Only
                  </label>
                </div>
                <fieldset className="streak-add-dialog__choices">
                  <legend>Answers</legend>
                  {newChoices.map((choice, index) => (
                    <div key={index} className="streak-add-dialog__choice-row">
                      <input
                        className="input"
                        value={choice}
                        onChange={(e) => updateNewChoice(index, e.target.value)}
                        disabled={questionBusy}
                        placeholder={`Answer ${index + 1}`}
                        required={index < 2}
                        aria-label={`Answer ${index + 1}`}
                      />
                      {newChoices.length > 2 ? (
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => removeNewChoiceRow(index)}
                          disabled={questionBusy}
                          aria-label={`Remove answer ${index + 1}`}
                        >
                          Remove
                        </button>
                      ) : null}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={addNewChoiceRow}
                    disabled={questionBusy || newChoices.length >= 12}
                  >
                    Add Answer
                  </button>
                </fieldset>
                <div className="delete-dialog__actions">
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => setAddOpen(false)}
                    disabled={questionBusy}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn--primary"
                    disabled={questionBusy}
                  >
                    {questionBusy ? 'Adding…' : 'Add Question'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : null}

        <DeleteConfirmDialog
          open={endCompetitionOpen}
          title="End Competition?"
          label={questionsName || 'Competition'}
          intro="This locks picks in every streak challenge using this competition and shows awards. This cannot be undone."
          busy={endCompetitionBusy}
          onCancel={() => setEndCompetitionOpen(false)}
          onConfirm={() => void handleEndCompetition()}
        />

        <DeleteConfirmDialog
          open={deleteQuestionTarget != null}
          title="Delete Question?"
          label={deleteQuestionTarget?.label ?? ''}
          relatedRecords={deleteQuestionTarget?.relatedRecords}
          loadingRelated={deleteQuestionTarget?.loadingRelated}
          busy={deleteQuestionBusy}
          onCancel={() => setDeleteQuestionTarget(null)}
          onConfirm={() => void confirmDeleteQuestion()}
        />
      </div>
    );
  }

  return (
    <div className="admin-page">
      <section className="card catalog-card">
        <AdminCatalogToolbar
          title="Streak Competitions"
          countLabel={
            filtered.length === rows.length
              ? `${rows.length} in catalog`
              : `${filtered.length} of ${rows.length} in catalog`
          }
          search={search}
          onSearchChange={setSearch}
          searchLabel="Search streak competitions"
          createLabel="Create Competition"
          onCreate={() => {
            setPageMsg(null);
            setView('create');
          }}
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
                {rows.length === 0 ? 'No streak competitions yet' : 'No matches'}
              </strong>
              {rows.length === 0
                ? 'Create a competition, then add questions for users to pick.'
                : 'Try a different search.'}
            </p>
          ) : (
            <ul className="catalog-list">
              {filtered.map((row) => (
                  <li
                    key={row.id}
                    className="catalog-list__row catalog-shelf__row"
                  >
                    <div className="catalog-shelf__main">
                      {row.image_url ? (
                        <img
                          className="catalog-list__avatar"
                          src={row.image_url}
                          alt=""
                        />
                      ) : (
                        <span className="catalog-list__avatar catalog-list__avatar--ph">
                          {row.name.charAt(0)}
                        </span>
                      )}
                      <span className="catalog-list__main">
                        <span className="catalog-list__name">{row.name}</span>
                        <span className="catalog-list__id">
                          {row.question_count} question
                          {row.question_count === 1 ? '' : 's'}
                        </span>
                      </span>
                    </div>
                    <div className="catalog-shelf__actions">
                      <button
                        type="button"
                        className="btn-icon"
                        title="Edit"
                        aria-label={`Edit ${row.name}`}
                        onClick={() => openEdit(row)}
                      >
                        <IconPencil />
                      </button>
                      <button
                        type="button"
                        className="btn-icon btn-icon--questions"
                        title="Questions"
                        aria-label={`Manage questions for ${row.name}`}
                        onClick={() => openQuestions(row.id)}
                      >
                        <IconQuestion />
                      </button>
                      <button
                        type="button"
                        className="btn-icon btn-icon--danger"
                        title="Delete"
                        aria-label={`Delete ${row.name}`}
                        onClick={() =>
                          startDeleteTarget(
                            'streak-competition',
                            row.id,
                            row.name,
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
        title="Delete Competition?"
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
