import { useCallback, useEffect, useState } from 'react';

import {
  ApiError,
  advanceStreakKnockout,
  getStreakKnockout,
  getStreakLeaderboard,
  swapStreakKnockoutSetup,
  type StreakKnockoutMatch,
  type StreakKnockoutPayload,
  type StreakLeaderboardEntry,
} from '../../utils/api';

import './StreakKnockout.css';
import { knockoutRoundLabel as roundLabel } from '../../utils/streakKnockout';

type Props = {
  streakChallengeId: number;
  onSelectPlayer: (userId: number, displayName: string) => void;
};

function MatchCard({
  match,
  onSelectPlayer,
}: {
  match: StreakKnockoutMatch;
  onSelectPlayer: (userId: number, displayName: string) => void;
}) {
  function renderSlot(
    player: StreakKnockoutMatch['player_a'],
    score: number,
    seed: number,
  ) {
    if (!player) {
      return (
        <div className="streak-knockout__slot streak-knockout__slot--empty">
          <span className="streak-knockout__seed">—</span>
          <span className="streak-knockout__name">TBD</span>
          <span className="streak-knockout__score">—</span>
        </div>
      );
    }
    return (
      <div className="streak-knockout__slot">
        <span className="streak-knockout__seed">{seed || '—'}</span>
        <button
          type="button"
          className="streak-knockout__name streak-knockout__name--link"
          onClick={() => onSelectPlayer(player.user_id, player.display_name)}
        >
          {player.display_name}
        </button>
        <span className="streak-knockout__score">{score}</span>
      </div>
    );
  }

  return (
    <div
      className={
        match.finalized
          ? 'streak-knockout__match streak-knockout__match--final'
          : 'streak-knockout__match'
      }
    >
      {match.is_live ? (
        <span className="streak-knockout__live" aria-label="Live">
          <span className="streak-knockout__live-dot" aria-hidden />
          Live
        </span>
      ) : null}
      {renderSlot(match.player_a, match.score_a, match.seed_a)}
      {renderSlot(match.player_b, match.score_b, match.seed_b)}
    </div>
  );
}

export function StreakKnockout({
  streakChallengeId,
  onSelectPlayer,
}: Props) {
  const [knockout, setKnockout] = useState<StreakKnockoutPayload | null>(null);
  const [entries, setEntries] = useState<StreakLeaderboardEntry[]>([]);
  const [loadErr, setLoadErr] = useState('');
  const [setupErr, setSetupErr] = useState('');
  const [startBusy, setStartBusy] = useState(false);

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const [data, board] = await Promise.all([
        getStreakKnockout(streakChallengeId),
        getStreakLeaderboard(streakChallengeId),
      ]);
      setKnockout(data.knockout);
      setEntries(board.entries);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load knockout bracket.',
      );
    }
  }, [streakChallengeId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleSwap(
    matchPosition: number,
    slot: 'a' | 'b',
    userId: number,
  ) {
    setSetupErr('');
    try {
      const result = await swapStreakKnockoutSetup(streakChallengeId, {
        match_position: matchPosition,
        slot,
        user_id: userId,
      });
      setKnockout(result.knockout);
    } catch (e) {
      setSetupErr(
        e instanceof ApiError ? e.message : 'Could not update bracket.',
      );
    }
  }

  async function handleStartKnockout() {
    setSetupErr('');
    setStartBusy(true);
    try {
      const result = await advanceStreakKnockout(streakChallengeId);
      setKnockout(result.knockout);
    } catch (e) {
      setSetupErr(
        e instanceof ApiError ? e.message : 'Could not start knockout.',
      );
    } finally {
      setStartBusy(false);
    }
  }

  if (loadErr) {
    return <div className="alert alert--error">{loadErr}</div>;
  }

  if (!knockout) {
    return <p className="streak-view__muted">Loading…</p>;
  }

  const totalRounds = knockout.rounds.length;

  return (
    <section className="card streak-knockout">
      {setupErr ? <div className="alert alert--error">{setupErr}</div> : null}
      {knockout.status === 'COMPLETE' && knockout.champion_user_id != null ? (
        <p className="streak-knockout__champion">
          Champion crowned.
        </p>
      ) : null}

      {knockout.status === 'SETUP' && knockout.can_manage ? (
        <div className="streak-knockout__manage">
          <p className="streak-knockout__setup-note">
            Scores update from the schedule while you adjust round-one slots.
            Start Knockout to lock the bracket; later rounds still advance on
            their scheduled times.
          </p>
          <button
            type="button"
            className="btn btn--primary"
            disabled={startBusy}
            onClick={() => void handleStartKnockout()}
          >
            {startBusy ? 'Starting…' : 'Start Knockout'}
          </button>
        </div>
      ) : null}

      <div className="streak-knockout__bracket">
        {knockout.rounds.map((round) => (
          <div key={round.round_index} className="streak-knockout__round">
            <h3 className="streak-knockout__round-title">
              {roundLabel(round.round_index, totalRounds)}
            </h3>
            <div className="streak-knockout__round-matches">
              {round.matches.map((match) => (
                <div key={match.id}>
                  <MatchCard match={match} onSelectPlayer={onSelectPlayer} />
                  {knockout.status === 'SETUP' &&
                  knockout.can_manage &&
                  round.round_index === 1 ? (
                    <SetupSwapControls
                      match={match}
                      entries={entries}
                      onSwap={handleSwap}
                    />
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {knockout.consolation.length > 0 ? (
        <div className="streak-knockout__consolation">
          <h3 className="streak-knockout__consolation-title">
            Consolation 🥲
          </h3>
          <table className="streak-knockout__consolation-table">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Record</th>
                <th scope="col">Win %</th>
              </tr>
            </thead>
            <tbody>
              {knockout.consolation.map((row) => (
                <tr key={row.user_id}>
                  <td>
                    <button
                      type="button"
                      className="streak-knockout__name streak-knockout__name--link"
                      onClick={() =>
                        onSelectPlayer(row.user_id, row.display_name)
                      }
                    >
                      {row.display_name}
                    </button>
                  </td>
                  <td>{row.record}</td>
                  <td>{row.win_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function SetupSwapControls({
  match,
  entries,
  onSwap,
}: {
  match: StreakKnockoutMatch;
  entries: StreakLeaderboardEntry[];
  onSwap: (matchPosition: number, slot: 'a' | 'b', userId: number) => void;
}) {
  return (
    <div className="streak-knockout__setup">
      <label className="streak-knockout__setup-row">
        <span>Slot A</span>
        <select
          className="input"
          value={match.player_a?.user_id ?? ''}
          onChange={(e) => {
            const userId = Number(e.target.value);
            if (userId) void onSwap(match.position, 'a', userId);
          }}
        >
          <option value="">Select player</option>
          {entries.map((entry) => (
            <option key={entry.user_id} value={entry.user_id}>
              {entry.display_name?.trim() || entry.username}
            </option>
          ))}
        </select>
      </label>
      <label className="streak-knockout__setup-row">
        <span>Slot B</span>
        <select
          className="input"
          value={match.player_b?.user_id ?? ''}
          onChange={(e) => {
            const userId = Number(e.target.value);
            if (userId) void onSwap(match.position, 'b', userId);
          }}
        >
          <option value="">Select player</option>
          {entries.map((entry) => (
            <option key={entry.user_id} value={entry.user_id}>
              {entry.display_name?.trim() || entry.username}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
