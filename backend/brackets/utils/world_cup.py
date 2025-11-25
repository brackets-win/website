"""
Utilities for World Cup 2026 bracket logic.
"""


def teams_to_bit_vector(third_place_teams):
    """
    Convert a list of third-place teams to a bit vector for lookup.
    Each group A-L is represented by a bit position (A=0, B=1, ..., L=11).

    Args:
        third_place_teams: List of strings like ['3B', '3C', '3E', ...]

    Returns:
        Integer bit vector

    Example:
        >>> teams_to_bit_vector(['3B', '3C', '3E'])
        22  # Binary: 0b000000010110
    """
    group_to_bit = {
        '3A': 0, '3B': 1, '3C': 2, '3D': 3,
        '3E': 4, '3F': 5, '3G': 6, '3H': 7,
        '3I': 8, '3J': 9, '3K': 10, '3L': 11
    }

    bit_vector = 0
    for team in third_place_teams:
        if team in group_to_bit:
            bit_vector |= (1 << group_to_bit[team])

    return bit_vector


def get_round_of_32_matchups(bracket, third_place_teams):
    """
    Get the Round of 32 matchups for the given third-place teams that advanced.

    Args:
        bracket: Bracket instance (must be World Cup 2026)
        third_place_teams: List of 8 third-place teams that advanced (e.g., ['3B', '3C', ...])

    Returns:
        Dictionary of matchups: {'1A': '3C', '1B': '3J', ...}
        or None if bracket doesn't have the combinations data

    Example:
        >>> bracket = Bracket.objects.get(name='2026 FIFA World Cup')
        >>> teams = ['3B', '3E', '3H', '3I', '3J', '3K', '3L', '3C']
        >>> matchups = get_round_of_32_matchups(bracket, teams)
        >>> print(matchups['1A'])
        '3C'
    """
    if not bracket.metadata or 'third_place_combinations' not in bracket.metadata:
        return None

    # Convert teams to bit vector
    bit_vector = teams_to_bit_vector(third_place_teams)

    # Lookup in metadata
    combinations = bracket.metadata['third_place_combinations']
    combination = combinations.get(str(bit_vector))

    if combination:
        return combination['matchups']

    return None
