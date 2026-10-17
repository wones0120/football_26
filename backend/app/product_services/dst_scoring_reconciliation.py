"""Versioned research DST scoring from complete NFL/nflverse event evidence.

No DB writes, live activation or aggregate seven-point TD subtraction. Missing
coverage is an error; a verified zero is a computed result. NFL play order uses
order_sequence because replay adjustments can make play_id nonchronological.
"""
import hashlib
import json
import math
from collections import defaultdict
from uuid import UUID

from Database.dst import normalize_team, dk_points_allowed_score

CONTRACT = 'draftkings_classic_dst_event_scoring_v1'
REQUIRED = {'game_id','play_id','order_sequence','home_team','away_team','home_score','away_score',
    'total_home_score','total_away_score','posteam','defteam','td_team','desc','play_type','play_deleted',
    'sack','interception','safety','touchdown','pass_touchdown','rush_touchdown','punt_attempt','kickoff_attempt','field_goal_attempt',
    'extra_point_attempt','two_point_attempt','punt_blocked','field_goal_result','extra_point_result',
    'defensive_two_point_conv','defensive_extra_point_conv','fumbled_1_team','fumbled_2_team',
    'fumble_recovery_1_team','fumble_recovery_2_team'}


class DstScoringUnresolved(ValueError):
    pass


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def team(value):
    return normalize_team(str(value)) if value is not None and str(value).lower() not in {'nan','none',''} else None


