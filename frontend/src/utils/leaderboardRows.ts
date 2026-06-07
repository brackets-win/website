/** Shared competition ranks and podium row styling for leaderboards. */

export function computeCompetitionRanks<T>(
  entries: T[],
  compare: (a: T, b: T) => number,
  getId: (entry: T) => number,
): Map<number, number> {
  const sorted = [...entries].sort(compare);
  const ranks = new Map<number, number>();
  for (let i = 0; i < sorted.length; i++) {
    const entry = sorted[i];
    const id = getId(entry);
    if (i === 0) {
      ranks.set(id, 1);
      continue;
    }
    const prev = sorted[i - 1];
    const prevRank = ranks.get(getId(prev))!;
    ranks.set(id, compare(entry, prev) === 0 ? prevRank : i + 1);
  }
  return ranks;
}

export function leaderboardRowClassName(
  rank: number | undefined,
  isViewer: boolean,
): string {
  const parts: string[] = [];
  if (isViewer) parts.push('leaderboard-row--viewer');
  if (rank === 1) parts.push('leaderboard-row--gold');
  else if (rank === 2) parts.push('leaderboard-row--silver');
  else if (rank === 3) parts.push('leaderboard-row--bronze');
  return parts.join(' ');
}
