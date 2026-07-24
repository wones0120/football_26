import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.app.product_services.beliefs import BeliefService, _normalize_create


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


class _BeliefConnection:
    def __init__(self):
        self.rows = []

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
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
                    "created_at": datetime.now(timezone.utc),
                }
            )
            self.rows.append(row)
            return _MappingsResult([row])
        if "FOR UPDATE" in sql:
            rows = [row for row in self.rows if row["belief_id"] == params["belief_id"]]
            rows.sort(key=lambda row: row["belief_version"], reverse=True)
            return _MappingsResult(rows[:1])
        if "WITH versions AS" in sql:
            latest = {}
            for row in self.rows:
                current = latest.get(row["belief_id"])
                if current is None or row["belief_version"] > current["belief_version"]:
                    latest[row["belief_id"]] = row
            rows = list(latest.values())
            if "status = 'active'" in sql:
                rows = [row for row in rows if row["status"] == "active"]
            if "season" in params:
                rows = [row for row in rows if row["season"] in {None, params["season"]}]
            if "week" in params:
                rows = [row for row in rows if row["week"] in {None, params["week"]}]
            if "slate" in params:
                rows = [
                    row for row in rows
                    if row["slate"] is None or row["slate"].upper() == params["slate"].upper()
                ]
            rows.sort(key=lambda row: row["created_at"], reverse=True)
            return _MappingsResult(rows[: params["limit"]])
        raise AssertionError(f"Unexpected SQL in test: {sql}")


class _BeliefEngine:
    def __init__(self):
        self.url = "postgresql://test"
        self.connection = _BeliefConnection()

    @contextmanager
    def begin(self):
        yield self.connection


class _TestBeliefService(BeliefService):
    def _ensure_schema(self):
        return None


class BeliefServiceTests(unittest.TestCase):
    def test_scope_contract_requires_context(self):
        with self.assertRaisesRegex(ValueError, "weekly beliefs require a season"):
            _normalize_create(
                {
                    "scope_type": "weekly",
                    "thought_text": "This slate rewards concentrated passing stacks.",
                }
            )
        with self.assertRaisesRegex(ValueError, "player beliefs require a subject_label"):
            _normalize_create(
                {
                    "scope_type": "player",
                    "thought_text": "The role is larger than the market expects.",
                }
            )

    def test_create_revise_deactivate_and_restore_are_immutable_versions(self):
        engine = _BeliefEngine()
        service = _TestBeliefService(engine=engine)

        created = service.create(
            {
                "scope_type": "weekly",
                "season": 2025,
                "week": 11,
                "slate": "sunday_main",
                "contest_format": "classic",
                "objective": "gpp",
                "direction": "prefer",
                "strength": 4,
                "confidence": 72,
                "thought_text": "Prioritize correlated passing attacks in condensed games.",
                "evidence_text": "The field is spreading ownership across too many games.",
                "is_retrospective": True,
            }
        )
        revised = service.revise(
            created["belief_id"],
            {
                "confidence": 81,
                "thought_text": "Prioritize double stacks in the two most condensed games.",
            },
        )
        inactive = service.set_status(created["belief_id"], "inactive")
        restored = service.set_status(created["belief_id"], "active")

        self.assertEqual(created["belief_version"], 1)
        self.assertEqual(revised["belief_version"], 2)
        self.assertEqual(revised["operation"], "revised")
        self.assertEqual(inactive["operation"], "deactivated")
        self.assertEqual(restored["operation"], "reactivated")
        self.assertEqual(restored["belief_version"], 4)
        self.assertEqual(len(engine.connection.rows), 4)
        self.assertEqual(
            engine.connection.rows[0]["thought_text"],
            "Prioritize correlated passing attacks in condensed games.",
        )

        memory = service.list(season=2025, week=11, slate="SUNDAY_MAIN")
        self.assertEqual(memory["summary"]["active"], 1)
        self.assertEqual(memory["summary"]["total"], 1)
        self.assertEqual(memory["rows"][0]["belief_version"], 4)
        self.assertTrue(memory["rows"][0]["is_retrospective"])
        self.assertEqual(memory["rows"][0]["impact_status"], "not_previewed")


if __name__ == "__main__":
    unittest.main()
