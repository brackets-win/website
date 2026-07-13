import type { ChallengeStatsSimilarityTeam } from './api';
import {
  isExhaustiveCluster,
  OutcomeGlobalUniverse,
  pathOutcomeKey,
  sumDisplayRowBranchMetric,
  sumDisplayRowPlacementMetric,
  teamSetKey,
  type DisplayRowPlacementRole,
  type OutcomeDisplayRow,
  type OutcomeLeafPath,
  type OutcomeTeamMetricMode,
} from './challengeOutcomesDisplay';

export type OutcomeSortKey = 'outcomes' | 'likelihood' | 'name';
type PlacementRole = 'champion' | 'runner_up' | 'third' | 'fourth' | 'semi';
type TeamMetricMode = 'outcomes' | 'likelihood';

type PathContext = {
  championId: number;
  runnerUpIds: number[];
  thirdIds: number[];
};

function sortTeams(
  teams: Iterable<ChallengeStatsSimilarityTeam>,
): ChallengeStatsSimilarityTeam[] {
  return [...teams].sort((a, b) =>
    a.display_name.localeCompare(b.display_name, undefined, {
      sensitivity: 'base',
    }),
  );
}

function winnersKey(
  winners: { user_bracket_id: number }[],
): string {
  return winners
    .map((entry) => entry.user_bracket_id)
    .sort((a, b) => a - b)
    .join(',');
}

export function buildPathOutcomeCounts(
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
): Map<string, number> {
  const counts = new Map<string, number>();
  const bump = (key: string) => {
    counts.set(key, (counts.get(key) ?? 0) + 1);
  };

  for (const leaf of leaves) {
    const championId = leaf.champion.bracket_contestant_id;
    const runnerUpId = leaf.runnerUp.bracket_contestant_id;
    bump(pathOutcomeKey(championId));
    bump(pathOutcomeKey(championId, runnerUpId));
    if (hasThirdPlace) {
      if (!leaf.third) continue;
      const thirdId = leaf.third.bracket_contestant_id;
      bump(pathOutcomeKey(championId, runnerUpId, thirdId));
      if (leaf.fourth) {
        bump(
          pathOutcomeKey(
            championId,
            runnerUpId,
            thirdId,
            leaf.fourth.bracket_contestant_id,
          ),
        );
      }
    } else {
      for (const semi of leaf.semifinalists ?? []) {
        bump(
          pathOutcomeKey(
            championId,
            runnerUpId,
            undefined,
            undefined,
            semi.bracket_contestant_id,
          ),
        );
      }
    }
  }
  return counts;
}

function buildPathContext(
  row: OutcomeDisplayRow,
  role: PlacementRole,
): PathContext {
  return {
    championId: row.champion.bracket_contestant_id,
    runnerUpIds: row.runnerUpTeams.map((team) => team.bracket_contestant_id),
    thirdIds:
      role === 'fourth' || role === 'semi'
        ? row.thirdTeams.map((team) => team.bracket_contestant_id)
        : [],
  };
}

function pathMetricKeys(
  context: PathContext,
  role: PlacementRole,
  teamId: number,
): string[] {
  if (role === 'champion') {
    return [pathOutcomeKey(teamId)];
  }
  if (role === 'runner_up') {
    return [pathOutcomeKey(context.championId, teamId)];
  }
  if (role === 'third') {
    return context.runnerUpIds.map((runnerUpId) =>
      pathOutcomeKey(context.championId, runnerUpId, teamId),
    );
  }
  if (role === 'fourth') {
    const keys: string[] = [];
    for (const runnerUpId of context.runnerUpIds) {
      if (context.thirdIds.length === 0) continue;
      for (const thirdId of context.thirdIds) {
        keys.push(
          pathOutcomeKey(context.championId, runnerUpId, thirdId, teamId),
        );
      }
    }
    return keys;
  }
  return context.runnerUpIds.map((runnerUpId) =>
    pathOutcomeKey(context.championId, runnerUpId, undefined, undefined, teamId),
  );
}

function sumPathMetricValues(
  keys: string[],
  teamMetricMode: TeamMetricMode,
  pathOutcomeCounts: Map<string, number>,
  pathLikelihood?: Record<string, number>,
): number | null {
  if (keys.length === 0) return null;
  let total = 0;
  let found = false;
  for (const key of keys) {
    const value =
      teamMetricMode === 'outcomes'
        ? pathOutcomeCounts.get(key)
        : pathLikelihood?.[key];
    if (value == null || Number.isNaN(value)) continue;
    total += value;
    found = true;
  }
  return found ? total : null;
}

/** Team-mode card ordering: total mass under a champion prefix. */
export function championCardMetricScore(
  champId: number,
  metric: 'outcome_count' | 'likelihood',
  pathOutcomeCounts: Map<string, number>,
  pathLikelihood?: Record<string, number>,
): number {
  const context: PathContext = {
    championId: champId,
    runnerUpIds: [],
    thirdIds: [],
  };
  const teamMetricMode: TeamMetricMode =
    metric === 'likelihood' ? 'likelihood' : 'outcomes';
  const raw = sumPathMetricValues(
    pathMetricKeys(context, 'champion', champId),
    teamMetricMode,
    pathOutcomeCounts,
    pathLikelihood,
  );
  return raw ?? -1;
}

