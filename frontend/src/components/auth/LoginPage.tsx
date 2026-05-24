import { useState } from 'react';

import { BracketsLogoMark } from '../BracketsLogoMark';

import './LoginPage.css';

type Props = {
  onLogin: (username: string, password: string) => Promise<void>;
  error: string;
  busy: boolean;
};

export function LoginPage({ onLogin, error, busy }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await onLogin(username.trim(), password);
  }

  return (
    <div className="login">
      <div className="login__card card">
        <div className="login__brand">
          <span className="login__mark">
            <BracketsLogoMark />
          </span>
          <div>
            <h1 className="login__title">brackets.win</h1>
            <p className="login__tagline">
              Sign in to fill and manage your picks.
            </p>
          </div>
        </div>

        <form className="login__form" onSubmit={handleSubmit}>
          {error ? (
            <div className="alert alert--error" role="alert">
              {error}
            </div>
          ) : null}

          <div className="field">
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              className="input"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary login__submit"
            disabled={busy || !username.trim()}
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}
