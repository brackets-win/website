/** JSON API client for the Django backend (session cookies). */

/** Same origin in dev (Vite proxy) and prod (brackets.win → Fly proxy). */
const apiRoot = `${window.location.origin}/brackets/api`;

export type ApiUser = {
  id: number;
  username: string;
  /** Staff users can access admin API routes. */
  is_staff?: boolean;
  must_change_password?: boolean;
};

export type AdminUserRow = {
  id: number;
  username: string;
  is_staff: boolean;
  must_change_password: boolean;
  date_joined: string | null;
};

export type ContestantTagInfo = {
  id: number;
  name: string;
};

export type ContestantCatalog = {
  id: number;
  identifier: string;
  name: string;
  description: string;
  image_url: string;
  metadata: unknown;
  tags: ContestantTagInfo[];
  photo_url?: string | null;
};

export type ChallengeUserEntry = {
  user_bracket_id: number;
  display_name: string;
  is_submitted: boolean;
  is_complete: boolean;
};

export type LeaderboardPreviewEntry = {
  rank: number;
  display_name: string;
  points: number;
  points_label?: string;
  is_viewer?: boolean;
};

export type LeaderboardPreview = {
  top: LeaderboardPreviewEntry[];
  viewer?: LeaderboardPreviewEntry | null;
  gap_before_viewer?: boolean;
};

export type ChallengeSummary = {
  id: number;
  name: string;
  created_by_username: string;
  bracket_id: number;
  bracket_name: string;
  bracket_image_url?: string | null;
  instance_type: string;
  instance_type_label?: string;
  needs_user_bracket?: boolean;
  uses_prediction_leaderboard?: boolean;
  is_public: boolean;
  is_private: boolean;
  join_code: string | null;
  submission_deadline: string | null;
  deadline_passed: boolean;
  max_entries: number;
  entry_count: number;
  user_bracket_id: number | null;
  user_entries: ChallengeUserEntry[];
  is_submitted: boolean;
  can_view_peer_brackets?: boolean;
  is_complete: boolean;
  can_join: boolean;
  can_add_entry: boolean;
  can_edit_picks: boolean;
  can_manage_bracket?: boolean;
  is_creator?: boolean;
  max_entries_minimum?: number | null;
  master_user_bracket_id?: number | null;
  tournament_team_count?: number | null;
  teams_configured?: boolean | null;
  leaderboard_preview?: LeaderboardPreview;
  show_live_group_results_note?: boolean;
  show_outcomes_tab?: boolean;
};

export type TournamentTeamRow = {
  id?: number;
  name: string;
  seed: number | null;
};

export type StreakCompetitionSummary = {
  id: number;
  name: string;
  image_url?: string | null;
  question_count: number;
  challenge_count?: number;
  ended_at?: string | null;
  is_over?: boolean;
};

export type StreakQuestionChoiceInfo = {
  id: number;
  label: string;
  /** Whole-number share of challenge picks; present on resolved questions only. */
  pick_pct?: number;
  /** Number of entrants who picked this choice; present on resolved questions only. */
  pick_count?: number;
  pickers?: StreakStatsPicker[];
};

export type StreakCompetitionQuestionAdmin = {
  id: number;
  text: string;
  closes_at: string;
  resolved_at: string | null;
  choices: StreakQuestionChoiceInfo[];
  correct_choice_id: number | null;
  correct_answer: string | null;
  order: number;
  is_open: boolean;
  pick_count: number;
  knockout_only?: boolean;
};

export type KnockoutPhaseInfo = {
  round_index: number;
  label: string;
  starts_at: string;
  headstart_enabled?: boolean;
};

export type StreakKnockoutHeaderSummary = {
  kind: 'matchup' | 'consolation';
  label: string;
  value: string;
};

export type StreakChallengeSummary = {
  id: number;
  name: string;
  streak_competition_id: number;
  streak_competition_name: string;
  image_url: string | null;
  created_by_username: string;
  is_public: boolean;
  is_private: boolean;
  join_code: string | null;
  is_participant: boolean;
  wins: number;
  losses: number;
  streak_signed: number;
  best_win_streak: number;
  broken_win_streak?: number;
  streak_display: string;
  current_display: string;
  long_win_display: string;
  is_creator?: boolean;
  competition_is_over?: boolean;
  competition_ended_at?: string | null;
  leaderboard_preview?: LeaderboardPreview;
  mode?: 'STREAK' | 'KNOCKOUT';
  is_knockout?: boolean;
  knockout_transition_at?: string | null;
  knockout_round_starts?: Record<string, string>;
  knockout_round_headstart?: Record<string, boolean>;
  knockout_third_place_match?: boolean;
  knockout_third_place_editable?: boolean;
  knockout_total_rounds?: number;
  knockout_header?: StreakKnockoutHeaderSummary | null;
};

export type StreakQuestionInfo = {
  id: number;
  text: string;
  closes_at: string;
  resolved_at: string | null;
  choices: StreakQuestionChoiceInfo[];
  correct_choice_id: number | null;
  correct_answer: string | null;
  user_choice_id: number | null;
  user_answer: string | null;
  is_open: boolean;
  deadline_locked: boolean;
  locked_by_question_id: number | null;
  can_clear_pick: boolean;
  knockout_only?: boolean;
  is_knockout_pick?: boolean;
  knockout_phase_label?: string | null;
  knockout_phase_starts_at?: string | null;
};

