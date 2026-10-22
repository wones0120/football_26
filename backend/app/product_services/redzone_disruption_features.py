"""Observed preplay red-zone sacks and typed original-offense turnover events."""
from copy import deepcopy
from .defense_context_evidence import _number
from .environment_context_evidence import _and
from .market_snapshots import canonical_team
from .evaluation_record import digest
from .defensive_event_distributions import VERSION as DEF_VERSION
from .explosive_touchdown_features import VERSION as OFF_VERSION
from .fumble_event_components import VERSION as FUMBLE_VERSION

VERSION='observed_redzone_disruption_features_v1'


def _or(a,b):return True if a is True or b is True else False if a is False and b is False else None

def _counter():return dict(known_exposures=0,known_events=0,unknown_exposures=0,unknown_outcomes=0)

def _add(m,eligible,event):
    if eligible is None:m['unknown_exposures']+=1
    elif eligible:
        m['known_exposures']+=1
        if event is None:m['unknown_outcomes']+=1
        else:m['known_events']+=event


def _key(r):
    n=_number(r['play_id'])
    if n is None or n<0 or int(n)!=n:raise ValueError('Native play key required')
    return r['game_id'],int(n)


def _index(rows):
    result={}
    for r in rows:
        k=_key(r)
        if k in result:raise ValueError('Duplicate native disruption event')
        result[k]=r
    return result


def build_redzone_disruption_features(defense,offense,fumbles,records,*,before_period,raw_source):
    for value,version in ((defense,DEF_VERSION),(offense,OFF_VERSION),(fumbles,FUMBLE_VERSION)):
        if value.get('version')!=version or value.get('before_period')!=before_period or value.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Matched descriptive source contracts required')
    if defense['provenance']['event_receipt_sha256']!=offense['source_event_sha256']:raise ValueError('Original physical source event pairing differs')
    sources=[defense['provenance']['source'],offense['source'],fumbles['provenance']['source'],raw_source]
    for field in ('snapshot_id','content_sha256'):
        if not sources[0].get(field) or any(s.get(field)!=sources[0][field] for s in sources):raise ValueError('Immutable raw source pairing differs')
    for raw in records:
        season,week=_number(raw.get('season')),_number(raw.get('week'))
        if raw.get('season_type')!='REG' or season is None or week is None or int(season)!=season or int(week)!=week or not 1<=week<=18 or season*100+week>=before_period or raw['game_id'].split('_')[:2]!=[str(int(season)),f'{int(week):02}']:raise ValueError('Strict prior native raw source period required')
    dindex=_index(defense['event_basis']);oindex={};findex=_index(fumbles['event_basis']);ledger=_index(fumbles['fumble_ledger']);rawindex=_index(records)
    for game in offense['game_rows']:
        for event in game['events']:
            key=_key(dict(event,game_id=game['game_id']))
            if key in oindex:raise ValueError('Duplicate official source event')
            oindex[key]=event
    if not set(oindex)<=set(dindex) or not set(dindex)<=set(findex) or not set(dindex)<=set(rawindex):raise ValueError('Complete original event key binding required')
    games={};basis=[]
    for key,e in sorted(dindex.items()):
        raw=rawindex[key];team=e['offense']
        if canonical_team(raw['posteam'])!=team:raise ValueError('Native raw offense differs')
        g=games.setdefault((key[0],team),dict(game_id=key[0],team=team,metrics={name:_counter() for name in ('sack_per_dropback','interception_per_pass','offense_fumble_loss_per_snap','turnover_event_per_snap')}))
        rush=False
        if key in oindex:
            ch={r['channel']:r for r in oindex[key]['channels']};rush=ch['rush']['official_eligibility']
            if ch['pass']['official_eligibility']!=e['official_pass']:raise ValueError('Official pass exposure pairing differs')
        phys=_or(e['dropback'],rush)
        if e['status'] in {'excluded','not_applicable'}:phys=False
        elif e['status']=='unknown':phys=None
        yard=_number(raw.get('yardline_100'));zone=None if yard is None or not 0<=yard<=100 else yard<=20
        f=findex[key];loss=None
        if f['eligible'] is True and f['fumble_play'] is False:loss=False
        elif f['eligible'] is True and f['fumble_play'] is True:
            proof=ledger.get(key)
            if proof and not proof['source_conflict'] and len(proof['reported_fumblers'])==1:
                owner=proof['reported_fumblers'][0]['team']
                if owner is not None:loss=proof['lost_from_fumbler_team'] if owner==team else False
        turnover=_or(e['interception'],loss)
        exposures={'sack_per_dropback':(_and(zone,e['dropback']),e['sack']), 'interception_per_pass':(_and(zone,e['official_pass']),e['interception']),
            'offense_fumble_loss_per_snap':(_and(zone,phys),loss),'turnover_event_per_snap':(_and(zone,phys),turnover)}
        for name,(eligible,event) in exposures.items():_add(g['metrics'][name],eligible,event)
        basis.append(dict(game_id=key[0],play_id=key[1],team=team,source_yardline_100=yard,redzone_membership=zone,physical_snap=phys,offense_fumble_loss=loss,turnover_event=turnover,exposures=exposures))
    rows=[]
    for _,g in sorted(games.items()):
        for m in g['metrics'].values():
            n=m['known_exposures'];known=n-m['unknown_outcomes'];m['value']=m['known_events']/n if n and not(m['unknown_outcomes'] or m['unknown_exposures']) else None;m['known_sample_rate']=m['known_events']/known if known else None
        rows.append(g)
    facts=dict(version=VERSION,candidate_id='X05-M06',before_period=before_period,game_rows=rows,event_basis=basis,source_event_sha256=offense['source_event_sha256'])
    return facts|dict(semantic_sha256=digest(facts),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False,
        limitations=['Official-inclusive preplay inside20 opportunity rates, not whole-drive failure probabilities','Typed original-offense fumbler loss only; opponent return fumbles are not offense losses','Unknown/multiple/missing recovery/team proof is not zero, known sample separately retained','INT OR same-original-offense fumble loss once per physical event; mechanisms never summed'])


