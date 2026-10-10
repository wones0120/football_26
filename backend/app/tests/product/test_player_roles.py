import pandas as pd
import pytest

from backend.app.product_services.player_roles import resolve_player_roles
from backend.app.product_services.canonical_projection_inputs import apply_pregame_projection_context
from backend.app.product_services.showdown_readiness import assess_showdown_inputs
from datetime import datetime, timezone


def context(pid, **facts):
    return dict(player_master_id=pid, source="official_team", source_uri="https://team.example/roster",
                evidence_json=facts)


@pytest.mark.parametrize("status", ["IR", "PUP", "NFI", "OUT", "INACTIVE", "SUSP"])
def test_unavailable_status_without_probability_excludes(status):
    pool = pd.DataFrame([dict(player_id="p", position="RB", salary=12000)])
    rows, _ = resolve_player_roles(pool, [dict(context("p"), injury_status=status)])
    assert rows.iloc[0].role_availability == "unavailable"
    assert not rows.iloc[0].role_optimizer_eligible


def test_rostered_active_and_depth_are_independent_of_salary():
    pool = pd.DataFrame([dict(player_id="p", position="WR", salary=12000)])
    rows, _ = resolve_player_roles(pool)
    assert rows.iloc[0].role_availability == "uncertain"
    assert rows.iloc[0].expected_depth_role == "uncertain"
    rows, _ = resolve_player_roles(pool, [context("p", roster_status="ACT", expected_depth_role="expected_starter")])
    assert rows.iloc[0].role_availability == "rostered"
    assert rows.iloc[0].expected_depth_role == "expected_starter"


def test_practice_squad_requires_sourced_game_activation():
    pool = pd.DataFrame([dict(player_id="p", position="WR")])
    rows, _ = resolve_player_roles(pool, [context("p", roster_status="PS")])
    assert not rows.iloc[0].role_optimizer_eligible
    rows, _ = resolve_player_roles(pool, [context("p", roster_status="PS", game_active=True)])
    assert rows.iloc[0].role_optimizer_eligible
    assert rows.iloc[0].role_availability == "active"


def test_final_inactive_overrides_active_roster_and_starter_depth():
    pool = pd.DataFrame([dict(player_id="p", position="WR", salary=12000)])
    rows, _ = resolve_player_roles(pool, [context("p", roster_status="ACT", game_active=False,
                                                 expected_depth_role="expected_starter")])
    assert rows.iloc[0].role_availability == "unavailable"
    assert rows.iloc[0].expected_depth_role == "expected_starter"
    assert not rows.iloc[0].role_optimizer_eligible


def test_backup_qb_requires_expected_package():
    pool = pd.DataFrame([dict(player_id="backup", position="QB", team_starting_qb_player_id="starter")])
    rows, _ = resolve_player_roles(pool)
    assert not rows.iloc[0].role_optimizer_eligible
    rows, _ = resolve_player_roles(pool, [context("backup", expected_qb_package=True)])
    assert rows.iloc[0].role_optimizer_eligible


def test_redistribution_only_to_supported_recipients_and_conserves_work():
    pool = pd.DataFrame([dict(player_id=pid, position="RB", recent_team="NO", salary=salary,
        player_games_history=3, snap_share_mean_3=.2, carry_share_mean_3=share,
        target_share_mean_3=share, carries_mean_3=share*20, targets_mean_3=share*10,
        team_carries_mean_3=20, team_targets_mean_3=10)
        for pid, salary, share in [("out", 10000, .5), ("promoted", 200, .3), ("rotation", 8000, .2)]])
    contexts = pd.DataFrame([
        dict(context("out", carry_redistribution_fraction=.8), injury_status="IR"),
        context("promoted", roster_status="ACT", expected_depth_role="expected_starter", redistribution_opportunities=["carry"]),
        context("rotation", roster_status="ACT", expected_depth_role="expected_backup")])
    rows, audit = apply_pregame_projection_context(pool, pregame_context=contexts)
    by_id = rows.set_index("player_id")
    assert by_id.loc["out", "carries_mean_3"] == 0
    assert by_id.loc["promoted", "carries_mean_3"] == pytest.approx(14)
    assert by_id.loc["rotation", "carries_mean_3"] == pytest.approx(4)
    carry = next(x for x in audit["allocations"] if x["opportunity"] == "carry")
    assert carry["unallocated_volume"] == pytest.approx(2)
    target = next(x for x in audit["allocations"] if x["opportunity"] == "target")
    assert target["redistributed_share"] == 0
    # Changing salaries cannot change any expected workload.
    pool["salary"] = [200, 12000, 200]
    swapped, _ = apply_pregame_projection_context(pool, pregame_context=contexts)
    assert swapped.carries_mean_3.tolist() == rows.carries_mean_3.tolist()


def test_unresolved_eligible_role_blocks_entry_readiness():
    rows, audit = resolve_player_roles(pd.DataFrame([dict(player_id="p", position="RB")]))
    result = assess_showdown_inputs([], {"strategy_runtime": {"current_slate_role_availability_audit": audit}}, datetime.now(timezone.utc))
    assert result["status"] == "BLOCKED"
    assert not result["entry_ready"]
