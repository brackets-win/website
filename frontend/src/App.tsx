import { useEffect, useState } from 'react';
import reactLogo from './assets/react.svg';
import viteLogo from '/vite.svg';
import './App.css';

import { testAPI } from './utils/api';
import {
  ApiError,
  authLogin,
  authMe,
  listBrackets,
  type BracketSummary,
} from './utils/api';

function App() {
  const [count, setCount] = useState(0);
  const [value1, setValue1] = useState(0);
  const [value2, setValue2] = useState(0);
  const [result, setResult] = useState<number>();

  const [me, setMe] = useState<string>('…');
  const [brackets, setBrackets] = useState<BracketSummary[]>([]);
  const [apiNote, setApiNote] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [who, list] = await Promise.all([authMe(), listBrackets()]);
        if (cancelled) return;
        setMe(who.user ? who.user.username : '(anonymous)');
        setBrackets(list.brackets);
        setApiNote('');
      } catch (e) {
        if (cancelled) return;
        setApiNote(
          e instanceof ApiError
            ? e.message
            : 'Could not reach API (is Django running on :8000?)',
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function getResult() {
    setResult(await testAPI(value1, value2));
  }

  async function loginDemo() {
    try {
      const { user } = await authLogin('player', 'demo');
      setMe(user.username);
      const list = await listBrackets();
      setBrackets(list.brackets);
      setApiNote('');
    } catch (e) {
      setApiNote(
        e instanceof ApiError
          ? e.message
          : 'Login failed — run: python manage.py seed_demo_bracket',
      );
    }
  }

  return (
    <>
      <div>
        <a href="https://vitejs.dev" target="_blank">
          <img src={viteLogo} className="logo" alt="Vite logo" />
        </a>
        <a href="https://react.dev" target="_blank">
          <img src={reactLogo} className="logo react" alt="React logo" />
        </a>
      </div>
      <h1>Vite + React</h1>

      <section style={{ textAlign: 'left', maxWidth: 480, margin: '0 auto' }}>
        <h2>API</h2>
        <p>
          Session: <strong>{me}</strong>
        </p>
        <p>
          Brackets:{' '}
          <strong>
            {brackets.map((b) => b.name).join(', ') || '(none)'}
          </strong>
        </p>
        {apiNote ? (
          <p style={{ color: 'coral' }}>{apiNote}</p>
        ) : null}
        <button type="button" onClick={loginDemo}>
          Log in as player/demo
        </button>
        <p style={{ fontSize: 12, opacity: 0.85 }}>
          Requires backend with{' '}
          <code>python manage.py seed_demo_bracket</code> and{' '}
          <code>runserver</code>.
        </p>
      </section>

      <div className="card">
        <button onClick={() => setCount((count) => count + 1)}>
          count is {count}
        </button>
        <p>
          Edit <code>src/App.tsx</code> and save to test HMR
        </p>
      </div>
      <p className="read-the-docs">
        Click on the Vite and React logos to learn more
      </p>

      <input
        type="number"
        value={value1}
        onChange={(event) => setValue1(parseInt(event.currentTarget.value, 10))}
      />
      +
      <input
        type="number"
        value={value2}
        onChange={(event) => setValue2(parseInt(event.currentTarget.value, 10))}
      />
      ={result ?? '?'}
      <br />
      <button onClick={getResult}>Calculate (legacy /brackets/test)</button>
    </>
  );
}

export default App;
