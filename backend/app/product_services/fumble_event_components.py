"""Fumble-play incidence and separately proven single-fumble team recovery."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,UTC
from decimal import Decimal
import csv,hashlib,math,re
from pathlib import Path
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team

VERSION='fumble_event_components_v1'
LIVE_PAIRS={'pass':{'PASS','SACK','INTERCEPTION','FUMBLE_RECOVERED_BY_OPPONENT'},'run':{'RUSH'},'qb_spike':{'PASS'},'qb_kneel':{'RUSH'},
    'punt':{'PUNT'},'kickoff':{'KICK_OFF'},'field_goal':{'FIELD_GOAL'},'extra_point':{'XP_KICK'}}
INDICATORS=('pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt')
FLAGS=(*INDICATORS,'no_play','quarter_end','fumble','fumble_lost','fumble_out_of_bounds')
REQUIRED=('game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','fumble','fumble_lost',
    'fumbled_1_team','fumbled_1_player_id','fumbled_2_team','fumbled_2_player_id','fumble_recovery_1_team','fumble_recovery_1_player_id','fumble_recovery_2_team','fumble_recovery_2_player_id')


def _flag(v):
    if v in (None,''):return None
    try:n=float(v)
    except (TypeError,ValueError):return None
    return bool(n) if math.isfinite(n) and n in (0,1) else None


def _eligibility(row):
    kind=row.get('play_type');native=row.get('play_type_nfl')
    if kind=='no_play' or _flag(row.get('no_play'))is True or _flag(row.get('two_point_attempt'))is True:return False,'explicit_exclusion'
    quiet=all(_flag(row.get(k))in (None,False) for k in INDICATORS) and _flag(row.get('fumble'))is not True
    if quiet and (kind=='quarter_end' or _flag(row.get('quarter_end'))is True or row.get('desc')in {'GAME','END GAME'} or (kind in (None,'')and native in {'GAME_START','END_QUARTER','END_GAME'})):return False,'explicit_quiet_administrative'
    if 'no_play'in row and _flag(row['no_play'])is None:return None,'unknown_explicit_no_play'
    if _flag(row.get('two_point_attempt'))is None:return None,'unknown_two_point_status'
    if kind in LIVE_PAIRS and native in LIVE_PAIRS[kind]:return True,'authenticated_native_live_class_pair'
    return None,'unknown_native_live_class'


def build_fumble_event_components(records,*,before_period,source):
    if type(before_period)is not int or not 1<=before_period%100<=18:raise ValueError('Explicit prior REG boundary required')
    games={};ledger=[];seen=set();basis=[]
    for row in records:
        if row.get('season_type')!='REG':continue
        season=Decimal(str(row['season']));week=Decimal(str(row['week']))
        if not season.is_finite() or not week.is_finite() or season!=int(season) or week!=int(week) or not 1<=week<=18:raise ValueError('Native integral period required')
        gid=row['game_id'];parts=gid.split('_');pair={canonical_team(t) for t in parts[2:]}
        if len(parts)!=4 or parts[:2]!=[str(int(season)),f'{int(week):02d}'] or len(pair)!=2:raise ValueError('Native game identity required')
        play=Decimal(str(row['play_id']))
        if not play.is_finite() or play!=int(play):raise ValueError('Native integral play identity required')
        key=(gid,str(int(play)))
        if key in seen:raise ValueError('Duplicate native play')
        seen.add(key)
        for field in ('posteam','defteam','fumbled_1_team','fumbled_2_team','fumble_recovery_1_team','fumble_recovery_2_team'):
            if row.get(field)not in (None,'') and canonical_team(row[field])not in pair:raise ValueError('Native team contradicts game')
        if int(season)*100+int(week)>=before_period:continue
        for field in ('fumbled_1_player_id','fumbled_2_player_id','fumble_recovery_1_player_id','fumble_recovery_2_player_id'):
            if row.get(field)not in (None,'') and not re.fullmatch(r'00-\d{7}',str(row[field])):raise ValueError('Native GSIS fumble/recovery identity required')
        game=games.setdefault(gid,dict(game_id=gid,season=int(season),week=int(week),known_live_plays=0,unknown_live_eligibility=0,
            known_fumble_plays=0,unknown_fumble_outcomes=0,unknown_possible_fumble_plays=0,known_single_fumble_recoveries=0,known_retained=0,known_lost=0,
            unknown_recovery_fumble_plays=0,excluded_source_rows=0))
        eligible,reason=_eligibility(row);fumble=_flag(row.get('fumble'))
        fumbled=[dict(slot=i,team=canonical_team(row[f'fumbled_{i}_team']) if row.get(f'fumbled_{i}_team')not in (None,'') else None,
            native_id=row.get(f'fumbled_{i}_player_id')or None) for i in (1,2) if row.get(f'fumbled_{i}_team')not in (None,'') or row.get(f'fumbled_{i}_player_id')not in (None,'')]
        recovered=[dict(slot=i,team=canonical_team(row[f'fumble_recovery_{i}_team']) if row.get(f'fumble_recovery_{i}_team')not in (None,'') else None,
            native_id=row.get(f'fumble_recovery_{i}_player_id')or None) for i in (1,2) if row.get(f'fumble_recovery_{i}_team')not in (None,'') or row.get(f'fumble_recovery_{i}_player_id')not in (None,'')]
        conflict=fumble is False and bool(fumbled or recovered)
        if conflict:fumble=None
        if eligible is False:game['excluded_source_rows']+=1
        elif eligible is None:
            game['unknown_live_eligibility']+=1
            if fumble is not False:game['unknown_possible_fumble_plays']+=1
        else:
            game['known_live_plays']+=1
            if fumble is None:
                game['unknown_fumble_outcomes']+=1;game['unknown_possible_fumble_plays']+=1
            elif fumble:game['known_fumble_plays']+=1
        proof=None;lost=None
        if eligible is True and fumble is True:
            if len(fumbled)==len(recovered)==1 and fumbled[0]['slot']==1 and fumbled[0]['team']and recovered[0]['team']and fumbled[0]['native_id']and recovered[0]['native_id']and recovered[0]['slot']==1:
                lost=fumbled[0]['team']!=recovered[0]['team'];flag=_flag(row.get('fumble_lost'))
                if flag is not None and flag!=lost:proof='conflicting_native_lost_flag';lost=None
                else:proof='sole_reported_fumbler_and_sole_reported_recovery_team'
            if lost is None:game['unknown_recovery_fumble_plays']+=1
            else:
                game['known_single_fumble_recoveries']+=1;game['known_lost'if lost else 'known_retained']+=1
        if fumble is True or fumbled or recovered or conflict:
            ledger.append(dict(game_id=gid,play_id=key[1],eligible=eligible,fumble_play=fumble,reported_fumblers=fumbled,reported_recoveries=recovered,
                recovery_proof=proof,lost_from_fumbler_team=lost,original_fumble_lost=_flag(row.get('fumble_lost')),source_conflict=conflict,
                pairing='No recovery-slot to fumbler-slot zip; multiple/unmatched occurrences unknown'))
        basis.append(dict(game_id=gid,play_id=key[1],eligible=eligible,eligibility_basis=reason,fumble_play=fumble,source_conflict=conflict))
    rows=[]
    for gid,game in sorted(games.items()):
        unknown=game['unknown_live_eligibility']or game['unknown_fumble_outcomes'];n=game['known_single_fumble_recoveries']
        game.update(exact_fumble_play_count=game['known_fumble_plays']if not game['unknown_possible_fumble_plays'] else None,
            fumble_play_incidence=game['known_fumble_plays']/game['known_live_plays']if game['known_live_plays']and not unknown else None,
            known_single_fumble_loss_fraction=game['known_lost']/n if n else None,
            all_fumble_loss_fraction=game['known_lost']/n if n and not(game['unknown_possible_fumble_plays'] or game['unknown_recovery_fumble_plays'])else None,
            complete_game_coverage='unverified')
        rows.append(game)
    team_rows={}
    for gid in games:
        for team in {canonical_team(t)for t in gid.split('_')[2:]}:
            team_rows[(gid,team)]=dict(game_id=gid,team=team,reported_source_fumbler_slots=0,known_single_recoveries=0,
                known_lost=0,known_retained=0,unknown_recovery_slots=0,unknown_condition_membership=0)
    ledger_keys={(r['game_id'],r['play_id'])for r in ledger}
    for event in basis:
        if event['eligible']is not False and event['fumble_play']is None and (event['game_id'],event['play_id'])not in ledger_keys:
            for (gid,team),value in team_rows.items():
                if gid==event['game_id']:value['unknown_condition_membership']+=1
    for event in ledger:
        if event['eligible']is False:continue
        candidates={r['team']for r in event['reported_fumblers']if r['team']}
        if not event['reported_fumblers']or any(r['team']is None for r in event['reported_fumblers']):
            candidates={team for gid,team in team_rows if gid==event['game_id']}
        if event['eligible']is not True or event['fumble_play']is not True:
            for team in candidates:team_rows[(event['game_id'],team)]['unknown_condition_membership']+=1
            continue
        if not event['reported_fumblers']or any(r['team']is None for r in event['reported_fumblers']):
            for gid,team in team_rows:
                if gid==event['game_id']:team_rows[(gid,team)]['unknown_condition_membership']+=1
        for fumbler in event['reported_fumblers']:
            if fumbler['team']is None:continue
            target=team_rows[(event['game_id'],fumbler['team'])];target['reported_source_fumbler_slots']+=1
            lost=event['lost_from_fumbler_team']
            if lost is None:target['unknown_recovery_slots']+=1
            else:
                target['known_single_recoveries']+=1;target['known_lost'if lost else 'known_retained']+=1
    for target in team_rows.values():
        n=target['known_single_recoveries'];unknown=target['unknown_recovery_slots']or target['unknown_condition_membership']
        target['known_single_fumble_loss_fraction']=target['known_lost']/n if n else None
        target['all_reported_fumble_loss_fraction']=target['known_lost']/n if n and not unknown else None
    core=dict(version=VERSION,before_period=before_period,game_rows=rows,team_recovery_rows=[v for k,v in sorted(team_rows.items())],fumble_ledger=sorted(ledger,key=lambda r:(r['game_id'],r['play_id'])),
        event_basis=sorted(basis,key=lambda r:(r['game_id'],r['play_id'])),
        definitions=dict(occurrence='Any reported fumble on eligible live native play / eligible live native plays, including supported kick classes; not count of individual fumbles',
            recovery='Team loss fraction among eligible fumble plays with a sole reported fumbler and sole reported recovery team; full fraction null under ambiguity'))
    return dict(**core,semantic_sha256=digest(core),provenance=dict(source=deepcopy(source)),forecast=None,
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
        limitations=['Native recovery slot numbers do not prove correspondence to first/second fumbler',
            'Unknown multiple/missing recovery events are not lost or retained zeros',
            'Occurrence play denominator is not a player touch count or official offensive snap budget',
            'Observed conditional recovery fraction is not a forward probability; full-game/original publication coverage unverified'])


def derive_retrospective_fumble_components(snapshot,*,before_period,actual_read_at=None,max_bytes=64*1024*1024,max_rows=100000):
    from backend.app.services.source_capture import verify_snapshot_artifact
    read=clock(actual_read_at or datetime.now(UTC));lock=clock(snapshot.slate_lock_at)
    if read is None or lock is None or not lock<=read<=datetime.now(UTC):raise ValueError('Actual postlock read required')
    verify_snapshot_artifact(snapshot)
    metadata=snapshot.metadata_json or {}
    if snapshot.source_system!='nflreadpy'or snapshot.dataset!='play_by_play'or snapshot.media_type!='text/csv'or metadata.get('contract_id')!='operational_opportunity_source_v1'or metadata.get('loader')!='load_pbp'or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}'or before_period!=snapshot.season*100+snapshot.week:raise ValueError('Indexed native PBP source/scope required')
    if snapshot.byte_count>max_bytes or clock(snapshot.captured_at)is None or clock(snapshot.observed_at)is None or clock(snapshot.captured_at)>read or clock(snapshot.observed_at)>read:raise ValueError('Source byte/clock bound differs')
    with Path(snapshot.artifact_path).open(newline='') as stream:
        reader=csv.DictReader(stream);names=set(reader.fieldnames or [])
        if not set(REQUIRED)<=names:raise ValueError('Native fumble/recovery schema absent')
        fields=set(REQUIRED)|set(FLAGS)|{'desc'};records=[]
        for i,row in enumerate(reader):
            if i>=max_rows:raise ValueError('Source row bound exceeded')
            if row.get('season_type')=='REG' and Decimal(str(row['season']))!=snapshot.season:raise ValueError('Native row season contradicts indexed source')
            records.append({k:(row[k]if row[k]!=''else None)for k in fields&names})
    source=dict(snapshot_id=str(snapshot.snapshot_id),content_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,
        captured_at=str(snapshot.captured_at),observed_at=str(snapshot.observed_at),actual_read_at=read.isoformat(),
        provider_metadata=deepcopy(metadata),original_pregame_availability='Unknown for historical revised source; no backdated current intake')
    result=build_fumble_event_components(records,before_period=before_period,source=source)
    result['provenance'].update(actual_derived_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        original_source_rows=len(records),original_no_play_field_present='no_play'in names,
        primary_dictionary='https://nflfastr.com/reference/fast_scraper.html')
    return result
