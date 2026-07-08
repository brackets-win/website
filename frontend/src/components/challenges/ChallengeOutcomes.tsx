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

type Props = {
  hasThirdPlace: boolean;
  winnerOdds: ChallengeOutcomesWinnerOdds[];
  tree: ChallengeOutcomesChampionBranch[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
};

type RawRow = {
  runnerUp: ChallengeStatsSimilarityTeam;
  third?: ChallengeStatsSimilarityTeam;
  fourth?: ChallengeStatsSimilarityTeam;
  semifinalists?: [ChallengeStatsSimilarityTeam, ChallengeStatsSimilarityTeam];
  winners: ChallengeOutcomesEntry[];
};

type CollapsedRow = {
  runnerUpTeams: ChallengeStatsSimilarityTeam[];
  thirdTeams: ChallengeStatsSimilarityTeam[];
  fourthTeams: ChallengeStatsSimilarityTeam[];
  semiTeams: ChallengeStatsSimilarityTeam[];
  winners: ChallengeOutcomesEntry[];
};

function teamSortKey(team: ChallengeStatsSimilarityTeam): string {
  return team.display_name.toLocaleLowerCase();
}

function sortTeams(teams: Iterable<ChallengeStatsSimilarityTeam>): ChallengeStatsSimilarityTeam[] {
  return [...teams].sort((a, b) =>
    teamSortKey(a).localeCompare(teamSortKey(b), undefined, { sensitivity: 'base' }),
  );
}

function winnerEntryKey(winners: ChallengeOutcomesEntry[]): string {
  return winners.map((entry) => entry.user_bracket_id).sort((a, b) => a - b).join(',');
}

function collectRawRows(
  champ: ChallengeOutcomesChampionBranch,
  hasThirdPlace: boolean,
): RawRow[] {
  const rows: RawRow[] = [];
  for (const ru of champ.children) {
    if (hasThirdPlace) {
      for (const third of ru.children) {
        for (const fourth of third.children) {
          for (const leaf of fourth.children) {
            rows.push({
              runnerUp: ru.team,
              third: third.team,
              fourth: fourth.team,
              winners: leaf.winners,
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
            runnerUp: ru.team,
            semifinalists: [third.team, fourth.team],
            winners: leaf.winners,
          });
        }
      }
    }
  }
  return rows;
}

function collapseRows(rawRows: RawRow[]): CollapsedRow[] {
  // Within a champion card: one row per exact challenge-winner list.
  // Runner-up, third, fourth (or semi) are flag clusters of every master
  // team that can still produce that same challenge winner set.
  const groups = new Map<string, RawRow[]>();
  for (const row of rawRows) {
    const key = winnerEntryKey(row.winners);
    const bucket = groups.get(key) ?? [];
    bucket.push(row);
    groups.set(key, bucket);
  }

  const collapsed: CollapsedRow[] = [];
  for (const group of groups.values()) {
    const ruMap = new Map<number, ChallengeStatsSimilarityTeam>();
    const thirdMap = new Map<number, ChallengeStatsSimilarityTeam>();
    const fourthMap = new Map<number, ChallengeStatsSimilarityTeam>();
    const semiMap = new Map<number, ChallengeStatsSimilarityTeam>();

    for (const row of group) {
      ruMap.set(row.runnerUp.bracket_contestant_id, row.runnerUp);
      if (row.third) thirdMap.set(row.third.bracket_contestant_id, row.third);
      if (row.fourth) fourthMap.set(row.fourth.bracket_contestant_id, row.fourth);
      for (const team of row.semifinalists ?? []) {
        semiMap.set(team.bracket_contestant_id, team);
      }
    }

    collapsed.push({
      runnerUpTeams: sortTeams(ruMap.values()),
      thirdTeams: sortTeams(thirdMap.values()),
      fourthTeams: sortTeams(fourthMap.values()),
      semiTeams: sortTeams(semiMap.values()),
      winners: group[0].winners,
    });
  }

  return collapsed.sort((a, b) => {
    const aLabel = a.winners.map((entry) => entry.display_name).join(', ');
    const bLabel = b.winners.map((entry) => entry.display_name).join(', ');
    return aLabel.localeCompare(bLabel, undefined, { sensitivity: 'base' });
  });
}

function teamHasImage(team: ChallengeStatsSimilarityTeam): boolean {
  return Boolean(team.image_url?.trim());
}

function TeamFlag({
  team,
  size,
}: {
  team: ChallengeStatsSimilarityTeam;
  size: 'lg' | 'md' | 'sm' | 'xs';
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
    </div>
  );
}

function TeamCluster({
  teams,
  singleSize = 'sm',
}: {
  teams: ChallengeStatsSimilarityTeam[];
  singleSize?: 'lg' | 'md' | 'sm' | 'xs';
}) {
  const sorted = sortTeams(teams);
  if (sorted.length === 0) return null;
  if (sorted.length === 1) {
    return <TeamFlag team={sorted[0]} size={singleSize} />;
  }
  return (
    <div
      className="challenge-outcomes__team-cluster"
      title={sorted.map((team) => team.display_name).join(', ')}
    >
      {sorted.map((team) => (
        <TeamFlag key={team.bracket_contestant_id} team={team} size="xs" />
      ))}
    </div>
  );
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
    <ul className="challenge-stats__sim-entries">
      {winners.map((entry, index) => {
        const isViewer =
          viewerUsername != null && entry.username === viewerUsername;
        const nameClass = isViewer
          ? 'challenge-stats__group-points-name challenge-stats__entry-name--viewer'
          : 'challenge-stats__group-points-name';
        return (
          <li key={entry.user_bracket_id}>
            {index > 0 ? (
              <span className="challenge-stats__sim-entry-sep" aria-hidden>
                ,{' '}
              </span>
            ) : null}
            {onSelectPlayer ? (
              <button
                type="button"
                className={`${nameClass} challenge-stats__group-points-name--btn`}
                onClick={() =>
                  onSelectPlayer(entry.user_bracket_id, entry.display_name)
                }
              >
                {entry.display_name}
              </button>
            ) : (
              <span className={nameClass}>{entry.display_name}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function WinnerOddsTable({ winnerOdds }: { winnerOdds: ChallengeOutcomesWinnerOdds[] }) {
  if (winnerOdds.length === 0) return null;

  return (
    <article className="challenge-stats__sim-card challenge-outcomes__summary-card">
      <div className="challenge-stats__sim-scroll">
        <table className="challenge-stats__sim-table challenge-outcomes__summary-table">
          <colgroup>
            <col />
            <col className="challenge-outcomes__summary-col--pct" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col">Winner</th>
              <th scope="col" className="challenge-outcomes__summary-th--pct">
                % of Outcomes
              </th>
            </tr>
          </thead>
          <tbody>
            {winnerOdds.map((row) => (
              <tr key={row.name}>
                <td className="challenge-outcomes__summary-winner">{row.name}</td>
                <td className="challenge-outcomes__summary-pct">
                  {row.pct.toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function ChampionTable({
  champ,
  rows,
  hasThirdPlace,
  onSelectPlayer,
  viewerUsername,
}: {
  champ: ChallengeOutcomesChampionBranch;
  rows: CollapsedRow[];
  hasThirdPlace: boolean;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
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
          <col className="challenge-stats__sim-col challenge-stats__sim-col--champ" />
          <col className="challenge-stats__sim-col challenge-stats__sim-col--ru" />
          {hasThirdPlace ? (
            <>
              <col className="challenge-stats__sim-col challenge-stats__sim-col--third" />
              <col className="challenge-stats__sim-col challenge-stats__sim-col--fourth" />
            </>
          ) : (
            <col className="challenge-stats__sim-col challenge-stats__sim-col--semi" />
          )}
          <col className="challenge-stats__sim-col challenge-stats__sim-col--entries" />
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
            <th scope="col" className="challenge-stats__sim-th--entries">
              Winner
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
              <tr
                key={`w:${winnerEntryKey(row.winners)}`}
                className={
                  rowIndex > 0
                    ? 'challenge-stats__sim-row challenge-stats__sim-row--div-3'
                    : 'challenge-stats__sim-row'
                }
              >
                {rowIndex === 0 ? (
                  <td
                    rowSpan={rows.length}
                    className="challenge-stats__sim-td--champ"
                  >
                    <TeamFlag team={champ.team} size="lg" />
                  </td>
                ) : null}
                <td>
                  <TeamCluster teams={row.runnerUpTeams} singleSize="md" />
                </td>
                {hasThirdPlace ? (
                  <>
                    <td>
                      <TeamCluster teams={row.thirdTeams} />
                    </td>
                    <td>
                      <TeamCluster teams={row.fourthTeams} />
                    </td>
                  </>
                ) : (
                  <td>
                    <TeamCluster teams={row.semiTeams} singleSize="sm" />
                  </td>
                )}
                <td className="challenge-stats__sim-td--entries">
                  <WinnerList
                    winners={row.winners}
                    onSelectPlayer={onSelectPlayer}
                    viewerUsername={viewerUsername}
                  />
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChallengeOutcomes({
  hasThirdPlace,
  winnerOdds,
  tree,
  onSelectPlayer,
  viewerUsername,
}: Props) {
  if (tree.length === 0) {
    return (
      <p className="challenge-stats__group-points-empty">
        No remaining outcomes to show yet.
      </p>
    );
  }

  return (
    <div className="challenge-outcomes__layout">
      <aside className="challenge-outcomes__summary">
        <WinnerOddsTable winnerOdds={winnerOdds} />
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
        <div className="challenge-stats__sim-cards">
          {tree.map((champ) => {
            const rows = collapseRows(collectRawRows(champ, hasThirdPlace));
            if (rows.length === 0) return null;
            return (
              <article
                key={champ.team.bracket_contestant_id}
                className="challenge-stats__sim-card"
              >
                <ChampionTable
                  champ={champ}
                  rows={rows}
                  hasThirdPlace={hasThirdPlace}
                  onSelectPlayer={onSelectPlayer}
                  viewerUsername={viewerUsername}
                />
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}
