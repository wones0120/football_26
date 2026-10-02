from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).parents[4] / "scripts" / "validate_espn_projection_sanity.py"
SPEC = spec_from_file_location("validate_espn_projection_sanity", SCRIPT)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_parse_espn_tables_reads_source_id_and_values() -> None:
    html = """
    <table><thead><tr><th>Player</th><th>Rating</th><th>Team</th><th>Opp</th>
    <th>Pos</th><th>Proj.</th><th>$</th></tr></thead><tbody><tr>
    <td><a href="http://www.espn.com/nfl/player/_/id/123/tyler-shough">Tyler Shough</a></td>
    <td><b>Average</b></td><td>NO</td><td>@BAL</td><td>QB</td><td>16.6</td><td>$5,300</td>
    </tr></tbody></table>
    """

    assert MODULE.parse_espn_tables(html) == [{
        "espn_player_id": "123",
        "player": "Tyler Shough",
        "value_tier": "Average",
        "team": "NO",
        "opponent": "BAL",
        "position": "QB",
        "projection": 16.6,
        "salary": 5300,
        "source_href": "http://www.espn.com/nfl/player/_/id/123/tyler-shough",
    }]


def test_match_requires_deterministic_identity_fields() -> None:
    local = {
        "player_id": "canonical-1",
        "name": "Chris Olave",
        "player_team": "NO",
        "position": "WR",
        "salary": 7200,
    }
    by_id, by_key = MODULE.build_pool_indexes([local])
    espn = {
        "espn_player_id": "456",
        "player": "Chris Olave",
        "team": "NO",
        "position": "WR",
        "salary": 7200,
    }

    matched, method, reason = MODULE.match_espn_row(
        espn, by_id=by_id, by_key=by_key, aliases={}
    )

    assert matched == local
    assert method == "normalized_name_team_position_salary"
    assert reason is None

    wrong_salary = {**espn, "salary": 7100}
    matched, method, reason = MODULE.match_espn_row(
        wrong_salary, by_id=by_id, by_key=by_key, aliases={}
    )
    assert matched is None
    assert method == "unmatched"
    assert "exact name/team/position/salary" in reason


def test_candidate_exposure_uses_frozen_pool_denominator() -> None:
    counts, total = MODULE.candidate_exposures({
        "all_candidates": [
            {"player_ids": ["a", "b"]},
            {"player_ids": ["a", "c"]},
        ]
    })

    assert total == 2
    assert counts["a"] == 2
    assert counts["b"] == 1
