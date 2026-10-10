"""Nonbinding display derived exclusively from the packet's frozen evidence.

Called after quality assessment and selection. No research imports, current
source queries, scoring, feasibility claims or selection rules belong here.
"""
from collections import Counter
from datetime import datetime


def build_prelock_checklist(candidates, finalists, control, *, run, readiness, player_lookup, overlap):
    def qb_family(c):
        teams = sorted({p["team"] for p in c["players"] if p["position"] == "QB"})
        return "two_qbs" if len(teams) == 2 else f"one_qb:{teams[0]}" if teams else "zero_qbs"

    def summarize(rows):
        receiver_captains = [c for c in rows if c["construction"]["captain_position"] in {"WR", "TE"}]
        paired = sum(any(p["position"] == "QB" and p["team"] == c["construction"]["captain_team"]
                         for p in c["players"]) for c in receiver_captains)
        return {
            "count": len(rows),
            "captain_archetypes": dict(sorted(Counter(c["construction"]["captain_archetype"] for c in rows).items())),
            "qb_counts": {str(n): sum(sum(p["position"] == "QB" for p in c["players"]) == n for c in rows) for n in (0, 1, 2)},
            "team_splits": {s: sum(c["construction"]["team_split"].split()[0] == s for c in rows) for s in ("3-3", "4-2", "5-1")},
            "receiver_captain_pairings": {"with_own_qb": paired, "without_own_qb": len(receiver_captains) - paired},
        }

    eligible = [c for c in candidates if c["quality_eligibility"]["eligible"]]
    teams = sorted({p["team"] for c in candidates for p in c["players"]})
    families = ["zero_qbs", *(f"one_qb:{t}" for t in teams), "two_qbs"]
    family_rows = []
    for family in families:
        generated = [c for c in candidates if qb_family(c) == family]
        quality = [c for c in eligible if qb_family(c) == family]
        retained = [c for c in finalists if qb_family(c) == family]
        proposed = [c for c in control if qb_family(c) == family]
        stage = ("generation" if not generated else "quality_filtering" if not quality else
                 "finalist_selection" if not retained else "represented")
        reasons = (["not_present_in_saved_generated_pool", "generation_reason_unavailable"] if not generated else
                   sorted({reason for c in generated for reason in c["quality_eligibility"]["reason_codes"]}) if not quality else
                   ["eligible_family_outside_deterministic_finalists"] if not retained else [])
        family_rows.append({"family": family, "generated": len(generated), "quality_eligible": len(quality),
                            "finalists": len(retained), "proposal": len(proposed), "absence_stage": stage,
                            "reason_codes": reasons})

    ownership = readiness.get("ownership") or {}
    try:
        observed = datetime.fromisoformat(ownership.get("ownership_observed_at", "").replace("Z", "+00:00"))
        cutoff = datetime.fromisoformat(run["data_cutoff_at"].replace("Z", "+00:00"))
        clock_safe = bool(observed.tzinfo and cutoff.tzinfo and observed <= cutoff)
    except (ValueError, TypeError, AttributeError):
        clock_safe = False
    sourced = bool(ownership.get("ownership_fresh") and ownership.get("ownership_source")
                   and ownership.get("source_ids") and clock_safe)
    rows = []
    for c in candidates:
        value = c["metrics"].get("projected_total_ownership") if sourced else None
        rows.append({"candidate_id": c["candidate_id"],
                     "physical_player_ids": sorted(p["player_id"] for p in c["players"]),
                     "captain": c["construction"]["captain_player_name"],
                     "quality_eligible": c["quality_eligibility"]["eligible"],
                     "salary_left": c["construction"]["salary_remaining"],
                     "projected_total_ownership": value,
                     "ownership_unavailable_reason": None if value is not None else "fresh_sourced_frozen_ownership_unavailable"})
    return {"contract_id": "showdown_prelock_review_checklist_v1", "nonbinding": True,
            "evidence_basis": "frozen_prelock_candidate_packet", "data_cutoff_at": run["data_cutoff_at"],
            "evidence_sha256": readiness.get("evidence_sha256"),
            "incomplete_evidence": readiness.get("incomplete_evidence", True),
            "scopes": {"generated": summarize(candidates), "quality_eligible": summarize(eligible),
                       "finalists": summarize(finalists), "saved_proposal": summarize(control)},
            "qb_families": family_rows,
            "saved_generation_qbs": sorted({str(p["player_id"]) for p in player_lookup.values() if p.get("position") == "QB"}),
            "ownership_provenance": {"status": "available" if sourced else "unavailable",
                                     "sources": (ownership.get("ownership_source") or []) if clock_safe else [],
                                     "source_ids": (ownership.get("source_ids") or []) if clock_safe else [],
                                     "observed_at": ownership.get("ownership_observed_at") if clock_safe else None},
            "candidate_details": rows,
            "proposed_pair": {"basis": "saved_optimizer_control", "candidate_ids": [c["candidate_id"] for c in control],
                              "physical_player_overlap": overlap["shared_players"] if overlap else None,
                              "unavailable_reason": None if overlap else "saved_proposal_is_not_exactly_two_entries"},
            "limitations": ["Coverage is descriptive; no family quota, salary target or overlap cap is imposed.",
                            "Absent generated families do not establish infeasibility; the saved archive may not explain generation.",
                            "The saved proposal is the production control, not an inferred AI decision."]}


def checklist_markdown(checklist):
    lines = ["", "## Nonbinding prelock review checklist", "",
             "Frozen prelock evidence only. Review prompts do not change scores, eligibility or selection.",
             f"Cutoff: {checklist['data_cutoff_at']} · incomplete evidence: {checklist['incomplete_evidence']}", "",
             "| Scope | Captain archetypes | Zero / one / two QBs | 3–3 / 4–2 / 5–1 | WR/TE CPT own QB: with / without |",
             "|---|---|---|---|---|"]
    for scope, s in checklist["scopes"].items():
        lines.append(f"| {scope} | {s['captain_archetypes']} | {s['qb_counts']} | {s['team_splits']} | {s['receiver_captain_pairings']} |")
    lines.extend(["", "QB-family absence (generation versus quality filtering):"])
    for f in checklist["qb_families"]:
        lines.append(f"- {f['family']}: generated {f['generated']}, quality eligible {f['quality_eligible']}, finalists {f['finalists']}, proposal {f['proposal']}; {f['absence_stage']}; {', '.join(f['reason_codes']) or 'present'}")
    pair = checklist["proposed_pair"]
    lines.extend(["", f"Projected ownership provenance: {checklist['ownership_provenance']}",
                  f"Saved proposal physical-player overlap: {pair['physical_player_overlap']} / 6 ({pair['unavailable_reason'] or pair['basis']}).",
                  "For an AI-proposed pair, intersect the canonical physical_player_ids in candidate_details; Captain/FLEX changes do not make a different player.", "",
                  "| Candidate | Salary left | Sourced projected total ownership |",
                  "|---|---:|---:|"])
    proposal_ids = set(pair["candidate_ids"])
    for row in checklist["candidate_details"]:
        if row["candidate_id"] in proposal_ids:
            lines.append(f"| {row['candidate_id']} | {row['salary_left']} | {row['projected_total_ownership']} |")
    lines.extend(["", *checklist["limitations"], ""])
    return lines
