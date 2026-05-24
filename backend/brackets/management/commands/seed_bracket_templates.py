from django.core.management.base import BaseCommand

from brackets.models import BracketTemplate, User

SYSTEM_TEMPLATES = [
    (
        '32 Group & Knockout',
        'GROUP_KNOCKOUT',
        32,
        'Group stage (groups of 4, top 2 advance) plus knockout rounds through the final.',
    ),
    (
        '16 Group & Knockout',
        'GROUP_KNOCKOUT',
        16,
        'Smaller group stage format with knockout rounds through the final.',
    ),
    (
        '64 Single-Elimination Knockout',
        'SINGLE_ELIM',
        64,
        'Six knockout rounds from the round of 64 through the final.',
    ),
    (
        '32 Single-Elimination Knockout',
        'SINGLE_ELIM',
        32,
        'Five knockout rounds from the round of 32 through the final.',
    ),
    (
        '16 Single-Elimination Knockout',
        'SINGLE_ELIM',
        16,
        'Four knockout rounds from the round of 16 through the final.',
    ),
    (
        '8 Single-Elimination Knockout',
        'SINGLE_ELIM',
        8,
        'Quarterfinals, semifinals, and final.',
    ),
    (
        '4 Single-Elimination Knockout',
        'SINGLE_ELIM',
        4,
        'Semifinals and final.',
    ),
]

LEGACY_NAMES = ('Group + Knockout', 'Single Elimination')


class Command(BaseCommand):
    help = 'Seed bracket structure templates for admin bracket creation'

    def handle(self, *args, **options):
        system_user, _ = User.objects.get_or_create(
            username='system',
            defaults={'email': 'system@brackets.win', 'is_staff': True},
        )

        removed, _ = BracketTemplate.objects.filter(
            is_system=True,
            name__in=LEGACY_NAMES,
        ).delete()
        if removed:
            self.stdout.write(
                self.style.WARNING(f'Removed {removed} legacy template(s)')
            )

        created_count = 0
        for name, template_type, default_n, description in SYSTEM_TEMPLATES:
            _, created = BracketTemplate.objects.update_or_create(
                name=name,
                defaults={
                    'template_type': template_type,
                    'default_number_of_contestants': default_n,
                    'description': description,
                    'created_by': system_user,
                    'is_system': True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created template: {name}'))
            else:
                self.stdout.write(f'Updated template: {name}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Bracket templates ready ({created_count} new, '
                f'{len(SYSTEM_TEMPLATES)} total)'
            )
        )
