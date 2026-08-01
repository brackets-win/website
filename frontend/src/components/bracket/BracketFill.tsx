import {
  Fragment,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import type { ScoringHighlights } from '../../utils/api';
import {
  ApiError,
  type BracketContestantInfo,
  type BracketDetail,
  type BracketStageInfo,
  type MatchupInfo,
  type ResultsEntryConfig,
  type UserBracketDetail,
  getBracket,
  getUserBracket,
  adminGetUserBracket,
  materializeBracketScores,
  patchMatchupScores,
  patchMatchupWinner,
  setBracketNextMatch,
  submitUserBracket,
  updateBracketGroupResultsMode,
} from '../../utils/api';
import {
  getGroupResultsMode,
  type GroupResultsMode,
} from '../../utils/groupResultsMode';
import { showOutcomeWeightsControl as canSetOutcomeWeights } from '../../utils/outcomeWeights';
import { getNextMatchMatchupId } from '../../utils/nextMatch';
import {
  invalidateHome,
  invalidateHomeForUserBracket,
} from '../../utils/homeCache';
import { ContestantAvatar } from './ContestantAvatar';
import { GroupStagePanel } from './GroupStagePanel';
import {
  buildMirrorBracketLayout,
  columnMatchupCenterPct,
  type MirrorBracketColumn,
} from './bracketMirrorLayout';
import {
  findMatchupById,
  prevKnockoutStageBeforeFinal,
  resolveFeederMatchups,
  stageUsesTreeFeeders,
  sortMatchupsByFeederOrder,
} from './knockoutFeederLayout';
import './BracketFill.css';
import { SetOutcomeWeightsModal } from './SetOutcomeWeightsModal';

/** Split bracket center column vertical layout (% of track height). */
const SPLIT_CENTER_CHAMP_GAP_PCT = 14;
const SPLIT_CENTER_FINAL_ABOVE_SEMI_PCT = 10;
/** Top of the 3rd-place match card (% track); label + winner box sit above it. */
const SPLIT_CENTER_THIRD_MATCH_TOP_PCT = 19;

function sortStages(stages: BracketStageInfo[]) {
  return [...stages].sort((a, b) => a.order - b.order);
}

type ScoringHighlightLookup = {
  isKnockoutScored: (stageId: number, contestantId: number) => boolean;
  isChampionScored: (contestantId: number) => boolean;
  isThirdScored: (contestantId: number) => boolean;
};

const ScoringHighlightContext = createContext<ScoringHighlightLookup | null>(
  null,
);

function useScoringHighlight() {
  return useContext(ScoringHighlightContext);
}

type NextMatchControl = {
  /** Matchup currently flagged as the next match (or null). */
  nextMatchMatchupId: number | null;
  busy: boolean;
  onSet: (matchupId: number | null) => void | Promise<void>;
};

const NextMatchContext = createContext<NextMatchControl | null>(null);

type KnockoutEntryControl = {
  mode: 'winner' | 'score';
  locked: boolean;
  applyScores: (
    matchupId: number,
    legs: Array<[number | null, number | null]>,
    winnerId?: number | null,
  ) => void | Promise<void>;
  applyWinner: (
    matchupId: number,
    contestantId: number,
  ) => void | Promise<void>;
};

const KnockoutEntryContext = createContext<KnockoutEntryControl>({
  mode: 'winner',
  locked: true,
  applyScores: async () => {},
  applyWinner: async () => {},
});

function useKnockoutEntry() {
  return useContext(KnockoutEntryContext);
}

/** Master-edit control: flag an undecided matchup as the leaderboard "Next Match". */
function NextMatchToggle({ matchup }: { matchup: MatchupInfo }) {
  const control = useContext(NextMatchContext);
  if (!control) return null;
  const eligible =
    matchup.contestant1 != null &&
    matchup.contestant2 != null &&
    matchup.winner == null;
  const isCurrent = control.nextMatchMatchupId === matchup.id;
  if (!isCurrent && !eligible) return null;
  if (isCurrent) {
    return (
      <div className="bf-next-match-control">
        <span
          className="bf-next-match-btn bf-next-match-btn--current"
          aria-label="Current Next Match"
        >
          Next Match
        </span>
        <button
          type="button"
          className="bf-next-match-clear"
          disabled={control.busy}
          onClick={() => void control.onSet(null)}
          aria-label="Clear Next Match"
        >
          Clear
        </button>
      </div>
    );
  }
  return (
    <div className="bf-next-match-control">
      <button
        type="button"
        className="bf-next-match-btn"
        disabled={control.busy}
        onClick={() => void control.onSet(matchup.id)}
        aria-label="Set Next Match"
      >
        Set Next Match
      </button>
    </div>
  );
}

function buildScoringLookup(
  highlights: ScoringHighlights | undefined,
): ScoringHighlightLookup | null {
  if (!highlights) return null;
  const koSet = new Set(
    highlights.knockout_contestants.map(
      (x) => `${x.stage_id}:${x.contestant_id}`,
    ),
  );
  return {
    isKnockoutScored: (stageId, contestantId) =>
      koSet.has(`${stageId}:${contestantId}`),
    isChampionScored: (contestantId) =>
      highlights.champion_contestant_id === contestantId,
    isThirdScored: (contestantId) =>
      highlights.third_place_contestant_id === contestantId,
  };
}

function ScoredMark() {
  return (
    <span className="bf-scored-check" aria-hidden>
      ✓
    </span>
  );
}

/** Short code for a knockout stage (QF1, SF2, R16, …). Uses API stage name + matchup position. */
function stageShortPrefix(stage: BracketStageInfo): string {
  const md = stage.metadata;
  if (
    md &&
    typeof md === 'object' &&
    'short_label' in md &&
    typeof (md as { short_label?: unknown }).short_label === 'string'
  ) {
    const s = (md as { short_label: string }).short_label.trim();
    if (s) return s;
  }
  const name = stage.name?.trim() ?? '';
  const KNOWN: Record<string, string> = {
    Quarterfinals: 'QF',
    Semifinals: 'SF',
    Final: 'F',
    'Group Stage': 'G',
  };
  if (KNOWN[name]) return KNOWN[name];
  const rom = /^Round of (\d+)$/i.exec(name);
  if (rom) return `R${rom[1]}`;
  if (!name) return 'G';
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return parts
      .map((p) => p[0].toUpperCase())
      .join('')
      .slice(0, 4);
  }
  return name.slice(0, 4).toUpperCase();
}

function feederDropLabel(
  feeder: MatchupInfo,
  knockoutStages: BracketStageInfo[],
  currentMatchup: MatchupInfo,
): string {
  const currentStage = knockoutStages.find((s) => s.id === currentMatchup.stage_id);
  const role = currentStage?.knockout?.is_third_place ? 'Loser' : 'Winner';
  const stage = knockoutStages.find((s) => s.id === feeder.stage_id);
  if (!stage) return `Game ${feeder.position} ${role}`;
  const prefix = stageShortPrefix(stage);
  const gamesInStage = Math.max(1, stage.number_of_contestants / 2);
  if (gamesInStage <= 1) {
    return `${prefix} ${role}`;
  }
  return `${prefix} ${role} ${feeder.position}`;
}

function MatchupContestantFace({
  contestant,
  showSeed,
}: {
  contestant: BracketContestantInfo;
  showSeed: boolean;
}) {
  return (
    <span className="bf-ko-face">
      <ContestantAvatar
        displayName={contestant.display_name}
        imageUrl={contestant.image_url}
        className="bf-ko-img"
        placeholderClassName="bf-ko-img bf-ko-img--ph"
      />
      <span className="bf-ko-name">{contestant.display_name}</span>
      {showSeed && contestant.seed != null ? (
        <span className="bf-ko-seed">#{contestant.seed}</span>
      ) : null}
    </span>
  );
}

function latestMatchup(
  detail: UserBracketDetail,
  m: MatchupInfo,
): MatchupInfo {
  return findMatchupById(detail, m.id) ?? m;
}

/** Highlight box for champion or 3rd-place winner above/below the match. */
function WinnerRevealBox({
  contestant,
  showSeeds,
  busy,
  onClear,
  clearLabel,
  scoreAs = 'champion',
}: {
  contestant: BracketContestantInfo;
  showSeeds: boolean;
  busy: boolean;
  onClear?: () => void;
  clearLabel: string;
  scoreAs?: 'champion' | 'third';
}) {
  const scoring = useScoringHighlight();
  const scored =
    scoreAs === 'third'
      ? (scoring?.isThirdScored(contestant.id) ?? false)
      : (scoring?.isChampionScored(contestant.id) ?? false);
  return (
    <div
      className={[
        'bf-champion-box',
        'bf-champion-box--active',
        'bf-winner-reveal',
        scored ? 'bf-champion-box--scored' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {scored ? <ScoredMark /> : null}
      {onClear ? (
        <button
          type="button"
          className="bf-pick-clear bf-pick-clear--champion"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation();
            onClear();
          }}
          aria-label={clearLabel}
        >
          ×
        </button>
      ) : null}
      <MatchupContestantFace contestant={contestant} showSeed={showSeeds} />
    </div>
  );
}

