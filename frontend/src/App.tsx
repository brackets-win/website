import { useCallback, useEffect, useMemo, useState } from 'react';

import { AdminPanel, type AdminTab } from './components/admin/AdminPanel';
import { LoginPage } from './components/auth/LoginPage';
import {
  ChallengeView,
  type ChallengeTab,
} from './components/challenges/ChallengeView';
import { ChallengesPage } from './components/challenges/ChallengesPage';
import { StreakChallengeView } from './components/challenges/StreakChallengeView';
import { AppShell, type AppPage } from './components/layout/AppShell';
import {
  ApiError,
  authLogin,
  authLogout,
  authMe,
  authRegister,
  listUserBrackets,
  type ApiUser,
} from './utils/api';

import './components/admin/admin-shared.css';

function readUbFromLocation(): number | null {
  const q = new URLSearchParams(window.location.search).get('ub');
  if (!q) return null;
  const n = parseInt(q, 10);
  return Number.isFinite(n) ? n : null;
}

export default function App() {
  const [sessionUser, setSessionUser] = useState<ApiUser | null | undefined>(
    undefined,
  );
  const [page, setPage] = useState<AppPage>('home');
  const [adminTab, setAdminTab] = useState<AdminTab>('contestants');
  const [loginBusy, setLoginBusy] = useState(false);
  const [authError, setAuthError] = useState('');

  const initialUb = useMemo(() => readUbFromLocation(), []);
  const [activeChallenge, setActiveChallenge] = useState<{
    challengeId: number;
    userBracketId: number | null;
    initialTab?: ChallengeTab;
  } | null>(null);
  const [activeStreakId, setActiveStreakId] = useState<number | null>(null);
  const [homeResetKey, setHomeResetKey] = useState(0);

  const refreshUserBrackets = useCallback(async () => {
    const ubs = await listUserBrackets();
    return ubs.user_brackets;
  }, []);

  const loadSession = useCallback(async () => {
    try {
      const who = await authMe();
      setSessionUser(who.user);
      setAuthError('');
      if (who.user) {
        const ubs = await listUserBrackets();
        if (initialUb != null) {
          const ub = ubs.user_brackets.find((u) => u.id === initialUb);
          if (ub?.challenge_id != null) {
            setActiveChallenge({
              challengeId: ub.challenge_id,
              userBracketId: ub.id,
            });
            setPage('challenge');
          }
        }
      } else {
        setActiveChallenge(null);
      }
    } catch (e) {
      setSessionUser(null);
      setAuthError(
        e instanceof ApiError ? e.message : 'Unable to connect.',
      );
    }
  }, [initialUb]);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  function navigate(next: AppPage) {
    if (next === 'admin' && !sessionUser?.is_staff) {
      return;
    }
    if (next === 'home') {
      setActiveChallenge(null);
      setActiveStreakId(null);
      setHomeResetKey((k) => k + 1);
    }
    setPage(next);
  }

  async function openChallenge(
    challengeId: number,
    userBracketId?: number | null,
    initialTab?: ChallengeTab,
  ) {
    setActiveStreakId(null);
    setActiveChallenge({
      challengeId,
      userBracketId: userBracketId ?? null,
      initialTab,
    });
    setPage('challenge');
    const params = new URLSearchParams(window.location.search);
    if (userBracketId != null) {
      params.set('ub', String(userBracketId));
    } else {
      params.delete('ub');
    }
    const next = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState(null, '', next);
  }

  function openStreak(streakChallengeId: number) {
    setActiveChallenge(null);
    setActiveStreakId(streakChallengeId);
    setPage('streak');
    const params = new URLSearchParams(window.location.search);
    params.delete('ub');
    window.history.replaceState(null, '', window.location.pathname);
  }

  async function handleLogin(username: string, password: string) {
    setLoginBusy(true);
    setAuthError('');
    try {
      const { user } = await authLogin(username, password);
      setSessionUser(user);
      setActiveChallenge(null);
      setPage('home');
    } catch (e) {
      setAuthError(
        e instanceof ApiError ? e.message : 'Sign in failed.',
      );
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleSignup(username: string, password: string) {
    setLoginBusy(true);
    setAuthError('');
    try {
      const { user } = await authRegister(username, password);
      setSessionUser(user);
      setActiveChallenge(null);
      setPage('home');
    } catch (e) {
      setAuthError(
        e instanceof ApiError ? e.message : 'Could not create account.',
      );
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleSignOut() {
    try {
      await authLogout();
    } catch {
      /* still clear local session */
    }
    setSessionUser(null);
    setActiveChallenge(null);
    setPage('home');
  }

  if (sessionUser === undefined) {
    return <div className="app-loading">Loading…</div>;
  }

  if (sessionUser === null) {
    return (
      <LoginPage
        onLogin={handleLogin}
        onSignup={handleSignup}
        error={authError}
        busy={loginBusy}
      />
    );
  }

  return (
    <AppShell
      user={sessionUser}
      page={page}
      onNavigate={navigate}
      onSignOut={() => void handleSignOut()}
    >
      {page === 'home' ? (
        <ChallengesPage
          key={homeResetKey}
          onOpenChallenge={openChallenge}
          onOpenStreak={openStreak}
        />
      ) : null}

      {page === 'challenge' && activeChallenge != null ? (
        <ChallengeView
          key={`${activeChallenge.challengeId}-${activeChallenge.userBracketId ?? 'x'}-${activeChallenge.initialTab ?? 'bracket'}`}
          challengeId={activeChallenge.challengeId}
          userBracketId={activeChallenge.userBracketId}
          initialTab={activeChallenge.initialTab}
          currentUser={sessionUser}
          onBack={() => navigate('home')}
          onSubmitted={() => void refreshUserBrackets()}
        />
      ) : null}

      {page === 'streak' && activeStreakId != null ? (
        <StreakChallengeView
          key={activeStreakId}
          streakChallengeId={activeStreakId}
          currentUser={sessionUser}
          onBack={() => navigate('home')}
        />
      ) : null}

      {page === 'admin' && sessionUser.is_staff ? (
        <AdminPanel tab={adminTab} onTabChange={setAdminTab} />
      ) : null}
    </AppShell>
  );
}
