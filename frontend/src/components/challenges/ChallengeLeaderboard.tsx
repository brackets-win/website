import { useMemo, useState } from 'react';

import type {
  LeaderboardColumn,
  LeaderboardDenominators,
  LeaderboardEntry,
} from '../../utils/api';
import { leaderboardRowClassName } from '../../utils/leaderboardRows';

import './ChallengeLeaderboard.css';

type SortKey = 'rank' | 'player' | 'total' | string;

type SortState = {
  key: SortKey;
  direction: 'asc' | 'desc';
};

type ScoreMode = 'pts' | 'pct';

type Props = {
  columns: LeaderboardColumn[];
  entries: LeaderboardEntry[];
  denominators?: LeaderboardDenominators | null;
  loading?: boolean;
  error?: string;
  viewerUsername?: string | null;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
};

function defaultDirection(key: SortKey): 'asc' | 'desc' {
  if (key === 'player' || key === 'rank' || key === 'potential_rank') return 'asc';
  return 'desc';
}

/** Competition ranking by a score accessor (1, 1, 3 — ties share rank, next skips). */
function computeRanksByScore(
  entries: LeaderboardEntry[],
  scoreOf: (entry: LeaderboardEntry) => number | null,
): Map<number, number> {
  const byScore = [...entries].sort((a, b) => {
    const sa = scoreOf(a);
    const sb = scoreOf(b);
    if (sa == null && sb == null) {
      return playerLabel(a).localeCompare(playerLabel(b), undefined, {
        sensitivity: 'base',
      });
    }
    if (sa == null) return 1;
    if (sb == null) return -1;
    const diff = sb - sa;
    if (diff !== 0) return diff;
    return playerLabel(a).localeCompare(playerLabel(b), undefined, {
      sensitivity: 'base',
    });
  });

  const ranks = new Map<number, number>();
  for (let i = 0; i < byScore.length; i++) {
    const entry = byScore[i];
    if (i === 0) {
      ranks.set(entry.user_bracket_id, 1);
      continue;
    }
    const prev = byScore[i - 1];
    const prevRank = ranks.get(prev.user_bracket_id)!;
    ranks.set(
      entry.user_bracket_id,
      scoreOf(entry) === scoreOf(prev) ? prevRank : i + 1,
    );
  }
  return ranks;
}

/** Competition ranking by total score (1, 1, 3 — ties share rank, next rank skips). */
function computeCompetitionRanks(
  entries: LeaderboardEntry[],
): Map<number, number> {
  return computeRanksByScore(entries, (e) => e.score);
}

/** Scoring column keys in chronological order (stages, then champion). */
function scoringColumnKeys(columns: LeaderboardColumn[]): string[] {
  return columns
    .map((col) => col.key)
    .filter((key) => key === 'champion' || key.startsWith('stage:'));
}

/**
 * Ranks as they stood *before* the latest scored stage, used to show each
 * player's rank movement. Returns null when there's no meaningful prior
 * ranking yet (nothing scored, or the current stage is the first with results).
 */
function computePreviousStageRanks(
  entries: LeaderboardEntry[],
  columns: LeaderboardColumn[],
  denominators: LeaderboardDenominators | null,
): Map<number, number> | null {
  if (!denominators) return null;
  const scoringCols = scoringColumnKeys(columns);
  const denomOf = (key: string) => denominators.columns?.[key] ?? 0;

  let latestScoredIdx = -1;
  for (let i = 0; i < scoringCols.length; i++) {
    if (denomOf(scoringCols[i]) > 0) latestScoredIdx = i;
  }
  if (latestScoredIdx < 0) return null;

  const previousCols = scoringCols.slice(0, latestScoredIdx);
  if (!previousCols.some((key) => denomOf(key) > 0)) return null;

  const previousScore = (entry: LeaderboardEntry) =>
    previousCols.reduce(
      (sum, key) => sum + (entry.stage_scores[key] ?? 0),
      0,
    );
  return computeRanksByScore(entries, previousScore);
}