/** Reserved winner slot (empty box until a 3rd-place winner is picked). */
function ThirdPlaceWinnerSlot({
  contestant,
  showSeeds,
  busy,
  onClear,
}: {
  contestant: BracketContestantInfo | null | undefined;
  showSeeds: boolean;
  busy: boolean;
  onClear?: () => void;
}) {
  if (contestant) {
    return (
      <WinnerRevealBox
        contestant={contestant}
        showSeeds={showSeeds}
        busy={busy}
        onClear={onClear}
        clearLabel="Remove 3rd place pick"
        scoreAs="third"
      />
    );
  }
  return (
    <div
      className="bf-champion-box bf-third-place-winner-placeholder"
      aria-label="3rd place winner"
    />
  );
}

export function matchupsForStage(
  ub: UserBracketDetail,
  stageId: number,
): MatchupInfo[] {
  const pack = ub.matchups_by_stage.find((s) => s.stage_id === stageId);
  return pack ? [...pack.matchups].sort((a, b) => a.position - b.position) : [];
}

/** Vertical center % (0–100) for a matchup so the bracket stays aligned & centered. */
export function matchupCenterPct(
  stageIdx: number,
  position: number,
  leaves: number,
): number {
  if (stageIdx === 0) {
    return ((position - 0.5) / leaves) * 100;
  }
  const top = matchupCenterPct(stageIdx - 1, 2 * position - 1, leaves);
  const bot = matchupCenterPct(stageIdx - 1, 2 * position, leaves);
  return (top + bot) / 2;
}

type Props = {
  userBracketId: number;
  /** When the parent already loaded the bracket definition, skip a second GET. */
  initialBracketDef?: BracketDetail | null;
  readOnly?: boolean;
  allowMasterEdit?: boolean;
  /** Read-only display of the official (master) bracket in challenges. */
  allowMasterView?: boolean;
  /** Admin master fill only: Live / Confirmed group results control. */
  showGroupResultsModeControl?: boolean;
  /** Admin master fill only: per-matchup "Set as Next Match" control. */
  showNextMatchControl?: boolean;
  /** Admin master fill only: Set Odds modal for weighted outcomes. */
  showOutcomeWeightsControl?: boolean;
  /**
   * When editing master results for prediction challenges, defer leaderboard
   * recompute until Apply. Tournaments have no challenge leaderboard — pass false.
   * Defaults to true whenever ``allowMasterEdit`` is set.
   */
  deferLeaderboardScoring?: boolean;
  showSubmit?: boolean;
  showScoringHighlights?: boolean;
  /** Load via staff admin endpoint (bypasses peer-privacy on public GET). */
  adminAccess?: boolean;
  /** Pin to one section and hide the in-fill Groups/Knockout tabs. */
  lockedPhase?: 'groups' | 'knockout';
  onSubmitted?: () => void;
};

