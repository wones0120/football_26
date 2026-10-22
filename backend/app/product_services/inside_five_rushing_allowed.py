"""Official-inclusive opponent rushing TD conversion from native inside-five plays."""
from collections import defaultdict
from datetime import datetime,UTC
from decimal import Decimal
from pathlib import Path
import math,csv,hashlib
from .factual_designation import clock
from .evaluation_record import digest
from .fumble_event_components import _flag,_eligibility
from .market_snapshots import canonical_team
from .participation_source_components import _int

VERSION='inside_five_rushing_allowed_v1'


def _and(a,b):return False if a is False or b is False else True if a is True and b is True else None


def _yardline(value):
    if value in(None,'')or type(value)is bool:return None
    try:n=float(value)
    except(TypeError,ValueError):return None
    return n if math.isfinite(n)and 0<=n<=100 else None


def _finish(events):
    eligible=[e for e in events if e['eligible']is True and e['defense']is not None]
    unknown=sum(e['eligible']is None or e['defense']is None for e in events)
    known=[e['rush_td']for e in eligible if e['rush_td']is not None];missing=len(eligible)-len(known)
    attempts=len(eligible)if not unknown else None
    td=sum(known)if not unknown and not missing else None
    return dict(exact_official_inside5_rushes=attempts,exact_inside5_rush_tds=td,value=td/attempts if td is not None and attempts else None,
        known_eligible_rush_lower_bound=len(eligible),known_td_lower_bound=sum(known),known_outcome_exposures=len(known),
        known_outcome_sample_fraction=sum(known)/len(known)if known else None,unknown_eligibility_or_side=unknown,unknown_td_outcomes=missing,
        unit='official_opponent_rushing_touchdowns_per_official_inside5_rush')


