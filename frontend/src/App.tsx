import { useEffect, useMemo, useState } from 'react';
import './App.css';

import { BracketFill } from './components/bracket/BracketFill';
import {
  ApiError,
  authLogin,
  authMe,
  listBrackets,
  listUserBrackets,
  type BracketSummary,
} from './utils/api';

function readUbFromLocation(): number | null {
  const q = new URLSearchParams(window.location.search).get('ub');
  if (!q) return null;
  const n = parseInt(q, 10);
  return Number.isFinite(n) ? n : null;
}

function App() {
  const [me, setMe] = useState<string>('…');
  const [brackets, setBrackets] = useState<BracketSummary[]>([]);
  const [apiNote, setApiNote] = useState<string>('');

  const initialUb = useMemo(() => readUbFromLocation(), []);
  const [userBracketId, setUserBracketId] = useState<number>(
    initialUb ?? 4,
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [who, list] = await Promise.all([authMe(), listBrackets()]);
        if (cancelled) return;
        setMe(who.user ? who.user.username : '(anonymous)');
        setBrackets(list.brackets);
        setApiNote('');

        if (who.user && initialUb == null) {
          const ubs = await listUserBrackets();
          if (cancelled) return;
          const pick = ubs.user_brackets[0];
          if (pick) setUserBracketId(pick.id);
        }
      } catch (e) {
        if (cancelled) return;
        setApiNote(
          e instanceof ApiError ? e.message : 'Unable to connect.',
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialUb]);

  async function loginDemo() {
    try {
      const { user } = await authLogin('player', 'demo');
      setMe(user.username);
      const [list, ubs] = await Promise.all([
        listBrackets(),
        listUserBrackets(),
      ]);
      setBrackets(list.brackets);
      const pick = ubs.user_brackets[0];
      if (pick) setUserBracketId(pick.id);
      setApiNote('');
    } catch (e) {
      if (e instanceof ApiError) {
        setApiNote(e.message);
      } else if (e instanceof TypeError) {
        setApiNote('Unable to connect.');
      } else {
        setApiNote(e instanceof Error ? e.message : 'Login failed.');
      }
    }
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '1rem' }}>
      <header style={{ marginBottom: '1.25rem' }}>
        <h1 style={{ margin: '0 0 0.5rem', fontSize: '1.35rem' }}>
          Brackets
        </h1>
        <p style={{ margin: 0, fontSize: '0.9rem', opacity: 0.85 }}>
          Session: <strong>{me}</strong>
          {brackets.length > 0
            ? ` · ${brackets.map((b) => b.name).join(', ')}`
            : ''}
        </p>
        {apiNote ? (
          <p style={{ color: '#c43333', marginTop: '0.5rem' }}>{apiNote}</p>
        ) : null}
        <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" onClick={loginDemo}>
            Log in as player/demo
          </button>
          <label style={{ display: 'flex', gap: '0.35rem', alignItems: 'center', fontSize: '0.9rem' }}>
            User bracket id
            <input
              type="number"
              min={1}
              value={userBracketId}
              onChange={(e) =>
                setUserBracketId(parseInt(e.target.value, 10) || 1)
              }
              style={{ width: 72 }}
            />
          </label>
        </div>
      </header>

      {me !== '(anonymous)' && me !== '…' ? (
        <BracketFill userBracketId={userBracketId} />
      ) : (
        <p style={{ fontSize: '0.9rem', color: '#5c6470' }}>Log in to view your bracket.</p>
      )}
    </div>
  );
}

export default App;