export type StreakLeaderboardEntry = {
  rank: number;
  user_id: number;
  username: string;
  display_name: string;
  streak_signed: number;
  current_display: string;
  long_win_display: string;
  long_loss_display: string;
  wins: number;
  losses: number;
  record: string;
  win_pct: number;
  season_wins: number;
  season_losses: number;
  season_record: string;
  season_win_pct: number;
  streak_wins: number;
  streak_losses: number;
  streak_record: string;
  streak_win_pct: number;
  knockout_wins: number;
  knockout_losses: number;
  knockout_record: string;
  knockout_win_pct: number;
  consolation_wins: number;
  consolation_losses: number;
  consolation_record: string;
  consolation_win_pct: number;
  total_wins: number;
  total_losses: number;
  total_record: string;
  total_win_pct: number;
  best_win_streak: number;
  best_loss_streak: number;
  broken_win_streak?: number;
  /** @deprecated use current_display */
  streak_display?: string;
  /** @deprecated use win_pct */
  win_rate?: number;
};


export type StreakAwardWinner = {
  user_id: number;
  username: string;
  display_name: string;
  long_win_display?: string;
  best_win_streak?: number;
  long_loss_display?: string;
  best_loss_streak?: number;
  win_pct?: number;
  wins?: number;
  record?: string;
  current_display?: string;
  streak_signed?: number;
};

export type StreakAwardCategory = {
  winners: StreakAwardWinner[];
};

export type StreakAwardQuestionWinner = {
  question_id: number;
  text: string;
  closes_at: string;
  correct_choice_id: number | null;
  choices: StreakQuestionChoiceInfo[];
  correct_count?: number;
  incorrect_count?: number;
  player?: {
    user_id: number;
    username: string;
    display_name: string;
  } | null;
  broken_win_streak?: number;
  long_win_display?: string;
};

export type StreakAwardQuestionCategory = {
  winners: StreakAwardQuestionWinner[];
};

export type StreakAwardsPayload = {
  had_knockout?: boolean;
  streak_champion: StreakAwardCategory;
  knockout_first?: StreakAwardCategory;
  knockout_second?: StreakAwardCategory;
  knockout_third?: StreakAwardCategory;
  best_streak?: StreakAwardCategory;
  consolation_champion?: StreakAwardCategory;
  best_picker: StreakAwardCategory;
  most_wins: StreakAwardCategory;
  active_streak: StreakAwardCategory;
  losing_streak: StreakAwardCategory;
  nicest_question: StreakAwardQuestionCategory;
  meanest_question: StreakAwardQuestionCategory;
  streak_ending_question: StreakAwardQuestionCategory;
};

export type StreakKnockoutPlayerSlot = {
  user_id: number;
  display_name: string;
  seed: number | null;
};

export type StreakKnockoutMatch = {
  id: number;
  round_index: number;
  position: number;
  player_a: StreakKnockoutPlayerSlot | null;
  player_b: StreakKnockoutPlayerSlot | null;
  seed_a: number;
  seed_b: number;
  score_a: number;
  score_b: number;
  score_a_correct: number;
  score_b_correct: number;
  score_a_bonus: number;
  score_b_bonus: number;
  score_bonus_enabled: boolean;
  winner_user_id: number | null;
  finalized: boolean;
  is_live: boolean;
  is_third_place?: boolean;
};

export type StreakKnockoutRound = {
  round_index: number;
  matches: StreakKnockoutMatch[];
};

export type StreakConsolationEntry = {
  user_id: number;
  display_name: string;
  wins: number;
  losses: number;
  record: string;
  win_pct: number;
};

export type StreakKnockoutPayload = {
  status: 'SETUP' | 'IN_PROGRESS' | 'COMPLETE';
  current_round: number;
  headstart_enabled: boolean;
  champion_user_id: number | null;
  third_place_winner_user_id?: number | null;
  third_place_match?: StreakKnockoutMatch | null;
  third_place_match_enabled?: boolean;
  total_rounds: number;
  rounds: StreakKnockoutRound[];
  consolation: StreakConsolationEntry[];
  can_manage: boolean;
  projected?: boolean;
};

export type StreakParticipantPickRow = {
  question_id: number;
  text: string;
  closes_at: string;
  choices: StreakQuestionChoiceInfo[];
  pick_choice_id: number;
  correct_choice_id: number | null;
  pick_label: string;
  correct_answer: string | null;
  is_correct: boolean;
  section_key?: string;
  section_label?: string;
};

export type StreakStatsPicker = {
  user_id: number;
  display_name: string;
};

export type StreakStatsChoice = {
  id: number;
  label: string;
  pick_count: number;
  pick_pct: number;
  pickers: StreakStatsPicker[];
};

export type StreakStatsQuestion = {
  question_id: number;
  text: string;
  closes_at: string;
  correct_choice_id: number | null;
  choices: StreakStatsChoice[];
};

export type StreakChallengeStatsPayload = {
  questions: StreakStatsQuestion[];
};

export type LeaderboardColumn = {
  key: string;
  name: string;
};

export type LeaderboardDenominators = {
  total: number;
  potential: number;
  columns: Record<string, number>;
};

export type ScoringHighlights = {
  group_positions: Record<string, Record<string, boolean>>;
  group_advancers: number[];
  knockout_contestants: { stage_id: number; contestant_id: number }[];
  champion_contestant_id: number | null;
  third_place_contestant_id: number | null;
};

export type TopFourPick = {
  bracket_contestant_id: number;
  image_url: string | null;
  display_name: string;
};

export type LeaderboardEntry = {
  username: string;
  display_name: string;
  user_bracket_id: number;
  score: number | null;
  potential: number | null;
  potential_rank: number | null;
  stage_scores: Record<string, number | null>;
  top_four_picks: (TopFourPick | null)[];
  /** Contestant this entry wants to win the admin-set next match (or null). */
  next_match_pick?: TopFourPick | null;
  submitted_at: string | null;
};

export type BracketTemplateSummary = {
  id: number;
  name: string;
  template_type: BracketStructureType;
  description: string;
  default_number_of_contestants: number | null;
  is_system: boolean;
};

