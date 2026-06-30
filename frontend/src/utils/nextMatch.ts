export function getNextMatchMatchupId(metadata: unknown): number | null {
  if (
    metadata &&
    typeof metadata === 'object' &&
    !Array.isArray(metadata)
  ) {
    const raw = (metadata as { next_match_matchup_id?: unknown })
      .next_match_matchup_id;
    if (typeof raw === 'number' && Number.isFinite(raw)) {
      return raw;
    }
  }
  return null;
}
