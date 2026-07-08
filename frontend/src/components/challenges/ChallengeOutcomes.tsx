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
  winner: ChallengeOutcomesEntry;
  outcomeCount: number;
};

type PlacementRow = {
  thirdTeams: ChallengeStatsSimilarityTeam[];
  fourthTeams: ChallengeStatsSimilarityTeam[];
  outcomeCount: number;
};

type SemiPlacementRow = {
  semiTeams: ChallengeStatsSimilarityTeam[];
  outcomeCount: number;
};

type EntryGroup = {
  winner: ChallengeOutcomesEntry;
  entryRows: RawRow[];
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

function dedupeTeams(teams: ChallengeStatsSimilarityTeam[]): ChallengeStatsSimilarityTeam[] {
  const byId = new Map<number, ChallengeStatsSimilarityTeam>();
  for (const team of teams) {
    byId.set(team.bracket_contestant_id, team);
  }
  return sortTeams(byId.values());
}

function teamSetKey(teams: ChallengeStatsSimilarityTeam[]): string {
  return teams
    .map((team) => team.bracket_contestant_id)
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

function expandRowsByEntry(champRows: RawRow[]): Map<number, RawRow[]> {
  const byEntry = new Map<number, RawRow[]>();
  for (const row of champRows) {
    for (const winner of row.winners) {
      const bucket = byEntry.get(winner.user_bracket_id) ?? [];
      bucket.push({ ...row, winners: [winner] });
      byEntry.set(winner.user_bracket_id, bucket);
    }
  }
  return byEntry;
}

function isExhaustiveCluster(
  teams: ChallengeStatsSimilarityTeam[],
  universe: ChallengeStatsSimilarityTeam[],
): boolean {
  if (teams.length <= 1 || universe.length <= 1) return false;
  return teamSetKey(teams) === teamSetKey(universe);
}

function thirdsForRunnerUpCluster(
  entryRows: RawRow[],
  runnerUpTeams: ChallengeStatsSimilarityTeam[],
): ChallengeStatsSimilarityTeam[] {
  const ruIds = new Set(runnerUpTeams.map((team) => team.bracket_contestant_id));
  return dedupeTeams(
    entryRows
      .filter((row) => ruIds.has(row.runnerUp.bracket_contestant_id) && row.third)
      .map((row) => row.third!),
  );
}

function fourthsForRunnerUpThirdCluster(
  entryRows: RawRow[],
  runnerUpTeams: ChallengeStatsSimilarityTeam[],
  thirdTeams: ChallengeStatsSimilarityTeam[],
): ChallengeStatsSimilarityTeam[] {
  const ruIds = new Set(runnerUpTeams.map((team) => team.bracket_contestant_id));
  const thirdIds = new Set(thirdTeams.map((team) => team.bracket_contestant_id));
  return dedupeTeams(
    entryRows
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

function semiTeamsForRunnerUpCluster(
  entryRows: RawRow[],
  runnerUpTeams: ChallengeStatsSimilarityTeam[],
): ChallengeStatsSimilarityTeam[] {
  const ruIds = new Set(runnerUpTeams.map((team) => team.bracket_contestant_id));
  const teams: ChallengeStatsSimilarityTeam[] = [];
  for (const row of entryRows) {
    if (!ruIds.has(row.runnerUp.bracket_contestant_id) || !row.semifinalists) continue;
    teams.push(...row.semifinalists);
  }
  return dedupeTeams(teams);
}

function placementSignature(placementRows: PlacementRow[]): string {
  return placementRows
    .map((row) => `${teamSetKey(row.thirdTeams)}:${teamSetKey(row.fourthTeams)}`)
    .join('|');
}

function semiPlacementSignature(placementRows: SemiPlacementRow[]): string {
  return placementRows.map((row) => teamSetKey(row.semiTeams)).join('|');
}

function buildPlacementRowsForRu(ruRows: RawRow[]): PlacementRow[] {
  const byThird = new Map<number, RawRow[]>();
  for (const row of ruRows) {
    if (!row.third || !row.fourth) continue;
    const thirdId = row.third.bracket_contestant_id;
    const bucket = byThird.get(thirdId) ?? [];
    bucket.push(row);
    byThird.set(thirdId, bucket);
  }

  const byFourthSignature = new Map<
    string,
    { thirdTeams: ChallengeStatsSimilarityTeam[]; fourthTeams: ChallengeStatsSimilarityTeam[]; outcomeCount: number }
  >();

  for (const thirdRows of byThird.values()) {
    const fourthTeams = dedupeTeams(thirdRows.map((row) => row.fourth!));
    const signature = teamSetKey(fourthTeams);
    const existing = byFourthSignature.get(signature);
    if (existing) {
      existing.thirdTeams.push(thirdRows[0].third!);
      existing.outcomeCount += thirdRows.length;
    } else {
      byFourthSignature.set(signature, {
        thirdTeams: [thirdRows[0].third!],
        fourthTeams,
        outcomeCount: thirdRows.length,
      });
    }
  }

  return [...byFourthSignature.values()]
    .map((group) => ({
      thirdTeams: dedupeTeams(group.thirdTeams),
      fourthTeams: group.fourthTeams,
      outcomeCount: group.outcomeCount,
    }))
    .sort((a, b) =>
      teamSortKey(a.thirdTeams[0]).localeCompare(teamSortKey(b.thirdTeams[0]), undefined, {
        sensitivity: 'base',
      }),
    );
}

function buildSemiPlacementRowsForRu(ruRows: RawRow[]): SemiPlacementRow[] {
  const bySemi = new Map<string, RawRow[]>();
  for (const row of ruRows) {
    if (!row.semifinalists) continue;
    const key = teamSetKey(sortTeams(row.semifinalists));
    const bucket = bySemi.get(key) ?? [];
    bucket.push(row);
    bySemi.set(key, bucket);
  }

  return [...bySemi.values()]
    .map((semiRows) => ({
      semiTeams: sortTeams(semiRows[0].semifinalists!),
      outcomeCount: semiRows.length,
    }))
    .sort((a, b) =>
      teamSortKey(a.semiTeams[0]).localeCompare(teamSortKey(b.semiTeams[0]), undefined, {
        sensitivity: 'base',
      }),
    );
}

function buildDisplayRows(entryRows: RawRow[], hasThirdPlace: boolean): DisplayRow[] {
  if (entryRows.length === 0) return [];

  const winner = entryRows[0].winners[0];
  const byRu = new Map<number, RawRow[]>();
  for (const row of entryRows) {
    const ruId = row.runnerUp.bracket_contestant_id;
    const bucket = byRu.get(ruId) ?? [];
    bucket.push(row);
    byRu.set(ruId, bucket);
  }

  const sortedRuIds = [...byRu.keys()].sort((a, b) => {
    const ruA = byRu.get(a)![0].runnerUp;
    const ruB = byRu.get(b)![0].runnerUp;
    return teamSortKey(ruA).localeCompare(teamSortKey(ruB), undefined, {
      sensitivity: 'base',
    });
  });

  if (!hasThirdPlace) {
    const bySignature = new Map<
      string,
      {
        runnerUpTeams: ChallengeStatsSimilarityTeam[];
        placementRows: SemiPlacementRow[];
      }
    >();

    for (const ruId of sortedRuIds) {
      const ruRows = byRu.get(ruId)!;
      const runnerUp = ruRows[0].runnerUp;
      const placementRows = buildSemiPlacementRowsForRu(ruRows);
      const signature = semiPlacementSignature(placementRows);
      const existing = bySignature.get(signature);
      if (existing) {
        existing.runnerUpTeams.push(runnerUp);
        existing.placementRows = existing.placementRows.map((row, index) => ({
          ...row,
          outcomeCount: row.outcomeCount + placementRows[index].outcomeCount,
        }));
      } else {
        bySignature.set(signature, {
          runnerUpTeams: [runnerUp],
          placementRows,
        });
      }
    }

    const rows: DisplayRow[] = [];
    for (const group of [...bySignature.values()].sort((a, b) =>
      teamSortKey(a.runnerUpTeams[0]).localeCompare(teamSortKey(b.runnerUpTeams[0]), undefined, {
        sensitivity: 'base',
      }),
    )) {
      const runnerUpTeams = dedupeTeams(group.runnerUpTeams);
      for (const placement of group.placementRows) {
        rows.push({
          runnerUpTeams,
          thirdTeams: [],
          fourthTeams: [],
          semiTeams: placement.semiTeams,
          winner,
          outcomeCount: placement.outcomeCount,
        });
      }
    }
    return rows;
  }

  const bySignature = new Map<
    string,
    {
      runnerUpTeams: ChallengeStatsSimilarityTeam[];
      placementRows: PlacementRow[];
    }
  >();

  for (const ruId of sortedRuIds) {
    const ruRows = byRu.get(ruId)!;
    const runnerUp = ruRows[0].runnerUp;
    const placementRows = buildPlacementRowsForRu(ruRows);
    const signature = placementSignature(placementRows);
    const existing = bySignature.get(signature);
    if (existing) {
      existing.runnerUpTeams.push(runnerUp);
      existing.placementRows = existing.placementRows.map((row, index) => ({
        ...row,
        outcomeCount: row.outcomeCount + placementRows[index].outcomeCount,
      }));
    } else {
      bySignature.set(signature, {
        runnerUpTeams: [runnerUp],
        placementRows,
      });
    }
  }

  const rows: DisplayRow[] = [];
  for (const group of [...bySignature.values()].sort((a, b) =>
    teamSortKey(a.runnerUpTeams[0]).localeCompare(teamSortKey(b.runnerUpTeams[0]), undefined, {
      sensitivity: 'base',
    }),
  )) {
    const runnerUpTeams = dedupeTeams(group.runnerUpTeams);
    for (const placement of group.placementRows) {
      rows.push({
        runnerUpTeams,
        thirdTeams: placement.thirdTeams,
        fourthTeams: placement.fourthTeams,
        semiTeams: [],
        winner,
        outcomeCount: placement.outcomeCount,
      });
    }
  }

  return rows;
}

function buildEntryGroups(champRows: RawRow[], hasThirdPlace: boolean): EntryGroup[] {
  const byEntry = expandRowsByEntry(champRows);
  const groups: EntryGroup[] = [];

  for (const entryRows of byEntry.values()) {
    const winner = entryRows[0].winners[0];
    groups.push({
      winner,
      entryRows,
      rows: buildDisplayRows(entryRows, hasThirdPlace),
    });
  }

  return groups.sort((a, b) => {
    if (b.entryRows.length !== a.entryRows.length) {
      return b.entryRows.length - a.entryRows.length;
    }
    return a.winner.display_name.localeCompare(b.winner.display_name, undefined, {
      sensitivity: 'base',
    });
  });
}

function flattenTableRows(groups: EntryGroup[]): TableRow[] {
  const flat: TableRow[] = [];

  for (const group of groups) {
    const rows = group.rows;
    rows.forEach((row, rowIndex) => {
      const prevRuKey =
        rowIndex > 0 ? teamSetKey(rows[rowIndex - 1].runnerUpTeams) : null;
      const ruKey = teamSetKey(row.runnerUpTeams);
      const showRu = rowIndex === 0 || prevRuKey !== ruKey;
      let ruSpan = 1;
      if (showRu) {
        for (let i = rowIndex + 1; i < rows.length; i++) {
          if (teamSetKey(rows[i].runnerUpTeams) !== ruKey) break;
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

function WinnerName({
  winner,
  onSelectPlayer,
  viewerUsername,
}: {
  winner: ChallengeOutcomesEntry;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  const isViewer = viewerUsername != null && winner.username === viewerUsername;
  const nameClass = isViewer
    ? 'challenge-stats__group-points-name challenge-stats__entry-name--viewer'
    : 'challenge-stats__group-points-name';

  if (onSelectPlayer) {
    return (
      <button
        type="button"
        className={`${nameClass} challenge-stats__group-points-name--btn`}
        onClick={() => onSelectPlayer(winner.user_bracket_id, winner.display_name)}
      >
        {winner.display_name}
      </button>
    );
  }

  return <span className={nameClass}>{winner.display_name}</span>;
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
              <th scope="col">Entry</th>
              <th scope="col" className="challenge-outcomes__summary-th--pct">
                % of Outcomes
              </th>
            </tr>
          </thead>
          <tbody>
            {winnerOdds.map((row) => (
              <tr key={row.entry.user_bracket_id}>
                <td className="challenge-outcomes__summary-winner">
                  <WinnerName
                    winner={row.entry}
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
  if (prev.winner.user_bracket_id !== curr.winner.user_bracket_id) return 4;
  if (teamSetKey(prev.runnerUpTeams) !== teamSetKey(curr.runnerUpTeams)) return 3;
  return 1;
}

function ChampionTable({
  champ,
  groups,
  rows,
  hasThirdPlace,
  onSelectPlayer,
  viewerUsername,
}: {
  champ: ChallengeOutcomesChampionBranch;
  groups: EntryGroup[];
  rows: TableRow[];
  hasThirdPlace: boolean;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  const entryRowsByWinner = new Map(
    groups.map((group) => [group.winner.user_bracket_id, group.entryRows]),
  );

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
          {rows.map((row, rowIndex) => {
            const entryRows = entryRowsByWinner.get(row.winner.user_bracket_id) ?? [];
            const thirdUniverse = thirdsForRunnerUpCluster(entryRows, row.runnerUpTeams);
            const fourthUniverse = fourthsForRunnerUpThirdCluster(
              entryRows,
              row.runnerUpTeams,
              row.thirdTeams,
            );

            return (
              <tr
                key={`${teamSetKey(row.runnerUpTeams)}-${teamSetKey(row.thirdTeams)}-${teamSetKey(row.fourthTeams)}-${teamSetKey(row.semiTeams)}-w:${row.winner.user_bracket_id}`}
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
                      universe={dedupeTeams(
                        entryRows.map((entryRow) => entryRow.runnerUp),
                      )}
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
                        universe={thirdUniverse}
                        allLabel="Any third-place finish for this runner-up"
                      />
                    </td>
                    <td>
                      <PlacementCell
                        teams={row.fourthTeams}
                        universe={fourthUniverse}
                        allLabel="Any fourth-place finish for this path"
                      />
                    </td>
                  </>
                ) : (
                  <td>
                    <PlacementCell
                      teams={row.semiTeams}
                      universe={semiTeamsForRunnerUpCluster(entryRows, row.runnerUpTeams)}
                      singleSize="sm"
                      allLabel="Any semi-finalist for this runner-up"
                    />
                  </td>
                )}
                {row.showWinnerCell ? (
                  <td
                    rowSpan={row.winnerRowSpan}
                    className="challenge-stats__sim-td--entries challenge-outcomes__td--winner"
                  >
                    <WinnerName
                      winner={row.winner}
                      onSelectPlayer={onSelectPlayer}
                      viewerUsername={viewerUsername}
                    />
                  </td>
                ) : null}
              </tr>
            );
          })}
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
            const champRows = collectRawRows(champ, hasThirdPlace);
            const groups = buildEntryGroups(champRows, hasThirdPlace);
            const rows = flattenTableRows(groups);
            if (rows.length === 0) return null;
            return (
              <article
                key={champ.team.bracket_contestant_id}
                className="challenge-stats__sim-card"
              >
                <ChampionTable
                  champ={champ}
                  groups={groups}
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
