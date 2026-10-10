"""Opt-in real PostgreSQL tests. Every inserted record is rolled back."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from backend.app.config import get_settings
from backend.app.product_services.ai_showdown_packet import build_packet
from backend.app.product_services.showdown_selection_records import SelectionDecisionStore, review_hash
from backend.app.product_services.showdown_selection_review import build_review
from backend.app.tests.product.test_showdown_selection_review import request_for, WEEK5, ROOT

pytestmark = pytest.mark.skipif(os.getenv("SHOWDOWN_REVIEW_DATABASE_TESTS") != "1", reason="Opt-in local database rollback test")


@pytest.fixture
def store_and_review():
    engine = create_engine(get_settings().sqlalchemy_database_uri)
    assert engine.url.host in {"localhost", "127.0.0.1", "::1"}
    source = json.loads((ROOT/"artifacts/showdown_selection_diversity_audit"/f"{WEEK5}-source.json").read_text())
    review = build_review(build_packet(source, ai_requested_entries=2))
    # Clearly synthetic future fixture, never persisted outside rollback.
    review["run_identity"]["kickoff_at"] = "2099-01-01T00:00:00+00:00"
    review["run_identity"]["frozen_source_hash_basis"] = "generation_snapshot"
    review["run_identity"]["frozen_source_evidence_hash"] = "TEST_ONLY_ROLLED_BACK"
    review["data_readiness"].update(status="READY", incomplete_evidence=False, non_production_override=False)
    with engine.connect() as c:
        tx = c.begin()
        class TransactionEngine:
            dialect = engine.dialect
            @contextmanager
            def connect(self): yield c
            @contextmanager
            def begin(self):
                with c.begin_nested(): yield c
        store = SelectionDecisionStore(TransactionEngine())
        try: yield store, review, c
        finally: tx.rollback()
    engine.dispose()


def test_store_retries_link_revisions_reject_branches_and_never_updates(store_and_review):
    from backend.app.product_services.showdown_selection_learning import SelectionLearningStore
    store, r, c = store_and_review
    assert store.history(WEEK5) == []
    assert SelectionLearningStore(store.engine).summary()["recorded_runs"] == 0
    req = request_for(r); req.idempotency_key = "TEST_ONLY_ROLLBACK_SELECTION_1"
    first = store.append_decision(r, req)
    assert store.append_decision(r, req) == first
    assert store.frozen_review(first["review_hash"]) == r
    changed = req.model_copy(update={"reasoning":"Different payload"})
    with pytest.raises(ValueError,match="Idempotency"):store.append_decision(r, changed)
    approved_req = request_for(r, "USER_APPROVED", first); approved_req.idempotency_key = "TEST_ONLY_ROLLBACK_SELECTION_2"
    second = store.append_decision(r, approved_req)
    assert SelectionLearningStore(store.engine).summary()["recorded_runs"] == 1
    assert second["previous_decision_id"] == first["decision_id"]
    assert store.history(WEEK5) == [first,second]
    branch = request_for(r, "SELECTED", first); branch.idempotency_key = "TEST_ONLY_ROLLBACK_BRANCH"
    with pytest.raises(ValueError, match="Stale"): store.append_decision(r,branch)
    for statement in ["UPDATE target.showdown_selection_decision SET status='PROPOSED' WHERE decision_id=:id",
                      "DELETE FROM target.showdown_selection_decision WHERE decision_id=:id",
                      "UPDATE target.showdown_selection_review SET review_json='{}' WHERE review_hash=:id"]:
        with pytest.raises(DBAPIError, match="append-only"):
            with c.begin_nested():
                c.execute(text(statement), {"id": r and (first["review_hash"] if "review_json" in statement else first["decision_id"])})
    assert store.history(WEEK5) == [first,second]


def test_store_never_reads_outcomes_during_prelock_decisions(store_and_review):
    from backend.app.product_services.showdown_selection_records import ExecutionRequest
    store,r,c=store_and_review
    req=request_for(r);req.idempotency_key="TEST_ONLY_ROLLBACK_NO_OUTCOMES"
    first=store.append_decision(r,req)
    approval=request_for(r,"USER_APPROVED",first);approval.idempotency_key="TEST_ONLY_ROLLBACK_APPROVED"
    second=store.append_decision(r,approval)
    execution=ExecutionRequest(idempotency_key="TEST_ONLY_ROLLBACK_EXECUTION", previous_decision_id=second["decision_id"],
                               learning_report_id="does-not-exist", entries=[{"contest_id":"1","entry_id":"1"},{"contest_id":"1","entry_id":"2"}])
    with pytest.raises(ValueError,match="postkickoff time"):
        store.append_execution(WEEK5,execution)
    assert len(store.history(WEEK5))==2
