import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import { BracketFill } from '../bracket/BracketFill';
import { DeleteConfirmDialog } from '../admin/DeleteConfirmDialog';
import {
  ApiError,
  deleteChallenge,
  getBracket,
  getChallenge,
  updateChallenge,
  getChallengeLeaderboard,
  getChallengeStats,
  joinChallenge,
  type ApiUser,
  type BracketDetail,
  type BracketStageInfo,
  type ChallengeStats,
  type ChallengeSummary,
  type LeaderboardColumn,
  type LeaderboardEntry,
} from '../../utils/api';
import { invalidateHome } from '../../utils/homeCache';
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
import {
  challengePath,
  challengePlayerPath,
  parseRouteId,
  type ChallengeTab,
} from '../../routes';

import { ChallengeLeaderboard } from './ChallengeLeaderboard';
import { ChallengeStats as ChallengeStatsPanel } from './ChallengeStats';
import { CopyJoinCode } from './CopyJoinCode';
import { TournamentTeamsPanel } from './TournamentTeamsPanel';
import './challengeThemes.css';
import './ChallengeView.css';

export type { ChallengeTab };

type Props = {
  challengeId: number;
  tab: ChallengeTab;
  viewingPlayerId?: number | null;
  currentUser: ApiUser;
};

function pointLabel(points: number): string {
  return `${points} ${points === 1 ? 'point' : 'points'}`;
}

function bracketScoringRules(bracket: BracketDetail | null): string[] {
  if (!bracket) return [];

  const stages = [...bracket.stages].sort((a, b) => a.order - b.order);
  const rules: string[] = [];

  stages.forEach((stage: BracketStageInfo) => {
    if (stage.stage_type === 'GROUP') {
      const exactPoints = stage.group?.points_per_exact_position ?? 0;
      if (exactPoints > 0) {
        rules.push(
          `${pointLabel(exactPoints)} for each exact correct group placement`,
        );
      }

      const advancerPoints = stage.group?.points_per_advancer ?? 0;
      if (advancerPoints > 0) {
        rules.push(
          `${pointLabel(advancerPoints)} for each team correctly advancing from ${stage.name}`,
        );
      }
      return;
    }

    if (stage.stage_type !== 'KNOCKOUT' || stage.knockout?.is_third_place) {
      return;
    }

    const points = stage.points_per_correct_pick ?? 0;
    if (points > 0) {
      rules.push(
        `${pointLabel(points)} for each team correctly placed in ${stage.name}`,
      );
    }
  });

  const thirdPlacePoints = bracket.points_third_place_winner ?? 0;
  if (bracket.has_third_place_match && thirdPlacePoints > 0) {
    rules.push(`${pointLabel(thirdPlacePoints)} for correct Third Place`);
  }

  const championPoints = bracket.points_champion ?? 0;
  if (championPoints > 0) {
    rules.push(`${pointLabel(championPoints)} for correct Champions`);
  }

  return rules;
}

