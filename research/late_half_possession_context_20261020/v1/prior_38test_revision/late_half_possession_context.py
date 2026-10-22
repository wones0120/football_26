"""Observed original possessions and scoring paths inside the final two minutes."""
from collections import defaultdict
from .drive_scoring_range import _physical_source,_half,_control,LIVE,VERSION as RANGE_VERSION
from .third_down_decision_context import load_reviewed_decision_boundary
from .turnover_drive_start_context import _order
from .original_drive_field_context import _integer
from .fumble_event_components import _flag,_eligibility
from .defense_context_evidence import _number
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='late_half_possession_context_v1'
MATERIAL=('first_down_pass','first_down_rush','first_down_penalty','third_down_failed','third_down_converted','fourth_down_failed','fourth_down_converted','pass_touchdown','rush_touchdown','fumble_lost','punt_blocked','safety','penalty')
SOURCE_FIELDS=set(LIVE)|set(MATERIAL)|{'game_id','play_id','season','week','season_type','posteam','defteam','drive','order_sequence','game_half','qtr','half_seconds_remaining','yardline_100','no_play','play_type','play_type_nfl','field_goal_result','quarter_end','desc'}


def project_late_half_source(row):return {k:row[k]if row[k]!=''else None for k in SOURCE_FIELDS&set(row)}


def _candidate(r):
    named,conflict=_control(r)
    if named:
        return None if conflict or any(_flag(r.get(k))is True for k in MATERIAL)else False
    live=_eligibility(r)[0];physical=_physical_source(r);kind=r.get('play_type')
    kick=False
    if kind in{'field_goal','punt'}:
        flag=_flag(r.get('field_goal_attempt'if kind=='field_goal'else'punt_attempt'))
        kick=False if live is False else True if flag is True and live is True else None
    return True if physical is True or kick is True else False if physical is False and kick is False else None


def _late(r):
    qtr=_integer(r.get('qtr'));half=_half(r);seconds=_number(r.get('half_seconds_remaining'))
    if qtr is not None and qtr not in{2,4}:return False
    if qtr is None or half is None or seconds is None or not 0<=seconds<=900:return None
    return seconds<=120


def _and(a,b):return False if a is False or b is False else True if a is True and b is True else None


def _touchdown(r):
    p,t=_flag(r.get('pass_touchdown')),_flag(r.get('rush_touchdown'));physical=_physical_source(r)
    if p is True and t is True or(p is True or t is True)and _flag(r.get('touchdown'))is False:return None
    if p is True:return True if physical is True and _flag(r.get('pass_attempt'))is True and _flag(r.get('sack'))is False else None
    if t is True:return True if physical is True and _flag(r.get('rush_attempt'))is True else None
    if p is False and t is False or _flag(r.get('touchdown'))is False:return False
    return None if physical is not False else False


def _finish(drives,extra):
    observed=[d for d in drives if d['late_window_entry']is True];unknown=sum(d['late_window_entry']is None for d in drives)+len(extra)
    out=dict(known_observed_late_possessions=len(observed),unknown_possible_late_possessions=unknown,
        exact_late_possession_count=len(observed)if not unknown else None,views={})
    for field in('reached20','reached5','offensive_TD','live_FG_attempt'):
        known=sum(d[field]is True for d in observed);u=sum(d[field]is None for d in observed)
        out['views'][field]=dict(known_successes=known,unknown_outcomes=u,exact_success_count=known if not unknown and not u else None,
            exact_per_possession_fraction=known/len(observed)if observed and not unknown and not u else None,
            known_outcome_sample_fraction=known/(len(observed)-u)if len(observed)>u else None)
    return out


