import { useCallback, useEffect, useMemo, useState } from 'react';

import { BracketFill } from '../bracket/BracketFill';
import {
  ApiError,
  getChallenge,
  getChallengeLeaderboard,
  type ChallengeSummary,
  type LeaderboardEntry,
} from '../../utils/api';
import { formatDeadlineEst } from '../../utils/est';

import { CopyJoinCode } from './CopyJoinCode';
import './ChallengeView.css';

export type ChallengeTab = 'fill' | 'bracket' | 'leaderboard' | 'settings';

type Props = {
  challengeId: number;
  userBracketId: number;
  initialTab?: ChallengeTab;
  onBack: () => void;
  onSubmitted: () => void;
};

export function ChallengeView({
  challengeId,
  userBracketId,
  initialTab,
  onBack,
  onSubmitted,
}: Props) {
  const [challenge, setChallenge] = useState<ChallengeSummary | null>(null);
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [tab, setTab] = useState<ChallengeTab>(initialTab ?? 'fill');

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const [{ challenge: c }, board] = await Promise.all([
        getChallenge(challengeId),
        getChallengeLeaderboard(challengeId),
      ]);
      setChallenge(c);
      setEntries(board.entries);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load challenge.',
      );
    }
  }, [challengeId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const activeTab = useMemo((): ChallengeTab => {
    if (!challenge) return tab;
    if (challenge.is_submitted || challenge.deadline_passed) {
      if (tab === 'fill') return 'bracket';
    }
    if (!challenge.can_edit_picks && tab === 'fill') return 'bracket';
    return tab;
  }, [challenge, tab]);

  const showFillTab =
    challenge != null &&
    challenge.can_edit_picks &&
    !challenge.is_submitted;

  function handleSubmitted() {
    void reload();
    onSubmitted();
    setTab('bracket');
  }

  if (loadErr && !challenge) {
    return (
      <div className="challenge-view">
        <div className="alert alert--error">{loadErr}</div>
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          ← My Challenges
        </button>
      </div>
    );
  }

  if (!challenge) {
    return <p className="challenge-view__muted">Loading…</p>;
  }

  return (
    <div className="challenge-view">
      <button
        type="button"
        className="btn btn--ghost challenge-view__back"
        onClick={onBack}
      >
        ← My Challenges
      </button>

      <header className="challenge-view__head card">
        <div className="challenge-view__head-inner">
          {challenge.bracket_image_url ? (
            <img
              className="challenge-view__bracket-img"
              src={challenge.bracket_image_url}
              alt=""
            />
          ) : (
            <span className="challenge-view__bracket-img challenge-view__bracket-img--ph">
              {challenge.bracket_name.charAt(0)}
            </span>
          )}
          <div>
          <h1>{challenge.name}</h1>
          <p className="challenge-view__meta">{challenge.bracket_name}</p>
          {challenge.submission_deadline ? (
            <p className="challenge-view__deadline">
              Submit by{' '}
              <strong>{formatDeadlineEst(challenge.submission_deadline)}</strong>
            </p>
          ) : null}
          {challenge.deadline_passed ? (
            <p className="challenge-view__status challenge-view__status--closed">
              Submissions closed
            </p>
          ) : challenge.is_submitted ? (
            <p className="challenge-view__status challenge-view__status--ok">
              Bracket submitted
            </p>
          ) : null}
          </div>
        </div>
      </header>

      <nav className="challenge-view__tabs" aria-label="Challenge sections">
        {showFillTab ? (
          <button
            type="button"
            className={
              activeTab === 'fill'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => setTab('fill')}
          >
            Fill bracket
          </button>
        ) : null}
        <button
          type="button"
          className={
            activeTab === 'bracket'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('bracket')}
        >
          My bracket
        </button>
        <button
          type="button"
          className={
            activeTab === 'leaderboard'
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
            activeTab === 'settings'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('settings')}
        >
          Settings
        </button>
      </nav>

      {activeTab === 'fill' && showFillTab ? (
        <BracketFill
          userBracketId={userBracketId}
          readOnly={false}
          showSubmit
          onSubmitted={handleSubmitted}
        />
      ) : null}

      {activeTab === 'bracket' ? (
        <BracketFill userBracketId={userBracketId} readOnly />
      ) : null}

      {activeTab === 'leaderboard' ? (
        <section className="card challenge-view__board">
          {entries.length === 0 ? (
            <p className="challenge-view__muted">No entries yet.</p>
          ) : (
            <table className="challenge-view__table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Player</th>
                  <th scope="col">Score</th>
                  <th scope="col">Submitted</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((row, i) => (
                  <tr key={row.user_bracket_id}>
                    <td>{i + 1}</td>
                    <td>{row.username}</td>
                    <td>{row.score != null ? row.score : '—'}</td>
                    <td>
                      {row.submitted_at
                        ? formatDeadlineEst(row.submitted_at)
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ) : null}

      {activeTab === 'settings' ? (
        <section className="card challenge-view__settings">
          {challenge.is_private && challenge.join_code ? (
            <CopyJoinCode code={challenge.join_code} />
          ) : (
            <p className="challenge-view__muted">
              This challenge is public. Anyone can join from the public list.
            </p>
          )}
        </section>
      ) : null}
    </div>
  );
}
