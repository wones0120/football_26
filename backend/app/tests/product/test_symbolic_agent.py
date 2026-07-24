import unittest
from unittest.mock import MagicMock

import pandas as pd

from backend.app.product_services.agent import (
    AgentTrace,
    NewsMatchupAgent,
    SymbolicRule,
    _metric_summary,
    _rule_recommendation,
)


class InMemoryAgent(NewsMatchupAgent):
    def __init__(self, rules, projections, injuries=None, matchups=None):
        super().__init__(engine=object())
        self.rules = rules
        self.projections = projections
        self.injuries = injuries if injuries is not None else pd.DataFrame()
        self.matchups = matchups if matchups is not None else pd.DataFrame()
        self.persisted_runs = []

    def _load_rules(self, enabled_only: bool = True):
        if enabled_only:
            return [rule for rule in self.rules if rule.enabled]
        return self.rules

    def _load_injuries(self, season: int, week: int) -> pd.DataFrame:
        return self.injuries.copy()

    def _load_matchups(self, season: int, week: int) -> pd.DataFrame:
        return self.matchups.copy()

    def _load_projections(
        self,
        season: int,
        week: int,
        slate: str | None = None,
        projection_run_id: str | None = None,
    ) -> pd.DataFrame:
        df = self.projections.copy()
        if slate and "slate" in df.columns:
            df = df[(df["slate"] == slate) | df["slate"].isna()].copy()
        if projection_run_id and "projection_run_id" in df.columns:
            df = df[df["projection_run_id"] == projection_run_id].copy()
        df["orig_mean"] = pd.to_numeric(df["predicted_mean"], errors="coerce").fillna(0.0)
        df["orig_p90"] = pd.to_numeric(df["predicted_p90"], errors="coerce").fillna(0.0)
        return df

    def _persist_rule_run(self, **kwargs) -> None:
        self.persisted_runs.append(kwargs)


def _rule(rule_id, rule_type, condition, action, enabled=True, priority=10):
    return SymbolicRule(
        rule_id=rule_id,
        rule_name=rule_id.replace("_", " ").title(),
        rule_type=rule_type,
        enabled=enabled,
        priority=priority,
        version=1,
        condition_json=condition,
        action_json=action,
    )


def _projection(player_id="p1", position="WR", team="BUF"):
    return pd.DataFrame(
        [
            {
                "player_id": player_id,
                "player_display_name": "Test Player",
                "position": position,
                "recent_team": team,
                "opponent_team": "MIA",
                "predicted_mean": 10.0,
                "predicted_p90": 20.0,
            }
        ]
    )


