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

function leafMatchesRowWinners(
  leaf: OutcomeLeafPath,
  row: OutcomeDisplayRow,
): boolean {
  return winnersKey(leaf.winners) === winnersKey(row.winners);
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

export function pathOutcomeKey(
  championId: number,
  runnerUpId?: number,
  thirdId?: number,
  fourthId?: number,
  semiId?: number,
): string {
  const parts: Array<string | number> = ['c', championId];
  if (runnerUpId == null) return parts.join(':');
  parts.push('ru', runnerUpId);
  if (thirdId == null && semiId == null) return parts.join(':');
  if (semiId != null) {
    parts.push('s', semiId);
    return parts.join(':');
  }
  parts.push('t', thirdId!);
  if (fourthId == null) return parts.join(':');
  parts.push('f', fourthId);
  return parts.join(':');
}

function deepestPathOutcomeKey(
  leaf: OutcomeLeafPath,
  hasThirdPlace: boolean,
): string | null {
  const championId = leaf.champion.bracket_contestant_id;
  const runnerUpId = leaf.runnerUp.bracket_contestant_id;
  if (hasThirdPlace) {
    if (!leaf.third || !leaf.fourth) return null;
    return pathOutcomeKey(
      championId,
      runnerUpId,
      leaf.third.bracket_contestant_id,
      leaf.fourth.bracket_contestant_id,
    );
  }
  const semi = leaf.semifinalists?.[0];
  if (!semi) return null;
  return pathOutcomeKey(
    championId,
    runnerUpId,
    undefined,
    undefined,
    semi.bracket_contestant_id,
  );
}

/** Leaves that collapse into a display row (full branch, not just a prefix). */
export function leavesMatchingDisplayRow(
  row: OutcomeDisplayRow,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
): OutcomeLeafPath[] {
  const championId = row.champion.bracket_contestant_id;
  const ruIds = new Set(
    row.runnerUpTeams.map((team) => team.bracket_contestant_id),
  );
  return leaves.filter((leaf) => {
    if (leaf.champion.bracket_contestant_id !== championId) return false;
    if (!ruIds.has(leaf.runnerUp.bracket_contestant_id)) return false;
    if (!leafMatchesRowWinners(leaf, row)) return false;

    if (hasThirdPlace) {
      const thirdIds = new Set(
        row.thirdTeams.map((team) => team.bracket_contestant_id),
      );
      const fourthIds = new Set(
        row.fourthTeams.map((team) => team.bracket_contestant_id),
      );
      if (!leaf.third || !thirdIds.has(leaf.third.bracket_contestant_id)) {
        return false;
      }
      if (!leaf.fourth || !fourthIds.has(leaf.fourth.bracket_contestant_id)) {
        return false;
      }
      return true;
    }

    const semiIds = new Set(
      row.semiTeams.map((team) => team.bracket_contestant_id),
    );
    for (const semi of leaf.semifinalists ?? []) {
      if (!semiIds.has(semi.bracket_contestant_id)) return false;
    }
    return (leaf.semifinalists?.length ?? 0) > 0;
  });
}

export type OutcomeTeamMetricMode = 'outcomes' | 'likelihood';

export type DisplayRowPlacementRole = 'runner_up' | 'third' | 'fourth' | 'semi';

/** Leaves in this display row scoped to specific team(s) at one placement column. */
export function leavesMatchingDisplayRowPlacement(
  row: OutcomeDisplayRow,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  role: DisplayRowPlacementRole,
  teamIds: number[],
): OutcomeLeafPath[] {
  const championId = row.champion.bracket_contestant_id;
  const rowRuIds = new Set(
    row.runnerUpTeams.map((team) => team.bracket_contestant_id),
  );
  const rowThirdIds = new Set(
    row.thirdTeams.map((team) => team.bracket_contestant_id),
  );
  const rowFourthIds = new Set(
    row.fourthTeams.map((team) => team.bracket_contestant_id),
  );
  const rowSemiIds = new Set(
    row.semiTeams.map((team) => team.bracket_contestant_id),
  );
  const placementIds = new Set(teamIds);

  return leaves.filter((leaf) => {
    if (leaf.champion.bracket_contestant_id !== championId) return false;
    if (!leafMatchesRowWinners(leaf, row)) return false;

    if (role === 'runner_up') {
      if (!placementIds.has(leaf.runnerUp.bracket_contestant_id)) return false;
      if (hasThirdPlace) {
        if (!leaf.third || !rowThirdIds.has(leaf.third.bracket_contestant_id)) {
          return false;
        }
        if (!leaf.fourth || !rowFourthIds.has(leaf.fourth.bracket_contestant_id)) {
          return false;
        }
        return true;
      }
      for (const semi of leaf.semifinalists ?? []) {
        if (!rowSemiIds.has(semi.bracket_contestant_id)) return false;
      }
      return (leaf.semifinalists?.length ?? 0) > 0;
    }

    if (!rowRuIds.has(leaf.runnerUp.bracket_contestant_id)) return false;

    if (hasThirdPlace) {
      if (!leaf.third || !rowThirdIds.has(leaf.third.bracket_contestant_id)) {
        return false;
      }
      if (role === 'third') {
        if (!placementIds.has(leaf.third.bracket_contestant_id)) return false;
        if (!leaf.fourth || !rowFourthIds.has(leaf.fourth.bracket_contestant_id)) {
          return false;
        }
        return true;
      }
      if (!leaf.fourth) return false;
      return placementIds.has(leaf.fourth.bracket_contestant_id);
    }

    return leaf.semifinalists?.some((semi) =>
      placementIds.has(semi.bracket_contestant_id),
    );
  });
}

/** Entry-mode placement cell: mass for this row at a specific column team/cluster. */
export function sumDisplayRowPlacementMetric(
  row: OutcomeDisplayRow,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  role: DisplayRowPlacementRole,
  teamIds: number[],
  metricMode: OutcomeTeamMetricMode,
  pathLikelihood?: Record<string, number>,
): number | null {
  const matching = leavesMatchingDisplayRowPlacement(
    row,
    leaves,
    hasThirdPlace,
    role,
    teamIds,
  );
  if (matching.length === 0) return null;

  if (metricMode === 'outcomes') {
    return matching.length;
  }

  let total = 0;
  let found = false;
  for (const leaf of matching) {
    const key = deepestPathOutcomeKey(leaf, hasThirdPlace);
    if (!key) continue;
    const value = pathLikelihood?.[key];
    if (value == null || Number.isNaN(value)) continue;
    total += value;
    found = true;
  }
  return found ? total : null;
}

/** Entry-mode champion cell: total mass for this whole branch row. */
export function sumDisplayRowBranchMetric(
  row: OutcomeDisplayRow,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  metricMode: OutcomeTeamMetricMode,
  pathLikelihood?: Record<string, number>,
): number | null {
  const matching = leavesMatchingDisplayRow(row, leaves, hasThirdPlace);
  if (matching.length === 0) return null;

  if (metricMode === 'outcomes') {
    return matching.length;
  }

  let total = 0;
  let found = false;
  for (const leaf of matching) {
    const key = deepestPathOutcomeKey(leaf, hasThirdPlace);
    if (!key) continue;
    const value = pathLikelihood?.[key];
    if (value == null || Number.isNaN(value)) continue;
    total += value;
    found = true;
  }
  return found ? total : null;
}

/** Per-row branch masses on an entry card, scaled to match API winner_odds totals. */
export type EntryCardMetrics = {
  branchOutcomes: number[];
  branchLikelihood: number[];
  outcomesScale: number;
  likelihoodScale: number;
};

export function buildEntryCardMetrics(
  displayRows: OutcomeDisplayRow[],
  entryLeaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  canonicalOutcomeCount: number,
  canonicalLikelihoodPct: number | null | undefined,
  pathLikelihood?: Record<string, number>,
): EntryCardMetrics {
  const branchOutcomes = displayRows.map(
    (row) =>
      sumDisplayRowBranchMetric(row, entryLeaves, hasThirdPlace, 'outcomes') ??
      0,
  );
  const branchLikelihood = displayRows.map(
    (row) =>
      sumDisplayRowBranchMetric(
        row,
        entryLeaves,
        hasThirdPlace,
        'likelihood',
        pathLikelihood,
      ) ?? 0,
  );

  const outcomeSum = branchOutcomes.reduce((total, count) => total + count, 0);
  const likelihoodSum = branchLikelihood.reduce(
    (total, mass) => total + mass,
    0,
  );

  const outcomesScale =
    outcomeSum > 0 && canonicalOutcomeCount > 0
      ? canonicalOutcomeCount / outcomeSum
      : 1;
  const likelihoodScale =
    likelihoodSum > 0 &&
    canonicalLikelihoodPct != null &&
    !Number.isNaN(canonicalLikelihoodPct)
      ? canonicalLikelihoodPct / likelihoodSum
      : 1;

  return {
    branchOutcomes,
    branchLikelihood,
    outcomesScale,
    likelihoodScale,
  };
}

export function scaledEntryCardBranchRaw(
  metrics: EntryCardMetrics,
  rowIndex: number,
  span: number,
  metricMode: OutcomeTeamMetricMode,
): number | null {
  if (span <= 0 || rowIndex < 0 || rowIndex + span > metrics.branchOutcomes.length) {
    return null;
  }

  const source =
    metricMode === 'outcomes' ? metrics.branchOutcomes : metrics.branchLikelihood;
  const scale =
    metricMode === 'outcomes' ? metrics.outcomesScale : metrics.likelihoodScale;

  let total = 0;
  let found = false;
  for (let index = rowIndex; index < rowIndex + span; index++) {
    const raw = source[index];
    if (raw <= 0) continue;
    total += raw;
    found = true;
  }
  if (!found) return null;
  return total * scale;
}

/** Entry-mode champion cell spanning multiple sibling display rows. */
export function sumDisplayRowSpanBranchMetric(
  rows: OutcomeDisplayRow[],
  startIndex: number,
  span: number,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  metricMode: OutcomeTeamMetricMode,
  pathLikelihood?: Record<string, number>,
): number | null {
  if (span <= 0 || startIndex < 0 || startIndex + span > rows.length) {
    return null;
  }

  let total = 0;
  let found = false;
  for (let index = startIndex; index < startIndex + span; index++) {
    const raw = sumDisplayRowBranchMetric(
      rows[index],
      leaves,
      hasThirdPlace,
      metricMode,
      pathLikelihood,
    );
    if (raw == null) continue;
    total += raw;
    found = true;
  }
  return found ? total : null;
}

/** Entry-mode placement cell spanning multiple sibling display rows. */
export function sumDisplayRowsPlacementMetric(
  rows: OutcomeDisplayRow[],
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  role: DisplayRowPlacementRole,
  teamIds: number[],
  metricMode: OutcomeTeamMetricMode,
  pathLikelihood?: Record<string, number>,
): number | null {
  if (rows.length === 0) return null;

  let total = 0;
  let found = false;
  for (const row of rows) {
    const raw = sumDisplayRowPlacementMetric(
      row,
      leaves,
      hasThirdPlace,
      role,
      teamIds,
      metricMode,
      pathLikelihood,
    );
    if (raw == null) continue;
    total += raw;
    found = true;
  }
  return found ? total : null;
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

function restoreEmptyRunnerUpsFromLeaves(
  rows: OutcomeDisplayRow[],
  items: RowWithLeaves[],
): OutcomeDisplayRow[] {
  return rows.map((row, index) => {
    if (row.runnerUpTeams.length > 0) return row;
    const teams = dedupeTeams(items[index].leaves.map((leaf) => leaf.runnerUp));
    return teams.length > 0 ? { ...row, runnerUpTeams: teams } : row;
  });
}

function restoreEmptyThirdsFromLeaves(
  rows: OutcomeDisplayRow[],
  items: RowWithLeaves[],
): OutcomeDisplayRow[] {
  return rows.map((row, index) => {
    if (row.thirdTeams.length > 0) return row;
    const ruIds = new Set(
      row.runnerUpTeams.map((team) => team.bracket_contestant_id),
    );
    const teams = dedupeTeams(
      items[index].leaves
        .filter((leaf) => ruIds.has(leaf.runnerUp.bracket_contestant_id))
        .flatMap((leaf) => (leaf.third ? [leaf.third] : [])),
    );
    return teams.length > 0 ? { ...row, thirdTeams: teams } : row;
  });
}

function restoreEmptyFourthsFromLeaves(
  rows: OutcomeDisplayRow[],
  items: RowWithLeaves[],
): OutcomeDisplayRow[] {
  return rows.map((row, index) => {
    if (row.fourthTeams.length > 0) return row;
    const ruIds = new Set(
      row.runnerUpTeams.map((team) => team.bracket_contestant_id),
    );
    const thirdIds = new Set(
      row.thirdTeams.map((team) => team.bracket_contestant_id),
    );
    const teams = dedupeTeams(
      items[index].leaves
        .filter(
          (leaf) =>
            ruIds.has(leaf.runnerUp.bracket_contestant_id) &&
            leaf.third != null &&
            thirdIds.has(leaf.third.bracket_contestant_id),
        )
        .flatMap((leaf) => (leaf.fourth ? [leaf.fourth] : [])),
    );
    return teams.length > 0 ? { ...row, fourthTeams: teams } : row;
  });
}

function restoreEmptySemisFromLeaves(
  rows: OutcomeDisplayRow[],
  items: RowWithLeaves[],
): OutcomeDisplayRow[] {
  return rows.map((row, index) => {
    if (row.semiTeams.length > 0) return row;
    const ruIds = new Set(
      row.runnerUpTeams.map((team) => team.bracket_contestant_id),
    );
    const teams = dedupeTeams(
      items[index].leaves
        .filter((leaf) => ruIds.has(leaf.runnerUp.bracket_contestant_id))
        .flatMap((leaf) => leaf.semifinalists ?? []),
    );
    return teams.length > 0 ? { ...row, semiTeams: teams } : row;
  });
}

function dropUnrenderableDisplayRows(
  rows: OutcomeDisplayRow[],
  hasThirdPlace: boolean,
): OutcomeDisplayRow[] {
  return rows.filter((row) => {
    if (row.runnerUpTeams.length === 0) return false;
    if (hasThirdPlace) {
      return row.thirdTeams.length > 0 && row.fourthTeams.length > 0;
    }
    return row.semiTeams.length > 0;
  });
}

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
  rows = restoreEmptyRunnerUpsFromLeaves(rows, items);
  rows = rows.map((row, index) =>
    refreshDownstreamFromLeaves(
      row,
      items[index].leaves,
      hasThirdPlace,
      universe,
    ),
  );

  if (!hasThirdPlace) {
    rows = reconcileColumnForSiblings(
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
    rows = restoreEmptySemisFromLeaves(rows, items);
    return dropUnrenderableDisplayRows(rows, hasThirdPlace);
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
  rows = restoreEmptyThirdsFromLeaves(rows, items);
  rows = rows.map((row, index) =>
    refreshFourthFromLeaves(row, items[index].leaves, hasThirdPlace, universe),
  );

  rows = reconcileColumnForSiblings(
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
  rows = restoreEmptyFourthsFromLeaves(rows, items);
  return dropUnrenderableDisplayRows(rows, hasThirdPlace);
}

/** Seed sibling reconciliation with per-runner-up rows so ALL does not swallow distinct branches. */
function buildInitialGroupItems(
  champion: ChallengeStatsSimilarityTeam,
  leaves: OutcomeLeafPath[],
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
): RowWithLeaves[] {
  const clustered = buildMaxClusteredRow(
    champion,
    leaves,
    hasThirdPlace,
    universe,
  );
  const ruUniverse = universe.runnerUps(champion.bracket_contestant_id);
  if (!isExhaustiveCluster(clustered.runnerUpTeams, ruUniverse)) {
    return [{ row: clustered, leaves }];
  }

  const byRunnerUp = new Map<number, OutcomeLeafPath[]>();
  for (const leaf of leaves) {
    const runnerUpId = leaf.runnerUp.bracket_contestant_id;
    const bucket = byRunnerUp.get(runnerUpId) ?? [];
    bucket.push(leaf);
    byRunnerUp.set(runnerUpId, bucket);
  }
  if (byRunnerUp.size <= 1) {
    return [{ row: clustered, leaves }];
  }

  const branchSizes = [...byRunnerUp.values()].map((group) => group.length);
  const shouldSplit =
    Math.min(...branchSizes) !== Math.max(...branchSizes) ||
    (branchSizes.some((size) => size === 1) &&
      branchSizes.some((size) => size > 1));
  if (!shouldSplit) {
    return [{ row: clustered, leaves }];
  }

  return [...byRunnerUp.values()].map((groupLeaves) => ({
    row: buildMaxClusteredRow(champion, groupLeaves, hasThirdPlace, universe),
    leaves: groupLeaves,
  }));
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

    for (const group of winnerGroups) {
      const groupItems = buildInitialGroupItems(
        champion,
        group,
        hasThirdPlace,
        universe,
      );
      rows.push(
        ...reconcileSiblingPlacementSplits(groupItems, universe, hasThirdPlace),
      );
    }
  }

  return rows;
}
