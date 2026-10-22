"""Descriptive official-workload associations with archived intended pregame lines."""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .schedule_context_features import load_schedule_context
from .workload_venue_splits import build_workload_venue_splits, CHANNELS

VERSION = 'workload_market_contexts_v1'
MARKET_VERSION = 'native_archived_pregame_market_context_v1'
FIELDS = {'G21-M02':'game_total_line', 'G21-M03':'team_spread_line', 'G21-M04':'team_implied_points'}


def _line(value):
    if value is None or value == '' or isinstance(value, bool):return None
    try:number = float(value)
    except (TypeError, ValueError):return None
    return number if math.isfinite(number) else None


def normalize_archived_market_context(records, schedule, *, before_period):
    """Source spread_line is expected HOME margin; canonical wager sign is its negative."""
    expected = {r['game_id']:r for r in schedule['game_rows']}
    rows = []; seen = set()
    for r in records:
        gid = r['game_id']; game = expected.get(gid)
        if game is None:raise ValueError('Market row outside authenticated native schedule')
        parts=gid.split('_')
        if (len(parts)!=4 or parts[:2]!=[str(game['season']),f"{game['week']:02d}"]
                or canonical_team(parts[2])!=game['away_team'] or canonical_team(parts[3])!=game['home_team']):
            raise ValueError('Native schedule game identity required')
        if gid in seen:raise ValueError('Duplicate native game market row')
        seen.add(gid)
        if (str(r['season']) != str(game['season']) or str(r['week']) != str(game['week'])
                or r['game_type'] != game['game_type']
                or canonical_team(r['home_team']) != game['home_team']
                or canonical_team(r['away_team']) != game['away_team']):
            raise ValueError('Market native scope/orientation contradicts schedule')
        if game['game_type'] != 'REG' or game['season']*100+game['week'] >= before_period:continue
        total = _line(r.get('total_line')); margin = _line(r.get('spread_line'))
        if total is not None and not 20 <= total <= 80:raise ValueError('Archived intended total outside source sanity bound')
        if margin is not None and abs(margin) > 30:raise ValueError('Archived expected home margin outside source sanity bound')
        home_spread = -margin if margin is not None else None
        for team, spread in ((game['home_team'],home_spread),
                (game['away_team'],-home_spread if home_spread is not None else None)):
            rows.append(dict(game_id=gid,season=game['season'],week=game['week'],team=team,
                game_total_line=total,team_spread_line=spread,
                team_implied_points=(total-spread)/2 if total is not None and spread is not None else None))
    rows.sort(key=lambda r:(r['game_id'],r['team']))
    basis = dict(version=MARKET_VERSION,before_period=before_period,rows=rows,
        market_kind='revised_archived_intended_pregame_line',
        sign_transform='canonical home_spread=-source spread_line; source positive means home favored',
        original_quote_at=None, original_decision_availability='unknown')
    return dict(**basis,semantic_sha256=digest(basis),provenance=deepcopy(schedule['provenance']),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)


