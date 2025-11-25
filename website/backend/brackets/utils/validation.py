"""
Validation utilities for bracket creation.
"""


def validate_seed_groups(bracket, number_of_groups):
    """
    Validate that number of seed groups evenly divides total contestants (for random_balanced).

    Returns tuple: (is_valid, error_message)
    """
    from brackets.models import BracketContestant

    total_contestants = BracketContestant.objects.filter(
        bracket=bracket).count()

    if total_contestants == 0:
        return False, "No contestants found in bracket"

    if number_of_groups <= 0:
        return False, "Number of seed groups must be positive"

    if number_of_groups > total_contestants:
        return False, f"Number of seed groups ({number_of_groups}) cannot exceed total contestants ({total_contestants})"

    if total_contestants % number_of_groups != 0:
        return False, f"Total contestants ({total_contestants}) must be evenly divisible by number of seed groups ({number_of_groups})"

    contestants_per_group = total_contestants // number_of_groups

    return True, f"{contestants_per_group} contestants per seed group"


def validate_seeds(bracket):
    """
    Validate that all contestants have unique consecutive seeds from 1 to n.

    Returns tuple: (is_valid, error_message)
    """
    from brackets.models import BracketContestant

    contestants = BracketContestant.objects.filter(
        bracket=bracket).order_by('seed')
    total = contestants.count()

    if total == 0:
        return False, "No contestants found in bracket"

    seeds = [c.seed for c in contestants]
    expected_seeds = list(range(1, total + 1))

    if seeds != expected_seeds:
        missing = set(expected_seeds) - set(seeds)
        duplicates = [s for s in seeds if seeds.count(s) > 1]

        if missing:
            return False, f"Missing seeds: {sorted(missing)}"
        if duplicates:
            return False, f"Duplicate seeds: {sorted(set(duplicates))}"

        return False, "Seeds are not consecutive from 1 to n"

    return True, None


def validate_seed_assignments(bracket):
    """
    Validate that all contestants have seed assignments (for random_balanced).

    Returns tuple: (is_valid, error_message)
    """
    from brackets.models import BracketContestant

    contestants = BracketContestant.objects.filter(bracket=bracket)

    if contestants.count() == 0:
        return False, "No contestants found in bracket"

    missing_seeds = contestants.filter(seed__isnull=True)

    if missing_seeds.exists():
        count = missing_seeds.count()
        return False, f"{count} contestant(s) missing seed assignment"

    return True, None


def get_seed_distribution(bracket):
    """
    Get distribution of contestants across seed values (for random_balanced).

    Returns dict: {seed: count} sorted by seed.
    """
    from brackets.models import BracketContestant
    from collections import Counter

    contestants = BracketContestant.objects.filter(bracket=bracket)
    seeds = [c.seed for c in contestants if c.seed is not None]

    return dict(sorted(Counter(seeds).items()))
