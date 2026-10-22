from datetime import UTC, datetime
from unittest.mock import Mock

from backend.app.product_services.optimizer import OptimizerJob, OptimizerService


def job(status="running", persisted=True):
    now = datetime.now(UTC)
    return OptimizerJob(job_id="saved-worker-run", status=status, created_at=now, updated_at=now,
        season=2026, week=6, slate="SUNDAY_NIGHT", strategy="showdown_gpp_portfolio_v3",
        contest_format="showdown", objective="gpp", params={}, lineage_persisted=persisted,
        results=[[{"name": "saved player"}]] if status == "completed" else None)


def test_worker_completion_replaces_an_api_cached_running_snapshot():
    service = OptimizerService(connection_string="sqlite:///:memory:")
    running, completed = job(), job("completed")
    service._cache_job(running)
    service._load_persisted_job = Mock(return_value=completed)
    assert service.get_job(running.job_id) is completed
    service._load_persisted_job.assert_called_once_with(running.job_id)


def test_local_running_and_completed_cache_do_not_reload_or_disappear():
    service = OptimizerService(connection_string="sqlite:///:memory:")
    service._load_persisted_job = Mock(return_value=None)
    for cached in [job(persisted=False), job("completed")]:
        service._cache_job(cached)
        assert service.get_job(cached.job_id) is cached
    service._load_persisted_job.assert_not_called()
    running = job()
    service._cache_job(running)
    assert service.get_job(running.job_id) is running  # A transient read failure keeps the known receipt.