export type BracketSummary = {
  id: number;
  identifier: string;
  name: string;
  description: string;
  image_url?: string | null;
  created_at: string;
  randomize_seeds_per_challenge: boolean;
  /** Single elimination: optional third-place match (semifinal losers). */
  has_third_place_match?: boolean;
  points_champion?: number;
  points_third_place_winner?: number;
  show_seeds?: boolean;
  metadata: unknown;
  challenge_count?: number;
  is_reusable?: boolean;
};

export type BracketContestantInfo = {
  id: number;
  display_name: string;
  seed: number | null;
  contestant_id: number | null;
  image_url: string | null;
};

export type MatchupInfo = {
  id: number;
  stage_id: number;
  position: number;
  contestant1: BracketContestantInfo | null;
  contestant2: BracketContestantInfo | null;
  winner: BracketContestantInfo | null;
  source_a_matchup_id: number | null;
  source_b_matchup_id: number | null;
};

export type UserBracketSummary = {
  id: number;
  bracket_id: number;
  user_id: number;
  challenge_id: number | null;
  display_name: string;
  is_master: boolean;
  created_at: string;
  submitted_at: string | null;
  is_complete: boolean;
  can_edit: boolean;
  /** Master bracket only: submitted scores are stale until materialized. */
  leaderboard_scores_pending?: boolean;
};

export type BracketStageInfo = {
  id: number;
  name: string;
  order: number;
  stage_type: string;
  number_of_contestants: number;
  contestants_advancing?: number | null;
  is_random_draw: boolean;
  submission_deadline: string | null;
  points_per_correct_pick: number;
  metadata: unknown;
  knockout?: {
    is_final: boolean;
    is_third_place?: boolean;
    number_of_legs: number;
    has_extra_time: boolean;
    has_penalty_shootout: boolean;
  };
  group?: {
    number_of_groups: number;
    matches_per_contestant: number;
    contestants_qualifying_per_group: number;
    remaining_spots_strategy: string | null;
    points_per_win: number;
    points_per_tie: number;
    points_per_loss: number;
    points_per_exact_position?: number;
    points_per_advancer?: number;
    ties_allowed: boolean;
  };
};

export type AdminStagePatch = {
  id: number;
  name?: string;
  points_per_correct_pick?: number;
  is_random_draw?: boolean;
  submission_deadline?: string | null;
  metadata?: unknown;
  number_of_groups?: number;
  matches_per_contestant?: number;
  contestants_qualifying_per_group?: number;
  remaining_spots_strategy?: string | null;
  points_per_win?: number;
  points_per_tie?: number;
  points_per_loss?: number;
  points_per_exact_position?: number;
  points_per_advancer?: number;
  ties_allowed?: boolean;
  number_of_legs?: number;
  has_extra_time?: boolean;
  has_penalty_shootout?: boolean;
  is_final?: boolean;
  is_third_place?: boolean;
};

/** Group bucket for UI (even split of bracket contestants). */
export type BracketGroupPreview = {
  code: string;
  stage_id: number;
  teams: BracketContestantInfo[];
};

export type BracketDetail = BracketSummary & {
  stages: BracketStageInfo[];
  contestants: BracketContestantInfo[];
  groups: BracketGroupPreview[];
  master_user_bracket_id?: number | null;
};

export type UserBracketPicksMetadata = {
  group_positions?: Record<string, Record<string, number | null | undefined>>;
  third_place_advancers?: number[];
};

export type UserBracketDetail = UserBracketSummary & {
  bracket: BracketSummary;
  matchups_by_stage: { stage_id: number; matchups: MatchupInfo[] }[];
  score_vs_master: number | null;
  metadata: UserBracketPicksMetadata;
  scoring_highlights?: ScoringHighlights;
};

