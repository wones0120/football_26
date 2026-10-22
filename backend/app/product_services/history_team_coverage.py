"""Strictly prior same-team versus other-team observed history coverage."""
from collections import defaultdict
from copy import deepcopy
import math
from uuid import UUID
from .evaluation_record import digest
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from .market_snapshots import canonical_team
from .workload_venue_splits import CHANNELS

VERSION='observed_history_team_coverage_v1'


def build_history_team_coverage(weekly,*,before_period,last_n=8):
    if weekly.get('version')!=WEEKLY_VERSION or weekly.get('before_period')!=before_period or weekly.get('pregame_serving_eligible') is not False:raise ValueError('Matched nonserving observed weekly source required')
    if type(before_period) is not int or not 1<=before_period%100<=18 or type(last_n) is not int or not 1<=last_n<=32:raise ValueError('Explicit prior REG history window required')
    people=defaultdict(list);seen=set();attachments=defaultdict(set)
    for r in weekly['rows']:
        season,week,native,team,pid=(r[k] for k in ('season','week','source_player_id','team','player_master_id'))
        if type(season) is not int or type(week) is not int or not 1<=week<=18 or season*100+week>=before_period or r['season_type']!='REG':raise ValueError('Strict prior native REG source required')
        if not isinstance(native,str) or not native:raise ValueError('Native history identity required')
        team=canonical_team(team) if team else None;key=(native,season,week,team)
        if key in seen:raise ValueError('Duplicate native player/team/period')
        seen.add(key)
        if pid is not None:
            if str(UUID(pid))!=pid:raise ValueError('Canonical history UUID spelling required')
            attachments[native].add(pid)
        counts={ch:r['metrics'].get(mid,{}).get('denominator') for ch,mid in CHANNELS.items()}
        if any(v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v<0 or int(v)!=v) for v in counts.values()):raise ValueError('Known nonnegative official history exposure required')
        people[native].append(dict(season=season,week=week,team=team,player_master_id=pid,counts=counts))
    if any(len(ids)>1 for ids in attachments.values()):raise ValueError('Native history has contradictory canonical attachments')
    rows=[]
    for native,logs in sorted(people.items()):
        logs=sorted(logs,key=lambda r:(r['season'],r['week'],str(r['team'])))
        for target in logs:
            period=target['season']*100+target['week'];available=[r for r in logs if r['season']*100+r['week']<period];prior=available[-last_n:]
            selected_periods={(r['season'],r['week']) for r in prior}
            if any(sum((r['season'],r['week'])==p for r in available)>1 for p in selected_periods):raise ValueError('Ambiguous same-period native history chronology')
            # Multiple source team records in one period cannot be silently ordered by team spelling.
            if len({(r['season'],r['week']) for r in prior})!=len(prior):raise ValueError('Ambiguous same-period native history chronology')
            known_team=target['team'] is not None and all(r['team'] is not None for r in prior)
            same=[r for r in prior if target['team'] is not None and r['team'] is not None and r['team']==target['team']];other=[r for r in prior if target['team'] is not None and r['team'] is not None and r['team']!=target['team']]
            channels={}
            for ch in CHANNELS:
                sides={}
                for label,sample in (('same_team',same),('other_team_observed',other)):
                    vals=[r['counts'][ch] for r in sample];known=[v for v in vals if v is not None]
                    sides[label]=dict(known_exposure_logs=len(known),unknown_exposure_logs=len(vals)-len(known),known_exposure_sum=sum(known),exact_exposure_sum=sum(known) if len(known)==len(vals) and known_team and prior else None)
                a,b=(sides[k]['exact_exposure_sum'] for k in ('same_team','other_team_observed'))
                channels[ch]=sides|dict(same_team_exposure_fraction=a/(a+b) if a is not None and b is not None and a+b>0 else None)
            rows.append(dict(source_player_id=native,player_master_id=target['player_master_id'],season=target['season'],week=target['week'],team=target['team'],
                observed_prior_logs=len(prior),requested_prior_logs=last_n,prior_native_periods=[[r['season'],r['week'],r['team']] for r in prior],same_team_prior_logs=len(same),other_team_prior_logs=len(other),
                unknown_team_logs=sum(r['team'] is None for r in prior),target_team_known=target['team'] is not None,
                same_team_log_fraction=len(same)/len(prior) if prior and known_team else None,
                metrics=channels))
    facts=dict(version=VERSION,prior_native_period_fields=['season','week','team'],exposure_fraction_unit='fraction_of_observed_prior_official_opportunities',candidate_id='X08-M06',before_period=before_period,last_n_prior_observed_native_logs=last_n,rows=rows,
        definition='Prior native observed history same-team vs other-team log/exposure coverage at each historical source team-period; not an actual forecast transport decision')
    return facts|dict(semantic_sha256=digest(facts),provenance=deepcopy(weekly['provenance']),identity_review_requests=deepcopy(weekly['identity_review_requests']),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False,
        limitations=['Historical target team is a revised observed source label, not original pregame team proof; no current roster or role inferred',
            'Other-team history is available observed source history, not proof any forecast transported or should transport it',
            'Strictly prior observed logs only; missing source games are not DNP/zero, no cross-player alias/name matching',
            'Unknown team or count masks exact fractions; zero opportunity denominator is undefined; current target workload is excluded',
            'Cross-season prior logs are explicitly retained and identified as observed history, not claimed same-regime or transferable evidence'])


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('Observed history coverage cannot serve models/forecasts/optimizer')
    return value
