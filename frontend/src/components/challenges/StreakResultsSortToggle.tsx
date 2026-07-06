import type { PickResultsSort } from '../../utils/streakKnockout';

import './StreakResultsSortToggle.css';

type Props = {
  value: PickResultsSort;
  onChange: (value: PickResultsSort) => void;
};

export function StreakResultsSortToggle({ value, onChange }: Props) {
  return (
    <div
      className="segmented streak-results-sort"
      role="group"
      aria-label="Sort order"
    >
      <button
        type="button"
        aria-pressed={value === 'desc'}
        onClick={() => onChange('desc')}
      >
        Newest
      </button>
      <button
        type="button"
        aria-pressed={value === 'asc'}
        onClick={() => onChange('asc')}
      >
        Oldest
      </button>
    </div>
  );
}
