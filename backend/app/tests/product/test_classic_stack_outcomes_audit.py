from scripts.audit_classic_stack_outcomes import construction


def test_stack_audit_classifies_bring_back_by_canonical_team_context() -> None:
    players = [
        {"position": "QB", "team": "DET", "opponent": "NYJ"},
        {"position": "WR", "team": "DET"},
        {"position": "TE", "team": "DET"},
        {"position": "RB", "team": "NYJ"},
        {"position": "WR", "team": "BAL"},
    ]
    family, qb = construction(players)
    assert family == "QB+2+bring-back"
    assert qb["team"] == "DET"
