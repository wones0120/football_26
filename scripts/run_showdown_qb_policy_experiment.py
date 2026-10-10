"""Offline four-way QB audit from one immutable freeze. Never submits or persists live runs."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
from time import monotonic
from unittest.mock import patch

import pandas as pd
import pulp

from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from backend.app.product_services.showdown_portfolio_selection import candidate_metrics, select_showdown_portfolio, signature
from scripts.research_showdown_prelock import FrozenService, PreparationComplete, capture_model, render_solution, thesis

ROOT = Path(__file__).resolve().parents[1]
POLICIES = {"A": (True, 2), "B": (True, 1), "C": (False, 2), "D": (False, 1)}
POLICIES.update(E=(True, 2), F=(True, 2))
TEAM_LIMITS = {"E": 4, "F": 3}
SEED = 20261005
ORIGINAL_CBC = pulp.PULP_CBC_CMD


def solver(*args, **kwargs):
    return ORIGINAL_CBC(msg=False, threads=1, options=[f"randomSeed {SEED}", f"randomCbcSeed {SEED}"])


def read(path):
    envelope = json.loads(path.read_text())
    if "payload" in envelope:
        assert digest_payload(envelope["payload"]) == envelope["sha256"], path
        return envelope["payload"]
    return envelope


def write(path, data):
    data = _json_safe(data)
    envelope = {"payload": data, "sha256": digest_payload(data)}
    if path.exists():
        assert read(path) == data, f"Immutable artifact differs: {path}"
    else:
        path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")


def parameters(directory, label):
    source = read(directory / "recent-A.json")
    omitted = {"strategy_runtime", "decision_snapshot", "strategy_config", "optimizer_rules",
               "objective_config", "contest_urls", "manual_contest_metadata",
               "prepared_input_job_id", "prepared_input_evidence"}
    params = {key: deepcopy(value) for key, value in source["constraint_config_json"].items() if key not in omitted}
    allow, maximum = POLICIES[label]
    params.update(no_qb_captain=not allow, no_two_qbs=maximum == 1)
    if label in TEAM_LIMITS:
        params["max_players_per_team"] = TEAM_LIMITS[label]
    return params


def football_hash(frame):
    # Both controls affect legal constructions, never these prepared player assessments.
    return digest_payload(_json_safe(frame.to_dict("records")))


class AuditService(FrozenService):
    def _persist_optimizer_run(self, job):
        return False  # This research deliberately has no live run lineage writes.


class PrepareService(AuditService):
    def _solve_lineup(self, pool, **kwargs):
        if kwargs.get("score_col") == "optimizer_context_ceiling_score":
            self.prepared = pool.copy().reset_index(drop=True)
            self.solve_kwargs = dict(kwargs)
            raise PreparationComplete()
        return OptimizerService._solve_lineup(self, pool, **kwargs)


class ReplayService(AuditService):
    def _solve_lineup(self, pool, **kwargs):
        if kwargs.get("score_col") == "optimizer_context_ceiling_score" and not hasattr(self, "prepared"):
            self.prepared = pool.copy().reset_index(drop=True)
            self.solve_kwargs = dict(kwargs)
        return OptimizerService._solve_lineup(self, pool, **kwargs)


def prepare(directory):
    frozen = read(directory / "input_freeze.json")
    service = PrepareService(frozen)
    with (directory / "prepare.log").open("w") as log, redirect_stdout(log), patch(
        "backend.app.product_services.optimizer.pulp.PULP_CBC_CMD", side_effect=solver
    ):
        try:
            service.run_job(frozen["season"], frozen["week"], frozen["slate"], "showdown_gpp_portfolio_v3",
                            parameters(directory, "A"), contest_format="showdown", objective="gpp",
                            projection_run_id=frozen["projection_run_id"])
        except PreparationComplete:
            pass
        if not hasattr(service, "prepared"):
            raise ValueError("Frozen preparation did not reach the production candidate solver")
        kwargs = service.solve_kwargs
        # The initial context solve precedes all per-portfolio exposure cuts.
        kwargs.update(exposure_remaining=None, captain_exposure_remaining=None,
                      exclude_lineups=None, exclude_signatures=None, quality_floor=None,
                      portfolio_script=None, locked_captain_player_id=None, include_control_comparison=False)
        model = capture_model(service, service.prepared, kwargs)
    snapshot = {"contract_id": "showdown_qb_prepared_input_v1", "source_optimizer_run_id": read(directory / "recent-A.json")["optimizer_run_id"],
                "source_freeze_sha256": digest_payload(frozen), "projection_run_id": frozen["projection_run_id"],
                "player_pool": service.prepared.to_dict("records"), "football_sha256": football_hash(service.prepared),
                "stack": kwargs["stack_params"], "score_column": kwargs["score_col"],
                "rule_profile": kwargs["rule_profile"].to_dict(), "solver_model": model.to_dict(),
                "fixed_parameters": parameters(directory, "A"), "seed": SEED,
                "code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (ROOT / "backend/app/product_services").glob("showdown*.py")}}
    snapshot["code_sha256"]["backend/app/product_services/optimizer.py"] = hashlib.sha256((ROOT / "backend/app/product_services/optimizer.py").read_bytes()).hexdigest()
    write(directory / "prepared_input.json", snapshot)
    print({"prepared_players": len(service.prepared), "football_sha256": snapshot["football_sha256"]}, flush=True)


def replay(directory, label):
    path = directory / f"controlled-{label}.json"
    if path.exists():
        print(label, "reusing immutable controlled result", flush=True)
        return
    frozen = read(directory / "input_freeze.json")
    snapshot = read(directory / "prepared_input.json")
    service = ReplayService(frozen)
    captured = {}
    def selection(candidates, **kwargs):
        captured.update(candidates=deepcopy(candidates), selection_kwargs=deepcopy(kwargs))
        selected, report = select_showdown_portfolio(candidates, **kwargs)
        captured.update(selected=deepcopy(selected), selection_report=deepcopy(report))
        return selected, report
    started = monotonic()
    with (directory / f"controlled-{label}.log").open("w") as log, redirect_stdout(log), patch(
        "backend.app.product_services.optimizer.select_showdown_portfolio", side_effect=selection
    ), patch("backend.app.product_services.optimizer.pulp.PULP_CBC_CMD", side_effect=solver):
        job = service.run_job(frozen["season"], frozen["week"], frozen["slate"], "showdown_gpp_portfolio_v3",
                             parameters(directory, label), contest_format="showdown", objective="gpp",
                             projection_run_id=frozen["projection_run_id"])
    if "selected" not in captured:
        raise ValueError(f"Replay did not reach portfolio selection: {job.message}")
    assert football_hash(service.prepared) == snapshot["football_sha256"], "Prepared football inputs changed"
    allow, maximum = POLICIES[label]
    captured.update(policy=label, allow_qb_captain=allow, max_starting_qbs_per_lineup=maximum,
                    max_players_per_team=TEAM_LIMITS.get(label, 5),
                    requested=5, effective_qb_captain_limit="eligible under fixed Captain appearance cap" if allow else 0,
                    effective_starting_qb_lineup_limit=maximum, prepared_snapshot_sha256=digest_payload(snapshot),
                    football_sha256=snapshot["football_sha256"], projection_run_id=frozen["projection_run_id"],
                    source_optimizer_run_id=snapshot["source_optimizer_run_id"], seed=SEED,
                    metadata_status="offline experiment; no optimizer-run or lineup persistence", elapsed_seconds=monotonic()-started)
    captured["execution_optimizer_code_sha256"] = hashlib.sha256((ROOT / "backend/app/product_services/optimizer.py").read_bytes()).hexdigest()
    write(path, captured)
    print(label, {"selected": len(captured["selected"]), "candidates": captured["selection_report"]["candidate_count"],
                  "quality": captured["selection_report"]["quality_eligible_count"], "seconds": captured["elapsed_seconds"]}, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--stage", choices=["prepare", "replay"], required=True)
    parser.add_argument("--policy", choices=list(POLICIES))
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.directory)
    else:
        for label in ([args.policy] if args.policy else POLICIES):
            replay(args.directory, label)


if __name__ == "__main__":
    main()
