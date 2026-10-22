"""Observed defensive event counts conditional on measured offensive exposure."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,UTC
import hashlib,math
from pathlib import Path
from .evaluation_record import digest
from .opportunity_events import validate_event_evidence,_flag
from .official_workload_components import _or
from .environment_context_evidence import _and
from .market_snapshots import canonical_team
from .factual_designation import clock

VERSION='defensive_event_distributions_v1'
DEFINITIONS={
 'X06-M06':dict(event='native sack flag',exposure='official-inclusive physical dropback union: pass attempt OR sack OR official rush with scramble',unit='observed_sacks_per_native_game_conditional_on_dropbacks'),
 'X06-M07':dict(event='native interception flag',exposure='official pass attempts including spikes, excluding sacks',unit='observed_interceptions_per_native_game_conditional_on_pass_attempts')}


def _new():return dict(known_exposure=0,unknown_exposure=0,known_event_count=0,unknown_event_outcome=0)


def _add(counter,eligible,outcome):
    if eligible is False:return
    if eligible is None:counter['unknown_exposure']+=1;return
    counter['known_exposure']+=1
    if outcome is None:counter['unknown_event_outcome']+=1
    elif outcome:counter['known_event_count']+=1


def _finish(c,source_rows):
    exposure=c['known_exposure'] if source_rows and not c['unknown_exposure'] else None
    count=c['known_event_count'] if exposure is not None and not c['unknown_event_outcome'] else None
    if count is not None and count>exposure:raise ValueError('Defensive event count exceeds its physical opportunity budget')
    return dict(**c,exact_observed_exposure=exposure,exact_observed_event_count=count,
        observed_event_rate=count/exposure if count is not None and exposure else None,
        missing_offense_log=not bool(source_rows),full_game_coverage='unverified')


def _distribution(logs,mid):
    known=[(r['metrics'][mid]['exact_observed_exposure'],r['metrics'][mid]['exact_observed_event_count']) for r in logs
        if r['metrics'][mid]['exact_observed_event_count']is not None]
    n=len(known);unknown=len(logs)-n;counts=Counter(y for x,y in known);joint=Counter(known)
    mean=math.fsum(y for x,y in known)/n if n else None
    variance=math.fsum((y-mean)**2 for x,y in known)/n if n else None
    grouped=defaultdict(Counter)
    for x,y in known:grouped[x][y]+=1
    conditional=[]
    for exposure,values in sorted(grouped.items()):
        size=sum(values.values())
        conditional.append(dict(opponent_exposure=exposure,known_paired_games=size,
            count_frequencies=[dict(event_count=y,games=k,known_sample_frequency=k/size,
                all_observed_games_frequency=k/size if not unknown else None) for y,k in sorted(values.items())],
            unknown_game_membership=unknown))
    return dict(observed_game_logs=len(logs),known_paired_games=n,unknown_game_pairs=unknown,
        known_sample_mean_event_count=mean,known_sample_population_variance=variance,
        mean_event_count=mean if not unknown else None,population_variance=variance if not unknown else None,
        known_sample_event_count_histogram=[dict(event_count=y,games=k,frequency=k/n) for y,k in sorted(counts.items())],
        known_sample_joint_histogram=[dict(opponent_exposure=x,event_count=y,games=k,frequency=k/n) for (x,y),k in sorted(joint.items())],
        conditional_distributions=conditional,
        interpretation='Empirical observed native-game frequency, not next-game probability or calibrated distribution')


def build_defensive_event_distributions(parent,*,before_period,cutoff):
    evidence=validate_event_evidence(parent['event_evidence'],before_period=before_period,cutoff=cutoff)
    games={};basis=[]
    for event in evidence['events']:
        gid=event['game_id'];parts=gid.split('_');pair={canonical_team(x) for x in parts[2:]}
        if len(parts)!=4 or len(pair)!=2 or event['team']not in pair:raise ValueError('Native offense/opponent scope required')
        for defense in pair:
            games.setdefault((gid,defense),dict(game_id=gid,season=int(parts[0]),week=int(parts[1]),defense_team=defense,
                offense_team=next(iter(pair-{defense})),source_offense_rows=0,counters={mid:_new() for mid in DEFINITIONS}))
        defense=next(iter(pair-{event['team']}));row=games[(gid,defense)];row['source_offense_rows']+=1
        raw=event['raw_flags']
        if raw.get('defteam')is not None and canonical_team(raw['defteam'])!=defense:raise ValueError('Native defense contradicts game opponent')
        channels={o['channel'] for o in event['opportunities']}
        passing=True if 'pass_attempts'in channels else None if 'pass_attempts'in event['unknown_channels'] else False
        rushing=True if 'rush_attempts'in channels else None if 'rush_attempts'in event['unknown_channels'] else False
        sack=_flag(raw.get('sack'));interception=_flag(raw.get('interception'))
        if event['status']in {'excluded','not_applicable'}:dropback=passing=False
        elif event['status']=='unknown':dropback=passing=None
        else:dropback=_or(passing,sack,_and(rushing,_flag(raw.get('qb_scramble'))))
        if passing is False and interception is True and event['status']not in {'excluded','not_applicable'}:
            raise ValueError('Interception contradicts known official pass-attempt eligibility')
        _add(row['counters']['X06-M06'],dropback,sack);_add(row['counters']['X06-M07'],passing,interception)
        basis.append(dict(game_id=gid,play_id=event['play_id'],offense=event['team'],status=event['status'],
            dropback=dropback,official_pass=passing,sack=sack,interception=interception))
    rows=[];groups=defaultdict(list)
    for key,row in sorted(games.items()):
        row['metrics']={mid:_finish(c,row['source_offense_rows']) for mid,c in row.pop('counters').items()}
        rows.append(row);groups[(row['season'],row['defense_team'])].append(row)
    profiles=[dict(season=season,defense_team=team,metrics={mid:_distribution(logs,mid) for mid in DEFINITIONS}) for (season,team),logs in sorted(groups.items())]
    core=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,game_rows=rows,team_distributions=profiles,
        event_basis=sorted(basis,key=lambda r:(r['game_id'],str(r['play_id']))))
    return dict(**core,semantic_sha256=digest(core),provenance=dict(source=deepcopy(evidence['source']),
        event_receipt_sha256=evidence['sha256'],producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),
        forecast=None,full_game_coverage='unverified',limitations=['Observed offense-event logs, not guaranteed complete games',
            'Unknown source flags/exposures stay unknown; missing offense side is not zero',
            'Native unmapped players remain in full team counts; no player-name joins',
            'Empirical conditional frequencies are not calibrated forecasts or independent model evidence'])


def derive_retrospective_defensive_events(parent_ref,snapshot,*,actual_read_at=None,directory=None):
    from .opportunity_source_capture import load_event_artifact
    now=datetime.now(UTC);read=clock(actual_read_at or now);original=clock(parent_ref['decision_cutoff_at']);lock=clock(snapshot.slate_lock_at)
    if original is None or lock is None or read is None or not original<lock<=read<=now:raise ValueError('Actual nonfuture postlock read and frozen original boundary required')
    parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
    result=build_defensive_event_distributions(parent,before_period=parent_ref['before_period'],cutoff=read)
    result.update(evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
    result['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),
        actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),parent_artifact_ref=deepcopy(parent_ref),
        meaning='Original boundary authenticates frozen bytes only; this is not a new pregame intake')
    return result
