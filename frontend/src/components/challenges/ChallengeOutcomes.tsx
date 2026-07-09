import { useMemo, useState } from 'react';

import type {
  ChallengeOutcomesChampionBranch,
  ChallengeOutcomesEntry,
  ChallengeOutcomesWinnerOdds,
  ChallengeStatsSimilarityTeam,
} from '../../utils/api';
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

type LeafPath = {
  champion: ChallengeStatsSimilarityTeam;
  runnerUp: ChallengeStatsSimilarityTeam;
  third?: ChallengeStatsSimilarityTeam;
  fourth?: ChallengeStatsSimilarityTeam;
  semifinalists?: [ChallengeStatsSimilarityTeam, ChallengeStatsSimilarityTeam];
  winners: ChallengeOutcomesEntry[];
};

type DisplayRow = {
  champion: ChallengeStatsSimilarityTeam;
  runnerUpTeams: ChallengeStatsSimilarityTeam[];
  thirdTeams: ChallengeStatsSimilarityTeam[];
  fourthTeams: ChallengeStatsSimilarityTeam[];
  semiTeams: ChallengeStatsSimilarityTeam[];
  winners: ChallengeOutcomesEntry[];
};

type TableRow = DisplayRow & {
  showChampCell: boolean;
  champRowSpan: number;
  showRuCell: boolean;
  ruRowSpan: number;
  showThirdCell: boolean;
  thirdRowSpan: number;
};

function teamSortKey(team: ChallengeStatsSimilarityTeam): string {
  return team.display_name.toLocaleLowerCase();
}

function sortTeams(
  teams: Iterable<ChallengeStatsSimilarityTeam>,
): ChallengeStatsSimilarityTeam[] {
  return [...teams].sort((a, b) =>
    teamSortKey(a).localeCompare(teamSortKey(b), undefined, {
      sensitivity: 'base',
    }),
  );
}

function dedupeTeams(
  teams: ChallengeStatsSimilarityTeam[],
): ChallengeStatsSimilarityTeam[] {
  const byId = new Map<number, ChallengeStatsSimilarityTeam>();
  for (const team of teams) {
    byId.set(team.bracket_contestant_id, team);
  }
  return sortTeams(byId.values());
}

function teamSetKey(teams: ChallengeStatsSimilarityTeam[]): string {
  return teams
    .map((team) => team.bracket_contestant_id)
    .sort((a, b) => a - b)
    .join(',');
}

function winnersKey(winners: ChallengeOutcomesEntry[]): string {
  return winners
    .map((entry) => entry.user_bracket_id)
    .sort((a, b) => a - b)
    .join(',');
}

function sortWinners(winners: ChallengeOutcomesEntry[]): ChallengeOutcomesEntry[] {
  return [...winners].sort((a, b) =>
    a.display_name.localeCompare(b.display_name, undefined, {
      sensitivity: 'base',
    }),
  );
}

function collectAllLeafPaths(
  tree: ChallengeOutcomesChampionBranch[],
  hasThirdPlace: boolean,
): LeafPath[] {
  const rows: LeafPath[] = [];
  for (const champ of tree) {
    for (const ru of champ.children) {
      if (hasThirdPlace) {
        for (const third of ru.children) {
          for (const fourth of third.children) {
            for (const leaf of fourth.children) {
              rows.push({
                champion: champ.team,
                runnerUp: ru.team,
                third: third.team,
                fourth: fourth.team,
                winners: sortWinners(leaf.winners),
              });
            }
          }
        }
      } else {
        for (const third of ru.children) {
          const fourth = third.children[0];
          if (!fourth) continue;
          for (const leaf of fourth.children) {
            rows.push({
              champion: champ.team,
              runnerUp: ru.team,
              semifinalists: [third.team, fourth.team],
              winners: sortWinners(leaf.winners),
            });
          }
        }
      }
    }
  }
  return rows;
}

function isExhaustiveCluster(
  teams: ChallengeStatsSimilarityTeam[],
  universe: ChallengeStatsSimilarityTeam[],
): boolean {
  if (teams.length === 0 || universe.length === 0) return false;
  if (universe.length <= 1) return false;
  return teamSetKey(teams) === teamSetKey(universe);
}

/** Global remaining teams under a prefix — from the FULL outcome tree. */
class GlobalUniverse {
  constructor(private readonly allLeaves: LeafPath[]) {}

