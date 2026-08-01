import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  createChallengeTeamContestant,
  drawChallengeTeams,
  getChallengeTeamCatalog,
  getChallengeTeams,
  saveChallengeTeams,
  startChallengeTournament,
  type ContestantCatalog,
  type ContestantTagInfo,
  type TournamentTeamRow,
} from '../../utils/api';
import {
  isPowerOf2,
  singleElimByeCount,
  singleElimPlayInCount,
} from '../../utils/singleElimByes';
import { ContestantAvatar } from '../bracket/ContestantAvatar';
import '../admin/BracketSeeder.css';

import './TournamentTeamsPanel.css';

type PlacementMode = 'manual' | 'random' | 'random_balanced';

type TeamPick = {
  contestant_id: number;
  name: string;
  photo_url?: string | null;
};

type Props = {
  challengeId: number;
  teamCount: number;
  onSaved: () => void;
  onStarted: () => void;
};

function emptySlots(count: number): (TeamPick | null)[] {
  return Array.from({ length: count }, () => null);
}

function pickFromRow(row: TournamentTeamRow): TeamPick | null {
  if (row.contestant_id == null) {
    // Legacy name-only rows — treat as unfilled for picker UX.
    return null;
  }
  return {
    contestant_id: row.contestant_id,
    name: row.name,
    photo_url: row.photo_url,
  };
}

function pickFromCatalog(c: ContestantCatalog): TeamPick {
  return {
    contestant_id: c.id,
    name: c.name,
    photo_url: c.photo_url ?? c.image_url ?? null,
  };
}

