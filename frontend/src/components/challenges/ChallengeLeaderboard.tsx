import { useMemo, useState } from 'react';

import type { LeaderboardColumn, LeaderboardEntry } from '../../utils/api';
import { leaderboardRowClassName } from '../../utils/leaderboardRows';

import './ChallengeLeaderboard.css';

type SortKey = 'rank' | 'player' | 'total' | string;

type SortState = {
  key: SortKey;
  direction: 'asc' | 'desc';
};

type Props = {
  columns: LeaderboardColumn[];
  entries: LeaderboardEntry[];
  loading?: boolean;
  error?: string;
  viewerUsername?: string | null;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
};

function defaultDirection(key: SortKey): 'asc' | 'desc' {
  if (key === 'player' || key === 'rank') return 'asc';
  return 'desc';
}

/** Competition ranking by total score (1, 1, 3 — ties share rank, next rank skips). */
function computeCompetitionRanks(
  entries: LeaderboardEntry[],
): Map<number, number> {
  const byScore = [...entries].sort((a, b) => {
    if (a.score == null && b.score == null) {
      return playerLabel(a).localeCompare(playerLabel(b), undefined, {
        sensitivity: 'base',
      });
    }
    if (a.score == null) return 1;
    if (b.score == null) return -1;
    const diff = b.score - a.score;
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
      entry.score === prev.score ? prevRank : i + 1,
    );
  }
  return ranks;
}

function playerLabel(entry: LeaderboardEntry): string {
  return entry.display_name?.trim() || entry.username;
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
  loading = false,
  error = '',
  viewerUsername = null,
  onSelectPlayer,
}: Props) {
  const [sort, setSort] = useState<SortState>({
    key: 'rank',
    direction: 'asc',
  });

  const submittedEntries = useMemo(
    () => entries.filter((e) => e.submitted_at != null),
    [entries],
  );

  const ranks = useMemo(
    () => computeCompetitionRanks(submittedEntries),
    [submittedEntries],
  );

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

  const sortableColumns = columns.filter((col) => col.key !== 'top_four_picks');
  const sortOptions: { key: SortKey; label: string }[] = [
    { key: 'rank', label: 'Rank' },
    { key: 'player', label: 'Player' },
    { key: 'total', label: 'Total' },
    ...sortableColumns.map((col) => ({ key: col.key, label: col.name })),
  ];

  return (
    <div className="challenge-leaderboard">
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
            const statColumns = columns.filter((c) => c.key !== 'top_four_picks');
            const statSplitAt = Math.ceil(statColumns.length / 2);
            const statColumnsLeft = statColumns.slice(0, statSplitAt);
            const statColumnsRight = statColumns.slice(statSplitAt);

            function renderStat(col: LeaderboardColumn) {
              const value =
                col.key === 'potential'
                  ? row.potential
                  : row.stage_scores[col.key];
              return (
                <div key={col.key} className="leaderboard-card__stat">
                  <dt>{col.name}</dt>
                  <dd>{value != null ? value : '—'}</dd>
                </div>
              );
            }

            return (
              <li
                key={row.user_bracket_id}
                className={`leaderboard-card ${leaderboardRowClassName(rank, isViewer)}`}
              >
                <div className="leaderboard-card__head">
                  <span className="leaderboard-card__rank">{rank}</span>
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
                      {row.score != null ? row.score : '—'}
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
              col.key === 'top_four_picks' ? (
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
                {ranks.get(row.user_bracket_id)}
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
                {row.score != null ? row.score : '—'}
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
                const value =
                  col.key === 'potential'
                    ? row.potential
                    : row.stage_scores[col.key];
                return (
                  <td key={col.key} className="is-num">
                    {value != null ? value : '—'}
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
