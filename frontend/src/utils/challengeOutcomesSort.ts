import type { ChallengeStatsSimilarityTeam } from './api';
import {
  isExhaustiveCluster,
  OutcomeGlobalUniverse,
  pathOutcomeKey,
  teamSetKey,
  type OutcomeDisplayRow,
  type OutcomeLeafPath,
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

function placementColumnSortScore(
  row: OutcomeDisplayRow,
  role: PlacementRole,
  teams: ChallengeStatsSimilarityTeam[],
  universe: ChallengeStatsSimilarityTeam[],
  sortKey: OutcomeSortKey,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): number {
  if (teams.length === 0) return -1;
  const context = buildPathContext(row, role);
  const clusterTeams = isExhaustiveCluster(teams, universe) ? universe : teams;
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

function compareDisplayRows(
  a: OutcomeDisplayRow,
  b: OutcomeDisplayRow,
  sortKey: OutcomeSortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): number {
  const champIdA = a.champion.bracket_contestant_id;
  const champIdB = b.champion.bracket_contestant_id;
  const ruIdsA = new Set(a.runnerUpTeams.map((team) => team.bracket_contestant_id));
  const ruIdsB = new Set(b.runnerUpTeams.map((team) => team.bracket_contestant_id));

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

  // Hierarchical grouping (champ → runner-up → third → fourth) so rowSpan cells
  // merge correctly; only order sibling branches by metric within each level.
  if (champIdA !== champIdB) {
    const metric =
      sortKey === 'likelihood' ? 'likelihood' : 'outcome_count';
    const champScoreA = championCardMetricScore(
      champIdA,
      metric,
      pathOutcomeCounts,
      pathLikelihood,
    );
    const champScoreB = championCardMetricScore(
      champIdB,
      metric,
      pathOutcomeCounts,
      pathLikelihood,
    );
    if (champScoreB !== champScoreA) return champScoreB - champScoreA;
    return a.champion.display_name.localeCompare(
      b.champion.display_name,
      undefined,
      { sensitivity: 'base' },
    );
  }

  const ruKeyA = teamSetKey(a.runnerUpTeams);
  const ruKeyB = teamSetKey(b.runnerUpTeams);
  if (ruKeyA !== ruKeyB) {
    const ruScoreA = placementColumnSortScore(
      a,
      'runner_up',
      a.runnerUpTeams,
      universe.runnerUps(champIdA),
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    const ruScoreB = placementColumnSortScore(
      b,
      'runner_up',
      b.runnerUpTeams,
      universe.runnerUps(champIdB),
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    if (ruScoreB !== ruScoreA) return ruScoreB - ruScoreA;
    return placementTeamsNameKey(a.runnerUpTeams).localeCompare(
      placementTeamsNameKey(b.runnerUpTeams),
      undefined,
      { sensitivity: 'base' },
    );
  }

  if (hasThirdPlace) {
    const thirdKeyA = teamSetKey(a.thirdTeams);
    const thirdKeyB = teamSetKey(b.thirdTeams);
    if (thirdKeyA !== thirdKeyB) {
      const thirdScoreA = placementColumnSortScore(
        a,
        'third',
        a.thirdTeams,
        universe.thirds(champIdA, ruIdsA),
        sortKey,
        pathOutcomeCounts,
        globalOutcomeTotal,
        pathLikelihood,
      );
      const thirdScoreB = placementColumnSortScore(
        b,
        'third',
        b.thirdTeams,
        universe.thirds(champIdB, ruIdsB),
        sortKey,
        pathOutcomeCounts,
        globalOutcomeTotal,
        pathLikelihood,
      );
      if (thirdScoreB !== thirdScoreA) return thirdScoreB - thirdScoreA;
      return placementTeamsNameKey(a.thirdTeams).localeCompare(
        placementTeamsNameKey(b.thirdTeams),
        undefined,
        { sensitivity: 'base' },
      );
    }

    const thirdIdsA = new Set(
      a.thirdTeams.map((team) => team.bracket_contestant_id),
    );
    const thirdIdsB = new Set(
      b.thirdTeams.map((team) => team.bracket_contestant_id),
    );
    const fourthKeyA = teamSetKey(a.fourthTeams);
    const fourthKeyB = teamSetKey(b.fourthTeams);
    if (fourthKeyA !== fourthKeyB) {
      const fourthScoreA = placementColumnSortScore(
        a,
        'fourth',
        a.fourthTeams,
        universe.fourths(champIdA, ruIdsA, thirdIdsA),
        sortKey,
        pathOutcomeCounts,
        globalOutcomeTotal,
        pathLikelihood,
      );
      const fourthScoreB = placementColumnSortScore(
        b,
        'fourth',
        b.fourthTeams,
        universe.fourths(champIdB, ruIdsB, thirdIdsB),
        sortKey,
        pathOutcomeCounts,
        globalOutcomeTotal,
        pathLikelihood,
      );
      if (fourthScoreB !== fourthScoreA) return fourthScoreB - fourthScoreA;
      return placementTeamsNameKey(a.fourthTeams).localeCompare(
        placementTeamsNameKey(b.fourthTeams),
        undefined,
        { sensitivity: 'base' },
      );
    }
  } else {
    const semiKeyA = teamSetKey(a.semiTeams);
    const semiKeyB = teamSetKey(b.semiTeams);
    if (semiKeyA !== semiKeyB) {
      const semiScoreA = placementColumnSortScore(
        a,
        'semi',
        a.semiTeams,
        universe.semis(champIdA, ruIdsA),
        sortKey,
        pathOutcomeCounts,
        globalOutcomeTotal,
        pathLikelihood,
      );
      const semiScoreB = placementColumnSortScore(
        b,
        'semi',
        b.semiTeams,
        universe.semis(champIdB, ruIdsB),
        sortKey,
        pathOutcomeCounts,
        globalOutcomeTotal,
        pathLikelihood,
      );
      if (semiScoreB !== semiScoreA) return semiScoreB - semiScoreA;
      return placementTeamsNameKey(a.semiTeams).localeCompare(
        placementTeamsNameKey(b.semiTeams),
        undefined,
        { sensitivity: 'base' },
      );
    }
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
    ),
  );
}
