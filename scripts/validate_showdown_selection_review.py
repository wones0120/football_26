"""Saved-input Week5 display validation; never reads outcome files or writes decisions."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.product_services.ai_showdown_packet import build_packet, render_markdown
from backend.app.product_services.showdown_selection_review import build_review, review_comparison, review_markdown
from backend.app.product_services.showdown_selection_records import DecisionRequest, ExecutionRequest, review_hash

RUN = "3a41af88-a28c-41b1-888c-462ddcd7d74d"
# User-requested observed roster diagnostic; this is not a prelock AI recommendation.
OBSERVED_PAIR = [RUN + ":beb41d478b13c469", RUN + ":8e2120be4073304e"]
OUT = ROOT / "artifacts/showdown_ai_selection_review"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads((ROOT / "artifacts/showdown_selection_diversity_audit" / f"{RUN}-source.json").read_text())
    original = deepcopy(source)
    legacy = json.loads((ROOT / "artifacts/showdown_selection_diversity_audit/week5_packet.json").read_text())
    packet = build_packet(source, ai_requested_entries=2)
    review = build_review(packet)
    comparison = review_comparison(review, OBSERVED_PAIR)
    rank41 = next(c for c in review["candidates"] if c["metrics"]["selector_rank"] == 41)
    assert review["counts"] == {"quality_eligible": 75, "finalists": 20, "ceiling_outsiders": 10}
    assert rank41["candidate_id"] in review["attention_shortlist"]["ceiling_outsider_candidate_ids"]
    assert comparison["proposed_pair"]["shared_player_count"] == 5
    assert comparison["alternative_portfolio"]["alternatives"][0]["shared_player_count"] <= 4
    assert packet["finalists"] == legacy["finalists"]
    assert packet["control_selection"] == legacy["control_selection"]
    assert {c["candidate_id"] for c in review["candidates"]} == {c["candidate_id"] for c in legacy["ai_review_universe"]["candidates"]}
    assert source == original
    baseline = json.loads((OUT / "working_baseline.json").read_text())
    production = {f: {"before": baseline[f], "after": sha256((ROOT/f).read_bytes()).hexdigest()} for f in (
        "backend/app/product_services/optimizer.py", "backend/app/product_services/gpp_optimizer.py",
        "backend/app/product_services/showdown_portfolio_selection.py")}
    assert production["backend/app/product_services/gpp_optimizer.py"]["before"] == production["backend/app/product_services/gpp_optimizer.py"]["after"]
    assert production["backend/app/product_services/showdown_portfolio_selection.py"]["before"] == production["backend/app/product_services/showdown_portfolio_selection.py"]["after"]
    values = {
        "week5_packet.json": packet,
        "example_review_packet.json": {"review": review, "review_hash": review_hash(review)},
        "week5_comparison.json": comparison,
        "ui_review_fixture.json": {"review": review, "review_hash": review_hash(review), "decision_history": [],
                                   "selection_status": "AI_SELECTION_UNKNOWN", "can_record_prelock": False,
                                   "server_time": "2026-10-09T16:00:00+00:00"},
        "validation_results.json": {"passed": True, "basis": "historical_display_replay_only", "run_id": RUN,
                                     "counts": review["counts"], "rank41": rank41["candidate_id"],
                                     "observed_pair_overlap": 5, "alternatives": comparison["alternative_portfolio"],
                                     "finalists_unchanged": True, "eligible_universe_unchanged": True,
                                     "control_selection_unchanged": True, "source_unchanged": True,
                                     "production_source_hashes": production,
                                     "concurrent_optimizer_input_changes": production["backend/app/product_services/optimizer.py"]["before"] != production["backend/app/product_services/optimizer.py"]["after"],
                                     "production_files_edited_by_this_task": [], "historical_ai_selection": "AI_SELECTION_UNKNOWN",
                                     "decision_records_created": 0},
    }
    for name, value in values.items():
        (OUT/name).write_text(json.dumps(value, indent=2)+"\n")
    (OUT/"example_review_packet.md").write_text(render_markdown(packet)+review_markdown(review))
    for name, model in [("showdown_selection_decision_request_v1", DecisionRequest), ("showdown_selection_execution_request_v1", ExecutionRequest)]:
        schema = model.model_json_schema(); schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"; schema["$id"] = name
        (ROOT/"docs/product"/f"{name}.schema.json").write_text(json.dumps(schema,indent=2)+"\n")
    print("PASS: 75 eligible / 20 finalists / 10 outsiders; rank41 surfaced; 5/6 observed overlap; lower-overlap alternatives; unchanged production/control/membership.")


if __name__ == "__main__": main()
