import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  type BracketContestantInfo,
  type BracketDetail,
  type BracketStageInfo,
  type ChallengeStatsBracketSlotEntry,
  type MatchupInfo,
  type UserBracketDetail,
  getBracket,
  getUserBracket,
} from '../../utils/api';
import { ContestantAvatar } from '../bracket/ContestantAvatar';
import {
  buildMirrorBracketLayout,
  columnMatchupCenterPct,
  type MirrorBracketColumn,
} from '../bracket/bracketMirrorLayout';
import {
  resolveFeederMatchups,
  sortMatchupsByFeederOrder,
} from '../bracket/knockoutFeederLayout';

import './BracketDistribution.css';

/** Split-bracket center column vertical layout (kept in sync with BracketFill). */
const SPLIT_CENTER_CHAMP_GAP_PCT = 14;
const SPLIT_CENTER_FINAL_ABOVE_SEMI_PCT = 10;
const SPLIT_CENTER_THIRD_MATCH_TOP_PCT = 19;

/** How many runner-up picks to list under the most common pick in each slot. */
const DEFAULT_MAX_OTHERS = 3;

type Slots = Record<string, ChallengeStatsBracketSlotEntry[]>;

type Props = {
  bracketId: number;
  masterUserBracketId: number | null;
  slots: Slots;
  maxOthers?: number;
};

function matchupsForStage(
  ub: UserBracketDetail,
  stageId: number,
): MatchupInfo[] {
  const pack = ub.matchups_by_stage.find((s) => s.stage_id === stageId);
  return pack ? [...pack.matchups].sort((a, b) => a.position - b.position) : [];
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
    wingMax: leaves,
  };
}

function columnCenterFn(
  col: MirrorBracketColumn,
): (stageIdx: number, position: number) => number {
  return (stageIdx, position) =>
    columnMatchupCenterPct(
      stageIdx,
      position,
      col.wingMin,
      col.wingMax,
      col.positionMin,
    );
}

/** Which matchup slot (1 = contestant1, 2 = contestant2) a feeder advances into. */
function slotSideForFeeder(
  m: MatchupInfo,
  feeder: MatchupInfo | null,
  feeders: { top: MatchupInfo | null; bottom: MatchupInfo | null },
  fallback: 1 | 2,
): 1 | 2 {
  if (feeder == null) return fallback;
  if (m.source_a_matchup_id === feeder.id) return 1;
  if (m.source_b_matchup_id === feeder.id) return 2;
  if (feeders.top?.id === feeder.id) return 1;
  if (feeders.bottom?.id === feeder.id) return 2;
  return fallback;
}

/** Team the master bracket placed in a given slot, for the green highlight. */
function masterSlotPick(
  master: UserBracketDetail | null,
  stageId: number,
  position: number,
  side: 1 | 2,
): number | null {
  if (!master) return null;
  const m = matchupsForStage(master, stageId).find(
    (x) => x.position === position,
  );
  if (!m) return null;
  const c = side === 1 ? m.contestant1 : m.contestant2;
  return c?.id ?? null;
}

function masterMatchupWinner(
  master: UserBracketDetail | null,
  stageId: number | undefined,
): number | null {
  if (!master || stageId == null) return null;
  const m = matchupsForStage(master, stageId)[0];
  return m?.winner?.id ?? null;
}

function formatPct(value: number): string {
  return `${Math.round(value)}%`;
}

/** Order a slot's picks for display: most common first, master pick always shown. */
function displayEntries(
  entries: ChallengeStatsBracketSlotEntry[],
  masterPickId: number | null,
  maxOthers: number,
): ChallengeStatsBracketSlotEntry[] {
  const ordered = entries
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => {
      const pctDiff = b.entry.pct - a.entry.pct;
      if (pctDiff !== 0) return pctDiff;
      const aIsMaster =
        masterPickId != null && a.entry.bracket_contestant_id === masterPickId;
      const bIsMaster =
        masterPickId != null && b.entry.bracket_contestant_id === masterPickId;
      if (aIsMaster !== bIsMaster) return aIsMaster ? -1 : 1;
      return a.index - b.index;
    })
    .map(({ entry }) => entry);

  const display = ordered.slice(0, 1 + maxOthers);
  if (
    masterPickId != null &&
    !display.some((e) => e.bracket_contestant_id === masterPickId)
  ) {
    const master = ordered.find(
      (e) => e.bracket_contestant_id === masterPickId,
    );
    if (master) display.push(master);
  }
  return display;
}

