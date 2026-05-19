import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ApiError,
  type BracketContestantInfo,
  type BracketDetail,
  type BracketStageInfo,
  type MatchupInfo,
  type UserBracketDetail,
  getBracket,
  getUserBracket,
  patchMatchupWinner,
  submitUserBracket,
} from '../../utils/api';
import { GroupStagePanel } from './GroupStagePanel';
import {
  buildMirrorBracketLayout,
  columnMatchupCenterPct,
  type MirrorBracketColumn,
} from './bracketMirrorLayout';
import './BracketFill.css';

function sortStages(stages: BracketStageInfo[]) {
  return [...stages].sort((a, b) => a.order - b.order);
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

function feederWinnerDropLabel(
  feeder: MatchupInfo,
  knockoutStages: BracketStageInfo[],
): string {
  const stage = knockoutStages.find((s) => s.id === feeder.stage_id);
  if (!stage) return `Game ${feeder.position} Winner`;
  const prefix = stageShortPrefix(stage);
  const gamesInStage = Math.max(1, stage.number_of_contestants / 2);
  if (gamesInStage <= 1) {
    return `${prefix} Winner`;
  }
  return `${prefix} Winner ${feeder.position}`;
}

function MatchupContestantFace({
  contestant,
  showSeed,
}: {
  contestant: BracketContestantInfo;
  showSeed: boolean;
}) {
  return (
    <>
      {contestant.image_url ? (
        <img className="bf-ko-img" src={contestant.image_url} alt="" />
      ) : (
        <span className="bf-ko-img bf-ko-img--ph" aria-hidden>
          {contestant.display_name.charAt(0)}
        </span>
      )}
      <span className="bf-ko-name">{contestant.display_name}</span>
      {showSeed && contestant.seed != null ? (
        <span className="bf-ko-seed">#{contestant.seed}</span>
      ) : null}
    </>
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
  readOnly?: boolean;
  allowMasterEdit?: boolean;
  showSubmit?: boolean;
  onSubmitted?: () => void;
};

export function BracketFill({
  userBracketId,
  readOnly = false,
  allowMasterEdit = false,
  showSubmit = false,
  onSubmitted,
}: Props) {
  const [detail, setDetail] = useState<UserBracketDetail | null>(null);
  const [bracketDef, setBracketDef] = useState<BracketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [phase, setPhase] = useState<'groups' | 'knockout'>('knockout');
  const phaseInitForUb = useRef<number | null>(null);

  const goToPhase = useCallback((next: 'groups' | 'knockout') => {
    setPhase((current) => {
      if (current === next) return current;
      return next;
    });
  }, []);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { user_bracket: ub } = await getUserBracket(userBracketId);
      const { bracket: b } = await getBracket(ub.bracket_id);
      setDetail(ub);
      setBracketDef(b);
    } catch (e) {
      setDetail(null);
      setBracketDef(null);
      setError(
        e instanceof ApiError ? e.message : 'Could not load bracket.',
      );
    }
  }, [userBracketId]);

  useEffect(() => {
    void load();
  }, [load]);

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
    (bracketDef.metadata as { tournament_type?: string }).tournament_type ===
      'world_cup_2026';

  const firstGroupStage = groupStages[0];

  useEffect(() => {
    if (!hasGroupUi) return;
    if (phaseInitForUb.current === userBracketId) return;
    phaseInitForUb.current = userBracketId;
    setPhase('groups');
  }, [hasGroupUi, userBracketId]);

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
    return Math.max(560, leaves * 160);
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

  const locked = readOnly || (detail != null && !detail.can_edit);

  const applyWinner = useCallback(
    async (feederMatchupId: number, contestantId: number) => {
      if (locked) return;
      setBusy(true);
      setError(null);
      try {
        await patchMatchupWinner(feederMatchupId, contestantId);
        await load();
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not save pick.');
      } finally {
        setBusy(false);
      }
    },
    [load, locked],
  );

  const clearWinner = useCallback(
    async (matchupId: number) => {
      if (locked) return;
      setBusy(true);
      setError(null);
      try {
        await patchMatchupWinner(matchupId, null);
        await load();
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not clear pick.');
      } finally {
        setBusy(false);
      }
    },
    [load, locked],
  );

  async function handleSubmit() {
    if (locked || !detail) return;
    setSubmitBusy(true);
    setError(null);
    try {
      await submitUserBracket(userBracketId);
      await load();
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

  if (detail.is_master && !allowMasterEdit) {
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
      <div className="bf-scroll">
        {mirrorLayout ? (
          <div className="bf-board-split">
            <MirrorWing
              columns={mirrorLayout.left}
              detail={detail}
              stages={knockoutStagesMain}
              showSeeds={showSeeds}
              applyWinner={applyWinner}
              busy={busy || locked}
              onClearWinner={clearWinner}
            />
            {mirrorLayout.center && finalMatchup ? (
              <>
                <SpineConnector
                  col={mirrorLayout.left[mirrorLayout.left.length - 1]}
                  towardCenter
                />
                <SplitCenterColumn
                  finalMatchup={finalMatchup}
                  thirdPlaceMatchup={thirdPlaceMatchup}
                  finalCenterPct={columnMatchupCenterPct(
                    mirrorLayout.left[mirrorLayout.left.length - 1].stageIdx,
                    mirrorLayout.left[mirrorLayout.left.length - 1].positionMin,
                    mirrorLayout.left[mirrorLayout.left.length - 1].wingMin,
                    mirrorLayout.left[mirrorLayout.left.length - 1].wingMax,
                    mirrorLayout.left[mirrorLayout.left.length - 1].positionMin,
                  )}
                  detail={detail}
                  knockoutStages={knockoutStagesMain}
                  showSeeds={showSeeds}
                  applyWinner={applyWinner}
                  busy={busy || locked}
                  onClearWinner={clearWinner}
                />
                <SpineConnector
                  col={mirrorLayout.right[mirrorLayout.right.length - 1]}
                  towardCenter
                />
              </>
            ) : null}
            <MirrorWing
              columns={mirrorLayout.right}
              detail={detail}
              stages={knockoutStagesMain}
              showSeeds={showSeeds}
              applyWinner={applyWinner}
              busy={busy || locked}
              onClearWinner={clearWinner}
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
                  busy={busy || locked}
                  onClearWinner={clearWinner}
                />
                {stageIdx < knockoutStagesMain.length - 1 ? (
                  <ConnectorBetweenStages
                    stageIdx={stageIdx}
                    leaves={leaves}
                    pairCount={
                      matchupsForStage(
                        detail,
                        knockoutStagesMain[stageIdx + 1].id,
                      ).length
                    }
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
                showSeeds={showSeeds}
                applyWinner={applyWinner}
                busy={busy || locked}
                onClearWinner={clearWinner}
              />
            ) : null}
          </div>
        )}
      </div>
    ) : (
      <p className="bf-meta bf-knockout-placeholder">
        Knockout pairings will fill in here as matchups are available.
      </p>
    );

  return (
    <section
      className={mirrorLayout ? 'bf bf--split-knockout' : 'bf'}
      aria-busy={busy}
      style={
        {
          '--bf-board-h': `${boardHeightPx}px`,
        } as React.CSSProperties
      }
    >
      <h2>{detail.bracket.name}</h2>
      {error ? <p className="bf-error">{error}</p> : null}

      {(hasGroupUi && firstGroupStage) || (showSubmit && !locked) ? (
        <div className="bf-toolbar">
          {hasGroupUi && firstGroupStage ? (
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
          {showSubmit && !locked ? (
            <button
              type="button"
              className="btn btn--primary bf-toolbar__submit"
              disabled={
                submitBusy ||
                busy ||
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
      ) : null}

      {hasGroupUi && firstGroupStage ? (
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
                initialMetadata={{
                  group_positions: meta.group_positions ?? {},
                  third_place_advancers: meta.third_place_advancers ?? [],
                }}
                busy={busy || locked}
                readOnly={locked}
                onSaved={load}
                onError={(msg) => setError(msg || null)}
                setBusy={setBusy}
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
      ) : (
        knockoutBoard
      )}

    </section>
  );
}

type MatchupCenterFn = (stageIdx: number, position: number) => number;

function ConnectorBetweenStages({
  stageIdx,
  leaves,
  pairCount,
  feederPositionMin = 1,
  centerPct,
  mirrored = false,
}: {
  stageIdx: number;
  leaves: number;
  pairCount: number;
  feederPositionMin?: number;
  centerPct?: MatchupCenterFn;
  mirrored?: boolean;
}) {
  const pct: MatchupCenterFn =
    centerPct ?? ((s, pos) => matchupCenterPct(s, pos, leaves));

  return (
    <div className="bf-connector-strip" aria-hidden>
      <div className="bf-stage-heading-spacer" />
      <div className="bf-connector-track">
        <svg
          className="bf-connector-svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {Array.from({ length: pairCount }, (_, idx) => {
            const feedA = feederPositionMin + 2 * idx;
            const feedB = feedA + 1;
            const y1 = pct(stageIdx, feedA);
            const y2 = pct(stageIdx, feedB);
            const ym = (y1 + y2) / 2;
            const d = mirrored
              ? `M 100 ${y1} H 76 M 100 ${y2} H 76 M 76 ${y1} V ${y2} M 76 ${ym} H 0`
              : `M 0 ${y1} H 24 M 0 ${y2} H 24 M 24 ${y1} V ${y2} M 24 ${ym} H 100`;
            return <path key={idx} d={d} className="bf-connector-path" />;
          })}
        </svg>
      </div>
    </div>
  );
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
  onClearWinner: (matchupId: number) => void;
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
              stageIdx={columns[colIdx].stageIdx}
              leaves={0}
              pairCount={
                columns[colIdx + 1].positionMax -
                columns[colIdx + 1].positionMin +
                1
              }
              feederPositionMin={columns[colIdx].positionMin}
              centerPct={columnCenterFn(columns[colIdx])}
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
}: {
  col: MirrorBracketColumn;
  towardCenter: boolean;
}) {
  const y = columnMatchupCenterPct(
    col.stageIdx,
    col.positionMin,
    col.wingMin,
    col.wingMax,
    col.positionMin,
  );
  const d = towardCenter ? `M 0 ${y} H 100` : `M 100 ${y} H 0`;
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

function findMatchupById(
  detail: UserBracketDetail,
  matchupId: number,
): MatchupInfo | undefined {
  for (const pack of detail.matchups_by_stage) {
    const found = pack.matchups.find((m) => m.id === matchupId);
    if (found) return found;
  }
  return undefined;
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
  onClearWinner: (matchupId: number) => void;
}) {
  const { stage, stageIdx, positionMin, positionMax, wingMin, wingMax } = col;
  const matchups = matchupsForStage(detail, stage.id).filter(
    (m) => m.position >= positionMin && m.position <= positionMax,
  );

  const isFirst = stageIdx === 0;
  const prevStage = stageIdx > 0 ? stages[stageIdx - 1] : null;
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
          const topPct = columnMatchupCenterPct(
            stageIdx,
            m.position,
            wingMin,
            wingMax,
            positionMin,
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
  onClearWinner: (matchupId: number) => void;
}) {
  const matchups = matchupsForStage(detail, stage.id);
  const isFirst = stageIdx === 0;
  const prevStage = stageIdx > 0 ? stages[stageIdx - 1] : null;

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
          const topPct = matchupCenterPct(stageIdx, m.position, leaves);
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

/** Split bracket center: champion above final, aligned with semifinal row. */
const SPLIT_CENTER_CHAMP_GAP_PCT = 14;
const SPLIT_CENTER_THIRD_GAP_PCT = 18;

function SplitCenterColumn({
  finalMatchup,
  thirdPlaceMatchup,
  finalCenterPct,
  detail,
  knockoutStages,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
}: {
  finalMatchup: MatchupInfo;
  thirdPlaceMatchup: MatchupInfo | undefined;
  finalCenterPct: number;
  detail: UserBracketDetail;
  knockoutStages: BracketStageInfo[];
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner: (matchupId: number) => void;
}) {
  const champ = finalMatchup.winner;
  const finalIdx = knockoutStages.findIndex((s) => s.knockout?.is_final);
  const prevStage =
    finalIdx > 0 ? knockoutStages[finalIdx - 1] : null;
  const champTop = Math.max(4, finalCenterPct - SPLIT_CENTER_CHAMP_GAP_PCT);
  const thirdTop = Math.min(96, finalCenterPct + SPLIT_CENTER_THIRD_GAP_PCT);

  return (
    <div className="bf-stage-col bf-stage-col--center">
      <p className="bf-stage-title">Final</p>
      <div className="bf-stage-track bf-center-track">
        <div
          className="bf-center-slot bf-center-slot--champion"
          style={{ top: `${champTop}%` }}
        >
          <p className="bf-stage-title bf-center-slot-label">Champion</p>
          <div className="bf-center-matchup-wrap bf-center-matchup-wrap--up">
            <div className="bf-champion-box">
              {champ ? (
                <>
                  <button
                    type="button"
                    className="bf-pick-clear bf-pick-clear--champion"
                    disabled={busy}
                    onClick={(e) => {
                      e.stopPropagation();
                      void onClearWinner(finalMatchup.id);
                    }}
                    aria-label="Remove champion pick"
                  >
                    ×
                  </button>
                  <MatchupContestantFace contestant={champ} showSeed={showSeeds} />
                </>
              ) : (
                <span className="bf-champion-placeholder">Champion</span>
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
              m={finalMatchup}
              detail={detail}
              isFirst={false}
              prevStageId={prevStage?.id ?? null}
              knockoutStages={knockoutStages}
              showSeeds={showSeeds}
              applyWinner={applyWinner}
              busy={busy}
              onClearWinner={onClearWinner}
            />
          </div>
        </div>

        {thirdPlaceMatchup ? (
          <div
            className="bf-center-slot bf-center-slot--third"
            style={{ top: `${thirdTop}%` }}
          >
            <p className="bf-stage-title bf-center-slot-label">Third place</p>
            <div className="bf-center-matchup-wrap">
              <MatchupCard
                m={thirdPlaceMatchup}
                detail={detail}
                isFirst={false}
                prevStageId={
                  knockoutStages.find((s) => s.knockout?.is_final)?.id ?? null
                }
                knockoutStages={knockoutStages}
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
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
}: {
  finalMatchup: MatchupInfo;
  thirdPlaceMatchup: MatchupInfo | undefined;
  detail: UserBracketDetail;
  knockoutStages: BracketStageInfo[];
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner: (matchupId: number) => void;
}) {
  const champ = finalMatchup.winner;

  return (
    <div className="bf-stage-col bf-stage-col--champion">
      <div className="bf-champion-stack">
        <div className="bf-champion-middle">
          <p className="bf-stage-title">Champion</p>
          <div className="bf-champion-box-wrap">
            <div className="bf-champion-box">
              {champ ? (
                <>
                  <button
                    type="button"
                    className="bf-pick-clear bf-pick-clear--champion"
                    disabled={busy}
                    onClick={(e) => {
                      e.stopPropagation();
                      void onClearWinner(finalMatchup.id);
                    }}
                    aria-label="Remove champion pick"
                  >
                    ×
                  </button>
                  <MatchupContestantFace contestant={champ} showSeed={showSeeds} />
                </>
              ) : (
                <span className="bf-champion-placeholder">Champion</span>
              )}
            </div>
          </div>
        </div>
        {thirdPlaceMatchup ? (
          <div className="bf-third-place-section">
            <p className="bf-stage-title">Third place</p>
            <div className="bf-third-place-match">
              <MatchupCard
                m={thirdPlaceMatchup}
                detail={detail}
                isFirst
                prevStageId={null}
                knockoutStages={knockoutStages}
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
  onClearWinner: (matchupId: number) => void;
}) {
  const prev = prevStageId ? matchupsForStage(detail, prevStageId) : [];
  const np = m.position;
  const feederTop = !isFirst
    ? (m.source_a_matchup_id != null
        ? findMatchupById(detail, m.source_a_matchup_id)
        : prev.find((x) => x.position === 2 * np - 1))
    : null;
  const feederBot = !isFirst
    ? (m.source_b_matchup_id != null
        ? findMatchupById(detail, m.source_b_matchup_id)
        : prev.find((x) => x.position === 2 * np))
    : null;

  const labelTop =
    feederTop != null
      ? feederWinnerDropLabel(feederTop, knockoutStages)
      : '';
  const labelBot =
    feederBot != null
      ? feederWinnerDropLabel(feederBot, knockoutStages)
      : '';

  return (
    <div className="bf-matchup">
      {!isFirst && feederTop && feederBot ? (
        <>
          <ReceiveOrPick
            contestant={m.contestant1}
            currentMatchupId={m.id}
            feeder={feederTop}
            otherContestantId={m.contestant2?.id}
            winnerId={m.winner?.id}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
            onClearWinner={onClearWinner}
            emptyLabel={labelTop}
          />
          <ReceiveOrPick
            contestant={m.contestant2}
            currentMatchupId={m.id}
            feeder={feederBot}
            otherContestantId={m.contestant1?.id}
            winnerId={m.winner?.id}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
            onClearWinner={onClearWinner}
            emptyLabel={labelBot}
          />
        </>
      ) : null}

      {isFirst ? (
        <>
          <ContestantOnly
            label={m.contestant1}
            matchupId={m.id}
            winnerId={m.winner?.id}
            otherId={m.contestant2?.id}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
          />
          <ContestantOnly
            label={m.contestant2}
            matchupId={m.id}
            winnerId={m.winner?.id}
            otherId={m.contestant1?.id}
            showSeeds={showSeeds}
            applyWinner={applyWinner}
            busy={busy}
          />
        </>
      ) : null}
    </div>
  );
}

/** First round: click a team to pick the winner of this game. */
function ContestantOnly({
  label,
  matchupId,
  winnerId,
  otherId,
  showSeeds,
  applyWinner,
  busy,
}: {
  label: BracketContestantInfo | null;
  matchupId: number;
  winnerId: number | undefined;
  otherId: number | undefined;
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
}) {
  if (!label) {
    return (
      <div className="bf-slot bf-slot--empty" aria-label="Empty slot">
        TBD
      </div>
    );
  }
  const isWinner =
    winnerId != null && winnerId === label.id && otherId != null;

  return (
    <div className="bf-slot">
      <button
        type="button"
        className={`bf-chip bf-chip--ko ${isWinner ? 'bf-chip--winner' : ''}`}
        disabled={busy}
        onClick={() => void applyWinner(matchupId, label.id)}
        aria-label={`${label.display_name}, pick to advance`}
      >
        <MatchupContestantFace contestant={label} showSeed={showSeeds} />
      </button>
    </div>
  );
}

/** Later rounds: empty slot waits for the listed feeder; click a team to pick this game’s winner. */
function ReceiveOrPick({
  contestant,
  currentMatchupId,
  feeder,
  otherContestantId,
  winnerId,
  showSeeds,
  applyWinner,
  busy,
  onClearWinner,
  emptyLabel,
}: {
  contestant: BracketContestantInfo | null;
  currentMatchupId: number;
  feeder: MatchupInfo;
  otherContestantId: number | undefined;
  winnerId: number | undefined;
  showSeeds: boolean;
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner: (matchupId: number) => void;
  emptyLabel: string;
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

  const clearMatchupId =
    feeder.winner != null
      ? feeder.id
      : winnerId != null
        ? currentMatchupId
        : null;

  const canPickThisGame = otherContestantId != null;

  return (
    <div
      className={
        clearMatchupId != null ? 'bf-slot bf-slot--with-clear' : 'bf-slot'
      }
    >
      <button
        type="button"
        className={`bf-chip bf-chip--ko ${isWinner ? 'bf-chip--winner' : ''}`}
        disabled={busy || !canPickThisGame}
        onClick={() => void applyWinner(currentMatchupId, contestant.id)}
        aria-label={`${contestant.display_name}, pick to advance`}
      >
        <MatchupContestantFace contestant={contestant} showSeed={showSeeds} />
      </button>
      {clearMatchupId != null ? (
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
