import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  createChallenge,
  createUserBracket,
  joinChallenge,
  listBrackets,
  listMyChallenges,
  listPublicChallenges,
  type BracketSummary,
  type ChallengeSummary,
} from '../../utils/api';
import { estLocalInputToIso, formatDeadlineEst } from '../../utils/est';

import type { ChallengeTab } from './ChallengeView';
import './ChallengesPage.css';

function ChallengeThumb({ url, name }: { url: string | null | undefined; name: string }) {
  if (url) {
    return <img className="challenge-thumb" src={url} alt="" />;
  }
  return (
    <span className="challenge-thumb challenge-thumb--ph" aria-hidden>
      {name.charAt(0)}
    </span>
  );
}

type Props = {
  onOpenChallenge: (
    challengeId: number,
    userBracketId: number,
    initialTab?: ChallengeTab,
  ) => void;
};

export function ChallengesPage({ onOpenChallenge }: Props) {
  const [rows, setRows] = useState<ChallengeSummary[]>([]);
  const [publicRows, setPublicRows] = useState<ChallengeSummary[]>([]);
  const [brackets, setBrackets] = useState<BracketSummary[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [loading, setLoading] = useState(true);
  const [joinOpen, setJoinOpen] = useState(false);
  const [joinCode, setJoinCode] = useState('');
  const [joinMsg, setJoinMsg] = useState('');
  const [joinBusy, setJoinBusy] = useState(false);
  const [startBusyId, setStartBusyId] = useState<number | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createBracketId, setCreateBracketId] = useState<number | ''>('');
  const [createPrivate, setCreatePrivate] = useState(false);
  const [createDeadline, setCreateDeadline] = useState('');
  const [createBusy, setCreateBusy] = useState(false);
  const [createErr, setCreateErr] = useState('');
  const reload = useCallback(async () => {
    setLoadErr('');
    setLoading(true);
    try {
      const [{ challenges }, { challenges: pub }, { brackets: bracketRows }] =
        await Promise.all([
          listMyChallenges(),
          listPublicChallenges(),
          listBrackets(),
        ]);
      setRows(challenges);
      setPublicRows(pub);
      setBrackets(bracketRows);
      setCreateBracketId((prev) => {
        if (prev !== '') return prev;
        return bracketRows[0]?.id ?? '';
      });
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load challenges.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  function resetCreateForm() {
    setCreateName('');
    setCreatePrivate(false);
    setCreateDeadline('');
    setCreateErr('');
  }

  const selectedBracket = useMemo(
    () =>
      createBracketId === ''
        ? null
        : brackets.find((b) => b.id === createBracketId) ?? null,
    [brackets, createBracketId],
  );

  function upsertChallenge(challenge: ChallengeSummary) {
    setRows((prev) => {
      const idx = prev.findIndex((c) => c.id === challenge.id);
      if (idx < 0) return [challenge, ...prev];
      const next = [...prev];
      next[idx] = challenge;
      return next;
    });
  }

  function openJoined(challenge: ChallengeSummary) {
    if (challenge.user_bracket_id == null) return;
    onOpenChallenge(challenge.id, challenge.user_bracket_id);
  }

  async function onJoinSubmit(e: React.FormEvent) {
    e.preventDefault();
    setJoinMsg('');
    const code = joinCode.trim();
    if (!code) {
      setJoinMsg('Enter a join code.');
      return;
    }
    setJoinBusy(true);
    try {
      const { challenge } = await joinChallenge({ join_code: code });
      upsertChallenge(challenge);
      setJoinOpen(false);
      setJoinCode('');
      openJoined(challenge);
    } catch (err) {
      setJoinMsg(
        err instanceof ApiError ? err.message : 'Could not join challenge.',
      );
    } finally {
      setJoinBusy(false);
    }
  }

  async function onJoinPublic(challenge: ChallengeSummary) {
    if (!challenge.can_join) {
      setJoinMsg('This challenge is no longer open.');
      return;
    }
    setJoinBusy(true);
    setJoinMsg('');
    try {
      const { challenge: joined } = await joinChallenge({
        challenge_id: challenge.id,
      });
      upsertChallenge(joined);
      openJoined(joined);
    } catch (err) {
      setJoinMsg(
        err instanceof ApiError ? err.message : 'Could not join challenge.',
      );
    } finally {
      setJoinBusy(false);
    }
  }

  async function onStartPicks(challenge: ChallengeSummary) {
    if (!challenge.can_join && !challenge.user_bracket_id) {
      setLoadErr('This challenge is closed.');
      return;
    }
    setStartBusyId(challenge.id);
    try {
      const { user_bracket } = await createUserBracket({
        bracket_id: challenge.bracket_id,
        challenge_id: challenge.id,
      });
      const updated = { ...challenge, user_bracket_id: user_bracket.id };
      upsertChallenge(updated);
      onOpenChallenge(challenge.id, user_bracket.id);
    } catch (err) {
      setLoadErr(
        err instanceof ApiError ? err.message : 'Could not start picks.',
      );
    } finally {
      setStartBusyId(null);
    }
  }

  function openExisting(c: ChallengeSummary) {
    if (c.user_bracket_id == null) {
      void onStartPicks(c);
      return;
    }
    onOpenChallenge(c.id, c.user_bracket_id);
  }

  async function onCreateSubmit(e: React.FormEvent) {
    e.preventDefault();
    setCreateErr('');
    const name = createName.trim();
    if (!name) {
      setCreateErr('Name is required.');
      return;
    }
    if (createBracketId === '' || !Number.isFinite(createBracketId)) {
      setCreateErr('Choose a bracket.');
      return;
    }
    const deadlineIso = estLocalInputToIso(createDeadline);
    if (createDeadline.trim() && !deadlineIso) {
      setCreateErr('Invalid submission deadline.');
      return;
    }
    setCreateBusy(true);
    try {
      const { challenge } = await createChallenge({
        name,
        bracket_id: createBracketId,
        is_private: createPrivate,
        submission_deadline: deadlineIso ?? null,
      });
      setRows((prev) => [challenge, ...prev]);
      resetCreateForm();
      setCreateOpen(false);
      if (challenge.user_bracket_id != null) {
        onOpenChallenge(
          challenge.id,
          challenge.user_bracket_id,
          challenge.is_private && challenge.join_code ? 'settings' : undefined,
        );
      }
    } catch (err) {
      setCreateErr(
        err instanceof ApiError ? err.message : 'Could not create challenge.',
      );
    } finally {
      setCreateBusy(false);
    }
  }

  return (
    <div className="challenges-page">
      <header className="challenges-page__hero">
        <div>
          <h1>My Challenges</h1>
          <p className="challenges-page__lead">
            Join a challenge, fill your bracket, and submit before the deadline.
          </p>
        </div>
        <div className="challenges-page__actions">
          <button
            type="button"
            className="btn btn--secondary challenges-page__action-btn"
            onClick={() => {
              setCreateOpen((v) => !v);
              setJoinOpen(false);
              setJoinMsg('');
              if (createOpen) resetCreateForm();
            }}
          >
            Create Challenge
          </button>
          <button
            type="button"
            className="btn btn--primary challenges-page__action-btn"
            onClick={() => {
              setJoinOpen((v) => !v);
              setCreateOpen(false);
              resetCreateForm();
              setJoinMsg('');
            }}
          >
            Join Challenge
          </button>
        </div>
      </header>

      {createOpen ? (
        <section className="card challenges-page__panel">
          <header className="challenges-page__panel-head">
            <h2>Create challenge</h2>
          </header>
          <form onSubmit={onCreateSubmit} className="challenges-page__create-form">
            <div className="field">
              <label htmlFor="create-name">Name</label>
              <input
                id="create-name"
                className="input"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                maxLength={100}
                required
                disabled={createBusy}
              />
            </div>

            <div className="field">
              <label htmlFor="create-bracket">Bracket</label>
              <select
                id="create-bracket"
                className="select"
                value={createBracketId === '' ? '' : String(createBracketId)}
                onChange={(e) =>
                  setCreateBracketId(
                    e.target.value ? parseInt(e.target.value, 10) : '',
                  )
                }
                disabled={createBusy || brackets.length === 0}
                required
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
              {selectedBracket ? (
                <div className="challenge-bracket-preview">
                  <ChallengeThumb
                    url={selectedBracket.image_url}
                    name={selectedBracket.name}
                  />
                  <span>{selectedBracket.name}</span>
                </div>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="create-deadline">
                Submission deadline <span className="field__hint">(US Eastern)</span>
              </label>
              <input
                id="create-deadline"
                className="input"
                type="datetime-local"
                value={createDeadline}
                onChange={(e) => setCreateDeadline(e.target.value)}
                disabled={createBusy}
              />
            </div>

            <label className="checkbox-row challenges-page__public-row">
              <input
                type="checkbox"
                checked={createPrivate}
                onChange={(e) => setCreatePrivate(e.target.checked)}
                disabled={createBusy}
              />
              Private (invite-only with a join code)
            </label>

            <div className="challenges-page__create-actions">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={createBusy || brackets.length === 0}
              >
                {createBusy ? 'Creating…' : 'Create challenge'}
              </button>
            </div>
          </form>
          {createErr ? (
            <div className="alert alert--error" role="status">
              {createErr}
            </div>
          ) : null}
        </section>
      ) : null}

      {joinOpen ? (
        <section className="card challenges-page__panel">
          <div className="challenges-page__join-private">
            <h3 className="challenges-page__join-section-title">
              Join Private Challenge
            </h3>
            <form onSubmit={onJoinSubmit} className="challenges-page__join-form">
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="join-code">Join code</label>
              <input
                id="join-code"
                className="input"
                value={joinCode}
                onChange={(e) =>
                  setJoinCode(
                    e.target.value.replace(/\s/g, '').toUpperCase().slice(0, 8),
                  )
                }
                placeholder="Enter code"
                autoComplete="off"
                maxLength={8}
                disabled={joinBusy}
              />
            </div>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={joinBusy}
            >
              {joinBusy ? 'Joining…' : 'Join'}
            </button>
          </form>
          </div>

          {publicRows.length > 0 ? (
            <div className="challenges-page__public-list">
              <h3 className="challenges-page__join-section-title">
                Join Public Challenge
              </h3>
              <ul className="challenge-list challenge-list--compact">
                {publicRows.map((c) => (
                  <li key={c.id} className="challenge-card challenge-card--compact">
                    <div className="challenge-card__body">
                      <ChallengeThumb url={c.bracket_image_url} name={c.name} />
                      <div>
                        <strong>{c.name}</strong>
                        <span className="challenge-card__meta">{c.bracket_name}</span>
                        {c.submission_deadline ? (
                          <span className="challenges-page__muted">
                            Due {formatDeadlineEst(c.submission_deadline)}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn btn--secondary"
                      disabled={joinBusy || !c.can_join}
                      onClick={() => void onJoinPublic(c)}
                    >
                      Join
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {joinMsg ? (
            <p className="challenges-page__join-msg" role="status">
              {joinMsg}
            </p>
          ) : null}
        </section>
      ) : null}

      {loadErr ? (
        <div className="alert alert--error">{loadErr}</div>
      ) : null}

      {!createOpen && !joinOpen && loading ? (
        <p className="challenges-page__muted">Loading…</p>
      ) : !createOpen && !joinOpen && rows.length === 0 ? (
        <div className="card empty-state">
          <strong>No challenges yet</strong>
          Create a challenge or join one with a code.
        </div>
      ) : !createOpen && !joinOpen ? (
        <ul className="challenge-list">
          {rows.map((c) => (
            <li key={c.id} className="challenge-card card">
              <div className="challenge-card__body">
                <ChallengeThumb url={c.bracket_image_url} name={c.name} />
                <div className="challenge-card__text">
                <h2 className="challenge-card__name">{c.name}</h2>
                <p className="challenge-card__meta">{c.bracket_name}</p>
                {c.submission_deadline ? (
                  <p className="challenges-page__muted">
                    Due {formatDeadlineEst(c.submission_deadline)}
                  </p>
                ) : null}
                {c.is_private ? (
                  <span className="challenge-card__badge">Private</span>
                ) : null}
                {c.is_submitted ? (
                  <span className="challenge-card__badge">Submitted</span>
                ) : c.deadline_passed ? (
                  <span className="challenge-card__badge">Closed</span>
                ) : null}
                </div>
              </div>
              <div className="challenge-card__actions">
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={startBusyId === c.id}
                  onClick={() => void openExisting(c)}
                >
                  {startBusyId === c.id
                    ? 'Opening…'
                    : c.is_submitted || c.deadline_passed
                      ? 'View'
                      : c.user_bracket_id != null
                        ? 'Open'
                        : 'Start'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