def build_inside_five_rushing_allowed(records,*,before_period):
    if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=18:raise ValueError('Explicit prior REG boundary required')
    expected=set();seen=set();groups=defaultdict(list);basis=[]
    for raw in records:
        year=_int(raw['season']);week=_int(raw['week']);gid=raw['game_id'];parts=gid.split('_');play=str(_int(raw['play_id']))
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or not 1<=week<=22:raise ValueError('Native game/period required')
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate native game/play')
        seen.add(key)
        if raw.get('season_type')!='REG'or year*100+week>=before_period:continue
        sides={canonical_team(t)for t in parts[2:]}
        if len(sides)!=2:raise ValueError('Two native game sides required')
        for side in sides:expected.add((gid,side))
        off=canonical_team(raw['posteam'])if raw.get('posteam')else None;defense=canonical_team(raw['defteam'])if raw.get('defteam')else None
        if any(t is not None and t not in sides for t in(off,defense))or off is not None and off==defense:raise ValueError('Native offense/defense contradict game')
        rushing=_flag(raw.get('rush_attempt'));passing=_flag(raw.get('pass_attempt'));sack=_flag(raw.get('sack'));scramble=_flag(raw.get('qb_scramble'));spike=_flag(raw.get('qb_spike'))
        conflict=(rushing is True and(passing is not False or sack is not False or spike is True))or(scramble is True and(rushing is not True or passing is True or sack is True))
        if conflict:rushing=None
        yardline=_yardline(raw.get('yardline_100'))
        inside=None if yardline is None else yardline<=5
        eligible=_and(_eligibility(raw)[0],_and(rushing,inside))
        if eligible is False:continue
        team=defense if off is not None and defense is not None else None
        td=_flag(raw.get('rush_touchdown'));td_team=canonical_team(raw['td_team'])if raw.get('td_team')else None
        if td_team is not None and td_team not in sides:raise ValueError('Native TD team contradicts game')
        outcome_conflict=td is True and(_flag(raw.get('touchdown'))is False or _flag(raw.get('pass_touchdown'))is True or td_team is not None and off is not None and td_team!=off)
        if outcome_conflict:td=None
        event=dict(game_id=gid,play_id=play,offense=off,defense=team,original_defense=defense,eligible=eligible,preplay_yardline_100=yardline,
            original_official_rush_flag=_flag(raw.get('rush_attempt')),original_pass_flag=passing,original_sack_flag=sack,original_scramble_flag=scramble,original_spike_flag=spike,
            official_flag_conflict=conflict,rush_td=td,original_rush_td=_flag(raw.get('rush_touchdown')),original_td_team=td_team,outcome_conflict=outcome_conflict,official_kneel=_flag(raw.get('qb_kneel')))
        basis.append(event)
        for side in {team}if team is not None else sides:groups[(gid,side)].append(event)
    rows=[dict(game_id=gid,defense=side,**_finish(groups[(gid,side)]))for gid,side in sorted(expected)]
    profiles=[]
    for season,team in sorted({(int(gid[:4]),side)for gid,side in expected}):
        events=[e for(gid,side),items in groups.items()if side==team and int(gid[:4])==season for e in items]
        profiles.append(dict(season=season,defense=team,observed_games=sorted(gid for gid,side in expected if side==team and int(gid[:4])==season),**_finish(events)))
    core=dict(version=VERSION,catalog_id='G15-M09',before_period=before_period,team_game_rows=rows,profiles=profiles,event_basis=sorted(basis,key=lambda e:(e['game_id'],int(e['play_id']))),
        definition='Opponent official rushing TD / all official inside5 rushes with preplay yardline100 in[0,5]; allnative rushers including kneels/scrambles, no2PT/no_play; source-live-class pair preserves absent vs explicit-null no_play',
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Observed log coverage is not proof of complete game or original pregame availability','No passing, redzone-drive-trip or future TD chance interpretation','Unknown eligibility, native side, zone or outcome remain unknown; known sample remains separate'])
    return dict(**core,semantic_sha256=digest(core))


def derive_retrospective_inside_five_rushing_allowed(snapshot,*,before_period,actual_read_at=None,max_bytes=64*1024*1024,max_rows=100000):
    from backend.app.services.source_capture import verify_snapshot_artifact
    read=clock(actual_read_at or datetime.now(UTC));lock=clock(snapshot.slate_lock_at)
    if read is None or lock is None or not lock<=read<=datetime.now(UTC):raise ValueError('Actual nonfuture postlock read required')
    verify_snapshot_artifact(snapshot)
    metadata=snapshot.metadata_json or {}
    if snapshot.source_system!='nflreadpy'or snapshot.dataset!='play_by_play'or snapshot.media_type!='text/csv'or metadata.get('contract_id')!='operational_opportunity_source_v1'or metadata.get('loader')!='load_pbp'or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}'or before_period!=snapshot.season*100+snapshot.week:raise ValueError('Indexed native source/scope required')
    if snapshot.byte_count>max_bytes or any(clock(v)is None or clock(v)>read for v in(snapshot.captured_at,snapshot.observed_at)):raise ValueError('Source byte or clock bound differs')
    required={'game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','pass_attempt','rush_attempt','sack','qb_scramble','qb_spike','qb_kneel','two_point_attempt','yardline_100','rush_touchdown'}
    optional={'no_play','quarter_end','desc','fumble','touchdown','pass_touchdown','td_team'}
    with Path(snapshot.artifact_path).open(newline='')as stream:
        reader=csv.DictReader(stream);names=set(reader.fieldnames or [])
        if not required<=names:raise ValueError('Native official inside5 schema missing')
        records=[]
        for i,row in enumerate(reader):
            if i>=max_rows:raise ValueError('Native source row bound exceeded')
            if row.get('season_type')=='REG'and Decimal(str(row['season']))!=snapshot.season:raise ValueError('Native season contradicts source')
            records.append({k:row[k]if row[k]!=''else None for k in(required|optional)&names})
    result=build_inside_five_rushing_allowed(records,before_period=before_period)
    result['provenance']=dict(source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,
        captured_at=str(snapshot.captured_at),observed_at=str(snapshot.observed_at),actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
        producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),eligibility_helper_sha256=hashlib.sha256(Path(__file__).with_name('fumble_event_components.py').read_bytes()).hexdigest(),
        original_source_rows=len(records),original_no_play_field_present='no_play'in names,provider_metadata=metadata,
        original_availability='Revised historical source capture; original pregame availability unknown',primary_dictionary='https://www.nflfastr.com/articles/field_descriptions.html')
    return result
