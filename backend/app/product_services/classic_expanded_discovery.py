"""Opt-in common-frame Classic discovery using the existing research sweeps."""
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from .classic_candidate_completeness import (
    DiscoveryRequest, capture_model, compact_candidate, discovery_requests,
    rank_candidates, roster_key, solve_request,
)

_WORKER = {}


def _initialize(base, context, backend, frontier):
    _WORKER.update(base=base, context=context, backend=backend, frontier=frontier)


def _solve(request):
    return solve_request(_WORKER['base'], _WORKER['context'], request,
                         _WORKER['backend'], _WORKER['frontier'])


def expand_reviewed_discovery(result, players, source_rows, controls, options, *, workers=1):
    """Complete mandatory sweeps, retaining proven, legal common-scored rosters.

    Enumeration is bounded at 50 rosters per eligible QB, not exhaustive.
    Candidate admission caps do not thin this full reference; selected-player
    and availability caps remain enforced by the ordinary portfolio selector.
    """
    risk = controls['classifications']
    excluded = set(options.get('exclude_player_ids') or [])
    excluded |= {p.player_id for p in players if risk.get(p.player_id, {}).get('bucket') in {'out', 'doubtful'}}
    excluded |= {p.player_id for p in players if p.position == 'QB' and p.player_id not in set(options['starting_qb_ids'])}
    context = dict(players=players, config=result.config, options=options, risk=risk,
                   excluded=excluded, elevated={pid for pid,r in risk.items() if r['bucket']=='questionable_elevated'},
                   source={str(r['player_id']):r for r in source_rows}, policy=controls['policy'])
    original = rank_candidates([compact_candidate([p.player_id for p in lineup],context) for lineup in result.lineups])
    base = capture_model(context)
    frontier = solve_request(base,context,DiscoveryRequest('global_frontier'),options['solver_backend'])
    if not frontier['rows'] or frontier['events'][0]['status'] != 'optimal':
        raise ValueError('Expanded discovery has no proven global frontier')
    peak = frontier['rows'][0]['objective_score']
    requests = [DiscoveryRequest('qb_frontier',qb_id=p.player_id,safety_max=50,tolerance=.30)
                for p in sorted(players,key=lambda p:p.player_id) if p.position=='QB' and p.player_id not in excluded]
    requests += discovery_requests(context,original)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers,mp_context=get_context('spawn'),initializer=_initialize,
                                 initargs=(base,context,options['solver_backend'],peak)) as executor:
            solved = list(executor.map(_solve,requests))
    else:
        solved = [solve_request(base,context,r,options['solver_backend'],peak) for r in requests]
    raw = {roster_key(r):r for r in original}
    sources = {roster_key(r):['existing_discovery'] for r in original}
    for value in [frontier]+solved:
        for event in value['events']:
            if event['status']=='optimal':
                row = compact_candidate(event['player_ids'],context)
                if abs(row['objective_score']-event['objective_score'])>1e-8:
                    raise ValueError('Expanded discovery common scorer mismatch')
                if (set(row['player_ids']) & excluded or
                    len(set(row['player_ids']) & context['elevated'])>context['policy']['max_elevated_per_lineup']):
                    continue
                key=roster_key(row);raw.setdefault(key,row);sources.setdefault(key,[]).append(value['request']['source'])
    rows = rank_candidates(list(raw.values()))
    by_id={p.player_id:p for p in players}
    return [[by_id[pid] for pid in row['player_ids']] for row in rows], dict(
        mode='opt_in_expanded_full_reference',mandatory_requests_completed=len(requests),
        qb_enumeration_safety_max=50,global_known_frontier=peak,known_legal_rosters=len(rows),
        sources_by_lineup={'|'.join(key):labels for key,labels in sources.items()},
        events=[dict(request=v['request'],stop=v['stop'],complete=v['complete'],events=v['events']) for v in [frontier]+solved],
        limits=['Known legal reference; enumeration may be bounded or unproven.','No scoring, ownership or availability policy changed.'])
