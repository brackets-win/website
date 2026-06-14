import type { StreakAwardWinner, StreakAwardsPayload } from '../../utils/api';

import './StreakAwards.css';

type Props = {
  awards: StreakAwardsPayload;
};

type AwardCard = {
  key: keyof StreakAwardsPayload;
  title: string;
  valueLabel: (winner: StreakAwardWinner) => string;
};

const AWARD_CARDS: AwardCard[] = [
  {
    key: 'streak_champion',
    title: 'Streak Champion',
    valueLabel: (w) => String(w.long_win_display ?? '—'),
  },
  {
    key: 'best_picker',
    title: 'Best Picker',
    valueLabel: (w) => `${w.win_pct ?? 0}%`,
  },
  {
    key: 'most_wins',
    title: 'Most Wins',
    valueLabel: (w) => String(w.wins ?? 0),
  },
  {
    key: 'active_streak',
    title: 'Active Streak',
    valueLabel: (w) => String(w.current_display ?? '—'),
  },
  {
    key: 'losing_streak',
    title: 'Losing Streak',
    valueLabel: (w) => String(w.long_loss_display ?? '—'),
  },
];

export function StreakAwards({ awards }: Props) {
  return (
    <section className="card streak-awards">
      <ul className="streak-awards__grid">
        {AWARD_CARDS.map((card) => {
          const winners = awards[card.key].winners;
          return (
            <li key={card.key} className="streak-awards__card">
              <h2 className="streak-awards__title">{card.title}</h2>
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
    </section>
  );
}
