import {
  INSTANCE_BRACKET_CHALLENGE,
  INSTANCE_POLL,
  INSTANCE_TOURNAMENT,
} from './challengeTypes';

export type ChallengeThemeKey =
  | 'bracket_challenge'
  | 'tournament'
  | 'poll'
  | 'streak';

export function challengeThemeClass(key: ChallengeThemeKey): string {
  return `challenge-theme challenge-theme--${key}`;
}

export function themeKeyForInstanceType(instanceType: string): ChallengeThemeKey {
  if (instanceType === INSTANCE_TOURNAMENT) return 'tournament';
  if (instanceType === INSTANCE_POLL) return 'poll';
  if (instanceType === INSTANCE_BRACKET_CHALLENGE) return 'bracket_challenge';
  return 'bracket_challenge';
}
