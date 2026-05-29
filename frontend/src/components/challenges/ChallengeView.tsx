import { useCallback, useEffect, useRef, useState } from 'react';

import { BracketFill } from '../bracket/BracketFill';
import { DeleteConfirmDialog } from '../admin/DeleteConfirmDialog';
import {
  ApiError,
  deleteChallenge,
  getChallenge,
  updateChallenge,
  getChallengeLeaderboard,
  getChallengeStats,
  joinChallenge,
  type ApiUser,
  type ChallengeStats,
  type ChallengeSummary,
  type LeaderboardColumn,
  type LeaderboardEntry,
} from '../../utils/api';
import {
  INSTANCE_BRACKET_CHALLENGE,
  INSTANCE_POLL,
  INSTANCE_TOURNAMENT,
} from '../../utils/challengeTypes';
import {
  challengeThemeClass,
  themeKeyForInstanceType,
} from '../../utils/challengeThemes';
import { formatDeadlineEst } from '../../utils/est';

import { ChallengeLeaderboard } from './ChallengeLeaderboard';
import { ChallengeStats as ChallengeStatsPanel } from './ChallengeStats';
import { CopyJoinCode } from './CopyJoinCode';
import { TournamentTeamsPanel } from './TournamentTeamsPanel';
import './challengeThemes.css';
import './ChallengeView.css';

export type ChallengeTab =
  | 'bracket'
  | 'teams'
  | 'official'
  | 'leaderboard'
  | 'stats'
  | 'settings';

type Props = {
  challengeId: number;
  userBracketId?: number | null;
  initialTab?: ChallengeTab;
  currentUser: ApiUser;
  onBack: () => void;
  onSubmitted: () => void;
};

