"""Retrospective opportunity quantiles under strictly prior snap stability."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,UTC
import math
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .recent_snap_features import VERSION as SNAP_VERSION, _number
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from .schedule_context_features import VERSION as SCHEDULE_VERSION
from .player_role_features import KNOWN_POSITIONS

VERSION='observed_prior_stable_snap_opportunity_quantiles_v1'
CONDITIONS=dict(prior_scheduled_games=3,minimum_offense_fraction=.6,maximum_fraction_range=.1,
               quantile=.9,quantile_method='linear_order_statistic_h=(n-1)*0.9',fraction_comparison_tolerance=1e-12)
METRICS={'X02-M06':('targets','G09-M01',{'WR','TE','RB','FB'}),
         'X02-M07':('carries','G07-M01',{'QB','RB','FB'})}


def normalize_stability_snaps(frozen,validated,*,before_period):
    if validated.get('version')!=SNAP_VERSION or validated.get('before_period')!=before_period:
        raise ValueError('Exact reviewed snap source period required')
    actors={(r['pfr_player_id'],r['team']):r['player_master_id'] for r in validated['actor_trends']}
    rows={};excluded=[]
    for record in frozen['rows']:
        raw=record['raw'];season,week=raw.get('season'),raw.get('week')
        if raw.get('game_type')!='REG' or season!=before_period//100 or season*100+week>=before_period:
            excluded.append(dict(source_row_id=record['source_row_id'],reason='Outside strict prior same-season REG'));continue
        team=canonical_team(raw['team']);native=raw.get('pfr_player_id');key=(native,team)
        if key not in actors:
            excluded.append(dict(source_row_id=record['source_row_id'],reason='No reviewed native identity scope'));continue
        snaps=_number(raw.get('offense_snaps'),count=True);fraction=_number(raw.get('offense_pct'))
        if snaps==0 and fraction is not None and fraction>0:snaps=fraction=None
        role=raw.get('position');role=role if isinstance(role,str) and role in KNOWN_POSITIONS else None
        gid=raw['game_id'];parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(season),f'{week:02}'] or team not in {canonical_team(t) for t in parts[2:]}:
            raise ValueError('Snap native game binding differs')
        item=dict(season=season,week=week,team=team,native_game_id=gid,pfr_player_id=native,
                  player_master_id=actors[key],offense_snaps=snaps,offense_fraction=fraction,source_position=role,
                  source_records=[])
        k=(gid,native,team);proof={p:record[p] for p in ('source_row_id','ingest_run_id','created_at')}
        if k in rows:
            if {k:v for k,v in rows[k].items() if k!='source_records'}!={k:v for k,v in item.items() if k!='source_records'}:
                raise ValueError('Equivalent snap revision has conflicting role/count/share')
        else:rows[k]=item
        rows[k]['source_records'].append(proof)
    return dict(version='source_native_snap_stability_inputs_v1',before_period=before_period,
                rows=[r for _,r in sorted(rows.items())],excluded_source_rows=excluded,
                provenance=deepcopy(validated['provenance']),identity_review_requests=deepcopy(validated['identity_review_requests']),
                pregame_serving_eligible=False)


def _qualification(prior,roles):
    """A known failed criterion proves exclusion even if another input is unknown."""
    known=[p for p in prior if p is not None]
    if any(p['offense_snaps']==0 or p['offense_fraction'] is not None and p['offense_fraction']<.6
           or p['source_position'] is not None and p['source_position'] not in roles for p in known):return False
    positions={p['source_position'] for p in known if p['source_position'] is not None}
    shares=[p['offense_fraction'] for p in known if p['offense_fraction'] is not None]
    if len(positions)>1 or shares and max(shares)-min(shares)>.1+1e-12:return False
    if len(known)!=3 or any(p['offense_snaps'] is None or p['offense_fraction'] is None or p['source_position'] is None for p in known):return None
    return True


def _q90(values):
    if not values:return None
    values=sorted(values);h=(len(values)-1)*.9;lo=math.floor(h);hi=math.ceil(h)
    return values[lo]+(h-lo)*(values[hi]-values[lo])


def build_stable_snap_quantiles(weekly,schedule,snaps,*,before_period,cutoff):
    decision=clock(cutoff)
    if (decision is None or decision>datetime.now(UTC) or snaps.get('before_period')!=before_period
            or snaps.get('version')!='source_native_snap_stability_inputs_v1' or snaps.get('pregame_serving_eligible') is not False
            or weekly.get('version')!=WEEKLY_VERSION or weekly.get('pregame_serving_eligible') is not False
            or schedule.get('version')!=SCHEDULE_VERSION or schedule.get('pregame_serving_eligible') is not False or weekly['before_period']<before_period):
        raise ValueError('Matching actual nonserving source contracts required')
    if clock(weekly['provenance'].get('actual_derived_at')) is None or clock(weekly['provenance']['actual_derived_at'])>decision:
        raise ValueError('Weekly source unavailable at cutoff')
    if type(before_period) is not int or not 1<=before_period%100<=18 or not 2012<=before_period//100<=decision.year:
        raise ValueError('Explicit prior REG source period required')
    games=defaultdict(list);binding={}
    for g in schedule['game_rows']:
        if g['game_type']!='REG' or g['season']!=before_period//100 or g['season']*100+g['week']>=before_period:continue
        for team in (g['home_team'],g['away_team']):
            key=(g['season'],g['week'],team)
            if key in binding:raise ValueError('Ambiguous scheduled team game')
            binding[key]=g['game_id'];games[(g['season'],team)].append(g)
    for gs in games.values():gs.sort(key=lambda r:r['week'])
    byactor=defaultdict(dict);identities=defaultdict(set)
    for s in snaps['rows']:
        for field,count in (('offense_snaps',True),('offense_fraction',False)):
            v=s[field]
            if v is not None and _number(v,count=count)!=v:raise ValueError('Normalized source count/fraction invalid')
        if s['offense_snaps']==0 and s['offense_fraction'] is not None and s['offense_fraction']>0:
            raise ValueError('Normalized snap/share contradiction')
        if s['native_game_id']!=binding.get((s['season'],s['week'],s['team'])):raise ValueError('Snap/schedule binding differs')
        key=(s['season'],s['team'],s['pfr_player_id'])
        if s['week'] in byactor[key]:raise ValueError('Duplicate native snap week')
        identities[key].add(s['player_master_id']);byactor[key][s['week']]=s
    weekly_lookup={}
    for r in weekly['rows']:
        if r['season']!=before_period//100 or r['season']*100+r['week']>=before_period:continue
        if r['native_game_id'] not in (None,'',binding.get((r['season'],r['week'],r['team']))):raise ValueError('Weekly native game differs')
        if r['player_master_id'] is None:continue
        key=(r['season'],r['week'],r['team'],r['player_master_id'])
        if key in weekly_lookup:raise ValueError('Ambiguous canonical weekly actor')
        weekly_lookup[key]=r
    rows=[]
    for key,source_games in sorted(byactor.items()):
        season,team,native=key
        if len(identities[key])!=1:raise ValueError('Canonical snap identity changes')
        pid=next(iter(identities[key]));metrics={};all_slots=[]
        gs=games[(season,team)]
        for mid,(channel,input_mid,roles) in METRICS.items():
            slots=[]
            for i,g in enumerate(gs):
                if i<3:continue
                prior=[source_games.get(p['week']) for p in gs[i-3:i]]
                qualified=_qualification(prior,roles)
                response=weekly_lookup.get((season,g['week'],team,pid)) if pid is not None else None
                n=response['metrics'].get(input_mid,{}).get('denominator') if response else None
                if n is not None and (type(n) not in {int,float} or not math.isfinite(n) or n<0 or int(n)!=n):raise ValueError('Official response count invalid')
                slots.append(dict(target_native_game_id=g['game_id'],target_week=g['week'],qualified=qualified,
                    prior_native_game_ids=[p['game_id'] for p in gs[i-3:i]],prior_source_snaps=deepcopy(prior),
                    official_response_count=n,response_source_ref=deepcopy(response['source_ref']) if response else None))
            eligible=[s for s in slots if s['qualified'] is True];unknown=sum(s['qualified'] is None for s in slots)
            observed=[s['official_response_count'] for s in eligible if s['official_response_count'] is not None]
            missing=len(eligible)-len(observed);sample=_q90(observed)
            metrics[mid]=dict(channel=channel,qualified_target_games=len(eligible),unknown_qualification_games=unknown,
                missing_qualified_responses=missing,known_response_games=len(observed),known_response_counts=observed,
                known_sample_q90=sample,exact_conditional_q90=sample if not unknown and not missing else None,
                unit='official_opportunity_count',slots=slots)
        rows.append(dict(season=season,team=team,pfr_player_id=native,player_master_id=pid,metrics=metrics))
    semantic_rows=deepcopy(rows)
    for r in semantic_rows:
        for m in r['metrics'].values():
            for slot in m['slots']:
                slot.pop('response_source_ref')
                for s in slot['prior_source_snaps']:
                    if s:s.pop('source_records')
    basis=dict(version=VERSION,before_period=before_period,conditions=CONDITIONS,rows=semantic_rows,
        definition='Historical next-scheduled-game observed opportunity q90 under strictly prior stable source-snap participation, not future tail forecast')
    return basis|dict(rows=rows,semantic_sha256=digest(basis),provenance=dict(weekly=deepcopy(weekly['provenance']),snaps=deepcopy(snaps['provenance']),schedule=deepcopy(schedule['provenance'])),
        identity_review_requests=deepcopy(snaps['identity_review_requests']),pregame_serving_eligible=False,
        evidence_use='postlock_descriptive_not_pregame_or_serving',forecast=None,models_or_optimizer_consumed=False,
        limitations=['Current response never qualifies its prior condition; missing scheduled games not skipped or filled',
            'Stable snap participation is the declared source condition, not healthy/stable opportunity/full-role guarantee',
            'Observed empirical quantile and cohort size only, no calibrated future tail or outcome-blind experiment',
            'Missing source actor/weekly response remains unknown, never DNP/zero; unresolved canonical actors retained',
            'Current retained revision and historical publication availability unknown; all artifacts nonserving'])


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or value.get('pregame_serving_eligible') is not False or purpose!='offline_descriptive':
        raise ValueError('Observed stable-snap quantiles cannot serve forecasts/models/optimizer')
    return value