def _available_at(provenance,cutoff):
    from .factual_designation import clock
    actual=clock(provenance.get('actual_publication_at'))
    if actual is None or actual>clock(cutoff):raise ValueError('Published source component unavailable at actual cutoff')


def derive_redzone_disruptions(refs,snapshot,*,actual_read_at):
    from datetime import datetime,UTC
    from pathlib import Path
    import hashlib,json,csv,importlib
    from .factual_designation import clock
    from ..services.source_capture import verify_snapshot_artifact
    actual=clock(actual_read_at);lock=clock(snapshot.slate_lock_at)
    if actual is None or lock is None or not lock<=actual<=datetime.now(UTC):raise ValueError('Explicit actual postlock read required')
    period=snapshot.season*100+snapshot.week;metadata=snapshot.metadata_json or {}
    if snapshot.source_system!='nflreadpy' or snapshot.dataset!='play_by_play' or snapshot.media_type!='text/csv' or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}' or metadata.get('contract_id')!='operational_opportunity_source_v1':raise ValueError('Indexed original PBP contract required')
    if clock(snapshot.observed_at)>clock(snapshot.captured_at) or clock(snapshot.captured_at)>actual or snapshot.byte_count>64*1024*1024:raise ValueError('Raw source clock/size differs')
    verify_snapshot_artifact(snapshot);values={}
    for name,folder in [('defense','defensive_event_distributions'),('offense','explosive_touchdown_features'),('fumbles','fumble_event_components')]:
        ref=refs[name];p=Path(ref['path']).resolve();raw=p.read_bytes()
        if p.parent!=Path('artifacts',folder).resolve() or p.name!=ref['sha256']+'.json' or len(raw)!=ref['bytes'] or len(raw)>8*1024*1024 or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Managed compact source bytes differ')
        v=json.loads(raw);provenance=v['provenance'];_available_at(provenance,actual)
        module=importlib.import_module('backend.app.product_services.'+folder)
        expected=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        if provenance.get('producer_code_sha256',provenance.get('producer_sha256'))!=expected:raise ValueError('Compact producer binding differs')
        values[name]=v
    records=[];count=0
    with Path(snapshot.artifact_path).open(newline='') as stream:
        for row in csv.DictReader(stream):
            count+=1
            if count>200000:raise ValueError('Raw source row bound exceeded')
            if row.get('season_type')!='REG':continue
            season,week=_number(row.get('season')),_number(row.get('week'))
            if season is None or week is None or int(season)!=season or int(week)!=week or not 1<=week<=18:raise ValueError('Native raw period unknown')
            if season*100+week<period:records.append({k:row[k] for k in ('game_id','play_id','season','week','season_type','posteam','yardline_100')})
    if count!=snapshot.row_count:raise ValueError('Original raw row cardinality differs')
    source=dict(snapshot_id=str(snapshot.snapshot_id),content_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,observed_at=str(snapshot.observed_at),captured_at=str(snapshot.captured_at),actual_read_at=actual.isoformat())
    result=build_redzone_disruption_features(values['defense'],values['offense'],values['fumbles'],records,before_period=period,raw_source=source)
    result['provenance']=dict(input_refs=deepcopy(refs),source=source,actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),historical_original_availability='Unknown; revised source and actual postlock derivation are descriptive only')
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('RZ disruption descriptions cannot serve forecasts/models/optimizer')
    return value
