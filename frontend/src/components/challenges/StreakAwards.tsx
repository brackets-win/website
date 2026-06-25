import type {
  StreakAwardQuestionCategory,
  StreakAwardQuestionWinner,
  StreakAwardWinner,
  StreakAwardsPayload,
} from '../../utils/api';

import { StreakQuestionChoices } from './StreakQuestionChoices';
import './StreakAwards.css';

type Props = {
  awards: StreakAwardsPayload;
};

type PersonAwardCard = {
  key: 'streak_champion' | 'best_picker' | 'most_wins' | 'active_streak' | 'losing_streak';
  emoji: string;
  title: string;
  valueLabel: (winner: StreakAwardWinner) => string;
};

const PERSON_AWARD_CARDS: PersonAwardCard[] = [
  {
    key: 'streak_champion',
    emoji: '🏆',
    title: 'Streak Champion',
    valueLabel: (w) => String(w.long_win_display ?? '—'),
  },
  {
    key: 'best_picker',
    emoji: '🎯',
    title: 'Best Picker',
    valueLabel: (w) => `${w.win_pct ?? 0}%`,
  },
  {
    key: 'most_wins',
    emoji: '💪',
    title: 'Most Wins',
    valueLabel: (w) => String(w.wins ?? 0),
  },
  {
    key: 'active_streak',
    emoji: '🔥',
    title: 'Active Streak',
    valueLabel: (w) => String(w.current_display ?? '—'),
  },
  {
    key: 'losing_streak',
    emoji: '🧊',
    title: 'Losing Streak',
    valueLabel: (w) => String(w.long_loss_display ?? '—'),
  },
];

type QuestionAwardCard = {
  key: 'nicest_question' | 'meanest_question' | 'streak_ending_question';
  emoji: string;
  title: string;
  badge: (winner: StreakAwardQuestionWinner) => string | null;
};

const QUESTION_AWARD_CARDS: QuestionAwardCard[] = [
  {
    key: 'nicest_question',
    emoji: '⛽',
    title: 'Nicest Question',
    badge: (w) =>
      w.correct_count != null
        ? `${w.correct_count} correct`
        : null,
  },
  {
    key: 'meanest_question',
    emoji: '🌊',
    title: 'Meanest Question',
    badge: (w) =>
      w.incorrect_count != null
        ? `${w.incorrect_count} wrong`
        : null,
  },
  {
    key: 'streak_ending_question',
    emoji: '🧯',
    title: 'Streak-Ending Question',
    badge: (w) =>
      w.player != null
        ? `Ended ${w.player.display_name}'s ${w.long_win_display ?? ''} streak`
        : null,
  },
];

function winnerKey(winner: StreakAwardQuestionWinner): string {
  return winner.player != null
    ? `${winner.question_id}-${winner.player.user_id}`
    : String(winner.question_id);
}

function QuestionAwardCardView({
  card,
  category,
}: {
  card: QuestionAwardCard;
  category: StreakAwardQuestionCategory;
}) {
  const winners = category.winners;
  return (
    <li className="streak-awards__card streak-awards__card--question">
      <h2 className="streak-awards__title">
        <span className="streak-awards__emoji" aria-hidden>
          {card.emoji}
        </span>
        {card.title}
      </h2>
      {winners.length === 0 ? (
        <p className="streak-awards__empty">No winner yet.</p>
      ) : (
        <ul className="streak-awards__questions">
          {winners.map((winner) => {
            const badge = card.badge(winner);
            return (
              <li
                key={winnerKey(winner)}
                className="streak-awards__question"
              >
                <p className="streak-awards__question-text">{winner.text}</p>
                {badge ? (
                  <p className="streak-awards__question-badge">{badge}</p>
                ) : null}
                <StreakQuestionChoices
                  choices={winner.choices}
                  userChoiceId={null}
                  correctChoiceId={winner.correct_choice_id}
                  resolved
                  statsMode
                  showPickStats
                />
              </li>
            );
          })}
        </ul>
      )}
    </li>
  );
}

export function StreakAwards({ awards }: Props) {
  return (
    <section className="card streak-awards">
      <ul className="streak-awards__grid">
        {PERSON_AWARD_CARDS.map((card) => {
          const winners = awards[card.key].winners;
          return (
            <li key={card.key} className="streak-awards__card">
              <h2 className="streak-awards__title">
                <span className="streak-awards__emoji" aria-hidden>
                  {card.emoji}
                </span>
                {card.title}
              </h2>
              {winners.length === 0 ? (
                <p className="streak-awards__empty">No winner yet.</p>
              ) : (
                <ul className="streak-awards__winners">
                  {winners.map((winner) => (
                    <li key={winner.user_id} className="streak-awards__winner">
                      <span className="streak-awards__name">
                        {winner.display_name}
                      </span>
                      <span className="streak-awards__value">
                        {card.valueLabel(winner)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      <ul className="streak-awards__questions-grid">
        {QUESTION_AWARD_CARDS.map((card) => (
          <QuestionAwardCardView
            key={card.key}
            card={card}
            category={awards[card.key]}
          />
        ))}
      </ul>
    </section>
  );
}
