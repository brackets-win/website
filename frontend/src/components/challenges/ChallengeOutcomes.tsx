import { useMemo, useState } from 'react';

import type {
  ChallengeOutcomesChampionBranch,
  ChallengeOutcomesEntry,
  ChallengeOutcomesWinnerOdds,
  ChallengeStatsSimilarityTeam,
} from '../../utils/api';
import {
  buildOutcomeDisplayRows,
  collectOutcomeLeafPaths,
  isExhaustiveCluster,
  OutcomeGlobalUniverse,
  pathOutcomeKey,
  sumDisplayRowBranchMetric,
  sumDisplayRowPlacementMetric,
  type DisplayRowPlacementRole,
  type OutcomeDisplayRow,
  type OutcomeLeafPath,
  teamSetKey,
} from '../../utils/challengeOutcomesDisplay';
import { ContestantAvatar } from '../bracket/ContestantAvatar';

import './BracketSimilarity.css';
import './ChallengeOutcomes.css';
import './ChallengeStats.css';

type GroupMode = 'entry' | 'team';
type SortKey = 'outcomes' | 'likelihood' | 'name';
type TeamMetricMode = 'outcomes' | 'likelihood';
type PlacementRole = 'champion' | 'runner_up' | 'third' | 'fourth' | 'semi';

