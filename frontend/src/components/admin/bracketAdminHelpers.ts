import type {
  AdminStagePatch,
  BracketStageInfo,
  BracketStructureConfig,
  BracketStructureType,
} from '../../utils/api';

export function metadataToText(value: unknown): string {
  if (value == null) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return '';
  }
}

export function parseMetadataJson(text: string): unknown {
  const t = text.trim();
  if (!t) return null;
  return JSON.parse(t) as unknown;
}

export function buildStructureConfig(opts: {
  structureKind: BracketStructureType;
  bNumGroups: string;
  bMatchesPer: number;
  bQualify: number;
  bPtWin: number;
  bPtTie: number;
  bPtLoss: number;
  bTiesAllowed: boolean;
  bGroupExactPts: number;
  bGroupAdvancerPts: number;
  bGroupRandom: boolean;
  bChampionPts: number;
  bThirdPlacePts: number;
  bKoLegs: number;
  bKoET: boolean;
  bKoPK: boolean;
  bKoPickPts: number;
  bKoRandom: boolean;
}): BracketStructureConfig {
  const cfg: BracketStructureConfig = {
    knockout: {
      number_of_legs: opts.bKoLegs,
      has_extra_time: opts.bKoET,
      has_penalty_shootout: opts.bKoPK,
      points_per_correct_pick: opts.bKoPickPts,
      is_random_draw: opts.bKoRandom,
    },
  };
  if (opts.structureKind === 'GROUP_KNOCKOUT') {
    const gs: NonNullable<BracketStructureConfig['group_stage']> = {
      matches_per_contestant: opts.bMatchesPer,
      contestants_qualifying_per_group: opts.bQualify,
      points_per_win: opts.bPtWin,
      points_per_tie: opts.bPtTie,
      points_per_loss: opts.bPtLoss,
      ties_allowed: opts.bTiesAllowed,
      points_per_exact_position: opts.bGroupExactPts,
      points_per_advancer: opts.bGroupAdvancerPts,
      is_random_draw: opts.bGroupRandom,
    };
    const ng = opts.bNumGroups.trim();
    if (ng !== '') {
      gs.number_of_groups = parseInt(ng, 10);
    }
    cfg.group_stage = gs;
  }
  cfg.points_champion = opts.bChampionPts;
  cfg.points_third_place_winner = opts.bThirdPlacePts;
  return cfg;
}

export function isPowerOfTwo(n: number): boolean {
  return Number.isInteger(n) && n >= 2 && (n & (n - 1)) === 0;
}

/**
 * Seeds 1..N in first-round tree order (top game first, then downward).
 * Mirrors the backend ``bracket_seed_order``. Returns null when N is not a
 * power of two (no standard single-elim layout exists).
 */
export function bracketSeedOrder(n: number): number[] | null {
  if (!isPowerOfTwo(n)) return null;
  let order = [1];
  while (order.length < n) {
    const size = order.length * 2;
    order = order.flatMap((x) => [x, size + 1 - x]);
  }
  return order;
}

export type FirstRoundGame = {
  position: number;
  topSeed: number;
  bottomSeed: number | null;
};

/**
 * First-round games for a visual seeder. For power-of-two fields this matches
 * the backend seed pairing exactly; otherwise it falls back to sequential
 * adjacent pairs so the admin can still place every contestant (a final odd
 * seed becomes a bye).
 */
export function firstRoundSeedGames(n: number): FirstRoundGame[] {
  const order = bracketSeedOrder(n);
  if (order) {
    const games: FirstRoundGame[] = [];
    for (let i = 0; i < order.length; i += 2) {
      games.push({
        position: games.length + 1,
        topSeed: order[i],
        bottomSeed: order[i + 1],
      });
    }
    return games;
  }
  const games: FirstRoundGame[] = [];
  for (let seed = 1; seed <= n; seed += 2) {
    games.push({
      position: games.length + 1,
      topSeed: seed,
      bottomSeed: seed + 1 <= n ? seed + 1 : null,
    });
  }
  return games;
}

export function stageToAdminPatch(s: BracketStageInfo): AdminStagePatch {
  const patch: AdminStagePatch = {
    id: s.id,
    name: s.name,
    points_per_correct_pick: s.points_per_correct_pick,
    is_random_draw: s.is_random_draw,
    metadata: s.metadata,
  };
  if (s.group) {
    patch.number_of_groups = s.group.number_of_groups;
    patch.matches_per_contestant = s.group.matches_per_contestant;
    patch.contestants_qualifying_per_group = s.group.contestants_qualifying_per_group;
    patch.remaining_spots_strategy = s.group.remaining_spots_strategy;
    patch.points_per_win = s.group.points_per_win;
    patch.points_per_tie = s.group.points_per_tie;
    patch.points_per_loss = s.group.points_per_loss;
    patch.points_per_exact_position = s.group.points_per_exact_position ?? 0;
    patch.points_per_advancer = s.group.points_per_advancer ?? 0;
    patch.ties_allowed = s.group.ties_allowed;
  }
  if (s.knockout) {
    patch.number_of_legs = s.knockout.number_of_legs;
    patch.has_extra_time = s.knockout.has_extra_time;
    patch.has_penalty_shootout = s.knockout.has_penalty_shootout;
    patch.is_final = s.knockout.is_final;
  }
  return patch;
}
