"""Exact physical-play and no-huddle catalog views of reviewed source context."""
from collections import defaultdict
from copy import deepcopy
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION='offensive_environment_catalog_v1'


def _count(v):
    if type(v) not in {int,float} or not math.isfinite(v) or v<0 or int(v)!=v:raise ValueError('Nonnegative known count required')
    return int(v)


def build_offensive_environment_catalog(context,*,before_period,last_n=8):
    if context.get('version')!='environment_context_evidence_v1' or context.get('before_period')!=before_period or context.get('forecast') is not None:
        raise ValueError('Matched descriptive environment context required')
    if type(before_period) is not int or not 1<=before_period%100<=18 or type(last_n) is not int or last_n<1:raise ValueError('Explicit REG target/window required')
    rows=[];seen=set();grouped=defaultdict(list)
    for original in context['game_rows']:
        team=canonical_team(original['team']);gid=original['game_id'];parts=gid.split('_')
        season,week=original['season'],original['week'];period=season*100+week
        if len(parts)!=4 or int(parts[0])!=season or int(parts[1])!=week or team not in {canonical_team(p) for p in parts[2:]} or not 1<=week<=18 or period>=before_period:
            raise ValueError('Prior native REG team/game scope required')
        if (team,gid) in seen:raise ValueError('Duplicate team/game')
        seen.add((team,gid))
        volume=original['offensive_play_volume'];snaps=_count(volume['known_offensive_snaps']);unknown=_count(volume['unknown_snap_eligibility'])
        if volume['observed_game_logs']!=1 or snaps!=_count(original['known_offensive_snaps']) or unknown!=_count(original['unknown_snap_eligibility']):raise ValueError('Physical source count contract differs')
        raw=original['metrics']['G01-M06'];den=_count(raw['eligible_events'])
        known=_count(raw['known_outcome_events']);missing=_count(raw['unknown_outcome_events']);uncertain=_count(raw['unknown_eligibility_events'])
        reported=raw['observed_outcome_sum']
        if known==0:
            if reported not in (None,0):raise ValueError('Outcome without known sample')
            n=None;lower=0
        else:n=_count(reported);lower=n
        if den!=snaps or known+missing!=den or lower>known or uncertain!=unknown:raise ValueError('No-huddle physical denominator differs')
        metrics={'G01-M01':dict(value=snaps if unknown==0 else None,known_lower_bound=snaps,unknown_eligibility=unknown,unit='physical_offensive_snaps_per_observed_log'),
            'G01-M06':dict(value=n/den if den and n is not None and not(missing or uncertain) else None,numerator=n,known_numerator_lower_bound=lower,known_outcome_events=known,numerator_basis='observed_known_sample' if known else 'empty_known_sample_lower_bound_only',known_denominator=den,unknown_outcome=missing,unknown_eligibility=uncertain,unit='no_huddle_fraction_of_physical_offensive_snaps')}
        row=dict(game_id=gid,period=period,team=team,metrics=metrics);rows.append(row)
        if season==before_period//100:grouped[team].append(row)
    rows.sort(key=lambda r:(r['period'],r['game_id'],r['team']));windows=[]
    for team,values in sorted(grouped.items()):
        values=sorted(values,key=lambda r:(r['period'],r['game_id']))[-last_n:]
        if len({r['period'] for r in values})!=len(values):raise ValueError('Ambiguous same-team multiple games per period')
        snaps=sum(r['metrics']['G01-M01']['known_lower_bound'] for r in values);unknown=sum(r['metrics']['G01-M01']['unknown_eligibility'] for r in values)
        known_outcomes=sum(r['metrics']['G01-M06']['known_outcome_events'] for r in values);lower=sum(r['metrics']['G01-M06']['known_numerator_lower_bound'] for r in values);n=lower if known_outcomes else None;den=sum(r['metrics']['G01-M06']['known_denominator'] for r in values);missing=sum(r['metrics']['G01-M06']['unknown_outcome'] for r in values)
        windows.append(dict(team=team,observed_game_ids=[r['game_id'] for r in values],metrics={
            'G01-M01':dict(value=snaps/len(values) if not unknown else None,known_lower_bound=snaps/len(values),observed_logs=len(values),unknown_eligibility=unknown),
            'G01-M06':dict(value=n/den if den and n is not None and not(unknown or missing) else None,numerator=n,known_numerator_lower_bound=lower,known_outcome_events=known_outcomes,numerator_basis='observed_known_sample' if known_outcomes else 'empty_known_sample_lower_bound_only',known_denominator=den,unknown_eligibility=unknown,unknown_outcome=missing)}))
    numerical=dict(version=VERSION,before_period=before_period,last_n_observed_same_season_games=last_n,game_rows=rows,team_windows=windows)
    return {**numerical,'semantic_sha256':digest(numerical),'source_context_semantic_sha256':context['semantic_measurements_sha256'],
        'limitations':['Physical union includes official passes/spikes, rushes/kneels and sacks once; not sum of overlapping dropback/rush channels',
            'Observed logs are not independently certified complete NFL games','Missing games do not become zero; windows count observed same-season team logs only'],
        'forecast':None,'model_consumed':False,'optimizer_consumed':False}


