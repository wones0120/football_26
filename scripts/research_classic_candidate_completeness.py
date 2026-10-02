#!/usr/bin/env python3
"""Run an immutable, offline, pre-lock Classic discovery experiment.

PYTHONHASHSEED=0 .venv/bin/python -m scripts.research_classic_candidate_completeness \
  --inputs artifacts/week4-thesis-frozen-analysis-inputs-8b5c114c.json \
  --output artifacts/candidate_completeness/week4-8b5c114c.json
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import floor
from multiprocessing import get_context
import os
from pathlib import Path
import resource
from tempfile import gettempdir
from time import perf_counter

from backend.app.product_services.cbc_solver import resolve_cbc_backend
from backend.app.product_services.classic_candidate_completeness import (
    TOLERANCES, DiscoveryRequest, admission_lineage, capture_model, compact_candidate,
    compare_targets, coverage_audits, discovery_requests, diversity, grouped_recall,
    load_context, rank_candidates, recall, roster_key, saturation, solve_request,
    validate_prospective,
)
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_small_field import _solve_seed_shard
from backend.app.product_services.classic_thesis_shadow import (
    _candidate_view, _dominance, _family_metrics, _portfolio_summary, _solve_portfolio,
)

_WORKER = {}


def _initialize(base, context, backend, frontier):
    _WORKER.update(base=base, context=context, backend=backend, frontier=frontier)


def _solve(request):
    return solve_request(_WORKER['base'], _WORKER['context'], request,
                         _WORKER['backend'], _WORKER['frontier'])


def _seed(request, context):
    return _solve_seed_shard(request, context)


def research_theses(candidates, context, saved_shadow):
    """Reuse v3 metrics and exact allocation solver for requested sizes only.

    Keep its overlap=6 research hypothesis explicit, and separately solve the
    saved user overlap=4/distinct-QB five-entry contract below.
    """
    from collections import defaultdict
    rows = [_candidate_view(r, context['source'], context['risk']) for r in candidates
            if len(set(r['player_ids']) & context['elevated']) <= context['policy']['max_elevated_per_lineup']]
    grouped = defaultdict(list)
    for r in rows:
        grouped[r['thesis_id']].append(r)
    best = max(r['selector'] for r in rows)
    families = [_family_metrics(g, rows, best) for g in grouped.values()]
    families.sort(key=lambda f: (-f['peak_selector'], f['thesis_id']))
    _dominance(families)
    by_id = {f['thesis_id']: f for f in families}
    viability = {f'{t:.2f}': {'qualified_count': sum(f['global_selector_gap'] <= t + 1e-9 for f in families),
        'frontier_count': sum(f['global_selector_gap'] <= t + 1e-9 and f['pareto_status'] == 'frontier' for f in families),
        'qb_directions': len({f['qb_id'] for f in families if f['global_selector_gap'] <= t + 1e-9}),
        'games': len({f['game_key'] for f in families if f['global_selector_gap'] <= t + 1e-9})} for t in TOLERANCES}
    portfolios = {}
    for count in (5, 20):
        chosen, status, used_tolerance, overlap_cap = [], 'not_attempted', None, None
        started = perf_counter()
        for tolerance in (.05, .10, .15, .20, None):
            eligible = [r for r in rows if tolerance is None or best - r['selector'] <= tolerance + 1e-9]
            for overlap in ((6, 7, 8) if count == 20 else (6,)):
                chosen, status = _solve_portfolio(eligible, by_id, count,
                    saved_shadow['selection_caps']['player_caps'],
                    context['policy']['selected_lineups_with_elevated_cap'], overlap)
                if chosen:
                    used_tolerance, overlap_cap = tolerance, overlap
                    break
            if chosen:
                break
        portfolios[str(count)] = {**_portfolio_summary(chosen, len(rows), status=status,
            tolerance=used_tolerance, overlap_cap=overlap_cap), 'seconds': perf_counter() - started}
    return {'families': families, 'viability': viability, 'shadow_portfolios': portfolios,
            'risk_legal_count': len(rows), 'portfolio_contract': 'existing v3 thesis research; overlap=6 then 7/8 for twenty; minimum two QB paths'}


def run(args):
    if args.output.exists():
        raise ValueError('Refusing to overwrite a discovery artifact')
    if not 1 <= args.workers <= 4 or os.environ.get('PYTHONHASHSEED') != '0':
        raise ValueError('Use 1-4 process workers with PYTHONHASHSEED=0')
    inputs = json.loads(args.inputs.read_text())
    context = load_context(inputs)
    context['caps'] = inputs['report']['production_controls']['candidate_caps']
    report = inputs['report']
    saved = report['all_candidates']
    source_hash = digest_payload(inputs)
    saved_shadow = json.loads(args.thesis.read_text())
    if saved_shadow['sha256'] != digest_payload({k: v for k, v in saved_shadow.items() if k != 'sha256'}):
        raise ValueError('Frozen thesis integrity mismatch')
    if saved_shadow['source']['candidate_universe_sha256'] != digest_payload({'candidates': saved}):
        raise ValueError('Frozen thesis candidate universe mismatch')
    backend = resolve_cbc_backend(args.solver)
    started = perf_counter()
    base = capture_model(context)
    model_seconds = perf_counter() - started
    print(f'Model captured: {len(base.variables())} variables, {len(base.constraints)} constraints, {model_seconds:.2f}s', flush=True)
    current = [compact_candidate(r['player_ids'], context) | {'rank': r['rank']} for r in saved]
    if any(abs(r['objective_score'] - c['objective_score']) > 1e-9 for r, c in zip(saved, current)):
        raise ValueError('Frozen selector replay mismatch')
    sources = report['candidate_discovery']['sources_by_lineup']
    historical = rank_candidates([compact_candidate(key.split('|'), context) for key in sources])
    if len(historical) != report['production_funnel']['legal']:
        raise ValueError('Historical raw roster count mismatch')
    print(f'Reconstructed {len(historical)} historical legal rosters', flush=True)
    raw = {roster_key(r): r for r in historical}
    provenance = {key: list(sources['|'.join(key)]) for key in raw}
    discovery_started = perf_counter()
    global_result = solve_request(base, context, DiscoveryRequest('global_frontier', safety_max=1), backend)
    if not global_result['rows']:
        raise ValueError('No proven global frontier')
    frontier = global_result['rows'][0]['objective_score']
    events = []
    partitions = []
    request_results = []
    def ingest(result):
        request_results.append({k: v for k, v in result.items() if k not in {'rows', 'events'}})
        for event in result['events']:
            record = {**event, 'source': result['request']['source'], 'request': result['request']}
            if event['status'] == 'optimal':
                row = compact_candidate(event['player_ids'], context)
                if abs(row['objective_score'] - event['objective_score']) > 1e-8:
                    raise ValueError('Solver/scorer objective mismatch')
                key = roster_key(row)
                raw.setdefault(key, row)
                provenance.setdefault(key, []).append(result['request']['source'])
                record['candidate'] = row
            events.append(record)
    ingest(global_result)
    qbs = sorted((p for p in context['players'] if p.position == 'QB' and p.player_id not in context['excluded']), key=lambda p: p.player_id)
    enumeration_requests = [DiscoveryRequest('qb_frontier', qb_id=p.player_id,
        safety_max=args.per_qb_max, tolerance=.30) for p in qbs]
    complementary = discovery_requests(context, current)
    planned = enumeration_requests + complementary
    replay = json.loads(args.replay_evidence.read_text()) if args.replay_evidence else None
    if replay:
        if replay['sha256'] != digest_payload({k:v for k,v in replay.items() if k != 'sha256'}):
            raise ValueError('Solve evidence hash mismatch')
        if replay['input_sha256'] != source_hash or replay['frontier'] != frontier or replay['method']['solver'] != backend:
            raise ValueError('Solve evidence input/frontier/backend mismatch')
        if replay['method']['per_qb_safety_max'] != args.per_qb_max:
            raise ValueError('Solve evidence safety maximum mismatch')
    cache_key = digest_payload({'input': source_hash, 'solver': backend,
        'module': sha256(Path('backend/app/product_services/classic_candidate_completeness.py').read_bytes()).hexdigest(),
        'frontier': frontier})
    cache_dir = Path(gettempdir()) / 'classic-discovery-cache' / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Results are reduced in declared request order, independent of completion
    # timing. That gives deterministic union order and a reproducible saturation
    # curve without pretending the parallel completion order is reproducible.
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context('spawn'),
            initializer=_initialize, initargs=(base, context, backend, frontier)) as executor:
        results = {}
        cache_hits = 0
        future_index = {}
        for i, request in enumerate(planned):
            path = cache_dir / (digest_payload(asdict(request)) + '.json')
            if replay:
                request_key = digest_payload(asdict(request))
                old = next((r for r in replay['requests'] if digest_payload(r['request']) == request_key), None)
                if old is None:
                    raise ValueError('Solve evidence lacks a planned request')
                old_events = [{k:v for k,v in e.items() if k not in {'source', 'request'}}
                              for e in replay['solve_events'] if digest_payload(e['request']) == request_key]
                rows = [e for e in old_events if e['status'] == 'optimal']
                if old['stop'] in {'tolerance', 'numerical_nonmonotonic'}:
                    rows = rows[:-1]
                results[i] = {**old, 'rows': rows, 'events': old_events}
            elif path.exists() and not args.fresh_solves:
                results[i] = json.loads(path.read_text())
                cache_hits += 1
            else:
                future_index[executor.submit(_solve, request)] = i
        for done, future in enumerate(as_completed(future_index), 1):
            index = future_index[future]
            results[index] = future.result()
            (cache_dir / (digest_payload(asdict(planned[index])) + '.json')).write_text(
                json.dumps(results[index], sort_keys=True, allow_nan=False))
            if done % 25 == 0 or done == len(planned):
                print(f'Solved {done}/{len(planned)} requests ({perf_counter()-discovery_started:.1f}s elapsed)', flush=True)
        for i in range(len(planned)):
            result = results[i]
            ingest(result)
            if i < len(enumeration_requests):
                partitions.append({k: v for k, v in result.items() if k not in {'rows', 'events'}} |
                    {'count': len(result['rows']), 'last_selector': result['rows'][-1]['objective_score'] if result['rows'] else None})
    discovery_seconds = perf_counter() - discovery_started
    raw_rows = rank_candidates(list(raw.values()))
    risk_legal_rows = [r for r in raw_rows if len(set(r['player_ids']) & context['elevated']) <= context['policy']['max_elevated_per_lineup']]
    enumeration = {}
    for tolerance in TOLERANCES:
        # For an exhausted/tolerance partition, all scores inside .30 have been
        # visited. A safety-limited partition certifies a tighter tolerance only
        # if its proven last optimum has already crossed that tighter boundary.
        complete = all(p['complete'] or (p['stop'] == 'safety_max' and p['last_selector'] is not None and
                       frontier - p['last_selector'] > tolerance + 1e-9) for p in partitions)
        rows = [r for r in risk_legal_rows if frontier - r['objective_score'] <= tolerance + 1e-9]
        enumeration[f'{tolerance:.2f}'] = {'known_count': len(rows), 'count_kind': 'exact' if complete else 'lower_bound',
                                         'complete': complete}
    print(f'Discovered {len(raw_rows)} unique raw candidates; frontier counts={enumeration}', flush=True)
    historical_started = perf_counter()
    historical_lineage = admission_lineage(historical, current, context['caps'], context['elevated'],
        context['policy']['max_elevated_per_lineup'], backend)
    historical_lineage_seconds = perf_counter() - historical_started
    print(f'Historical reasons: {dict(Counter(r["primary_reason"] for r in historical_lineage))}', flush=True)
    targets = compare_targets(raw_rows, context, (205, 300, 400, 500), backend, frontier)
    print(f'Target counts: {[(t, r["diversity"]["count"]) for t,r in targets.items()]}', flush=True)
    for t, result in targets.items():
        begin = perf_counter()
        result['lineage'] = admission_lineage(raw_rows, result['admitted'], context['caps'], context['elevated'],
            context['policy']['max_elevated_per_lineup'], backend)
        result['lineage_seconds'] = perf_counter() - begin
        result['reason_counts'] = dict(Counter(r['primary_reason'] for r in result['lineage']))
        result['player_coverage'], result['qb_coverage'] = coverage_audits(raw_rows, result['admitted'], context,
            frontier, result['lineage'], current)
        result['coverage_warnings'] = [r['player_id'] for r in result['player_coverage'] if r['coverage_warning']]
        print(f'Target {t}: reasons={result["reason_counts"]}, warnings={len(result["coverage_warnings"])}', flush=True)
    current_lineage = admission_lineage(raw_rows, current, context['caps'], context['elevated'],
        context['policy']['max_elevated_per_lineup'], backend)
    player_audit, qb_audit = coverage_audits(raw_rows, current, context, frontier, current_lineage, current)
    thesis = {'current': {'families': saved_shadow['families'], 'viability': saved_shadow['viability'],
                         'shadow_portfolios': saved_shadow['shadow_portfolios']}}
    for label, rows in [('expanded', raw_rows)] + [(f'target_{t}', r['admitted']) for t, r in targets.items()]:
        print(f'Thesis analysis: {label}, {len(rows)} candidates', flush=True)
        thesis[label] = research_theses(rows, context, saved_shadow)
    # Honor saved user overlap/distinct-QB policy in separate portfolio sensitivity.
    from backend.app.product_services.classic_small_field import _select_global
    user_portfolios = {}
    for label, rows in [('current', current), ('expanded', raw_rows)] + [(f'target_{t}', r['admitted']) for t, r in targets.items()]:
        begin = perf_counter()
        legal = [r for r in rows if len(set(r['player_ids']) & context['elevated']) <= context['policy']['max_elevated_per_lineup']]
        indices = _select_global(legal, 5, inputs['max_exposure'],
            locked_player_ids=set(context['options'].get('locked_player_ids') or []),
            maximum_exposure_by_player=saved_shadow['selection_caps']['player_caps'],
            minimum_exposure_by_player=context['options'].get('minimum_exposure_by_player') or {},
            solver_backend=backend, max_lineup_overlap=4, distinct_qb_paths=True,
            max_lineups_with_any_player_ids=(context['elevated'], context['policy']['selected_lineups_with_elevated_cap']))
        user_portfolios[label] = {'count': len(indices), 'selector_sum': sum(legal[i]['objective_score'] for i in indices),
            'player_ids': [legal[i]['player_ids'] for i in indices], 'seconds': perf_counter() - begin,
            'status': 'optimal' if len(indices) == 5 else 'infeasible_or_unproven'}
    baseline_seconds = None
    baseline_matches = None
    if replay:
        baseline_seconds = replay['runtime']['current_seed_replay_seconds']
        baseline_matches = replay['runtime']['baseline_seed_rosters_match']
    if args.replay_baseline:
        baseline_started = perf_counter()
        workers = context['options']['seed_generation_workers']
        qb_ids = [p.player_id for p in context['players'] if p.position == 'QB' and p.player_id in set(context['options']['starting_qb_ids'])]
        sizes = [205 // workers + (i < 205 % workers) for i in range(workers)]
        seed_context = dict(players=context['players'], config=context['config'],
            enforce_single_te=context['options']['enforce_single_te'], avoid_dst_opponents=context['options']['avoid_dst_opponents'],
            solver_backend=context['options']['solver_backend'], candidate_caps=context['caps'],
            elevated_ids=context['elevated'], max_elevated=context['policy']['max_elevated_per_lineup'])
        with ProcessPoolExecutor(max_workers=workers, mp_context=get_context('spawn')) as executor:
            futures = [executor.submit(_seed, (i, sizes[i], tuple(qb_ids[i::workers]), workers), seed_context) for i in range(workers)]
            baseline = {tuple(sorted(ids)) for f in futures for ids in f.result()['lineups']}
        baseline_seconds = perf_counter() - baseline_started
        expected = {tuple(key.split('|')) for key, labels in sources.items() if 'sequential' in labels}
        baseline_matches = baseline == expected
        print(f'Baseline seed replay {baseline_seconds:.1f}s, matches={baseline_matches}', flush=True)
    validate_prospective(inputs)
    if digest_payload(json.loads(args.inputs.read_text())) != source_hash:
        raise ValueError('Source changed during research')
    body = {'contract': 'classic_candidate_discovery_completeness_v1', 'frozen_at': datetime.now(UTC).isoformat(),
        'source': saved_shadow['source'], 'input_sha256': source_hash, 'source_file_sha256': sha256(args.inputs.read_bytes()).hexdigest(),
        'production_unchanged': True, 'production_candidate_sha256': digest_payload({'candidates': saved}),
        'production_selected_ranks': report['selected_ranks'], 'frontier': frontier,
        'method': {'solver': backend, 'workers': args.workers, 'per_qb_safety_max': args.per_qb_max,
            'replayed_solve_evidence_sha256': replay['sha256'] if replay else None,
            'original_solve_code_sha256': replay['method']['code_sha256'] if replay else None,
            'request_cache_hits': cache_hits,
            'seed': 1, 'threads_per_solver': 1, 'solver_seconds_limit': 30,
            'new_discovery_enforces_per_lineup_injury_policy': True,
            'exact_no_good_cut_overlap': 8, 'saved_production_uniqueness_overlap': context['config'].uniqueness_overlap,
            'raw_policy': 'no aggregate exposure caps; frozen football and per-lineup injury policy',
            'code_sha256': {str(p): sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), Path('backend/app/product_services/classic_candidate_completeness.py')]},
            'frozen_production_code_sha256': report['frozen_solver_snapshot']['payload']['metadata']['code_sha256']},
        'enumeration': enumeration, 'partitions': partitions, 'requests': request_results,
        'raw_candidates': raw_rows, 'provenance': {'|'.join(k): v for k,v in sorted(provenance.items())},
        'historical_raw_candidates': historical, 'historical_lineage': historical_lineage,
        'historical_reason_counts': dict(Counter(r['primary_reason'] for r in historical_lineage)),
        'current_pool_diversity': diversity(current), 'raw_diversity': diversity(raw_rows),
        'current_frontier_recall': recall(risk_legal_rows, current, frontier),
        'roster_legal_current_frontier_recall': recall(raw_rows, current, frontier),
        'normal_generation_recall': recall(risk_legal_rows, historical, frontier),
        'current_grouped_recall': grouped_recall(risk_legal_rows, current, frontier, context),
        'current_lineage': current_lineage, 'player_coverage': player_audit, 'qb_coverage': qb_audit,
        'targets': targets, 'saturation': saturation(events, frontier),
        'solve_events': [{k: v for k,v in e.items() if k != 'candidate'} for e in events],
        'thesis': thesis, 'user_five_portfolios': user_portfolios,
        'runtime': {'model_build_seconds': model_seconds, 'expanded_discovery_seconds': discovery_seconds,
            'original_expanded_discovery_seconds': replay['runtime']['expanded_discovery_seconds'] if replay else discovery_seconds,
            'historical_lineage_seconds': historical_lineage_seconds, 'current_seed_replay_seconds': baseline_seconds,
            'baseline_seed_rosters_match': baseline_matches, 'current_saved_joint_admission_seconds': report['production_funnel']['joint_admission_seconds'],
            'solve_seconds_by_source': {s: sum(e['seconds'] for e in events if e['source'] == s) for s in sorted({e['source'] for e in events})},
            'solve_counts_by_source': dict(Counter(e['source'] for e in events)),
            'parent_peak_rss_native_units': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'children_peak_rss_native_units': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            'total_seconds': perf_counter() - started},
        'limits': ['Counts marked lower_bound are not the legal-space cardinality.',
                   'Recall denominator is the expanded known universe, not a proven exhaustive universe.',
                   'Historical raw keys survive, but original request failures and chronological logs do not.',
                   'Saturation uses deterministic declared request order, not parallel completion time.',
                   'Fixed target admission is the saved cardinality-first selector objective, with unchanged caps.',
                   'Known equivalent ranks are relative to the frozen 205, not exact legal-space ranks.',
                   'Research thesis portfolios reuse v3 overlap hypotheses; user five-entry sensitivity separately keeps overlap=4.']}
    body['raw_serialized_bytes'] = len(json.dumps(raw_rows, sort_keys=True, separators=(',', ':')).encode())
    output = {**body, 'sha256': digest_payload(body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(output, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    print(f'Frozen {args.output}: {output["sha256"]}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--thesis', type=Path, default=Path('artifacts/week4-dynamic-thesis-shadow-8b5c114c.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--solver', choices=('native', 'bundled', 'auto'), default='native')
    parser.add_argument('--per-qb-max', type=int, default=50)
    parser.add_argument('--replay-baseline', action='store_true')
    parser.add_argument('--replay-evidence', type=Path, help='Re-analyze hashed prior solves; original solve code/time provenance is retained')
    parser.add_argument('--fresh-solves', action='store_true', help='Bypass request caches for a fresh runtime benchmark')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
