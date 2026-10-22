"""Centered lagged team/market input products, not learned or causal responses."""
from collections import defaultdict
from copy import deepcopy
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .offensive_environment_catalog import _count
from .team_decision_catalog_features import _measure
from .workload_market_contexts import MARKET_VERSION
from .environment_context_evidence import DEFINITIONS as ENV_DEFINITIONS

VERSION='team_market_interactions_v1'
PRODUCTS={
 'X01-M01':('prior_physical_snaps_mean','game_total_line','G01-M01 × G19-M01','physical_snaps_x_market_points'),
 'X01-M02':('prior_called_pass_fraction','team_spread_line','G02-M01 × G19-M04','called_pass_fraction_x_signed_market_points'),
 'X01-M03':('prior_official_carries_mean','team_implied_points','G06-M01 full-team official carries × G19-M07','official_carries_x_market_points')}
FIELDS=('prior_physical_snaps_mean','prior_called_pass_fraction','prior_official_carries_mean',
 'game_total_line','team_spread_line','team_implied_points')


def _key(row,upper):
    gid=row['game_id'];team=canonical_team(row['team']);parts=gid.split('_')
    if len(parts)!=4 or not parts[0].isdigit() or not parts[1].isdigit():raise ValueError('Native game identity required')
    year,week=int(parts[0]),int(parts[1])
    if (not 1<=week<=18 or parts[1]!=f'{week:02d}' or year*100+week>=upper
            or len({canonical_team(x) for x in parts[2:]})!=2 or team not in {canonical_team(x) for x in parts[2:]}):
        raise ValueError('Strict prior native game/team scope required')
    return gid,team,year,week


def _lineage(source):
    p=source['provenance'];s=p['source'];line=(s.get('snapshot_id'),s.get('content_sha256'),p.get('event_receipt_sha256'))
    if not all(line):raise ValueError('Native source/event ancestry required')
    return line


