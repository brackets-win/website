import { ContestantsAdmin } from './ContestantsAdmin';
import { BracketsAdmin } from './BracketsAdmin';

import './AdminPanel.css';

export type AdminTab = 'contestants' | 'brackets';

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
        </nav>
      </div>

      {tab === 'contestants' ? <ContestantsAdmin /> : <BracketsAdmin />}
    </div>
  );
}
