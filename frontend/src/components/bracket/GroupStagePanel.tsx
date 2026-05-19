import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  BracketContestantInfo,
  BracketGroupPreview,
  BracketStageInfo,
} from '../../utils/api';
import { ApiError, patchUserBracketMetadata } from '../../utils/api';
import { thirdPlaceAdvanceCount } from '../../utils/groupStageConfig';

type Meta = {
  group_positions: Record<string, Record<string, number | null | undefined>>;
  third_place_advancers: number[];
};

const WC_GROUPS_PER_SHELF = 3;

/** Rank slot keys for a group — one per team in that group (from the API). */
function positionKeysForGroup(g: BracketGroupPreview): string[] {
  return Array.from({ length: g.teams.length }, (_, i) => String(i + 1));
}

type DragPayload = {
  contestantId: number;
  from:
    | { type: 'slot'; groupCode: string; slot: string }
    | { type: 'unplaced'; groupCode: string }
    | { type: 'third-candidate' }
    | { type: 'third-adv' };
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
  options?: { exceptGroupCode?: string },
): { gp: Meta['group_positions']; tp: number[] } {
  const nextGp: Meta['group_positions'] = { ...gp };
  for (const code of Object.keys(nextGp)) {
    if (code === options?.exceptGroupCode) continue;
    const row = { ...nextGp[code] };
    for (const k of Object.keys(row)) {
      if (row[k] === ids) row[k] = null;
    }
    nextGp[code] = row;
  }
  return { gp: nextGp, tp: tp.filter((x) => x !== ids) };
}

function orderedIds(
  keys: string[],
  row: Record<string, number | null | undefined>,
): (number | null)[] {
  return keys.map((k) => {
    const v = row[k];
    return v == null ? null : v;
  });
}

function rowFromOrdered(
  keys: string[],
  list: (number | null)[],
): Record<string, number | null> {
  const row: Record<string, number | null> = {};
  for (let i = 0; i < keys.length; i++) {
    row[keys[i]] = list[i] ?? null;
  }
  return row;
}

/** Reorder when dropping onto an already-filled rank (1→3 pushes 2→1, 3→2). */
function reorderTeamInGroup(
  keys: string[],
  row: Record<string, number | null | undefined>,
  contestantId: number,
  targetKey: string,
): Record<string, number | null> {
  if (row[targetKey] == null) {
    return placeInEmptySlot(keys, row, contestantId, targetKey);
  }

  const toIdx = keys.indexOf(targetKey);
  if (toIdx < 0) return { ...row } as Record<string, number | null>;

  const list = orderedIds(keys, row);
  const fromIdx = list.indexOf(contestantId);
  if (fromIdx < 0) {
    const next = { ...row } as Record<string, number | null>;
    for (const k of keys) {
      if (next[k] === contestantId) next[k] = null;
    }
    next[targetKey] = contestantId;
    return next;
  }
  list.splice(fromIdx, 1);
  list.splice(toIdx, 0, contestantId);
  return rowFromOrdered(keys, list);
}

/** Fill one empty rank only; other ranks stay put. */
function placeInEmptySlot(
  keys: string[],
  row: Record<string, number | null | undefined>,
  contestantId: number,
  targetKey: string,
): Record<string, number | null> {
  const next = { ...row } as Record<string, number | null>;
  for (const k of keys) {
    if (next[k] === contestantId) next[k] = null;
  }
  next[targetKey] = contestantId;
  return next;
}

/** Place into a rank; empty targets never shift other teams. */
function placeInGroupSlot(
  keys: string[],
  row: Record<string, number | null | undefined>,
  contestantId: number,
  targetKey: string,
): Record<string, number | null> {
  if (row[targetKey] == null) {
    return placeInEmptySlot(keys, row, contestantId, targetKey);
  }
  return reorderTeamInGroup(keys, row, contestantId, targetKey);
}

function thirdIdsFromGp(gp: Meta['group_positions']): Set<number> {
  const ids = new Set<number>();
  for (const row of Object.values(gp)) {
    const t = row?.['3'];
    if (t != null) ids.add(t);
  }
  return ids;
}

function sanitizeThirdAdvancers(
  gp: Meta['group_positions'],
  tp: number[],
  maxCount: number,
): number[] {
  const allowed = thirdIdsFromGp(gp);
  return tp.filter((id) => allowed.has(id)).slice(0, maxCount);
}

