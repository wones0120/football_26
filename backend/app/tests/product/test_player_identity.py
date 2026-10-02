import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
        self.assertEqual(decision.reason, "unique_position")

    def test_name_only_match_remains_unresolved(self) -> None:
        decision = choose_identity(
            player_name="Josh Allen", team="BUF", position="QB",
            masters=[MasterIdentity(player_id="wrong-player", full_name="Josh Allen", team="ARI", position="OL")],
        )
        self.assertIsNone(decision.player_id)
        self.assertEqual(decision.reason, "insufficient_evidence")

    def test_matching_team_does_not_override_known_position_conflict(self) -> None:
        decision = choose_identity(
            player_name="Rocco Underwood", team="PHI", position="TE",
            masters=[MasterIdentity(
                player_id="long-snapper", full_name="Rocco Underwood",
                team="PHI", position="LS",
            )],
        )

        self.assertIsNone(decision.player_id)
        self.assertEqual(decision.reason, "insufficient_evidence")

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

    def test_projection_reconciliation_is_scoped_to_one_slate(self) -> None:
        from backend.app.api.product_routes import reconcile_slate_salary_identities
        from backend.app.product_schemas import StartingQBRequest

        session = MagicMock()
        with patch(
            "backend.app.api.product_routes.repair_salary_identities",
            return_value=SimpleNamespace(
                salary_rows_seen=2, salary_rows_resolved=1,
                salary_rows_quarantined=1,
            ),
        ) as repair:
            result = reconcile_slate_salary_identities(
                StartingQBRequest(season=2026, week=3, slate="SUNDAY_MAIN"),
                session=session,
            )
        repair.assert_called_once_with(
            session.get_bind.return_value, season=2026, week=3,
            slate="SUNDAY_MAIN",
        )
        self.assertEqual(result["salary_rows_quarantined"], 1)


if __name__ == "__main__":
    unittest.main()
