"""Observed workload by declared native Eastern kickoff-time groups."""
from copy import deepcopy
import csv
from pathlib import Path
import re
import hashlib
from .evaluation_record import digest
from .schedule_context_features import load_schedule_context
from .market_snapshots import canonical_team
from .workload_venue_splits import build_workload_venue_splits, CHANNELS

VERSION='workload_kickoff_groups_v1'
CONTEXT_VERSION='native_eastern_kickoff_groups_v1'
DICTIONARY='https://raw.githubusercontent.com/nflverse/nflreadr/main/data-raw/dictionary_schedules.csv'


def _seconds(value):
    if not isinstance(value,str):return None
    match=re.fullmatch(r'(\d{2}):(\d{2})(?::(\d{2}))?',value.strip())
    if not match:return None
    hour,minute,second=(int(x or 0) for x in match.groups())
    return hour*3600+minute*60+second if hour<24 and minute<60 and second<60 else None


def normalize_kickoff_context(records,schedule,*,before_period):
    games={r['game_id']:r for r in schedule['game_rows']};rows=[];seen=set()
    for raw in records:
        gid=raw['game_id'];game=games.get(gid)
        if game is None or gid in seen:raise ValueError('Unique authenticated native schedule required')
        seen.add(gid)
        if (str(raw['season'])!=str(game['season']) or str(raw['week'])!=str(game['week'])
                or raw['game_type']!=game['game_type'] or canonical_team(raw['home_team'])!=game['home_team']
                or canonical_team(raw['away_team'])!=game['away_team']):raise ValueError('Native kickoff scope/orientation differs')
        if game['game_type']!='REG' or game['season']*100+game['week']>=before_period:continue
        original=raw.get('gametime');seconds=_seconds(original)
        rows.append(dict(game_id=gid,season=game['season'],week=game['week'],source_gametime=original,
            native_eastern_kickoff_seconds=seconds,at_or_after_19_eastern=seconds>=19*3600 if seconds is not None else None))
    rows.sort(key=lambda r:r['game_id'])
    basis=dict(version=CONTEXT_VERSION,before_period=before_period,rows=rows,
        definition='Native source gametime in24-hour Eastern: >=19:00 versus before19:00, predeclared threshold',
        source_clock_timezone='Eastern',dictionary=DICTIONARY)
    return dict(**basis,semantic_sha256=digest(basis),provenance=deepcopy(schedule['provenance']),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)


def load_kickoff_context(snapshot,*,before_period,cutoff):
    schedule=load_schedule_context(snapshot,cutoff=cutoff)
    with Path(snapshot.artifact_path).open(newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames or []
        result=normalize_kickoff_context(reader,schedule,before_period=before_period)
    result['provenance'].update(source_gametime_field_present='gametime'in fields,
        producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return schedule,result


def build_workload_kickoff_groups(weekly,schedule,kickoff,*,before_period):
    base=build_workload_venue_splits(weekly,schedule,before_period=before_period)
    if (kickoff.get('version')!=CONTEXT_VERSION or kickoff.get('before_period')!=before_period
            or kickoff.get('pregame_serving_eligible')is not False or not kickoff['provenance'].get('snapshot_id')
            or kickoff['provenance'].get('snapshot_id')!=schedule['provenance'].get('snapshot_id')
            or not kickoff['provenance'].get('sha256') or kickoff['provenance'].get('sha256')!=schedule['provenance'].get('sha256')):
        raise ValueError('Matched authenticated Eastern kickoff/schedule source required')
    lookup={};games={r['game_id']:r for r in schedule['game_rows']}
    for row in kickoff['rows']:
        gid=row['game_id'];game=games.get(gid)
        if (game is None or gid in lookup or game['game_type']!='REG' or row['season']!=game['season']
                or row['week']!=game['week'] or row['season']*100+row['week']>=before_period):raise ValueError('Prior unique native kickoff scope required')
        seconds=_seconds(row['source_gametime'])
        if row['native_eastern_kickoff_seconds']!=seconds or row['at_or_after_19_eastern']!=(seconds>=19*3600 if seconds is not None else None):
            raise ValueError('Native Eastern clock/group contradicts source')
        lookup[gid]=row
    rows=[]
    for actor in base['rows']:
        logs=[deepcopy(log)|dict(kickoff=deepcopy(lookup.get(log['native_game_id']))) for log in actor['logs']]
        unknown=sum(r['kickoff']is None or r['kickoff']['at_or_after_19_eastern']is None for r in logs)
        channels={}
        for ch in CHANNELS:
            groups={}
            for flag,label in ((True,'at_or_after_19_eastern'),(False,'before_19_eastern')):
                sample=[r for r in logs if r['kickoff']is not None and r['kickoff']['at_or_after_19_eastern']is flag]
                missing=sum(r['counts'][ch]is None for r in sample)
                total=sum(r['counts'][ch] for r in sample) if sample and not missing else None
                groups[label]=dict(observed_logs=len(sample),unknown_exposures=missing,exact_sum=total,
                    mean_per_observed_log=total/len(sample) if total is not None else None)
            night,early=(groups[k]['mean_per_observed_log'] for k in ('at_or_after_19_eastern','before_19_eastern'))
            channels[ch]=dict(**groups,night_minus_earlier=night-early if night is not None and early is not None and not(unknown or actor['native_team_scope_unknown']) else None,
                unit='official_opportunities_per_observed_source_log')
        rows.append({k:deepcopy(actor[k]) for k in ('season','team','source_player_id','player_master_id','native_team_scope_unknown')}|
            dict(metrics={'G21-M06':dict(channels=channels,unknown_kickoff_logs=unknown)},logs=logs))
    semantic=[{**r,'logs':[{k:v for k,v in log.items() if k!='source_ref'} for log in r['logs']]} for r in rows]
    basis=dict(version=VERSION,candidate_id='G21-M06',before_period=before_period,definition=kickoff['definition'],rows=semantic)
    return basis|dict(rows=rows,semantic_sha256=digest(basis),source_semantic_hashes=dict(**base['source_semantic_hashes'],kickoff=kickoff['semantic_sha256']),
        provenance=dict(**deepcopy(base['provenance']),kickoff=deepcopy(kickoff['provenance'])),
        identity_review_requests=deepcopy(base['identity_review_requests']),evidence_use=base['evidence_use'],
        pregame_serving_eligible=False,forecast=None,models_or_optimizer_consumed=False,
        limitations=base['limitations']+['Declared >=19:00 Eastern kickoff group, not verified national-TV/broadcaster designation',
            'Native kickoff time can be revised; original scheduled-time publication availability unknown',
            'Unknown/unparseable native clocks mask exact differences; no inference from venue time zone',
            'Observed group difference only, not causal prime-time adjustment or predictive fit'])
