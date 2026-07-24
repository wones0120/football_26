import unittest

from Database.player_identity import (
    MasterIdentity,
    choose_identity,
    normalize_player_name,
    strip_name_suffix,
)


class PlayerIdentityTests(unittest.TestCase):
    def test_normalizes_punctuation_accents_and_suffixes(self) -> None:
        self.assertEqual(normalize_player_name("Da'Quan Félton III"), "da quan felton iii")
        self.assertEqual(strip_name_suffix("Da'Quan Félton III"), "da quan felton")

    def test_unique_suffix_match_is_repaired_despite_stale_team(self) -> None:
        masters = [
            MasterIdentity(
                player_id="aaron-jones",
                full_name="Aaron Jones",
                team="MIN",
                position="RB",
            )
        ]

        decision = choose_identity(
            player_name="Aaron Jones Sr.",
            team="CHI",
            position="RB",
            masters=masters,
        )

        self.assertEqual(decision.player_id, "aaron-jones")
        self.assertEqual(decision.reason, "unique_name")

    def test_position_breaks_suffix_duplicate_tie(self) -> None:
        masters = [
            MasterIdentity(
                player_id="salary-duplicate",
                full_name="Lew Nichols",
                position="FLEX",
            ),
            MasterIdentity(
                player_id="canonical-player",
                full_name="Lew Nichols III",
                team="PIT",
                position="RB",
            ),
        ]

        decision = choose_identity(
            player_name="Lew Nichols",
            team="GB",
            position="RB",
            masters=masters,
        )

        self.assertEqual(decision.player_id, "canonical-player")
        self.assertEqual(decision.reason, "unique_position")

    def test_punctuation_spacing_can_match_compact_master_name(self) -> None:
        decision = choose_identity(
            player_name="Da'Quan Felton",
            team="NYG",
            position="WR",
            masters=[
                MasterIdentity(
                    player_id="felton",
                    full_name="DaQuan Felton",
                    team="NYG",
                    position="WR",
                )
            ],
        )

        self.assertEqual(decision.player_id, "felton")

    def test_equally_supported_candidates_are_quarantined(self) -> None:
        masters = [
            MasterIdentity(player_id="one", full_name="Chris Smith", position="WR"),
            MasterIdentity(player_id="two", full_name="Chris Smith Jr.", position="WR"),
        ]

        decision = choose_identity(
            player_name="Chris Smith",
            team="BUF",
            position="WR",
            masters=masters,
        )

        self.assertIsNone(decision.player_id)
        self.assertEqual(decision.reason, "ambiguous")
        self.assertEqual(decision.candidate_player_ids, ("one", "two"))

    def test_absent_player_is_quarantined_without_new_identity(self) -> None:
        decision = choose_identity(
            player_name="Unknown Prospect",
            team="BUF",
            position="WR",
            masters=[],
        )

        self.assertIsNone(decision.player_id)
        self.assertEqual(decision.reason, "no_match")


if __name__ == "__main__":
    unittest.main()
