"""Observed third-failure opportunities and native next-decision states."""
from collections import Counter,defaultdict
from .drive_scoring_range import _physical_source,_half,_control,LIVE,VERSION as RANGE_VERSION
from .turnover_drive_start_context import _order
from .original_drive_field_context import _integer
from .fumble_event_components import _flag,_eligibility
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='observed_third_failure_next_decision_v1'
CHOICES=('field_goal_attempt','punt_attempt','physical_fourth_down_attempt')
SOURCE_FIELDS=set(LIVE)|{'game_id','play_id','season','week','season_type','posteam','defteam','drive','order_sequence','game_half','qtr','half_seconds_remaining','game_seconds_remaining','play_type','play_type_nfl','no_play','down','third_down_failed','third_down_converted','pass_touchdown','rush_touchdown','first_down_pass','first_down_rush','first_down_penalty','field_goal_result'}


def project_decision_source(row):
    return {k:row[k] if row[k]!='' else None for k in SOURCE_FIELDS&set(row)}


def _failure(raw):
    physical=_physical_source(raw);failed=_flag(raw.get('third_down_failed'));down=_integer(raw.get('down'))
    contradictions=any(_flag(raw.get(k)) is True for k in ('third_down_converted','first_down_pass','first_down_rush','first_down_penalty','pass_touchdown','rush_touchdown'))
    if physical is False or failed is False:return False
    if failed is True and (contradictions or down not in (None,3)):return None
    if down not in (None,3):return False
    if physical is None or failed is None or down is None:return None
    return True


def _summary(anchors,unknown_anchors):
    counts=Counter(a['outcome_category'] for a in anchors if a['outcome_category'] is not None)
    known=sum(counts.values());unknown=sum(a['outcome_category'] is None for a in anchors);n=len(anchors)
    choices=sum(counts[c] for c in CHOICES);complete=not unknown and not unknown_anchors
    return dict(known_eligible_third_failure_anchors=n,unknown_possible_anchor_rows=len(unknown_anchors),known_outcome_anchors=known,unknown_outcome_anchors=unknown,
        known_outcome_counts=dict(sorted(counts.items())),exact_outcome_counts=dict(sorted(counts.items())) if complete else None,
        all_anchor_denominator=n if not unknown_anchors else None,
        all_anchor_categorical_frequencies={c:k/n for c,k in sorted(counts.items())} if complete and n else None,
        known_outcome_sample_frequencies={c:k/known for c,k in sorted(counts.items())} if known else None,
        known_observed_choice_anchors=choices,known_choice_only_sample_frequencies={c:counts[c]/choices for c in CHOICES} if choices else None,
        exact_choice_only_frequencies={c:counts[c]/choices for c in CHOICES} if complete and choices else None,
        empty_anchor_cohort=not n and not unknown_anchors)


