"""Explicit, nonbinding selection-review endpoints; no optimizer writes."""
from datetime import UTC, datetime
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ..product_dependencies import get_optimizer_service
from ..product_services.optimizer import OptimizerService
from ..product_services.ai_showdown_packet import build_packet, build_retrospective_packet
from ..product_services.showdown_selection_review import build_review, review_comparison, review_markdown
from ..product_services.showdown_selection_records import DecisionRequest, ExecutionRequest, SelectionDecisionStore, review_hash
from ..product_services.showdown_selection_learning import SelectionLearningStore
from ..product_services.target_schema import TargetSchemaCompatibilityError

router = APIRouter()


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_hash: str
    candidate_ids: list[str] = Field(min_length=2, max_length=2)


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learning_report_id: str


def run_review(job_id: str, service: OptimizerService) -> dict:
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Optimizer run not found")
    source = {key: getattr(job, key) for key in ("status", "season", "week", "slate", "strategy", "contest_format",
                                                  "created_at", "data_cutoff_at", "projection_run_id", "params", "results")}
    source["job_id"] = job.job_id
    source["player_pool"] = (job.params.get("strategy_runtime") or {}).get("player_pool")
    # Historical display can explain a late run, but cannot create live decisions.
    try:
        try:
            packet = build_packet(source, ai_requested_entries=2)
        except ValueError as exc:
            if "Run was created at or after kickoff" not in str(exc):
                raise
            packet = build_retrospective_packet(source, ai_requested_entries=2)
        review = build_review(packet)
        return review
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def store_call(call):
    try:
        return call()
    except TargetSchemaCompatibilityError as exc:
        raise HTTPException(status_code=503, detail=f"Selection research schema unavailable. Apply migration 0047_showdown_selection_review.sql. {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/optimizer/results/{job_id}/selection-review")
def selection_review(job_id: str, service: OptimizerService = Depends(get_optimizer_service)) -> dict:
    store = SelectionDecisionStore(service.engine)
    records = store_call(lambda: store.history(job_id))
    if records:
        # Continue the content-addressed saved review, never silently regenerate it.
        review = store_call(lambda: store.frozen_review(records[-1]["review_hash"]))
    else:
        review = run_review(job_id, service)
    cutoff = datetime.fromisoformat(review["run_identity"]["kickoff_at"])
    can_record = (datetime.now(UTC) < cutoff and review["data_readiness"].get("status") == "READY"
                  and not review["data_readiness"].get("incomplete_evidence")
                  and not review["data_readiness"].get("non_production_override")
                  and review["run_identity"]["timing_status"] == "prelock_saved_run")
    return {"review": review, "review_hash": review_hash(review), "decision_history": records,
            "selection_status": records[-1]["status"] if records else "AI_SELECTION_UNKNOWN",
            "can_record_prelock": bool(can_record), "server_time": datetime.now(UTC).isoformat()}


@router.post("/optimizer/results/{job_id}/selection-review/compare")
def selection_comparison(job_id: str, request: ComparisonRequest, service: OptimizerService = Depends(get_optimizer_service)) -> dict:
    value = selection_review(job_id, service)
    if request.review_hash != value["review_hash"]:
        raise HTTPException(status_code=422, detail="Review hash mismatch; reopen the exact frozen run")
    return store_call(lambda: review_comparison(value["review"], request.candidate_ids))


@router.post("/optimizer/results/{job_id}/selection-review/decisions")
def record_selection(job_id: str, request: DecisionRequest, service: OptimizerService = Depends(get_optimizer_service)) -> dict:
    store = SelectionDecisionStore(service.engine)
    records = store_call(lambda: store.history(job_id))
    review = store_call(lambda: store.frozen_review(records[-1]["review_hash"])) if records else run_review(job_id, service)
    return store_call(lambda: store.append_decision(review, request))


@router.post("/optimizer/results/{job_id}/selection-review/execution")
def confirm_selection_execution(job_id: str, request: ExecutionRequest, service: OptimizerService = Depends(get_optimizer_service)) -> dict:
    return store_call(lambda: SelectionDecisionStore(service.engine).append_execution(job_id, request))


@router.get("/optimizer/results/{job_id}/selection-review/download")
def download_selection_review(job_id: str, format: str = Query("json", pattern="^(json|md)$"),
                              service: OptimizerService = Depends(get_optimizer_service)) -> Response:
    value = selection_review(job_id, service)
    # The prelock artifact intentionally excludes history/execution/outcomes.
    safe = {"review": value["review"], "review_hash": value["review_hash"]}
    content = json.dumps(safe, indent=2) if format == "json" else review_markdown(value["review"])
    return Response(content=content, media_type="application/json" if format == "json" else "text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="SHOWDOWN_SELECTION_REVIEW_{job_id}.{format}"'})


@router.get("/optimizer/results/{job_id}/selection-review/decisions/download")
def download_selection_decisions(job_id: str, service: OptimizerService = Depends(get_optimizer_service)) -> Response:
    records = store_call(lambda: SelectionDecisionStore(service.engine).history(job_id))
    return Response(content=json.dumps({"selection_status": records[-1]["status"] if records else "AI_SELECTION_UNKNOWN", "decisions": records}, indent=2),
                    media_type="application/json", headers={"Content-Disposition": f'attachment; filename="SHOWDOWN_SELECTION_DECISIONS_{job_id}.json"'})


@router.post("/learning/research/showdown-selection-review/{decision_id}/evaluate")
def evaluate_selection(decision_id: str, request: EvaluationRequest, service: OptimizerService = Depends(get_optimizer_service)) -> dict:
    return store_call(lambda: SelectionLearningStore(service.engine).evaluate(decision_id, request.learning_report_id))


@router.get("/learning/research/showdown-selection-review")
def selection_research_summary(season: int | None = Query(None, ge=2000), service: OptimizerService = Depends(get_optimizer_service)) -> dict:
    return store_call(lambda: SelectionLearningStore(service.engine).summary(season))
