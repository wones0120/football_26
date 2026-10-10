"""Report immutable kicker-role replays and compare the saved production rebuild."""
from __future__ import annotations
from collections import Counter
from itertools import combinations
from pathlib import Path
from statistics import mean
import hashlib
import pulp
from backend.app.product_services.showdown_portfolio_selection import candidate_metrics, signature
from scripts.run_showdown_qb_policy_experiment import read, write, solver, POLICIES, TEAM_LIMITS

D = Path('artifacts/kicker_role_audit')
OLD = Path('artifacts/showdown_qb_policy_controlled/2026w4-monday-2771d4f1')
NAMES = ['Bijan Robinson', 'Tyler Shough', 'Michael Penix Jr.', 'Chris Olave', 'Charlie Smyth', 'Daniel Carlson', 'Nick Folk']


def summary(lineups, selector=None):
    metrics = [candidate_metrics(lineup) for lineup in lineups]
    exposure = Counter(row['name'] for lineup in lineups for row in lineup)
    rosters = [set(row['player_id'] for row in lineup) for lineup in lineups]
    return dict(count=len(lineups), avg_mean=mean(row['mean'] for row in metrics),
        avg_p90=mean(row['p90'] for row in metrics),
        portfolio_selector=selector if selector is not None else sum(row['selector'] for row in metrics),
        exposure={name:exposure[name] for name in NAMES},
        captains=dict(Counter(row['captain_name'] for row in metrics)),
        team_splits=dict(Counter(row['team_split'] for row in metrics)),
        avg_overlap=mean(len(left & right) for left,right in combinations(rosters,2)))


def exact_selector(run, universe):
    report=run['selection_report']; allow,maximum=POLICIES[run['policy']]
    eligible=[r for r in universe['rows'] if (allow or r['captain_position']!='QB') and r['qb_count']<=maximum
        and max(r['team_counts'].values())<=TEAM_LIMITS.get(run['policy'],5)
        and r['mean']>=.95*report['best_mean']-1e-8 and r['p90']>=.95*report['best_p90']-1e-8]
    params=run['selection_kwargs']; model=pulp.LpProblem('AuditExactPortfolioSelector',pulp.LpMaximize)
    xs=[pulp.LpVariable(f'entry_{i}',cat='Binary') for i in range(len(eligible))]
    model+=pulp.lpSum(xs)==len(run['selected'])
    for pid,limit in params['player_limits'].items():
        model+=pulp.lpSum(x for x,r in zip(xs,eligible) if pid in r['player_ids'])<=limit
        model+=pulp.lpSum(x for x,r in zip(xs,eligible) if pid==r['captain_player_id'])<=params['captain_limit']
    model+=pulp.lpSum(x*r['selector'] for x,r in zip(xs,eligible))
    assert model.solve(solver())==pulp.LpStatusOptimal
    return pulp.value(model.objective)


