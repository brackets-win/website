import { Fragment, useMemo, useState, type CSSProperties } from 'react';

import type {
  ChallengeStats,
  ChallengeStatsGroupEntry,
  ChallengeStatsKnockoutRow,
  ChallengeStatsProgressionBucket,
  LeaderboardColumn,
} from '../../utils/api';

import { BracketDistribution } from './BracketDistribution';

import './ChallengeStats.css';

type Props = {
  stats: ChallengeStats;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
  bracketId?: number;
  masterUserBracketId?: number | null;
};

type KnockoutSortKey = 'team' | string;

type SortState = {
  key: KnockoutSortKey;
  direction: 'asc' | 'desc';
};

type StatsSubtab = 'teams' | 'groups' | 'knockout';

const SUBTAB_LABELS: Record<StatsSubtab, string> = {
  teams: 'Teams',
  groups: 'Groups',
  knockout: 'Knockout',
};

function TeamChip({
  displayName,
  imageUrl,
}: {
  displayName: string;
  imageUrl: string | null;
}) {
  return (
    <span className="challenge-stats__chip">
      {imageUrl ? (
        <img
          className="challenge-stats__chip-img"
          src={imageUrl}
          alt=""
        />
      ) : (
        <span className="challenge-stats__chip-img challenge-stats__chip-img--ph">
          {displayName.charAt(0)}
        </span>
      )}
      <span className="challenge-stats__chip-name">{displayName}</span>
    </span>
  );
}

type NamedEntry = {
  user_bracket_id: number;
  display_name: string;
  username?: string;
};

