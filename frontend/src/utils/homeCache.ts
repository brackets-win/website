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

function snapshotNeedsChallengesFetch(): boolean {
  return (snapshot?.challenges.length ?? 0) === 0;
}

function defaultScopesToFetch(): HomeScope[] {
  if (stale.size > 0) {
    return [...stale];
  }
  if (snapshot == null) {
    return ALL_SCOPES;
  }
  if (snapshotNeedsChallengesFetch()) {
    return ['challenges'];
  }
  return [];
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
  refreshInFlight = null;
  notify();
}

function scheduleRefreshIfNeeded() {
  if (listeners.size === 0 || refreshInFlight != null) {
    return;
  }
  const scopes = defaultScopesToFetch();
  if (scopes.length === 0) {
    return;
  }
  void refreshHome(scopes);
}

export function invalidateHome(...scopes: HomeScope[]) {
  if (scopes.length === 0) {
    for (const scope of ALL_SCOPES) stale.add(scope);
  } else {
    for (const scope of scopes) stale.add(scope);
  }
  scheduleRefreshIfNeeded();
}

let masterInvalidateTimer: ReturnType<typeof setTimeout> | null = null;

export function invalidateHomeForUserBracket(ub: UserBracketDetail) {
  if (!ub.is_master && ub.challenge_id == null) return;

  if (ub.is_master) {
    if (masterInvalidateTimer != null) {
      clearTimeout(masterInvalidateTimer);
    }
    masterInvalidateTimer = setTimeout(() => {
      masterInvalidateTimer = null;
      invalidateHome('challenges');
    }, 750);
    return;
  }

  invalidateHome('challenges');
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

export function upsertHomeChallenge(challenge: ChallengeSummary) {
  const prev = snapshot ?? emptySnapshot();
  const idx = prev.challenges.findIndex((row) => row.id === challenge.id);
  const challenges =
    idx < 0
      ? [challenge, ...prev.challenges]
      : prev.challenges.map((row, i) => (i === idx ? challenge : row));
  snapshot = { ...prev, challenges };
  notify();
}

export function upsertHomeStreakChallenge(streakChallenge: StreakChallengeSummary) {
  const prev = snapshot ?? emptySnapshot();
  const idx = prev.streakChallenges.findIndex(
    (row) => row.id === streakChallenge.id,
  );
  const streakChallenges =
    idx < 0
      ? [streakChallenge, ...prev.streakChallenges]
      : prev.streakChallenges.map((row, i) => (i === idx ? streakChallenge : row));
  snapshot = { ...prev, streakChallenges };
  notify();
}

export type RefreshHomeResult = {
  snapshot: HomeSnapshot | null;
  error?: string;
};

export async function refreshHome(
  scopes?: HomeScope[],
): Promise<RefreshHomeResult> {
  const toFetch = scopesToFetch(scopes ?? defaultScopesToFetch());
  if (toFetch.length === 0) {
    return { snapshot };
  }

  if (refreshInFlight) {
    return refreshInFlight;
  }

  const gen = ++refreshGen;
  refreshInFlight = (async (): Promise<RefreshHomeResult> => {
    const errors: string[] = [];
    const succeeded = new Set<HomeScope>();
    const previous = snapshot;
    const next: HomeSnapshot = {
      challenges: previous?.challenges ?? [],
      streakChallenges: previous?.streakChallenges ?? [],
      publicChallenges: previous?.publicChallenges ?? [],
      brackets: previous?.brackets ?? [],
      streakCompetitions: previous?.streakCompetitions ?? [],
    };

    const tasks: Promise<void>[] = [];

    if (toFetch.includes('challenges')) {
      tasks.push(
        listMyChallenges()
          .then(({ challenges }) => {
            next.challenges = challenges;
            succeeded.add('challenges');
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
            succeeded.add('streaks');
          })
          .catch((e) => {
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
            succeeded.add('public');
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
            succeeded.add('brackets');
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
            succeeded.add('competitions');
          })
          .catch((e) => {
            errors.push(
              e instanceof ApiError
                ? e.message
                : 'Unable to load streak competitions.',
            );
          }),
      );
    }

    try {
      await Promise.all(tasks);

      if (gen !== refreshGen) {
        return { snapshot };
      }

      const challengesFailed =
        toFetch.includes('challenges') && !succeeded.has('challenges');

      for (const scope of toFetch) {
        if (succeeded.has(scope)) {
          stale.delete(scope);
        }
      }

      if (challengesFailed && (previous?.challenges.length ?? 0) > 0) {
        next.challenges = previous!.challenges;
      }

      const shouldCommit =
        succeeded.size > 0 ||
        (previous != null && !challengesFailed) ||
        (!challengesFailed && !toFetch.includes('challenges'));

      if (shouldCommit) {
        snapshot = next;
        notify();
      }

      if (challengesFailed) {
        stale.add('challenges');
      }

      return {
        snapshot,
        error: errors[0],
      };
    } finally {
      refreshInFlight = null;
      if (gen === refreshGen) {
        scheduleRefreshIfNeeded();
      }
    }
  })();

  return refreshInFlight;
}