def score_game(rows, *, expected_game_id, expected_teams, canonical_player_ids, expected_score=None):
    """Score one complete final game, retaining every scoring event/play ID.

    PA includes offensive/ST TDs, all made XP/conversions/FGs and conversion
    returns; excludes TDs made by the opponent defense against the offense and
    safeties. XP after a defensive TD still counts against the returning team's
    opponent DST; subtracting seven per defensive TD is incorrect.
    """
    if not rows:
        raise DstScoringUnresolved('Missing complete game play-by-play')
    if REQUIRED - set(rows[0]):
        raise DstScoringUnresolved('Missing scoring fields: '+','.join(sorted(REQUIRED-set(rows[0]))))
    keys=[r['play_id'] for r in rows]
    if len(keys)!=len(set(keys)):
        raise DstScoringUnresolved('Duplicate play IDs; no implicit double-counting')
    if any(r['game_id']!=expected_game_id for r in rows):
        raise DstScoringUnresolved('Canonical game mismatch')
    homes={team(r['home_team']) for r in rows};aways={team(r['away_team']) for r in rows}
    if len(homes)!=1 or len(aways)!=1 or homes & aways or homes|aways != {team(t) for t in expected_teams}:
        raise DstScoringUnresolved('Canonical team/game membership mismatch')
    home,away=next(iter(homes)),next(iter(aways));teams={home,away}
    if not teams <= set(canonical_player_ids):raise DstScoringUnresolved('Missing canonical DST identity map')
    for t in teams:UUID(str(canonical_player_ids[t]))
    if any(number(r.get('order_sequence')) is None for r in rows):
        raise DstScoringUnresolved('Missing source play order')
    plays=sorted(rows,key=lambda r:float(r['order_sequence']))
    if not any('END GAME' in str(r.get('desc') or '').upper() for r in plays):
        raise DstScoringUnresolved('Missing final END GAME evidence')
    finals={(number(r['home_score']),number(r['away_score'])) for r in rows}
    if len(finals)!=1 or None in next(iter(finals)):
        raise DstScoringUnresolved('Missing/conflicting final score')
    final_home,final_away=next(iter(finals))
    if expected_score is not None and (final_home,final_away)!=(float(expected_score[home]),float(expected_score[away])):
        raise DstScoringUnresolved('Independent final score mismatch')
    totals={t:defaultdict(float) for t in teams};events=[];last={home:0.,away:0.}
    def add(t,key,value,row):
        if t not in teams:raise DstScoringUnresolved('Scoring event lacks canonical credited team')
        totals[t][key]+=value;events.append(dict(play_id=row['play_id'],team=t,component=key,value=value,description=row.get('desc')))
    for r in plays:
        if number(r['play_deleted'])==1:continue
        offense,defense=team(r['posteam']),team(r['defteam'])
        flag=lambda k:number(r.get(k))==1
        conversion=flag('extra_point_attempt') or flag('two_point_attempt')
        st=any(flag(k) for k in ['punt_attempt','kickoff_attempt','field_goal_attempt','extra_point_attempt'])
        # Explicitly nullified plays may retain an action play_type with all
        # counters null. This is distinct from an unobserved valid play.
        nullified=all(number(r.get(k)) is None for k in ['sack','interception','safety','touchdown']) and ('NO PLAY' in str(r.get('desc','')).upper() or 'NULLIFIED' in str(r.get('desc','')).upper())
        if nullified:
            if {home:number(r['total_home_score']),away:number(r['total_away_score'])}!=last:raise DstScoringUnresolved('Nullified play changes score')
            events.append(dict(play_id=r['play_id'],team=None,component='nullified_play',value=0,description=r.get('desc')))
            continue
        # Non-play administration may have null flags. Statistical plays may not.
        if r.get('play_type') in {'pass','run','punt','kickoff','field_goal','extra_point'} and any(number(r.get(k)) is None for k in ['sack','interception','safety','touchdown']):
            raise DstScoringUnresolved('Missing event counters on a statistical play')
        if not conversion:
            if flag('sack'):add(defense,'sacks',1,r)
            if flag('interception'):add(defense,'interceptions',1,r)
            if flag('safety'):add(defense,'safeties',1,r)
            for i in (1,2):
                recovered=team(r.get(f'fumble_recovery_{i}_team'));fumbled=team(r.get(f'fumbled_{i}_team'))
                if recovered and not fumbled and i==2:
                    # The first recovery establishes possession before the
                    # second fumble; no display-name/player guess is used.
                    fumbled=team(r.get('fumble_recovery_1_team'))
                if recovered and not fumbled:raise DstScoringUnresolved('Recovery without fumbling-team evidence')
                if recovered and recovered!=fumbled:add(recovered,'fumble_recoveries',1,r)
            if flag('touchdown'):
                credited=team(r.get('td_team'))
                if st:add(credited,'special_teams_touchdowns',1,r)
                elif credited==defense:add(credited,'defensive_touchdowns',1,r)
                elif credited==offense and not flag('pass_touchdown') and not flag('rush_touchdown'):add(credited,'offensive_fumble_touchdowns',1,r)
        if flag('punt_blocked') or r.get('field_goal_result')=='blocked' or r.get('extra_point_result')=='blocked':
            add(defense,'blocked_kicks',1,r)
        if flag('defensive_two_point_conv') or flag('defensive_extra_point_conv'):
            add(defense,'conversion_returns',1,r)
        current={home:number(r['total_home_score']),away:number(r['total_away_score'])}
        if any(v is None for v in current.values()):raise DstScoringUnresolved('Missing score timeline')
        changes={t:current[t]-last[t] for t in teams}
        if any(v<0 for v in changes.values()) or sum(v>0 for v in changes.values())>1:
            raise DstScoringUnresolved('Nonmonotone/conflicting scoring timeline')
        for scored,delta in changes.items():
            if not delta:continue
            defensive_td=flag('touchdown') and not st and team(r.get('td_team'))==defense
            excluded=defensive_td or flag('safety')
            valid_score=(flag('touchdown') and delta==6 or flag('safety') and delta==2 or
                r.get('field_goal_result')=='made' and delta==3 or r.get('extra_point_result')=='good' and delta==1 or
                conversion and delta==2)
            if not valid_score:raise DstScoringUnresolved(f'Unclassified score event {expected_game_id}:{r["play_id"]}')
            if not excluded:add(next(iter(teams-{scored})),'points_allowed',delta,r)
            else:events.append(dict(play_id=r['play_id'],team=next(iter(teams-{scored})),component='excluded_points_allowed',value=delta,description=r.get('desc')))
        last=current
    if last!={home:final_home,away:final_away}:
        raise DstScoringUnresolved('Incomplete score timeline versus final score')
    result=[]
    for t in sorted(teams):
        c={k:float(totals[t][k]) for k in ['sacks','interceptions','fumble_recoveries','safeties','defensive_touchdowns','special_teams_touchdowns','blocked_kicks','conversion_returns','points_allowed','offensive_fumble_touchdowns']}
        points=(c['sacks']+2*c['interceptions']+2*c['fumble_recoveries']+2*c['safeties']+
            6*c['defensive_touchdowns']+6*c['special_teams_touchdowns']+2*c['blocked_kicks']+2*c['conversion_returns']+dk_points_allowed_score(c['points_allowed']))
        result.append(dict(contract_id=CONTRACT,game_id=expected_game_id,team=t,opponent=next(iter(teams-{t})),
            player_master_id=str(canonical_player_ids[t]),dk_points=points,components=c,
            final_score={home:final_home,away:final_away},points_allowed_score=dk_points_allowed_score(c['points_allowed']),coverage='complete_final_event_scoring',events=[e for e in events if e['team']==t]))
    return result


