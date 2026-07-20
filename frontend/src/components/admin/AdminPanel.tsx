import { ContestantsAdmin } from './ContestantsAdmin';
import { BracketsAdmin } from './BracketsAdmin';
import { ChallengesAdmin } from './ChallengesAdmin';
import { StreakCompetitionsAdmin } from './StreakCompetitionsAdmin';
import { UsersAdmin } from './UsersAdmin';
import type { AdminTab } from '../../routes';

import './AdminPanel.css';

type Props = {
  tab: AdminTab;
  onTabChange: (tab: AdminTab) => void;
};

export function AdminPanel({ tab, onTabChange }: Props) {
  return (
    <div className="admin-hub">
      <div className="admin-hub__intro card">
        <h2 className="admin-hub__title">Admin</h2>
        <nav className="admin-hub__tabs" aria-label="Admin sections">
          <button
            type="button"
            className="admin-hub__tab"
            data-active={tab === 'contestants'}
            onClick={() => onTabChange('contestants')}
          >
            Contestants
          </button>
          <button
            type="button"
            className="admin-hub__tab"
            data-active={tab === 'brackets'}
            onClick={() => onTabChange('brackets')}
          >
            Brackets
          </button>
          <button
            type="button"
            className="admin-hub__tab"
            data-active={tab === 'challenges'}
            onClick={() => onTabChange('challenges')}
          >
            Challenges
          </button>
          <button
            type="button"
            className="admin-hub__tab"
            data-active={tab === 'streak'}
            onClick={() => onTabChange('streak')}
          >
            Streaks
          </button>
          <button
            type="button"
            className="admin-hub__tab"
            data-active={tab === 'users'}
            onClick={() => onTabChange('users')}
          >
            Users
          </button>
        </nav>
      </div>

      {tab === 'contestants' ? (
        <ContestantsAdmin />
      ) : tab === 'brackets' ? (
        <BracketsAdmin />
      ) : tab === 'challenges' ? (
        <ChallengesAdmin />
      ) : tab === 'streak' ? (
        <StreakCompetitionsAdmin />
      ) : (
        <UsersAdmin />
      )}
    </div>
  );
}
