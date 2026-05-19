import re

from django.core.management.base import BaseCommand

from brackets.data.fwc26.teams_by_group import TEAM_IDENTIFIERS, TEAMS_BY_GROUP
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
from brackets.utils.third_place_structure import sync_third_place_structure

WC_IDENTIFIER = 'fifa-world-cup-2026'


def _team_identifier(display_name: str) -> str:
    if display_name in TEAM_IDENTIFIERS:
        return TEAM_IDENTIFIERS[display_name]
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', display_name.strip().lower())
    return slug.strip('-') or 'team'


class Command(BaseCommand):
    help = 'Seeds the 2026 FIFA World Cup bracket structure'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace-teams',
            action='store_true',
            help=(
                'Replace all teams on an existing fifa-world-cup-2026 bracket '
                '(keeps stages and metadata).'
            ),
        )

    def _load_third_place_combinations(self):
        return build_third_place_combinations_lookup(
            load_third_place_combinations_raw()
        )

    def _seed_teams(self, bracket: Bracket, user: User) -> int:
        """Create contestants and bracket entries in group order (seeds 1–48)."""
        BracketContestant.objects.filter(bracket=bracket).delete()
        seed = 1
        for code in sorted(TEAMS_BY_GROUP.keys()):
            for display_name in TEAMS_BY_GROUP[code]:
                ident = _team_identifier(display_name)
                cont, _ = Contestant.objects.get_or_create(
                    identifier=ident,
                    defaults={'name': display_name, 'created_by': user},
                )
                if cont.name != display_name:
                    cont.name = display_name
                    cont.save(update_fields=['name'])
                BracketContestant.objects.create(
                    bracket=bracket,
                    contestant=cont,
                    seed=seed,
                )
                seed += 1
        return seed - 1

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

        existing = Bracket.objects.filter(identifier=WC_IDENTIFIER).first()
        if existing and options['replace_teams']:
            user = existing.created_by
            n = self._seed_teams(existing, user)
            master_ub = existing.get_master_bracket()
            ensure_knockout_matchup_shell(master_ub)
            self.stdout.write(self.style.SUCCESS(
                f'Replaced {n} teams on {existing.identifier} (seeds follow groups A–L).'))
            return

        if existing:
            if existing.show_seeds:
                existing.show_seeds = False
                existing.save(update_fields=["show_seeds"])
            if not existing.has_third_place_match:
                existing.has_third_place_match = True
                existing.save(update_fields=["has_third_place_match"])
            sync_third_place_structure(existing)
            master_ub = existing.get_master_bracket()
            ensure_knockout_matchup_shell(master_ub)
            self.stdout.write(self.style.WARNING(
                'FIFA World Cup 2026 bracket already exists. Skipping. '
                'Use --replace-teams to refresh teams.'))
            return

        # Load third-place combinations from file
        third_place_combinations = self._load_third_place_combinations()
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(third_place_combinations)} third-place combinations'))

        # Create the bracket with metadata
        bracket = Bracket.objects.create(
            identifier=WC_IDENTIFIER,
            name='FIFA World Cup 2026',
            description='FIFA World Cup 2026 with 48 teams, 12 groups, and knockout rounds',
            created_by=user,
            show_seeds=False,
            has_third_place_match=True,
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
            f'Created bracket: {bracket.identifier} ({bracket.name})'))

        from brackets.data.fwc26.r32_tree_slots import (
            R32_TREE_SLOTS,
            build_r32_group_knockout_mapping,
        )
        from brackets.utils.group_knockout_fill import apply_knockout_fill_to_stage

        r32_mapping = build_r32_group_knockout_mapping()
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(R32_TREE_SLOTS)} R32 tree slots'))

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
                is_third_place=stage_data.get('is_third_place', False),
            )

            if 'custom_mapping' in stage_data:
                apply_knockout_fill_to_stage(
                    knockout_stage, stage_data['custom_mapping'])
                self.stdout.write(self.style.NOTICE(
                    f'  → Applied mapping knockout fill'))

            self.stdout.write(self.style.SUCCESS(
                f'Created stage: {knockout_stage.name}'))

        sync_third_place_structure(bracket)

        n_teams = self._seed_teams(bracket, user)
        master_ub = bracket.get_master_bracket()
        ensure_knockout_matchup_shell(master_ub)
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {n_teams} teams (groups A–L) and knockout shell on '
            f'master user bracket id={master_ub.id}'))

        self.stdout.write(self.style.SUCCESS(
            '\n✓ FIFA World Cup 2026 bracket seeded successfully!'))
        self.stdout.write(self.style.NOTICE(
            f'Total stages created: {bracket.stages.count()}'))
