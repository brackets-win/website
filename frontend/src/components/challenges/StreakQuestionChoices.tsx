import type {
  StreakQuestionChoiceInfo,
  StreakStatsChoice,
  StreakStatsPicker,
} from '../../utils/api';

import './StreakQuestionChoices.css';

type ChoiceRow = StreakQuestionChoiceInfo | StreakStatsChoice;

type H2hPickLabels = {
  leftPickChoiceId: number | null;
  rightPickChoiceId: number | null;
  leftBadge: string;
  rightBadge: string;
  leftBadgeShort: string;
  rightBadgeShort: string;
};

type Props = {
  choices: ChoiceRow[];
  userChoiceId: number | null;
  correctChoiceId: number | null;
  resolved: boolean;
  showPickPct?: boolean;
  showPickStats?: boolean;
  statsMode?: boolean;
  h2h?: H2hPickLabels;
  expandableStats?: boolean;
  expandedKey?: string | null;
  questionId?: number;
  disabled?: boolean;
  deadlineLocked?: boolean;
  canClearPick?: boolean;
  onPick?: (choiceId: number) => void;
  onClearPick?: () => void;
  onToggleExpand?: (questionId: number, choiceId: number) => void;
  onSelectPicker?: (userId: number, displayName: string) => void;
  viewerUserId?: number;
};

function choicePickers(choice: ChoiceRow): StreakStatsPicker[] {
  return 'pickers' in choice ? choice.pickers : [];
}

export function StreakQuestionChoices({
  choices,
  userChoiceId,
  correctChoiceId,
  resolved,
  showPickPct = false,
  showPickStats = false,
  statsMode = false,
  h2h,
  expandableStats = false,
  expandedKey = null,
  questionId,
  disabled = false,
  deadlineLocked = false,
  canClearPick = false,
  onPick,
  onClearPick,
  onToggleExpand,
  onSelectPicker,
  viewerUserId,
}: Props) {
  const actionsClassName = expandableStats
    ? 'streak-question__actions streak-question__actions--fill streak-question__actions--stats'
    : 'streak-question__actions streak-question__actions--fill';

  return (
    <div className={actionsClassName} role="group" aria-label="Choices">
      {choices.map((choice) => {
        const isUserPick = userChoiceId === choice.id;
        const isCorrect =
          resolved &&
          correctChoiceId != null &&
          choice.id === correctChoiceId &&
          (statsMode || isUserPick);
        const isWrong =
          resolved &&
          correctChoiceId != null &&
          (statsMode
            ? choice.id !== correctChoiceId
            : isUserPick && choice.id !== correctChoiceId);

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

        const expandKey =
          questionId != null ? `${questionId}-${choice.id}` : null;
        const isExpanded =
          expandableStats && expandKey != null && expandedKey === expandKey;
        const pickers = choicePickers(choice);

        if (expandableStats) {
          className += ' streak-choice--expandable';
        }

        if (!expandableStats) {
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
                  onClearPick?.();
                  return;
                }
                onPick?.(choice.id);
              }}
            >
              {isCorrect ? (
                <span
                  className="streak-choice__mark streak-choice__mark--correct"
                  aria-hidden
                >
                  ✓
                </span>
              ) : null}
              {isWrong ? (
                <span
                  className="streak-choice__mark streak-choice__mark--wrong"
                  aria-hidden
                >
                  ✗
                </span>
              ) : null}
              {h2h && h2h.leftPickChoiceId === choice.id ? (
                <span className="streak-choice__h2h-badges streak-choice__h2h-badges--left">
                  <span className="streak-choice__h2h-badge streak-choice__h2h-badge--desktop">
                    {h2h.leftBadge}
                  </span>
                  <span className="streak-choice__h2h-badge streak-choice__h2h-badge--mobile">
                    {h2h.leftBadgeShort}
                  </span>
                </span>
              ) : null}
              <span className="streak-choice__label">{choice.label}</span>
              {showPickStats &&
              choice.pick_count != null &&
              choice.pick_pct != null ? (
                <span className="streak-choice__pct">
                  {choice.pick_count} ({choice.pick_pct}%)
                </span>
              ) : showPickPct && choice.pick_pct != null ? (
                <span className="streak-choice__pct">{choice.pick_pct}%</span>
              ) : null}
              {h2h && h2h.rightPickChoiceId === choice.id ? (
                <span className="streak-choice__h2h-badges streak-choice__h2h-badges--right">
                  <span className="streak-choice__h2h-badge streak-choice__h2h-badge--desktop">
                    {h2h.rightBadge}
                  </span>
                  <span className="streak-choice__h2h-badge streak-choice__h2h-badge--mobile">
                    {h2h.rightBadgeShort}
                  </span>
                </span>
              ) : null}
            </button>
          );
        }

        return (
          <div key={choice.id} className="streak-choice-wrap">
            <button
              type="button"
              className={className}
              aria-expanded={isExpanded}
              onClick={() => {
                if (questionId != null && onToggleExpand) {
                  onToggleExpand(questionId, choice.id);
                }
              }}
            >
              {isCorrect ? (
                <span
                  className="streak-choice__mark streak-choice__mark--correct"
                  aria-hidden
                >
                  ✓
                </span>
              ) : null}
              {isWrong ? (
                <span
                  className="streak-choice__mark streak-choice__mark--wrong"
                  aria-hidden
                >
                  ✗
                </span>
              ) : null}
              <span className="streak-choice__label">{choice.label}</span>
              {showPickStats &&
              choice.pick_count != null &&
              choice.pick_pct != null ? (
                <span className="streak-choice__pct">
                  {choice.pick_count} ({choice.pick_pct}%)
                </span>
              ) : null}
            </button>
            {isExpanded ? (
              <div className="streak-choice__expand">
                {pickers.length === 0 ? (
                  <p className="streak-choice__expand-empty">No picks</p>
                ) : (
                  <ul className="streak-choice__expand-list">
                    {pickers.map((picker) => {
                      const isViewer =
                        viewerUserId != null &&
                        picker.user_id === viewerUserId;
                      const pickerClassName = isViewer
                        ? 'streak-choice__picker streak-choice__picker--viewer'
                        : 'streak-choice__picker';
                      return (
                      <li
                        key={picker.user_id}
                        className="streak-choice__expand-item"
                      >
                        {onSelectPicker ? (
                          <button
                            type="button"
                            className={pickerClassName}
                            onClick={() =>
                              onSelectPicker(
                                picker.user_id,
                                picker.display_name,
                              )
                            }
                          >
                            {picker.display_name}
                          </button>
                        ) : (
                          <span className={pickerClassName}>
                            {picker.display_name}
                          </span>
                        )}
                      </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
