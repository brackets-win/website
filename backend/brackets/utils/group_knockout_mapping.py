"""
Utilities for mapping contestants from group stages to knockout stages.
"""


def create_knockout_matchups_from_groups(user_bracket, knockout_stage):
    """
    Create matchup objects for the first knockout stage based on group results.
    Uses default mapping or custom mapping from stage metadata.

    Args:
        user_bracket: UserBracket instance
        knockout_stage: The first KnockoutStage after groups

    Returns:
        List of created Matchup objects
    """
    from brackets.models import Matchup, Group

    bracket = user_bracket.bracket

    # Get the group stage (should be before this knockout stage)
    group_stages = bracket.stages.filter(
        stage_type='GROUP',
        order__lt=knockout_stage.order
    )

    if not group_stages.exists():
        raise ValueError("No group stage found before this knockout stage")

    group_stage = group_stages.last()
    groups = Group.objects.filter(stage=group_stage, bracket=bracket).order_by('order')
    num_groups = groups.count()

    # Determine mapping to use
    if knockout_stage.metadata and 'group_knockout_mapping' in knockout_stage.metadata:
        # Use custom mapping from metadata
        mapping_data = knockout_stage.metadata['group_knockout_mapping']
        mapping = []
        for pos_str, teams in mapping_data.items():
            position = int(pos_str)
            mapping.append((position, teams['team_a'], teams['team_b']))
    else:
        # Use default mapping
        mapping = generate_default_group_knockout_mapping(num_groups)

    # Create matchups based on mapping
    created_matchups = []

    for position, team_a_code, team_b_code in mapping:
        # Get contestants by position codes (may be None if groups not completed)
        contestant_a = get_contestant_by_position_code(bracket, team_a_code)
        contestant_b = get_contestant_by_position_code(bracket, team_b_code)

        # Create the matchup (contestants can be null initially)
        matchup = Matchup.objects.create(
            user_bracket=user_bracket,
            stage=knockout_stage,
            position=position,
            contestant1=contestant_a,
            contestant2=contestant_b
        )

        created_matchups.append(matchup)

    return created_matchups


def update_knockout_matchups_from_groups(user_bracket, knockout_stage):
    """
    Update existing knockout matchups with contestants based on finalized group results.
    Used when group stage is completed and positions are set.

    Args:
        user_bracket: UserBracket instance
        knockout_stage: The first KnockoutStage after groups

    Returns:
        Number of matchups updated
    """
    from brackets.models import Matchup, Group

    bracket = user_bracket.bracket

    # Get the mapping used when matchups were created
    if knockout_stage.metadata and 'group_knockout_mapping' in knockout_stage.metadata:
        mapping_data = knockout_stage.metadata['group_knockout_mapping']
        mapping = []
        for pos_str, teams in mapping_data.items():
            position = int(pos_str)
            mapping.append((position, teams['team_a'], teams['team_b']))
    else:
        gs = bracket.stages.filter(
            stage_type='GROUP',
            order__lt=knockout_stage.order,
        ).last()
        if gs is None:
            raise ValueError("No group stage found before this knockout stage")
        groups = Group.objects.filter(stage=gs, bracket=bracket).order_by('order')
        num_groups = groups.count()
        mapping = generate_default_group_knockout_mapping(num_groups)

    # Update matchups with actual contestants
    updated_count = 0

    for position, team_a_code, team_b_code in mapping:
        try:
            matchup = Matchup.objects.get(
                user_bracket=user_bracket,
                stage=knockout_stage,
                position=position
            )

            # Get contestants by position codes
            contestant_a = get_contestant_by_position_code(
                bracket, team_a_code)
            contestant_b = get_contestant_by_position_code(
                bracket, team_b_code)

            # Update if contestants are found
            if contestant_a or contestant_b:
                if contestant_a:
                    matchup.contestant1 = contestant_a
                if contestant_b:
                    matchup.contestant2 = contestant_b
                matchup.save()
                updated_count += 1

        except Matchup.DoesNotExist:
            continue

    return updated_count


