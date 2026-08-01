/** Single-elim bye / field-size helpers (mirrors backend single_elim_byes). */

export function isPowerOf2(n: number): boolean {
  return n >= 2 && (n & (n - 1)) === 0;
}

export function nextPowerOf2(n: number): number {
  let p = 1;
  while (p < n) p *= 2;
  return p;
}

/** Even sizes from ``min`` through ``max`` inclusive. */
export function evenTeamSizes(min = 4, max = 64): number[] {
  const out: number[] = [];
  for (let n = min; n <= max; n += 2) out.push(n);
  return out;
}

export function singleElimFieldSize(roster: number): number {
  return nextPowerOf2(roster);
}

export function singleElimByeCount(roster: number): number {
  return singleElimFieldSize(roster) - roster;
}

export function singleElimPlayInCount(roster: number): number {
  return roster - singleElimByeCount(roster);
}

export type ByeDrawPot = {
  key: 'bye_vs_r1' | 'bye' | 'round_1';
  label: string;
  size: number;
};

function firstRoundSeedPairs(fieldSize: number): Array<[number, number]> {
  let order = [1];
  while (order.length < fieldSize) {
    const n = order.length * 2;
    order = order.flatMap((x) => [x, n + 1 - x]);
  }
  const pairs: Array<[number, number]> = [];
  for (let i = 0; i < order.length; i += 2) {
    pairs.push([order[i]!, order[i + 1]!]);
  }
  return pairs;
}

/** Pot bands for random-balanced draws on non-power-of-2 single-elim fields. */
export function singleElimByeDrawPots(roster: number): ByeDrawPot[] {
  if (!Number.isFinite(roster) || roster < 2 || roster % 2 !== 0) return [];
  if (isPowerOf2(roster)) return [];

  const field = singleElimFieldSize(roster);
  const pairs = firstRoundSeedPairs(field);

  const byeVsR1: number[] = [];
  const pureBye: number[] = [];
  const round1: number[] = [];

  const slotKind = (a: number, b: number): ['PLAY' | 'BYE' | 'EMPTY', number[]] => {
    const hasA = a <= roster;
    const hasB = b <= roster;
    if (hasA && hasB) return ['PLAY', [a, b]];
    if (hasA !== hasB) return ['BYE', [hasA ? a : b]];
    return ['EMPTY', []];
  };

  for (let p = 1; p <= field / 4; p += 1) {
    const [a1, b1] = pairs[2 * p - 2]!;
    const [a2, b2] = pairs[2 * p - 1]!;
    const [kind1, seeds1] = slotKind(a1, b1);
    const [kind2, seeds2] = slotKind(a2, b2);
    const kinds = new Set([kind1, kind2]);
    if (kinds.has('PLAY') && kinds.has('BYE')) {
      if (kind1 === 'PLAY') {
        round1.push(...seeds1);
        byeVsR1.push(...seeds2);
      } else {
        round1.push(...seeds2);
        byeVsR1.push(...seeds1);
      }
    } else if (kind1 === 'BYE' && kind2 === 'BYE') {
      pureBye.push(...seeds1, ...seeds2);
    } else if (kind1 === 'PLAY' && kind2 === 'PLAY') {
      round1.push(...seeds1, ...seeds2);
    }
  }

  const pots: ByeDrawPot[] = [];
  if (byeVsR1.length > 0) {
    pots.push({
      key: 'bye_vs_r1',
      label: 'Bye vs R1 Winners',
      size: byeVsR1.length,
    });
  }
  if (pureBye.length > 0) {
    pots.push({ key: 'bye', label: 'Bye', size: pureBye.length });
  }
  if (round1.length > 0) {
    pots.push({ key: 'round_1', label: 'Round 1', size: round1.length });
  }
  return pots;
}
