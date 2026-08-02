import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Trophy } from 'lucide-react';

import {
  ApiError,
  createChallenge,
  createStreakChallenge,
  createUserBracket,
  joinChallenge,
  joinStreakChallenge,
  updateChallenge,
  type ApiUser,
  type BracketSummary,
  type ChallengeSummary,
  type LeaderboardPreview,
  type LeaderboardPreviewEntry,
  type StreakChallengeSummary,
  type StreakCompetitionSummary,
  type TournamentFinalSummary,
} from '../../utils/api';
import { ContestantAvatar } from '../bracket/ContestantAvatar';
import {
  getHomeSnapshot,
  invalidateHome,
  refreshHome,
  subscribeHome,
  upsertHomeChallenge,
  upsertHomeStreakChallenge,
} from '../../utils/homeCache';
import {
  defaultChallengeTab,
  INSTANCE_BRACKET_CHALLENGE,
  INSTANCE_POLL,
  INSTANCE_TOURNAMENT,
  SHOW_POLL_SECTIONS,
  SHOW_TOURNAMENT_SECTIONS,
} from '../../utils/challengeTypes';
import { evenTeamSizes } from '../../utils/singleElimByes';
import {
  knockoutRounds,
} from '../admin/bracketAdminHelpers';
import { estLocalInputToIso, formatDeadlineEst } from '../../utils/est';
import {
  challengePath,
  streakPath,
  type ChallengeTab,
} from '../../routes';

import { ActivityTypeIcon } from './ActivityTypeIcons';
import './ChallengesPage.css';

function ChallengeThumb({ url, name }: { url: string | null | undefined; name: string }) {
  if (url) {
    return <img className="challenge-thumb" src={url} alt="" />;
  }
  return (
    <span className="challenge-thumb challenge-thumb--ph" aria-hidden>
      {name.charAt(0)}
    </span>
  );
}

function CreatedByMeta({ username }: { username: string }) {
  if (!username) return null;
  return <p className="challenge-card__meta">Created by {username}</p>;
}

function hasLeaderboardPreview(preview?: LeaderboardPreview): boolean {
  return Boolean(preview && (preview.top.length > 0 || preview.viewer));
}

function ChallengeCardLeaderboardRow({ entry }: { entry: LeaderboardPreviewEntry }) {
  return (
    <>
      <span className="challenge-card__leader-rank">{entry.rank}</span>
      <span className="challenge-card__leader-name">{entry.display_name}</span>
      <span className="challenge-card__leader-pts">
        {entry.points_label ?? entry.points}
      </span>
    </>
  );
}

function ChallengeCardLeaderboard({ preview }: { preview: LeaderboardPreview }) {
  if (!hasLeaderboardPreview(preview)) return null;
  return (
    <ol className="challenge-card__leaderboard" aria-label="Leaderboard">
      {preview.top.map((e) => (
        <li
          key={`top-${e.rank}-${e.display_name}`}
          className={
            e.is_viewer
              ? 'challenge-card__leader-row challenge-card__leader-row--viewer'
              : 'challenge-card__leader-row'
          }
        >
          <ChallengeCardLeaderboardRow entry={e} />
        </li>
      ))}
      {preview.gap_before_viewer ? (
        <li className="challenge-card__leader-gap" aria-hidden />
      ) : null}
      {preview.viewer ? (
        <li className="challenge-card__leader-row challenge-card__leader-row--viewer">
          <ChallengeCardLeaderboardRow entry={preview.viewer} />
        </li>
      ) : null}
    </ol>
  );
}

function FinalTrophyMark() {
  return (
    <Trophy
      className="challenge-card__final-trophy"
      size={16}
      strokeWidth={2}
      aria-hidden
    />
  );
}

