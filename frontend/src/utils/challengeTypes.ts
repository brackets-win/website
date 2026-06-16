export const INSTANCE_BRACKET_CHALLENGE = 'CHALLENGE';
export const INSTANCE_TOURNAMENT = 'TOURNAMENT';
export const INSTANCE_POLL = 'POLL';

/** Home-page tournament/poll sections (create, join, cards). */
export const SHOW_TOURNAMENT_AND_POLL_SECTIONS = false;

export type BracketInstanceType =
  | typeof INSTANCE_BRACKET_CHALLENGE
  | typeof INSTANCE_TOURNAMENT
  | typeof INSTANCE_POLL;

export const BRACKET_INSTANCE_TYPES: {
  value: BracketInstanceType;
  label: string;
}[] = [
  { value: INSTANCE_BRACKET_CHALLENGE, label: 'Bracket Challenge' },
  { value: INSTANCE_TOURNAMENT, label: 'Tournament' },
  { value: INSTANCE_POLL, label: 'Poll' },
];

export function needsUserBracket(instanceType: string): boolean {
  return instanceType === INSTANCE_BRACKET_CHALLENGE || instanceType === INSTANCE_POLL;
}

export function usesPredictionLeaderboard(instanceType: string): boolean {
  return instanceType === INSTANCE_BRACKET_CHALLENGE;
}

export function defaultChallengeTab(challenge: {
  instance_type: string;
  is_submitted: boolean;
}): 'bracket' | 'leaderboard' {
  if (
    challenge.instance_type === INSTANCE_BRACKET_CHALLENGE &&
    challenge.is_submitted
  ) {
    return 'leaderboard';
  }
  return 'bracket';
}

export function instanceTypeLabel(instanceType: string): string {
  const row = BRACKET_INSTANCE_TYPES.find((t) => t.value === instanceType);
  return row?.label ?? instanceType;
}

export function formatStreakDisplay(streakSigned: number): string {
  if (streakSigned > 0) return `${streakSigned}W`;
  if (streakSigned < 0) return `${-streakSigned}L`;
  return '—';
}

export function streakEmoji(
  streakSigned: number,
  bestWinStreak: number,
  brokenWinStreak = 0,
): string | null {
  if (streakSigned === -1 && brokenWinStreak >= 3) return '🧯';
  if (streakSigned <= -3) return '🧊';

  if (streakSigned <= 0 || bestWinStreak <= 0) return null;
  if (streakSigned !== bestWinStreak) return null;
  if (streakSigned >= 10) return '🐦‍🔥';
  if (streakSigned >= 7) return '☄️';
  if (streakSigned >= 5) return '🌋';
  if (streakSigned >= 3) return '🔥';
  return null;
}

/** Emoji when an active streak has a notable state. */
export function activeLongWinStreakEmoji(
  streakSigned: number,
  bestWinStreak: number,
): string | null {
  return streakEmoji(streakSigned, bestWinStreak);
}
