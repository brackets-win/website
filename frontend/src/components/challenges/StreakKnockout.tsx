import {
  Fragment,
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
} from 'react';

import {
  ApiError,
  advanceStreakKnockout,
  getStreakChallenge,
  getStreakKnockout,
  getStreakLeaderboard,
  swapStreakKnockoutSetup,
  type StreakKnockoutMatch,
  type StreakKnockoutPayload,
  type StreakLeaderboardEntry,
  type StreakQuestionInfo,
} from '../../utils/api';

import '../bracket/BracketFill.css';
import './StreakKnockout.css';
import { columnMatchupCenterPct } from '../bracket/bracketMirrorLayout';
import {
  activeKnockoutRoundIndex,
  knockoutRoundLabel as roundLabel,
  stageQuestionProgress,
  type KnockoutPhaseInfo,
} from '../../utils/streakKnockout';
import {
  readStreakChallengeSessionCache,
  writeStreakChallengeSessionCache,
} from '../../utils/streakChallengeSessionCache';

type MatchupPlayer = {
  userId: number;
  displayName: string;
};

type Props = {
  streakChallengeId: number;
  onSelectPlayer: (
    userId: number,
    displayName: string,
    filter?: { scope?: 'consolation' | 'round'; roundIndex?: number },
    matchup?: {
      userA: MatchupPlayer;
      userB: MatchupPlayer;
    },
  ) => void;
};

function formatScore(correct: number, bonus: number, bonusEnabled: boolean) {
  if (!bonusEnabled) return String(correct);
  return `${correct} (+${bonus})`;
}

function scoreParts(
  {
    match,
    side,
  }: {
  match: StreakKnockoutMatch;
  side: 'a' | 'b';
  },
) {
  return side === 'a'
    ? {
        player: match.player_a,
        seed: match.seed_a,
        correct: match.score_a_correct,
        bonus: match.score_a_bonus,
      }
    : {
        player: match.player_b,
        seed: match.seed_b,
        correct: match.score_b_correct,
        bonus: match.score_b_bonus,
      };
}

function BracketSlot({
  match,
  side,
  onSelectPlayer,
}: {
  match: StreakKnockoutMatch;
  side: 'a' | 'b';
  onSelectPlayer: Props['onSelectPlayer'];
}) {
  const { player, seed, correct, bonus } = scoreParts({ match, side });
  const isWinner = player != null && match.winner_user_id === player.user_id;
  const matchup =
    match.player_a && match.player_b
      ? {
          userA: {
            userId: match.player_a.user_id,
            displayName: match.player_a.display_name,
          },
          userB: {
            userId: match.player_b.user_id,
            displayName: match.player_b.display_name,
          },
        }
      : undefined;

  if (!player) {
    return (
      <div className="bf-slot streak-bf__slot streak-bf__slot--empty">
        <span className="bf-ko-seed">—</span>
        <span className="streak-bf__name">TBD</span>
        <span className="streak-bf__score">—</span>
      </div>
    );
  }

  return (
    <div
      className={
        isWinner
          ? 'bf-slot streak-bf__slot streak-bf__slot--winner'
          : 'bf-slot streak-bf__slot'
      }
    >
      <div className="streak-bf__identity">
        <span className="bf-ko-seed">{seed || '—'}</span>
        <button
          type="button"
          className="streak-bf__name streak-leaderboard__player"
          onClick={() =>
            onSelectPlayer(
              player.user_id,
              player.display_name,
              {
                scope: 'round',
                roundIndex: match.round_index,
              },
              matchup,
            )
          }
        >
          {player.display_name}
        </button>
      </div>
      <span className="streak-bf__score">
        {formatScore(correct, bonus, match.score_bonus_enabled)}
      </span>
    </div>
  );
}

function BracketMatchup({
  match,
  onSelectPlayer,
}: {
  match: StreakKnockoutMatch;
  onSelectPlayer: Props['onSelectPlayer'];
}) {
  return (
    <div
      className={
        match.finalized || match.winner_user_id != null
          ? 'bf-matchup streak-bf__matchup streak-bf__matchup--decided'
          : 'bf-matchup streak-bf__matchup'
      }
    >
      <BracketSlot match={match} side="a" onSelectPlayer={onSelectPlayer} />
      <BracketSlot match={match} side="b" onSelectPlayer={onSelectPlayer} />
    </div>
  );
}

function StageTitle({
  label,
  isActive,
  progress,
}: {
  label: string;
  isActive: boolean;
  progress: { resolved: number; total: number } | null;
}) {
  if (!isActive || progress == null) {
    return <p className="bf-stage-title">{label}</p>;
  }

  return (
    <p className="bf-stage-title streak-bf__stage-title">
      <span className="streak-bf__stage-title-inner">
        <span className="streak-bf__stage-live" aria-label="Live" title="Live" />
        <span className="streak-bf__stage-title-label">{label}</span>
        <span className="streak-bf__stage-progress">
          ({progress.resolved} out of {progress.total})
        </span>
      </span>
    </p>
  );
}

