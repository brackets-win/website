import {
  ApiError,
  listBrackets,
  listMyChallenges,
  listMyStreakChallenges,
  listPublicChallenges,
  listStreakCompetitions,
  type BracketSummary,
  type ChallengeSummary,
  type StreakChallengeSummary,
  type StreakCompetitionSummary,
  type UserBracketDetail,
} from './api';

export type HomeScope =
  | 'challenges'
  | 'streaks'
  | 'public'
  | 'brackets'
  | 'competitions';

const ALL_SCOPES: HomeScope[] = [
  'challenges',
  'streaks',
  'public',
  'brackets',
  'competitions',
];

export type HomeSnapshot = {
  challenges: ChallengeSummary[];
  streakChallenges: StreakChallengeSummary[];
  publicChallenges: ChallengeSummary[];
  brackets: BracketSummary[];
  streakCompetitions: StreakCompetitionSummary[];
};

type Listener = () => void;

let snapshot: HomeSnapshot | null = null;
const stale = new Set<HomeScope>();
const listeners = new Set<Listener>();
let refreshGen = 0;
let refreshInFlight: Promise<RefreshHomeResult> | null = null;

function notify() {
  for (const listener of listeners) {
    listener();
  }
}

function scopesToFetch(requested: HomeScope[]): HomeScope[] {
  if (requested.length === 0) return [];
  const out = new Set<HomeScope>();
  for (const scope of requested) {
    out.add(scope);
  }
  return ALL_SCOPES.filter((scope) => out.has(scope));
}

export function getHomeSnapshot(): HomeSnapshot | null {
  return snapshot;
}

export function hasHomeSnapshot(): boolean {
  return snapshot != null;
}

export function subscribeHome(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function clearHomeCache() {
  snapshot = null;
  stale.clear();
  refreshGen += 1;
  notify();
}

export function invalidateHome(...scopes: HomeScope[]) {
  if (scopes.length === 0) {
    for (const scope of ALL_SCOPES) stale.add(scope);
  } else {
    for (const scope of scopes) stale.add(scope);
  }
  void refreshHome();
}

export function invalidateHomeForUserBracket(ub: UserBracketDetail) {
  if (ub.is_master || ub.challenge_id != null) {
    invalidateHome('challenges');
  }
}

export function invalidateHomeForStreakCompetition(_competitionId: number) {
  invalidateHome('streaks', 'competitions');
}

function emptySnapshot(): HomeSnapshot {
  return {
    challenges: [],
    streakChallenges: [],
    publicChallenges: [],
    brackets: [],
    streakCompetitions: [],
  };
}

function ensureSnapshot(): HomeSnapshot {
  if (!snapshot) {
    snapshot = emptySnapshot();
  }
  return snapshot;
}

export function upsertHomeChallenge(challenge: ChallengeSummary) {
  const next = ensureSnapshot();
  const idx = next.challenges.findIndex((row) => row.id === challenge.id);
  if (idx < 0) {
    next.challenges = [challenge, ...next.challenges];
  } else {
    const challenges = [...next.challenges];
    challenges[idx] = challenge;
    next.challenges = challenges;
  }
  notify();
}

export function upsertHomeStreakChallenge(streakChallenge: StreakChallengeSummary) {
  const next = ensureSnapshot();
  const idx = next.streakChallenges.findIndex(
    (row) => row.id === streakChallenge.id,
  );
  if (idx < 0) {
    next.streakChallenges = [streakChallenge, ...next.streakChallenges];
  } else {
    const streakChallenges = [...next.streakChallenges];
    streakChallenges[idx] = streakChallenge;
    next.streakChallenges = streakChallenges;
  }
  notify();
}

export type RefreshHomeResult = {
  snapshot: HomeSnapshot | null;
  error?: string;
};

export async function refreshHome(
  scopes?: HomeScope[],
): Promise<RefreshHomeResult> {
  const toFetch = scopesToFetch(
    scopes ?? (stale.size > 0 ? [...stale] : snapshot ? [] : ALL_SCOPES),
  );
  if (toFetch.length === 0) {
    return { snapshot };
  }

  if (refreshInFlight) {
    return refreshInFlight;
  }

  const gen = ++refreshGen;
  refreshInFlight = (async () => {
    const errors: string[] = [];
    const next: HomeSnapshot = {
      challenges: snapshot?.challenges ?? [],
      streakChallenges: snapshot?.streakChallenges ?? [],
      publicChallenges: snapshot?.publicChallenges ?? [],
      brackets: snapshot?.brackets ?? [],
      streakCompetitions: snapshot?.streakCompetitions ?? [],
    };

    const tasks: Promise<void>[] = [];

    if (toFetch.includes('challenges')) {
      tasks.push(
        listMyChallenges()
          .then(({ challenges }) => {
            next.challenges = challenges;
          })
          .catch((e) => {
            errors.push(
              e instanceof ApiError
                ? e.message
                : 'Unable to load your challenges.',
            );
          }),
      );
    }

    if (toFetch.includes('streaks')) {
      tasks.push(
        listMyStreakChallenges()
          .then(({ streak_challenges }) => {
            next.streakChallenges = streak_challenges;
          })
          .catch((e) => {
            next.streakChallenges = [];
            errors.push(
              e instanceof ApiError
                ? e.message
                : 'Unable to load streak challenges.',
            );
          }),
      );
    }

    if (toFetch.includes('public')) {
      tasks.push(
        listPublicChallenges()
          .then(({ challenges }) => {
            next.publicChallenges = challenges;
          })
          .catch((e) => {
            errors.push(
              e instanceof ApiError
                ? e.message
                : 'Unable to load public challenges.',
            );
          }),
      );
    }

    if (toFetch.includes('brackets')) {
      tasks.push(
        listBrackets()
          .then(({ brackets }) => {
            next.brackets = brackets;
          })
          .catch((e) => {
            errors.push(
              e instanceof ApiError ? e.message : 'Unable to load brackets.',
            );
          }),
      );
    }

    if (toFetch.includes('competitions')) {
      tasks.push(
        listStreakCompetitions()
          .then(({ streak_competitions }) => {
            next.streakCompetitions = streak_competitions.filter(
              (c) => !c.is_over,
            );
          })
          .catch((e) => {
            next.streakCompetitions = [];
            errors.push(
              e instanceof ApiError
                ? e.message
                : 'Unable to load streak competitions.',
            );
          }),
      );
    }

    await Promise.all(tasks);

    if (gen !== refreshGen) {
      return { snapshot };
    }

    for (const scope of toFetch) {
      stale.delete(scope);
    }

    snapshot = next;
    notify();
    refreshInFlight = null;

    return {
      snapshot,
      error: errors[0],
    };
  })();

  return refreshInFlight;
}
