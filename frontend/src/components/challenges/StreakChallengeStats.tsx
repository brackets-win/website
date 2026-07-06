import { useEffect, useMemo, useRef, useState } from 'react';

import {
  ApiError,
  getStreakChallengeStats,
  type StreakChallengeStatsPayload,
} from '../../utils/api';
import { formatDeadlineEst } from '../../utils/est';
import { compareClosesAt, type PickResultsSort } from '../../utils/streakKnockout';

import { StreakQuestionChoices } from './StreakQuestionChoices';
import { StreakResultsSortToggle } from './StreakResultsSortToggle';
import './StreakChallengeStats.css';

type Props = {
  streakChallengeId: number;
  viewerUserId: number;
  userChoiceByQuestionId: Record<number, number | null>;
  onSelectPlayer: (userId: number, displayName: string) => void;
  sortOrder: PickResultsSort;
  onSortOrderChange: (sort: PickResultsSort) => void;
};

type PickStatus = 'correct' | 'wrong' | 'none';

function pickStatus(
  userChoiceId: number | null | undefined,
  correctChoiceId: number | null,
): PickStatus {
  if (userChoiceId == null) return 'none';
  if (correctChoiceId == null) return 'none';
  return userChoiceId === correctChoiceId ? 'correct' : 'wrong';
}

function PickStatusIcon({ status }: { status: PickStatus }) {
  if (status === 'correct') {
    return (
      <span
        className="streak-question__pick-status streak-question__pick-status--correct"
        aria-label="Correct pick"
      >
        <span className="streak-question__pick-status-mark" aria-hidden>
          ✓
        </span>
      </span>
    );
  }
  if (status === 'wrong') {
    return (
      <span
        className="streak-question__pick-status streak-question__pick-status--wrong"
        aria-label="Incorrect pick"
      >
        <span className="streak-question__pick-status-mark" aria-hidden>
          ✗
        </span>
      </span>
    );
  }
  return (
    <span
      className="streak-question__pick-status streak-question__pick-status--none"
      aria-label="No pick"
    >
      <span className="streak-question__pick-status-mark" aria-hidden>
        —
      </span>
    </span>
  );
}

export function StreakChallengeStats({
  streakChallengeId,
  viewerUserId,
  userChoiceByQuestionId,
  onSelectPlayer,
  sortOrder,
  onSortOrderChange,
}: Props) {
  const [stats, setStats] = useState<StreakChallengeStatsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const fetchGen = useRef(0);

  useEffect(() => {
    const gen = ++fetchGen.current;
    setLoading(true);
    setError('');
    void getStreakChallengeStats(streakChallengeId)
      .then((data) => {
        if (gen !== fetchGen.current) return;
        setStats(data);
      })
      .catch((e) => {
        if (gen !== fetchGen.current) return;
        setError(
          e instanceof ApiError ? e.message : 'Unable to load results.',
        );
      })
      .finally(() => {
        if (gen !== fetchGen.current) return;
        setLoading(false);
      });
  }, [streakChallengeId]);

  const sortedQuestions = useMemo(() => {
    if (!stats?.questions.length) return [];
    return [...stats.questions].sort((a, b) =>
      compareClosesAt(
        { closes_at: a.closes_at, id: a.question_id },
        { closes_at: b.closes_at, id: b.question_id },
        sortOrder,
      ),
    );
  }, [stats?.questions, sortOrder]);

  function toggleExpanded(questionId: number, choiceId: number) {
    const key = `${questionId}-${choiceId}`;
    setExpandedKey((prev) => (prev === key ? null : key));
  }

  if (loading) {
    return <p className="streak-view__muted">Loading…</p>;
  }

  if (error) {
    return <div className="alert alert--error">{error}</div>;
  }

  if (!stats || stats.questions.length === 0) {
    return <p className="streak-view__muted">No closed questions yet.</p>;
  }

  return (
    <section className="streak-view__questions streak-challenge-stats">
      {stats.questions.length >= 2 ? (
        <div className="streak-challenge-stats__head">
          <StreakResultsSortToggle
            value={sortOrder}
            onChange={onSortOrderChange}
          />
        </div>
      ) : null}
      <ul className="streak-question-list">
        {sortedQuestions.map((question) => {
          const userChoiceId =
            userChoiceByQuestionId[question.question_id] ?? null;
          const status = pickStatus(userChoiceId, question.correct_choice_id);
          return (
          <li
            key={question.question_id}
            className="card streak-question streak-question--results"
          >
            <PickStatusIcon status={status} />
            <div className="streak-question__body">
            <div className="streak-question__head">
              <div className="streak-question__head-main">
                <p className="streak-question__text">{question.text}</p>
                <p className="streak-question__meta">
                  Closed {formatDeadlineEst(question.closes_at)}
                </p>
              </div>
            </div>
            <StreakQuestionChoices
              choices={question.choices}
              userChoiceId={userChoiceId}
              correctChoiceId={question.correct_choice_id}
              resolved
              statsMode
              showPickStats
              expandableStats
              expandedKey={expandedKey}
              questionId={question.question_id}
              viewerUserId={viewerUserId}
              onToggleExpand={toggleExpanded}
              onSelectPicker={onSelectPlayer}
            />
            </div>
          </li>
          );
        })}
      </ul>
    </section>
  );
}
