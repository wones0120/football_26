"""Observed full-team inside-five versus longitudinal end-zone target allocation."""
from copy import deepcopy
import math
from .evaluation_record import digest
from .player_scoring_zone_components import VERSION as ZONE_VERSION
from .endzone_target_components import VERSION as END_VERSION
VERSION='observed_target_zone_allocation_v1'
USE='postlock_descriptive_not_pregame_or_serving'


def _n(v):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or int(v)!=v or v<0:
        raise ValueError('Nonnegative known integer count required')
    return int(v)


def _index(rows,fields):
    out={}
    for row in rows:
        key=tuple(row[k] for k in fields)
        if key in out:raise ValueError('Duplicate native target allocation key')
        out[key]=row
    return out


def build_target_zone_allocation(zones,endzone,*,before_period):
    for block,version in ((zones,ZONE_VERSION),(endzone,END_VERSION)):
        if block.get('version')!=version or block.get('before_period')!=before_period or block.get('evidence_use')!=USE or block.get('pregame_serving_eligible') is not False:
            raise ValueError('Matched retrospective target contracts required')
    source=zones['provenance']['source'];other=endzone['source']
    for key in ('snapshot_id','content_sha256'):
        if not source.get(key) or source.get(key)!=other.get(key):raise ValueError('Target source identity mismatch')
    if zones['provenance']['event_receipt_sha256']!=endzone['source_event_sha256']:raise ValueError('Target event receipt mismatch')
    zteams=_index(zones['full_team_denominators'],('game_id','team'))
    eteams=_index(endzone['team_game_rows'],('game_id','team'))
    if set(zteams)!=set(eteams):raise ValueError('Target team-game populations differ')
    zactors=_index([r for r in zones['actor_game_rows'] if 'G11-M06' in r['metrics']],('game_id','team','source_player_id'))
    eactors=_index(endzone['actor_game_rows'],('game_id','team','source_player_id'))
    actors=[];teams=[];canonical={}
    for key in sorted(set(zactors)|set(eactors)):
        z,e=zactors.get(key),eactors.get(key);a=(z or {}).get('player_master_id');b=(e or {}).get('player_master_id')
        if a and b and a!=b:raise ValueError('Native target canonical conflict')
        pid=a or b
        if pid:
            ckey=(key[0],pid)
            if ckey in canonical and canonical[ckey]!=key:raise ValueError('Canonical target native/team collision')
            canonical[ckey]=key
        if key[:2] not in zteams:raise ValueError('Target actor outside full-team source universe')
        zcount=z['metrics']['G11-M06'] if z else None;zt=zteams[key[:2]]['channels']['targets']['inside5'];et=eteams[key[:2]]
        pairs={
            'inside5':(_n(zcount['counted_lower_bound']) if zcount else None,zcount['exact_within_log_count'] if zcount else None,_n(zt['counted_lower_bound']),zt['exact_within_log_count']),
            'endzone':(_n(e['known_endzone_targets']) if e else None,e['value'] if e else None,_n(et['known_endzone_targets']),et['value'])}
        channels={}
        for name,(lower,n,team_lower,d) in pairs.items():
            if (lower is not None and lower>team_lower) or (n is not None and _n(n)!=lower) or (d is not None and _n(d)!=team_lower):raise ValueError('Target count/budget inconsistency')
            channels[name]=dict(known_actor_count=lower,exact_actor_count=n,known_team_count=team_lower,exact_team_count=d,
                share=n/d if n is not None and d is not None and d>0 else None,zero_denominator=d==0)
        x,y=channels['inside5']['share'],channels['endzone']['share']
        actors.append(dict(game_id=key[0],team=key[1],source_player_id=key[2],player_master_id=pid,channels=channels,
            endzone_minus_inside5_share=y-x if x is not None and y is not None else None))
    for key in sorted(zteams):
        zr=zteams[key]['channels']['targets']['inside5'];er=eteams[key];members=[r for r in actors if (r['game_id'],r['team'])==key];channels={}
        for name,lower,exact in (('inside5',_n(zr['counted_lower_bound']),zr['exact_within_log_count']),('endzone',_n(er['known_endzone_targets']),er['value'])):
            attributed=sum(r['channels'][name]['known_actor_count'] for r in members if r['channels'][name]['known_actor_count'] is not None)
            if attributed>lower:raise ValueError('Native target allocation exceeds full-team count')
            all_native_counts=all(r['channels'][name]['known_actor_count'] is not None for r in members)
            canonical_mass=sum(r['channels'][name]['known_actor_count'] for r in members if r['player_master_id'] and r['channels'][name]['known_actor_count'] is not None)
            channels[name]=dict(known_canonical_actor_count=canonical_mass,known_native_without_canonical_count=attributed-canonical_mass,missing_actor_channel_rows=sum(r['channels'][name]['known_actor_count'] is None for r in members),known_full_team_count=lower,exact_full_team_count=exact,known_native_actor_count=attributed,
                unresolved_allocation_lower_count=lower-attributed,unattributed_known_count=lower-attributed if all_native_counts else None,unattributed_known_fraction=(lower-attributed)/exact if all_native_counts and exact is not None and exact>0 else None,
                exact_actor_share_sum=sum(r['channels'][name]['share'] for r in members) if exact is not None and exact>0 and all(r['channels'][name]['share'] is not None for r in members) else None)
        teams.append(dict(game_id=key[0],team=key[1],channels=channels))
    basis=dict(version=VERSION,candidate_id='X05-M07',before_period=before_period,actor_game_rows=actors,team_game_rows=teams,
        definition='Separate same-game native receiver shares of all official inside5 LOS targets and source-longitudinal end-zone targets; endzone share minus inside5 share; channels may overlap',
        source=deepcopy(source),source_event_sha256=endzone['source_event_sha256'])
    return basis|dict(semantic_sha256=digest(basis),evidence_use=USE,pregame_serving_eligible=False,
        limitations=['Observed source logs, not complete-game or future allocation probabilities','Inside5 LOS and longitudinal end-zone endpoints overlap; never summed as disjoint budgets','Unknown eligibility/identity attribution masks exact shares; known lower counts and full-team residual retained','Empty denominator undefined; no absent-native actor zeros'],forecast=None,model_consumed=False,optimizer_consumed=False)


