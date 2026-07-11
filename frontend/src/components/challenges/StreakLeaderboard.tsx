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
  | 'streak_record'
  | 'streak_win_pct'
  | 'knockout_record'
  | 'knockout_win_pct'
  | 'consolation_record'
  | 'consolation_win_pct'
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

type KnockoutSection = {
  label: string;
  recordKey: StreakSortKey;
  winPctKey: StreakSortKey;
  record: (entry: StreakLeaderboardEntry) => string;
  winPct: (entry: StreakLeaderboardEntry) => number;
};

const KNOCKOUT_SECTIONS: KnockoutSection[] = [
  {
    label: 'Streak',
    recordKey: 'streak_record',
    winPctKey: 'streak_win_pct',
    record: (e) => e.streak_record,
    winPct: (e) => e.streak_win_pct,
  },
  {
    label: 'Knockout',
    recordKey: 'knockout_record',
    winPctKey: 'knockout_win_pct',
    record: (e) => e.knockout_record,
    winPct: (e) => e.knockout_win_pct,
  },
  {
    label: 'Consolation',
    recordKey: 'consolation_record',
    winPctKey: 'consolation_win_pct',
    record: (e) => e.consolation_record,
    winPct: (e) => e.consolation_win_pct,
  },
  {
    label: 'Total',
    recordKey: 'total_record',
    winPctKey: 'total_win_pct',
    record: (e) => e.total_record,
    winPct: (e) => e.total_win_pct,
  },
];

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

