"""
Utilities for distributing contestants to groups and knockout stages.
"""
import random
from collections import defaultdict


def generate_challenge_seed_mapping(bracket, challenge):
    """
    Generate randomized seed mapping for a challenge (for random_balanced strategy).

    Contestants are grouped by seed value, then randomly assigned position seeds within each group.

    Returns dict mapping bracket_contestant_id (str) to actual_position_seed (int).
    """
    from brackets.models import BracketContestant

    contestants = BracketContestant.objects.filter(bracket=bracket)

    # Group contestants by their seed value
    seed_groups = defaultdict(list)
    for contestant in contestants:
        seed = contestant.seed if contestant.seed is not None else 999999  # Put unseeded at end
        seed_groups[seed].append(contestant)

    # Calculate position seed ranges for each seed group
    seed_mapping = {}
    current_position = 1

    for seed_value in sorted(seed_groups.keys()):
        group_contestants = seed_groups[seed_value]
        group_size = len(group_contestants)

        # Randomly assign position seeds within this group's range
        available_positions = list(
            range(current_position, current_position + group_size))
        random.shuffle(available_positions)

        for contestant, position_seed in zip(group_contestants, available_positions):
            seed_mapping[str(contestant.id)] = position_seed

        current_position += group_size

    return seed_mapping


def get_contestant_seed(contestant, challenge=None):
    """
    Get effective seed for a contestant, checking challenge seed mapping if applicable.
    """
    if challenge and challenge.seed_mapping:
        return challenge.seed_mapping.get(str(contestant.id), contestant.seed)
    return contestant.seed


def distribute_contestants_to_groups(
    bracket,
    group_stage,
    strategy='balanced',
    challenge=None,
    manual_mapping=None
):
    """
    Distribute BracketContestants to Groups based on strategy.

    Strategies: 'balanced' (snake draft), 'random_balanced' (seed-based random + snake),
    'random' (pure random), 'custom' (manual via manual_mapping dict).

    Returns list of created GroupMembership objects.
    """
    from brackets.models import BracketContestant, Group, GroupMembership

    # Get all bracket contestants with effective seeds
    contestants = list(BracketContestant.objects.filter(bracket=bracket))

    # Sort by effective seed (considering challenge seed mapping)
    contestants.sort(key=lambda c: get_contestant_seed(c, challenge))

    # Get or create groups for this stage
    groups = []
    for i in range(group_stage.number_of_groups):
        group, created = Group.objects.get_or_create(
            bracket=bracket,
            stage=group_stage,
            order=i + 1,
            defaults={'name': f'Group {chr(65 + i)}'}  # Group A, B, C, etc.
        )
        groups.append(group)

    memberships = []

    if strategy == 'custom':
        if not manual_mapping:
            raise ValueError(
                "manual_mapping is required for 'custom' strategy")

        # Place contestants according to manual mapping
        for contestant in contestants:
            if contestant.id in manual_mapping:
                group_order = manual_mapping[contestant.id]
                group = next(
                    (g for g in groups if g.order == group_order), None)
                if group:
                    membership = GroupMembership.objects.create(
                        group=group,
                        contestant=contestant
                    )
                    memberships.append(membership)

    elif strategy == 'balanced':
        # Snake draft distribution
        # Example for 4 groups: A, B, C, D, D, C, B, A, A, B, C, D, ...
        group_assignment = []
        num_groups = len(groups)

        for i in range(len(contestants)):
            cycle = i // num_groups
            position_in_cycle = i % num_groups

            if cycle % 2 == 0:
                # Forward: A, B, C, D
                group_index = position_in_cycle
            else:
                # Backward: D, C, B, A
                group_index = num_groups - 1 - position_in_cycle

            group_assignment.append(groups[group_index])

        # Create memberships
        for contestant, group in zip(contestants, group_assignment):
            membership = GroupMembership.objects.create(
                group=group,
                contestant=contestant
            )
            memberships.append(membership)

    elif strategy == 'random_balanced':
        # Random balanced: randomize seeds within tiers, then snake
        # First, generate or use existing seed mapping
        if challenge and bracket.randomize_seeds_per_challenge:
            if not challenge.seed_mapping:
                # Generate new seed mapping based on tiers
                challenge.seed_mapping = generate_challenge_seed_mapping(
                    bracket, challenge)
                challenge.save()

            # Re-sort contestants by their challenge-specific seeds
            contestants.sort(key=lambda c: get_contestant_seed(c, challenge))

        # Now apply balanced (snake) distribution
        group_assignment = []
        num_groups = len(groups)

        for i in range(len(contestants)):
            cycle = i // num_groups
            position_in_cycle = i % num_groups

            if cycle % 2 == 0:
                group_index = position_in_cycle
            else:
                group_index = num_groups - 1 - position_in_cycle

            group_assignment.append(groups[group_index])

        for contestant, group in zip(contestants, group_assignment):
            membership = GroupMembership.objects.create(
                group=group,
                contestant=contestant
            )
            memberships.append(membership)

    elif strategy == 'random':
        # Pure random distribution
        contestant_list = list(contestants)
        random.shuffle(contestant_list)

        # Distribute evenly across groups
        for i, contestant in enumerate(contestant_list):
            group = groups[i % len(groups)]
            membership = GroupMembership.objects.create(
                group=group,
                contestant=contestant
            )
            memberships.append(membership)

    else:
        raise ValueError(
            f"Unknown strategy: {strategy}. Must be 'random', 'balanced', 'random_balanced', or 'custom'")

    return memberships


def seed_knockout_matchups(user_bracket, knockout_stage):
    """
    Create matchups for one knockout stage only (first round with seeds).

    Prefer ``ensure_full_knockout_matchups`` for a complete tree.

    Returns list of created Matchup objects.
    """
    from brackets.models import BracketContestant, Matchup

    bracket = user_bracket.bracket
    contestants = list(BracketContestant.objects.filter(
        bracket=bracket
    ).order_by('seed'))

    num_contestants = len(contestants)

    if num_contestants != knockout_stage.number_of_contestants:
        raise ValueError(
            f"Number of contestants ({num_contestants}) doesn't match "
            f"knockout stage requirement ({knockout_stage.number_of_contestants})"
        )

    matchups = []
    num_matchups = num_contestants // 2

    for position in range(1, num_matchups + 1):
        seed1 = position
        seed2 = num_contestants - position + 1

        contestant1 = contestants[seed1 - 1]
        contestant2 = contestants[seed2 - 1]

        matchup = Matchup.objects.create(
            user_bracket=user_bracket,
            stage=knockout_stage,
            position=position,
            contestant1=contestant1,
            contestant2=contestant2
        )
        matchups.append(matchup)

    return matchups
