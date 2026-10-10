"""Pre-generation, cutoff-safe evidence contract for live Classic Large GPP.

This contract certifies source usability, not model quality or final submission
clearance. Capture clocks never stand in for unavailable publication clocks.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from .slate_preparation import (SlatePreparationRequest, aware, digest, source_manifest,
                                projection_proof, verify_consumption, verify_artifacts)
from .showdown_data_readiness import number
from .showdown_player_context import CONTEXT_CONTRACT, assess_availability, is_excluded_specialist
from .replay import parse_slate_lock
from .salary_eligibility import is_salary_status_eligible
from .classic_player_pool import assess_pool_player

CONTRACT = "classic_large_gpp_data_readiness_v1"
FROZEN_CONTRACT = "classic_large_gpp_frozen_evidence_v1"
SOURCE_NAMES = ("salary_pool", "projection", "player_status", "market", "ownership")
REQUIRED_REFRESH_SOURCES = {
    "salary_pool": "salary_pool", "market": "market", "player_status": "player_status",
    "official_player_status": "player_status", "starting_qb": "player_status",
    "canonical_player_context": "player_status", "historical_training_features": "projection",
    "projection": "projection", "ownership": "ownership",
}
WEATHER = {"status": "NOT_REQUIRED_BY_CURRENT_MODEL", "required": False,
           "reason_codes": [], "material_paths": [],
           "explanation": "The current Classic projection, ceiling, ownership, context scoring, correlation and eligibility paths do not consume weather."}


def server_prepares_live_classic(payload, engine):
    from types import SimpleNamespace
    from .showdown_data_readiness import is_live_slate
    return payload.get("strategy") in {"classic_large_gpp_v1", "classic_single_lineup_v1"} and is_live_slate(SimpleNamespace(engine=engine),
        season=payload["season"], week=payload["week"], slate=payload["slate"])


class ClassicDataNotReady(ValueError):
    def __init__(self, readiness):
        self.readiness = readiness
        descriptions = {"salary_pool": "Review the original salary provenance and unresolved native identities; a verified existing CSV does not need replacement.",
            "projection": "Current projections could not be rebuilt from verified source dependencies.",
            "player_status": "Current player availability or roles need verification.",
            "market": "Fresh sourced spread/total evidence is required for every eligible game.",
            "ownership": "Ownership must be rebuilt from the verified current projection."}
        messages = [descriptions.get(name, "A material model source needs a verified readiness contract.")
                    for name, check in readiness["required_sources"].items() if check["status"] != "READY"]
        unknown = sorted({str(p.get("player") or p.get("player_id") or p.get("salary_source_row_id"))
                          for p in readiness.get("players", []) if p.get("disposition") in {"unresolved", "invalid_canonical_identity"}})
        if unknown: messages.append("Unverified players: " + ", ".join(unknown[:12]) + ("…" if len(unknown) > 12 else "") + ".")
        super().__init__("Classic is not data-ready. " + " ".join(messages) +
                         " No candidates or lineups were generated. Review the saved source checks.")


def freshness_rules(settings):
    return {name: float(getattr(settings, f"classic_{name}_max_age_hours")) for name in SOURCE_NAMES}


def _time_reasons(value, name, *, cutoff, now, max_age):
    try:
        observed = aware(value)
        if observed > cutoff or observed > now:
            return [f"{name}_after_cutoff"]
        if (now - observed).total_seconds() > max_age * 3600:
            return [f"{name}_stale"]
        return []
    except (TypeError, ValueError, AttributeError):
        return [f"{name}_timestamp_missing"]


def _uuid(value):
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def read_evidence(service, *, season, week, slate, projection_run_id, cutoff):
    """Re-read persisted canonical inputs and prove their projection consumption."""
    request = SlatePreparationRequest(season=season, week=week, slate=slate, action="rebuild")
    with Session(service.engine) as session:
        manifest = source_manifest(session, request, cutoff)
        artifact_error = None
        try:
            verify_artifacts(manifest, session)
        except (ValueError, OSError) as exc:
            artifact_error = str(exc)
        from .classic_salary_provenance import read_salary_provenance
        salary_provenance = read_salary_provenance(session, manifest, cutoff=cutoff)
        ownership_lineage = {str(r['ownership_run_id']): dict(r) for r in session.execute(text('''
            SELECT ownership_run_id,status,metrics_json FROM target.ownership_model_run
            WHERE season=:season AND week=:week AND UPPER(slate_id)=UPPER(:slate)
        '''), dict(season=season,week=week,slate=slate)).mappings()}
        lineage = None
        if projection_run_id:
            feature = session.execute(text("""
                SELECT m.feature_run_id FROM target.projection_run p
                JOIN target.model_run m USING (model_run_id)
                WHERE p.projection_run_id=:projection
            """), {"projection": projection_run_id}).scalar_one_or_none()
            if feature:
                proof = projection_proof(session, {"projection_run_id": projection_run_id, "feature_run_id": feature})
                run = proof["run"]
                if (run["status"] == "completed" and (run["season"], run["week"], str(run["slate_id"]).upper()) ==
                        (season, week, slate.upper())):
                    try:
                        consumption = verify_consumption(manifest, proof["features"], run["source_versions_json"])
                        prepared = run["source_versions_json"].get("slate_preparation") or {}
                        if prepared.get("source_sha256") == digest(manifest):
                            lineage = {"run": {k: run.get(k) for k in ("projection_run_id", "model_run_id", "feature_run_id", "season", "week", "slate_id", "status")},
                                "source_versions_sha256": digest(run["source_versions_json"]),
                                "consumption": consumption, "proof_sha256": digest(proof)}
                    except ValueError:
                        pass
    return {"source_manifest": manifest, "artifact_error": artifact_error, "projection_lineage": lineage,
            "salary_provenance": salary_provenance, "ownership_lineage": ownership_lineage}


def refresh_salary_evidence(service, *, season, week, slate):
    """Use canonical identity repair and verify the immutable DK import.

    The app has a file importer, not a DraftKings download API. Verifying an
    existing import cannot renew its clock or supply an absent draft-group ID.
    """
    from Database.player_identity import repair_salary_identities
    repair = vars(repair_salary_identities(service.engine, season=season, week=week, slate=slate))
    with Session(service.engine) as session:
        manifest = source_manifest(session, SlatePreparationRequest(
            season=season, week=week, slate=slate, action="rebuild"))
        verify_artifacts(manifest, session)
        from .classic_salary_provenance import read_salary_provenance
        provenance = read_salary_provenance(session, manifest, cutoff=datetime.now(UTC))
    return {"mode": "verified_existing_canonical_import", "identity_repair": repair,
            "canonical_import_replay": None, "original_import_provenance": provenance,
            "ingest_run_ids": sorted({str(r["ingest_run_id"]) for r in manifest["salaries"]}),
            "automatic_download_available": False,
            "action_if_missing_or_stale": "Review the exact missing provenance evidence; a verified original CSV does not need replacement.",
            "source_clocks_preserved": True}


def refresh_live_sources(service, *, season, week, slate, params, progress=None):
    from .showdown_data_readiness import refresh_live_sources as refresh
    from .classic_official_context import supplement_unresolved_context
    return refresh(service, season=season, week=week, slate=slate, params=params, progress=progress,
        label="Classic", salary_refresher=lambda: refresh_salary_evidence(service, season=season, week=week, slate=slate),
        ownership_required=True, official_require_complete_coverage=False,
        player_context_supplement=lambda: supplement_unresolved_context(service.engine, season=season, week=week, slate=slate))


def evaluate_readiness(rows, *, season, week, slate, projection_run_id, evidence_cutoff,
                       evaluated_at, rules, evidence, refresh=None):
    cutoff, now = aware(evidence_cutoff), aware(evaluated_at)
    manifest = evidence.get("source_manifest") or {}
    games = manifest.get("games") or []
    salary = {str(r["curated_salary_id"]): r for r in manifest.get("salaries", [])}
    markets = {str(r["market_snapshot_id"]): r for r in manifest.get("markets", [])}
    contexts = {str(r["player_master_id"]): r for r in manifest.get("availability", [])}
    game_pairs = {frozenset((g["home_team"], g["away_team"])): g for g in games}
    checks = {name: {"status": "READY", "required": True, "reason_codes": [], "affected_player_ids": [],
                     "max_age_hours": rules[name], "evidence": []} for name in SOURCE_NAMES}
    reasons_by_player = {}
    def fail(name, code, pid=None):
        checks[name]["reason_codes"].append(code)
        if pid is not None:
            checks[name]["affected_player_ids"].append(str(pid))
            reasons_by_player.setdefault(str(pid), set()).add(code)
    def clock(name, value, pid, field):
        # A derived prediction is written after its information cutoff. Its
        # inputs must precede cutoff; its creation must precede evaluation.
        upper = now if field == "projection_created_at" else cutoff
        for reason in _time_reasons(value, name, cutoff=upper, now=now, max_age=rules[name]):
            fail(name, reason, pid)
        return {"field": field, "observed_at": value,
                "freshness": "fresh" if not _time_reasons(value, name, cutoff=upper, now=now, max_age=rules[name]) else "unusable"}

    if not rows: fail("salary_pool", "salary_pool_empty")
    if not games: fail("salary_pool", "slate_games_missing")
    if len({str(r.get("ingest_run_id")) for r in salary.values()}) != 1:
        fail("salary_pool", "salary_import_mixed_or_missing")
    if len({str((r.get("metadata_json") or {}).get("native_draft_group")) for r in salary.values()}) != 1:
        fail("salary_pool", "salary_draft_group_ambiguous")
    if evidence.get("artifact_error"): fail("salary_pool", "source_artifact_unverified")
    for proof in (evidence.get("salary_provenance") or {}).values():
        for reason in proof.get("reason_codes", []):
            fail("salary_pool", reason)
    represented_salary_ids = {str(r.get("salary_source_row_id")) for r in rows}
    missing_salary_rows = [s for sid, s in salary.items() if sid not in represented_salary_ids]
    for s in missing_salary_rows:
        fail("salary_pool", "native_salary_player_unassessed", s.get("player_master_id") or s["curated_salary_id"])
    for g in games:
        try:
            if now >= aware(g["kickoff_at"]) or cutoff >= aware(g["kickoff_at"]):
                fail("salary_pool", "slate_locked")
        except (KeyError, TypeError, ValueError):
            fail("salary_pool", "slate_kickoff_missing")
    lineage = evidence.get("projection_lineage")
    if not lineage or str(lineage["run"].get("projection_run_id")) != str(projection_run_id):
        fail("projection", "projection_dependency_lineage_unverified")
    eligible, assessments, represented_games = [], [], set()
    expected_ownership = ((refresh or {}).get('ownership', {}).get('result') or {}).get('ownership_run_id')
    def ownership_valid(row):
        run_id = row.get('ownership_run_id')
        if refresh and 'ownership' in refresh and (not expected_ownership or str(run_id) != str(expected_ownership)):
            return False
        if 'ownership_lineage' in evidence:
            proof = evidence['ownership_lineage'].get(str(run_id)) or {}
            provenance = (proof.get('metrics_json') or {}).get('input_provenance') or {}
            if (proof.get('status') != 'completed' or not projection_run_id or
                    str(provenance.get('target_projection_run_id')) != str(projection_run_id)):
                return False
        return number(row.get('ownership')) is not None and 0 <= row['ownership'] <= 100 and bool(run_id)
    for s in missing_salary_rows:
        assessments.append({"player_id": str(s.get("player_master_id")) if s.get("player_master_id") else None,
            "salary_source_row_id": str(s["curated_salary_id"]), "player": s.get("player_name"),
            "team": s.get("team"), "availability": "unknown",
            "disposition": "invalid_canonical_identity" if not _uuid(s.get("player_master_id")) else "unresolved",
            "reason_codes": ["native_salary_player_unassessed"]})
    for r in rows:
        pid = str(r.get("player_id"))
        # Unsupported Classic positions are audited, never adapted into a slot.
        if r.get("position") not in {"QB", "RB", "WR", "TE", "DST"}:
            assessments.append({"player_id": pid, "disposition": "not_a_classic_position"})
            continue
        s = salary.get(str(r.get("salary_source_row_id")))
        game = game_pairs.get(frozenset((r.get("player_team"), r.get("opponent_team"))))
        salary_invalid = (not s or not _uuid(pid) or r.get("identity_resolved") is not True or not r.get("dk_player_id") or
                str(s.get("player_master_id")) != pid or s.get("source_system") != "draftkings" or
                str(s.get("source_player_key")) != str(r.get("dk_player_id")) or
                str(s.get("ingest_run_id")) != str(r.get("salary_ingest_run_id")) or
                number(s.get("salary")) != number(r.get("salary")) or not number(r.get("salary")) or
                r.get("salary", 0) <= 0 or not game or not s.get("game_info") or
                (s.get("team"), s.get("opponent")) != (r.get("player_team"), r.get("opponent_team")))
        if salary_invalid:
            fail("salary_pool", "salary_identity_or_game_invalid", pid)
        if s:
            native_kickoff = parse_slate_lock([s.get("game_info")])
            if not native_kickoff or not game or abs((aware(native_kickoff) - aware(game["kickoff_at"])).total_seconds()) > 60:
                fail("salary_pool", "salary_game_kickoff_mismatch", pid)
            position = str(s.get("position") or s.get("roster_position") or "").upper()
            if position in {"D", "DEF"}: position = "DST"
            if position != r.get("position") or r.get("salary_status_eligible") is not is_salary_status_eligible(s.get("player_status")):
                fail("salary_pool", "salary_eligibility_unverified", pid)
            metadata = s.get("metadata_json") or {}
            original = (evidence.get('salary_provenance') or {}).get(str(s.get('ingest_run_id')), {})
            verified_original = original.get('verified') is True and original.get('source_checksum') == s.get('source_checksum')
            if not ((s.get("snapshot_id") or verified_original) and s.get("source_checksum") and
                    s.get("ingest_status") == "completed"):
                fail("salary_pool", "salary_native_source_unverified", pid)
            # An authenticated original CSV plus exact player/game checks proves
            # the optimization pool. Contest entry compatibility is separate.
            if not metadata.get('native_draft_group') and not verified_original:
                fail('salary_pool', 'salary_native_draft_group_missing')
            clocks = ([clock('salary_pool', original.get('imported_at'), pid, 'original_imported_at'),
                       clock('salary_pool', original.get('completed_at'), pid, 'original_import_completed_at')]
                if verified_original and not s.get('snapshot_id') else
                [clock("salary_pool", s.get("source_observed_at"), pid, "source_observed_at"),
                 clock("salary_pool", s.get("captured_at"), pid, "captured_at")])
            checks["salary_pool"]["evidence"].append({"player_id": pid, "row_id": s["curated_salary_id"],
                "ingest_run_id": s.get("ingest_run_id"), "snapshot_id": s.get("snapshot_id"),
                "native_draft_group": metadata.get("native_draft_group"), "source_checksum": s.get("source_checksum"),
                "clocks": clocks, "publication_at": metadata.get("publication_time"),
                "observation_basis": original.get('observation_basis') if verified_original and not s.get('snapshot_id') else s.get("observation_basis")})
        if r.get("salary_status_eligible") is False:
            assessments.append({"player_id": pid, "disposition": "salary_ineligible"})
            continue
        scope = assess_pool_player(r, cutoff=cutoff, evaluated_at=now, max_age_hours=rules["player_status"])
        state, reasons = scope["availability_state"], scope["availability_reasons"]
        role_excluded = bool(scope["role_exclusion_policy"])
        if r.get("position") != "DST" and not role_excluded:
            for reason in reasons: fail("player_status", reason, pid)
            if state == "UNKNOWN": fail("player_status", "player_availability_unknown", pid)
            if state != "UNAVAILABLE" and (r.get("canonical_role") in {None, "", "uncertain", "unknown", "UNKNOWN"} or not r.get("role_source") or not r.get("role_source_ids")):
                fail("player_status", "player_role_unknown", pid)
            if state != "UNAVAILABLE":
                clock("player_status", r.get("role_observed_at"), pid, "role_observed_at")
        status = str(r.get("availability_status") or r.get("official_availability_status") or "").upper()
        specialist = is_excluded_specialist(r, cutoff=cutoff, evaluated_at=now, max_age_hours=rules["player_status"])
        disposition = "unavailable" if state == "UNAVAILABLE" else "unknown" if state == "UNKNOWN" else (
            "doubtful" if status in {"D", "DOUBTFUL"} else "questionable_elevated" if status in {"Q", "QUESTIONABLE"} else "available")
        final_facts = [f for f in ((contexts.get(pid, {}).get("evidence_json") or {}).get("source_facts") or [])
            if f.get("kind") == "game_status" and type(f.get("game_active")) is bool and f.get("source") and f.get("source_ids")
            and not _time_reasons(f.get("observed_at"), "player_status", cutoff=cutoff, now=now, max_age=rules["player_status"])
            and not _time_reasons(f.get("received_at"), "player_status", cutoff=cutoff, now=now, max_age=rules["player_status"])]
        final = max(final_facts, key=lambda f: aware(f["observed_at"])) if final_facts else None
        from .classic_prospective import classify_availability
        risk_row = {**r, "official_availability_status": r.get("official_availability_status") or status}
        try:
            risk = classify_availability(risk_row, cutoff)
        except ValueError:
            risk = {"bucket": "questionable_elevated" if status in {"Q", "QUESTIONABLE"} else disposition,
                    "evidence_gap": True}
            fail("player_status", "player_risk_context_after_cutoff", pid)
        if state != "UNAVAILABLE" and not role_excluded and risk.get("bucket", "").startswith("questionable"):
            # A fresh practice report supports assessing a known Q designation.
            # An absent workload forecast remains elevated uncertainty, not a
            # fabricated full-role clearance or a failure of source ingestion.
            if not (final and final["game_active"]):
                if risk.get("practice_status") not in {"FULL", "LIMITED", "DNP"}:
                    fail("player_status", "questionable_usage_context_unresolved", pid)
                clock("player_status", r.get("practice_observed_at"), pid, "practice_observed_at")
                if r.get("expected_workload_status") or r.get("expected_workload_observed_at"):
                    clock("player_status", r.get("expected_workload_observed_at"), pid, "expected_workload_observed_at")
        if (state != "UNAVAILABLE" and not role_excluded and r.get("position") == "QB"
                and (r.get("canonical_role") != "expected_starter" or r.get("is_starting_qb") is not True)):
            fail("player_status", "starting_qb_unverified", pid)
        player_reasons = sorted(reasons_by_player.get(pid, []))
        assessments.append({"player_id": pid, "player": r.get("name") or r.get("player_name"),
            "team": r.get("player_team"), "availability": disposition, "role": r.get("canonical_role"),
            "risk_assessment": risk, "reason_codes": player_reasons,
            "unresolved_evidence": sorted(set(reasons + list(r.get("canonical_context_reason_codes") or []))),
            "materiality": scope["materiality"], "materiality_evidence": scope["materiality_evidence"],
            "game_day_clearance": "CLEARED" if final and final["game_active"] else "UNAVAILABLE" if final else "UNEVALUATED",
            "game_day_clearance_evidence": deepcopy(final), "disposition": "invalid_canonical_identity" if salary_invalid else
            "unavailable" if state == "UNAVAILABLE" else "quarantined_unresolved_evidence" if scope["quarantine"] else
            "explicitly_excluded_specialist" if specialist else "role_ineligible" if role_excluded else "unresolved" if state == "UNKNOWN" or
            pid in checks["player_status"]["affected_player_ids"] else "explicitly_excluded_specialist" if specialist else
            "role_ineligible" if r.get("role_optimizer_eligible") is False else "generation_eligible"})
        checks["player_status"]["evidence"].append({"player_id": pid, "availability": disposition,
            **{k: r.get(k) for k in ("availability_source", "availability_source_ids", "availability_observed_at",
                                      "role_source", "role_source_ids", "role_observed_at", "canonical_context_reason_codes")}})
        if assessments[-1]["disposition"] != "generation_eligible":
            continue
        eligible.append(pid)
        if game: represented_games.add(game["game_id"])
        if (not projection_run_id or str(r.get("projection_run_id")) != str(projection_run_id) or
                r.get("projection_inputs_complete") is not True or r.get("feature_inputs_complete") is not True or
                not r.get("projection_model_version") or number(r.get("projection")) is None or
                number(r.get("p90")) is None or r["projection"] < 0 or r["p90"] < r["projection"]):
            fail("projection", "projection_inputs_missing_or_invalid", pid)
        checks["projection"]["evidence"].append({"player_id": pid, "projection_run_id": r.get("projection_run_id"),
            "clocks": [clock("projection", r.get(field), pid, field) for field in ("projection_observed_at", "projection_created_at")]})
        m = markets.get(str(r.get("market_snapshot_row_id")))
        if (not m or not game or m.get("game_id") != game["game_id"] or not m.get("source") or
                not m.get("source_snapshot_id") or not m.get("content_sha256") or
                r.get("market_context_point_in_time_safe") is not True or
                r.get("canonical_game_id") != game["game_id"]):
            fail("market", "market_game_evidence_missing", pid)
        else:
            total, spread = number(m.get("game_total")), number(m.get("home_spread"))
            team_spread = spread if r["player_team"] == game["home_team"] else -spread if spread is not None else None
            if (total is None or total <= 0 or spread is None or number(r.get("game_total_line")) != total or
                    number(r.get("team_spread_line")) != team_spread or
                    number(r.get("team_implied_total")) != (total - team_spread) / 2):
                fail("market", "market_values_or_derived_totals_invalid", pid)
            checks["market"]["evidence"].append({"game_id": game["game_id"], "snapshot_id": m["market_snapshot_id"],
                "source_snapshot_id": m["source_snapshot_id"], "source": m["source"],
                "clocks": [clock("market", m.get(field), pid, field) for field in ("observed_at", "ingested_at")],
                "quote_publication_at": None, "quote_publication_freshness": "UNKNOWN"})
        if not ownership_valid(r):
            fail("ownership", "ownership_missing", pid)
        checks["ownership"]["evidence"].append({"player_id": pid, "run_id": r.get("ownership_run_id"),
            "clocks": [clock("ownership", r.get("ownership_observed_at"), pid, "ownership_observed_at")]})
    # Market environments are a slate-level requirement even if player evidence
    # prevents a particular game from having certified scoring rows yet.
    represented_games = {g["game_id"] for g in games}
    for game in games:
        current = [m for m in markets.values() if m.get("game_id") == game["game_id"]]
        m = current[0] if len(current) == 1 else None
        if (not m or not m.get("source") or not m.get("source_snapshot_id") or not m.get("content_sha256")
                or number(m.get("game_total")) is None or m["game_total"] <= 0 or number(m.get("home_spread")) is None):
            fail("market", "market_game_evidence_missing")
        else:
            checks["market"]["evidence"].append({"game_id": game["game_id"], "snapshot_id": m["market_snapshot_id"],
                "source_snapshot_id": m["source_snapshot_id"], "source": m["source"],
                "clocks": [clock("market", m.get(field), None, field) for field in ("observed_at", "ingested_at")]})
    if not eligible: fail("projection", "generation_pool_empty")
    errors = []
    if evidence.get("read_error"):
        errors.append("canonical_evidence_read_failed")
    for name, item in (refresh or {}).items():
        source = REQUIRED_REFRESH_SOURCES.get(name)
        if source and item.get("status") != "completed":
            code = f"{name}_refresh_failed"
            fail(source, code)
            if item.get("status") == "ERROR": errors.append(code)
    weather = deepcopy(WEATHER)
    if (lineage or {}).get("consumption", {}).get("weather_consumed"):
        # No current Classic path supplies a material-weather readiness proof.
        # A new consuming model must implement its source contract first.
        weather.update(status="NOT_READY", required=True,
            reason_codes=["material_weather_evidence_unverified"],
            explanation="Projection lineage declares material weather consumption without a verified weather readiness contract.")
        checks["weather"] = weather
    for check in checks.values():
        check["reason_codes"] = sorted(set(check["reason_codes"]))
        check["affected_player_ids"] = sorted(set(check.get("affected_player_ids", [])))
        check["status"] = "NOT_READY" if check["reason_codes"] else "READY"
        check["evidence"] = list({digest(item): item for item in check.get("evidence", [])}.values())
    reasons = sorted(set(errors + [r for c in checks.values() for r in c["reason_codes"]]))
    kickoffs = sorted(g["kickoff_at"] for g in games)
    return {"contract_id": CONTRACT, "season": season, "week": week, "slate": slate,
        "evaluated_at": now.isoformat(), "evidence_cutoff": cutoff.isoformat(),
        "kickoff_window": {"first": kickoffs[0] if kickoffs else None, "last": kickoffs[-1] if kickoffs else None},
        "status": "ERROR" if errors else "NOT_READY" if reasons else "READY", "reason_codes": reasons,
        "required_sources": checks, "optional_sources": {**({} if weather["required"] else {"weather": weather}),
            "final_game_day_clearance": {"status": "UNEVALUATED", "required": False,
                "explanation": "Baseline source readiness is separate from final inactives and entry submission clearance."}},
        "generation_eligible_player_ids": sorted(p["player_id"] for p in assessments if p["disposition"] == "generation_eligible"),
        "players": assessments,
        "pool_populations": {"native_salary_rows": len(salary), "assessed_salary_rows": len(represented_salary_ids & salary.keys()),
            "canonically_resolved_salary_rows": sum(_uuid(s.get("player_master_id")) for s in salary.values()),
            **{label: sum(p["disposition"] in dispositions for p in assessments) for label, dispositions in {
                "confirmed_unavailable": {"unavailable", "salary_ineligible"},
                "role_ineligible": {"role_ineligible", "explicitly_excluded_specialist", "not_a_classic_position"},
                "unresolved": {"unresolved", "invalid_canonical_identity"},
                "quarantined_unresolved_evidence": {"quarantined_unresolved_evidence"},
                "certified_generation_eligible": {"generation_eligible"}}.items()}},
        "unresolved_player_coverage": {"blocking_players": sum(p["disposition"] in {"unresolved", "invalid_canonical_identity"} for p in assessments),
            "quarantined_players": sum(p["disposition"] == "quarantined_unresolved_evidence" for p in assessments),
            "quarantine_policy": "Fresh sourced existing role exclusion only; unknown offensive opportunity or materiality blocks."},
        "blocker_groups": {"source_level": sorted({code for name, check in checks.items() for code in check["reason_codes"]
                if name != "player_status" or code.endswith('_refresh_failed') or not check.get("affected_player_ids")}),
            "salary_identity_players": [deepcopy(p) for p in assessments if p['disposition'] == 'invalid_canonical_identity'],
            "material_players": [deepcopy(p) for p in assessments if p["disposition"] == "unresolved"]},
        "projection_coverage": {"population": "certified_generation_pool", "required_players": len(eligible), "complete_players": sum(
            bool(projection_run_id) and str(r.get('projection_run_id')) == str(projection_run_id) and
            str(r.get("player_id")) in eligible and r.get("projection_inputs_complete") is True and
            r.get("feature_inputs_complete") is True and number(r.get("projection")) is not None and
            number(r.get("p90")) is not None for r in rows)},
        "ownership_coverage": {"population": "certified_generation_pool", "required_players": len(eligible), "complete_players": sum(
            str(r.get("player_id")) in eligible and ownership_valid(r) for r in rows)},
        "market_coverage": {"required_game_ids": sorted(represented_games),
            "covered_game_ids": sorted({e["game_id"] for e in checks["market"]["evidence"]})},
        "salary_provenance": deepcopy(evidence.get('salary_provenance', {})),
        "projection_lineage": deepcopy(lineage), "source_manifest_sha256": digest(manifest),
        "refresh": deepcopy(refresh or {})}


def freeze_evidence(rows, readiness, *, optimizer_run_id, evidence, role_context=()):
    if readiness["status"] != "READY": raise ClassicDataNotReady(readiness)
    value = {"contract_id": FROZEN_CONTRACT, "optimizer_run_id": optimizer_run_id,
        "frozen_at": readiness["evaluated_at"], "evidence_cutoff": readiness["evidence_cutoff"],
        "data_readiness": deepcopy(readiness), "player_pool": deepcopy([r for r in rows
            if str(r.get("player_id")) in readiness["generation_eligible_player_ids"]]),
        "audited_salary_pool": deepcopy(rows),
        "role_context": deepcopy(list(role_context)), "canonical_evidence": deepcopy(evidence)}
    value["sha256"] = digest(value)
    return value


def validate_frozen_evidence(value):
    if value.get("contract_id") != FROZEN_CONTRACT or value.get("sha256") != digest({k: v for k, v in value.items() if k != "sha256"}):
        raise ValueError("Frozen Classic evidence checksum mismatch")
    if value["data_readiness"]["status"] != "READY": raise ClassicDataNotReady(value["data_readiness"])
    return value["data_readiness"]


def annotate_entry_report(report, readiness):
    """Keep source readiness separate from final submission clearance."""
    result = deepcopy(report)
    checks = result.setdefault("checks", {})
    for title, source in (("Salary/source freshness", "salary_pool"),
                          ("Availability evidence", "player_status"),
                          ("Prepared input dependency lineage", "projection")):
        check = readiness["required_sources"][source]
        checks[title] = {"status": "PASS" if check["status"] == "READY" else "BLOCKER",
            "reason": f"Verified before generation under {CONTRACT}; original source clocks and IDs frozen."}
    checks["Current weather evidence"] = {"status": "NOT_REQUIRED_BY_CURRENT_MODEL", "reason": WEATHER["explanation"]}
    checks["Current entry availability clearance"] = {"status": "UNEVALUATED",
        "reason": "Generation inputs passed; final game-day entry clearance remains a separate check."}
    checks["Upstream market quote publication freshness"] = {"status": "INFORMATIONAL",
        "reason": "Freshness uses the frozen provider observation clock; upstream quote publication time is unknown."}
    result["generation_readiness"] = {"contract_id": CONTRACT, "status": readiness["status"],
        "evaluated_at": readiness["evaluated_at"], "evidence_cutoff": readiness["evidence_cutoff"]}
    result["status"] = "BLOCKED" if any(c["status"] == "BLOCKER" for c in checks.values()) else "ENTRY_CLEARANCE_PENDING"
    result["entry_ready"] = False
    result["reasons"] = [c["reason"] for c in checks.values() if c["status"] not in {"PASS", "NOT_REQUIRED_BY_CURRENT_MODEL"}]
    return result


def assess_current_inputs(service, *, season, week, slate, projection_run_id):
    from ..config import get_settings
    from .optimizer import _json_safe
    from .player_roles import resolve_player_roles
    now = datetime.now(UTC)
    pool = service._load_player_pool(season, week, slate, projection_run_id=projection_run_id, evidence_cutoff_at=now)
    contexts = pool.attrs.pop("role_context", [])
    pool, _ = resolve_player_roles(pool, contexts=contexts)
    pool.attrs = {}
    evidence = read_evidence(service, season=season, week=week, slate=slate,
                             projection_run_id=projection_run_id, cutoff=now)
    return evaluate_readiness(_json_safe(pool.to_dict("records")), season=season, week=week, slate=slate,
        projection_run_id=projection_run_id, evidence_cutoff=now, evaluated_at=now,
        rules=freshness_rules(get_settings()), evidence=_json_safe(evidence))