function compareConsolationStandings(
  a: StreakLeaderboardEntry,
  b: StreakLeaderboardEntry,
  direction: 'asc' | 'desc',
): number {
  let result = compareNumeric(a.consolation_wins, b.consolation_wins, direction);
  if (result !== 0) return result;
  result = compareNumeric(a.consolation_win_pct, b.consolation_win_pct, direction);
  if (result !== 0) return result;
  result = compareNumeric(a.rank, b.rank, 'asc');
  if (result !== 0) return result;
  return playerLabel(a).localeCompare(playerLabel(b), undefined, {
    sensitivity: 'base',
  });
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
  } else if (key === 'streak_record') {
    result = compareNumeric(a.streak_wins, b.streak_wins, direction);
    return result;
  } else if (key === 'streak_win_pct') {
    result = compareNumeric(a.streak_win_pct, b.streak_win_pct, direction);
    return result;
  } else if (key === 'knockout_record') {
    result = compareNumeric(a.knockout_wins, b.knockout_wins, direction);
    return result;
  } else if (key === 'knockout_win_pct') {
    result = compareNumeric(a.knockout_win_pct, b.knockout_win_pct, direction);
    return result;
  } else if (key === 'consolation_record') {
    return compareConsolationStandings(a, b, direction);
  } else if (key === 'consolation_win_pct') {
    let result = compareNumeric(
      a.consolation_win_pct,
      b.consolation_win_pct,
      direction,
    );
    if (result !== 0) return result;
    result = compareNumeric(a.consolation_wins, b.consolation_wins, direction);
    if (result !== 0) return result;
    result = compareNumeric(a.rank, b.rank, 'asc');
    if (result !== 0) return result;
    return playerLabel(a).localeCompare(playerLabel(b), undefined, {
      sensitivity: 'base',
    });
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
  sectionDivider = false,
}: {
  label: string;
  sortKey: StreakSortKey;
  sort: SortState;
  onSort: (key: StreakSortKey) => void;
  sectionDivider?: boolean;
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
      className={
        sectionDivider
          ? 'is-num streak-leaderboard__section-divider'
          : 'is-num'
      }
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

const SORT_OPTIONS: {
  key: StreakSortKey;
  label: string;
  mobileLabel?: string;
}[] = [
  { key: 'rank', label: '#', mobileLabel: 'Rank' },
  { key: 'player', label: 'Player' },
  { key: 'long_w', label: 'Best' },
  { key: 'current', label: 'Current' },
  { key: 'long_l', label: 'Worst' },
  { key: 'record', label: 'Record' },
  { key: 'win_pct', label: 'Win %' },
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
  { key: 'long_l', label: 'Worst' },
  { key: 'streak_record', label: 'Streak W-L', mobileLabel: 'Streak' },
  { key: 'streak_win_pct', label: 'Streak %', mobileLabel: 'Streak %' },
  { key: 'knockout_record', label: 'Knockout W-L', mobileLabel: 'KO' },
  { key: 'knockout_win_pct', label: 'Knockout %', mobileLabel: 'KO %' },
  {
    key: 'consolation_record',
    label: 'Consolation W-L',
    mobileLabel: 'Cons.',
  },
  {
    key: 'consolation_win_pct',
    label: 'Consolation %',
    mobileLabel: 'Cons. %',
  },
  { key: 'total_record', label: 'Total W-L', mobileLabel: 'Total' },
  { key: 'total_win_pct', label: 'Total %', mobileLabel: 'Total %' },
];

function FixedHeader({
  label,
  sortKey,
  sort,
  onSort,
  className = 'is-num',
}: {
  label: string;
  sortKey: StreakSortKey;
  sort: SortState;
  onSort: (key: StreakSortKey) => void;
  className?: string;
}) {
  const active = sort.key === sortKey;
  const ariaSort = active
    ? sort.direction === 'asc'
      ? 'ascending'
      : 'descending'
    : 'none';

  return (
    <th scope="col" rowSpan={2} className={className} aria-sort={ariaSort}>
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
                      <dt>Worst</dt>
                      <dd>{e.long_loss_display}</dd>
                    </div>
                    {isKnockout ? (
                      KNOCKOUT_SECTIONS.map((section) => (
                        <Fragment key={section.label}>
                          <div className="leaderboard-card__stat">
                            <dt>{section.label} W-L</dt>
                            <dd>{section.record(e)}</dd>
                          </div>
                          <div className="leaderboard-card__stat">
                            <dt>{section.label} %</dt>
                            <dd>{section.winPct(e)}%</dd>
                          </div>
                        </Fragment>
                      ))
                    ) : (
                      <>
                        <div className="leaderboard-card__stat">
                          <dt>Record</dt>
                          <dd>{e.record}</dd>
                        </div>
                        <div className="leaderboard-card__stat">
                          <dt>Win %</dt>
                          <dd>{e.win_pct}%</dd>
                        </div>
                      </>
                    )}
                  </dl>
                </li>
              </Fragment>
            );
          })}
        </ol>
      </div>
      <div className="table-scroll streak-leaderboard__desktop">
        <table
          className={
            isKnockout
              ? 'data-table streak-leaderboard__table streak-leaderboard__table--knockout'
              : 'data-table streak-leaderboard__table'
          }
        >
          {isKnockout ? (
            <colgroup>
              <col className="streak-leaderboard__col-rank" />
              <col className="streak-leaderboard__col-player" />
              <col className="streak-leaderboard__col-streak-stat" />
              <col className="streak-leaderboard__col-streak-stat" />
              <col className="streak-leaderboard__col-streak-stat" />
              {KNOCKOUT_SECTIONS.flatMap((section) => [
                <col
                  key={`${section.label}-record`}
                  className="streak-leaderboard__col-section"
                />,
                <col
                  key={`${section.label}-pct`}
                  className="streak-leaderboard__col-section"
                />,
              ])}
            </colgroup>
          ) : null}
          <thead>
            {isKnockout ? (
              <>
                <tr className="streak-leaderboard__section-row">
                  <FixedHeader
                    label="#"
                    sortKey="rank"
                    sort={sort}
                    onSort={onSort}
                  />
                  <FixedHeader
                    label="Player"
                    sortKey="player"
                    sort={sort}
                    onSort={onSort}
                    className="is-player"
                  />
                  <FixedHeader
                    label="Best"
                    sortKey="long_w"
                    sort={sort}
                    onSort={onSort}
                  />
                  <FixedHeader
                    label="Current"
                    sortKey="current"
                    sort={sort}
                    onSort={onSort}
                  />
                  <FixedHeader
                    label="Worst"
                    sortKey="long_l"
                    sort={sort}
                    onSort={onSort}
                  />
                  {KNOCKOUT_SECTIONS.map((section) => (
                    <th
                      key={section.label}
                      scope="colgroup"
                      colSpan={2}
                      className="streak-leaderboard__section-label streak-leaderboard__section-divider"
                    >
                      {section.label}
                    </th>
                  ))}
                </tr>
                <tr>
                  {KNOCKOUT_SECTIONS.map((section) => (
                    <Fragment key={section.label}>
                      <SortableHeader
                        label="W-L"
                        sortKey={section.recordKey}
                        sort={sort}
                        onSort={onSort}
                        sectionDivider
                      />
                      <SortableHeader
                        label="%"
                        sortKey={section.winPctKey}
                        sort={sort}
                        onSort={onSort}
                      />
                    </Fragment>
                  ))}
                </tr>
              </>
            ) : (
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
                    <span
                      className="challenge-leaderboard__sort-icon"
                      aria-hidden
                    >
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
                  label="Worst"
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
                  label="Win %"
                  sortKey="win_pct"
                  sort={sort}
                  onSort={onSort}
                />
              </tr>
            )}
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
                  <td className="is-num">{e.long_loss_display}</td>
                  {isKnockout ? (
                    KNOCKOUT_SECTIONS.map((section) => (
                      <Fragment key={section.label}>
                        <td className="is-num streak-leaderboard__section-divider">
                          {section.record(e)}
                        </td>
                        <td className="is-num">{section.winPct(e)}%</td>
                      </Fragment>
                    ))
                  ) : (
                    <>
                      <td className="is-num">{e.record}</td>
                      <td className="is-num">{e.win_pct}%</td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
