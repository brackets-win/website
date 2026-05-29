import { useCallback, useEffect, useMemo, useState } from 'react';

import { DeleteConfirmDialog } from '../admin/DeleteConfirmDialog';
import {
  ApiError,
  deleteStreakChallenge,
  getStreakChallenge,
  getStreakLeaderboard,
  getStreakParticipantPicks,
  clearStreakPick,
  streakPick,
  type ApiUser,
  type StreakLeaderboardEntry,
  type StreakParticipantPickRow,
  type StreakQuestionInfo,
  type StreakChallengeSummary,
} from '../../utils/api';
import {
  computeCompetitionRanks,
  leaderboardRowClassName,
} from '../../utils/leaderboardRows';
import { challengeThemeClass } from '../../utils/challengeThemes';
import { formatDeadlineEst } from '../../utils/est';

import { CopyJoinCode } from './CopyJoinCode';
import { StreakQuestionChoices } from './StreakQuestionChoices';
import './challengeThemes.css';
import './StreakChallengeView.css';
import '../challenges/ChallengeView.css';
import './ChallengeLeaderboard.css';

const streakThemeClass = challengeThemeClass('streak');

type Props = {
  streakChallengeId: number;
  currentUser: ApiUser;
  onBack: () => void;
};

function streakRankCompare(
  a: StreakLeaderboardEntry,
  b: StreakLeaderboardEntry,
): number {
  if (b.streak_signed !== a.streak_signed) {
    return b.streak_signed - a.streak_signed;
  }
  if (b.win_pct !== a.win_pct) {
    return b.win_pct - a.win_pct;
  }
  return a.username.localeCompare(b.username, undefined, { sensitivity: 'base' });
}

type Tab = 'leaderboard' | 'make' | 'past' | 'settings';

function compareClosesAtAsc(
  a: { closes_at: string; id: number },
  b: { closes_at: string; id: number },
): number {
  const diff =
    new Date(a.closes_at).getTime() - new Date(b.closes_at).getTime();
  if (diff !== 0) return diff;
  return a.id - b.id;
}

function compareClosesAtDesc(
  a: { closes_at: string; id: number },
  b: { closes_at: string; id: number },
): number {
  const diff =
    new Date(b.closes_at).getTime() - new Date(a.closes_at).getTime();
  if (diff !== 0) return diff;
  return b.id - a.id;
}

type SelectedPlayer = {
  userId: number;
  username: string;
};

