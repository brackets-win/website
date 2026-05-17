import { useCallback, useEffect, useMemo, useState } from 'react';
import type {
  BracketContestantInfo,
  BracketGroupPreview,
  BracketStageInfo,
} from '../../utils/api';
import { ApiError, patchUserBracketMetadata } from '../../utils/api';

type Meta = {
  group_positions: Record<string, Record<string, number | null | undefined>>;
  third_place_advancers: number[];
};

const ORD = ['1', '2', '3'] as const;
const WC_GROUPS_PER_SHELF = 3;

type DragPayload = {
  contestantId: number;
  from: { type: 'slot'; groupCode: string; slot: string } | { type: 'pool'; groupCode: string } | { type: 'third' };
};

function parseDrag(e: React.DragEvent): DragPayload | null {
  const raw = e.dataTransfer.getData('application/json');
  if (!raw) return null;
  try {
    return JSON.parse(raw) as DragPayload;
  } catch {
    return null;
  }
}

function stripContestant(
  gp: Meta['group_positions'],
  ids: number,
  tp: number[],
): { gp: Meta['group_positions']; tp: number[] } {
  const nextGp: Meta['group_positions'] = { ...gp };
  for (const code of Object.keys(nextGp)) {
    const row = { ...nextGp[code] };
    for (const k of Object.keys(row)) {
      if (row[k] === ids) row[k] = null;
    }
    nextGp[code] = row;
  }
  return { gp: nextGp, tp: tp.filter((x) => x !== ids) };
}

function chunkGroups<T>(items: T[], size: number): T[][] {
  const shelves: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    shelves.push(items.slice(i, i + size));
  }
  return shelves;
}

type Props = {
  userBracketId: number;
  groups: BracketGroupPreview[];
  groupStage: BracketStageInfo;
  isWorldCup: boolean;
  initialMetadata: Meta;
  busy: boolean;
  readOnly?: boolean;
  onSaved: () => Promise<void>;
  onError: (msg: string) => void;
  setBusy: (b: boolean) => void;
};