function TournamentCardFinal({ final }: { final: TournamentFinalSummary }) {
  const champion =
    final.winner_id === final.contestant1.id
      ? final.contestant1
      : final.winner_id === final.contestant2.id
        ? final.contestant2
        : null;
  if (!champion) return null;

  const scoreMode =
    final.knockout_entry === 'score' &&
    final.scores != null &&
    final.scores.total1 != null &&
    final.scores.total2 != null;

  if (!scoreMode) {
    return (
      <div
        className="challenge-card__final"
        aria-label={`Champion ${champion.display_name}`}
      >
        <FinalTrophyMark />
        <ContestantAvatar
          displayName={champion.display_name}
          imageUrl={champion.image_url}
          className="challenge-card__final-crest"
          placeholderClassName="challenge-card__final-crest challenge-card__final-crest--ph"
        />
      </div>
    );
  }

  const leftWins = final.winner_id === final.contestant1.id;
  const rightWins = final.winner_id === final.contestant2.id;
  return (
    <div
      className="challenge-card__final challenge-card__final--score"
      aria-label={`Final ${final.contestant1.display_name} ${final.scores!.total1}–${final.scores!.total2} ${final.contestant2.display_name}`}
    >
      {leftWins ? <FinalTrophyMark /> : null}
      <ContestantAvatar
        displayName={final.contestant1.display_name}
        imageUrl={final.contestant1.image_url}
        className="challenge-card__final-crest"
        placeholderClassName="challenge-card__final-crest challenge-card__final-crest--ph"
      />
      <span className="challenge-card__final-score">
        {final.scores!.total1}–{final.scores!.total2}
      </span>
      <ContestantAvatar
        displayName={final.contestant2.display_name}
        imageUrl={final.contestant2.image_url}
        className="challenge-card__final-crest"
        placeholderClassName="challenge-card__final-crest challenge-card__final-crest--ph"
      />
      {rightWins ? <FinalTrophyMark /> : null}
    </div>
  );
}

type ActivityKey = 'bracket_challenge' | 'tournament' | 'poll' | 'streak';
type PanelMode = 'create' | 'join';

type PanelState = {
  key: ActivityKey;
  mode: PanelMode;
};

