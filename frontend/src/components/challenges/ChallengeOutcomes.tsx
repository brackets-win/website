import type {
  ChallengeOutcomesChampionBranch,
  ChallengeOutcomesEntry,
  ChallengeOutcomesWinnerOdds,
  ChallengeStatsSimilarityTeam,
} from '../../utils/api';
import { ContestantAvatar } from '../bracket/ContestantAvatar';

import './BracketSimilarity.css';
import './ChallengeOutcomes.css';
import './ChallengeStats.css';

type Props = {
  hasThirdPlace: boolean;
  winnerOdds: ChallengeOutcomesWinnerOdds[];
  tree: ChallengeOutcomesChampionBranch[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
};

type RawRow = {
  runnerUp: ChallengeStatsSimilarityTeam;
  third?: ChallengeStatsSimilarityTeam;
  fourth?: ChallengeStatsSimilarityTeam;
  semifinalists?: [ChallengeStatsSimilarityTeam, ChallengeStatsSimilarityTeam];
  winners: ChallengeOutcomesEntry[];
};

type DisplayRow = {
  runnerUpTeams: ChallengeStatsSimilarityTeam[];
  thirdTeams: ChallengeStatsSimilarityTeam[];
  fourthTeams: ChallengeStatsSimilarityTeam[];
  semiTeams: ChallengeStatsSimilarityTeam[];
  winners: ChallengeOutcomesEntry[];
  outcomeCount: number;
};

type WinnerGroup = {
  winners: ChallengeOutcomesEntry[];
  totalOutcomes: number;
  rows: DisplayRow[];
};

type TableRow = DisplayRow & {
  showWinnerCell: boolean;
  winnerRowSpan: number;
  showRuCell: boolean;
  ruRowSpan: number;
};

function teamSortKey(team: ChallengeStatsSimilarityTeam): string {
  return team.display_name.toLocaleLowerCase();
}

function sortTeams(teams: Iterable<ChallengeStatsSimilarityTeam>): ChallengeStatsSimilarityTeam[] {
  return [...teams].sort((a, b) =>
    teamSortKey(a).localeCompare(teamSortKey(b), undefined, { sensitivity: 'base' }),
  );
}

function teamSetKey(teams: ChallengeStatsSimilarityTeam[]): string {
  return teams
    .map((team) => team.bracket_contestant_id)
    .sort((a, b) => a - b)
    .join(',');
}

function winnerEntryKey(winners: ChallengeOutcomesEntry[]): string {
  return winners
    .map((entry) => entry.user_bracket_id)
    .sort((a, b) => a - b)
    .join(',');
}

function collectRawRows(
  champ: ChallengeOutcomesChampionBranch,
  hasThirdPlace: boolean,
): RawRow[] {
  const rows: RawRow[] = [];
  for (const ru of champ.children) {
    if (hasThirdPlace) {
      for (const third of ru.children) {
        for (const fourth of third.children) {
          for (const leaf of fourth.children) {
            rows.push({
              runnerUp: ru.team,
              third: third.team,
              fourth: fourth.team,
              winners: leaf.winners,
            });
          }
        }
      }
    } else {
      for (const third of ru.children) {
        const fourth = third.children[0];
        if (!fourth) continue;
        for (const leaf of fourth.children) {
          rows.push({
            runnerUp: ru.team,
            semifinalists: [third.team, fourth.team],
            winners: leaf.winners,
          });
        }
      }
    }
  }
  return rows;
}

function teamIds(teams: ChallengeStatsSimilarityTeam[]): Set<number> {
  return new Set(teams.map((team) => team.bracket_contestant_id));
}

function isExhaustiveCluster(
  teams: ChallengeStatsSimilarityTeam[],
  universe: ChallengeStatsSimilarityTeam[],
): boolean {
  if (teams.length <= 1 || universe.length <= 1) return false;
  return teamSetKey(teams) === teamSetKey(universe);
}

function remainingRunnerUps(allRaw: RawRow[]): ChallengeStatsSimilarityTeam[] {
  return dedupeTeams(allRaw.map((row) => row.runnerUp));
}

function remainingThirds(
  allRaw: RawRow[],
  runnerUpTeams: ChallengeStatsSimilarityTeam[],
): ChallengeStatsSimilarityTeam[] {
  const ruIds = teamIds(runnerUpTeams);
  return dedupeTeams(
    allRaw
      .filter((row) => ruIds.has(row.runnerUp.bracket_contestant_id) && row.third)
      .map((row) => row.third!),
  );
}

function remainingFourths(
  allRaw: RawRow[],
  runnerUpTeams: ChallengeStatsSimilarityTeam[],
  thirdTeams: ChallengeStatsSimilarityTeam[],
): ChallengeStatsSimilarityTeam[] {
  const ruIds = teamIds(runnerUpTeams);
  const thirdIds = teamIds(thirdTeams);
  return dedupeTeams(
    allRaw
      .filter(
        (row) =>
          ruIds.has(row.runnerUp.bracket_contestant_id) &&
          row.third &&
          thirdIds.has(row.third.bracket_contestant_id) &&
          row.fourth,
      )
      .map((row) => row.fourth!),
  );
}

function remainingSemiTeams(
  allRaw: RawRow[],
  runnerUpTeams: ChallengeStatsSimilarityTeam[],
): ChallengeStatsSimilarityTeam[] {
  const ruIds = teamIds(runnerUpTeams);
  const teams: ChallengeStatsSimilarityTeam[] = [];
  for (const row of allRaw) {
    if (!ruIds.has(row.runnerUp.bracket_contestant_id) || !row.semifinalists) continue;
    teams.push(...row.semifinalists);
  }
  return dedupeTeams(teams);
}

function dedupeTeams(teams: ChallengeStatsSimilarityTeam[]): ChallengeStatsSimilarityTeam[] {
  const byId = new Map<number, ChallengeStatsSimilarityTeam>();
  for (const team of teams) {
    byId.set(team.bracket_contestant_id, team);
  }
  return sortTeams(byId.values());
}

function outcomeKey(raw: RawRow, hasThirdPlace: boolean): string {
  if (hasThirdPlace) {
    return `${raw.runnerUp.bracket_contestant_id}|${raw.third!.bracket_contestant_id}|${raw.fourth!.bracket_contestant_id}`;
  }
  const semiKey = sortTeams(raw.semifinalists!)
    .map((team) => team.bracket_contestant_id)
    .join('+');
  return `${raw.runnerUp.bracket_contestant_id}|${semiKey}`;
}

function outcomeMatchesRow(
  raw: RawRow,
  row: DisplayRow,
  hasThirdPlace: boolean,
): boolean {
  const ruIds = new Set(row.runnerUpTeams.map((team) => team.bracket_contestant_id));
  if (!ruIds.has(raw.runnerUp.bracket_contestant_id)) return false;

  if (hasThirdPlace) {
    const thirdIds = new Set(row.thirdTeams.map((team) => team.bracket_contestant_id));
    const fourthIds = new Set(row.fourthTeams.map((team) => team.bracket_contestant_id));
    return (
      thirdIds.has(raw.third!.bracket_contestant_id) &&
      fourthIds.has(raw.fourth!.bracket_contestant_id)
    );
  }

  const semiIds = new Set(row.semiTeams.map((team) => team.bracket_contestant_id));
  return raw.semifinalists!.every((team) => semiIds.has(team.bracket_contestant_id));
}

function representedOutcomeKeys(
  row: DisplayRow,
  group: RawRow[],
  hasThirdPlace: boolean,
): Set<string> {
  const keys = new Set<string>();
  for (const raw of group) {
    if (outcomeMatchesRow(raw, row, hasThirdPlace)) {
      keys.add(outcomeKey(raw, hasThirdPlace));
    }
  }
  return keys;
}

function setsEqual<T>(left: Set<T>, right: Set<T>): boolean {
  if (left.size !== right.size) return false;
  for (const value of left) {
    if (!right.has(value)) return false;
  }
  return true;
}

function atomicDisplayRow(raw: RawRow): DisplayRow {
  return {
    runnerUpTeams: [raw.runnerUp],
    thirdTeams: raw.third ? [raw.third] : [],
    fourthTeams: raw.fourth ? [raw.fourth] : [],
    semiTeams: raw.semifinalists ? sortTeams(raw.semifinalists) : [],
    winners: raw.winners,
    outcomeCount: 1,
  };
}

function mergeTeamRows(left: DisplayRow, right: DisplayRow): DisplayRow {
  return {
    runnerUpTeams: dedupeTeams([...left.runnerUpTeams, ...right.runnerUpTeams]),
    thirdTeams: dedupeTeams([...left.thirdTeams, ...right.thirdTeams]),
    fourthTeams: dedupeTeams([...left.fourthTeams, ...right.fourthTeams]),
    semiTeams: dedupeTeams([...left.semiTeams, ...right.semiTeams]),
    winners: left.winners,
    outcomeCount: left.outcomeCount + right.outcomeCount,
  };
}

function finalizeDisplayRow(
  row: DisplayRow,
  group: RawRow[],
  hasThirdPlace: boolean,
): DisplayRow {
  return {
    ...row,
    outcomeCount: representedOutcomeKeys(row, group, hasThirdPlace).size,
  };
}

function sortDisplayRows(rows: DisplayRow[], hasThirdPlace: boolean): DisplayRow[] {
  return rows.sort((a, b) => {
    const ruCmp = teamSortKey(a.runnerUpTeams[0]).localeCompare(
      teamSortKey(b.runnerUpTeams[0]),
      undefined,
      { sensitivity: 'base' },
    );
    if (ruCmp !== 0) return ruCmp;
    if (!hasThirdPlace) return 0;
    return teamSortKey(a.thirdTeams[0]).localeCompare(
      teamSortKey(b.thirdTeams[0]),
      undefined,
      { sensitivity: 'base' },
    );
  });
}

function buildDisplayRows(group: RawRow[], hasThirdPlace: boolean): DisplayRow[] {
  if (group.length === 0) return [];

  let rows = group.map((raw) => atomicDisplayRow(raw));

  let changed = true;
  while (changed) {
    changed = false;
    outer: for (let i = 0; i < rows.length; i++) {
      for (let j = i + 1; j < rows.length; j++) {
        const merged = mergeTeamRows(rows[i], rows[j]);
        const mergedKeys = representedOutcomeKeys(merged, group, hasThirdPlace);
        const unionKeys = new Set([
          ...representedOutcomeKeys(rows[i], group, hasThirdPlace),
          ...representedOutcomeKeys(rows[j], group, hasThirdPlace),
        ]);
        if (!setsEqual(mergedKeys, unionKeys)) continue;

        rows = [
          ...rows.slice(0, i),
          ...rows.slice(i + 1, j),
          ...rows.slice(j + 1),
          finalizeDisplayRow(merged, group, hasThirdPlace),
        ];
        changed = true;
        break outer;
      }
    }
  }

  return sortDisplayRows(
    rows.map((row) => finalizeDisplayRow(row, group, hasThirdPlace)),
    hasThirdPlace,
  );
}

function buildWinnerGroups(rawRows: RawRow[], hasThirdPlace: boolean): WinnerGroup[] {
  const byWinner = new Map<string, RawRow[]>();
  for (const row of rawRows) {
    const key = winnerEntryKey(row.winners);
    const bucket = byWinner.get(key) ?? [];
    bucket.push(row);
    byWinner.set(key, bucket);
  }

  const groups: WinnerGroup[] = [];
  for (const group of byWinner.values()) {
    groups.push({
      winners: group[0].winners,
      totalOutcomes: group.length,
      rows: buildDisplayRows(group, hasThirdPlace),
    });
  }

  return groups.sort((a, b) => b.totalOutcomes - a.totalOutcomes);
}

function flattenTableRows(groups: WinnerGroup[]): TableRow[] {
  const flat: TableRow[] = [];

  for (const group of groups) {
    const rows = group.rows;
    rows.forEach((row, rowIndex) => {
      const showRu =
        rowIndex === 0 || teamSetKey(rows[rowIndex - 1].runnerUpTeams) !== teamSetKey(row.runnerUpTeams);
      let ruSpan = 1;
      if (showRu) {
        for (let i = rowIndex + 1; i < rows.length; i++) {
          if (teamSetKey(rows[i].runnerUpTeams) !== teamSetKey(row.runnerUpTeams)) break;
          ruSpan++;
        }
      }

      flat.push({
        ...row,
        showWinnerCell: rowIndex === 0,
        winnerRowSpan: rows.length,
        showRuCell: showRu,
        ruRowSpan: ruSpan,
      });
    });
  }

  return flat;
}

function teamHasImage(team: ChallengeStatsSimilarityTeam): boolean {
  return Boolean(team.image_url?.trim());
}

function TeamFlag({
  team,
  size,
}: {
  team: ChallengeStatsSimilarityTeam;
  size: 'lg' | 'md' | 'sm' | 'xs';
}) {
  const showName = !teamHasImage(team);
  return (
    <div
      className={[
        'challenge-stats__sim-flag',
        `challenge-stats__sim-flag--${size}`,
        showName ? '' : 'challenge-stats__sim-flag--image-only',
      ]
        .filter(Boolean)
        .join(' ')}
      title={team.display_name}
    >
      <ContestantAvatar
        displayName={team.display_name}
        imageUrl={team.image_url}
        className="challenge-stats__sim-flag-img"
        placeholderClassName="challenge-stats__sim-flag-img challenge-stats__sim-flag-img--ph"
      />
      {showName ? (
        <span className="challenge-stats__sim-flag-name">{team.display_name}</span>
      ) : null}
    </div>
  );
}

function TeamCluster({
  teams,
  singleSize = 'sm',
}: {
  teams: ChallengeStatsSimilarityTeam[];
  singleSize?: 'lg' | 'md' | 'sm' | 'xs';
}) {
  const sorted = sortTeams(teams);
  if (sorted.length === 0) return null;
  if (sorted.length === 1) {
    return <TeamFlag team={sorted[0]} size={singleSize} />;
  }
  return (
    <div
      className="challenge-outcomes__team-cluster"
      title={sorted.map((team) => team.display_name).join(', ')}
    >
      {sorted.map((team) => (
        <TeamFlag key={team.bracket_contestant_id} team={team} size="xs" />
      ))}
    </div>
  );
}

function AllPill({
  label,
  size = 'sm',
}: {
  label: string;
  size?: 'md' | 'sm';
}) {
  return (
    <span
      className={[
        'challenge-outcomes__all-pill',
        size === 'md' ? 'challenge-outcomes__all-pill--md' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      title={label}
    >
      ALL
    </span>
  );
}

function PlacementCell({
  teams,
  universe,
  singleSize = 'sm',
  allLabel,
}: {
  teams: ChallengeStatsSimilarityTeam[];
  universe: ChallengeStatsSimilarityTeam[];
  singleSize?: 'lg' | 'md' | 'sm' | 'xs';
  allLabel: string;
}) {
  const sorted = sortTeams(teams);
  if (sorted.length === 0) return null;
  if (isExhaustiveCluster(sorted, universe)) {
    return <AllPill label={allLabel} size={singleSize === 'md' ? 'md' : 'sm'} />;
  }
  return <TeamCluster teams={sorted} singleSize={singleSize} />;
}

function WinnerList({
  winners,
  onSelectPlayer,
  viewerUsername,
}: {
  winners: ChallengeOutcomesEntry[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <ul className="challenge-stats__sim-entries challenge-outcomes__entries">
      {winners.map((entry, index) => {
        const isViewer =
          viewerUsername != null && entry.username === viewerUsername;
        const nameClass = isViewer
          ? 'challenge-stats__group-points-name challenge-stats__entry-name--viewer'
          : 'challenge-stats__group-points-name';
        return (
          <li key={entry.user_bracket_id}>
            {index > 0 ? (
              <span className="challenge-stats__sim-entry-sep" aria-hidden>
                ,{' '}
              </span>
            ) : null}
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
          </li>
        );
      })}
    </ul>
  );
}

function WinnerOddsTable({
  winnerOdds,
  onSelectPlayer,
  viewerUsername,
}: {
  winnerOdds: ChallengeOutcomesWinnerOdds[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  if (winnerOdds.length === 0) return null;

  return (
    <article className="challenge-stats__sim-card challenge-outcomes__summary-card">
      <div className="challenge-stats__sim-scroll">
        <table className="challenge-stats__sim-table challenge-outcomes__summary-table">
          <colgroup>
            <col />
            <col className="challenge-outcomes__summary-col--pct" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col">Winner</th>
              <th scope="col" className="challenge-outcomes__summary-th--pct">
                % of Outcomes
              </th>
            </tr>
          </thead>
          <tbody>
            {winnerOdds.map((row) => (
              <tr key={winnerEntryKey(row.entries)}>
                <td className="challenge-outcomes__summary-winner">
                  <WinnerList
                    winners={row.entries}
                    onSelectPlayer={onSelectPlayer}
                    viewerUsername={viewerUsername}
                  />
                </td>
                <td className="challenge-outcomes__summary-pct">
                  {row.pct.toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function rowDividerLevel(rows: TableRow[], rowIndex: number): number {
  if (rowIndex === 0) return 0;
  const prev = rows[rowIndex - 1];
  const curr = rows[rowIndex];
  if (winnerEntryKey(prev.winners) !== winnerEntryKey(curr.winners)) return 4;
  if (teamSetKey(prev.runnerUpTeams) !== teamSetKey(curr.runnerUpTeams)) return 3;
  return 1;
}

function ChampionTable({
  champ,
  champRawRows,
  rows,
  hasThirdPlace,
  onSelectPlayer,
  viewerUsername,
}: {
  champ: ChallengeOutcomesChampionBranch;
  champRawRows: RawRow[];
  rows: TableRow[];
  hasThirdPlace: boolean;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  const ruUniverse = remainingRunnerUps(champRawRows);

  return (
    <div className="challenge-stats__sim-scroll">
      <table
        className={[
          'challenge-stats__sim-table',
          'challenge-outcomes__table',
          hasThirdPlace ? '' : 'challenge-stats__sim--no-third',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <colgroup>
          <col className="challenge-stats__sim-col challenge-stats__sim-col--champ challenge-outcomes__col--champ" />
          <col className="challenge-stats__sim-col challenge-stats__sim-col--ru challenge-outcomes__col--placement" />
          {hasThirdPlace ? (
            <>
              <col className="challenge-stats__sim-col challenge-stats__sim-col--third challenge-outcomes__col--placement" />
              <col className="challenge-stats__sim-col challenge-stats__sim-col--fourth challenge-outcomes__col--placement" />
            </>
          ) : (
            <col className="challenge-stats__sim-col challenge-stats__sim-col--semi challenge-outcomes__col--placement" />
          )}
          <col className="challenge-stats__sim-col challenge-stats__sim-col--entries challenge-outcomes__col--winner" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Champion</th>
            <th scope="col">Runner-Up</th>
            {hasThirdPlace ? (
              <>
                <th scope="col">Third Place</th>
                <th scope="col">Fourth Place</th>
              </>
            ) : (
              <th scope="col">Semi Final</th>
            )}
            <th scope="col" className="challenge-stats__sim-th--entries">
              Winner
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={`${teamSetKey(row.runnerUpTeams)}-${teamSetKey(row.thirdTeams)}-${teamSetKey(row.fourthTeams)}-${teamSetKey(row.semiTeams)}-w:${winnerEntryKey(row.winners)}`}
              className={
                rowDividerLevel(rows, rowIndex) > 0
                  ? `challenge-stats__sim-row challenge-stats__sim-row--div-${rowDividerLevel(rows, rowIndex)}`
                  : 'challenge-stats__sim-row'
              }
            >
              {rowIndex === 0 ? (
                <td rowSpan={rows.length} className="challenge-stats__sim-td--champ">
                  <TeamFlag team={champ.team} size="lg" />
                </td>
              ) : null}
              {row.showRuCell ? (
                <td rowSpan={row.ruRowSpan}>
                  <PlacementCell
                    teams={row.runnerUpTeams}
                    universe={ruUniverse}
                    singleSize="md"
                    allLabel="Any remaining runner-up"
                  />
                </td>
              ) : null}
              {hasThirdPlace ? (
                <>
                  <td>
                    <PlacementCell
                      teams={row.thirdTeams}
                      universe={remainingThirds(champRawRows, row.runnerUpTeams)}
                      allLabel="Any remaining third-place team"
                    />
                  </td>
                  <td>
                    <PlacementCell
                      teams={row.fourthTeams}
                      universe={remainingFourths(
                        champRawRows,
                        row.runnerUpTeams,
                        row.thirdTeams,
                      )}
                      allLabel="Any remaining fourth-place team"
                    />
                  </td>
                </>
              ) : (
                <td>
                  <PlacementCell
                    teams={row.semiTeams}
                    universe={remainingSemiTeams(champRawRows, row.runnerUpTeams)}
                    singleSize="sm"
                    allLabel="Any remaining semi-finalist"
                  />
                </td>
              )}
              {row.showWinnerCell ? (
                <td
                  rowSpan={row.winnerRowSpan}
                  className="challenge-stats__sim-td--entries challenge-outcomes__td--winner"
                >
                  <WinnerList
                    winners={row.winners}
                    onSelectPlayer={onSelectPlayer}
                    viewerUsername={viewerUsername}
                  />
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChallengeOutcomes({
  hasThirdPlace,
  winnerOdds,
  tree,
  onSelectPlayer,
  viewerUsername,
}: Props) {
  if (tree.length === 0) {
    return (
      <p className="challenge-stats__group-points-empty">
        No remaining outcomes to show yet.
      </p>
    );
  }

  return (
    <div className="challenge-outcomes__layout">
      <aside className="challenge-outcomes__summary">
        <WinnerOddsTable
          winnerOdds={winnerOdds}
          onSelectPlayer={onSelectPlayer}
          viewerUsername={viewerUsername}
        />
      </aside>
      <div
        className={[
          'challenge-outcomes__detail',
          'challenge-stats__sim',
          hasThirdPlace ? '' : 'challenge-stats__sim--no-third',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <div className="challenge-stats__sim-cards">
          {tree.map((champ) => {
            const champRawRows = collectRawRows(champ, hasThirdPlace);
            const groups = buildWinnerGroups(champRawRows, hasThirdPlace);
            const rows = flattenTableRows(groups);
            if (rows.length === 0) return null;
            return (
              <article
                key={champ.team.bracket_contestant_id}
                className="challenge-stats__sim-card"
              >
                <ChampionTable
                  champ={champ}
                  champRawRows={champRawRows}
                  rows={rows}
                  hasThirdPlace={hasThirdPlace}
                  onSelectPlayer={onSelectPlayer}
                  viewerUsername={viewerUsername}
                />
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}
