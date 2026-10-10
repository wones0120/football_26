"""Audit an already frozen packet; actuals never enter the packet exporter."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.product_services.ai_showdown_finalist_audit import audit_finalist_set, render_audit_markdown
from backend.app.product_services.optimizer_effectiveness import actual_points_by_player


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("actuals", type=Path, help="JSON with resolved observations or actual_points_by_player (canonical base DK points)")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--universe-best-score", type=float)
    parser.add_argument("--manual-selection", type=Path)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text())
    source = json.loads(args.source.read_text())
    labels = json.loads(args.actuals.read_text())
    for field in ("season", "week", "slate"):
        if field in labels and labels[field] != packet["run"][field]:
            parser.error(f"Actuals {field} does not match frozen packet")
    actuals = labels.get("actual_points_by_player")
    if actuals is None:
        actuals = actual_points_by_player(labels["observations"], "showdown")
    selected = None
    if args.manual_selection:
        from backend.app.product_services.ai_showdown_packet import validate_manual_selection
        selected = validate_manual_selection(json.loads(args.manual_selection.read_text()), packet)["selected_candidate_ids"]
    audit = audit_finalist_set(packet, source, actuals, universe_best_actual_score=args.universe_best_score,
                              selected_candidate_ids=selected, contest_fields=labels.get("contest_fields"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.packet.stem + "_POST_SLATE_AUDIT"
    (args.output_dir / (stem + ".json")).write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    (args.output_dir / (stem + ".md")).write_text(render_audit_markdown(audit))
    print(json.dumps({k: audit[k] for k in ("optimizer_run_id", "status", "best_generated_actual_score", "best_finalist_actual_score", "finalist_selection_regret")}))


if __name__ == "__main__":
    main()
