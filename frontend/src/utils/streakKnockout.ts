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
