import type { ChallengeStatsSimilarityTeam } from './api';
import {
  isExhaustiveCluster,
  OutcomeGlobalUniverse,
  pathOutcomeKey,
  sumDisplayRowBranchMetric,
  sumDisplayRowPlacementMetric,
  sumDisplayRowSpanBranchMetric,
  sumDisplayRowsPlacementMetric,
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

/** Shared path prefix through champion (1), +runner-up (2), +third/semi (3), +fourth (4). */
export function rowPrefixKey(
  row: OutcomeDisplayRow,
  depth: number,
  hasThirdPlace: boolean,
): string {
  const parts = [String(row.champion.bracket_contestant_id)];
  if (depth <= 1) return parts[0];
  parts.push(teamSetKey(row.runnerUpTeams));
  if (depth <= 2) return parts.join('|');
  if (hasThirdPlace) {
    parts.push(teamSetKey(row.thirdTeams));
    if (depth <= 3) return parts.join('|');
    parts.push(teamSetKey(row.fourthTeams));
    return parts.join('|');
  }
  parts.push(teamSetKey(row.semiTeams));
  return parts.join('|');
}

export function maxRowPrefixDepth(hasThirdPlace: boolean): number {
  return hasThirdPlace ? 4 : 3;
}

/** Partition rows that share the same placement path through `depth`. */
export function partitionRowsByPrefixDepth(
  rows: OutcomeDisplayRow[],
  depth: number,
  hasThirdPlace: boolean,
): Map<string, OutcomeDisplayRow[]> {
  const groups = new Map<string, OutcomeDisplayRow[]>();
  for (const row of rows) {
    const key = rowPrefixKey(row, depth, hasThirdPlace);
    const bucket = groups.get(key) ?? [];
    bucket.push(row);
    groups.set(key, bucket);
  }
  return groups;
}

/** Every rowSpan column requires rows with the same prefix to be contiguous. */
export function assertRowSpanContiguity(
  rows: OutcomeDisplayRow[],
  hasThirdPlace: boolean,
): void {
  const maxDepth = maxRowPrefixDepth(hasThirdPlace);
  for (let depth = 1; depth <= maxDepth; depth++) {
    const indicesByPrefix = new Map<string, number[]>();
    rows.forEach((row, index) => {
      const key = rowPrefixKey(row, depth, hasThirdPlace);
      const bucket = indicesByPrefix.get(key) ?? [];
      bucket.push(index);
      indicesByPrefix.set(key, bucket);
    });
    for (const [prefix, indices] of indicesByPrefix) {
      if (indices.length <= 1) continue;
      const min = Math.min(...indices);
      const max = Math.max(...indices);
      if (max - min + 1 !== indices.length) {
        throw new Error(
          `rowSpan prefix violation at depth ${depth} for ${prefix}`,
        );
      }
    }
  }
}

function rowGroupNameKey(
  group: OutcomeDisplayRow[],
  role: PlacementRole,
): string {
  const row = group[0];
  if (role === 'champion') return row.champion.display_name;
  return placementTeamsNameKey(roleTeams(row, role));
}

function rowGroupColumnSortScore(
  group: OutcomeDisplayRow[],
  role: PlacementRole,
  sortKey: OutcomeSortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood: Record<string, number> | undefined,
  entryLeaves: OutcomeLeafPath[] | undefined,
): number {
  if (group.length === 0) return -1;

  const metricMode: OutcomeTeamMetricMode =
    sortKey === 'likelihood' ? 'likelihood' : 'outcomes';

  if (entryLeaves) {
    if (role === 'champion') {
      return normalizeSortScore(
        sumDisplayRowSpanBranchMetric(
          group,
          0,
          group.length,
          entryLeaves,
          hasThirdPlace,
          metricMode,
          pathLikelihood,
        ),
        sortKey,
        globalOutcomeTotal,
      );
    }

    const placementRole = role as DisplayRowPlacementRole;
    const teamIds = roleTeams(group[0], role).map(
      (team) => team.bracket_contestant_id,
    );
    return normalizeSortScore(
      sumDisplayRowsPlacementMetric(
        group,
        entryLeaves,
        hasThirdPlace,
        placementRole,
        teamIds,
        metricMode,
        pathLikelihood,
      ),
      sortKey,
      globalOutcomeTotal,
    );
  }

  let total = 0;
  let found = false;
  for (const row of group) {
    const ruIds = new Set(
      row.runnerUpTeams.map((team) => team.bracket_contestant_id),
    );
    const thirdIds = new Set(
      row.thirdTeams.map((team) => team.bracket_contestant_id),
    );
    const score = rowColumnSortScore(
      row,
      role,
      sortKey,
      hasThirdPlace,
      universe,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
      entryLeaves,
      ruIds,
      thirdIds,
    );
    if (score < 0) continue;
    total += score;
    found = true;
  }
  return found ? total : -1;
}

function compareRowGroups(
  groupA: OutcomeDisplayRow[],
  groupB: OutcomeDisplayRow[],
  role: PlacementRole,
  sortKey: OutcomeSortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood: Record<string, number> | undefined,
  entryLeaves: OutcomeLeafPath[] | undefined,
): number {
  if (sortKey !== 'name') {
    const scoreA = rowGroupColumnSortScore(
      groupA,
      role,
      sortKey,
      hasThirdPlace,
      universe,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
      entryLeaves,
    );
    const scoreB = rowGroupColumnSortScore(
      groupB,
      role,
      sortKey,
      hasThirdPlace,
      universe,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
      entryLeaves,
    );
    if (scoreB !== scoreA) return scoreB - scoreA;
  }

  return rowGroupNameKey(groupA, role).localeCompare(
    rowGroupNameKey(groupB, role),
    undefined,
    { sensitivity: 'base' },
  );
}

// Display sort contract: rows that share a path prefix through column N are
// NEVER separated. We only partition by rowPrefixKey, rank sibling partitions
// by combined column mass, and recurse — never flat-sort the full row list.
function sortRowGroups(
  rows: OutcomeDisplayRow[],
  depth: number,
  sortKey: OutcomeSortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood: Record<string, number> | undefined,
  entryLeaves: OutcomeLeafPath[] | undefined,
): OutcomeDisplayRow[] {
  const columnRoles: PlacementRole[] = hasThirdPlace
    ? ['champion', 'runner_up', 'third', 'fourth']
    : ['champion', 'runner_up', 'semi'];
  const maxDepth = maxRowPrefixDepth(hasThirdPlace);

  if (rows.length <= 1 || depth > maxDepth) {
    return rows;
  }

  const role = columnRoles[depth - 1];
  const groups = partitionRowsByPrefixDepth(rows, depth, hasThirdPlace);

  const sortedKeys = [...groups.keys()].sort((keyA, keyB) =>
    compareRowGroups(
      groups.get(keyA)!,
      groups.get(keyB)!,
      role,
      sortKey,
      hasThirdPlace,
      universe,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
      entryLeaves,
    ),
  );

  return sortedKeys.flatMap((key) =>
    sortRowGroups(
      groups.get(key)!,
      depth + 1,
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

/**
 * Order outcome rows for the paths table. Sibling branches are ranked by metric
 * or name, but rows with a shared prefix through any column always stay together.
 */
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
  if (rows.length <= 1) {
    const result = [...rows];
    assertRowSpanContiguity(result, hasThirdPlace);
    return result;
  }

  const sorted = sortRowGroups(
    rows,
    1,
    sortKey,
    hasThirdPlace,
    universe,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
    entryLeaves,
  );
  assertRowSpanContiguity(sorted, hasThirdPlace);
  return sorted;
}
