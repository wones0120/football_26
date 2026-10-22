"""Nominal terminal-decision field sites on original offensive drives."""
from collections import defaultdict
from copy import deepcopy
from .original_drive_field_context import _field,_integer,_one,VERSION as ORIGINAL_VERSION
from .turnover_drive_start_context import _physical,_quiet,_order
from .fumble_event_components import _flag
from .defense_context_evidence import _number
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='original_drive_nominal_scoring_range_v1'
LIVE=('pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','qb_spike','qb_kneel','interception','fumble',
 'kickoff_attempt','punt_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt','touchdown','return_touchdown')
ELIGIBLE_TYPES={'FIELD_GOAL','MISSED_FG','BLOCKED_FG','BLOCKED_FG,_DOWNS','PUNT','BLOCKED_PUNT,_DOWNS','DOWNS'}


def _control(raw):
    named=raw.get('play_type_nfl') in {'TIMEOUT','END_QUARTER','END_GAME'} or raw.get('play_type') in {'time_out','quarter_end'}
    conflict=named and any(_flag(raw.get(k)) is True for k in LIVE)
    return named,conflict


def _physical_source(raw):
    named,conflict=_control(raw)
    return None if conflict else False if named else _physical(raw)


def build_drive_scoring_range(records,original,scoring,fumbles,completed,*,range_yards=35):
    if type(range_yards) is not int or not 0<range_yards<=50:raise ValueError('Declared nominal opponent-yard range required')
    if original.get('version')!=ORIGINAL_VERSION or original.get('pregame_serving_eligible') is not False:raise ValueError('Reviewed original drive source required')
    from .explosive_touchdown_features import VERSION as SCORING_VERSION
    from .fumble_event_components import VERSION as FUMBLE_VERSION
    from .scoreboard_result_features import VERSION as SCORE_VERSION
    for x,version in ((scoring,SCORING_VERSION),(fumbles,FUMBLE_VERSION),(completed,SCORE_VERSION)):
        if x.get('version')!=version or x.get('before_period')!=original['before_period'] or x.get('pregame_serving_eligible') is not False:raise ValueError('Matched nonserving source component versions/period required')
    if scoring['source_event_sha256']!=original['source_event_sha256']:raise ValueError('Same native offensive event receipt required')
    before=original['before_period'];idx={};groups=defaultdict(list);orders=defaultdict(list);bad_order=set()
    for raw in records:
        if raw.get('season_type')!='REG':continue
        season,week=_integer(raw.get('season')),_integer(raw.get('week'))
        if season is None or week is None or not 1<=week<=18:raise ValueError('Native raw REG period required')
        if season*100+week>=before:continue
        gid=raw['game_id'];parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(season),f'{week:02}']:raise ValueError('Native raw game/period differs')
        pid=_integer(raw.get('play_id'));key=(gid,pid)
        if pid is None or key in idx:raise ValueError('Unique native play identity required')
        idx[key]=raw;order=_order(raw.get('order_sequence'));orders[gid].append(order)
        if order is None:bad_order.add(gid)
        did=_integer(raw.get('drive'))
        if did is not None:groups[(gid,did)].append(raw)
    for gid,values in orders.items():
        if len(set(values))!=len(values):bad_order.add(gid)
    tds={};passes=set()
    for g in scoring['game_rows']:
        for e in g['events']:
            key=(g['game_id'],_integer(e['play_id']))
            if key in tds:raise ValueError('Duplicate scored physical event')
            tds[key]=any(c['official_eligibility'] is True and c['touchdown'] is True for c in e['channels'])
            if any(c['channel']=='pass' and c['official_eligibility'] is True for c in e['channels']):passes.add(key)
    losses={}
    for e in fumbles['fumble_ledger']:
        key=(e['game_id'],_integer(e['play_id']))
        if key in losses:raise ValueError('Unique typed fumble event required')
        losses[key]=e
    finals={g['game_id'] for g in completed['game_rows'] if g['exact_completed_score'] is not None}
    known_drives={(g['game_id'],g['team']):{d['original_drive_id'] for d in g['drives']} for g in original['game_rows']}
    extra_raw=defaultdict(list)
    for (gid,pid),r in idx.items():
        if _physical_source(r) is False:continue
        pair={canonical_team(x) for x in gid.split('_')[2:]}
        team=canonical_team(r['posteam']) if r.get('posteam') else None
        if team is not None and team not in pair:raise ValueError('Raw original offense outside native game')
        did=_integer(r.get('drive'));possible={team} if team is not None else {t for t in pair if did in known_drives.get((gid,t),set())} or pair
        for t in possible:
            if did is None or did not in known_drives.get((gid,t),set()):extra_raw[(gid,t)].append(pid)
    output=[]
    for g in original['game_rows']:
        gid,team=g['game_id'],g['team'];pair={canonical_team(x) for x in gid.split('_')[2:]}
        if team not in pair:raise ValueError('Native original offense required')
        drives=[]
        for d in g['drives']:
            raw=groups[(gid,d['original_drive_id'])];first=idx.get((gid,d['source_first_play_id']));last=idx.get((gid,d['source_last_play_id']))
            endpoints,end_values=_one(raw,'drive_end_yard_line');transition,types=_one(raw,'drive_end_transition')
            if types!=d['raw_end_transitions']:raise ValueError('Frozen original terminal metadata differs')
            site=_field(endpoints,team,pair) if len(end_values)==1 else None
            physical=[r for r in raw if _physical_source(r) is True]
            uncertain=sum(_physical_source(r) is None for r in raw)
            source_half=first.get('game_half') if first else None
            same_half=bool(source_half and last and last.get('game_half')==source_half)
            first_order=_order(first.get('order_sequence')) if first else None;last_order=_order(last.get('order_sequence')) if last else None
            own_first=bool(first and canonical_team(first['posteam'])==team and _integer(first.get('drive'))==d['original_drive_id']) if first and first.get('posteam') else False
            own_last=bool(last and last.get('posteam') and canonical_team(last['posteam'])==team)
            boundary=bool(gid not in bad_order and own_first and last and same_half and first_order is not None and last_order is not None
                and first_order<=last_order and _integer(last.get('drive'))==d['original_drive_id'] and physical and not uncertain
                and all(first_order<=_order(r['order_sequence'])<=last_order and r.get('posteam') and canonical_team(r['posteam'])==team for r in physical))
            decision_site=None;known_class=None;in_range=None;reason='Unknown native boundary/half/physical cohort'
            terminal_key=(gid,d['source_last_play_id'])
            if boundary and len(types)==1:
                if transition in ELIGIBLE_TYPES and own_last:
                    fg=transition in {'FIELD_GOAL','MISSED_FG','BLOCKED_FG','BLOCKED_FG,_DOWNS'}
                    punt=transition in {'PUNT','BLOCKED_PUNT,_DOWNS'}
                    proof=False
                    if fg:
                        expected='made' if transition=='FIELD_GOAL' else 'missed' if transition=='MISSED_FG' else 'blocked'
                        proof=last.get('play_type')=='field_goal' and _flag(last.get('field_goal_attempt')) is True and last.get('field_goal_result')==expected
                    elif punt:proof=last.get('play_type')=='punt' and _flag(last.get('punt_attempt')) is True and _flag(last.get('punt_blocked')) is (transition=='BLOCKED_PUNT,_DOWNS')
                    else:proof=_physical_source(last) is True and _flag(last.get('fourth_down_failed')) is True and _integer(last.get('down'))==4
                    los=_number(last.get('yardline_100'))
                    if proof:
                        known_class=transition
                        if site is not None and los is not None and 0<=los<=100 and site==los:
                            decision_site=los;in_range=los<=range_yards;reason='Corroborated original-offense terminal predecision site'
                        else:reason='Source end field unknown or differs from original-offense terminal LOS'
                    else:reason='Source terminal label not independently corroborated'
                elif transition=='TOUCHDOWN':
                    td=any(tds.get((gid,_integer(r['play_id']))) is True for r in raw if r.get('posteam') and canonical_team(r['posteam'])==team
                        and first_order<=_order(r['order_sequence'])<=last_order)
                    if td:known_class=transition;in_range=False;reason='Known physical offensive TD excluded, source-last try not a kick site'
                    else:reason='No matched physical offensive TD proof within original drive'
                elif transition=='INTERCEPTION' and own_last:
                    if terminal_key in passes and _flag(last.get('interception')) is True:known_class=transition;in_range=False;reason='Typed original official-pass interception excluded'
                elif transition=='FUMBLE' and own_last:
                    f=losses.get(terminal_key)
                    if (f and f['eligible'] is True and f['fumble_play'] is True and f['lost_from_fumbler_team'] is True
                            and len(f['reported_fumblers'])==1 and f['reported_fumblers'][0]['team']==team):
                        known_class=transition;in_range=False;reason='Typed original-offense lost fumble excluded'
                elif transition in {'END_HALF','END_GAME'}:
                    named,conflict=_control(last);qtr=_integer(last.get('qtr'));half_clock=_number(last.get('half_seconds_remaining'));game_clock=_number(last.get('game_seconds_remaining'))
                    end_half=transition=='END_HALF' and last.get('play_type_nfl')=='END_QUARTER' and qtr==2 and half_clock==0
                    end_game=transition=='END_GAME' and last.get('play_type_nfl')=='END_GAME' and qtr is not None and qtr>=4 and game_clock==0 and gid in finals
                    if named and not conflict and (end_half or end_game):known_class=transition;in_range=False;reason='Known clock/source half boundary (and independent final-game proof when needed) excluded'
            drives.append(dict(original_drive_id=d['original_drive_id'],raw_end_fields=end_values,source_reported_end_yardline100=site,
                raw_end_transitions=types,source_first_play_id=d['source_first_play_id'],source_last_play_id=d['source_last_play_id'],
                last_physical_snap_play_id=_integer(max(physical,key=lambda r:_order(r['order_sequence']))['play_id']) if physical and gid not in bad_order else None,
                known_half_binding=same_half,native_boundary_and_cohort_verified=boundary,unknown_physical_source_rows=uncertain,
                verified_terminal_class=known_class,terminal_predecision_site_yardline100=decision_site,
                nominal_range_terminal_decision=in_range,classification_basis=reason))
        unknown=sum(d['nominal_range_terminal_decision'] is None for d in drives);extra=g['unknown_original_drive_events']
        known_count=sum(d['nominal_range_terminal_decision'] is True for d in drives)
        output.append(dict(native_game_id=gid,team=team,season=g['season'],week=g['week'],drives=drives,
            metrics=dict(observed_original_drives=len(drives),unknown_original_drive_events=extra,unknown_drive_decisions=unknown,unassigned_source_physical_candidate_rows=extra_raw[(gid,team)],
                known_in_range_terminal_decisions_lower_bound=known_count,exact_observed_game_count=known_count if drives and not unknown and not extra and not extra_raw[(gid,team)] else None),
            terminal_class_counts={t:sum(d['verified_terminal_class']==t for d in drives) for t in sorted({d['verified_terminal_class'] for d in drives if d['verified_terminal_class']})}))
    core=dict(version=VERSION,candidate_id='G23-M05',before_period=before,nominal_range_yards=range_yards,game_rows=output,
        definition='Original physical-offense drives ending at nominal in-range FG/punt/4th-failure terminal predecision sites; typed TD/giveaway/clock-ended classes excluded')
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',forecast=None,model_or_optimizer_consumed=False,
        limitations=['Nominal field-position context, not actual actionable FG opportunity, expected attempts, kicker ability or guaranteed52yard distance',
            'Source end field, source last play and last physical LOS remain distinct; no return landing/try position donated',
            'Unknown/censored/cohort/half/terminal evidence masks exact count; known sample remains separate',
            'Original source completeness/publication unknown; no model/optimizer/serving claim'])