function chunkGroups<T>(items: T[], size: number): T[][] {
  const shelves: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    shelves.push(items.slice(i, i + size));
  }
  return shelves;
}

function slotLabel(index: number): string {
  const n = index + 1;
  const mod100 = n % 100;
  const mod10 = n % 10;
  let suffix = 'th';
  if (mod100 < 11 || mod100 > 13) {
    if (mod10 === 1) suffix = 'st';
    else if (mod10 === 2) suffix = 'nd';
    else if (mod10 === 3) suffix = 'rd';
  }
  return `${n}${suffix}`;
}

function firstEmptySlot(
  keys: string[],
  positions: Record<string, number | null | undefined>,
): string | null {
  for (const k of keys) {
    if (positions[k] == null) return k;
  }
  return null;
}

/** When one team and one rank slot remain, place the team automatically. */
function autoFillGroup(
  g: BracketGroupPreview,
  gp: Meta['group_positions'],
): Meta['group_positions'] {
  const keys = positionKeysForGroup(g);
  const positions = { ...(gp[g.code] ?? {}) };
  const placed = new Set<number>();
  for (const k of keys) {
    const id = positions[k];
    if (id != null) placed.add(id);
  }
  const unplaced = g.teams.filter((t) => !placed.has(t.id));
  const emptySlots = keys.filter((k) => positions[k] == null);
  if (unplaced.length === 1 && emptySlots.length === 1) {
    return {
      ...gp,
      [g.code]: { ...positions, [emptySlots[0]]: unplaced[0].id },
    };
  }
  return gp;
}

function autoFillAllGroups(
  groups: BracketGroupPreview[],
  gp: Meta['group_positions'],
): Meta['group_positions'] {
  let next = gp;
  for (const g of groups) {
    next = autoFillGroup(g, next);
  }
  return next;
}

