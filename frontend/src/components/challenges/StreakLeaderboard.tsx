import { useMemo, useState } from 'react';

import type { StreakLeaderboardEntry } from '../../utils/api';
import {
  computeCompetitionRanks,
  leaderboardRowClassName,
} from '../../utils/leaderboardRows';

import './ChallengeLeaderboard.css';

type StreakSortKey =
  | 'rank'
  | 'player'
  | 'current'
  | 'long_w'
  | 'long_l'
  | 'record'
  | 'win_pct';

type SortState = {
  key: StreakSortKey;
  direction: 'asc' | 'desc';
};

type Props = {
  entries: StreakLeaderboardEntry[];
  viewerUserId: number;
  onSelectPlayer: (userId: number, displayName: string) => void;
};

function playerLabel(entry: StreakLeaderboardEntry): string {
  return entry.display_name?.trim() || entry.username;
}

function defaultStreakStatsCompare(
  a: StreakLeaderboardEntry,
  b: StreakLeaderboardEntry,
): number {
  if (b.best_win_streak !== a.best_win_streak) {
    return b.best_win_streak - a.best_win_streak;
  }
  if (b.streak_signed !== a.streak_signed) {
    return b.streak_signed - a.streak_signed;
  }
  if (b.wins !== a.wins) {
    return b.wins - a.wins;
  }
  if (b.win_pct !== a.win_pct) {
    return b.win_pct - a.win_pct;
  }
  return 0;
}

function defaultDirection(key: StreakSortKey): 'asc' | 'desc' {
  if (key === 'player' || key === 'rank') return 'asc';
  return 'desc';
}

function compareNumeric(
  a: number,
  b: number,
  direction: 'asc' | 'desc',
): number {
  const diff = a - b;
  return direction === 'asc' ? diff : -diff;
}

