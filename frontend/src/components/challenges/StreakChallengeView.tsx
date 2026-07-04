import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { DeleteConfirmDialog } from '../admin/DeleteConfirmDialog';
import {
  ApiError,
  deleteStreakChallenge,
  getStreakAwards,
  getStreakChallenge,
  getStreakLeaderboard,
  getStreakParticipantPicks,
  clearStreakPick,
  saveStreakKnockoutSchedule,
  streakPick,
  type ApiUser,
  type KnockoutPhaseInfo,
  type StreakAwardsPayload,
  type StreakLeaderboardEntry,
  type StreakParticipantPickRow,
  type StreakQuestionInfo,
  type StreakChallengeSummary,
} from '../../utils/api';
import { invalidateHome } from '../../utils/homeCache';
import { streakEmoji } from '../../utils/challengeTypes';
import { challengeThemeClass } from '../../utils/challengeThemes';
import { estLocalInputToIso, formatDeadlineEst, isoToEstLocalInput } from '../../utils/est';
import {
  knockoutRoundLabel,
  makePickPhaseDividers,
  uniquePlayerAbbreviations,
} from '../../utils/streakKnockout';
import {
  streakPath,
  streakPlayerPath,
  type StreakTab,
} from '../../routes';

import { CopyJoinCode } from './CopyJoinCode';
import { StreakAwards } from './StreakAwards';
import { StreakChallengeStats } from './StreakChallengeStats';
import { StreakKnockout } from './StreakKnockout';
import { StreakLeaderboard } from './StreakLeaderboard';
import { StreakQuestionChoices } from './StreakQuestionChoices';
import './challengeThemes.css';
import './StreakChallengeView.css';
import '../challenges/ChallengeView.css';
import './ChallengeLeaderboard.css';

const streakThemeClass = challengeThemeClass('streak');

type Props = {
  streakChallengeId: number;
  tab: StreakTab;
  viewingPlayerId?: number | null;
  currentUser: ApiUser;
};

function streakPlayerLabel(entry: StreakLeaderboardEntry): string {
  return entry.display_name?.trim() || entry.username;
}

function compareClosesAtAsc(
  a: { closes_at: string; id: number },
  b: { closes_at: string; id: number },
): number {
  const diff =
    new Date(a.closes_at).getTime() - new Date(b.closes_at).getTime();
  if (diff !== 0) return diff;
  return a.id - b.id;
}

function compareClosesAtDesc(
  a: { closes_at: string; id: number },
  b: { closes_at: string; id: number },
): number {
  const diff =
    new Date(b.closes_at).getTime() - new Date(a.closes_at).getTime();
  if (diff !== 0) return diff;
  return b.id - a.id;
}

type MatchupPlayer = {
  userId: number;
  displayName: string;
};

type PickFilter = {
  scope?: 'streak' | 'consolation' | 'round';
  roundIndex?: number;
};

type SelectedPlayer = {
  userId: number;
  displayName: string;
  fromTab: StreakTab;
  picksFilter?: PickFilter;
  matchup?: {
    userA: MatchupPlayer;
    userB: MatchupPlayer;
  };
};

type MatchupOutcome = 'correct' | 'wrong' | 'none';

type HeadToHeadQuestionRow = {
  questionId: number;
  text: string;
  closesAt: string;
  choices: StreakParticipantPickRow['choices'];
  correctChoiceId: number | null;
  leftPickChoiceId: number | null;
  rightPickChoiceId: number | null;
  leftOutcome: MatchupOutcome;
  rightOutcome: MatchupOutcome;
};

function knockoutRoundStartsAt(
  summary: StreakChallengeSummary | null,
  roundIndex: number,
): string | null {
  if (!summary || roundIndex <= 0) return null;
  if (roundIndex === 1) return summary.knockout_transition_at ?? null;
  return summary.knockout_round_starts?.[String(roundIndex)] ?? null;
}

function pickOutcomeFromChoice(
  pickChoiceId: number | null,
  correctChoiceId: number | null,
): MatchupOutcome {
  if (pickChoiceId == null || correctChoiceId == null) return 'none';
  return pickChoiceId === correctChoiceId ? 'correct' : 'wrong';
}