export function ChallengeView({
  challengeId,
  userBracketId,
  initialTab,
  currentUser,
  onBack,
  onSubmitted,
}: Props) {
  const [challenge, setChallenge] = useState<ChallengeSummary | null>(null);
  const [columns, setColumns] = useState<LeaderboardColumn[]>([]);
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [stats, setStats] = useState<ChallengeStats | null>(null);
  const [loadErr, setLoadErr] = useState('');
  const [tab, setTab] = useState<ChallengeTab>(initialTab ?? 'bracket');
  const [viewingPlayer, setViewingPlayer] = useState<{
    userBracketId: number;
    name: string;
  } | null>(null);
  const [activeBracketId, setActiveBracketId] = useState<number | null>(
    userBracketId ?? null,
  );
  const [addEntryName, setAddEntryName] = useState('');
  const [addEntryBusy, setAddEntryBusy] = useState(false);
  const [addEntryErr, setAddEntryErr] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteErr, setDeleteErr] = useState('');
  const [maxEntriesDraft, setMaxEntriesDraft] = useState('1');
  const [maxEntriesBusy, setMaxEntriesBusy] = useState(false);
  const [maxEntriesErr, setMaxEntriesErr] = useState('');
  const [bracketRevision, setBracketRevision] = useState(0);
  const autoTeamsTabDone = useRef(false);

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const { challenge: c } = await getChallenge(challengeId);
      setChallenge(c);
      if (c.uses_prediction_leaderboard !== false) {
        const board = await getChallengeLeaderboard(challengeId);
        setColumns(board.columns);
        setEntries(board.entries);
        if (
          c.instance_type === INSTANCE_BRACKET_CHALLENGE &&
          c.can_view_peer_brackets
        ) {
          setStats(await getChallengeStats(challengeId));
        } else {
          setStats(null);
        }
      } else {
        setColumns([]);
        setEntries([]);
        setStats(null);
      }
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load challenge.',
      );
    }
  }, [challengeId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    autoTeamsTabDone.current = false;
  }, [challengeId]);

  const teamsNeedSetup =
    challenge?.instance_type === INSTANCE_TOURNAMENT &&
    challenge.can_manage_bracket === true &&
    challenge.teams_configured === false;

  useEffect(() => {
    if (!challenge || autoTeamsTabDone.current || initialTab != null) return;
    if (teamsNeedSetup) {
      setTab('teams');
      autoTeamsTabDone.current = true;
    }
  }, [challenge, teamsNeedSetup, initialTab]);

  function handleTeamsSaved() {
    void reload();
    setBracketRevision((n) => n + 1);
    setTab('bracket');
  }

  useEffect(() => {
    if (userBracketId != null) {
      setActiveBracketId(userBracketId);
    }
  }, [userBracketId, challengeId]);

  useEffect(() => {
    if (challenge) {
      setMaxEntriesDraft(String(challenge.max_entries));
      setMaxEntriesErr('');
    }
  }, [challenge?.id, challenge?.max_entries]);

  useEffect(() => {
    if (!challenge || challenge.can_view_peer_brackets) return;
    const showBoard = challenge.uses_prediction_leaderboard !== false;
    if (tab === 'stats') {
      setTab(showBoard ? 'leaderboard' : 'bracket');
    }
    if (viewingPlayer != null) {
      setViewingPlayer(null);
    }
  }, [challenge, tab, viewingPlayer]);

  useEffect(() => {
    if (!challenge) return;
    if (
      activeBracketId != null &&
      userEntries.some((e) => e.user_bracket_id === activeBracketId)
    ) {
      return;
    }
    const fallback =
      challenge.user_bracket_id ??
      userEntries[0]?.user_bracket_id ??
      null;
    setActiveBracketId(fallback);
  }, [challenge, activeBracketId]);

  async function handleAddEntry(e: React.FormEvent) {
    e.preventDefault();
    if (!challenge) return;
    const name = addEntryName.trim();
    if (!name) {
      setAddEntryErr('Enter a name for this entry.');
      return;
    }
    setAddEntryBusy(true);
    setAddEntryErr('');
    try {
      const { challenge: updated } = await joinChallenge({
        challenge_id: challenge.id,
        display_name: name,
      });
      setChallenge(updated);
      setActiveBracketId(updated.user_bracket_id);
      setAddEntryName('');
    } catch (err) {
      setAddEntryErr(
        err instanceof ApiError ? err.message : 'Could not add entry.',
      );
    } finally {
      setAddEntryBusy(false);
    }
  }

  function handleSubmitted() {
    void reload();
    onSubmitted();
    setTab('bracket');
  }

  async function handleSaveMaxEntries(e: React.FormEvent) {
    e.preventDefault();
    if (!challenge) return;
    const value = Math.max(1, parseInt(maxEntriesDraft, 10) || 1);
    if (value === challenge.max_entries) return;
    setMaxEntriesBusy(true);
    setMaxEntriesErr('');
    try {
      const { challenge: updated } = await updateChallenge(challenge.id, {
        max_entries: value,
      });
      setChallenge(updated);
      setMaxEntriesDraft(String(updated.max_entries));
    } catch (err) {
      setMaxEntriesErr(
        err instanceof ApiError
          ? err.message
          : 'Could not update entry limit.',
      );
    } finally {
      setMaxEntriesBusy(false);
    }
  }

  async function handleDeleteChallenge() {
    setDeleteBusy(true);
    setDeleteErr('');
    try {
      await deleteChallenge(challengeId);
      setDeleteOpen(false);
      onBack();
    } catch (err) {
      setDeleteErr(
        err instanceof ApiError ? err.message : 'Could not delete challenge.',
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  if (loadErr && !challenge) {
    return (
      <div
        className={`${challengeThemeClass('bracket_challenge')} challenge-view`}
      >
        <div className="alert alert--error">{loadErr}</div>
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          ← My Challenges
        </button>
      </div>
    );
  }

  if (!challenge) {
    return (
      <div
        className={`${challengeThemeClass('bracket_challenge')} challenge-view`}
      >
        <p className="challenge-view__muted">Loading…</p>
      </div>
    );
  }

  const themeClass = challengeThemeClass(
    themeKeyForInstanceType(challenge.instance_type),
  );

  const userEntries = challenge.user_entries ?? [];

  const isTournament = challenge.instance_type === INSTANCE_TOURNAMENT;
  const isPoll = challenge.instance_type === INSTANCE_POLL;
  const isBracketChallenge =
    challenge.instance_type === INSTANCE_BRACKET_CHALLENGE;

  const masterId = challenge.master_user_bracket_id ?? null;
  const primaryBracketId = isTournament
    ? masterId
    : activeBracketId ?? challenge.user_bracket_id;

  const canEditResults = isTournament && challenge.can_manage_bracket === true;
  const showTeamsTab = canEditResults;
  const tournamentTeamCount = challenge.tournament_team_count ?? 0;

  const headerSubtitle = (() => {
    const title = challenge.name.trim();
    const bracket = challenge.bracket_name.trim();
    if (bracket && bracket.toLowerCase() !== title.toLowerCase()) {
      return bracket;
    }
    if (isTournament && tournamentTeamCount > 0) {
      const label = tournamentTeamCount === 1 ? 'team' : 'teams';
      return `${tournamentTeamCount} ${label}`;
    }
    return null;
  })();

  const showOwnScoring =
    isBracketChallenge &&
    primaryBracketId != null &&
    tab === 'bracket' &&
    viewingPlayer == null;

  const showEntrySwitcher =
    isBracketChallenge &&
    !isTournament &&
    (userEntries.length > 1 || challenge.can_add_entry);

  const bracketTabLabel = isPoll
    ? 'Vote'
    : isTournament
      ? 'Bracket'
      : 'My Bracket';

  const showLeaderboard = challenge.uses_prediction_leaderboard !== false;
  const canViewPeerBrackets = challenge.can_view_peer_brackets === true;
  const showOfficial =
    isBracketChallenge && masterId != null && !isTournament;

  if (primaryBracketId == null && !isTournament) {
    return (
      <div className={`${themeClass} challenge-view`}>
        <p className="challenge-view__muted">No bracket linked yet.</p>
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          ← My Challenges
        </button>
      </div>
    );
  }

  return (
    <div className={`${themeClass} challenge-view`}>
      <button
        type="button"
        className="btn btn--ghost challenge-view__back"
        onClick={onBack}
      >
        ← My Challenges
      </button>

      <header className="challenge-view__head card">
        <div className="challenge-view__head-inner">
          {challenge.bracket_image_url ? (
            <img
              className="challenge-view__bracket-img"
              src={challenge.bracket_image_url}
              alt=""
            />
          ) : (
            <span className="challenge-view__bracket-img challenge-view__bracket-img--ph">
              {challenge.bracket_name.charAt(0)}
            </span>
          )}
          <div>
            <p className="challenge-view__type">
              {challenge.instance_type_label ?? challenge.instance_type}
            </p>
            <h1>{challenge.name}</h1>
            {headerSubtitle ? (
              <p className="challenge-view__meta">{headerSubtitle}</p>
            ) : null}
            {isBracketChallenge && challenge.submission_deadline ? (
              <p className="challenge-view__deadline">
                Submit by{' '}
                <strong>{formatDeadlineEst(challenge.submission_deadline)}</strong>
              </p>
            ) : null}
            {isBracketChallenge && challenge.deadline_passed ? (
              <p className="challenge-view__status challenge-view__status--closed">
                Submissions closed
              </p>
            ) : challenge.is_submitted && isBracketChallenge ? (
              <p className="challenge-view__status challenge-view__status--ok">
                Bracket submitted
              </p>
            ) : null}
          </div>
        </div>
      </header>

      {showEntrySwitcher && !viewingPlayer ? (
        <section className="challenge-view__entries card">
          {userEntries.length > 0 ? (
            <div
              className="challenge-view__entry-tabs"
              role="tablist"
              aria-label="Your entries"
            >
              {userEntries.map((entry) => (
                <button
                  key={entry.user_bracket_id}
                  type="button"
                  role="tab"
                  aria-selected={activeBracketId === entry.user_bracket_id}
                  className={
                    activeBracketId === entry.user_bracket_id
                      ? 'challenge-view__entry-tab challenge-view__entry-tab--active'
                      : 'challenge-view__entry-tab'
                  }
                  onClick={() => setActiveBracketId(entry.user_bracket_id)}
                >
                  {entry.display_name || 'Entry'}
                  {entry.is_submitted ? ' ✓' : ''}
                </button>
              ))}
            </div>
          ) : null}
          {challenge.can_add_entry ? (
            <form
              className="challenge-view__add-entry"
              onSubmit={(e) => void handleAddEntry(e)}
            >
              <label htmlFor="add-entry-name" className="challenge-view__add-entry-label">
                {challenge.entry_count > 0 ? 'Add another entry' : 'Your name'}
              </label>
              <div className="challenge-view__add-entry-row">
                <input
                  id="add-entry-name"
                  className="input"
                  value={addEntryName}
                  onChange={(e) => setAddEntryName(e.target.value)}
                  placeholder="Name on the leaderboard"
                  maxLength={80}
                  disabled={addEntryBusy}
                  required
                />
                <button
                  type="submit"
                  className="btn btn--secondary"
                  disabled={addEntryBusy}
                >
                  {addEntryBusy ? 'Adding…' : 'Add Entry'}
                </button>
              </div>
              <p className="challenge-view__entry-limit">
                {challenge.entry_count} of {challenge.max_entries} entries used
              </p>
              {addEntryErr ? (
                <p className="challenge-view__add-entry-err">{addEntryErr}</p>
              ) : null}
            </form>
          ) : (
            <p className="challenge-view__entry-limit">
              {challenge.entry_count} of {challenge.max_entries} entries used
            </p>
          )}
        </section>
      ) : null}

      <nav className="challenge-view__tabs" aria-label="Challenge sections">
        {showLeaderboard ? (
          <button
            type="button"
            className={
              tab === 'leaderboard'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => setTab('leaderboard')}
          >
            Leaderboard
          </button>
        ) : null}
        {showOfficial ? (
          <button
            type="button"
            className={
              tab === 'official'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => setTab('official')}
          >
            {challenge.bracket_name}
          </button>
        ) : null}
        {showTeamsTab ? (
          <button
            type="button"
            className={
              tab === 'teams'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => setTab('teams')}
          >
            Teams
          </button>
        ) : null}
        {primaryBracketId != null ? (
          <button
            type="button"
            className={
              tab === 'bracket'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => setTab('bracket')}
          >
            {bracketTabLabel}
          </button>
        ) : null}
        {showLeaderboard && isBracketChallenge && canViewPeerBrackets ? (
          <button
            type="button"
            className={
              tab === 'stats'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => setTab('stats')}
          >
            Stats
          </button>
        ) : null}
        <button
          type="button"
          className={
            tab === 'settings'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => setTab('settings')}
        >
          Settings
        </button>
      </nav>

      {viewingPlayer ? (
        <section className="challenge-view__player-bracket card">
          <div className="challenge-view__player-bracket-head">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setViewingPlayer(null)}
            >
              ← Leaderboard
            </button>
            <h2 className="challenge-view__player-bracket-title">
              {viewingPlayer.name}
            </h2>
          </div>
          <BracketFill
            userBracketId={viewingPlayer.userBracketId}
            readOnly
            showSubmit={false}
            showScoringHighlights={isBracketChallenge}
          />
        </section>
      ) : null}

      {!viewingPlayer && tab === 'teams' && showTeamsTab ? (
        <section className="card challenge-view__settings challenge-view__teams-panel">
          <h2 className="challenge-view__settings-heading">Teams</h2>
          {tournamentTeamCount > 0 ? (
            <TournamentTeamsPanel
              challengeId={challengeId}
              teamCount={tournamentTeamCount}
              onSaved={handleTeamsSaved}
            />
          ) : (
            <p className="challenge-view__muted">Unable to load team slots.</p>
          )}
        </section>
      ) : null}

      {!viewingPlayer && tab === 'bracket' && primaryBracketId != null ? (
        <BracketFill
          key={`${primaryBracketId}-${bracketRevision}`}
          userBracketId={primaryBracketId}
          readOnly={isTournament ? !canEditResults : false}
          allowMasterEdit={canEditResults}
          allowMasterView={isTournament}
          showScoringHighlights={showOwnScoring}
          showSubmit={isBracketChallenge && !isTournament}
          onSubmitted={handleSubmitted}
        />
      ) : null}

      {!viewingPlayer && tab === 'official' && masterId != null ? (
        <section className="challenge-view__official">
          <BracketFill
            userBracketId={masterId}
            allowMasterView
            readOnly
            showSubmit={false}
          />
        </section>
      ) : null}

      {!viewingPlayer && tab === 'leaderboard' && showLeaderboard ? (
        <section className="card challenge-view__board">
          {!canViewPeerBrackets && isBracketChallenge ? (
            <p className="challenge-view__muted challenge-view__peer-gate">
              Submit your bracket to view other players&apos; brackets.
            </p>
          ) : null}
          <ChallengeLeaderboard
            columns={columns}
            entries={entries}
            viewerUsername={currentUser.username}
            onSelectPlayer={
              canViewPeerBrackets
                ? (id, name) => {
                    setViewingPlayer({ userBracketId: id, name });
                  }
                : undefined
            }
          />
        </section>
      ) : null}

      {!viewingPlayer && tab === 'stats' && showLeaderboard && isBracketChallenge ? (
        <section className="card challenge-view__stats">
          {stats ? (
            <ChallengeStatsPanel stats={stats} />
          ) : (
            <p className="challenge-view__muted">Loading…</p>
          )}
        </section>
      ) : null}

      {!viewingPlayer && tab === 'settings' ? (
        <section className="card challenge-view__settings">
          {challenge.is_private && challenge.join_code ? (
            <CopyJoinCode code={challenge.join_code} />
          ) : (
            <p className="challenge-view__muted">
              This challenge is public. Anyone can join from the public list.
            </p>
          )}
          {challenge.is_creator && isBracketChallenge ? (
            <form
              className="challenge-view__settings-form"
              onSubmit={(e) => void handleSaveMaxEntries(e)}
            >
              <h2 className="challenge-view__settings-heading">
                Entries per person
              </h2>
              <p className="challenge-view__muted">
                How many brackets each player may submit.
              </p>
              <div className="field">
                <label htmlFor="challenge-max-entries">Maximum entries</label>
                <input
                  id="challenge-max-entries"
                  className="input"
                  type="number"
                  min={challenge.max_entries_minimum ?? 1}
                  max={50}
                  value={maxEntriesDraft}
                  onChange={(e) => setMaxEntriesDraft(e.target.value)}
                  disabled={maxEntriesBusy}
                />
              </div>
              {maxEntriesErr ? (
                <div className="alert alert--error" role="status">
                  {maxEntriesErr}
                </div>
              ) : null}
              <button
                type="submit"
                className="btn btn--primary"
                disabled={
                  maxEntriesBusy ||
                  parseInt(maxEntriesDraft, 10) === challenge.max_entries
                }
              >
                {maxEntriesBusy ? 'Saving…' : 'Save'}
              </button>
            </form>
          ) : null}
          {challenge.is_creator ? (
            <div className="challenge-view__danger">
              <h2 className="challenge-view__danger-title">Delete Challenge</h2>
              <p className="challenge-view__muted">
                Permanently remove this challenge and all entries. This cannot be
                undone.
              </p>
              {deleteErr ? (
                <div className="alert alert--error" role="status">
                  {deleteErr}
                </div>
              ) : null}
              <button
                type="button"
                className="btn btn--danger"
                onClick={() => {
                  setDeleteErr('');
                  setDeleteOpen(true);
                }}
              >
                Delete Challenge
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      <DeleteConfirmDialog
        open={deleteOpen}
        title="Delete Challenge?"
        label={challenge?.name ?? ''}
        intro={
          challenge
            ? `“${challenge.name}” will be permanently removed along with all player entries.`
            : undefined
        }
        busy={deleteBusy}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => void handleDeleteChallenge()}
      />
    </div>
  );
}
