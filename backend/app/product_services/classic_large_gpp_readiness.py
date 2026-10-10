"""Reporting-only Large-GPP assessment of frozen inputs; never solve or refresh."""
from collections import Counter, defaultdict
from datetime import UTC, datetime

from .classic_primary_game import canonical_primary_game
from .classic_prospective import _timestamp, digest_payload, slate_kickoff_evidence_pool
from .classic_small_field import classic_entry_readiness
from .classic_strategy_contract import digest, portfolio_audit
from .gpp_optimizer import Player
from .optimizer_effectiveness import chronological_validation

VERSION = "classic_large_gpp_readiness_v1"


def game_appearance_summary(lineups, contract):
    lookup = {p["player_id"]: p for p in (contract or {}).get("effective", {}).get("players", [])}
    games = defaultdict(lambda: {"per_entry_including_dst": [0] * len(lineups),
                                 "per_entry_offense": [0] * len(lineups)})
    primary = Counter()
    unavailable = []
    for index, lineup in enumerate(lineups):
        for saved in lineup:
            row = {**lookup.get(str(saved.get("player_id")), {}), **saved}
            try:
                game = canonical_primary_game(row.get("team") or row.get("player_team"),
                                              row.get("opponent") or row.get("opponent_team"))
            except (ValueError, AttributeError):
                unavailable.append({"entry": index + 1, "player_id": saved.get("player_id")})
                continue
            games[game]["per_entry_including_dst"][index] += 1
            if row.get("position") not in {"DST", "D", "DEF"}:
                games[game]["per_entry_offense"][index] += 1
            if row.get("position") == "QB":
                primary[game] += 1
    return {"entries": len(lineups), "roster_appearances": sum(map(len, lineups)),
            "offensive_appearances": sum(p.get("position") not in {"DST", "D", "DEF"} for l in lineups for p in l),
            "primary_qb_games": dict(primary), "unavailable": unavailable,
            "games": [{"game": game, **counts,
                       "entries_containing_game": sum(n > 0 for n in counts["per_entry_including_dst"]),
                       "appearances_including_dst": sum(counts["per_entry_including_dst"]),
                       "offensive_appearances": sum(counts["per_entry_offense"])}
                      for game, counts in sorted(games.items())]}


def finish_large_gpp_readiness(*, checks, market_coverage, contract, selected, source, decision_at):
    audit = portfolio_audit(contract, selected)
    checks["Legal roster and requested portfolio constraints"] = {
        "status": "PASS" if audit["validation"]["status"] == "verified" else "BLOCKER",
        "reason": str(audit["validation"])}
    # Large GPP has no retained broad candidate pool or Small-field automatic risk caps.
    checks["Questionable-player risk"] = {"status": "PASS" if audit["validation"]["status"] == "verified" else "BLOCKER",
        "reason": "Saved upstream classifications and explicit/global limits only; achieved exposure is not a requested cap"}
    checks["Market source provenance"] = {"status": "PASS" if all(
        row.get("market_source_system") and row.get("market_observed_at") for row in source.values()
    ) else "DEVELOPMENT_PREVIEW", "reason": "Source names and observation times retained from the consumed frozen feature frame; missing provenance stays unavailable"}
    evidence = []
    selected_ids = {p.player_id for lineup in selected for p in lineup}
    for pid in sorted(selected_ids):
        row = source.get(pid, {})
        risk = contract["effective"].get("risk_classifications", {}).get(pid, {})
        evidence.append({"player_id": pid, "name": row.get("player_name") or row.get("name"),
            "designation": risk.get("designation"), "frozen_bucket": risk.get("bucket"),
            "injury_observed_at": row.get("injury_observed_at"),
            "injury_source": row.get("injury_source_system"),
            "practice_status": row.get("practice_participation"),
            "practice_observed_at": row.get("practice_observed_at"),
            "context_source": row.get("pregame_context_source"),
            "context_observed_at": row.get("pregame_context_observed_at"),
            "official_availability_status": row.get("official_availability_status"),
            "evidence_gap": risk.get("evidence_gap"),
            "source_evidence_consumed": bool(row.get("practice_participation") and risk.get("practice_status") == row.get("practice_participation")),
            "current_evidence_consumed": False})
    # No current source fetch/clearance has occurred. Do not borrow job/fetch times.
    checks["Availability evidence"] = {"status": "DEVELOPMENT_PREVIEW" if any(
        contract["effective"].get("risk_classifications", {}).get(pid, {}).get("evidence_gap", True)
        for pid in selected_ids) else "PASS",
        "reason": "Frozen upstream evidence gaps retained; source and practice dates shown separately"}
    checks["Current entry availability clearance"] = {"status": "DEVELOPMENT_PREVIEW",
        "reason": "Not evaluated: frozen source/practice evidence is not a current final-inactive or starter clearance check"}
    checks["Salary/source freshness"] = {"status": "DEVELOPMENT_PREVIEW",
        "reason": "Saved salary lineage is shown; current salary/source freshness not checked. No new threshold assumed"}
    checks["Current weather evidence"] = {"status": "DEVELOPMENT_PREVIEW",
        "reason": "Current material weather/source freshness not evaluated by this saved-input assessment"}
    status = "BLOCKED" if any(c["status"] == "BLOCKER" for c in checks.values()) else "DEVELOPMENT_PREVIEW"
    return {"version": VERSION, "status": status, "entry_ready": False,
            "preview_valid": audit["validation"]["status"] == "verified",
            "checks": checks, "market_coverage": market_coverage,
            "availability_evidence": evidence,
            "current_entry_clearance": "UNEVALUATED", "entry_verification": "PENDING",
            "contest_assignment": "UNEVALUATED", "submission_verified": False,
            "portfolio_validation": audit["validation"],
            "elevated_exposure": audit["elevated_player_exposures"],
            "candidate_pool": "Sequential selected entries; broad discovery coverage unavailable",
            "reasons": [f"{name}: {c['reason']}" for name, c in checks.items() if c["status"] != "PASS"],
            "assessed_at": decision_at.isoformat() if decision_at else None}


