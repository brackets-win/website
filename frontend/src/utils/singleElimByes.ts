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
