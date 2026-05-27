import { useMemo, useState, type CSSProperties } from 'react';

import type { ChallengeStats, ChallengeStatsKnockoutRow } from '../../utils/api';

import './ChallengeStats.css';

type Props = {
  stats: ChallengeStats;
};

type KnockoutSortKey = 'team' | string;

type SortState = {
  key: KnockoutSortKey;
  direction: 'asc' | 'desc';
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

function formatAverage(avg: number | null): string {
  if (avg == null) return '—';
  return Number(avg.toFixed(2)).toString();
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

export function ChallengeStats({ stats }: Props) {
  const { submitted_count, group_stage, knockout } = stats;
  const [sort, setSort] = useState<SortState>({
    key: 'progression_score',
    direction: 'desc',
  });

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

      {group_stage.length > 0 ? (
        <section className="challenge-stats__section">
          <h2 className="challenge-stats__heading">Group Stage</h2>
          <div className="challenge-stats__group-grid">
            {group_stage.map((group) => (
              <div key={group.code} className="challenge-stats__group-card">
                <div className="challenge-stats__group-head-row">
                  <div className="challenge-stats__group-head">
                    Group {group.code}
                  </div>
                  <span className="challenge-stats__group-avg-label">Avg Place</span>
                </div>
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
                      <span
                        className="challenge-stats__group-avg"
                        title={`${team.pick_count} picks`}
                      >
                        {formatAverage(team.average_position)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {knockout.columns.length > 0 ? (
        <section className="challenge-stats__section">
          <h2 className="challenge-stats__heading">Knockout</h2>
          <div className="challenge-stats__ko-scroll">
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
                {sortedKnockoutRows.map((row) => (
                  <tr key={row.bracket_contestant_id}>
                    <td className="challenge-stats__ko-team">
                      <TeamChip
                        displayName={row.display_name}
                        imageUrl={row.image_url}
                      />
                    </td>
                    {knockout.columns.map((col) => {
                      if (col.key === 'progression_score') {
                        return (
                          <td key={col.key} className="is-num challenge-stats__ko-pct">
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
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}
