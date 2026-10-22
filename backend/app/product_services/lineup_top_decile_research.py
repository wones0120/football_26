"""Interpretable complete-lineup research features and contest-local labels.

No contest outcomes are accepted by the predictor feature builder. No live policy.
"""
import math
from collections import Counter

CONTRACT = 'complete_lineup_top_decile_research_v1'
CORE_FEATURES = ['mean_sum', 'marginal_p90_spread_sum', 'min_mean', 'max_mean_share', 'mean_herfindahl',
    'salary_used', 'min_base_salary', 'base_salary_std', 'team_roster_herfindahl', 'game_roster_herfindahl',
    'max_team_count', 'max_game_count', 'qb_receiver_pairs', 'opposing_qb_receiver_pairs', 'qb_count',
    'captain_mean_fraction', 'captain_QB', 'captain_RB', 'captain_WR', 'captain_TE', 'captain_K', 'captain_DST']
RICH_FEATURES = ['min_skill_workload', 'skill_workload_sum', 'max_workload_share', 'implied_points_mean', 'implied_points_min', 'total_line_mean', 'absolute_spread_mean']


def top_decile_boundary(points):
    values = sorted((round(float(p), 2) for p in points), reverse=True)
    if not values or not all(math.isfinite(p) for p in values):
        raise ValueError('Finite complete field scores required')
    rank = max(1, math.ceil(.1 * len(values)))
    cutoff = values[rank - 1]
    return dict(field_size=len(values), nominal_boundary_rank=rank, points_cutoff=cutoff,
                positives=sum(p >= cutoff for p in values), ties_at_boundary=sum(p == cutoff for p in values),
                tie_policy='all entries tied at the decile score after DK-cent rounding of CSV float artifacts are positive')


def canonical_roster(players, contest_format):
    roles = [p['role'] for p in players]
    ids = [p['player_id'] for p in players]
    if len(ids) != len(set(ids)) or len(ids) != (6 if contest_format == 'showdown' else 9):
        raise ValueError('Wrong roster size or duplicate canonical player')
    if contest_format == 'showdown' and (roles.count('CPT') != 1 or roles.count('FLEX') != 5):
        raise ValueError('Showdown needs exact Captain identity and five FLEX players')
    if contest_format == 'classic' and 'CPT' in roles:
        raise ValueError('Classic cannot contain a Captain')
    return tuple(sorted((p['player_id'], p['role'] == 'CPT') for p in players))


def lineup_features(players, contest_format, *, rich=False):
    canonical_roster(players, contest_format)
    for p in players:
        if not all(type(p.get(k)) in (int, float) and math.isfinite(p[k]) for k in ['mean', 'p90', 'salary']):
            raise ValueError('Missing original pregame moments/salary; no imputed projection')
        if p['p90'] < p['mean'] or p['salary'] < 0:
            raise ValueError('Invalid original moments/salary')
        if not p.get('team') or not p.get('game_id') or p.get('position') not in {'QB','RB','WR','TE','K','DST'}:
            raise ValueError('Missing canonical role/game context')
    n = len(players)
    means = [p['mean'] * (1.5 if p['role'] == 'CPT' else 1) for p in players]
    total = sum(means)
    base_salary = [p['salary'] / (1.5 if p['role'] == 'CPT' else 1) for p in players]
    teams = Counter(p['team'] for p in players)
    games = Counter(p['game_id'] for p in players)
    qbs = [p for p in players if p['position'] == 'QB']
    receivers = [p for p in players if p['position'] in {'WR','TE'}]
    cap = next((p for p in players if p['role'] == 'CPT'), None)
    values = [total, sum((p['p90']-p['mean']) * (1.5 if p['role']=='CPT' else 1) for p in players),
        min(means), max(means)/total if total else 0, sum((x/total)**2 for x in means) if total else 0,
        sum(p['salary'] for p in players), min(base_salary),
        math.sqrt(sum((x-sum(base_salary)/n)**2 for x in base_salary)/n),
        sum((v/n)**2 for v in teams.values()), sum((v/n)**2 for v in games.values()), max(teams.values()), max(games.values()),
        sum(q['team']==r['team'] for q in qbs for r in receivers),
        sum(q['game_id']==r['game_id'] and q['team']!=r['team'] for q in qbs for r in receivers), len(qbs),
        cap['mean']*1.5/total if cap and total else 0,
        *[int(bool(cap and cap['position']==pos)) for pos in ['QB','RB','WR','TE','K','DST']]]
    if rich:
        skill = [p for p in players if p['position'] in {'QB','RB','WR','TE'}]
        workload = []
        for p in skill:
            f = p.get('features') or {}
            keys = ['carries_mean_3'] if p['position']=='QB' else ['targets_mean_3'] if p['position'] in {'WR','TE'} else ['carries_mean_3','targets_mean_3']
            if any(type(f.get(k)) not in (int,float) or not math.isfinite(f[k]) for k in keys):
                raise ValueError('Rich cohort missing recorded pregame workload, not zero')
            workload.append(sum(f[k] for k in keys))
        context = [(p.get('features') or {}) for p in skill]
        fields = ['team_implied_total','game_total_line','team_spread_line']
        if any(type(f.get(k)) not in (int,float) or not math.isfinite(f[k]) for f in context for k in fields):
            raise ValueError('Rich cohort missing recorded pregame game context')
        total_work = sum(workload)
        values += [min(workload), total_work, max(workload)/total_work if total_work else 0,
            sum(f['team_implied_total'] for f in context)/len(context), min(f['team_implied_total'] for f in context),
            sum(f['game_total_line'] for f in context)/len(context), sum(abs(f['team_spread_line']) for f in context)/len(context)]
    return values


def predict_artifact(artifact, values):
    """Portable coefficient inference; never a mutation of player projections."""
    if artifact.get('contract_id') != CONTRACT:
        raise ValueError('Unsupported lineup model contract')
    names=artifact['features']
    if names not in [CORE_FEATURES, CORE_FEATURES+RICH_FEATURES] or len(values)!=len(names):
        raise ValueError('Lineup model feature contract mismatch')
    arrays=[artifact['mean'],artifact['scale'],artifact['coefficients']]
    if any(len(a)!=len(names) for a in arrays) or not all(math.isfinite(float(v)) for a in arrays+[values] for v in a):
        raise ValueError('Nonfinite or incomplete model values')
    if any(v<=0 for v in artifact['scale']):
        raise ValueError('Invalid feature scale')
    logit=float(artifact['intercept'])+sum((value-mean)/scale*coefficient for value,mean,scale,coefficient in zip(values,*arrays))
    return 1/(1+math.exp(-max(-700,min(700,logit))))
