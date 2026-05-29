import type { BracketStageInfo } from '../../utils/api';

/** One column in the mirror bracket (left half, final, or right half). */
export type MirrorBracketColumn = {
  key: string;
  stage: BracketStageInfo;
  stageIdx: number;
  positionMin: number;
  positionMax: number;
  side: 'left' | 'center' | 'right';
  /** First-round positions for this wing (used for vertical alignment). */
  wingMin: number;
  wingMax: number;
};

export type MirrorBracketLayout = {
  left: MirrorBracketColumn[];
  center: MirrorBracketColumn | null;
  right: MirrorBracketColumn[];
};

/**
 * Split bracket when the opening knockout stage has 32+ contestants:
 * left wing and right wing converge on the final in the center.
 */
export function buildMirrorBracketLayout(
  stages: BracketStageInfo[],
  leaves: number,
  openingContestants: number,
): MirrorBracketLayout | null {
  if (openingContestants < 32 || leaves < 2 || stages.length === 0) {
    return null;
  }

  const finalIdx = stages.findIndex((s) => s.knockout?.is_final);
  const splitEnd = finalIdx >= 0 ? finalIdx : stages.length;
  const halfLeaves = leaves / 2;

  const left: MirrorBracketColumn[] = [];
  const right: MirrorBracketColumn[] = [];

  for (let stageIdx = 0; stageIdx < splitEnd; stageIdx++) {
    const stage = stages[stageIdx];
    const matchupsInStage = leaves / 2 ** stageIdx;
    const leftMax = matchupsInStage / 2;
    left.push({
      key: `L-${stage.id}`,
      stage,
      stageIdx,
      positionMin: 1,
      positionMax: leftMax,
      side: 'left',
      wingMin: 1,
      wingMax: halfLeaves,
    });
  }

  let center: MirrorBracketColumn | null = null;
  const finalStage = finalIdx >= 0 ? stages[finalIdx] : undefined;
  if (finalStage) {
    center = {
      key: `F-${finalStage.id}`,
      stage: finalStage,
      stageIdx: finalIdx,
      positionMin: 1,
      positionMax: 1,
      side: 'center',
      wingMin: 1,
      wingMax: 1,
    };
  }

  // Same stage order as left (R32 → … → SF); CSS row-reverse places SF beside the final.
  for (let stageIdx = 0; stageIdx < splitEnd; stageIdx++) {
    const stage = stages[stageIdx];
    const matchupsInStage = leaves / 2 ** stageIdx;
    const rightMin = matchupsInStage / 2 + 1;
    right.push({
      key: `R-${stage.id}`,
      stage,
      stageIdx,
      positionMin: rightMin,
      positionMax: matchupsInStage,
      side: 'right',
      wingMin: halfLeaves + 1,
      wingMax: leaves,
    });
  }

  return { left, center, right };
}

/** First matchup position in this wing at ``stageIdx`` (left wing is always 1). */
export function wingStagePositionMin(
  stageIdx: number,
  wingMin: number,
  halfLeaves: number,
): number {
  if (wingMin === 1) return 1;
  return Math.floor(halfLeaves / 2 ** stageIdx) + 1;
}

/** Vertical % within a wing column (full height, not global bracket offset). */
export function columnMatchupCenterPct(
  stageIdx: number,
  position: number,
  wingMin: number,
  wingMax: number,
  _positionMin: number,
  feederTopPos?: number,
  feederBottomPos?: number,
): number {
  if (stageIdx === 0) {
    const count = wingMax - wingMin + 1;
    const idx = position - wingMin;
    return ((idx + 0.5) / count) * 100;
  }
  const halfLeaves = wingMax - wingMin + 1;
  const feederTop = feederTopPos ?? 2 * position - 1;
  const feederBot = feederBottomPos ?? 2 * position;
  const prevPosMin = wingStagePositionMin(stageIdx - 1, wingMin, halfLeaves);
  const top = columnMatchupCenterPct(
    stageIdx - 1,
    feederTop,
    wingMin,
    wingMax,
    prevPosMin,
  );
  const bot = columnMatchupCenterPct(
    stageIdx - 1,
    feederBot,
    wingMin,
    wingMax,
    prevPosMin,
  );
  return (top + bot) / 2;
}