function matchupAnchorStyle(
  stageIdx: number,
  position: number,
  openingMatchCount: number,
): CSSProperties {
  if (stageIdx === 0) {
    return {
      top: `${((position - 1) / openingMatchCount) * 100}%`,
      height: `${100 / openingMatchCount}%`,
      transform: 'none',
    };
  }
  return {
    top: `${columnMatchupCenterPct(stageIdx, position, 1, openingMatchCount, 1)}%`,
    transform: 'translateY(-50%)',
  };
}

function ConnectorStrip({
  fromStageIdx,
  nextMatches,
  openingMatchCount,
}: {
  fromStageIdx: number;
  nextMatches: StreakKnockoutMatch[];
  openingMatchCount: number;
}) {
  return (
    <div className="bf-connector-strip" aria-hidden>
      <div className="bf-stage-heading-spacer" />
      <div className="bf-connector-track">
        <svg
          className="bf-connector-svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {nextMatches.map((match) => {
            const feederTop = 2 * match.position - 1;
            const feederBottom = 2 * match.position;
            const y1 = columnMatchupCenterPct(
              fromStageIdx,
              feederTop,
              1,
              openingMatchCount,
              1,
            );
            const y2 = columnMatchupCenterPct(
              fromStageIdx,
              feederBottom,
              1,
              openingMatchCount,
              1,
            );
            const ym = columnMatchupCenterPct(
              fromStageIdx + 1,
              match.position,
              1,
              openingMatchCount,
              1,
            );
            const d = `M 0 ${y1} H 24 M 0 ${y2} H 24 M 24 ${y1} V ${y2} M 24 ${ym} H 100`;
            return <path key={match.id} d={d} className="bf-connector-path" />;
          })}
        </svg>
      </div>
    </div>
  );
}