export function BracketFill({
  userBracketId,
  initialBracketDef = null,
  readOnly = false,
  allowMasterEdit = false,
  allowMasterView = false,
  showGroupResultsModeControl = false,
  showNextMatchControl = false,
  showOutcomeWeightsControl = false,
  deferLeaderboardScoring: deferLeaderboardScoringProp,
  showSubmit = false,
  showScoringHighlights = false,
  adminAccess = false,
  lockedPhase,
  onSubmitted,
}: Props) {
  const [detail, setDetail] = useState<UserBracketDetail | null>(null);
  const [bracketDef, setBracketDef] = useState<BracketDetail | null>(
    initialBracketDef,
  );
  const [error, setError] = useState<string | null>(null);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [materializeBusy, setMaterializeBusy] = useState(false);
  const [materializeRemaining, setMaterializeRemaining] = useState<number | null>(
    null,
  );
  const [groupResultsMode, setGroupResultsMode] =
    useState<GroupResultsMode>('confirmed');
  const [groupResultsModeBusy, setGroupResultsModeBusy] = useState(false);
  const [nextMatchBusy, setNextMatchBusy] = useState(false);
  const [outcomeWeightsOpen, setOutcomeWeightsOpen] = useState(false);
  const [phase, setPhase] = useState<'groups' | 'knockout'>('knockout');
  const phaseInitForUb = useRef<number | null>(null);

  const goToPhase = useCallback((next: 'groups' | 'knockout') => {
    setPhase((current) => {
      if (current === next) return current;
      return next;
    });
  }, []);

  const initialBracketDefRef = useRef(initialBracketDef);
  initialBracketDefRef.current = initialBracketDef;

  const load = useCallback(
    async (options?: {
      refetchBracket?: boolean;
    }): Promise<UserBracketDetail | null> => {
      setError(null);
      const refetchBracket = options?.refetchBracket !== false;
      try {
        const { user_bracket: ub } = await (adminAccess
          ? adminGetUserBracket(userBracketId)
          : getUserBracket(userBracketId));
        setDetail(ub);
        if (refetchBracket) {
          const seed = initialBracketDefRef.current;
          if (seed != null && seed.id === ub.bracket_id) {
            setBracketDef(seed);
          } else {
            const { bracket: b } = await getBracket(ub.bracket_id);
            setBracketDef(b);
          }
        }
        return ub;
      } catch (e) {
        setDetail(null);
        if (refetchBracket && initialBracketDefRef.current == null) {
          setBracketDef(null);
        }
        setError(
          e instanceof ApiError ? e.message : 'Could not load bracket.',
        );
        return null;
      }
    },
    [userBracketId, adminAccess],
  );

  // Parent may finish loading the shared bracket def after first mount.
  useEffect(() => {
    if (initialBracketDef == null) return;
    setBracketDef((prev) => {
      if (prev == null || prev.id === initialBracketDef.id) {
        return initialBracketDef;
      }
      return prev;
    });
  }, [initialBracketDef]);

  const reloadUserBracket = useCallback(async (): Promise<UserBracketDetail | null> => {
    return load({ refetchBracket: false });
  }, [load]);

  const handleGroupSaved = useCallback(
    (ub?: UserBracketDetail) => {
      if (ub) {
        setDetail(ub);
        invalidateHomeForUserBracket(ub);
        return;
      }
      void reloadUserBracket().then((loaded) => {
        if (loaded) invalidateHomeForUserBracket(loaded);
      });
    },
    [reloadUserBracket],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (bracketDef) {
      setGroupResultsMode(getGroupResultsMode(bracketDef.metadata));
    }
  }, [bracketDef]);

  const sortedStages = useMemo(() => {
    if (!bracketDef) return [];
    return sortStages(bracketDef.stages);
  }, [bracketDef]);

  const groupStages = useMemo(
    () => sortedStages.filter((s) => s.stage_type === 'GROUP'),
    [sortedStages],
  );

  const groupsPreview = bracketDef?.groups ?? [];

  const hasGroupUi =
    !!bracketDef &&
    groupStages.length > 0 &&
    (groupsPreview?.length ?? 0) > 0;

  const isWorldCup =
    bracketDef?.metadata != null &&
    typeof bracketDef.metadata === 'object' &&
    ['world_cup_2026', 'euro_2024'].includes(
      (bracketDef.metadata as { tournament_type?: string }).tournament_type ??
        '',
    );

  const firstGroupStage = groupStages[0];

  const showGroupResultsMode =
    showGroupResultsModeControl &&
    detail?.is_master === true &&
    hasGroupUi &&
    !!firstGroupStage;

  const showLiveGroupResultsNote =
    groupResultsMode === 'live' &&
    hasGroupUi &&
    !!firstGroupStage &&
    !showGroupResultsModeControl;

  const showOutcomeWeights =
    showOutcomeWeightsControl &&
    detail?.is_master === true &&
    bracketDef != null &&
    canSetOutcomeWeights(bracketDef, detail);

  const onGroupResultsModeChange = useCallback(
    async (next: GroupResultsMode) => {
      if (!bracketDef || next === groupResultsMode || groupResultsModeBusy) return;
      setGroupResultsModeBusy(true);
      setError(null);
      try {
        const { bracket } = await updateBracketGroupResultsMode(
          bracketDef.id,
          next,
        );
        setBracketDef(bracket);
        setGroupResultsMode(getGroupResultsMode(bracket.metadata));
        const ub = await load();
        if (ub) invalidateHomeForUserBracket(ub);
        else invalidateHome('challenges');
      } catch (e) {
        setError(
          e instanceof ApiError
            ? e.message
            : 'Could not update group results mode.',
        );
      } finally {
        setGroupResultsModeBusy(false);
      }
    },
    [bracketDef, groupResultsMode, groupResultsModeBusy, load],
  );

  const handleSetNextMatch = useCallback(
    async (matchupId: number | null) => {
      if (!bracketDef || nextMatchBusy) return;
      setNextMatchBusy(true);
      setError(null);
      try {
        const { bracket } = await setBracketNextMatch(bracketDef.id, matchupId);
        setBracketDef(bracket);
        // Reload the master entry so the "Apply" prompt reflects the pending
        // next-match recompute (mirrors how master result edits defer scoring).
        await load();
      } catch (e) {
        setError(
          e instanceof ApiError ? e.message : 'Could not update next match.',
        );
      } finally {
        setNextMatchBusy(false);
      }
    },
    [bracketDef, nextMatchBusy, load],
  );

  const nextMatchControl = useMemo<NextMatchControl | null>(() => {
    if (!showNextMatchControl || detail?.is_master !== true) return null;
    return {
      nextMatchMatchupId: getNextMatchMatchupId(bracketDef?.metadata),
      busy: nextMatchBusy,
      onSet: handleSetNextMatch,
    };
  }, [
    showNextMatchControl,
    detail?.is_master,
    bracketDef?.metadata,
    nextMatchBusy,
    handleSetNextMatch,
  ]);

  useEffect(() => {
    if (lockedPhase) {
      setPhase(lockedPhase);
      return;
    }
    if (!hasGroupUi) return;
    if (phaseInitForUb.current === userBracketId) return;
    phaseInitForUb.current = userBracketId;
    setPhase('groups');
  }, [hasGroupUi, userBracketId, lockedPhase]);

  const stages = useMemo(() => {
    if (!bracketDef) return [];
    return sortedStages.filter((s) => s.stage_type === 'KNOCKOUT');
  }, [bracketDef, sortedStages]);

  /** Columns + connectors only (excludes optional third-place stage shown under Champion). */
  const knockoutStagesMain = useMemo(
    () => stages.filter((s) => !s.knockout?.is_third_place),
    [stages],
  );

  const thirdPlaceStage = useMemo(() => {
    if (!bracketDef?.has_third_place_match) return undefined;
    return stages.find((s) => s.knockout?.is_third_place);
  }, [bracketDef?.has_third_place_match, stages]);

  const leaves = useMemo(() => {
    if (!detail || knockoutStagesMain.length === 0) return 0;
    return matchupsForStage(detail, knockoutStagesMain[0].id).length;
  }, [detail, knockoutStagesMain]);

  const openingKoStage = knockoutStagesMain[0];
  const openingContestants = openingKoStage?.number_of_contestants ?? 0;
  const splitKnockoutBoard = openingContestants >= 32 && leaves >= 2;

  const boardHeightPx = useMemo(() => {
    if (splitKnockoutBoard) {
      // Each R32 band must fit two full team rows (not clipped).
      const wingGames = Math.max(leaves / 2, 1);
      const matchupPx = 108;
      return Math.max(640, wingGames * matchupPx);
    }
    return Math.max(640, leaves * 188);
  }, [leaves, splitKnockoutBoard]);

  const mirrorLayout = useMemo(
    () =>
      buildMirrorBracketLayout(
        knockoutStagesMain,
        leaves,
        openingContestants,
      ),
    [knockoutStagesMain, leaves, openingContestants],
  );

  const locked =
    readOnly ||
    (detail != null &&
      !detail.can_edit &&
      !(allowMasterEdit && detail.is_master));

  const deferLeaderboardScoring =
    (deferLeaderboardScoringProp ?? allowMasterEdit) &&
    detail?.is_master === true;

  // Never lock the whole board on a pick save — chips stay clickable.
  const uiBusy = locked;

  const resultsEntry = useMemo((): ResultsEntryConfig => {
    const meta =
      bracketDef?.metadata &&
      typeof bracketDef.metadata === 'object' &&
      !Array.isArray(bracketDef.metadata)
        ? (bracketDef.metadata as Record<string, unknown>)
        : {};
    const raw =
      meta.results_entry && typeof meta.results_entry === 'object'
        ? (meta.results_entry as Record<string, unknown>)
        : {};
    const group = String(raw.group || 'standings');
    const knockout = String(raw.knockout || 'winner');
    return {
      group:
        group === 'table' || group === 'fixtures' ? group : 'standings',
      knockout: knockout === 'score' ? 'score' : 'winner',
    };
  }, [bracketDef?.metadata]);

  const maxKnockoutLegs = useMemo(() => {
    let max = 1;
    for (const s of knockoutStagesMain) {
      const n = s.knockout?.number_of_legs ?? 1;
      if (n > max) max = n;
    }
    if (thirdPlaceStage) {
      const n = thirdPlaceStage.knockout?.number_of_legs ?? 1;
      if (n > max) max = n;
    }
    return Math.min(2, Math.max(1, max));
  }, [knockoutStagesMain, thirdPlaceStage]);

  const koColWidthPx =
    resultsEntry.knockout === 'score'
      ? maxKnockoutLegs >= 2
        ? 308
        : 268
      : 212;

  const hasTournamentResultsEntry = useMemo(() => {
    const meta = bracketDef?.metadata;
    return (
      meta != null &&
      typeof meta === 'object' &&
      !Array.isArray(meta) &&
      'results_entry' in meta
    );
  }, [bracketDef?.metadata]);

  const scoringLookup = useMemo(() => {
    if (!showScoringHighlights || !detail) return null;
    return buildScoringLookup(detail.scoring_highlights);
  }, [showScoringHighlights, detail?.scoring_highlights]);

  const applyWinner = useCallback(
    async (feederMatchupId: number, contestantId: number) => {
      if (locked) return;
      setError(null);
      try {
        await patchMatchupWinner(feederMatchupId, contestantId);
        // Downstream KO slots change server-side — refetch entry only (cache bracketDef).
        const ub = await reloadUserBracket();
        if (ub) invalidateHomeForUserBracket(ub);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not save pick.');
      }
    },
    [locked, reloadUserBracket],
  );

  const applyScores = useCallback(
    async (
      matchupId: number,
      legs: Array<[number | null, number | null]>,
      winnerId?: number | null,
    ) => {
      if (locked) return;
      setError(null);
      try {
        await patchMatchupScores(matchupId, legs, winnerId);
        const ub = await reloadUserBracket();
        if (ub) invalidateHomeForUserBracket(ub);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not save scores.');
      }
    },
    [locked, reloadUserBracket],
  );

  const clearWinner = useCallback(
    async (matchupId: number) => {
      if (locked) return;
      setError(null);
      try {
        await patchMatchupWinner(matchupId, null);
        const ub = await reloadUserBracket();
        if (ub) invalidateHomeForUserBracket(ub);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not clear pick.');
      }
    },
    [locked, reloadUserBracket],
  );

  const onClearWinner = locked ? undefined : clearWinner;

  const handleMaterializeScores = useCallback(async () => {
    if (!bracketDef || materializeBusy || !detail?.leaderboard_scores_pending) {
      return;
    }
    setMaterializeBusy(true);
    setMaterializeRemaining(null);
    setError(null);
    try {
      const maxBatches = 500;
      for (let batch = 0; batch < maxBatches; batch += 1) {
        const res = await materializeBracketScores(bracketDef.id);
        setMaterializeRemaining(
          res.remaining_count > 0 ? res.remaining_count : null,
        );
        setDetail((prev) =>
          prev
            ? {
                ...prev,
                leaderboard_scores_pending: res.leaderboard_scores_pending,
              }
            : prev,
        );
        if (!res.leaderboard_scores_pending) {
          const ub = await load();
          if (ub) invalidateHomeForUserBracket(ub);
          else invalidateHome('challenges');
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      throw new ApiError(
        'Score update is taking longer than expected. Try Apply again.',
        0,
      );
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : 'Could not update leaderboard scores.',
      );
    } finally {
      setMaterializeBusy(false);
      setMaterializeRemaining(null);
    }
  }, [bracketDef, materializeBusy, detail?.leaderboard_scores_pending, load]);

  const showApplyScores =
    deferLeaderboardScoring && detail?.leaderboard_scores_pending === true;

  async function handleSubmit() {
    if (locked || !detail) return;
    setSubmitBusy(true);
    setError(null);
    try {
      await submitUserBracket(userBracketId);
      const ub = await load();
      if (ub) invalidateHomeForUserBracket(ub);
      onSubmitted?.();
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : 'Could not submit bracket.',
      );
    } finally {
      setSubmitBusy(false);
    }
  }

  if (error && !detail) {
    return (
      <section className="bf">
        <p className="bf-error">{error}</p>
      </section>
    );
  }

  if (!detail || !bracketDef) {
    return (
      <section className="bf">
        <p className="bf-meta">Loading bracket…</p>
      </section>
    );
  }

  if (detail.is_master && !allowMasterEdit && !allowMasterView) {
    return (
      <section className="bf">
        <p className="bf-error">
          This is the master results bracket; open a player copy to make picks.
        </p>
      </section>
    );
  }

  if (stages.length === 0) {
    return (
      <section className="bf">
        <p className="bf-error">No knockout stages found for this bracket.</p>
      </section>
    );
  }

  const knockoutEmpty = leaves === 0;

  const finalStage = knockoutStagesMain.find((s) => s.knockout?.is_final);
  const finalMatchups =
    finalStage != null ? matchupsForStage(detail, finalStage.id) : [];
  const finalMatchup = finalMatchups[0];

  const thirdPlaceMatchup =
    thirdPlaceStage != null
      ? matchupsForStage(detail, thirdPlaceStage.id)[0]
      : undefined;

  const meta = detail.metadata ?? {};
  const showSeeds = bracketDef?.show_seeds !== false;

  const knockoutBoard =
    !knockoutEmpty ? (
      <>
        <div className="bf-ko-desktop bf-scroll">
        <div className="bf-ko-touch-zoom">
        {mirrorLayout ? (
          <div className="bf-board-split">
            <MirrorWing
              columns={mirrorLayout.left}
              detail={detail}
              stages={knockoutStagesMain}
              showSeeds={showSeeds}
              applyWinner={applyWinner}
              busy={uiBusy}
              onClearWinner={onClearWinner}
            />
            {mirrorLayout.center && finalMatchup ? (
              (() => {
                const semiCol =
                  mirrorLayout.left[mirrorLayout.left.length - 1];
                const semiCenterPct = columnMatchupCenterPct(
                  semiCol.stageIdx,
                  semiCol.positionMin,
                  semiCol.wingMin,
                  semiCol.wingMax,
                  semiCol.positionMin,
                );
                const finalCenterPct = Math.max(
                  10,
                  semiCenterPct - SPLIT_CENTER_FINAL_ABOVE_SEMI_PCT,
                );
                return (
                  <>
                    <SpineConnector
                      col={semiCol}
                      towardCenter
                      targetCenterPct={finalCenterPct}
                    />
                    <SplitCenterColumn
                      finalMatchup={finalMatchup}
                      thirdPlaceMatchup={thirdPlaceMatchup}
                      semiCenterPct={semiCenterPct}
                      finalCenterPct={finalCenterPct}
                      detail={detail}
                      knockoutStages={knockoutStagesMain}
                      allKnockoutStages={stages}
                      showSeeds={showSeeds}
                      applyWinner={applyWinner}
                      busy={uiBusy}
                      onClearWinner={onClearWinner}
                    />
                    <SpineConnector
                      col={
                        mirrorLayout.right[mirrorLayout.right.length - 1]
                      }
                      towardCenter={false}
                      targetCenterPct={finalCenterPct}
                    />
                  </>
                );
              })()
            ) : null}
            <MirrorWing
              columns={mirrorLayout.right}
              detail={detail}
              stages={knockoutStagesMain}
              showSeeds={showSeeds}
              applyWinner={applyWinner}
              busy={uiBusy}
              onClearWinner={onClearWinner}
              reverse
            />
          </div>
        ) : (
          <div className="bf-board-inner">
            {knockoutStagesMain.map((stage, stageIdx) => (
              <Fragment key={stage.id}>
                <BracketStageColumn
                  stage={stage}
                  stageIdx={stageIdx}
                  leaves={leaves}
                  detail={detail}
                  stages={knockoutStagesMain}
                  showSeeds={showSeeds}
                  applyWinner={applyWinner}
                  busy={uiBusy}
                  onClearWinner={onClearWinner}
                />
                {stageIdx < knockoutStagesMain.length - 1 ? (
                  <ConnectorBetweenStages
                    fromCol={linearStageColumn(
                      knockoutStagesMain[stageIdx],
                      stageIdx,
                      leaves,
                    )}
                    toCol={linearStageColumn(
                      knockoutStagesMain[stageIdx + 1],
                      stageIdx + 1,
                      leaves,
                    )}
                    detail={detail}
                  />
                ) : null}
              </Fragment>
            ))}
            {finalMatchup ? (
              <ChampionColumn
                finalMatchup={finalMatchup}
                thirdPlaceMatchup={thirdPlaceMatchup}
                detail={detail}
                knockoutStages={knockoutStagesMain}
                allKnockoutStages={stages}
                showSeeds={showSeeds}
                applyWinner={applyWinner}
                busy={uiBusy}
                onClearWinner={onClearWinner}
              />
            ) : null}
          </div>
        )}
        </div>
        </div>
      </>
    ) : (
      <p className="bf-meta bf-knockout-placeholder">
        Knockout pairings will fill in here as matchups are available.
      </p>
    );

  return (
    <ScoringHighlightContext.Provider value={scoringLookup}>
    <NextMatchContext.Provider value={nextMatchControl}>
    <KnockoutEntryContext.Provider
      value={{
        mode: resultsEntry.knockout,
        locked,
        applyScores,
        applyWinner,
      }}
    >
    <section
      className={[
        'bf',
        mirrorLayout ? 'bf--split-knockout' : '',
        resultsEntry.knockout === 'score' ? 'bf--score-entry' : '',
        resultsEntry.knockout === 'score' && maxKnockoutLegs >= 2
          ? 'bf--two-legs'
          : '',
      ]
        .filter(Boolean)
        .join(' ')}
      style={
        {
          '--bf-board-h': `${boardHeightPx}px`,
          '--bf-ko-col-width': `${koColWidthPx}px`,
        } as CSSProperties
      }
    >
      <h2>{detail.bracket.name}</h2>
      {error ? <p className="bf-error">{error}</p> : null}

      {showApplyScores ? (
        <div className="bf-scores-pending" role="status">
          <p className="bf-scores-pending__text">
            Results are saved. Challenge leaderboard scores are not updated yet.
          </p>
          <button
            type="button"
            className="btn btn--primary bf-scores-pending__btn"
            disabled={materializeBusy}
            onClick={() => void handleMaterializeScores()}
          >
            {materializeBusy
              ? materializeRemaining != null
                ? `Applying… (${materializeRemaining} left)`
                : 'Applying…'
              : 'Apply'}
          </button>
        </div>
      ) : null}

      {(() => {
        const showPointsBadge =
          showScoringHighlights &&
          !detail.is_master &&
          (detail.submitted_at != null || !detail.can_edit);
        const showToolbar =
          (hasGroupUi && firstGroupStage && !lockedPhase) ||
          (showSubmit && !locked) ||
          showPointsBadge ||
          showGroupResultsMode ||
          showOutcomeWeights;
        if (!showToolbar && !showLiveGroupResultsNote) return null;
        const points =
          detail.score_vs_master != null ? detail.score_vs_master : null;
        return (
          <div className="bf-toolbar-stack">
            <div className="bf-toolbar">
              {hasGroupUi && firstGroupStage && !lockedPhase ? (
                <div
                  className="bf-tabs"
                  role="tablist"
                  aria-label="Bracket sections"
                >
                  <button
                    type="button"
                    role="tab"
                    aria-selected={phase === 'groups'}
                    className={
                      phase === 'groups' ? 'bf-tab bf-tab--active' : 'bf-tab'
                    }
                    onClick={() => goToPhase('groups')}
                  >
                    Group Stage
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={phase === 'knockout'}
                    className={
                      phase === 'knockout' ? 'bf-tab bf-tab--active' : 'bf-tab'
                    }
                    onClick={() => goToPhase('knockout')}
                  >
                    Knockout
                  </button>
                </div>
              ) : null}
              {showGroupResultsMode ? (
                <div
                  className="bf-group-mode"
                  role="radiogroup"
                  aria-label="Group results"
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={groupResultsMode === 'live'}
                    className={
                      groupResultsMode === 'live'
                        ? 'bf-group-mode__btn bf-group-mode__btn--active'
                        : 'bf-group-mode__btn'
                    }
                    disabled={groupResultsModeBusy}
                    onClick={() => void onGroupResultsModeChange('live')}
                  >
                    Live
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={groupResultsMode === 'confirmed'}
                    className={
                      groupResultsMode === 'confirmed'
                        ? 'bf-group-mode__btn bf-group-mode__btn--active'
                        : 'bf-group-mode__btn'
                    }
                    disabled={groupResultsModeBusy}
                    onClick={() => void onGroupResultsModeChange('confirmed')}
                  >
                    Confirmed
                  </button>
                </div>
              ) : null}
              {showOutcomeWeights ? (
                <button
                  type="button"
                  className="bf-set-odds-btn"
                  onClick={() => setOutcomeWeightsOpen(true)}
                >
                  Set Odds
                </button>
              ) : null}
              <div className="bf-toolbar__end">
                {showPointsBadge ? (
                  <p className="bf-toolbar__points" aria-live="polite">
                    {points != null ? `${points} POINTS` : '— POINTS'}
                  </p>
                ) : null}
                {showSubmit && !locked ? (
                  <button
                    type="button"
                    className="btn btn--primary bf-toolbar__submit"
                    disabled={
                      submitBusy ||
                      !detail.is_complete ||
                      !!detail.submitted_at
                    }
                    onClick={() => void handleSubmit()}
                  >
                    {submitBusy
                      ? 'Submitting…'
                      : detail.submitted_at
                        ? 'Submitted'
                        : 'Submit Bracket'}
                  </button>
                ) : null}
              </div>
            </div>
            {showLiveGroupResultsNote ? (
              <p className="bf-group-mode-note">
                Group stage results are not final. Bracket points are only
                projections that assume that group standings hold.
              </p>
            ) : null}
          </div>
        );
      })()}

      {lockedPhase === 'groups' && hasGroupUi && firstGroupStage ? (
        <GroupStagePanel
          userBracketId={userBracketId}
          groups={groupsPreview}
          groupStage={firstGroupStage}
          isWorldCup={isWorldCup}
          firstKnockoutContestants={
            knockoutStagesMain[0]?.number_of_contestants
          }
          initialMetadata={{
            group_positions: meta.group_positions ?? {},
            third_place_advancers: meta.third_place_advancers ?? [],
            group_fixtures: meta.group_fixtures,
            group_stage_completed: meta.group_stage_completed === true,
          }}
          scoringHighlights={
            showScoringHighlights ? detail.scoring_highlights : undefined
          }
          busy={uiBusy}
          readOnly={locked}
          entryMode={resultsEntry.group}
          showCompleteGroupStage={
            hasTournamentResultsEntry &&
            detail?.is_master === true &&
            resultsEntry.group === 'standings'
          }
          onSaved={handleGroupSaved}
          onError={(msg) => setError(msg || null)}
          saveDebounceMs={deferLeaderboardScoring ? 600 : 200}
          lightweightSave
        />
      ) : lockedPhase === 'knockout' || !hasGroupUi || !firstGroupStage ? (
        knockoutBoard
      ) : (
        <div className="bf-phase-viewport" data-phase={phase} aria-live="polite">
          <div className="bf-phase-track" data-active={phase}>
            <div
              className="bf-phase-panel"
              data-inert={phase !== 'groups' ? true : undefined}
            >
              <GroupStagePanel
                userBracketId={userBracketId}
                groups={groupsPreview}
                groupStage={firstGroupStage}
                isWorldCup={isWorldCup}
                firstKnockoutContestants={
                  knockoutStagesMain[0]?.number_of_contestants
                }
                initialMetadata={{
                  group_positions: meta.group_positions ?? {},
                  third_place_advancers: meta.third_place_advancers ?? [],
                  group_fixtures: meta.group_fixtures,
                  group_stage_completed: meta.group_stage_completed === true,
                }}
                scoringHighlights={
                  showScoringHighlights ? detail.scoring_highlights : undefined
                }
                busy={uiBusy}
                readOnly={locked}
                entryMode={resultsEntry.group}
                showCompleteGroupStage={
                  hasTournamentResultsEntry &&
                  detail?.is_master === true &&
                  resultsEntry.group === 'standings'
                }
                onSaved={handleGroupSaved}
                onError={(msg) => setError(msg || null)}
                saveDebounceMs={deferLeaderboardScoring ? 600 : 200}
                lightweightSave
              />
            </div>
            <div
              className="bf-phase-panel"
              data-inert={phase !== 'knockout' ? true : undefined}
            >
              {knockoutBoard}
            </div>
          </div>
        </div>
      )}

      {outcomeWeightsOpen && bracketDef && detail ? (
        <SetOutcomeWeightsModal
          bracket={bracketDef}
          detail={detail}
          onClose={() => setOutcomeWeightsOpen(false)}
          onSaved={(updated) => {
            setBracketDef(updated);
            void load({ refetchBracket: false });
          }}
        />
      ) : null}

    </section>
    </KnockoutEntryContext.Provider>
    </NextMatchContext.Provider>
    </ScoringHighlightContext.Provider>
  );
}