  runnerUps(championId: number): ChallengeStatsSimilarityTeam[] {
    return dedupeTeams(
      this.allLeaves
        .filter((row) => row.champion.bracket_contestant_id === championId)
        .map((row) => row.runnerUp),
    );
  }

  thirds(championId: number, runnerUpIds: Set<number>): ChallengeStatsSimilarityTeam[] {
    return dedupeTeams(
      this.allLeaves
        .filter(
          (row) =>
            row.champion.bracket_contestant_id === championId &&
            runnerUpIds.has(row.runnerUp.bracket_contestant_id) &&
            row.third,
        )
        .map((row) => row.third!),
    );
  }

  fourths(
    championId: number,
    runnerUpIds: Set<number>,
    thirdIds: Set<number>,
  ): ChallengeStatsSimilarityTeam[] {
    return dedupeTeams(
      this.allLeaves
        .filter(
          (row) =>
            row.champion.bracket_contestant_id === championId &&
            runnerUpIds.has(row.runnerUp.bracket_contestant_id) &&
            row.third &&
            thirdIds.has(row.third.bracket_contestant_id) &&
            row.fourth,
        )
        .map((row) => row.fourth!),
    );
  }

  semis(championId: number, runnerUpIds: Set<number>): ChallengeStatsSimilarityTeam[] {
    const teams: ChallengeStatsSimilarityTeam[] = [];
    for (const row of this.allLeaves) {
      if (
        row.champion.bracket_contestant_id !== championId ||
        !runnerUpIds.has(row.runnerUp.bracket_contestant_id) ||
        !row.semifinalists
      ) {
        continue;
      }
      teams.push(...row.semifinalists);
    }
    return dedupeTeams(teams);
  }
}

type PlacementSlice = {
  thirdTeams: ChallengeStatsSimilarityTeam[];
  fourthTeams: ChallengeStatsSimilarityTeam[];
  winners: ChallengeOutcomesEntry[];
};

type SemiSlice = {
  semiTeams: ChallengeStatsSimilarityTeam[];
  winners: ChallengeOutcomesEntry[];
};

/**
 * Under one (champion, runner-up) for one entry: merge thirds that share the
 * same fourth pattern + winner set. ALL uses the GLOBAL remaining teams.
 */
function buildPlacementSlices(
  ruLeaves: LeafPath[],
  universe: GlobalUniverse,
  championId: number,
  runnerUpId: number,
): PlacementSlice[] {
  const ruIds = new Set([runnerUpId]);
  const byThird = new Map<number, LeafPath[]>();
  for (const leaf of ruLeaves) {
    if (!leaf.third || !leaf.fourth) continue;
    const id = leaf.third.bracket_contestant_id;
    const bucket = byThird.get(id) ?? [];
    bucket.push(leaf);
    byThird.set(id, bucket);
  }

  type Acc = {
    thirdTeams: ChallengeStatsSimilarityTeam[];
    fourthTeams: ChallengeStatsSimilarityTeam[];
    winners: ChallengeOutcomesEntry[];
  };
  const byKey = new Map<string, Acc>();

  for (const thirdLeaves of byThird.values()) {
    const third = thirdLeaves[0].third!;
    // Group this third's leaves by winner-set, collecting fourths under each.
    const byWinners = new Map<string, LeafPath[]>();
    for (const leaf of thirdLeaves) {
      const key = winnersKey(leaf.winners);
      const bucket = byWinners.get(key) ?? [];
      bucket.push(leaf);
      byWinners.set(key, bucket);
    }

    for (const winnerLeaves of byWinners.values()) {
      const groupFourths = dedupeTeams(winnerLeaves.map((leaf) => leaf.fourth!));
      const groupWinners = sortWinners(winnerLeaves[0].winners);
      const fourthUniverse = universe.fourths(
        championId,
        ruIds,
        new Set([third.bracket_contestant_id]),
      );
      const fourthKey = isExhaustiveCluster(groupFourths, fourthUniverse)
        ? '__ALL__'
        : teamSetKey(groupFourths);
      const mergeKey = `${fourthKey}|${winnersKey(groupWinners)}`;
      const existing = byKey.get(mergeKey);
      if (existing) {
        existing.thirdTeams.push(third);
        existing.fourthTeams = dedupeTeams([
          ...existing.fourthTeams,
          ...groupFourths,
        ]);
      } else {
        byKey.set(mergeKey, {
          thirdTeams: [third],
          fourthTeams: groupFourths,
          winners: groupWinners,
        });
      }
    }
  }

  return [...byKey.values()]
    .map((group) => ({
      thirdTeams: dedupeTeams(group.thirdTeams),
      fourthTeams: group.fourthTeams,
      winners: group.winners,
    }))
    .sort((a, b) =>
      teamSortKey(a.thirdTeams[0]).localeCompare(
        teamSortKey(b.thirdTeams[0]),
        undefined,
        { sensitivity: 'base' },
      ),
    );
}