def build_third_down_decisions(records,ranges):
    if ranges.get('version')!=RANGE_VERSION or ranges.get('pregame_serving_eligible') is not False:raise ValueError('Reviewed nonserving original-drive boundary context required')
    before=ranges['before_period'];index={};timeline=defaultdict(list);bad=set();by_side={};drive_index={}
    for g in ranges['game_rows']:
        key=(g['native_game_id'],g['team'])
        if key in by_side:raise ValueError('Unique reviewed native offense-game required')
        by_side[key]=g
        for d in g['drives']:
            dk=(*key,d['original_drive_id'])
            if dk in drive_index:raise ValueError('Unique native original drive required')
            drive_index[dk]=d
    for raw in records:
        if raw.get('season_type')!='REG':continue
        season,week=_integer(raw.get('season')),_integer(raw.get('week'))
        if season is None or week is None or not 1<=week<=18:raise ValueError('Native REG period required')
        if season*100+week>=before:continue
        gid=raw['game_id'];parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(season),f'{week:02}']:raise ValueError('Native game-period differs')
        key=(gid,_integer(raw.get('play_id')))
        if key[1] is None or key in index:raise ValueError('Unique native play identity required')
        index[key]=raw;timeline[gid].append(raw)
        if _order(raw.get('order_sequence')) is None:bad.add(gid)
    for gid,rs in timeline.items():
        os=[_order(r.get('order_sequence')) for r in rs]
        if len(set(os))!=len(os):bad.add(gid)
        if gid not in bad:rs.sort(key=lambda r:_order(r['order_sequence']))
    anchors=defaultdict(list);uncertain=defaultdict(list);global_unknown=[]
    def next_state(raw,team,drive):
        gid=raw['game_id'];half=_half(raw);pid=_integer(raw['play_id']);did=_integer(raw.get('drive'))
        unknown=lambda reason,play=None:dict(outcome_category=None,outcome_reason=reason,next_decision_play_id=play)
        if gid in bad or half is None or drive is None or not drive['native_boundary_and_cohort_verified']:return unknown('Unknown provider order/original boundary/half')
        first=index.get((gid,drive['source_first_play_id']));last=index.get((gid,drive['source_last_play_id']))
        start_order=_order(first.get('order_sequence')) if first else None;end_order=_order(last.get('order_sequence')) if last else None
        anchor_order=_order(raw.get('order_sequence'))
        if start_order is None or end_order is None or not start_order<=anchor_order<=end_order:return unknown('Anchor outside verified source first/last boundary')
        def terminal():
            t=drive['verified_terminal_class']
            if t in {'END_HALF','END_GAME'}:return dict(outcome_category='verified_clock_end_before_next_decision',outcome_reason=t,next_decision_play_id=drive['source_last_play_id'])
            if t in {'INTERCEPTION','FUMBLE'}:return dict(outcome_category='typed_possession_end_before_next_decision',outcome_reason=t,next_decision_play_id=drive['source_last_play_id'])
            return unknown('Right-censored or unproven next decision/competing endpoint')
        for r in timeline[gid]:
            order=_order(r.get('order_sequence'))
            if order<=_order(raw['order_sequence']):continue
            if order>end_order:break
            rid=_integer(r['play_id']);named,conflict=_control(r)
            if conflict:return unknown('Positive live evidence on nominal control',rid)
            if _half(r)!=half:return unknown('Unknown/changed recognized source half',rid)
            if _integer(r.get('drive'))!=did:return unknown('Original-drive reset before next decision',rid)
            if _flag(r.get('first_down_penalty')) is True:
                off=canonical_team(r['posteam']) if r.get('posteam') else None
                if off==team:return dict(outcome_category='explicit_penalty_new_series',outcome_reason='Native same-side first-down-by-penalty proof before control skipping',next_decision_play_id=rid)
                return unknown('Material penalty first-down without same-offense proof',rid)
            if named:
                if rid==drive['source_last_play_id'] and drive['verified_terminal_class'] in {'END_HALF','END_GAME'}:return terminal()
                if r.get('play_type_nfl')=='TIMEOUT' or r.get('play_type_nfl')=='END_QUARTER' and _integer(r.get('qtr')) in {1,3}:continue
                return unknown('Unproven clock/control boundary',rid)
            off=canonical_team(r['posteam']) if r.get('posteam') else None
            if off!=team:return unknown('Missing/opposing offense before next decision',rid)
            if _flag(r.get('first_down_penalty')) is True:
                return dict(outcome_category='explicit_penalty_new_series',outcome_reason='Native first-down-by-penalty proof',next_decision_play_id=rid)
            live,_=_eligibility(r)
            if live is not True:return unknown('Unclassified/excluded/penalty live boundary, not a quiet admin skip',rid)
            down=_integer(r.get('down'))
            if down==4 and r.get('play_type')=='field_goal' and _flag(r.get('field_goal_attempt')) is True:
                return dict(outcome_category='field_goal_attempt',outcome_reason='Native live fourth-down field-goal attempt',next_decision_play_id=rid)
            if down==4 and r.get('play_type')=='punt' and _flag(r.get('punt_attempt')) is True:
                return dict(outcome_category='punt_attempt',outcome_reason='Native live fourth-down punt',next_decision_play_id=rid)
            physical=_physical_source(r)
            if physical is True and down==4:
                return dict(outcome_category='physical_fourth_down_attempt',outcome_reason='Official physical fourth-down attempt, not coach intent/aggression',next_decision_play_id=rid,
                    source_qb_kneel=_flag(r.get('qb_kneel')),source_qb_spike=_flag(r.get('qb_spike')))
            if physical is True and down in {1,2,3}:
                return dict(outcome_category='observed_new_or_repeated_down',outcome_reason='Next source physical down is not fourth; cause not inferred',next_decision_play_id=rid,source_next_down=down)
            return unknown('Unknown next-decision eligibility/down/type',rid)
        return terminal()
    for (gid,pid),raw in index.items():
        eligible=_failure(raw)
        if eligible is False:continue
        pair={canonical_team(x) for x in gid.split('_')[2:]};team=canonical_team(raw['posteam']) if raw.get('posteam') else None
        if team is not None and team not in pair:raise ValueError('Native offense outside game pair')
        did=_integer(raw.get('drive'));half=_half(raw)
        if eligible is None or team is None or did is None or half is None:
            item=dict(native_game_id=gid,play_id=pid,possible_offense_teams=sorted({team} if team else pair),reason='Unknown third-failure/native side/drive/half membership')
            global_unknown.append(item)
            for side in item['possible_offense_teams']:uncertain[(gid,side)].append(item)
            continue
        d=drive_index.get((gid,team,did));result=next_state(raw,team,d)
        anchors[(gid,team)].append(dict(native_game_id=gid,anchor_play_id=pid,original_drive_id=did,source_order=str(_order(raw.get('order_sequence'))),recognized_half=half,
            native_failed_third_down=True,**result))
    output=[];profiles=defaultdict(lambda:dict(anchors=[],unknown=[],gids=[]))
    for (gid,team),g in sorted(by_side.items()):
        a=anchors[(gid,team)];u=uncertain[(gid,team)];a.sort(key=lambda r:(_order(r['source_order']) is None,_order(r['source_order']) or 0))
        row=dict(native_game_id=gid,team=team,season=g['season'],week=g['week'],third_failure_anchors=a,unknown_possible_anchor_rows=u,metrics=_summary(a,u));output.append(row)
        p=profiles[(g['season'],team)];p['anchors']+=a;p['unknown']+=u;p['gids'].append(gid)
    missing_sides=sorted(set(anchors).union(uncertain)-set(by_side))
    core=dict(version=VERSION,candidate_id='X05-M08',before_period=before,game_rows=output,
        team_profiles=[dict(season=s,team=t,observed_game_ids=p['gids'],metrics=_summary(p['anchors'],p['unknown'])) for (s,t),p in sorted(profiles.items())],
        unknown_native_anchor_incidents=global_unknown,unbound_native_offense_sides=missing_sides,
        definitions=dict(unit='Each native source-proven physical failed-third-down opportunity/series, not distinct drives',
            all_anchor_frequency='Outcome count / all eligible third-failure anchors, only if every membership/outcome is known',
            conditional_choice_frequency='FG/punt/physical4th counts / sum of those three choice counts, separately named',
            known_sample='Explicitly observed known outcome/choice subset; never substituted for complete cohort',
            observation='Same-original-drive/offense/recognized-half next native-order event, only fully quiet controls skipped'))
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',forecast=None,model_or_optimizer_consumed=False,
        limitations=['Physical fourth-down attempts retain kneel/spike subtype, not inferred aggressive intent',
            'Competing new-series/typed-possession-end/clock-end states retained in all-anchor denominator',
            'Unknown penalty/live/reset/censoring blocks inheritance of a later decision; EOF is not no attempt',
            'Source cohort completeness/publication unknown; no future decision probabilities/causality/serving'])


def load_reviewed_decision_boundary(ref,*,cutoff):
    from pathlib import Path
    import json,hashlib
    from datetime import datetime,UTC
    from . import drive_scoring_range
    from .factual_designation import clock
    p=Path(ref['path']).resolve();actual=clock(cutoff)
    if p.parent!=Path('artifacts/drive_scoring_range').resolve() or p.name!=ref['sha256']+'.json' or not 0<ref['bytes']<=4*1024*1024:raise ValueError('Managed bounded reviewed drive boundary required')
    raw=p.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Boundary artifact bytes differ')
    x=json.loads(raw);pr=x['provenance'];t=clock(pr.get('actual_publication_at'))
    if actual is None or actual>datetime.now(UTC) or t is None or t>actual:raise ValueError('Boundary publication unavailable')
    if x.get('version')!=RANGE_VERSION or x.get('pregame_serving_eligible') is not False or x.get('forecast') is not None or pr.get('producer_code_sha256')!=hashlib.sha256(Path(drive_scoring_range.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed boundary producer/version/use differs')
    keys=('version','candidate_id','before_period','nominal_range_yards','game_rows','definition')
    if x['semantic_sha256']!=digest({k:x[k] for k in keys}):raise ValueError('Boundary semantic core differs')
    return x