def main():
    archive=read(D/'historical_audit.json'); job=read(D/'final_job.json')
    ref=archive['reference_run'][0]; previous=ref['constraint_config_json']['strategy_runtime']['showdown_portfolio_policy']['candidate_selection']
    prior_selector=sum(r['selector'] for r in previous['ranked_metrics'] if r['rank'] in previous['selected_ranks'])
    before=summary([r['players'] for r in archive['reference_lineups']],prior_selector)
    production_report=job['params']['strategy_runtime']['showdown_portfolio_policy']['candidate_selection']
    after=summary(job['results'], production_report['selected_portfolio_selector'])
    universe=read(D/'controlled/ranked-universe.json')
    policies={}
    for label in POLICIES:
        run=read(D/f'controlled/controlled-{label}.json'); old=read(OLD/f'controlled-{label}.json')
        feasibility=read(D/f'controlled/feasibility-{label}.json')
        optimal=exact_selector(run,universe); metrics=summary(run['selected'])
        gap = optimal - metrics['portfolio_selector']
        assert gap >= -1e-5
        print(label, 'selected', metrics['portfolio_selector'], 'exact', optimal, 'gap', gap, flush=True)
        policies[label]=dict(before=summary(old['selected']),after=metrics,
            exact_portfolio_selector=optimal, candidate_coverage_selector_gap=gap, feasibility=feasibility,
            selected=run['selected'],quality_best_mean=run['selection_report']['best_mean'],
            quality_best_p90=run['selection_report']['best_p90'])
    assert [signature(l) for l in job['results']]==[signature(l) for l in policies['A']['selected']]
    old_pool=read(D/'controlled/prepared_input.json')['player_pool']
    new_pool=read(D/'final_prepared_pool.json')
    assert {r['player_id'] for r in old_pool}=={r['player_id'] for r in new_pool}
    fresh=read(D/'rebuilt_projections.json')['records'];frozen=read(D/'controlled/input_freeze.json')['player_pool']
    source={r['player_id']:r for r in frozen}
    changed=[r['player_display_name'] for r in fresh if r['player_id'] in source and
        abs(r['predicted_mean']-source[r['player_id']]['projection'])>1e-6]
    assert changed==['Charlie Smyth']
    assert abs(after['portfolio_selector']-policies['A']['after']['portfolio_selector'])<1e-5
    write(D/'comparison_verified.json',dict(reference_run_id=ref['optimizer_run_id'],
        corrected_run_id=job['job_id'],corrected_projection_run_id=job['projection_run_id'],
        before=before,after=after,policies=policies,production_matches_frozen_A=True,
        changed_projections_vs_control=changed,player_pool=new_pool))
    out=['# Showdown kicker role audit', '',
        'The defect was missing current kicking-role eligibility. Smyth’s projection was his own 2025 history, not Carlson’s copied projection. The slate-agnostic gate now excludes him, identifies Carlson/Folk, and produces five corrected production entries without changing portfolio balancing.', '',
        f"Saved optimizer: `{job['job_id']}`. Projection: `{job['projection_run_id']}`. Reference: `{ref['optimizer_run_id']}`.", '',
        '## Root cause and available evidence', '',
        '- There was no starting-kicker identity table/filter. The starter workflow and ranked nflverse capture were QB-only; the Showdown opportunity gate applies to RB/WR/TE. Multiple same-team kickers could remain eligible.',
        '- Week 4 raw weekly roster records, joined through canonical nflreadpy GSIS aliases, list Smyth `DEV`, Carlson `ACT`, Folk `ACT`. Their unranked `depth_chart_position=K` does not specify K1/K2. The optimizer’s older roster safety check reads the curated participation table, whose current-week team coverage was absent.',
        '- Current same-season prior FG/PAT usage exists: Carlson attempts 5/4/4 in Weeks 1/2/3; Folk 5/2/5. Smyth has no 2026 kicking usage. Older 2025 ability was incorrectly carried forward into a normal core exposure classification.',
        '- Smyth has six historical games: roll-three 12.0, roll-eight 9.3333; 60% × 12 + 40% × 9.3333 = 10.9333. Residual calibration added 5.64396 for P90 16.57729. Generic availability defaulted to 1; kicker starting probability/role was not gated.',
        '- A separate old fallback could also lend a peer kicker’s history to a no-history backup. New projections permit peer anchoring only for an expected primary; unsupported roles have zero mean and all quantiles. Shared-duty kickers require their own history.',
        '- Official Saints depth chart lists Carlson; its August 31 preseason report describes him ahead of Smyth. Public checks corroborate the local roster/usage evidence, but no current web chart was injected into historical replays. Sources: [Saints depth chart](https://www.neworleanssaints.com/team/depth-chart), [Saints preseason kicker report](https://www.neworleanssaints.com/news/kicker-daniel-carlson-made-most-of-limited-preseason-time-with-new-orleans-saints).', '',
        '## Gate contract', '',
        'Use sourced pregame primary duties, ranked K1, unique current active-roster kicker, then unique recent prior FG/PAT usage. Resolve by canonical IDs and normalized team across the entire evidence pool, including players absent from salaries. Never rank roles by salary or fantasy projection. Backups/unresolved identities are excluded with retained assessments and explicit reasons; missing/conflicting identity produces a warning. Explicit sourced replacement/shared duties are the exception. Receipts and observations must precede the selected projection cutoff; usage must precede the target week in the same season. No schema migration or dependency was needed.', '',
        '## Historical/current scope', '',
        'Before correction, 17 team/slate salary pools in 2024–2026 contained multiple kickers. These are exposure points, not proof that every backup was selected. All 10 persisted duplicate-kicker projection runs were 2026 Week 4 Monday ATL–NO. All 28 saved Smyth lineup appearances were on that slate. No saved lineup selected two kickers from the same team. Thus the current failure is confirmed; the inspected saved projections/lineups do not demonstrate another historical occurrence. Existing generic roster/availability exclusions sometimes protected historical pools; missing coverage left the structural gap. Full inventory: `artifacts/kicker_role_audit/database_evidence.json` and `historical_audit.json`.', '',
        '## ATL–NO comparison', '',
        'The original saved reference used an earlier projection run; several small non-kicker differences exist versus today’s local rebuild. Causal comparison uses the prior controlled experiment’s immutable freeze: every non-kicker projection and both primary-kicker projections remain identical. The fresh production result exactly matches corrected frozen Policy A. Salary identities/counts remain 55 raw rows; prepared eligibility falls from 20 to 19, with Smyth the only role removal.', '',
        '| Metric | Original saved reference | Corrected production |',
        '| --- | --- | --- |']
    for label,key in [('Entries','count'),('Average mean','avg_mean'),('Average P90','avg_p90'),('Portfolio selector','portfolio_selector'),('Average shared identities','avg_overlap')]:
        out.append(f"| {label} | {before[key]:.3f} | {after[key]:.3f} |")
    for name in NAMES:
        out.append(f"| {name} exposure | {before['exposure'][name]}/5 | {after['exposure'][name]}/5 |")
    out += [f"| Team splits | {before['team_splits']} | {after['team_splits']} |",
            f"| Captain distribution | {before['captains']} | {after['captains']} |", '',
        '**NO 4–2 remains the majority: 3/5 before and 3/5 after.** One former NO 5–1 entry becomes 3–3. This does not establish a universal team-split preference across games.', '',
        '| Kicker | Before mean / P90 | Rebuilt mean / P90 | Eligibility |', '| --- | --- | --- | --- |',
        '| Charlie Smyth | 10.933 / 16.577 | 0 / 0 | Excluded: backup without expected duties |',
        '| Daniel Carlson | 6.750 / 12.394 | 6.750 / 12.394 | Primary NO |',
        '| Nick Folk | 7.000 / 12.644 | 7.000 / 12.644 | Primary ATL |', '',
        '### Original five reference lineups', '',
        '| Entry | Captain | FLEX |', '| --- | --- | --- |']
    for original in archive['reference_lineups']:
        captain=next(r['name'] for r in original['players'] if r['roster_position']=='CPT')
        flex=', '.join(r['name'] for r in original['players'] if r['roster_position']=='FLEX')
        out.append(f"| {original['lineup_number']} | {captain} | {flex} |")
    out += ['', '### Five corrected lineups', '',
        '| Entry | Captain | FLEX | Salary | Mean | P90 | Selector | Split |', '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for i,lineup in enumerate(job['results'],1):
        m=candidate_metrics(lineup);flex=', '.join(r['name'] for r in lineup if r['roster_position']=='FLEX')
        m['selector']=candidate_metrics(policies['A']['selected'][i-1])['selector']
        out.append(f"| {i} | {m['captain_name']} | {flex} | {m['salary']:.0f} | {m['mean']:.3f} | {m['p90']:.3f} | {m['selector']:.3f} | {m['team_split']} |")
    out += ['', '### Prepared player pool', '', '| Player | Team | Position | Mean | P90 |', '| --- | --- | --- | --- | --- |']
    for row in sorted(new_pool,key=lambda r:(r['player_team'],r['position'],-r['projection'])):
        out.append(f"| {row['name']} | {row['player_team']} | {row['position']} | {row['projection']:.3f} | {row['p90']:.3f} |")
    out += ['', '## Corrected controlled QB-policy experiment', '',
        'All six policies use the same 19-player prepared football frame, seed 20261005, unchanged 95% joint mean/P90 quality screen, requested-count core/QB/punt/Captain caps, candidate-generation breadth and disabled scenario diversity. A–D change only QB eligibility; E/F retain the previously authorized team-cap challengers. No new balancing rule or automatic relaxation was applied.', '',
        '| Policy | QB Captain | Max QBs | Max/team | Entries | Mean | P90 | Overlap | Selector | Penix appearances |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for label,p in policies.items():
        s=p['after'];allow,max_qbs=POLICIES[label]
        out.append(f"| {label} | {'Yes' if allow else 'No'} | {max_qbs} | {TEAM_LIMITS.get(label,5)} | {s['count']}/5 | {s['avg_mean']:.3f} | {s['avg_p90']:.3f} | {s['avg_overlap']:.3f} | {s['portfolio_selector']:.3f} | {s['exposure']['Michael Penix Jr.']} |")
    out += ['',
        'A/B now select identical portfolios; C/D also select identical portfolios. All six select no two-QB entry. The prior two-QB/Penix tradeoff and Smyth-dependent bottleneck/relaxation conclusions are superseded. C/D still cannot reach five under the exact unchanged constraints: **Olave alone is mandatory in every quality-eligible roster, and his four-appearance cap prevents five entries.** Increasing only his cap to five is mathematically sufficient; the diagnostic quality-only five-entry threshold is now 93.934648%, not the old 94.443492%. These are diagnostics, not applied changes. Allowing Shough Captain also creates a five-entry witness; allowing only Penix Captain does not.', '',
        f"Exhaustive enumeration examined {universe['examined_salary_legal_rosters']:,} salary/team-legal signatures and certified {universe['certification_candidates']:,} retained signatures against the frozen production MILP. All policy raw maxima match their production candidate benchmark. Selected-versus-full-universe selector gaps by policy: { {label:round(p['candidate_coverage_selector_gap'],6) for label,p in policies.items()} }. These are candidate discovery gaps; no discovery or balancing changes were made. The archived PIT–CLE historical replay is unchanged; no duplicate projected kicker pool was found there, and this audit makes no new standings-success inference.", '',
        '## Validation and replay limits', '',
        '- Latest broader validation: 206 passed, 1 unrelated QB-starter expectation failed. `test_confirmed_starters_allow_partial_canonical_team_coverage` expects a missing team’s QB to fall back to salary; separate working-tree changes now forbid that fallback. This task did not change that QB policy or its test. Kicker tests (including mixed projected/unprojected salary rows, explicit backup duties, cutoff/known-kickoff rejection and no-history projection protection), calibration, pool safety, Showdown policies and production/research parity pass. `git diff --check` and Python compilation pass.',
        '- The original projection cutoff cannot be reconstructed from today’s replaced curated salary table; its raw source/frozen research frame remains preserved. Fresh projections use current local data. The frozen correction only changes kicking eligibility and asserts identical prepared inputs across all policies; fresh production asserts the same selected signatures and unchanged non-kicker projections versus that freeze.',
        '- Two intermediate local optimizer runs (`8143caff-ecfc-42bd-80ef-0b20b5eb0335`, `06d6f155-7d67-4f2e-886c-dcc466dfd284`) excluded all kickers because the new loader initially required every salary row to have a projection cutoff. They are superseded by the final run above. The fix uses available cutoffs, with a regression test; no records were deleted.',
        '- Existing stale market/final-clearance/native-draft-group warnings remain. The rebuild is a development preview and was not submitted. Original projections, lineups, raw snapshots and prior research were retained.', '',
        'Machine-readable comparisons, full player pool, all selected lineups, exact feasibility witnesses and checksum envelopes: `artifacts/kicker_role_audit/comparison_verified.json` and `artifacts/kicker_role_audit/controlled/`. The earlier `comparison.json` omitted persisted solver metadata and reported zero for the fresh selector; the verified comparison restores it from the saved selection report. Reproduction: `scripts/audit_kicker_roles.py`, existing `run_showdown_qb_policy_experiment.py`, `enumerate_showdown_policy_universe.py`, `audit_showdown_qb_policy_feasibility.py`, `rebuild_kicker_role_slate.py`, and `report_kicker_role_audit.py`.', '']
    Path('SHOWDOWN_KICKER_ROLE_AUDIT.md').write_text('\n'.join(out))
    manifest={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        Path('backend/app/product_services/kicker_roles.py'),Path('backend/app/product_services/optimizer.py'),
        Path('backend/app/product_services/predictions.py'),Path('backend/app/product_services/canonical_projection_inputs.py')]}
    key=hashlib.sha256(str(sorted(manifest.items())).encode()).hexdigest()[:12]
    write(D/f'code_manifest-{key}.json',manifest)
    print({'saved_run':job['job_id'],'before':before,'after':after,'production_matches_frozen_A':True})

if __name__=='__main__':main()
