import unittest

from Database.player_identity import MasterIdentity
from scripts.product.audit_salary_identities import evaluate_unresolved_rows


class SalaryIdentityAuditTests(unittest.TestCase):
    def test_accepts_only_reproduced_ambiguous_and_no_match_quarantines(self) -> None:
        masters = [
            MasterIdentity(player_id="one", full_name="Chris Smith", position="WR"),
            MasterIdentity(player_id="two", full_name="Chris Smith Jr.", position="WR"),
        ]
        rows = [
            {
                "source_record_key": "ambiguous-row",
                "player_name": "Chris Smith",
                "team": "BUF",
                "position": "WR",
                "status": "open",
                "reason_code": "ambiguous",
            },
            {
                "source_record_key": "no-match-row",
                "player_name": "Unknown Prospect",
                "team": "BUF",
                "position": "WR",
                "status": "open",
                "reason_code": "no_match",
            },
        ]

        report = evaluate_unresolved_rows(masters, rows)

        self.assertEqual(report["accepted_quarantine_rows"], 2)
        self.assertEqual(
            report["accepted_quarantine_reasons"],
            {"ambiguous": 1, "no_match": 1},
        )
        self.assertEqual(report["deterministic_match_count"], 0)
        self.assertEqual(report["reason_mismatch_count"], 0)
        self.assertEqual(report["untracked_count"], 0)
        self.assertEqual(report["unaccepted_quarantine_count"], 0)

    def test_surfaces_new_deterministic_match(self) -> None:
        masters = [MasterIdentity(player_id="known", full_name="Known Player", position="RB")]
        rows = [
            {
                "source_record_key": "stale-quarantine",
                "player_name": "Known Player",
                "team": "BUF",
                "position": "RB",
                "status": "open",
                "reason_code": "no_match",
            }
        ]

        report = evaluate_unresolved_rows(masters, rows)

        self.assertEqual(report["deterministic_match_count"], 1)
        self.assertEqual(report["deterministic_match_sample"][0]["player_id"], "known")
        self.assertEqual(report["accepted_quarantine_rows"], 0)

    def test_rejects_untracked_or_unaccepted_reason(self) -> None:
        rows = [
            {
                "source_record_key": "untracked",
                "player_name": "Unknown Prospect",
                "team": "BUF",
                "position": "WR",
                "status": None,
                "reason_code": None,
            },
            {
                "source_record_key": "missing-name",
                "player_name": "",
                "team": "BUF",
                "position": "WR",
                "status": "open",
                "reason_code": "missing_name",
            },
        ]

        report = evaluate_unresolved_rows([], rows)

        self.assertEqual(report["untracked_count"], 1)
        self.assertEqual(report["reason_mismatch_count"], 1)
        self.assertEqual(report["unaccepted_quarantine_count"], 2)
        self.assertEqual(report["accepted_quarantine_rows"], 0)


if __name__ == "__main__":
    unittest.main()
