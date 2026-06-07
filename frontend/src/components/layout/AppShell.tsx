import type { ReactNode } from 'react';

import type { ApiUser } from '../../utils/api';
import { BracketsLogoMark } from '../BracketsLogoMark';

import './AppShell.css';

export type AppPage = 'home' | 'challenge' | 'streak' | 'admin';

type Props = {
  user: ApiUser;
  page: AppPage;
  onNavigate: (page: AppPage) => void;
  onSignOut: () => void;
  children: ReactNode;
};

export function AppShell({
  user,
  page,
  onNavigate,
  onSignOut,
  children,
}: Props) {
  const initial = user.username.charAt(0).toUpperCase();

  return (
    <div className="shell">
      <header className="shell__header">
        <div className="shell__header-inner">
          <button
            type="button"
            className="shell__logo"
            aria-label="brackets.win home"
            onClick={() => onNavigate('home')}
          >
            <span className="shell__logo-mark">
              <BracketsLogoMark />
            </span>
            <span className="shell__logo-text">brackets.win</span>
          </button>

          <div className="shell__user">
            {user.is_staff ? (
              <button
                type="button"
                className={`btn btn--secondary shell__admin${page === 'admin' ? ' shell__admin--active' : ''}`}
                onClick={() => onNavigate('admin')}
              >
                Admin
              </button>
            ) : null}
            <span className="shell__avatar" aria-hidden>
              {initial}
            </span>
            <span className="shell__username">{user.username}</span>
            <button
              type="button"
              className="btn btn--ghost shell__signout"
              onClick={onSignOut}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="shell__main">{children}</main>
    </div>
  );
}
