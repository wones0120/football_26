"""Additional measured defense variants; no pressure/coverage proxies or forecasts."""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
import hashlib
from pathlib import Path
import re
from uuid import UUID

from Database.player_identity import normalize_position
from .opportunity_events import validate_event_evidence, _flag
from .defense_context_evidence import _eligibility, _number, _metric, _finish, _hash
from .environment_context_evidence import _snap, _and
from .market_snapshots import canonical_team, utc_time

VERSION='defense_context_extensions_v1'
DEFINITIONS={
    'G14-M06':dict(variant='provider_cpoe_nonspike_official_attempt_v1',unit='provider_percentage_points',denominator='known provider CPOE among eligible attempts',lineage='nflfastR vendor-derived completion expectation; model/training chronology unknown'),
    'G14-M08':dict(variant='yac_per_known_completion_v1',unit='yards_per_completion',denominator='known YAC on proven completed nonspike official passes'),
    'G14-M10':dict(variant='pass_td_after_observed_redzone_drive_entry_v1',unit='passing_td_per_observed_entered_drive',denominator='distinct native fixed_drive with proven preplay inside20 offensive snap; known outcome requires observed pass TD or corroborated terminal evidence; partial drive remains unknown'),
    'G15-M08':dict(variant='nonkneel_rush_shortyard_le2_conversion_v1',unit='observed_rate',denominator='official nonkneel rush, preplay ydstogo in [0,2]; scramble included'),
    'G15-M10':dict(variant='position_proven_qb_nonkneel_rush_net_yards_v1',unit='net_yards_per_rush',denominator='native scoped position-proven QB official nonkneel rush'),
    'qb_rush_td_support':dict(variant='position_proven_qb_nonkneel_rush_td_v1',unit='observed_rate',catalog_supports='G15-M10'),
    'scramble_net_yards_support':dict(variant='source_flagged_scramble_only_v1',unit='net_yards_per_flagged_scramble',catalog_supports='G15-M10; narrower variant, not all QB rushing'),
}


def _positions(proofs,cutoff):
    indexed={};semantic=[]
    for proof in proofs:
        if proof.get('source_id') is None or not proof.get('available_at') or utc_time(proof['available_at'])>utc_time(cutoff):
            raise ValueError('Position proof source/availability missing or future')
        gid=str(proof.get('game_id') or '');match=re.fullmatch(r'(\d{4})_(\d{2})_([A-Z]{2,3})_([A-Z]{2,3})',gid)
        native=proof.get('source_player_id');team=canonical_team(str(proof.get('team') or ''))
        if not match or not isinstance(native,str) or not re.fullmatch(r'00-\d{7}',native):raise ValueError('Position proof native scope invalid')
        if team not in {canonical_team(match[3]),canonical_team(match[4])}:raise ValueError('Position proof team conflicts with native game')
        pid=proof.get('player_master_id')
        if pid is not None and str(UUID(str(pid)))!=pid:raise ValueError('Position proof canonical UUID spelling invalid')
        position=normalize_position(proof.get('position'))
        if position not in {'QB','RB','WR','TE','OL','C','G','T','OT','OG'}:raise ValueError('Position proof position unavailable')
        fact=dict(game_id=gid,source_player_id=native,team=team,position=position,player_master_id=pid)
        key=(gid,native,team)
        if key in indexed and indexed[key]!=fact:raise ValueError('Contradictory native position/canonical proofs')
        indexed[key]=fact
    semantic=sorted(indexed.values(),key=lambda r:(r['game_id'],r['source_player_id'],r['team']))
    return indexed,semantic



def _no_pass_terminal(event):
    """Require explicit provider drive result/transition plus matching event fact."""
    if event['status']=='excluded':return None
    raw=event['raw_flags'];kind=raw.get('play_type')
    result=raw.get('fixed_drive_result');transition=raw.get('drive_end_transition')
    if kind=='field_goal' and _flag(raw.get('field_goal_attempt')) is True:
        if (result,transition,raw.get('field_goal_result'))==('Field goal','FIELD_GOAL','made'):return 'provider_field_goal_terminal'
        if (result,transition,raw.get('field_goal_result'))==('Missed field goal','MISSED_FG','missed'):return 'provider_missed_field_goal_terminal'
    if kind=='punt' and _flag(raw.get('punt_attempt')) is True and _flag(raw.get('punt_blocked')) is False and (result,transition)==('Punt','PUNT'):
        return 'provider_punt_terminal'
    if result in {'Turnover','Opp touchdown'} and transition=='INTERCEPTION' and _flag(raw.get('interception')) is True and _flag(raw.get('pass_attempt')) is True:
        return 'provider_interception_terminal'
    if result in {'Turnover','Opp touchdown'} and transition=='FUMBLE' and _flag(raw.get('fumble_lost')) is True:
        return 'provider_fumble_lost_terminal'
    if (result,transition)==('Turnover on downs','DOWNS') and _flag(raw.get('fourth_down_failed')) is True:
        return 'provider_turnover_on_downs_terminal'
    return None

