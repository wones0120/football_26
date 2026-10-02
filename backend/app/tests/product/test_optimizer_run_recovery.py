from datetime import datetime, timezone

from backend.app.api.product_routes import run_optimizer
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerJob


class _OptimizerServiceStub:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    def run_job(self, **kwargs) -> OptimizerJob:
        self.kwargs = kwargs
        now = datetime.now(timezone.utc)
        return OptimizerJob(
            job_id=kwargs["optimizer_run_id"],
            status="completed",
            created_at=now,
            updated_at=now,
            season=kwargs["season"],
            week=kwargs["week"],
            slate=kwargs["slate"],
            strategy=kwargs["strategy"],
            contest_format=kwargs["contest_format"],
            objective=kwargs["objective"],
            params={**kwargs["params"], "strategy_config": {}},
            projection_run_id=kwargs["projection_run_id"],
            results=[],
        )


def test_optimizer_route_preserves_client_supplied_run_id_for_timeout_recovery():
    service = _OptimizerServiceStub()
    request = OptimizerRunRequest.model_validate({
        "season": 2026,
        "week": 2,
        "slate": "SUNDAY_MAIN",
        "strategy": "classic_small_field_gpp",
        "optimizer_run_id": "browser-generated-run-id",
        "contest_format": "classic",
        "objective": "gpp",
        "projection_run_id": "projection-run-id",
        "params": {"num_lineups": 2},
    })

    response = run_optimizer(request, service=service)

    assert service.kwargs is not None
    assert service.kwargs["optimizer_run_id"] == "browser-generated-run-id"
    assert response.job_id == "browser-generated-run-id"
