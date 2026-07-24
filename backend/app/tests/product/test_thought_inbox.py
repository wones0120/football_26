import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.app.product_services.beliefs import BeliefService
from backend.app.product_services.thought_inbox import (
    ThoughtInboxService,
    extract_candidate_beliefs,
    split_raw_thoughts,
)


class _MappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def one(self):
        return self.rows[0]

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _ThoughtConnection:
    def __init__(self):
        self.captures = []
        self.candidates = []
        self.decisions = []
        self.beliefs = []

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        now = datetime.now(timezone.utc)
        if "INSERT INTO target.raw_thought_capture" in sql:
            row = {
                key: params.get(key)
                for key in (
                    "capture_id", "context_type", "raw_text", "subject_label", "subject_id",
                    "season", "week", "slate", "contest_format", "objective",
                    "extraction_policy_id", "source",
                )
            }
            row.update({"notices_json": json.loads(params["notices_json"]), "created_at": now})
            self.captures.append(row)
            return _MappingsResult([row])
        if "INSERT INTO target.raw_thought_candidate" in sql and "candidate_decision" not in sql:
            row = {
                key: params.get(key)
                for key in (
                    "candidate_id", "capture_id", "ordinal", "scope_type", "subject_label",
                    "subject_id", "season", "week", "slate", "contest_format", "objective",
                    "direction", "strength", "confidence", "thought_text", "extraction_reason",
                )
            }
            row["created_at"] = now
            self.candidates.append(row)
            return _MappingsResult([row])
        if "INSERT INTO target.human_belief" in sql:
            row = {
                key: params.get(key)
                for key in (
                    "belief_version_id", "belief_id", "belief_version", "supersedes_version_id",
                    "operation", "status", "scope_type", "subject_label", "subject_id", "season",
                    "week", "slate", "contest_format", "objective", "direction", "strength",
                    "confidence", "thought_text", "evidence_text", "expires_at",
                    "is_retrospective", "source",
                )
            }
            row.update(
                {
                    "impact_status": "not_previewed",
                    "metadata_json": json.loads(params["metadata_json"]),
                    "created_at": now,
                }
            )
            self.beliefs.append(row)
            return _MappingsResult([row])
        if "INSERT INTO target.raw_thought_candidate_decision" in sql:
            row = {
                **params,
                "reviewed_payload_json": json.loads(params["reviewed_payload_json"]),
                "created_at": now,
            }
            self.decisions.append(row)
            return _MappingsResult([])
        if "FOR UPDATE OF c" in sql:
            candidate = next(
                (row for row in self.candidates if row["candidate_id"] == params["candidate_id"]),
                None,
            )
            if not candidate:
                return _MappingsResult([])
            capture = next(row for row in self.captures if row["capture_id"] == candidate["capture_id"])
            decision = next(
                (row for row in self.decisions if row["candidate_id"] == candidate["candidate_id"]),
                None,
            )
            return _MappingsResult(
                [
                    {
                        **candidate,
                        "extraction_policy_id": capture["extraction_policy_id"],
                        "decision_id": decision.get("decision_id") if decision else None,
                        "decision": decision.get("decision") if decision else None,
                    }
                ]
            )
        if "FROM target.raw_thought_candidate c" in sql:
            capture_ids = set(params["capture_ids"])
            rows = []
            for candidate in self.candidates:
                if candidate["capture_id"] not in capture_ids:
                    continue
                decision = next(
                    (row for row in self.decisions if row["candidate_id"] == candidate["candidate_id"]),
                    None,
                )
                rows.append(
                    {
                        **candidate,
                        "decision_id": decision.get("decision_id") if decision else None,
                        "decision": decision.get("decision") if decision else None,
                        "belief_id": decision.get("belief_id") if decision else None,
                        "belief_version_id": decision.get("belief_version_id") if decision else None,
                        "reviewed_payload_json": decision.get("reviewed_payload_json", {}) if decision else {},
                        "decided_at": decision.get("created_at") if decision else None,
                    }
                )
            return _MappingsResult(rows)
        if "FROM target.raw_thought_capture" in sql:
            return _MappingsResult(list(reversed(self.captures))[: params["limit"]])
        raise AssertionError(f"Unexpected SQL in test: {sql}")