def build_defense_context_extensions(event_receipt, *, before_period, cutoff, position_evidence=(),last_n_games=8):
    """Measure from a parent verified by intake; checksum alone is not provenance."""
    if isinstance(last_n_games,bool) or not isinstance(last_n_games,int) or not 1<=last_n_games<=32:raise ValueError('Observed-game window invalid')
    evidence=validate_event_evidence(event_receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
    position_evidence=deepcopy(list(position_evidence));positions,position_facts=_positions(position_evidence,cutoff)
    for proof in position_facts:
        year,week=map(int,proof['game_id'].split('_')[:2])
        if not 1<=week<=18 or year*100+week>=before_period:raise ValueError('Position proof must be prior REG game')
    games={};drives={};basis=[];used_proofs=set();identity_requests={}
    for event in sorted(evidence['events'],key=lambda e:(e['game_id'],int(e['play_id']))):
        raw=event['raw_flags'];gid=event['game_id'];offense=event['team'];parts=gid.split('_')
        pair={canonical_team(t) for t in parts[2:]}
        if len(pair)!=2 or offense not in pair:raise ValueError('Defense native game/team scope invalid')
        defense=next(iter(pair-{offense}))
        if raw.get('defteam') is not None and raw['defteam']!=defense:raise ValueError('Defense source team contradicts native game')
        key=(gid,defense);game=games.setdefault(key,dict(game_id=gid,defense_team=defense,offense_team=offense,
            season=event['season'],week=event['week'],metrics={m:_metric() for m in DEFINITIONS},
            drive_quality=dict(observed_redzone_drive_ids=[],uncertain_redzone_drive_ids=[],redzone_events_missing_drive_id=0,conflicting_td_drive_ids=[],drive_outcomes=[])))
        passing,_,rushing=_eligibility(event);completion=_flag(raw.get('complete_pass'))
        completed=_and(passing,completion)
        ydstogo=_number(raw.get('ydstogo'));short=False if rushing is False or (ydstogo is not None and ydstogo>2) else None if rushing is None or ydstogo is None or ydstogo<0 else True
        first=_flag(raw.get('first_down_rush'));td=_flag(raw.get('rush_touchdown'))
        conversion=True if first is True or td is True else False if first is False and td is False else None
        native=raw.get('rusher_player_id');proof=positions.get((gid,native,offense));position_qb=None if proof is None else proof['position']=='QB'
        if proof is not None and rushing is not False:
            used_proofs.add((gid,native,offense))
            mapped={o['player_master_id'] for o in event['opportunities'] if o['channel']=='rush_attempts' and o['player_master_id'] is not None}
            if proof['player_master_id'] is not None and mapped and mapped!={proof['player_master_id']}:raise ValueError('Position proof canonical UUID contradicts native event alias')
            if proof['player_master_id'] is None and not mapped:
                identity_requests[(gid,native,offense)]=dict(game_id=gid,source_player_id=native,team=offense,reason='Position known by native key; canonical attachment unresolved, persist through existing identity queue')
        qb_rush=_and(rushing,position_qb);scramble=_and(rushing,_flag(raw.get('qb_scramble')))
        cpoe=_number(raw.get('cpoe'))
        if cpoe is not None and not -100<=cpoe<=100:raise ValueError('Provider CPOE outside physical percentage-point range')
        outcomes={'G14-M06':(passing,cpoe),'G14-M08':(completed,_number(raw.get('yards_after_catch'))),
            'G15-M08':(short,None if conversion is None else float(conversion)),
            'G15-M10':(qb_rush,_number(raw.get('yards_gained'))),
            'qb_rush_td_support':(qb_rush,None if td is None else float(td)),
            'scramble_net_yards_support':(scramble,_number(raw.get('yards_gained')))}
        for metric,(eligible,value) in outcomes.items():
            target=game['metrics'][metric]
            if eligible is None:target['unknown_eligibility_events']+=1
            elif eligible:
                target['eligible_events']+=1
                if value is None:target['unknown_outcome_events']+=1
                else:target['known_outcome_events']+=1;target['observed_outcome_sum']+=value
        yard=_number(raw.get('yardline_100'));zone=None if yard is None or not 0<=yard<=100 else yard<=20
        entry=_and(_snap(event),zone);drive=_number(raw.get('fixed_drive'))
        drive=str(int(drive)) if drive is not None and drive>=0 and drive.is_integer() else None
        if drive is None:
            if entry is not False:game['drive_quality']['redzone_events_missing_drive_id']+=1
        else:
            item=drives.setdefault((gid,defense,drive),dict(game_key=key,drive_id=drive,entries=[],uncertain_entry=False,events=[]))
            if entry is True:item['entries'].append(int(event['play_id']))
            elif entry is None:item['uncertain_entry']=True
            item['events'].append(dict(play_id=int(event['play_id']),passing=passing,td=_flag(raw.get('pass_touchdown')),rushing=rushing,rush_td=td,no_pass_terminal=_no_pass_terminal(event)))
        basis.append(dict(game_id=gid,play_id=event['play_id'],defense=defense,outcomes=outcomes,drive=drive,entry=entry,pass_td=_flag(raw.get('pass_touchdown'))))
    for (_,_,_),drive in sorted(drives.items()):
        game=games[drive['game_key']];metric=game['metrics']['G14-M10'];quality=game['drive_quality'];did=drive['drive_id']
        if not drive['entries']:
            if drive['uncertain_entry']:quality['uncertain_redzone_drive_ids'].append(did);metric['unknown_eligibility_events']+=1
            continue
        entry=min(drive['entries']);quality['observed_redzone_drive_ids'].append(did);metric['eligible_events']+=1
        touchdowns=[e for e in drive['events'] if e['passing'] is True and e['td'] is True]
        rushing_touchdowns=[e for e in drive['events'] if e['rushing'] is True and e['rush_td'] is True]
        other_terminal=[e for e in drive['events'] if e['no_pass_terminal']]
        terminal=touchdowns+rushing_touchdowns+other_terminal
        conflict=len({e['play_id'] for e in terminal})>1 or any(e['play_id']<entry for e in terminal) or bool(touchdowns and (rushing_touchdowns or other_terminal))
        completion_basis='conflicting_touchdown_evidence' if conflict else 'observed_passing_touchdown' if touchdowns else 'observed_rushing_touchdown' if rushing_touchdowns else other_terminal[0]['no_pass_terminal'] if other_terminal else 'unknown_no_terminal_evidence'
        quality['drive_outcomes'].append(dict(drive_id=did,completion_basis=completion_basis,
            terminal_play_ids=sorted(e['play_id'] for e in terminal),outcome_known=not conflict and bool(terminal)))
        if conflict:quality['conflicting_td_drive_ids'].append(did)
        if conflict or not terminal:metric['unknown_outcome_events']+=1
        else:metric['known_outcome_events']+=1;metric['observed_outcome_sum']+=float(bool(touchdowns))
    grouped=defaultdict(list)
    for game in games.values():grouped[game['defense_team']].append(game)
    windows=[]
    for team,rows in sorted(grouped.items()):
        rows.sort(key=lambda r:(r['season'],r['week']))
        if len({(r['season'],r['week']) for r in rows})!=len(rows):raise ValueError('Ambiguous defense period chronology')
        selected=rows[-last_n_games:];totals={m:_metric() for m in DEFINITIONS}
        for row in selected:
            for m,value in row['metrics'].items():
                for k,n in value.items():totals[m][k]+=n
        windows.append(dict(defense_team=team,observed_game_ids=[r['game_id'] for r in selected],metrics={m:_finish(v) for m,v in totals.items()}))
    result=dict(version=VERSION,before_period=before_period,last_n_observed_games=last_n_games,status='observed_descriptive_extensions',
        definitions=deepcopy(DEFINITIONS),identity_review_requests=[v for _,v in sorted(identity_requests.items())],game_rows=[dict(row,metrics={m:_finish(v) for m,v in row['metrics'].items()}) for _,row in sorted(games.items())],team_windows=windows,
        limitations=['Verified parent/source intake required; pure checksum does not authenticate source','Revised source; original pregame availability/full-game coverage unknown',
            'No-TD partial drive outcome unknown without sourced terminal evidence; observed entry is not complete trip coverage',
            'QB complete rushing needs scoped native position proof; scramble-only support is narrower','Pressure/blitz/man-zone/contact unavailable; no proxy substitution'],forecast=None)
    result['semantic_measurements_sha256']=_hash(dict(result=result,source_basis=basis,position_facts=[positions[k] for k in sorted(used_proofs)],
        source_quality={k:evidence['source'].get(k) for k in ('game_completion','full_game_coverage')}))
    result['provenance']=dict(source=deepcopy(evidence['source']),event_receipt_sha256=evidence['sha256'],position_evidence=position_evidence,
        decision_cutoff_at=str(cutoff),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result
