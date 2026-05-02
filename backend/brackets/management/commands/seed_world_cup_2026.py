from django.core.management.base import BaseCommand
from brackets.models import (
    Bracket,
    BracketContestant,
    Contestant,
    GroupStage,
    KnockoutStage,
    User,
)
from brackets.utils.fwc26_regulations import (
    build_third_place_combinations_lookup,
    load_third_place_combinations_raw,
)
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell


class Command(BaseCommand):
    help = 'Seeds the 2026 FIFA World Cup bracket structure'

    def _load_third_place_combinations(self):
        return build_third_place_combinations_lookup(
            load_third_place_combinations_raw()
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(
            'Starting 2026 World Cup bracket seeding...'))

        # Get or create a system user for bracket creation
        user, created = User.objects.get_or_create(
            username='system',
            defaults={
                'email': 'system@brackets.win',
                'is_staff': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Created system user'))

        # Check if bracket already exists
        if Bracket.objects.filter(name='2026 FIFA World Cup').exists():
            self.stdout.write(self.style.WARNING(
                '2026 FIFA World Cup bracket already exists. Skipping.'))
            return

        # Load third-place combinations from file
        third_place_combinations = self._load_third_place_combinations()
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(third_place_combinations)} third-place combinations'))

        # Create the bracket with metadata
        bracket = Bracket.objects.create(
            name='2026 FIFA World Cup',
            description='The 2026 FIFA World Cup with 48 teams, 12 groups, and knockout rounds',
            created_by=user,
            metadata={
                'third_place_combinations': third_place_combinations,
                'tournament_type': 'world_cup_2026',
                'lookup_info': {
                    'type': 'bit_vector',
                    'description': 'Each group A-L is a bit position (A=0, B=1, ..., L=11)',
                    'example': 'teams_to_bits(["3B", "3C"]) = 0b110 = 6'
                }
            }
        )
        self.stdout.write(self.style.SUCCESS(
            f'Created bracket: {bracket.name}'))

        from brackets.utils.group_knockout_mapping import set_custom_group_knockout_mapping

        # World Cup 2026 Round of 32 mapping (from FIFA regulations)
        # Codes like '1A'/'A1' = group positions; '3A'..='3L' = third-place qualifier slots.
        r32_mapping = [
            (1, 'A2', 'B2'),             # M73: Runner-up A vs Runner-up B
            (2, 'E1', '3E'),
            (3, 'F1', 'C2'),             # M75: Winner F vs Runner-up C
            (4, 'C1', 'F2'),             # M76: Winner C vs Runner-up F
            (5, 'I1', '3I'),
            (6, 'E2', 'I2'),             # M78: Runner-up E vs Runner-up I
            (7, 'A1', '3A'),
            (8, 'L1', '3L'),
            (9, 'D1', '3D'),
            (10, 'G1', '3G'),
            (11, 'K2', 'L2'),            # M83: Runner-up K vs Runner-up L
            (12, 'H1', 'J2'),            # M84: Winner H vs Runner-up J
            (13, 'B1', '3B'),
            (14, 'J1', 'H2'),            # M86: Winner J vs Runner-up H
            (15, 'K1', '3K'),
            (16, 'D2', 'G2'),            # M88: Runner-up D vs Runner-up G
        ]
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(r32_mapping)} Round of 32 matchups'))

        # Create Group Stage
        group_stage = GroupStage.objects.create(
            bracket=bracket,
            name='Group Stage',
            order=1,
            stage_type='GROUP',
            number_of_contestants=48,
            contestants_advancing=32,
            is_random_draw=False,
            number_of_groups=12,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
            remaining_spots_strategy='HighestPlaceWithinGroup',
            points_per_win=3,
            points_per_tie=1,
            points_per_loss=0,
            ties_allowed=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Created stage: {group_stage.name}'))

        # Create Knockout Stages
        knockout_stages = [
            {
                'name': 'Round of 32',
                'order': 2,
                'number_of_contestants': 32,
                'contestants_advancing': 16,
                'is_final': False,
                'custom_mapping': r32_mapping,
            },
            {
                'name': 'Round of 16',
                'order': 3,
                'number_of_contestants': 16,
                'contestants_advancing': 8,
                'is_final': False,
            },
            {
                'name': 'Quarter Final',
                'order': 4,
                'number_of_contestants': 8,
                'contestants_advancing': 4,
                'is_final': False,
            },
            {
                'name': 'Semi Final',
                'order': 5,
                'number_of_contestants': 4,
                'contestants_advancing': 2,
                'is_final': False,
            },
            {
                'name': 'Final',
                'order': 6,
                'number_of_contestants': 2,
                'contestants_advancing': 1,
                'is_final': True,
            },
        ]

        for stage_data in knockout_stages:
            knockout_stage = KnockoutStage.objects.create(
                bracket=bracket,
                name=stage_data['name'],
                order=stage_data['order'],
                stage_type='KNOCKOUT',
                number_of_contestants=stage_data['number_of_contestants'],
                contestants_advancing=stage_data['contestants_advancing'],
                is_random_draw=False,
                number_of_legs=1,
                has_extra_time=True,
                has_penalty_shootout=True,
                is_final=stage_data['is_final'],
            )

            if 'custom_mapping' in stage_data:
                set_custom_group_knockout_mapping(
                    knockout_stage, stage_data['custom_mapping'])
                self.stdout.write(self.style.NOTICE(
                    f'  → Applied custom group-to-knockout mapping'))

            self.stdout.write(self.style.SUCCESS(
                f'Created stage: {knockout_stage.name}'))

        # Placeholder teams (4 per group × 12 groups) + empty knockout matchups on master
        for i in range(48):
            label = f'Team {i + 1:02d}'
            cont, _ = Contestant.objects.get_or_create(
                name=label,
                defaults={'created_by': user},
            )
            BracketContestant.objects.update_or_create(
                bracket=bracket,
                contestant=cont,
                defaults={'seed': i + 1},
            )

        master_ub = bracket.get_master_bracket()
        ensure_knockout_matchup_shell(master_ub)
        self.stdout.write(self.style.SUCCESS(
            f'Seeded 48 teams and knockout shell on master user bracket id={master_ub.id}'))

        self.stdout.write(self.style.SUCCESS(
            '\n✓ 2026 FIFA World Cup bracket seeded successfully!'))
        self.stdout.write(self.style.NOTICE(
            f'Total stages created: {bracket.stages.count()}'))
