import type {
  StreakAwardsPayload,
  StreakKnockoutPayload,
  StreakLeaderboardEntry,
  StreakQuestionInfo,
  StreakChallengeSummary,
} from './api';
import type { KnockoutPhaseInfo } from './streakKnockout';

export type StreakChallengeSessionCache = {
  summary?: StreakChallengeSummary;
  questions?: StreakQuestionInfo[];
  knockoutPhases?: KnockoutPhaseInfo[];
  entries?: StreakLeaderboardEntry[];
  awards?: StreakAwardsPayload | null;
  knockout?: StreakKnockoutPayload | null;
};

const cache = new Map<number, StreakChallengeSessionCache>();

export function readStreakChallengeSessionCache(
  streakChallengeId: number,
): StreakChallengeSessionCache | null {
  return cache.get(streakChallengeId) ?? null;
}

export function writeStreakChallengeSessionCache(
  streakChallengeId: number,
  patch: StreakChallengeSessionCache,
): void {
  cache.set(streakChallengeId, {
    ...cache.get(streakChallengeId),
    ...patch,
  });
}

export function clearStreakChallengeSessionCache(streakChallengeId: number): void {
  cache.delete(streakChallengeId);
}
