/** US Eastern wall times for challenge deadlines. */

export const EST_TIMEZONE = 'America/New_York';

/** Convert datetime-local value (interpreted as EST) to UTC ISO for the API. */
export function estLocalInputToIso(localValue: string): string | undefined {
  const trimmed = localValue.trim();
  if (!trimmed) return undefined;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(trimmed);
  if (!m) return undefined;
  const [, y, mo, d, h, mi] = m;
  const probe = new Date(
    `${y}-${mo}-${d}T${h}:${mi}:00Z`,
  );
  if (Number.isNaN(probe.getTime())) return undefined;
  const asUtc = Date.UTC(
    Number(y),
    Number(mo) - 1,
    Number(d),
    Number(h),
    Number(mi),
  );
  const offsetMs = easternOffsetMs(asUtc);
  return new Date(asUtc - offsetMs).toISOString();
}

function easternOffsetMs(utcMs: number): number {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: EST_TIMEZONE,
    timeZoneName: 'shortOffset',
  });
  const parts = fmt.formatToParts(new Date(utcMs));
  const tz = parts.find((p) => p.type === 'timeZoneName')?.value ?? 'GMT-5';
  const m = /GMT([+-])(\d{1,2})(?::(\d{2}))?/.exec(tz);
  if (!m) return 5 * 60 * 60 * 1000;
  const sign = m[1] === '-' ? -1 : 1;
  const hours = parseInt(m[2], 10);
  const mins = m[3] ? parseInt(m[3], 10) : 0;
  return sign * (hours * 60 + mins) * 60 * 1000;
}

/** Format an API ISO deadline for display in Eastern time (e.g. "Jun 15, 2026 at 11:59 PM EST"). */
export function formatDeadlineEst(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const datePart = new Intl.DateTimeFormat('en-US', {
    timeZone: EST_TIMEZONE,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(d);
  const timePart = new Intl.DateTimeFormat('en-US', {
    timeZone: EST_TIMEZONE,
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(d);
  return `${datePart} at ${timePart}`;
}

/** Build value for `<input type="datetime-local" />` from API ISO (Eastern). */
export function isoToEstLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: EST_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}