function buildSemiSlices(ruLeaves: LeafPath[]): SemiSlice[] {
  const byKey = new Map<string, SemiSlice>();
  for (const leaf of ruLeaves) {
    if (!leaf.semifinalists) continue;
    const semis = sortTeams(leaf.semifinalists);
    const key = `${teamSetKey(semis)}|${winnersKey(leaf.winners)}`;
    if (!byKey.has(key)) {
      byKey.set(key, {
        semiTeams: semis,
        winners: sortWinners(leaf.winners),
      });
    }
  }
  return [...byKey.values()].sort((a, b) =>
    teamSortKey(a.semiTeams[0]).localeCompare(
      teamSortKey(b.semiTeams[0]),
      undefined,
      { sensitivity: 'base' },
    ),
  );
}

function placementPatternKey(
  slices: PlacementSlice[],
  universe: GlobalUniverse,
  championId: number,
  runnerUpId: number,
): string {
  const ruIds = new Set([runnerUpId]);
  return slices
    .map((slice) => {
      const thirdUniverse = universe.thirds(championId, ruIds);
      const thirdKey = isExhaustiveCluster(slice.thirdTeams, thirdUniverse)
        ? '__ALL__'
        : teamSetKey(slice.thirdTeams);
      const thirdIds = new Set(
        slice.thirdTeams.map((team) => team.bracket_contestant_id),
      );
      const fourthUniverse = universe.fourths(championId, ruIds, thirdIds);
      const fourthKey = isExhaustiveCluster(slice.fourthTeams, fourthUniverse)
        ? '__ALL__'
        : teamSetKey(slice.fourthTeams);
      return `${thirdKey}:${fourthKey}:${winnersKey(slice.winners)}`;
    })
    .join('|');
}

function semiPatternKey(slices: SemiSlice[]): string {
  return slices
    .map(
      (slice) => `${teamSetKey(slice.semiTeams)}:${winnersKey(slice.winners)}`,
    )
    .join('|');
}

/**
 * Build compact display rows from a leaf set (one entry's leaves, or every leaf).
 * ALL uses GLOBAL remaining teams from the full tree — never only this leaf set —
 * so "ALL" never hides a path that belongs to someone else.
 */
