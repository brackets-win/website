import type { StreakQuestionChoiceInfo } from '../../utils/api';

import './StreakQuestionChoices.css';

type Props = {
  choices: StreakQuestionChoiceInfo[];
  userChoiceId: number | null;
  correctChoiceId: number | null;
  resolved: boolean;
  showPickPct?: boolean;
  disabled?: boolean;
  deadlineLocked?: boolean;
  canClearPick?: boolean;
  onPick?: (choiceId: number) => void;
  onClearPick?: () => void;
};

export function StreakQuestionChoices({
  choices,
  userChoiceId,
  correctChoiceId,
  resolved,
  showPickPct = false,
  disabled = false,
  deadlineLocked = false,
  canClearPick = false,
  onPick,
  onClearPick,
}: Props) {
  return (
    <div
      className="streak-question__actions streak-question__actions--fill"
      role="group"
      aria-label="Choices"
    >
      {choices.map((choice) => {
        const isUserPick = userChoiceId === choice.id;
        const isCorrect =
          resolved &&
          correctChoiceId != null &&
          choice.id === correctChoiceId &&
          isUserPick;
        const isWrong =
          resolved &&
          correctChoiceId != null &&
          isUserPick &&
          choice.id !== correctChoiceId;

        let className = 'streak-choice btn btn--secondary';
        if (!resolved) {
          className = isUserPick
            ? 'streak-choice btn btn--primary'
            : 'streak-choice btn btn--secondary';
        } else if (isCorrect) {
          className = 'streak-choice streak-choice--correct';
        } else if (isWrong) {
          className = 'streak-choice streak-choice--wrong';
        }

        const canToggleClear =
          !resolved && canClearPick && isUserPick && onClearPick != null;

        return (
          <button
            key={choice.id}
            type="button"
            className={className}
            disabled={
              disabled ||
              resolved ||
              deadlineLocked ||
              (canToggleClear ? false : !onPick)
            }
            title={canToggleClear ? 'Click again to clear' : undefined}
            onClick={() => {
              if (canToggleClear) {
                onClearPick();
                return;
              }
              onPick?.(choice.id);
            }}
          >
            {isCorrect ? (
              <span className="streak-choice__mark streak-choice__mark--correct" aria-hidden>
                ✓
              </span>
            ) : null}
            {isWrong ? (
              <span className="streak-choice__mark streak-choice__mark--wrong" aria-hidden>
                ✗
              </span>
            ) : null}
            <span className="streak-choice__label">{choice.label}</span>
            {showPickPct && choice.pick_pct != null ? (
              <span className="streak-choice__pct">{choice.pick_pct}%</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