function ChampionColumn({
  knockout,
  onSelectPlayer,
}: {
  knockout: StreakKnockoutPayload;
  onSelectPlayer: Props['onSelectPlayer'];
}) {
  const finalMatch =
    knockout.rounds.length > 0
      ? knockout.rounds[knockout.rounds.length - 1].matches[0] ?? null
      : null;
  const thirdPlaceMatch = knockout.third_place_match_enabled
    ? knockout.third_place_match ?? null
    : null;
  const champion =
    finalMatch?.player_a?.user_id === knockout.champion_user_id
      ? finalMatch.player_a
      : finalMatch?.player_b?.user_id === knockout.champion_user_id
        ? finalMatch.player_b
        : null;
  const finalMatchup =
    finalMatch?.player_a && finalMatch.player_b
      ? {
          userA: {
            userId: finalMatch.player_a.user_id,
            displayName: finalMatch.player_a.display_name,
          },
          userB: {
            userId: finalMatch.player_b.user_id,
            displayName: finalMatch.player_b.display_name,
          },
        }
      : undefined;

  return (
    <div className="bf-stage-col bf-stage-col--champion">
      <div className="bf-champion-stack">
        <div className="bf-champion-middle">
          <p className="bf-stage-title">Champion</p>
          <div className="bf-champion-box-wrap">
            <div
              className={
                champion
                  ? 'bf-champion-box bf-champion-box--active'
                  : 'bf-champion-box'
              }
            >
              {champion ? (
                <>
                  <button
                    type="button"
                    className="streak-bf__champion-name streak-leaderboard__player"
                    onClick={() =>
                      onSelectPlayer(
                        champion.user_id,
                        champion.display_name,
                        {
                          scope: 'round',
                          roundIndex: knockout.rounds.length,
                        },
                        finalMatchup,
                      )
                    }
                  >
                    {champion.display_name}
                  </button>
                  <span className="bf-champion-seed">
                    Seed #{champion.seed || '—'}
                  </span>
                </>
              ) : (
                <span className="bf-champion-placeholder">Champion</span>
              )}
            </div>
          </div>
        </div>
        {thirdPlaceMatch ? (
          <div className="bf-third-place-section streak-bf__third-place-section">
            <div className="streak-bf__third-place-match">
              <BracketMatchup
                match={thirdPlaceMatch}
                onSelectPlayer={onSelectPlayer}
              />
            </div>
            <p className="bf-stage-title streak-bf__third-place-label">3RD PLACE</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function StreakKnockout({
  streakChallengeId,
  onSelectPlayer,
}: Props) {
  const [knockout, setKnockout] = useState<StreakKnockoutPayload | null>(
    () => readStreakChallengeSessionCache(streakChallengeId)?.knockout ?? null,
  );
  const [questions, setQuestions] = useState<StreakQuestionInfo[]>(
    () => readStreakChallengeSessionCache(streakChallengeId)?.questions ?? [],
  );
  const [knockoutPhases, setKnockoutPhases] = useState<KnockoutPhaseInfo[]>(
    () =>
      readStreakChallengeSessionCache(streakChallengeId)?.knockoutPhases ?? [],
  );
  const [entries, setEntries] = useState<StreakLeaderboardEntry[]>(
    () => readStreakChallengeSessionCache(streakChallengeId)?.entries ?? [],
  );
  const [loadErr, setLoadErr] = useState('');
  const [setupErr, setSetupErr] = useState('');
  const [startBusy, setStartBusy] = useState(false);

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const [data, board, detail] = await Promise.all([
        getStreakKnockout(streakChallengeId),
        getStreakLeaderboard(streakChallengeId),
        getStreakChallenge(streakChallengeId),
      ]);
      setKnockout(data.knockout);
      setQuestions(detail.questions);
      setKnockoutPhases(detail.knockout_phases ?? []);
      setEntries(board.entries);
      writeStreakChallengeSessionCache(streakChallengeId, {
        knockout: data.knockout,
        questions: detail.questions,
        knockoutPhases: detail.knockout_phases ?? [],
        entries: board.entries,
      });
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
      writeStreakChallengeSessionCache(streakChallengeId, {
        knockout: result.knockout,
      });
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
      writeStreakChallengeSessionCache(streakChallengeId, {
        knockout: result.knockout,
      });
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

  const totalRounds = knockout.total_rounds || knockout.rounds.length;
  const isProjected = knockout.projected === true;
  const activeRoundIndex = activeKnockoutRoundIndex(knockout);
  const openingMatchCount = knockout.rounds[0]?.matches.length ?? 0;
  const boardHeightPx = Math.max(
    520,
    openingMatchCount * (knockout.status === 'SETUP' && !isProjected ? 210 : 160),
  );

  return (
    <section className="card streak-knockout">
      {setupErr ? <div className="alert alert--error">{setupErr}</div> : null}
      {knockout.status === 'COMPLETE' &&
      knockout.champion_user_id != null &&
      !isProjected ? (
        <p className="streak-knockout__champion">
          Champion crowned.
        </p>
      ) : null}

      {isProjected ? (
        <p className="streak-knockout__projected-note">
          The bracket is not finalized yet. These projected matchups are based
          on the current leaderboard.
        </p>
      ) : null}

      {knockout.status === 'SETUP' && knockout.can_manage && !isProjected ? (
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

      {knockout.rounds.length > 0 ? (
        <div
          className={isProjected ? 'bf streak-bf streak-bf--projected' : 'bf streak-bf'}
          style={{ '--bf-board-h': `${boardHeightPx}px` } as CSSProperties}
        >
          <div className="bf-ko-desktop bf-scroll">
            <div className="bf-ko-touch-zoom">
              <div className="bf-board-inner">
                {knockout.rounds.map((round, stageIdx) => {
                  const phase = knockoutPhases.find(
                    (entry) => entry.round_index === round.round_index,
                  );
                  const isActive = activeRoundIndex === round.round_index;
                  const progress =
                    phase != null
                      ? stageQuestionProgress(questions, phase.starts_at)
                      : null;

                  return (
                  <Fragment key={round.round_index}>
                    <div className="bf-stage-col">
                      <StageTitle
                        label={roundLabel(round.round_index, totalRounds)}
                        isActive={isActive}
                        progress={progress}
                      />
                      <div className="bf-stage-track">
                        {round.matches.map((match) => (
                          <div
                            key={match.id}
                            className={
                              stageIdx === 0
                                ? 'bf-matchup-anchor bf-matchup-anchor--band'
                                : 'bf-matchup-anchor'
                            }
                            style={matchupAnchorStyle(
                              stageIdx,
                              match.position,
                              openingMatchCount,
                            )}
                          >
                            <BracketMatchup
                              match={match}
                              onSelectPlayer={onSelectPlayer}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                    {stageIdx < knockout.rounds.length - 1 ? (
                      <ConnectorStrip
                        fromStageIdx={stageIdx}
                        nextMatches={knockout.rounds[stageIdx + 1].matches}
                        openingMatchCount={openingMatchCount}
                      />
                    ) : null}
                  </Fragment>
                  );
                })}
                <ChampionColumn
                  knockout={knockout}
                  onSelectPlayer={onSelectPlayer}
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {knockout.status === 'SETUP' && knockout.can_manage && !isProjected ? (
        <div className="streak-knockout__setup-panel">
          <h3 className="streak-knockout__setup-title">Round 1 Matchups</h3>
          <div className="streak-knockout__setup-grid">
            {(knockout.rounds[0]?.matches ?? []).map((match) => (
              <div key={match.id} className="streak-knockout__setup-card">
                <p className="streak-knockout__setup-card-title">
                  Match {match.position}
                </p>
                <SetupSwapControls
                  match={match}
                  entries={entries}
                  onSwap={handleSwap}
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {knockout.consolation.length > 0 ? (
        <div className="streak-knockout__consolation">
          <h3 className="streak-knockout__consolation-title">
            Consolation
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
                      className="streak-knockout__name streak-leaderboard__player"
                      onClick={() =>
                        onSelectPlayer(row.user_id, row.display_name, {
                          scope: 'consolation',
                        })
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
