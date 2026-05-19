import { useMemo, useState } from 'react';

import type { LeaderboardColumn, LeaderboardEntry } from '../../utils/api';

import './ChallengeLeaderboard.css';

type SortKey = 'rank' | 'player' | 'total' | string;

type SortState = {
  key: SortKey;
  direction: 'asc' | 'desc';
};

type Props = {
  columns: LeaderboardColumn[];
  entries: LeaderboardEntry[];
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
      return a.username.localeCompare(b.username, undefined, {
        sensitivity: 'base',
      });
    }
    if (a.score == null) return 1;
    if (b.score == null) return -1;
    const diff = b.score - a.score;
    if (diff !== 0) return diff;
    return a.username.localeCompare(b.username, undefined, {
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
    result = a.username.localeCompare(b.username, undefined, {
      sensitivity: 'base',
    });
  } else if (key === 'total') {
    result = compareWithNullsLast(a.score, b.score, direction);
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
  align?: 'left' | 'right';
}) {
  const active = sort.key === sortKey;
  const ariaSort = active
    ? sort.direction === 'asc'
      ? 'ascending'
      : 'descending'
    : 'none';

  return (
    <th
      scope="col"
      className={align === 'right' ? 'is-num' : undefined}
      aria-sort={ariaSort}
    >
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

export function ChallengeLeaderboard({ columns, entries }: Props) {
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
      return a.username.localeCompare(b.username, undefined, {
        sensitivity: 'base',
      });
    });
    return rows;
  }, [submittedEntries, sort, ranks]);

  if (submittedEntries.length === 0) {
    return <p className="challenge-view__muted">No submitted brackets yet.</p>;
  }

  return (
    <div className="challenge-leaderboard">
      <table className="data-table challenge-leaderboard__table">
        <thead>
          <tr>
            <SortableHeader
              label="#"
              sortKey="rank"
              sort={sort}
              onSort={onSort}
              align="right"
            />
            <SortableHeader
              label="Player"
              sortKey="player"
              sort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label="Total"
              sortKey="total"
              sort={sort}
              onSort={onSort}
              align="right"
            />
            {columns.map((col) => (
              <SortableHeader
                key={col.key}
                label={col.name}
                sortKey={col.key}
                sort={sort}
                onSort={onSort}
                align="right"
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedEntries.map((row) => (
            <tr key={row.user_bracket_id}>
              <td className="is-rank is-num">
                {ranks.get(row.user_bracket_id)}
              </td>
              <td>{row.username}</td>
              <td className="is-num">
                {row.score != null ? row.score : '—'}
              </td>
              {columns.map((col) => {
                const stageScore = row.stage_scores[col.key];
                return (
                  <td key={col.key} className="is-num">
                    {stageScore != null ? stageScore : '—'}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