def load_reviewed_range_component(ref,folder,*,cutoff):
    from pathlib import Path
    import json,hashlib,importlib
    from datetime import datetime,UTC
    from .factual_designation import clock
    supported={'original_drive_field_context':'producer_sha256','explosive_touchdown_features':'producer_sha256',
        'fumble_event_components':'producer_code_sha256','scoreboard_result_features':'producer_code_sha256'}
    if folder not in supported:raise ValueError('Declared reviewed component required')
    p=Path(ref['path']).resolve();actual=clock(cutoff)
    if p.parent!=Path('artifacts',folder).resolve() or p.name!=ref['sha256']+'.json' or not 0<ref['bytes']<=16*1024*1024:raise ValueError('Managed bounded source component required')
    raw=p.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Immutable component bytes differ')
    x=json.loads(raw);provenance=x['provenance'];module=importlib.import_module('backend.app.product_services.'+folder)
    if (x.get('pregame_serving_eligible') is not False or x.get('forecast') is not None or x.get('version')!=module.VERSION
            or provenance.get(supported[folder])!=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()):raise ValueError('Reviewed source producer/version/use differs')
    t=clock(provenance.get('actual_publication_at'))
    if actual is None or actual>datetime.now(UTC) or t is None or t>actual:raise ValueError('Published source component unavailable at actual cutoff')
    if folder in {'original_drive_field_context','explosive_touchdown_features'}:
        keys=('version','before_period','game_rows','source_event_sha256','definitions') if folder=='original_drive_field_context' else ('version','candidate_id','before_period','thresholds','game_rows','source_event_sha256')
        if x['semantic_sha256']!=digest({k:x[k] for k in keys}):raise ValueError('Source semantic core differs')
    elif folder=='fumble_event_components':
        if x['semantic_sha256']!=digest({k:x[k] for k in ('version','before_period','game_rows','team_recovery_rows','fumble_ledger','event_basis','definitions')}):raise ValueError('Typed fumble semantic core differs')
    else:
        from .scoreboard_result_features import build_opponent_team_point_distributions
        replay=build_opponent_team_point_distributions([o for g in x['game_rows'] for o in g['source_observations']],{g['game_id']:g['corroboration'] for g in x['game_rows']},before_period=x['before_period'])
        if replay['semantic_sha256']!=x['semantic_sha256']:raise ValueError('Completed-score semantic core differs')
    return x
