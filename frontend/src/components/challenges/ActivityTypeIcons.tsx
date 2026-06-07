import { ChartNoAxesColumn, Flame, Trophy } from 'lucide-react';

import { BracketsLogoMark } from '../BracketsLogoMark';

const ICON_SIZE = 20;
const ICON_STROKE = 2;

export type ActivityTypeKey =
  | 'bracket_challenge'
  | 'tournament'
  | 'poll'
  | 'streak';

export function ActivityTypeIcon({
  type,
  className,
}: {
  type: ActivityTypeKey;
  className?: string;
}) {
  switch (type) {
    case 'bracket_challenge':
      return <BracketsLogoMark className={className} />;
    case 'tournament':
      return (
        <Trophy
          className={className}
          size={ICON_SIZE}
          strokeWidth={ICON_STROKE}
          aria-hidden
        />
      );
    case 'poll':
      return (
        <ChartNoAxesColumn
          className={className}
          size={ICON_SIZE}
          strokeWidth={ICON_STROKE}
          aria-hidden
        />
      );
    case 'streak':
      return (
        <Flame
          className={className}
          size={ICON_SIZE}
          strokeWidth={ICON_STROKE}
          aria-hidden
        />
      );
  }
}