function compareEntries(
  a: StreakLeaderboardEntry,
  b: StreakLeaderboardEntry,
  sort: SortState,
  ranks: Map<number, number>,
): number {
  const { key, direction } = sort;
  let result = 0;

  if (key === 'rank') {
    const rankA = ranks.get(a.user_id) ?? Number.MAX_SAFE_INTEGER;
    const rankB = ranks.get(b.user_id) ?? Number.MAX_SAFE_INTEGER;
    result = rankA - rankB;
  } else if (key === 'player') {
    result = playerLabel(a).localeCompare(playerLabel(b), undefined, {
      sensitivity: 'base',
    });
  } else if (key === 'current') {
    result = compareNumeric(a.streak_signed, b.streak_signed, direction);
    return result;
  } else if (key === 'long_w') {
    result = compareNumeric(a.best_win_streak, b.best_win_streak, direction);
    return result;
  } else if (key === 'long_l') {
    result = compareNumeric(a.best_loss_streak, b.best_loss_streak, direction);
    return result;
  } else if (key === 'record') {
    result = compareNumeric(a.wins, b.wins, direction);
    return result;
  } else if (key === 'win_pct') {
    result = compareNumeric(a.win_pct, b.win_pct, direction);
    return result;
  }

  return direction === 'asc' ? result : -result;
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: StreakSortKey;
  sort: SortState;
  onSort: (key: StreakSortKey) => void;
}) {
  const active = sort.key === sortKey;
  const ariaSort = active
    ? sort.direction === 'asc'
      ? 'ascending'
      : 'descending'
    : 'none';

  return (
    <th scope="col" className="is-num" aria-sort={ariaSort}>
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

const SORT_OPTIONS: {
  key: StreakSortKey;
  label: string;
  mobileLabel?: string;
}[] = [
  { key: 'rank', label: '#', mobileLabel: 'Rank' },
  { key: 'player', label: 'Player' },
  { key: 'current', label: 'Current' },
  { key: 'long_w', label: 'Long W' },
  { key: 'long_l', label: 'Long L' },
  { key: 'record', label: 'Record' },
  { key: 'win_pct', label: 'Win %' },
];

export function StreakLeaderboard({
  entries,
  viewerUserId,
  onSelectPlayer,
}: Props) {
  const [sort, setSort] = useState<SortState>({
    key: 'rank',
    direction: 'asc',
  });

  const ranks = useMemo(
    () =>
      computeCompetitionRanks(entries, defaultStreakStatsCompare, (e) => e.user_id),
    [entries],
  );

  function onSort(key: StreakSortKey) {
    setSort((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { key, direction: defaultDirection(key) };
    });
  }

  const sortedEntries = useMemo(() => {
    const rows = [...entries];
    rows.sort((a, b) => {
      const primary = compareEntries(a, b, sort, ranks);
      if (primary !== 0) return primary;
      const rankA = ranks.get(a.user_id) ?? Number.MAX_SAFE_INTEGER;
      const rankB = ranks.get(b.user_id) ?? Number.MAX_SAFE_INTEGER;
      if (rankA !== rankB) return rankA - rankB;
      return playerLabel(a).localeCompare(playerLabel(b), undefined, {
        sensitivity: 'base',
      });
    });
    return rows;
  }, [entries, sort, ranks]);

  if (entries.length === 0) {
    return <p className="streak-view__muted">No players yet.</p>;
  }

  return (
    <>
      <div className="streak-leaderboard__mobile">
        <div
          className="challenge-leaderboard__sort-bar"
          role="group"
          aria-label="Sort leaderboard"
        >
          {SORT_OPTIONS.map((opt) => (
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
              {opt.mobileLabel ?? opt.label}
            </button>
          ))}
        </div>
        <ol className="leaderboard-cards">
          {sortedEntries.map((e) => {
            const rank = ranks.get(e.user_id)!;
            const isViewer = e.user_id === viewerUserId;
            return (
              <li
                key={e.user_id}
                className={`leaderboard-card ${leaderboardRowClassName(rank, isViewer)}`}
              >
                <div className="leaderboard-card__head">
                  <span className="leaderboard-card__rank">{rank}</span>
                  <button
                    type="button"
                    className="streak-leaderboard__player leaderboard-card__name"
                    onClick={() => onSelectPlayer(e.user_id, playerLabel(e))}
                  >
                    {playerLabel(e)}
                  </button>
                  <div>
                    <span className="leaderboard-card__total-label">Current</span>
                    <span className="leaderboard-card__total">{e.current_display}</span>
                  </div>
                </div>
                <dl className="leaderboard-card__stats leaderboard-card__stats--column-major">
                  <div className="leaderboard-card__stat">
                    <dt>Long W</dt>
                    <dd>{e.long_win_display}</dd>
                  </div>
                  <div className="leaderboard-card__stat">
                    <dt>Long L</dt>
                    <dd>{e.long_loss_display}</dd>
                  </div>
                  <div className="leaderboard-card__stat">
                    <dt>Record</dt>
                    <dd>{e.record}</dd>
                  </div>
                  <div className="leaderboard-card__stat">
                    <dt>Win %</dt>
                    <dd>{e.win_pct}%</dd>
                  </div>
                </dl>
              </li>
            );
          })}
        </ol>
      </div>
      <div className="table-scroll streak-leaderboard__desktop">
        <table className="data-table streak-leaderboard__table">
          <thead>
            <tr>
              <SortableHeader
                label="#"
                sortKey="rank"
                sort={sort}
                onSort={onSort}
              />
              <th scope="col" className="is-player">
                <button
                  type="button"
                  className={
                    sort.key === 'player'
                      ? 'challenge-leaderboard__th-btn challenge-leaderboard__th-btn--active'
                      : 'challenge-leaderboard__th-btn'
                  }
                  onClick={() => onSort('player')}
                >
                  <span>Player</span>
                  <span className="challenge-leaderboard__sort-icon" aria-hidden>
                    {sort.key === 'player'
                      ? sort.direction === 'asc'
                        ? '↑'
                        : '↓'
                      : '↕'}
                  </span>
                </button>
              </th>
              <SortableHeader
                label="Current"
                sortKey="current"
                sort={sort}
                onSort={onSort}
              />
              <SortableHeader
                label="Long W"
                sortKey="long_w"
                sort={sort}
                onSort={onSort}
              />
              <SortableHeader
                label="Long L"
                sortKey="long_l"
                sort={sort}
                onSort={onSort}
              />
              <SortableHeader
                label="Record"
                sortKey="record"
                sort={sort}
                onSort={onSort}
              />
              <SortableHeader
                label="WIN %"
                sortKey="win_pct"
                sort={sort}
                onSort={onSort}
              />
            </tr>
          </thead>
          <tbody>
            {sortedEntries.map((e) => {
              const rank = ranks.get(e.user_id)!;
              const isViewer = e.user_id === viewerUserId;
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
                      onClick={() => onSelectPlayer(e.user_id, playerLabel(e))}
                    >
                      {playerLabel(e)}
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
    </>
  );
}