def assess_large_gpp_saved_inputs(*, contract, snapshot, lineups, salary_identity,
                                assessed_at=None, current_assessment=False):
    assessed_at = assessed_at or datetime.now(UTC)
    payload = snapshot.get("payload", {})
    if (digest_payload(payload) != snapshot.get("sha256") or
        digest({k: v for k, v in contract.items() if k != "sha256"}) != contract.get("sha256") or
        digest(contract["effective"]) != contract.get("effective_sha256") or
        contract.get("metadata", {}).get("input_snapshot_sha256") != snapshot.get("sha256")):
        raise ValueError("Frozen readiness inputs or contract checksum mismatch")
    source = {str(row["player_id"]): row for row in payload["final_solver_rows"]}
    peers = [Player(**{**row, "tags": set(row.get("tags", []))}) for row in contract["effective"]["players"]]
    lookup = {p.player_id: p for p in peers}
    selected = [[lookup[str(row["player_id"])] for row in lineup] for lineup in lineups]
    original_decision = _timestamp(payload["metadata"].get("created_at"))
    decision = assessed_at if current_assessment else original_decision
    timing = chronological_validation({"data_cutoff_at": decision, "optimizer_created_at": decision},
                                     slate_kickoff_evidence_pool(list(source.values())))
    options = payload.get("parameters", {})
    readiness = classic_entry_readiness(players=peers, selected=selected, candidates=[], source=source,
        salary_identity=salary_identity, production_funnel=None, controls=None,
        first_kickoff_at=timing.get("first_saved_kickoff_at"), decision_at=decision,
        requested_count=contract["effective"]["entry_count"], large_gpp_contract=contract,
        market_fresh_hours=float(options.get("market_fresh_hours", 6)),
        market_stale_hours=float(options.get("market_stale_hours", 24)),
        market_stale_policy=str(options.get("market_stale_policy", "warning")))
    readiness.update(assessed_at=assessed_at.isoformat(), original_decision_at=original_decision.isoformat() if original_decision else None,
        freshness_as_of=decision.isoformat() if decision else None,
        scope="present-time assessment of frozen saved inputs; original readiness unchanged" if current_assessment else "saved decision on consumed frozen inputs",
        source_input_sha256=snapshot["sha256"], contract_sha256=contract["sha256"],
        salary_evidence=[{k: row.get(k) for k in ("player_id", "salary_source_row_id", "salary_ingest_run_id", "salary_source_system", "salary_source_checksum", "salary_source_observed_at")}
                         for row in source.values() if row["player_id"] in {p.player_id for l in selected for p in l}])
    preparation = options.get("prepared_input_evidence")
    if preparation:
        readiness["preparation_evidence"] = preparation
        readiness["checks"]["Prepared input dependency lineage"] = {"status": "PASS",
            "reason": f"Verified preparation {preparation['prepared_input_job_id']} consumed by projection {preparation['projection_run_id']}; source SHA256 {preparation['source_sha256']}"}
        readiness["checks"]["Upstream market quote publication freshness"] = {"status": "DEVELOPMENT_PREVIEW",
            "reason": "nflverse capture_clock is a new source download, not verification of quote publication time; upstream quote freshness unknown"}
        readiness["reasons"].append(readiness["checks"]["Upstream market quote publication freshness"]["reason"])
    return readiness


def saved_salary_identity(engine, rows):
    from sqlalchemy import text
    from .optimizer import validate_saved_salary_identity
    if engine.dialect.name != "postgresql":
        return {"status": "UNAVAILABLE", "reason": "Saved salary source lookup unavailable", "violations": []}
    ids = [int(row["salary_source_row_id"]) for row in rows if str(row.get("salary_source_row_id", "")).isdigit()]
    if len(ids) != len(rows):
        return {"status": "UNAVAILABLE", "reason": "Saved curated salary IDs missing", "violations": []}
    with engine.connect() as connection:
        salaries = [dict(r) for r in connection.execute(text("SELECT curated_salary_id, player_master_id, team, opponent, salary FROM public.curated_salary WHERE curated_salary_id = ANY(:ids)"), {"ids": ids}).mappings()]
    return validate_saved_salary_identity(rows, salaries)


def assess_saved_job(job, engine):
    if job.strategy != "classic_large_gpp_v1" or job.status != "completed":
        raise ValueError("Requires a completed saved Classic Large-GPP job")
    snapshot = job.params.get("strategy_runtime", {}).get("classic_run_input_snapshot")
    contract = job.params.get("effective_strategy_contract")
    if not snapshot or not contract:
        raise ValueError("Frozen readiness inputs unavailable; current inputs cannot replace them")
    return assess_large_gpp_saved_inputs(contract=contract, snapshot=snapshot, lineups=job.results,
        salary_identity=saved_salary_identity(engine, snapshot["payload"]["final_solver_rows"]), current_assessment=True)
