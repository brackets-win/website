import { useEffect, useMemo, useState } from 'react';
import type { BracketDetail, MatchupInfo, UserBracketDetail } from '../../utils/api';
import { ApiError, updateBracketOutcomeWeights } from '../../utils/api';
import {
  currentRoundUndecidedMatchups,
  getOutcomeWeightsFromMetadata,
  remainingKnockoutTeams,
  savedPriorRoundMatchups,
} from '../../utils/outcomeWeights';
import './SetOutcomeWeightsModal.css';

type Props = {
  bracket: BracketDetail;
  detail: UserBracketDetail;
  onClose: () => void;
  onSaved: (bracket: BracketDetail) => void;
};

function parseRank(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 1) return null;
  return Math.trunc(parsed);
}

function parseOdds(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) return null;
  return Math.round(parsed * 10) / 10;
}

function MatchupCard({
  matchup,
  rankings,
  odds,
  onRankingChange,
  onOddsChange,
  readOnlyOdds = false,
}: {
  matchup: MatchupInfo;
  rankings: Record<string, string>;
  odds: string;
  onRankingChange: (teamId: number, value: string) => void;
  onOddsChange?: (value: string) => void;
  readOnlyOdds?: boolean;
}) {
  const c1 = matchup.contestant1;
  const c2 = matchup.contestant2;
  if (!c1 || !c2) return null;

  const c1Odds = parseOdds(odds);
  const c2Odds =
    c1Odds != null ? Math.round((100 - c1Odds) * 10) / 10 : null;

  return (
    <article
      className={[
        'set-odds-card',
        readOnlyOdds ? 'set-odds-card--saved' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="set-odds-card__teams">
        <div className="set-odds-team">
          <div className="set-odds-team__meta">
            <span className="set-odds-team__name">{c1.display_name}</span>
            {!readOnlyOdds ? (
              <label className="set-odds-field">
                <span>Ranking</span>
                <input
                  className="input set-odds-field__input"
                  inputMode="numeric"
                  value={rankings[String(c1.id)] ?? ''}
                  onChange={(event) =>
                    onRankingChange(c1.id, event.target.value)
                  }
                />
              </label>
            ) : null}
          </div>
        </div>
        <div className="set-odds-card__vs">vs</div>
        <div className="set-odds-team">
          <div className="set-odds-team__meta">
            <span className="set-odds-team__name">{c2.display_name}</span>
            {!readOnlyOdds ? (
              <label className="set-odds-field">
                <span>Ranking</span>
                <input
                  className="input set-odds-field__input"
                  inputMode="numeric"
                  value={rankings[String(c2.id)] ?? ''}
                  onChange={(event) =>
                    onRankingChange(c2.id, event.target.value)
                  }
                />
              </label>
            ) : null}
          </div>
        </div>
      </div>
      <div className="set-odds-field set-odds-field--matchup">
        <span>
          {readOnlyOdds
            ? 'Saved odds'
            : `Odds (${c1.display_name} win %)`}
        </span>
        {readOnlyOdds ? (
          <p className="set-odds-saved-odds">
            {c1.display_name}: {odds}% · {c2.display_name}:{' '}
            {c2Odds != null ? `${c2Odds}%` : '—'}
          </p>
        ) : (
          <>
            <input
              className="input set-odds-field__input"
              inputMode="decimal"
              value={odds}
              onChange={(event) => onOddsChange?.(event.target.value)}
            />
            {c2Odds != null ? (
              <span className="set-odds-field__hint">
                {c2.display_name}: {c2Odds}%
              </span>
            ) : null}
          </>
        )}
      </div>
    </article>
  );
}

export function SetOutcomeWeightsModal({
  bracket,
  detail,
  onClose,
  onSaved,
}: Props) {
  const currentMatchups = useMemo(
    () => currentRoundUndecidedMatchups(bracket, detail),
    [bracket, detail],
  );
  const priorMatchups = useMemo(
    () => savedPriorRoundMatchups(bracket, detail),
    [bracket, detail],
  );
  const remainingTeams = useMemo(
    () => remainingKnockoutTeams(bracket, detail),
    [bracket, detail],
  );

  const [rankings, setRankings] = useState<Record<string, string>>({});
  const [matchupOdds, setMatchupOdds] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const saved = getOutcomeWeightsFromMetadata(bracket.metadata);
    const nextRankings: Record<string, string> = {};
    for (const team of remainingTeams) {
      const savedRank = saved.team_rankings[String(team.id)];
      nextRankings[String(team.id)] =
        savedRank != null ? String(savedRank) : '';
    }
    const nextOdds: Record<string, string> = {};
    for (const matchup of currentMatchups) {
      const savedOdds = saved.matchup_odds[String(matchup.id)];
      nextOdds[String(matchup.id)] =
        savedOdds != null ? String(savedOdds) : '';
    }
    setRankings(nextRankings);
    setMatchupOdds(nextOdds);
  }, [bracket.metadata, currentMatchups, remainingTeams]);

  const onRankingChange = (teamId: number, value: string) => {
    setRankings((current) => ({ ...current, [String(teamId)]: value }));
  };

  const onOddsChange = (matchupId: number, value: string) => {
    setMatchupOdds((current) => ({
      ...current,
      [String(matchupId)]: value,
    }));
  };

  const handleSave = async () => {
    setError(null);
    const saved = getOutcomeWeightsFromMetadata(bracket.metadata);

    const team_rankings: Record<string, number> = { ...saved.team_rankings };
    for (const team of remainingTeams) {
      const rank = parseRank(rankings[String(team.id)] ?? '');
      if (rank == null) {
        setError(`Set a ranking for ${team.display_name}.`);
        return;
      }
      team_rankings[String(team.id)] = rank;
    }

    const matchup_odds: Record<string, number> = { ...saved.matchup_odds };
    for (const matchup of currentMatchups) {
      const raw = matchupOdds[String(matchup.id)] ?? '';
      if (!raw.trim()) continue;
      const pct = parseOdds(raw);
      if (pct == null) {
        setError('Odds must be between 0 and 100.');
        return;
      }
      matchup_odds[String(matchup.id)] = pct;
    }

    setBusy(true);
    try {
      const { bracket: updated } = await updateBracketOutcomeWeights(
        bracket.id,
        { team_rankings, matchup_odds },
      );
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : 'Could not save odds.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="delete-dialog-backdrop"
      onClick={() => {
        if (!busy) onClose();
      }}
    >
      <div
        className="delete-dialog set-odds-dialog card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="set-odds-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="set-odds-dialog-title" className="set-odds-dialog__title">
          Set Odds
        </h2>
        <p className="set-odds-dialog__intro">
          Rankings and saved round odds shape later rounds until new odds are
          set.
        </p>
        {priorMatchups.length > 0 ? (
          <section className="set-odds-dialog__section">
            <h3 className="set-odds-dialog__section-title">Saved Round Odds</h3>
            <div className="set-odds-dialog__cards">
              {priorMatchups.map(({ matchup, odds }) => (
                <MatchupCard
                  key={matchup.id}
                  matchup={matchup}
                  rankings={rankings}
                  odds={String(odds)}
                  onRankingChange={onRankingChange}
                  readOnlyOdds
                />
              ))}
            </div>
          </section>
        ) : null}
        {currentMatchups.length > 0 ? (
          <section className="set-odds-dialog__section">
            <h3 className="set-odds-dialog__section-title">Current Round</h3>
            <div className="set-odds-dialog__cards">
              {currentMatchups.map((matchup) => (
                <MatchupCard
                  key={matchup.id}
                  matchup={matchup}
                  rankings={rankings}
                  odds={matchupOdds[String(matchup.id)] ?? ''}
                  onRankingChange={onRankingChange}
                  onOddsChange={(value) => onOddsChange(matchup.id, value)}
                />
              ))}
            </div>
          </section>
        ) : null}
        {error ? <p className="alert alert--error">{error}</p> : null}
        <div className="delete-dialog__actions">
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy || remainingTeams.length === 0}
            onClick={() => void handleSave()}
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