def apply_research_corrections(matrix_rows, corrected_rows):
    """Return a separate exact-identity dataset; never mutate original rows.

    Correction lookup requires canonical team + season/week and canonical DST
    UUID. Original rows and unresolved mappings remain explicit in the receipt.
    """
    lookup={};duplicates=set()
    for row in corrected_rows:
        key=(int(row['season']),int(row['week']),team(row['team']))
        if key in lookup:duplicates.add(key)
        lookup[key]=row
    if duplicates:raise DstScoringUnresolved('Ambiguous corrected team/period')
    out=[];receipts=[]
    for source in matrix_rows:
        row=dict(source);key=(int(row['season']),int(row['week']),team(row['team']));corrected=lookup.get(key)
        identity_ok=corrected and str(row.get('player_master_id'))==corrected['player_master_id'] and team(row['opponent'])==corrected['opponent']
        if not identity_ok:
            receipts.append(dict(matrix_row_id=row['player_game_feature_matrix_id'],status='unresolved_identity_or_source',old_points=row['dk_points'],key=key));continue
        if row.get('game_id') and row['game_id']!=corrected['game_id']:
            receipts.append(dict(matrix_row_id=row['player_game_feature_matrix_id'],status='conflicting_game_id',key=key));continue
        old=row['dk_points'];row.update(dk_points=corrected['dk_points'],game_id=corrected['game_id'],dst_scoring_contract=CONTRACT,dst_source_sha256=corrected['source_sha256'])
        receipts.append(dict(matrix_row_id=row['player_game_feature_matrix_id'],status='corrected' if old!=row['dk_points'] else 'verified_unchanged',old_points=old,new_points=row['dk_points'],game_id=row['game_id'],team=row['team'],player_master_id=row['player_master_id'],source_sha256=corrected['source_sha256']))
        out.append(row)
    payload=dict(contract_id=CONTRACT,classification='CORRECTED_RESEARCH_DATASET_NOT_LIVE',rows=out,receipts=receipts)
    payload['sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
    return payload


def require_completed_schedule_scores(schedule_rows, *, now):
    """Never turn missing final schedule evidence into a completed DST zero.

    A conservative 24-hour boundary after scheduled kickoff distinguishes future
    feature placeholders from historical labels. A postponed/uncertain game
    without a final score blocks, rather than being declared played. Duplicate
    source versions may supply the same final score; conflicting finals block.
    """
    from datetime import datetime, UTC, timedelta
    from zoneinfo import ZoneInfo
    games={}
    for row in schedule_rows:
        raw=row.get('raw_row_json') or {};gid=row.get('game_id') or raw.get('game_id')
        date=raw.get('gameday');clock=raw.get('gametime') or '23:59'
        if not gid or not date:continue
        kickoff=datetime.fromisoformat(str(date)+'T'+str(clock)).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(UTC)
        record=games.setdefault(gid,dict(kickoff=kickoff,finals=set()))
        h,a=number(raw.get('home_score')),number(raw.get('away_score'))
        if h is not None and a is not None:record['finals'].add((h,a))
    unresolved=[gid for gid,r in games.items() if r['kickoff']+timedelta(hours=24)<now and len(r['finals'])!=1]
    if unresolved:raise DstScoringUnresolved('Completed-date DST outcomes need final score evidence; refusing zero labels: '+', '.join(sorted(unresolved)))
    return dict(completed_games=sum(r['kickoff']+timedelta(hours=24)<now for r in games.values()),future_games=sum(r['kickoff']+timedelta(hours=24)>=now for r in games.values()))