function mergeHeadToHeadPicks(
  leftRows: StreakParticipantPickRow[],
  rightRows: StreakParticipantPickRow[],
  baseQuestions: StreakQuestionInfo[] = [],
): HeadToHeadQuestionRow[] {
  const byQuestionId = new Map<number, HeadToHeadQuestionRow>();

  for (const question of baseQuestions) {
    byQuestionId.set(question.id, {
      questionId: question.id,
      text: question.text,
      closesAt: question.closes_at,
      choices: question.choices,
      correctChoiceId: question.correct_choice_id,
      leftPickChoiceId: null,
      rightPickChoiceId: null,
      leftOutcome: 'none',
      rightOutcome: 'none',
    });
  }

  for (const row of leftRows) {
    const existing = byQuestionId.get(row.question_id);
    if (existing) {
      existing.leftPickChoiceId = row.pick_choice_id;
      existing.leftOutcome = pickOutcomeFromChoice(
        row.pick_choice_id,
        row.correct_choice_id,
      );
      if (existing.correctChoiceId == null) {
        existing.correctChoiceId = row.correct_choice_id;
      }
      if (existing.choices.length === 0) {
        existing.choices = row.choices;
      }
      continue;
    }

    byQuestionId.set(row.question_id, {
      questionId: row.question_id,
      text: row.text,
      closesAt: row.closes_at,
      choices: row.choices,
      correctChoiceId: row.correct_choice_id,
      leftPickChoiceId: row.pick_choice_id,
      rightPickChoiceId: null,
      leftOutcome: pickOutcomeFromChoice(
        row.pick_choice_id,
        row.correct_choice_id,
      ),
      rightOutcome: 'none',
    });
  }

  for (const row of rightRows) {
    const existing = byQuestionId.get(row.question_id);
    const rightOutcome = pickOutcomeFromChoice(
      row.pick_choice_id,
      row.correct_choice_id,
    );

    if (existing) {
      existing.rightPickChoiceId = row.pick_choice_id;
      existing.rightOutcome = rightOutcome;
      if (existing.correctChoiceId == null) {
        existing.correctChoiceId = row.correct_choice_id;
      }
      if (existing.choices.length === 0) {
        existing.choices = row.choices;
      }
      continue;
    }

    byQuestionId.set(row.question_id, {
      questionId: row.question_id,
      text: row.text,
      closesAt: row.closes_at,
      choices: row.choices,
      correctChoiceId: row.correct_choice_id,
      leftPickChoiceId: null,
      rightPickChoiceId: row.pick_choice_id,
      leftOutcome: 'none',
      rightOutcome,
    });
  }

  return [...byQuestionId.values()].sort((a, b) =>
    compareClosesAtAsc(
      { closes_at: a.closesAt, id: a.questionId },
      { closes_at: b.closesAt, id: b.questionId },
    ),
  );
}