type Props = {
  hasThirdPlace: boolean;
  winnerOdds: ChallengeOutcomesWinnerOdds[];
  teamLikelihood?: Record<string, number>;
  tree: ChallengeOutcomesChampionBranch[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
};

type LeafPath = OutcomeLeafPath;
type DisplayRow = OutcomeDisplayRow;

type TableRow = DisplayRow & {
  showChampCell: boolean;
  champRowSpan: number;
  showRuCell: boolean;
  ruRowSpan: number;
  showThirdCell: boolean;
  thirdRowSpan: number;
};

function sortTeams(
  teams: Iterable<ChallengeStatsSimilarityTeam>,
): ChallengeStatsSimilarityTeam[] {
  return [...teams].sort((a, b) =>
    a.display_name.localeCompare(b.display_name, undefined, {
      sensitivity: 'base',
    }),
  );
}

function winnersKey(winners: ChallengeOutcomesEntry[]): string {
  return winners
    .map((entry) => entry.user_bracket_id)
    .sort((a, b) => a - b)
    .join(',');
}

function flattenTableRows(rows: DisplayRow[]): TableRow[] {
  return rows.map((row, rowIndex) => {
    const prevChampId =
      rowIndex > 0 ? rows[rowIndex - 1].champion.bracket_contestant_id : null;
    const showChamp =
      rowIndex === 0 ||
      prevChampId !== row.champion.bracket_contestant_id;
    let champSpan = 1;
    if (showChamp) {
      for (let i = rowIndex + 1; i < rows.length; i++) {
        if (rows[i].champion.bracket_contestant_id !== row.champion.bracket_contestant_id) {
          break;
        }
        champSpan++;
      }
    }

    const sameChampAsPrev =
      rowIndex > 0 &&
      rows[rowIndex - 1].champion.bracket_contestant_id ===
        row.champion.bracket_contestant_id;
    const prevRuKey = sameChampAsPrev
      ? teamSetKey(rows[rowIndex - 1].runnerUpTeams)
      : null;
    const ruKey = teamSetKey(row.runnerUpTeams);
    const showRu = showChamp || prevRuKey !== ruKey;
    let ruSpan = 1;
    if (showRu) {
      for (let i = rowIndex + 1; i < rows.length; i++) {
        if (
          rows[i].champion.bracket_contestant_id !==
            row.champion.bracket_contestant_id ||
          teamSetKey(rows[i].runnerUpTeams) !== ruKey
        ) {
          break;
        }
        ruSpan++;
      }
    }

    const thirdKey = teamSetKey(row.thirdTeams);
    const sameRuAsPrev = sameChampAsPrev && prevRuKey === ruKey;
    const prevThirdKey = sameRuAsPrev
      ? teamSetKey(rows[rowIndex - 1].thirdTeams)
      : null;
    const showThird = row.thirdTeams.length === 0
      ? false
      : showRu || prevThirdKey !== thirdKey;
    let thirdSpan = 1;
    if (showThird && row.thirdTeams.length > 0) {
      for (let i = rowIndex + 1; i < rows.length; i++) {
        if (
          rows[i].champion.bracket_contestant_id !==
            row.champion.bracket_contestant_id ||
          teamSetKey(rows[i].runnerUpTeams) !== ruKey ||
          teamSetKey(rows[i].thirdTeams) !== thirdKey
        ) {
          break;
        }
        thirdSpan++;
      }
    }

    return {
      ...row,
      showChampCell: showChamp,
      champRowSpan: champSpan,
      showRuCell: showRu,
      ruRowSpan: ruSpan,
      showThirdCell: showThird,
      thirdRowSpan: thirdSpan,
    };
  });
}

function teamHasImage(team: ChallengeStatsSimilarityTeam): boolean {
  return Boolean(team.image_url?.trim());
}

function TeamFlag({
  team,
  size,
  metricPct,
}: {
  team: ChallengeStatsSimilarityTeam;
  size: 'lg' | 'md' | 'sm' | 'xs';
  metricPct?: string | null;
}) {
  const showName = !teamHasImage(team);
  return (
    <div
      className={[
        'challenge-stats__sim-flag',
        `challenge-stats__sim-flag--${size}`,
        showName ? '' : 'challenge-stats__sim-flag--image-only',
      ]
        .filter(Boolean)
        .join(' ')}
      title={team.display_name}
    >
      <ContestantAvatar
        displayName={team.display_name}
        imageUrl={team.image_url}
        className="challenge-stats__sim-flag-img"
        placeholderClassName="challenge-stats__sim-flag-img challenge-stats__sim-flag-img--ph"
      />
      {showName ? (
        <span className="challenge-stats__sim-flag-name">{team.display_name}</span>
      ) : null}
      {metricPct ? (
        <span className="challenge-outcomes__team-flag-pct">{metricPct}</span>
      ) : null}
    </div>
  );
}

type EntryMetricContext = {
  row: DisplayRow;
  allLeaves: LeafPath[];
  hasThirdPlace: boolean;
};

function TeamCluster({
  teams,
  singleSize = 'sm',
  role,
  pathContext,
  teamMetricMode,
  pathOutcomeCounts,
  globalOutcomeTotal,
  pathLikelihood,
  sortKey,
  groupMode,
  entryMetric,
}: {
  teams: ChallengeStatsSimilarityTeam[];
  singleSize?: 'lg' | 'md' | 'sm' | 'xs';
  role: PlacementRole;
  pathContext: PathContext;
  teamMetricMode: TeamMetricMode;
  pathOutcomeCounts: Map<string, number>;
  globalOutcomeTotal: number;
  pathLikelihood?: Record<string, number>;
  sortKey: SortKey;
  groupMode: GroupMode;
  entryMetric?: EntryMetricContext;
}) {
  const sorted = sortTeamsForPathSort(
    teams,
    pathContext,
    role,
    sortKey,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
  );
  if (sorted.length === 0) return null;
  if (sorted.length === 1) {
    return (
      <TeamFlag
        team={sorted[0]}
        size={singleSize}
        metricPct={resolvePlacementMetricPct(
          groupMode,
          role,
          [sorted[0].bracket_contestant_id],
          entryMetric,
          pathContext,
          teamMetricMode,
          pathOutcomeCounts,
          globalOutcomeTotal,
          pathLikelihood,
        )}
      />
    );
  }
  return (
    <div
      className="challenge-outcomes__team-cluster"
      title={sorted.map((team) => team.display_name).join(', ')}
    >
      {sorted.map((team) => (
        <TeamFlag
          key={team.bracket_contestant_id}
          team={team}
          size="xs"
          metricPct={resolvePlacementMetricPct(
            groupMode,
            role,
            [team.bracket_contestant_id],
            entryMetric,
            pathContext,
            teamMetricMode,
            pathOutcomeCounts,
            globalOutcomeTotal,
            pathLikelihood,
          )}
        />
      ))}
    </div>
  );
}

function AllPill({
  label,
  size = 'sm',
  metricPct,
}: {
  label: string;
  size?: 'md' | 'sm';
  metricPct?: string | null;
}) {
  return (
    <span
      className={[
        'challenge-outcomes__all-pill-wrap',
        size === 'md' ? 'challenge-outcomes__all-pill-wrap--md' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      title={label}
    >
      <span
        className={[
          'challenge-outcomes__all-pill',
          size === 'md' ? 'challenge-outcomes__all-pill--md' : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        ALL
      </span>
      {metricPct ? (
        <span className="challenge-outcomes__team-flag-pct">{metricPct}</span>
      ) : null}
    </span>
  );
}

function PlacementCell({
  teams,
  universe,
  singleSize = 'sm',
  allLabel,
  role,
  pathContext,
  teamMetricMode,
  pathOutcomeCounts,
  globalOutcomeTotal,
  pathLikelihood,
  sortKey,
  groupMode,
  entryMetric,
}: {
  teams: ChallengeStatsSimilarityTeam[];
  universe: ChallengeStatsSimilarityTeam[];
  singleSize?: 'lg' | 'md' | 'sm' | 'xs';
  allLabel: string;
  role: PlacementRole;
  pathContext: PathContext;
  teamMetricMode: TeamMetricMode;
  pathOutcomeCounts: Map<string, number>;
  globalOutcomeTotal: number;
  pathLikelihood?: Record<string, number>;
  sortKey: SortKey;
  groupMode: GroupMode;
  entryMetric?: EntryMetricContext;
}) {
  const sorted = sortTeamsForPathSort(
    teams,
    pathContext,
    role,
    sortKey,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
  );
  if (sorted.length === 0) return null;
  if (isExhaustiveCluster(sorted, universe)) {
    return (
      <AllPill
        label={allLabel}
        size={singleSize === 'md' ? 'md' : 'sm'}
        metricPct={resolvePlacementMetricPct(
          groupMode,
          role,
          sorted.map((team) => team.bracket_contestant_id),
          entryMetric,
          pathContext,
          teamMetricMode,
          pathOutcomeCounts,
          globalOutcomeTotal,
          pathLikelihood,
        )}
      />
    );
  }
  return (
    <TeamCluster
      teams={sorted}
      singleSize={singleSize}
      role={role}
      pathContext={pathContext}
      teamMetricMode={teamMetricMode}
      pathOutcomeCounts={pathOutcomeCounts}
      globalOutcomeTotal={globalOutcomeTotal}
      pathLikelihood={pathLikelihood}
      sortKey={sortKey}
      groupMode={groupMode}
      entryMetric={entryMetric}
    />
  );
}

function WinnerName({
  winner,
  onSelectPlayer,
  viewerUsername,
}: {
  winner: ChallengeOutcomesEntry;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  const isViewer = viewerUsername != null && winner.username === viewerUsername;
  const nameClass = isViewer
    ? 'challenge-stats__group-points-name challenge-stats__entry-name--viewer'
    : 'challenge-stats__group-points-name';

  if (onSelectPlayer) {
    return (
      <button
        type="button"
        className={`${nameClass} challenge-stats__group-points-name--btn`}
        onClick={() => onSelectPlayer(winner.user_bracket_id, winner.display_name)}
      >
        {winner.display_name}
      </button>
    );
  }

  return <span className={nameClass}>{winner.display_name}</span>;
}

function WinnerList({
  winners,
  onSelectPlayer,
  viewerUsername,
}: {
  winners: ChallengeOutcomesEntry[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <span className="challenge-outcomes__winner-list">
      {winners.map((winner, index) => (
        <span key={winner.user_bracket_id}>
          {index > 0 ? <span className="challenge-outcomes__winner-sep">, </span> : null}
          <WinnerName
            winner={winner}
            onSelectPlayer={onSelectPlayer}
            viewerUsername={viewerUsername}
          />
        </span>
      ))}
    </span>
  );
}

function formatLikelihood(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)}%`;
}

function formatOutcomePct(value: number): string {
  return `${value.toFixed(1)}%`;
}

type PathContext = {
  championId: number;
  runnerUpIds: number[];
  thirdIds: number[];
};

function lookupEntryChampionMetricPct(
  row: DisplayRow,
  allLeaves: LeafPath[],
  hasThirdPlace: boolean,
  teamMetricMode: TeamMetricMode,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): string | null {
  if (teamMetricMode === 'outcomes' && globalOutcomeTotal === 0) {
    return null;
  }
  const raw = sumDisplayRowBranchMetric(
    row,
    allLeaves,
    hasThirdPlace,
    teamMetricMode,
    pathLikelihood,
  );
  if (raw == null) return null;
  return formatRoundedTeamMetricPct(
    raw,
    teamMetricMode,
    globalOutcomeTotal,
  );
}

function toDisplayRowPlacementRole(
  role: PlacementRole,
): DisplayRowPlacementRole | null {
  if (role === 'champion') return null;
  return role;
}

function lookupEntryPlacementMetricPct(
  row: DisplayRow,
  allLeaves: LeafPath[],
  hasThirdPlace: boolean,
  role: DisplayRowPlacementRole,
  teamIds: number[],
  teamMetricMode: TeamMetricMode,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): string | null {
  if (teamMetricMode === 'outcomes' && globalOutcomeTotal === 0) {
    return null;
  }
  const raw = sumDisplayRowPlacementMetric(
    row,
    allLeaves,
    hasThirdPlace,
    role,
    teamIds,
    teamMetricMode,
    pathLikelihood,
  );
  if (raw == null) return null;
  return formatRoundedTeamMetricPct(
    raw,
    teamMetricMode,
    globalOutcomeTotal,
  );
}

function resolvePlacementMetricPct(
  groupMode: GroupMode,
  role: PlacementRole,
  teamIds: number[],
  entryMetric: EntryMetricContext | undefined,
  pathContext: PathContext,
  teamMetricMode: TeamMetricMode,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): string | null {
  if (groupMode === 'entry' && entryMetric) {
    const placementRole = toDisplayRowPlacementRole(role);
    if (placementRole) {
      return lookupEntryPlacementMetricPct(
        entryMetric.row,
        entryMetric.allLeaves,
        entryMetric.hasThirdPlace,
        placementRole,
        teamIds,
        teamMetricMode,
        globalOutcomeTotal,
        pathLikelihood,
      );
    }
  }
  if (teamIds.length === 1) {
    return lookupTeamMetricPct(
      pathContext,
      role,
      teamIds[0],
      teamMetricMode,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
  }
  return lookupClusterMetricPct(
    pathContext,
    role,
    teamIds.map((teamId) => ({
      bracket_contestant_id: teamId,
      display_name: '',
      image_url: null,
    })),
    teamMetricMode,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
  );
}

function buildPathOutcomeCounts(
  leaves: LeafPath[],
  hasThirdPlace: boolean,
): Map<string, number> {
  const counts = new Map<string, number>();
  const bump = (key: string) => {
    counts.set(key, (counts.get(key) ?? 0) + 1);
  };

  for (const leaf of leaves) {
    const championId = leaf.champion.bracket_contestant_id;
    const runnerUpId = leaf.runnerUp.bracket_contestant_id;
    bump(pathOutcomeKey(championId));
    bump(pathOutcomeKey(championId, runnerUpId));
    if (hasThirdPlace) {
      if (!leaf.third) continue;
      const thirdId = leaf.third.bracket_contestant_id;
      bump(pathOutcomeKey(championId, runnerUpId, thirdId));
      if (leaf.fourth) {
        bump(pathOutcomeKey(championId, runnerUpId, thirdId, leaf.fourth.bracket_contestant_id));
      }
    } else {
      for (const semi of leaf.semifinalists ?? []) {
        bump(pathOutcomeKey(championId, runnerUpId, undefined, undefined, semi.bracket_contestant_id));
      }
    }
  }
  return counts;
}

function buildPathContext(row: DisplayRow, role: PlacementRole): PathContext {
  return {
    championId: row.champion.bracket_contestant_id,
    runnerUpIds: row.runnerUpTeams.map((team) => team.bracket_contestant_id),
    thirdIds:
      role === 'fourth' || role === 'semi'
        ? row.thirdTeams.map((team) => team.bracket_contestant_id)
        : [],
  };
}

function pathMetricKeys(
  context: PathContext,
  role: PlacementRole,
  teamId: number,
): string[] {
  if (role === 'champion') {
    return [pathOutcomeKey(teamId)];
  }
  if (role === 'runner_up') {
    return [pathOutcomeKey(context.championId, teamId)];
  }
  if (role === 'third') {
    return context.runnerUpIds.map((runnerUpId) =>
      pathOutcomeKey(context.championId, runnerUpId, teamId),
    );
  }
  if (role === 'fourth') {
    const keys: string[] = [];
    for (const runnerUpId of context.runnerUpIds) {
      if (context.thirdIds.length === 0) continue;
      for (const thirdId of context.thirdIds) {
        keys.push(pathOutcomeKey(context.championId, runnerUpId, thirdId, teamId));
      }
    }
    return keys;
  }
  return context.runnerUpIds.map((runnerUpId) =>
    pathOutcomeKey(context.championId, runnerUpId, undefined, undefined, teamId),
  );
}

function sumPathMetricValues(
  keys: string[],
  teamMetricMode: TeamMetricMode,
  pathOutcomeCounts: Map<string, number>,
  pathLikelihood?: Record<string, number>,
): number | null {
  if (keys.length === 0) return null;
  let total = 0;
  let found = false;
  for (const key of keys) {
    const value =
      teamMetricMode === 'outcomes'
        ? pathOutcomeCounts.get(key)
        : pathLikelihood?.[key];
    if (value == null || Number.isNaN(value)) continue;
    total += value;
    found = true;
  }
  return found ? total : null;
}

function formatRoundedTeamMetricPct(
  rawValue: number,
  teamMetricMode: TeamMetricMode,
  globalOutcomeTotal: number,
): string {
  const value =
    teamMetricMode === 'outcomes'
      ? (100 * rawValue) / globalOutcomeTotal
      : rawValue;
  if (value > 0 && value < 1) return '<1%';
  if (value > 99 && value < 100) return '>99%';
  return `${Math.round(value)}%`;
}

function lookupTeamMetricPct(
  context: PathContext,
  role: PlacementRole,
  teamId: number,
  teamMetricMode: TeamMetricMode,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): string | null {
  if (teamMetricMode === 'outcomes' && globalOutcomeTotal === 0) {
    return null;
  }
  const keys = pathMetricKeys(context, role, teamId);
  const raw = sumPathMetricValues(
    keys,
    teamMetricMode,
    pathOutcomeCounts,
    pathLikelihood,
  );
  if (raw == null) return null;
  return formatRoundedTeamMetricPct(
    raw,
    teamMetricMode,
    globalOutcomeTotal,
  );
}

function lookupClusterMetricPct(
  context: PathContext,
  role: PlacementRole,
  teams: ChallengeStatsSimilarityTeam[],
  teamMetricMode: TeamMetricMode,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): string | null {
  if (teamMetricMode === 'outcomes' && globalOutcomeTotal === 0) {
    return null;
  }
  let total = 0;
  let found = false;
  for (const team of teams) {
    const keys = pathMetricKeys(context, role, team.bracket_contestant_id);
    const raw = sumPathMetricValues(
      keys,
      teamMetricMode,
      pathOutcomeCounts,
      pathLikelihood,
    );
    if (raw == null) continue;
    total += raw;
    found = true;
  }
  if (!found) return null;
  return formatRoundedTeamMetricPct(
    total,
    teamMetricMode,
    globalOutcomeTotal,
  );
}

function teamMetricSortScore(
  context: PathContext,
  role: PlacementRole,
  teamId: number,
  sortKey: SortKey,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): number {
  if (sortKey === 'name') return 0;
  const metricMode: TeamMetricMode =
    sortKey === 'likelihood' ? 'likelihood' : 'outcomes';
  const raw = sumPathMetricValues(
    pathMetricKeys(context, role, teamId),
    metricMode,
    pathOutcomeCounts,
    pathLikelihood,
  );
  if (raw == null) return -1;
  if (sortKey === 'likelihood') return raw;
  return globalOutcomeTotal > 0 ? (100 * raw) / globalOutcomeTotal : raw;
}

function sortTeamsForPathSort(
  teams: ChallengeStatsSimilarityTeam[],
  context: PathContext,
  role: PlacementRole,
  sortKey: SortKey,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): ChallengeStatsSimilarityTeam[] {
  if (sortKey === 'name') {
    return sortTeams(teams);
  }
  return [...teams].sort((a, b) => {
    const scoreA = teamMetricSortScore(
      context,
      role,
      a.bracket_contestant_id,
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    const scoreB = teamMetricSortScore(
      context,
      role,
      b.bracket_contestant_id,
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    if (scoreB !== scoreA) return scoreB - scoreA;
    return a.display_name.localeCompare(b.display_name, undefined, {
      sensitivity: 'base',
    });
  });
}

function placementTeamsNameKey(teams: ChallengeStatsSimilarityTeam[]): string {
  return sortTeams(teams)
    .map((team) => team.display_name)
    .join(', ');
}

function placementColumnSortScore(
  row: DisplayRow,
  role: PlacementRole,
  teams: ChallengeStatsSimilarityTeam[],
  universe: ChallengeStatsSimilarityTeam[],
  sortKey: SortKey,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): number {
  if (teams.length === 0) return -1;
  const context = buildPathContext(row, role);
  const clusterTeams = isExhaustiveCluster(teams, universe) ? universe : teams;
  let total = 0;
  let found = false;
  for (const team of clusterTeams) {
    const score = teamMetricSortScore(
      context,
      role,
      team.bracket_contestant_id,
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    if (score < 0) continue;
    total += score;
    found = true;
  }
  return found ? total : -1;
}

function compareDisplayRows(
  a: DisplayRow,
  b: DisplayRow,
  sortKey: SortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): number {
  const champIdA = a.champion.bracket_contestant_id;
  const champIdB = b.champion.bracket_contestant_id;
  const ruIdsA = new Set(a.runnerUpTeams.map((team) => team.bracket_contestant_id));
  const ruIdsB = new Set(b.runnerUpTeams.map((team) => team.bracket_contestant_id));

  if (sortKey === 'name') {
    const cmpChamp = a.champion.display_name.localeCompare(
      b.champion.display_name,
      undefined,
      { sensitivity: 'base' },
    );
    if (cmpChamp !== 0) return cmpChamp;
    const cmpRu = placementTeamsNameKey(a.runnerUpTeams).localeCompare(
      placementTeamsNameKey(b.runnerUpTeams),
      undefined,
      { sensitivity: 'base' },
    );
    if (cmpRu !== 0) return cmpRu;
    if (hasThirdPlace) {
      const cmpThird = placementTeamsNameKey(a.thirdTeams).localeCompare(
        placementTeamsNameKey(b.thirdTeams),
        undefined,
        { sensitivity: 'base' },
      );
      if (cmpThird !== 0) return cmpThird;
      const cmpFourth = placementTeamsNameKey(a.fourthTeams).localeCompare(
        placementTeamsNameKey(b.fourthTeams),
        undefined,
        { sensitivity: 'base' },
      );
      if (cmpFourth !== 0) return cmpFourth;
    } else {
      const cmpSemi = placementTeamsNameKey(a.semiTeams).localeCompare(
        placementTeamsNameKey(b.semiTeams),
        undefined,
        { sensitivity: 'base' },
      );
      if (cmpSemi !== 0) return cmpSemi;
    }
    return winnersKey(a.winners).localeCompare(winnersKey(b.winners));
  }

  const ruScoreA = placementColumnSortScore(
    a,
    'runner_up',
    a.runnerUpTeams,
    universe.runnerUps(champIdA),
    sortKey,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
  );
  const ruScoreB = placementColumnSortScore(
    b,
    'runner_up',
    b.runnerUpTeams,
    universe.runnerUps(champIdB),
    sortKey,
    pathOutcomeCounts,
    globalOutcomeTotal,
    pathLikelihood,
  );
  if (ruScoreB !== ruScoreA) return ruScoreB - ruScoreA;

  if (hasThirdPlace) {
    const thirdScoreA = placementColumnSortScore(
      a,
      'third',
      a.thirdTeams,
      universe.thirds(champIdA, ruIdsA),
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    const thirdScoreB = placementColumnSortScore(
      b,
      'third',
      b.thirdTeams,
      universe.thirds(champIdB, ruIdsB),
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    if (thirdScoreB !== thirdScoreA) return thirdScoreB - thirdScoreA;

    const thirdIdsA = new Set(
      a.thirdTeams.map((team) => team.bracket_contestant_id),
    );
    const thirdIdsB = new Set(
      b.thirdTeams.map((team) => team.bracket_contestant_id),
    );
    const fourthScoreA = placementColumnSortScore(
      a,
      'fourth',
      a.fourthTeams,
      universe.fourths(champIdA, ruIdsA, thirdIdsA),
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    const fourthScoreB = placementColumnSortScore(
      b,
      'fourth',
      b.fourthTeams,
      universe.fourths(champIdB, ruIdsB, thirdIdsB),
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    if (fourthScoreB !== fourthScoreA) return fourthScoreB - fourthScoreA;
  } else {
    const semiScoreA = placementColumnSortScore(
      a,
      'semi',
      a.semiTeams,
      universe.semis(champIdA, ruIdsA),
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    const semiScoreB = placementColumnSortScore(
      b,
      'semi',
      b.semiTeams,
      universe.semis(champIdB, ruIdsB),
      sortKey,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    );
    if (semiScoreB !== semiScoreA) return semiScoreB - semiScoreA;
  }

  return winnersKey(a.winners).localeCompare(winnersKey(b.winners));
}

function sortOutcomeDisplayRows(
  rows: DisplayRow[],
  sortKey: SortKey,
  hasThirdPlace: boolean,
  universe: OutcomeGlobalUniverse,
  pathOutcomeCounts: Map<string, number>,
  globalOutcomeTotal: number,
  pathLikelihood?: Record<string, number>,
): DisplayRow[] {
  return [...rows].sort((a, b) =>
    compareDisplayRows(
      a,
      b,
      sortKey,
      hasThirdPlace,
      universe,
      pathOutcomeCounts,
      globalOutcomeTotal,
      pathLikelihood,
    ),
  );
}

function compareOutcomesSort(
  a: ChallengeOutcomesWinnerOdds,
  b: ChallengeOutcomesWinnerOdds,
  sortKey: SortKey,
): number {
  if (sortKey === 'name') {
    return a.entry.display_name.localeCompare(b.entry.display_name, undefined, {
      sensitivity: 'base',
    });
  }
  if (sortKey === 'likelihood') {
    const la = a.likelihood ?? -1;
    const lb = b.likelihood ?? -1;
    if (lb !== la) return lb - la;
    return a.entry.display_name.localeCompare(b.entry.display_name, undefined, {
      sensitivity: 'base',
    });
  }
  if (b.outcome_count !== a.outcome_count) {
    return b.outcome_count - a.outcome_count;
  }
  return a.entry.display_name.localeCompare(b.entry.display_name, undefined, {
    sensitivity: 'base',
  });
}

function sortWinnerOdds(
  rows: ChallengeOutcomesWinnerOdds[],
  sortKey: SortKey,
): ChallengeOutcomesWinnerOdds[] {
  return [...rows].sort((a, b) => compareOutcomesSort(a, b, sortKey));
}

function championCardMetricScore(
  champId: number,
  metric: 'outcome_count' | 'likelihood',
  pathOutcomeCounts: Map<string, number>,
  pathLikelihood?: Record<string, number>,
): number {
  const context: PathContext = {
    championId: champId,
    runnerUpIds: [],
    thirdIds: [],
  };
  const teamMetricMode: TeamMetricMode =
    metric === 'likelihood' ? 'likelihood' : 'outcomes';
  const raw = sumPathMetricValues(
    pathMetricKeys(context, 'champion', champId),
    teamMetricMode,
    pathOutcomeCounts,
    pathLikelihood,
  );
  return raw ?? -1;
}

function WinnerOddsTable({
  winnerOdds,
  onSelectPlayer,
  viewerUsername,
}: {
  winnerOdds: ChallengeOutcomesWinnerOdds[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  if (winnerOdds.length === 0) return null;

  return (
    <article className="challenge-stats__sim-card challenge-outcomes__summary-card">
      <div className="challenge-stats__sim-scroll">
        <table className="challenge-stats__sim-table challenge-outcomes__summary-table">
          <colgroup>
            <col />
            <col className="challenge-outcomes__summary-col--pct" />
            <col className="challenge-outcomes__summary-col--likelihood" />
          </colgroup>
          <thead>
            <tr>
              <th
                scope="col"
                className="challenge-outcomes__summary-th--winner"
              >
                Winner
              </th>
              <th scope="col" className="challenge-outcomes__summary-th--pct">
                % of Outcomes
              </th>
              <th
                scope="col"
                className="challenge-outcomes__summary-th--likelihood"
              >
                Likelihood
              </th>
            </tr>
          </thead>
          <tbody>
            {winnerOdds.map((row) => (
              <tr key={row.entry.user_bracket_id}>
                <td className="challenge-outcomes__summary-winner">
                  <WinnerName
                    winner={row.entry}
                    onSelectPlayer={onSelectPlayer}
                    viewerUsername={viewerUsername}
                  />
                </td>
                <td className="challenge-outcomes__summary-pct">
                  <span className="challenge-outcomes__metric-value">
                    {formatOutcomePct(row.pct)}
                  </span>
                </td>
                <td className="challenge-outcomes__summary-likelihood">
                  <span className="challenge-outcomes__metric-value">
                    {formatLikelihood(row.likelihood)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function rowDividerLevel(rows: TableRow[], rowIndex: number): number {
  if (rowIndex === 0) return 0;
  const prev = rows[rowIndex - 1];
  const curr = rows[rowIndex];
  if (prev.champion.bracket_contestant_id !== curr.champion.bracket_contestant_id) {
    return 3;
  }
  if (teamSetKey(prev.runnerUpTeams) !== teamSetKey(curr.runnerUpTeams)) {
    return 2;
  }
  return 1;
}

function PathsTable({
  rows,
  hasThirdPlace,
  universe,
  onSelectPlayer,
  viewerUsername,
  teamMetricMode,
  pathOutcomeCounts,
  globalOutcomeTotal,
  pathLikelihood,
  sortKey,
  groupMode,
  allLeaves,
}: {
  rows: TableRow[];
  hasThirdPlace: boolean;
  universe: OutcomeGlobalUniverse;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
  teamMetricMode: TeamMetricMode;
  pathOutcomeCounts: Map<string, number>;
  globalOutcomeTotal: number;
  pathLikelihood?: Record<string, number>;
  sortKey: SortKey;
  groupMode: GroupMode;
  allLeaves: LeafPath[];
}) {
  return (
    <div className="challenge-stats__sim-scroll">
      <table
        className={[
          'challenge-stats__sim-table',
          'challenge-outcomes__table',
          hasThirdPlace ? '' : 'challenge-stats__sim--no-third',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <colgroup>
          <col className="challenge-stats__sim-col challenge-stats__sim-col--champ challenge-outcomes__col--champ" />
          <col className="challenge-stats__sim-col challenge-stats__sim-col--ru challenge-outcomes__col--placement" />
          {hasThirdPlace ? (
            <>
              <col className="challenge-stats__sim-col challenge-stats__sim-col--third challenge-outcomes__col--placement" />
              <col className="challenge-stats__sim-col challenge-stats__sim-col--fourth challenge-outcomes__col--placement" />
            </>
          ) : (
            <col className="challenge-stats__sim-col challenge-stats__sim-col--semi challenge-outcomes__col--placement" />
          )}
          <col className="challenge-stats__sim-col challenge-stats__sim-col--entries challenge-outcomes__col--winner" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Champion</th>
            <th scope="col">Runner-Up</th>
            {hasThirdPlace ? (
              <>
                <th scope="col">Third Place</th>
                <th scope="col">Fourth Place</th>
              </>
            ) : (
              <th scope="col">Semi Final</th>
            )}
            <th scope="col" className="challenge-outcomes__th--winner">
              Winner
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => {
            const champId = row.champion.bracket_contestant_id;
            const ruIds = new Set(
              row.runnerUpTeams.map((team) => team.bracket_contestant_id),
            );
            const thirdIds = new Set(
              row.thirdTeams.map((team) => team.bracket_contestant_id),
            );
            const champContext = buildPathContext(row, 'champion');
            const ruContext = buildPathContext(row, 'runner_up');
            const thirdContext = buildPathContext(row, 'third');
            const fourthContext = buildPathContext(row, 'fourth');
            const semiContext = buildPathContext(row, 'semi');
            const entryMetric =
              groupMode === 'entry'
                ? { row, allLeaves, hasThirdPlace }
                : undefined;

            return (
              <tr
                key={`${champId}-${teamSetKey(row.runnerUpTeams)}-${teamSetKey(row.thirdTeams)}-${teamSetKey(row.fourthTeams)}-${teamSetKey(row.semiTeams)}-${winnersKey(row.winners)}`}
                className={
                  rowDividerLevel(rows, rowIndex) > 0
                    ? `challenge-stats__sim-row challenge-stats__sim-row--div-${rowDividerLevel(rows, rowIndex)}`
                    : 'challenge-stats__sim-row'
                }
              >
                {row.showChampCell ? (
                  <td
                    rowSpan={row.champRowSpan}
                    className="challenge-stats__sim-td--champ"
                  >
                    <TeamFlag
                      team={row.champion}
                      size="lg"
                      metricPct={
                        groupMode === 'entry'
                          ? lookupEntryChampionMetricPct(
                              row,
                              allLeaves,
                              hasThirdPlace,
                              teamMetricMode,
                              globalOutcomeTotal,
                              pathLikelihood,
                            )
                          : lookupTeamMetricPct(
                              champContext,
                              'champion',
                              row.champion.bracket_contestant_id,
                              teamMetricMode,
                              pathOutcomeCounts,
                              globalOutcomeTotal,
                              pathLikelihood,
                            )
                      }
                    />
                  </td>
                ) : null}
                {row.showRuCell ? (
                  <td rowSpan={row.ruRowSpan}>
                    <PlacementCell
                      teams={row.runnerUpTeams}
                      universe={universe.runnerUps(champId)}
                      singleSize="md"
                      allLabel="Any remaining runner-up"
                      role="runner_up"
                      pathContext={ruContext}
                      teamMetricMode={teamMetricMode}
                      pathOutcomeCounts={pathOutcomeCounts}
                      globalOutcomeTotal={globalOutcomeTotal}
                      pathLikelihood={pathLikelihood}
                      sortKey={sortKey}
                      groupMode={groupMode}
                      entryMetric={entryMetric}
                    />
                  </td>
                ) : null}
                {hasThirdPlace ? (
                  <>
                    {row.showThirdCell ? (
                      <td rowSpan={row.thirdRowSpan}>
                        <PlacementCell
                          teams={row.thirdTeams}
                          universe={universe.thirds(champId, ruIds)}
                          allLabel="Any remaining third-place finish"
                          role="third"
                          pathContext={thirdContext}
                          teamMetricMode={teamMetricMode}
                          pathOutcomeCounts={pathOutcomeCounts}
                          globalOutcomeTotal={globalOutcomeTotal}
                          pathLikelihood={pathLikelihood}
                          sortKey={sortKey}
                          groupMode={groupMode}
                          entryMetric={entryMetric}
                        />
                      </td>
                    ) : null}
                    <td>
                      <PlacementCell
                        teams={row.fourthTeams}
                        universe={universe.fourths(champId, ruIds, thirdIds)}
                        allLabel="Any remaining fourth-place finish"
                        role="fourth"
                        pathContext={fourthContext}
                        teamMetricMode={teamMetricMode}
                        pathOutcomeCounts={pathOutcomeCounts}
                        globalOutcomeTotal={globalOutcomeTotal}
                        pathLikelihood={pathLikelihood}
                        sortKey={sortKey}
                        groupMode={groupMode}
                        entryMetric={entryMetric}
                      />
                    </td>
                  </>
                ) : (
                  <td>
                    <PlacementCell
                      teams={row.semiTeams}
                      universe={universe.semis(champId, ruIds)}
                      singleSize="sm"
                      allLabel="Any remaining semi-finalists"
                      role="semi"
                      pathContext={semiContext}
                      teamMetricMode={teamMetricMode}
                      pathOutcomeCounts={pathOutcomeCounts}
                      globalOutcomeTotal={globalOutcomeTotal}
                      pathLikelihood={pathLikelihood}
                      sortKey={sortKey}
                      groupMode={groupMode}
                      entryMetric={entryMetric}
                    />
                  </td>
                )}
                <td className="challenge-outcomes__td--winner">
                  <WinnerList
                    winners={row.winners}
                    onSelectPlayer={onSelectPlayer}
                    viewerUsername={viewerUsername}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ChallengeOutcomes({
  hasThirdPlace,
  winnerOdds,
  teamLikelihood,
  tree,
  onSelectPlayer,
  viewerUsername,
}: Props) {
  const [groupMode, setGroupMode] = useState<GroupMode>('entry');
  const [sortKey, setSortKey] = useState<SortKey>('outcomes');
  const [teamMetricMode, setTeamMetricMode] =
    useState<TeamMetricMode>('outcomes');

  const viewModel = useMemo(() => {
    if (tree.length === 0) return null;

    const allLeaves = collectOutcomeLeafPaths(tree, hasThirdPlace);
    const universe = new OutcomeGlobalUniverse(allLeaves);

    const globalDisplayRows = buildOutcomeDisplayRows(
      allLeaves,
      hasThirdPlace,
      universe,
    );

    const entryCards = winnerOdds
      .map((odds) => {
        const displayRows = globalDisplayRows.filter((row) =>
          row.winners.some(
            (winner) => winner.user_bracket_id === odds.entry.user_bracket_id,
          ),
        );
        return {
          odds,
          displayRows,
        };
      })
      .filter((card) => card.displayRows.length > 0);

    const teamDisplayRows = globalDisplayRows;

    const teamChampionCards: {
      champId: number;
      displayRows: DisplayRow[];
    }[] = [];
    const byChamp = new Map<number, DisplayRow[]>();
    for (const row of teamDisplayRows) {
      const id = row.champion.bracket_contestant_id;
      const bucket = byChamp.get(id) ?? [];
      bucket.push({
        champion: row.champion,
        runnerUpTeams: row.runnerUpTeams,
        thirdTeams: row.thirdTeams,
        fourthTeams: row.fourthTeams,
        semiTeams: row.semiTeams,
        winners: row.winners,
      });
      byChamp.set(id, bucket);
    }
    for (const [champId, displayRows] of byChamp) {
      teamChampionCards.push({
        champId,
        displayRows,
      });
    }

    return { universe, entryCards, teamChampionCards, allLeaves };
  }, [tree, hasThirdPlace, winnerOdds]);

  const entryCards = viewModel?.entryCards ?? [];
  const teamChampionCards = viewModel?.teamChampionCards ?? [];
  const universe = viewModel?.universe;
  const allLeaves = viewModel?.allLeaves ?? [];
  const globalOutcomeTotal = allLeaves.length;

  const pathOutcomeCounts = useMemo(
    () => buildPathOutcomeCounts(allLeaves, hasThirdPlace),
    [allLeaves, hasThirdPlace],
  );

  const sortedWinnerOdds = useMemo(
    () => sortWinnerOdds(winnerOdds, sortKey),
    [winnerOdds, sortKey],
  );

  const sortedEntryCards = useMemo(() => {
    if (universe == null) return [];
    return [...entryCards]
      .sort((a, b) => compareOutcomesSort(a.odds, b.odds, sortKey))
      .map((card) => ({
        ...card,
        rows: flattenTableRows(
          sortOutcomeDisplayRows(
            card.displayRows,
            sortKey,
            hasThirdPlace,
            universe,
            pathOutcomeCounts,
            globalOutcomeTotal,
            teamLikelihood,
          ),
        ),
      }));
  }, [
    entryCards,
    sortKey,
    hasThirdPlace,
    universe,
    pathOutcomeCounts,
    globalOutcomeTotal,
    teamLikelihood,
  ]);

  const sortedTeamChampionCards = useMemo(() => {
    if (universe == null) return [];
    const cards = [...teamChampionCards];
    cards.sort((a, b) => {
      const champA = a.displayRows[0]?.champion;
      const champB = b.displayRows[0]?.champion;
      if (!champA || !champB) return 0;

      if (sortKey === 'name') {
        return champA.display_name.localeCompare(champB.display_name, undefined, {
          sensitivity: 'base',
        });
      }

      const metric =
        sortKey === 'likelihood' ? 'likelihood' : 'outcome_count';
      const scoreA = championCardMetricScore(
        a.champId,
        metric,
        pathOutcomeCounts,
        teamLikelihood,
      );
      const scoreB = championCardMetricScore(
        b.champId,
        metric,
        pathOutcomeCounts,
        teamLikelihood,
      );
      if (scoreB !== scoreA) return scoreB - scoreA;

      return champA.display_name.localeCompare(champB.display_name, undefined, {
        sensitivity: 'base',
      });
    });
    return cards.map((card) => ({
      ...card,
      rows: flattenTableRows(
        sortOutcomeDisplayRows(
          card.displayRows,
          sortKey,
          hasThirdPlace,
          universe,
          pathOutcomeCounts,
          globalOutcomeTotal,
          teamLikelihood,
        ),
      ),
    }));
  }, [
    teamChampionCards,
    sortKey,
    hasThirdPlace,
    universe,
    pathOutcomeCounts,
    globalOutcomeTotal,
    teamLikelihood,
  ]);

  if (viewModel == null || universe == null) {
    return (
      <p className="challenge-stats__group-points-empty">
        No remaining outcomes to show yet.
      </p>
    );
  }

  const sortNameLabel = groupMode === 'entry' ? 'Entry' : 'Team';

  return (
    <div className="challenge-outcomes__layout">
      <aside className="challenge-outcomes__summary">
        <WinnerOddsTable
          winnerOdds={sortedWinnerOdds}
          onSelectPlayer={onSelectPlayer}
          viewerUsername={viewerUsername}
        />
      </aside>
      <div
        className={[
          'challenge-outcomes__detail',
          'challenge-stats__sim',
          hasThirdPlace ? '' : 'challenge-stats__sim--no-third',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <div className="challenge-outcomes__toolbar">
          <div className="challenge-outcomes__toolbar-grouping">
            <div
              className="challenge-outcomes__mode segmented"
              role="group"
              aria-label="Outcomes grouping"
            >
              <button
                type="button"
                aria-pressed={groupMode === 'entry'}
                onClick={() => setGroupMode('entry')}
              >
                ENTRY
              </button>
              <button
                type="button"
                aria-pressed={groupMode === 'team'}
                onClick={() => setGroupMode('team')}
              >
                TEAM
              </button>
            </div>
            <div
              className="challenge-outcomes__metric-mode segmented"
              role="group"
              aria-label="Team flag metric"
            >
              <button
                type="button"
                aria-pressed={teamMetricMode === 'outcomes'}
                onClick={() => setTeamMetricMode('outcomes')}
              >
                % Outcomes
              </button>
              <button
                type="button"
                aria-pressed={teamMetricMode === 'likelihood'}
                onClick={() => setTeamMetricMode('likelihood')}
                disabled={teamLikelihood == null}
              >
                Likelihood
              </button>
            </div>
          </div>
          <label className="challenge-outcomes__sort">
            <span className="challenge-outcomes__sort-label">Sort by</span>
            <select
              className="challenge-outcomes__sort-select"
              value={sortKey}
              onChange={(event) =>
                setSortKey(event.target.value as SortKey)
              }
              aria-label="Sort outcomes"
            >
              <option value="outcomes">% of Outcomes</option>
              <option value="likelihood">Likelihood</option>
              <option value="name">{sortNameLabel}</option>
            </select>
          </label>
        </div>

        {groupMode === 'entry' ? (
          <div className="challenge-outcomes__entry-cards">
            {sortedEntryCards.map(({ odds, rows }) => (
              <article
                key={odds.entry.user_bracket_id}
                className="challenge-stats__sim-card challenge-outcomes__entry-card"
              >
                <header className="challenge-outcomes__entry-card-header">
                  <h3 className="challenge-outcomes__entry-card-title">
                    {odds.entry.display_name}
                  </h3>
                  <p className="challenge-outcomes__entry-card-stats">
                    <span className="challenge-outcomes__metric-value">
                      {formatOutcomePct(odds.pct)}
                    </span>
                    <span className="challenge-outcomes__metric-label">
                      of Outcomes
                    </span>
                    <span
                      className="challenge-outcomes__entry-card-stat-sep"
                      aria-hidden
                    >
                      |
                    </span>
                    <span className="challenge-outcomes__metric-value">
                      {formatLikelihood(odds.likelihood)}
                    </span>
                    <span className="challenge-outcomes__metric-label">
                      Likelihood
                    </span>
                  </p>
                </header>
                <PathsTable
                  rows={rows}
                  hasThirdPlace={hasThirdPlace}
                  universe={universe!}
                  onSelectPlayer={onSelectPlayer}
                  viewerUsername={viewerUsername}
                  teamMetricMode={teamMetricMode}
                  pathOutcomeCounts={pathOutcomeCounts}
                  globalOutcomeTotal={globalOutcomeTotal}
                  pathLikelihood={teamLikelihood}
                  sortKey={sortKey}
                  groupMode="entry"
                  allLeaves={allLeaves}
                />
              </article>
            ))}
          </div>
        ) : (
          <div className="challenge-stats__sim-cards">
            {sortedTeamChampionCards.map(({ champId, rows }) => (
              <article key={champId} className="challenge-stats__sim-card">
                <PathsTable
                  rows={rows}
                  hasThirdPlace={hasThirdPlace}
                  universe={universe!}
                  onSelectPlayer={onSelectPlayer}
                  viewerUsername={viewerUsername}
                  teamMetricMode={teamMetricMode}
                  pathOutcomeCounts={pathOutcomeCounts}
                  globalOutcomeTotal={globalOutcomeTotal}
                  pathLikelihood={teamLikelihood}
                  sortKey={sortKey}
                  groupMode="team"
                  allLeaves={allLeaves}
                />
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
