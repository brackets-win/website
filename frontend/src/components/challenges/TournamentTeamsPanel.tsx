import { useCallback, useEffect, useState } from 'react';

import {
  ApiError,
  getChallengeTeams,
  saveChallengeTeams,
  type TournamentTeamRow,
} from '../../utils/api';

type Props = {
  challengeId: number;
  teamCount: number;
  onSaved: () => void;
};

function emptyNames(count: number): string[] {
  return Array.from({ length: count }, () => '');
}

function namesFromRows(rows: TournamentTeamRow[], count: number): string[] {
  const base = emptyNames(count);
  rows.forEach((row, idx) => {
    if (idx >= base.length) return;
    base[idx] = row.name;
  });
  return base;
}

export function TournamentTeamsPanel({
  challengeId,
  teamCount,
  onSaved,
}: Props) {
  const [names, setNames] = useState<string[]>(() => emptyNames(teamCount));
  const [busy, setBusy] = useState(false);
  const [loadErr, setLoadErr] = useState('');
  const [saveErr, setSaveErr] = useState('');

  const load = useCallback(async () => {
    setLoadErr('');
    try {
      const { teams } = await getChallengeTeams(challengeId);
      setNames(namesFromRows(teams, teamCount));
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load teams.',
      );
      setNames(emptyNames(teamCount));
    }
  }, [challengeId, teamCount]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setNames((prev) => {
      if (prev.length === teamCount) return prev;
      const next = emptyNames(teamCount);
      for (let i = 0; i < Math.min(prev.length, next.length); i += 1) {
        next[i] = prev[i];
      }
      return next;
    });
  }, [teamCount]);

  function updateName(index: number, value: string) {
    setNames((prev) => prev.map((n, i) => (i === index ? value : n)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaveErr('');
    const teams = names.map((name, idx) => ({
      name: name.trim(),
      seed: idx + 1,
    }));
    if (teams.some((t) => !t.name)) {
      setSaveErr('Enter a name for every team.');
      return;
    }
    setBusy(true);
    try {
      await saveChallengeTeams(challengeId, { teams });
      onSaved();
    } catch (err) {
      setSaveErr(err instanceof ApiError ? err.message : 'Could not save teams.');
    } finally {
      setBusy(false);
    }
  }

  if (loadErr) {
    return <p className="challenge-view__muted">{loadErr}</p>;
  }

  return (
    <form className="challenge-view__teams-form" onSubmit={(e) => void handleSubmit(e)}>
      <ul
        className="challenge-view__teams-list"
        style={
          {
            '--teams-per-col': Math.ceil(teamCount / 2),
          } as React.CSSProperties
        }
      >
        {names.map((name, idx) => (
          <li key={idx} className="challenge-view__teams-row">
            <span className="challenge-view__teams-seed" aria-hidden>
              {idx + 1}
            </span>
            <input
              id={`team-name-${idx}`}
              className="input"
              value={name}
              onChange={(e) => updateName(idx, e.target.value)}
              maxLength={100}
              required
              disabled={busy}
              placeholder="Team name"
              aria-label={`Seed ${idx + 1} team name`}
            />
          </li>
        ))}
      </ul>
      {saveErr ? (
        <div className="alert alert--error" role="status">
          {saveErr}
        </div>
      ) : null}
      <button type="submit" className="btn btn--primary" disabled={busy}>
        {busy ? 'Saving…' : 'Save Teams'}
      </button>
    </form>
  );
}