def build_late_half_context(records,boundaries):
    if boundaries.get('version')!=RANGE_VERSION or boundaries.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed nonserving original boundary required')
    before=boundaries['before_period'];timeline=defaultdict(list);index={};bad=set();teams={};parents={}
    for g in boundaries['game_rows']:
        key=(g['native_game_id'],g['team'])
        if key in parents:raise ValueError('Unique source offense game required')
        parents[key]=g
        for d in g['drives']:
            dk=(*key,d['original_drive_id'])
            if dk in teams:raise ValueError('Unique native original drive required')
            teams[dk]=d
    for r in records:
        if r.get('season_type')!='REG':continue
        y,w=_integer(r.get('season')),_integer(r.get('week'));gid=r['game_id'];pid=_integer(r.get('play_id'))
        if y is None or w is None or not 1<=w<=18 or gid.split('_')[:2]!=[str(y),f'{w:02d}']or pid is None:raise ValueError('Native source period/game/play required')
        if y*100+w>=before:continue
        key=(gid,pid)
        if key in index:raise ValueError('Unique native source play required')
        index[key]=r;timeline[gid].append(r)
        if _order(r.get('order_sequence'))is None:bad.add(gid)
    for gid,rs in timeline.items():
        orders=[_order(r.get('order_sequence'))for r in rs]
        if len(set(orders))!=len(orders):bad.add(gid)
        if gid not in bad:rs.sort(key=lambda r:_order(r['order_sequence']))
    unassigned=defaultdict(list);incidents=[]
    for(gid,pid),r in index.items():
        candidate=_and(_candidate(r),_late(r));off=canonical_team(r['posteam'])if r.get('posteam')else None;pair={canonical_team(t)for t in gid.split('_')[2:]}
        if off is not None and off not in pair:raise ValueError('Native source offense outside game')
        if candidate is False:continue
        did=_integer(r.get('drive'))
        if off is None or did is None or(gid,off,did)not in teams:
            incident=dict(game_id=gid,play_id=pid,possible_offense_teams=sorted({off}if off else pair),reason='Unassigned possible late possession native team/drive')
            incidents.append(incident)
            for team in incident['possible_offense_teams']:unassigned[(gid,team)].append(incident)
    output=[];grouped=defaultdict(list)
    for(gid,team),parent in sorted(parents.items()):
        drives=[]
        for d in parent['drives']:
            did=d['original_drive_id'];rs=[r for r in timeline[gid]if _integer(r.get('drive'))==did and r.get('posteam')and canonical_team(r['posteam'])==team]
            candidates=[(r,_and(_candidate(r),_late(r)))for r in rs];known=[r for r,v in candidates if v is True];uncertain=[r for r,v in candidates if v is None]
            entry=min(known,key=lambda r:_order(r['order_sequence']))if known and gid not in bad else None
            first_source=index.get((gid,d['source_first_play_id']));last_source=index.get((gid,d['source_last_play_id']))
            source_pair_proven=bool(d['native_boundary_and_cohort_verified']and first_source and last_source and first_source.get('posteam')and canonical_team(first_source['posteam'])==team and _integer(first_source.get('drive'))==did and _integer(last_source.get('drive'))==did)
            status=True if entry else None if uncertain or gid in bad or not source_pair_proven else False
            earlier_possible=bool(entry and any(_order(r.get('order_sequence'))<=_order(entry['order_sequence'])for r in uncertain))
            row=dict(original_drive_id=did,late_window_entry=status,first_late_play_id=_integer(entry['play_id'])if entry and not earlier_possible else None,first_known_late_play_id=_integer(entry['play_id'])if entry else None,
                first_late_entry_type=entry.get('play_type')if entry else None,source_first_play_id=d['source_first_play_id'],source_last_play_id=d['source_last_play_id'],
                unknown_late_membership_play_ids=[_integer(r['play_id'])for r in uncertain],starts_before_vs_inside_window=None,
                reached20=None,reached5=None,offensive_TD=None,live_FG_attempt=None,complete_postentry_segment=False)
            if entry:
                first=index.get((gid,d['source_first_play_id']));last=index.get((gid,d['source_last_play_id']));start=_order(first.get('order_sequence'))if first else None;end=_order(last.get('order_sequence'))if last else None;eo=_order(entry['order_sequence']);half=_half(entry)
                if first and _candidate(first)is True and _half(first)==half and _late(first)is not None:row['starts_before_vs_inside_window']='inside'if _late(first)else'before'
                segment=[r for r in rs if _order(r.get('order_sequence'))is not None and eo<=_order(r['order_sequence'])<=(end if end is not None else eo)]
                unsafe=bool(uncertain or start is None or end is None or not start<=eo<=end or not d['native_boundary_and_cohort_verified'])
                # Every provider event between entry/end matters, including unassigned control/live rows.
                if end is not None:
                    for r in timeline[gid]:
                        if eo<=_order(r['order_sequence'])<=end:
                            named,conflict=_control(r);material=conflict or named and any(_flag(r.get(k))is True for k in MATERIAL)
                            if material or _half(r)!=half or _integer(r.get('drive'))!=did:unsafe=True
                            if _candidate(r)is not False and (not r.get('posteam')or canonical_team(r['posteam'])!=team):unsafe=True
                terminal=bool(not unsafe and d['verified_terminal_class']is not None and end is not None and end>=eo)
                row['complete_postentry_segment']=terminal
                for field,threshold in(('reached20',20),('reached5',5)):
                    states=[]
                    for r in segment:
                        membership=_and(_candidate(r),_late(r));zone=_number(r.get('yardline_100'));zone=None if zone is None or not 0<=zone<=100 else zone<=threshold
                        states.append(_and(membership,zone))
                    row[field]=True if True in states else False if terminal and all(v is False for v in states)else None
                td=[];fg=[]
                for r in segment:
                    membership=_and(_candidate(r),_late(r));td.append(_and(membership,_touchdown(r)))
                    fg_flag=_flag(r.get('field_goal_attempt'))
                    attempt=None if fg_flag is True and r.get('play_type')!='field_goal'else False if r.get('play_type')!='field_goal'else fg_flag
                    fg.append(_and(membership,attempt))
                row['offensive_TD']=True if True in td else False if terminal and all(v is False for v in td)else None
                row['live_FG_attempt']=True if True in fg else False if terminal and all(v is False for v in fg)else None
            drives.append(row)
        extras=list(unassigned[(gid,team)])
        if not parent['drives']:extras.append(dict(game_id=gid,possible_offense_teams=[team],reason='Missing reviewed original-offense source cohort, not known zero possessions'))
        metrics=_finish(drives,extras)
        output.append(dict(game_id=gid,team=team,season=parent['season'],week=parent['week'],drives=drives,unassigned_possible_entries=extras,metrics=metrics));grouped[(parent['season'],team)].append((drives,extras))
    profiles=[dict(season=y,team=t,metrics=_finish([d for ds,extra in gs for d in ds],[e for ds,extra in gs for e in extra]))for(y,t),gs in sorted(grouped.items())]
    core=dict(version=VERSION,candidate_id='X05-M09',before_period=before,game_rows=output,profiles=profiles,unassigned_native_incidents=incidents,
        definition='Observed ORIGINAL offense possession with physical offense OR live FG/punt preplay at recognized q2/q4 halfclock0..120; native firstentry and postentry scoring-path views')
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,forecast=None,models_or_optimizer_consumed=False,
        limitations=['First source-observed late entry, not possession duration or all-game completeness','Starts-before vs inside is context, not extra possession credit','Known reach/score paths can be observed; negative outcomes need complete native terminal-after-entry proof','Late FG/punt decisions qualify entry even if prior physical offense snap was before120seconds','TD and FG paths separate; no receiver/pass TD duplicate or future probability'])