def load_reviewed_environment_context(context_ref,snapshot,*,actual_read_at,context_directory=None,parent_directory=None):
    """Verify a reviewed immutable derived context without re-inflating its parent."""
    from pathlib import Path
    from datetime import datetime,UTC
    import hashlib
    from backend.app.services.source_capture import verify_snapshot_artifact
    from .factual_designation import clock
    from .opportunity_source_publication import _managed_json
    from . import environment_context_evidence as producer
    from . import defense_context_evidence as numerical_helper
    import re
    cutoff=clock(actual_read_at);lock=clock(snapshot.slate_lock_at)
    if cutoff is None or lock is None or not lock<=cutoff<=datetime.now(UTC):raise ValueError('Actual nonfuture postlock descriptive read required')
    verify_snapshot_artifact(snapshot)
    if snapshot.source_system!='nflreadpy' or snapshot.dataset!='play_by_play' or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}':raise ValueError('Indexed native PBP source required')
    context,payload,path=_managed_json(context_directory or Path('artifacts/opportunity_context'),context_ref['sha256'],max_bytes=2*1024*1024)
    if str(path)!=context_ref['path'] or len(payload)!=context_ref['bytes']:raise ValueError('Exact managed context reference required')
    provenance=context['provenance'];publication=provenance['artifact_publication'];parent=publication['parent_artifact_ref'];source=provenance['source']
    period=snapshot.season*100+snapshot.week
    if context['before_period']!=period or parent['before_period']!=period or source['snapshot_id']!=str(snapshot.snapshot_id) or source['content_sha256']!=snapshot.content_sha256 or parent['source_snapshot_id']!=str(snapshot.snapshot_id) or parent['source_sha256']!=snapshot.content_sha256 or provenance['event_receipt_sha256']!=parent['event_receipt_sha256']:raise ValueError('Context source/period/ancestry differs')
    observed,captured=clock(snapshot.observed_at),clock(snapshot.captured_at)
    clocks=[observed,captured,clock(parent['decision_cutoff_at']),clock(publication['decision_cutoff_at']),clock(publication['published_at']),cutoff]
    if any(v is None for v in clocks) or any(a>b for a,b in zip(clocks,clocks[1:])) or clocks[2]>=lock:raise ValueError('Context source/publication clocks differ')
    for field,module in (('producer_code_sha256',producer),('numerical_helper_code_sha256',numerical_helper)):
        if provenance[field]!=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed context producer differs')
    if clock(provenance['decision_cutoff_at'])!=clock(publication['decision_cutoff_at']):raise ValueError('Context decision clocks differ')
    for mid in ('G01-M01','G01-M06'):
        lineage=provenance['metric_lineage'][mid]
        if lineage['before_period']!=period or lineage['source_snapshot_id']!=str(snapshot.snapshot_id) or lineage['event_receipt_sha256']!=parent['event_receipt_sha256']:raise ValueError('Metric lineage differs')
    if parent.get('contract_id')!='opportunity_event_artifact_v1' or not re.fullmatch(r'[0-9a-f]{64}',str(parent.get('artifact_sha256'))):raise ValueError('Managed parent identity differs')
    root=Path(parent_directory or 'artifacts/opportunity_events').resolve();parent_path=root/(parent['artifact_sha256']+'.json.gz')
    if str(parent_path)!=parent['path'] or parent_path.stat().st_size!=parent['compressed_bytes']:raise ValueError('Parent managed reference differs')
    h=hashlib.sha256()
    with parent_path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    if h.hexdigest()!=parent['artifact_sha256']:raise ValueError('Parent artifact byte hash differs')
    proof=dict(actual_read_at=cutoff.isoformat(),original_context_ref=deepcopy(context_ref),original_context_provenance=deepcopy(provenance),
        source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,parent_inflated=False,
        trust_boundary='Reviewed server-managed context plus original source/parent bytes; no claim new source derivation or original historical pregame availability')
    return dict(context=context,provenance=proof,evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)


def read_reviewed_environment_catalog(context_ref,snapshot,*,actual_read_at,context_directory=None,parent_directory=None):
    loaded=load_reviewed_environment_context(context_ref,snapshot,actual_read_at=actual_read_at,context_directory=context_directory,parent_directory=parent_directory)
    result=build_offensive_environment_catalog(loaded['context'],before_period=loaded['context']['before_period'])
    result.update({k:loaded[k] for k in ('provenance','evidence_use','pregame_serving_eligible')})
    return result