function SlotDistribution({
  entries,
  masterPickId,
  maxOthers,
}: {
  entries: ChallengeStatsBracketSlotEntry[];
  masterPickId: number | null;
  maxOthers: number;
}) {
  if (entries.length === 0) {
    return (
      <div className="bd-slot bd-slot--empty" aria-hidden>
        —
      </div>
    );
  }
  const display = displayEntries(entries, masterPickId, maxOthers);
  const [top, ...others] = display;
  const topIsMaster =
    masterPickId != null && top.bracket_contestant_id === masterPickId;

  return (
    <div className="bd-slot">
      <div
        className={
          topIsMaster ? 'bd-slot-top bd-slot-top--master' : 'bd-slot-top'
        }
      >
        <ContestantAvatar
          displayName={top.display_name}
          imageUrl={top.image_url}
          className="bd-slot-img"
          placeholderClassName="bd-slot-img bd-slot-img--ph"
        />
        <span className="bd-slot-top-name">{top.display_name}</span>
        <span className="bd-slot-top-pct">{formatPct(top.pct)}</span>
      </div>
      {others.length > 0 ? (
        <ul className="bd-slot-others">
          {others.map((entry) => {
            const isMaster =
              masterPickId != null &&
              entry.bracket_contestant_id === masterPickId;
            return (
              <li
                key={entry.bracket_contestant_id}
                className={
                  isMaster
                    ? 'bd-slot-other bd-slot-other--master'
                    : 'bd-slot-other'
                }
              >
                <span className="bd-slot-other-name">{entry.display_name}</span>
                <span className="bd-slot-other-pct">
                  {formatPct(entry.pct)}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function SeededSlot({
  contestant,
}: {
  contestant: BracketContestantInfo | null | undefined;
}) {
  if (!contestant) {
    return (
      <div className="bd-slot bd-slot--empty" aria-hidden>
        —
      </div>
    );
  }
  return (
    <div className="bd-slot">
      <div className="bd-slot-top">
        <ContestantAvatar
          displayName={contestant.display_name}
          imageUrl={contestant.image_url}
          className="bd-slot-img"
          placeholderClassName="bd-slot-img bd-slot-img--ph"
        />
        <span className="bd-slot-top-name">{contestant.display_name}</span>
      </div>
    </div>
  );
}

function MatchupBox({
  m,
  isFirst,
  prevStageId,
  master,
  slots,
  maxOthers,
  seededOnly = false,
}: {
  m: MatchupInfo;
  isFirst: boolean;
  prevStageId: number | null;
  master: UserBracketDetail | null;
  slots: Slots;
  maxOthers: number;
  seededOnly?: boolean;
}) {
  if (seededOnly) {
    return (
      <div className="bf-matchup bd-matchup">
        <SeededSlot contestant={m.contestant1} />
        <SeededSlot contestant={m.contestant2} />
      </div>
    );
  }
  const feeders = resolveFeederMatchups(m, master ?? undefinedDetail, prevStageId);
  const topSide = isFirst
    ? 1
    : slotSideForFeeder(m, feeders.top, feeders, 1);
  const botSide = isFirst
    ? 2
    : slotSideForFeeder(m, feeders.bottom, feeders, 2);

  const topKey = `${m.stage_id}:${m.position}:${topSide}`;
  const botKey = `${m.stage_id}:${m.position}:${botSide}`;

  return (
    <div className="bf-matchup bd-matchup">
      <SlotDistribution
        entries={slots[topKey] ?? []}
        masterPickId={masterSlotPick(master, m.stage_id, m.position, topSide)}
        maxOthers={maxOthers}
      />
      <SlotDistribution
        entries={slots[botKey] ?? []}
        masterPickId={masterSlotPick(master, m.stage_id, m.position, botSide)}
        maxOthers={maxOthers}
      />
    </div>
  );
}

/** Sentinel so the feeder helpers can run before the master finishes loading. */
const undefinedDetail = {
  matchups_by_stage: [],
} as unknown as UserBracketDetail;

function ChampionCell({
  label,
  entries,
  masterPickId,
  maxOthers,
}: {
  label: string;
  entries: ChallengeStatsBracketSlotEntry[];
  masterPickId: number | null;
  maxOthers: number;
}) {
  return (
    <div className="bd-champion">
      <p className="bf-stage-title">{label}</p>
      <div className="bf-matchup bd-matchup bd-matchup--single">
        <SlotDistribution
          entries={entries}
          masterPickId={masterPickId}
          maxOthers={maxOthers}
        />
      </div>
    </div>
  );
}

function DistStageColumn({
  col,
  stages,
  master,
  slots,
  maxOthers,
  seededOpeningRound,
}: {
  col: MirrorBracketColumn;
  stages: BracketStageInfo[];
  master: UserBracketDetail | null;
  slots: Slots;
  maxOthers: number;
  seededOpeningRound: boolean;
}) {
  const { stage, stageIdx, positionMin, positionMax, wingMin, wingMax } = col;
  const isFirst = stageIdx === 0;
  const prevStage = stageIdx > 0 ? stages[stageIdx - 1] : null;
  const detail = master ?? undefinedDetail;
  const matchups = sortMatchupsByFeederOrder(
    matchupsForStage(detail, stage.id).filter(
      (m) => m.position >= positionMin && m.position <= positionMax,
    ),
    detail,
    prevStage?.id ?? null,
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
          const feeders = resolveFeederMatchups(m, detail, prevStage?.id ?? null);
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
              <MatchupBox
                m={m}
                isFirst={isFirst}
                prevStageId={prevStage?.id ?? null}
                master={master}
                slots={slots}
                maxOthers={maxOthers}
                seededOnly={seededOpeningRound && isFirst}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DistConnector({
  fromCol,
  toCol,
  master,
  mirrored = false,
}: {
  fromCol: MirrorBracketColumn;
  toCol: MirrorBracketColumn;
  master: UserBracketDetail | null;
  mirrored?: boolean;
}) {
  const detail = master ?? undefinedDetail;
  const fromPct = columnCenterFn(fromCol);
  const prevStageId = fromCol.stage.id;
  const nextMatchups = sortMatchupsByFeederOrder(
    matchupsForStage(detail, toCol.stage.id).filter(
      (m) => m.position >= toCol.positionMin && m.position <= toCol.positionMax,
    ),
    detail,
    prevStageId,
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

function SpineConnector({
  col,
  towardCenter,
  targetCenterPct,
}: {
  col: MirrorBracketColumn;
  towardCenter: boolean;
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

function ThirdPlaceBlock({
  stage,
  master,
  slots,
  maxOthers,
  stacked,
}: {
  stage: BracketStageInfo;
  master: UserBracketDetail | null;
  slots: Slots;
  maxOthers: number;
  stacked?: boolean;
}) {
  const detail = master ?? undefinedDetail;
  const m = matchupsForStage(detail, stage.id)[0];
  const position = m?.position ?? 1;
  return (
    <div
      className={
        stacked
          ? 'bd-third bd-third--stacked'
          : 'bd-third'
      }
    >
      <ChampionCell
        label="3rd Place"
        entries={slots['third_place'] ?? []}
        masterPickId={masterMatchupWinner(master, stage.id)}
        maxOthers={maxOthers}
      />
      <div className="bf-matchup bd-matchup bd-third-match">
        <SlotDistribution
          entries={slots[`${stage.id}:${position}:1`] ?? []}
          masterPickId={masterSlotPick(master, stage.id, position, 1)}
          maxOthers={maxOthers}
        />
        <SlotDistribution
          entries={slots[`${stage.id}:${position}:2`] ?? []}
          masterPickId={masterSlotPick(master, stage.id, position, 2)}
          maxOthers={maxOthers}
        />
      </div>
    </div>
  );
}

function DistChampionColumn({
  master,
  slots,
  maxOthers,
  finalStage,
  thirdStage,
}: {
  master: UserBracketDetail | null;
  slots: Slots;
  maxOthers: number;
  finalStage: BracketStageInfo | undefined;
  thirdStage: BracketStageInfo | undefined;
}) {
  return (
    <div className="bf-stage-col bf-stage-col--champion">
      <div className="bf-champion-stack">
        <div className="bf-champion-middle">
          <ChampionCell
            label="Champion"
            entries={slots['champion'] ?? []}
            masterPickId={masterMatchupWinner(master, finalStage?.id)}
            maxOthers={maxOthers}
          />
        </div>
        {thirdStage ? (
          <ThirdPlaceBlock
            stage={thirdStage}
            master={master}
            slots={slots}
            maxOthers={maxOthers}
            stacked
          />
        ) : null}
      </div>
    </div>
  );
}

function DistSplitCenter({
  finalMatchup,
  finalStage,
  thirdStage,
  semiCenterPct,
  finalCenterPct,
  master,
  slots,
  maxOthers,
}: {
  finalMatchup: MatchupInfo;
  finalStage: BracketStageInfo | undefined;
  thirdStage: BracketStageInfo | undefined;
  semiCenterPct: number;
  finalCenterPct: number;
  master: UserBracketDetail | null;
  slots: Slots;
  maxOthers: number;
}) {
  const finalTitle = finalStage?.name?.trim() ? finalStage.name : 'Final';
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
            <ChampionCell
              label="Champion"
              entries={slots['champion'] ?? []}
              masterPickId={masterMatchupWinner(master, finalStage?.id)}
              maxOthers={maxOthers}
            />
          </div>
        </div>

        <div
          className="bf-center-slot bf-center-slot--final"
          style={{ top: `${finalCenterPct}%` }}
        >
          <div className="bf-center-matchup-wrap">
            <MatchupBox
              m={finalMatchup}
              isFirst={false}
              prevStageId={null}
              master={master}
              slots={slots}
              maxOthers={maxOthers}
            />
          </div>
        </div>

        {thirdStage ? (
          <div
            className="bf-center-slot bf-center-slot--third"
            style={{ top: `${thirdMatchTop}%` }}
          >
            <ThirdPlaceBlock
              stage={thirdStage}
              master={master}
              slots={slots}
              maxOthers={maxOthers}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function BracketDistribution({
  bracketId,
  masterUserBracketId,
  slots,
  maxOthers = DEFAULT_MAX_OTHERS,
}: Props) {
  const [bracketDef, setBracketDef] = useState<BracketDetail | null>(null);
  const [master, setMaster] = useState<UserBracketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { bracket } = await getBracket(bracketId);
      setBracketDef(bracket);
      if (masterUserBracketId != null) {
        const { user_bracket } = await getUserBracket(masterUserBracketId);
        setMaster(user_bracket);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Unable to load bracket.');
    }
  }, [bracketId, masterUserBracketId]);

  useEffect(() => {
    void load();
  }, [load]);

  const sortedStages = useMemo(
    () =>
      bracketDef
        ? [...bracketDef.stages].sort((a, b) => a.order - b.order)
        : [],
    [bracketDef],
  );

  const knockoutStages = useMemo(
    () => sortedStages.filter((s) => s.stage_type === 'KNOCKOUT'),
    [sortedStages],
  );
  const hasGroupStage = useMemo(
    () => sortedStages.some((s) => s.stage_type === 'GROUP'),
    [sortedStages],
  );
  const knockoutStagesMain = useMemo(
    () => knockoutStages.filter((s) => !s.knockout?.is_third_place),
    [knockoutStages],
  );
  const seededOpeningRound = !hasGroupStage;
  const thirdStage = useMemo(
    () =>
      bracketDef?.has_third_place_match
        ? knockoutStages.find((s) => s.knockout?.is_third_place)
        : undefined,
    [bracketDef?.has_third_place_match, knockoutStages],
  );
  const finalStage = useMemo(
    () => knockoutStagesMain.find((s) => s.knockout?.is_final),
    [knockoutStagesMain],
  );

  const leaves = useMemo(() => {
    if (!master || knockoutStagesMain.length === 0) return 0;
    return matchupsForStage(master, knockoutStagesMain[0].id).length;
  }, [master, knockoutStagesMain]);

  const openingContestants = knockoutStagesMain[0]?.number_of_contestants ?? 0;
  const splitKnockoutBoard = openingContestants >= 32 && leaves >= 2;

  const boardHeightPx = useMemo(() => {
    if (splitKnockoutBoard) {
      // Each wing's opening band must fit two stacked distribution cells.
      return Math.max(900, (leaves / 2) * 200);
    }
    return Math.max(640, leaves * 210);
  }, [leaves, splitKnockoutBoard]);

  const mirrorLayout = useMemo(
    () =>
      buildMirrorBracketLayout(knockoutStagesMain, leaves, openingContestants),
    [knockoutStagesMain, leaves, openingContestants],
  );

  if (error) {
    return <p className="challenge-view__muted">{error}</p>;
  }
  if (!bracketDef || (masterUserBracketId != null && !master)) {
    return <p className="challenge-view__muted">Loading bracket…</p>;
  }
  if (knockoutStagesMain.length === 0 || leaves === 0) {
    return null;
  }

  const finalMatchup =
    finalStage != null ? matchupsForStage(master!, finalStage.id)[0] : undefined;

  return (
    <div
      className={
        mirrorLayout ? 'bd bf--split-knockout' : 'bd'
      }
      style={
        {
          '--bf-board-h': `${boardHeightPx}px`,
        } as React.CSSProperties
      }
    >
      <div className="bf-ko-desktop bf-scroll">
        <div className="bf-ko-touch-zoom">
          {mirrorLayout ? (
            <div className="bf-board-split">
              <div className="bf-board-wing">
                {mirrorLayout.left.map((col, colIdx) => (
                  <Fragment key={col.key}>
                    <DistStageColumn
                      col={col}
                      stages={knockoutStagesMain}
                      master={master}
                      slots={slots}
                      maxOthers={maxOthers}
                      seededOpeningRound={seededOpeningRound}
                    />
                    {colIdx < mirrorLayout.left.length - 1 ? (
                      <DistConnector
                        fromCol={mirrorLayout.left[colIdx]}
                        toCol={mirrorLayout.left[colIdx + 1]}
                        master={master}
                      />
                    ) : null}
                  </Fragment>
                ))}
              </div>
              {mirrorLayout.center && finalMatchup
                ? (() => {
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
                        <DistSplitCenter
                          finalMatchup={finalMatchup}
                          finalStage={finalStage}
                          thirdStage={thirdStage}
                          semiCenterPct={semiCenterPct}
                          finalCenterPct={finalCenterPct}
                          master={master}
                          slots={slots}
                          maxOthers={maxOthers}
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
                : null}
              <div className="bf-board-wing bf-board-wing--right">
                {mirrorLayout.right.map((col, colIdx) => (
                  <Fragment key={col.key}>
                    <DistStageColumn
                      col={col}
                      stages={knockoutStagesMain}
                      master={master}
                      slots={slots}
                      maxOthers={maxOthers}
                      seededOpeningRound={seededOpeningRound}
                    />
                    {colIdx < mirrorLayout.right.length - 1 ? (
                      <DistConnector
                        fromCol={mirrorLayout.right[colIdx]}
                        toCol={mirrorLayout.right[colIdx + 1]}
                        master={master}
                        mirrored
                      />
                    ) : null}
                  </Fragment>
                ))}
              </div>
            </div>
          ) : (
            <div className="bf-board-inner">
              {knockoutStagesMain.map((stage, stageIdx) => (
                <Fragment key={stage.id}>
                  <DistStageColumn
                    col={linearStageColumn(stage, stageIdx, leaves)}
                    stages={knockoutStagesMain}
                    master={master}
                    slots={slots}
                    maxOthers={maxOthers}
                    seededOpeningRound={seededOpeningRound}
                  />
                  {stageIdx < knockoutStagesMain.length - 1 ? (
                    <DistConnector
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
                      master={master}
                    />
                  ) : null}
                </Fragment>
              ))}
              <DistChampionColumn
                master={master}
                slots={slots}
                maxOthers={maxOthers}
                finalStage={finalStage}
                thirdStage={thirdStage}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
