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
  bGroupPickPts: number;
  bGroupRandom: boolean;
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
      points_per_correct_pick: opts.bGroupPickPts,
      is_random_draw: opts.bGroupRandom,
    };
    const ng = opts.bNumGroups.trim();
    if (ng !== '') {
      gs.number_of_groups = parseInt(ng, 10);
    }
    cfg.group_stage = gs;
  }
  return cfg;
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
