"""Observed sack/interception eligible exposures, never expected event counts."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,UTC
from pathlib import Path
import hashlib,json
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .defensive_event_distributions import VERSION as PARENT_VERSION

VERSION='observed_defensive_opportunity_catalog_v1'
DEFINITIONS={'G23-M07':dict(parent_id='X06-M06',event_field='dropback',unit='observed_sack_eligible_nonspike_dropbacks',
    eligibility='NON-SPIKE official pass OR sack OR official rush with scramble; physical union once, source exclusions inherited')}


def _play_key(gid,pid):
    from decimal import Decimal,InvalidOperation
    try:n=Decimal(str(pid))
    except (InvalidOperation,ValueError):raise ValueError('Native numeric play ID required, never chronology')
    if not n.is_finite() or n<0 or n!=n.to_integral_value():raise ValueError('Native integer play ID required')
    return gid,str(int(n))


def build_defensive_opportunities(source,*,spike_records):
    if source.get('version')!=PARENT_VERSION or source.get('pregame_serving_eligible') is not False or source.get('forecast') is not None:
        raise ValueError('Reviewed nonserving defensive event source required')
    spikes={}
    from .opportunity_events import _flag
    for r in spike_records:
        key=_play_key(r['game_id'],r['play_id'])
        if key in spikes:raise ValueError('Duplicate native spike source row')
        value=r.get('qb_spike')
        if isinstance(value,str):
            try:value=float(value)
            except ValueError:value=None
        spikes[key]=_flag(value)
    events=defaultdict(list);seen=set();sides=set()
    for e in source['event_basis']:
        key=_play_key(e['game_id'],e['play_id'])
        if key in seen:raise ValueError('Duplicate native source event')
        if key not in spikes:raise ValueError('All reviewed native events require raw spike-source coverage')
        seen.add(key);parts=e['game_id'].split('_')
        if len(parts)!=4 or len({canonical_team(x) for x in parts[2:]})!=2:raise ValueError('Native two-team game required')
        pair={canonical_team(x) for x in parts[2:]}
        if e['offense'] not in pair or int(parts[0])*100+int(parts[1])>=source['before_period']:raise ValueError('Native offense/prior period differs')
        sides.update((e['game_id'],t) for t in pair)
        for f in ('dropback','official_pass'):
            if e[f] is not None and type(e[f]) is not bool:raise ValueError('Tri-state source eligibility required')
        defense=next(iter(pair-{e['offense']}));events[(e['game_id'],defense)].append(e)
    rows=[];keys=set();groups=defaultdict(list)
    for r in source['game_rows']:
        key=(r['game_id'],r['defense_team'])
        if key in keys or key not in sides:raise ValueError('Unique complete native defensive sides required')
        keys.add(key);parts=r['game_id'].split('_')
        if (r['season'],r['week'])!=(int(parts[0]),int(parts[1])) or {r['offense_team'],r['defense_team']}!={canonical_team(x) for x in parts[2:]}:
            raise ValueError('Native game-side binding differs')
        basis=events[key]
        if r['source_offense_rows']!=len(basis):raise ValueError('Source opportunity universe differs')
        metrics={}
        for mid,d in DEFINITIONS.items():
            original=[e['dropback'] for e in basis];parent=r['metrics'][d['parent_id']]
            base_known=sum(v is True for v in original);base_unknown=sum(v is None for v in original)
            if (parent['known_exposure'],parent['unknown_exposure'],parent['exact_observed_exposure'])!=(base_known,base_unknown,base_known if basis and not base_unknown else None):raise ValueError('Reviewed dropback exposure differs from native events')
            values=[]
            for e in basis:
                db=e['dropback'];spike=spikes[_play_key(e['game_id'],e['play_id'])]
                conflict=spike is True and (e['sack'] is True or db is True and e['official_pass'] is False)
                value=False if e['status'] in {'excluded','not_applicable'} else None if conflict else False if db is False or spike is True else None if db is None or spike is None else True
                values.append(value)
            known=sum(v is True for v in values);unknown=sum(v is None for v in values);exact=known if basis and not unknown else None
            metrics[mid]=dict(known_eligible_exposures_lower_bound=known,unknown_eligible_events=unknown,exact_observed_opportunities=exact,
                missing_opponent_offense_log=not bool(basis),event_outcome_not_required=True)
        row=dict(native_game_id=r['game_id'],season=r['season'],week=r['week'],defense_team=r['defense_team'],offense_team=r['offense_team'],metrics=metrics)
        rows.append(row);groups[(r['season'],r['defense_team'])].append(row)
    if keys!=sides:raise ValueError('Do not drop source-missing native game sides')
    profiles=[]
    for (season,team),logs in sorted(groups.items()):
        measures={}
        for mid in DEFINITIONS:
            values=[x['metrics'][mid]['exact_observed_opportunities'] for x in logs];known=[x for x in values if x is not None]
            measures[mid]=dict(observed_source_game_sides=len(logs),known_game_sides=len(known),unknown_game_sides=len(values)-len(known),
                known_sample_opportunities=sum(known) if known else None,exact_pooled_opportunities=sum(known) if known and len(known)==len(values) else None)
        profiles.append(dict(season=season,defense_team=team,metrics=measures))
    basis=dict(version=VERSION,before_period=source['before_period'],definitions=DEFINITIONS,game_rows=rows,team_profiles=profiles)
    return dict(**basis,semantic_sha256=digest(basis),pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',
        full_game_coverage='unverified',forecast=None,model_or_optimizer_consumed=False,
        limitations=['NON-SPIKE eligible dropback exposure counts, not sack outcomes, expected events, pass-rush wins or future probabilities',
            'Known zero exposure valid only with source opponent-event proof; missing side/unknown eligibility stays unknown',
            'Native participants remain in full team budgets regardless of alias mapping; no name joins'])


def load_reviewed_defensive_events(ref,snapshot,*,cutoff):
    from . import defensive_event_distributions
    from ..services.source_capture import verify_snapshot_artifact
    actual=clock(cutoff);p=Path(ref['path']).resolve()
    if p.parent!=Path('artifacts/defensive_event_distributions').resolve() or p.name!=ref['sha256']+'.json' or not 0<ref['bytes']<=8*1024*1024:
        raise ValueError('Managed bounded defensive evidence required')
    raw=p.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Defensive evidence bytes differ')
    x=json.loads(raw);v=x['provenance'];retro=v['retrospective_read'];ancestor=retro['parent_artifact_ref']
    if v['producer_code_sha256']!=hashlib.sha256(Path(defensive_event_distributions.__file__).read_bytes()).hexdigest():raise ValueError('Defensive evidence producer differs')
    if x['semantic_sha256']!=digest({k:x[k] for k in ('version','before_period','definitions','game_rows','team_distributions','event_basis')}):raise ValueError('Defensive evidence semantic core differs')
    for t in (clock(v.get('actual_publication_at')),clock(retro.get('actual_read_at')),clock(retro.get('actual_derived_at')),clock(snapshot.captured_at)):
        if actual is None or t is None or t>actual:raise ValueError('Actual source clock missing or future')
    observed,captured=clock(snapshot.observed_at),clock(snapshot.captured_at)
    original,lock,read,derived,published=[clock(t) for t in (retro.get('original_evidence_boundary_at'),retro.get('source_lock_at'),retro.get('actual_read_at'),retro.get('actual_derived_at'),v.get('actual_publication_at'))]
    if (observed is None or captured is None or actual>datetime.now(UTC) or observed>captured
            or None in (original,lock,read,derived,published) or not captured<=original<lock<=read<=derived<=published<=actual
            or clock(ancestor.get('decision_cutoff_at'))!=original or clock(snapshot.slate_lock_at)!=lock
            or clock(ancestor.get('source_captured_at'))!=captured):raise ValueError('Source chronology differs')
    if (str(snapshot.snapshot_id)!=ancestor['source_snapshot_id'] or snapshot.content_sha256!=ancestor['source_sha256']
            or snapshot.source_system!='nflreadpy' or snapshot.dataset!='play_by_play' or snapshot.media_type!='text/csv'
            or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}' or (snapshot.metadata_json or {}).get('contract_id')!='operational_opportunity_source_v1'
            or x['before_period']!=snapshot.season*100+snapshot.week or x['before_period']!=ancestor['before_period']
            or v['source'].get('snapshot_id')!=str(snapshot.snapshot_id) or v['source'].get('content_sha256')!=snapshot.content_sha256
            or v['event_receipt_sha256']!=ancestor['event_receipt_sha256']):
        raise ValueError('Indexed source/event boundary pairing differs')
    if not 0<snapshot.byte_count<=64*1024*1024:raise ValueError('Bounded indexed raw source required')
    verify_snapshot_artifact(snapshot)
    q=Path(ancestor['path']).resolve()
    if q.parent!=Path('artifacts/opportunity_events').resolve() or q.name!=ancestor['artifact_sha256']+'.json.gz' or not 0<ancestor['compressed_bytes']<=16*1024*1024:raise ValueError('Managed bounded compressed ancestor required')
    b=q.read_bytes()
    if len(b)!=ancestor['compressed_bytes'] or hashlib.sha256(b).hexdigest()!=ancestor['artifact_sha256']:raise ValueError('Compressed ancestor bytes differ')
    return x


def read_spike_source(snapshot,*,before_period):
    import csv
    records=[];total=0
    with Path(snapshot.artifact_path).open(newline='') as stream:
        for r in csv.DictReader(stream):
            total+=1
            if total>200000:raise ValueError('Bounded indexed source row count required')
            if r.get('season_type')!='REG':continue
            try:season,week=int(r['season']),int(r['week'])
            except (ValueError,KeyError):raise ValueError('Native REG period required')
            if season*100+week>=before_period:continue
            parts=r['game_id'].split('_')
            if parts[:2]!=[str(season),f'{week:02}']:raise ValueError('Raw native game/period differs')
            records.append(dict(game_id=r['game_id'],play_id=r['play_id'],qb_spike=r.get('qb_spike')))
    if total!=snapshot.row_count:raise ValueError('Indexed raw source cardinality differs')
    return records