/** Carat (up/down) or gray dash showing rank movement vs. the previous stage. */
function RankDeltaIndicator({ delta }: { delta: number | null }) {
  if (delta == null) return null;
  if (delta > 0) {
    return (
      <span
        className="leaderboard-rank-delta leaderboard-rank-delta--up"
        title={`Up ${delta} since last stage`}
        aria-label={`Up ${delta} since last stage`}
      >
        ▲
      </span>
    );
  }
  if (delta < 0) {
    return (
      <span
        className="leaderboard-rank-delta leaderboard-rank-delta--down"
        title={`Down ${-delta} since last stage`}
        aria-label={`Down ${-delta} since last stage`}
      >
        ▼
      </span>
    );
  }
  return (
    <span
      className="leaderboard-rank-delta leaderboard-rank-delta--same"
      title="No change since last stage"
      aria-label="No change since last stage"
    >
      –
    </span>
  );
}

function playerLabel(entry: LeaderboardEntry): string {
  return entry.display_name?.trim() || entry.username;
}

/** Single contestant image (the team this player wants to win the next match). */
function NextMatchPick({ pick }: { pick: LeaderboardEntry['next_match_pick'] }) {
  return (
    <span className="challenge-leaderboard__top-four-slot">
      {pick?.image_url ? (
        <img
          src={pick.image_url}
          alt={pick.display_name}
          className="challenge-leaderboard__top-four-img"
        />
      ) : pick ? (
        <span
          className="challenge-leaderboard__top-four-fallback"
          title={pick.display_name}
        >
          {pick.display_name.slice(0, 2).toUpperCase()}
        </span>
      ) : (
        <span className="challenge-leaderboard__top-four-empty" aria-hidden />
      )}
    </span>
  );
}

function compareWithNullsLast(
  a: number | null,
  b: number | null,
  direction: 'asc' | 'desc',
): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  const diff = a - b;
  return direction === 'asc' ? diff : -diff;
}

function compareEntries(
  a: LeaderboardEntry,
  b: LeaderboardEntry,
  sort: SortState,
  ranks: Map<number, number>,
): number {
  const { key, direction } = sort;
  let result = 0;

  if (key === 'rank') {
    const rankA = ranks.get(a.user_bracket_id) ?? Number.MAX_SAFE_INTEGER;
    const rankB = ranks.get(b.user_bracket_id) ?? Number.MAX_SAFE_INTEGER;
    result = rankA - rankB;
  } else if (key === 'player') {
    result = playerLabel(a).localeCompare(playerLabel(b), undefined, {
      sensitivity: 'base',
    });
  } else if (key === 'total') {
    result = compareWithNullsLast(a.score, b.score, direction);
    return result;
  } else if (key === 'potential') {
    result = compareWithNullsLast(a.potential, b.potential, direction);
    return result;
  } else if (key === 'potential_rank') {
    result = compareWithNullsLast(a.potential_rank, b.potential_rank, direction);
    return result;
  } else {
    result = compareWithNullsLast(
      a.stage_scores[key] ?? null,
      b.stage_scores[key] ?? null,
      direction,
    );
    return result;
  }

  return direction === 'asc' ? result : -result;
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  align = 'left',
}: {
  label: string;
  sortKey: SortKey;
  sort: SortState;
  onSort: (key: SortKey) => void;
  align?: 'left' | 'center';
}) {
  const active = sort.key === sortKey;
  const ariaSort = active
    ? sort.direction === 'asc'
      ? 'ascending'
      : 'descending'
    : 'none';
  const thClass =
    align === 'left'
      ? 'is-player'
      : align === 'center'
        ? 'is-num'
        : undefined;

  return (
    <th scope="col" className={thClass} aria-sort={ariaSort}>
      <button
        type="button"
        className={
          active
            ? 'challenge-leaderboard__th-btn challenge-leaderboard__th-btn--active'
            : 'challenge-leaderboard__th-btn'
        }
        onClick={() => onSort(sortKey)}
      >
        <span>{label}</span>
        <span className="challenge-leaderboard__sort-icon" aria-hidden>
          {active ? (sort.direction === 'asc' ? '↑' : '↓') : '↕'}
        </span>
      </button>
    </th>
  );
}

