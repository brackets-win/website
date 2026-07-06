import type {
  ChallengeStatsSimilarityBranch,
  ChallengeStatsSimilarityEntry,
  ChallengeStatsSimilarityFourthBranch,
  ChallengeStatsSimilarityLeaf,
  ChallengeStatsSimilarityRunnerUpBranch,
  ChallengeStatsSimilarityTeam,
  ChallengeStatsSimilarityThirdBranch,
} from '../../utils/api';
import { ContestantAvatar } from '../bracket/ContestantAvatar';

import './BracketSimilarity.css';

type Props = {
  hasThirdPlace: boolean;
  tree: ChallengeStatsSimilarityBranch[];
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
};

function TeamFlag({
  team,
  size,
  count,
}: {
  team: ChallengeStatsSimilarityTeam;
  size: 'lg' | 'md' | 'sm' | 'xs';
  count?: number;
}) {
  return (
    <div
      className={`challenge-stats__sim-flag challenge-stats__sim-flag--${size}`}
      title={team.display_name}
    >
      <ContestantAvatar
        displayName={team.display_name}
        imageUrl={team.image_url}
        className="challenge-stats__sim-flag-img"
        placeholderClassName="challenge-stats__sim-flag-img challenge-stats__sim-flag-img--ph"
      />
      <span className="challenge-stats__sim-flag-name">{team.display_name}</span>
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
      {entries.map((entry) => {
        const isViewer =
          viewerUsername != null && entry.username === viewerUsername;
        return (
          <li key={entry.user_bracket_id}>
            {onSelectPlayer ? (
              <button
                type="button"
                className={
                  isViewer
                    ? 'challenge-stats__sim-entry challenge-stats__sim-entry--viewer challenge-stats__sim-entry--btn'
                    : 'challenge-stats__sim-entry challenge-stats__sim-entry--btn'
                }
                onClick={() =>
                  onSelectPlayer(entry.user_bracket_id, entry.display_name)
                }
              >
                {entry.display_name}
              </button>
            ) : (
              <span
                className={
                  isViewer
                    ? 'challenge-stats__sim-entry challenge-stats__sim-entry--viewer'
                    : 'challenge-stats__sim-entry'
                }
              >
                {entry.display_name}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function SimilarityLeaf({
  leaf,
  onSelectPlayer,
  viewerUsername,
}: {
  leaf: ChallengeStatsSimilarityLeaf;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <div className="challenge-stats__sim-leaf">
      <div className="challenge-stats__sim-qf-flags" aria-label="Quarter-finalists">
        {leaf.quarter_finalists.map((team) => (
          <TeamFlag key={team.bracket_contestant_id} team={team} size="xs" />
        ))}
      </div>
      <EntryList
        entries={leaf.entries}
        onSelectPlayer={onSelectPlayer}
        viewerUsername={viewerUsername}
      />
    </div>
  );
}

function SimilarityFourthGroup({
  node,
  onSelectPlayer,
  viewerUsername,
}: {
  node: ChallengeStatsSimilarityFourthBranch;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <div className="challenge-stats__sim-fourth-group">
      <TeamFlag team={node.team} size="sm" count={node.count} />
      <div className="challenge-stats__sim-nested">
        {node.children.map((leaf) => (
          <SimilarityLeaf
            key={leaf.quarter_finalists.map((t) => t.bracket_contestant_id).join('-')}
            leaf={leaf}
            onSelectPlayer={onSelectPlayer}
            viewerUsername={viewerUsername}
          />
        ))}
      </div>
    </div>
  );
}

function SimilarityThirdGroup({
  node,
  onSelectPlayer,
  viewerUsername,
}: {
  node: ChallengeStatsSimilarityThirdBranch;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <div className="challenge-stats__sim-third-group">
      <TeamFlag team={node.team} size="sm" count={node.count} />
      <div className="challenge-stats__sim-nested">
        {node.children.map((child) => (
          <SimilarityFourthGroup
            key={child.team.bracket_contestant_id}
            node={child}
            onSelectPlayer={onSelectPlayer}
            viewerUsername={viewerUsername}
          />
        ))}
      </div>
    </div>
  );
}

function SimilaritySemifinalistsGroup({
  thirdNode,
  onSelectPlayer,
  viewerUsername,
}: {
  thirdNode: ChallengeStatsSimilarityThirdBranch;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  const fourthNode = thirdNode.children[0];
  return (
    <div className="challenge-stats__sim-semifinalists-group">
      <div
        className="challenge-stats__sim-semifinalists-pair"
        aria-label="Semifinalists"
      >
        <TeamFlag team={thirdNode.team} size="sm" />
        {fourthNode ? <TeamFlag team={fourthNode.team} size="sm" /> : null}
      </div>
      <div className="challenge-stats__sim-nested">
        {thirdNode.children.flatMap((fourth) =>
          fourth.children.map((leaf) => (
            <SimilarityLeaf
              key={leaf.quarter_finalists
                .map((t) => t.bracket_contestant_id)
                .join('-')}
              leaf={leaf}
              onSelectPlayer={onSelectPlayer}
              viewerUsername={viewerUsername}
            />
          )),
        )}
      </div>
    </div>
  );
}

function SimilarityRunnerUpGroup({
  node,
  hasThirdPlace,
  onSelectPlayer,
  viewerUsername,
}: {
  node: ChallengeStatsSimilarityRunnerUpBranch;
  hasThirdPlace: boolean;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <div className="challenge-stats__sim-ru-group">
      <TeamFlag team={node.team} size="md" count={node.count} />
      <div className="challenge-stats__sim-nested">
        {hasThirdPlace
          ? node.children.map((child) => (
              <SimilarityThirdGroup
                key={child.team.bracket_contestant_id}
                node={child}
                onSelectPlayer={onSelectPlayer}
                viewerUsername={viewerUsername}
              />
            ))
          : node.children.map((child) => (
              <SimilaritySemifinalistsGroup
                key={child.team.bracket_contestant_id}
                thirdNode={child}
                onSelectPlayer={onSelectPlayer}
                viewerUsername={viewerUsername}
              />
            ))}
      </div>
    </div>
  );
}

function SimilarityChampionGroup({
  node,
  hasThirdPlace,
  onSelectPlayer,
  viewerUsername,
}: {
  node: ChallengeStatsSimilarityBranch;
  hasThirdPlace: boolean;
  onSelectPlayer?: (userBracketId: number, displayName: string) => void;
  viewerUsername?: string | null;
}) {
  return (
    <div className="challenge-stats__sim-champ-group">
      <TeamFlag team={node.team} size="lg" count={node.count} />
      <div className="challenge-stats__sim-nested">
        {node.children.map((child) => (
          <SimilarityRunnerUpGroup
            key={child.team.bracket_contestant_id}
            node={child}
            hasThirdPlace={hasThirdPlace}
            onSelectPlayer={onSelectPlayer}
            viewerUsername={viewerUsername}
          />
        ))}
      </div>
    </div>
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
      <div className="challenge-stats__sim-header" aria-hidden>
        <span>Champion</span>
        <span>Runner-Up</span>
        {hasThirdPlace ? (
          <>
            <span>Third Place</span>
            <span>Fourth Place</span>
          </>
        ) : (
          <span>Semifinalists</span>
        )}
        <span>Quarter-Finalists</span>
        <span>Entries</span>
      </div>
      <div className="challenge-stats__sim-tree">
        {tree.map((node) => (
          <SimilarityChampionGroup
            key={node.team.bracket_contestant_id}
            node={node}
            hasThirdPlace={hasThirdPlace}
            onSelectPlayer={onSelectPlayer}
            viewerUsername={viewerUsername}
          />
        ))}
      </div>
    </div>
  );
}
