# Brackets Backend Data Model

## Models Overview

### User & Authentication
- **User** - Platform users with profiles and permissions
- **UserTier** - Subscription tiers defining feature access

### Bracket Structure
- **Bracket** - Specific tournament instance (e.g., "2026 FIFA World Cup")
- **BracketStage** - Single phase (group or knockout) within a bracket
- **BracketTemplate** - Reusable blueprint for common bracket structures (e.g., "Group & Knockout", "Single Elimination")
- **GroupStage** - Group stage with qualifying rules
- **KnockoutStage** - Single/double elimination phase

### Contestants
- **ContestantTag** - Tags for categorizing contestants (e.g., "soccer", "national", "club")
- **Contestant** - Reusable contestant definition (e.g., "Brazil", "Real Madrid")
- **BracketContestant** - Instance of contestant in a specific bracket with seed

### Tournament Groups
- **Group** - Tournament group (e.g., "Group A") with auto-generated codes
- **GroupMembership** - Tracks contestant's participation and final position in a group

### Matchups
- **Matchup** - Individual match with contestants and winner
- **UserPick** - User's prediction for a matchup

### User Brackets & Challenges
- **UserBracket** - User's filled bracket (or master bracket for actual results)
- **BracketChallenge** - Competition group with optional per-challenge seed randomization
- **ChallengeParticipant** - Links users to challenges

### Activity
- **ActivityLog** - Tracks user actions and system events

## Bracket Templates

System templates for quick bracket creation:
- **Group & Knockout**: Group stage (groups of 4 with 2 qualifying) + knockout rounds
- **Single Elimination**: Pure knockout bracket with multiple rounds

Templates automatically generate all necessary BracketStages based on contestant count.

## Distribution Strategies

When populating initial bracket positions:

- **Balanced**: Admin assigns seeds 1-n, snake draft applied
- **Random Balanced**: Admin assigns seed pool values to groups of contestants, randomized within each seed pool
- **Random**: Pure random distribution
- **Custom**: Admin manually places each contestant