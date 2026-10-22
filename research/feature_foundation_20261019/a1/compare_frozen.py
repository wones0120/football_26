"""Reproduce the A1 synthetic, fixed-model parity check without fitting."""
import json
from pathlib import Path
import types

from backend.app.product_services.workload_count_forecast import forecast
from backend.app.tests.product.test_workload_count_forecast import MODEL, actors, history


def main():
    root = Path(__file__).parent
    old = types.ModuleType("backend.app.product_services._foundation_baseline")
    exec(compile((root / "workload_count_forecast.before.txt").read_text(),
                 "<frozen-before-a1>", "exec"), old.__dict__)
    cases = [("regular", history(), actors(), [])]
    h = history(); h.loc[h.player_master_id.eq("Aw"), "player_master_id"] = None
    cases.append(("unmapped", h, actors()[:2], []))
    h = history(); h.loc[h.player_master_id.eq("Ar"), "position"] = "FB"
    cases.append(("fullback", h, actors(), []))
    h = history().loc[lambda r: ~(r.player_master_id.eq("Aq") & r.period.eq(202507))]
    a = actors(); a[0]["current_role_evidence"] = dict(source_ids=[1], source_uri="native://role")
    proof = dict(kind="official_gamebook_not_active_v1", player_master_id="Aq", team="A", period=202507)
    cases.extend([("unknown-gap", h, a, []), ("verified-gap", h, a, [proof])])
    h = history(); h.loc[h.player_master_id.eq("Ar") & h.period.eq(202508), "team"] = "B"
    cases.append(("changed-team", h, actors(), []))
    h = history(); h.loc[h.player_master_id.eq("Ar") & h.period.eq(202508), "targets"] = None
    cases.append(("missing-channel", h, actors(), []))
    checks = []
    for label, h, a, gaps in cases:
        kwargs = dict(before_period=202509, starters={"A": "Aq"}, model=MODEL, verified_gaps=gaps)
        expected = old.forecast(h, a, **kwargs)
        current = forecast(h, a, **kwargs)
        current.pop("history_evidence")
        for row in current["players"]:
            row.pop("history_window_status", None)
        assert current == expected, label
        checks.append(dict(case=label, exact_numeric_and_existing_metadata_parity=True))
    print(json.dumps(dict(status="passed", cases=checks, fit_called=False,
        source="pre-edit source copied before A1; supplied fixed model; synthetic fixtures only"), indent=2))


if __name__ == "__main__":
    main()
