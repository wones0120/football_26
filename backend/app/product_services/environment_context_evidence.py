"""Observed offensive environment from an operationally verified prior event parent.

Game-clock start intervals are pace proxies, not elapsed wall-clock or a claim
that the clock was running. Observed drive IDs are not verified possessions.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .opportunity_events import _flag, validate_event_evidence
from .defense_context_evidence import _number, _hash, _metric, _finish

VERSION = 'environment_context_evidence_v1'
DEFINITIONS = {
    'G01-M01': 'Union physical official offensive snaps per observed game log; pass/rush channels and sack once; spikes/kneels included',
    'G01-M02': 'Known offensive snaps attached to native fixed_drive / distinct observed fixed_drive IDs; not complete possessions',
    'G01-M04': 'Game-clock seconds between adjacent same-offense/same-fixed-drive/same-quarter offensive snap starts; proxy, clock state unknown',
    'G01-M05': 'Same start-interval proxy with both starts qtr1..3 and abs(preplay score_differential)<=7',
    'G01-M06': 'Known no_huddle flag among eligible physical offensive snaps',
    'G01-M07': 'Same start-interval proxy with both starts in qtr1..2',
    'G01-M08': 'Same start-interval proxy with both starts in qtr3..4; overtime separate',
    'G01-M09': 'Same start-interval proxy with both starts trailing by preplay score_differential',
    'G01-M10': 'Same start-interval proxy with both starts leading by preplay score_differential',
    'G02-M01': 'Nonspike reported dropback / (nonspike reported dropback + designed nonkneel rush); scramble only dropback',
    'G02-M02': 'Same pass-call rate, qtr1..3 and abs(preplay score_differential)<=7',
    'G02-M03': 'Observed pass-call indicator minus supplied vendor xpass in [0,1]; vendor model/training chronology unknown',
    'G02-M04': 'Same pass-call rate, preplay down1..2',
    'G02-M05': 'Same pass-call rate, preplay down1',
    'G02-M06': 'Same pass-call rate, preplay down3',
    'G02-M07': 'Same pass-call rate, preplay yardline_100 in [0,20]',
    'G02-M08': 'Same pass-call rate, preplay yardline_100 in [0,5]',
    'G02-M09': 'Same pass-call rate, preplay score_differential<0',
    'G02-M10': 'Same pass-call rate, preplay score_differential>0',
}
PACE = ('G01-M04','G01-M05','G01-M07','G01-M08','G01-M09','G01-M10')
CALLS = tuple(k for k in DEFINITIONS if k.startswith('G02'))
UNITS = {m: 'game_clock_seconds_between_snap_starts' if m in PACE else 'observed_pass_call_fraction_minus_vendor_xpass' if m=='G02-M03' else 'observed_rate' for m in (*PACE,'G01-M06',*CALLS)}
UNITS.update({'G01-M01':'known_snaps_per_observed_game_log','G01-M02':'known_snaps_per_observed_native_drive'})


def _snap(event):
    if event['status'] in {'excluded', 'not_applicable'}:
        return False
    if event['status'] == 'unknown':
        return None
    if any(o['channel'] in {'pass_attempts','rush_attempts'} for o in event['opportunities']):
        return True
    return _flag(event['raw_flags'].get('sack'))


def _call(event):
    raw = event['raw_flags']; snap = _snap(event)
    if snap is not True:
        return 'unknown' if snap is None else 'excluded'
    spike = _flag(raw.get('qb_spike')); kneel = _flag(raw.get('qb_kneel'))
    if spike is True or kneel is True:
        return 'excluded'
    drop = _flag(raw.get('qb_dropback'))
    if drop is True:
        return 'pass' if spike is False else 'unknown'
    rush = any(o['channel']=='rush_attempts' for o in event['opportunities'])
    scramble = _flag(raw.get('qb_scramble'))
    if drop is False and rush and scramble is False and kneel is False:
        return 'rush'
    return 'unknown'


def _conditions(raw):
    q = _number(raw.get('qtr')); score = _number(raw.get('score_differential'))
    down = _number(raw.get('down')); yard = _number(raw.get('yardline_100'))
    validq = q in {1,2,3,4,5}
    neutral = False if validq and q > 3 else None if not validq or score is None else abs(score)<=7
    red = None if yard is None or not 0<=yard<=100 else yard<=20
    goal = None if yard is None or not 0<=yard<=100 else yard<=5
    return dict(neutral=neutral,firsthalf=None if not validq else q in {1,2},secondhalf=None if not validq else q in {3,4},
        trailing=None if score is None else score<0,leading=None if score is None else score>0,
        early=None if down not in {1,2,3,4} else down in {1,2},
        first=None if down not in {1,2,3,4} else down==1,third=None if down not in {1,2,3,4} else down==3,red=red,goal=goal)


def _and(a,b):
    return False if a is False or b is False else None if a is None or b is None else True


def _add(metric, eligibility, value):
    if eligibility is None:
        metric['unknown_eligibility_events'] += 1
    elif eligibility:
        metric['eligible_events'] += 1
        if value is None:
            metric['unknown_outcome_events'] += 1
        else:
            metric['known_outcome_events'] += 1
            metric['observed_outcome_sum'] += value


def build_environment_context_evidence(event_receipt, *, before_period, cutoff, last_n_games=8):
    """Pure measured builder; actual source/parent authentication belongs to intake."""
    if isinstance(last_n_games,bool) or not isinstance(last_n_games,int) or not 1<=last_n_games<=32:
        raise ValueError('Observed-game window must be integer in [1,32]')
    evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
    games={};previous={};basis=[];control_breaks=[]
    timeline=[dict(game_id=e['game_id'],play_id=e['play_id'],event=e) for e in evidence['events']]
    seen={(e['game_id'],int(e['play_id'])) for e in evidence['events']}
    for group in ('unscoped_nonoffensive_rows','scoped_administrative_rows'):
        for raw in event_receipt.get(group,[]):
            gid=str(raw.get('game_id') or '')
            if (raw.get('season_type')!='REG' or not 1<=int(raw['week'])<=18
                    or int(raw['season'])*100+int(raw['week'])>=before_period
                    or gid.split('_')[:2]!=[str(int(raw['season'])),f"{int(raw['week']):02d}"]):
                raise ValueError('Adjacency control lacks valid prior native scope')
            numeric=_number(raw.get('play_id'))
            if numeric is None or not numeric.is_integer():raise ValueError('Adjacency control native play ID missing')
            key=(gid,int(numeric))
            if key in seen:raise ValueError('Duplicate native adjacency control')
            seen.add(key)
            timeline.append(dict(game_id=gid,play_id=str(int(numeric)),control=dict(game_id=gid,play_id=str(int(numeric)),
                source_control_group=group,play_type=raw.get('play_type'))))
    for entry in sorted(timeline,key=lambda e:(e['game_id'],int(e['play_id']))):
        if 'control' in entry:
            control_breaks.append(entry['control']);basis.append(dict(control=entry['control']))
            previous[entry['game_id']]=dict(team=None,snap=False,drive=None,clock=None,qtr=None,conditions={},control=True)
            continue
        event=entry['event']
        raw=event['raw_flags'];key=(event['game_id'],event['team'])
        game=games.setdefault(key,dict(game_id=key[0],team=key[1],season=event['season'],week=event['week'],
            known_offensive_snaps=0,unknown_snap_eligibility=0,known_drive_snaps=0,unknown_drive_snap_ids=0,
            drive_ids=set(),metrics={m:_metric() for m in (*PACE,'G01-M06',*CALLS)},
            interval_rejections=defaultdict(int),vendor_fields=dict(xpass_present=0,xpass_known_bounded=0,pass_oe_present=0,pass_oe_known=0)))
        snap=_snap(event);call=_call(event);conditions=_conditions(raw)
        drive=_number(raw.get('fixed_drive'));drive=str(int(drive)) if drive is not None and drive>=0 and drive.is_integer() else None
        if snap is None:game['unknown_snap_eligibility']+=1
        elif snap:
            game['known_offensive_snaps']+=1
            if drive is None:game['unknown_drive_snap_ids']+=1
            else:game['known_drive_snaps']+=1;game['drive_ids'].add(drive)
        no_huddle=_flag(raw.get('no_huddle'))
        _add(game['metrics']['G01-M06'],snap,None if no_huddle is None else float(no_huddle))
        knowncall=call in {'pass','rush'};call_eligible=True if knowncall else None if call=='unknown' else False
        observed=float(call=='pass') if knowncall else None
        subsets={'G02-M01':True,'G02-M02':conditions['neutral'],'G02-M03':True,'G02-M04':conditions['early'],
            'G02-M05':conditions['first'],'G02-M06':conditions['third'],'G02-M07':conditions['red'],
            'G02-M08':conditions['goal'],'G02-M09':conditions['trailing'],'G02-M10':conditions['leading']}
        xpass=_number(raw.get('xpass'));xpass=xpass if xpass is not None and 0<=xpass<=1 else None
        for m,condition in subsets.items():
            value=None if observed is None or (m=='G02-M03' and xpass is None) else observed-xpass if m=='G02-M03' else observed
            _add(game['metrics'][m],_and(call_eligible,condition),value)
        for field in ('xpass','pass_oe'):
            if field in raw:game['vendor_fields'][field+'_present']+=1
            if _number(raw.get(field)) is not None and (field!='xpass' or xpass is not None):
                game['vendor_fields'][field+('_known_bounded' if field=='xpass' else '_known')]+=1
        current=dict(team=key[1],snap=snap,drive=drive,clock=_number(raw.get('game_seconds_remaining')),qtr=_number(raw.get('qtr')),conditions=conditions)
        prev=previous.get(key[0]);previous[key[0]]=current
        reason=None;elapsed=None;interval_eligibility=True
        if prev is None:reason='first_observed_row'
        elif prev['snap'] is not True or snap is not True:reason='intervening_or_unknown_non_snap; adjacency_not_proven'
        elif drive is None or prev['drive'] is None:reason='drive_unknown'
        elif drive!=prev['drive']:reason='drive_change'
        elif current['qtr'] is None or prev['qtr']!=current['qtr']:reason='quarter_unknown_or_change'
        elif current['clock'] is None or prev['clock'] is None:reason='clock_unknown'
        elif not 0<=current['clock']<=3600 or not 0<=prev['clock']<=3600:reason='regulation_clock_out_of_range_or_overtime'
        elif prev['clock']<current['clock']:reason='nonmonotonic_clock'
        else:elapsed=prev['clock']-current['clock']
        if prev is not None and prev.get('control'):
            reason='source_control_break';elapsed=None
        elif prev is not None and prev['team']!=key[1]:
            reason='offense_change';elapsed=None
        if reason in {'first_observed_row','drive_change','offense_change','source_control_break'}:
            interval_eligibility=False
        elif reason=='quarter_unknown_or_change':
            interval_eligibility=False if current['qtr'] is not None and prev['qtr'] is not None else None
        elif reason=='drive_unknown':interval_eligibility=None
        elif reason=='intervening_or_unknown_non_snap; adjacency_not_proven':
            interval_eligibility=False if snap is False or prev['snap'] is False else None
        if reason:game['interval_rejections'][reason]+=1
        if snap is not False:
            pace_conditions={'G01-M04':True,'G01-M05':conditions['neutral'],'G01-M07':conditions['firsthalf'],
                'G01-M08':conditions['secondhalf'],'G01-M09':conditions['trailing'],'G01-M10':conditions['leading']}
            for m,condition in pace_conditions.items():
                previous_condition=True if m=='G01-M04' else None if prev is None else prev['conditions'].get({
                    'G01-M05':'neutral','G01-M07':'firsthalf','G01-M08':'secondhalf','G01-M09':'trailing','G01-M10':'leading'}[m])
                _add(game['metrics'][m],_and(interval_eligibility,_and(condition,previous_condition)),elapsed)
        basis.append(dict(game_id=key[0],play_id=event['play_id'],team=key[1],snap=snap,call=call,
            conditions=conditions,drive=drive,clock=current['clock'],qtr=current['qtr'],xpass=xpass,no_huddle=no_huddle))
    grouped=defaultdict(list)
    for game in games.values():grouped[game['team']].append(game)
    windows=[]
    def finish(rows):
        metrics={m:_metric() for m in (*PACE,'G01-M06',*CALLS)}
        for row in rows:
            for m,v in row['metrics'].items():
                for k,n in v.items():metrics[m][k]+=n
        snaps=sum(r['known_offensive_snaps'] for r in rows);unknown=sum(r['unknown_snap_eligibility'] for r in rows)
        drives=sum(len(r['drive_ids']) for r in rows);drive_snaps=sum(r['known_drive_snaps'] for r in rows)
        return dict(metrics={m:_finish(v) for m,v in metrics.items()},
            offensive_play_volume=dict(metric_id='G01-M01',known_offensive_snaps=snaps,unknown_snap_eligibility=unknown,
                observed_game_logs=len(rows),known_snaps_per_observed_log=snaps/len(rows) if rows else None),
            observed_drive_volume=dict(metric_id='G01-M02',observed_native_drives=drives,known_attached_snaps=drive_snaps,
                unknown_drive_snap_ids=sum(r['unknown_drive_snap_ids'] for r in rows),known_snaps_per_observed_drive=drive_snaps/drives if drives else None))
    for team,rows in sorted(grouped.items()):
        rows.sort(key=lambda r:(r['season'],r['week'],r['game_id']))
        if len({(r['season'],r['week']) for r in rows})!=len(rows):raise ValueError('Ambiguous multiple team games per period')
        selected=rows[-last_n_games:]
        windows.append(dict(team=team,observed_game_ids=[r['game_id'] for r in selected],**finish(selected)))
    game_rows=[]
    for _,game in sorted(games.items()):
        game_rows.append({k:v for k,v in game.items() if k not in {'metrics','drive_ids'}}|dict(native_drive_ids=sorted(game['drive_ids']),**finish([game])))
    result=dict(version=VERSION,status='observed_descriptive_environment',before_period=before_period,last_n_observed_games=last_n_games,
        definitions=deepcopy(DEFINITIONS),units=deepcopy(UNITS),adjacency_control_breaks=control_breaks,game_rows=game_rows,team_windows=windows,
        limitations=['Observed logs/drives not verified complete games/possessions','Pace is game-clock snap-start proxy; clock-stopped status unavailable, zero intervals retained',
            'Vendor xpass/pass_oe availability/coverage separate from unknown model/training chronology; own expectation model not implemented',
            'Pure checksum requires actual immutable source/parent verification by intake; original historical availability unknown'],forecast=None)
    result['semantic_measurements_sha256']=_hash(dict(result=result,source_basis=basis,source_quality=dict(full_game_coverage=evidence['source'].get('full_game_coverage'), game_completion=evidence['source'].get('game_completion'), official_reconciliation=sorted([{k:v for k,v in r.items() if k not in {'official_source_id','official_imported_at'}} for r in evidence.get('official_reconciliation',[])],key=lambda r:json.dumps(r,sort_keys=True)))))
    result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],decision_cutoff_at=str(cutoff),
        metric_lineage={m:dict(definition=d,unit=UNITS[m],before_period=before_period,source_snapshot_id=evidence['source']['snapshot_id'],event_receipt_sha256=evidence['sha256']) for m,d in DEFINITIONS.items()},
        producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        numerical_helper_code_sha256=hashlib.sha256(Path(__file__).with_name('defense_context_evidence.py').read_bytes()).hexdigest())
    return result
