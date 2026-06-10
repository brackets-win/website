import type { ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { adminPath } from '../../routes';
import type { ApiUser } from '../../utils/api';
import { BracketsLogoMark } from '../BracketsLogoMark';

import './AppShell.css';

type Props = {
  user: ApiUser;
  onSignOut: () => void;
  children: ReactNode;
};

export function AppShell({ user, onSignOut, children }: Props) {
  const initial = user.username.charAt(0).toUpperCase();
  const location = useLocation();
  const navigate = useNavigate();
  const onAdmin = location.pathname.startsWith('/admin');

  function handleSignOut() {
    onSignOut();
    navigate('/', { replace: true });
  }

  return (
    <div className="shell">
      <header className="shell__header">
        <div className="shell__header-inner">
          <Link
            to="/"
            className="shell__logo"
            aria-label="brackets.win home"
          >
            <span className="shell__logo-mark">
              <BracketsLogoMark />
            </span>
            <span className="shell__logo-text">brackets.win</span>
          </Link>

          <div className="shell__user">
            {user.is_staff ? (
              <Link
                to={adminPath('contestants')}
                className={`btn btn--secondary shell__admin${onAdmin ? ' shell__admin--active' : ''}`}
              >
                Admin
              </Link>
            ) : null}
            <span className="shell__avatar" aria-hidden>
              {initial}
            </span>
            <span className="shell__username">{user.username}</span>
            <button
              type="button"
              className="btn btn--ghost shell__signout"
              onClick={handleSignOut}
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
