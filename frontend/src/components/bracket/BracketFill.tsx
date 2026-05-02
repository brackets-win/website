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
} from '../../utils/api';
import { GroupStagePanel } from './GroupStagePanel';
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
  return `${prefix}${feeder.position} Winner`;
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
};

export function BracketFill({ userBracketId }: Props) {
  const [detail, setDetail] = useState<UserBracketDetail | null>(null);
  const [bracketDef, setBracketDef] = useState<BracketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<'groups' | 'knockout'>('knockout');
  const phaseInitForUb = useRef<number | null>(null);

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
        e instanceof ApiError
          ? e.message
          : 'Could not load bracket (sign in and check user bracket id).',
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

  const thirdPlaceStage = useMemo(
    () => stages.find((s) => s.knockout?.is_third_place),
    [stages],
  );

  const leaves = useMemo(() => {
    if (!detail || knockoutStagesMain.length === 0) return 0;
    return matchupsForStage(detail, knockoutStagesMain[0].id).length;
  }, [detail, knockoutStagesMain]);

  const boardHeightPx = useMemo(
    () => Math.max(560, leaves * 160),
    [leaves],
  );

  const applyWinner = useCallback(
    async (feederMatchupId: number, contestantId: number) => {
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
    [load],
  );

  const clearWinner = useCallback(
    async (matchupId: number) => {
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
    [load],
  );

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

  if (detail.is_master) {
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

  const knockoutBoard =
    !knockoutEmpty ? (
      <div className="bf-scroll">
        <div className="bf-board-inner">
          {knockoutStagesMain.map((stage, stageIdx) => (
            <Fragment key={stage.id}>
              <BracketStageColumn
                stage={stage}
                stageIdx={stageIdx}
                leaves={leaves}
                detail={detail}
                stages={knockoutStagesMain}
                applyWinner={applyWinner}
                busy={busy}
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
              applyWinner={applyWinner}
              busy={busy}
              onClearWinner={clearWinner}
            />
          ) : null}
        </div>
      </div>
    ) : (
      <p className="bf-meta bf-knockout-placeholder">
        Knockout pairings will fill in here as matchups are available.
      </p>
    );

  return (
    <section
      className="bf"
      aria-busy={busy}
      style={
        {
          '--bf-board-h': `${boardHeightPx}px`,
        } as React.CSSProperties
      }
    >
      <h2>{detail.bracket.name}</h2>
      <p className="bf-meta">
        {detail.score_vs_master != null
          ? `Score vs master: ${detail.score_vs_master}`
          : 'Score —'}
      </p>
      {error ? <p className="bf-error">{error}</p> : null}

      {hasGroupUi && firstGroupStage ? (
        <div className="bf-tabs" role="tablist" aria-label="Bracket sections">
          <button
            type="button"
            role="tab"
            aria-selected={phase === 'groups'}
            className={
              phase === 'groups' ? 'bf-tab bf-tab--active' : 'bf-tab'
            }
            onClick={() => setPhase('groups')}
          >
            Groups
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={phase === 'knockout'}
            className={
              phase === 'knockout' ? 'bf-tab bf-tab--active' : 'bf-tab'
            }
            onClick={() => setPhase('knockout')}
          >
            Knockout
          </button>
        </div>
      ) : null}

      {hasGroupUi && phase === 'groups' && firstGroupStage ? (
        <GroupStagePanel
          userBracketId={userBracketId}
          groups={groupsPreview}
          groupStage={firstGroupStage}
          isWorldCup={isWorldCup}
          initialMetadata={{
            group_positions: meta.group_positions ?? {},
            third_place_advancers: meta.third_place_advancers ?? [],
          }}
          busy={busy}
          onSaved={load}
          onError={(msg) => setError(msg || null)}
          setBusy={setBusy}
        />
      ) : null}

      {(!hasGroupUi || phase === 'knockout') ? knockoutBoard : null}

    </section>
  );
}

function ConnectorBetweenStages({
  stageIdx,
  leaves,
  pairCount,
}: {
  stageIdx: number;
  leaves: number;
  pairCount: number;
}) {
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
            const pos = idx + 1;
            const y1 = matchupCenterPct(stageIdx, 2 * pos - 1, leaves);
            const y2 = matchupCenterPct(stageIdx, 2 * pos, leaves);
            const ym = (y1 + y2) / 2;
            const d = `M 0 ${y1} H 24 M 0 ${y2} H 24 M 24 ${y1} V ${y2} M 24 ${ym} H 100`;
            return <path key={idx} d={d} className="bf-connector-path" />;
          })}
        </svg>
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
  applyWinner,
  busy,
  onClearWinner,
}: {
  stage: BracketStageInfo;
  stageIdx: number;
  leaves: number;
  detail: UserBracketDetail;
  stages: BracketStageInfo[];
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

function ChampionColumn({
  finalMatchup,
  thirdPlaceMatchup,
  detail,
  knockoutStages,
  applyWinner,
  busy,
  onClearWinner,
}: {
  finalMatchup: MatchupInfo;
  thirdPlaceMatchup: MatchupInfo | undefined;
  detail: UserBracketDetail;
  knockoutStages: BracketStageInfo[];
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
                  <span className="bf-champion-name">{champ.display_name}</span>
                  {champ.seed != null ? (
                    <span className="bf-champion-seed">#{champ.seed}</span>
                  ) : null}
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
  applyWinner,
  busy,
  onClearWinner,
}: {
  m: MatchupInfo;
  detail: UserBracketDetail;
  isFirst: boolean;
  prevStageId: number | null;
  knockoutStages: BracketStageInfo[];
  applyWinner: (matchupId: number, contestantId: number) => void | Promise<void>;
  busy: boolean;
  onClearWinner: (matchupId: number) => void;
}) {
  const prev = prevStageId ? matchupsForStage(detail, prevStageId) : [];
  const np = m.position;
  const feederTop = !isFirst ? prev.find((x) => x.position === 2 * np - 1) : null;
  const feederBot = !isFirst ? prev.find((x) => x.position === 2 * np) : null;

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
            applyWinner={applyWinner}
            busy={busy}
          />
          <ContestantOnly
            label={m.contestant2}
            matchupId={m.id}
            winnerId={m.winner?.id}
            otherId={m.contestant1?.id}
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
  applyWinner,
  busy,
}: {
  label: BracketContestantInfo | null;
  matchupId: number;
  winnerId: number | undefined;
  otherId: number | undefined;
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
        className={`bf-chip ${isWinner ? 'bf-chip--winner' : ''}`}
        disabled={busy}
        onClick={() => void applyWinner(matchupId, label.id)}
        aria-label={`${label.display_name}, pick to advance`}
      >
        {label.display_name}
        {label.seed != null ? (
          <span style={{ opacity: 0.55, marginLeft: 6 }}>#{label.seed}</span>
        ) : null}
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
        className={`bf-chip ${isWinner ? 'bf-chip--winner' : ''}`}
        disabled={busy || !canPickThisGame}
        onClick={() => void applyWinner(currentMatchupId, contestant.id)}
        aria-label={`${contestant.display_name}, pick to advance`}
      >
        {contestant.display_name}
        {contestant.seed != null ? (
          <span style={{ opacity: 0.55, marginLeft: 6 }}>
            #{contestant.seed}
          </span>
        ) : null}
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