function buildDisplayRows(
  workingLeaves: LeafPath[],
  hasThirdPlace: boolean,
  universe: GlobalUniverse,
): DisplayRow[] {
  if (workingLeaves.length === 0) return [];

  const byChamp = new Map<number, LeafPath[]>();
  for (const leaf of workingLeaves) {
    const id = leaf.champion.bracket_contestant_id;
    const bucket = byChamp.get(id) ?? [];
    bucket.push(leaf);
    byChamp.set(id, bucket);
  }

  const champIds = [...byChamp.keys()].sort((a, b) => {
    const ca = byChamp.get(a)![0].champion;
    const cb = byChamp.get(b)![0].champion;
    return teamSortKey(ca).localeCompare(teamSortKey(cb), undefined, {
      sensitivity: 'base',
    });
  });

  const rows: DisplayRow[] = [];

  for (const champId of champIds) {
    const champLeaves = byChamp.get(champId)!;
    const champion = champLeaves[0].champion;

    const byRu = new Map<number, LeafPath[]>();
    for (const leaf of champLeaves) {
      const id = leaf.runnerUp.bracket_contestant_id;
      const bucket = byRu.get(id) ?? [];
      bucket.push(leaf);
      byRu.set(id, bucket);
    }

    const ruIds = [...byRu.keys()].sort((a, b) => {
      const ra = byRu.get(a)![0].runnerUp;
      const rb = byRu.get(b)![0].runnerUp;
      return teamSortKey(ra).localeCompare(teamSortKey(rb), undefined, {
        sensitivity: 'base',
      });
    });

    if (hasThirdPlace) {
      // Cluster runner-ups whose third/fourth patterns are the same after
      // normalizing exhaustive columns to ALL (raw team sets may differ
      // across RUs even when both display as ALL).
      const bySig = new Map<
        string,
        {
          runnerUpTeams: ChallengeStatsSimilarityTeam[];
          slices: PlacementSlice[];
        }
      >();

      for (const ruId of ruIds) {
        const ruLeaves = byRu.get(ruId)!;
        const runnerUp = ruLeaves[0].runnerUp;
        const slices = buildPlacementSlices(
          ruLeaves,
          universe,
          champId,
          ruId,
        );
        const sig = placementPatternKey(slices, universe, champId, ruId);
        const existing = bySig.get(sig);
        if (existing && existing.slices.length === slices.length) {
          existing.runnerUpTeams.push(runnerUp);
          // Union placement teams so a merged ALL cluster still covers every
          // RU's thirds/fourths when checked against the wider universe.
          existing.slices = existing.slices.map((slice, index) => ({
            thirdTeams: dedupeTeams([
              ...slice.thirdTeams,
              ...slices[index].thirdTeams,
            ]),
            fourthTeams: dedupeTeams([
              ...slice.fourthTeams,
              ...slices[index].fourthTeams,
            ]),
            winners: slice.winners,
          }));
        } else if (!existing) {
          bySig.set(sig, {
            runnerUpTeams: [runnerUp],
            slices,
          });
        } else {
          // Same ALL-normalized pattern label but different slice counts —
          // keep separate rather than inventing a bad merge.
          bySig.set(`${sig}#${ruId}`, {
            runnerUpTeams: [runnerUp],
            slices,
          });
        }
      }

      const groups = [...bySig.values()].sort((a, b) =>
        teamSortKey(a.runnerUpTeams[0]).localeCompare(
          teamSortKey(b.runnerUpTeams[0]),
          undefined,
          { sensitivity: 'base' },
        ),
      );

      for (const group of groups) {
        const runnerUpTeams = dedupeTeams(group.runnerUpTeams);
        for (const slice of group.slices) {
          rows.push({
            champion,
            runnerUpTeams,
            thirdTeams: slice.thirdTeams,
            fourthTeams: slice.fourthTeams,
            semiTeams: [],
            winners: slice.winners,
          });
        }
      }
    } else {
      const bySig = new Map<
        string,
        {
          runnerUpTeams: ChallengeStatsSimilarityTeam[];
          slices: SemiSlice[];
        }
      >();

      for (const ruId of ruIds) {
        const ruLeaves = byRu.get(ruId)!;
        const runnerUp = ruLeaves[0].runnerUp;
        const slices = buildSemiSlices(ruLeaves);
        const sig = semiPatternKey(slices);
        const existing = bySig.get(sig);
        if (existing) {
          existing.runnerUpTeams.push(runnerUp);
        } else {
          bySig.set(sig, {
            runnerUpTeams: [runnerUp],
            slices,
          });
        }
      }

      const groups = [...bySig.values()].sort((a, b) =>
        teamSortKey(a.runnerUpTeams[0]).localeCompare(
          teamSortKey(b.runnerUpTeams[0]),
          undefined,
          { sensitivity: 'base' },
        ),
      );

      for (const group of groups) {
        const runnerUpTeams = dedupeTeams(group.runnerUpTeams);
        for (const slice of group.slices) {
          rows.push({
            champion,
            runnerUpTeams,
            thirdTeams: [],
            fourthTeams: [],
            semiTeams: slice.semiTeams,
            winners: slice.winners,
          });
        }
      }
    }
  }

  return rows;
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

function TeamCluster({
  teams,
  singleSize = 'sm',
  role,
  teamMetricMode,
  outcomePctIndex,
  teamLikelihood,
  likelihoodScope,
}: {
  teams: ChallengeStatsSimilarityTeam[];
  singleSize?: 'lg' | 'md' | 'sm' | 'xs';
  role: PlacementRole;
  teamMetricMode: TeamMetricMode;
  outcomePctIndex: Map<string, number>;
  teamLikelihood?: Record<string, number>;
  likelihoodScope?: TeamLikelihoodScope;
}) {
  const sorted = sortTeams(teams);
  if (sorted.length === 0) return null;
  if (sorted.length === 1) {
    return (
      <TeamFlag
        team={sorted[0]}
        size={singleSize}
        metricPct={lookupTeamMetricPct(
          role,
          sorted[0].bracket_contestant_id,
          teamMetricMode,
          outcomePctIndex,
          teamLikelihood,
          likelihoodScope,
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
          metricPct={lookupTeamMetricPct(
            role,
            team.bracket_contestant_id,
            teamMetricMode,
            outcomePctIndex,
            teamLikelihood,
            likelihoodScope,
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
  teamMetricMode,
  outcomePctIndex,
  teamLikelihood,
  likelihoodScope,
}: {
  teams: ChallengeStatsSimilarityTeam[];
  universe: ChallengeStatsSimilarityTeam[];
  singleSize?: 'lg' | 'md' | 'sm' | 'xs';
  allLabel: string;
  role: PlacementRole;
  teamMetricMode: TeamMetricMode;
  outcomePctIndex: Map<string, number>;
  teamLikelihood?: Record<string, number>;
  likelihoodScope?: TeamLikelihoodScope;
}) {
  const sorted = sortTeams(teams);
  if (sorted.length === 0) return null;
  if (isExhaustiveCluster(sorted, universe)) {
    return (
      <AllPill
        label={allLabel}
        size={singleSize === 'md' ? 'md' : 'sm'}
        metricPct={lookupClusterMetricPct(
          role,
          universe,
          teamMetricMode,
          outcomePctIndex,
          teamLikelihood,
          likelihoodScope,
        )}
      />
    );
  }
  return (
    <TeamCluster
      teams={sorted}
      singleSize={singleSize}
      role={role}
      teamMetricMode={teamMetricMode}
      outcomePctIndex={outcomePctIndex}
      teamLikelihood={teamLikelihood}
      likelihoodScope={likelihoodScope}
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

function teamMetricKey(role: PlacementRole, teamId: number): string {
  return `${role}:${teamId}`;
}

function teamIdsForLeafRole(
  leaf: LeafPath,
  role: PlacementRole,
  hasThirdPlace: boolean,
): number[] {
  if (role === 'champion') {
    return [leaf.champion.bracket_contestant_id];
  }
  if (role === 'runner_up') {
    return [leaf.runnerUp.bracket_contestant_id];
  }
  if (hasThirdPlace) {
    if (role === 'third') {
      return leaf.third ? [leaf.third.bracket_contestant_id] : [];
    }
    if (role === 'fourth') {
      return leaf.fourth ? [leaf.fourth.bracket_contestant_id] : [];
    }
    return [];
  }
  if (role === 'semi') {
    return (
      leaf.semifinalists?.map((team) => team.bracket_contestant_id) ?? []
    );
  }
  return [];
}

function buildTeamOutcomePctIndex(
  leaves: LeafPath[],
  hasThirdPlace: boolean,
): Map<string, number> {
  const counts = new Map<string, number>();
  const roles: PlacementRole[] = hasThirdPlace
    ? ['champion', 'runner_up', 'third', 'fourth']
    : ['champion', 'runner_up', 'semi'];

  for (const leaf of leaves) {
    for (const role of roles) {
      for (const teamId of teamIdsForLeafRole(leaf, role, hasThirdPlace)) {
        const key = teamMetricKey(role, teamId);
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
  }

  const total = leaves.length;
  const pcts = new Map<string, number>();
  if (total === 0) return pcts;

  for (const [key, count] of counts) {
    pcts.set(key, Math.round((1000 * count) / total) / 10);
  }
  return pcts;
}

function formatTeamMetricPct(value: number): string {
  return `${value.toFixed(1)}%`;
}

type TeamLikelihoodScope =
  | { kind: 'entry'; entryId: number }
  | { kind: 'champion'; championId: number };

function lookupTeamMetricValue(
  role: PlacementRole,
  teamId: number,
  teamMetricMode: TeamMetricMode,
  outcomePctIndex: Map<string, number>,
  teamLikelihood?: Record<string, number>,
  likelihoodScope?: TeamLikelihoodScope,
): number | null {
  const key = teamMetricKey(role, teamId);
  if (teamMetricMode === 'outcomes') {
    const value = outcomePctIndex.get(key);
    return value == null ? null : value;
  }
  const scopedKey =
    likelihoodScope?.kind === 'entry'
      ? `entry:${likelihoodScope.entryId}:${role}:${teamId}`
      : likelihoodScope?.kind === 'champion'
        ? `champion:${likelihoodScope.championId}:${role}:${teamId}`
        : key;
  const value = teamLikelihood?.[scopedKey];
  if (value == null || Number.isNaN(value)) return null;
  return value;
}

function lookupTeamMetricPct(
  role: PlacementRole,
  teamId: number,
  teamMetricMode: TeamMetricMode,
  outcomePctIndex: Map<string, number>,
  teamLikelihood?: Record<string, number>,
  likelihoodScope?: TeamLikelihoodScope,
): string | null {
  const value = lookupTeamMetricValue(
    role,
    teamId,
    teamMetricMode,
    outcomePctIndex,
    teamLikelihood,
    likelihoodScope,
  );
  return value == null ? null : formatTeamMetricPct(value);
}

function lookupClusterMetricPct(
  role: PlacementRole,
  teams: ChallengeStatsSimilarityTeam[],
  teamMetricMode: TeamMetricMode,
  outcomePctIndex: Map<string, number>,
  teamLikelihood?: Record<string, number>,
  likelihoodScope?: TeamLikelihoodScope,
): string | null {
  let total = 0;
  let found = false;
  for (const team of teams) {
    const value = lookupTeamMetricValue(
      role,
      team.bracket_contestant_id,
      teamMetricMode,
      outcomePctIndex,
      teamLikelihood,
      likelihoodScope,
    );
    if (value == null) continue;
    total += value;
    found = true;
  }
  if (!found) return null;
  return formatTeamMetricPct(total);
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

function maxWinnerMetricForRows(
  rows: TableRow[],
  oddsByEntry: Map<number, ChallengeOutcomesWinnerOdds>,
  metric: 'outcome_count' | 'likelihood',
): number {
  let max = -1;
  for (const row of rows) {
    for (const winner of row.winners) {
      const odds = oddsByEntry.get(winner.user_bracket_id);
      if (!odds) continue;
      const value =
        metric === 'outcome_count'
          ? odds.outcome_count
          : (odds.likelihood ?? -1);
      if (value > max) max = value;
    }
  }
  return max;
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
  outcomePctIndex,
  teamLikelihood,
  likelihoodScope,
}: {
  rows: TableRow[];
  hasThirdPlace: boolean;
  universe: GlobalUniverse;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
  teamMetricMode: TeamMetricMode;
  outcomePctIndex: Map<string, number>;
  teamLikelihood?: Record<string, number>;
  likelihoodScope?: TeamLikelihoodScope;
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
                      metricPct={lookupTeamMetricPct(
                        'champion',
                        row.champion.bracket_contestant_id,
                        teamMetricMode,
                        outcomePctIndex,
                        teamLikelihood,
                        likelihoodScope,
                      )}
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
                      teamMetricMode={teamMetricMode}
                      outcomePctIndex={outcomePctIndex}
                      teamLikelihood={teamLikelihood}
                      likelihoodScope={likelihoodScope}
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
                          teamMetricMode={teamMetricMode}
                          outcomePctIndex={outcomePctIndex}
                          teamLikelihood={teamLikelihood}
                          likelihoodScope={likelihoodScope}
                        />
                      </td>
                    ) : null}
                    <td>
                      <PlacementCell
                        teams={row.fourthTeams}
                        universe={universe.fourths(champId, ruIds, thirdIds)}
                        allLabel="Any remaining fourth-place finish"
                        role="fourth"
                        teamMetricMode={teamMetricMode}
                        outcomePctIndex={outcomePctIndex}
                        teamLikelihood={teamLikelihood}
                        likelihoodScope={likelihoodScope}
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
                      teamMetricMode={teamMetricMode}
                      outcomePctIndex={outcomePctIndex}
                      teamLikelihood={teamLikelihood}
                      likelihoodScope={likelihoodScope}
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

    const allLeaves = collectAllLeafPaths(tree, hasThirdPlace);
    const universe = new GlobalUniverse(allLeaves);

    const entryCards = winnerOdds
      .map((odds) => {
        const entryLeaves = allLeaves.filter((leaf) =>
          leaf.winners.some(
            (winner) => winner.user_bracket_id === odds.entry.user_bracket_id,
          ),
        );
        const displayRows = buildDisplayRows(
          entryLeaves,
          hasThirdPlace,
          universe,
        );
        return {
          odds,
          rows: flattenTableRows(displayRows),
        };
      })
      .filter((card) => card.rows.length > 0);

    const teamRows = flattenTableRows(
      buildDisplayRows(allLeaves, hasThirdPlace, universe),
    );

    const teamChampionCards: { champId: number; rows: TableRow[] }[] = [];
    const byChamp = new Map<number, DisplayRow[]>();
    for (const row of teamRows) {
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
        rows: flattenTableRows(displayRows),
      });
    }

    return { universe, entryCards, teamChampionCards, allLeaves };
  }, [tree, hasThirdPlace, winnerOdds]);

  const entryCards = viewModel?.entryCards ?? [];
  const teamChampionCards = viewModel?.teamChampionCards ?? [];
  const universe = viewModel?.universe;
  const allLeaves = viewModel?.allLeaves ?? [];

  const oddsByEntry = useMemo(
    () => new Map(winnerOdds.map((row) => [row.entry.user_bracket_id, row])),
    [winnerOdds],
  );

  const sortedWinnerOdds = useMemo(
    () => sortWinnerOdds(winnerOdds, sortKey),
    [winnerOdds, sortKey],
  );

  const sortedEntryCards = useMemo(() => {
    return [...entryCards].sort((a, b) =>
      compareOutcomesSort(a.odds, b.odds, sortKey),
    );
  }, [entryCards, sortKey]);

  const sortedTeamChampionCards = useMemo(() => {
    const cards = [...teamChampionCards];
    cards.sort((a, b) => {
      const champA = a.rows[0]?.champion;
      const champB = b.rows[0]?.champion;
      if (!champA || !champB) return 0;

      if (sortKey === 'name') {
        return champA.display_name.localeCompare(champB.display_name, undefined, {
          sensitivity: 'base',
        });
      }

      const metric =
        sortKey === 'likelihood' ? 'likelihood' : 'outcome_count';
      const scoreA = maxWinnerMetricForRows(a.rows, oddsByEntry, metric);
      const scoreB = maxWinnerMetricForRows(b.rows, oddsByEntry, metric);
      if (scoreB !== scoreA) return scoreB - scoreA;

      return champA.display_name.localeCompare(champB.display_name, undefined, {
        sensitivity: 'base',
      });
    });
    return cards;
  }, [teamChampionCards, sortKey, oddsByEntry]);

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
            {sortedEntryCards.map(({ odds, rows }) => {
              const cardLeaves = allLeaves.filter((leaf) =>
                leaf.winners.some(
                  (winner) =>
                    winner.user_bracket_id === odds.entry.user_bracket_id,
                ),
              );
              const outcomePctIndex = buildTeamOutcomePctIndex(
                cardLeaves,
                hasThirdPlace,
              );

              return (
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
                  outcomePctIndex={outcomePctIndex}
                  teamLikelihood={teamLikelihood}
                  likelihoodScope={{
                    kind: 'entry',
                    entryId: odds.entry.user_bracket_id,
                  }}
                />
              </article>
              );
            })}
          </div>
        ) : (
          <div className="challenge-stats__sim-cards">
            {sortedTeamChampionCards.map(({ champId, rows }) => {
              const cardLeaves = allLeaves.filter(
                (leaf) => leaf.champion.bracket_contestant_id === champId,
              );
              const outcomePctIndex = buildTeamOutcomePctIndex(
                cardLeaves,
                hasThirdPlace,
              );

              return (
              <article key={champId} className="challenge-stats__sim-card">
                <PathsTable
                  rows={rows}
                  hasThirdPlace={hasThirdPlace}
                  universe={universe!}
                  onSelectPlayer={onSelectPlayer}
                  viewerUsername={viewerUsername}
                  teamMetricMode={teamMetricMode}
                  outcomePctIndex={outcomePctIndex}
                  teamLikelihood={teamLikelihood}
                  likelihoodScope={{ kind: 'champion', championId: champId }}
                />
              </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
