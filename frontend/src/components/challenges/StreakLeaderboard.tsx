import { Fragment, useMemo, useState } from 'react';

import type { StreakLeaderboardEntry } from '../../utils/api';
import {
  computeCompetitionRanks,
  leaderboardRowClassName,
} from '../../utils/leaderboardRows';
import { streakEmoji } from '../../utils/challengeTypes';

import './ChallengeLeaderboard.css';

type StreakSortKey =
  | 'rank'
  | 'player'
  | 'current'
  | 'long_w'
  | 'long_l'
  | 'record'
  | 'win_pct'
  | 'season_record'
  | 'season_win_pct'
  | 'total_record'
  | 'total_win_pct';

type SortState = {
  key: StreakSortKey;
  direction: 'asc' | 'desc';
};

type Props = {
  entries: StreakLeaderboardEntry[];
  viewerUserId: number;
  onSelectPlayer: (userId: number, displayName: string) => void;
  isKnockout: boolean;
  knockoutCutoffCount: number | null;
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
  if (a.best_loss_streak !== b.best_loss_streak) {
    return a.best_loss_streak - b.best_loss_streak;
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
  } else if (key === 'season_record') {
    result = compareNumeric(a.season_wins, b.season_wins, direction);
    return result;
  } else if (key === 'season_win_pct') {
    result = compareNumeric(a.season_win_pct, b.season_win_pct, direction);
    return result;
  } else if (key === 'total_record') {
    result = compareNumeric(a.total_wins, b.total_wins, direction);
    return result;
  } else if (key === 'total_win_pct') {
    result = compareNumeric(a.total_win_pct, b.total_win_pct, direction);
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
  { key: 'long_w', label: 'Best' },
  { key: 'current', label: 'Current' },
  { key: 'record', label: 'Record' },
  { key: 'win_pct', label: 'Win %' },
  { key: 'long_l', label: 'Worst' },
];

const KNOCKOUT_SORT_OPTIONS: {
  key: StreakSortKey;
  label: string;
  mobileLabel?: string;
}[] = [
  { key: 'rank', label: '#', mobileLabel: 'Rank' },
  { key: 'player', label: 'Player' },
  { key: 'long_w', label: 'Best' },
  { key: 'current', label: 'Current' },
  { key: 'season_record', label: 'Season Record', mobileLabel: 'Season Rec' },
  { key: 'season_win_pct', label: 'Season Win %', mobileLabel: 'Season %' },
  { key: 'total_record', label: 'Total Record', mobileLabel: 'Total Rec' },
  { key: 'total_win_pct', label: 'Total Win %', mobileLabel: 'Total %' },
  { key: 'long_l', label: 'Worst' },
];

export function StreakLeaderboard({
  entries,
  viewerUserId,
  onSelectPlayer,
  isKnockout,
  knockoutCutoffCount,
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

  const sortOptions = isKnockout ? KNOCKOUT_SORT_OPTIONS : SORT_OPTIONS;
  const showCutoffDivider =
    knockoutCutoffCount != null &&
    sort.key === 'rank' &&
    knockoutCutoffCount > 0 &&
    knockoutCutoffCount < sortedEntries.length;

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
              {opt.mobileLabel ?? opt.label}
            </button>
          ))}
        </div>
        <ol
          className={
            showCutoffDivider
              ? 'leaderboard-cards leaderboard-cards--rank-grouped'
              : 'leaderboard-cards'
          }
        >
          {sortedEntries.map((e, index) => {
            const rank = ranks.get(e.user_id)!;
            const isViewer = e.user_id === viewerUserId;
            const activeStreakEmoji = streakEmoji(
              e.streak_signed,
              e.best_win_streak,
              e.broken_win_streak ?? 0,
            );
            return (
              <Fragment key={e.user_id}>
                {showCutoffDivider && index === knockoutCutoffCount ? (
                  <li className="streak-leaderboard__cutoff-divider" aria-hidden />
                ) : null}
                <li
                  className={`leaderboard-card ${leaderboardRowClassName(rank, isViewer)}`}
                >
                  <div className="leaderboard-card__head">
                    <span className="leaderboard-card__rank">{rank}</span>
                    <button
                      type="button"
                      className="streak-leaderboard__player leaderboard-card__name"
                      onClick={() => onSelectPlayer(e.user_id, playerLabel(e))}
                    >
                      {playerLabel(e)}{activeStreakEmoji ? (
                        <span
                          className="streak-leaderboard__name-emoji"
                          aria-hidden
                        >
                          {activeStreakEmoji}
                        </span>
                      ) : null}
                    </button>
                    <div className="leaderboard-card__hero">
                      <span className="leaderboard-card__total-label">Best</span>
                      <span className="leaderboard-card__total">
                        {e.long_win_display}
                      </span>
                    </div>
                  </div>
                  <dl className="leaderboard-card__stats leaderboard-card__stats--column-major">
                    <div className="leaderboard-card__stat">
                      <dt>Current</dt>
                      <dd>{e.current_display}</dd>
                    </div>
                    <div className="leaderboard-card__stat">
                      <dt>{isKnockout ? 'Season Record' : 'Record'}</dt>
                      <dd>{isKnockout ? e.season_record : e.record}</dd>
                    </div>
                    <div className="leaderboard-card__stat">
                      <dt>Worst</dt>
                      <dd>{e.long_loss_display}</dd>
                    </div>
                    <div className="leaderboard-card__stat">
                      <dt>{isKnockout ? 'Season Win %' : 'Win %'}</dt>
                      <dd>{isKnockout ? e.season_win_pct : e.win_pct}%</dd>
                    </div>
                    {isKnockout ? (
                      <>
                        <div className="leaderboard-card__stat">
                          <dt>Total Record</dt>
                          <dd>{e.total_record}</dd>
                        </div>
                        <div className="leaderboard-card__stat">
                          <dt>Total Win %</dt>
                          <dd>{e.total_win_pct}%</dd>
                        </div>
                      </>
                    ) : null}
                  </dl>
                </li>
              </Fragment>
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
                label="Best"
                sortKey="long_w"
                sort={sort}
                onSort={onSort}
              />
              <SortableHeader
                label="Current"
                sortKey="current"
                sort={sort}
                onSort={onSort}
              />
              <SortableHeader
                label={isKnockout ? 'Season Record' : 'Record'}
                sortKey={isKnockout ? 'season_record' : 'record'}
                sort={sort}
                onSort={onSort}
              />
              <SortableHeader
                label={isKnockout ? 'SEASON WIN %' : 'WIN %'}
                sortKey={isKnockout ? 'season_win_pct' : 'win_pct'}
                sort={sort}
                onSort={onSort}
              />
              {isKnockout ? (
                <>
                  <SortableHeader
                    label="Total Record"
                    sortKey="total_record"
                    sort={sort}
                    onSort={onSort}
                  />
                  <SortableHeader
                    label="TOTAL WIN %"
                    sortKey="total_win_pct"
                    sort={sort}
                    onSort={onSort}
                  />
                </>
              ) : null}
              <SortableHeader
                label="Worst"
                sortKey="long_l"
                sort={sort}
                onSort={onSort}
              />
            </tr>
          </thead>
          <tbody>
            {sortedEntries.map((e, index) => {
              const rank = ranks.get(e.user_id)!;
              const isViewer = e.user_id === viewerUserId;
              const activeStreakEmoji = streakEmoji(
                e.streak_signed,
                e.best_win_streak,
                e.broken_win_streak ?? 0,
              );
              const cutoffRowClass =
                showCutoffDivider && index === knockoutCutoffCount - 1
                  ? ' streak-leaderboard__cutoff-row'
                  : '';
              return (
                <tr
                  key={e.user_id}
                  className={`${leaderboardRowClassName(rank, isViewer)}${cutoffRowClass}`}
                >
                  <td className="is-num">{rank}</td>
                  <td className="is-player">
                    <button
                      type="button"
                      className="streak-leaderboard__player"
                      onClick={() => onSelectPlayer(e.user_id, playerLabel(e))}
                    >
                      {playerLabel(e)}{activeStreakEmoji ? (
                        <span
                          className="streak-leaderboard__name-emoji"
                          aria-hidden
                        >
                          {activeStreakEmoji}
                        </span>
                      ) : null}
                    </button>
                  </td>
                  <td className="is-num">{e.long_win_display}</td>
                  <td className="is-num">{e.current_display}</td>
                  <td className="is-num">
                    {isKnockout ? e.season_record : e.record}
                  </td>
                  <td className="is-num">
                    {isKnockout ? e.season_win_pct : e.win_pct}%
                  </td>
                  {isKnockout ? (
                    <>
                      <td className="is-num">{e.total_record}</td>
                      <td className="is-num">{e.total_win_pct}%</td>
                    </>
                  ) : null}
                  <td className="is-num">{e.long_loss_display}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