type MatchupCenterFn = (stageIdx: number, position: number) => number;

function ConnectorBetweenStages({
  fromCol,
  toCol,
  detail,
  mirrored = false,
}: {
  fromCol: MirrorBracketColumn;
  toCol: MirrorBracketColumn;
  detail: UserBracketDetail;
  mirrored?: boolean;
}) {
  const fromPct = columnCenterFn(fromCol);
  const prevStageId = fromCol.stage.id;
  const treeOpts = {
    useTreeFeeders: stageUsesTreeFeeders(toCol.stage),
  };
  const nextMatchups = sortMatchupsByFeederOrder(
    matchupsForStage(detail, toCol.stage.id).filter(
      (m) => m.position >= toCol.positionMin && m.position <= toCol.positionMax,
    ),
    detail,
    prevStageId,
    treeOpts,
  );

  return (
    <div className="bf-connector-strip" aria-hidden>
      <div className="bf-stage-heading-spacer" />
      <div className="bf-connector-track">
        <svg
          className="bf-connector-svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {nextMatchups.map((m) => {
            const { top, bottom } = resolveFeederMatchups(
              m,
              detail,
              prevStageId,
              treeOpts,
            );
            if (!top || !bottom) return null;
            const y1 = fromPct(fromCol.stageIdx, top.position);
            const y2 = fromPct(fromCol.stageIdx, bottom.position);
            const ym = columnMatchupCenterPct(
              toCol.stageIdx,
              m.position,
              toCol.wingMin,
              toCol.wingMax,
              toCol.positionMin,
              top.position,
              bottom.position,
            );
            const d = mirrored
              ? `M 100 ${y1} H 76 M 100 ${y2} H 76 M 76 ${y1} V ${y2} M 76 ${ym} H 0`
              : `M 0 ${y1} H 24 M 0 ${y2} H 24 M 24 ${y1} V ${y2} M 24 ${ym} H 100`;
            return <path key={m.id} d={d} className="bf-connector-path" />;
          })}
        </svg>
      </div>
    </div>
  );
}

