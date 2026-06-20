import { useState } from 'react';

import { BracketsLogoMark } from '../BracketsLogoMark';

import './LoginPage.css';

type Props = {
  username: string;
  forced: boolean;
  onSubmit: (newPassword: string) => Promise<void>;
  onSignOut: () => void;
  error: string;
  busy: boolean;
};

export function ChangePasswordPage({
  username,
  forced,
  onSubmit,
  onSignOut,
  error,
  busy,
}: Props) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [localErr, setLocalErr] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalErr('');
    if (!password) {
      setLocalErr('Enter a new password.');
      return;
    }
    if (password !== confirmPassword) {
      setLocalErr('Passwords do not match.');
      return;
    }
    await onSubmit(password);
  }

  const displayErr = localErr || error;

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
              {forced
                ? `Hi ${username}, set a new password to continue.`
                : 'Choose a new password for your account.'}
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
            <label htmlFor="change-password-new">New Password</label>
            <input
              id="change-password-new"
              className="input"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="change-password-confirm">Confirm Password</label>
            <input
              id="change-password-confirm"
              className="input"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary login__submit"
            disabled={busy || !password}
          >
            {busy ? 'Saving…' : 'Save Password'}
          </button>

          <p className="login__switch">
            <button
              type="button"
              className="login__switch-btn"
              onClick={onSignOut}
              disabled={busy}
            >
              Sign Out
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
