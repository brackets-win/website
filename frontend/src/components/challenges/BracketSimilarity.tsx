import type {
  ChallengeStatsSimilarityBranch,
  ChallengeStatsSimilarityEntry,
  ChallengeStatsSimilarityLeaf,
  ChallengeStatsSimilarityTeam,
} from '../../utils/api';
import { ContestantAvatar } from '../bracket/ContestantAvatar';

import './BracketSimilarity.css';

type Props = {
  hasThirdPlace: boolean;
  tree: ChallengeStatsSimilarityBranch[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
};

type FlattenedRow = {
  runnerUp: ChallengeStatsSimilarityTeam;
  runnerUpCount: number;
  third?: ChallengeStatsSimilarityTeam;
  thirdCount?: number;
  fourth?: ChallengeStatsSimilarityTeam;
  fourthCount?: number;
  semifinalists?: [ChallengeStatsSimilarityTeam, ChallengeStatsSimilarityTeam];
  quarterFinalists: ChallengeStatsSimilarityTeam[];
  leaf: ChallengeStatsSimilarityLeaf;
};

function flattenChampionRows(
  champ: ChallengeStatsSimilarityBranch,
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
              runnerUpCount: ru.count,
              third: third.team,
              thirdCount: third.count,
              fourth: fourth.team,
              fourthCount: fourth.count,
              quarterFinalists: leaf.quarter_finalists,
              leaf,
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
            runnerUpCount: ru.count,
            semifinalists: [third.team, fourth.team],
            quarterFinalists: leaf.quarter_finalists,
            leaf,
          });
        }
      }
    }
  }
  return rows;
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

/** Divider strength within a champion card (runner-up and below only). */
function rowDividerLevel(
  rows: FlattenedRow[],
  rowIndex: number,
  hasThirdPlace: boolean,
): number {
  if (rowIndex === 0) return 0;
  const prev = rows[rowIndex - 1];
  const curr = rows[rowIndex];
  if (ruKey(prev) !== ruKey(curr)) return 4;
  if (hasThirdPlace) {
    if (thirdKey(prev) !== thirdKey(curr)) return 3;
    if (fourthKey(prev) !== fourthKey(curr)) return 2;
  } else if (semiKey(prev) !== semiKey(curr)) {
    return 3;
  }
  return 1;
}

function teamHasImage(team: ChallengeStatsSimilarityTeam): boolean {
  return Boolean(team.image_url?.trim());
}

function TeamFlag({
  team,
  size,
  count,
}: {
  team: ChallengeStatsSimilarityTeam;
  size: 'lg' | 'md' | 'sm' | 'xs';
  count?: number;
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
      {count != null && count > 1 ? (
        <span className="challenge-stats__sim-flag-count">{count}</span>
      ) : null}
    </div>
  );
}

function EntryList({
  entries,
  onSelectPlayer,
  viewerUsername,
}: {
  entries: ChallengeStatsSimilarityEntry[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <ul className="challenge-stats__sim-entries">
      {entries.map((entry, index) => {
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

function ChampionTable({
  rows,
  hasThirdPlace,
  onSelectPlayer,
  viewerUsername,
}: {
  rows: FlattenedRow[];
  hasThirdPlace: boolean;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <div className="challenge-stats__sim-scroll">
      <table className="challenge-stats__sim-table">
        <colgroup>
          <col className="challenge-stats__sim-col challenge-stats__sim-col--ru" />
          {hasThirdPlace ? (
            <>
              <col className="challenge-stats__sim-col challenge-stats__sim-col--third" />
              <col className="challenge-stats__sim-col challenge-stats__sim-col--fourth" />
            </>
          ) : (
            <col className="challenge-stats__sim-col challenge-stats__sim-col--semi" />
          )}
          <col className="challenge-stats__sim-col challenge-stats__sim-col--qf" />
          <col className="challenge-stats__sim-col challenge-stats__sim-col--entries" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Runner-Up</th>
            {hasThirdPlace ? (
              <>
                <th scope="col">Third Place</th>
                <th scope="col">Fourth Place</th>
              </>
            ) : (
              <th scope="col">Semi Final</th>
            )}
            <th scope="col">Quarter Final</th>
            <th scope="col" className="challenge-stats__sim-th--entries">
              <span className="visually-hidden">Entries</span>
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
            const dividerLevel = rowDividerLevel(rows, rowIndex, hasThirdPlace);

            return (
              <tr
                key={`${hasThirdPlace ? fourthKey(row) : semiKey(row)}-qf:${row.quarterFinalists.map((t) => t.bracket_contestant_id).join('-')}`}
                className={
                  dividerLevel > 0
                    ? `challenge-stats__sim-row challenge-stats__sim-row--div-${dividerLevel}`
                    : 'challenge-stats__sim-row'
                }
              >
                {ru.show ? (
                  <td rowSpan={ru.span}>
                    <TeamFlag
                      team={row.runnerUp}
                      size="md"
                      count={row.runnerUpCount}
                    />
                  </td>
                ) : null}
                {hasThirdPlace ? (
                  <>
                    {third?.show ? (
                      <td rowSpan={third.span}>
                        <TeamFlag
                          team={row.third!}
                          size="sm"
                          count={row.thirdCount}
                        />
                      </td>
                    ) : null}
                    {fourth?.show ? (
                      <td rowSpan={fourth.span}>
                        <TeamFlag
                          team={row.fourth!}
                          size="sm"
                          count={row.fourthCount}
                        />
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
                <td>
                  <div
                    className="challenge-stats__sim-qf-flags"
                    aria-label="Quarter Final"
                  >
                    {row.quarterFinalists.map((team) => (
                      <TeamFlag
                        key={team.bracket_contestant_id}
                        team={team}
                        size="xs"
                      />
                    ))}
                  </div>
                </td>
                <td className="challenge-stats__sim-td--entries">
                  <EntryList
                    entries={row.leaf.entries}
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

function ChampionCard({
  champ,
  hasThirdPlace,
  onSelectPlayer,
  viewerUsername,
}: {
  champ: ChallengeStatsSimilarityBranch;
  hasThirdPlace: boolean;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  const rows = flattenChampionRows(champ, hasThirdPlace);
  if (rows.length === 0) return null;

  return (
    <section className="challenge-stats__sim-card">
      <div className="challenge-stats__sim-card-champ">
        <p className="challenge-stats__sim-card-champ-label">Champion</p>
        <TeamFlag team={champ.team} size="lg" count={champ.count} />
      </div>
      <ChampionTable
        rows={rows}
        hasThirdPlace={hasThirdPlace}
        onSelectPlayer={onSelectPlayer}
        viewerUsername={viewerUsername}
      />
    </section>
  );
}

export function BracketSimilarity({
  hasThirdPlace,
  tree,
  onSelectPlayer,
  viewerUsername,
}: Props) {
  if (tree.length === 0) {
    return (
      <p className="challenge-view__muted">
        No complete top-eight predictions to compare yet.
      </p>
    );
  }

  return (
    <div
      className={
        hasThirdPlace
          ? 'challenge-stats__sim'
          : 'challenge-stats__sim challenge-stats__sim--no-third'
      }
    >
      <div className="challenge-stats__sim-cards">
        {tree.map((champ) => (
          <ChampionCard
            key={champ.team.bracket_contestant_id}
            champ={champ}
            hasThirdPlace={hasThirdPlace}
            onSelectPlayer={onSelectPlayer}
            viewerUsername={viewerUsername}
          />
        ))}
      </div>
    </div>
  );
}
