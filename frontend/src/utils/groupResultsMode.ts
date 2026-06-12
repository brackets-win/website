export type GroupResultsMode = 'live' | 'confirmed';

export function getGroupResultsMode(metadata: unknown): GroupResultsMode {
  if (
    metadata &&
    typeof metadata === 'object' &&
    !Array.isArray(metadata) &&
    (metadata as { group_results_mode?: unknown }).group_results_mode === 'live'
  ) {
    return 'live';
  }
  return 'confirmed';
}