export function ChallengesPage({ currentUser: _currentUser }: { currentUser: ApiUser }) {
  const navigate = useNavigate();

  function openChallenge(
    challengeId: number,
    userBracketId?: number | null,
    initialTab?: ChallengeTab,
  ) {
    navigate(
      challengePath(
        challengeId,
        initialTab ?? 'bracket',
        userBracketId != null ? { entry: userBracketId } : undefined,
      ),
    );
  }

  function openStreak(streakChallengeId: number) {
    navigate(streakPath(streakChallengeId, 'leaderboard'));
  }

  function slugify(value: string): string {
    return (
      value
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 48) || 'activity'
    );
  }
  const initialHome = getHomeSnapshot();
  const [rows, setRows] = useState<ChallengeSummary[]>(
    () => initialHome?.challenges ?? [],
  );
  const [streakRows, setStreakRows] = useState<StreakChallengeSummary[]>(
    () => initialHome?.streakChallenges ?? [],
  );
  const [streakCompetitions, setStreakCompetitions] = useState<
    StreakCompetitionSummary[]
  >(() => initialHome?.streakCompetitions ?? []);
  const [publicRows, setPublicRows] = useState<ChallengeSummary[]>(
    () => initialHome?.publicChallenges ?? [],
  );
  const [brackets, setBrackets] = useState<BracketSummary[]>(
    () => initialHome?.brackets ?? [],
  );
  const [loadErr, setLoadErr] = useState('');
  const [loading, setLoading] = useState(() => initialHome == null);
  const [challengesLoaded, setChallengesLoaded] = useState(
    () => (initialHome?.challenges.length ?? 0) > 0,
  );
  const [panel, setPanel] = useState<PanelState | null>(null);
  const [formErr, setFormErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [startBusyId, setStartBusyId] = useState<number | null>(null);

  const [joinDisplayName, setJoinDisplayName] = useState('');
  const [joinCode, setJoinCode] = useState('');

  const [bcName, setBcName] = useState('');
  const [bcBracketId, setBcBracketId] = useState<number | ''>('');
  const [bcDeadline, setBcDeadline] = useState('');
  const [bcMaxEntries, setBcMaxEntries] = useState('1');

  const [tName, setTName] = useState('');
  const [tSize, setTSize] = useState(8);
  const [tStructure, setTStructure] = useState<'SINGLE_ELIM' | 'GROUP_KNOCKOUT'>(
    'SINGLE_ELIM',
  );
  const [tThird, setTThird] = useState(false);
  const [tShowSeeds, setTShowSeeds] = useState(true);
  const [tFillMethod, setTFillMethod] = useState<'standard' | 'randomize'>(
    'standard',
  );
  const [tGroupEntry, setTGroupEntry] = useState<'standings' | 'fixtures'>(
    'standings',
  );
  const [tKoEntry, setTKoEntry] = useState<'winner' | 'score'>('winner');
  const [tKoRoundLegs, setTKoRoundLegs] = useState<Record<number, 1 | 2>>({});
  const [tThirdLegs, setTThirdLegs] = useState<1 | 2>(1);
  const [tMatchesPer, setTMatchesPer] = useState(3);
  const [tImage, setTImage] = useState<File | null>(null);

  const [sName, setSName] = useState('');
  const [sCompetitionId, setSCompetitionId] = useState<number | ''>('');

  const applySnapshot = useCallback((home: NonNullable<ReturnType<typeof getHomeSnapshot>>) => {
    setRows(home.challenges);
    setStreakRows(home.streakChallenges);
    setPublicRows(home.publicChallenges);
    setBrackets(home.brackets);
    setStreakCompetitions(home.streakCompetitions);
    setBcBracketId((prev) => {
      if (prev !== '') return prev;
      return home.brackets[0]?.id ?? '';
    });
    setSCompetitionId((prev) => {
      if (prev !== '') return prev;
      return home.streakCompetitions[0]?.id ?? '';
    });
    if (home.challenges.length > 0) {
      setChallengesLoaded(true);
    }
  }, []);

  useEffect(() => subscribeHome(() => {
    const home = getHomeSnapshot();
    if (home) applySnapshot(home);
  }), [applySnapshot]);

  useEffect(() => {
    setLoadErr('');
    void refreshHome([
      'challenges',
      'streaks',
      'public',
      'brackets',
      'competitions',
    ]).then(({ error, snapshot: refreshed }) => {
      const hasCards =
        (refreshed?.challenges.length ?? 0) > 0 ||
        (refreshed?.streakChallenges.length ?? 0) > 0;
      if (error && !hasCards) {
        setLoadErr(error);
      }
      setChallengesLoaded(true);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (panel == null) return;
    if (!SHOW_TOURNAMENT_SECTIONS && panel.key === 'tournament') {
      setPanel(null);
    }
    if (!SHOW_POLL_SECTIONS && panel.key === 'poll') {
      setPanel(null);
    }
  }, [panel]);

  const bracketChallengeRows = useMemo(
    () => rows.filter((c) => c.instance_type === INSTANCE_BRACKET_CHALLENGE),
    [rows],
  );
  const tournamentRows = useMemo(
    () => rows.filter((c) => c.instance_type === INSTANCE_TOURNAMENT),
    [rows],
  );
  const pollRows = useMemo(
    () => rows.filter((c) => c.instance_type === INSTANCE_POLL),
    [rows],
  );

  const tKnockoutRounds = useMemo(
    () =>
      knockoutRounds({
        structureKind: tStructure,
        numContestants: tSize,
        numGroups: tStructure === 'GROUP_KNOCKOUT' ? tSize / 4 : null,
        qualifyPerGroup: 2,
      }),
    [tStructure, tSize],
  );

  function resetForms() {
    setFormErr('');
    setJoinCode('');
    setBcName('');
    setBcDeadline('');
    setBcMaxEntries('1');
    setTName('');
    setTSize(8);
    setTStructure('SINGLE_ELIM');
    setTThird(false);
    setTShowSeeds(true);
    setTFillMethod('standard');
    setTGroupEntry('standings');
    setTKoEntry('winner');
    setTKoRoundLegs({});
    setTThirdLegs(1);
    setTMatchesPer(3);
    setTImage(null);
    setSName('');
    setSCompetitionId(streakCompetitions[0]?.id ?? '');
  }

  function closePanel() {
    setPanel(null);
    resetForms();
  }

  function upsertChallenge(challenge: ChallengeSummary) {
    upsertHomeChallenge(challenge);
    setRows((prev) => {
      const idx = prev.findIndex((c) => c.id === challenge.id);
      if (idx < 0) return [challenge, ...prev];
      const next = [...prev];
      next[idx] = challenge;
      return next;
    });
  }

  function openChallengeRow(c: ChallengeSummary) {
    if (c.instance_type === INSTANCE_TOURNAMENT) {
      openChallenge(c.id, null);
      return;
    }
    if (c.user_bracket_id == null) {
      void startEntry(c);
      return;
    }
    openChallenge(c.id, c.user_bracket_id, defaultChallengeTab(c));
  }

  async function startEntry(challenge: ChallengeSummary) {
    const displayName = joinDisplayName.trim();
    if (!displayName) {
      setFormErr('Enter your name first.');
      return;
    }
    setStartBusyId(challenge.id);
    setFormErr('');
    try {
      const { user_bracket } = await createUserBracket({
        bracket_id: challenge.bracket_id,
        challenge_id: challenge.id,
        display_name: displayName,
      });
      const updated = { ...challenge, user_bracket_id: user_bracket.id };
      upsertChallenge(updated);
      invalidateHome('challenges');
      openChallenge(challenge.id, user_bracket.id);
    } catch (err) {
      setFormErr(
        err instanceof ApiError ? err.message : 'Could not start.',
      );
    } finally {
      setStartBusyId(null);
    }
  }

  async function handleJoin(
    instanceType: string | undefined,
    challengeId?: number,
  ) {
    setFormErr('');
    const displayName = joinDisplayName.trim();
    const code = joinCode.trim();
    if (!displayName) {
      setFormErr('Enter your name.');
      return;
    }
    if (!challengeId && !code) {
      setFormErr('Enter a join code.');
      return;
    }
    setBusy(true);
    try {
      if (panel?.key === 'streak') {
        const { streak_challenge } = await joinStreakChallenge(
          challengeId != null
            ? { streak_challenge_id: challengeId, display_name: displayName }
            : { join_code: code, display_name: displayName },
        );
        upsertHomeStreakChallenge(streak_challenge);
        setStreakRows((prev) => {
          const idx = prev.findIndex((s) => s.id === streak_challenge.id);
          if (idx < 0) return [streak_challenge, ...prev];
          const next = [...prev];
          next[idx] = streak_challenge;
          return next;
        });
        invalidateHome('streaks');
        closePanel();
        openStreak(streak_challenge.id);
        return;
      }

      const { challenge } = await joinChallenge({
        challenge_id: challengeId,
        join_code: code || undefined,
        display_name: displayName,
        instance_type: instanceType,
      });
      upsertChallenge(challenge);
      invalidateHome('challenges');
      closePanel();
      openChallengeRow(challenge);
    } catch (err) {
      setFormErr(err instanceof ApiError ? err.message : 'Could not join.');
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateBracketChallenge(e: React.FormEvent) {
    e.preventDefault();
    setFormErr('');
    const name = bcName.trim();
    if (!name) {
      setFormErr('Name is required.');
      return;
    }
    if (bcBracketId === '' || !Number.isFinite(bcBracketId)) {
      setFormErr('Choose a bracket.');
      return;
    }
    const deadlineIso = estLocalInputToIso(bcDeadline);
    if (bcDeadline.trim() && !deadlineIso) {
      setFormErr('Invalid submission deadline.');
      return;
    }
    setBusy(true);
    try {
      const { challenge } = await createChallenge({
        name,
        bracket_id: bcBracketId,
        instance_type: INSTANCE_BRACKET_CHALLENGE,
        is_private: true,
        submission_deadline: deadlineIso ?? null,
        max_entries: Math.max(1, parseInt(bcMaxEntries, 10) || 1),
      });
      upsertChallenge(challenge);
      invalidateHome('challenges');
      closePanel();
      if (challenge.user_bracket_id != null) {
        openChallenge(
          challenge.id,
          challenge.user_bracket_id,
          challenge.is_private && challenge.join_code ? 'settings' : undefined,
        );
      }
    } catch (err) {
      setFormErr(err instanceof ApiError ? err.message : 'Could not create.');
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateTournament(e: React.FormEvent) {
    e.preventDefault();
    setFormErr('');
    const name = tName.trim();
    const size = tSize;
    const structure = tStructure;
    const hasThird = tThird;
    const showSeeds = tShowSeeds;
    if (!name) {
      setFormErr('Name is required.');
      return;
    }
    if (!Number.isFinite(size) || size < 2) {
      setFormErr('Choose at least 2 teams.');
      return;
    }
    if (structure === 'SINGLE_ELIM' && size % 2 !== 0) {
      setFormErr('Single elimination needs an even team count.');
      return;
    }
    if (structure === 'GROUP_KNOCKOUT' && size % 4 !== 0) {
      setFormErr('Group & Knockout needs a team count divisible by 4.');
      return;
    }
    setBusy(true);
    try {
      const numberOfGroups = size / 4;
      const roundLegs: Record<string, number> = {};
      for (const round of tKnockoutRounds) {
        roundLegs[String(round.size)] = tKoRoundLegs[round.size] === 2 ? 2 : 1;
      }
      let { challenge } = await createChallenge({
        name,
        instance_type: INSTANCE_TOURNAMENT,
        is_private: true,
        bracket_setup: {
          structure,
          identifier: slugify(name),
          bracket_name: name,
          number_of_contestants: size,
          has_third_place: hasThird,
          show_seeds: showSeeds,
          structure_config: {
            results_entry: {
              group: structure === 'GROUP_KNOCKOUT' ? tGroupEntry : 'standings',
              knockout: tKoEntry,
            },
            ...(structure === 'GROUP_KNOCKOUT'
              ? {
                  group_stage: {
                    number_of_groups: numberOfGroups,
                    contestants_qualifying_per_group: 2,
                    matches_per_contestant:
                      tGroupEntry === 'standings' ? 3 : tMatchesPer,
                  },
                  knockout: {
                    number_of_legs: 1,
                    round_legs: roundLegs,
                    ...(hasThird
                      ? { third_place_number_of_legs: tThirdLegs }
                      : {}),
                    metadata: {
                      knockout_fill_method: tFillMethod,
                    },
                  },
                }
              : {
                  knockout: {
                    number_of_legs: 1,
                    round_legs: roundLegs,
                    ...(hasThird
                      ? { third_place_number_of_legs: tThirdLegs }
                      : {}),
                  },
                }),
          },
        },
      });
      if (tImage) {
        const fd = new FormData();
        fd.append('image', tImage);
        ({ challenge } = await updateChallenge(challenge.id, fd));
      }
      upsertChallenge(challenge);
      invalidateHome('challenges');
      closePanel();
      openChallengeRow(challenge);
    } catch (err) {
      setFormErr(err instanceof ApiError ? err.message : 'Could not create.');
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateStreak(e: React.FormEvent) {
    e.preventDefault();
    setFormErr('');
    const name = sName.trim();
    if (!name) {
      setFormErr('Name is required.');
      return;
    }
    if (sCompetitionId === '' || !Number.isFinite(sCompetitionId)) {
      setFormErr('Choose a competition.');
      return;
    }
    setBusy(true);
    try {
      const { streak_challenge } = await createStreakChallenge({
        name,
        streak_competition_id: sCompetitionId,
        is_private: true,
      });
      upsertHomeStreakChallenge(streak_challenge);
      setStreakRows((prev) => [streak_challenge, ...prev]);
      invalidateHome('streaks', 'competitions');
      closePanel();
      openStreak(streak_challenge.id);
    } catch (err) {
      setFormErr(err instanceof ApiError ? err.message : 'Could not create.');
    } finally {
      setBusy(false);
    }
  }

  function renderActivityList(
    items: ChallengeSummary[],
    showDeadline: boolean,
    loaded = true,
  ) {
    if (!loaded && items.length === 0) {
      return <p className="activity-section__empty">Loading…</p>;
    }
    if (items.length === 0) {
      return <p className="activity-section__empty">None yet.</p>;
    }
    return (
      <ul className="challenge-list">
        {items.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              className="challenge-card card challenge-card--clickable"
              disabled={startBusyId === c.id}
              onClick={() => void openChallengeRow(c)}
            >
              <div className="challenge-card__body">
                <ChallengeThumb url={c.bracket_image_url} name={c.name} />
                <div className="challenge-card__text">
                  <h3 className="challenge-card__name">{c.name}</h3>
                  {c.instance_type !== INSTANCE_TOURNAMENT ? (
                    <p className="challenge-card__meta">{c.bracket_name}</p>
                  ) : null}
                  <CreatedByMeta username={c.created_by_username} />
                  {showDeadline && c.submission_deadline && !c.is_submitted ? (
                    <p className="challenge-card__due">
                      Due {formatDeadlineEst(c.submission_deadline)}
                    </p>
                  ) : null}
                  {c.is_private ? (
                    <span className="challenge-card__badge">Private</span>
                  ) : null}
                </div>
                {c.instance_type === INSTANCE_TOURNAMENT &&
                c.tournament_final ? (
                  <TournamentCardFinal final={c.tournament_final} />
                ) : hasLeaderboardPreview(c.leaderboard_preview) ? (
                  <ChallengeCardLeaderboard preview={c.leaderboard_preview!} />
                ) : null}
              </div>
            </button>
          </li>
        ))}
      </ul>
    );
  }

  function renderStreakList() {
    if (streakRows.length === 0) {
      return <p className="activity-section__empty">None yet.</p>;
    }
    return (
      <ul className="challenge-list">
        {streakRows.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              className="challenge-card card challenge-card--clickable"
              onClick={() => openStreak(s.id)}
            >
              <div className="challenge-card__body">
                <ChallengeThumb url={s.image_url} name={s.name} />
                <div className="challenge-card__text">
                  <h3 className="challenge-card__name">{s.name}</h3>
                  {s.streak_competition_name ? (
                    <p className="challenge-card__meta">
                      {s.streak_competition_name}
                    </p>
                  ) : null}
                  <CreatedByMeta username={s.created_by_username} />
                  {s.is_private ? (
                    <span className="challenge-card__badge">Private</span>
                  ) : null}
                </div>
                {hasLeaderboardPreview(s.leaderboard_preview) ? (
                  <ChallengeCardLeaderboard preview={s.leaderboard_preview!} />
                ) : null}
              </div>
            </button>
          </li>
        ))}
      </ul>
    );
  }

  function renderJoinForm(instanceType?: string) {
    const publicForType = instanceType
      ? publicRows.filter((c) => c.instance_type === instanceType)
      : [];
    return (
      <form
        className="activity-panel__form"
        onSubmit={(e) => {
          e.preventDefault();
          void handleJoin(instanceType);
        }}
      >
        <div className="field">
          <label htmlFor={`join-name-${instanceType ?? 'streak'}`}>Your name</label>
          <input
            id={`join-name-${instanceType ?? 'streak'}`}
            className="input"
            value={joinDisplayName}
            onChange={(e) => setJoinDisplayName(e.target.value)}
            maxLength={80}
            required
            disabled={busy}
          />
        </div>
        <div className="field">
          <label htmlFor={`join-code-${instanceType ?? 'streak'}`}>Join code</label>
          <input
            id={`join-code-${instanceType ?? 'streak'}`}
            className="input"
            value={joinCode}
            onChange={(e) =>
              setJoinCode(
                e.target.value.replace(/\s/g, '').toUpperCase().slice(0, 8),
              )
            }
            maxLength={8}
            disabled={busy}
          />
        </div>
        <div className="activity-panel__actions">
          <button type="button" className="btn btn--ghost" onClick={closePanel}>
            Cancel
          </button>
          <button type="submit" className="btn btn--primary" disabled={busy}>
            {busy ? 'Joining…' : 'Join'}
          </button>
        </div>
        {publicForType.length > 0 ? (
          <div className="activity-panel__public">
            <p className="activity-panel__public-label">Or join public</p>
            <ul className="challenge-list challenge-list--compact">
              {publicForType.map((c) => (
                <li key={c.id} className="challenge-card challenge-card--compact">
                  <div className="challenge-card__body">
                    <div>
                      <strong>{c.name}</strong>
                      {c.instance_type !== INSTANCE_TOURNAMENT ? (
                        <span className="challenge-card__meta">
                          {c.bracket_name}
                        </span>
                      ) : null}
                      <CreatedByMeta username={c.created_by_username} />
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn--secondary"
                    disabled={busy || !c.can_join}
                    onClick={() => void handleJoin(instanceType, c.id)}
                  >
                    Join
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </form>
    );
  }

  function renderSection(
    key: ActivityKey,
    title: string,
    list: React.ReactNode,
    createForm: React.ReactNode,
    joinInstanceType?: string,
    showCreate = true,
  ) {
    const isOpen = panel?.key === key;
    return (
      <section className={`activity-section card activity-section--${key}`}>
        <div className="activity-section__head">
          <div className="activity-section__title-wrap">
            <span className="activity-section__icon" aria-hidden>
              <ActivityTypeIcon type={key} />
            </span>
            <h2 className="activity-section__title">{title}</h2>
          </div>
          {!isOpen ? (
            <div className="activity-section__buttons">
              {showCreate ? (
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => {
                    resetForms();
                    setPanel({ key, mode: 'create' });
                  }}
                >
                  Create
                </button>
              ) : null}
              <button
                type="button"
                className="btn btn--outline"
                onClick={() => {
                  resetForms();
                  setPanel({ key, mode: 'join' });
                }}
              >
                Join
              </button>
            </div>
          ) : null}
        </div>
        {isOpen ? (
          <div className="activity-panel">
            <h3 className="activity-panel__heading">
              {panel.mode === 'create' && showCreate ? 'Create' : 'Join'} {title}
            </h3>
            {panel.mode === 'create' && showCreate
              ? createForm
              : renderJoinForm(joinInstanceType)}
            {formErr ? (
              <div className="alert alert--error" role="status">
                {formErr}
              </div>
            ) : null}
          </div>
        ) : (
          list
        )}
      </section>
    );
  }

  return (
    <div className="challenges-page">
      <header className="challenges-page__hero">
        <h1>My Challenges</h1>
      </header>

      {loadErr ? <div className="alert alert--error">{loadErr}</div> : null}

      {loading &&
      rows.length === 0 &&
      streakRows.length === 0 ? (
        <p className="challenges-page__muted">Loading…</p>
      ) : (
        <div className="challenges-page__sections">
          {renderSection(
            'bracket_challenge',
            'Bracket Challenge',
            renderActivityList(bracketChallengeRows, true, challengesLoaded),
            <form className="activity-panel__form" onSubmit={handleCreateBracketChallenge}>
              <div className="field">
                <label htmlFor="bc-name">Challenge name</label>
                <input
                  id="bc-name"
                  className="input"
                  value={bcName}
                  onChange={(e) => setBcName(e.target.value)}
                  required
                  disabled={busy}
                />
              </div>
              <div className="field">
                <label htmlFor="bc-bracket">Bracket</label>
                <select
                  id="bc-bracket"
                  className="select"
                  value={bcBracketId === '' ? '' : String(bcBracketId)}
                  onChange={(e) =>
                    setBcBracketId(
                      e.target.value ? parseInt(e.target.value, 10) : '',
                    )
                  }
                  required
                  disabled={busy || brackets.length === 0}
                >
                  {brackets.length === 0 ? (
                    <option value="">No brackets available</option>
                  ) : (
                    brackets.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))
                  )}
                </select>
              </div>
              <div className="field">
                <label htmlFor="bc-deadline">Submission deadline (US Eastern)</label>
                <input
                  id="bc-deadline"
                  className="input"
                  type="datetime-local"
                  value={bcDeadline}
                  onChange={(e) => setBcDeadline(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="field">
                <label htmlFor="bc-max">Entries per person</label>
                <input
                  id="bc-max"
                  className="input"
                  type="number"
                  min={1}
                  max={50}
                  value={bcMaxEntries}
                  onChange={(e) => setBcMaxEntries(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="activity-panel__actions">
                <button type="button" className="btn btn--ghost" onClick={closePanel}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={busy || brackets.length === 0}
                >
                  {busy ? 'Creating…' : 'Create'}
                </button>
              </div>
            </form>,
            INSTANCE_BRACKET_CHALLENGE,
          )}

          {renderSection(
            'streak',
            'Streak Challenge',
            renderStreakList(),
            <form className="activity-panel__form" onSubmit={handleCreateStreak}>
              <div className="field">
                <label htmlFor="s-competition">Competition</label>
                {streakCompetitions.length === 0 ? (
                  <p className="activity-panel__hint">
                    No competitions available yet.
                  </p>
                ) : (
                  <select
                    id="s-competition"
                    className="select"
                    value={sCompetitionId === '' ? '' : String(sCompetitionId)}
                    onChange={(e) =>
                      setSCompetitionId(
                        e.target.value ? parseInt(e.target.value, 10) : '',
                      )
                    }
                    disabled={busy}
                    required
                  >
                    {streakCompetitions.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div className="field">
                <label htmlFor="s-name">Challenge name</label>
                <input
                  id="s-name"
                  className="input"
                  value={sName}
                  onChange={(e) => setSName(e.target.value)}
                  required
                  disabled={busy || streakCompetitions.length === 0}
                />
              </div>
              <div className="activity-panel__actions">
                <button type="button" className="btn btn--ghost" onClick={closePanel}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={busy || streakCompetitions.length === 0}
                >
                  {busy ? 'Creating…' : 'Create'}
                </button>
              </div>
            </form>,
          )}

          {SHOW_TOURNAMENT_SECTIONS
            ? renderSection(
                'tournament',
                'Tournament',
                renderActivityList(tournamentRows, false),
                <form
                  className="activity-panel__form"
                  onSubmit={(e) => void handleCreateTournament(e)}
                >
                  <div className="field">
                    <label htmlFor="t-name">Tournament name</label>
                    <input
                      id="t-name"
                      className="input"
                      value={tName}
                      onChange={(e) => setTName(e.target.value)}
                      required
                      disabled={busy}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="t-image">Image</label>
                    <input
                      id="t-image"
                      className="input"
                      type="file"
                      accept="image/*"
                      disabled={busy}
                      onChange={(e) =>
                        setTImage(e.target.files?.[0] ?? null)
                      }
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="t-structure">Structure</label>
                    <select
                      id="t-structure"
                      className="select"
                      value={tStructure}
                      onChange={(e) => {
                        const next = e.target.value as
                          | 'SINGLE_ELIM'
                          | 'GROUP_KNOCKOUT';
                        setTStructure(next);
                        setTShowSeeds(next === 'SINGLE_ELIM');
                        if (next === 'GROUP_KNOCKOUT' && tSize < 8) {
                          setTSize(8);
                        }
                      }}
                      disabled={busy}
                    >
                      <option value="SINGLE_ELIM">Single Elimination</option>
                      <option value="GROUP_KNOCKOUT">Group & Knockout</option>
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="t-size">Teams</label>
                    <select
                      id="t-size"
                      className="select"
                      value={tSize}
                      onChange={(e) => setTSize(parseInt(e.target.value, 10))}
                      disabled={busy}
                    >
                      {(tStructure === 'GROUP_KNOCKOUT'
                        ? [8, 16, 32]
                        : evenTeamSizes(4, 64)
                      ).map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </div>
                  {tStructure === 'GROUP_KNOCKOUT' ? (
                    <>
                      <div className="field">
                        <label htmlFor="t-fill">Group → Knockout Fill</label>
                        <select
                          id="t-fill"
                          className="select"
                          value={tFillMethod}
                          onChange={(e) =>
                            setTFillMethod(
                              e.target.value as 'standard' | 'randomize',
                            )
                          }
                          disabled={busy}
                        >
                          <option value="standard">Standard</option>
                          <option value="randomize">Randomize</option>
                        </select>
                      </div>
                      <div className="field">
                        <label htmlFor="t-group-entry">Group Results</label>
                        <select
                          id="t-group-entry"
                          className="select"
                          value={tGroupEntry}
                          onChange={(e) =>
                            setTGroupEntry(
                              e.target.value as 'standings' | 'fixtures',
                            )
                          }
                          disabled={busy}
                        >
                          <option value="standings">Standings</option>
                          <option value="fixtures">Fixtures</option>
                        </select>
                      </div>
                      {tGroupEntry === 'fixtures' ? (
                        <div className="field">
                          <label htmlFor="t-matches-per">
                            Matches Per Team
                          </label>
                          <select
                            id="t-matches-per"
                            className="select"
                            value={tMatchesPer}
                            onChange={(e) =>
                              setTMatchesPer(parseInt(e.target.value, 10))
                            }
                            disabled={busy}
                          >
                            {[3, 6].map((n) => (
                              <option key={n} value={n}>
                                {n === 3 ? '3 (Once Each)' : '6 (Home & Away)'}
                              </option>
                            ))}
                          </select>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                  <div className="field">
                    <label htmlFor="t-ko-entry">Knockout Results</label>
                    <select
                      id="t-ko-entry"
                      className="select"
                      value={tKoEntry}
                      onChange={(e) =>
                        setTKoEntry(e.target.value as 'winner' | 'score')
                      }
                      disabled={busy}
                    >
                      <option value="winner">Winner Only</option>
                      <option value="score">Score</option>
                    </select>
                  </div>
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={tThird}
                      onChange={(e) => setTThird(e.target.checked)}
                      disabled={busy}
                    />
                    Third-place Match
                  </label>
                  <fieldset className="field" disabled={busy}>
                    <legend>Legs Per Knockout Round</legend>
                    {tKnockoutRounds.map((round) => (
                      <div className="field" key={round.size}>
                        <label htmlFor={`t-ko-legs-${round.size}`}>
                          {round.name}
                        </label>
                        <select
                          id={`t-ko-legs-${round.size}`}
                          className="select"
                          value={tKoRoundLegs[round.size] ?? 1}
                          onChange={(e) => {
                            const legs =
                              parseInt(e.target.value, 10) === 2 ? 2 : 1;
                            setTKoRoundLegs((prev) => ({
                              ...prev,
                              [round.size]: legs,
                            }));
                          }}
                        >
                          <option value={1}>1 Leg</option>
                          <option value={2}>2 Legs</option>
                        </select>
                      </div>
                    ))}
                    {tThird ? (
                      <div className="field">
                        <label htmlFor="t-ko-legs-third">Third Place</label>
                        <select
                          id="t-ko-legs-third"
                          className="select"
                          value={tThirdLegs}
                          onChange={(e) =>
                            setTThirdLegs(
                              parseInt(e.target.value, 10) === 2 ? 2 : 1,
                            )
                          }
                        >
                          <option value={1}>1 Leg</option>
                          <option value={2}>2 Legs</option>
                        </select>
                      </div>
                    ) : null}
                  </fieldset>
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={tShowSeeds}
                      onChange={(e) => setTShowSeeds(e.target.checked)}
                      disabled={busy}
                    />
                    Show Seed Numbers
                  </label>
                  <div className="activity-panel__actions">
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={closePanel}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="btn btn--primary"
                      disabled={busy}
                    >
                      {busy ? 'Creating…' : 'Create'}
                    </button>
                  </div>
                </form>,
                INSTANCE_TOURNAMENT,
              )
            : null}

          {SHOW_POLL_SECTIONS
            ? renderSection(
                'poll',
                'Poll',
                renderActivityList(pollRows, false),
                null,
                INSTANCE_POLL,
                false,
              )
            : null}
        </div>
      )}
    </div>
  );
}