function linearStageColumn(
  stage: BracketStageInfo,
  stageIdx: number,
  leaves: number,
): MirrorBracketColumn {
  const matchupsInStage = leaves / 2 ** stageIdx;
  return {
    key: `linear-${stage.id}`,
    stage,
    stageIdx,
    positionMin: 1,
    positionMax: matchupsInStage,
    side: 'left',
    wingMin: 1,
    // Keep every linear column on the opening-round vertical scale so
    // quarterfinals/semifinals/final align and connectors land correctly.
    wingMax: leaves,
  };
}

function columnCenterFn(col: MirrorBracketColumn): MatchupCenterFn {
  return (stageIdx, position) =>
    columnMatchupCenterPct(
      stageIdx,
      position,
      col.wingMin,
      col.wingMax,
      col.positionMin,
    );
}

function MirrorWing({
  columns,
  detail,
  stages,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
  reverse = false,
}: {
  columns: MirrorBracketColumn[];
  detail: UserBracketDetail;
  stages: BracketStageInfo[];
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
  reverse?: boolean;
}) {
  return (
    <div
      className={
        reverse ? 'bf-board-wing bf-board-wing--right' : 'bf-board-wing'
      }
    >
      {columns.map((col, colIdx) => (
        <Fragment key={col.key}>
          <MirrorBracketStageColumn
            col={col}
            detail={detail}
            stages={stages}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
            onClearWinner={onClearWinner}
          />
          {colIdx < columns.length - 1 ? (
            <ConnectorBetweenStages
              fromCol={columns[colIdx]}
              toCol={columns[colIdx + 1]}
              detail={detail}
              mirrored={reverse}
            />
          ) : null}
        </Fragment>
      ))}
    </div>
  );
}

function SpineConnector({
  col,
  towardCenter,
  targetCenterPct,
}: {
  col: MirrorBracketColumn;
  towardCenter: boolean;
  /** Where the horizontal meets the center column (final matchup). */
  targetCenterPct: number;
}) {
  const ySemi = columnMatchupCenterPct(
    col.stageIdx,
    col.positionMin,
    col.wingMin,
    col.wingMax,
    col.positionMin,
  );
  const yFinal = targetCenterPct;
  const d = towardCenter
    ? `M 0 ${ySemi} H 24 V ${yFinal} H 100`
    : `M 100 ${ySemi} H 76 V ${yFinal} H 0`;
  return (
    <div className="bf-connector-strip" aria-hidden>
      <div className="bf-stage-heading-spacer" />
      <div className="bf-connector-track">
        <svg
          className="bf-connector-svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          <path d={d} className="bf-connector-path" />
        </svg>
      </div>
    </div>
  );
}

function contestantForFeeder(
  m: MatchupInfo,
  feeder: MatchupInfo,
  feeders: { top: MatchupInfo | null; bottom: MatchupInfo | null },
  knockoutStages: BracketStageInfo[],
): BracketContestantInfo | null {
  let slot: BracketContestantInfo | null = null;
  if (m.source_a_matchup_id === feeder.id) slot = m.contestant1;
  else if (m.source_b_matchup_id === feeder.id) slot = m.contestant2;
  else if (feeders.top?.id === feeder.id) slot = m.contestant1;
  else if (feeders.bottom?.id === feeder.id) slot = m.contestant2;

  const currentStage = knockoutStages.find((s) => s.id === m.stage_id);
  const useLoser = currentStage?.knockout?.is_third_place === true;
  if (slot) {
    if (useLoser && !feeder.winner) return null;
    return slot;
  }
  if (!feeder.winner || !feeder.contestant1 || !feeder.contestant2) {
    return null;
  }
  if (useLoser) {
    return feeder.winner.id === feeder.contestant1.id
      ? feeder.contestant2
      : feeder.contestant1;
  }
  if (currentStage?.knockout?.is_final && feeder.winner) {
    return feeder.winner;
  }
  return null;
}

