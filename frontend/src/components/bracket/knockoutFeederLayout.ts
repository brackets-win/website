import type {
  BracketStageInfo,
  MatchupInfo,
  UserBracketDetail,
} from '../../utils/api';
import { wingStagePositionMin } from './bracketMirrorLayout';

/** Knockout stage immediately before the final (e.g. semifinals). */
export function prevKnockoutStageBeforeFinal(
  stages: BracketStageInfo[],
): BracketStageInfo | null {
  const ordered = [...stages].sort((a, b) => a.order - b.order);
  const final = ordered.find((s) => s.knockout?.is_final);
  if (final) {
    const idx = ordered.findIndex((s) => s.id === final.id);
    return idx > 0 ? ordered[idx - 1] : null;
  }
  return ordered.length >= 2 ? ordered[ordered.length - 2] : null;
}

export function findMatchupById(
  detail: UserBracketDetail,
  matchupId: number,
): MatchupInfo | undefined {
  for (const pack of detail.matchups_by_stage) {
    const found = pack.matchups.find((m) => m.id === matchupId);
    if (found) return found;
  }
  return undefined;
}

/** R32 (etc.) games that feed this matchup, ordered top → bottom by tree position. */
export function resolveFeederMatchups(
  m: MatchupInfo,
  detail: UserBracketDetail,
  prevStageId: number | null,
  opts?: { useTreeFeeders?: boolean },
): { top: MatchupInfo | null; bottom: MatchupInfo | null } {
  if (prevStageId == null) {
    return { top: null, bottom: null };
  }

  const useTree = opts?.useTreeFeeders !== false;
  const hasExplicitSources =
    m.source_a_matchup_id != null || m.source_b_matchup_id != null;

  // Reseed / randomize rounds are not fed by fixed tree slots.
  if (!useTree && !hasExplicitSources) {
    return { top: null, bottom: null };
  }

  const prev = matchupsForStage(detail, prevStageId);
  const np = m.position;

  const rawTop =
    m.source_a_matchup_id != null
      ? findMatchupById(detail, m.source_a_matchup_id)
      : useTree
        ? (prev.find((x) => x.position === 2 * np - 1) ?? null)
        : null;
  const rawBottom =
    m.source_b_matchup_id != null
      ? findMatchupById(detail, m.source_b_matchup_id)
      : useTree
        ? (prev.find((x) => x.position === 2 * np) ?? null)
        : null;

  if (!rawTop || !rawBottom) {
    return { top: rawTop ?? null, bottom: rawBottom ?? null };
  }

  if (rawTop.position <= rawBottom.position) {
    return { top: rawTop, bottom: rawBottom };
  }
  return { top: rawBottom, bottom: rawTop };
}

export function stageUsesTreeFeeders(stage: BracketStageInfo | undefined): boolean {
  const mode = stage?.knockout?.seeding_mode ?? 'standard';
  return mode === 'standard';
}

export function feederSortKey(
  m: MatchupInfo,
  detail: UserBracketDetail,
  prevStageId: number | null,
  opts?: { useTreeFeeders?: boolean },
): number {
  const { top, bottom } = resolveFeederMatchups(m, detail, prevStageId, opts);
  if (top && bottom) return top.position;
  if (top) return top.position;
  if (bottom) return bottom.position;
  return m.position;
}

export function sortMatchupsByFeederOrder(
  matchups: MatchupInfo[],
  detail: UserBracketDetail,
  prevStageId: number | null,
  opts?: { useTreeFeeders?: boolean },
): MatchupInfo[] {
  return [...matchups].sort(
    (a, b) =>
      feederSortKey(a, detail, prevStageId, opts) -
      feederSortKey(b, detail, prevStageId, opts),
  );
}

function matchupsForStage(
  ub: UserBracketDetail,
  stageId: number,
): MatchupInfo[] {
  const pack = ub.matchups_by_stage.find((s) => s.stage_id === stageId);
  return pack ? [...pack.matchups].sort((a, b) => a.position - b.position) : [];
}

/** Vertical center for a later-round box from its feeder positions on the prior round. */
export function centerPctBetweenFeeders(
  stageIdx: number,
  feederTopPos: number,
  feederBottomPos: number,
  wingMin: number,
  wingMax: number,
  openingPositionMin: number,
): number {
  const top = openingCenterPct(
    stageIdx - 1,
    feederTopPos,
    wingMin,
    wingMax,
    openingPositionMin,
  );
  const bot = openingCenterPct(
    stageIdx - 1,
    feederBottomPos,
    wingMin,
    wingMax,
    openingPositionMin,
  );
  return (top + bot) / 2;
}

function openingCenterPct(
  stageIdx: number,
  position: number,
  wingMin: number,
  wingMax: number,
  _positionMin: number,
): number {
  if (stageIdx === 0) {
    const count = wingMax - wingMin + 1;
    const idx = position - wingMin;
    return ((idx + 0.5) / count) * 100;
  }
  const feederTop = 2 * position - 1;
  const feederBot = 2 * position;
  const halfLeaves = wingMax - wingMin + 1;
  const prevPosMin = wingStagePositionMin(stageIdx - 1, wingMin, halfLeaves);
  return centerPctBetweenFeeders(
    stageIdx,
    feederTop,
    feederBot,
    wingMin,
    wingMax,
    prevPosMin,
  );
}
