"""Synthetic persisted preparation lookup for solver/readiness unit tests.

The real preparation queue and validation are covered in test_slate_preparation.
These tests supply saved lineage and prohibit source collectors during a solve.
"""
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def prepared_optimizer(service, *, return_value=None, side_effect=None):
    result = side_effect() if side_effect else return_value
    evidence = {"action": "prepare", "ownership_run_id": result["ownership_run_id"],
                "data_cutoff_at": result["data_cutoff_at"].isoformat(),
                "source_refresh": result["report"]}
    original = service.run_job

    def run(**kwargs):
        kwargs["params"] = {**kwargs.get("params", {}), "prepared_input_job_id": "prepared-fixture"}
        kwargs["projection_run_id"] = result["projection_run_id"]
        return original(**kwargs)

    with patch.object(service, "run_job", side_effect=run), \
         patch("backend.app.product_services.slate_preparation.validate_prepared_optimizer", return_value=evidence) as lookup, \
         patch("backend.app.product_services.analyst_preparation.bind_saved_preparation"), \
         patch("backend.app.product_services.classic_data_readiness.refresh_live_sources") as classic, \
         patch("backend.app.product_services.showdown_data_readiness.refresh_live_sources") as showdown:
        yield lookup
        classic.assert_not_called()
        showdown.assert_not_called()