function MirrorBracketStageColumn({
  col,
  detail,
  stages,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
}: {
  col: MirrorBracketColumn;
  detail: UserBracketDetail;
  stages: BracketStageInfo[];
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
}) {
  const { stage, stageIdx, positionMin, positionMax, wingMin, wingMax } = col;
  const isFirst = stageIdx === 0;
  const prevStage = stageIdx > 0 ? stages[stageIdx - 1] : null;
  const treeOpts = { useTreeFeeders: stageUsesTreeFeeders(stage) };
  const matchups = sortMatchupsByFeederOrder(
    matchupsForStage(detail, stage.id).filter(
      (m) => m.position >= positionMin && m.position <= positionMax,
    ),
    detail,
    prevStage?.id ?? null,
    treeOpts,
  );
  const wingSlots = wingMax - wingMin + 1;
  const stageTitle =
    stage.name?.trim() !== ''
      ? stage.name
      : stageIdx === 0
        ? 'Opening round'
        : `Round ${stageIdx + 1}`;

  return (
    <div className="bf-stage-col">
      <p className="bf-stage-title">{stageTitle}</p>
      <div className="bf-stage-track">
        {matchups.map((m) => {
          const feeders = resolveFeederMatchups(
            m,
            detail,
            prevStage?.id ?? null,
            treeOpts,
          );
          const topPct = columnMatchupCenterPct(
            stageIdx,
            m.position,
            wingMin,
            wingMax,
            positionMin,
            feeders.top?.position,
            feeders.bottom?.position,
          );
          const anchorStyle =
            isFirst && wingSlots > 0
              ? {
                  top: `${((m.position - wingMin) / wingSlots) * 100}%`,
                  height: `${100 / wingSlots}%`,
                  transform: 'none' as const,
                }
              : {
                  top: `${topPct}%`,
                  transform: 'translateY(-50%)' as const,
                };
          return (
            <div
              key={m.id}
              className={
                isFirst
                  ? 'bf-matchup-anchor bf-matchup-anchor--band'
                  : 'bf-matchup-anchor'
              }
              style={anchorStyle}
            >
              <MatchupCard
                m={m}
                detail={detail}
                isFirst={isFirst}
                prevStageId={prevStage?.id ?? null}
                knockoutStages={stages}
                showSeeds={showSeeds}
                applyWinner={applyWinner}
                busy={busy}
                onClearWinner={onClearWinner}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function BracketStageColumn({
  stage,
  stageIdx,
  leaves,
  detail,
  stages,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
}: {
  stage: BracketStageInfo;
  stageIdx: number;
  leaves: number;
  detail: UserBracketDetail;
  stages: BracketStageInfo[];
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
}) {
  const isFirst = stageIdx === 0;
  const prevStage = stageIdx > 0 ? stages[stageIdx - 1] : null;
  const treeOpts = { useTreeFeeders: stageUsesTreeFeeders(stage) };
  const matchups = sortMatchupsByFeederOrder(
    matchupsForStage(detail, stage.id),
    detail,
    prevStage?.id ?? null,
    treeOpts,
  );

  const stageTitle =
    stage.name?.trim() !== ''
      ? stage.name
      : stageIdx === 0
        ? 'Opening round'
        : `Round ${stageIdx + 1}`;

  return (
    <div className="bf-stage-col">
      <p className="bf-stage-title">{stageTitle}</p>
      <div className="bf-stage-track">
        {matchups.map((m) => {
          const col = linearStageColumn(stage, stageIdx, leaves);
          const feeders = resolveFeederMatchups(
            m,
            detail,
            prevStage?.id ?? null,
            treeOpts,
          );
          const topPct = columnMatchupCenterPct(
            stageIdx,
            m.position,
            col.wingMin,
            col.wingMax,
            col.positionMin,
            feeders.top?.position,
            feeders.bottom?.position,
          );
          const bandFirst =
            stageIdx === 0 && leaves > 0
              ? {
                  top: `${((m.position - 1) / leaves) * 100}%`,
                  height: `${100 / leaves}%`,
                  transform: 'none' as const,
                }
              : {
                  top: `${topPct}%`,
                  transform: 'translateY(-50%)' as const,
                };
          return (
            <div
              key={m.id}
              className={
                stageIdx === 0
                  ? 'bf-matchup-anchor bf-matchup-anchor--band'
                  : 'bf-matchup-anchor'
              }
              style={bandFirst}
            >
              <MatchupCard
                m={m}
                detail={detail}
                isFirst={isFirst}
                prevStageId={prevStage?.id ?? null}
                knockoutStages={stages}
                showSeeds={showSeeds}
                applyWinner={applyWinner}
                busy={busy}
                onClearWinner={onClearWinner}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SplitCenterColumn({
  finalMatchup,
  thirdPlaceMatchup,
  semiCenterPct,
  finalCenterPct,
  detail,
  knockoutStages,
  allKnockoutStages,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
}: {
  finalMatchup: MatchupInfo;
  thirdPlaceMatchup: MatchupInfo | undefined;
  semiCenterPct: number;
  finalCenterPct: number;
  detail: UserBracketDetail;
  knockoutStages: BracketStageInfo[];
  allKnockoutStages: BracketStageInfo[];
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
}) {
  const finalLive = latestMatchup(detail, finalMatchup);
  const champ = finalLive.winner;
  const thirdLive = thirdPlaceMatchup
    ? latestMatchup(detail, thirdPlaceMatchup)
    : undefined;
  const bronze = thirdLive?.winner;
  const prevStage = prevKnockoutStageBeforeFinal(knockoutStages);
  const finalStage = knockoutStages.find((s) => s.knockout?.is_final);
  const finalTitle =
    finalStage?.name?.trim() ? finalStage.name : 'Final';
  const champTop = Math.max(4, finalCenterPct - SPLIT_CENTER_CHAMP_GAP_PCT);
  const thirdMatchTop = Math.min(
    82,
    semiCenterPct + SPLIT_CENTER_THIRD_MATCH_TOP_PCT,
  );

  return (
    <div className="bf-stage-col bf-stage-col--center">
      <p className="bf-stage-title">{finalTitle}</p>
      <div className="bf-stage-track bf-center-track">
        <div
          className="bf-center-slot bf-center-slot--champion"
          style={{ top: `${champTop}%` }}
        >
          <div className="bf-center-slot-anchor bf-center-slot-anchor--up">
            <div className="bf-center-slot-stack">
              <p className="bf-stage-title">Champion</p>
              {champ ? (
                <WinnerRevealBox
                  contestant={champ}
                  showSeeds={showSeeds}
                  busy={busy}
                  onClear={
                    onClearWinner
                      ? () => void onClearWinner(finalLive.id)
                      : undefined
                  }
                  clearLabel="Remove champion pick"
                />
              ) : (
                <div className="bf-champion-box" aria-label="Champion" />
              )}
            </div>
          </div>
        </div>

        <div
          className="bf-center-slot bf-center-slot--final"
          style={{ top: `${finalCenterPct}%` }}
        >
          <div className="bf-center-matchup-wrap">
            <MatchupCard
              m={finalLive}
              detail={detail}
              isFirst={false}
              prevStageId={prevStage?.id ?? null}
              knockoutStages={allKnockoutStages}
              showSeeds={showSeeds}
              applyWinner={applyWinner}
              busy={busy}
              onClearWinner={onClearWinner}
            />
          </div>
        </div>

        {thirdLive ? (
          <div
            className="bf-center-slot bf-center-slot--third"
            style={{ top: `${thirdMatchTop}%` }}
          >
            <div className="bf-center-third-above">
              <div className="bf-center-slot-stack bf-center-slot-stack--third">
                <p className="bf-stage-title">3rd place</p>
                <ThirdPlaceWinnerSlot
                  contestant={bronze}
                  showSeeds={showSeeds}
                  busy={busy}
                  onClear={
                    onClearWinner
                      ? () => void onClearWinner(thirdLive.id)
                      : undefined
                  }
                />
              </div>
            </div>
            <div className="bf-center-third-match">
              <MatchupCard
                m={thirdLive}
                detail={detail}
                isFirst={false}
                prevStageId={prevStage?.id ?? null}
                knockoutStages={allKnockoutStages}
                showSeeds={showSeeds}
                applyWinner={applyWinner}
                busy={busy}
                onClearWinner={onClearWinner}
              />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ChampionColumn({
  finalMatchup,
  thirdPlaceMatchup,
  detail,
  knockoutStages,
  allKnockoutStages,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
}: {
  finalMatchup: MatchupInfo;
  thirdPlaceMatchup: MatchupInfo | undefined;
  detail: UserBracketDetail;
  knockoutStages: BracketStageInfo[];
  allKnockoutStages: BracketStageInfo[];
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
}) {
  const finalLive = latestMatchup(detail, finalMatchup);
  const champ = finalLive.winner;
  const thirdLive = thirdPlaceMatchup
    ? latestMatchup(detail, thirdPlaceMatchup)
    : undefined;
  const bronze = thirdLive?.winner;
  const prevStage = prevKnockoutStageBeforeFinal(knockoutStages);

  return (
    <div className="bf-stage-col bf-stage-col--champion">
      <div className="bf-champion-stack">
        <div className="bf-champion-middle">
          <p className="bf-stage-title">Champion</p>
          <div className="bf-champion-box-wrap">
            <div className="bf-center-slot-stack">
              {champ ? (
                <WinnerRevealBox
                  contestant={champ}
                  showSeeds={showSeeds}
                  busy={busy}
                  onClear={
                    onClearWinner
                      ? () => void onClearWinner(finalLive.id)
                      : undefined
                  }
                  clearLabel="Remove champion pick"
                />
              ) : (
                <div className="bf-champion-box" aria-label="Champion" />
              )}
            </div>
          </div>
        </div>
        {thirdLive ? (
          <div className="bf-third-place-section bf-third-place-section--stacked">
            <div className="bf-center-third-above">
              <div className="bf-center-slot-stack bf-center-slot-stack--third">
                <p className="bf-stage-title">3rd place</p>
                <ThirdPlaceWinnerSlot
                  contestant={bronze}
                  showSeeds={showSeeds}
                  busy={busy}
                  onClear={
                    onClearWinner
                      ? () => void onClearWinner(thirdLive.id)
                      : undefined
                  }
                />
              </div>
            </div>
            <div className="bf-center-third-match">
              <MatchupCard
                m={thirdLive}
                detail={detail}
                isFirst={false}
                prevStageId={prevStage?.id ?? null}
                knockoutStages={allKnockoutStages}
                showSeeds={showSeeds}
                applyWinner={applyWinner}
                busy={busy}
                onClearWinner={onClearWinner}
              />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function MatchupCard({
  m,
  detail,
  isFirst,
  prevStageId,
  knockoutStages,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
}: {
  m: MatchupInfo;
  detail: UserBracketDetail;
  isFirst: boolean;
  prevStageId: number | null;
  knockoutStages: BracketStageInfo[];
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
}) {
  const stageInfo = knockoutStages.find((s) => s.id === m.stage_id);
  const entry = useKnockoutEntry();
  const legsCount = Math.min(2, Math.max(1, stageInfo?.knockout?.number_of_legs ?? 1));
  const scoreMode = entry.mode === 'score';
  const feeders = resolveFeederMatchups(m, detail, prevStageId, {
    useTreeFeeders: stageUsesTreeFeeders(stageInfo),
  });
  const { top: feederTop, bottom: feederBot } = feeders;
  const isThirdPlace = stageInfo?.knockout?.is_third_place === true;
  const contestantTop =
    feederTop != null
      ? contestantForFeeder(m, feederTop, feeders, knockoutStages)
      : m.contestant1;
  const contestantBot =
    feederBot != null
      ? contestantForFeeder(m, feederBot, feeders, knockoutStages)
      : m.contestant2;
  const labelTop =
    feederTop != null
      ? feederDropLabel(feederTop, knockoutStages, m)
      : '';
  const labelBot =
    feederBot != null
      ? feederDropLabel(feederBot, knockoutStages, m)
      : '';
  const showLaterRound =
    !isFirst &&
    (feederTop != null ||
      feederBot != null ||
      contestantTop != null ||
      contestantBot != null);

  const teamTop = isFirst ? m.contestant1 : contestantTop;
  const teamBot = isFirst ? m.contestant2 : contestantBot;

  if (scoreMode) {
    return (
      <div className="bf-matchup bf-matchup--scores">
        <MatchupScoreBlock
          matchup={m}
          teamTop={teamTop}
          teamBot={teamBot}
          emptyTop={isFirst ? undefined : labelTop}
          emptyBot={isFirst ? undefined : labelBot}
          legsCount={legsCount}
          showSeeds={showSeeds}
          busy={busy || entry.locked}
          readOnly={entry.locked}
          onSaveLegs={(legs, winnerId) =>
            void entry.applyScores(m.id, legs, winnerId)
          }
          onPickWinner={
            entry.locked
              ? undefined
              : (contestantId) => void entry.applyWinner(m.id, contestantId)
          }
          onClearWinner={
            onClearWinner && m.winner
              ? () => void onClearWinner(m.id)
              : undefined
          }
        />
        <NextMatchToggle matchup={m} />
      </div>
    );
  }

  return (
    <div className="bf-matchup">
      {showLaterRound ? (
        <>
          <LaterRoundSlot
            contestant={contestantTop}
            currentMatchup={m}
            feeder={feederTop}
            otherContestantId={contestantBot?.id}
            winnerId={m.winner?.id}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
            onClearWinner={onClearWinner}
            emptyLabel={labelTop}
            allowSlotClear={!isThirdPlace}
          />
          <LaterRoundSlot
            contestant={contestantBot}
            currentMatchup={m}
            feeder={feederBot}
            otherContestantId={contestantTop?.id}
            winnerId={m.winner?.id}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
            onClearWinner={onClearWinner}
            emptyLabel={labelBot}
            allowSlotClear={!isThirdPlace}
          />
        </>
      ) : null}

      {isFirst ? (
        <>
          <ContestantOnly
            label={m.contestant1}
            matchupId={m.id}
            stageId={m.stage_id}
            winnerId={m.winner?.id}
            otherId={m.contestant2?.id}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
            onClearWinner={onClearWinner}
          />
          <ContestantOnly
            label={m.contestant2}
            matchupId={m.id}
            stageId={m.stage_id}
            winnerId={m.winner?.id}
            otherId={m.contestant1?.id}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
            onClearWinner={onClearWinner}
          />
        </>
      ) : null}

      <NextMatchToggle matchup={m} />
    </div>
  );
}

function MatchupScoreBlock({
  matchup,
  teamTop,
  teamBot,
  emptyTop,
  emptyBot,
  legsCount,
  showSeeds,
  busy,
  readOnly,
  onSaveLegs,
  onPickWinner,
  onClearWinner,
}: {
  matchup: MatchupInfo;
  teamTop: BracketContestantInfo | null | undefined;
  teamBot: BracketContestantInfo | null | undefined;
  emptyTop?: string;
  emptyBot?: string;
  legsCount: number;
  showSeeds: boolean;
  busy: boolean;
  readOnly: boolean;
  onSaveLegs: (
    legs: Array<[number | null, number | null]>,
    winnerId?: number | null,
  ) => void;
  onPickWinner?: (contestantId: number) => void;
  onClearWinner?: () => void;
}) {
  const initialLegs = useMemo(() => {
    const fromServer = matchup.scores?.legs;
    const base: Array<[number | null, number | null]> = Array.from(
      { length: legsCount },
      (_, i) => {
        const pair = fromServer?.[i];
        if (pair && pair.length >= 2) {
          return [pair[0] ?? null, pair[1] ?? null];
        }
        return [null, null];
      },
    );
    return base;
  }, [matchup.scores?.legs, legsCount, matchup.id]);

  const [legs, setLegs] = useState(initialLegs);
  useEffect(() => {
    setLegs(initialLegs);
  }, [initialLegs]);

  const allLegsComplete = legs.every(([a, b]) => a != null && b != null);
  const computed = (() => {
    let t1 = 0;
    let t2 = 0;
    let any = false;
    for (const [a, b] of legs) {
      if (a == null || b == null) continue;
      any = true;
      t1 += a;
      t2 += b;
    }
    return any ? ([t1, t2] as const) : ([null, null] as const);
  })();
  const scoresTied =
    allLegsComplete &&
    computed[0] != null &&
    computed[1] != null &&
    computed[0] === computed[1];
  const canPickWinner =
    !readOnly &&
    !busy &&
    scoresTied &&
    teamTop != null &&
    teamBot != null &&
    onPickWinner != null;

  function setCell(legIdx: number, side: 0 | 1, raw: string) {
    const trimmed = raw.trim();
    const val =
      trimmed === ''
        ? null
        : Number.isFinite(Number(trimmed))
          ? Math.max(0, Math.min(99, parseInt(trimmed, 10)))
          : null;
    setLegs((prev) =>
      prev.map((pair, i) => {
        if (i !== legIdx) return pair;
        const next: [number | null, number | null] = [...pair];
        next[side] = val;
        return next;
      }),
    );
  }

  function commit() {
    const complete = legs.every(([a, b]) => a != null && b != null);
    let t1 = 0;
    let t2 = 0;
    if (complete) {
      for (const [a, b] of legs) {
        t1 += a as number;
        t2 += b as number;
      }
    }
    const tied = complete && t1 === t2;
    // Keep a host-picked winner when re-saving a still-tied scoreline.
    const serverLegs = matchup.scores?.legs;
    const serverWasTied =
      Array.isArray(serverLegs) &&
      serverLegs.length === legsCount &&
      serverLegs.every(
        (pair) =>
          pair != null &&
          pair.length >= 2 &&
          pair[0] != null &&
          pair[1] != null,
      ) &&
      (() => {
        let s1 = 0;
        let s2 = 0;
        for (const pair of serverLegs) {
          s1 += pair[0] as number;
          s2 += pair[1] as number;
        }
        return s1 === s2;
      })();
    if (tied && serverWasTied && matchup.winner?.id != null) {
      onSaveLegs(legs, matchup.winner.id);
      return;
    }
    onSaveLegs(legs);
  }

  const winnerId = matchup.winner?.id;
  const hasScoreEntry = legs.some(
    ([a, b]) => a != null || b != null,
  );
  // Clear-X is for winner-only picks. With scores entered, edit/clear via the
  // score cells instead — the × was colliding with the inputs.
  const clearWinnerIfScoreless =
    !hasScoreEntry && onClearWinner != null ? onClearWinner : undefined;

  return (
    <div className="bf-score-match">
      <MatchupScoreRow
        contestant={teamTop ?? null}
        emptyLabel={emptyTop || 'TBD'}
        side={0}
        legs={legs}
        total={computed[0]}
        isWinner={winnerId != null && teamTop?.id === winnerId}
        showSeeds={showSeeds}
        busy={busy}
        readOnly={readOnly || !teamTop || !teamBot}
        canPick={canPickWinner}
        onPick={
          canPickWinner && teamTop
            ? () => onPickWinner(teamTop.id)
            : undefined
        }
        onChange={setCell}
        onBlurCommit={commit}
        onClear={
          winnerId != null && teamTop?.id === winnerId
            ? clearWinnerIfScoreless
            : undefined
        }
      />
      <MatchupScoreRow
        contestant={teamBot ?? null}
        emptyLabel={emptyBot || 'TBD'}
        side={1}
        legs={legs}
        total={computed[1]}
        isWinner={winnerId != null && teamBot?.id === winnerId}
        showSeeds={showSeeds}
        busy={busy}
        readOnly={readOnly || !teamTop || !teamBot}
        canPick={canPickWinner}
        onPick={
          canPickWinner && teamBot
            ? () => onPickWinner(teamBot.id)
            : undefined
        }
        onChange={setCell}
        onBlurCommit={commit}
        onClear={
          winnerId != null && teamBot?.id === winnerId
            ? clearWinnerIfScoreless
            : undefined
        }
      />
    </div>
  );
}

function MatchupScoreRow({
  contestant,
  emptyLabel,
  side,
  legs,
  total,
  isWinner,
  showSeeds,
  busy,
  readOnly,
  canPick,
  onPick,
  onChange,
  onBlurCommit,
  onClear,
}: {
  contestant: BracketContestantInfo | null;
  emptyLabel: string;
  side: 0 | 1;
  legs: Array<[number | null, number | null]>;
  total: number | null;
  isWinner: boolean;
  showSeeds: boolean;
  busy: boolean;
  readOnly: boolean;
  canPick?: boolean;
  onPick?: () => void;
  onChange: (legIdx: number, side: 0 | 1, raw: string) => void;
  onBlurCommit: () => void;
  onClear?: () => void;
}) {
  if (!contestant) {
    const singleLeg = legs.length === 1;
    return (
      <div className="bf-slot bf-slot--empty bf-score-row">
        <span className="bf-score-row__name">{emptyLabel}</span>
        <div className="bf-score-row__cols" aria-hidden>
          {singleLeg ? (
            <span className="bf-score-total">—</span>
          ) : (
            <>
              {legs.map((_, i) => (
                <span key={i} className="bf-score-leg">
                  —
                </span>
              ))}
              <span className="bf-score-total">—</span>
            </>
          )}
        </div>
      </div>
    );
  }

  const singleLeg = legs.length === 1;

  return (
    <div
      className={[
        'bf-slot',
        'bf-score-row',
        isWinner ? 'bf-score-row--winner' : '',
        canPick ? 'bf-score-row--pickable' : '',
        onClear ? 'bf-slot--with-clear' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="bf-score-row__team">
        {onPick ? (
          <button
            type="button"
            className={[
              'bf-score-row__pick',
              isWinner ? 'bf-score-row__pick--winner' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            disabled={busy}
            onClick={() => onPick()}
            aria-label={`${contestant.display_name}, pick to advance`}
          >
            <MatchupContestantFace
              contestant={contestant}
              showSeed={showSeeds}
            />
          </button>
        ) : (
          <MatchupContestantFace contestant={contestant} showSeed={showSeeds} />
        )}
        {onClear ? (
          <button
            type="button"
            className="bf-pick-clear"
            disabled={busy}
            onClick={() => onClear()}
            aria-label="Remove result"
          >
            ×
          </button>
        ) : null}
      </div>
      <div className="bf-score-row__cols">
        {singleLeg ? (
          <input
            className="bf-score-total bf-score-total--input"
            inputMode="numeric"
            maxLength={2}
            value={legs[0]?.[side] ?? ''}
            disabled={busy || readOnly}
            aria-label={`Score for ${contestant.display_name}`}
            onChange={(e) => onChange(0, side, e.target.value)}
            onBlur={onBlurCommit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                (e.target as HTMLInputElement).blur();
              }
            }}
          />
        ) : (
          <>
            {legs.map((pair, legIdx) => (
              <input
                key={legIdx}
                className="bf-score-leg"
                inputMode="numeric"
                maxLength={2}
                value={pair[side] ?? ''}
                disabled={busy || readOnly}
                aria-label={`Leg ${legIdx + 1} score for ${contestant.display_name}`}
                onChange={(e) => onChange(legIdx, side, e.target.value)}
                onBlur={onBlurCommit}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    (e.target as HTMLInputElement).blur();
                  }
                }}
              />
            ))}
            <span className="bf-score-total" aria-label="Total">
              {total == null ? '—' : total}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

/** First round: click a team to pick the winner of this game. */
function ContestantOnly({
  label,
  matchupId,
  stageId,
  winnerId,
  otherId,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
}: {
  label: BracketContestantInfo | null;
  matchupId: number;
  stageId: number;
  winnerId: number | undefined;
  otherId: number | undefined;
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
}) {
  if (!label) {
    return (
      <div className="bf-slot bf-slot--empty" aria-label={otherId != null ? 'Bye' : 'Empty slot'}>
        {otherId != null ? 'Bye' : 'TBD'}
      </div>
    );
  }
  const isWinner =
    winnerId != null && winnerId === label.id && otherId != null;
  const showClear = isWinner && onClearWinner != null;
  const scoring = useScoringHighlight();
  const scored = scoring?.isKnockoutScored(stageId, label.id) ?? false;

  return (
    <div
      className={showClear ? 'bf-slot bf-slot--with-clear' : 'bf-slot'}
    >
      <button
        type="button"
        className={[
          'bf-chip',
          'bf-chip--ko',
          isWinner ? 'bf-chip--winner' : '',
          scored ? 'bf-chip--scored' : '',
        ]
          .filter(Boolean)
          .join(' ')}
        disabled={busy}
        onClick={() => void applyWinner(matchupId, label.id)}
        aria-label={`${label.display_name}, pick to advance`}
      >
        {scored ? <ScoredMark /> : null}
        <MatchupContestantFace contestant={label} showSeed={showSeeds} />
      </button>
      {showClear ? (
        <button
          type="button"
          className="bf-pick-clear"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation();
            void onClearWinner(matchupId);
          }}
          aria-label="Remove pick"
        >
          ×
        </button>
      ) : null}
    </div>
  );
}

/** One slot in a later-round matchup (feeder-linked or direct contestant). */
function LaterRoundSlot({
  contestant,
  currentMatchup,
  feeder,
  otherContestantId,
  winnerId,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
  emptyLabel,
  allowSlotClear = true,
}: {
  contestant: BracketContestantInfo | null;
  currentMatchup: MatchupInfo;
  feeder: MatchupInfo | null;
  otherContestantId: number | undefined;
  winnerId: number | undefined;
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
  emptyLabel: string;
  allowSlotClear?: boolean;
}) {
  if (!feeder) {
    if (!contestant) {
      return (
        <div className="bf-slot bf-slot--pending">
          <span className="bf-slot--empty">{emptyLabel || 'TBD'}</span>
        </div>
      );
    }
    return (
      <ContestantOnly
        label={contestant}
        matchupId={currentMatchup.id}
        stageId={currentMatchup.stage_id}
        winnerId={winnerId}
        otherId={otherContestantId}
        showSeeds={showSeeds}
        applyWinner={applyWinner}
        busy={busy}
        onClearWinner={onClearWinner}
      />
    );
  }

  return (
    <ReceiveOrPick
      contestant={contestant}
      currentMatchupId={currentMatchup.id}
      currentMatchup={currentMatchup}
      feeder={feeder}
      otherContestantId={otherContestantId}
      winnerId={winnerId}
      showSeeds={showSeeds}
      applyWinner={applyWinner}
      busy={busy}
      onClearWinner={onClearWinner}
      emptyLabel={emptyLabel}
      allowSlotClear={allowSlotClear}
    />
  );
}

/** Later rounds: empty slot waits for the listed feeder; click a team to pick this game’s winner. */
function ReceiveOrPick({
  contestant,
  currentMatchupId,
  currentMatchup,
  feeder,
  otherContestantId,
  winnerId,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
  emptyLabel,
  allowSlotClear = true,
}: {
  contestant: BracketContestantInfo | null;
  currentMatchupId: number;
  currentMatchup: MatchupInfo;
  feeder: MatchupInfo;
  otherContestantId: number | undefined;
  winnerId: number | undefined;
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner?: (matchupId: number) => void;
  emptyLabel: string;
  allowSlotClear?: boolean;
}) {
  if (!contestant) {
    return (
      <div className="bf-slot bf-slot--pending">
        <span className="bf-slot--empty">{emptyLabel}</span>
      </div>
    );
  }

  const isWinner =
    winnerId != null &&
    winnerId === contestant.id &&
    otherContestantId != null;

  // × clears the prior-round pick that advanced this team here, not this round's winner.
  const clearMatchupId =
    onClearWinner != null && allowSlotClear && feeder.winner != null
      ? feeder.id
      : null;

  const canPickThisGame = otherContestantId != null;
  const scoring = useScoringHighlight();
  const scored =
    scoring?.isKnockoutScored(currentMatchup.stage_id, contestant.id) ?? false;

  return (
    <div
      className={
        clearMatchupId != null ? 'bf-slot bf-slot--with-clear' : 'bf-slot'
      }
    >
      <button
        type="button"
        className={[
          'bf-chip',
          'bf-chip--ko',
          isWinner ? 'bf-chip--winner' : '',
          scored ? 'bf-chip--scored' : '',
        ]
          .filter(Boolean)
          .join(' ')}
        disabled={busy || !canPickThisGame}
        onClick={() => void applyWinner(currentMatchupId, contestant.id)}
        aria-label={`${contestant.display_name}, pick to advance`}
      >
        {scored ? <ScoredMark /> : null}
        <MatchupContestantFace contestant={contestant} showSeed={showSeeds} />
      </button>
      {clearMatchupId != null && onClearWinner ? (
        <button
          type="button"
          className="bf-pick-clear"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation();
            void onClearWinner(clearMatchupId);
          }}
          aria-label="Remove pick"
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