function joinUrl(path: string): string {
  const base = apiRoot.replace(/\/$/, '');
  const p = path.startsWith('/') ? path.slice(1) : path;
  return `${base}/${p}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function isFormData(b: unknown): b is FormData {
  return typeof FormData !== 'undefined' && b instanceof FormData;
}

async function apiFetch<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const form = isFormData(body);
  const init: RequestInit = {
    method,
    credentials: 'include',
    headers: {
      ...(!form && body !== undefined
        ? { 'Content-Type': 'application/json' }
        : {}),
    },
    body: form
      ? body
      : body !== undefined
        ? JSON.stringify(body)
        : undefined,
  };

  const res = await fetch(joinUrl(path), init);
  let parsed: unknown = {};
  try {
    parsed = await res.json();
  } catch {
    parsed = {};
  }

  if (!res.ok) {
    if (import.meta.env.DEV && (res.status === 502 || res.status === 503)) {
      throw new ApiError('Unable to connect.', res.status, parsed);
    }
    if (res.status === 504) {
      throw new ApiError(
        'The request timed out. Try Apply again.',
        res.status,
        parsed,
      );
    }
    const msg =
      typeof parsed === 'object' &&
      parsed !== null &&
      'error' in parsed &&
      typeof (parsed as { error?: { message?: string } }).error?.message ===
        'string'
        ? (parsed as { error: { message: string } }).error.message
        : res.statusText;
    throw new ApiError(
      msg || `Request failed (${res.status})`,
      res.status,
      parsed,
    );
  }

  return parsed as T;
}

/** Legacy ping endpoint (`POST /brackets/test`). */
export async function testAPI(value1: number, value2: number): Promise<number> {
  const res = await fetch(`${window.location.origin}/brackets/test`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ num1: value1, num2: value2 }),
  });
  const data = (await res.json()) as { data?: number };
  if (!res.ok) {
    throw new ApiError('test failed', res.status, data);
  }
  return data.data ?? NaN;
}

export async function authMe(): Promise<{ user: ApiUser | null }> {
  return apiFetch('GET', 'auth/me');
}

export async function authLogin(
  username: string,
  password: string,
): Promise<{ user: ApiUser }> {
  return apiFetch('POST', 'auth/login', { username, password });
}

export async function authRegister(
  username: string,
  password: string,
): Promise<{ user: ApiUser }> {
  return apiFetch('POST', 'auth/register', { username, password });
}

export async function authLogout(): Promise<{ ok: boolean }> {
  return apiFetch('POST', 'auth/logout');
}

export async function authChangePassword(body: {
  new_password: string;
  current_password?: string;
}): Promise<{ user: ApiUser }> {
  return apiFetch('POST', 'auth/change-password', body);
}

export async function listBrackets(): Promise<{ brackets: BracketSummary[] }> {
  return apiFetch('GET', 'brackets');
}

const bracketDetailInFlight = new Map<
  number,
  Promise<{ bracket: BracketDetail }>
>();

export async function getBracket(
  bracketId: number,
): Promise<{ bracket: BracketDetail }> {
  const existing = bracketDetailInFlight.get(bracketId);
  if (existing) return existing;
  const request = apiFetch('GET', `brackets/${bracketId}`).finally(() => {
    if (bracketDetailInFlight.get(bracketId) === request) {
      bracketDetailInFlight.delete(bracketId);
    }
  }) as Promise<{ bracket: BracketDetail }>;
  bracketDetailInFlight.set(bracketId, request);
  return request;
}

export async function updateBracketGroupResultsMode(
  bracketId: number,
  group_results_mode: 'live' | 'confirmed',
): Promise<{ bracket: BracketDetail }> {
  return apiFetch('PATCH', `brackets/${bracketId}/group-results-mode`, {
    group_results_mode,
  });
}

export async function setBracketNextMatch(
  bracketId: number,
  matchupId: number | null,
): Promise<{ bracket: BracketDetail }> {
  return apiFetch('PATCH', `brackets/${bracketId}/next-match`, {
    matchup_id: matchupId,
  });
}

export type OutcomeWeightsPayload = {
  team_rankings: Record<string, number>;
  matchup_odds: Record<string, number>;
};

export async function updateBracketOutcomeWeights(
  bracketId: number,
  payload: OutcomeWeightsPayload,
): Promise<{ bracket: BracketDetail }> {
  return apiFetch('PATCH', `brackets/${bracketId}/outcome-weights`, payload);
}

export async function materializeBracketScores(
  bracketId: number,
): Promise<{
  updated_count: number;
  remaining_count: number;
  leaderboard_scores_pending: boolean;
}> {
  return apiFetch('POST', `brackets/${bracketId}/materialize-scores`);
}

export async function listMyChallenges(): Promise<{
  challenges: ChallengeSummary[];
}> {
  return apiFetch('GET', 'challenges');
}

export type BracketSetupPayload = {
  structure: 'SINGLE_ELIM' | 'GROUP_KNOCKOUT';
  identifier?: string;
  bracket_name?: string;
  number_of_contestants: number;
  has_third_place?: boolean;
};

export async function createChallenge(body: {
  name: string;
  bracket_id?: number;
  bracket_setup?: BracketSetupPayload;
  instance_type?: string;
  is_private?: boolean;
  submission_deadline?: string | null;
  max_entries?: number;
}): Promise<{ challenge: ChallengeSummary }> {
  return apiFetch('POST', 'challenges', body);
}

export async function getPollVotes(
  challengeId: number,
  stageId: number,
  position: number,
): Promise<{
  user_picked: boolean;
  totals: Record<string, number>;
  total_votes: number;
}> {
  const q = new URLSearchParams({
    stage_id: String(stageId),
    position: String(position),
  });
  return apiFetch(
    'GET',
    `challenges/${challengeId}/poll-votes?${q.toString()}`,
  );
}

export async function listPublicChallenges(): Promise<{
  challenges: ChallengeSummary[];
}> {
  return apiFetch('GET', 'challenges/public');
}

const challengeDetailInFlight = new Map<
  number,
  Promise<{ challenge: ChallengeSummary }>
>();

export async function getChallenge(
  challengeId: number,
): Promise<{ challenge: ChallengeSummary }> {
  const existing = challengeDetailInFlight.get(challengeId);
  if (existing) return existing;
  const request = apiFetch('GET', `challenges/${challengeId}`).finally(() => {
    if (challengeDetailInFlight.get(challengeId) === request) {
      challengeDetailInFlight.delete(challengeId);
    }
  }) as Promise<{ challenge: ChallengeSummary }>;
  challengeDetailInFlight.set(challengeId, request);
  return request;
}

export async function updateChallenge(
  challengeId: number,
  body: { max_entries: number },
): Promise<{ challenge: ChallengeSummary }> {
  return apiFetch('PATCH', `challenges/${challengeId}`, body);
}

export async function deleteChallenge(
  challengeId: number,
): Promise<{ ok: true }> {
  return apiFetch('DELETE', `challenges/${challengeId}`);
}

export async function getChallengeTeams(challengeId: number): Promise<{
  team_count: number;
  teams: TournamentTeamRow[];
}> {
  return apiFetch('GET', `challenges/${challengeId}/teams`);
}

export async function saveChallengeTeams(
  challengeId: number,
  body: { teams: Array<{ name: string; seed?: number }> },
): Promise<{ team_count: number; teams: TournamentTeamRow[] }> {
  return apiFetch('PUT', `challenges/${challengeId}/teams`, body);
}

export async function getChallengeLeaderboard(challengeId: number): Promise<{
  columns: LeaderboardColumn[];
  entries: LeaderboardEntry[];
  denominators?: LeaderboardDenominators;
}> {
  return apiFetch('GET', `challenges/${challengeId}/leaderboard`);
}

export type ChallengeStatsGroupTeam = {
  bracket_contestant_id: number;
  display_name: string;
  image_url: string | null;
  average_position: number | null;
  /** Final placement from the master bracket; null until the group is decided. */
  master_position: number | null;
  pick_count: number;
};

export type ChallengeStatsGroupEntry = {
  user_bracket_id: number;
  display_name: string;
  username: string;
  points: number;
};

export type ChallengeStatsGroup = {
  code: string;
  teams: ChallengeStatsGroupTeam[];
  max_points: number;
  avg_points: number | null;
  entries: ChallengeStatsGroupEntry[];
};

export type ChallengeStatsProgressionEntry = {
  user_bracket_id: number;
  display_name: string;
  username: string;
};

export type ChallengeStatsProgressionBucket = {
  key: string;
  label: string;
  entries: ChallengeStatsProgressionEntry[];
};

export type ChallengeStatsKnockoutRow = {
  bracket_contestant_id: number;
  display_name: string;
  image_url: string | null;
  progression_score: number;
  percentages: Record<string, number>;
  progression: ChallengeStatsProgressionBucket[];
};

export type ChallengeStatsBracketSlotEntry = {
  bracket_contestant_id: number;
  display_name: string;
  image_url: string | null;
  count: number;
  pct: number;
};

/**
 * Knockout pick distribution per bracket slot. Slots are keyed
 * `"{stage_id}:{position}:{side}"` (side 1 = matchup contestant1, 2 = contestant2)
 * plus a `champion` slot for the final winner. Each list is sorted most-picked
 * first.
 */
export type ChallengeStatsBracket = {
  slots: Record<string, ChallengeStatsBracketSlotEntry[]>;
};

export type ChallengeStatsSimilarityTeam = {
  bracket_contestant_id: number;
  display_name: string;
  image_url: string | null;
};

export type ChallengeStatsSimilarityEntry = {
  user_bracket_id: number;
  display_name: string;
  username?: string;
};

export type ChallengeStatsSimilarityLeaf = {
  quarter_finalists: ChallengeStatsSimilarityTeam[];
  count: number;
  entries: ChallengeStatsSimilarityEntry[];
};

export type ChallengeStatsSimilarityFourthBranch = {
  team: ChallengeStatsSimilarityTeam;
  count: number;
  children: ChallengeStatsSimilarityLeaf[];
};

export type ChallengeStatsSimilarityThirdBranch = {
  team: ChallengeStatsSimilarityTeam;
  count: number;
  children: ChallengeStatsSimilarityFourthBranch[];
};

export type ChallengeStatsSimilarityRunnerUpBranch = {
  team: ChallengeStatsSimilarityTeam;
  count: number;
  children: ChallengeStatsSimilarityThirdBranch[];
};

export type ChallengeStatsSimilarityBranch = {
  team: ChallengeStatsSimilarityTeam;
  count: number;
  children: ChallengeStatsSimilarityRunnerUpBranch[];
};

export type ChallengeStatsSimilarity = {
  has_third_place: boolean;
  tree: ChallengeStatsSimilarityBranch[];
};

export type ChallengeStats = {
  submitted_count: number;
  group_stage: ChallengeStatsGroup[];
  knockout: {
    columns: LeaderboardColumn[];
    rows: ChallengeStatsKnockoutRow[];
  };
  bracket: ChallengeStatsBracket;
  similarity: ChallengeStatsSimilarity | null;
};

export type ChallengeOutcomesWinnerOdds = {
  entry: ChallengeOutcomesEntry;
  outcome_count: number;
  pct: number;
  /** Weighted win probability when odds/rankings are configured. */
  likelihood?: number | null;
};

export type ChallengeOutcomesEntry = {
  user_bracket_id: number;
  display_name: string;
  username?: string;
};

export type ChallengeOutcomesLeaf = {
  winners: ChallengeOutcomesEntry[];
};

export type ChallengeOutcomesFourthBranch = {
  team: ChallengeStatsSimilarityTeam;
  children: ChallengeOutcomesLeaf[];
};

export type ChallengeOutcomesThirdBranch = {
  team: ChallengeStatsSimilarityTeam;
  children: ChallengeOutcomesFourthBranch[];
};

export type ChallengeOutcomesRunnerUpBranch = {
  team: ChallengeStatsSimilarityTeam;
  children: ChallengeOutcomesThirdBranch[];
};

export type ChallengeOutcomesChampionBranch = {
  team: ChallengeStatsSimilarityTeam;
  children: ChallengeOutcomesRunnerUpBranch[];
};

export type ChallengeOutcomesSimilarity = {
  has_third_place: boolean;
  total_outcomes: number;
  winner_odds: ChallengeOutcomesWinnerOdds[];
  tree: ChallengeOutcomesChampionBranch[];
  /** Path-prefix weighted likelihood (e.g. c:12:ru:34:t:56). */
  team_likelihood?: Record<string, number>;
};

export async function getChallengeOutcomes(
  challengeId: number,
): Promise<ChallengeOutcomesSimilarity> {
  return apiFetch('GET', `challenges/${challengeId}/outcomes`);
}

export async function getChallengeStats(
  challengeId: number,
): Promise<ChallengeStats> {
  return apiFetch('GET', `challenges/${challengeId}/stats`);
}

export async function listStreakCompetitions(): Promise<{
  streak_competitions: StreakCompetitionSummary[];
}> {
  return apiFetch('GET', 'streak-competitions');
}

export async function listMyStreakChallenges(): Promise<{
  streak_challenges: StreakChallengeSummary[];
}> {
  return apiFetch('GET', 'streak-challenges');
}

export async function createStreakChallenge(body: {
  name: string;
  streak_competition_id: number;
  is_private?: boolean;
}): Promise<{ streak_challenge: StreakChallengeSummary }> {
  return apiFetch('POST', 'streak-challenges', body);
}

export async function joinStreakChallenge(body: {
  join_code?: string;
  streak_challenge_id?: number;
  display_name: string;
}): Promise<{ streak_challenge: StreakChallengeSummary }> {
  const display_name = body.display_name.trim();
  if (body.streak_challenge_id != null) {
    return apiFetch('POST', 'streak-challenges/join', {
      streak_challenge_id: body.streak_challenge_id,
      display_name,
    });
  }
  return apiFetch('POST', 'streak-challenges/join', {
    join_code: body.join_code!.trim().toUpperCase(),
    display_name,
  });
}

export async function getStreakChallenge(streakChallengeId: number): Promise<{
  streak_challenge: StreakChallengeSummary;
  questions: StreakQuestionInfo[];
  knockout_phases: KnockoutPhaseInfo[];
}> {
  return apiFetch('GET', `streak-challenges/${streakChallengeId}`);
}

export async function deleteStreakChallenge(
  streakChallengeId: number,
): Promise<{ ok: true }> {
  return apiFetch('DELETE', `streak-challenges/${streakChallengeId}`);
}

export async function getStreakLeaderboard(
  streakChallengeId: number,
): Promise<{ entries: StreakLeaderboardEntry[] }> {
  return apiFetch(
    'GET',
    `streak-challenges/${streakChallengeId}/leaderboard`,
  );
}

export async function getStreakAwards(
  streakChallengeId: number,
): Promise<StreakAwardsPayload> {
  return apiFetch('GET', `streak-challenges/${streakChallengeId}/awards`);
}

export async function getStreakKnockout(
  streakChallengeId: number,
): Promise<{ knockout: StreakKnockoutPayload }> {
  return apiFetch('GET', `streak-challenges/${streakChallengeId}/knockout`);
}

export async function startStreakKnockout(
  streakChallengeId: number,
  confirm: string,
): Promise<{
  streak_challenge: StreakChallengeSummary;
  knockout: StreakKnockoutPayload;
}> {
  return apiFetch('POST', `streak-challenges/${streakChallengeId}/knockout/start`, {
    confirm,
  });
}

export async function saveStreakKnockoutSchedule(
  streakChallengeId: number,
  body: {
    knockout_transition_at: string;
    knockout_round_starts: Record<string, string>;
    knockout_round_headstart: Record<string, boolean>;
    knockout_third_place_match?: boolean;
  },
): Promise<{
  streak_challenge: StreakChallengeSummary;
  knockout_phases: KnockoutPhaseInfo[];
}> {
  return apiFetch(
    'PATCH',
    `streak-challenges/${streakChallengeId}/knockout/schedule`,
    body,
  );
}

export async function saveStreakKnockoutThirdPlace(
  streakChallengeId: number,
  knockout_third_place_match: boolean,
): Promise<{
  streak_challenge: StreakChallengeSummary;
  knockout_phases: KnockoutPhaseInfo[];
}> {
  return apiFetch(
    'PATCH',
    `streak-challenges/${streakChallengeId}/knockout/schedule`,
    { knockout_third_place_match },
  );
}

export async function swapStreakKnockoutSetup(
  streakChallengeId: number,
  body: {
    match_position: number;
    slot: 'a' | 'b';
    user_id: number;
  },
): Promise<{ knockout: StreakKnockoutPayload }> {
  return apiFetch(
    'PATCH',
    `streak-challenges/${streakChallengeId}/knockout/setup`,
    body,
  );
}

export async function advanceStreakKnockout(
  streakChallengeId: number,
  headstartEnabled?: boolean,
): Promise<{
  knockout: StreakKnockoutPayload;
  warnings: string[];
  completed: boolean;
}> {
  return apiFetch(
    'POST',
    `streak-challenges/${streakChallengeId}/knockout/advance`,
    headstartEnabled === undefined ? {} : { headstart_enabled: headstartEnabled },
  );
}

export async function getStreakChallengeStats(
  streakChallengeId: number,
): Promise<StreakChallengeStatsPayload> {
  return apiFetch('GET', `streak-challenges/${streakChallengeId}/stats`);
}

export async function getStreakParticipantPicks(
  streakChallengeId: number,
  userId: number,
  filter?: { scope?: 'streak' | 'consolation' | 'round'; roundIndex?: number },
): Promise<{ display_name: string; username: string; picks: StreakParticipantPickRow[] }> {
  const params = new URLSearchParams();
  if (filter?.scope) params.set('scope', filter.scope);
  if (filter?.scope === 'round' && filter.roundIndex != null) {
    params.set('round_index', String(filter.roundIndex));
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return apiFetch(
    'GET',
    `streak-challenges/${streakChallengeId}/players/${userId}/picks${suffix}`,
  );
}

export async function streakPick(
  streakChallengeId: number,
  questionId: number,
  choiceId: number,
): Promise<{ question: StreakQuestionInfo }> {
  return apiFetch('POST', `streak-questions/${questionId}/pick`, {
    streak_challenge_id: streakChallengeId,
    choice_id: choiceId,
  });
}

export async function clearStreakPick(
  streakChallengeId: number,
  questionId: number,
): Promise<{ question: StreakQuestionInfo }> {
  return apiFetch('DELETE', `streak-questions/${questionId}/pick`, {
    streak_challenge_id: streakChallengeId,
  });
}

export async function adminCreateStreakCompetition(
  body: FormData | { name: string },
): Promise<{ streak_competition: StreakCompetitionSummary }> {
  return apiFetch('POST', 'streak-competitions', body);
}

export async function adminGetStreakCompetition(
  streakCompetitionId: number,
): Promise<{
  streak_competition: StreakCompetitionSummary;
  questions: StreakCompetitionQuestionAdmin[];
}> {
  return apiFetch('GET', `streak-competitions/${streakCompetitionId}`);
}

export async function adminUpdateStreakCompetition(
  streakCompetitionId: number,
  body: FormData | { name?: string; end_competition?: boolean },
): Promise<{ streak_competition: StreakCompetitionSummary }> {
  return apiFetch('PATCH', `streak-competitions/${streakCompetitionId}`, body);
}

export async function adminDeleteStreakCompetition(
  streakCompetitionId: number,
): Promise<{ ok: boolean }> {
  return apiFetch('DELETE', `streak-competitions/${streakCompetitionId}`);
}

export async function adminAddStreakCompetitionQuestion(
  streakCompetitionId: number,
  body: {
    text: string;
    closes_at: string;
    choices: string[];
    knockout_only?: boolean;
  },
): Promise<{ question: StreakCompetitionQuestionAdmin }> {
  return apiFetch(
    'POST',
    `streak-competitions/${streakCompetitionId}/questions`,
    body,
  );
}

export async function adminResolveStreakQuestion(
  questionId: number,
  correct_choice_id: number | null,
): Promise<{ question: StreakCompetitionQuestionAdmin }> {
  return apiFetch('POST', `streak-questions/${questionId}/resolve`, {
    correct_choice_id,
  });
}

export async function adminUpdateStreakQuestion(
  questionId: number,
  body: {
    text: string;
    closes_at: string;
    choices?: Array<{ id?: number; label: string }>;
    knockout_only?: boolean;
  },
): Promise<{ question: StreakCompetitionQuestionAdmin }> {
  return apiFetch('PATCH', `streak-questions/${questionId}`, body);
}

export async function adminDeleteStreakQuestion(
  questionId: number,
): Promise<{ ok: boolean }> {
  return apiFetch('DELETE', `streak-questions/${questionId}`);
}

export async function joinChallenge(body: {
  join_code?: string;
  challenge_id?: number;
  display_name: string;
  instance_type?: string;
}): Promise<{ challenge: ChallengeSummary }> {
  const display_name = body.display_name.trim();
  const payload = { display_name, instance_type: body.instance_type };
  if (body.challenge_id != null) {
    return apiFetch('POST', 'challenges/join', {
      challenge_id: body.challenge_id,
      ...payload,
    });
  }
  return apiFetch('POST', 'challenges/join', {
    join_code: body.join_code!.trim().toUpperCase(),
    ...payload,
  });
}

export async function submitUserBracket(
  userBracketId: number,
): Promise<{ user_bracket: UserBracketDetail }> {
  return apiFetch('POST', `user-brackets/${userBracketId}/submit`);
}

export async function listUserBrackets(params?: {
  bracket_id?: number;
}): Promise<{ user_brackets: UserBracketSummary[] }> {
  const q = params?.bracket_id != null ? `?bracket_id=${params.bracket_id}` : '';
  return apiFetch('GET', `user-brackets${q}`);
}

export async function createUserBracket(body: {
  bracket_id: number;
  challenge_id?: number | null;
  display_name: string;
}): Promise<{ user_bracket: UserBracketDetail }> {
  return apiFetch('POST', 'user-brackets', {
    ...body,
    display_name: body.display_name.trim(),
  });
}

export async function getUserBracket(
  userBracketId: number,
): Promise<{ user_bracket: UserBracketDetail }> {
  return apiFetch('GET', `user-brackets/${userBracketId}`);
}

export async function patchUserBracketMetadata(
  userBracketId: number,
  body: {
    group_positions?: Record<
      string,
      Record<string, number | null | undefined>
    >;
    third_place_advancers?: number[];
  },
): Promise<{ user_bracket: UserBracketDetail }> {
  return apiFetch('PATCH', `user-brackets/${userBracketId}`, body);
}

export async function patchMatchupWinner(
  matchupId: number,
  winnerId: number | null,
): Promise<{ matchup: MatchupInfo }> {
  return apiFetch('PATCH', `matchups/${matchupId}`, {
    winner_id: winnerId,
  });
}

export async function adminListContestants(): Promise<{
  contestants: ContestantCatalog[];
  tags: ContestantTagInfo[];
}> {
  return apiFetch('GET', 'admin/contestants');
}

export async function adminUpdateContestant(
  contestantId: number,
  body:
    | FormData
    | {
        name?: string;
        description?: string;
      },
): Promise<{ contestant: ContestantCatalog }> {
  return apiFetch('PATCH', `admin/contestants/${contestantId}`, body);
}

export type DeleteImpactRecord = {
  label: string;
  count: number;
};

export type DeleteImpactResource =
  | 'bracket'
  | 'challenge'
  | 'streak-competition'
  | 'contestant'
  | 'streak-question'
  | 'user';

export async function adminGetDeleteImpact(
  resource: DeleteImpactResource,
  objectId: number,
): Promise<{ related: DeleteImpactRecord[] }> {
  return apiFetch('GET', `admin/delete-impact/${resource}/${objectId}`);
}

export async function adminDeleteContestant(
  contestantId: number,
): Promise<{ ok: boolean }> {
  return apiFetch('DELETE', `admin/contestants/${contestantId}`);
}

export async function adminUpdateBracket(
  bracketId: number,
  body:
    | FormData
    | {
        name?: string;
        description?: string;
        show_seeds?: boolean;
        randomize_seeds_per_challenge?: boolean;
        has_third_place_match?: boolean;
        points_champion?: number;
        points_third_place_winner?: number;
        metadata?: unknown;
      },
): Promise<{ bracket: BracketDetail }> {
  return apiFetch('PATCH', `admin/brackets/${bracketId}`, body);
}

export async function adminUpdateBracketStages(
  bracketId: number,
  stages: AdminStagePatch[],
): Promise<{ bracket: BracketDetail }> {
  return apiFetch('PATCH', `admin/brackets/${bracketId}/stages`, { stages });
}

export async function adminDeleteBracket(
  bracketId: number,
): Promise<{ ok: boolean }> {
  return apiFetch('DELETE', `admin/brackets/${bracketId}`);
}

export async function adminCreateContestant(
  body:
    | FormData
    | {
        identifier: string;
        name: string;
        description?: string;
      },
): Promise<{ contestant: ContestantCatalog }> {
  return apiFetch('POST', 'admin/contestants', body);
}

export type BracketStructureType = 'SINGLE_ELIM' | 'GROUP_KNOCKOUT';

export type BracketStructureConfig = {
  group_stage?: {
    number_of_groups?: number;
    matches_per_contestant?: number;
    contestants_qualifying_per_group?: number;
    remaining_spots_strategy?: string | null;
    points_per_win?: number;
    points_per_tie?: number;
    points_per_loss?: number;
    ties_allowed?: boolean;
    points_per_correct_pick?: number;
    points_per_exact_position?: number;
    points_per_advancer?: number;
    is_random_draw?: boolean;
  };
  points_champion?: number;
  points_third_place_winner?: number;
  knockout?: {
    number_of_legs?: number;
    has_extra_time?: boolean;
    has_penalty_shootout?: boolean;
    points_per_correct_pick?: number;
    is_random_draw?: boolean;
    round_points?: Record<number, number>;
  };
};

export async function listBracketTemplates(): Promise<{
  templates: BracketTemplateSummary[];
}> {
  return apiFetch('GET', 'bracket-templates');
}

export async function adminListBracketTemplates(): Promise<{
  templates: BracketTemplateSummary[];
}> {
  return apiFetch('GET', 'admin/bracket-templates');
}

export async function adminCreateBracket(
  body:
    | FormData
    | {
        template_id?: number;
        structure?: BracketStructureType;
        identifier: string;
        name: string;
        description?: string;
        number_of_contestants: number;
        has_third_place?: boolean;
        randomize_seeds_per_challenge?: boolean;
        show_seeds?: boolean;
        metadata?: unknown;
        structure_config?: BracketStructureConfig;
        bracket_contestants?: { contestant_id: number; seed: number | null }[];
      },
): Promise<{ bracket: BracketDetail }> {
  return apiFetch('POST', 'admin/brackets', body);
}

export async function adminAssignBracketContestants(
  bracketId: number,
  assignments: { contestant_id: number; seed: number | null }[],
  options?: { replace?: boolean },
): Promise<{ bracket: BracketDetail }> {
  return apiFetch('POST', `admin/brackets/${bracketId}/contestants`, {
    assignments,
    replace: options?.replace ?? false,
  });
}

export async function adminListUsers(): Promise<{ users: AdminUserRow[] }> {
  return apiFetch('GET', 'admin/users');
}

export async function adminDeleteUser(userId: number): Promise<{ ok: boolean }> {
  return apiFetch('DELETE', `admin/users/${userId}`);
}

export async function adminResetUserPassword(
  userId: number,
): Promise<{ user: AdminUserRow; temp_password: string }> {
  return apiFetch('POST', `admin/users/${userId}/reset-password`);
}

export type AdminChallengeRow = {
  id: number;
  name: string;
  created_by_username: string;
  bracket_id: number;
  bracket_name: string;
  bracket_image_url?: string | null;
  instance_type: string;
  instance_type_label?: string;
  needs_user_bracket?: boolean;
  is_public: boolean;
  is_private: boolean;
  join_code: string | null;
  submission_deadline: string | null;
  deadline_passed: boolean;
  max_entries: number;
  participant_count: number;
  entry_count: number;
  max_entries_minimum?: number | null;
};

export async function adminListChallenges(): Promise<{
  challenges: AdminChallengeRow[];
}> {
  return apiFetch('GET', 'admin/challenges');
}

export async function adminCreateChallenge(body: {
  name: string;
  bracket_id: number;
  submission_deadline?: string | null;
  max_entries?: number;
  is_private?: boolean;
}): Promise<{ challenge: AdminChallengeRow }> {
  return apiFetch('POST', 'admin/challenges', body);
}

export async function adminGetChallenge(
  challengeId: number,
): Promise<{ challenge: AdminChallengeRow }> {
  return apiFetch('GET', `admin/challenges/${challengeId}`);
}

export async function adminUpdateChallenge(
  challengeId: number,
  body: {
    name?: string;
    submission_deadline?: string | null;
    max_entries?: number;
    is_private?: boolean;
  },
): Promise<{ challenge: AdminChallengeRow }> {
  return apiFetch('PATCH', `admin/challenges/${challengeId}`, body);
}

export async function adminDeleteChallenge(
  challengeId: number,
): Promise<{ ok: true }> {
  return apiFetch('DELETE', `admin/challenges/${challengeId}`);
}

export async function adminCreateChallengeEntry(
  challengeId: number,
  body: { user_id: number; display_name?: string },
): Promise<{ entry: AdminChallengeEntry }> {
  return apiFetch('POST', `admin/challenges/${challengeId}/entries`, body);
}

export type AdminChallengeEntry = {
  user_bracket_id: number;
  user_id: number;
  username: string;
  display_name: string;
  is_submitted: boolean;
  submitted_at: string | null;
  is_complete: boolean;
};

export async function adminListChallengeEntries(
  challengeId: number,
): Promise<{ entries: AdminChallengeEntry[] }> {
  return apiFetch('GET', `admin/challenges/${challengeId}/entries`);
}

export async function adminUpdateChallengeEntry(
  challengeId: number,
  userBracketId: number,
  body: { display_name: string },
): Promise<{ entry: AdminChallengeEntry }> {
  return apiFetch(
    'PATCH',
    `admin/challenges/${challengeId}/entries/${userBracketId}`,
    body,
  );
}

export async function adminGetUserBracket(
  userBracketId: number,
): Promise<{ user_bracket: UserBracketDetail }> {
  return apiFetch('GET', `admin/user-brackets/${userBracketId}`);
}