/** World Cup (and similar): one third-place advancer slot left, one candidate left. */
function autoFillThirdAdvancers(
  gp: Meta['group_positions'],
  tp: number[],
  advanceCount: number,
): number[] {
  const candidates = [...thirdIdsFromGp(gp)];
  const notSelected = candidates.filter((id) => !tp.includes(id));
  if (
    tp.length === advanceCount - 1 &&
    notSelected.length === 1 &&
    tp.length < advanceCount
  ) {
    return [...tp, notSelected[0]];
  }
  return tp;
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

type DragPreview = {
  groupCode: string;
  contestantId: number;
  overSlot: string;
};

function DragHandle({
  disabled,
  label,
  onDragStart,
  onDragEnd,
}: {
  disabled: boolean;
  label: string;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: (e: React.DragEvent) => void;
}) {
  return (
    <span
      className="bf-g-drag-handle"
      draggable={!disabled}
      aria-label={label}
      title={label}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
    >
      <span className="bf-g-drag-bar" aria-hidden />
      <span className="bf-g-drag-bar" aria-hidden />
      <span className="bf-g-drag-bar" aria-hidden />
    </span>
  );
}

function ContestantChip({
  contestant,
  reorderable,
  dragFromChip,
  busy,
  readOnly,
  muted,
  dragging,
  previewShift,
  onDragStart,
  onDragEnd,
  onClick,
  onClear,
  clearLabel,
}: {
  contestant: BracketContestantInfo;
  /** Show grip handle; drag starts from handle only. */
  reorderable?: boolean;
  /** Drag whole chip (third-place rail, etc.). */
  dragFromChip?: boolean;
  busy: boolean;
  readOnly: boolean;
  muted?: boolean;
  dragging?: boolean;
  previewShift?: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: (e: React.DragEvent) => void;
  onClick?: () => void;
  onClear?: () => void;
  clearLabel?: string;
}) {
  const canDrag = !busy && !readOnly;
  const chipDraggable = Boolean(dragFromChip && canDrag);
  const chipClass = [
    'bf-chip',
    'bf-g-chip',
    muted ? 'bf-g-chip--muted' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const shelfClass = [
    'bf-g-chip-shelf',
    dragging ? 'bf-g-chip-shelf--dragging' : '',
    previewShift ? 'bf-g-chip-shelf--preview-shift' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={shelfClass}>
      {reorderable ? (
        <DragHandle
          disabled={!canDrag}
          label="Drag to reorder"
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
        />
      ) : null}
      <button
        type="button"
        className={chipClass}
        draggable={chipDraggable}
        onDragStart={chipDraggable ? onDragStart : undefined}
        onDragEnd={chipDraggable ? onDragEnd : undefined}
        onClick={onClick}
        disabled={busy || readOnly}
      >
        {contestant.image_url ? (
          <img className="bf-g-chip-img" src={contestant.image_url} alt="" />
        ) : (
          <span className="bf-g-chip-img bf-g-chip-img--ph" aria-hidden>
            {contestant.display_name.charAt(0)}
          </span>
        )}
        <span className="bf-g-chip-name">{contestant.display_name}</span>
      </button>
      {onClear ? (
        <button
          type="button"
          className="bf-g-chip-clear"
          aria-label={clearLabel ?? 'Remove'}
          disabled={busy || readOnly}
          onPointerDown={(e) => {
            e.stopPropagation();
          }}
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            onClear();
          }}
        >
          ×
        </button>
      ) : null}
    </div>
  );
}

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
  const thirdAdvanceCount = thirdPlaceAdvanceCount(groupStage);
  const hasThirdPlaceRail = thirdAdvanceCount > 0;

  const [gp, setGp] = useState<Meta['group_positions']>({});
  const [tp, setTp] = useState<number[]>([]);
  const [dragPreview, setDragPreview] = useState<DragPreview | null>(null);
  const [activeDragId, setActiveDragId] = useState<number | null>(null);
  const gpRef = useRef(gp);
  const tpRef = useRef(tp);
  const dragPayloadRef = useRef<DragPayload | null>(null);
  const saveQueueRef = useRef(Promise.resolve());

  gpRef.current = gp;
  tpRef.current = tp;

  useEffect(() => {
    if (busy) return;
    const nextGp = initialMetadata.group_positions ?? {};
    const nextTp = sanitizeThirdAdvancers(
      nextGp,
      initialMetadata.third_place_advancers ?? [],
      thirdAdvanceCount,
    );
    setGp(nextGp);
    setTp(nextTp);
    gpRef.current = nextGp;
    tpRef.current = nextTp;
  }, [initialMetadata, userBracketId, busy, thirdAdvanceCount]);

  const byId = useMemo(() => {
    const m = new Map<number, BracketContestantInfo>();
    for (const g of groups) {
      for (const t of g.teams) m.set(t.id, t);
    }
    return m;
  }, [groups]);

  const groupByCode = useMemo(() => {
    const m = new Map<string, BracketGroupPreview>();
    for (const g of groups) m.set(g.code, g);
    return m;
  }, [groups]);

  const teamInGroup = useCallback(
    (groupCode: string, contestantId: number) => {
      const g = groupByCode.get(groupCode);
      return g?.teams.some((t) => t.id === contestantId) ?? false;
    },
    [groupByCode],
  );

  const thirdPlaceCandidateIds = useMemo(
    () => thirdIdsFromGp(gp),
    [gp],
  );

  const thirdPlaceCandidates = useMemo(() => {
    const selected = new Set(tp);
    return [...thirdPlaceCandidateIds]
      .filter((id) => !selected.has(id))
      .map((id) => byId.get(id))
      .filter((c): c is BracketContestantInfo => c != null);
  }, [thirdPlaceCandidateIds, byId, tp]);

  const shelves = useMemo(
    () =>
      isWorldCup
        ? chunkGroups(groups, WC_GROUPS_PER_SHELF)
        : [groups],
    [groups, isWorldCup],
  );

  const finalizePicks = useCallback(
    (
      nextGp: Meta['group_positions'],
      nextTp: number[],
      options?: { skipAutoFill?: boolean },
    ) => {
      let gpOut = options?.skipAutoFill
        ? nextGp
        : autoFillAllGroups(groups, nextGp);
      let tpOut = nextTp;
      if (hasThirdPlaceRail) {
        tpOut = autoFillThirdAdvancers(gpOut, tpOut, thirdAdvanceCount);
      }
      return { gp: gpOut, tp: tpOut };
    },
    [groups, hasThirdPlaceRail, thirdAdvanceCount],
  );

  const persist = useCallback(
    (
      nextGp: Meta['group_positions'],
      nextTp: number[],
      options?: { skipAutoFill?: boolean },
    ) => {
      const { gp: filledGp, tp: filledTp } = finalizePicks(
        nextGp,
        nextTp,
        options,
      );
      const safeTp = hasThirdPlaceRail
        ? sanitizeThirdAdvancers(filledGp, filledTp, thirdAdvanceCount)
        : filledTp;
      saveQueueRef.current = saveQueueRef.current.then(async () => {
        if (readOnly) return;
        setBusy(true);
        onError('');
        gpRef.current = filledGp;
        tpRef.current = safeTp;
        try {
          await patchUserBracketMetadata(userBracketId, {
            group_positions: filledGp,
            ...(hasThirdPlaceRail ? { third_place_advancers: safeTp } : {}),
          });
          setGp(filledGp);
          if (hasThirdPlaceRail) setTp(safeTp);
          await onSaved();
        } catch (e) {
          onError(
            e instanceof ApiError
              ? e.message
              : 'Could not save group picks.',
          );
          await onSaved();
        } finally {
          setBusy(false);
        }
      });
      return saveQueueRef.current;
    },
    [
      userBracketId,
      hasThirdPlaceRail,
      thirdAdvanceCount,
      onSaved,
      onError,
      setBusy,
      readOnly,
      finalizePicks,
    ],
  );

  const clearDrag = useCallback(() => {
    dragPayloadRef.current = null;
    setDragPreview(null);
    setActiveDragId(null);
  }, []);

  const onDragStart = useCallback(
    (e: React.DragEvent, payload: DragPayload) => {
      if (readOnly) return;
      dragPayloadRef.current = payload;
      setActiveDragId(payload.contestantId);
      e.dataTransfer.setData('application/json', JSON.stringify(payload));
      e.dataTransfer.effectAllowed = 'move';
    },
    [readOnly],
  );

  const onDragEnd = useCallback(() => {
    clearDrag();
  }, [clearDrag]);

  const canPreviewGroupDrag = useCallback(
    (groupCode: string, payload: DragPayload | null) => {
      if (!payload) return false;
      if (payload.from.type === 'third-adv' || payload.from.type === 'third-candidate') {
        return false;
      }
      if (
        (payload.from.type === 'slot' || payload.from.type === 'unplaced') &&
        payload.from.groupCode !== groupCode
      ) {
        return false;
      }
      return teamInGroup(groupCode, payload.contestantId);
    },
    [teamInGroup],
  );

  const updateDragPreview = useCallback(
    (groupCode: string, slot: string) => {
      const p = dragPayloadRef.current;
      if (!canPreviewGroupDrag(groupCode, p)) {
        setDragPreview(null);
        return;
      }
      setDragPreview({
        groupCode,
        contestantId: p!.contestantId,
        overSlot: slot,
      });
    },
    [canPreviewGroupDrag],
  );

  const placeInSlot = useCallback(
    (groupCode: string, slot: string, contestantId: number) => {
      clearDrag();
      const g = groupByCode.get(groupCode);
      if (!g || !teamInGroup(groupCode, contestantId)) return;
      const keys = positionKeysForGroup(g);
      const curGp = gpRef.current;
      const curTp = tpRef.current;
      const { gp: g1, tp: t1 } = stripContestant(curGp, contestantId, curTp, {
        exceptGroupCode: groupCode,
      });
      const nextRow = placeInGroupSlot(
        keys,
        g1[groupCode] ?? {},
        contestantId,
        slot,
      );
      void persist({ ...g1, [groupCode]: nextRow }, t1);
    },
    [persist, teamInGroup, groupByCode, clearDrag],
  );

  const clearSlot = useCallback(
    (groupCode: string, slot: string) => {
      const curGp = gpRef.current;
      const row = { ...(curGp[groupCode] ?? {}) };
      const removed = row[slot];
      if (removed == null) return;
      row[slot] = null;
      const g1 = { ...curGp, [groupCode]: row };
      const t1 = tpRef.current.filter((x) => x !== removed);
      void persist(g1, t1, { skipAutoFill: true });
    },
    [persist],
  );

  const placeInFirstEmpty = useCallback(
    (groupCode: string, contestantId: number) => {
      clearDrag();
      const g = groupByCode.get(groupCode);
      if (!g) return;
      const slot = firstEmptySlot(
        positionKeysForGroup(g),
        gpRef.current[groupCode] ?? {},
      );
      if (!slot) return;
      placeInSlot(groupCode, slot, contestantId);
    },
    [placeInSlot, groupByCode, clearDrag],
  );

  const onDropSlot = useCallback(
    (e: React.DragEvent, groupCode: string, slot: string) => {
      e.preventDefault();
      const p = parseDrag(e) ?? dragPayloadRef.current;
      clearDrag();
      if (!p) return;
      if (!teamInGroup(groupCode, p.contestantId)) return;
      if (p.from.type === 'third-adv' || p.from.type === 'third-candidate') {
        return;
      }
      if (
        (p.from.type === 'slot' || p.from.type === 'unplaced') &&
        p.from.groupCode !== groupCode
      ) {
        return;
      }
      placeInSlot(groupCode, slot, p.contestantId);
    },
    [placeInSlot, teamInGroup, clearDrag],
  );

  const addThirdAdvancer = useCallback(
    (contestantId: number, index?: number) => {
      if (!thirdIdsFromGp(gpRef.current).has(contestantId)) return;
      let next = [...tpRef.current];
      const prevIdx = next.indexOf(contestantId);
      if (prevIdx >= 0) next.splice(prevIdx, 1);
      if (next.length >= thirdAdvanceCount && prevIdx < 0) return;
      const idx =
        index != null ? Math.min(index, next.length) : next.length;
      next.splice(idx, 0, contestantId);
      void persist(gpRef.current, next.slice(0, thirdAdvanceCount));
    },
    [persist, thirdAdvanceCount],
  );

  const onDropThirdAdvSlot = useCallback(
    (e: React.DragEvent, index: number) => {
      e.preventDefault();
      if (!hasThirdPlaceRail) return;
      const p = parseDrag(e);
      if (!p) return;
      if (!thirdIdsFromGp(gpRef.current).has(p.contestantId)) return;
      addThirdAdvancer(p.contestantId, index);
    },
    [addThirdAdvancer, hasThirdPlaceRail],
  );

  const removeFromThird = useCallback(
    (id: number) => {
      void persist(gpRef.current, tpRef.current.filter((x) => x !== id));
    },
    [persist],
  );

  const renderThirdAdvSlot = (index: number) => {
    const id = tp[index];
    const c = id != null ? byId.get(id) : null;
    return (
      <div key={index} className="bf-g-third-cell bf-g-third-cell--rail">
        <span className="bf-g-third-idx">{index + 1}</span>
        {c ? (
          <ContestantChip
            contestant={c}
            dragFromChip
            busy={busy}
            readOnly={readOnly}
            onDragStart={(e) =>
              onDragStart(e, {
                contestantId: c.id,
                from: { type: 'third-adv' },
              })
            }
            onDragEnd={onDragEnd}
            clearLabel="Remove from list"
            onClear={() => removeFromThird(c.id)}
          />
        ) : (
          <div
            className="bf-g-drop-zone bf-g-drop-zone--third"
            onDragOver={(e) => {
              if (!readOnly) e.preventDefault();
            }}
            onDrop={(e) => onDropThirdAdvSlot(e, index)}
          />
        )}
      </div>
    );
  };

  const renderGroupCard = (g: BracketGroupPreview) => {
    const keys = positionKeysForGroup(g);
    const basePositions = gp[g.code] ?? {};
    const previewActive =
      activeDragId != null &&
      dragPreview != null &&
      dragPreview.groupCode === g.code;
    const displayPositions =
      previewActive && dragPreview
        ? placeInGroupSlot(
            keys,
            basePositions,
            dragPreview.contestantId,
            dragPreview.overSlot,
          )
        : basePositions;

    const placed = new Set<number>();
    for (const k of keys) {
      const id = displayPositions[k];
      if (id != null) placed.add(id);
    }
    const unplaced = g.teams.filter((t) => !placed.has(t.id));
    const draggingId = activeDragId;

    return (
      <div
        key={g.code}
        className={isWorldCup ? 'bf-g-card bf-g-card--wc' : 'bf-g-card'}
      >
        <div className="bf-g-card-head">Group {g.code}</div>
        <div
          className={`bf-g-slots${previewActive ? ' bf-g-slots--preview' : ''}`}
          onDragLeave={(e) => {
            if (e.currentTarget.contains(e.relatedTarget as Node)) return;
            if (dragPreview?.groupCode === g.code) setDragPreview(null);
          }}
        >
          {keys.map((k, i) => {
            const cid = displayPositions[k] ?? null;
            const c = cid != null ? byId.get(cid) : null;
            const isOver = previewActive && dragPreview?.overSlot === k;
            const baseCid = basePositions[k] ?? null;
            const previewShift =
              previewActive &&
              baseCid != null &&
              cid != null &&
              baseCid !== cid;

            return (
              <div
                key={k}
                className={[
                  'bf-g-slot',
                  isOver ? 'bf-g-slot--over' : '',
                  c ? 'bf-g-slot--filled' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onDragEnter={(e) => {
                  if (readOnly) return;
                  e.preventDefault();
                  updateDragPreview(g.code, k);
                }}
                onDragOver={(e) => {
                  if (readOnly) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = 'move';
                  updateDragPreview(g.code, k);
                }}
                onDrop={(e) => onDropSlot(e, g.code, k)}
              >
                <span className="bf-g-slot-label">{slotLabel(i)}</span>
                {c ? (
                  <ContestantChip
                    contestant={c}
                    reorderable
                    busy={busy}
                    readOnly={readOnly}
                    dragging={draggingId === c.id}
                    previewShift={previewShift}
                    onDragStart={(e) =>
                      onDragStart(e, {
                        contestantId: c.id,
                        from: { type: 'slot', groupCode: g.code, slot: k },
                      })
                    }
                    onDragEnd={onDragEnd}
                    clearLabel={`Remove from ${slotLabel(i)}`}
                    onClear={() => clearSlot(g.code, k)}
                  />
                ) : (
                  <div className="bf-g-drop-zone" />
                )}
              </div>
            );
          })}
        </div>
        {unplaced.length > 0 ? (
          <div className="bf-g-unplaced">
            {unplaced.map((t) => (
              <ContestantChip
                key={t.id}
                contestant={t}
                reorderable
                busy={busy}
                readOnly={readOnly}
                muted
                dragging={draggingId === t.id}
                onDragStart={(e) =>
                  onDragStart(e, {
                    contestantId: t.id,
                    from: { type: 'unplaced', groupCode: g.code },
                  })
                }
                onDragEnd={onDragEnd}
                onClick={() => {
                  if (readOnly || busy) return;
                  clearDrag();
                  placeInFirstEmpty(g.code, t.id);
                }}
              />
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  const thirdColSplit = Math.ceil(thirdAdvanceCount / 2);

  const thirdPlaceSection = hasThirdPlaceRail ? (
    <aside className="bf-g-third-rail" aria-label="Third-place qualifiers">
      <p className="bf-g-third-rail-head">Best 3rd place</p>
      <p className="bf-g-third-rail-sub">
        Pick {thirdAdvanceCount} to advance
      </p>
      {thirdPlaceCandidates.length > 0 ? (
        <div className="bf-g-third-candidates">
          {thirdPlaceCandidates.map((c) => (
              <ContestantChip
                key={c.id}
                contestant={c}
                dragFromChip
                busy={busy}
                readOnly={readOnly}
                muted
                onDragStart={(e) =>
                  onDragStart(e, {
                    contestantId: c.id,
                    from: { type: 'third-candidate' },
                  })
                }
                onDragEnd={onDragEnd}
                onClick={() => {
                  if (readOnly || busy) return;
                  addThirdAdvancer(c.id);
                }}
              />
            ))}
        </div>
      ) : null}
      <div className="bf-g-third-rail-slots bf-g-third-rail-slots--cols">
        <div className="bf-g-third-col">
          {Array.from({ length: thirdColSplit }, (_, i) =>
            renderThirdAdvSlot(i),
          )}
        </div>
        <div className="bf-g-third-col">
          {Array.from(
            { length: thirdAdvanceCount - thirdColSplit },
            (_, i) => renderThirdAdvSlot(i + thirdColSplit),
          )}
        </div>
      </div>
    </aside>
  ) : null;

  const groupBody = hasThirdPlaceRail ? (
    <div className="bf-g-wc-body">
      <div className="bf-g-shelves">
        {shelves.map((shelf, shelfIdx) => (
          <div key={shelfIdx} className="bf-g-shelf">
            {shelf.map((g) => renderGroupCard(g))}
          </div>
        ))}
      </div>
      {thirdPlaceSection}
    </div>
  ) : (
    <div className="bf-g-grid">{groups.map((g) => renderGroupCard(g))}</div>
  );

  return (
    <div className={isWorldCup ? 'bf-g bf-g--wc' : 'bf-g'}>
      {groupBody}
    </div>
  );
}
