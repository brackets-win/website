import { useMemo, useState } from 'react';

import type { ContestantCatalog, ContestantTagInfo } from '../../utils/api';
import { ContestantAvatar } from '../bracket/ContestantAvatar';

import './BracketSeeder.css';
import './GroupRosterAssigner.css';

export type GroupRosterSlot = {
  groupCode: string;
  slot: number;
  seed: number;
  label: string;
};

/** Contiguous seed chunks → group slots (same order as ``bracket_groups_preview``). */
export function buildGroupRosterSlots(
  numGroups: number,
  teamsPerGroup: number,
): GroupRosterSlot[] {
  if (numGroups < 1 || teamsPerGroup < 1) return [];
  const out: GroupRosterSlot[] = [];
  for (let g = 0; g < numGroups; g++) {
    const code = String.fromCharCode(65 + g);
    for (let slot = 1; slot <= teamsPerGroup; slot++) {
      const seed = g * teamsPerGroup + slot;
      out.push({
        groupCode: code,
        slot,
        seed,
        label: `${code}${slot}`,
      });
    }
  }
  return out;
}

type Props = {
  numGroups: number;
  teamsPerGroup: number;
  contestants: ContestantCatalog[];
  tags: ContestantTagInfo[];
  assignmentBySeed: Map<number, number>;
  onAssign: (seed: number, contestantId: number | null) => void;
  disabled?: boolean;
  readOnly?: boolean;
};

function contestantImage(c: ContestantCatalog): string | null {
  return c.photo_url ?? c.image_url ?? null;
}

function matchesFilter(
  c: ContestantCatalog,
  query: string,
  tagIds: number[],
): boolean {
  if (query) {
    const q = query.toLowerCase();
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
}

export function GroupRosterAssigner({
  numGroups,
  teamsPerGroup,
  contestants,
  tags,
  assignmentBySeed,
  onAssign,
  disabled = false,
  readOnly = false,
}: Props) {
  const [pickingSeed, setPickingSeed] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [tagIds, setTagIds] = useState<number[]>([]);

  const slots = useMemo(
    () => buildGroupRosterSlots(numGroups, teamsPerGroup),
    [numGroups, teamsPerGroup],
  );

  const byGroup = useMemo(() => {
    const map = new Map<string, GroupRosterSlot[]>();
    for (const s of slots) {
      const list = map.get(s.groupCode) ?? [];
      list.push(s);
      map.set(s.groupCode, list);
    }
    return map;
  }, [slots]);

  const contestantById = useMemo(() => {
    const map = new Map<number, ContestantCatalog>();
    for (const c of contestants) map.set(c.id, c);
    return map;
  }, [contestants]);

  const assignedIds = useMemo(
    () => new Set(assignmentBySeed.values()),
    [assignmentBySeed],
  );

  const available = useMemo(() => {
    return contestants.filter((c) => {
      if (!matchesFilter(c, query.trim(), tagIds)) return false;
      const current =
        pickingSeed != null ? assignmentBySeed.get(pickingSeed) : undefined;
      if (assignedIds.has(c.id) && c.id !== current) return false;
      return true;
    });
  }, [contestants, query, tagIds, assignedIds, assignmentBySeed, pickingSeed]);

  const pickingLabel =
    pickingSeed != null
      ? (slots.find((s) => s.seed === pickingSeed)?.label ?? `Seed ${pickingSeed}`)
      : '';

  function closePicker() {
    setPickingSeed(null);
    setQuery('');
    setTagIds([]);
  }

  function toggleTag(id: number) {
    setTagIds((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id],
    );
  }

  if (slots.length === 0) {
    return (
      <p className="field__hint">
        Set the number of groups and contestants to place teams.
      </p>
    );
  }

  return (
    <div className="group-roster">
      <div className="group-roster__grid">
        {[...byGroup.entries()].map(([code, groupSlots]) => (
          <section key={code} className="group-roster__card">
            <h4 className="group-roster__title">Group {code}</h4>
            <div className="group-roster__slots">
              {groupSlots.map((s) => {
                const assignedId = assignmentBySeed.get(s.seed);
                const assigned =
                  assignedId != null
                    ? contestantById.get(assignedId)
                    : undefined;
                if (!assigned) {
                  if (readOnly) {
                    return (
                      <div
                        key={s.seed}
                        className="seeder-slot seeder-slot--empty seeder-slot--readonly"
                      >
                        <span className="seeder-slot__seed">{s.label}</span>
                        <span className="seeder-slot__add">Empty</span>
                      </div>
                    );
                  }
                  return (
                    <button
                      key={s.seed}
                      type="button"
                      className="seeder-slot seeder-slot--empty"
                      onClick={() => setPickingSeed(s.seed)}
                      disabled={disabled}
                    >
                      <span className="seeder-slot__seed">{s.label}</span>
                      <span className="seeder-slot__add">+ Add team</span>
                    </button>
                  );
                }
                return (
                  <div
                    key={s.seed}
                    className="seeder-slot seeder-slot--filled"
                  >
                    <span className="seeder-slot__seed">{s.label}</span>
                    <ContestantAvatar
                      displayName={assigned.name}
                      imageUrl={contestantImage(assigned)}
                      className="seeder-slot__avatar"
                      placeholderClassName="seeder-slot__avatar seeder-slot__avatar--ph"
                    />
                    {readOnly ? (
                      <span className="seeder-slot__name-btn">{assigned.name}</span>
                    ) : (
                      <button
                        type="button"
                        className="seeder-slot__name-btn"
                        onClick={() => setPickingSeed(s.seed)}
                        title="Change team"
                        disabled={disabled}
                      >
                        {assigned.name}
                      </button>
                    )}
                    {!readOnly ? (
                      <button
                        type="button"
                        className="seeder-slot__remove"
                        aria-label={`Remove ${assigned.name} from ${s.label}`}
                        onClick={() => onAssign(s.seed, null)}
                        disabled={disabled}
                      >
                        ×
                      </button>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      {pickingSeed != null ? (
        <div
          className="seeder-picker-backdrop"
          role="presentation"
          onClick={closePicker}
        >
          <div
            className="seeder-picker card"
            role="dialog"
            aria-modal="true"
            aria-label={`Choose team for ${pickingLabel}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="seeder-picker__head">
              <h3 className="seeder-picker__title">{pickingLabel}</h3>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={closePicker}
              >
                Close
              </button>
            </div>
            <input
              type="search"
              className="input"
              placeholder="Search by name…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
            {tags.length > 0 ? (
              <div className="seeder-picker__tags">
                {tags.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`seeder-tag${
                      tagIds.includes(t.id) ? ' seeder-tag--on' : ''
                    }`}
                    onClick={() => toggleTag(t.id)}
                  >
                    {t.name}
                  </button>
                ))}
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
                    onClick={() => {
                      onAssign(pickingSeed, c.id);
                      closePicker();
                    }}
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
          </div>
        </div>
      ) : null}
    </div>
  );
}
