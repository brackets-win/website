"""
Create a small single-elimination bracket with 8 seeded teams for local API/UI testing.

Usage:
  python manage.py seed_demo_bracket
  python manage.py seed_demo_bracket --password secret  # set demo user password
"""
from django.core.management.base import BaseCommand

from brackets.models import (
    BracketContestant,
    BracketTemplate,
    Contestant,
    User,
)
from brackets.utils.knockout_tree import ensure_full_knockout_matchups


class Command(BaseCommand):
    help = "Seed an 8-team single-elimination bracket and demo users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="demo",
            help="Password for demo and player accounts",
        )

    def handle(self, *args, **options):
        password = options["password"]

        system_user, _ = User.objects.get_or_create(
            username="system",
            defaults={"email": "system@brackets.win", "is_staff": True},
        )

        tpl, _ = BracketTemplate.objects.get_or_create(
            name="Single Elimination",
            defaults={
                "template_type": "SINGLE_ELIM",
                "description": "Pure knockout bracket.",
                "created_by": system_user,
                "is_system": True,
            },
        )

        owner, _ = User.objects.get_or_create(
            username="demo",
            defaults={"email": "demo@brackets.win"},
        )
        owner.set_password(password)
        owner.save()

        player, _ = User.objects.get_or_create(
            username="player",
            defaults={"email": "player@brackets.win"},
        )
        player.set_password(password)
        player.save()

        bracket = tpl.create_bracket(
            bracket_name="Demo 8-team bracket",
            number_of_contestants=8,
            created_by=owner,
        )

        team_names = [
            "Alpha",
            "Bravo",
            "Charlie",
            "Delta",
            "Echo",
            "Foxtrot",
            "Golf",
            "Hotel",
        ]
        for seed, name in enumerate(team_names, start=1):
            c, _ = Contestant.objects.get_or_create(
                name=name,
                defaults={"created_by": owner},
            )
            BracketContestant.objects.update_or_create(
                bracket=bracket,
                contestant=c,
                defaults={"seed": seed},
            )

        master = bracket.get_master_bracket()
        ensure_full_knockout_matchups(master)

        play_ub = bracket.userbracket_set.filter(user=player, is_master=False).first()
        if play_ub is None:
            from brackets.models import UserBracket

            play_ub = UserBracket.objects.create(
                user=player,
                bracket=bracket,
                is_master=False,
            )
        ensure_full_knockout_matchups(play_ub)

        self.stdout.write(
            self.style.SUCCESS(
                f"Bracket id={bracket.id} ready. "
                f"Log in as demo/{password} or player/{password}. "
                f"Master UB id={master.id}, player UB id={play_ub.id}."
            )
        )
