"""FlagCDN fallback for nation-tagged contestants."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from brackets.api.serializers import contestant_public
from brackets.models import BracketContestant, Contestant, ContestantTag, User, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell
from brackets.utils.top_four_picks import serialize_top_four_picks


class NationFlagFallbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="flags", password="x")
        self.nation = ContestantTag.objects.create(name="nation")

    def test_contestant_public_uses_flagcdn_for_nation_tag(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "flag-se4", "Flag SE4", 4, self.user
        )
        england = Contestant.objects.create(
            identifier="england",
            name="England",
            created_by=self.user,
        )
        england.tags.add(self.nation)
        bc = BracketContestant.objects.create(
            bracket=bracket, contestant=england, seed=1
        )

        payload = contestant_public(bc)
        self.assertEqual(payload["image_url"], "https://flagcdn.com/w40/gb-eng.png")

    def test_nation_flag_overrides_uploaded_photo(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "flag-photo", "Flag Photo", 4, self.user
        )
        england = Contestant.objects.create(
            identifier="england",
            name="England",
            created_by=self.user,
        )
        england.tags.add(self.nation)
        england.photo.save(
            "old.png",
            SimpleUploadedFile(
                "old.png",
                bytes.fromhex(
                    "89504e470d0a1a0a0000000d4948445200000001000000010806"
                    "0000001f15c4890000000a49444154789c6300010000050001"
                    "d90a2a0000000049454e44ae426082"
                ),
                content_type="image/png",
            ),
            save=True,
        )
        bc = BracketContestant.objects.create(
            bracket=bracket, contestant=england, seed=1
        )

        payload = contestant_public(bc)
        self.assertEqual(payload["image_url"], "https://flagcdn.com/w40/gb-eng.png")

    def test_contestant_public_does_not_fallback_without_nation_tag(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "flag-se4-2", "Flag SE4 2", 4, self.user
        )
        england = Contestant.objects.create(
            identifier="england",
            name="England",
            created_by=self.user,
        )
        bc = BracketContestant.objects.create(
            bracket=bracket, contestant=england, seed=1
        )

        payload = contestant_public(bc)
        self.assertIsNone(payload["image_url"])

    def test_nation_flag_ignores_stale_empty_tag_prefetch(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "flag-prefetch", "Flag Prefetch", 4, self.user
        )
        england = Contestant.objects.create(
            identifier="england",
            name="England",
            created_by=self.user,
        )
        england.tags.add(self.nation)
        bc = BracketContestant.objects.create(
            bracket=bracket, contestant=england, seed=1
        )
        bc.contestant._prefetched_objects_cache = {"tags": []}

        payload = contestant_public(bc)
        self.assertEqual(payload["image_url"], "https://flagcdn.com/w40/gb-eng.png")

    def test_top_four_serialization_uses_nation_flag_fallback(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "flag-top4", "Flag Top4", 4, self.user
        )
        contestants: list[Contestant] = []
        ids = ["england", "scotland", "wales", "united-states"]
        names = ["England", "Scotland", "Wales", "United States"]
        for ident, name in zip(ids, names, strict=True):
            c = Contestant.objects.create(
                identifier=ident,
                name=name,
                created_by=self.user,
            )
            c.tags.add(self.nation)
            contestants.append(c)

        teams = [
            BracketContestant.objects.create(
                bracket=bracket, contestant=c, seed=i + 1
            )
            for i, c in enumerate(contestants)
        ]
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        ensure_knockout_matchup_shell(ub)
        stages = list(bracket.stages.filter(stage_type="KNOCKOUT").order_by("order"))
        semi, final = stages
        sf1 = ub.matchup_set.get(stage=semi, position=1)
        sf2 = ub.matchup_set.get(stage=semi, position=2)
        fm = ub.matchup_set.get(stage=final, position=1)
        sf1.contestant1, sf1.contestant2, sf1.winner = teams[0], teams[1], teams[0]
        sf1.save()
        sf2.contestant1, sf2.contestant2, sf2.winner = teams[2], teams[3], teams[2]
        sf2.save()
        fm.contestant1, fm.contestant2, fm.winner = teams[0], teams[2], teams[0]
        fm.save()

        top4 = serialize_top_four_picks(ub)
        self.assertEqual(top4[0]["image_url"], "https://flagcdn.com/w40/gb-eng.png")
        self.assertEqual(top4[1]["image_url"], "https://flagcdn.com/w40/gb-wls.png")