def load_target_zone_allocation(refs,*,actual_read_at):
    """Authenticate reviewed immutable parents; retain actual composition clocks."""
    import hashlib,json
    from datetime import datetime,UTC
    from pathlib import Path
    from .factual_designation import clock
    from . import player_scoring_zone_components,endzone_target_components
    actual=clock(actual_read_at)
    if actual is None or actual>datetime.now(UTC):raise ValueError('Nonfuture actual composition clock required')
    values={}
    for name,module,folder in (('zones',player_scoring_zone_components,'player_scoring_zone_components'),('endzone',endzone_target_components,'endzone_target_components')):
        ref=refs[name];path=Path(ref['path']).resolve();root=(Path('artifacts')/folder).resolve()
        if path.parent!=root or ref['bytes']>16*1024*1024:raise ValueError('Managed target input path/size required')
        raw=path.read_bytes()
        if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Managed target bytes changed')
        value=json.loads(raw);p=value['provenance'];published=clock(p.get('actual_publication_at'))
        if published is None or published>actual:raise ValueError('Target input publication unavailable/future')
        expected=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        if p.get('producer_code_sha256',p.get('producer_sha256'))!=expected:raise ValueError('Reviewed target producer differs')
        values[name]=value
    z,e=values['zones'],values['endzone']
    result=build_target_zone_allocation(z,e,before_period=z['before_period'])
    s=result['source']
    rawpath=Path(s['artifact_path']);raw=rawpath.read_bytes()
    if len(raw)>64*1024*1024 or hashlib.sha256(raw).hexdigest()!=s['content_sha256']:raise ValueError('Original target source bytes differ')
    manifest=json.loads(Path(s['manifest_path']).read_text())
    if str(manifest['snapshot_id'])!=s['snapshot_id'] or manifest['content_sha256']!=s['content_sha256']:raise ValueError('Original target source manifest differs')
    for key in ('observed_at','captured_at','effective_at','received_at'):
        if clock(s.get(key)) is None or clock(s[key])>actual:raise ValueError('Target source clock missing/future')
    result['provenance']=dict(input_refs=deepcopy(refs),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
        original_parent_provenance=dict(zones=deepcopy(z['provenance']),endzone=deepcopy(e['provenance'])),
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or value.get('pregame_serving_eligible') is not False or purpose!='offline_descriptive':raise ValueError('Target allocation cannot serve forecasts/models/optimizer')
    return value