export function StreakChallengeView({
  streakChallengeId,
  tab,
  viewingPlayerId = null,
  currentUser,
}: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const playerNavState = location.state as
    | {
        playerName?: string;
        fromTab?: StreakTab;
        picksScope?: 'streak' | 'consolation' | 'round';
        roundIndex?: number;
        matchupUserAId?: number;
        matchupUserAName?: string;
        matchupUserBId?: number;
        matchupUserBName?: string;
      }
    | null
    | undefined;
  const playerNameFromState = playerNavState?.playerName;

  function goToTab(nextTab: StreakTab) {
    navigate(streakPath(streakChallengeId, nextTab));
  }

  const [summary, setSummary] = useState<StreakChallengeSummary | null>(null);
  const [questions, setQuestions] = useState<StreakQuestionInfo[]>([]);
  const [entries, setEntries] = useState<StreakLeaderboardEntry[]>([]);
  const [awards, setAwards] = useState<StreakAwardsPayload | null>(null);
  const [loadErr, setLoadErr] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteErr, setDeleteErr] = useState('');
  const [knockoutPhases, setKnockoutPhases] = useState<KnockoutPhaseInfo[]>([]);
  const [scheduleTransition, setScheduleTransition] = useState('');
  const [scheduleRoundStarts, setScheduleRoundStarts] = useState<
    Record<string, string>
  >({});
  const [scheduleRoundHeadstart, setScheduleRoundHeadstart] = useState<
    Record<string, boolean>
  >({});
  const [scheduleBusy, setScheduleBusy] = useState(false);
  const [scheduleErr, setScheduleErr] = useState('');
  const [scheduleMsg, setScheduleMsg] = useState('');

  const selectedPlayer = useMemo<SelectedPlayer | null>(() => {
    if (viewingPlayerId == null) return null;
    const fromBoard = entries.find((entry) => entry.user_id === viewingPlayerId);
    return {
      userId: viewingPlayerId,
      displayName:
        playerNameFromState ??
        (fromBoard ? streakPlayerLabel(fromBoard) : 'Player'),
      fromTab: playerNavState?.fromTab ?? 'leaderboard',
      picksFilter: playerNavState?.picksScope
        ? {
            scope: playerNavState.picksScope,
            roundIndex: playerNavState.roundIndex,
          }
        : undefined,
      matchup:
        playerNavState?.matchupUserAId != null &&
        playerNavState.matchupUserAName &&
        playerNavState.matchupUserBId != null &&
        playerNavState.matchupUserBName
          ? {
              userA: {
                userId: playerNavState.matchupUserAId,
                displayName: playerNavState.matchupUserAName,
              },
              userB: {
                userId: playerNavState.matchupUserBId,
                displayName: playerNavState.matchupUserBName,
              },
            }
          : undefined,
    };
  }, [viewingPlayerId, entries, playerNameFromState, playerNavState]);

  const [playerPicks, setPlayerPicks] = useState<StreakParticipantPickRow[]>(
    [],
  );
  const [matchupRightPicks, setMatchupRightPicks] = useState<
    StreakParticipantPickRow[]
  >([]);
  const [playerPicksBusy, setPlayerPicksBusy] = useState(false);
  const [playerPicksErr, setPlayerPicksErr] = useState('');

  const reload = useCallback(async () => {
    setLoadErr('');
    try {
      const detail = await getStreakChallenge(streakChallengeId);
      const board = await getStreakLeaderboard(streakChallengeId);
      setSummary(detail.streak_challenge);
      setQuestions(detail.questions);
      setKnockoutPhases(detail.knockout_phases ?? []);
      setEntries(board.entries);
      if (detail.streak_challenge.competition_is_over) {
        try {
          setAwards(await getStreakAwards(streakChallengeId));
        } catch {
          setAwards(null);
        }
      } else {
        setAwards(null);
      }
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Unable to load streak challenge.',
      );
    }
  }, [streakChallengeId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const competitionIsOver = summary?.competition_is_over === true;
  const isKnockout = summary?.is_knockout === true;
  const hasScheduledKnockout = summary?.knockout_transition_at != null;
  const canManageKnockout =
    summary?.is_creator === true || currentUser.is_staff === true;
  const knockoutCutoffCount =
    summary?.knockout_transition_at &&
    (summary.knockout_total_rounds ?? 0) > 0
      ? 2 ** (summary.knockout_total_rounds ?? 0)
      : null;

  useEffect(() => {
    if (!summary || isKnockout) return;
    setScheduleTransition(
      summary.knockout_transition_at
        ? isoToEstLocalInput(summary.knockout_transition_at)
        : '',
    );
    const roundStarts: Record<string, string> = {};
    const roundHeadstart: Record<string, boolean> = {};
    const totalRounds = summary.knockout_total_rounds ?? 0;
    for (let round = 1; round <= totalRounds; round += 1) {
      const key = String(round);
      if (round >= 2) {
        const raw = summary.knockout_round_starts?.[key];
        roundStarts[key] = raw ? isoToEstLocalInput(raw) : '';
      }
      roundHeadstart[key] = summary.knockout_round_headstart?.[key] !== false;
    }
    setScheduleRoundStarts(roundStarts);
    setScheduleRoundHeadstart(roundHeadstart);
  }, [summary, isKnockout]);

  useEffect(() => {
    if (!summary) return;
    if (competitionIsOver && tab === 'make') {
      navigate(streakPath(streakChallengeId, 'awards'), { replace: true });
      return;
    }
    if (!competitionIsOver && tab === 'awards') {
      navigate(streakPath(streakChallengeId, 'leaderboard'), { replace: true });
    }
  }, [summary, competitionIsOver, tab, navigate, streakChallengeId]);

  function onSelectLeaderboardPlayer(userId: number, displayName: string) {
    navigate(streakPlayerPath(streakChallengeId, userId), {
      state: {
        playerName: displayName,
        fromTab: 'leaderboard',
        picksScope: hasScheduledKnockout ? 'streak' : undefined,
      },
    });
  }

  function onSelectKnockoutPlayer(
    userId: number,
    displayName: string,
    filter?: PickFilter,
    matchup?: {
      userA: MatchupPlayer;
      userB: MatchupPlayer;
    },
  ) {
    navigate(streakPlayerPath(streakChallengeId, userId), {
      state: {
        playerName: displayName,
        fromTab: 'knockout',
        picksScope: filter?.scope,
        roundIndex: filter?.roundIndex,
        matchupUserAId: matchup?.userA.userId,
        matchupUserAName: matchup?.userA.displayName,
        matchupUserBId: matchup?.userB.userId,
        matchupUserBName: matchup?.userB.displayName,
      },
    });
  }

  const userChoiceByQuestionId = useMemo(() => {
    const map: Record<number, number | null> = {};
    for (const q of questions) {
      if (q.resolved_at != null) {
        map[q.id] = q.user_choice_id;
      }
    }
    return map;
  }, [questions]);

  const makeQuestions = useMemo(() => {
    const make = questions.filter((q) => q.resolved_at == null);
    make.sort(compareClosesAtAsc);
    return make;
  }, [questions]);

  const makePickRows = useMemo(
    () => makePickPhaseDividers(makeQuestions),
    [makeQuestions],
  );
  const activeKnockoutPhase = useMemo(() => {
    if (!isKnockout || knockoutPhases.length === 0) return null;
    const nowMs = Date.now();
    let activePhase: KnockoutPhaseInfo | null = null;
    for (const phase of knockoutPhases) {
      const startsAtMs = new Date(phase.starts_at).getTime();
      if (!Number.isFinite(startsAtMs) || startsAtMs > nowMs) continue;
      if (
        activePhase == null ||
        startsAtMs > new Date(activePhase.starts_at).getTime()
      ) {
        activePhase = phase;
      }
    }
    return activePhase;
  }, [isKnockout, knockoutPhases]);
  const showMakePicksCaution = useMemo(() => {
    if (
      activeKnockoutPhase == null ||
      summary?.knockout_header?.kind !== 'matchup'
    ) {
      return false;
    }
    return questions.some(
      (question) =>
        question.resolved_at == null &&
        question.is_open &&
        question.is_knockout_pick === true &&
        question.knockout_phase_starts_at === activeKnockoutPhase.starts_at &&
        question.user_choice_id == null,
    );
  }, [activeKnockoutPhase, questions, summary?.knockout_header?.kind]);
  const firstKnockoutStageLabel = useMemo(() => {
    const totalRounds = summary?.knockout_total_rounds ?? 0;
    if (totalRounds <= 0) return null;
    return knockoutRoundLabel(1, totalRounds);
  }, [summary?.knockout_total_rounds]);

  const scheduleRoundFields = useMemo(() => {
    const totalRounds = summary?.knockout_total_rounds ?? 0;
    const rows: Array<{ round: number; label: string }> = [];
    for (let round = 2; round <= totalRounds; round += 1) {
      rows.push({
        round,
        label: knockoutRoundLabel(round, totalRounds),
      });
    }
    return rows;
  }, [summary?.knockout_total_rounds]);

  const sortedPlayerPicks = useMemo(
    () =>
      [...playerPicks].sort((a, b) =>
        compareClosesAtDesc(
          { closes_at: a.closes_at, id: a.question_id },
          { closes_at: b.closes_at, id: b.question_id },
        ),
      ),
    [playerPicks],
  );

  const headToHeadBaseQuestions = useMemo(() => {
    if (
      selectedPlayer?.matchup == null ||
      selectedPlayer.picksFilter?.scope !== 'round' ||
      selectedPlayer.picksFilter.roundIndex == null
    ) {
      return [];
    }

    const roundIndex = selectedPlayer.picksFilter.roundIndex;
    const start = knockoutRoundStartsAt(summary, roundIndex);
    if (!start) return [];
    const end = knockoutRoundStartsAt(summary, roundIndex + 1);
    const startMs = new Date(start).getTime();
    const endMs = end ? new Date(end).getTime() : null;

    return questions
      .filter((question) => {
        if (question.resolved_at == null) return false;
        const closesAtMs = new Date(question.closes_at).getTime();
        if (closesAtMs < startMs) return false;
        if (endMs != null && closesAtMs >= endMs) return false;
        return true;
      })
      .sort(compareClosesAtAsc);
  }, [questions, selectedPlayer, summary]);

  const headToHeadRows = useMemo(
    () =>
      mergeHeadToHeadPicks(
        playerPicks,
        matchupRightPicks,
        headToHeadBaseQuestions,
      ),
    [headToHeadBaseQuestions, playerPicks, matchupRightPicks],
  );

  const headToHeadLabels = useMemo(() => {
    const matchup = selectedPlayer?.matchup;
    if (!matchup) return null;
    const [leftShort, rightShort] = uniquePlayerAbbreviations(
      matchup.userA.displayName,
      matchup.userB.displayName,
    );
    return {
      userA: matchup.userA.displayName,
      userB: matchup.userB.displayName,
      userAShort: leftShort,
      userBShort: rightShort,
    };
  }, [selectedPlayer?.matchup]);

  useEffect(() => {
    if (selectedPlayer == null) {
      setPlayerPicks([]);
      setMatchupRightPicks([]);
      setPlayerPicksErr('');
      return;
    }
    let cancelled = false;
    setPlayerPicksBusy(true);
    setPlayerPicksErr('');
    const matchup = selectedPlayer.matchup;
    void Promise.all([
      getStreakParticipantPicks(
        streakChallengeId,
        matchup?.userA.userId ?? selectedPlayer.userId,
        selectedPlayer.picksFilter,
      ),
      matchup
        ? getStreakParticipantPicks(
            streakChallengeId,
            matchup.userB.userId,
            selectedPlayer.picksFilter,
          )
        : Promise.resolve(null),
    ])
      .then(([leftData, rightData]) => {
        if (!cancelled) {
          setPlayerPicks(leftData.picks);
          setMatchupRightPicks(rightData?.picks ?? []);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setPlayerPicksErr(
            e instanceof ApiError ? e.message : 'Unable to load picks.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setPlayerPicksBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPlayer, streakChallengeId]);

  async function onPick(questionId: number, choiceId: number) {
    try {
      await streakPick(streakChallengeId, questionId, choiceId);
      await reload();
    } catch (e) {
      setLoadErr(e instanceof ApiError ? e.message : 'Could not save pick.');
    }
  }

  async function onClearPick(questionId: number) {
    try {
      await clearStreakPick(streakChallengeId, questionId);
      await reload();
    } catch (e) {
      setLoadErr(e instanceof ApiError ? e.message : 'Could not clear pick.');
    }
  }

  function renderQuestion(q: StreakQuestionInfo) {
    const closesAtPassed = !q.is_open;
    const deadlineLocked = q.deadline_locked;
    const isLocked = closesAtPassed || deadlineLocked;
    const lockLabel = closesAtPassed
      ? 'Closed'
      : 'Multiple picks cannot share a deadline';
    return (
      <li
        key={q.id}
        className={
          isLocked
            ? 'card streak-question streak-question--locked'
            : 'card streak-question'
        }
      >
        <div className="streak-question__head">
          <div className="streak-question__head-main">
            <p className="streak-question__text">{q.text}</p>
            <p className="streak-question__meta">
              {closesAtPassed
                ? `Closed ${formatDeadlineEst(q.closes_at)}`
                : `Closes ${formatDeadlineEst(q.closes_at)}`}
            </p>
          </div>
          {isLocked ? (
            <p
              className="streak-question__locked"
              aria-label={lockLabel}
            >
              <svg
                className="streak-question__lock-icon"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              <span className="streak-question__locked-text">{lockLabel}</span>
            </p>
          ) : null}
        </div>
        <StreakQuestionChoices
          choices={q.choices}
          userChoiceId={q.user_choice_id}
          correctChoiceId={q.correct_choice_id}
          resolved={q.resolved_at != null}
          disabled={!q.is_open || deadlineLocked}
          deadlineLocked={isLocked}
          canClearPick={q.can_clear_pick}
          onPick={
            q.is_open && !deadlineLocked
              ? (choiceId) => void onPick(q.id, choiceId)
              : undefined
          }
          onClearPick={
            q.can_clear_pick ? () => void onClearPick(q.id) : undefined
          }
        />
      </li>
    );
  }

  async function handleSaveKnockoutSchedule(e: React.FormEvent) {
    e.preventDefault();
    const transitionIso = estLocalInputToIso(scheduleTransition);
    if (!transitionIso) {
      setScheduleErr('Set a knockout start time.');
      return;
    }
    const roundStarts: Record<string, string> = {};
    const roundHeadstart: Record<string, boolean> = {};
    roundHeadstart['1'] = scheduleRoundHeadstart['1'] !== false;
    for (const row of scheduleRoundFields) {
      const iso = estLocalInputToIso(scheduleRoundStarts[String(row.round)] ?? '');
      if (!iso) {
        setScheduleErr(`Set a start time for ${row.label}.`);
        return;
      }
      roundStarts[String(row.round)] = iso;
      roundHeadstart[String(row.round)] =
        scheduleRoundHeadstart[String(row.round)] !== false;
    }
    setScheduleBusy(true);
    setScheduleErr('');
    setScheduleMsg('');
    try {
      const result = await saveStreakKnockoutSchedule(streakChallengeId, {
        knockout_transition_at: transitionIso,
        knockout_round_starts: roundStarts,
        knockout_round_headstart: roundHeadstart,
      });
      setSummary(result.streak_challenge);
      setKnockoutPhases(result.knockout_phases);
      setScheduleMsg('Knockout schedule saved.');
      await reload();
    } catch (e) {
      setScheduleErr(
        e instanceof ApiError ? e.message : 'Could not save schedule.',
      );
    } finally {
      setScheduleBusy(false);
    }
  }

  async function handleDeleteChallenge() {
    setDeleteBusy(true);
    setDeleteErr('');
    try {
      await deleteStreakChallenge(streakChallengeId);
      invalidateHome('streaks');
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

  function renderMatchupOutcomeMark(outcome: MatchupOutcome) {
    if (outcome === 'correct') {
      return (
        <span
          className="streak-choice__mark streak-choice__mark--correct streak-player-picks__h2h-mark"
          aria-hidden
        >
          ✓
        </span>
      );
    }
    if (outcome === 'wrong') {
      return (
        <span
          className="streak-choice__mark streak-choice__mark--wrong streak-player-picks__h2h-mark"
          aria-hidden
        >
          ✗
        </span>
      );
    }
    return (
      <span className="streak-player-picks__h2h-mark streak-player-picks__h2h-mark--none">
        —
      </span>
    );
  }

  if (loadErr && !summary) {
    return (
      <div className={`${streakThemeClass} streak-view`}>
        <div className="alert alert--error">{loadErr}</div>
        <Link to="/" className="btn btn--ghost">
          ← My Challenges
        </Link>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className={`${streakThemeClass} streak-view`}>
        <p className="streak-view__muted">Loading…</p>
      </div>
    );
  }

  if (selectedPlayer != null) {
    const matchup = selectedPlayer.matchup;
    const rootClassName = `${streakThemeClass} streak-view${
      hasScheduledKnockout ? ' streak-view--wide' : ''
    }`;
    return (
      <div className={rootClassName}>
        <button
          type="button"
          className="btn btn--ghost streak-player-picks__back"
          onClick={() => goToTab(selectedPlayer.fromTab)}
        >
          ← {selectedPlayer.fromTab === 'knockout' ? 'Knockout' : 'Leaderboard'}
        </button>
        <section className="card streak-view__panel">
          <h2 className="streak-player-picks__title">
            {matchup && headToHeadLabels
              ? `${headToHeadLabels.userA} vs ${headToHeadLabels.userB}`
              : `${selectedPlayer.displayName}'s picks`}
          </h2>
          {playerPicksErr ? (
            <div className="alert alert--error">{playerPicksErr}</div>
          ) : null}
          {playerPicksBusy ? (
            <p className="streak-view__muted">Loading…</p>
          ) : matchup && headToHeadLabels ? (
            headToHeadRows.length === 0 ? (
              <p className="streak-view__muted">No resolved picks yet.</p>
            ) : (
              <>
                <div className="streak-player-picks__h2h-head" aria-hidden>
                  <span className="streak-player-picks__h2h-head-name streak-player-picks__h2h-head-name--left">
                    {headToHeadLabels.userA}
                  </span>
                  <span className="streak-player-picks__h2h-head-gap" />
                  <span className="streak-player-picks__h2h-head-name streak-player-picks__h2h-head-name--right">
                    {headToHeadLabels.userB}
                  </span>
                </div>
                <ul className="streak-player-picks__list">
                  {headToHeadRows.map((row) => (
                    <li
                      key={row.questionId}
                      className="streak-player-picks__item streak-player-picks__item--h2h"
                    >
                      <div className="streak-player-picks__h2h-grid">
                        <div className="streak-player-picks__h2h-mark-col">
                          {renderMatchupOutcomeMark(row.leftOutcome)}
                        </div>
                        <div className="streak-player-picks__h2h-main">
                          <p className="streak-player-picks__question">{row.text}</p>
                          <p className="streak-player-picks__meta">
                            Closed {formatDeadlineEst(row.closesAt)}
                          </p>
                          <StreakQuestionChoices
                            choices={row.choices}
                            userChoiceId={null}
                            correctChoiceId={row.correctChoiceId}
                            resolved
                            disabled
                            statsMode
                            h2h={{
                              leftPickChoiceId: row.leftPickChoiceId,
                              rightPickChoiceId: row.rightPickChoiceId,
                              leftBadge: headToHeadLabels.userA,
                              rightBadge: headToHeadLabels.userB,
                              leftBadgeShort: headToHeadLabels.userAShort,
                              rightBadgeShort: headToHeadLabels.userBShort,
                            }}
                          />
                        </div>
                        <div className="streak-player-picks__h2h-mark-col streak-player-picks__h2h-mark-col--right">
                          {renderMatchupOutcomeMark(row.rightOutcome)}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )
          ) : sortedPlayerPicks.length === 0 ? (
            <p className="streak-view__muted">No picks yet.</p>
          ) : (
            <ul className="streak-player-picks__list">
              {sortedPlayerPicks.map((row) => (
                <li key={row.question_id} className="streak-player-picks__item">
                  <p className="streak-player-picks__question">{row.text}</p>
                  <p className="streak-player-picks__meta">
                    Closed {formatDeadlineEst(row.closes_at)}
                  </p>
                  <StreakQuestionChoices
                    choices={row.choices}
                    userChoiceId={row.pick_choice_id}
                    correctChoiceId={row.correct_choice_id}
                    resolved
                    disabled
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    );
  }

  const activeStreakEmoji = streakEmoji(
    summary.streak_signed,
    summary.best_win_streak,
    summary.broken_win_streak ?? 0,
  );
  const rootClassName = `${streakThemeClass} streak-view${
    hasScheduledKnockout ? ' streak-view--wide' : ''
  }`;

  return (
    <div className={rootClassName}>
      <Link to="/" className="btn btn--ghost challenge-view__back">
        ← My Challenges
      </Link>

      <header className="challenge-view__head card">
        <div className="challenge-view__head-inner">
          {summary.image_url ? (
            <img
              className="challenge-view__bracket-img"
              src={summary.image_url}
              alt=""
            />
          ) : (
            <span className="challenge-view__bracket-img challenge-view__bracket-img--ph">
              {(summary.streak_competition_name || summary.name).charAt(0)}
            </span>
          )}
          <div>
            <p className="challenge-view__type">Streak Challenge</p>
            <h1>{summary.name}</h1>
            {summary.streak_competition_name ? (
              <p className="challenge-view__meta">{summary.streak_competition_name}</p>
            ) : null}
            {isKnockout && summary.knockout_header ? (
              <p className="streak-view__stat">
                <span className="streak-view__stat-group">
                  <span className="streak-view__stat-label streak-view__stat-label--knockout">
                    {summary.knockout_header.label}
                  </span>
                </span>
                <span className="streak-view__stat-sep" aria-hidden>
                  |
                </span>
                <span className="streak-view__stat-value">
                  {summary.knockout_header.value}
                </span>
              </p>
            ) : (
              <p className="streak-view__stat">
                <span className="streak-view__stat-group">
                  <span className="streak-view__stat-label">BEST</span>
                  <span className="streak-view__stat-value">
                    {summary.long_win_display}
                  </span>
                </span>
                <span className="streak-view__stat-sep" aria-hidden>
                  |
                </span>
                <span className="streak-view__stat-group">
                  <span className="streak-view__stat-label">CURRENT</span>
                  <span className="streak-view__stat-value">
                    {summary.current_display}
                  </span>
                </span>
                <span className="streak-view__stat-sep" aria-hidden>
                  |
                </span>
                <span className="streak-view__stat-value">
                  {summary.wins}-{summary.losses}
                </span>
                {activeStreakEmoji ? (
                  <span className="streak-view__stat-emoji" aria-hidden>
                    {activeStreakEmoji}
                  </span>
                ) : null}
              </p>
            )}
          </div>
        </div>
      </header>

      {loadErr ? <div className="alert alert--error">{loadErr}</div> : null}

      <nav className="challenge-view__tabs" aria-label="Streak sections">
        {competitionIsOver ? (
          <button
            type="button"
            className={
              tab === 'awards'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => goToTab('awards')}
          >
            Awards
          </button>
        ) : null}
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
        {hasScheduledKnockout ? (
          <button
            type="button"
            className={
              tab === 'knockout'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => goToTab('knockout')}
          >
            Knockout
          </button>
        ) : null}
        <button
          type="button"
          className={
            tab === 'results'
              ? 'challenge-view__tab challenge-view__tab--active'
              : 'challenge-view__tab'
          }
          onClick={() => goToTab('results')}
        >
          Results
        </button>
        {!competitionIsOver ? (
          <button
            type="button"
            className={
              tab === 'make'
                ? 'challenge-view__tab challenge-view__tab--active'
                : 'challenge-view__tab'
            }
            onClick={() => goToTab('make')}
            aria-label={showMakePicksCaution ? 'Make Picks' : undefined}
          >
            {showMakePicksCaution ? (
              <span className="streak-view__tab-alert">
                <span aria-hidden>⚠️</span>
                <span>Make Picks</span>
                <span aria-hidden>⚠️</span>
              </span>
            ) : (
              'Make Picks'
            )}
          </button>
        ) : null}
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

      {tab === 'awards' && competitionIsOver && awards ? (
        <StreakAwards awards={awards} />
      ) : null}

      {tab === 'leaderboard' ? (
        <section className="card streak-view__panel">
          <StreakLeaderboard
            entries={entries}
            viewerUserId={currentUser.id}
            onSelectPlayer={onSelectLeaderboardPlayer}
            isKnockout={isKnockout}
            knockoutCutoffCount={knockoutCutoffCount}
          />
        </section>
      ) : null}

      {tab === 'knockout' && hasScheduledKnockout ? (
        <StreakKnockout
          streakChallengeId={streakChallengeId}
          onSelectPlayer={onSelectKnockoutPlayer}
        />
      ) : null}

      {tab === 'make' ? (
        <section className="streak-view__questions streak-view__questions--make">
          <ul className="streak-question-list">
            {makePickRows.map((row) =>
              row.type === 'divider' ? (
                <li
                  key={row.key}
                  className="streak-make-phase"
                  aria-label={`${row.label} picks`}
                >
                  {row.label === firstKnockoutStageLabel ? (
                    <span className="streak-make-phase__note">
                      Knockout: Answer All Questions
                    </span>
                  ) : null}
                  <span className="streak-make-phase__line" aria-hidden />
                  <span className="streak-make-phase__label">{row.label}</span>
                </li>
              ) : (
                renderQuestion(row.question)
              ),
            )}
          </ul>
          {makeQuestions.length === 0 ? (
            <p className="streak-view__muted">No open questions right now.</p>
          ) : null}
        </section>
      ) : null}

      {tab === 'results' ? (
        <StreakChallengeStats
          streakChallengeId={streakChallengeId}
          viewerUserId={currentUser.id}
          userChoiceByQuestionId={userChoiceByQuestionId}
          onSelectPlayer={onSelectLeaderboardPlayer}
        />
      ) : null}

      {tab === 'rules' ? (
        <section className="card streak-view__rules">
          {isKnockout ? (
            <>
              <h2 className="streak-view__rules-heading">Streak Mode</h2>
              <p>
                Win the challenge by earning the longest winning streak, active or
                inactive.
              </p>
              <ul className="streak-view__rules-list">
                <li>
                  Make your picks before the questions close. You can adjust your picks
                  anytime before they close.
                </li>
                <li>
                  You cannot make multiple picks with the exact same closing time. Tap on
                  your selected answer again to clear the pick.
                </li>
                <li>
                  You can make as many picks or as few picks as you want. The goal is to
                  create the longest winning streak with correct picks.
                </li>
                <li>
                  Tiebreakers: Best Streak, then Current Streak, then Wins, then Win
                  %, then better Worst Streak
                </li>
              </ul>
              <h2 className="streak-view__rules-heading">Knockout Mode</h2>
              <ul className="streak-view__rules-list">
                <li>
                  Top seeds from the streak leaderboard qualify for a single-elimination
                  bracket.
                </li>
                <li>
                  Each round counts total correct picks plus an optional best streak
                  bonus from your frozen best streak.
                </li>
                <li>
                  Ties go to the higher seed. Round times are set in Settings; Start
                  Knockout locks round-one matchups and later rounds advance on
                  schedule.
                </li>
                <li>
                  Eliminated and non-qualifying players can keep picking for the
                  consolation leaderboard.
                </li>
              </ul>
            </>
          ) : (
            <>
              <p>
                Win the challenge by earning the longest winning streak, active or
                inactive.
              </p>
              <ul className="streak-view__rules-list">
                <li>
                  Make your picks before the questions close. You can adjust your picks
                  anytime before they close.
                </li>
                <li>
                  You cannot make multiple picks with the exact same closing time. Tap on
                  your selected answer again to clear the pick.
                </li>
                <li>
                  You can make as many picks or as few picks as you want. The goal is to
                  create the longest winning streak with correct picks.
                </li>
                <li>
                  Tiebreakers: Best Streak, then Current Streak, then Wins, then Win
                  %, then better Worst Streak
                </li>
              </ul>
            </>
          )}
        </section>
      ) : null}

      {tab === 'settings' ? (
        <section className="card challenge-view__settings">
          {summary.is_private && summary.join_code ? (
            <CopyJoinCode code={summary.join_code} />
          ) : (
            <p className="streak-view__muted">
              This challenge is public. Anyone can join from the public list.
            </p>
          )}
          {canManageKnockout && !competitionIsOver ? (
            <div className="challenge-view__danger">
              <h2 className="challenge-view__danger-title">H2H Knockout Schedule</h2>
              {isKnockout ? (
                <>
                  <p className="streak-view__muted">
                    Knockout mode is active. Round times were set before the bracket
                    started.
                  </p>
                  {knockoutPhases.length > 0 ? (
                    <ul className="streak-knockout-schedule-readonly">
                      {knockoutPhases.map((phase) => (
                        <li key={phase.round_index}>
                          <span>{phase.label}</span>
                          <span className="streak-knockout-schedule-readonly__meta">
                            <span>{formatDeadlineEst(phase.starts_at)}</span>
                            <span>
                              Best Streak Bonus:{' '}
                              {phase.headstart_enabled === false ? 'Off' : 'On'}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </>
              ) : (
                <form
                  className="streak-knockout-schedule-form"
                  onSubmit={(e) => void handleSaveKnockoutSchedule(e)}
                >
                  <p className="streak-view__muted">
                    Set when each bracket round&apos;s picks begin. Questions after
                    each time are knockout picks and are not limited to one per
                    deadline. Start Knockout on the Knockout tab locks the bracket;
                    later rounds advance at these times.
                  </p>
                  <div className="streak-knockout-schedule-row">
                    <div className="field">
                      <label htmlFor="streak-knockout-transition">
                        {knockoutRoundLabel(1, summary.knockout_total_rounds ?? 1)} Start
                      </label>
                      <input
                        id="streak-knockout-transition"
                        className="input"
                        type="datetime-local"
                        value={scheduleTransition}
                        onChange={(e) => setScheduleTransition(e.target.value)}
                        disabled={scheduleBusy}
                        required
                      />
                    </div>
                    <label className="streak-knockout-schedule-row__headstart checkbox-label">
                      <input
                        type="checkbox"
                        checked={scheduleRoundHeadstart['1'] !== false}
                        onChange={(e) =>
                          setScheduleRoundHeadstart((prev) => ({
                            ...prev,
                            '1': e.target.checked,
                          }))
                        }
                        disabled={scheduleBusy}
                      />
                      Best Streak Bonus
                    </label>
                  </div>
                  {scheduleRoundFields.map((row) => (
                    <div className="streak-knockout-schedule-row" key={row.round}>
                      <div className="field">
                        <label htmlFor={`streak-knockout-round-${row.round}`}>
                          {row.label} Start
                        </label>
                        <input
                          id={`streak-knockout-round-${row.round}`}
                          className="input"
                          type="datetime-local"
                          value={scheduleRoundStarts[String(row.round)] ?? ''}
                          onChange={(e) =>
                            setScheduleRoundStarts((prev) => ({
                              ...prev,
                              [String(row.round)]: e.target.value,
                            }))
                          }
                          disabled={scheduleBusy}
                          required
                        />
                      </div>
                      <label className="streak-knockout-schedule-row__headstart checkbox-label">
                        <input
                          type="checkbox"
                          checked={
                            scheduleRoundHeadstart[String(row.round)] !== false
                          }
                          onChange={(e) =>
                            setScheduleRoundHeadstart((prev) => ({
                              ...prev,
                              [String(row.round)]: e.target.checked,
                            }))
                          }
                          disabled={scheduleBusy}
                        />
                        Best Streak Bonus
                      </label>
                    </div>
                  ))}
                  {scheduleErr ? (
                    <div className="alert alert--error" role="status">
                      {scheduleErr}
                    </div>
                  ) : null}
                  {scheduleMsg ? (
                    <div className="alert alert--success" role="status">
                      {scheduleMsg}
                    </div>
                  ) : null}
                  <button
                    type="submit"
                    className="btn btn--primary"
                    disabled={scheduleBusy}
                  >
                    {scheduleBusy ? 'Saving…' : 'Save Schedule'}
                  </button>
                </form>
              )}
            </div>
          ) : null}
          {summary.is_creator ? (
            <div className="challenge-view__danger">
              <h2 className="challenge-view__danger-title">Delete Challenge</h2>
              <p className="streak-view__muted">
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
        label={summary?.name ?? ''}
        intro={
          summary
            ? `“${summary.name}” will be permanently removed along with all player entries.`
            : undefined
        }
        busy={deleteBusy}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => void handleDeleteChallenge()}
      />

    </div>
  );
}
