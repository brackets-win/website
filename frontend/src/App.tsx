import { useCallback, useEffect, useState } from 'react';
import {
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
} from 'react-router-dom';

import { AdminPanel } from './components/admin/AdminPanel';
import { LoginPage } from './components/auth/LoginPage';
import { ChallengeView } from './components/challenges/ChallengeView';
import { ChallengesPage } from './components/challenges/ChallengesPage';
import { StreakChallengeView } from './components/challenges/StreakChallengeView';
import { AppShell } from './components/layout/AppShell';
import { LegacyUbRedirect } from './components/routing/LegacyUbRedirect';
import {
  adminPath,
  challengePath,
  isAdminTab,
  isChallengeTab,
  isStreakTab,
  parseRouteId,
  streakPath,
  type AdminTab,
  type ChallengeTab,
} from './routes';
import {
  ApiError,
  authLogin,
  authLogout,
  authMe,
  authRegister,
  getChallenge,
  type ApiUser,
} from './utils/api';
import { defaultChallengeTab } from './utils/challengeTypes';

import './components/admin/admin-shared.css';

function ChallengeLandingRedirect() {
  const { challengeId: challengeIdParam } = useParams();
  const challengeId = parseRouteId(challengeIdParam);
  const [tab, setTab] = useState<ChallengeTab | 'error' | null>(null);

  useEffect(() => {
    if (challengeId == null) return;
    setTab(null);
    void getChallenge(challengeId)
      .then(({ challenge }) => setTab(defaultChallengeTab(challenge)))
      .catch(() => setTab('error'));
  }, [challengeId]);

  if (challengeId == null) {
    return <Navigate to="/" replace />;
  }
  if (tab == null) {
    return null;
  }
  if (tab === 'error') {
    return <Navigate to={challengePath(challengeId, 'bracket')} replace />;
  }
  return <Navigate to={challengePath(challengeId, tab)} replace />;
}

function StreakTabRedirect() {
  return <Navigate to="leaderboard" replace />;
}

function AdminTabRedirect() {
  return <Navigate to={adminPath('contestants')} replace />;
}

function AdminRoute({ user }: { user: ApiUser }) {
  const { tab } = useParams();
  const navigate = useNavigate();

  if (!user.is_staff) {
    return <Navigate to="/" replace />;
  }

  const activeTab: AdminTab = isAdminTab(tab) ? tab : 'contestants';
  if (tab != null && !isAdminTab(tab)) {
    return <Navigate to={adminPath('contestants')} replace />;
  }

  return (
    <AdminPanel
      tab={activeTab}
      onTabChange={(next) => {
        navigate(adminPath(next));
      }}
    />
  );
}

function ChallengeViewRoute({ currentUser }: { currentUser: ApiUser }) {
  const { challengeId: challengeIdParam, tab, userBracketId } = useParams();
  const challengeId = parseRouteId(challengeIdParam);
  const playerUserBracketId = parseRouteId(userBracketId);

  if (challengeId == null) {
    return <Navigate to="/" replace />;
  }

  if (playerUserBracketId != null) {
    return (
      <ChallengeView
        challengeId={challengeId}
        tab="leaderboard"
        viewingPlayerId={playerUserBracketId}
        currentUser={currentUser}
      />
    );
  }

  if (tab === 'player' || tab == null || !isChallengeTab(tab)) {
    return <Navigate to={challengePath(challengeId, 'bracket')} replace />;
  }

  return (
    <ChallengeView
      challengeId={challengeId}
      tab={tab}
      currentUser={currentUser}
    />
  );
}

function StreakChallengeViewRoute({ currentUser }: { currentUser: ApiUser }) {
  const { streakId: streakIdParam, tab, userId } = useParams();
  const streakId = parseRouteId(streakIdParam);
  const playerUserId = parseRouteId(userId);

  if (streakId == null) {
    return <Navigate to="/" replace />;
  }

  if (playerUserId != null) {
    return (
      <StreakChallengeView
        streakChallengeId={streakId}
        tab="leaderboard"
        viewingPlayerId={playerUserId}
        currentUser={currentUser}
      />
    );
  }

  if (tab === 'player' || tab == null || !isStreakTab(tab)) {
    return <Navigate to={streakPath(streakId, 'leaderboard')} replace />;
  }

  return (
    <StreakChallengeView
      streakChallengeId={streakId}
      tab={tab}
      currentUser={currentUser}
    />
  );
}

export default function App() {
  const [sessionUser, setSessionUser] = useState<ApiUser | null | undefined>(
    undefined,
  );
  const [loginBusy, setLoginBusy] = useState(false);
  const [authError, setAuthError] = useState('');

  const loadSession = useCallback(async () => {
    try {
      const who = await authMe();
      setSessionUser(who.user);
      setAuthError('');
    } catch (e) {
      setSessionUser(null);
      setAuthError(
        e instanceof ApiError ? e.message : 'Unable to connect.',
      );
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  async function handleLogin(username: string, password: string) {
    setLoginBusy(true);
    setAuthError('');
    try {
      const { user } = await authLogin(username, password);
      setSessionUser(user);
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
    <AppShell user={sessionUser} onSignOut={() => void handleSignOut()}>
      <LegacyUbRedirect />
      <Routes>
        <Route path="/" element={<ChallengesPage />} />

        <Route
          path="/challenge/:challengeId"
          element={<ChallengeLandingRedirect />}
        />
        <Route
          path="/challenge/:challengeId/player/:userBracketId"
          element={<ChallengeViewRoute currentUser={sessionUser} />}
        />
        <Route
          path="/challenge/:challengeId/:tab"
          element={<ChallengeViewRoute currentUser={sessionUser} />}
        />

        <Route path="/streak/:streakId" element={<StreakTabRedirect />} />
        <Route
          path="/streak/:streakId/player/:userId"
          element={<StreakChallengeViewRoute currentUser={sessionUser} />}
        />
        <Route
          path="/streak/:streakId/:tab"
          element={<StreakChallengeViewRoute currentUser={sessionUser} />}
        />

        <Route path="/admin" element={<AdminTabRedirect />} />
        <Route
          path="/admin/:tab"
          element={<AdminRoute user={sessionUser} />}
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
