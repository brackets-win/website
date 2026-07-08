import type {
  ChallengeOutcomesChampionBranch,
  ChallengeOutcomesWinnerOdds,
  ChallengeStatsSimilarityTeam,
} from '../../utils/api';
import { ContestantAvatar } from '../bracket/ContestantAvatar';

import './BracketSimilarity.css';
import './ChallengeOutcomes.css';

type Props = {
  hasThirdPlace: boolean;
  winnerOdds: ChallengeOutcomesWinnerOdds[];
  tree: ChallengeOutcomesChampionBranch[];
};

type FlattenedRow = {
  runnerUp: ChallengeStatsSimilarityTeam;
  third?: ChallengeStatsSimilarityTeam;
  fourth?: ChallengeStatsSimilarityTeam;
  semifinalists?: [ChallengeStatsSimilarityTeam, ChallengeStatsSimilarityTeam];
  winners: string[];
};

function flattenChampionRows(
  champ: ChallengeOutcomesChampionBranch,
  hasThirdPlace: boolean,
): FlattenedRow[] {
  const rows: FlattenedRow[] = [];
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
  return sortRowsForWinnerGrouping(rows);
}

function sortRowsForWinnerGrouping(rows: FlattenedRow[]): FlattenedRow[] {
  return [...rows].sort((a, b) => {
    const winnerCmp = winnerKey(a).localeCompare(winnerKey(b));
    if (winnerCmp !== 0) return winnerCmp;
    const ruCmp = a.runnerUp.display_name.localeCompare(
      b.runnerUp.display_name,
      undefined,
      { sensitivity: 'base' },
    );
    if (ruCmp !== 0) return ruCmp;
    if (a.third && b.third) {
      const thirdCmp = a.third.display_name.localeCompare(
        b.third.display_name,
        undefined,
        { sensitivity: 'base' },
      );
      if (thirdCmp !== 0) return thirdCmp;
    }
    if (a.fourth && b.fourth) {
      return a.fourth.display_name.localeCompare(b.fourth.display_name, undefined, {
        sensitivity: 'base',
      });
    }
    return semiKey(a).localeCompare(semiKey(b));
  });
}

function cellSpan(
  rows: FlattenedRow[],
  rowIndex: number,
  keyFn: (row: FlattenedRow) => string,
): { show: boolean; span: number } {
  const key = keyFn(rows[rowIndex]);
  if (rowIndex > 0 && keyFn(rows[rowIndex - 1]) === key) {
    return { show: false, span: 0 };
  }
  let span = 1;
  for (let i = rowIndex + 1; i < rows.length; i++) {
    if (keyFn(rows[i]) !== key) break;
    span++;
  }
  return { show: true, span };
}

function winnerKey(row: FlattenedRow): string {
  return row.winners.join('\0');
}

function ruKey(row: FlattenedRow): string {
  return `r:${row.runnerUp.bracket_contestant_id}`;
}

function thirdKey(row: FlattenedRow): string {
  return `${ruKey(row)}-t:${row.third!.bracket_contestant_id}`;
}

function fourthKey(row: FlattenedRow): string {
  return `${thirdKey(row)}-f:${row.fourth!.bracket_contestant_id}`;
}

function semiKey(row: FlattenedRow): string {
  const [a, b] = row.semifinalists ?? [];
  return `${ruKey(row)}-s:${a?.bracket_contestant_id ?? 0}-${b?.bracket_contestant_id ?? 0}`;
}

function rowDividerLevel(
  rows: FlattenedRow[],
  rowIndex: number,
  hasThirdPlace: boolean,
): number {
  if (rowIndex === 0) return 0;
  const prev = rows[rowIndex - 1];
  const curr = rows[rowIndex];
  if (winnerKey(prev) !== winnerKey(curr)) return 5;
  if (ruKey(prev) !== ruKey(curr)) return 4;
  if (hasThirdPlace) {
    if (thirdKey(prev) !== thirdKey(curr)) return 3;
    if (fourthKey(prev) !== fourthKey(curr)) return 2;
  } else if (semiKey(prev) !== semiKey(curr)) {
    return 3;
  }
  return 1;
}

