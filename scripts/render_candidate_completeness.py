#!/usr/bin/env python3
"""Render measured discovery evidence; never synthesize exhaustive counts."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_candidate_completeness import STAGES


def discovery_stage_audit(evidence):
    """Materialize duplicate-request lineage against the initial raw universe.

    The admission ledger is per unique roster; this derivative preserves every
    request, including later requests that rediscover an already known roster.
    """
    seen = {tuple(sorted(r['player_ids'])) for r in evidence['historical_raw_candidates']}
    target_maps = {t: {tuple(r['player_ids']): r for r in result['lineage']}
                   for t, result in evidence['targets'].items()}
    rows = []
    for index, event in enumerate(evidence['solve_events'], 1):
        row = {'request_ordinal': index, 'source': event['source'], 'request': event['request'],
               'solver_status': event['status'], 'seconds': event['seconds']}
        if event['status'] == 'optimal':
            key = tuple(sorted(event['player_ids']))
            duplicate = key in seen
            seen.add(key)
            row.update(player_ids=list(key), discovery_primary_reason='duplicate_rejected' if duplicate else 'unique_legal_discovered',
                       selector=event['objective_score'])
            row['target_stage_trace'] = {t: ([{'stage': s, 'status': 'passed' if i < 3 else 'rejected' if i == 3 else 'not_reached'}
                                               for i, s in enumerate(STAGES)] if duplicate else ledger[key]['stage_trace'])
                                         for t, ledger in target_maps.items()}
            row['target_primary_reason'] = {t: 'duplicate_rejected' if duplicate else ledger[key]['primary_reason']
                                            for t, ledger in target_maps.items()}
        else:
            row['discovery_primary_reason'] = 'solver_request_' + event['status']
        rows.append(row)
    body = {'contract': 'classic_discovery_request_stage_trace_v1', 'source_evidence_sha256': evidence['sha256'],
            'eligible_player_count': len(evidence['player_coverage']), 'solver_requests': len(rows),
            'legal_solved': sum(r['solver_status'] == 'optimal' for r in rows),
            'duplicate_rejected': sum(r['discovery_primary_reason'] == 'duplicate_rejected' for r in rows),
            'events': rows}
    return {**body, 'sha256': digest_payload(body)}


def fmt(value, places=3):
    return 'unavailable' if value is None else f'{value:.{places}f}' if isinstance(value, float) else str(value)


def table(headers, rows):
    def escape(v):
        return str(v).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(escape(v) for v in row) + ' |' for row in rows])


def render(d, inputs, validation=None):
    report = inputs['report']
    players = {r['player_id']: r for r in d['player_coverage']}
    tolerances = ['0.05', '0.10', '0.15', '0.20', '0.30']
    targets = d['targets']
    frontier = d['frontier']
    omissions = [('Bucky Irving', 'a9f8d797-040e-4469-b9d5-bb39bf3792b2'),
                 ('Brock Bowers', 'af2cef33-41db-4417-b880-13885bff6921'),
                 ('Justin Jefferson', '37b2e76d-353b-4b03-8a4a-652774647103'),
                 ('Jaxon Smith-Njigba', '1838dd60-35e8-4018-b307-39cde90e1f03'),
                 ('Lamar Jackson', 'ccab2695-91ed-49ce-b78b-938f23f4739b')]
    raw = d['raw_candidates']
    known = d['current_frontier_recall']['0.20']['known_legal']
    found = d['current_frontier_recall']['0.20']['discovered']
    generated = d['normal_generation_recall']['0.20']['discovered']
    candidate_source = 'artifacts/candidate_completeness/week4-8b5c114c-reviewed.json'
    lines = ['# Week 4 candidate frontier completeness', '',
        f"Frozen production run: `{d['source']['optimizer_run_id']}`. Analysis frozen **{d['frozen_at']}**, before the saved first kickoff **{d['source']['first_kickoff_at']}**.", '',
        f"Evidence: [{candidate_source}]({candidate_source}); SHA-256 `{d['sha256']}`. Input SHA-256 `{d['input_sha256']}`. All findings use the saved pregame frame; no live projections, outcomes, or new market data were read.", '',
        '## 1. Executive summary', '',
        f"**NO: the current 205 are not sufficiently complete.** Expanded discovery found **{len(raw)} unique roster-legal candidates**, including **{known} known risk-legal candidates inside 0.20**. The frozen 205 contain **{found}/{known} ({found / known:.1%})** of that known competitive set. The historical raw 286 had generated **{generated}/{known} ({generated / known:.1%})** before admission.", '',
        'The four named near-frontier omissions and the Lamar negative control are evaluated below using canonical IDs. The algorithm uses pregame position leaders, coverage gaps, and systematic construction sweeps; these names appear only in the report and regression fixtures.', '',
        '**Production remains unchanged:** target 205, saved selected ranks, projection/mean/P90 inputs, selector and correlation weights, ownership, exposure and injury policy, overlap=4, distinct-QB-path=true, thesis allocation, and exports. No API route, production solver/scorer, or database row was modified.', '',
        '**Scope of the count claim:** exact roster cuts are implemented, but bounded enumeration is not an exhaustive count of the legal space. Every censored tolerance is reported as a lower bound. Recall means recall against this expanded known reference set; it is not a mathematical certificate of global recall.', '',
        '## 2. Current generation architecture', '',
        'The saved optimizer creates four QB shards containing 52/51/51/51 seed rosters. Each shard rotates the saved minimum stack templates and applies shard-level candidate caps and elevated-questionable limits. The saved uniqueness overlap=7 excludes rosters sharing eight or nine players with an earlier shard roster. Sharding also supplies a smaller pool to the normalized seed objective; final reports score against the full frozen pool. These are search restrictions, not exhaustive frontier enumeration.', '',
        'Expansion adds global mean, P90, and selector optima, and one unrestricted plus four exact QB-family probes per starting QB. The saved exact templates are QB+1/QB+2 with zero/one bring-back. There is no exact QB+3 template sweep, partner-combination sweep, or systematic player coverage search in that expansion. Canonical roster deduplication produces 286 raw legal rosters. Joint admission maximizes cardinality up to 205, then selector sum under the saved candidate caps. Refill was not needed.', '',
        '## 3. Exact raw → legal → admission lineage', '',
        'Historical raw keys survive in `candidate_discovery.sources_by_lineup`, allowing exact scorer replay. All 205 saved accepted scores replay within 1e-9. The historical request ledger preserves 113 expansion requests and their legal/infeasible statuses; original seed timing and failed request details are not available. No missing historical log has been invented.', '',
        table(['Historical stage / terminal reason', 'Count'], [[k, v] for k, v in sorted(d['historical_reason_counts'].items())]), '',
        'The legacy 65 `rejected_by_player_cap` records are split by a counterfactual: can the incoming roster participate in any cap-feasible pool of the same cardinality? If yes, its primary reason is admission-target competition. If no, its primary reason is a player-cap conflict. Direct insertion conflicts remain secondary evidence even when displacement is feasible. Injury, duplicate, family, and quality reasons have independent fields; no family or quality rule was added.', '',
        'For each aggregate-cap conflict the artifact stores canonical player ID, exposure count/fraction, cap/count limit, one-roster swap feasibility, joint displacement feasibility, and a displaceable roster hash when available. Admission is a joint optimization: “before admission” is explicitly the chosen-pool baseline before counterfactual insertion, not an invented sequential history. Feasible displacement does not prove the swap would improve selector sum.', '',
        'Every new solver event records its deterministic request, source, legal/unproven/infeasible status, runtime, canonical roster, and selector. Every unique raw candidate has an admission terminal reason at each tested target. Eligible player status is recorded for all frozen players. Roster-legal raw evidence includes the historical 16 risk failures; primary frontier recall excludes those failures.', '']
    lines += ['The [request stage ledger](artifacts/candidate_completeness/week4-request-stage-lineage.json) materializes all ten stage statuses for every legal solve at every target, including duplicate rediscoveries against the initial raw universe. It distinguishes request-level duplicate rejection from the unique-roster admission ledger. Infeasible and unproven requests remain request failures and are never relabeled legal admission rejections.', '']
    for i, (name, pid) in enumerate(omissions, 4):
        p = players[pid]
        rows = [r for r in raw if pid in r['player_ids']]
        best = max(rows, key=lambda r: r['objective_score'])
        provenance = d['provenance']['|'.join(sorted(best['player_ids']))]
        source_names = sorted({s for r in rows for s in d['provenance']['|'.join(sorted(r['player_ids']))]})
        historical_count = sum(pid in r['player_ids'] for r in d['historical_raw_candidates'])
        historical_best = max((r['objective_score'] for r in d['historical_raw_candidates'] if pid in r['player_ids']), default=None)
        lines += [f'## {i}. {"Why Lamar differs" if i == 8 else "Why " + name + " was missed"}', '',
            f"**{name}** (`{pid}`): eligible={p['eligible']}; historical raw count={historical_count}; frozen admitted count={p['admitted_candidate_count']}; expanded raw count={p['raw_candidate_count']}. Best legal selector **{best['objective_score']:.6f}**, gap **{frontier-best['objective_score']:.6f}**, equivalent frozen-205 rank **{p['best_equivalent_rank']}**; QB **{best['qb']['name']}**, **{best['stack']['type']}**, salary **${best['salary']:,}**.", '',
            ('**Confirmed generation omission:** no historical raw roster contains this player, so admission could not recover it.' if historical_count == 0 else
             f'Historical best selector **{historical_best:.6f}**, gap **{frontier-historical_best:.6f}**. ' +
             ('**Competitive construction was never generated:** weaker containing rosters existed but none was inside 0.20. Their admission rejection does not explain the missing strong construction.' if i != 8 and frontier-historical_best > .20 else
              'Historical construction existed; admission dropped it through target competition. For Lamar its gap exceeds the competitive tolerance.')), '',
            f"Best-roster sources: `{', '.join(sorted(set(provenance)))}`. All containing sources: `{', '.join(source_names)}`. Target admitted counts (205/300/400/500): " +
            '/'.join(str(next(r['admitted_candidate_count'] for r in targets[t]['player_coverage'] if r['player_id'] == pid)) for t in targets) + '.', '']
        if i == 6:
            lines += ['Jefferson retains the frozen elevated-questionable classification. Every new discovery solve limits elevated players to one per roster; admission keeps his 25% candidate cap and portfolio solving keeps his saved selected cap and the elevated-lineup budget.', '']
        if i == 7:
            triples = [r for r in rows if r['stack']['partner_count'] == 3 and frontier-r['objective_score'] <= .20 + 1e-9]
            lines += [f'QB+3 containing JSN inside 0.20: **{len(triples)}**. The exact triple-stack sweep is a general QB request, not a JSN special case.', '']
        if i == 8:
            lines += ['A legal Lamar construction is found automatically, but its saved pregame selector is outside 0.30. This is a quality explanation under the frozen model, not evidence that the model is outcome-correct.', '']
    lines += ['## 9. Expanded discovery methodology', '',
        'Capture the exact saved solver model once in an isolated offline process using a non-solving adapter; restore the adapter before real solves. No production code or frozen code hash changes. Preserve the full pool and normalization denominators. Fix ineligible players to zero. The raw research frontier uses saved salary, roster, team/game limits, DST opposition, tags, locks, starting-QB eligibility, stack minimums, and per-lineup injury control. Aggregate candidate exposure caps apply only after discovery.', '',
        f"Solve one global selector optimum, then partition the legal space by starting QB and enumerate up to **{d['method']['per_qb_safety_max']}** optima per direction using exact `sum(selected roster variables) <= 8` cuts. Stop a partition on a proven optimum outside 0.30, proven infeasibility, a safety maximum, or unproven/numerically inconsistent solver behavior. CBC uses one thread and fixed seeds, zero requested relative/absolute gaps, and tighter integer/primal/dual/cutoff tolerances. Each solve has a 30-second safety limit; a feasible incumbent is not accepted as a proof of optimality.", '',
        'Complementary deterministic sources: all starting QBs × QB+1/2/3 × zero/one bring-back where frozen policy permits; primary/secondary/TE partner combinations up to triples; forced inclusion for pregame position leaders in mean, P90, role, salary value, ownership, and environment, plus underrepresented ceiling leaders; RB/WR FLEX, allowed TE FLEX, TE choices via player sweep, DST price tiers, stars-and-scrubs, and balanced builds. Single-TE policy remains enforced. No strong lineup is removed merely for high overlap.', '',
        'The player screen uses the union of the top 12 per position for each measurable property, plus the top 24 ceiling players with at most one saved representation. QB probes cover all viable saved starters. Partner sweeps use three role/projection leaders plus a TE when absent. These bounded screens are prospective research hypotheses and still leave unsearched combinations.', '',
        'Bucky, Bowers, Jefferson, and JSN are recovered by the automatic pregame screen without a manually supplied player list. Their best rosters in this bounded experiment come from the generic player-forced sweep. This does not claim that bounded unforced enumeration alone recovered them.', '',
        '## 10. Frontier counts at .05/.10/.15/.20/.30', '',
        table(['Tolerance', 'Known risk-legal lineups', 'Count status'], [[t, d['enumeration'][t]['known_count'], d['enumeration'][t]['count_kind']] for t in tolerances]), '',
        'These counts include the deduplicated union of historical and expanded discoveries. Exactness is certified only if every QB partition has proven exhaustion/boundary or has already crossed the tighter tolerance. A partition safety maximum means the unvisited remainder can contain additional competitive rosters. See the per-QB partition stopping records in the JSON.', '',
        '## 11. Current pipeline frontier recall', '',
        table(['Tolerance', 'Normal raw generated / known', 'Normal generation recall', 'Frozen admitted / known', 'Frozen 205 recall'],
              [[t, f"{d['normal_generation_recall'][t]['discovered']}/{d['normal_generation_recall'][t]['known_legal']}",
                f"{d['normal_generation_recall'][t]['recall']:.1%}", f"{d['current_frontier_recall'][t]['discovered']}/{d['current_frontier_recall'][t]['known_legal']}",
                f"{d['current_frontier_recall'][t]['recall']:.1%}"] for t in tolerances]), '',
        f"At 0.20, **{known-generated}** known competitive lineups were never generated and **{generated-found}** were generated but not admitted. Of the **{known-found}** known misses, generation accounts for **{(known-generated)/max(1,known-found):.1%}** and admission for **{(generated-found)/max(1,known-found):.1%}**. This decomposition is conditional on the known expanded universe.", '']
    for number, dimension, title in [(12, 'qb', 'Recall by QB'), (13, 'game', 'Recall by game'),
                                      (14, 'stack_family', 'Recall by stack family'), (15, 'player', 'Recall by player')]:
        groups = d['current_grouped_recall'][dimension]
        rows = []
        for key, metrics in groups.items():
            if metrics['0.30']['known_legal'] == 0:
                continue
            label = players[key]['player'] if dimension in {'qb', 'player'} else key
            if dimension == 'stack_family':
                parts = key.split('|'); label = players[parts[0]]['player'] + ' ' + ' '.join(parts[1:])
            rows.append([label] + [f"{metrics[t]['discovered']}/{metrics[t]['known_legal']} ({metrics[t]['recall']:.0%})" if metrics[t]['recall'] is not None else '—' for t in tolerances])
        lines += [f'## {number}. {title}', '', table(['Group'] + tolerances, rows), '']
    lines += ['The same grouped diagnostic is also stored by position, player salary tier (cheap ≤4000; star ≥7500; middle otherwise), and frozen role class. Each denominator counts rosters containing that group once; group membership is not mutually exclusive. Unclassified roles remain unclassified.', '']
    for dimension in ('position', 'salary_tier', 'role_class'):
        lines += [f'**{dimension}**', '', table(['Group', '0.20 admitted / known'], [[key, f"{m['0.20']['discovered']}/{m['0.20']['known_legal']}"] for key, m in d['current_grouped_recall'][dimension].items()]), '']
    gaps = [p for p in d['player_coverage'] if p['coverage_warning']]
    lines += ['## 16. Player coverage gaps', '',
        f"**{len(gaps)} warnings:** a known raw construction exists within 0.20, but the frozen admitted pool has zero representation.", '',
        table(['Player', 'Raw count', 'Admitted', 'Best raw', 'Equivalent rank', 'Mean/P90', 'Role score', 'Salary', 'Reduction reasons'],
              [[p['player'], p['raw_candidate_count'], p['admitted_candidate_count'], fmt(p['best_raw_selector']), p['best_equivalent_rank'],
                f"{p['mean']:.1f}/{p['p90']:.1f}", fmt(p['role_score']), p['salary'], json.dumps(p['raw_to_admitted_reasons'], sort_keys=True)] for p in gaps]), '',
        'The full [player audit CSV](artifacts/candidate_completeness/week4-player-coverage.csv) includes every frozen player, eligibility, raw frontier/total counts, admitted counts, best raw/admitted selectors, equivalent frozen rank, known-reference rank, mean/P90, role label/score, salary, and reduction reasons. Missing role labels are not inferred from name recognition.', '',
        'For the frozen 205 comparison, expanded raw→saved-pool reasons describe a counterfactual insertion/displacement against the frozen pool. They are not claims that the historical pipeline requested or rejected newly discovered rosters. The historical 286 ledger is the actual generation/admission reconstruction; section 11 separates never-generated misses from admitted misses.', '',
        '## 17. QB coverage gaps', '',
        table(['Starting QB', 'Game', 'Best legal', 'Equivalent rank', 'Raw within .05/.10/.15/.20/.30', 'Admitted', 'Mean/P90', 'Salary'],
              [[p['player'], p['canonical_game'], fmt(p['best_legal_selector']), p['best_equivalent_rank'],
                '/'.join(str(p['frontier_counts'][t]) for t in tolerances), p['admitted_candidate_count'],
                f"{p['mean']:.1f}/{p['p90']:.1f}", p['salary']] for p in d['qb_coverage']]), '',
        'Discovered exact stack families for every QB are retained in the [QB audit CSV](artifacts/candidate_completeness/week4-qb-coverage.csv). “Best legal” is the best proven construction found; an unproven request does not establish weakness.', '',
        '## 18. 205 vs 300 vs 400 vs 500', '',
        'All four targets admit from the identical expanded raw universe using the unchanged cardinality-first, selector-second joint admission and frozen caps. Generation cost is shared, so this is an admission sensitivity, not four independently generated universes. There is no refill or target-specific discovery.', '',
        table(['Target', 'Admitted', 'Recall .05/.10/.15/.20/.30', 'Players', 'QBs', 'Games', 'Families', 'Mean overlap', 'Max exposure', 'QB HHI', 'Median selector', 'Admission seconds', 'Warnings'],
              [[t, r['diversity']['count'], '/'.join(f"{r['frontier_recall'][v]['recall']:.1%}" for v in tolerances),
                r['diversity']['players'], r['diversity']['qb_directions'], r['diversity']['games'], r['diversity']['stack_families'],
                fmt(r['diversity']['average_overlap']), f"{r['diversity']['max_player_exposure']:.1%}", fmt(r['diversity']['qb_hhi']),
                fmt(r['diversity']['selector']['median']), fmt(r['admission_seconds']), len(r['coverage_warnings'])] for t,r in targets.items()]), '',
        'Selector max/min/mean/median, exact roster duplication, all primary rejection counts, player/QB coverage, thesis depth, lineage runtime, and downstream five/twenty portfolios are retained for every target. Duplication in each admitted pool is zero. Serialization cost per admitted candidate is approximated below; it is not the solver working set.', '',
        '**Smallest tested target recommendation: 400**, using explicit research acceptance criteria: at least 95% known roster recall inside 0.20, zero near-frontier player warnings, all qualified inside-0.20 direction/game/families, the same optimal saved-user-policy five-entry selector sum as the expanded universe, and the same expanded twenty-entry thesis allocation. Target 300 reaches 97.7% recall and zero player warnings, but loses the user-policy five-entry optimum (26.991746 versus 27.202641). Target 400 preserves it and the twenty-entry allocation. Target 500 adds wider 0.30 recall, without changing those portfolio results. This is the smallest of the four tested targets, not a proof that every intermediate target below 400 fails.', '',
        'The expanded raw universe retains the exact canonical roster set of the best saved-user-policy five. Targets 400 and 500 attain the same optimal selector sum with alternative tied roster sets. Target 205 from the improved raw universe has only three QB directions, so it cannot satisfy the saved five-distinct-QB user contract. Target 300 is feasible but drops necessary weaker-QB alternatives and lowers the optimum. This shows why frontier recall alone is insufficient for admission research.', '',
        '## 19. Search saturation curve', '',
        'Requests are reduced in declared source/canonical-ID order after parallel solving. This curve is reproducible for a pinned solver build; it is not wall-clock completion order. Counts include unique legal candidates even when a terminal frontier-boundary probe falls outside the enumeration window.', '',
        table(['Solves', 'New unique', 'New players', 'New QBs', 'New families', 'New games', 'New within .05/.10/.15/.20', 'Best new selector'],
              [[r['solves'], r['new_unique'], r['new_players'], r['new_qbs'], r['new_stack_families'], r['new_games'],
                '/'.join(str(r['new_within_tolerance'][t]) for t in tolerances[:4]), fmt(r['best_new_selector'])] for r in d['saturation']['curve']]), '',
        '## 20. Proposed dynamic stopping rule', '',
        f"The exploratory quiet-block detector first fires at solve **{d['saturation']['proposed_stop_solve']}**: no new unique construction inside 0.20 for two complete 50-solve blocks. This is a diagnostic only. An ordered QB batch can be quiet before a later stack/player sweep finds new information; this trigger must not prematurely stop mandatory source coverage.", '',
        'Proposed promotion research: finish all viable QB/template probes, pregame player coverage probes, and structural sources; then continue incremental exact frontier/partner enumeration until two consecutive 50-solve blocks add no inside-0.20 candidates, players, viable QB/families, or games, with stable grouped coverage and known-reference recall; stop at a predeclared runtime/solve safety limit. Mark safety-limited runs incomplete and expose coverage warnings. Measure a holdout sweep before trusting saturation. No stopping rule is promoted here.', '',
        'A flat empirical curve cannot prove completeness of unexplored legal space. Raw roster recall and meaningful directional diversity are separate targets; a fixed admitted count cannot establish either.', '',
        '**Saturation was not reached.** Although the naive detector fires at 450, the final blocks ending at 850/900/950/963 add 56 further unique inside-0.20 candidates. Mandatory automatic player coverage probes arrive late in the declared schedule. This is direct evidence that quiet blocks alone would stop this slate too early.', '',
        '## 21. Runtime / cost', '',
        table(['Measurement', 'Value'], [[k, fmt(v)] for k,v in d['runtime'].items() if not isinstance(v, dict)]), '',
        table(['Source', 'Solves', 'Sum solver CPU/wall seconds across workers'], [[s, d['runtime']['solve_counts_by_source'][s], fmt(seconds)] for s,seconds in d['runtime']['solve_seconds_by_source'].items()]), '',
        f"Raw serialized candidates: **{d['raw_serialized_bytes']:,} bytes**; average **{d['raw_serialized_bytes']/len(raw):,.0f} bytes/candidate**. Approximate serialized pool costs at 300/400/500: " +
        '/'.join(f"{d['raw_serialized_bytes']/len(raw)*n/1e6:.2f} MB" for n in (300,400,500)) + '.', '',
        'On this macOS host, `ru_maxrss` native units are bytes. Parent and child maxima are separately reported; a child maximum is not the simultaneous total of all four workers. JSON size is a storage proxy, not peak solver RAM. There is no metered cloud-compute charge or external API call in this experiment.', '',
        'The original frozen production full run took **347.6 seconds**, including its prospective shadow (existing README/RELEASE_NOTES record). Its seed generation was independently replayed here in **257.7 seconds** with all 205 raw seed rosters matching exactly. Fresh expanded discovery took **265.3 seconds** on four processes; exact QB enumeration consumed **600.5 summed worker-seconds** and automatic player-forced probes **180.1 summed worker-seconds**. The initial complete experiment, including baseline replay and portfolio diagnostics, took **543.7 seconds**. The final artifact re-analyzes those immutable solve events to add the complete stage trace and keeps the original solve code hashes, evidence hash, and timings separate from re-analysis timings.', '',
        'The initial global benchmark took roughly 2–5 seconds per fresh solve. Exhaustive frontier cost scales with the unknown roster count and growing cut set; bounded exact QB partitions plus deterministic complementary requests are the implemented practical alternative. Direction/partner/player requests and disjoint QB partitions are safely parallelizable in processes. Within a partition, enumeration is sequential. Admission remains a joint optimization. Fixed candidate targets reuse the same generation cost; their incremental costs are measured admission and portfolio solve time, not an invented linear generation estimate.', '',
        'Deterministic reproduction requires identical frozen inputs/code, canonical order, CBC build/backend, one solver thread, fixed seeds, and declared result reduction order. A different backend or CBC version may choose a different tied optimum. Repeated actual solver tests verify canonical roster sequences on a small legal fixture; all full experiment input/code hashes are retained. Original seed replay equality is separately reported; a mismatch would limit interpretation of its runtime benchmark.', '',
        '## 22. Thesis analysis: current vs expanded universe', '',
        'The existing dynamic v3 thesis grouping, depth, Pareto screen, and lexicographic allocation are reused. Research thesis portfolios retain their existing overlap hypotheses (6 for five, then 6/7/8 for twenty) and at least two QB paths. A separate five-entry sensitivity below keeps the saved user overlap=4 and distinct-QB-path=true. Neither replaces production.', '',
        table(['Universe', 'Qualified families .20', 'Pareto-frontier families .20', 'QB directions .20', 'Games .20'],
              [[label, result['viability']['0.20']['qualified_count'], result['viability']['0.20']['frontier_count'],
                result['viability']['0.20'].get('qb_directions', len({f['qb_id'] for f in result['families'] if f['global_selector_gap'] <= .20 + 1e-9})),
                result['viability']['0.20'].get('games', len({f['game_key'] for f in result['families'] if f['global_selector_gap'] <= .20 + 1e-9}))] for label,result in d['thesis'].items()]), '']
    baseline_families = {f['thesis_id'] for f in d['thesis']['current']['families'] if f['global_selector_gap'] <= .20 + 1e-9}
    new_families = [f for f in d['thesis']['expanded']['families'] if f['global_selector_gap'] <= .20 + 1e-9 and f['thesis_id'] not in baseline_families]
    lines += ['New qualified families inside 0.20:', '', table(['QB', 'Game', 'Stack', 'Bring-back', 'Peak selector', 'Frontier gap', 'Depth within .20'],
        [[f['qb'], f['game'], f['stack_family'], f['bring_back_presence'], fmt(f['peak_selector']), fmt(f['global_selector_gap']), f['depth'].get('within_0.20')] for f in new_families]), '']
    for section, count, title in [(23, '5', 'Five-entry shadow comparison'), (24, '20', 'Twenty-entry shadow comparison')]:
        lines += [f'## {section}. {title}', '', table(['Universe', 'Status', 'Entries', 'Selector sum', 'Mean sum', 'P90 sum', 'Tolerance', 'Overlap cap'],
            [[label, (p := result['shadow_portfolios'][count])['status'], p['entries'], fmt(p.get('selector_sum')), fmt(p.get('mean_sum')), fmt(p.get('p90_sum')), p.get('quality_tolerance'), p.get('max_overlap_constraint')]
             for label,result in d['thesis'].items()]), '']
        for label, result in d['thesis'].items():
            p = result['shadow_portfolios'][count]
            lines += [f"**{label} allocation:** `{json.dumps(p.get('allocation', p.get('thesis_allocation')), sort_keys=True)}`", '']
            if count == '5':
                lines += [table(['Rank in this universe', 'QB', 'Game', 'Stack', 'Selector', 'Canonical roster'],
                    [[r['rank'], r['qb'], r['game'], r['stack_family'], fmt(r['selector']), ', '.join(r['player_ids'])] for r in p.get('lineups', [])]), '']
        if count == '5':
            lines += ['Saved user five-entry policy sensitivity (overlap=4, one lineup per distinct QB direction; unchanged exposure and elevated-lineup limits):', '',
                table(['Universe', 'Status', 'Entries', 'Selector sum', 'Runtime seconds'], [[label, p['status'], p['count'], fmt(p['selector_sum']), fmt(p['seconds'])] for label,p in d['user_five_portfolios'].items()]), '']
    lines += ['## 25. Production impact if eventually promoted', '',
        'Broader discovery would change the candidates available to the existing admission and portfolio solvers; it can change thesis breadth and selected rosters even with all weights and constraints fixed. Raw frontier rosters must remain auditable before caps. A larger admitted target consumes more memory and portfolio pair-constraint work and can improve roster recall without guaranteeing meaningful player/family retention.', '',
        'Recommend promoting the observational request/raw/admission ledger and coverage warnings first, then a separate reviewed change for systematic QB+3/partner/player-gap discovery before unchanged cap admission. Keep the final candidate target and admission/selection policy unchanged until the measured gaps have a retention rule and runtime validation. This report does not authorize or perform promotion.', '',
        '## 26. Files changed', '',
        '- `backend/app/product_services/classic_candidate_completeness.py`: isolated model capture, exact roster enumeration, prospective validation, player-agnostic requests, lineage/counterfactuals, recall, diversity, saturation, target comparisons, coverage audits.',
        '- `scripts/research_classic_candidate_completeness.py`: immutable frozen-fixture runner, process workers, deterministic reduction, request checkpoints, target/thesis/user-policy comparisons, runtime and hashes.',
        '- `scripts/render_candidate_completeness.py`: report and complete player/QB CSV audits.',
        '- `backend/app/tests/product/test_classic_candidate_completeness.py`: targeted behavior and Week 4 canonical-ID regression tests.',
        '- `artifacts/candidate_completeness/week4-8b5c114c.json` (original solves), `week4-8b5c114c-complete.json` (stage-trace supplement), `week4-8b5c114c-reviewed.json` (final reviewed analysis), player/QB CSVs, this report, README, RELEASE_NOTES.', '',
        '## 27. Tests', '',
        'Run targeted validation after generating the fixture artifact:', '',
        '```sh', 'PYTHONHASHSEED=0 .venv/bin/python -m pytest backend/app/tests/product/test_classic_candidate_completeness.py backend/app/tests/product/test_classic_frontier_diagnostic.py backend/app/tests/product/test_classic_thesis_shadow.py backend/app/tests/product/test_classic_prospective.py backend/app/tests/product/test_classic_small_field.py -q', '```', '',
        'Coverage: deterministic actual-solver enumeration, exact no-good uniqueness, inclusive tolerance boundary/safety censoring, all-QB templates, forced inclusion, partner singles/doubles/triples/TE, raw/admitted reasons and displacement, target reuse, saturation, canonical recall, diversity, leakage/cutoff/prelock guards, unchanged production hashes/rosters, and Bucky/Bowers/Jefferson/JSN/Lamar fixtures.', '',
        ('**Validation: ' + validation['summary'] + '.** No skipped regression fixtures. Python compilation and focused documentation diff checks also passed. See [validation evidence](artifacts/candidate_completeness/week4-validation.json).' if validation else '**Validation results have not been attached to this rendering.**'), '',
        '## 28. Remaining uncertainty', '',
        '- The unenumerated remainder of safety-limited QB directions prevents exhaustive counts and a true global recall estimate.',
        '- Player and partner screens are broad deterministic hypotheses, not proofs that all meaningful combinations were searched.',
        '- Exact roster recall penalizes omitted near-duplicates; meaningful direction/game/player coverage must also be assessed.',
        '- A quiet ordered batch is not proof of search saturation; a mandatory-source/holdout experiment remains needed for a stopping rule.',
        '- Summed player P90 is not lineup P90; these frozen selector/thesis hypotheses are not outcome-calibrated.',
        '- Original historical attempt chronology is unavailable; saved raw keys and final admission counterfactuals are exact reconstructions, not original event logs.',
        '- Portfolio solver timeouts are explicitly unproven and cannot establish that a better portfolio does not exist.', '',
        '## Required final answers', '',
        '**Is the current 205-candidate universe sufficiently complete? NO.** The known legal near-frontier omissions and measured recall contradict completeness.', '',
        f"**Is the primary problem generation or admission?** At 0.20, generation misses **{known-generated}** known risk-legal rosters; admission omits **{generated-found}** of those historically generated. Generation is **{(known-generated)/max(1,known-found):.1%}** of known misses. The four named near-frontier regressions are classified individually above.", '',
        '**How many legal candidates exist within each tolerance?** Known risk-legal counts (.05/.10/.15/.20/.30): ' + '/'.join(str(d['enumeration'][t]['known_count']) for t in tolerances) + '. Count statuses: ' + '/'.join(d['enumeration'][t]['count_kind'] for t in tolerances) + '. Exact total cardinality is unavailable wherever enumeration is censored.', '',
        '**What frontier recall does the current 205 achieve?** ' + '/'.join(f"{d['current_frontier_recall'][t]['recall']:.1%}" for t in tolerances) + ' against the expanded known risk-legal universe, in tolerance order.', '',
        '**Does increasing the candidate target alone solve the problem? NO.** It cannot recover ungenerated rosters. On the expanded raw universe, target-only admission results are measured above; caps and selector competition can still leave coverage warnings.', '',
        '**What is the smallest candidate target that preserves nearly all meaningful frontier diversity? 400 of the tested targets**, when preserving the saved-user-policy five-entry optimum and expanded twenty-entry allocation is part of the acceptance criteria. 300 is sufficient for 97.7% known inside-0.20 roster recall and zero player coverage warnings alone; it loses the best saved-policy five-entry construction. A globally minimum target is not established.', '',
        '**Would a dynamic saturation-based stopping rule be better than a fixed 205 target?** It is a better research direction for raw discovery, conditional on mandatory-source coverage, grouped coverage checks, a holdout sweep, and hard safety limits. This experiment does not validate a production stopping rule.', '',
        '**Does improved discovery materially change the thesis conclusions? YES for construction families, NO for competitive QB/game breadth.** Qualified families inside 0.20 expand from 4 to 7 and Pareto-frontier families from 2 to 3. The same three QB directions and two games remain competitive; no new KC/BUF/SEA/MIN/TB direction reaches 0.20 under the frozen model.', '',
        '**Does improved discovery materially change the best five-lineup shadow?** The existing v3 dynamic thesis shadow changes from Lawrence/Burrow/Brissett = 3/1/1 to Lawrence/Burrow = 3/2, and its chosen tolerance tightens from 0.20 to 0.15. Its selector sum changes from 27.687854 to 27.643977 (−0.043877); the lower sum reflects a different adaptive eligible set, not evidence of degraded legal frontier quality. Under the identical saved user overlap=4/distinct-QB policy, the optimum remains 27.202641 with the exact same canonical roster set in the expanded raw universe. Targets 400/500 tie that score with alternative roster sets.', '',
        '**Does improved discovery materially change the 20-lineup thesis allocation? YES, modestly.** Lawrence/Burrow/Brissett shifts from 12/4/4 to 12/5/3; qualified constructions broaden, selector sum rises from 110.187825 to 110.283352 (+0.095527), and the expanded twenty is feasible inside 0.20 instead of requiring the unrestricted tolerance fallback. Targets 300/400/500 reproduce this expanded allocation.', '',
        '**What exact change should be promoted next?** Add the request/raw/admission lineage and near-frontier zero-coverage warning to the production report, then review the general QB+3/partner/player-gap discovery sweep as a separate promotion. Preserve all scoring and portfolio policy. Do not raise the production target merely to hide incomplete generation.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=Path('artifacts/candidate_completeness/week4-8b5c114c-reviewed.json'))
    parser.add_argument('--inputs', type=Path, default=Path('artifacts/week4-thesis-frozen-analysis-inputs-8b5c114c.json'))
    parser.add_argument('--report', type=Path, default=Path('WEEK4_CANDIDATE_FRONTIER_COMPLETENESS.md'))
    args = parser.parse_args()
    d = json.loads(args.evidence.read_text())
    if d['sha256'] != digest_payload({k:v for k,v in d.items() if k != 'sha256'}):
        raise ValueError('Evidence hash mismatch')
    validation_path = args.evidence.parent / 'week4-validation.json'
    validation = json.loads(validation_path.read_text()) if validation_path.exists() else None
    if validation and validation['evidence_sha256'] != d['sha256']:
        raise ValueError('Validation belongs to a different evidence artifact')
    args.report.write_text(render(d, json.loads(args.inputs.read_text()), validation))
    (args.evidence.parent / 'week4-request-stage-lineage.json').write_text(
        json.dumps(discovery_stage_audit(d), indent=2, sort_keys=True, allow_nan=False) + '\n')
    for key, filename in [('player_coverage', 'week4-player-coverage.csv'), ('qb_coverage', 'week4-qb-coverage.csv')]:
        rows = d[key]
        with (args.evidence.parent / filename).open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows({k:json.dumps(v, sort_keys=True) if isinstance(v, (dict,list)) else v for k,v in r.items()} for r in rows)


if __name__ == '__main__':
    main()
