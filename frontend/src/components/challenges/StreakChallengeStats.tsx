import { useEffect, useRef, useState } from 'react';

import {
  ApiError,
  getStreakChallengeStats,
  type StreakChallengeStatsPayload,
} from '../../utils/api';
import { formatDeadlineEst } from '../../utils/est';

import { StreakQuestionChoices } from './StreakQuestionChoices';
import './StreakChallengeStats.css';

type Props = {
  streakChallengeId: number;
  onSelectPlayer: (userId: number, displayName: string) => void;
};

export function StreakChallengeStats({
  streakChallengeId,
  onSelectPlayer,
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
          e instanceof ApiError ? e.message : 'Unable to load stats.',
        );
      })
      .finally(() => {
        if (gen !== fetchGen.current) return;
        setLoading(false);
      });
  }, [streakChallengeId]);

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
      <ul className="streak-question-list">
        {stats.questions.map((question) => (
          <li key={question.question_id} className="card streak-question">
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
              userChoiceId={null}
              correctChoiceId={question.correct_choice_id}
              resolved
              statsMode
              showPickStats
              expandableStats
              expandedKey={expandedKey}
              questionId={question.question_id}
              onToggleExpand={toggleExpanded}
              onSelectPicker={onSelectPlayer}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
