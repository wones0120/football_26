"""One definition for production Large-GPP ranking and its audit explanations."""

LARGE_GPP_CANDIDATE_POLICY = {
    "score_field": "strategy_p90_score",
    "value_floor": {"default": 3.0, "WR": 3.4, "TE": 3.4, "DST": 0.0},
    "team_caps": {"WR": 4, "TE": 3, "RB": 2},
    "positions": {
        "QB": {"top": 14, "min_score": 17.0, "min_value": 3.0},
        "RB": {"top": 20, "min_score": 11.0, "min_value": 3.0},
        "WR": {"top": 34, "min_score": 10.0, "min_value": 3.4},
        "TE": {"top": 16, "min_score": 8.0, "min_value": 3.4},
        "DST": {"top": 12, "min_score": 0.0, "min_value": 0.0},
    },
    "qb_eligibility": "starting QB or explicit specialty role; positive mean and P90",
    "ranking": "context-adjusted marginal P90 descending with the existing pandas ranking; freeze the resulting input order for solver ties",
    "threshold_logic": "(score >= min_score OR ceiling_per_k >= min_value) AND position value floor",
    "darts": {"positions": ["WR", "TE"], "maximum_salary": 4500, "minimum_ceiling_per_k": 3.4},
    "safety_addbacks": ["best missing QB per team", "top two WR/TE per team",
                        "best opposing RB/WR/TE", "best WR/TE per team costing at most 4000"],
    "note": "Safety addbacks can exceed initial positional/team caps and thresholds; upstream eligibility remains enforced.",
}
