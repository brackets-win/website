"""Admin delete-impact counts for confirmation dialogs."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.models import UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.delete_impact import bracket_delete_impact

User = get_user_model()


class DeleteImpactTests(TestCase):
    def test_bracket_lists_user_brackets_without_challenges(self):
        host = User.objects.create_user(username="host", password="x")
        bracket = create_bracket_with_structure("SINGLE_ELIM", "orphan", "X", 4, host)
        UserBracket.objects.create(user=host, bracket=bracket, is_master=False)

        related = {r["label"]: r["count"] for r in bracket_delete_impact(bracket)}
        self.assertNotIn("bracket challenges", related)
        self.assertGreaterEqual(related["user brackets"], 2)
