import assert from 'node:assert/strict';
import test from 'node:test';

import type {
  ChallengeOutcomesChampionBranch,
  ChallengeOutcomesEntry,
  ChallengeStatsSimilarityTeam,
} from './api';
import {
  buildOutcomeDisplayRows,
  collectOutcomeLeafPaths,
  isExhaustiveCluster,
  leavesMatchingDisplayRow,
  OutcomeGlobalUniverse,
  sumDisplayRowBranchMetric,
  sumDisplayRowPlacementMetric,
  sumDisplayRowsPlacementMetric,
  sumDisplayRowSpanBranchMetric,
  teamSetKey,
  type OutcomeLeafPath,
} from './challengeOutcomesDisplay';
import {
  buildPathOutcomeCounts,
  sortOutcomeDisplayRows,
} from './challengeOutcomesSort';

function team(
  id: number,
  name: string,
  imageUrl: string | null = `/${name}.png`,
): ChallengeStatsSimilarityTeam {
  return {
    bracket_contestant_id: id,
    display_name: name,
    image_url: imageUrl,
  };
}

function winner(id: number, name: string): ChallengeOutcomesEntry {
  return { user_bracket_id: id, display_name: name };
}

function fourthLeaf(winners: ChallengeOutcomesEntry[]) {
  return { winners };
}

function thirdBranch(
  third: ChallengeStatsSimilarityTeam,
  fourth: ChallengeStatsSimilarityTeam,
  winners: ChallengeOutcomesEntry[],
) {
  return { team: third, children: [{ team: fourth, children: [fourthLeaf(winners)] }] };
}

function ruBranch(
  runnerUp: ChallengeStatsSimilarityTeam,
  thirds: ReturnType<typeof thirdBranch>[],
) {
  return { team: runnerUp, children: thirds };
}

function buildTree(
  champion: ChallengeStatsSimilarityTeam,
  runnerUps: ReturnType<typeof ruBranch>[],
): ChallengeOutcomesChampionBranch[] {
  return [{ team: champion, children: runnerUps }];
}

test('exhaustive cluster requires more than one team in universe', () => {
  const only = [team(1, 'Spain')];
  assert.equal(isExhaustiveCluster(only, only), false);
  assert.equal(
    isExhaustiveCluster([team(1, 'Spain'), team(2, 'France')], only),
    false,
  );
});

