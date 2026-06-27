import { useMemo, useState } from 'react';

import type { ContestantCatalog, ContestantTagInfo } from '../../utils/api';
import { ContestantAvatar } from '../bracket/ContestantAvatar';

import { firstRoundSeedGames, isPowerOfTwo } from './bracketAdminHelpers';
import './BracketSeeder.css';

type Props = {
  open: boolean;
  title: string;
  numContestants: number;
  contestants: ContestantCatalog[];
  tags: ContestantTagInfo[];
  assignmentBySeed: Map<number, number>;
  onAssign: (seed: number, contestantId: number | null) => void;
  onClose: () => void;
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
  if (tagIds.length > 0) {
    const has = c.tags.some((t) => tagIds.includes(t.id));
    if (!has) return false;
  }
  return true;
}

export function BracketSeeder({
  open,
  title,
  numContestants,
  contestants,
  tags,
  assignmentBySeed,
  onAssign,
  onClose,
}: Props) {
  const [pickingSeed, setPickingSeed] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [tagIds, setTagIds] = useState<number[]>([]);

  const games = useMemo(
    () => firstRoundSeedGames(numContestants),
    [numContestants],
  );

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
      // Allow the contestant already in the slot being edited.
      const current =
        pickingSeed != null ? assignmentBySeed.get(pickingSeed) : undefined;
      if (assignedIds.has(c.id) && c.id !== current) return false;
      return true;
    });
  }, [contestants, query, tagIds, assignedIds, assignmentBySeed, pickingSeed]);

  if (!open) return null;

  const placedCount = assignmentBySeed.size;

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

  function renderSlot(seed: number | null) {
    if (seed == null) {
      return <div className="seeder-slot seeder-slot--bye">Bye</div>;
    }
    const assignedId = assignmentBySeed.get(seed);
    const assigned =
      assignedId != null ? contestantById.get(assignedId) : undefined;
    return (
      <div
        className={`seeder-slot${assigned ? ' seeder-slot--filled' : ''}`}
      >
        <span className="seeder-slot__seed">{seed}</span>
        {assigned ? (
          <>
            <ContestantAvatar
              displayName={assigned.name}
              imageUrl={contestantImage(assigned)}
              className="seeder-slot__avatar"
              placeholderClassName="seeder-slot__avatar seeder-slot__avatar--ph"
            />
            <span className="seeder-slot__name">{assigned.name}</span>
            <button
              type="button"
              className="seeder-slot__btn seeder-slot__btn--edit"
              onClick={() => setPickingSeed(seed)}
            >
              Change
            </button>
            <button
              type="button"
              className="seeder-slot__btn seeder-slot__remove"
              aria-label={`Remove contestant from seed ${seed}`}
              onClick={() => onAssign(seed, null)}
            >
              ×
            </button>
          </>
        ) : (
          <button
            type="button"
            className="seeder-slot__add"
            onClick={() => setPickingSeed(seed)}
          >
            + Add
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="seeder-backdrop" role="presentation">
      <div
        className="seeder-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Seed bracket"
      >
        <header className="seeder-header">
          <button
            type="button"
            className="seeder-back"
            onClick={onClose}
            aria-label="Back to bracket form"
          >
            <span aria-hidden>←</span> Back
          </button>
          <h2 className="seeder-title">{title}</h2>
          <span className="seeder-count">
            {placedCount} / {numContestants} placed
          </span>
        </header>

        {!isPowerOfTwo(numContestants) ? (
          <p className="seeder-note">
            Standard bracket layout needs a power-of-two field (8, 16, 32…).
            Slots are paired in seed order below.
          </p>
        ) : null}

        <div className="seeder-board">
          {games.map((game) => (
            <div key={game.position} className="seeder-game">
              {renderSlot(game.topSeed)}
              {renderSlot(game.bottomSeed)}
            </div>
          ))}
        </div>
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
            aria-label={`Choose contestant for seed ${pickingSeed}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="seeder-picker__head">
              <h3 className="seeder-picker__title">
                Seed {pickingSeed}
              </h3>
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
                <p className="field__hint">No matching contestants.</p>
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
