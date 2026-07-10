import type {
  ChallengeOutcomesChampionBranch,
  ChallengeOutcomesEntry,
  ChallengeStatsSimilarityTeam,
} from './api';

export type OutcomeLeafPath = {
  champion: ChallengeStatsSimilarityTeam;
  runnerUp: ChallengeStatsSimilarityTeam;
  third?: ChallengeStatsSimilarityTeam;
  fourth?: ChallengeStatsSimilarityTeam;
  semifinalists?: [ChallengeStatsSimilarityTeam, ChallengeStatsSimilarityTeam];
  winners: ChallengeOutcomesEntry[];
};

export type OutcomeDisplayRow = {
  champion: ChallengeStatsSimilarityTeam;
  runnerUpTeams: ChallengeStatsSimilarityTeam[];
  thirdTeams: ChallengeStatsSimilarityTeam[];
  fourthTeams: ChallengeStatsSimilarityTeam[];
  semiTeams: ChallengeStatsSimilarityTeam[];
  winners: ChallengeOutcomesEntry[];
};

function teamSortKey(team: ChallengeStatsSimilarityTeam): string {
  return team.display_name.toLocaleLowerCase();
}

function sortTeams(
  teams: Iterable<ChallengeStatsSimilarityTeam>,
): ChallengeStatsSimilarityTeam[] {
  return [...teams].sort((a, b) =>
    teamSortKey(a).localeCompare(teamSortKey(b), undefined, {
      sensitivity: 'base',
    }),
  );
}

function dedupeTeams(
  teams: ChallengeStatsSimilarityTeam[],
): ChallengeStatsSimilarityTeam[] {
  const byId = new Map<number, ChallengeStatsSimilarityTeam>();
  for (const team of teams) {
    byId.set(team.bracket_contestant_id, team);
  }
  return sortTeams(byId.values());
}

export function teamSetKey(teams: ChallengeStatsSimilarityTeam[]): string {
  return teams
    .map((team) => team.bracket_contestant_id)
    .sort((a, b) => a - b)
    .join(',');
}

function winnersKey(winners: ChallengeOutcomesEntry[]): string {
  return winners
    .map((entry) => entry.user_bracket_id)
    .sort((a, b) => a - b)
    .join(',');
}

function sortWinners(winners: ChallengeOutcomesEntry[]): ChallengeOutcomesEntry[] {
  return [...winners].sort((a, b) =>
    a.display_name.localeCompare(b.display_name, undefined, {
      sensitivity: 'base',
    }),
  );
}