export function GroupStagePanel({
  userBracketId,
  groups,
  groupStage,
  isWorldCup,
  initialMetadata,
  busy,
  readOnly = false,
  onSaved,
  onError,
  setBusy,
}: Props) {
  const gInfo = groupStage.group;
  const numSlots = isWorldCup
    ? 3
    : Math.max(1, gInfo?.contestants_qualifying_per_group ?? 2);

  const [gp, setGp] = useState<Meta['group_positions']>({});
  const [tp, setTp] = useState<number[]>([]);

  useEffect(() => {
    setGp(initialMetadata.group_positions ?? {});
    setTp(initialMetadata.third_place_advancers ?? []);
  }, [initialMetadata, userBracketId]);

  const byId = useMemo(() => {
    const m = new Map<number, BracketContestantInfo>();
    for (const g of groups) {
      for (const t of g.teams) m.set(t.id, t);
    }
    return m;
  }, [groups]);

  const shelves = useMemo(
    () =>
      isWorldCup
        ? chunkGroups(groups, WC_GROUPS_PER_SHELF)
        : [groups],
    [groups, isWorldCup],
  );

  const save = useCallback(
    async (nextGp: Meta['group_positions'], nextTp: number[]) => {
      if (readOnly) return;
      setBusy(true);
      onError('');
      try {
        await patchUserBracketMetadata(userBracketId, {
          group_positions: nextGp,
          ...(isWorldCup ? { third_place_advancers: nextTp } : {}),
        });
        setGp(nextGp);
        if (isWorldCup) setTp(nextTp);
        await onSaved();
      } catch (e) {
        onError(
          e instanceof ApiError ? e.message : 'Could not save group picks.',
        );
      } finally {
        setBusy(false);
      }
    },
    [userBracketId, isWorldCup, onSaved, onError, setBusy, readOnly],
  );

  const onDragStart = useCallback(
    (e: React.DragEvent, payload: DragPayload) => {
      if (readOnly) return;
      e.dataTransfer.setData('application/json', JSON.stringify(payload));
      e.dataTransfer.effectAllowed = 'move';
    },
    [],
  );

  const placeInSlot = useCallback(
    async (groupCode: string, slot: string, contestantId: number) => {
      let { gp: g1, tp: t1 } = stripContestant(gp, contestantId, tp);
      const row = { ...g1[groupCode] };
      const displaced = row[slot] ?? null;
      row[slot] = contestantId;
      g1 = { ...g1, [groupCode]: row };
      if (displaced && displaced !== contestantId) {
        const r2 = stripContestant(g1, displaced, t1);
        g1 = r2.gp;
        t1 = r2.tp;
      }
      await save(g1, t1);
    },
    [gp, tp, save],
  );

  const onDropSlot = useCallback(
    (e: React.DragEvent, groupCode: string, slot: string) => {
      e.preventDefault();
      const p = parseDrag(e);
      if (!p) return;
      void placeInSlot(groupCode, slot, p.contestantId);
    },
    [placeInSlot],
  );

  const onDropPool = useCallback(
    (e: React.DragEvent, _groupCode: string) => {
      e.preventDefault();
      const p = parseDrag(e);
      if (!p) return;
      void (async () => {
        let { gp: g1, tp: t1 } = stripContestant(gp, p.contestantId, tp);
        await save(g1, t1);
      })();
    },
    [gp, tp, save],
  );

  const onDropThirdSlot = useCallback(
    (e: React.DragEvent, index: number) => {
      e.preventDefault();
      if (!isWorldCup) return;
      const p = parseDrag(e);
      if (!p) return;
      const id = p.contestantId;
      const thirdInGp = Object.values(gp).some(
        (row) => row?.['3'] === id || row?.[3] === id,
      );
      if (!thirdInGp) {
        onError('Place the team third in a group before adding here.');
        return;
      }
      void (async () => {
        let next = [...tp];
        const prevIdx = next.indexOf(id);
        if (prevIdx >= 0) next.splice(prevIdx, 1);
        if (next.length >= 8 && prevIdx < 0) {
          onError('Remove a team before adding another.');
          return;
        }
        const idx = Math.min(index, next.length);
        next.splice(idx, 0, id);
        next = next.slice(0, 8);
        await save(gp, next);
      })();
    },
    [gp, tp, save, isWorldCup, onError],
  );

  const removeFromThird = useCallback(
    async (id: number) => {
      await save(gp, tp.filter((x) => x !== id));
    },
    [gp, tp, save],
  );

  const labelForSlot = (i: number) =>
    i === 0 ? '1st' : i === 1 ? '2nd' : '3rd';

  const renderGroupCard = (g: BracketGroupPreview) => {
    const positions = gp[g.code] ?? {};
    const taken = new Set<number>();
    for (let i = 0; i < numSlots; i++) {
      const k = ORD[i];
      const id = positions[k];
      if (id != null) taken.add(id);
    }
    const poolTeams = g.teams.filter((t) => !taken.has(t.id));

    return (
      <div
        key={g.code}
        className={isWorldCup ? 'bf-g-card bf-g-card--wc' : 'bf-g-card'}
      >
        <div className="bf-g-card-head">Group {g.code}</div>
        <div className="bf-g-slots">
          {Array.from({ length: numSlots }, (_, i) => {
            const k = ORD[i];
            const cid = positions[k] ?? null;
            const c = cid != null ? byId.get(cid) : null;
            return (
              <div
                key={k}
                className="bf-g-slot"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => onDropSlot(e, g.code, k)}
              >
                <span className="bf-g-slot-label">{labelForSlot(i)}</span>
                {c ? (
                  <button
                    type="button"
                    draggable={!busy}
                    className="bf-chip bf-g-chip"
                    onDragStart={(e) =>
                      onDragStart(e, {
                        contestantId: c.id,
                        from: { type: 'slot', groupCode: g.code, slot: k },
                      })
                    }
                    disabled={busy}
                  >
                    {c.display_name}
                    {c.seed != null ? (
                      <span className="bf-g-seed">#{c.seed}</span>
                    ) : null}
                  </button>
                ) : (
                  <span className="bf-slot bf-slot--empty bf-g-placeholder">
                    Drop here
                  </span>
                )}
              </div>
            );
          })}
        </div>
        <div
          className="bf-g-pool"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => onDropPool(e, g.code)}
        >
          <span className="bf-g-pool-label">Unassigned</span>
          <div className="bf-g-pool-chips">
            {poolTeams.map((t) => (
              <button
                key={t.id}
                type="button"
                draggable={!busy}
                className="bf-chip bf-g-chip bf-g-chip--muted"
                onDragStart={(e) =>
                  onDragStart(e, {
                    contestantId: t.id,
                    from: { type: 'pool', groupCode: g.code },
                  })
                }
                disabled={busy}
              >
                {t.display_name}
                {t.seed != null ? (
                  <span className="bf-g-seed">#{t.seed}</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  };

  const thirdPlaceRail = isWorldCup ? (
    <aside className="bf-g-third-rail" aria-label="Third-place qualifiers">
      <p className="bf-g-third-rail-head">Best 3rd place</p>
      <p className="bf-g-third-rail-sub">Pick 8 to advance</p>
      <div className="bf-g-third-rail-slots">
        {Array.from({ length: 8 }, (_, index) => {
          const id = tp[index];
          const c = id != null ? byId.get(id) : null;
          return (
            <div
              key={index}
              className="bf-g-third-cell bf-g-third-cell--rail"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => onDropThirdSlot(e, index)}
            >
              <span className="bf-g-third-idx">{index + 1}</span>
              {c ? (
                <div className="bf-g-third-pill">
                  <span>{c.display_name}</span>
                  <button
                    type="button"
                    className="bf-pick-clear"
                    disabled={busy}
                    onClick={() => void removeFromThird(c.id)}
                    aria-label="Remove from list"
                  >
                    ×
                  </button>
                </div>
              ) : (
                <span className="bf-g-third-empty">Drop 3rd</span>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  ) : null;

  const groupBody = isWorldCup ? (
    <div className="bf-g-wc-body">
      <div className="bf-g-shelves">
        {shelves.map((shelf, shelfIdx) => (
          <div key={shelfIdx} className="bf-g-shelf">
            {shelf.map((g) => renderGroupCard(g))}
          </div>
        ))}
      </div>
      {thirdPlaceRail}
    </div>
  ) : (
    <div className="bf-g-grid">{groups.map((g) => renderGroupCard(g))}</div>
  );

  return (
    <div className={isWorldCup ? 'bf-g bf-g--wc' : 'bf-g'}>
      <p className="bf-g-hint">
        Drag teams into finishing order ({numSlots} per group
        {isWorldCup ? ', then choose 8 third-place teams' : ''}).
      </p>
      {groupBody}
    </div>
  );
}
