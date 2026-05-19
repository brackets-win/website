import { useCallback, useEffect, useState } from 'react';

import { BracketFill } from '../bracket/BracketFill';
import {
  ApiError,
  getChallenge,
  getChallengeLeaderboard,
  type ChallengeSummary,
  type LeaderboardColumn,
  type LeaderboardEntry,
} from '../../utils/api';
import { formatDeadlineEst } from '../../utils/est';

import { ChallengeLeaderboard } from './ChallengeLeaderboard';
import { CopyJoinCode } from './CopyJoinCode';
import './ChallengeView.css';

export type ChallengeTab = 'bracket' | 'leaderboard' | 'settings';

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
  const [columns, setColumns] = useState<LeaderboardColumn[]>([]);
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [tab, setTab] = useState<ChallengeTab>(initialTab ?? 'bracket');

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const [{ challenge: c }, board] = await Promise.all([
        getChallenge(challengeId),
        getChallengeLeaderboard(challengeId),
      ]);
      setChallenge(c);
      setColumns(board.columns);
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

  const canEdit =
    challenge.can_edit_picks &&
    !challenge.is_submitted &&
    !challenge.deadline_passed;

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
        <button
          type="button"
          className={
            tab === 'bracket'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('bracket')}
        >
          My Bracket
        </button>
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
            tab === 'settings'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('settings')}
        >
          Settings
        </button>
      </nav>

      {tab === 'bracket' ? (
        <BracketFill
          userBracketId={userBracketId}
          readOnly={!canEdit}
          showSubmit={canEdit}
          onSubmitted={handleSubmitted}
        />
      ) : null}

      {tab === 'leaderboard' ? (
        <section className="card challenge-view__board">
          <ChallengeLeaderboard columns={columns} entries={entries} />
        </section>
      ) : null}

      {tab === 'settings' ? (
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