export function collectOutcomeLeafPaths(
  tree: ChallengeOutcomesChampionBranch[],
  hasThirdPlace: boolean,
): OutcomeLeafPath[] {
  const rows: OutcomeLeafPath[] = [];
  for (const champ of tree) {
    for (const ru of champ.children) {
      if (hasThirdPlace) {
        for (const third of ru.children) {
          for (const fourth of third.children) {
            for (const leaf of fourth.children) {
              rows.push({
                champion: champ.team,
                runnerUp: ru.team,
                third: third.team,
                fourth: fourth.team,
                winners: sortWinners(leaf.winners),
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
              champion: champ.team,
              runnerUp: ru.team,
              semifinalists: [third.team, fourth.team],
              winners: sortWinners(leaf.winners),
            });
          }
        }
      }
    }
  }
  return rows;
}

export function isExhaustiveCluster(
  teams: ChallengeStatsSimilarityTeam[],
  universe: ChallengeStatsSimilarityTeam[],
): boolean {
  if (teams.length === 0 || universe.length === 0) return false;
  if (universe.length <= 1) return false;
  return teamSetKey(teams) === teamSetKey(universe);
}

/** Global remaining teams under a prefix — from the FULL outcome tree. */
export class OutcomeGlobalUniverse {
  constructor(private readonly allLeaves: OutcomeLeafPath[]) {}

  runnerUps(championId: number): ChallengeStatsSimilarityTeam[] {
    return dedupeTeams(
      this.allLeaves
        .filter((row) => row.champion.bracket_contestant_id === championId)
        .map((row) => row.runnerUp),
    );
  }

  thirds(championId: number, runnerUpIds: Set<number>): ChallengeStatsSimilarityTeam[] {
    return dedupeTeams(
      this.allLeaves
        .filter(
          (row) =>
            row.champion.bracket_contestant_id === championId &&
            runnerUpIds.has(row.runnerUp.bracket_contestant_id) &&
            row.third,
        )
        .map((row) => row.third!),
    );
  }

  fourths(
    championId: number,
    runnerUpIds: Set<number>,
    thirdIds: Set<number>,
  ): ChallengeStatsSimilarityTeam[] {
    return dedupeTeams(
      this.allLeaves
        .filter(
          (row) =>
            row.champion.bracket_contestant_id === championId &&
            runnerUpIds.has(row.runnerUp.bracket_contestant_id) &&
            row.third &&
            thirdIds.has(row.third.bracket_contestant_id) &&
            row.fourth,
        )
        .map((row) => row.fourth!),
    );
  }

  semis(championId: number, runnerUpIds: Set<number>): ChallengeStatsSimilarityTeam[] {
    const teams: ChallengeStatsSimilarityTeam[] = [];
    for (const row of this.allLeaves) {
      if (
        row.champion.bracket_contestant_id !== championId ||
        !runnerUpIds.has(row.runnerUp.bracket_contestant_id) ||
        !row.semifinalists
      ) {
        continue;
      }
      teams.push(...row.semifinalists);
    }
    return dedupeTeams(teams);
  }
}

function reconcileColumnForSiblings(
  rows: OutcomeDisplayRow[],
  siblingKey: (row: OutcomeDisplayRow) => string,
  getUniverse: (row: OutcomeDisplayRow) => ChallengeStatsSimilarityTeam[],
  getTeams: (row: OutcomeDisplayRow) => ChallengeStatsSimilarityTeam[],
  applyTeams: (
    row: OutcomeDisplayRow,
    teams: ChallengeStatsSimilarityTeam[],
  ) => OutcomeDisplayRow,
): OutcomeDisplayRow[] {
  const groups = new Map<string, number[]>();
  rows.forEach((row, index) => {
    const key = siblingKey(row);
    const bucket = groups.get(key) ?? [];
    bucket.push(index);
    groups.set(key, bucket);
  });

  const next = [...rows];
  for (const indices of groups.values()) {
    if (indices.length <= 1) continue;

    const groupRows = indices.map((index) => rows[index]);
    const columnUniverse = getUniverse(groupRows[0]);
    const splitTeams = dedupeTeams(
      groupRows
        .filter((row) => !isExhaustiveCluster(getTeams(row), columnUniverse))
        .flatMap((row) => getTeams(row)),
    );
    const splitIds = new Set(
      splitTeams.map((team) => team.bracket_contestant_id),
    );
    if (splitIds.size === 0) continue;

    for (const index of indices) {
      const row = rows[index];
      if (!isExhaustiveCluster(getTeams(row), columnUniverse)) continue;
      next[index] = applyTeams(
        row,
        columnUniverse.filter(
          (team) => !splitIds.has(team.bracket_contestant_id),
        ),
      );
    }
  }

  return next;
}

function buildMaxClusteredRow(
  champion: ChallengeStatsSimilarityTeam,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
): OutcomeDisplayRow {
  const champId = champion.bracket_contestant_id;
  const ruUniverse = universe.runnerUps(champId);
  const runnerUpTeamsRaw = dedupeTeams(leaves.map((leaf) => leaf.runnerUp));
  const runnerUpTeams = isExhaustiveCluster(runnerUpTeamsRaw, ruUniverse)
    ? ruUniverse
    : runnerUpTeamsRaw;
  const ruIds = new Set(
    runnerUpTeams.map((team) => team.bracket_contestant_id),
  );

  if (hasThirdPlace) {
    const thirdUniverse = universe.thirds(champId, ruIds);
    const thirdTeamsRaw = dedupeTeams(
      leaves.flatMap((leaf) => (leaf.third ? [leaf.third] : [])),
    );
    const thirdTeams = isExhaustiveCluster(thirdTeamsRaw, thirdUniverse)
      ? thirdUniverse
      : thirdTeamsRaw;
    const thirdIds = new Set(
      thirdTeams.map((team) => team.bracket_contestant_id),
    );
    const fourthUniverse = universe.fourths(champId, ruIds, thirdIds);
    const fourthTeamsRaw = dedupeTeams(
      leaves.flatMap((leaf) => (leaf.fourth ? [leaf.fourth] : [])),
    );
    const fourthTeams = isExhaustiveCluster(fourthTeamsRaw, fourthUniverse)
      ? fourthUniverse
      : fourthTeamsRaw;

    return {
      champion,
      runnerUpTeams,
      thirdTeams,
      fourthTeams,
      semiTeams: [],
      winners: sortWinners(leaves[0].winners),
    };
  }

  const semiUniverse = universe.semis(champId, ruIds);
  const semiTeamsRaw = dedupeTeams(
    leaves.flatMap((leaf) => leaf.semifinalists ?? []),
  );
  const semiTeams = isExhaustiveCluster(semiTeamsRaw, semiUniverse)
    ? semiUniverse
    : semiTeamsRaw;

  return {
    champion,
    runnerUpTeams,
    thirdTeams: [],
    fourthTeams: [],
    semiTeams,
    winners: sortWinners(leaves[0].winners),
  };
}

function refreshDownstreamFromLeaves(
  row: OutcomeDisplayRow,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
): OutcomeDisplayRow {
  const ruIds = new Set(
    row.runnerUpTeams.map((team) => team.bracket_contestant_id),
  );
  const matchingLeaves = leaves.filter((leaf) =>
    ruIds.has(leaf.runnerUp.bracket_contestant_id),
  );
  if (matchingLeaves.length === 0) return row;

  const rechustered = buildMaxClusteredRow(
    row.champion,
    matchingLeaves,
    hasThirdPlace,
    universe,
  );

  return {
    ...row,
    thirdTeams: rechustered.thirdTeams,
    fourthTeams: rechustered.fourthTeams,
    semiTeams: rechustered.semiTeams,
  };
}

function refreshFourthFromLeaves(
  row: OutcomeDisplayRow,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
): OutcomeDisplayRow {
  if (!hasThirdPlace) return row;

  const ruIds = new Set(
    row.runnerUpTeams.map((team) => team.bracket_contestant_id),
  );
  const thirdIds = new Set(
    row.thirdTeams.map((team) => team.bracket_contestant_id),
  );
  const matchingLeaves = leaves.filter(
    (leaf) =>
      ruIds.has(leaf.runnerUp.bracket_contestant_id) &&
      leaf.third != null &&
      thirdIds.has(leaf.third.bracket_contestant_id),
  );
  if (matchingLeaves.length === 0) return row;

  const champId = row.champion.bracket_contestant_id;
  const fourthUniverse = universe.fourths(champId, ruIds, thirdIds);
  const fourthTeamsRaw = dedupeTeams(
    matchingLeaves.flatMap((leaf) => (leaf.fourth ? [leaf.fourth] : [])),
  );
  const fourthTeams = isExhaustiveCluster(fourthTeamsRaw, fourthUniverse)
    ? fourthUniverse
    : fourthTeamsRaw;

  return { ...row, fourthTeams };
}

type RowWithLeaves = { row: OutcomeDisplayRow; leaves: OutcomeLeafPath[] };

function reconcileSiblingPlacementSplits(
  items: RowWithLeaves[],
  universe: OutcomeGlobalUniverse,
  hasThirdPlace: boolean,
): OutcomeDisplayRow[] {
  if (items.length <= 1) return items.map((item) => item.row);

  let rows = items.map((item) => item.row);

  rows = reconcileColumnForSiblings(
    rows,
    () => '',
    (row) => universe.runnerUps(row.champion.bracket_contestant_id),
    (row) => row.runnerUpTeams,
    (row, teams) => ({ ...row, runnerUpTeams: teams }),
  );
  rows = rows.map((row, index) =>
    refreshDownstreamFromLeaves(
      row,
      items[index].leaves,
      hasThirdPlace,
      universe,
    ),
  );

  if (!hasThirdPlace) {
    return reconcileColumnForSiblings(
      rows,
      (row) => teamSetKey(row.runnerUpTeams),
      (row) => {
        const ruIds = new Set(
          row.runnerUpTeams.map((team) => team.bracket_contestant_id),
        );
        return universe.semis(row.champion.bracket_contestant_id, ruIds);
      },
      (row) => row.semiTeams,
      (row, teams) => ({ ...row, semiTeams: teams }),
    );
  }

  rows = reconcileColumnForSiblings(
    rows,
    (row) => teamSetKey(row.runnerUpTeams),
    (row) => {
      const ruIds = new Set(
        row.runnerUpTeams.map((team) => team.bracket_contestant_id),
      );
      return universe.thirds(row.champion.bracket_contestant_id, ruIds);
    },
    (row) => row.thirdTeams,
    (row, teams) => ({ ...row, thirdTeams: teams }),
  );
  rows = rows.map((row, index) =>
    refreshFourthFromLeaves(row, items[index].leaves, hasThirdPlace, universe),
  );

  return reconcileColumnForSiblings(
    rows,
    (row) =>
      `${teamSetKey(row.runnerUpTeams)}|${teamSetKey(row.thirdTeams)}`,
    (row) => {
      const ruIds = new Set(
        row.runnerUpTeams.map((team) => team.bracket_contestant_id),
      );
      const thirdIds = new Set(
        row.thirdTeams.map((team) => team.bracket_contestant_id),
      );
      return universe.fourths(
        row.champion.bracket_contestant_id,
        ruIds,
        thirdIds,
      );
    },
    (row) => row.fourthTeams,
    (row, teams) => ({ ...row, fourthTeams: teams }),
  );
}

export function buildOutcomeDisplayRows(
  workingLeaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
): OutcomeDisplayRow[] {
  if (workingLeaves.length === 0) return [];

  const byChamp = new Map<number, OutcomeLeafPath[]>();
  for (const leaf of workingLeaves) {
    const id = leaf.champion.bracket_contestant_id;
    const bucket = byChamp.get(id) ?? [];
    bucket.push(leaf);
    byChamp.set(id, bucket);
  }

  const champIds = [...byChamp.keys()].sort((a, b) => {
    const ca = byChamp.get(a)![0].champion;
    const cb = byChamp.get(b)![0].champion;
    return teamSortKey(ca).localeCompare(teamSortKey(cb), undefined, {
      sensitivity: 'base',
    });
  });

  const rows: OutcomeDisplayRow[] = [];

  for (const champId of champIds) {
    const champLeaves = byChamp.get(champId)!;
    const champion = champLeaves[0].champion;

    const byWinners = new Map<string, OutcomeLeafPath[]>();
    for (const leaf of champLeaves) {
      const key = winnersKey(leaf.winners);
      const bucket = byWinners.get(key) ?? [];
      bucket.push(leaf);
      byWinners.set(key, bucket);
    }

    const winnerGroups = [...byWinners.values()].sort((a, b) =>
      winnersKey(a[0].winners).localeCompare(winnersKey(b[0].winners)),
    );

    const champItems: RowWithLeaves[] = winnerGroups.map((group) => ({
      row: buildMaxClusteredRow(champion, group, hasThirdPlace, universe),
      leaves: group,
    }));
    rows.push(
      ...reconcileSiblingPlacementSplits(champItems, universe, hasThirdPlace),
    );
  }

  return rows;
}
