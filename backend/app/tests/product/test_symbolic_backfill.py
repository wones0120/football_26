import unittest
from unittest.mock import patch

from scripts.product.backfill_symbolic_learning import WeekState, backfill_week, validate_required_tables


class FakeConfig:
    rule_run_id = "new-run"


class FakeAgent:
    def __init__(self, state):
        self.engine = object()
        self.state = state
        self.run_calls = 0
        self.evaluate_calls = 0

    def run(self, season, week):
        self.run_calls += 1
        return None, [object(), object()], FakeConfig(), []

    def evaluate_learning(self, season, week, rule_run_id=None, slate=None):
        self.evaluate_calls += 1
        return {
            "learning_run_id": "learn-1",
            "status": "completed",
            "message": "ok",
            "rows_written": {
                "projection_snapshots": 10,
                "rule_evaluations": 3,
                "learning_runs": 1,
            },
        }


class FakeEngine:
    def __init__(self, table_names):
        self.table_names = table_names

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *_args, **_kwargs):
        class Row:
            def __init__(self, tablename):
                self.tablename = tablename

        class Result:
            def fetchall(result_self):
                return [Row(name) for name in self.table_names]

        return Result()


class SymbolicBackfillTests(unittest.TestCase):
    def test_preflight_reports_missing_required_tables(self):
        with self.assertRaisesRegex(RuntimeError, "nfl_weekly_data_with_scores"):
            validate_required_tables(FakeEngine(["player_expected_points"]))

    def test_skips_week_without_base_projections(self):
        agent = FakeAgent(WeekState(season=2025, week=1, actual_rows=10, projection_rows=0))
        with patch("scripts.product.backfill_symbolic_learning.load_week_state", return_value=agent.state):
            result = backfill_week(agent, 2025, 1)

        self.assertEqual(result.status, "skipped")
        self.assertEqual(agent.run_calls, 0)
        self.assertEqual(agent.evaluate_calls, 0)

    def test_runs_agent_when_adjusted_rows_are_missing(self):
        states = [
            WeekState(season=2025, week=1, actual_rows=10, projection_rows=10, adjusted_rows=0),
            WeekState(
                season=2025,
                week=1,
                actual_rows=10,
                projection_rows=10,
                adjusted_rows=10,
                latest_rule_run_id="new-run",
            ),
        ]
        agent = FakeAgent(states[0])
        with patch("scripts.product.backfill_symbolic_learning.load_week_state", side_effect=states):
            result = backfill_week(agent, 2025, 1)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.rule_run_id, "new-run")
        self.assertEqual(agent.run_calls, 1)
        self.assertEqual(agent.evaluate_calls, 1)

    def test_skips_existing_learning_run_unless_forced(self):
        state = WeekState(
            season=2025,
            week=1,
            actual_rows=10,
            projection_rows=10,
            adjusted_rows=10,
            learning_rows=1,
            latest_rule_run_id="existing-run",
        )
        agent = FakeAgent(state)
        with patch("scripts.product.backfill_symbolic_learning.load_week_state", return_value=state):
            result = backfill_week(agent, 2025, 1)

        self.assertEqual(result.status, "skipped")
        self.assertEqual(agent.evaluate_calls, 0)


if __name__ == "__main__":
    unittest.main()
