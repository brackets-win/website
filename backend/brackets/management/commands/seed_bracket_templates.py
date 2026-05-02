from django.core.management.base import BaseCommand
from brackets.models import BracketTemplate, User


class Command(BaseCommand):
    help = 'Seed common bracket templates'

    def handle(self, *args, **options):
        # Get or create system user
        system_user, _ = User.objects.get_or_create(
            username='system',
            defaults={'email': 'system@brackets.win', 'is_staff': True},
        )

        # 1. Group + Knockout Template
        group_knockout, created = BracketTemplate.objects.get_or_create(
            name='Group + Knockout',
            defaults={
                'template_type': 'GROUP_KNOCKOUT',
                'description': 'Classic tournament format with group stage (groups of 4, 2 qualify) followed by knockout rounds. Works with 32, 16, or 8 contestants.',
                'created_by': system_user,
                'is_system': True
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(
                f'Created template: {group_knockout.name}'))

        # 2. Single Elimination Template
        single_elim, created = BracketTemplate.objects.get_or_create(
            name='Single Elimination',
            defaults={
                'template_type': 'SINGLE_ELIM',
                'description': 'Pure knockout bracket. Works with 64, 32, 16, 8, or 4 contestants.',
                'created_by': system_user,
                'is_system': True
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(
                f'Created template: {single_elim.name}'))

        self.stdout.write(self.style.SUCCESS(
            'Bracket templates seeded successfully'))
