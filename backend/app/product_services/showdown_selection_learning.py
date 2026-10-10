"""Postgame shadow evaluation. Never imported by the prelock review builder."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json

from sqlalchemy import text

from .ai_showdown_packet import _date, digest
from .optimizer_effectiveness import candidate_signature
from .showdown_selection_records import SelectionDecisionStore, review_hash, verify_record
from .showdown_selection_review import POLICY


def valid_prelock_decision(record: dict) -> bool:
    identity = record["run_identity"]
    # Keep the known late-generated Sunday slate descriptive even if a legacy
    # importer were to label its chronology differently in the future.
    excluded = identity["season"] == 2026 and identity["week"] == 4 and identity["slate"] == "SUNDAY_NIGHT"
    return (not excluded and identity["timing_status"] == "prelock_saved_run"
            and record["status"] != "PROPOSED"
            and _date(identity["created_at"]) < _date(identity["kickoff_at"])
            and _date(record.get("selection_frozen_at") or record["decision_timestamp"]) < _date(identity["kickoff_at"]))


def evaluate_decision(record: dict, review: dict, report: dict, candidate_outcomes: list[dict], *, now: datetime) -> dict:
    verify_record(record)
    if review_hash(review) != record["review_hash"]:
        raise ValueError("Frozen review hash mismatch")
    identity = record["run_identity"]
    if now.tzinfo is None or now < _date(identity["kickoff_at"]):
        raise ValueError("Outcome joining is forbidden before kickoff")
    if record["status"] == "PROPOSED":
        raise ValueError("Select a pair before joining outcomes; a proposal is not a final decision")
    if any(report.get(k) != identity[k] for k in ("season", "week", "slate")):
        raise ValueError("Learning report belongs to another slate")
    by_signature = defaultdict(set)
    for row in candidate_outcomes:
        sig = candidate_signature(row, "showdown")
        points = (row.get("postgame") or {}).get("actual_points")
        if sig is not None and isinstance(points, (int, float)):
            by_signature[sig].add(float(points))
    scores = {c["candidate_id"]: (next(iter(by_signature[sig])) if len(by_signature.get(sig, set())) == 1 else None)
              for c in review["candidates"] for sig in [candidate_signature(c, "showdown")]}
    selected = record["proposed_candidate_ids"]
    selected_scores = [scores[cid] for cid in selected]
    considered = record["attention"]["explicitly_considered_ids"]
    finalists = record["attention"]["finalists_automatically_surfaced"]
    outsiders = record["attention"]["ceiling_outsiders_automatically_surfaced"]
    all_complete = all(v is not None for v in scores.values())
    selected_complete = all(v is not None for v in selected_scores)
    best = lambda ids: max((scores[cid] for cid in ids if scores[cid] is not None), default=None)
    best_selected = best(selected) if selected_complete else None
    execution = record.get("execution")
    entered_points = [{"contest_id": e["contest_id"], "entry_id": e["entry_id"], "entry_points": e.get("entry_points")}
                      for e in report.get("entries", []) if execution and
                      (str(e["contest_id"]), str(e["entry_id"])) in
                      {(x["contest_id"], x["entry_id"]) for x in execution["entries"]}]
    entered_complete = len(entered_points) == 2 and all(e["entry_points"] is not None for e in entered_points)
    result = {"contract_id": "showdown_selection_outcome_v1", "protocol": POLICY,
              "decision_id": record["decision_id"], "decision_hash": record["record_hash"],
              "review_hash": record["review_hash"], "learning_report_id": report["report_id"],
              "learning_evidence_hash": report["evidence_hash"], "evaluated_at": now.isoformat(),
              "chronologically_valid": valid_prelock_decision(record),
              "excluded_reason": None if valid_prelock_decision(record) else "not_a_valid_prelock_decision_or_excluded_week4_sunday",
              "candidate_scores_complete": all_complete, "selected_candidate_scores": dict(zip(selected, selected_scores)),
              "eligible_candidates_scored": sum(v is not None for v in scores.values()),
              "best_eligible_actual": best(scores), "best_considered_actual": best(considered),
              "best_finalist_actual": best(finalists), "best_ceiling_outsider_actual": best(outsiders),
              "best_chosen_candidate_actual": best_selected,
              "best_entry_performance": max(e["entry_points"] for e in entered_points) if entered_complete else None,
              "final_selection_regret": best(scores) - best_selected if all_complete and selected_complete else None,
              "attention_potential_gap": best(scores) - best(set(finalists + outsiders)) if all_complete else None,
              "entry_execution_fidelity": execution["matches_approved_pair"] if execution else None,
              "actual_entered_pair": execution["entries"] if execution else None,
              "actual_entered_points": entered_points,
              "overlap_bucket": str(record["proposed_pair"]["shared_player_count"]),
              "review_workload": {"surfaced": len(finalists) + len(outsiders),
                                  "other_displayed": len(record["attention"]["other_displayed_candidate_ids"]),
                                  "explicitly_considered": len(considered)},
              "limitations": ["No thresholds are tuned from outcomes. Each slate is one observation.",
                              "Missing/conflicting actuals remain unavailable; exact regret requires all eligible scores."]}
    result["outcome_hash"] = digest(result)
    return result


class SelectionLearningStore:
    def __init__(self, engine):
        self.engine = engine
        self.decisions = SelectionDecisionStore(engine)

    def evaluate(self, decision_id: str, report_id: str) -> dict:
        self.decisions.ensure_schema()
        with self.engine.begin() as c:
            record = c.execute(text("SELECT record_json FROM target.showdown_selection_decision WHERE decision_id=:id"), {"id": decision_id}).scalar()
            if not record:
                raise ValueError("Immutable decision not found; legacy AI picks remain AI_SELECTION_UNKNOWN")
            verify_record(record)
            now = c.execute(text("SELECT clock_timestamp()")).scalar_one()
            # Check chronology BEFORE opening any outcome table.
            if now < _date(record["run_identity"]["kickoff_at"]) or record["status"] == "PROPOSED":
                raise ValueError("A frozen selection and postkickoff timestamp are required before reading outcomes")
            existing = c.execute(text("SELECT outcome_json FROM target.showdown_selection_outcome WHERE decision_id=:id AND learning_report_id=:report"), {"id": decision_id, "report": report_id}).scalar()
            if existing:
                return existing
            review = self.decisions.frozen_review(record["review_hash"])
            report = c.execute(text("SELECT report_json FROM target.slate_learning_report WHERE report_id=:id"), {"id": report_id}).scalar()
            if not report:
                raise ValueError("Frozen learning report not found; import results and generate the existing learning report first")
            rows = c.execute(text("""
                SELECT coalesce(detail.detail_json->'candidates', run.value->'candidates', '[]'::jsonb) AS candidates,
                       run.value->'candidate_detail'->>'evidence_hash' AS expected_detail_hash,
                       detail.detail_json
                FROM target.slate_learning_report report
                CROSS JOIN LATERAL jsonb_array_elements(report.report_json->'optimizer_effectiveness'->'runs') run(value)
                LEFT JOIN target.slate_learning_run_detail detail ON detail.detail_id=run.value->'candidate_detail'->>'detail_id'
                WHERE report.report_id=:report AND run.value->>'optimizer_run_id'=:run
            """), {"report": report_id, "run": record["run_identity"]["optimizer_run_id"]}).mappings().all()
            if not rows:
                raise ValueError("Learning report has no frozen candidate outcomes for this run")
            outcomes = []
            for row in rows:
                if row["expected_detail_hash"] and digest(row["detail_json"]) != row["expected_detail_hash"]:
                    raise ValueError("Frozen learning candidate evidence is missing or changed")
                outcomes.extend(row["candidates"])
            result = evaluate_decision(record, review, report, outcomes, now=now)
            c.execute(text("""INSERT INTO target.showdown_selection_outcome (outcome_id, decision_id, learning_report_id, outcome_json)
                VALUES (:id, :decision, :report, CAST(:outcome AS JSONB)) ON CONFLICT (decision_id, learning_report_id) DO NOTHING"""),
                      {"id": "showdown-outcome-" + result["outcome_hash"], "decision": decision_id,
                       "report": report_id, "outcome": json.dumps(result)})
            return c.execute(text("SELECT outcome_json FROM target.showdown_selection_outcome WHERE decision_id=:id AND learning_report_id=:report"), {"id": decision_id, "report": report_id}).scalar_one()

    def summary(self, season: int | None = None) -> dict:
        self.decisions.ensure_schema()
        with self.engine.connect() as c:
            rows = c.execute(text("""
                SELECT decision.record_json, outcome.outcome_json
                FROM (SELECT DISTINCT ON (optimizer_run_id) * FROM target.showdown_selection_decision
                      ORDER BY optimizer_run_id, CASE WHEN status='PROPOSED' THEN 1 ELSE 0 END, revision DESC) decision
                LEFT JOIN LATERAL (SELECT outcome_json FROM target.showdown_selection_outcome
                    WHERE decision_id=decision.decision_id ORDER BY evaluated_at DESC LIMIT 1) outcome ON true
                WHERE (CAST(:season AS INTEGER) IS NULL OR (decision.record_json->'run_identity'->>'season')::int=CAST(:season AS INTEGER))
                ORDER BY decision.decided_at DESC
            """), {"season": season}).mappings().all()
        results = []
        for row in rows:
            r, o = row["record_json"], row["outcome_json"]
            verify_record(r)
            results.append({"decision_id": r["decision_id"], "run_identity": r["run_identity"], "status": r["status"],
                            "chronologically_valid": valid_prelock_decision(r), "tracking": r["research_tracking"],
                            "proposed_pair_overlap": r["proposed_pair"]["shared_player_count"],
                            "alternative_pair_overlap": r["alternative_portfolio"]["alternatives"][0]["shared_player_count"] if r["alternative_portfolio"]["alternatives"] else None,
                            "quality_opportunity_cost": r["alternative_portfolio"]["alternatives"][0]["quality_opportunity_cost"] if r["alternative_portfolio"]["alternatives"] else None,
                            "final_chosen_pair": r["research_tracking"]["chosen_pair"],
                            "actual_entered_pair": r["execution"]["entries"] if r["execution"] else None, "outcome": o})
        valid = [r for r in results if r["chronologically_valid"]]
        buckets = {}
        for bucket in sorted({str(r["proposed_pair_overlap"]) for r in valid}):
            group = [r for r in valid if str(r["proposed_pair_overlap"]) == bucket]
            regrets = [r["outcome"]["final_selection_regret"] for r in group if r["outcome"] and r["outcome"]["final_selection_regret"] is not None]
            buckets[bucket] = {"slates": len(group), "evaluated_slates": sum(r["outcome"] is not None for r in group),
                               "mean_regret": sum(regrets) / len(regrets) if regrets else None}
        return {"protocol": POLICY, "research_only": True, "legacy_selection_status": "AI_SELECTION_UNKNOWN",
                "recorded_runs": len(results), "valid_prelock_slates": len(valid), "runs": results,
                "outcomes_by_overlap_bucket": buckets, "threshold_tuning": "DISABLED",
                "limitations": "Research only. Week 4 Sunday is excluded. No early-result threshold tuning; small samples are descriptive."}