def generate_default_group_knockout_mapping(num_groups):
    """
    Generate standard group-to-knockout first round mapping.
    Pattern: Alternate pairing, winners vs runners-up, same-group teams on opposite sides.

    Args:
        num_groups: Number of groups (must be even)

    Returns:
        List of tuples: [(position, team_a_code, team_b_code), ...]

    Example for 4 groups (A, B, C, D):
        [(1, 'A1', 'B2'), (2, 'C1', 'D2'), (3, 'B1', 'A2'), (4, 'D1', 'C2')]

    Example for 8 groups (A-H):
        [(1, 'A1', 'B2'), (2, 'C1', 'D2'), (3, 'E1', 'F2'), (4, 'G1', 'H2'),
         (5, 'B1', 'A2'), (6, 'D1', 'C2'), (7, 'F1', 'E2'), (8, 'H1', 'G2')]
    """
    if num_groups % 2 != 0:
        raise ValueError(
            "Number of groups must be even for standard knockout mapping")

    # Generate group codes (A, B, C, ... or 1, 2, 3, ...)
    # Using letters for now
    group_codes = [chr(65 + i) for i in range(num_groups)]  # A, B, C, ...

    mapping = []
    position = 1

    # First half: Winners vs Runners-up (alternating pairs)
    for i in range(0, num_groups, 2):
        group_a = group_codes[i]
        group_b = group_codes[i + 1]

        # Winner of A vs Runner-up of B
        mapping.append((position, f"{group_a}1", f"{group_b}2"))
        position += 1

    # Second half: Reverse - ensures same group teams on opposite sides
    for i in range(0, num_groups, 2):
        group_a = group_codes[i]
        group_b = group_codes[i + 1]

        # Winner of B vs Runner-up of A
        mapping.append((position, f"{group_b}1", f"{group_a}2"))
        position += 1

    return mapping


def set_custom_group_knockout_mapping(knockout_stage, mapping):
    """
    Store a custom group-to-knockout mapping in the stage metadata.

    Args:
        knockout_stage: KnockoutStage instance
        mapping: List of tuples [(position, team_a_code, team_b_code), ...]
                 Example: [(1, 'A1', 'B2'), (2, 'C1', '3D'), ...]
    """
    mapping_dict = {}
    for position, team_a, team_b in mapping:
        mapping_dict[str(position)] = {
            'team_a': team_a,
            'team_b': team_b
        }

    if not knockout_stage.metadata:
        knockout_stage.metadata = {}

    knockout_stage.metadata['group_knockout_mapping'] = mapping_dict
    knockout_stage.save()


def get_contestant_by_position_code(bracket, position_code):
    """
    Get a contestant by their group position code (e.g., "A1", "B2").

    Args:
        bracket: Bracket instance
        position_code: String like "A1", "B2", "3A", "3B" (third place from group A/B)

    Returns:
        Contestant instance or None
    """
    from brackets.models import Group, GroupMembership

    # Parse the code - could be "A1" or "3A" format
    # For now assume format is like "A1" (group code + position)
    if len(position_code) < 2:
        return None

    # Try parsing as letter+digit (e.g., "A1")
    if position_code[0].isalpha():
        group_code = position_code[0]
        try:
            position = int(position_code[1:])
        except ValueError:
            return None
    # Try parsing as digit+letter (e.g., "3A" for third place)
    elif position_code[0].isdigit():
        try:
            position = int(position_code[0])
            group_code = position_code[1:]
        except ValueError:
            return None
    else:
        return None

    try:
        # Find group by matching code (which is derived from order)
        groups = Group.objects.filter(bracket=bracket)
        group = None
        for g in groups.order_by('stage_id', 'order'):
            if g.code == group_code:
                group = g
                break

        if not group:
            return None

        membership = GroupMembership.objects.get(
            group=group,
            final_position=position
        )
        return membership.contestant
    except GroupMembership.DoesNotExist:
        return None
