"""Unavailable actors' source-observed prior opportunities, never donated."""
from collections import defaultdict
from copy import deepcopy
from uuid import UUID
import math,re
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .official_absence_source import VERSION as ABSENCE_VERSION
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from .weekly_feature_ancestry import VERSION as ANCESTRY_VERSION

VERSION='unavailable_teammate_opportunity_v1'
CHANNELS={'pass_attempts':'attempts','rush_attempts':'carries','targets':'targets'}

def build_unavailable_opportunity(absences,weekly,ancestry,games):
    if (absences.get('version'),weekly.get('version'),ancestry.get('version'))!=(ABSENCE_VERSION,WEEKLY_VERSION,ANCESTRY_VERSION)or any(x.get('pregame_serving_eligible')is not False for x in(absences,weekly,ancestry)):raise ValueError('Reviewed nonserving absence/weekly/normalization parents required')
    if weekly['before_period']!=ancestry['before_period']:raise ValueError('Same frozen weekly normalization scope required')
    fields=ancestry['field_order']
    if len(set(fields))!=len(fields)or not set(CHANNELS.values())<=set(fields):raise ValueError('Unique source count-field ancestry required')
    diagnostics={r['source_id']:r for r in ancestry['rows']}
    if len(diagnostics)!=len(ancestry['rows']):raise ValueError('Unique normalization source row required')
    index={};uncertain_team=set()
    for r in weekly['rows']:
        if r['season_type']!='REG':raise ValueError('REG weekly source required')
        native=r['source_player_id'];team=canonical_team(r['team'])if r['team']else None
        if team is None:uncertain_team.add((r['season'],r['week'],native));continue
        key=(r['season'],r['week'],team,native)
        if key in index:raise ValueError('Unique native player/week/team source required')
        index[key]=r
    schedule={};calendars=defaultdict(list)
    for g in games:
        if g['game_type']!='REG':continue
        gid=g['game_id'];parts=gid.split('_');year,week=g['season'],g['week'];home,away=canonical_team(g['home_team']),canonical_team(g['away_team'])
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or canonical_team(parts[2])!=away or canonical_team(parts[3])!=home or home==away or gid in schedule:raise ValueError('Unique native schedule binding required')
        schedule[gid]=g
        for team in(home,away):calendars[(year,team)].append(g)
    for gs in calendars.values():
        gs.sort(key=lambda g:g['week'])
        if len({g['week']for g in gs})!=len(gs):raise ValueError('Unique native scheduled team/week required')
    rows=[];excluded=[];seen=set();seen_native=set()
    for a in absences['rows']:
        if a['source_row_key']in seen:raise ValueError('Unique official source absence fact required')
        seen.add(a['source_row_key'])
        if not a['ordinary_absence_anchor']:
            if a['source_status']not in{'DID_NOT_PLAY','EMERGENCY_THIRD_QB_EXCEPTION'}:raise ValueError('Explicit excluded source status required')
            excluded.append(deepcopy(a));continue
        if a['source_status']!='NOT_ACTIVE':raise ValueError('Only literal ordinary NOT_ACTIVE can create unavailable ledger')
        year,week,team=a['season'],a['week'],canonical_team(a['team']);gid=a['native_game_id'];g=schedule.get(gid)
        if g is None or(g['season'],g['week'])!=(year,week)or team not in{canonical_team(g['home_team']),canonical_team(g['away_team'])}or year*100+week>=weekly['before_period']:raise ValueError('Exact prior source absence native game required')
        native=a['source_native_gsis_id'];pid=a['player_master_id']
        if pid is not None and str(UUID(pid))!=pid:raise ValueError('Canonical UUID spelling required')
        nk=(gid,team,native)
        if native is not None and nk in seen_native:raise ValueError('Duplicate sourced native unavailable actor would double count')
        seen_native.add(nk)
        gs=calendars[(year,team)];i=next(i for i,x in enumerate(gs)if x['game_id']==gid);prior=gs[max(0,i-2):i];slots=[]
        for pg in prior:
            key=(year,pg['week'],team,native);r=index.get(key)if native is not None else None;counts={c:None for c in CHANNELS};identity=False;reason=None
            if r is None:reason='missing_native_weekly_row_unknown_not_DNP_or_zero'
            elif(year,pg['week'],native)in uncertain_team:reason='additional_unknown_team_membership_masks_source_slot'
            else:
                if r['native_game_id']not in(None,'',pg['game_id']):raise ValueError('Present source native game conflicts with scheduled baseline')
                d=diagnostics.get(r['source_ref']['source_id'])
                if d is None or d['quarantined']or(d['season'],d['week'],d['team'],d['source_player_id'],d['player_master_id'])!=(year,pg['week'],team,native,r['player_master_id'])or len(d['fields'])!=len(fields):raise ValueError('Same source-row native/identity/count normalization required')
                for c,f in CHANNELS.items():
                    state,value,_=d['fields'][fields.index(f)]
                    if state=='KNOWN':
                        if type(value)not in(int,float)or not math.isfinite(value)or value<0 or int(value)!=value:raise ValueError('Known official count must be a nonnegative integer')
                        counts[c]=value
                    elif value is not None:raise ValueError('Unknown normalization branch cannot manufacture a count')
                identity=pid is not None and r['player_master_id']==pid
                if not identity:reason='canonical_attachment_unknown_or_conflicting'
            slots.append(dict(native_game_id=pg['game_id'],week=pg['week'],source_row_present=r is not None,source_id=r['source_ref']['source_id']if r else None,native_counts=counts,canonical_qualified=identity,unknown_reason=reason))
        metrics={}
        for c in CHANNELS:
            vals=[s['native_counts'][c]for s in slots];native_mean=sum(vals)/2 if len(vals)==2 and all(v is not None for v in vals)else None
            value=native_mean if native_mean is not None and all(s['canonical_qualified']for s in slots)else None
            metrics[c]=dict(native_prior_two_game_mean=native_mean,catalog_unavailable_prior_mean=value,unit='source_observed_official_opportunities_per_scheduled_game',known_source_slots=sum(v is not None for v in vals),expected_baseline_slots=2,applicability='All native players may have official pass/rush/target opportunity; position never supplies zero')
        rows.append(dict(source_fact=deepcopy(a),native_game_id=gid,team=team,season=year,week=week,source_native_gsis_id=native,player_master_id=pid,preabsence_scheduled_slots=slots,metrics=metrics))
    grouped=defaultdict(list)
    for r in rows:grouped[(r['native_game_id'],r['team'])].append(r)
    totals=[]
    for(gid,team),rs in sorted(grouped.items()):
        metrics={}
        for c in CHANNELS:
            values=[r['metrics'][c]['catalog_unavailable_prior_mean']for r in rs];known=[v for v in values if v is not None]
            metrics[c]=dict(complete_unavailable_prior_mean_sum=sum(known)if len(known)==len(values)else None,known_partial_sum=sum(known)if known else None,known_actor_count=len(known),unknown_actor_count=len(values)-len(known),total_meaning='Full sum only if every potentially relevant sourced ordinary inactive actor has proven compatible volume; no transfer')
        totals.append(dict(native_game_id=gid,team=team,source_ordinary_inactive_count=len(rs),metrics=metrics))
    core=dict(version=VERSION,candidate_id='G17-M09',before_period=weekly['before_period'],rows=rows,team_game_totals=totals,excluded_source_domains=excluded,
        definition='ALL source-proven ordinary inactive actors retain fixed TWO immediately preceding same-team/season scheduled game official pass/rush/target means. Unknown slots never skipped/filled; missing canonical mass separate; team partial sum is not total vacated budget.',replacement_redistribution=None,route_or_TD_opportunity=None,forecast=None)
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,model_consumed=False,optimizer_consumed=False)
