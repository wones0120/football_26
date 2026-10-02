"""Time-safe residual-ceiling diagnostics for the shadow projection path."""

import pandas as pd

from scripts.validate_forward_opportunity import prior_week_p90_proxy


def test_p90_proxy_uses_only_earlier_held_out_weeks():
    rows = []
    for week in (10, 11):
        for i in range(120):
            rows.append({"week": week, "position": "WR", "actual": 5.0 + i % 4,
                         "direct": 5.0, "hybrid": 5.5})
    frame = pd.DataFrame(rows)
    before = prior_week_p90_proxy(frame)
    changed = frame.copy()
    changed.loc[changed["week"].eq(11), "actual"] = 1000.0
    after = prior_week_p90_proxy(changed)
    assert before["direct"]["weeks"] == [11]
    assert after["direct"]["weeks"] == [11]
    assert (before["direct"]["calibration_rows"][0]["prior_residual_p90"]
            == after["direct"]["calibration_rows"][0]["prior_residual_p90"])
    assert before["direct"]["exceedance_rate"] != after["direct"]["exceedance_rate"]
    assert before["direct"]["n"] == 120