export function ChallengeLeaderboard({
  columns,
  entries,
  denominators = null,
  loading = false,
  error = '',
  viewerUsername = null,
  onSelectPlayer,
}: Props) {
  const [sort, setSort] = useState<SortState>({
    key: 'rank',
    direction: 'asc',
  });
  const [mode, setMode] = useState<ScoreMode>('pts');

  /**
   * Render a point value as raw points or as a % of its column denominator.
   * Stage, champion, and total columns show a dash before any results exist
   * (denominator 0) in both modes; potential rank is never converted.
   */
  function displayScore(colKey: string, raw: number | null): string {
    if (colKey === 'potential_rank') {
      return raw != null ? String(raw) : '—';
    }
    if (raw == null) return '—';
    if (colKey === 'potential') {
      const denom = denominators?.potential ?? 0;
      if (mode === 'pct' && denom > 0) {
        return `${Math.round((raw / denom) * 100)}%`;
      }
      return String(raw);
    }
    const denom =
      colKey === 'total'
        ? denominators?.total
        : denominators?.columns?.[colKey];
    if (!denom || denom <= 0) return '—';
    if (mode === 'pct') return `${Math.round((raw / denom) * 100)}%`;
    return String(raw);
  }

  const submittedEntries = useMemo(
    () => entries.filter((e) => e.submitted_at != null),
    [entries],
  );

  const ranks = useMemo(
    () => computeCompetitionRanks(submittedEntries),
    [submittedEntries],
  );

  const previousRanks = useMemo(
    () => computePreviousStageRanks(submittedEntries, columns, denominators),
    [submittedEntries, columns, denominators],
  );

  function rankDelta(userBracketId: number, currentRank?: number): number | null {
    if (!previousRanks || currentRank == null) return null;
    const prev = previousRanks.get(userBracketId);
    if (prev == null) return null;
    return prev - currentRank;
  }

  function onSort(key: SortKey) {
    setSort((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { key, direction: defaultDirection(key) };
    });
  }

  const sortedEntries = useMemo(() => {
    const rows = [...submittedEntries];
    rows.sort((a, b) => {
      const primary = compareEntries(a, b, sort, ranks);
      if (primary !== 0) return primary;
      const rankA = ranks.get(a.user_bracket_id) ?? Number.MAX_SAFE_INTEGER;
      const rankB = ranks.get(b.user_bracket_id) ?? Number.MAX_SAFE_INTEGER;
      if (rankA !== rankB) return rankA - rankB;
      return playerLabel(a).localeCompare(playerLabel(b), undefined, {
        sensitivity: 'base',
      });
    });
    return rows;
  }, [submittedEntries, sort, ranks]);

  if (loading) {
    return <p className="challenge-view__muted">Loading…</p>;
  }

  if (error) {
    return <div className="alert alert--error" role="status">{error}</div>;
  }

  if (submittedEntries.length === 0) {
    return <p className="challenge-view__muted">No submitted brackets yet.</p>;
  }

  const sortableColumns = columns.filter(
    (col) => col.key !== 'top_four_picks' && col.key !== 'next_match',
  );
  const sortOptions: { key: SortKey; label: string }[] = [
    { key: 'rank', label: 'Rank' },
    { key: 'player', label: 'Player' },
    { key: 'total', label: 'Total' },
    ...sortableColumns.map((col) => ({ key: col.key, label: col.name })),
  ];

  return (
    <div className="challenge-leaderboard">
      <div
        className="challenge-leaderboard__mode segmented"
        role="group"
        aria-label="Score display"
      >
        <button
          type="button"
          aria-pressed={mode === 'pts'}
          onClick={() => setMode('pts')}
        >
          PTS
        </button>
        <button
          type="button"
          aria-pressed={mode === 'pct'}
          onClick={() => setMode('pct')}
        >
          %
        </button>
      </div>
      <div className="challenge-leaderboard__mobile">
        <div
          className="challenge-leaderboard__sort-bar"
          role="group"
          aria-label="Sort leaderboard"
        >
          {sortOptions.map((opt) => (
            <button
              key={opt.key}
              type="button"
              className={
                sort.key === opt.key
                  ? 'challenge-leaderboard__sort-pill challenge-leaderboard__sort-pill--active'
                  : 'challenge-leaderboard__sort-pill'
              }
              onClick={() => onSort(opt.key)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <ol className="leaderboard-cards">
          {sortedEntries.map((row) => {
            const rank = ranks.get(row.user_bracket_id);
            const isViewer =
              viewerUsername != null && row.username === viewerUsername;
            const topFourCol = columns.find((c) => c.key === 'top_four_picks');
            const nextMatchCol = columns.find((c) => c.key === 'next_match');
            const statColumns = columns.filter(
              (c) => c.key !== 'top_four_picks' && c.key !== 'next_match',
            );
            const statSplitAt = Math.ceil(statColumns.length / 2);
            const statColumnsLeft = statColumns.slice(0, statSplitAt);
            const statColumnsRight = statColumns.slice(statSplitAt);

            function renderStat(col: LeaderboardColumn) {
              const value =
                col.key === 'potential'
                  ? row.potential
                  : col.key === 'potential_rank'
                    ? row.potential_rank
                    : row.stage_scores[col.key];
              return (
                <div key={col.key} className="leaderboard-card__stat">
                  <dt>{col.name}</dt>
                  <dd>{displayScore(col.key, value)}</dd>
                </div>
              );
            }

            return (
              <li
                key={row.user_bracket_id}
                className={`leaderboard-card ${leaderboardRowClassName(rank, isViewer)}`}
              >
                <div className="leaderboard-card__head">
                  <span className="leaderboard-card__rank">
                    <RankDeltaIndicator
                      delta={rankDelta(row.user_bracket_id, rank)}
                    />
                    {rank}
                  </span>
                  {onSelectPlayer ? (
                    <button
                      type="button"
                      className="challenge-leaderboard__player-btn leaderboard-card__name"
                      onClick={() =>
                        onSelectPlayer(row.user_bracket_id, playerLabel(row))
                      }
                    >
                      {playerLabel(row)}
                    </button>
                  ) : (
                    <p className="leaderboard-card__name">{playerLabel(row)}</p>
                  )}
                  <div>
                    <span className="leaderboard-card__total-label">Total</span>
                    <span className="leaderboard-card__total">
                      {displayScore('total', row.score)}
                    </span>
                  </div>
                </div>
                {statColumns.length > 0 ? (
                  <div className="leaderboard-card__stats">
                    <dl className="leaderboard-card__stats-col">
                      {statColumnsLeft.map(renderStat)}
                    </dl>
                    <dl className="leaderboard-card__stats-col">
                      {statColumnsRight.map(renderStat)}
                    </dl>
                  </div>
                ) : null}
                {nextMatchCol ? (
                  <div className="leaderboard-card__next-match">
                    <span className="leaderboard-card__top-four-label">
                      {nextMatchCol.name}
                    </span>
                    <NextMatchPick pick={row.next_match_pick} />
                  </div>
                ) : null}
                {topFourCol ? (
                  <div className="leaderboard-card__top-four">
                    <span className="leaderboard-card__top-four-label">
                      {topFourCol.name}
                    </span>
                    <div
                      className="challenge-leaderboard__top-four-row"
                      aria-label="Top four picks"
                    >
                      {[0, 1, 2, 3].map((i) => {
                        const picks = row.top_four_picks ?? [];
                        const pick = picks[i] ?? null;
                        return (
                          <span
                            key={i}
                            className="challenge-leaderboard__top-four-slot"
                          >
                            {pick?.image_url ? (
                              <img
                                src={pick.image_url}
                                alt={pick.display_name}
                                className="challenge-leaderboard__top-four-img"
                              />
                            ) : pick ? (
                              <span
                                className="challenge-leaderboard__top-four-fallback"
                                title={pick.display_name}
                              >
                                {pick.display_name.slice(0, 2).toUpperCase()}
                              </span>
                            ) : (
                              <span
                                className="challenge-leaderboard__top-four-empty"
                                aria-hidden
                              />
                            )}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      </div>

      <div className="challenge-leaderboard__desktop">
      <table className="data-table challenge-leaderboard__table">
        <thead>
          <tr>
            <SortableHeader
              label="#"
              sortKey="rank"
              sort={sort}
              onSort={onSort}
              align="center"
            />
            <SortableHeader
              label="Player"
              sortKey="player"
              sort={sort}
              onSort={onSort}
              align="left"
            />
            <SortableHeader
              label="Total"
              sortKey="total"
              sort={sort}
              onSort={onSort}
              align="center"
            />
            {columns.map((col) =>
              col.key === 'top_four_picks' || col.key === 'next_match' ? (
                <th
                  key={col.key}
                  scope="col"
                  className="is-num challenge-leaderboard__top-four-th"
                >
                  {col.name}
                </th>
              ) : (
                <SortableHeader
                  key={col.key}
                  label={col.name}
                  sortKey={col.key}
                  sort={sort}
                  onSort={onSort}
                  align="center"
                />
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {sortedEntries.map((row) => {
            const rank = ranks.get(row.user_bracket_id);
            const isViewer =
              viewerUsername != null && row.username === viewerUsername;
            return (
            <tr
              key={row.user_bracket_id}
              className={leaderboardRowClassName(rank, isViewer)}
            >
              <td className="is-rank is-num">
                <span className="leaderboard-rank-cell">
                  <RankDeltaIndicator
                    delta={rankDelta(row.user_bracket_id, rank)}
                  />
                  {rank}
                </span>
              </td>
              <td className="is-player">
                {onSelectPlayer ? (
                  <button
                    type="button"
                    className="challenge-leaderboard__player-btn"
                    onClick={() =>
                      onSelectPlayer(row.user_bracket_id, playerLabel(row))
                    }
                  >
                    {playerLabel(row)}
                  </button>
                ) : (
                  playerLabel(row)
                )}
              </td>
              <td className="is-num">
                {displayScore('total', row.score)}
              </td>
              {columns.map((col) => {
                if (col.key === 'top_four_picks') {
                  const picks = row.top_four_picks ?? [];
                  return (
                    <td
                      key={col.key}
                      className="is-num challenge-leaderboard__top-four"
                    >
                      <div
                        className="challenge-leaderboard__top-four-row"
                        aria-label="Top four picks"
                      >
                        {[0, 1, 2, 3].map((i) => {
                          const pick = picks[i] ?? null;
                          return (
                            <span
                              key={i}
                              className="challenge-leaderboard__top-four-slot"
                            >
                              {pick?.image_url ? (
                                <img
                                  src={pick.image_url}
                                  alt={pick.display_name}
                                  className="challenge-leaderboard__top-four-img"
                                />
                              ) : pick ? (
                                <span
                                  className="challenge-leaderboard__top-four-fallback"
                                  title={pick.display_name}
                                >
                                  {pick.display_name.slice(0, 2).toUpperCase()}
                                </span>
                              ) : (
                                <span
                                  className="challenge-leaderboard__top-four-empty"
                                  aria-hidden
                                />
                              )}
                            </span>
                          );
                        })}
                      </div>
                    </td>
                  );
                }
                if (col.key === 'next_match') {
                  return (
                    <td
                      key={col.key}
                      className="is-num challenge-leaderboard__next-match"
                    >
                      <NextMatchPick pick={row.next_match_pick} />
                    </td>
                  );
                }
                const value =
                  col.key === 'potential'
                    ? row.potential
                    : col.key === 'potential_rank'
                      ? row.potential_rank
                      : row.stage_scores[col.key];
                return (
                  <td key={col.key} className="is-num">
                    {displayScore(col.key, value)}
                  </td>
                );
              })}
            </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </div>
  );
}
