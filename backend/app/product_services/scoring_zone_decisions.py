"""Observed inside-five and goal-to-go called-pass/rush decisions by preplay state."""
from collections import defaultdict
from copy import deepcopy
from .opportunity_events import validate_event_evidence,_flag
from .environment_context_evidence import _call
from .defense_context_evidence import _number
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='observed_scoring_zone_decisions_v1'


def _state(raw,mid):
    down=_number(raw.get('down'));down=int(down) if down in {1,2,3,4} else None
    if mid=='X05-M04':
        yard=_number(raw.get('yardline_100'));member=None if yard is None or not 0<=yard<=100 else yard<=5
        distance=_number(raw.get('ydstogo'));distance=int(distance) if distance is not None and 0<=distance<=100 and distance==int(distance) else None
        return member,(down,distance) if down is not None and distance is not None else None
    return _flag(raw.get('goal_to_go')),(down,) if down is not None else None


def build_scoring_zone_decisions(event_receipt,*,before_period,cutoff):
    evidence=validate_event_evidence(event_receipt,before_period=before_period,cutoff=cutoff)
    teams={};event_ids=set()
    for e in evidence['events']:
        key=(e['game_id'],canonical_team(e['team']));native=(e['game_id'],e['play_id'])
        if native in event_ids:raise ValueError('Duplicate native event')
        event_ids.add(native)
        game=teams.setdefault(key,{mid:dict(cells={},unknown_coordinate_events=0,excluded_events=0,outside_subset_events=0) for mid in ('X05-M04','X05-M05')})
        decision=_call(e)
        for mid,table in game.items():
            member,coords=_state(e['raw_flags'],mid)
            if decision=='excluded':table['excluded_events']+=1;continue
            if member is False:table['outside_subset_events']+=1;continue
            if coords is None:table['unknown_coordinate_events']+=1;continue
            cell=table['cells'].setdefault(coords,dict(pass_calls=0,rush_calls=0,unknown_membership_events=0,unknown_call_events=0))
            if member is None:cell['unknown_membership_events']+=1
            elif decision=='unknown':cell['unknown_call_events']+=1
            elif decision=='pass':cell['pass_calls']+=1
            elif decision=='rush':cell['rush_calls']+=1
            else:raise ValueError('Unsupported reviewed call classification')
    rows=[]
    for (gid,team),metrics in sorted(teams.items()):
        result={}
        for mid,table in metrics.items():
            cells=[]
            for coords,m in sorted(table['cells'].items()):
                known=m['pass_calls']+m['rush_calls'];complete=not(m['unknown_membership_events'] or m['unknown_call_events'] or table['unknown_coordinate_events'])
                cells.append(dict(down=coords[0],**({'yards_to_go':coords[1]} if mid=='X05-M04' else {}),**m,known_called_decisions=known,
                    exact_decisions=known if complete else None,pass_fraction=m['pass_calls']/known if known and complete else None,
                    rush_fraction=m['rush_calls']/known if known and complete else None,known_sample_pass_fraction=m['pass_calls']/known if known else None))
            result[mid]={k:v for k,v in table.items() if k!='cells'}|dict(cells=cells)
        rows.append(dict(game_id=gid,team=team,metrics=result))
    facts=dict(version=VERSION,before_period=before_period,catalog_ids=['X05-M04','X05-M05'],game_rows=rows,
        definitions={'X05-M04':'Preplay yardline_100 in[0,5], native down1–4 and exact integer yards_to_go; called-pass vs designed nonkneel rush fraction',
                     'X05-M05':'Source goal_to_go=True, native down1–4; called-pass vs designed nonkneel rush fraction'},
        called_decision_basis='Reviewed G02: nonspike reported dropback OR designed nonkneel rush; scramble only dropback, sacks are pass calls; spikes/kneels/no_play/2PT excluded')
    return facts|dict(semantic_sha256=digest(facts),source_event_sha256=evidence['sha256'],source=deepcopy(evidence['source']),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False,
        limitations=['Observed conditional frequencies only, not calibrated future decision probabilities or scoring forecasts',
            'Inside-five and goal-to-go are separately sourced overlapping subsets, never added as independent opportunities',
            'Unknown membership/call masks its known coordinate; unknown coordinate can belong to any cell and masks all exact game cells',
            'Known-sample rates stay separately labeled; zero decisions undefined and absent cells are not certified zero',
            'Native team/game source scope before preferences; no player position/call-intent inference beyond declared reviewed call taxonomy'])


def derive_retrospective_scoring_zone_decisions(parent_ref,snapshot,*,actual_read_at,directory=None):
    from datetime import datetime,UTC
    from pathlib import Path
    import hashlib
    from .factual_designation import clock
    from .opportunity_source_capture import load_event_artifact
    original,actual,lock=(clock(v) for v in (parent_ref['decision_cutoff_at'],actual_read_at,snapshot.slate_lock_at))
    if None in (original,actual,lock) or not original<lock<=actual<=datetime.now(UTC):raise ValueError('Explicit nonfuture postlock retrospective boundary required')
    parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original,directory=directory)
    result=build_scoring_zone_decisions(parent['event_evidence'],before_period=parent_ref['before_period'],cutoff=actual)
    result['provenance']=dict(parent_artifact_ref=deepcopy(parent_ref),source=deepcopy(parent['event_evidence']['source']),
        producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
        original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),original_historical_availability='Unknown revised source; original pregame availability not established')
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('Observed scoring-zone decisions cannot serve models/forecasts/optimizer')
    return value