function contestantImage(c: ContestantCatalog): string | null {
  return c.photo_url ?? c.image_url ?? null;
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

/** Fill pots from a flat list without dropping teams when pot count changes. */
function distributeToPots(
  picks: TeamPick[],
  count: number,
  capacities: number[],
): TeamPick[][] {
  const buckets: TeamPick[][] = Array.from({ length: count }, () => []);
  let i = 0;
  for (let potIdx = 0; potIdx < count; potIdx += 1) {
    const cap = Math.max(0, capacities[potIdx] ?? 0);
    while (buckets[potIdx]!.length < cap && i < picks.length) {
      buckets[potIdx]!.push(picks[i]!);
      i += 1;
    }
  }
  return buckets;
}

function reshapePots(
  prev: TeamPick[][],
  count: number,
  capacities: number[],
): TeamPick[][] {
  const fits =
    prev.length === count &&
    prev.every((bucket, i) => bucket.length <= (capacities[i] ?? 0));
  if (fits) return prev;
  return distributeToPots(prev.flat(), count, capacities);
}

function groupCode(index: number): string {
  return String.fromCharCode(65 + index);
}

export function TournamentTeamsPanel({
  challengeId,
  teamCount,
  onSaved,
  onStarted,
}: Props) {
  const [mode, setMode] = useState<PlacementMode>('manual');
  const [structure, setStructure] = useState<'SINGLE_ELIM' | 'GROUP_KNOCKOUT'>(
    'SINGLE_ELIM',
  );
  const [numberOfGroups, setNumberOfGroups] = useState<number | null>(null);
  const [teamsPerGroup, setTeamsPerGroup] = useState<number | null>(null);
  const [capacity, setCapacity] = useState(teamCount);

  const [manualSlots, setManualSlots] = useState<(TeamPick | null)[]>(() =>
    emptySlots(teamCount),
  );
  const [poolSlots, setPoolSlots] = useState<(TeamPick | null)[]>(() =>
    emptySlots(teamCount),
  );
  const [potCount, setPotCount] = useState(2);
  const [potSlots, setPotSlots] = useState<TeamPick[][]>(() => [[], []]);
  const [draftTarget, setDraftTarget] = useState<string | null>(null);

  const [catalog, setCatalog] = useState<ContestantCatalog[]>([]);
  const [tags, setTags] = useState<ContestantTagInfo[]>([]);
  const [query, setQuery] = useState('');
  const [tagIds, setTagIds] = useState<number[]>([]);
  const [pickerTab, setPickerTab] = useState<'pick' | 'create'>('pick');
  const [createName, setCreateName] = useState('');
  const [createPhoto, setCreatePhoto] = useState<File | null>(null);
  const [createPhotoPreview, setCreatePhotoPreview] = useState<string | null>(
    null,
  );
  const [createBusy, setCreateBusy] = useState(false);

  const [busy, setBusy] = useState(false);
  const [loadErr, setLoadErr] = useState('');
  const [saveErr, setSaveErr] = useState('');

  const potOptions = useMemo(() => divisorsForPots(capacity), [capacity]);
  const byeCount = useMemo(
    () =>
      structure === 'SINGLE_ELIM' && !isPowerOf2(capacity)
        ? singleElimByeCount(capacity)
        : 0,
    [structure, capacity],
  );
  const useByePots = byeCount > 0;
  const playInCount = useByePots ? singleElimPlayInCount(capacity) : 0;
  const potSize = potCount > 0 ? capacity / potCount : 0;
  const potCapacities = useMemo(() => {
    if (useByePots) return [byeCount, playInCount];
    return Array.from({ length: potCount }, () => potSize);
  }, [useByePots, byeCount, playInCount, potCount, potSize]);

  const assignedIds = useMemo(() => {
    const ids = new Set<number>();
    if (mode === 'manual') {
      for (const slot of manualSlots) {
        if (slot) ids.add(slot.contestant_id);
      }
    } else if (mode === 'random') {
      for (const slot of poolSlots) {
        if (slot) ids.add(slot.contestant_id);
      }
    } else {
      for (const bucket of potSlots) {
        for (const slot of bucket) ids.add(slot.contestant_id);
      }
    }
    return ids;
  }, [mode, manualSlots, poolSlots, potSlots]);

  const available = useMemo(() => {
    const q = query.trim().toLowerCase();
    return catalog.filter((c) => {
      if (assignedIds.has(c.id)) return false;
      if (q) {
        if (
          !c.name.toLowerCase().includes(q) &&
          !c.identifier.toLowerCase().includes(q)
        ) {
          return false;
        }
      }
      if (tagIds.length > 0 && !c.tags.some((t) => tagIds.includes(t.id))) {
        return false;
      }
      return true;
    });
  }, [catalog, assignedIds, query, tagIds]);

  const filterTags = useMemo(() => {
    const map = new Map<number, ContestantTagInfo>();
    for (const t of tags) map.set(t.id, t);
    for (const c of catalog) {
      for (const t of c.tags) map.set(t.id, t);
    }
    return Array.from(map.values()).sort((a, b) =>
      a.name.localeCompare(b.name),
    );
  }, [tags, catalog]);

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

      const bySeed = emptySlots(n);
      meta.teams.forEach((row) => {
        if (row.seed != null && row.seed >= 1 && row.seed <= n) {
          bySeed[row.seed - 1] = pickFromRow(row);
        }
      });
      const picks = bySeed.filter((s): s is TeamPick => s != null);
      setManualSlots(bySeed);
      setPoolSlots(bySeed.map((slot) => (slot ? { ...slot } : null)));

      const seByes =
        meta.structure === 'SINGLE_ELIM' && !isPowerOf2(n)
          ? singleElimByeCount(n)
          : 0;
      if (seByes > 0) {
        const play = singleElimPlayInCount(n);
        setPotCount(2);
        setPotSlots(distributeToPots(picks, 2, [seByes, play]));
      } else {
        const nextPotCount = defaultPotCount(n, meta.teams_per_group);
        const cap = nextPotCount > 0 ? n / nextPotCount : 0;
        setPotCount(nextPotCount);
        setPotSlots(
          distributeToPots(
            picks,
            nextPotCount,
            Array.from({ length: nextPotCount }, () => cap),
          ),
        );
      }
    },
    [teamCount],
  );

  const load = useCallback(async () => {
    setLoadErr('');
    try {
      const [meta, cat] = await Promise.all([
        getChallengeTeams(challengeId),
        getChallengeTeamCatalog(challengeId),
      ]);
      applyMeta(meta);
      setCatalog(cat.contestants);
      setTags(cat.tags);
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load teams.',
      );
      setManualSlots(emptySlots(teamCount));
      setPoolSlots(emptySlots(teamCount));
      setPotSlots([[], []]);
    }
  }, [applyMeta, challengeId, teamCount]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (useByePots) {
      if (potCount !== 2) setPotCount(2);
      return;
    }
    if (!potOptions.includes(potCount) && potOptions.length > 0) {
      setPotCount(defaultPotCount(capacity, teamsPerGroup));
    }
  }, [potOptions, potCount, capacity, teamsPerGroup, useByePots]);

  useEffect(() => {
    setPotSlots((prev) => reshapePots(prev, potCount, potCapacities));
  }, [potCount, potCapacities]);

  useEffect(() => {
    return () => {
      if (createPhotoPreview) URL.revokeObjectURL(createPhotoPreview);
    };
  }, [createPhotoPreview]);

  function picksFromMode(m: PlacementMode): TeamPick[] {
    if (m === 'manual') {
      return manualSlots.filter((s): s is TeamPick => s != null);
    }
    if (m === 'random') {
      return poolSlots.filter((s): s is TeamPick => s != null);
    }
    return potSlots.flat();
  }

  /** Prefer the active mode; if it’s empty, keep the fullest roster from any mode. */
  function picksForSwitch(): TeamPick[] {
    const current = picksFromMode(mode);
    if (current.length > 0) return current;
    const manual = manualSlots.filter((s): s is TeamPick => s != null);
    const pool = poolSlots.filter((s): s is TeamPick => s != null);
    const pots = potSlots.flat();
    let best = manual;
    if (pool.length > best.length) best = pool;
    if (pots.length > best.length) best = pots;
    return best;
  }

  function slotsFromPicks(picks: TeamPick[]): (TeamPick | null)[] {
    const next = emptySlots(capacity);
    picks.slice(0, capacity).forEach((pick, i) => {
      next[i] = pick;
    });
    return next;
  }

  function potsFromPicks(picks: TeamPick[]): TeamPick[][] {
    return distributeToPots(picks, potCount, potCapacities);
  }

  function syncAllModes(picks: TeamPick[]) {
    const slots = slotsFromPicks(picks);
    setManualSlots(slots);
    setPoolSlots(slots.map((slot) => (slot ? { ...slot } : null)));
    setPotSlots(potsFromPicks(picks));
  }

  function switchMode(next: PlacementMode) {
    if (next === mode) return;
    // Keep one shared roster across modes so an empty view can’t wipe teams.
    syncAllModes(picksForSwitch());
    setMode(next);
  }

  const allSlotsFilled = useMemo(() => {
    if (mode === 'manual') return manualSlots.every((s) => s != null);
    if (mode === 'random') return poolSlots.every((s) => s != null);
    return potSlots.reduce((n, b) => n + b.length, 0) === capacity;
  }, [mode, manualSlots, poolSlots, potSlots, capacity]);

  function openDraft(target: string) {
    setDraftTarget(target);
    setQuery('');
    setPickerTab('pick');
    setCreateName('');
    setCreatePhoto(null);
    if (createPhotoPreview) URL.revokeObjectURL(createPhotoPreview);
    setCreatePhotoPreview(null);
  }

  function closeDraft() {
    setDraftTarget(null);
    setQuery('');
    setPickerTab('pick');
    setCreateName('');
    setCreatePhoto(null);
    if (createPhotoPreview) URL.revokeObjectURL(createPhotoPreview);
    setCreatePhotoPreview(null);
  }

  function commitPick(pick: TeamPick) {
    if (!draftTarget) return;

    if (draftTarget.startsWith('manual:')) {
      const idx = parseInt(draftTarget.slice('manual:'.length), 10);
      setManualSlots((prev) =>
        prev.map((slot, i) => (i === idx ? pick : slot)),
      );
    } else if (draftTarget.startsWith('pool:')) {
      const idx = parseInt(draftTarget.slice('pool:'.length), 10);
      setPoolSlots((prev) =>
        prev.map((slot, i) => (i === idx ? pick : slot)),
      );
    } else if (draftTarget.startsWith('pot:')) {
      const potIdx = parseInt(draftTarget.slice('pot:'.length), 10);
      const cap = potCapacities[potIdx] ?? potSize;
      setPotSlots((prev) =>
        prev.map((bucket, i) => {
          if (i !== potIdx) return bucket;
          if (bucket.length >= cap) return bucket;
          return [...bucket, pick];
        }),
      );
    }
    closeDraft();
  }

  async function handleCreateTeam() {
    const name = createName.trim();
    if (!name) return;
    setCreateBusy(true);
    setSaveErr('');
    try {
      const fd = new FormData();
      fd.append('name', name);
      if (createPhoto) fd.append('photo', createPhoto);
      const { contestant } = await createChallengeTeamContestant(
        challengeId,
        fd,
      );
      setCatalog((prev) => {
        if (prev.some((c) => c.id === contestant.id)) return prev;
        return [...prev, contestant].sort((a, b) =>
          a.name.localeCompare(b.name),
        );
      });
      commitPick(pickFromCatalog(contestant));
    } catch (err) {
      setSaveErr(
        err instanceof ApiError ? err.message : 'Could not create team.',
      );
    } finally {
      setCreateBusy(false);
    }
  }

  function clearManual(idx: number) {
    setManualSlots((prev) => prev.map((slot, i) => (i === idx ? null : slot)));
  }

  function reorderManual(fromIdx: number, toIdx: number) {
    if (fromIdx === toIdx || fromIdx < 0 || toIdx < 0) return;
    setManualSlots((prev) => {
      if (fromIdx >= prev.length || toIdx >= prev.length) return prev;
      const next = [...prev];
      const [item] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, item ?? null);
      return next;
    });
  }

  function clearPool(idx: number) {
    setPoolSlots((prev) => prev.map((slot, i) => (i === idx ? null : slot)));
  }

  function removeFromPot(potIdx: number, teamIdx: number) {
    setPotSlots((prev) =>
      prev.map((bucket, i) =>
        i === potIdx ? bucket.filter((_, j) => j !== teamIdx) : bucket,
      ),
    );
  }

  function renderFilled(
    pick: TeamPick,
    label: string | null,
    onClear: () => void,
    dragProps?: {
      dragHandle?: boolean;
      onDragStart?: (e: React.DragEvent) => void;
    },
  ) {
    return (
      <div className="ttp__filled">
        {dragProps?.dragHandle ? (
          <span
            className="ttp__drag"
            draggable={!busy}
            aria-label="Drag to reorder seed"
            title="Drag to reorder"
            onDragStart={dragProps.onDragStart}
          >
            <span className="ttp__drag-bar" aria-hidden />
            <span className="ttp__drag-bar" aria-hidden />
            <span className="ttp__drag-bar" aria-hidden />
          </span>
        ) : null}
        {label ? <span className="ttp__slot-label">{label}</span> : null}
        <ContestantAvatar
          displayName={pick.name}
          imageUrl={pick.photo_url ?? null}
          className="ttp__avatar"
          placeholderClassName="ttp__avatar ttp__avatar--ph"
        />
        <span className="ttp__filled-name">{pick.name}</span>
        <button
          type="button"
          className="ttp__clear"
          onClick={onClear}
          disabled={busy}
          aria-label={`Remove ${pick.name}`}
        >
          ×
        </button>
      </div>
    );
  }

  async function handleSaveManual(e: React.FormEvent) {
    e.preventDefault();
    setSaveErr('');
    if (manualSlots.some((slot) => !slot)) {
      setSaveErr('Add a team for every slot.');
      return;
    }
    const teams = manualSlots.map((slot, idx) => ({
      name: slot!.name,
      contestant_id: slot!.contestant_id,
      seed: idx + 1,
    }));
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

  async function handleStartTournament() {
    setSaveErr('');
    if (!allSlotsFilled) {
      setSaveErr('Add a team for every slot before starting.');
      return;
    }
    setBusy(true);
    try {
      let body: Parameters<typeof startChallengeTournament>[1];
      if (mode === 'manual') {
        body = {
          mode: 'manual',
          teams: manualSlots.map((slot, idx) => ({
            name: slot!.name,
            contestant_id: slot!.contestant_id,
            seed: idx + 1,
          })),
        };
      } else if (mode === 'random') {
        body = {
          mode: 'random',
          teams: poolSlots.map((slot) => ({
            name: slot!.name,
            contestant_id: slot!.contestant_id,
          })),
        };
      } else {
        const flat: Array<{
          name: string;
          pot: number;
          contestant_id: number;
        }> = [];
        potSlots.forEach((bucket, potIdx) => {
          bucket.forEach((slot) => {
            flat.push({
              name: slot.name,
              contestant_id: slot.contestant_id,
              pot: potIdx + 1,
            });
          });
        });
        body = { mode: 'random_balanced', teams: flat };
      }
      const meta = await startChallengeTournament(challengeId, body);
      applyMeta(meta);
      onStarted();
    } catch (err) {
      setSaveErr(
        err instanceof ApiError ? err.message : 'Could not start tournament.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleDraw() {
    setSaveErr('');
    let teams: Array<{
      name: string;
      pot?: number;
      contestant_id: number;
    }>;
    if (mode === 'random') {
      if (poolSlots.some((slot) => !slot)) {
        setSaveErr('Add a team for every slot before drawing.');
        return;
      }
      teams = poolSlots.map((slot) => ({
        name: slot!.name,
        contestant_id: slot!.contestant_id,
      }));
    } else {
      const flat: Array<{
        name: string;
        pot: number;
        contestant_id: number;
      }> = [];
      potSlots.forEach((bucket, potIdx) => {
        bucket.forEach((slot) => {
          flat.push({
            name: slot.name,
            contestant_id: slot.contestant_id,
            pot: potIdx + 1,
          });
        });
      });
      if (flat.length !== capacity) {
        setSaveErr(
          useByePots
            ? `Fill both pots (${byeCount} bye, ${playInCount} round 1) before drawing.`
            : `Fill every pot (${potSize} teams each) before drawing.`,
        );
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
            onClick={() => switchMode(value)}
            disabled={busy}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'random_balanced' && !useByePots ? (
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
                      const pick = manualSlots[idx] ?? null;
                      const label = `${g.code}${((seed - 1) % (teamsPerGroup ?? 1)) + 1}`;
                      return (
                        <li key={seed}>
                          {pick ? (
                            renderFilled(pick, label, () => clearManual(idx))
                          ) : (
                            <button
                              type="button"
                              className="ttp__empty"
                              onClick={() => openDraft(`manual:${idx}`)}
                              disabled={busy}
                            >
                              <span className="ttp__slot-label">{label}</span>
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
            <ul className="ttp__slots ttp__slots--seeds">
              {manualSlots.map((pick, idx) => (
                <Fragment key={idx}>
                  {byeCount > 0 && idx === byeCount ? (
                    <li className="ttp__seed-divider" aria-hidden>
                      <span className="ttp__seed-divider-line" />
                      <span className="ttp__seed-divider-label">Round 1</span>
                      <span className="ttp__seed-divider-line" />
                    </li>
                  ) : null}
                  <li
                    className="ttp__seed-row"
                    onDragOver={(e) => {
                      if (busy) return;
                      e.preventDefault();
                      e.dataTransfer.dropEffect = 'move';
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (busy) return;
                      const raw = e.dataTransfer.getData('text/plain');
                      const fromIdx = parseInt(raw, 10);
                      if (!Number.isFinite(fromIdx)) return;
                      reorderManual(fromIdx, idx);
                    }}
                  >
                    {pick ? (
                      renderFilled(
                        pick,
                        String(idx + 1),
                        () => clearManual(idx),
                        {
                          dragHandle: true,
                          onDragStart: (e) => {
                            e.dataTransfer.setData('text/plain', String(idx));
                            e.dataTransfer.effectAllowed = 'move';
                          },
                        },
                      )
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
                </Fragment>
              ))}
            </ul>
          )}
          {saveErr ? (
            <div className="alert alert--error" role="status">
              {saveErr}
            </div>
          ) : null}
          <div className="ttp__actions">
            <button type="submit" className="btn btn--primary" disabled={busy}>
              {busy ? 'Saving…' : 'Save Teams'}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !allSlotsFilled}
              onClick={() => void handleStartTournament()}
            >
              {busy ? 'Starting…' : 'Start Tournament'}
            </button>
          </div>
        </form>
      ) : null}

      {mode === 'random' ? (
        <div className="ttp__draw-block">
          <ul className="ttp__slots ttp__slots--flat">
            {poolSlots.map((pick, idx) => (
              <li key={idx}>
                {pick ? (
                  renderFilled(pick, String(idx + 1), () => clearPool(idx))
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
          <div className="ttp__actions">
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !allSlotsFilled}
              onClick={() => void handleDraw()}
            >
              {busy ? 'Drawing…' : 'Draw'}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !allSlotsFilled}
              onClick={() => void handleStartTournament()}
            >
              {busy ? 'Starting…' : 'Start Tournament'}
            </button>
          </div>
        </div>
      ) : null}

      {mode === 'random_balanced' ? (
        <div className="ttp__draw-block">
          <div className="ttp__pots">
            {potSlots.map((bucket, potIdx) => {
              const cap = potCapacities[potIdx] ?? potSize;
              const title = useByePots
                ? potIdx === 0
                  ? 'Bye'
                  : 'Round 1'
                : `Pot ${potIdx + 1}`;
              return (
                <div key={potIdx} className="ttp__box">
                  <h3 className="ttp__box-title">
                    {title}
                    <span className="ttp__box-cap">
                      {bucket.length}/{cap}
                    </span>
                  </h3>
                  <ul className="ttp__slots">
                    {bucket.map((pick, teamIdx) => (
                      <li key={`${pick.contestant_id}-${teamIdx}`}>
                        {renderFilled(pick, null, () =>
                          removeFromPot(potIdx, teamIdx),
                        )}
                      </li>
                    ))}
                    {Array.from({
                      length: Math.max(0, cap - bucket.length),
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
              );
            })}
          </div>
          {saveErr ? (
            <div className="alert alert--error" role="status">
              {saveErr}
            </div>
          ) : null}
          <div className="ttp__actions">
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !allSlotsFilled}
              onClick={() => void handleDraw()}
            >
              {busy ? 'Drawing…' : 'Draw'}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !allSlotsFilled}
              onClick={() => void handleStartTournament()}
            >
              {busy ? 'Starting…' : 'Start Tournament'}
            </button>
          </div>
        </div>
      ) : null}

      {draftTarget ? (
        <div
          className="ttp__draft-backdrop"
          role="presentation"
          onClick={closeDraft}
        >
          <div
            className="ttp__draft ttp__draft--picker"
            role="dialog"
            aria-modal="true"
            aria-label="Add team"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="ttp__draft-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={pickerTab === 'pick'}
                className={
                  pickerTab === 'pick'
                    ? 'ttp__draft-tab ttp__draft-tab--on'
                    : 'ttp__draft-tab'
                }
                onClick={() => setPickerTab('pick')}
              >
                Pick
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={pickerTab === 'create'}
                className={
                  pickerTab === 'create'
                    ? 'ttp__draft-tab ttp__draft-tab--on'
                    : 'ttp__draft-tab'
                }
                onClick={() => setPickerTab('create')}
              >
                Create
              </button>
            </div>

            {pickerTab === 'pick' ? (
              <>
                <input
                  type="search"
                  className="input"
                  placeholder="Search by name…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  autoFocus
                />
                {filterTags.length > 0 ? (
                  <div className="ttp__tag-filters" role="group" aria-label="Tags">
                    <span className="ttp__tag-filters-label">Tags</span>
                    <div className="ttp__tag-filters-list">
                      {filterTags.map((t) => {
                        const on = tagIds.includes(t.id);
                        return (
                          <button
                            key={t.id}
                            type="button"
                            className={
                              on
                                ? 'ttp__tag-chip ttp__tag-chip--on'
                                : 'ttp__tag-chip'
                            }
                            aria-pressed={on}
                            onClick={() =>
                              setTagIds((prev) =>
                                prev.includes(t.id)
                                  ? prev.filter((id) => id !== t.id)
                                  : [...prev, t.id],
                              )
                            }
                          >
                            {t.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
                <div className="seeder-picker__list">
                  {available.length === 0 ? (
                    <p className="field__hint">No matching teams.</p>
                  ) : (
                    available.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        className="seeder-picker__item"
                        onClick={() => commitPick(pickFromCatalog(c))}
                      >
                        <ContestantAvatar
                          displayName={c.name}
                          imageUrl={contestantImage(c)}
                          className="seeder-picker__avatar"
                          placeholderClassName="seeder-picker__avatar seeder-picker__avatar--ph"
                        />
                        <span className="seeder-picker__name">{c.name}</span>
                        {c.tags.length > 0 ? (
                          <span className="seeder-picker__item-tags">
                            {c.tags.map((t) => t.name).join(', ')}
                          </span>
                        ) : null}
                      </button>
                    ))
                  )}
                </div>
              </>
            ) : (
              <div className="ttp__create">
                <div className="field">
                  <label htmlFor="ttp-create-name">Name</label>
                  <input
                    id="ttp-create-name"
                    className="input"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    maxLength={100}
                    autoFocus
                  />
                </div>
                <div className="field">
                  <label htmlFor="ttp-create-photo">Photo</label>
                  <input
                    id="ttp-create-photo"
                    type="file"
                    accept="image/*"
                    onChange={(e) => {
                      const file = e.target.files?.[0] ?? null;
                      if (createPhotoPreview) {
                        URL.revokeObjectURL(createPhotoPreview);
                      }
                      setCreatePhoto(file);
                      setCreatePhotoPreview(
                        file ? URL.createObjectURL(file) : null,
                      );
                    }}
                  />
                  {createPhotoPreview ? (
                    <img
                      className="ttp__create-preview"
                      src={createPhotoPreview}
                      alt=""
                    />
                  ) : null}
                </div>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={createBusy || !createName.trim()}
                  onClick={() => void handleCreateTeam()}
                >
                  {createBusy ? 'Creating…' : 'Create Team'}
                </button>
              </div>
            )}

            <div className="ttp__draft-actions">
              <button
                type="button"
                className="btn btn--ghost"
                onClick={closeDraft}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export { divisorsForPots };
