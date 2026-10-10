"""Export one frozen optimizer-result JSON artifact for packet review.

Usage: python -m scripts.export_ai_showdown_packet INPUT.json OUTPUT_DIR
The API download is the normal path for saved database runs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.product_services.ai_showdown_packet import build_packet, build_retrospective_packet, render_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--finalists", type=int, default=20)
    parser.add_argument("--ai-requested-entries", "--entries", dest="ai_requested_entries", type=int)
    parser.add_argument("--allow-incomplete-evidence", action="store_true", help="Explicit non-production diagnostic override")
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--slate")
    parser.add_argument("--retrospective", action="store_true", help="Diagnostic only; cannot certify a late-created pool as prelock")
    parser.add_argument("--minimum-quality-fraction", type=float, default=.80)
    parser.add_argument("--strong-quality-fraction", type=float, default=.90)
    args = parser.parse_args()
    source = json.loads(args.input.read_text())
    for key in ("season", "week", "slate"):
        if getattr(args, key) is not None:
            source[key] = getattr(args, key)
    if not all(source.get(key) is not None for key in ("season", "week", "slate")):
        parser.error("Season, week, and slate are required when absent from the frozen input")
    builder = build_retrospective_packet if args.retrospective else build_packet
    extra = {} if args.retrospective else {"allow_incomplete_evidence": args.allow_incomplete_evidence}
    packet = builder(source, finalist_count=args.finalists, ai_requested_entries=args.ai_requested_entries, **extra,
                     quality_policy={"minimum_fraction": args.minimum_quality_fraction, "strong_fraction": args.strong_quality_fraction})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"AI_SHOWDOWN_SELECTION_PACKET_{source.get('slate') or args.input.stem}_{packet['run']['optimizer_run_id']}"
    if args.retrospective: stem += "_RETROSPECTIVE"
    elif args.allow_incomplete_evidence: stem += "_INCOMPLETE_EVIDENCE"
    (args.output_dir / f"{stem}.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    (args.output_dir / f"{stem}.md").write_text(render_markdown(packet))
    print(json.dumps({"packet_id": packet["evidence_hash"], "finalists": len(packet["finalists"]), "output": stem}))


if __name__ == "__main__":
    main()