function teamMetricSortScore(
  context: PathContext,
  role: PlacementRole,
  teamId: number,
  sortKey: OutcomeSortKey,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): number {
  if (sortKey === 'name') return 0;
  const metricMode: TeamMetricMode =
    sortKey === 'likelihood' ? 'likelihood' : 'outcomes';
  const raw = sumPathMetricValues(
    pathMetricKeys(context, role, teamId),
    metricMode,
    pathOutcomeCounts,
    pathLikelihood,
  );
  if (raw == null) return -1;
  if (sortKey === 'likelihood') return raw;
  return globalOutcomeTotal > 0 ? (100 * raw) / globalOutcomeTotal : raw;
}

function placementTeamsNameKey(teams: ChallengeStatsSimilarityTeam[]): string {
  return sortTeams(teams)
    .map((team) => team.display_name)
    .join(', ');
}

function roleTeams(
  row: OutcomeDisplayRow,
  role: PlacementRole,
): ChallengeStatsSimilarityTeam[] {
  if (role === 'champion') return [row.champion];
  if (role === 'runner_up') return row.runnerUpTeams;
  if (role === 'third') return row.thirdTeams;
  if (role === 'fourth') return row.fourthTeams;
  return row.semiTeams;
}

function roleUniverse(
  row: OutcomeDisplayRow,
  role: PlacementRole,
  universe: OutcomeGlobalUniverse,
  ruIds: Set<number>,
  thirdIds: Set<number>,
): ChallengeStatsSimilarityTeam[] {
  const champId = row.champion.bracket_contestant_id;
  if (role === 'champion') return [row.champion];
  if (role === 'runner_up') return universe.runnerUps(champId);
  if (role === 'third') return universe.thirds(champId, ruIds);
  if (role === 'fourth') return universe.fourths(champId, ruIds, thirdIds);
  return universe.semis(champId, ruIds);
}

function normalizeSortScore(
  raw: number | null,
  sortKey: OutcomeSortKey,
  globalOutcomeTotal: number,
): number {
  if (raw == null) return -1;
  if (sortKey === 'likelihood') return raw;
  return globalOutcomeTotal > 0 ? (100 * raw) / globalOutcomeTotal : raw;
}