class SymbolicAgentRuleTests(unittest.TestCase):
    def test_injury_downgrade_records_non_destructive_run(self):
        rules = [
            _rule(
                "injury_negative",
                "injury",
                {"indicators": ["Q"], "match_mode": "prefix_or_exact"},
                {"mean_multiplier": 0.9, "p90_multiplier": 0.8, "reason": "Questionable"},
            )
        ]
        injuries = pd.DataFrame(
            [{"player_id": "p1", "injury_indicator": "Q", "first_name": "Test", "last_name": "Player", "team": "BUF"}]
        )
        agent = InMemoryAgent(rules, _projection(), injuries=injuries)

        proj, adjustments, config, traces = agent.run(2025, 1)

        self.assertEqual(len(adjustments), 1)
        self.assertEqual(len(traces), 1)
        self.assertEqual(config.rule_run_id, traces[0].rule_run_id)
        self.assertAlmostEqual(float(proj.iloc[0]["predicted_mean"]), 9.0)
        self.assertAlmostEqual(float(proj.iloc[0]["predicted_p90"]), 16.0)
        self.assertAlmostEqual(float(agent.projections.iloc[0]["predicted_mean"]), 10.0)
        self.assertEqual(agent.persisted_runs[0]["projections_adjusted"], 1)

    def test_positive_injury_note_applies_boost(self):
        rules = [
            _rule(
                "injury_positive",
                "injury",
                {"indicators": ["ACTIVE"], "match_mode": "prefix_or_exact"},
                {"mean_multiplier": 1.05, "p90_multiplier": 1.05, "reason": "Active"},
            )
        ]
        injuries = pd.DataFrame(
            [{"player_id": "p1", "injury_indicator": "ACTIVE", "first_name": "Test", "last_name": "Player", "team": "BUF"}]
        )
        agent = InMemoryAgent(rules, _projection(), injuries=injuries)

        proj, adjustments, _, _ = agent.run(2025, 1)

        self.assertEqual(len(adjustments), 1)
        self.assertAlmostEqual(float(proj.iloc[0]["predicted_mean"]), 10.5)

    def test_matchup_pass_boost_and_slow_penalty_are_position_aware(self):
        rules = [
            _rule(
                "pass_boost",
                "matchup",
                {"positions": ["QB", "WR", "TE"], "pass_funnel_gt": 0.0, "or_pace_gt": 120.0},
                {"mean_multiplier": 1.1, "p90_multiplier": 1.1, "reason": "Pass boost"},
            ),
            _rule(
                "slow_penalty",
                "matchup",
                {"positions": ["WR", "TE"], "pass_funnel_lt": 0.0, "pace_lt": 110.0},
                {"mean_multiplier": 0.5, "p90_multiplier": 0.5, "reason": "Slow"},
                priority=20,
            ),
        ]
        matchups = pd.DataFrame(
            [
                {
                    "recent_team": "BUF",
                    "opponent_team": "MIA",
                    "pass_funnel": 1.0,
                    "off_plays_per_g": 60.0,
                    "def_plays_allowed_per_g": 62.0,
                }
            ]
        )
        agent = InMemoryAgent(rules, _projection(position="WR"), matchups=matchups)

        proj, adjustments, _, traces = agent.run(2025, 1)

        self.assertEqual(len(adjustments), 1)
        self.assertEqual([trace.rule_id for trace in traces], ["pass_boost"])
        self.assertAlmostEqual(float(proj.iloc[0]["predicted_mean"]), 11.0)

    def test_disabled_rules_do_not_apply(self):
        rules = [
            _rule(
                "disabled_injury",
                "injury",
                {"indicators": ["Q"], "match_mode": "prefix_or_exact"},
                {"mean_multiplier": 0.1, "p90_multiplier": 0.1, "reason": "Disabled"},
                enabled=False,
            )
        ]
        injuries = pd.DataFrame(
            [{"player_id": "p1", "injury_indicator": "Q", "first_name": "Test", "last_name": "Player", "team": "BUF"}]
        )
        agent = InMemoryAgent(rules, _projection(), injuries=injuries)

        proj, adjustments, _, traces = agent.run(2025, 1)

        self.assertEqual(adjustments, [])
        self.assertEqual(traces, [])
        self.assertAlmostEqual(float(proj.iloc[0]["predicted_mean"]), 10.0)

    def test_reruns_create_distinct_rule_run_ids(self):
        rules = [
            _rule(
                "injury_negative",
                "injury",
                {"indicators": ["Q"], "match_mode": "prefix_or_exact"},
                {"mean_multiplier": 0.9, "p90_multiplier": 0.9, "reason": "Questionable"},
            )
        ]
        injuries = pd.DataFrame(
            [{"player_id": "p1", "injury_indicator": "Q", "first_name": "Test", "last_name": "Player", "team": "BUF"}]
        )
        agent = InMemoryAgent(rules, _projection(), injuries=injuries)

        _, _, config_one, _ = agent.run(2025, 1)
        _, _, config_two, _ = agent.run(2025, 1)

        self.assertNotEqual(config_one.rule_run_id, config_two.rule_run_id)
        self.assertEqual(len(agent.persisted_runs), 2)

    def test_run_carries_projection_and_slate_lineage_to_persistence(self):
        rules = [
            _rule(
                "injury_negative",
                "injury",
                {"indicators": ["Q"], "match_mode": "prefix_or_exact"},
                {"mean_multiplier": 0.9, "p90_multiplier": 0.9, "reason": "Questionable"},
            )
        ]
        injuries = pd.DataFrame(
            [{"player_id": "p1", "injury_indicator": "Q", "first_name": "Test", "last_name": "Player", "team": "BUF"}]
        )
        projections = _projection()
        projections["projection_run_id"] = "projection-run-1"
        projections["slate"] = "SUNDAY_MAIN"
        agent = InMemoryAgent(rules, projections, injuries=injuries)

        _, _, config, _ = agent.run(2025, 1, slate="SUNDAY_MAIN")

        self.assertEqual(config.projection_run_id, "projection-run-1")
        self.assertEqual(agent.persisted_runs[0]["projection_run_id"], "projection-run-1")
        self.assertEqual(agent.persisted_runs[0]["slate"], "SUNDAY_MAIN")

    def test_target_symbolic_persistence_links_projection_run(self):
        agent = NewsMatchupAgent.__new__(NewsMatchupAgent)
        agent.engine = MagicMock()
        connection = agent.engine.begin.return_value.__enter__.return_value
        trace = AgentTrace(
            rule_run_id="rule-run-1",
            player_id="p1",
            rule_id="injury_negative",
            rule_name="Injury Negative",
            reason="Questionable",
            mean_before=10.0,
            mean_after=9.0,
            p90_before=20.0,
            p90_after=18.0,
            mean_multiplier=0.9,
            p90_multiplier=0.9,
        )
        projections = _projection()
        projections["orig_mean"] = 10.0
        projections["orig_p90"] = 20.0
        projections["predicted_mean"] = 9.0
        projections["predicted_p90"] = 18.0
        projections["game_id"] = pd.NA
        projections["slate"] = pd.NA

        persisted = agent._persist_target_symbolic_run(
            rule_run_id="rule-run-1",
            projection_run_id="projection-run-1",
            season=2025,
            week=1,
            slate="SUNDAY_MAIN",
            rules_loaded=1,
            rules_applied=1,
            traces=[trace],
            proj=projections,
            adjust_reasons={"p1": ["Questionable"]},
            rule_versions={"injury_negative": 2},
        )

        self.assertTrue(persisted)
        run_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], dict)
            and call.args[1].get("rule_run_id") == "rule-run-1"
            and "rules_loaded" in call.args[1]
        )
        self.assertEqual(run_payload["projection_run_id"], "projection-run-1")
        application_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], list)
            and call.args[1]
            and "rule_version" in call.args[1][0]
        )
        self.assertEqual(application_payload[0]["rule_version"], 2)
        adjusted_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], list)
            and call.args[1]
            and "adjusted_mean" in call.args[1][0]
        )
        self.assertEqual(adjusted_payload[0]["game_id"], "2025_01_unknown_p1")
        self.assertEqual(adjusted_payload[0]["slate_id"], "SUNDAY_MAIN")

    def test_metric_summary_reports_improvement(self):
        df = pd.DataFrame(
            [
                {"actual_points": 9.0, "base": 5.0, "adjusted": 8.0},
                {"actual_points": 10.0, "base": 12.0, "adjusted": 11.0},
            ]
        )

        summary = _metric_summary(df, "base", "adjusted")

        self.assertEqual(summary["rows"], 2)
        self.assertEqual(summary["improved_rows"], 2)
        self.assertGreater(summary["mae_delta"], 0)

    def test_rule_recommendation_flags_consistent_underperformance(self):
        recommendation = _rule_recommendation(
            {
                "rule_id": "slow_penalty",
                "rows": 30,
                "mae_delta": -0.75,
                "hit_rate": 0.3,
            }
        )

        self.assertEqual(recommendation["action"], "review_or_disable")
        self.assertEqual(recommendation["severity"], "warning")

    def test_rule_recommendation_requires_more_data_for_small_samples(self):
        recommendation = _rule_recommendation(
            {
                "rule_id": "injury_positive",
                "rows": 4,
                "mae_delta": 1.5,
                "hit_rate": 1.0,
            }
        )

        self.assertEqual(recommendation["action"], "collect_more_data")


if __name__ == "__main__":
    unittest.main()
