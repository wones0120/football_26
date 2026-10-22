"""Separate native return mechanisms and observed physical return-TD counts."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,UTC
from decimal import Decimal,InvalidOperation
from pathlib import Path
import csv,hashlib,re
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .fumble_event_components import build_fumble_event_components,_flag,REQUIRED,FLAGS
from . import fumble_event_components as fumble_source

VERSION='return_touchdown_components_v1'
CHANNELS=('interception_possessions','kickoff_actual_returns','punt_actual_returns','opponent_fumble_recoveries')
EXTRA=('return_touchdown','touchdown','td_team','return_team','return_yards','pass_touchdown','rush_touchdown','interception',
 'interception_player_id','kickoff_attempt','punt_attempt','kickoff_returner_player_id','punt_returner_player_id','touchback',
 'kickoff_fair_catch','kickoff_downed','kickoff_out_of_bounds','punt_fair_catch','punt_downed','punt_out_of_bounds','punt_blocked','own_kickoff_recovery','own_kickoff_recovery_td')


def _and(a,b):return False if a is False or b is False else True if a is True and b is True else None


def _counter():return dict(known_exposures=0,unknown_exposure_membership=0,known_matched_return_TDs=0,unknown_matched_TD_outcomes=0)


def _finish(c):
    n=c['known_exposures'];unknown=c['unknown_exposure_membership']or c['unknown_matched_TD_outcomes']
    return dict(**c,exact_exposures=None if c['unknown_exposure_membership']else n,
        exact_matched_return_TDs=None if unknown else c['known_matched_return_TDs'],
        known_exposure_sample_TD_fraction=c['known_matched_return_TDs']/n if n and not c['unknown_matched_TD_outcomes']else None,
        observed_TD_per_exposure=c['known_matched_return_TDs']/n if n and not unknown else None)


def _kick_return(row,kind):
    """An attempt is not an actual return; fair catches/touchbacks stay outside."""
    attempt=_flag(row.get('kickoff_attempt'if kind=='kickoff'else 'punt_attempt'))
    if attempt is False:
        native=row.get('kickoff_returner_player_id'if kind=='kickoff'else 'punt_returner_player_id')
        return None if row.get('play_type')==kind and native else False
    if row.get('play_type')!=kind or row.get('play_type_nfl')!=('KICK_OFF'if kind=='kickoff'else 'PUNT'):return None
    blocked=_flag(row.get('punt_blocked'))if kind=='punt'else _flag(row.get('own_kickoff_recovery'))
    if blocked is not False:return None
    flags=('touchback','kickoff_fair_catch','kickoff_downed','kickoff_out_of_bounds')if kind=='kickoff'else ('touchback','punt_fair_catch','punt_downed','punt_out_of_bounds')
    values=[_flag(row.get(k))for k in flags]
    yards=row.get('return_yards');number=None
    if yards not in (None,''):
        try:number=Decimal(str(yards))
        except InvalidOperation:pass
        if number is not None and not number.is_finite():number=None
    if any(v is True for v in values):
        return None if number is not None and number!=0 else False
    if any(v is None for v in values):return None
    native=row.get('kickoff_returner_player_id'if kind=='kickoff'else 'punt_returner_player_id')
    return _and(attempt,True if native else None)


def build_return_touchdown_components(records,*,before_period,source):
    if not isinstance(records,(list,tuple)):raise ValueError('Bounded native record sequence required')
    base=build_fumble_event_components(records,before_period=before_period,source=source)
    eligibility={(r['game_id'],r['play_id']):r for r in base['event_basis']}
    recoveries={(r['game_id'],r['play_id']):r for r in base['fumble_ledger']}
    gamekeys=[r['game_id']for r in base['game_rows']];teams={}
    for gid in gamekeys:
        for team in {canonical_team(t)for t in gid.split('_')[2:]}:
            teams[(gid,team)]=dict(game_id=gid,team=team,known_physical_return_TDs=0,unknown_return_TD_membership=0,channels={c:_counter()for c in CHANNELS})
    ledger=[];gaps=Counter()
    for row in records:
        if row.get('season_type')!='REG':continue
        if int(Decimal(str(row['season'])))*100+int(Decimal(str(row['week'])))>=before_period:continue
        gid=row['game_id'];play=str(int(Decimal(str(row['play_id']))));key=(gid,play);pair={t for g,t in teams if g==gid}
        evidence=eligibility[key];eligible=evidence['eligible']
        def team(field):
            v=row.get(field)
            if v in (None,''):return None
            v=canonical_team(v)
            if v not in pair:raise ValueError('Native return/TD team contradicts game')
            return v
        tdteam=team('td_team');retteam=team('return_team');defteam=team('defteam')
        for field in ('interception_player_id','kickoff_returner_player_id','punt_returner_player_id'):
            if row.get(field)not in (None,'')and not re.fullmatch(r'00-\d{7}',str(row[field])):raise ValueError('Native return GSIS ID required')
        rt=_flag(row.get('return_touchdown'));td=_flag(row.get('touchdown'))
        conflict=rt is True and (td is False or _flag(row.get('pass_touchdown'))is True or _flag(row.get('rush_touchdown'))is True)
        realized=_and(eligible,None if conflict else _and(rt,td))
        interception=_flag(row.get('interception'))
        if row.get('play_type')in {'run','qb_kneel','punt','kickoff','field_goal','extra_point'}and interception is None:interception=False
        if interception is True and row.get('play_type')!='pass':interception=None
        mechanisms={'interception_possessions':(_and(eligible,interception),defteam),
            'kickoff_actual_returns':(_and(eligible,_kick_return(row,'kickoff')),retteam),
            'punt_actual_returns':(_and(eligible,_kick_return(row,'punt')),retteam)}
        f=recoveries.get(key);fumble=evidence['fumble_play'];recovery=False if fumble is False else None;recoverer=None
        if f and f['eligible']is True and f['fumble_play']is True and f['lost_from_fumbler_team']is not None:
            recovery=f['lost_from_fumbler_team'];recoverer=f['reported_recoveries'][0]['team']
        mechanisms['opponent_fumble_recoveries']=(_and(eligible,recovery),recoverer)
        if _flag(row.get('punt_blocked'))is True:gaps['blocked_punt_mechanism_events']+=1
        if _flag(row.get('own_kickoff_recovery'))is True:gaps['own_kickoff_recovery_mechanism_events']+=1
        if conflict:gaps['conflicting_offensive_return_TD_flags']+=1
        for member in pair:
            output=teams[(gid,member)]
            if realized is True and tdteam==member:output['known_physical_return_TDs']+=1
            elif realized is not False and (tdteam is None or tdteam==member):output['unknown_return_TD_membership']+=1
            for channel,(predicate,membership)in mechanisms.items():
                c=output['channels'][channel]
                if predicate is True and membership==member:
                    c['known_exposures']+=1
                    if realized is True and tdteam==member:c['known_matched_return_TDs']+=1
                    elif realized is not False and (tdteam is None or tdteam==member):c['unknown_matched_TD_outcomes']+=1
                elif predicate is not False and (membership is None or membership==member):c['unknown_exposure_membership']+=1
        if realized is not False or any(v[0]is not False for v in mechanisms.values()):
            ledger.append(dict(game_id=gid,play_id=play,eligible=eligible,eligibility_basis=evidence['eligibility_basis'],
                physical_return_TD=realized,source_td_team=tdteam,source_return_team=retteam,source_conflict=conflict,
                mechanisms={k:dict(exposure=v[0],team=v[1])for k,v in mechanisms.items()},
                original_native_fields={k:deepcopy(row.get(k))for k in EXTRA},raw_no_play_present='no_play'in row,
                raw_no_play=deepcopy(row.get('no_play'))))
    rows=[];profiles=defaultdict(list)
    for (gid,team),row in sorted(teams.items()):
        row['exact_physical_return_TDs']=None if row['unknown_return_TD_membership']else row['known_physical_return_TDs']
        row['channels']={k:_finish(v)for k,v in row['channels'].items()};rows.append(row);profiles[(int(gid[:4]),team)].append(row)
    distributions=[]
    for (season,team),games in sorted(profiles.items()):
        observed=[g['exact_physical_return_TDs']for g in games if g['exact_physical_return_TDs']is not None];n=len(observed);unknown=len(games)-n
        hist=[dict(return_TDs=k,games=v,known_sample_frequency=v/n,all_observed_games_frequency=None if unknown else v/n)for k,v in sorted(Counter(observed).items())]
        distributions.append(dict(season=season,team=team,known_games=n,unknown_games=unknown,observed_return_TD_histogram=hist,
            mechanism_totals={c:_finish({k:sum(g['channels'][c][k]for g in games)for k in _counter()})for c in CHANNELS}))
    basis=dict(version=VERSION,before_period=before_period,catalog_id='X06-M09',team_game_rows=rows,
        team_distributions=distributions,event_ledger=sorted(ledger,key=lambda r:(r['game_id'],int(r['play_id']))),mechanism_scope_gaps=dict(gaps))
    return dict(**basis,semantic_sha256=digest(basis),provenance=dict(source=deepcopy(source)),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        definitions=dict(physical_return_TDs='Native return_touchdown AND touchdown on an eligible physical play, counted once for td_team',
            interception_possessions='Eligible native interception possessions for explicit defteam, including no return advancement',
            kickoff_actual_returns='Native kickoff returner + return_team, explicit non-return flags false; not all kickoffs',
            punt_actual_returns='Native punt returner + return_team, explicit non-return flags false; not all punts',
            opponent_fumble_recoveries='Sole typed native fumbler/recoverer, proven lost to other team; no recovery-slot zip'),
        limitations=['Mechanism channels may overlap on one play; never sum their TD credits or divide all return TDs by only one channel exposure',
            'Blocked-kick/own-kick/other mechanisms remain explicit coverage gaps; no catch/return chance inferred from missing IDs',
            'Uncertain native live eligibility/outcome/team masks exact count; absent return team is not initial offense by default',
            'Native team-grain retains all actors; no canonical/name attachment or invented player role',
            'Observed source logs and empirical frequencies only; full-game completeness/original publication unverified, not future return-TD probability'])


def derive_retrospective_return_components(snapshot,*,before_period,actual_read_at=None,max_bytes=64*1024*1024,max_rows=100000):
    from backend.app.services.source_capture import verify_snapshot_artifact
    read=clock(actual_read_at or datetime.now(UTC));lock=clock(snapshot.slate_lock_at);metadata=snapshot.metadata_json or {}
    if read is None or lock is None or not lock<=read<=datetime.now(UTC):raise ValueError('Actual retrospective postlock read required')
    verify_snapshot_artifact(snapshot)
    if snapshot.source_system!='nflreadpy'or snapshot.dataset!='play_by_play'or snapshot.media_type!='text/csv'or metadata.get('contract_id')!='operational_opportunity_source_v1'or metadata.get('loader')!='load_pbp'or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}'or before_period!=snapshot.season*100+snapshot.week:raise ValueError('Indexed native source/scope required')
    if snapshot.byte_count>max_bytes or clock(snapshot.observed_at)is None or clock(snapshot.captured_at)is None or not clock(snapshot.observed_at)<=clock(snapshot.captured_at)<=read:raise ValueError('Native source clock/byte bound differs')
    records=[]
    with Path(snapshot.artifact_path).open(newline='')as stream:
        reader=csv.DictReader(stream);names=set(reader.fieldnames or [])
        if not(set(REQUIRED)|set(EXTRA))<=names:raise ValueError('Native return/mechanism fields absent')
        fields=set(REQUIRED)|set(EXTRA)|set(FLAGS)|{'desc'}
        for index,row in enumerate(reader):
            if index>=max_rows:raise ValueError('Native source row bound exceeded')
            if row.get('season_type')=='REG'and Decimal(str(row['season']))!=snapshot.season:raise ValueError('Native source season differs')
            records.append({k:row[k]if row[k]!=''else None for k in fields&names})
    source=dict(snapshot_id=str(snapshot.snapshot_id),content_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,captured_at=str(snapshot.captured_at),observed_at=str(snapshot.observed_at),actual_read_at=read.isoformat(),original_publication='unknown; revised retrospective source')
    value=build_return_touchdown_components(records,before_period=before_period,source=source)
    value['provenance'].update(actual_derived_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        fumble_helper_sha256=hashlib.sha256(Path(fumble_source.__file__).read_bytes()).hexdigest(),
        source_rows=len(records),original_no_play_field_present='no_play'in names,primary_dictionary='https://nflfastr.com/reference/fast_scraper.html')
    return value