function teamRowColumnSortScore(
  row: OutcomeDisplayRow,
  role: PlacementRole,
  sortKey: OutcomeSortKey,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood: Record<string, number> | undefined,
  ruIds: Set<number>,
  thirdIds: Set<number>,
): number {
  const teams = roleTeams(row, role);
  if (teams.length === 0) return -1;
  const columnUniverse = roleUniverse(row, role, universe, ruIds, thirdIds);
  const context = buildPathContext(row, role);
  const clusterTeams = isExhaustiveCluster(teams, columnUniverse)
    ? columnUniverse
    : teams;
  let total = 0;
  let found = false;
  for (const team of clusterTeams) {
    const score = teamMetricSortScore(
      context,
      role,
      team.bracket_contestant_id,
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    if (score < 0) continue;
    total += score;
    found = true;
  }
  return found ? total : -1;
}

function entryRowColumnSortScore(
  row: OutcomeDisplayRow,
  role: PlacementRole,
  sortKey: OutcomeSortKey,
  entryLeaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  globalOutcomeTotal: number,
  pathLikelihood: Record<string, number> | undefined,
): number {
  const metricMode: OutcomeTeamMetricMode =
    sortKey === 'likelihood' ? 'likelihood' : 'outcomes';
  const teams = roleTeams(row, role);
  if (teams.length === 0) return -1;

  let raw: number | null;
  if (role === 'champion') {
    raw = sumDisplayRowBranchMetric(
      row,
      entryLeaves,
      hasThirdPlace,
      metricMode,
      pathLikelihood,
    );
  } else {
    raw = sumDisplayRowPlacementMetric(
      row,
      entryLeaves,
      hasThirdPlace,
      role as DisplayRowPlacementRole,
      teams.map((team) => team.bracket_contestant_id),
      metricMode,
      pathLikelihood,
    );
  }
  return normalizeSortScore(raw, sortKey, globalOutcomeTotal);
}

function rowColumnSortScore(
  row: OutcomeDisplayRow,
  role: PlacementRole,
  sortKey: OutcomeSortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood: Record<string, number> | undefined,
  entryLeaves: OutcomeLeafPath[] | undefined,
  ruIds: Set<number>,
  thirdIds: Set<number>,
): number {
  if (entryLeaves) {
    return entryRowColumnSortScore(
      row,
      role,
      sortKey,
      entryLeaves,
      hasThirdPlace,
      globalOutcomeTotal,
      pathLikelihood,
    );
  }
  return teamRowColumnSortScore(
    row,
    role,
    sortKey,
    universe,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
    ruIds,
    thirdIds,
  );
}

function compareRowColumnLevel(
  a: OutcomeDisplayRow,
  b: OutcomeDisplayRow,
  role: PlacementRole,
  sortKey: OutcomeSortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood: Record<string, number> | undefined,
  entryLeaves: OutcomeLeafPath[] | undefined,
  ruIdsA: Set<number>,
  ruIdsB: Set<number>,
  thirdIdsA: Set<number>,
  thirdIdsB: Set<number>,
): number | null {
  const scoreA = rowColumnSortScore(
    a,
    role,
    sortKey,
    hasThirdPlace,
    universe,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
    entryLeaves,
    ruIdsA,
    thirdIdsA,
  );
  const scoreB = rowColumnSortScore(
    b,
    role,
    sortKey,
    hasThirdPlace,
    universe,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
    entryLeaves,
    ruIdsB,
    thirdIdsB,
  );
  if (scoreB !== scoreA) return scoreB - scoreA;
  return null;
}

function compareDisplayRows(
  a: OutcomeDisplayRow,
  b: OutcomeDisplayRow,
  sortKey: OutcomeSortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
  entryLeaves?: OutcomeLeafPath[],
): number {
  const champIdA = a.champion.bracket_contestant_id;
  const champIdB = b.champion.bracket_contestant_id;
  const ruIdsA = new Set(a.runnerUpTeams.map((team) => team.bracket_contestant_id));
  const ruIdsB = new Set(b.runnerUpTeams.map((team) => team.bracket_contestant_id));
  const thirdIdsA = new Set(
    a.thirdTeams.map((team) => team.bracket_contestant_id),
  );
  const thirdIdsB = new Set(
    b.thirdTeams.map((team) => team.bracket_contestant_id),
  );

  if (sortKey === 'name') {
    const cmpChamp = a.champion.display_name.localeCompare(
      b.champion.display_name,
      undefined,
      { sensitivity: 'base' },
    );
    if (cmpChamp !== 0) return cmpChamp;
    const cmpRu = placementTeamsNameKey(a.runnerUpTeams).localeCompare(
      placementTeamsNameKey(b.runnerUpTeams),
      undefined,
      { sensitivity: 'base' },
    );
    if (cmpRu !== 0) return cmpRu;
    if (hasThirdPlace) {
      const cmpThird = placementTeamsNameKey(a.thirdTeams).localeCompare(
        placementTeamsNameKey(b.thirdTeams),
        undefined,
        { sensitivity: 'base' },
      );
      if (cmpThird !== 0) return cmpThird;
      const cmpFourth = placementTeamsNameKey(a.fourthTeams).localeCompare(
        placementTeamsNameKey(b.fourthTeams),
        undefined,
        { sensitivity: 'base' },
      );
      if (cmpFourth !== 0) return cmpFourth;
    } else {
      const cmpSemi = placementTeamsNameKey(a.semiTeams).localeCompare(
        placementTeamsNameKey(b.semiTeams),
        undefined,
        { sensitivity: 'base' },
      );
      if (cmpSemi !== 0) return cmpSemi;
    }
    return winnersKey(a.winners).localeCompare(winnersKey(b.winners));
  }

  // Group by shared cell identity at each column (for rowSpan), then order
  // sibling branches using that column's row-level metric left → right.
  const columnLevels: PlacementRole[] = hasThirdPlace
    ? ['champion', 'runner_up', 'third', 'fourth']
    : ['champion', 'runner_up', 'semi'];

  for (const role of columnLevels) {
    const keysDiffer =
      role === 'champion'
        ? champIdA !== champIdB
        : role === 'runner_up'
          ? teamSetKey(a.runnerUpTeams) !== teamSetKey(b.runnerUpTeams)
          : role === 'third'
            ? teamSetKey(a.thirdTeams) !== teamSetKey(b.thirdTeams)
            : role === 'fourth'
              ? teamSetKey(a.fourthTeams) !== teamSetKey(b.fourthTeams)
              : teamSetKey(a.semiTeams) !== teamSetKey(b.semiTeams);

    if (!keysDiffer) continue;

    const metricCmp = compareRowColumnLevel(
      a,
      b,
      role,
      sortKey,
      hasThirdPlace,
      universe,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
      entryLeaves,
      ruIdsA,
      ruIdsB,
      thirdIdsA,
      thirdIdsB,
    );
    if (metricCmp != null) return metricCmp;

    const nameKeyA =
      role === 'champion'
        ? a.champion.display_name
        : placementTeamsNameKey(roleTeams(a, role));
    const nameKeyB =
      role === 'champion'
        ? b.champion.display_name
        : placementTeamsNameKey(roleTeams(b, role));
    return nameKeyA.localeCompare(nameKeyB, undefined, { sensitivity: 'base' });
  }

  return winnersKey(a.winners).localeCompare(winnersKey(b.winners));
}

export function sortOutcomeDisplayRows(
  rows: OutcomeDisplayRow[],
  sortKey: OutcomeSortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
  entryLeaves?: OutcomeLeafPath[],
): OutcomeDisplayRow[] {
  return [...rows].sort((a, b) =>
    compareDisplayRows(
      a,
      b,
      sortKey,
      hasThirdPlace,
      universe,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
      entryLeaves,
    ),
  );
}