export function ChallengeView({
  challengeId,
  tab,
  viewingPlayerId = null,
  currentUser,
}: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [challenge, setChallenge] = useState<ChallengeSummary | null>(null);
  const [bracketDef, setBracketDef] = useState<BracketDetail | null>(null);
  const [columns, setColumns] = useState<LeaderboardColumn[]>([]);
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [stats, setStats] = useState<ChallengeStats | null>(null);
  const [boardLoading, setBoardLoading] = useState(false);
  const [boardLoaded, setBoardLoaded] = useState(false);
  const boardFetchGen = useRef(0);
  const [boardErr, setBoardErr] = useState('');
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsErr, setStatsErr] = useState('');
  const statsFetchGen = useRef(0);
  const [loadErr, setLoadErr] = useState('');
  const entryFromUrl =
    parseRouteId(searchParams.get('entry')) ??
    parseRouteId(searchParams.get('ub'));
  const [activeBracketId, setActiveBracketId] = useState<number | null>(
    entryFromUrl,
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

  const playerNameFromState = (
    location.state as { playerName?: string } | null | undefined
  )?.playerName;

  const reload = useCallback(async () => {
    setLoadErr('');
    setBoardErr('');
    setBoardLoaded(false);
    boardFetchGen.current += 1;
    setStats(null);
    setStatsErr('');
    setStatsLoading(false);
    statsFetchGen.current += 1;
    try {
      const { challenge: c } = await getChallenge(challengeId);
      setChallenge(c);
      if (c.instance_type === INSTANCE_BRACKET_CHALLENGE) {
        const { bracket } = await getBracket(c.bracket_id);
        setBracketDef(bracket);
      } else {
        setBracketDef(null);
      }
      if (c.uses_prediction_leaderboard === false) {
        setColumns([]);
        setEntries([]);
      }
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load challenge.',
      );
    }
  }, [challengeId]);

  const viewingPlayer = useMemo(() => {
    if (viewingPlayerId == null) return null;
    const fromBoard = entries.find(
      (entry) => entry.user_bracket_id === viewingPlayerId,
    );
    return {
      userBracketId: viewingPlayerId,
      name:
        playerNameFromState ??
        fromBoard?.display_name?.trim() ??
        fromBoard?.username ??
        'Player',
    };
  }, [viewingPlayerId, entries, playerNameFromState]);

  const leaderboardColumns = useMemo(() => {
    if (!challenge?.show_live_group_results_note) return columns;
    return columns.filter((col) => col.key !== 'potential');
  }, [columns, challenge?.show_live_group_results_note]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (tab !== 'leaderboard') return;
    if (!challenge || challenge.uses_prediction_leaderboard === false) return;
    if (boardLoaded || boardLoading) return;

    const gen = boardFetchGen.current;
    setBoardLoading(true);
    setBoardErr('');
    void getChallengeLeaderboard(challengeId)
      .then((board) => {
        if (gen !== boardFetchGen.current) return;
        setColumns(board.columns);
        setEntries(board.entries);
        setBoardLoaded(true);
      })
      .catch((err) => {
        if (gen !== boardFetchGen.current) return;
        setBoardErr(
          err instanceof ApiError ? err.message : 'Unable to load leaderboard.',
        );
        setColumns([]);
        setEntries([]);
      })
      .finally(() => {
        if (gen !== boardFetchGen.current) return;
        setBoardLoading(false);
      });
  }, [tab, challenge, challengeId, boardLoaded, boardLoading]);

  useEffect(() => {
    if (tab !== 'stats') return;
    if (!challenge || challenge.instance_type !== INSTANCE_BRACKET_CHALLENGE) return;
    if (challenge.can_view_peer_brackets !== true) return;
    if (stats != null || statsLoading) return;

    const gen = statsFetchGen.current;
    setStatsLoading(true);
    setStatsErr('');
    void getChallengeStats(challengeId)
      .then((data) => {
        if (gen !== statsFetchGen.current) return;
        setStats(data);
      })
      .catch((e) => {
        if (gen !== statsFetchGen.current) return;
        setStatsErr(
          e instanceof ApiError ? e.message : 'Unable to load stats.',
        );
      })
      .finally(() => {
        if (gen !== statsFetchGen.current) return;
        setStatsLoading(false);
      });
  }, [tab, challenge, challengeId, stats, statsLoading]);

  useEffect(() => {
    autoTeamsTabDone.current = false;
  }, [challengeId]);

  const teamsNeedSetup =
    challenge?.instance_type === INSTANCE_TOURNAMENT &&
    challenge.can_manage_bracket === true &&
    challenge.teams_configured === false;

  useEffect(() => {
    if (!challenge || autoTeamsTabDone.current) return;
    if (teamsNeedSetup && tab !== 'teams') {
      autoTeamsTabDone.current = true;
      navigate(challengePath(challengeId, 'teams'), { replace: true });
    }
  }, [challenge, teamsNeedSetup, tab, navigate, challengeId]);

  function goToTab(nextTab: ChallengeTab) {
    navigate(
      challengePath(
        challengeId,
        nextTab,
        activeBracketId != null && nextTab === 'bracket'
          ? { entry: activeBracketId }
          : undefined,
      ),
    );
  }

  function selectEntry(entryId: number) {
    setActiveBracketId(entryId);
    const next = new URLSearchParams(searchParams);
    next.set('entry', String(entryId));
    next.delete('ub');
    setSearchParams(next, { replace: true });
  }

  function handleTeamsSaved() {
    void reload();
    setBracketRevision((n) => n + 1);
    goToTab('bracket');
  }

  useEffect(() => {
    if (entryFromUrl != null) {
      setActiveBracketId(entryFromUrl);
    }
  }, [entryFromUrl, challengeId]);

  useEffect(() => {
    if (challenge) {
      setMaxEntriesDraft(String(challenge.max_entries));
      setMaxEntriesErr('');
    }
  }, [challenge?.id, challenge?.max_entries]);

  useEffect(() => {
    if (!challenge || challenge.can_view_peer_brackets) return;
    if (viewingPlayerId != null) {
      navigate(challengePath(challengeId, 'leaderboard'), { replace: true });
    }
  }, [challenge, viewingPlayerId, navigate, challengeId]);

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
      invalidateHome('challenges');
      setChallenge(updated);
      if (updated.user_bracket_id != null) {
        selectEntry(updated.user_bracket_id);
      }
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
    invalidateHome('challenges');
    void reload();
    goToTab('bracket');
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
      invalidateHome('challenges');
      setDeleteOpen(false);
      navigate('/');
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
        <Link to="/" className="btn btn--ghost">
          ← My Challenges
        </Link>
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
  const scoringRules = isBracketChallenge
    ? bracketScoringRules(bracketDef)
    : [];
  const hasGroupStage =
    bracketDef?.stages.some((stage) => stage.stage_type === 'GROUP') === true;

  if (primaryBracketId == null && !isTournament) {
    return (
      <div className={`${themeClass} challenge-view`}>
        <p className="challenge-view__muted">No bracket linked yet.</p>
        <Link to="/" className="btn btn--ghost">
          ← My Challenges
        </Link>
      </div>
    );
  }

  return (
    <div className={`${themeClass} challenge-view`}>
      <Link to="/" className="btn btn--ghost challenge-view__back">
        ← My Challenges
      </Link>

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

      <nav className="challenge-view__tabs" aria-label="Challenge sections">
        {showLeaderboard ? (
          <button
            type="button"
            className={
              tab === 'leaderboard'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => goToTab('leaderboard')}
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
            onClick={() => goToTab('official')}
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
            onClick={() => goToTab('teams')}
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
            onClick={() => goToTab('bracket')}
          >
            {bracketTabLabel}
          </button>
        ) : null}
        {showLeaderboard && isBracketChallenge ? (
          <button
            type="button"
            className={
              tab === 'stats'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => goToTab('stats')}
          >
            Stats
          </button>
        ) : null}
        {isBracketChallenge ? (
          <button
            type="button"
            className={
              tab === 'rules'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => goToTab('rules')}
          >
            Rules
          </button>
        ) : null}
        <button
          type="button"
          className={
            tab === 'settings'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => goToTab('settings')}
        >
          Settings
        </button>
      </nav>

      {showEntrySwitcher && !viewingPlayer && tab === 'bracket' ? (
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
                  onClick={() => selectEntry(entry.user_bracket_id)}
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

      {!viewingPlayer &&
      tab === 'leaderboard' &&
      showLeaderboard &&
      isBracketChallenge &&
      challenge.show_live_group_results_note ? (
        <p className="challenge-view__live-note">
          Group stage results are not final. Bracket points are only projections
          that assume that group standings hold.
        </p>
      ) : null}

      {viewingPlayer ? (
        <section className="challenge-view__player-bracket card">
          <div className="challenge-view__player-bracket-head">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => goToTab('leaderboard')}
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
            columns={leaderboardColumns}
            entries={entries}
            loading={boardLoading}
            error={boardErr}
            viewerUsername={currentUser.username}
            onSelectPlayer={
              canViewPeerBrackets
                ? (id, name) => {
                    navigate(challengePlayerPath(challengeId, id), {
                      state: { playerName: name },
                    });
                  }
                : undefined
            }
          />
        </section>
      ) : null}

      {!viewingPlayer && tab === 'stats' && showLeaderboard && isBracketChallenge ? (
        <section className="card challenge-view__stats">
          {!canViewPeerBrackets ? (
            <p className="challenge-view__muted">
              Submit a bracket to view stats.
            </p>
          ) : statsLoading ? (
            <p className="challenge-view__muted">Loading…</p>
          ) : statsErr ? (
            <div className="alert alert--error" role="status">
              {statsErr}
            </div>
          ) : stats ? (
            <ChallengeStatsPanel stats={stats} />
          ) : null}
        </section>
      ) : null}

      {!viewingPlayer && tab === 'rules' && isBracketChallenge ? (
        <section className="card challenge-view__rules">
          <p>
            Win the challenge by predicting the most accurate bracket and earning
            the most points.
          </p>
          <ul className="challenge-view__rules-list">
            <li>Fill out and submit your bracket before the deadline.</li>
            <li>
              Follow the Leaderboard to see where you stand. Potential Points are
              the maximum possible points that your bracket can still reach.
              Potential Points will not show until any group phase points are
              confirmed.
            </li>
            {hasGroupStage ? (
              <li>
                If a competition is in its group phase, points will only be
                projections and not confirmed. They are the points that you would
                have if the current group standings held. Therefore, your points
                can go down during this period as actual group standings shuffle.
              </li>
            ) : null}
          </ul>
          {scoringRules.length > 0 ? (
            <>
              <h2 className="challenge-view__rules-heading">Bracket Scoring</h2>
              <ul className="challenge-view__rules-list">
                {scoringRules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
            </>
          ) : null}
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
