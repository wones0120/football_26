"""Phase 6A research-only joint outcomes and paired lineup distributions.

The factor loadings are declared structural priors, not learned estimates.
No result produced here is eligible for automatic model promotion.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MODEL_ID = "joint_game_factor_research_v1"
ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / "artifacts/source_snapshots/joint_simulations"
QUANTILES = ("projection_p10", "projection_p25", "projection_p50", "projection_p75", "projection_p90")


@dataclass(frozen=True)
class FactorPrior:
    game_environment: float = 0.20
    team_passing: float = 0.50
    leading_rusher: float = 0.30
    trailing_passer: float = 0.15
    defense_opposing_pass: float = -0.40


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def prepare_pool(pool: pd.DataFrame) -> pd.DataFrame:
    required = {"player_id", "position", "team_id", "opponent_team_id", "game_id", "projection_mean", *QUANTILES}
    missing = sorted(required - set(pool.columns))
    if missing:
        raise ValueError("Joint simulation snapshot is missing: " + ", ".join(missing))
    frame = pool.copy()
    for key in ("player_id", "game_id", "team_id", "opponent_team_id", "position"):
        frame[key] = frame[key].fillna("").astype(str).str.strip()
        if frame[key].str.lower().isin({"", "none", "nan", "null"}).any():
            raise ValueError(f"Joint simulation requires explicit canonical {key} for every player")
    if frame["player_id"].duplicated().any():
        raise ValueError("Duplicate canonical player_id in simulation snapshot")
    if not frame["position"].isin({"QB", "RB", "WR", "TE", "K", "DST"}).all():
        raise ValueError("Snapshot requires natural player positions, including K/DST")
    values = frame[["projection_mean", *QUANTILES]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (np.diff(values[:, 1:], axis=1) < 0).any():
        raise ValueError("Research v1 requires finite, monotone marginal quantiles")
    for _, game in frame.groupby("game_id"):
        teams = set(game["team_id"]) | set(game["opponent_team_id"])
        if len(teams) != 2 or (game["team_id"] == game["opponent_team_id"]).any():
            raise ValueError("Conflicting canonical team/opponent identities within a game")
    return frame.sort_values("player_id").reset_index(drop=True)


def sample_joint_outcomes(pool: pd.DataFrame, *, num_simulations: int, seed: int,
                          prior: FactorPrior = FactorPrior()) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, dict]:
    """Reorder identical marginal draws using a shared-factor Gaussian rank copula.

    Each column is a permutation of its independent baseline. Thus the empirical
    player distribution is preserved exactly; only cross-player dependence changes.
    """
    if not 100 <= num_simulations <= 20_000:
        raise ValueError("num_simulations must be between 100 and 20000")
    if not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be between 0 and 2**32 - 1")
    if not all(np.isfinite(value) for value in asdict(prior).values()):
        raise ValueError("Factor loadings must be finite")
    frame = prepare_pool(pool)
    if frame.empty or len(frame) > 1000:
        raise ValueError("Research simulation requires 1 to 1000 players")
    marginal_rng = np.random.default_rng(seed)
    uniforms = marginal_rng.random((num_simulations, len(frame)))
    independent = np.empty_like(uniforms)
    probabilities = [0, .10, .25, .50, .75, .90, 1]
    for index, row in frame.iterrows():
        p10, p25, p50, p75, p90 = row[list(QUANTILES)].to_numpy(dtype=float)
        values = [p10 - (p25-p10)*2/3, p10, p25, p50, p75, p90, p90 + (p90-p75)*2/3]
        independent[:, index] = np.interp(uniforms[:, index], probabilities, values)
    rng = np.random.default_rng(np.random.SeedSequence([seed, 603]))
    loadings: list[dict[tuple[str, ...], float]] = []
    for row in frame.to_dict("records"):
        game, team, opponent, position = (row[key] for key in ("game_id", "team_id", "opponent_team_id", "position"))
        side = 1.0 if team < opponent else -1.0
        player_loadings = {(game, "environment"): prior.game_environment if position != "DST" else -prior.game_environment}
        if position in {"QB", "WR", "TE"}:
            player_loadings[(game, "passing", team)] = prior.team_passing
            player_loadings[(game, "script")] = -side * prior.trailing_passer
        elif position in {"RB", "DST"}:
            player_loadings[(game, "script")] = side * prior.leading_rusher
        if position == "DST":
            player_loadings[(game, "passing", opponent)] = prior.defense_opposing_pass
        if sum(value**2 for value in player_loadings.values()) >= 1:
            raise ValueError("Shared factor variance must be below one per player")
        loadings.append(player_loadings)
    factor_keys = sorted(set().union(*(row.keys() for row in loadings)))
    factors = {key: rng.standard_normal(num_simulations) for key in factor_keys}
    joint = np.empty_like(independent)
    for index, coefficients in enumerate(loadings):
        variance = sum(value**2 for value in coefficients.values())
        latent = np.sqrt(1 - variance) * rng.standard_normal(num_simulations)
        for key, value in coefficients.items():
            latent += value * factors[key]
        order = np.argsort(latent, kind="stable")
        joint[order, index] = np.sort(independent[:, index])
    diagnostic = {
        "players": len(frame), "games": int(frame["game_id"].nunique()),
        "factor_count": len(factor_keys),
        "marginals_preserved_exactly": bool(np.array_equal(np.sort(independent, axis=0), np.sort(joint, axis=0))),
        "factor_prior": asdict(prior), "factor_evidence": "unvalidated_structural_prior",
        "marginal_contract": "signed_piecewise_quantiles_research_v1",
        "negative_outcomes_retained": int(np.count_nonzero(independent < 0)),
        "max_sample_mean_gap_from_projection_mean": float(np.max(np.abs(independent.mean(axis=0) - frame["projection_mean"].to_numpy()))),
    }
    return frame, independent, joint, diagnostic


def lineup_distribution(outcomes: np.ndarray, pool: pd.DataFrame, lineup: list[dict],
                        *, contest_format: str, threshold: float | None = None) -> tuple[np.ndarray, dict]:
    ids = [str(player.get("player_id") or "") for player in lineup]
    if len(ids) != len(set(ids)):
        raise ValueError("A lineup cannot repeat a canonical player")
    if contest_format not in {"classic", "showdown"}:
        raise ValueError("Unknown contest format")
    if len(ids) != (9 if contest_format == "classic" else 6):
        raise ValueError("Unexpected lineup roster size")
    lookup = {player_id: index for index, player_id in enumerate(pool["player_id"])}
    if set(ids) - lookup.keys():
        raise ValueError("Lineup players are missing from the immutable simulation snapshot")
    roles = [str(player.get("roster_position") or "").upper() for player in lineup]
    if contest_format == "showdown" and (roles.count("CPT") != 1 or roles.count("FLEX") != 5):
        raise ValueError("Showdown needs one CPT and five FLEX slots")
    if contest_format == "classic" and "CPT" in roles:
        raise ValueError("Classic lineups cannot contain a Captain")
    totals = np.zeros(len(outcomes))
    for player_id, role in zip(ids, roles):
        totals += outcomes[:, lookup[player_id]] * (1.5 if role == "CPT" else 1.0)
    if threshold is not None and not np.isfinite(threshold):
        raise ValueError("threshold must be finite")
    summary = {"mean": float(totals.mean()), "stddev": float(totals.std()),
               **{label: float(np.quantile(totals, probability)) for label, probability in
                  (("p10", .1), ("median", .5), ("p75", .75), ("p90", .9))}}
    if threshold is not None:
        probability = float(np.mean(totals >= threshold))
        summary.update(threshold=threshold, probability_at_or_above_threshold=probability,
                       threshold_mc_standard_error=float(np.sqrt(probability * (1-probability) / len(totals))))
    return totals, summary


def evaluate_experiment(pool: pd.DataFrame, *, lineage: dict, lineups: list[list[dict]] | None = None,
                        num_simulations: int = 5000, seed: int = 603,
                        threshold: float | None = None) -> dict:
    frame, independent, joint, diagnostics = sample_joint_outcomes(pool, num_simulations=num_simulations, seed=seed)
    comparisons = []
    for index, scored in enumerate(lineups or []):
        control = (scored[0].get("lineup_control_comparison") or {}).get("control_lineup")
        if not control:
            raise ValueError("Optimizer run has no saved OPT-007 control; generate a new optimizer run")
        results = {}
        for name, draws in (("independent", independent), ("joint", joint)):
            scored_draws, scored_summary = lineup_distribution(draws, frame, scored, contest_format=lineage["contest_format"], threshold=threshold)
            control_draws, control_summary = lineup_distribution(draws, frame, control, contest_format=lineage["contest_format"], threshold=threshold)
            difference = scored_draws - control_draws
            results[name] = {
                "scored": scored_summary, "control": control_summary,
                "deltas_scored_minus_control": {key: scored_summary[key] - control_summary[key] for key in ("mean", "p10", "median", "p75", "p90", "stddev")},
                "paired_mean_delta": float(difference.mean()),
                "paired_mean_mc_standard_error": float(difference.std(ddof=1) / np.sqrt(len(difference))),
                "probability_scored_beats_control": float(np.mean(difference > 0)),
                "probability_tie": float(np.mean(difference == 0)),
            }
        comparisons.append({"lineup_number": index + 1, **results})
    inputs = {"model_id": MODEL_ID, "lineage": lineage, "num_simulations": num_simulations,
              "seed": seed, "threshold": threshold, "factor_prior": diagnostics["factor_prior"],
              "numpy_version": np.__version__,
              "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "pool": frame[["player_id", "position", "game_id", "team_id", "opponent_team_id", "projection_mean", *QUANTILES]].to_dict("records"),
              "lineups": lineups or []}
    # The entire replay contract is content addressed, including frozen source scope.
    experiment_id = _digest(inputs)
    return {"experiment_id": experiment_id, "model_id": MODEL_ID, "status": "completed_research",
            "performance_claim_eligible": False, "production_promotion_eligible": False,
            "warnings": ["Factor loadings are structural priors, not learned correlations.",
                         "Marginal preservation does not prove calibration against actual outcomes.",
                         "Signed quantile tails are linearly extrapolated, not constrained by a play-level scoring model; the supplied projection mean is not enforced.",
                         "Threshold probabilities are not cash rates or payout estimates.",
                         "Snapshot cutoffs alone do not prove salary/source observation timing."],
            "diagnostics": diagnostics, "lineage": lineage, "comparisons": comparisons,
            "draws_sha256": hashlib.sha256(joint.tobytes()).hexdigest(), "replay_inputs": inputs}


def replay_experiment(report: dict) -> dict:
    inputs = report["replay_inputs"]
    if _digest(inputs) != report["experiment_id"]:
        raise ValueError("Joint research input checksum mismatch")
    if (inputs["model_id"] != MODEL_ID or inputs["factor_prior"] != asdict(FactorPrior())
            or inputs["numpy_version"] != np.__version__
            or inputs["implementation_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError("Unknown joint research model or prior version")
    return evaluate_experiment(pd.DataFrame(inputs["pool"]), lineage=inputs["lineage"],
                               lineups=inputs["lineups"], num_simulations=inputs["num_simulations"],
                               seed=inputs["seed"], threshold=inputs["threshold"])


def save_experiment(report: dict, root: Path = ARTIFACT_ROOT) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{report['experiment_id']}.json"
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    # Link a fully written temporary file atomically; an existing run is never overwritten.
    descriptor, temporary = tempfile.mkstemp(dir=root, prefix=".joint-")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(payload)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_text() != payload:
                raise ValueError("Existing experiment content does not match its immutable identity")
    finally:
        os.unlink(temporary)
    return destination


def run_joint_research(simulation_service, optimizer_service, *, simulation_run_id: str,
                       optimizer_run_id: str | None = None, num_simulations: int = 5000,
                       seed: int = 603, threshold: float | None = None,
                       allow_missing_cutoff: bool = False, artifact_root: Path = ARTIFACT_ROOT) -> dict:
    source = simulation_service.fetch_by_id(simulation_run_id)
    if source is None:
        raise ValueError("Completed source simulation run not found")
    if source.data_cutoff_at is None and not allow_missing_cutoff:
        raise ValueError("Source simulation has no cutoff; explicitly allow missing-cutoff exploratory research")
    lineups = None
    if optimizer_run_id:
        job = optimizer_service.get_job(optimizer_run_id)
        if job is None or job.status != "completed" or not job.results:
            raise ValueError("Completed optimizer run not found")
        expected = (source.season, source.week, source.slate.upper(), source.contest_format, source.projection_run_id, source.data_cutoff_at)
        actual = (job.season, job.week, job.slate.upper(), job.contest_format, job.projection_run_id, job.data_cutoff_at)
        if expected != actual:
            raise ValueError("Simulation and optimizer scope, projection lineage, or cutoff do not match")
        lineups = job.results
    pool = simulation_service._load_persisted_pool(simulation_run_id)
    lineage = {"simulation_run_id": simulation_run_id, "optimizer_run_id": optimizer_run_id,
               "projection_run_id": source.projection_run_id, "season": source.season,
               "week": source.week, "slate": source.slate, "contest_format": source.contest_format,
               "data_cutoff_at": source.data_cutoff_at.isoformat() if source.data_cutoff_at else None,
               "cutoff_status": "recorded_not_independently_verified" if source.data_cutoff_at else "missing_exploratory_only"}
    report = evaluate_experiment(pool, lineage=lineage, lineups=lineups,
                                 num_simulations=num_simulations, seed=seed, threshold=threshold)
    path = save_experiment(report, artifact_root)
    return {**report, "artifact_path": str(path)}
