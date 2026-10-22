"""Append source observations, never patch base rows or generate transitions."""
from copy import deepcopy
import math
from research.game_progression_pilot_20261020.raw_source_feasibility.linkage import quarter_seconds
from research.game_progression_pilot_20261020.observation_contract.contract import integer

VERSION='raw_clock_stop_observation_amendment_v1'

def build_records(cases,raw_rows,base_rows,bindings):
    game=bindings['game_id'];source_sha=bindings['raw_source_sha256']
    ids=[integer(r.get('playId'))for r in raw_rows];orders=[r.get('orderSequence')for r in raw_rows]
    if (None in ids or len(set(ids))!=len(ids)or len(set(orders))!=len(orders)
            or not all(type(v)in(int,float)and math.isfinite(v)for v in orders)):
        raise ValueError('Unique finite native raw identity/order required')
    raw={pid:(i,row)for i,(pid,row)in enumerate(zip(ids,raw_rows))}
    base={}
    for row in base_rows:
        key=row['provenance']['native_cycle_id']
        if key in base:raise ValueError('Ambiguous base native identity')
        base[key]=row
    selected=[r for r in cases if r['status']=='SOURCE_TYPED_CLOCK_STOP_OBSERVATION']
    selected_ids=[r['play_id']for r in selected]
    if len(set(selected_ids))!=len(selected_ids):raise ValueError('Duplicate selected source identity')
    records=[]
    for case in sorted(selected,key=lambda r:r['order_sequence']):
        pid=case['play_id'];key=f'{game}:{pid}'
        if key in base:raise ValueError('Append must not replace an existing base observation')
        if pid not in raw:raise ValueError('Missing native raw row')
        ordinal,row=raw[pid];q=integer(row.get('quarter'));clock=quarter_seconds(row.get('clockTime'))
        if (q not in(1,2,3,4)or clock is None or row.get('playType')!='TIMEOUT'
                or row.get('playDeleted')is not False or row.get('playReviewStatus')not in(None,'')
                or row.get('orderSequence')!=case['order_sequence']or q!=case['quarter']
                or row.get('clockTime')!=case['source_clock']or row.get('playDescription')!=case['reported_description']):
            raise ValueError('Qualified case must match undeleted native timeout evidence')
        expected_reason='SOURCE_REPORTED_TWO_MINUTE_WARNING'if row.get('playDescription')=='Two-Minute Warning'else'UNKNOWN_STOP_CAUSE'
        if (case['reason']!=expected_reason or not case['same_quarter_clock_bracket']
                or case['timeout_team']is not None or case['timeout_budget_debit_proven']
                or case['physical_play_end_clock']is not None or case['restart_policy']is not None
                or case['generated_state_transition_supported']):raise ValueError('Source qualification/unknown support differs')
        anchors=[];native=[]
        for name in ('preceding_matched_play_id','following_matched_play_id'):
            aid=case[name];ak=f'{game}:{aid}'
            if aid not in raw or ak not in base:raise ValueError('Both native and base anchors required')
            anchor=base[ak];araw=raw[aid][1];observed=anchor['pre_event']['clock']
            if (anchor['provenance']['projection_sha256']!=bindings['base_projection_sha256']
                    or anchor['record_id']!=f'clock_timeout_action_observation_v1|{bindings["base_projection_sha256"]}|{anchor["provenance"]["source_ordinal_zero_based"]}'
                    or observed['status']!='SOURCE_PRE_EVENT_VALIDATED'or observed['quarter']!=q
                    or araw.get('quarter')!=q or observed['quarter_seconds']!=quarter_seconds(araw.get('clockTime'))
                    or anchor['raw_pre_event']['order_sequence']!=araw.get('orderSequence')):
                raise ValueError('Base and raw anchor clock/order must agree')
            anchors.append(dict(native_id=ak,base_record_id=anchor['record_id'],
                base_source_ordinal_zero_based=anchor['provenance']['source_ordinal_zero_based'],
                raw_table_ordinal_zero_based=raw[aid][0]))
            native.append(araw)
        if not(native[0]['orderSequence']<row['orderSequence']<native[1]['orderSequence']
            and quarter_seconds(native[0]['clockTime'])>=clock>=quarter_seconds(native[1]['clockTime'])):
            raise ValueError('Verified same-quarter clock/order bracket required')
        half=1 if q<=2 else 2;half_clock=clock+(900 if q in(1,3)else 0)
        records.append(dict(version=VERSION,record_id=f'{VERSION}|{source_sha}|{bindings["native_game_uuid"]}|{pid}',
            operation='APPEND_SOURCE_OBSERVATION',replaces_record_id=None,native_id=key,
            provenance=dict(raw_source_sha256=source_sha,decoded_table_sha256=bindings['decoded_sha256'],
                native_game_uuid=bindings['native_game_uuid'],game_id=game,play_id=pid,
                raw_table_path='$.data.viewer.gameDetail.plays',raw_table_ordinal_zero_based=ordinal,
                base_ledger_sha256=bindings['base_ledger_sha256'],assessment_sha256=bindings['assessment_sha256'],
                original_pregame_availability_proven=False),
            row_kind='SOURCE_CLOCK_STOP_CONTROL',order_sequence=row['orderSequence'],
            reported_native_fields=deepcopy({k:row.get(k)for k in ('playId','orderSequence','quarter','clockTime','playType','playDeleted','playReviewStatus','playDescription','timeOfDay','endClockTime')}),
            observed_clock=dict(basis='NATIVE_CONTROL_EVENT_QUARTER_CLOCK',quarter=q,quarter_seconds=clock,
                derived_half=half,derived_half_seconds=half_clock,derived_game_seconds=half_clock+(1800 if half==1 else 0)),
            clock_stop=dict(status='SOURCE_TYPED_CLOCK_STOP_OBSERVATION',running_at_event=False,reason=case['reason'],independent_official_adjudication=False),
            anchor_links=dict(preceding=anchors[0],following=anchors[1],relation='NATIVE_ORDER_AND_CLOCK_BRACKET_ONLY'),
            unobserved=dict(possession=None,field100=None,down=None,distance=None,scores=None,timeout_team=None,
                timeout_budgets=None,timeout_debit=None,physical_play_end_clock=None,restart_policy=None,runoff=None,
                correction=None,untimed_action_required=None),
            opportunity_or_scoring_credit=None,continuation_support='UNKNOWN',generated_policy_supported=False,activation=False))
    return records
