import type { BracketStageInfo } from './api';

/** Teams that advance directly from each group (top N). */
export function contestantsQualifyingPerGroup(
  stage: BracketStageInfo,
): number {
  return stage.group?.contestants_qualifying_per_group ?? 0;
}

/**
 * Extra knockout spots filled from group also-rans (e.g. 8 best third-place teams).
 * Derived from ``contestants_advancing`` minus direct qualifiers.
 */
export function thirdPlaceAdvanceCount(stage: BracketStageInfo): number {
  const g = stage.group;
  if (!g || stage.contestants_advancing == null) return 0;
  const direct = g.number_of_groups * g.contestants_qualifying_per_group;
  return Math.max(0, stage.contestants_advancing - direct);
}

/** Finish ranks that must be filled per group before submit (includes 3rd when needed). */
export function placementRanksRequired(stage: BracketStageInfo): number {
  const q = contestantsQualifyingPerGroup(stage);
  return q + (thirdPlaceAdvanceCount(stage) > 0 ? 1 : 0);
}
