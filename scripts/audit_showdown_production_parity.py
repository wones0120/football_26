"""Offline Showdown parity replay. Reads frozen inputs; never persists a job."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import json
from pathlib import Path
import time
from unittest.mock import patch

from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio
from scripts.research_showdown_prelock import FrozenService


class ReplayService(FrozenService):
    _solve_lineup = OptimizerService._solve_lineup

    def _persist_optimizer_run(self, job):
        return False


def read(path):
    data = json.loads(path.read_text())
    if "sha256" in data:
        assert digest_payload(data["payload"]) == data["sha256"], path
        return data["payload"]
    return data


def write(path, payload):
    if path.exists():
        raise ValueError(f"Immutable audit output already exists: {path}")
    payload = _json_safe(payload)
    path.write_text(json.dumps({"payload": payload, "sha256": digest_payload(payload)}, indent=2, sort_keys=True)+"\n")


def replay(directory, freeze_path, label):
    frozen = read(freeze_path)
    job = read(directory / "production_job.json")
    params = {k: deepcopy(v) for k, v in job["params"].items()
              if k not in {"strategy_runtime", "decision_snapshot", "strategy_config", "optimizer_rules", "objective_config", "projection_availability_scenario"}}
    captured = {}
    service = ReplayService(frozen)
    def selection(candidates, **kwargs):
        captured.update(candidates=deepcopy(candidates), selection_kwargs=deepcopy(kwargs))
        selected, report = select_showdown_portfolio(candidates, **kwargs)
        captured.update(selected=deepcopy(selected), selection_report=deepcopy(report))
        return selected, report
    start = time.monotonic()
    with (directory / (label+".log")).open("w") as log, redirect_stdout(log), patch(
        "backend.app.product_services.optimizer.select_showdown_portfolio", side_effect=selection
    ):
        result = service.run_job(frozen["season"], frozen["week"], frozen["slate"], job["strategy"], params,
                                 contest_format="showdown", objective="gpp", projection_run_id=frozen["projection_run_id"])
    captured.update(job=result.__dict__, seconds=time.monotonic()-start, input_sha256=digest_payload(frozen))
    write(directory/(label+".json"), captured)
    print(label, result.status, result.message, round(captured["seconds"], 2), flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("freeze", type=Path)
    parser.add_argument("label")
    args=parser.parse_args()
    replay(args.directory, args.freeze, args.label)


if __name__ == "__main__":
    main()
