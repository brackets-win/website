import { useState } from 'react';

import { BracketsLogoMark } from '../BracketsLogoMark';

import './LoginPage.css';

type Mode = 'signin' | 'signup';

type Props = {
  onLogin: (username: string, password: string) => Promise<void>;
  onSignup: (username: string, password: string) => Promise<void>;
  error: string;
  busy: boolean;
};

export function LoginPage({ onLogin, onSignup, error, busy }: Props) {
  const [mode, setMode] = useState<Mode>('signin');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [localErr, setLocalErr] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalErr('');
    const name = username.trim();
    if (!name || !password) {
      setLocalErr('Enter a username and password.');
      return;
    }
    if (mode === 'signup') {
      if (password !== confirmPassword) {
        setLocalErr('Passwords do not match.');
        return;
      }
      await onSignup(name, password);
      return;
    }
    await onLogin(name, password);
  }

  function switchMode(next: Mode) {
    setMode(next);
    setLocalErr('');
    setPassword('');
    setConfirmPassword('');
  }

  const displayErr = localErr || error;
  const signingUp = mode === 'signup';

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
              {signingUp
                ? 'Create an account to join challenges.'
                : 'Sign in to fill and manage your picks.'}
            </p>
          </div>
        </div>

        <form className="login__form" onSubmit={(e) => void handleSubmit(e)}>
          {displayErr ? (
            <div className="alert alert--error" role="alert">
              {displayErr}
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
              autoComplete={
                signingUp ? 'new-password' : 'current-password'
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          {signingUp ? (
            <div className="field">
              <label htmlFor="login-confirm-password">Confirm Password</label>
              <input
                id="login-confirm-password"
                className="input"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={busy}
                required
              />
            </div>
          ) : null}

          <button
            type="submit"
            className="btn btn--primary login__submit"
            disabled={busy || !username.trim()}
          >
            {busy
              ? signingUp
                ? 'Creating Account…'
                : 'Signing In…'
              : signingUp
                ? 'Create Account'
                : 'Sign In'}
          </button>

          <p className="login__switch">
            {signingUp ? (
              <>
                Already have an account?{' '}
                <button
                  type="button"
                  className="login__switch-btn"
                  onClick={() => switchMode('signin')}
                  disabled={busy}
                >
                  Sign In
                </button>
              </>
            ) : (
              <>
                New here?{' '}
                <button
                  type="button"
                  className="login__switch-btn"
                  onClick={() => switchMode('signup')}
                  disabled={busy}
                >
                  Create Account
                </button>
              </>
            )}
          </p>
        </form>
      </div>
    </div>
  );
}
