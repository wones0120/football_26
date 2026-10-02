#!/usr/bin/env python3
"""Render the Week 4 review document from frozen candidate and control evidence."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean

from backend.app.product_services.classic_prospective import digest_payload


def fmt(value, digits=3):
    return '—' if value is None else f'{value:.{digits}f}'


def depth_label(count, third_drop=None, fifth_drop=None):
    if count >= 5 and fifth_drop is not None and fifth_drop <= .10:
        return 'deep'
    if count >= 3 and third_drop is not None and third_drop <= .10:
        return 'moderate'
    return 'thin'


def correlation_total(row):
    return sum(row['components'].get(k, 0) for k in
               ('qb_stack', 'bring_back', 'game_environment', 'correlation', 'penalties', 'other_residual'))


def render(inputs, shadow, supplement):
    for record in (shadow, supplement):
        assert record['sha256'] == digest_payload({k: v for k, v in record.items() if k != 'sha256'})
    assert supplement['source_shadow_sha256'] == shadow['sha256']
    assert supplement['input_sha256'] == digest_payload(inputs)
    families = shadow['families']
    by_family = {f['thesis_id']: f for f in families}
    rows = {r['rank']: r for r in shadow['candidate_universe']}
    players = {p['player_id']: p for p in supplement['players']}
    source_report = inputs['report']
    saved = {r['rank']: r for r in source_report['all_candidates']}
    portfolios = shadow['shadow_portfolios']
    base = supplement['base']

    def label(f):
        return f"{f['qb']} {f['stack_family']}" + (' + BB' if f['bring_back_presence'] else ' / no BB')

    def names(ids):
        return ', '.join(players[pid]['name'] for pid in ids) or 'unchanged'

    def roster(row):
        return '; '.join(f"{pos}: {names([pid for pid in row['player_ids'] if players[pid]['position'] == pos])}"
                         for pos in ('QB', 'RB', 'WR', 'TE', 'DST'))

    def table(headers, entries):
        lines.extend(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'])
        lines.extend('| ' + ' | '.join(str(v) for v in entry) + ' |' for entry in entries)
        lines.append('')

    def vectors(f):
        risk = f['risk']
        return [f['peak_selector'], f['peak_mean'], f['peak_p90'], f['depth']['within_0.20'],
                correlation_total(rows[f['best_rank']]), -risk['best_elevated_dependencies'],
                -risk['best_availability_evidence_gaps'], -risk['best_fragile_cheap_dependencies'],
                risk['ownership_complete_rate']]

    dominators = {f['thesis_id']: [g for g in families if g is not f
        and all(a >= b - 1e-9 for a, b in zip(vectors(g), vectors(f)))
        and any(a > b + 1e-9 for a, b in zip(vectors(g), vectors(f)))] for f in families}
    lines = ['# Week 4 Dynamic Thesis Portfolio Shadow', '',
        '**Completed prospective analysis.** The frozen 205-candidate pool supports **three competitive QB directions** '
        '(Lawrence, Burrow, Brissett), expressed as **four competitive stack families**, across **two canonical games: '
        'JAX@CIN and ARI@NYG** at the 0.20 selector tolerance. It does not support five strong independent game environments.', '',
        'Brissett is a **GENUINE SALARY-EFFICIENCY THESIS** within the saved model: his weaker QB projection is offset '
        'by stronger non-QB allocation, especially McBride and the RB/WR core. Lawrence and Burrow still lead him on '
        'the existing selector. The recommended shadow five remain ranks **1, 6, 31, 48, 83**; the shadow 20 allocate '
        '**12 Lawrence, 4 Burrow, 4 Brissett**. These are prospective experiments, not validated contest-win claims.', '',
        '## Frozen evidence and production boundary', '',
        f"Source optimizer: `{shadow['source']['optimizer_run_id']}`. Source decision cutoff: "
        f"**{shadow['source']['decision_cutoff_at']}**. First saved kickoff: **{shadow['source']['first_kickoff_at']}**. "
        f"Supplement completed pre-lock: **{supplement['frozen_at']}**.", '',
        f"Candidate-universe SHA-256: `{shadow['source']['candidate_universe_sha256']}`. "
        f"Preserved v3 shadow SHA-256: `{shadow['sha256']}`. Completion supplement SHA-256: `{supplement['sha256']}`.", '',
        'The inputs are saved player IDs, projections, salaries, P90, ownership, pregame risk/market/context facts, '
        'and resolved solver configuration. All five saved scoring/solver file hashes match the source snapshot, '
        'and all 205 candidate selectors were replayed to within 1e-9. No live player refresh, outcomes, or postgame data '
        'was consulted. The redundant database `run_created_at` local-offset display is not the chronology authority; '
        'the saved UTC decision cutoff above is.', '',
        'Production stays at overlap **4**, distinct QB paths **true**, **205 candidates**, and selected ranks '
        '**31, 48, 83, 90, 93**. Projections, player P90, selector/correlation weights, ownership logic, candidate caps '
        'and questionable-player controls are unchanged. Forced/control rosters are diagnostics and never enter the '
        '205-candidate pool, production, or the frozen shadow portfolios.', '',
        'The immutable v3 database shadow is preserved. This completion is a separate hashed local supplement '
        'with its own pre-lock timestamp; it does not rewrite v3. The initial template-only opportunity-cost JSON '
        'is superseded by the v2 completion supplement, which also searches the saved hard stack rules.', '',
        '## Dynamic football discovery and interpretation', '',
        f"The pool discovers **{len(families)} stack families**, **{len({f['qb_id'] for f in families})} QB directions**, "
        f"and **{len({f['game_key'] for f in families})} primary canonical games**. No fixed number of theses is imposed.", '',
        'A broad football direction is canonical game + canonical QB ID. A construction family further records '
        'QB pass-catcher count and bring-back presence. Bring-back identities/counts and one-offs are variants. '
        'QB+2 and QB+3 Lawrence families remain one Lawrence passing direction. Lawrence/JAX and Burrow/CIN are '
        'different passing directions in **the same JAX@CIN game**. Mahomes/KC and Cousins/LV likewise share **KC@LV**. '
        'None are independent game environments merely because the quarterbacks differ.', '',
        'Market labels use only saved point-in-time-safe source evidence. “Passing thesis” identifies roster '
        'construction, not an inferred promise of a shootout. **All P90 totals below sum individual player P90s; '
        'they are not the 90th percentile of joint lineup outcomes.** Portfolio sums are descriptive totals, not '
        'probabilities or independent scenario counts.', '',
        '## Quality tolerance and thesis depth', '',
        'The global selector frontier is **5.606632** (rank 1). Tolerances are absolute selector-point losses, '
        'not percentages. A family is viable at a tolerance if at least one saved candidate lies inside it. '
        'Near-frontier depth labels are descriptive: ≥5 candidates = deep, 3–4 = moderate, 1–2 = thin, 0 = absent. '
        'Overall family labels also require selector depth: deep = ≥5 variants and best→5th drop ≤0.10; '
        'moderate = ≥3 and best→3rd drop ≤0.10; otherwise thin. These cutoffs are heuristics, not learned classes.', '']
    table(['Tolerance', 'Viable stack families', 'Viable QB directions', 'Canonical games', 'Candidates in window'],
          [[t, shadow['viability'][t]['qualified_count'],
            len({by_family[tid]['qb_id'] for tid in shadow['viability'][t]['qualified_theses']}),
            ', '.join(sorted({by_family[tid]['game'] for tid in shadow['viability'][t]['qualified_theses']})),
            sum(f['depth'][f'within_{t}'] for f in families)] for t in ('0.05','0.10','0.15','0.20')])
    lines += ['**The working observation is confirmed:** at **0.20**, the leading families are Lawrence QB+2/3 '
              'with bring-back, Burrow QB+2 with bring-back, and Brissett QB+2 without bring-back. At that boundary '
              'Brissett has only two qualifying variants; this is a thin near-frontier branch.', '']
    table(['Tolerance', 'Viable family / best global rank', 'Count in window', 'Window depth'],
          [[t, f"{label(by_family[tid])} / #{by_family[tid]['best_rank']}",
            (n := by_family[tid]['depth'][f'within_{t}']),
            'deep' if n >= 5 else 'moderate' if n >= 3 else 'thin']
           for t in ('0.05','0.10','0.15','0.20') for tid in shadow['viability'][t]['qualified_theses']])
    lines += ['### Every discovered family: viability, ranks and depth', '',
              'Counts .05/.10/.15/.20 explicitly encode viability at every tolerance: zero means no viable candidate. '
              'The rank columns use the saved global selector ordering. Labels describe internal depth; a deep family '
              'can still be far below the global frontier.', '']
    table(['Family', 'Game', 'N', 'Best selector', 'Ranks 1 / 2 / 3 / 5', 'Counts .05 / .10 / .15 / .20',
           'Drop best→3 / best→5', 'Depth'],
          [[label(f), f['game'], f['count'], fmt(f['peak_selector']),
            ' / '.join(str(f['depth']['ranks'][str(k)] or '—') for k in (1,2,3,5)),
            ' / '.join(str(f['depth'][f'within_{t}']) for t in ('0.05','0.10','0.15','0.20')),
            f"{fmt(f['depth']['selector_drop_to_3'])} / {fmt(f['depth']['selector_drop_to_5'])}",
            depth_label(f['count'], f['depth']['selector_drop_to_3'], f['depth']['selector_drop_to_5'])] for f in families])
    lines += ['### Every discovered family: projected quality', '',
              '“Best” means the selector-leading candidate. Best 3 and best 5 mean/P90 values average the first '
              '3/5 selector-ranked variants, using all available variants when fewer exist. Peak mean/P90 are '
              'separate maxima and may come from different rosters; they are not combined into a fictitious lineup.', '']
    table(['Family', 'Mean best / best 3 / best 5', 'P90 best / best 3 / best 5', 'Peak mean / P90'],
          [[label(f), ' / '.join(fmt(f['best_k'][str(k)]['mean'], 2) for k in (1,3,5)),
            ' / '.join(fmt(f['best_k'][str(k)]['p90'], 2) for k in (1,3,5)),
            f"{fmt(f['peak_mean'],2)} / {fmt(f['peak_p90'],2)}"] for f in families])

    lines += ['## Pareto / frontier evidence', '',
        'The preserved v3 screen compares peak selector, peak mean, peak P90, depth within 0.10, availability '
        'and ownership completeness. It marks Burrow and Lawrence QB+3 dominated because it does not treat '
        'correlation structure as a separate dimension. That is numerical dominance under those axes, not proof '
        'that the reverse passing direction has no football value.', '',
        'For this completed review, a second **correlation-aware Pareto screen** compares peak selector, mean, '
        'summed P90, depth within 0.20, best-candidate total rule contribution, elevated-player count, availability '
        'evidence gaps, cheap-role evidence gaps and ownership completeness. Higher quality/depth/rule contribution '
        'and lower gaps/dependencies are favored; every dimension must be at least as good, with one strict '
        'improvement, to dominate. Rule contribution is the existing QB-stack + bring-back + game + other '
        'correlation/penalty terms, not a new thesis score. This screen is diagnostic and does not rerun or rewrite '
        'the frozen v3 portfolio allocation.', '',
        'Positive correlation bonuses are selector-policy evidence, not empirical covariance estimates. Different '
        'stack/game structures remain interpretable dimensions; dominance is not a causal outcome claim.', '']
    table(['Family', 'Best rank', 'Selector gap', 'Rule total', 'Q elevated / availability gaps / cheap gaps',
           'Ownership coverage', 'Correlation-aware frontier'],
          [[label(f),f['best_rank'],fmt(f['global_selector_gap']),fmt(correlation_total(rows[f['best_rank']])),
            f"{f['risk']['best_elevated_dependencies']} / {f['risk']['best_availability_evidence_gaps']} / {f['risk']['best_fragile_cheap_dependencies']}",
            f"{f['risk']['ownership_complete_rate']:.0%}",
            'survives' if not dominators[f['thesis_id']] else f"dominated by {label(dominators[f['thesis_id']][0])}"] for f in families])
    reasons = {
        1:'best selector and deepest competitive family; strong mean with double-stack and bring-back support',
        13:'slightly more rule contribution from the third catcher (0.396 vs 0.390), preserving a defensible stack variant despite lower raw quality',
        48:'reverse CIN passing direction and the highest best-family rule contribution (0.407); a deep near-frontier hedge within JAX@CIN',
        83:'higher raw mean/P90 allocation than the leading selector roster and a second primary game, despite weaker context and correlation',
        85:'highest family peak mean/P90, but outside 0.20 and dependent on elevated availability evidence',
        90:'zero elevated dependencies/evidence gaps and a competitive KC stack rule contribution; outside the strong-quality window',
        94:'many KC variants with no elevated dependency in the best candidate and zero cheap-role gaps; lower selector but a depth/risk tradeoff',
        104:'BUF triple-stack rule support and no cheap-role gaps; outside 0.20',
        105:'BUF double-stack/bring-back depth with no cheap-role gaps; outside 0.20',
        111:'KC triple-stack contribution with zero elevated, availability or cheap-role gaps; only one candidate, outside 0.20',
        114:'higher raw mean in a KC single-stack with clean availability evidence; only one candidate, outside 0.20',
        115:'HOU passing construction with clean elevated/availability evidence and a relatively high rule contribution; thin and outside 0.20',
        118:'ARI single-stack/bring-back with clean elevated/availability evidence, retaining raw P90 support; thin and outside 0.20',
        158:'GB single-stack raw mean with clean elevated/availability evidence; thin and outside 0.20',
        159:'GB single-stack/bring-back raw P90 with clean elevated/availability evidence; thin and outside 0.20',
        164:'GB double-stack/bring-back balances more correlation contribution with clean elevated/availability evidence; thin and outside 0.20',
        172:'HOU single-stack/bring-back preserves more raw mean/P90 than its double-stack family with clean availability; thin and outside 0.20',
    }
    for f in families:
        if not dominators[f['thesis_id']]:
            lines += [f"- **{label(f)}:** remains on this frontier because {reasons[f['best_rank']]}. "]
    lines += ['', 'Exactly four correlation-aware survivors are inside 0.20, but only three QB directions and two '
              'games. Families outside the tolerance can be defensible on one dimension without being strong '
              'portfolio recommendations. Dominated rows above have an explicit witness and are not rewarded '
              'as new scenarios.', '', '## Why Brissett survives: QB opportunity cost', '',
              'Baseline is the strongest saved Brissett candidate, **rank 83**, salary **$49,900**, selector '
              '**5.425765**, mean **133.82**, summed P90 **231.33**. It uses Brissett + Michael Wilson + Trey McBride, '
              'no ARI–NYG bring-back, and an RB flex. Brissett’s saved QB values are **$5,000 / 16.40 mean / '
              '27.30 P90 / 1.81% ownership**. Rankings here use unrounded saved projections.', '']
    controls = [c for c in supplement['qb_controls'] if c['qb'] != 'Jacoby Brissett']
    table(['QB', 'Salary', 'Mean', 'P90', 'Ownership', 'Salary ↑ vs Brissett', 'Mean ↑', 'P90 ↑', 'Ownership ↑ (pp)'],
          [[c['qb'] + (' (highest projected viable)' if c['is_highest_projected_viable_qb'] else ''),
            players[c['qb_id']]['salary'],fmt(players[c['qb_id']]['projection'],2),
            fmt(players[c['qb_id']]['ceiling'],2),fmt(players[c['qb_id']]['ownership'],2)+'%',
            c['saved_allocation_delta']['qb_salary_saved'],fmt(c['saved_allocation_delta']['qb_mean_sacrificed'],2),
            fmt(c['saved_allocation_delta']['qb_p90_sacrificed'],2),
            fmt(c['saved_allocation_delta']['qb_ownership_difference_alt_minus_base'],2)] for c in controls])
    lines += ['Josh Allen is the highest-projected saved starting QB with a legal construction and a candidate '
              'in the frozen universe, so he also satisfies the highest-projected viable QB control. Ownership '
              'is diagnostic: all these QB values exist, while leverage weight is zero and soft ownership/chalk '
              'penalties are disabled. Lower Brissett ownership is not a hidden selector bonus.', '',
              '### Best saved lineup for each QB', '']
    table(['QB', 'Global rank', 'Mean', 'P90 sum', 'Selector', 'Stack', 'QB-stack / BB / other correlation',
           'All rule terms', 'Context'],
          [[r['qb']['name'],r['rank'],fmt(r['mean'],2),fmt(r['p90'],2),fmt(r['objective_score']),r['stack']['type'],
            ' / '.join(fmt(r['components'][k]) for k in ('qb_stack','bring_back','correlation')),
            fmt(correlation_total(r)),fmt(r['components']['context'])]
           for r in [base]+[c['saved_best'] for c in controls]])
    for c in controls:
        r = c['saved_best']
        lines += [f"- **{c['qb']} #{r['rank']}:** {roster(r)}."]
    lines += ['', '### QB sacrifice versus whole-lineup gains', '',
              'Positive gains below favor the Brissett baseline. These compare each QB’s saved best, allowing '
              'different stack/flex choices; the structure-preserving controls follow next.', '']
    table(['Opponent QB', 'QB mean sacrificed', 'Non-QB mean gained', 'Net lineup mean', 'QB P90 sacrificed',
           'Non-QB P90 gained', 'Net lineup P90', 'Selector Δ'],
          [[c['qb'],*[fmt(c['saved_allocation_delta'][k],2 if k!='net_selector_gain' else 3) for k in
            ('qb_mean_sacrificed','non_qb_mean_gain','net_mean_gain','qb_p90_sacrificed','non_qb_p90_gain',
             'net_p90_gain','net_selector_gain')]] for c in controls])

    lines += ['## Legal pay-up-at-QB counterfactual', '',
              'Each control forces the alternative QB and reoptimizes the rest legally. It preserves **QB+WR+TE, '
              'no bring-back, RB flex, and at least four of rank 83’s eight non-QB players**. The four-player '
              'retention rule is an explicit comparability heuristic. Salary ≤$50,000, exactly one TE, team ≤4, '
              'game ≤5, DST-opponent avoidance, punt limits, locks and at most one elevated-questionable player '
              'remain the saved rules. An additional free-structure solve tests sensitivity to these controls. '
              'CBC reports an optimal legal solution for each run. Candidate/portfolio exposure percentages apply '
              'to pools and portfolios; a single forced roster instead enforces the saved per-lineup risk rule.', '',
              'The Brissett control reproduces rank 83 exactly. Thus he remains optimal with his QB required even '
              'when stack size and flex may vary, rather than being an accident of his saved family representative.', '']
    table(['QB', 'Comparable mean', 'P90', 'Selector', 'Equivalent global rank', 'Salary', 'Original non-QBs retained',
           'Stack catchers', 'Rule total / context'],
          [[c['qb'],fmt((r:=c['comparable'])['mean'],2),fmt(r['p90'],2),fmt(r['objective_score']),
            r['equivalent_global_rank'],r['salary'],len(set(r['player_ids']) & (set(base['player_ids'])-{base['qb']['player_id']})),
            ', '.join(p['name'] for p in r['stack']['partners']),
            f"{fmt(correlation_total(r))} / {fmt(r['components']['context'])}"] for c in supplement['qb_controls']])
    lines += ['Equivalent global rank means one plus the count of saved candidates with a strictly better selector; '
              'it does not insert a new roster into the frozen universe.', '']
    for c in controls:
        lines += [f"- **{c['qb']} comparable:** {roster(c['comparable'])}."]
    lines += ['', '### Where the saved salary goes', '',
              'These are position-group differences for rank 83 minus each comparable pay-up roster. A positive '
              'salary amount means Brissett spends more at that position. Player switches also reflect stack '
              'requirements; the dollar savings are not a randomized causal effect. A negative projection gain '
              'is shown instead of pretending every position improves.', '']
    table(['Pay-up QB', 'Position', 'Brissett-only players', 'Pay-up-only players', 'Salary gained', 'Mean gained', 'P90 gained'],
          [[c['qb'],pos,names(d['base_only']),names(d['alternative_only']),d['salary_gain'],fmt(d['mean_gain'],2),fmt(d['p90_gain'],2)]
           for c in controls for pos,d in c['comparable_allocation_delta']['positions'].items()])
    lines += ['Salary accounting: the Brissett baseline leaves $100 unused; every comparable pay-up roster uses '
              '$50,000. Therefore his extra non-QB spend equals the QB savings **minus $100**. Against Allen, '
              '$2,700 QB savings become $2,600 non-QB spend: $1,200 at TE, $1,200 net at WR, $200 at RB. McBride '
              'replaces Kincaid (+4.33 mean/+6.42 P90); Nacua plus Ayomanor replace Shakir plus Robinson '
              '(+7.37/+7.37); Henry replaces Walker at a slight projection loss (−0.25/−0.25).', '',
              'Against Lawrence, the net $800 non-QB spend is **+$1,000 RB, +$3,300 TE, −$3,500 WR**. '
              'McBride over Strange gains 10.59 mean/12.68 P90 and Brown over Stevenson gains 4.89/7.38, '
              'while Ayomanor instead of Washington loses 9.71/12.73. This is salary allocation across an entire '
              'stack, not a claim that $900 alone purchases every named upgrade.', '']
    table(['Pay-up QB', 'QB salary saved', 'Non-QB spend ↑', 'QB mean sacrificed', 'Non-QB mean gained', 'Net mean',
           'QB P90 sacrificed', 'Non-QB P90 gained', 'Net P90', 'Selector Δ'],
          [[c['qb'],d['qb_salary_saved'],d['non_qb_salary_gain'],*[fmt(d[k],2 if k!='net_selector_gain' else 3) for k in
            ('qb_mean_sacrificed','non_qb_mean_gain','net_mean_gain','qb_p90_sacrificed','non_qb_p90_gain','net_p90_gain','net_selector_gain')]]
           for c in controls for d in [c['comparable_allocation_delta']]])
    lines += ['### Free-structure sensitivity and evidence classification', '']
    table(['Required QB', 'Free-structure selector', 'Equivalent rank', 'Stack', 'Mean / P90', 'Same as saved best?'],
          [[c['qb'],fmt((r:=c['relaxed'])['objective_score']),r['equivalent_global_rank'],r['stack']['type'],
            f"{fmt(r['mean'],2)} / {fmt(r['p90'],2)}",set(r['player_ids'])==set(c['saved_best']['player_ids'])] for c in supplement['qb_controls']])
    lines += ['**GENUINE SALARY-EFFICIENCY THESIS, conditional on the saved projections and roles.** '
              'Brissett sacrifices 2.19–6.08 QB mean points against the required alternatives. His legal comparable '
              'rosters gain 5.77–12.34 non-QB mean points, leaving 2.68–9.06 net mean gains. The summed-P90 '
              'accounting also stays positive. His rule and context bonuses are weaker, so his viability is '
              'primarily **salary allocation plus the projected Wilson/McBride stack**, not a correlation boost. '
              'He is not the selector winner: Lawrence’s comparable selector is 0.00884 higher; free-structure '
              'Lawrence and Burrow beat him by 0.18087 and 0.10292 respectively.', '',
              'Plain English: **the optimizer can buy enough extra projected production at tight end and the '
              'other non-QB positions to compensate for Brissett’s lower projection. It sees an affordable '
              'Wilson/McBride stack and a strong supporting roster. Paying more for the quarterback forces '
              'tradeoffs elsewhere.** This does not make Brissett a better real quarterback. His modest '
              'frontier depth and dependencies on Ayomanor’s cheap role and Nacua’s saved elevated-questionable '
              'status remain material. The comparison does not prove the projections or stack correlations are '
              'calibrated, and the arbitrary four-player core is tested by the free-structure sensitivity.', '',
              '## Dynamic shadow portfolios: 1, 3, 5, 10, 20', '',
              'Preserve the existing v3 joint solves. For each size, they maximize qualified non-dominated family '
              'coverage, then canonical game coverage, then the existing selector. They enforce saved player '
              'exposure (80% ordinary, 60% QB), questionable caps, at least two QB paths for multiple entries, '
              'and a shadow overlap cap of six. They try .05/.10/.15/.20, then the full saved pool if needed. '
              'No fixed five-family rule or equal allocation is imposed. Diversity credit remains limited to '
              'families whose best candidate is within 0.20.', '']
    table(['Entries','Tolerance','Selector total','Mean total','P90 total','Stack families / QB directions / games','Ranks'],
          [[n, p['quality_tolerance'] if p['quality_tolerance'] is not None else 'full saved pool',
            fmt(p['selector_sum']),fmt(p['mean_sum'],2),fmt(p['p90_sum'],2),
            f"{len(p['thesis_allocation'])} / {len(p['directional_qb_exposure'])} / {len(p['canonical_game_exposure'])}",
            ', '.join(map(str,p['selected_ranks']))] for n in (1,3,5,10,20) for p in [portfolios[str(n)]]])
    table(['Family','1 entry','3 entries','5 entries','10 entries','20 entries'],
          [[label(by_family[tid]),*[portfolios[str(n)]['thesis_allocation'].get(tid,0) for n in (1,3,5,10,20)]]
           for tid in sorted({tid for p in portfolios.values() for tid in p['thesis_allocation']},key=lambda tid:by_family[tid]['best_rank'])])
    lines += ['The 20-entry solve needs the full saved pool because the .20 window cannot fill all slots under '
              'the saved exposure constraints. Its ranks 103 and 109 fall outside .20 (gaps **0.311** and **0.315**). '
              'This is a disclosed quality relaxation within Brissett’s existing direction, not a weak fifth '
              'game introduced for diversity. The other 18 entries remain within .20.', '',
              '### The intended “five similar sets” concept', '',
              'This slate supports **three competitive broad passing directions**, with Lawrence split into two '
              'stack shapes. The 20-entry allocation is **10 Lawrence QB+2, 2 Lawrence QB+3, 4 Burrow QB+2, '
              '4 Brissett QB+2**. Thus there are four construction sets, three QB directions, and two primary '
              'games—not five independent sets of football outcomes. The weights emerge from selector quality, '
              'candidate availability/depth and exposure constraints rather than equal shares. They are '
              'constrained allocation results, not validated optimal betting fractions.', '']
    table(['Entries','Within-family avg / max','Across-family avg / max','Within pairs / across pairs'],
          [[n,f"{fmt(p['overlap']['within_average'],2)} / {p['overlap']['within_max'] or '—'}",
            f"{fmt(p['overlap']['across_average'],2)} / {p['overlap']['across_max'] or '—'}",
            f"{p['overlap']['within_pairs']} / {p['overlap']['across_pairs']}"] for n in (1,3,5,10,20) for p in [portfolios[str(n)]]])
    twenty = [rows[r] for r in portfolios['20']['selected_ranks']]
    within_qb, across_qb = [], []
    for i,a in enumerate(twenty):
        for b in twenty[i+1:]:
            (within_qb if a['qb_id']==b['qb_id'] else across_qb).append(len(set(a['player_ids'])&set(b['player_ids'])))
    lines += [f"Using the broader QB-direction definition, 20-entry overlap is **{mean(within_qb):.2f} average / "
              f"{max(within_qb)} max within direction**, and **{mean(across_qb):.2f} average / {max(across_qb)} max "
              'across directions**. Shared one-offs and the common game make these directions dependent; '
              'six shared players across some families remains substantial redundancy.', '',
              '## Five-entry shadow representatives and joint tradeoffs', '']
    why = {1:'highest selector; anchor double-stack construction',6:'second Lawrence double-stack at 0.028 cost; jointly legal distinct core',
           31:'triple-stack variant at 0.016 cost; avoids elevated-risk/core-cap conflict',
           48:'strong reverse CIN passing direction; deep quality',83:'competitive salary allocation and second primary game'}
    table(['Thesis','Canonical game','QB','Candidate rank','Selector','Mean','P90','Why selected'],
          [[r['stack_family']+(' + BB' if r['bring_back_count'] else ' / no BB'),r['game'],r['qb'],r['rank'],fmt(r['selector']),
            fmt(r['mean'],2),fmt(r['p90'],2),why[r['rank']]] for r in [rows[n] for n in portfolios['5']['selected_ranks']]])
    five = portfolios['5']
    table(['Overlap',*[str(n) for n in five['selected_ranks']]],
          [[a,*[len(set(rows[a]['player_ids'])&set(rows[b]['player_ids'])) if a!=b else '—' for b in five['selected_ranks']]]
           for a in five['selected_ranks']])
    lines += ['Taking each family’s #1 independently fails the joint constraints. Rank 13 (the triple-stack peak) '
              'would put Nacua in **3/5 entries**, above his saved **2/5 elevated-player cap**, alongside ranks 1 '
              'and 83. Rank 31 gives up **0.016291 selector**, drops that elevated dependency, and reduces average '
              'overlap against ranks 1/6/48/83 from **4.75 to 4.00**; maximum stays six. Rank 6 costs **0.028217** '
              'versus rank 1 and overlaps rank 1 by five; taking rank 1 twice would duplicate all nine players. '
              'These are joint legality/redundancy tradeoffs, not five independently chosen peaks.', '']
    for n in five['selected_ranks']:
        r=saved[n]
        lines += [f"- **{shadow['source']['optimizer_run_id']} / candidate rank {n}**, "
                  f"{label(by_family[rows[n]['thesis_id']])}; canonical roster SHA-256 "
                  f"`{digest_payload({'player_ids':sorted(r['player_ids'])})}`. {roster(r)}."]
    lines += ['', 'Saved candidates have no separate lineup UUID. Run UUID + complete candidate rank is the '
              'saved identifier; the canonical-ID roster hash disambiguates it. Full canonical player IDs '
              'are retained in the shadow JSON.', '', '### Exposures and totals', '']
    table(['Player','Shadow five','Saved production five'],
          [[players[pid]['name'],f"{five['player_exposure'].get(pid,0)}/5",f"{shadow['production_five']['player_exposure'].get(pid,0)}/5"]
           for pid in sorted(set(five['player_exposure'])|set(shadow['production_five']['player_exposure']),key=lambda pid:players[pid]['name'])])
    table(['QB direction','Shadow','Production'],
          [[q,f"{five['directional_qb_exposure'].get(q,0)}/5",f"{shadow['production_five']['directional_qb_exposure'].get(q,0)}/5"]
           for q in sorted(set(five['directional_qb_exposure'])|set(shadow['production_five']['directional_qb_exposure']))])
    table(['Primary canonical game','Shadow','Production'],
          [[g,f"{five['canonical_game_exposure'].get(g,0)}/5",f"{shadow['production_five']['canonical_game_exposure'].get(g,0)}/5"]
           for g in sorted(set(five['canonical_game_exposure'])|set(shadow['production_five']['canonical_game_exposure']))])
    game_counts = Counter()
    for n in five['selected_ranks']:
        game_counts.update({players[pid]['game_id'].split(' ',1)[0] for pid in rows[n]['player_ids']})
    lines += ['Primary-game exposure above counts the thesis anchor once per lineup. Full-roster game '
              'participation includes one-offs and DSTs and is: '+', '.join(f'{g} {n}/5' for g,n in sorted(game_counts.items()))+'. '
              'Those incidental games are not additional discovered primary thesis environments.', '',
              '### Objective production comparison', '',
              'Production uses the user’s overlap=4 and distinct-QB settings. The shadow allows repeat QBs and '
              'overlap=6. Higher shadow score describes that different feasible set; it does not establish that '
              'the user settings are wrong or that the shadow will perform better.', '']
    prod=shadow['production_five']
    table(['Metric','Production','Shadow','Shadow − production'],
          [[name,fmt(prod[k]),fmt(five[k]),fmt(five[k]-prod[k])] for name,k in
           [('Selector total','selector_sum'),('Projected mean total','mean_sum'),('Summed player P90 total','p90_sum')]])
    lines += [f"Production ranks **{prod['selected_ranks']}**, shadow ranks **{five['selected_ranks']}**. "
              f"Both have **{five['elevated_lineups']}/5 elevated-questionable lineups**. Production has five QB directions "
              'and three primary canonical games; shadow has three QB directions and two games. Shadow trades '
              'that broader game coverage for more of the saved selector-leading constructions.', '',
              '## Forced-inclusion diagnostics for zero-coverage players', '',
              'Every named player has **0/205** production candidate coverage. Each was forced by canonical ID '
              'under saved legal salary, stack, team, game, TE, DST and per-lineup risk constraints. The completed '
              'diagnostics optimize unrestricted saved hard stack rules **and every saved exact stack template**, '
              'then retain the best selector. This corrects the earlier JSN diagnostic: an allowed QB+3 '
              'construction achieves **5.429477**, rather than the template-restricted **5.402880**. Therefore '
              'JSN is within .20, and “below quality floor” is not a sufficient explanation for his absence.', '']
    table(['Player','Best legal QB / stack','Selector','Equivalent rank','Mean','P90','Frontier loss','Salary / unused',
           'Admission single-swap feasible?','Diagnostic classification'],
          [[d['player'],f"{(r:=d['best'])['qb']['name']} / {r['stack']['type']}",fmt(r['objective_score']),
            r['equivalent_global_rank'],fmt(r['mean'],2),fmt(r['p90'],2),fmt(r['frontier_loss']),
            f"{r['salary']} / {50000-r['salary']}",d['single_swap_cap_feasible'],d['cause']] for d in supplement['forced_diagnostics']])
    lines += ['Production admission recorded **286 legal inputs, 16 injury-count rejections, 65 residual '
              'admission exclusions, 205 accepted, 0 quality rejections, and 0 refill attempts**. The '
              '`rejected_by_player_cap` residual counter includes competition for the target count as well '
              'as caps; it is not a player-specific causal rejection log. The .20 quality floor used here '
              'is a shadow competitiveness criterion, not a hard production admission cutoff.', '',
              'The single-swap check establishes that one legal forced roster can replace some saved candidate '
              'without violating unchanged pool exposure caps. It rules out an absolute aggregate-cap '
              'prohibition for these five. It does not prove which seed solver branch originally omitted '
              'every possible alternative roster.', '']
    explanations = {
        'Jaxon Smith-Njigba':'**Candidate search omission / stack construction.** Two saved discovery injections '
            'already contained JSN, but neither survived joint target/cap/selector admission. His stronger forced '
            'Lawrence QB+3 shape was not in the final pool; exact QB+1/2 discovery is not exhaustive over '
            'three-catcher variants. The $9,100 salary displaces strong alternatives, but the best legal loss '
            'is only 0.177. Earlier “quality floor” attribution was too restrictive.',
        'Justin Jefferson':'**Candidate search omission, with a real availability constraint.** The saved '
            'structural discovery injections contain no Jefferson roster. He is Q/elevated, with uncertain '
            'workload and an evidence gap; his candidate cap is 25% and the per-lineup elevated limit is one. '
            'The required solve retains those controls, is inside .20, and can fit the unchanged pool by a '
            'single swap. The separate prospective shadow-generation arm had Jefferson exposure, confirming '
            'that generation method matters; it is not the frozen production universe. No hard ban explains zero.',
        'Bucky Irving':'**Candidate search omission.** No saved structural discovery injection includes Bucky. '
            'The forced roster is equivalent to rank 48, only 0.077 below the frontier, and fits a legal '
            'cap-preserving pool swap. His 90% candidate cap is not zero. The finite QB-shard/uniqueness '
            'search plus admission did not explore/retain this strong legal construction; no lack of legal '
            'rosters or hard quality exclusion is supported.',
        'Brock Bowers':'**Candidate search omission with salary opportunity cost.** No saved structural '
            'discovery injection includes Bowers. A $6,900 TE absorbs salary otherwise allocated to the '
            'supporting roster; nonetheless a required Lawrence double-stack is only 0.126 below the '
            'frontier and swap-feasible under his 90% candidate cap. Zero representation is not justified '
            'by a hard exposure/risk prohibition.',
        'Lamar Jackson':'**Quality floor for shadow viability; correlation structure and admission competition '
            'for production absence.** Five saved Lamar discovery injections were legal, then absent from '
            'the final 205. His strongest saved-rule forced roster is 0.488 below the frontier, with only '
            '0.042631 QB-stack support and no other active positive correlation terms. The saved BAL–TEN '
            'total is 43.5, and his saved mean is 16.92 despite a $7,300 salary. He cannot match the '
            'Lawrence/CIN stack contributions under these frozen values. This is model salary/stack '
            'opportunity cost plus joint admission competition, not reputation or no viable legal lineup.',
    }
    for d in supplement['forced_diagnostics']:
        lines += [f"### {d['player']}", '', explanations[d['player']], '',
                  f"Best legal diagnostic roster: {roster(d['best'])}.", '',
                  f"Canonical roster SHA-256: `{d['best']['roster_sha256']}`. "
                  f"Ownership completeness: {d['best']['ownership_sum'] is not None}. "
                  'It remains diagnostic only.', '']
    lines += ['The original solver branch/rejection lineage is not exhaustive enough to attribute every missing '
              'player to a single dollar or cap. The exact observable mechanics above replace “construction '
              'cause unisolated”; deeper causal separation would require a new generation/admission experiment '
              'while keeping this frozen pool unchanged.', '',
              '## Validation, saved artifacts and prospective limits', '',
              'The 14 focused thesis-shadow/completion tests passed. Completion validation replays all 205 saved scores, '
              'checks source/supplement hashes, checks each required player, validates every diagnostic/control '
              'roster and arithmetic, and compares production state before/after. A local completion manifest '
              'hashes this document and its evidence. The v3 database freeze and historical validation results '
              'reported in the prior handoff are preserved; no database append/update/delete is performed by '
              'this completion.', '',
              'Evidence files: `artifacts/week4-dynamic-thesis-shadow-8b5c114c.json` (preserved v3), '
              '`artifacts/week4-thesis-frozen-analysis-inputs-8b5c114c.json` (read-only export), '
              '`artifacts/week4-thesis-opportunity-cost-8b5c114c-v2.json` (authoritative completion supplement), '
              '`artifacts/week4-thesis-completion-manifest.json` (file hashes). The initial '
              '`week4-thesis-opportunity-cost-8b5c114c.json` is a superseded template-only diagnostic, '
              'not the final evidence for forced inclusion.', '',
              'These hypotheses are frozen pre-lock: membership, four tolerances, descriptive depth labels, '
              'Pareto axes, QB controls, shadow representatives and allocation. Future outcomes belong in a '
              'separate evaluation artifact and must not revise these decisions.', '',
              '## Required final answers', '',
              '### Does this slate support five genuinely strong directional theses?', '',
              '**NO.** Inside .20 there are four viable stack families, but only three broad QB directions '
              '(Lawrence/JAX passing, Burrow/CIN passing, Brissett/ARI passing). Brissett is thin at that '
              'quality boundary. Lawrence’s two stack shapes do not create two independent games.', '',
              '### How many genuinely distinct canonical game environments are represented?', '',
              '**Two primary environments: JAX@CIN and ARI@NYG** in the five- and twenty-entry shadows. '
              'The full candidate universe spans more games, and production also anchors KC@LV. Mahomes and '
              'Cousins are opposite directions within that same KC@LV environment.', '',
              '### Why is Brissett viable?', '',
              'His $5,000 salary and the projected Wilson/McBride stack leave room for enough non-QB '
              'production to offset the QB points sacrificed. Against Allen’s comparable legal roster, '
              'he gives up **6.08 QB mean** and gains **11.45 non-QB mean**, net **+5.37**; summed P90 '
              'is **+7.71**. Against Lawrence’s comparable roster, mean is **+2.68** and summed P90 '
              '**+4.24**, but the selector is **0.00884 worse**. He is competitive, not the overall winner.', '',
              '### Is Brissett’s viability driven primarily by QB value, salary allocation, stack quality, '
              'correlation, candidate-generation behavior, or a mixture?', '',
              '**Primarily salary allocation, supported by projected stack quality; a mixture with role/model '
              'dependencies.** His correlation/context bonuses are weaker than the leaders. Free-structure '
              'required-QB optimization reproduces rank 83, reducing the case for a pure candidate/selector '
              'artifact. Classification: **GENUINE SALARY-EFFICIENCY THESIS**, conditional on the frozen model.', '',
              '### If I entered exactly five lineups, which five shadow representatives would the thesis system choose?', '']
    for n in five['selected_ranks']:
        lines += [f"- `{shadow['source']['optimizer_run_id']}` / **candidate #{n}** — {label(by_family[rows[n]['thesis_id']])}, {rows[n]['game']}."]
    lines += ['', 'The complete rosters, canonical roster hashes, exposures and overlap matrix are listed above. '
              'These five remain shadow recommendations.', '',
              '### If I entered 20 lineups, how would the system allocate them by thesis?', '']
    for tid,n in portfolios['20']['thesis_allocation'].items():
        lines += [f"- **{n}** — {label(by_family[tid])}, {by_family[tid]['game']}."]
    lines += ['', '**Totals: 12 Lawrence, 4 Burrow, 4 Brissett; 16 JAX@CIN, 4 ARI@NYG.** '
              'Two Brissett entries require widening beyond .20. Four construction sets do not establish '
              'five independent football scenarios.', '',
              '### What is still heuristic or unvalidated?', '',
              '- Thesis boundaries, absolute tolerances, depth labels, Pareto axes and lexicographic priorities '
              'are pregame research choices, not learned contest-outcome rules.',
              '- The saved small-field strategy borrows the Classic large-GPP correlation policy, explicitly '
              'marked unvalidated for small fields. Rule bonuses are not calibrated joint outcome probabilities.',
              '- Summed player P90 is not lineup P90. No joint outcome simulation, covariance, field percentile, '
              'contest EV or confidence interval establishes superiority of these portfolios.',
              '- The 205-candidate universe is finite and generated by QB shards plus structural discovery and '
              'joint cap/target admission. Strong forced-inclusion omissions demonstrate incomplete search '
              'coverage. Diagnoses isolate legal feasibility and observable stages, not every hidden causal branch.',
              '- The four-non-QB comparability rule and RB-flex/WR+TE structure are heuristic. The free-structure '
              'sensitivity confirms the original QB peaks but does not isolate salary independently of teammates.',
              '- Availability uncertainty, cheap-role evidence gaps, ownership coverage and projection error '
              'remain. Brissett’s thin frontier depth and the relaxed two slots in the 20-entry portfolio matter.',
              '- Different portfolio constraints make production/shadow deltas descriptive. Actuals must be '
              'evaluated later in a separate time-safe artifact, without changing this pre-lock record.', '']
    return '\n'.join(line.rstrip() for line in lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--shadow',type=Path,required=True)
    parser.add_argument('--supplement',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    args.report.write_text(render(*[json.loads(p.read_text()) for p in (args.inputs,args.shadow,args.supplement)]))
    print(f'Wrote {args.report}: {sha256(args.report.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