def build_team_market_interactions(environment,official,markets,*,before_period,reference_before_period,last_n=8):
    if (type(before_period)is not int or not 1<=before_period%100<=18
            or type(reference_before_period)is not int or reference_before_period//100!=before_period//100
            or not before_period//100*100+1<reference_before_period<before_period
            or type(last_n)is not int or not 1<=last_n<=32):raise ValueError('Explicit time-separated reference/target/window required')
    parent_period=environment['before_period']
    if (environment.get('version')!='environment_context_evidence_v1'
            or environment.get('forecast')is not None or environment['definitions'].get('G02-M01')!=ENV_DEFINITIONS['G02-M01']
            or official.get('version')!='official_workload_components_v1' or official.get('before_period')!=parent_period
            or official.get('pregame_serving_eligible')is not False or official.get('forecast')is not None
            or not reference_before_period<=parent_period<=before_period
            or markets.get('version')!=MARKET_VERSION or markets.get('before_period')!=before_period
            or markets.get('pregame_serving_eligible')is not False
            or markets.get('market_kind')!='revised_archived_intended_pregame_line'):
        raise ValueError('Reviewed matched descriptive parent contracts required')
    if _lineage(environment)!=_lineage(official):raise ValueError('Physical-volume/call/carry source ancestry differs')
    volume={};rush={}
    for row in environment['game_rows']:
        gid,team,year,week=_key(row,parent_period);key=(gid,team)
        if row['season']!=year or row['week']!=week or key in volume:raise ValueError('Duplicate/contradictory native environment scope')
        count=_count(row['known_offensive_snaps']);unknown=_count(row['unknown_snap_eligibility'])
        volume[key]=dict(value=float(count) if not unknown else None,known_physical_snap_lower_bound=count,
            unknown_snap_eligibility=unknown,call=_measure(row['metrics']['G02-M01']))
    for row in official['full_team_denominators']:
        gid,team,_,_=_key(row,parent_period);key=(gid,team)
        if key in rush:raise ValueError('Duplicate native official full-team budget')
        m=row['measurements']['official_carries'];value=m['exact_within_log_count']
        if value is not None:
            value=float(_count(value))
            if m['unknown_eligibility_events'] or m['unknown_outcome_events']:raise ValueError('Unknown official carry eligibility cannot have exact count')
        rush[key]=dict(value=value,measurement=deepcopy(m))
    target_rows=[];seen=set();by_team=defaultdict(list)
    for row in markets['rows']:
        gid,team,year,week=_key(row,before_period);key=(gid,team)
        if row['season']!=year or row['week']!=week or key in seen:raise ValueError('Duplicate/contradictory native market scope')
        seen.add(key)
        if year!=before_period//100:continue
        total,spread,implied=(row[k] for k in ('game_total_line','team_spread_line','team_implied_points'))
        for value in (total,spread,implied):
            if value is not None and (type(value)not in {int,float} or not math.isfinite(value)):raise ValueError('Finite or explicit unknown market component required')
        if total is not None and not 20<=total<=80 or spread is not None and abs(spread)>30:raise ValueError('Canonical intended market sanity bound differs')
        if implied!=((total-spread)/2 if total is not None and spread is not None else None):raise ValueError('Implied points disagree with signed spread/total')
        target_rows.append(dict(game_id=gid,team=team,season=year,week=week,period=year*100+week,
            market=dict(game_total_line=total,team_spread_line=spread,team_implied_points=implied)))
        by_team[team].append(target_rows[-1])
    for team,rows in by_team.items():
        rows.sort(key=lambda r:(r['period'],r['game_id']))
        if len({r['period'] for r in rows})!=len(rows):raise ValueError('Ambiguous native team period')
    def example(target):
        history=[r for r in by_team[target['team']] if r['period']<target['period']][-last_n:]
        logs=[]
        for prior in history:
            key=(prior['game_id'],prior['team']);logs.append(dict(game_id=key[0],period=prior['period'],
                physical=deepcopy(volume.get(key)),official=deepcopy(rush.get(key))))
        physical=[r['physical']['value'] if r['physical']is not None else None for r in logs]
        carries=[r['official']['value'] if r['official']is not None else None for r in logs]
        calls=[r['physical']['call'] if r['physical']is not None else None for r in logs]
        call_known=bool(calls) and all(c is not None and not(c['unknown_outcome_events'] or c['unknown_eligibility_events']) for c in calls)
        denominator=sum(c['known_denominator'] for c in calls) if call_known else 0
        values=dict(prior_physical_snaps_mean=math.fsum(physical)/len(physical) if physical and all(v is not None for v in physical) else None,
            prior_official_carries_mean=math.fsum(carries)/len(carries) if carries and all(v is not None for v in carries) else None,
            prior_called_pass_fraction=sum(c['numerator'] for c in calls)/denominator if denominator else None,**target['market'])
        return dict(game_id=target['game_id'],team=target['team'],period=target['period'],parents=values,
            observed_prior_game_slots=len(logs),max_history_period=max((r['period'] for r in logs),default=None),history=logs)
    examples=[example(r) for r in sorted(target_rows,key=lambda r:(r['game_id'],r['team']))]
    training=[r for r in examples if r['period']<reference_before_period]
    means={};counts={}
    for field in FIELDS:
        known=[r['parents'][field] for r in training if r['parents'][field]is not None]
        means[field]=math.fsum(known)/len(known) if known else None;counts[field]=len(known)
    reference=dict(before_period=reference_before_period,selection='same-season target examples strictly before declared reference boundary; each parent uses strict earlier native games',
        target_game_team_keys=[(r['game_id'],r['team']) for r in training],means=means,known_reference_counts=counts,
        max_reference_target_period=max((r['period'] for r in training),default=None),last_n_prior_native_game_slots=last_n)
    reference['sha256']=digest(reference)
    rows=[]
    for row in examples:
        if row['period']<reference_before_period:continue
        if row['max_history_period']is not None and row['max_history_period']>=row['period']:raise ValueError('Current/forward game entered lagged parents')
        centered={f:row['parents'][f]-means[f] if row['parents'][f]is not None and means[f]is not None else None for f in FIELDS}
        metrics={mid:dict(value=centered[left]*centered[right] if centered[left]is not None and centered[right]is not None else None,
            unit=unit,parent_ids=parents,centered_parent_fields=[left,right],not_a_physical_budget=True) for mid,(left,right,parents,unit) in PRODUCTS.items()}
        rows.append({**row,'centered_parents':centered,'metrics':metrics,'reference_sha256':reference['sha256']})
    basis=dict(version=VERSION,before_period=before_period,parent_before_period=parent_period,reference=reference,
        definitions={mid:dict(left=a,right=b,parents=p,unit=u,meaning='Descriptive centered lagged-input product only; no learned/causal response') for mid,(a,b,p,u) in PRODUCTS.items()},game_rows=rows)
    return dict(**basis,semantic_sha256=digest(basis),source_semantic_hashes=dict(environment=environment['semantic_measurements_sha256'],official=official['semantic_measurements_sha256'],markets=markets['semantic_sha256']),
        provenance=dict(environment=deepcopy(environment['provenance']),official=deepcopy(official['provenance']),markets=deepcopy(markets['provenance'])),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['No target-game observed workload is used; missing earlier native-game parent stays unknown, never zero',
            'Declared reference-only centering is preprocessing, not regression, causal effect or predictive model',
            'Reference means use known training-parent samples with separate counts; all-missing reference gives null product',
            'Native scheduled prior slots are retained with missing-source masks; observed log completeness remains unknown',
            'Revised archived intended quote original predecision availability unknown; not reconstructed historical pregame evidence',
            'Products are feature coordinates, not independent evidence or extra physical play/rush/pass budgets'],
        consumer_status='Feature-only descriptive interactions; predictive response/calibration/model/scenario/optimizer/current serving pending')
