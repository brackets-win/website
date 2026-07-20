import { useState } from 'react';

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
  viewerUserId: number;
  onSelectPlayer: (userId: number, displayName: string) => void;
};

type PersonAwardCard = {
  key: keyof StreakAwardsPayload;
  emoji: string;
  title: string;
  /** Screen-reader / tooltip label when title is hidden (emoji-only cards). */
  ariaLabel?: string;
  valueLabel: (winner: StreakAwardWinner) => string | null;
};

const BASE_PERSON_AWARD_CARDS: PersonAwardCard[] = [
  {
    key: 'streak_champion',
    emoji: '🏆',
    title: 'Streak Champion',
    valueLabel: (w) => String(w.long_win_display ?? w.display_name ?? '—'),
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

const KNOCKOUT_PODIUM_CARDS: PersonAwardCard[] = [
  {
    key: 'knockout_first',
    emoji: '🥇',
    title: '',
    ariaLabel: '1st Place',
    valueLabel: () => null,
  },
  {
    key: 'knockout_second',
    emoji: '🥈',
    title: '',
    ariaLabel: '2nd Place',
    valueLabel: () => null,
  },
  {
    key: 'knockout_third',
    emoji: '🥉',
    title: '',
    ariaLabel: '3rd Place',
    valueLabel: () => null,
  },
];

const KNOCKOUT_BEST_STREAK_CARD: PersonAwardCard = {
  key: 'best_streak',
  emoji: '🐦‍🔥',
  title: 'Best Streak',
  valueLabel: (w) => String(w.long_win_display ?? '—'),
};

const CONSOLATION_CHAMPION_CARD: PersonAwardCard = {
  key: 'consolation_champion',
  emoji: '🥲',
  title: 'Consolation Champion',
  valueLabel: (w) => String(w.record ?? w.wins ?? '—'),
};

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
    badge: () => null,
  },
  {
    key: 'meanest_question',
    emoji: '🌊',
    title: 'Meanest Question',
    badge: () => null,
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

function personAwardCards(awards: StreakAwardsPayload): PersonAwardCard[] {
  if (!awards.had_knockout) {
    return [...BASE_PERSON_AWARD_CARDS];
  }

  return [
    ...KNOCKOUT_PODIUM_CARDS,
    KNOCKOUT_BEST_STREAK_CARD,
    ...BASE_PERSON_AWARD_CARDS.slice(1),
    CONSOLATION_CHAMPION_CARD,
  ];
}

function categoryWinners(
  awards: StreakAwardsPayload,
  key: keyof StreakAwardsPayload,
): StreakAwardWinner[] {
  const category = awards[key];
  if (
    category &&
    typeof category === 'object' &&
    'winners' in category &&
    Array.isArray(category.winners)
  ) {
    return category.winners as StreakAwardWinner[];
  }
  return [];
}

function QuestionAwardCardView({
  card,
  category,
  expandedKey,
  viewerUserId,
  onToggleExpand,
  onSelectPlayer,
}: {
  card: QuestionAwardCard;
  category: StreakAwardQuestionCategory;
  expandedKey: string | null;
  viewerUserId: number;
  onToggleExpand: (questionId: number, choiceId: number) => void;
  onSelectPlayer: (userId: number, displayName: string) => void;
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
              <li key={winnerKey(winner)} className="streak-awards__question">
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
                  expandableStats
                  expandedKey={expandedKey}
                  questionId={winner.question_id}
                  viewerUserId={viewerUserId}
                  onToggleExpand={onToggleExpand}
                  onSelectPicker={onSelectPlayer}
                />
              </li>
            );
          })}
        </ul>
      )}
    </li>
  );
}

export function StreakAwards({
  awards,
  viewerUserId,
  onSelectPlayer,
}: Props) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const personCards = personAwardCards(awards);

  function toggleExpanded(questionId: number, choiceId: number) {
    const key = `${questionId}-${choiceId}`;
    setExpandedKey((prev) => (prev === key ? null : key));
  }

  return (
    <section className="card streak-awards">
      <ul className="streak-awards__grid">
        {personCards.map((card) => {
          const winners = categoryWinners(awards, card.key);
          return (
            <li key={String(card.key)} className="streak-awards__card">
              <h2
                className={
                  card.title
                    ? 'streak-awards__title'
                    : 'streak-awards__title streak-awards__title--emoji-only'
                }
                aria-label={card.ariaLabel ?? card.title}
              >
                <span className="streak-awards__emoji" aria-hidden>
                  {card.emoji}
                </span>
                {card.title || null}
              </h2>
              {winners.length === 0 ? (
                <p className="streak-awards__empty">No winner yet.</p>
              ) : (
                <ul className="streak-awards__winners">
                  {winners.map((winner) => {
                    const value = card.valueLabel(winner);
                    return (
                      <li key={winner.user_id} className="streak-awards__winner">
                        <span className="streak-awards__name">
                          {winner.display_name}
                        </span>
                        {value ? (
                          <span className="streak-awards__value">{value}</span>
                        ) : null}
                      </li>
                    );
                  })}
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
            expandedKey={expandedKey}
            viewerUserId={viewerUserId}
            onToggleExpand={toggleExpanded}
            onSelectPlayer={onSelectPlayer}
          />
        ))}
      </ul>
    </section>
  );
}
