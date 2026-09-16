#!/usr/bin/env python3
"""Create or replay a content-addressed Phase 6A experimental simulation report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.product_services.joint_simulations import replay_experiment, run_joint_research
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.simulations import SimulationService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--simulation-run-id")
    choice.add_argument("--replay", type=Path)
    parser.add_argument("--optimizer-run-id")
    parser.add_argument("--num-simulations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=603)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--allow-missing-cutoff", action="store_true")
    args = parser.parse_args()
    if args.replay:
        saved = json.loads(args.replay.read_text())
        result = replay_experiment(saved)
        if result["draws_sha256"] != saved["draws_sha256"]:
            raise ValueError("Replay draws differ from the saved experiment")
        print(json.dumps({"experiment_id": result["experiment_id"], "replay": "verified"}))
    else:
        result = run_joint_research(SimulationService(), OptimizerService(),
                                    simulation_run_id=args.simulation_run_id,
                                    optimizer_run_id=args.optimizer_run_id,
                                    num_simulations=args.num_simulations,
                                    seed=args.seed, threshold=args.threshold,
                                    allow_missing_cutoff=args.allow_missing_cutoff)
        print(json.dumps({key: value for key, value in result.items() if key != "replay_inputs"}, indent=2))


if __name__ == "__main__":
    main()