function EntryNames({
  entries,
  onSelectPlayer,
  viewerUsername,
}: {
  entries: NamedEntry[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <>
      {entries.map((entry, i) => {
        const isViewer =
          viewerUsername != null && entry.username === viewerUsername;
        const nameClass = isViewer
          ? 'challenge-stats__group-points-name challenge-stats__entry-name--viewer'
          : 'challenge-stats__group-points-name';
        return (
          <span
            key={entry.user_bracket_id}
            className="challenge-stats__group-points-name-wrap"
          >
            {onSelectPlayer ? (
              <button
                type="button"
                className={`${nameClass} challenge-stats__group-points-name--btn`}
                onClick={() =>
                  onSelectPlayer(entry.user_bracket_id, entry.display_name)
                }
              >
                {entry.display_name}
              </button>
            ) : (
              <span className={nameClass}>{entry.display_name}</span>
            )}
            {i < entries.length - 1 ? <span aria-hidden>, </span> : null}
          </span>
        );
      })}
    </>
  );
}

function ProgressionList({
  buckets,
  onSelectPlayer,
  viewerUsername,
}: {
  buckets: ChallengeStatsProgressionBucket[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  if (buckets.length === 0) {
    return (
      <p className="challenge-stats__group-points-empty">No entries yet.</p>
    );
  }
  return (
    <ul className="challenge-stats__prog-list">
      {buckets.map((bucket) => (
        <li key={bucket.key} className="challenge-stats__prog-row">
          <span className="challenge-stats__prog-label">{bucket.label}</span>
          <span className="challenge-stats__prog-names">
            <EntryNames
              entries={bucket.entries}
              onSelectPlayer={onSelectPlayer}
              viewerUsername={viewerUsername}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

function formatAverage(avg: number | null): string {
  if (avg == null) return '—';
  return Number(avg.toFixed(2)).toString();
}

// Green → Yellow → Orange → Red ramp for the avg-place "prediction surprise" pill.
const GYOR_STOPS: [number, number, number][] = [
  [34, 197, 94], // green  (predicted exactly right)
  [234, 179, 8], // yellow
  [249, 115, 22], // orange
  [239, 68, 68], // red    (predicted the opposite end of the group)
];

// Pill background opacity. The hue carries the meaning, so a perfect prediction
// reads clearly green and the biggest miss clearly red. Tune for subtlety.
const GYOR_ALPHA = 0.85;

function gyorRgb(t: number): [number, number, number] {
  const clamped = Math.min(1, Math.max(0, t));
  const segments = GYOR_STOPS.length - 1;
  const scaled = clamped * segments;
  const i = Math.min(segments - 1, Math.floor(scaled));
  const f = scaled - i;
  const [r1, g1, b1] = GYOR_STOPS[i];
  const [r2, g2, b2] = GYOR_STOPS[i + 1];
  return [
    Math.round(r1 + (r2 - r1) * f),
    Math.round(g1 + (g2 - g1) * f),
    Math.round(b1 + (b2 - b1) * f),
  ];
}

/**
 * Pill coloring for the avg-place number, based on how far a team's average
 * predicted place sits from its actual (master-bracket) placement, normalized
 * by the max possible gap (teamsInGroup - 1) so groups of different sizes stay
 * comparable. No pill until the master bracket has placed the team.
 */
function groupAvgPillStyle(
  masterPosition: number | null,
  averagePosition: number | null,
  teamsInGroup: number,
): CSSProperties | undefined {
  if (masterPosition == null || averagePosition == null || teamsInGroup <= 1) {
    return undefined;
  }
  // Normalized [0, 1]: 0 = predicted exactly right, 1 = predicted the opposite
  // end of the group. In a group of 4 this maps 1-vs-1→green, 1-vs-2→yellow,
  // 1-vs-3→orange, 1-vs-4→red.
  const t = Math.min(
    1,
    Math.abs(masterPosition - averagePosition) / (teamsInGroup - 1),
  );
  const [r, g, b] = gyorRgb(t);
  const textColor = relativeLuminance(r, g, b) < 0.5 ? '#fff' : '#1f2937';
  return {
    backgroundColor: `rgba(${r}, ${g}, ${b}, ${GYOR_ALPHA})`,
    color: textColor,
  };
}

type GroupDifficulty = {
  label: string;
  level: 'easy' | 'medium' | 'hard';
};

/** Difficulty from avg/max points: more points earned = easier group. */
function groupDifficulty(
  avgPoints: number | null,
  maxPoints: number,
): GroupDifficulty | null {
  if (avgPoints == null || maxPoints <= 0) return null;
  const ratio = avgPoints / maxPoints;
  if (ratio >= 0.6) return { label: 'Easy', level: 'easy' };
  if (ratio >= 0.35) return { label: 'Medium', level: 'medium' };
  return { label: 'Hard', level: 'hard' };
}

type PointsBucket = {
  points: number;
  entries: ChallengeStatsGroupEntry[];
};

/** Group entries (pre-sorted by points desc, then name) by their points value. */
function bucketEntriesByPoints(
  entries: ChallengeStatsGroupEntry[],
): PointsBucket[] {
  const buckets: PointsBucket[] = [];
  for (const entry of entries) {
    const last = buckets[buckets.length - 1];
    if (last && last.points === entry.points) {
      last.entries.push(entry);
    } else {
      buckets.push({ points: entry.points, entries: [entry] });
    }
  }
  return buckets;
}

function formatPct(value: number): string {
  if (value === 0) return '0%';
  if (value === 100) return '100%';
  return `${value % 1 === 0 ? value.toFixed(0) : value.toFixed(1)}%`;
}

function formatProgression(value: number): string {
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
}

function formatMobileStatLabel(name: string, key: string): string {
  if (key === 'progression_score') return 'Progression Score';
  if (/third place/i.test(name)) return 'Third Place';
  return name;
}

const BRACKET_HEAT_RGB = [87, 130, 168] as const;

function linearizeChannel(c: number): number {
  c /= 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(r: number, g: number, b: number): number {
  return (
    0.2126 * linearizeChannel(r) +
    0.7152 * linearizeChannel(g) +
    0.0722 * linearizeChannel(b)
  );
}

function mixedHeatRgb(pct: number): [number, number, number] {
  const t = pct / 100;
  return BRACKET_HEAT_RGB.map((channel) =>
    Math.round(channel * t + 255 * (1 - t)),
  ) as [number, number, number];
}

function pctCellStyle(value: number): CSSProperties {
  const pct = Math.min(100, Math.max(0, value));
  const [r, g, b] = mixedHeatRgb(pct);
  const bgLum = relativeLuminance(r, g, b);
  return {
    '--pct': pct,
    // Heat-map style: white once the fill is visibly saturated (incl. 100%).
    color: bgLum < 0.45 ? '#fff' : undefined,
  } as CSSProperties;
}

function defaultKnockoutDirection(key: KnockoutSortKey): 'asc' | 'desc' {
  if (key === 'team') return 'asc';
  return 'desc';
}

function compareKnockoutRows(
  a: ChallengeStatsKnockoutRow,
  b: ChallengeStatsKnockoutRow,
  sort: SortState,
): number {
  const { key, direction } = sort;
  let result = 0;

  if (key === 'team') {
    result = a.display_name.localeCompare(b.display_name, undefined, {
      sensitivity: 'base',
    });
  } else {
    if (key === 'progression_score') {
      result = a.progression_score - b.progression_score;
      return direction === 'asc' ? result : -result;
    }
    result = (a.percentages[key] ?? 0) - (b.percentages[key] ?? 0);
    return direction === 'asc' ? result : -result;
  }

  return direction === 'asc' ? result : -result;
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  align = 'center',
}: {
  label: string;
  sortKey: KnockoutSortKey;
  sort: SortState;
  onSort: (key: KnockoutSortKey) => void;
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
      ? 'challenge-stats__ko-team-th'
      : 'is-num';

  return (
    <th scope="col" className={thClass} aria-sort={ariaSort}>
      <button
        type="button"
        className={
          active
            ? 'challenge-stats__th-btn challenge-stats__th-btn--active'
            : 'challenge-stats__th-btn'
        }
        onClick={() => onSort(sortKey)}
      >
        <span>{label}</span>
        <span className="challenge-stats__sort-icon" aria-hidden>
          {active ? (sort.direction === 'asc' ? '↑' : '↓') : '↕'}
        </span>
      </button>
    </th>
  );
}

export function ChallengeStats({
  stats,
  onSelectPlayer,
  viewerUsername,
  bracketId,
  masterUserBracketId,
}: Props) {
  const { submitted_count, group_stage, knockout, bracket } = stats;
  const bracketSlotCount = Object.keys(bracket?.slots ?? {}).length;
  const hasTeams = knockout.columns.length > 0;
  const hasGroups = group_stage.length > 0;
  const hasKnockout = bracketSlotCount > 0 && bracketId != null;
  const availableSubtabs = useMemo<StatsSubtab[]>(() => {
    const tabs: StatsSubtab[] = [];
    if (hasTeams) tabs.push('teams');
    if (hasGroups) tabs.push('groups');
    if (hasKnockout) tabs.push('knockout');
    return tabs;
  }, [hasTeams, hasGroups, hasKnockout]);
  const [activeSubtab, setActiveSubtab] = useState<StatsSubtab>('teams');
  const currentSubtab = availableSubtabs.includes(activeSubtab)
    ? activeSubtab
    : availableSubtabs[0];
  const [sort, setSort] = useState<SortState>({
    key: 'progression_score',
    direction: 'desc',
  });
  const [groupsExpanded, setGroupsExpanded] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(
    () => new Set(),
  );

  function toggleGroups() {
    setGroupsExpanded((prev) => !prev);
  }

  function toggleRow(id: number) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  const sortedKnockoutRows = useMemo(() => {
    const rows = [...knockout.rows];
    rows.sort((a, b) => {
      const primary = compareKnockoutRows(a, b, sort);
      if (primary !== 0) return primary;
      return a.display_name.localeCompare(b.display_name, undefined, {
        sensitivity: 'base',
      });
    });
    return rows;
  }, [knockout.rows, sort]);

  const mobileStatColumns = useMemo(
    () => knockout.columns.filter((col) => col.key !== 'progression_score'),
    [knockout.columns],
  );

  function renderMobileKnockoutStat(
    row: ChallengeStatsKnockoutRow,
    col: LeaderboardColumn,
  ) {
    const pct = row.percentages[col.key] ?? 0;
    return (
      <div
        key={col.key}
        className="challenge-stats__ko-card-stat challenge-stats__ko-card-stat--pct"
        style={pctCellStyle(pct)}
      >
        <dt>{formatMobileStatLabel(col.name, col.key)}</dt>
        <dd>{formatPct(pct)}</dd>
      </div>
    );
  }

  function onSort(key: KnockoutSortKey) {
    setSort((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { key, direction: defaultKnockoutDirection(key) };
    });
  }

  if (submitted_count === 0) {
    return (
      <p className="challenge-view__muted">
        Stats appear once players submit brackets.
      </p>
    );
  }

  return (
    <div className="challenge-stats">
      <p className="challenge-stats__meta">
        Stats based on {submitted_count} submitted{' '}
        {submitted_count === 1 ? 'bracket' : 'brackets'}
      </p>

      {availableSubtabs.length > 1 ? (
        <nav
          className="challenge-stats__subtabs"
          role="tablist"
          aria-label="Stats sections"
        >
          {availableSubtabs.map((subtab) => (
            <button
              key={subtab}
              type="button"
              role="tab"
              aria-selected={currentSubtab === subtab}
              className={
                currentSubtab === subtab
                  ? 'challenge-stats__subtab challenge-stats__subtab--active'
                  : 'challenge-stats__subtab'
              }
              onClick={() => setActiveSubtab(subtab)}
            >
              {SUBTAB_LABELS[subtab]}
            </button>
          ))}
        </nav>
      ) : null}

      {currentSubtab === 'groups' && hasGroups ? (
        <section className="challenge-stats__section">
          <h2 className="challenge-stats__heading">Groups</h2>
          <p className="challenge-stats__section-note">
            Average group placement predictions. Click on a group name to expand
            with average points earned per group, group difficulty, and points
            earned by each bracket entry.
          </p>
          <div className="challenge-stats__group-grid">
            {group_stage.map((group) => {
              const expanded = groupsExpanded;
              return (
                <div key={group.code} className="challenge-stats__group-card">
                  <button
                    type="button"
                    className="challenge-stats__group-head-row challenge-stats__group-toggle"
                    aria-expanded={expanded}
                    onClick={toggleGroups}
                  >
                    <span className="challenge-stats__group-head">
                      <span
                        className="challenge-stats__group-chevron"
                        aria-hidden
                      >
                        {expanded ? '▾' : '▸'}
                      </span>
                      Group {group.code}
                    </span>
                    <span className="challenge-stats__group-avg-label">
                      Avg Place
                    </span>
                  </button>
                  <div className="challenge-stats__group-teams">
                    {group.teams.map((team, index) => (
                      <div
                        key={team.bracket_contestant_id}
                        className="challenge-stats__group-row"
                      >
                        <span className="challenge-stats__group-rank">
                          {index + 1}
                        </span>
                        <TeamChip
                          displayName={team.display_name}
                          imageUrl={team.image_url}
                        />
                        {(() => {
                          const pill = groupAvgPillStyle(
                            team.master_position,
                            team.average_position,
                            group.teams.length,
                          );
                          return (
                            <span
                              className={
                                pill
                                  ? 'challenge-stats__group-avg challenge-stats__group-avg--pill'
                                  : 'challenge-stats__group-avg'
                              }
                              style={pill}
                              title={`${team.pick_count} picks`}
                            >
                              {formatAverage(team.average_position)}
                            </span>
                          );
                        })()}
                      </div>
                    ))}
                  </div>
                  {expanded ? (
                    <div className="challenge-stats__group-points">
                      <div className="challenge-stats__group-points-summary">
                        <div className="challenge-stats__group-points-stat">
                          <div className="challenge-stats__group-points-stat-top">
                            <span className="challenge-stats__group-points-stat-label">
                              Avg Points
                            </span>
                            {(() => {
                              const difficulty = groupDifficulty(
                                group.avg_points,
                                group.max_points,
                              );
                              if (!difficulty) return null;
                              return (
                                <span
                                  className={`challenge-stats__group-difficulty challenge-stats__group-difficulty--${difficulty.level}`}
                                >
                                  {difficulty.label}
                                </span>
                              );
                            })()}
                          </div>
                          <span className="challenge-stats__group-points-stat-value">
                            {formatAverage(group.avg_points)}
                            <span className="challenge-stats__group-points-stat-max">
                              {' '}
                              / {group.max_points}
                            </span>
                          </span>
                        </div>
                      </div>
                      {group.entries.length > 0 ? (
                        <ul className="challenge-stats__group-points-list">
                          {bucketEntriesByPoints(group.entries).map(
                            (bucket) => (
                              <li
                                key={bucket.points}
                                className="challenge-stats__group-points-row"
                              >
                                <span className="challenge-stats__group-points-pts">
                                  {bucket.points}
                                </span>
                                <span className="challenge-stats__group-points-names">
                                  <EntryNames
                                    entries={bucket.entries}
                                    onSelectPlayer={onSelectPlayer}
                                    viewerUsername={viewerUsername}
                                  />
                                </span>
                              </li>
                            ),
                          )}
                        </ul>
                      ) : (
                        <p className="challenge-stats__group-points-empty">
                          No entries yet.
                        </p>
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {currentSubtab === 'teams' && hasTeams ? (
        <section className="challenge-stats__section">
          <h2 className="challenge-stats__heading">Teams</h2>
          <p className="challenge-stats__section-note">
            Predicted progression percentages by team. Click on a team name to
            expand with predicted progression by each bracket entry.
          </p>
          <div className="challenge-stats__ko-mobile">
            <div
              className="challenge-stats__sort-bar"
              role="group"
              aria-label="Sort knockout stats"
            >
              <button
                type="button"
                className={
                  sort.key === 'team'
                    ? 'challenge-stats__sort-pill challenge-stats__sort-pill--active'
                    : 'challenge-stats__sort-pill'
                }
                onClick={() => onSort('team')}
              >
                Team
              </button>
              {knockout.columns.map((col) => (
                <button
                  key={col.key}
                  type="button"
                  className={
                    sort.key === col.key
                      ? 'challenge-stats__sort-pill challenge-stats__sort-pill--active'
                      : 'challenge-stats__sort-pill'
                  }
                  onClick={() => onSort(col.key)}
                >
                  {formatMobileStatLabel(col.name, col.key)}
                </button>
              ))}
            </div>
            <ol className="challenge-stats__ko-cards">
              {sortedKnockoutRows.map((row) => {
                const rowExpanded = expandedRows.has(row.bracket_contestant_id);
                return (
                  <li
                    key={row.bracket_contestant_id}
                    className="challenge-stats__ko-card"
                  >
                    <button
                      type="button"
                      className="challenge-stats__ko-card-head challenge-stats__ko-card-toggle"
                      aria-expanded={rowExpanded}
                      onClick={() => toggleRow(row.bracket_contestant_id)}
                    >
                      <span className="challenge-stats__ko-card-head-team">
                        <span
                          className="challenge-stats__group-chevron"
                          aria-hidden
                        >
                          {rowExpanded ? '▾' : '▸'}
                        </span>
                        <TeamChip
                          displayName={row.display_name}
                          imageUrl={row.image_url}
                        />
                      </span>
                      <span
                        className="challenge-stats__ko-card-score"
                        aria-label={`Progression score ${formatProgression(row.progression_score)}`}
                      >
                        {formatProgression(row.progression_score)}
                      </span>
                    </button>
                    {mobileStatColumns.length > 0 ? (
                      <dl className="challenge-stats__ko-card-stats">
                        {mobileStatColumns.map((col) =>
                          renderMobileKnockoutStat(row, col),
                        )}
                      </dl>
                    ) : null}
                    {rowExpanded ? (
                      <div className="challenge-stats__ko-card-prog">
                        <ProgressionList
                          buckets={row.progression}
                          onSelectPlayer={onSelectPlayer}
                          viewerUsername={viewerUsername}
                        />
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          </div>
          <div className="challenge-stats__ko-scroll challenge-stats__ko-desktop">
            <table className="data-table challenge-stats__ko-table">
              <thead>
                <tr>
                  <SortableHeader
                    label="Team"
                    sortKey="team"
                    sort={sort}
                    onSort={onSort}
                    align="left"
                  />
                  {knockout.columns.map((col) => (
                    <SortableHeader
                      key={col.key}
                      label={col.name}
                      sortKey={col.key}
                      sort={sort}
                      onSort={onSort}
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedKnockoutRows.map((row) => {
                  const rowExpanded = expandedRows.has(
                    row.bracket_contestant_id,
                  );
                  return (
                    <Fragment key={row.bracket_contestant_id}>
                      <tr
                        className="challenge-stats__ko-row challenge-stats__ko-row--clickable"
                        aria-expanded={rowExpanded}
                        onClick={() => toggleRow(row.bracket_contestant_id)}
                      >
                        <td className="challenge-stats__ko-team">
                          <span className="challenge-stats__ko-team-cell">
                            <span
                              className="challenge-stats__group-chevron"
                              aria-hidden
                            >
                              {rowExpanded ? '▾' : '▸'}
                            </span>
                            <TeamChip
                              displayName={row.display_name}
                              imageUrl={row.image_url}
                            />
                          </span>
                        </td>
                        {knockout.columns.map((col) => {
                          if (col.key === 'progression_score') {
                            return (
                              <td
                                key={col.key}
                                className="is-num challenge-stats__ko-pct"
                              >
                                {formatProgression(row.progression_score)}
                              </td>
                            );
                          }
                          const pct = row.percentages[col.key] ?? 0;
                          return (
                            <td
                              key={col.key}
                              className="is-num challenge-stats__ko-pct"
                              style={pctCellStyle(pct)}
                            >
                              {formatPct(pct)}
                            </td>
                          );
                        })}
                      </tr>
                      {rowExpanded ? (
                        <tr className="challenge-stats__ko-prog-row">
                          <td colSpan={knockout.columns.length + 1}>
                            <ProgressionList
                              buckets={row.progression}
                              onSelectPlayer={onSelectPlayer}
                              viewerUsername={viewerUsername}
                            />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {currentSubtab === 'knockout' && hasKnockout && bracketId != null ? (
        <section className="challenge-stats__section">
          <h2 className="challenge-stats__heading">Knockout</h2>
          <p className="challenge-stats__section-note">
            Percentage of prediction entries that placed teams in each knockout
            spot. Correct result is highlighted in green.
          </p>
          <BracketDistribution
            bracketId={bracketId}
            masterUserBracketId={masterUserBracketId ?? null}
            slots={bracket.slots}
          />
        </section>
      ) : null}
    </div>
  );
}