function TeamFlag({
  team,
  size,
}: {
  team: ChallengeStatsSimilarityTeam;
  size: 'lg' | 'md' | 'sm';
}) {
  return (
    <span className={`challenge-stats__sim-flag challenge-stats__sim-flag--${size}`}>
      <ContestantAvatar
        displayName={team.display_name}
        imageUrl={team.image_url}
        className="challenge-stats__sim-flag-img"
        placeholderClassName="challenge-stats__sim-flag-img challenge-stats__sim-flag-img--ph"
      />
      <span className="challenge-stats__sim-flag-name">{team.display_name}</span>
    </span>
  );
}

function WinnerList({ winners }: { winners: string[] }) {
  return (
    <ul className="challenge-stats__sim-entries">
      {winners.map((name, index) => (
        <li key={`${name}-${index}`}>
          {index > 0 ? (
            <span className="challenge-stats__sim-entry-sep" aria-hidden>
              ·
            </span>
          ) : null}
          <span className="challenge-stats__group-points-name">{name}</span>
        </li>
      ))}
    </ul>
  );
}

function WinnerOddsTable({ winnerOdds }: { winnerOdds: ChallengeOutcomesWinnerOdds[] }) {
  if (winnerOdds.length === 0) return null;

  return (
    <div className="challenge-outcomes__summary-scroll">
      <table className="challenge-outcomes__summary-table">
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
  );
}

function ChampionTable({
  champ,
  rows,
  hasThirdPlace,
}: {
  champ: ChallengeOutcomesChampionBranch;
  rows: FlattenedRow[];
  hasThirdPlace: boolean;
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
          {rows.map((row, rowIndex) => {
            const ru = cellSpan(rows, rowIndex, ruKey);
            const third = hasThirdPlace
              ? cellSpan(rows, rowIndex, thirdKey)
              : null;
            const fourth = hasThirdPlace
              ? cellSpan(rows, rowIndex, fourthKey)
              : null;
            const semi = !hasThirdPlace
              ? cellSpan(rows, rowIndex, semiKey)
              : null;
            const winner = cellSpan(rows, rowIndex, winnerKey);
            const dividerLevel = rowDividerLevel(rows, rowIndex, hasThirdPlace);

            return (
              <tr
                key={`${hasThirdPlace ? fourthKey(row) : semiKey(row)}-w:${winnerKey(row)}`}
                className={
                  dividerLevel > 0
                    ? `challenge-stats__sim-row challenge-stats__sim-row--div-${Math.min(dividerLevel, 4)}`
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
                {ru.show ? (
                  <td rowSpan={ru.span}>
                    <TeamFlag team={row.runnerUp} size="md" />
                  </td>
                ) : null}
                {hasThirdPlace ? (
                  <>
                    {third?.show ? (
                      <td rowSpan={third.span}>
                        <TeamFlag team={row.third!} size="sm" />
                      </td>
                    ) : null}
                    {fourth?.show ? (
                      <td rowSpan={fourth.span}>
                        <TeamFlag team={row.fourth!} size="sm" />
                      </td>
                    ) : null}
                  </>
                ) : semi?.show ? (
                  <td rowSpan={semi.span}>
                    <div className="challenge-stats__sim-semifinalists-pair">
                      {row.semifinalists?.map((team) => (
                        <TeamFlag
                          key={team.bracket_contestant_id}
                          team={team}
                          size="sm"
                        />
                      ))}
                    </div>
                  </td>
                ) : null}
                {winner.show ? (
                  <td rowSpan={winner.span} className="challenge-stats__sim-td--entries">
                    <WinnerList winners={row.winners} />
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ChallengeOutcomes({ hasThirdPlace, winnerOdds, tree }: Props) {
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
            const rows = flattenChampionRows(champ, hasThirdPlace);
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
                />
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}
