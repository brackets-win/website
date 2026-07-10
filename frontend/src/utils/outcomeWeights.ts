import type {
  BracketDetail,
  BracketStageInfo,
  MatchupInfo,
  UserBracketDetail,
} from './api';

export type OutcomeWeightsConfig = {
  team_rankings: Record<string, number>;
  matchup_odds: Record<string, number>;
};

const OUTCOME_WEIGHTS_KEY = 'outcome_weights';
const TEAM_RANKINGS_KEY = 'team_rankings';
const MATCHUP_ODDS_KEY = 'matchup_odds';

export function getOutcomeWeightsFromMetadata(
  metadata: unknown,
): OutcomeWeightsConfig {
  if (!metadata || typeof metadata !== 'object') {
    return { team_rankings: {}, matchup_odds: {} };
  }
  const raw = (metadata as Record<string, unknown>)[OUTCOME_WEIGHTS_KEY];
  if (!raw || typeof raw !== 'object') {
    return { team_rankings: {}, matchup_odds: {} };
  }
  const block = raw as Record<string, unknown>;
  const team_rankings: Record<string, number> = {};
  const matchup_odds: Record<string, number> = {};

  if (block[TEAM_RANKINGS_KEY] && typeof block[TEAM_RANKINGS_KEY] === 'object') {
    for (const [key, value] of Object.entries(
      block[TEAM_RANKINGS_KEY] as Record<string, unknown>,
    )) {
      const rank = Number(value);
      if (Number.isFinite(rank) && rank >= 1) {
        team_rankings[key] = Math.trunc(rank);
      }
    }
  }

  if (block[MATCHUP_ODDS_KEY] && typeof block[MATCHUP_ODDS_KEY] === 'object') {
    for (const [key, value] of Object.entries(
      block[MATCHUP_ODDS_KEY] as Record<string, unknown>,
    )) {
      const pct = Number(value);
      if (Number.isFinite(pct) && pct >= 0 && pct <= 100) {
        matchup_odds[key] = Math.round(pct * 10) / 10;
      }
    }
  }

  return { team_rankings, matchup_odds };
}

function isThirdPlaceStage(stage: BracketStageInfo): boolean {
  return stage.knockout?.is_third_place === true;
}

function knockoutStages(bracket: BracketDetail): BracketStageInfo[] {
  return [...bracket.stages]
    .filter((stage) => stage.stage_type === 'KNOCKOUT')
    .sort((a, b) => a.order - b.order);
}

function matchupsForStage(
  detail: UserBracketDetail,
  stageId: number,
): MatchupInfo[] {
  const bucket = detail.matchups_by_stage.find(
    (row) => row.stage_id === stageId,
  );
  return bucket?.matchups ?? [];
}

export function currentRoundUndecidedMatchups(
  bracket: BracketDetail,
  detail: UserBracketDetail,
): MatchupInfo[] {
  const mainStages = knockoutStages(bracket).filter(
    (stage) => !isThirdPlaceStage(stage),
  );

  for (const stage of mainStages) {
    const matchups = matchupsForStage(detail, stage.id);
    if (matchups.length === 0) continue;
    if (matchups.every((matchup) => matchup.winner != null)) continue;
    return undecidedPairedMatchups(matchups);
  }

  return [];
}

/** Every main-bracket KO game that is paired and still undecided. */
export function allUndecidedPairedMatchups(
  bracket: BracketDetail,
  detail: UserBracketDetail,
): MatchupInfo[] {
  const rows: MatchupInfo[] = [];
  for (const stage of knockoutStages(bracket)) {
    if (isThirdPlaceStage(stage)) continue;
    rows.push(...undecidedPairedMatchups(matchupsForStage(detail, stage.id)));
  }
  return rows;
}

/** Later-round games that are already set but not in the current round. */
export function upcomingUndecidedMatchups(
  bracket: BracketDetail,
  detail: UserBracketDetail,
): MatchupInfo[] {
  const currentIds = new Set(
    currentRoundUndecidedMatchups(bracket, detail).map((matchup) => matchup.id),
  );
  return allUndecidedPairedMatchups(bracket, detail).filter(
    (matchup) => !currentIds.has(matchup.id),
  );
}

function undecidedPairedMatchups(matchups: MatchupInfo[]): MatchupInfo[] {
  return matchups.filter(
    (matchup) =>
      matchup.winner == null &&
      matchup.contestant1 != null &&
      matchup.contestant2 != null,
  );
}

export function currentRoundTeamIds(
  bracket: BracketDetail,
  detail: UserBracketDetail,
): NonNullable<MatchupInfo['contestant1']>[] {
  const mainStages = knockoutStages(bracket).filter(
    (stage) => !isThirdPlaceStage(stage),
  );

  for (const stage of mainStages) {
    const matchups = matchupsForStage(detail, stage.id);
    if (matchups.length === 0) continue;
    if (matchups.every((matchup) => matchup.winner != null)) continue;

    const teams = new Map<number, NonNullable<MatchupInfo['contestant1']>>();
    for (const matchup of matchups) {
      if (matchup.contestant1) {
        teams.set(matchup.contestant1.id, matchup.contestant1);
      }
      if (matchup.contestant2) {
        teams.set(matchup.contestant2.id, matchup.contestant2);
      }
    }
    return [...teams.values()].sort((a, b) =>
      a.display_name.localeCompare(b.display_name, undefined, {
        sensitivity: 'base',
      }),
    );
  }

  return [];
}

export function remainingKnockoutTeams(
  bracket: BracketDetail,
  detail: UserBracketDetail,
): NonNullable<MatchupInfo['contestant1']>[] {
  return currentRoundTeamIds(bracket, detail);
}

export function savedPriorRoundMatchups(
  bracket: BracketDetail,
  detail: UserBracketDetail,
): { matchup: MatchupInfo; odds: number }[] {
  const saved = getOutcomeWeightsFromMetadata(bracket.metadata);
  const currentIds = new Set(
    currentRoundUndecidedMatchups(bracket, detail).map((matchup) => matchup.id),
  );
  const rows: { matchup: MatchupInfo; odds: number }[] = [];

  for (const stage of knockoutStages(bracket)) {
    for (const matchup of matchupsForStage(detail, stage.id)) {
      if (currentIds.has(matchup.id)) continue;
      if (!matchup.contestant1 || !matchup.contestant2) continue;
      if (matchup.winner == null) continue;
      const odds = saved.matchup_odds[String(matchup.id)];
      if (odds == null) continue;
      rows.push({ matchup, odds });
    }
  }

  return rows;
}

export function showOutcomeWeightsControl(
  bracket: BracketDetail,
  detail: UserBracketDetail,
): boolean {
  const current = currentRoundUndecidedMatchups(bracket, detail);
  return current.length > 0 && current.length <= 4;
}
