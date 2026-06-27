export const CHALLENGE_TABS = [
  'bracket',
  'teams',
  'official',
  'leaderboard',
  'stats',
  'rules',
  'settings',
] as const;

export type ChallengeTab = (typeof CHALLENGE_TABS)[number];

export const STREAK_TABS = [
  'awards',
  'leaderboard',
  'knockout',
  'results',
  'make',
  'rules',
  'settings',
] as const;

export type StreakTab = (typeof STREAK_TABS)[number];

export const ADMIN_TABS = ['contestants', 'brackets', 'streak', 'users'] as const;

export type AdminTab = (typeof ADMIN_TABS)[number];

export function isChallengeTab(value: string | undefined): value is ChallengeTab {
  return CHALLENGE_TABS.includes(value as ChallengeTab);
}

export function isStreakTab(value: string | undefined): value is StreakTab {
  return STREAK_TABS.includes(value as StreakTab);
}

export function isAdminTab(value: string | undefined): value is AdminTab {
  return ADMIN_TABS.includes(value as AdminTab);
}

export function challengePath(
  challengeId: number,
  tab: ChallengeTab = 'bracket',
  opts?: { entry?: number },
): string {
  const path = `/challenge/${challengeId}/${tab}`;
  if (opts?.entry != null) {
    return `${path}?entry=${opts.entry}`;
  }
  return path;
}

export function challengePlayerPath(
  challengeId: number,
  userBracketId: number,
): string {
  return `/challenge/${challengeId}/player/${userBracketId}`;
}

export function streakPath(
  streakChallengeId: number,
  tab: StreakTab = 'leaderboard',
): string {
  return `/streak/${streakChallengeId}/${tab}`;
}

export function streakPlayerPath(
  streakChallengeId: number,
  userId: number,
): string {
  return `/streak/${streakChallengeId}/player/${userId}`;
}

export function adminPath(tab: AdminTab = 'contestants'): string {
  return `/admin/${tab}`;
}

export function parseRouteId(value: string | null | undefined): number | null {
  if (!value) return null;
  const n = parseInt(value, 10);
  return Number.isFinite(n) ? n : null;
}
