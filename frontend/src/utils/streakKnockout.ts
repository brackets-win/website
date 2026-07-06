import type {
  StreakKnockoutPayload,
  StreakParticipantPickRow,
  StreakQuestionInfo,
} from './api';

export function knockoutRoundLabel(
  roundIndex: number,
  totalRounds: number,
): string {
  if (roundIndex === totalRounds) return 'Final';
  if (roundIndex === totalRounds - 1) return 'Semi Final';
  if (roundIndex === totalRounds - 2 && totalRounds >= 3) return 'Quarter Final';
  return `Round ${roundIndex}`;
}

export type KnockoutPhaseInfo = {
  round_index: number;
  label: string;
  starts_at: string;
};

function questionPhaseKey(question: {
  knockout_phase_starts_at?: string | null;
  knockout_phase_label?: string | null;
}): string | null {
  const startsAt = question.knockout_phase_starts_at ?? null;
  const label = question.knockout_phase_label ?? null;
  if (!startsAt || !label) return null;
  return `${startsAt}\0${label}`;
}

export function activeKnockoutRoundIndex(
  knockout: StreakKnockoutPayload,
): number | null {
  for (const round of knockout.rounds) {
    if (round.matches.some((match) => match.is_live)) {
      return round.round_index;
    }
  }
  if (knockout.status === 'IN_PROGRESS') {
    return knockout.current_round;
  }
  return null;
}

export function stageQuestionProgress(
  questions: StreakQuestionInfo[],
  phaseStartsAt: string,
): { resolved: number; total: number } {
  const stageQuestions = questions.filter(
    (question) => question.knockout_phase_starts_at === phaseStartsAt,
  );
  return {
    total: stageQuestions.length,
    resolved: stageQuestions.filter((question) => question.resolved_at != null)
      .length,
  };
}

export function uniquePlayerAbbreviations(
  nameA: string,
  nameB: string,
): [string, string] {
  const compactA = nameA.trim().replace(/\s+/g, '');
  const compactB = nameB.trim().replace(/\s+/g, '');
  if (!compactA || !compactB) {
    return [compactA.toUpperCase(), compactB.toUpperCase()];
  }

  let lenA = 1;
  let lenB = 1;
  while (lenA <= compactA.length || lenB <= compactB.length) {
    const abbrA = compactA.slice(0, lenA).toUpperCase();
    const abbrB = compactB.slice(0, lenB).toUpperCase();
    if (abbrA !== abbrB) {
      return [abbrA, abbrB];
    }
    if (lenA <= lenB && lenA < compactA.length) {
      lenA += 1;
    } else if (lenB < compactB.length) {
      lenB += 1;
    } else if (lenA < compactA.length) {
      lenA += 1;
    } else {
      break;
    }
  }
  return [compactA.toUpperCase(), compactB.toUpperCase()];
}

export function makePickPhaseDividers<T extends {
  id: number;
  closes_at: string;
  knockout_phase_starts_at?: string | null;
  knockout_phase_label?: string | null;
}>(
  questions: T[],
): Array<
  | { type: 'divider'; label: string; key: string }
  | { type: 'question'; question: T }
> {
  if (questions.length === 0) return [];

  const rows: Array<
    | { type: 'divider'; label: string; key: string }
    | { type: 'question'; question: T }
  > = [];

  for (let i = 0; i < questions.length; i += 1) {
    const question = questions[i];
    const phaseKey = questionPhaseKey(question);
    const prevPhaseKey = i > 0 ? questionPhaseKey(questions[i - 1]) : null;

    // Divider only when entering a new knockout phase that has open questions
    // below it, and there is at least one question above (streak or prior round).
    if (
      phaseKey !== null &&
      phaseKey !== prevPhaseKey &&
      i > 0 &&
      question.knockout_phase_label
    ) {
      rows.push({
        type: 'divider',
        label: question.knockout_phase_label,
        key: phaseKey,
      });
    }
    rows.push({ type: 'question', question });
  }

  while (rows.length > 0 && rows[rows.length - 1].type === 'divider') {
    rows.pop();
  }

  return rows;
}

export type PickResultsSort = 'desc' | 'asc';

type ClosesAtRow = {
  closes_at: string;
  id?: number;
  question_id?: number;
};

export function compareClosesAt(
  a: ClosesAtRow,
  b: ClosesAtRow,
  sort: PickResultsSort,
): number {
  const timeA = new Date(a.closes_at).getTime();
  const timeB = new Date(b.closes_at).getTime();
  const idA = a.id ?? a.question_id ?? 0;
  const idB = b.id ?? b.question_id ?? 0;
  if (sort === 'desc') {
    if (timeA !== timeB) return timeB - timeA;
    return idB - idA;
  }
  if (timeA !== timeB) return timeA - timeB;
  return idA - idB;
}

export function playerPickPhaseDividers(
  picks: StreakParticipantPickRow[],
  sort: PickResultsSort = 'desc',
): Array<
  | { type: 'divider'; label: string; key: string }
  | { type: 'pick'; pick: StreakParticipantPickRow }
> {
  if (picks.length === 0) return [];

  const sorted = [...picks].sort((a, b) => compareClosesAt(a, b, sort));
  const rows: Array<
    | { type: 'divider'; label: string; key: string }
    | { type: 'pick'; pick: StreakParticipantPickRow }
  > = [];
  let prevKey: string | null = null;

  for (const pick of sorted) {
    const key = pick.section_key ?? 'streak';
    const label = pick.section_label ?? 'Streak';
    if (key !== prevKey) {
      rows.push({ type: 'divider', label, key });
      prevKey = key;
    }
    rows.push({ type: 'pick', pick });
  }

  return rows;
}
