import type { BracketStageInfo } from './api';

/** Teams that advance directly from each group (top N). */
export function contestantsQualifyingPerGroup(
  stage: BracketStageInfo,
): number {
  return stage.group?.contestants_qualifying_per_group ?? 0;
}

export function groupPositionPicking(
  stage: BracketStageInfo,
): 'all' | 'qualifying_only' {
  return stage.group?.group_position_picking === 'qualifying_only'
    ? 'qualifying_only'
    : 'all';
}

/**
 * Extra knockout spots filled from group also-rans (e.g. 8 best third-place teams).
 * Derived from ``contestants_advancing`` minus direct qualifiers.
 */
/** Third-place pool size from the first knockout stage field size when set. */
export function thirdPlaceAdvanceCount(
  stage: BracketStageInfo,
  opts?: { firstKnockoutContestants?: number },
): number {
  const g = stage.group;
  if (!g) return 0;
  const direct = g.number_of_groups * g.contestants_qualifying_per_group;
  const koSize = opts?.firstKnockoutContestants;
  if (koSize != null && koSize > direct) {
    return koSize - direct;
  }
  if (stage.contestants_advancing == null) return 0;
  return Math.max(0, stage.contestants_advancing - direct);
}

/**
 * Finish ranks that must be filled per group before submit.
 * Under ``qualifying_only``, only the direct qualifiers (top q) — third-place
 * advancers are picked separately from remaining teams.
 */
export function placementRanksRequired(
  stage: BracketStageInfo,
  opts?: { firstKnockoutContestants?: number },
): number {
  const q = contestantsQualifyingPerGroup(stage);
  if (groupPositionPicking(stage) === 'qualifying_only') {
    return q;
  }
  return q + (thirdPlaceAdvanceCount(stage, opts) > 0 ? 1 : 0);
}