export function StreakChallengeView({
  streakChallengeId,
  currentUser,
  onBack,
}: Props) {
  const [summary, setSummary] = useState<StreakChallengeSummary | null>(null);
  const [questions, setQuestions] = useState<StreakQuestionInfo[]>([]);
  const [entries, setEntries] = useState<StreakLeaderboardEntry[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [tab, setTab] = useState<Tab>('leaderboard');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteErr, setDeleteErr] = useState('');

  const [selectedPlayer, setSelectedPlayer] = useState<SelectedPlayer | null>(
    null,
  );
  const [playerPicks, setPlayerPicks] = useState<StreakParticipantPickRow[]>(
    [],
  );
  const [playerPicksBusy, setPlayerPicksBusy] = useState(false);
  const [playerPicksErr, setPlayerPicksErr] = useState('');

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const [detail, board] = await Promise.all([
        getStreakChallenge(streakChallengeId),
        getStreakLeaderboard(streakChallengeId),
      ]);
      setSummary(detail.streak_challenge);
      setQuestions(detail.questions);
      setEntries(board.entries);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load streak challenge.',
      );
    }
  }, [streakChallengeId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const streakRanks = useMemo(
    () =>
      computeCompetitionRanks(entries, streakRankCompare, (e) => e.user_id),
    [entries],
  );

  const { makeQuestions, pastQuestions } = useMemo(() => {
    const past: StreakQuestionInfo[] = [];
    const make: StreakQuestionInfo[] = [];
    for (const q of questions) {
      if (q.resolved_at != null) {
        if (q.user_choice_id != null) {
          past.push(q);
        }
      } else {
        make.push(q);
      }
    }
    make.sort(compareClosesAtAsc);
    past.sort(compareClosesAtDesc);
    return { makeQuestions: make, pastQuestions: past };
  }, [questions]);

  const sortedPlayerPicks = useMemo(
    () =>
      [...playerPicks].sort((a, b) =>
        compareClosesAtDesc(
          { closes_at: a.closes_at, id: a.question_id },
          { closes_at: b.closes_at, id: b.question_id },
        ),
      ),
    [playerPicks],
  );

  useEffect(() => {
    if (selectedPlayer == null) {
      setPlayerPicks([]);
      setPlayerPicksErr('');
      return;
    }
    let cancelled = false;
    setPlayerPicksBusy(true);
    setPlayerPicksErr('');
    void getStreakParticipantPicks(streakChallengeId, selectedPlayer.userId)
      .then((data) => {
        if (!cancelled) setPlayerPicks(data.picks);
      })
      .catch((e) => {
        if (!cancelled) {
          setPlayerPicksErr(
            e instanceof ApiError ? e.message : 'Unable to load picks.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setPlayerPicksBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPlayer, streakChallengeId]);

  async function onPick(questionId: number, choiceId: number) {
    try {
      await streakPick(streakChallengeId, questionId, choiceId);
      await reload();
    } catch (e) {
      setLoadErr(e instanceof ApiError ? e.message : 'Could not save pick.');
    }
  }

  async function onClearPick(questionId: number) {
    try {
      await clearStreakPick(streakChallengeId, questionId);
      await reload();
    } catch (e) {
      setLoadErr(e instanceof ApiError ? e.message : 'Could not clear pick.');
    }
  }

  function renderQuestion(
    q: StreakQuestionInfo,
    mode: 'make' | 'past',
  ) {
    const resolved = q.resolved_at != null;
    const deadlineLocked = mode === 'make' && q.deadline_locked;
    return (
      <li
        key={q.id}
        className={
          deadlineLocked
            ? 'card streak-question streak-question--locked'
            : 'card streak-question'
        }
      >
        <div className="streak-question__head">
          <div className="streak-question__head-main">
            <p className="streak-question__text">{q.text}</p>
            <p className="streak-question__meta">
              Closes {formatDeadlineEst(q.closes_at)}
            </p>
          </div>
          {deadlineLocked ? (
            <p className="streak-question__locked">
              <svg
                className="streak-question__lock-icon"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              Multiple picks cannot share a deadline
            </p>
          ) : null}
        </div>
        <StreakQuestionChoices
          choices={q.choices}
          userChoiceId={q.user_choice_id}
          correctChoiceId={q.correct_choice_id}
          resolved={resolved}
          showPickPct={mode === 'past'}
          disabled={mode === 'past' || !q.is_open}
          deadlineLocked={deadlineLocked}
          canClearPick={mode === 'make' && q.can_clear_pick}
          onPick={
            mode === 'make' && q.is_open && !q.deadline_locked
              ? (choiceId) => void onPick(q.id, choiceId)
              : undefined
          }
          onClearPick={
            mode === 'make' && q.can_clear_pick
              ? () => void onClearPick(q.id)
              : undefined
          }
        />
      </li>
    );
  }

  async function handleDeleteChallenge() {
    setDeleteBusy(true);
    setDeleteErr('');
    try {
      await deleteStreakChallenge(streakChallengeId);
      setDeleteOpen(false);
      onBack();
    } catch (err) {
      setDeleteErr(
        err instanceof ApiError ? err.message : 'Could not delete challenge.',
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  if (loadErr && !summary) {
    return (
      <div className={`${streakThemeClass} streak-view`}>
        <div className="alert alert--error">{loadErr}</div>
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          ← My Challenges
        </button>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className={`${streakThemeClass} streak-view`}>
        <p className="streak-view__muted">Loading…</p>
      </div>
    );
  }

  if (selectedPlayer != null) {
    return (
      <div className={`${streakThemeClass} streak-view`}>
        <button
          type="button"
          className="btn btn--ghost streak-player-picks__back"
          onClick={() => setSelectedPlayer(null)}
        >
          ← Leaderboard
        </button>
        <section className="card streak-view__panel">
          <h2 className="streak-player-picks__title">
            {selectedPlayer.username}&apos;s picks
          </h2>
          {playerPicksErr ? (
            <div className="alert alert--error">{playerPicksErr}</div>
          ) : null}
          {playerPicksBusy ? (
            <p className="streak-view__muted">Loading…</p>
          ) : sortedPlayerPicks.length === 0 ? (
            <p className="streak-view__muted">No picks yet.</p>
          ) : (
            <ul className="streak-player-picks__list">
              {sortedPlayerPicks.map((row) => (
                <li key={row.question_id} className="streak-player-picks__item">
                  <p className="streak-player-picks__question">{row.text}</p>
                  <p className="streak-player-picks__meta">
                    Closed {formatDeadlineEst(row.closes_at)}
                  </p>
                  <StreakQuestionChoices
                    choices={row.choices}
                    userChoiceId={row.pick_choice_id}
                    correctChoiceId={row.correct_choice_id}
                    resolved
                    disabled
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className={`${streakThemeClass} streak-view`}>
      <button
        type="button"
        className="btn btn--ghost challenge-view__back"
        onClick={onBack}
      >
        ← My Challenges
      </button>

      <header className="challenge-view__head card">
        <div className="challenge-view__head-inner">
          {summary.image_url ? (
            <img
              className="challenge-view__bracket-img"
              src={summary.image_url}
              alt=""
            />
          ) : (
            <span className="challenge-view__bracket-img challenge-view__bracket-img--ph">
              {(summary.streak_competition_name || summary.name).charAt(0)}
            </span>
          )}
          <div>
            <p className="challenge-view__type">Streak Challenge</p>
            <h1>{summary.name}</h1>
            {summary.streak_competition_name ? (
              <p className="challenge-view__meta">{summary.streak_competition_name}</p>
            ) : null}
            <p className="streak-view__stat">
              {summary.streak_signed >= 5 ? (
                <span className="streak-view__fire" aria-hidden>
                  🔥
                </span>
              ) : null}
              <strong>{summary.streak_display}</strong>
              <span className="streak-view__stat-sep" aria-hidden>
                {' '}
                |{' '}
              </span>
              <span className="streak-view__record">
                {summary.wins}-{summary.losses}
              </span>
            </p>
          </div>
        </div>
      </header>

      {loadErr ? <div className="alert alert--error">{loadErr}</div> : null}

      <nav className="challenge-view__tabs" aria-label="Streak sections">
        <button
          type="button"
          className={
            tab === 'leaderboard'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('leaderboard')}
        >
          Leaderboard
        </button>
        <button
          type="button"
          className={
            tab === 'make'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('make')}
        >
          Make Picks
        </button>
        <button
          type="button"
          className={
            tab === 'past'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('past')}
        >
          Past Picks
        </button>
        <button
          type="button"
          className={
            tab === 'settings'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('settings')}
        >
          Settings
        </button>
      </nav>

      {tab === 'leaderboard' ? (
        <section className="card streak-view__panel">
          <div className="table-scroll">
            <table className="data-table streak-leaderboard__table">
              <thead>
                <tr>
                  <th className="is-num">#</th>
                  <th className="is-player">Player</th>
                  <th className="is-num">Current</th>
                  <th className="is-num">Long W</th>
                  <th className="is-num">Long L</th>
                  <th className="is-num">Record</th>
                  <th className="is-num">WIN %</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => {
                  const rank = streakRanks.get(e.user_id) ?? e.rank;
                  const isViewer = e.user_id === currentUser.id;
                  return (
                  <tr
                    key={e.user_id}
                    className={leaderboardRowClassName(rank, isViewer)}
                  >
                    <td className="is-num">{rank}</td>
                    <td className="is-player">
                      <button
                        type="button"
                        className="streak-leaderboard__player"
                        onClick={() =>
                          setSelectedPlayer({
                            userId: e.user_id,
                            username: e.username,
                          })
                        }
                      >
                        {e.username}
                      </button>
                    </td>
                    <td className="is-num">{e.current_display}</td>
                    <td className="is-num">{e.long_win_display}</td>
                    <td className="is-num">{e.long_loss_display}</td>
                    <td className="is-num">{e.record}</td>
                    <td className="is-num">{e.win_pct}%</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {entries.length === 0 ? (
            <p className="streak-view__muted">No players yet.</p>
          ) : null}
        </section>
      ) : null}

      {tab === 'make' ? (
        <section className="streak-view__questions streak-view__questions--make">
          <ul className="streak-question-list">
            {makeQuestions.map((q) => renderQuestion(q, 'make'))}
          </ul>
          {makeQuestions.length === 0 ? (
            <p className="streak-view__muted">No open questions right now.</p>
          ) : null}
        </section>
      ) : null}

      {tab === 'past' ? (
        <section className="streak-view__questions">
          <ul className="streak-question-list">
            {pastQuestions.map((q) => renderQuestion(q, 'past'))}
          </ul>
          {pastQuestions.length === 0 ? (
            <p className="streak-view__muted">No picks yet.</p>
          ) : null}
        </section>
      ) : null}

      {tab === 'settings' ? (
        <section className="card challenge-view__settings">
          {summary.is_private && summary.join_code ? (
            <CopyJoinCode code={summary.join_code} />
          ) : (
            <p className="streak-view__muted">
              This challenge is public. Anyone can join from the public list.
            </p>
          )}
          {summary.is_creator ? (
            <div className="challenge-view__danger">
              <h2 className="challenge-view__danger-title">Delete Challenge</h2>
              <p className="streak-view__muted">
                Permanently remove this challenge and all entries. This cannot be
                undone.
              </p>
              {deleteErr ? (
                <div className="alert alert--error" role="status">
                  {deleteErr}
                </div>
              ) : null}
              <button
                type="button"
                className="btn btn--danger"
                onClick={() => {
                  setDeleteErr('');
                  setDeleteOpen(true);
                }}
              >
                Delete Challenge
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      <DeleteConfirmDialog
        open={deleteOpen}
        title="Delete Challenge?"
        label={summary?.name ?? ''}
        intro={
          summary
            ? `“${summary.name}” will be permanently removed along with all player entries.`
            : undefined
        }
        busy={deleteBusy}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => void handleDeleteChallenge()}
      />
    </div>
  );
}