def load_archived_market_context(snapshot, *, before_period, cutoff):
    schedule = load_schedule_context(snapshot,cutoff=cutoff)
    with Path(snapshot.artifact_path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'game_id','season','week','game_type','home_team','away_team','total_line','spread_line'}
        if not required <= set(reader.fieldnames or []):raise ValueError('Native archived market fields absent')
        result = normalize_archived_market_context(reader,schedule,before_period=before_period)
    result['provenance']['producer_code_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return schedule, result


def _association(logs, channel, field, native_team_unknown):
    pairs = [(r['market'][field],r['counts'][channel]) for r in logs
        if r['market'] is not None and r['market'][field] is not None and r['counts'][channel] is not None]
    n = len(pairs); unknown = len(logs)-n
    xmean = math.fsum(x for x,y in pairs)/n if n else None
    ymean = math.fsum(y for x,y in pairs)/n if n else None
    xss = math.fsum((x-xmean)**2 for x,y in pairs) if n else None
    cross = math.fsum((x-xmean)*(y-ymean) for x,y in pairs) if n else None
    covariance = cross/n if n >= 2 else None
    slope = cross/xss if n >= 2 and xss > 0 else None
    exact = not (unknown or native_team_unknown)
    return dict(observed_logs=len(logs),known_paired_logs=n,unknown_pairs=unknown,
        known_sample_mean_line=xmean,known_sample_mean_official_count=ymean,
        known_sample_centered_cross_sum=cross,known_sample_line_centered_square_sum=xss,
        known_sample_population_covariance=covariance,known_sample_slope=slope,
        population_covariance=covariance if exact else None,
        slope=slope if exact else None,
        unit='official_opportunities_per_pregame_line_point',
        status='descriptive_bivariate_sample_not_predictive_or_causal',
        minimum_distinct_line_values=2,shrinkage='none',original_quote_availability='unknown')


def build_workload_market_contexts(weekly,schedule,markets,*,before_period):
    base = build_workload_venue_splits(weekly,schedule,before_period=before_period)
    if (markets.get('version') != MARKET_VERSION or markets.get('before_period') != before_period
            or markets.get('pregame_serving_eligible') is not False
            or markets.get('market_kind') != 'revised_archived_intended_pregame_line'
            or not markets['provenance'].get('snapshot_id') or not markets['provenance'].get('sha256')
            or markets['provenance'].get('snapshot_id') != schedule['provenance'].get('snapshot_id')
            or markets['provenance'].get('sha256') != schedule['provenance'].get('sha256')):
        raise ValueError('Matched authenticated native archived market/schedule source required')
    market_lookup = {}
    games = {r['game_id']:r for r in schedule['game_rows']}
    for row in markets['rows']:
        gid = row['game_id']; game = games.get(gid); team = canonical_team(row['team'])
        if (game is None or game['game_type'] != 'REG' or row['season'] != game['season']
                or row['week'] != game['week'] or row['season']*100+row['week'] >= before_period
                or team not in {game['home_team'],game['away_team']}):
            raise ValueError('Prior native market/game/team scope required')
        if (gid,team) in market_lookup:raise ValueError('Duplicate native market team/game')
        for field in FIELDS.values():
            value = row[field]
            if value is not None and (type(value) not in {int,float} or not math.isfinite(value)):
                raise ValueError('Finite market component or explicit null required')
        total,spread,implied = (row[k] for k in FIELDS.values())
        if total is not None and not 20<=total<=80:raise ValueError('Invalid intended market total')
        if spread is not None and abs(spread)>30:raise ValueError('Invalid signed team spread')
        if implied != ((total-spread)/2 if total is not None and spread is not None else None):
            raise ValueError('Implied points conflict with canonical total/spread')
        market_lookup[(gid,team)] = row
    for gid,game in games.items():
        home=market_lookup.get((gid,game['home_team']));away=market_lookup.get((gid,game['away_team']))
        if home is not None and away is not None:
            if home['game_total_line']!=away['game_total_line'] or home['team_spread_line']!=(-away['team_spread_line'] if away['team_spread_line'] is not None else None):
                raise ValueError('Contradictory same-game line/orientation')
    rows = []
    for actor in base['rows']:
        logs = [deepcopy(log) | dict(market=deepcopy(market_lookup.get((log['native_game_id'],actor['team'])))) for log in actor['logs']]
        metrics = {mid:dict(source_field=field,channels={ch:_association(logs,ch,field,actor['native_team_scope_unknown']) for ch in CHANNELS}) for mid,field in FIELDS.items()}
        rows.append({k:deepcopy(actor[k]) for k in ('season','team','source_player_id','player_master_id','native_team_scope_unknown')} | dict(metrics=metrics,logs=logs))
    semantic_rows = [{**r,'logs':[{k:v for k,v in log.items() if k != 'source_ref'} for log in r['logs']]} for r in rows]
    basis = dict(version=VERSION,before_period=before_period,definitions=FIELDS,rows=semantic_rows,
        definition='Same-season/team observed official count versus intended pregame line: paired sample moments/covariance/slope, no predictive fit')
    return basis | dict(rows=rows,semantic_sha256=digest(basis),
        provenance=dict(**deepcopy(base['provenance']),markets=deepcopy(markets['provenance'])),
        source_semantic_hashes=dict(**base['source_semantic_hashes'],markets=markets['semantic_sha256']),
        identity_review_requests=deepcopy(base['identity_review_requests']),
        evidence_use=base['evidence_use'],pregame_serving_eligible=False,forecast=None,models_or_optimizer_consumed=False,
        limitations=base['limitations']+['Archived intended pregame closing lines can be revised; original quote/publication availability unknown',
            'No realized score, actual game total or score margin is used as a market input',
            'Population covariance and unshrunk bivariate slope describe observed samples, not causal response or trained forecast',
            'Unknown quote/exposure masks the all-observed-log descriptor; known paired sample remains separately labeled'])