test('collapsed row drops ALL runner-up when a sibling splits one out', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const france = team(3, 'France');
  const germany = team(4, 'Germany');
  const england = team(5, 'England');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(spain, [
    ruBranch(argentina, [thirdBranch(england, france, [harry])]),
    ruBranch(france, [thirdBranch(germany, england, [nate])]),
    ruBranch(germany, [thirdBranch(england, france, [nate])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const universe = new OutcomeGlobalUniverse(leaves);
  const rows = buildOutcomeDisplayRows(leaves, true, universe);

  assert.equal(rows.length, 2);

  const nateRow = rows.find((row) => row.winners[0].display_name === 'Nate')!;
  const harryRow = rows.find((row) => row.winners[0].display_name === 'Harry')!;
  assert.ok(nateRow);
  assert.ok(harryRow);

  const ruUniverse = universe.runnerUps(spain.bracket_contestant_id);
  assert.equal(
    isExhaustiveCluster(nateRow.runnerUpTeams, ruUniverse),
    false,
    'collapsed row must not show ALL runner-up when Argentina is split below',
  );
  assert.ok(
    !nateRow.runnerUpTeams.some(
      (rowTeam) => rowTeam.bracket_contestant_id === argentina.bracket_contestant_id,
    ),
  );
  assert.equal(nateRow.runnerUpTeams.length, 2);

  assert.deepEqual(
    harryRow.runnerUpTeams.map((rowTeam) => rowTeam.bracket_contestant_id),
    [argentina.bracket_contestant_id],
  );

  const nateRuIds = new Set(
    nateRow.runnerUpTeams.map((rowTeam) => rowTeam.bracket_contestant_id),
  );
  const nateThirdUniverse = universe.thirds(spain.bracket_contestant_id, nateRuIds);
  assert.equal(
    isExhaustiveCluster(nateRow.thirdTeams, nateThirdUniverse),
    true,
    'third can still collapse to ALL within the reconciled runner-up prefix',
  );
  assert.equal(
    isExhaustiveCluster(nateRow.fourthTeams, universe.fourths(
      spain.bracket_contestant_id,
      nateRuIds,
      new Set(nateRow.thirdTeams.map((rowTeam) => rowTeam.bracket_contestant_id)),
    )),
    true,
    'fourth can still collapse to ALL within the reconciled prefix',
  );
});

test('rows with no sibling splits still show ALL when exhaustive', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const france = team(3, 'France');
  const england = team(4, 'England');
  const germany = team(5, 'Germany');

  const nate = winner(10, 'Nate');

  const tree = buildTree(spain, [
    ruBranch(argentina, [thirdBranch(england, france, [nate])]),
    ruBranch(france, [thirdBranch(germany, england, [nate])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const universe = new OutcomeGlobalUniverse(leaves);
  const rows = buildOutcomeDisplayRows(leaves, true, universe);

  assert.equal(rows.length, 1);
  const ruUniverse = universe.runnerUps(spain.bracket_contestant_id);
  assert.equal(isExhaustiveCluster(rows[0].runnerUpTeams, ruUniverse), true);
});

test('third ALL collapses only within the same runner-up sibling group', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const france = team(3, 'France');
  const england = team(4, 'England');
  const germany = team(5, 'Germany');
  const portugal = team(6, 'Portugal');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(spain, [
    ruBranch(argentina, [
      thirdBranch(england, france, [harry]),
      thirdBranch(germany, portugal, [nate]),
    ]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const universe = new OutcomeGlobalUniverse(leaves);
  const rows = buildOutcomeDisplayRows(leaves, true, universe);

  assert.equal(rows.length, 2);
  const nateRow = rows.find((row) => row.winners[0].display_name === 'Nate')!;
  const harryRow = rows.find((row) => row.winners[0].display_name === 'Harry')!;
  assert.ok(nateRow);
  assert.ok(harryRow);

  const ruIds = new Set([argentina.bracket_contestant_id]);
  const thirdUniverse = universe.thirds(spain.bracket_contestant_id, ruIds);
  assert.equal(
    isExhaustiveCluster(nateRow.thirdTeams, thirdUniverse),
    false,
    'Nate row must not show ALL third when Harry splits England out below',
  );
  assert.equal(nateRow.thirdTeams.length, 1);
  assert.equal(nateRow.thirdTeams[0].bracket_contestant_id, germany.bracket_contestant_id);
  assert.equal(harryRow.thirdTeams[0].bracket_contestant_id, england.bracket_contestant_id);
});

test('entry cards reuse globally reconciled rows instead of re-collapsing per entry', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const france = team(3, 'France');
  const germany = team(4, 'Germany');
  const england = team(5, 'England');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(spain, [
    ruBranch(argentina, [thirdBranch(england, france, [harry])]),
    ruBranch(france, [thirdBranch(germany, england, [nate])]),
    ruBranch(germany, [thirdBranch(england, france, [nate])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const universe = new OutcomeGlobalUniverse(leaves);
  const globalRows = buildOutcomeDisplayRows(leaves, true, universe);

  const nateRows = globalRows.filter((row) =>
    row.winners.some((entry) => entry.user_bracket_id === nate.user_bracket_id),
  );
  const harryRows = globalRows.filter((row) =>
    row.winners.some((entry) => entry.user_bracket_id === harry.user_bracket_id),
  );

  assert.equal(nateRows.length, 1);
  assert.equal(harryRows.length, 1);

  const ruUniverse = universe.runnerUps(spain.bracket_contestant_id);
  assert.equal(
    isExhaustiveCluster(nateRows[0].runnerUpTeams, ruUniverse),
    false,
    'Nate entry card must not inherit a per-entry ALL runner-up row',
  );
  assert.equal(nateRows[0].runnerUpTeams.length, 2);
  assert.deepEqual(
    harryRows[0].runnerUpTeams.map((rowTeam) => rowTeam.bracket_contestant_id),
    [argentina.bracket_contestant_id],
  );
});

test('entry champion branch metric counts only matching leaves, not champion prefix', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const france = team(3, 'France');
  const germany = team(4, 'Germany');
  const england = team(5, 'England');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(spain, [
    ruBranch(argentina, [thirdBranch(england, france, [harry])]),
    ruBranch(france, [thirdBranch(germany, england, [nate])]),
    ruBranch(germany, [thirdBranch(england, france, [nate])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const globalRows = buildOutcomeDisplayRows(
    leaves,
    true,
    new OutcomeGlobalUniverse(leaves),
  );
  const nateRow = globalRows.find((row) =>
    row.winners.some((entry) => entry.user_bracket_id === nate.user_bracket_id),
  )!;

  assert.equal(sumDisplayRowBranchMetric(nateRow, leaves, true, 'outcomes'), 2);
  assert.equal(
    leavesMatchingDisplayRow(nateRow, leaves, true).length,
    2,
  );
});

test('entry placement metrics stay within the row branch', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const france = team(3, 'France');
  const germany = team(4, 'Germany');
  const england = team(5, 'England');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(spain, [
    ruBranch(argentina, [thirdBranch(england, france, [harry])]),
    ruBranch(france, [thirdBranch(germany, england, [nate])]),
    ruBranch(germany, [thirdBranch(england, france, [nate])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const globalRows = buildOutcomeDisplayRows(
    leaves,
    true,
    new OutcomeGlobalUniverse(leaves),
  );
  const nateRow = globalRows.find((row) =>
    row.winners.some((entry) => entry.user_bracket_id === nate.user_bracket_id),
  )!;
  const harryRow = globalRows.find((row) =>
    row.winners.some((entry) => entry.user_bracket_id === harry.user_bracket_id),
  )!;

  const nateBranch = sumDisplayRowBranchMetric(nateRow, leaves, true, 'outcomes')!;
  const harryBranch = sumDisplayRowBranchMetric(harryRow, leaves, true, 'outcomes')!;

  const nateFranceRu = sumDisplayRowPlacementMetric(
    nateRow,
    leaves,
    true,
    'runner_up',
    [france.bracket_contestant_id],
    'outcomes',
  )!;
  const nateGermanyRu = sumDisplayRowPlacementMetric(
    nateRow,
    leaves,
    true,
    'runner_up',
    [germany.bracket_contestant_id],
    'outcomes',
  )!;
  const harryArgentinaRu = sumDisplayRowPlacementMetric(
    harryRow,
    leaves,
    true,
    'runner_up',
    [argentina.bracket_contestant_id],
    'outcomes',
  )!;

  assert.equal(nateFranceRu + nateGermanyRu, nateBranch);
  assert.ok(nateFranceRu <= nateBranch);
  assert.ok(nateGermanyRu <= nateBranch);
  assert.equal(harryArgentinaRu, harryBranch);
});

test('champion span metric sums sibling display rows under the same champion', () => {
  const england = team(5, 'England');
  const spain = team(1, 'Spain');
  const france = team(3, 'France');
  const germany = team(4, 'Germany');
  const portugal = team(6, 'Portugal');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(england, [
    ruBranch(spain, [
      thirdBranch(germany, portugal, [nate]),
      thirdBranch(portugal, germany, [nate]),
    ]),
    ruBranch(france, [thirdBranch(germany, portugal, [nate, harry])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const globalRows = buildOutcomeDisplayRows(
    leaves,
    true,
    new OutcomeGlobalUniverse(leaves),
  );
  const nateRows = globalRows.filter((row) =>
    row.winners.some((entry) => entry.user_bracket_id === nate.user_bracket_id),
  );

  assert.equal(nateRows.length, 2);

  const spainRow = nateRows.find(
    (row) => row.runnerUpTeams[0]?.bracket_contestant_id === spain.bracket_contestant_id,
  )!;
  const franceRow = nateRows.find(
    (row) => row.runnerUpTeams[0]?.bracket_contestant_id === france.bracket_contestant_id,
  )!;
  assert.ok(spainRow);
  assert.ok(franceRow);

  const spainBranch = sumDisplayRowBranchMetric(spainRow, leaves, true, 'outcomes')!;
  const franceBranch = sumDisplayRowBranchMetric(franceRow, leaves, true, 'outcomes')!;
  const spanTotal = sumDisplayRowSpanBranchMetric(
    nateRows,
    0,
    nateRows.length,
    leaves,
    true,
    'outcomes',
  )!;

  assert.equal(spainBranch, 2);
  assert.equal(franceBranch, 1);
  assert.equal(spanTotal, spainBranch + franceBranch);

  const spainRu = sumDisplayRowPlacementMetric(
    spainRow,
    leaves,
    true,
    'runner_up',
    [spain.bracket_contestant_id],
    'outcomes',
  )!;
  const franceRu = sumDisplayRowPlacementMetric(
    franceRow,
    leaves,
    true,
    'runner_up',
    [france.bracket_contestant_id],
    'outcomes',
  )!;
  assert.equal(spainRu + franceRu, spanTotal);
});

test('runner-up span metric sums rows split below on third place', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const england = team(4, 'England');
  const france = team(3, 'France');
  const germany = team(5, 'Germany');
  const portugal = team(6, 'Portugal');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(spain, [
    ruBranch(argentina, [
      thirdBranch(england, france, [nate]),
      thirdBranch(germany, portugal, [nate, harry]),
    ]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const globalRows = buildOutcomeDisplayRows(
    leaves,
    true,
    new OutcomeGlobalUniverse(leaves),
  );
  const nateRows = globalRows.filter((row) =>
    row.winners.some((entry) => entry.user_bracket_id === nate.user_bracket_id),
  );

  assert.equal(nateRows.length, 2);
  assert.equal(
    teamSetKey(nateRows[0].runnerUpTeams),
    teamSetKey(nateRows[1].runnerUpTeams),
  );

  const argentinaId = argentina.bracket_contestant_id;
  const rowMetrics = nateRows.map(
    (row) =>
      sumDisplayRowPlacementMetric(
        row,
        leaves,
        true,
        'runner_up',
        [argentinaId],
        'outcomes',
      )!,
  );
  const spanTotal = sumDisplayRowsPlacementMetric(
    nateRows,
    leaves,
    true,
    'runner_up',
    [argentinaId],
    'outcomes',
  )!;

  assert.equal(spanTotal, rowMetrics[0] + rowMetrics[1]);
  assert.equal(
    spanTotal,
    nateRows.reduce(
      (total, row) =>
        total +
        sumDisplayRowBranchMetric(row, leaves, true, 'outcomes')!,
      0,
    ),
  );
});

test('third span metric sums rows split below on fourth place', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const england = team(4, 'England');
  const france = team(3, 'France');
  const portugal = team(6, 'Portugal');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(spain, [
    ruBranch(argentina, [
      thirdBranch(england, france, [nate]),
      thirdBranch(england, portugal, [nate, harry]),
    ]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const globalRows = buildOutcomeDisplayRows(
    leaves,
    true,
    new OutcomeGlobalUniverse(leaves),
  );
  const nateRows = globalRows.filter((row) =>
    row.winners.some((entry) => entry.user_bracket_id === nate.user_bracket_id),
  );

  assert.equal(nateRows.length, 2);
  assert.equal(
    teamSetKey(nateRows[0].thirdTeams),
    teamSetKey(nateRows[1].thirdTeams),
  );

  const englandId = england.bracket_contestant_id;
  const rowMetrics = nateRows.map(
    (row) =>
      sumDisplayRowPlacementMetric(
        row,
        leaves,
        true,
        'third',
        [englandId],
        'outcomes',
      )!,
  );
  const spanTotal = sumDisplayRowsPlacementMetric(
    nateRows,
    leaves,
    true,
    'third',
    [englandId],
    'outcomes',
  )!;

  assert.equal(spanTotal, rowMetrics[0] + rowMetrics[1]);
  assert.equal(
    spanTotal,
    nateRows.reduce(
      (total, row) =>
        total +
        sumDisplayRowPlacementMetric(
          row,
          leaves,
          true,
          'runner_up',
          [argentina.bracket_contestant_id],
          'outcomes',
        )!,
      0,
    ),
  );
});

test('row metrics only include leaves with the exact same winner set', () => {
  const england = team(5, 'England');
  const spain = team(1, 'Spain');
  const france = team(3, 'France');
  const germany = team(4, 'Germany');
  const portugal = team(6, 'Portugal');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(england, [
    ruBranch(spain, [thirdBranch(germany, portugal, [nate, harry])]),
    ruBranch(spain, [thirdBranch(portugal, germany, [nate])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const globalRows = buildOutcomeDisplayRows(
    leaves,
    true,
    new OutcomeGlobalUniverse(leaves),
  );
  const tieRow = globalRows.find(
    (row) => row.winners.length === 2,
  )!;
  const soloRow = globalRows.find(
    (row) => row.winners.length === 1,
  )!;
  const soloLeaf = leaves.find(
    (leaf) =>
      leaf.runnerUp.bracket_contestant_id === spain.bracket_contestant_id &&
      leaf.winners.length === 1,
  )!;
  const tieLeaf = leaves.find((leaf) => leaf.winners.length === 2)!;

  assert.equal(
    leavesMatchingDisplayRow(tieRow, [soloLeaf], true).length,
    0,
    'solo-win leaf must not count toward a tie row',
  );
  assert.equal(
    leavesMatchingDisplayRow(soloRow, [tieLeaf], true).length,
    0,
    'tie leaf must not count toward a solo-win row',
  );
  assert.equal(sumDisplayRowBranchMetric(tieRow, leaves, true, 'outcomes'), 1);
  assert.equal(sumDisplayRowBranchMetric(soloRow, leaves, true, 'outcomes'), 1);
});

test('buildOutcomeDisplayRows never emits rows with empty placement columns', () => {
  const spain = team(1, 'Spain');
  const argentina = team(2, 'Argentina');
  const france = team(3, 'France');
  const germany = team(4, 'Germany');
  const england = team(5, 'England');
  const portugal = team(6, 'Portugal');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');
  const keaton = winner(30, 'Keaton');

  const tree = buildTree(spain, [
    ruBranch(argentina, [thirdBranch(england, france, [harry])]),
    ruBranch(france, [thirdBranch(germany, england, [nate])]),
    ruBranch(germany, [thirdBranch(england, portugal, [keaton])]),
    ruBranch(argentina, [thirdBranch(germany, portugal, [keaton])]),
    ruBranch(france, [thirdBranch(england, portugal, [keaton])]),
    ruBranch(germany, [thirdBranch(england, france, [keaton])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const rows = buildOutcomeDisplayRows(
    leaves,
    true,
    new OutcomeGlobalUniverse(leaves),
  );

  for (const row of rows) {
    assert.ok(row.runnerUpTeams.length > 0, 'runner-up must not be empty');
    assert.ok(row.thirdTeams.length > 0, 'third must not be empty');
    assert.ok(row.fourthTeams.length > 0, 'fourth must not be empty');
  }
});

test('entry card branch metrics partition an entry winning leaves exactly once', () => {
  const england = team(5, 'England');
  const spain = team(1, 'Spain');
  const france = team(3, 'France');
  const germany = team(4, 'Germany');
  const portugal = team(6, 'Portugal');

  const nate = winner(10, 'Nate');
  const harry = winner(20, 'Harry');

  const tree = buildTree(england, [
    ruBranch(spain, [
      thirdBranch(germany, portugal, [nate]),
      thirdBranch(portugal, germany, [nate]),
    ]),
    ruBranch(france, [thirdBranch(germany, portugal, [nate, harry])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const globalRows = buildOutcomeDisplayRows(
    leaves,
    true,
    new OutcomeGlobalUniverse(leaves),
  );
  const nateRows = globalRows.filter((row) =>
    row.winners.some((entry) => entry.user_bracket_id === nate.user_bracket_id),
  );
  const nateLeaves = leaves.filter((leaf) =>
    leaf.winners.some((entry) => entry.user_bracket_id === nate.user_bracket_id),
  );

  const branchTotal = nateRows.reduce(
    (total, row) => total + sumDisplayRowBranchMetric(row, leaves, true, 'outcomes')!,
    0,
  );
  assert.equal(branchTotal, nateLeaves.length);

  const matched = new Set<OutcomeLeafPath>();
  for (const row of nateRows) {
    for (const leaf of leavesMatchingDisplayRow(row, leaves, true)) {
      assert.ok(!matched.has(leaf), 'each winning leaf must map to one row');
      matched.add(leaf);
    }
  }
  assert.equal(matched.size, nateLeaves.length);
});

test('metric sort keeps shared runner-up rows adjacent within a champion card', () => {

  const argentina = team(2, 'Argentina');
  const france = team(3, 'France');
  const spain = team(1, 'Spain');
  const england = team(5, 'England');
  const germany = team(4, 'Germany');
  const portugal = team(6, 'Portugal');

  const jake = winner(10, 'Jake');
  const katie = winner(20, 'Katie');
  const nate = winner(30, 'Nate');

  const tree = buildTree(argentina, [
    ruBranch(france, [
      thirdBranch(england, portugal, [jake]),
      thirdBranch(germany, portugal, [katie]),
    ]),
    ruBranch(spain, [thirdBranch(france, england, [nate])]),
  ]);

  const leaves = collectOutcomeLeafPaths(tree, true);
  const universe = new OutcomeGlobalUniverse(leaves);
  const rows = buildOutcomeDisplayRows(leaves, true, universe);
  assert.equal(rows.length, 3);

  const franceRows = rows.filter(
    (row) =>
      row.runnerUpTeams.length === 1 &&
      row.runnerUpTeams[0].bracket_contestant_id === france.bracket_contestant_id,
  );
  const spainRow = rows.find(
    (row) =>
      row.runnerUpTeams.length === 1 &&
      row.runnerUpTeams[0].bracket_contestant_id === spain.bracket_contestant_id,
  )!;
  assert.equal(franceRows.length, 2);
  assert.ok(spainRow);

  const shuffled = [spainRow, franceRows[1], franceRows[0]];
  const pathOutcomeCounts = buildPathOutcomeCounts(leaves, true);
  const sorted = sortOutcomeDisplayRows(
    shuffled,
    'outcomes',
    true,
    universe,
    pathOutcomeCounts,
    leaves.length,
  );

  const franceIndices = sorted
    .map((row, index) =>
      teamSetKey(row.runnerUpTeams) === teamSetKey(franceRows[0].runnerUpTeams)
        ? index
        : -1,
    )
    .filter((index) => index >= 0);
  assert.equal(franceIndices.length, 2);
  assert.equal(
    Math.abs(franceIndices[0] - franceIndices[1]),
    1,
    'France runner-up rows must not be separated by another branch',
  );
});
