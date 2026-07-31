import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  drawChallengeTeams,
  getChallengeTeams,
  saveChallengeTeams,
  type TournamentTeamRow,
} from '../../utils/api';

import './TournamentTeamsPanel.css';

type PlacementMode = 'manual' | 'random' | 'random_balanced';

type Props = {
  challengeId: number;
  teamCount: number;
  onSaved: () => void;
};

function emptyNames(count: number): string[] {
  return Array.from({ length: count }, () => '');
}

function divisorsForPots(total: number): number[] {
  if (total < 4) return [];
  const out: number[] = [];
  for (let d = 2; d <= total / 2; d += 1) {
    if (total % d === 0) out.push(d);
  }
  return out;
}

function defaultPotCount(
  total: number,
  teamsPerGroup: number | null,
): number {
  const opts = divisorsForPots(total);
  if (opts.length === 0) return 2;
  if (teamsPerGroup && opts.includes(teamsPerGroup)) return teamsPerGroup;
  return opts[0] ?? 2;
}

function groupCode(index: number): string {
  return String.fromCharCode(65 + index);
}

export function TournamentTeamsPanel({
  challengeId,
  teamCount,
  onSaved,
}: Props) {
  const [mode, setMode] = useState<PlacementMode>('manual');
  const [structure, setStructure] = useState<'SINGLE_ELIM' | 'GROUP_KNOCKOUT'>(
    'SINGLE_ELIM',
  );
  const [numberOfGroups, setNumberOfGroups] = useState<number | null>(null);
  const [teamsPerGroup, setTeamsPerGroup] = useState<number | null>(null);
  const [capacity, setCapacity] = useState(teamCount);

  const [manualNames, setManualNames] = useState<string[]>(() =>
    emptyNames(teamCount),
  );
  const [poolNames, setPoolNames] = useState<string[]>(() =>
    emptyNames(teamCount),
  );
  const [potCount, setPotCount] = useState(2);
  const [potNames, setPotNames] = useState<string[][]>(() => [[], []]);
  const [draftName, setDraftName] = useState('');
  const [draftTarget, setDraftTarget] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [loadErr, setLoadErr] = useState('');
  const [saveErr, setSaveErr] = useState('');

  const potOptions = useMemo(() => divisorsForPots(capacity), [capacity]);
  const potSize = potCount > 0 ? capacity / potCount : 0;

  const applyMeta = useCallback(
    (meta: {
      team_count: number;
      structure: 'SINGLE_ELIM' | 'GROUP_KNOCKOUT';
      number_of_groups: number | null;
      teams_per_group: number | null;
      teams: TournamentTeamRow[];
    }) => {
      const n = meta.team_count || teamCount;
      setCapacity(n);
      setStructure(meta.structure);
      setNumberOfGroups(meta.number_of_groups);
      setTeamsPerGroup(meta.teams_per_group);

      const bySeed = emptyNames(n);
      meta.teams.forEach((row) => {
        if (row.seed != null && row.seed >= 1 && row.seed <= n) {
          bySeed[row.seed - 1] = row.name;
        }
      });
      setManualNames(bySeed);
      setPoolNames(bySeed.map((name) => name));

      const nextPotCount = defaultPotCount(n, meta.teams_per_group);
      setPotCount(nextPotCount);
      setPotNames(Array.from({ length: nextPotCount }, () => []));
    },
    [teamCount],
  );

  const load = useCallback(async () => {
    setLoadErr('');
    try {
      const meta = await getChallengeTeams(challengeId);
      applyMeta(meta);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load teams.',
      );
      setManualNames(emptyNames(teamCount));
      setPoolNames(emptyNames(teamCount));
    }
  }, [applyMeta, challengeId, teamCount]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!potOptions.includes(potCount) && potOptions.length > 0) {
      const next = defaultPotCount(capacity, teamsPerGroup);
      setPotCount(next);
    }
  }, [capacity, potCount, potOptions, teamsPerGroup]);

  useEffect(() => {
    setPotNames((prev) => {
      const next = Array.from({ length: potCount }, (_, i) =>
        (prev[i] ?? []).slice(0, potSize),
      );
      return next;
    });
  }, [potCount, potSize]);

  function openDraft(target: string) {
    setDraftTarget(target);
    setDraftName('');
  }

  function closeDraft() {
    setDraftTarget(null);
    setDraftName('');
  }

  function commitDraft() {
    const name = draftName.trim();
    if (!name || !draftTarget) return;

    if (draftTarget.startsWith('manual:')) {
      const idx = parseInt(draftTarget.slice('manual:'.length), 10);
      setManualNames((prev) =>
        prev.map((n, i) => (i === idx ? name : n)),
      );
    } else if (draftTarget.startsWith('pool:')) {
      const idx = parseInt(draftTarget.slice('pool:'.length), 10);
      setPoolNames((prev) => prev.map((n, i) => (i === idx ? name : n)));
    } else if (draftTarget.startsWith('pot:')) {
      const potIdx = parseInt(draftTarget.slice('pot:'.length), 10);
      setPotNames((prev) =>
        prev.map((bucket, i) => {
          if (i !== potIdx) return bucket;
          if (bucket.length >= potSize) return bucket;
          return [...bucket, name];
        }),
      );
    }
    closeDraft();
  }

  function clearManual(idx: number) {
    setManualNames((prev) => prev.map((n, i) => (i === idx ? '' : n)));
  }

  function clearPool(idx: number) {
    setPoolNames((prev) => prev.map((n, i) => (i === idx ? '' : n)));
  }

  function removeFromPot(potIdx: number, teamIdx: number) {
    setPotNames((prev) =>
      prev.map((bucket, i) =>
        i === potIdx ? bucket.filter((_, j) => j !== teamIdx) : bucket,
      ),
    );
  }

  async function handleSaveManual(e: React.FormEvent) {
    e.preventDefault();
    setSaveErr('');
    const teams = manualNames.map((name, idx) => ({
      name: name.trim(),
      seed: idx + 1,
    }));
    if (teams.some((t) => !t.name)) {
      setSaveErr('Add a name for every slot.');
      return;
    }
    setBusy(true);
    try {
      const meta = await saveChallengeTeams(challengeId, { teams });
      applyMeta(meta);
      onSaved();
    } catch (err) {
      setSaveErr(err instanceof ApiError ? err.message : 'Could not save teams.');
    } finally {
      setBusy(false);
    }
  }

  async function handleDraw() {
    setSaveErr('');
    let teams: Array<{ name: string; pot?: number }>;
    if (mode === 'random') {
      teams = poolNames.map((name) => ({ name: name.trim() }));
      if (teams.some((t) => !t.name)) {
        setSaveErr('Add a name for every team before drawing.');
        return;
      }
    } else {
      const flat: Array<{ name: string; pot: number }> = [];
      potNames.forEach((bucket, potIdx) => {
        bucket.forEach((name) => {
          flat.push({ name: name.trim(), pot: potIdx + 1 });
        });
      });
      if (flat.length !== capacity) {
        setSaveErr(
          `Fill every pot (${potSize} teams each) before drawing.`,
        );
        return;
      }
      if (flat.some((t) => !t.name)) {
        setSaveErr('Every pot team needs a name.');
        return;
      }
      teams = flat;
    }
    setBusy(true);
    try {
      const meta = await drawChallengeTeams(challengeId, {
        mode: mode === 'random' ? 'random' : 'random_balanced',
        teams,
      });
      applyMeta(meta);
      onSaved();
    } catch (err) {
      setSaveErr(err instanceof ApiError ? err.message : 'Could not draw teams.');
    } finally {
      setBusy(false);
    }
  }

  if (loadErr) {
    return <p className="challenge-view__muted">{loadErr}</p>;
  }

  const groupCards =
    structure === 'GROUP_KNOCKOUT' &&
    numberOfGroups != null &&
    teamsPerGroup != null
      ? Array.from({ length: numberOfGroups }, (_, g) => ({
          code: groupCode(g),
          seeds: Array.from(
            { length: teamsPerGroup },
            (__, s) => g * teamsPerGroup + s + 1,
          ),
        }))
      : null;

  return (
    <div className="ttp">
      <div className="ttp__mode" role="group" aria-label="Placement mode">
        {(
          [
            ['manual', 'Manual'],
            ['random', 'Full Random'],
            ['random_balanced', 'Random Balanced'],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={
              mode === value ? 'ttp__mode-btn ttp__mode-btn--on' : 'ttp__mode-btn'
            }
            onClick={() => setMode(value)}
            disabled={busy}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'random_balanced' ? (
        <div className="field ttp__pot-count">
          <label htmlFor="ttp-pots">Pots</label>
          <select
            id="ttp-pots"
            className="select"
            value={potCount}
            onChange={(e) => setPotCount(parseInt(e.target.value, 10))}
            disabled={busy || potOptions.length === 0}
          >
            {potOptions.map((n) => (
              <option key={n} value={n}>
                {n} ({capacity / n} each)
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {mode === 'manual' ? (
        <form
          className="challenge-view__teams-form"
          onSubmit={(e) => void handleSaveManual(e)}
        >
          {groupCards ? (
            <div className="ttp__groups">
              {groupCards.map((g) => (
                <div key={g.code} className="ttp__box">
                  <h3 className="ttp__box-title">Group {g.code}</h3>
                  <ul className="ttp__slots">
                    {g.seeds.map((seed) => {
                      const idx = seed - 1;
                      const name = manualNames[idx] ?? '';
                      return (
                        <li key={seed}>
                          {name ? (
                            <div className="ttp__filled">
                              <span className="ttp__slot-label">{`${g.code}${((seed - 1) % (teamsPerGroup ?? 1)) + 1}`}</span>
                              <span className="ttp__filled-name">{name}</span>
                              <button
                                type="button"
                                className="ttp__clear"
                                onClick={() => clearManual(idx)}
                                disabled={busy}
                                aria-label={`Remove ${name}`}
                              >
                                ×
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="ttp__empty"
                              onClick={() => openDraft(`manual:${idx}`)}
                              disabled={busy}
                            >
                              <span className="ttp__slot-label">{`${g.code}${((seed - 1) % (teamsPerGroup ?? 1)) + 1}`}</span>
                              <span className="ttp__plus" aria-hidden>
                                +
                              </span>
                              <span>Add Team</span>
                            </button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <ul className="ttp__slots ttp__slots--flat">
              {manualNames.map((name, idx) => (
                <li key={idx}>
                  {name ? (
                    <div className="ttp__filled">
                      <span className="ttp__slot-label">{idx + 1}</span>
                      <span className="ttp__filled-name">{name}</span>
                      <button
                        type="button"
                        className="ttp__clear"
                        onClick={() => clearManual(idx)}
                        disabled={busy}
                        aria-label={`Remove ${name}`}
                      >
                        ×
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="ttp__empty"
                      onClick={() => openDraft(`manual:${idx}`)}
                      disabled={busy}
                    >
                      <span className="ttp__slot-label">{idx + 1}</span>
                      <span className="ttp__plus" aria-hidden>
                        +
                      </span>
                      <span>Add Team</span>
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {saveErr ? (
            <div className="alert alert--error" role="status">
              {saveErr}
            </div>
          ) : null}
          <button type="submit" className="btn btn--primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save Teams'}
          </button>
        </form>
      ) : null}

      {mode === 'random' ? (
        <div className="ttp__draw-block">
          <ul className="ttp__slots ttp__slots--flat">
            {poolNames.map((name, idx) => (
              <li key={idx}>
                {name ? (
                  <div className="ttp__filled">
                    <span className="ttp__slot-label">{idx + 1}</span>
                    <span className="ttp__filled-name">{name}</span>
                    <button
                      type="button"
                      className="ttp__clear"
                      onClick={() => clearPool(idx)}
                      disabled={busy}
                      aria-label={`Remove ${name}`}
                    >
                      ×
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="ttp__empty"
                    onClick={() => openDraft(`pool:${idx}`)}
                    disabled={busy}
                  >
                    <span className="ttp__plus" aria-hidden>
                      +
                    </span>
                    <span>Add Team</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
          {saveErr ? (
            <div className="alert alert--error" role="status">
              {saveErr}
            </div>
          ) : null}
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy}
            onClick={() => void handleDraw()}
          >
            {busy ? 'Drawing…' : 'Draw'}
          </button>
        </div>
      ) : null}

      {mode === 'random_balanced' ? (
        <div className="ttp__draw-block">
          <div className="ttp__pots">
            {potNames.map((bucket, potIdx) => (
              <div key={potIdx} className="ttp__box">
                <h3 className="ttp__box-title">
                  Pot {potIdx + 1}
                  <span className="ttp__box-cap">
                    {bucket.length}/{potSize}
                  </span>
                </h3>
                <ul className="ttp__slots">
                  {bucket.map((name, teamIdx) => (
                    <li key={`${name}-${teamIdx}`}>
                      <div className="ttp__filled">
                        <span className="ttp__filled-name">{name}</span>
                        <button
                          type="button"
                          className="ttp__clear"
                          onClick={() => removeFromPot(potIdx, teamIdx)}
                          disabled={busy}
                          aria-label={`Remove ${name}`}
                        >
                          ×
                        </button>
                      </div>
                    </li>
                  ))}
                  {Array.from({
                    length: Math.max(0, potSize - bucket.length),
                  }).map((_, emptyIdx) => (
                    <li key={`empty-${emptyIdx}`}>
                      <button
                        type="button"
                        className="ttp__empty"
                        onClick={() => openDraft(`pot:${potIdx}`)}
                        disabled={busy}
                      >
                        <span className="ttp__plus" aria-hidden>
                          +
                        </span>
                        <span>Add Team</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          {saveErr ? (
            <div className="alert alert--error" role="status">
              {saveErr}
            </div>
          ) : null}
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy}
            onClick={() => void handleDraw()}
          >
            {busy ? 'Drawing…' : 'Draw'}
          </button>
        </div>
      ) : null}

      {structure === 'GROUP_KNOCKOUT' ? (
        <p className="ttp__hint">
          After the draw, set group finish order on the Bracket tab. Knockout
          slots fill from the group → knockout method chosen at create.
        </p>
      ) : null}

      {draftTarget ? (
        <div className="ttp__draft-backdrop" role="presentation">
          <div
            className="ttp__draft"
            role="dialog"
            aria-modal="true"
            aria-label="Add team"
          >
            <label htmlFor="ttp-draft-name">Team Name</label>
            <input
              id="ttp-draft-name"
              className="input"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              maxLength={100}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  commitDraft();
                }
                if (e.key === 'Escape') closeDraft();
              }}
            />
            <div className="ttp__draft-actions">
              <button
                type="button"
                className="btn btn--ghost"
                onClick={closeDraft}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={commitDraft}
                disabled={!draftName.trim()}
              >
                Add Team
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export { divisorsForPots };
