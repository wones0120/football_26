"""Render the sourced role audit and frozen before/after research comparison."""
from collections import Counter
import json
from pathlib import Path
from statistics import mean

from scripts.audit_showdown_qb_policy_feasibility import diversity
from scripts.run_showdown_qb_policy_experiment import read, write, POLICIES, TEAM_LIMITS
from backend.app.product_services.showdown_portfolio_selection import signature

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "artifacts/current_slate_role_audit"
OLD = ROOT / "artifacts/showdown_qb_policy_controlled/2026w4-monday-2771d4f1"
NEW = D / "corrected_v2"


def fmt(value):
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items()) or "none"
    return str(value).replace("|", "/").replace("\n", " ")


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(fmt(v) for v in row) + " |" for row in rows])


def main():
    before = read(D / "current_before.json")
    after = read(NEW / "input_freeze.json")
    snapshot = read(NEW / "prepared_input.json")
    old_snapshot = read(OLD / "prepared_input.json")
    live = read(D / "live_corrected_portfolio.json")
    audit = live["params"]["strategy_runtime"]["current_slate_role_availability_audit"]
    bplayers = {r["player_id"]: r for r in before["player_pool"]}
    aplayers = {r["player_id"]: r for r in after["player_pool"]}
    facts = {r["player_master_id"]: r["evidence_json"] for r in after["pool_attrs"]["role_context"]}
    old_ids = {r["player_id"] for r in old_snapshot["player_pool"]}
    new_ids = {r["player_id"] for r in snapshot["player_pool"]}
    old_runs = {k: read(OLD / f"controlled-{k}.json") for k in POLICIES}
    runs = {k: read(NEW / f"controlled-{k}.json") for k in POLICIES}
    certificates = read(NEW / "corrected_feasibility.json")
    old_metrics = {k: diversity(r["selected"], old_snapshot) for k, r in old_runs.items()}
    metrics = {k: diversity(r["selected"], snapshot) for k, r in runs.items()}
    latest = read(D / "latest_saved_optimizer_before.json")
    latest_rows = read(D / "latest_saved_lineups_before.json")
    latest_lineups = [r["players"] for r in latest_rows]
    latest_metrics = diversity(latest_lineups, old_snapshot)
    latest_metrics["portfolio_selector"] = sum(r["objective_score"] for r in latest_rows)
    for metric in [*old_metrics.values(), *metrics.values(), latest_metrics]:
        metric["core_players"].sort(key=lambda row: row["player_id"])
    assert {signature(r) for r in live["results"]} == {signature(r) for r in runs["A"]["selected"]}
    # Persisted rosters are Captain-first; the solver value may remain on a
    # FLEX row. Read retained solve metadata rather than assuming row order.
    live_selector = sum(next(float(p["solver_objective_value"]) for p in lineup
                             if p.get("solver_objective_value") is not None) for lineup in live["results"])
    assert abs(live_selector - metrics["A"]["portfolio_selector"]) < 1e-6
    comparisons = []
    for row in audit["players"]:
        pid = row["player_id"]
        b, a = bplayers.get(pid, {}), aplayers.get(pid, {})
        comparisons.append({**row, "before_eligible": pid in old_ids, "after_eligible": pid in new_ids,
            "before_projection": b.get("projection", 0), "after_projection": a.get("projection", 0),
            "before_p90": b.get("p90", 0), "after_p90": a.get("p90", 0),
            "roster_status": facts.get(pid, {}).get("roster_status", b.get("player_status")),
            "game_active": facts.get(pid, {}).get("game_active"),
            "source_uris": facts.get(pid, {}).get("source_uris", [])})
    comparisons.sort(key=lambda r: (not r["after_eligible"], r["team"], r["position"], r["player"]))
    def prior_depth(row):
        prior = bplayers.get(row["player_id"], {})
        if row["position"] == "QB":
            return "starter" if prior.get("is_starting_qb") else "backup/no expected package"
        if row["position"] == "DST":
            return "team defense"
        return prior.get("pregame_role_label") or "unverified; no explicit starter/backup gate"
    calibration = read(D / "corrected_projection_run.json")["calibration_metrics"]
    allocations = calibration["pregame_context"]["allocations"]
    comparison = {"before_projection_run_id": before["projection_run_id"],
        "after_projection_run_id": after["projection_run_id"], "live_optimizer_run_id": live["job_id"],
        "players": comparisons, "before_policies": old_metrics, "after_policies": metrics,
        "latest_saved_before": latest_metrics, "feasibility": certificates,
        "opportunity_allocations": allocations, "entry_readiness": live["params"]["entry_readiness"]}
    write(D / "comparison_v2.json", json.loads(json.dumps(comparison)))
    text = ["# CURRENT SLATE ROLE AND AVAILABILITY AUDIT", "",
        "2026 Week 4 ATL–NO Monday Night Showdown. **BLOCKED — NOT ENTRY READY.** The corrected projections and a provisional three-entry portfolio are saved. No permanent QB, team-concentration, exposure, quality-floor, Captain, or portfolio-selector rule was changed.", "",
        "## Findings and football evidence", "",
        "- Charlie Smyth is on the Saints practice squad; Daniel Carlson is their listed primary kicker. Smyth is excluded and his mean/P90/Captain projection is zero. The Oct. 5 elevation announcement contains two defensive players and does not elevate Smyth. [Saints roster](https://www.neworleanssaints.com/team/players-roster/), [depth chart](https://www.neworleanssaints.com/team/depth-chart), [elevations](https://www.neworleanssaints.com/news/new-orleans-saints-roster-moves-announced-transactions-2026-nfl-week-4-elevations).",
        "- Travis Etienne Jr. is on IR. The official chart lists Alvin Kamara first, Kendre Miller second and CJ Donaldson third. The coach describes a committee led by Kamara/Miller with situational work for Donaldson. Kamara is an expected starter; Miller is a promoted committee backup. [Official backfield report](https://www.neworleanssaints.com/news/new-orleans-saints-running-back-depth-being-tested-early), [depth chart](https://www.neworleanssaints.com/team/depth-chart).",
        "- Etienne was already zero/ineligible in the frozen BEFORE pool. The missing correction was explicit downstream role/opportunity resolution, not a newly discovered removal of a positive Etienne projection.",
        "- The official charts support Shough/Penix as QB1, Folk/Carlson as K1, and the WR/TE depth roles below. Backup QBs have no sourced package and remain excluded. Active-roster WR Kevin Austin Jr. has a promotion; the model retains measured receiving usage without inventing a share of every missing receiver's targets. [Falcons chart](https://www.atlantafalcons.com/news/atlanta-falcons-week-4-depth-chart-vs-new-orleans-saints), [Falcons roster](https://www.atlantafalcons.com/team/players-roster/).",
        "- Noah Fant is questionable. Barion Brown practiced fully and has no game designation. Those facts do not establish final dressing or a specific snap share. No automatic Fant-to-Juwan/Delp projection transfer was applied. [Official injury report](https://www.neworleanssaints.com/news/injury-report-atlanta-falcons-vs-new-orleans-saints-2026-nfl-week-4-saturday).",
        "- Every one of the 55 canonical salary-pool players is assessed below. Sources resolve 52 identities using canonical aliases plus team and position. The remaining cases include team defenses and Zach Wood's salary TE versus official LS mismatch; Wood remains unavailable/quarantined. Salary presence never establishes participation. Source records outside this salary pool remain in the identity-review artifact.", "",
        "Availability 'rostered' means active-roster membership with final game clearance unknown. 'Active' is reserved for sourced game-active evidence (or the aggregate team defense). Expected starter/backup is a separate dimension. Unavailable players include IR/PUP/reserve and practice-squad players without a current elevation; uncertain depth is retained explicitly. No NFI-positive player was identified in this pool; the resolver rejects NFI generically.", "",
        "## CURRENT SLATE ROLE AND AVAILABILITY AUDIT — optimizer-eligible players", "",
        table(["player", "team", "position", "availability", "expected depth role", "starter evidence", "role change", "projection change", "optimizer eligibility", "confidence"],
              [[r["player"], r["team"], r["position"], r["role_availability"], r["expected_depth_role"],
                r["role_starter_evidence"] or "unresolved", r["role_change"] or "role verified; no numerical promotion asserted",
                f"{r['before_projection']:.3f} → {r['after_projection']:.3f}", "eligible (provisional)",
                r["role_confidence"] + ("; " + r["role_resolution_warning"] if r["role_resolution_warning"] else "")]
               for r in comparisons if r["after_eligible"]]), "",
        "## Full-pool availability and projection comparison", "",
        "BEFORE roles were not uniformly source-verified. The table reports the corrected source-backed depth classification rather than retroactively claiming that the old model had verified those roles. CPT fantasy mean/P90 is exactly 1.5× FLEX; the existing position-specific selector weight is separate and unchanged. Zero CPT values for excluded players do not authorize selection.", "",
        table(["Player", "Team / pos", "Roster status", "BEFORE depth assessment", "AFTER availability / depth", "Eligible before → after", "FLEX mean before → after", "FLEX P90 before → after", "CPT mean before → after", "CPT P90 before → after", "Confidence / unresolved issue"],
              [[r["player"], f"{r['team']} / {r['position']}", r["roster_status"] or "unresolved",
                prior_depth(r), f"{r['role_availability']} / {r['expected_depth_role']}", f"{r['before_eligible']} → {r['after_eligible']}",
                f"{r['before_projection']:.3f} → {r['after_projection']:.3f}", f"{r['before_p90']:.3f} → {r['after_p90']:.3f}",
                f"{1.5*r['before_projection']:.3f} → {1.5*r['after_projection']:.3f}", f"{1.5*r['before_p90']:.3f} → {1.5*r['after_p90']:.3f}",
                r["role_confidence"] + ("; " + r["role_resolution_warning"] if r["role_resolution_warning"] else "")]
               for r in comparisons]), "",
        f"Prepared eligible pool: **{len(old_ids)} → {len(new_ids)}**. Removed: {', '.join(bplayers[i]['name'] for i in sorted(old_ids-new_ids))}. Added: {', '.join(aplayers[i]['name'] for i in sorted(new_ids-old_ids))}. These include confirmed depth roles that previously failed the low-opportunity gate; a starter label does not itself inflate a projection.", "",
        "## Vacated opportunity and uncertainty", "",
        "The corrected allocator uses lagged full-team volume and measured player shares. It retains historical opportunity from excluded starters, never fills missing shares from salary, and leaves unsupported work unallocated. It preserves football estimates independently of user optimizer exclusions.", "",
        "The coach supports Kamara/Miller as carry recipients; he does not publish a numerical split. The provisional forecast allocates Etienne's 6.896 modeled carries across those two backs in proportion to their measured prior carries (62.67%/37.33%). This conserves that missing carry volume across a committee; it does **not** transfer 100% of Etienne's fantasy projection to Kamara. It is an explicit model assumption, not a sourced carry count. Other missing backs' work remains unallocated.", ""]
    for allocation in allocations:
        if allocation["team"] != "NO":
            continue
        text += [f"### NO {allocation['opportunity']} allocation", "",
                 table(["Player", "Prior modeled volume", "Vacated", "Received", "Corrected expected volume", "Supported recipient"],
                       [[aplayers.get(r['player_id'], bplayers.get(r['player_id'], {})).get('name', r['player_id']),
                         r['prior_volume'], r['vacated_volume'], r['received_volume'], r['expected_volume'], r['recipient_supported']]
                        for r in allocation['players'] if any(r[x] for x in ['prior_volume','vacated_volume','received_volume','expected_volume'])]), "",
                 f"Team reference volume {allocation['team_volume']:.3f}; allocated {allocation['player_projected_volume_sum']:.3f}; explicitly unallocated {allocation['unallocated_volume']:.3f}.", ""]
    text += ["Kamara's FLEX mean rises **7.438 → 8.768**, P90 **15.349 → 20.003**, and CPT mean **11.157 → 13.152**. Miller's mean changes **5.541 → 5.132** despite receiving some vacated carries because the old allocation inflated available-player shares; the corrected whole-team anchor is lower. Donaldson retains his measured situational role. Targets are not automatically increased; expected snap, route, goal-line and red-zone shares are unknown. Historical snap rates remain historical. The backfield uncertainty flags stay enabled and block entry-ready status.", "",
        "WR/TE missing targets are shown explicitly above. No full target redistribution is fabricated from IR/PUP/PS status alone. Official depth promotions inform eligibility and uncertainty; exact target/route/red-zone promotion remains evidence-dependent.", "",
        "## Controlled policy experiment — BEFORE vs AFTER", "",
        "One immutable corrected football snapshot is shared by A–F. CBC uses one thread and fixed seed 20261005. Quality floors, exposure caps, Captain limits, stack rules, objective weights and selector are unchanged. A allows QB CPT and up to two starting QBs; B allows QB CPT and one QB; C bans QB CPT and allows two QBs; D bans QB CPT and allows one QB. E/F allow QB CPT/two QBs with max-4/max-3 per team. A–D allow five per team.", "",
        "Mean/P90 below are average per-entry sums, including CPT scoring. **P90 is the sum of player marginal P90s, not a joint lineup or portfolio percentile.** Selector totals vary with entry count; per-entry selector is also shown. Overlap counts shared players without distinguishing CPT/FLEX. Exposure denominators use actual generated entries; unchanged caps still use the requested five-entry denominator.", "",
        table(["Policy", "Entries B→A", "Mean B→A", "P90 B→A", "Selector total B→A", "Selector/entry B→A", "Avg overlap B→A", "QB CPT B→A", "Two QB B→A"],
              [[k, f"{old_metrics[k]['generated']} → {metrics[k]['generated']}",
                f"{old_metrics[k]['avg_mean']:.3f} → {metrics[k]['avg_mean']:.3f}", f"{old_metrics[k]['avg_p90']:.3f} → {metrics[k]['avg_p90']:.3f}",
                f"{old_metrics[k]['portfolio_selector']:.3f} → {metrics[k]['portfolio_selector']:.3f}",
                f"{old_metrics[k]['portfolio_selector']/old_metrics[k]['generated']:.3f} → {metrics[k]['portfolio_selector']/metrics[k]['generated']:.3f}",
                f"{old_metrics[k]['avg_shared_players']:.3f} → {metrics[k]['avg_shared_players']:.3f}",
                f"{100*old_metrics[k]['qb_captain_exposure']:.1f}% → {100*metrics[k]['qb_captain_exposure']:.1f}%",
                f"{100*old_metrics[k]['two_qb_exposure']:.1f}% → {100*metrics[k]['two_qb_exposure']:.1f}%"] for k in POLICIES]), "",
        table(["Policy", "Team splits before → after", "Captain distribution before → after", "QB count before → after"],
              [[k, f"{fmt(old_metrics[k]['team_split_distribution'])} → {fmt(metrics[k]['team_split_distribution'])}",
                f"{fmt(old_metrics[k]['captain_distribution'])} → {fmt(metrics[k]['captain_distribution'])}",
                f"{fmt(old_metrics[k]['qb_count_distribution'])} → {fmt(metrics[k]['qb_count_distribution'])}"] for k in POLICIES]), "",
        "### Requested player exposures — fixed A controls", "",
        table(["Player", "Controlled BEFORE appearances / exposure", "Latest saved BEFORE appearances / exposure", "AFTER appearances / exposure"],
              [[name, f"{old_metrics['A']['player_appearances'].get(name,0)}/{old_metrics['A']['generated']} ({100*old_metrics['A']['player_appearances'].get(name,0)/old_metrics['A']['generated']:.1f}%)",
                f"{latest_metrics['player_appearances'].get(name,0)}/{latest_metrics['generated']} ({100*latest_metrics['player_appearances'].get(name,0)/latest_metrics['generated']:.1f}%)",
                f"{metrics['A']['player_appearances'].get(name,0)}/{metrics['A']['generated']} ({100*metrics['A']['player_appearances'].get(name,0)/metrics['A']['generated']:.1f}%)"]
               for name in ['Charlie Smyth','Alvin Kamara','Bijan Robinson','Tyler Shough','Michael Penix Jr.','Chris Olave']]), "",
        "### Exact feasibility, not candidate-discovery speculation", "",
        "The independent universe enumerated 583,690 salary-legal physical rosters, checked saved MILP constraints, and certified all signatures that could meet the 95% mean/P90 floors for each policy. A fresh joint MILP maximized fill first and selector second with unchanged caps. Every production replay matched its global optimum within floating-point tolerance. Thus underfill is genuine under these provisional forecasts and controls.", "",
        table(["Policy", "Exact max entries", "Complete quality signatures", "Mandatory players within quality universe", "Selector gap"],
              [[k, certificates[k]['exact_maximum_count'], certificates[k]['complete_quality_signatures'],
                '; '.join(f"{p['name']} (cap {p['cap']}/5)" for p in certificates[k]['mandatory_players']),
                certificates[k]['selector_gap_at_same_count']] for k in POLICIES]), "",
        "B/C/D/F are now constrained by Kevin Austin Jr.'s unchanged two-of-five cheap-player cap because every quality-eligible signature needs him. In A/E, the combined exposure/CPT caps limit the joint set even though no singly capped player is universal. Shough is universal in every corrected quality universe. The prior universal Olave+Smyth explanation for C/D no longer applies.", "",
        "## Which earlier conclusions changed?", "",
        "- **QB Captain:** materially input-sensitive. A now retains two Shough CPT entries in three, and C/D produce only two entries. B's corrected selector is lower than C/D at equal count even though its average mean/P90 is higher; permitting QB CPT alone is not a proven general advantage. The existing historical CPT prior was not retrained or invalidated by this prospective audit.",
        "- **Two QBs:** still materially useful in corrected A (two of three entries). B underfills more severely; C and D happen to select identical one-QB sets even though C permits two. This supports retaining the option for research, not a permanent blanket requirement.",
        "- **Max-4/team:** the corrected E challenger fills four entries versus A's three, with slightly lower average mean/P90 and lower overlap. It is no longer merely the earlier five-versus-five score/diversity comparison. This remains an experiment; no default was promoted.",
        "- **NO concentration:** persists after removing Smyth. Corrected A uses two 4-NO/2-ATL entries and one 5-NO/1-ATL; E is all 4-NO/2-ATL. Source-corrected Shough/Olave/Vele drive concentration, so the earlier NO leaning cannot be attributed entirely to the backup kicker. Its magnitude and recommended exposure are nevertheless input-sensitive and unvalidated.",
        "- **Premium players:** materially changed. Compare realized exposures above; Kamara now has a documented starting role and higher mean/ceiling, while Bijan/Penix allocations respond to the changed feasible set. Olave remains highly exposed without being universal in the whole corrected quality universe. Underfilled realized 100% exposure is not evidence that a five-entry 100% allocation is acceptable.",
        "These are conditional prospective comparisons, not causal single-player ablations. The broader corrected source layer and removal of salary-based opportunity inference changed multiple players at once. Repeated model conclusions based on the erroneous freeze should not be used to justify permanent portfolio-rule changes.", "",
        "## Saved build and separate latest-saved baseline", "",
        f"Controlled BEFORE projection `{before['projection_run_id']}`; corrected projection `{after['projection_run_id']}`; corrected persisted optimizer `{live['job_id']}`. The actual saved three-entry build matches corrected controlled A, including selector and physical signatures.", "",
        "A separate latest saved optimizer existed with a different projection ID when portfolio history was captured. It is retained below to avoid blending its results into the earlier controlled freeze:", "",
        table(["Baseline", "Projection", "Entries", "Mean", "P90", "Selector", "Overlap", "Captain distribution", "Team splits", "QB count"],
              [[latest['optimizer_run_id'], latest['projection_run_id'], latest_metrics['generated'],latest_metrics['avg_mean'],latest_metrics['avg_p90'],latest_metrics['portfolio_selector'],latest_metrics['avg_shared_players'],latest_metrics['captain_distribution'],latest_metrics['team_split_distribution'],latest_metrics['qb_count_distribution']],
               [live['job_id'],after['projection_run_id'],metrics['A']['generated'],metrics['A']['avg_mean'],metrics['A']['avg_p90'],metrics['A']['portfolio_selector'],metrics['A']['avg_shared_players'],metrics['A']['captain_distribution'],metrics['A']['team_split_distribution'],metrics['A']['qb_count_distribution']]]), "",
        table(["Saved corrected entry", "Captain", "FLEX"], [[i,next(p['name'] for p in lineup if p['roster_position']=='CPT'),
              ', '.join(p['name'] for p in lineup if p['roster_position']!='CPT')] for i,lineup in enumerate(live['results'],1)]), "",
        "## Entry-ready blockers and remaining validation", "",
        "Important promotion workload is unresolved for Kamara/Miller; Fant is questionable and Nick Muse lacks current depth evidence (both excluded by downstream gates). The readiness role check conservatively flags all four football-eligible unresolved cases, of which only Kamara/Miller survive to the final optimizer pool. Final game inactives, native DK draft-group confirmation, fresh market/quote and weather clearance, complete role ownership and contest assignment are not established. No CSV was submitted or entry-ready certification issued. The exact 2026 game state remains provisional pending final authoritative evidence.", "",
        "## Reproducibility and engineering validation", "",
        f"Football snapshot SHA256: `{snapshot['football_sha256']}`. Context run `eb6d2c89-d164-4484-acad-38a0d336be3d`; feature run `b08d6096-890e-4c98-b05d-459e236ee608`. Official source captures retain URLs, observation/receipt clocks, immutable HTML and hashes. Publication time is unknown where the page did not provide a reliable clock; current pages were not backdated. Replays use identical frozen inputs and do not write live optimizer runs. The accepted replay is `corrected_v2`; the earlier diagnostic `corrected` replay is explicitly superseded because missing cutoffs originally prevented full context attachment.", "",
        "Targeted backend validation: 161 tests passed across canonical inputs, role resolution, kicker roles, starters, optimizer mode and Showdown production/research parity. UI TypeScript/Vite build passed. All 13 report-renderer tests passed; the saved API response retains 55 audit rows and BLOCKED readiness. Final-code preparation reproduces the same football hash and complete solver model. Local runtime fingerprints are verified. Browser policy blocked local-file visual preview, so pixel-level layout inspection was not completed; the audit table has a horizontal-scroll container for narrow screens. Existing unrelated working-tree changes were preserved.", "",
        "Artifacts: [comparison JSON](artifacts/current_slate_role_audit/comparison_v2.json), [source observations](artifacts/current_slate_role_audit/official_observations.json), [identity review](artifacts/current_slate_role_audit/identity_review.json), [corrected frozen input](artifacts/current_slate_role_audit/corrected_v2/input_freeze.json), [exact feasibility](artifacts/current_slate_role_audit/corrected_v2/corrected_feasibility.json), [persisted portfolio](artifacts/current_slate_role_audit/live_corrected_portfolio.json).", ""]
    (ROOT / "CURRENT_SLATE_ROLE_AND_AVAILABILITY_AUDIT.md").write_text("\n".join(text))
    print("Rendered full 55-player audit, six policies and saved portfolio parity.")


if __name__ == "__main__":
    main()
