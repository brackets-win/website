/** JSON API client for the Django backend (session cookies). */

const apiRoot = import.meta.env.DEV
  ? `${window.location.origin}/brackets/api`
  : 'https://brackets-win.fly.dev/brackets/api';

export type ApiUser = { id: number; username: string };

export type BracketSummary = {
  id: number;
  name: string;
  description: string;
  created_at: string;
  randomize_seeds_per_challenge: boolean;
  /** Single elimination: optional third-place match (semifinal losers). */
  has_third_place_match?: boolean;
  metadata: unknown;
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
  is_master: boolean;
  created_at: string;
};

export type BracketStageInfo = {
  id: number;
  name: string;
  order: number;
  stage_type: string;
  number_of_contestants: number;
  contestants_advancing?: number | null;
  submission_deadline: string | null;
  points_per_correct_pick: number;
  metadata: unknown;
  knockout?: {
    is_final: boolean;
    number_of_legs: number;
    is_third_place?: boolean;
  };
  group?: {
    number_of_groups: number;
    matches_per_contestant: number;
    contestants_qualifying_per_group: number;
    remaining_spots_strategy: string | null;
  };
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

async function apiFetch<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = {
    method,
    credentials: 'include',
    headers: {
      ...(body !== undefined
        ? { 'Content-Type': 'application/json' }
        : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };

  const res = await fetch(joinUrl(path), init);
  const parsed = (await res.json().catch(() => ({}))) as unknown;

  if (!res.ok) {
    if (import.meta.env.DEV && (res.status === 502 || res.status === 503)) {
      throw new ApiError('Unable to connect.', res.status, parsed);
    }
    const msg =
      typeof parsed === 'object' &&
      parsed !== null &&
      'error' in parsed &&
      typeof (parsed as { error?: { message?: string } }).error?.message ===
        'string'
        ? (parsed as { error: { message: string } }).error.message
        : res.statusText;
    throw new ApiError(msg || 'Request failed', res.status, parsed);
  }

  return parsed as T;
}

/** Legacy ping endpoint (`POST /brackets/test`). */
export async function testAPI(value1: number, value2: number): Promise<number> {
  const apiHost = import.meta.env.DEV
    ? window.location.origin
    : 'https://brackets-win.fly.dev';
  const res = await fetch(`${apiHost}/brackets/test`, {
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

export async function authLogout(): Promise<{ ok: boolean }> {
  return apiFetch('POST', 'auth/logout');
}

export async function listBrackets(): Promise<{ brackets: BracketSummary[] }> {
  return apiFetch('GET', 'brackets');
}

export async function getBracket(
  bracketId: number,
): Promise<{ bracket: BracketDetail }> {
  return apiFetch('GET', `brackets/${bracketId}`);
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
}): Promise<{ user_bracket: UserBracketDetail }> {
  return apiFetch('POST', 'user-brackets', body);
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
