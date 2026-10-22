"""Assess newly discovered raw-only controls, preserving the schema-first finding."""
from pathlib import Path
from collections import Counter
import json,time,signal
import pyarrow.parquet as pq
from research.game_progression_pilot_20261020.v1.prepare_integrated import ref,load
from research.game_progression_pilot_20261020.raw_source_feasibility.linkage import table_records
from research.game_progression_pilot_20261020.raw_source_feasibility.controls import additional_controls

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic()
    with (D/'CONTROL_ASSESSMENT_STARTED.json').open('x')as s:json.dump(dict(cap_seconds=30,reason='Schema-only inventory found 15 raw-only IDs. Assess typed controls and matched native-order brackets without refetch or inventory rerun.'),s)
    def cap(*_):raise TimeoutError('30-second control assessment cap')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        inventory=load(ref(D/'INVENTORY.json'));inspection=load(ref(D/'CACHED_INSPECTION.json'))
        raw=table_records(load(inspection['decoded_ref'])['data']['viewer']['gameDetail']['plays'])
        # Keep only fully agreeing anchors; marker clock normalizations remain disclosed.
        disputed={r['play_id']for r in inventory['comparison']['differences']}
        anchors=set(inventory['comparison']['matched_ids'])-disputed
        cases=additional_controls(raw,anchors)
        known=[r for r in cases if r['status']=='SOURCE_TYPED_CLOCK_STOP_OBSERVATION']
        report=dict(version='raw_only_control_feasibility_assessment_v1',elapsed_seconds=time.monotonic()-start,
            inventory_ref=ref(D/'INVENTORY.json'),decoded_ref=inspection['decoded_ref'],
            code_refs=[ref(D/n)for n in ('controls.py','assess_controls.py')],
            cases=cases,additional_control_records=len(known),cause_counts=dict(Counter(r['reason']for r in known)),
            raw_only_records_by_matched_anchor_definition=len(cases),excluded_disputed_anchor_ids=sorted(disputed),
            partial_feasibility_pass=bool(known),support_type='NATIVE_CLOCK_STOP_EVENT_OBSERVATIONS_ONLY',
            prior_schema_only_gate_superseded=True,new_supported_play_end_game_clock_records=0,new_supported_restart_enforcement_records=0,
            generated_continuation_supported=False,source_refetches=0,activation=False)
        with (D/'CONTROL_ASSESSMENT.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','additional_control_records','cause_counts','raw_only_records_by_matched_anchor_definition','partial_feasibility_pass')}))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
