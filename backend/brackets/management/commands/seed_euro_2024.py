import re

from django.core.management.base import BaseCommand

from brackets.data.euro24.teams_by_group import TEAM_IDENTIFIERS, TEAMS_BY_GROUP
from brackets.models import (
    Bracket,
    BracketContestant,
    Contestant,
    GroupStage,
    KnockoutStage,
    User,
)
from brackets.utils.euro24_regulations import (
    build_third_place_combinations_lookup,
    load_third_place_combinations_raw,
)
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell
from brackets.utils.third_place_structure import sync_third_place_structure

EURO_IDENTIFIER = 'uefa-euro-2024'


def _team_identifier(display_name: str) -> str:
    if display_name in TEAM_IDENTIFIERS:
        return TEAM_IDENTIFIERS[display_name]
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', display_name.strip().lower())
    return slug.strip('-') or 'team'


class Command(BaseCommand):
    help = 'Seeds the UEFA Euro 2024 bracket structure'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace-teams',
            action='store_true',
            help=(
                'Replace all teams on an existing uefa-euro-2024 bracket '
                '(keeps stages and metadata).'
            ),
        )

    def _load_third_place_combinations(self):
        return build_third_place_combinations_lookup(
            load_third_place_combinations_raw()
        )

    def _seed_teams(self, bracket: Bracket, user: User) -> int:
        """Create contestants and bracket entries in group order (seeds 1–24)."""
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
            'Starting UEFA Euro 2024 bracket seeding...'))

        user, created = User.objects.get_or_create(
            username='system',
            defaults={
                'email': 'system@brackets.win',
                'is_staff': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Created system user'))

        existing = Bracket.objects.filter(identifier=EURO_IDENTIFIER).first()
        if existing and options['replace_teams']:
            user = existing.created_by
            n = self._seed_teams(existing, user)
            master_ub = existing.get_master_bracket()
            ensure_knockout_matchup_shell(master_ub)
            self.stdout.write(self.style.SUCCESS(
                f'Replaced {n} teams on {existing.identifier} (seeds follow groups A–F).'))
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
                'UEFA Euro 2024 bracket already exists. Skipping. '
                'Use --replace-teams to refresh teams.'))
            return

        third_place_combinations = self._load_third_place_combinations()
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(third_place_combinations)} third-place combinations'))

        bracket = Bracket.objects.create(
            identifier=EURO_IDENTIFIER,
            name='UEFA Euro 2024',
            description=(
                'UEFA European Championship 2024 with 24 teams, 6 groups, '
                'and knockout rounds (16 of 24 advance)'
            ),
            created_by=user,
            show_seeds=False,
            has_third_place_match=True,
            points_champion=10,
            points_third_place_winner=3,
            metadata={
                'third_place_combinations': third_place_combinations,
                'tournament_type': 'euro_2024',
                'lookup_info': {
                    'type': 'bit_vector',
                    'description': 'Each group A-F is a bit position (A=0, B=1, ..., F=5)',
                    'example': 'teams_to_bits(["3C", "3D", "3E", "3F"]) = 0b111100 = 60',
                },
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f'Created bracket: {bracket.identifier} ({bracket.name})'))

        from brackets.data.euro24.r16_tree_slots import (
            R16_TREE_SLOTS,
            build_r16_group_knockout_mapping,
        )
        from brackets.utils.group_knockout_fill import apply_knockout_fill_to_stage

        r16_mapping = build_r16_group_knockout_mapping()
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(R16_TREE_SLOTS)} R16 tree slots'))

        group_stage = GroupStage.objects.create(
            bracket=bracket,
            name='Group Stage',
            order=1,
            stage_type='GROUP',
            number_of_contestants=24,
            contestants_advancing=16,
            is_random_draw=False,
            number_of_groups=6,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
            remaining_spots_strategy='HighestPlaceWithinGroup',
            points_per_win=3,
            points_per_tie=1,
            points_per_loss=0,
            points_per_exact_position=1,
            points_per_advancer=0,
            ties_allowed=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Created stage: {group_stage.name}'))

        knockout_stages = [
            {
                'name': 'Round of 16',
                'order': 2,
                'number_of_contestants': 16,
                'contestants_advancing': 8,
                'is_final': False,
                'points_per_correct_pick': 1,
                'custom_mapping': r16_mapping,
            },
            {
                'name': 'Quarter Final',
                'order': 3,
                'number_of_contestants': 8,
                'contestants_advancing': 4,
                'is_final': False,
                'points_per_correct_pick': 2,
            },
            {
                'name': 'Semi Final',
                'order': 4,
                'number_of_contestants': 4,
                'contestants_advancing': 2,
                'is_final': False,
                'points_per_correct_pick': 3,
            },
            {
                'name': 'Final',
                'order': 5,
                'number_of_contestants': 2,
                'contestants_advancing': 1,
                'is_final': True,
                'points_per_correct_pick': 5,
            },
        ]

        for stage_data in knockout_stages:
            pick_pts = stage_data.pop('points_per_correct_pick', 1)
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
                points_per_correct_pick=pick_pts,
            )

            if 'custom_mapping' in stage_data:
                apply_knockout_fill_to_stage(
                    knockout_stage, stage_data['custom_mapping'])
                self.stdout.write(self.style.NOTICE(
                    '  → Applied mapping knockout fill'))

            self.stdout.write(self.style.SUCCESS(
                f'Created stage: {knockout_stage.name}'))

        sync_third_place_structure(bracket)

        n_teams = self._seed_teams(bracket, user)
        master_ub = bracket.get_master_bracket()
        ensure_knockout_matchup_shell(master_ub)
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {n_teams} teams (groups A–F) and knockout shell on '
            f'master user bracket id={master_ub.id}'))

        self.stdout.write(self.style.SUCCESS(
            '\n✓ UEFA Euro 2024 bracket seeded successfully!'))
        self.stdout.write(self.style.NOTICE(
            f'Total stages created: {bracket.stages.count()}'))