class _ThoughtEngine:
    def __init__(self):
        self.url = "postgresql://test"
        self.connection = _ThoughtConnection()

    @contextmanager
    def begin(self):
        yield self.connection


class _BeliefService(BeliefService):
    def _ensure_schema(self):
        return None


class _PredictionsService:
    def fetch_predictions(self, **_kwargs):
        return [
            {"player_id": "player-josh-allen", "player_display_name": "Josh Allen"},
            {"player_id": "player-amon-ra", "player_display_name": "Amon-Ra St. Brown"},
        ]


class _ThoughtInboxService(ThoughtInboxService):
    def _ensure_schema(self):
        return None


class ThoughtInboxTests(unittest.TestCase):
    def test_sentence_split_preserves_player_abbreviation(self):
        rows, truncated = split_raw_thoughts(
            "I love Amon-Ra St. Brown this week. Fade the expensive chalk."
        )
        self.assertFalse(truncated)
        self.assertEqual(len(rows), 2)
        self.assertIn("St. Brown", rows[0])

    def test_extraction_matches_players_and_keeps_unmatched_slate_thoughts(self):
        rows, notices = extract_candidate_beliefs(
            "Love Josh Allen in concentrated builds.\nThe late games look overowned.",
            context_type="auto",
            season=2026,
            week=1,
            slate="sunday_main",
            contest_format="classic",
            objective="gpp",
            players=_PredictionsService().fetch_predictions(),
        )
        self.assertEqual(rows[0]["scope_type"], "player")
        self.assertEqual(rows[0]["subject_id"], "player-josh-allen")
        self.assertEqual(rows[0]["direction"], "prefer")
        self.assertEqual(rows[1]["scope_type"], "weekly")
        self.assertEqual(rows[1]["direction"], "fade")
        self.assertTrue(any("draft candidates only" in notice for notice in notices))

    def test_general_capture_becomes_playbook_candidate(self):
        rows, _ = extract_candidate_beliefs(
            "Prefer concentrated portfolios when my edge is narrow.",
            context_type="general",
            season=2026,
            week=1,
        )
        self.assertEqual(rows[0]["scope_type"], "global")
        self.assertIsNone(rows[0]["season"])

    def test_capture_accept_and_reject_are_persisted_with_lineage(self):
        engine = _ThoughtEngine()
        belief_service = _BeliefService(engine=engine)
        service = _ThoughtInboxService(
            engine=engine,
            belief_service=belief_service,
            predictions_service=_PredictionsService(),
        )
        capture = service.capture(
            {
                "context_type": "auto",
                "raw_text": "Love Josh Allen in GPPs.\nAvoid fragile chalk without volume.",
                "season": 2026,
                "week": 1,
                "slate": "SUNDAY_MAIN",
                "contest_format": "classic",
                "objective": "gpp",
            }
        )
        self.assertEqual(capture["raw_text"], "Love Josh Allen in GPPs.\nAvoid fragile chalk without volume.")
        self.assertEqual(len(capture["candidates"]), 2)

        candidate = capture["candidates"][0]
        accepted = service.decide(
            candidate["candidate_id"],
            "accepted",
            {
                "scope_type": candidate["scope_type"],
                "subject_label": candidate["subject_label"],
                "subject_id": candidate["subject_id"],
                "season": candidate["season"],
                "week": candidate["week"],
                "slate": candidate["slate"],
                "contest_format": candidate["contest_format"],
                "objective": candidate["objective"],
                "direction": candidate["direction"],
                "strength": 4,
                "confidence": 75,
                "thought_text": candidate["thought_text"],
                "is_retrospective": False,
            },
        )
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(len(engine.connection.beliefs), 1)
        self.assertEqual(engine.connection.beliefs[0]["source"], "raw_thought_inbox")
        self.assertEqual(
            engine.connection.beliefs[0]["metadata_json"]["raw_thought_capture_id"],
            capture["capture_id"],
        )

        with self.assertRaisesRegex(ValueError, "immutable decision"):
            service.decide(candidate["candidate_id"], "rejected")

        rejected = service.decide(capture["candidates"][1]["candidate_id"], "rejected")
        self.assertEqual(rejected["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
