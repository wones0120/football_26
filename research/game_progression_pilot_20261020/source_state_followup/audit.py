"""One cached source audit; never changes frozen runs or executes simulations."""
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path
import json, signal, time
from backend.app.product_services.game_state_reconstruction import reconstruct_game_transitions, build_original_drive_blocks
from backend.app.product_services.event_boundary_progression import compile_cycles
from backend.app.product_services.game_progression_source_adapter import prior_contexts
from research.game_progression_pilot_20261020.v1.prepare_integrated import load, ref, ROOT

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic()
    with (D/'AUDIT_STARTED.json').open('x')as sink:
        json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=60),sink)
    def cap(*_):raise TimeoutError('60-second audit cap; no retry')
    previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        m=load(ref(D.parent/'scenario_04/MANIFEST.json'));v3=load(m['original_manifest_ref'])
        preserved=m['preserved_refs']+[ref(D.parent/'scenario_04'/name)for name in ('MANIFEST.json','VALIDATION.json','changed_smoke_1/paths.jsonl','changed_smoke_1/results.jsonl','changed_smoke_1/SUMMARY.json')]
        for r in preserved:assert ref(r['path'])==r
        paths=[json.loads(line)for line in (D.parent/'scenario_04/changed_smoke_1/paths.jsonl').read_text().splitlines()]
        stops=[r for r in paths if r.get('result')and r['result']['status']=='UNKNOWN_SOURCE_STATE']
        ids={r['result']['trace'][-1]['cycle_id']for r in stops}
        prior=load(v3['prior_manifest_ref']);contexts=prior_contexts(load(prior['input_refs']['prior_contexts'])['team_contexts'])
        projection=load(v3['source_projection_refs'][0]);raw=[dict(zip(projection['columns'],r))for r in projection['rows']]
        reconstruction=reconstruct_game_transitions(raw,source_lineage=projection['source_lineage'])
        blocks=build_original_drive_blocks(reconstruction);changed=compile_cycles(reconstruction,blocks,contexts)
        original=load(m['library_ref'])
        assert len(changed['cycles'])==len(original['cycles'])==43852
        assert changed['threats']==original['threats']and changed['boundaries']==original['boundaries']
        assert changed['source_marker_exclusions']==original['source_marker_exclusions']and changed['explicit_OT_exclusions']==original['explicit_OT_exclusions']
        assert sum(b['source_row_count']for b in blocks['blocks'])+len(blocks['deterministic_admin_markers'])+len(blocks['explicit_overtime_rows'])+len(reconstruction['quarantine'])==len(raw)
        fixed=('cycle_id','source_season','context_key','start','source_side','wait','endpoint','prior_bins')
        for old,new in zip(original['cycles'],changed['cycles']):
            assert all(old[k]==new[k]for k in fixed)
            assert not old['state_certified']or new['state_certified']
        old_by={c['cycle_id']:c for c in original['cycles']};new_by={c['cycle_id']:c for c in changed['cycles']}
        evidence=[]
        for game in reconstruction['games']:
            for step in game['rows']:
                cid=game['game_id']+':'+step['play_id'];event=step['event']
                if cid not in new_by:continue
                old,new=old_by[cid],new_by[cid]
                if cid in ids or old!=new:
                    evidence.append(dict(cycle_id=cid,raw=step['raw'],source_ordinal=step['source_ordinal'],
                        native_action_class_proof=event.get('native_action_class_proof'),source_transition_proofs=step['source_transition_proofs'],
                        old_state_certified=old['state_certified'],new_state_certified=new['state_certified'],
                        old_barriers=old['barriers'],new_barriers=new['barriers'],event_barriers_retained=event['barriers'],
                        old_production=old['production'],new_production=new['production'],reported_production=event.get('reported_production_by_side')))
        dispositions=[]
        for row in stops:
            cid=row['result']['trace'][-1]['cycle_id'];new=new_by[cid]
            dispositions.append(dict(game_id=row['game_id'],path=row['path'],arm=row['arm'],original_disposition=row['disposition'],cycle_id=cid,
                source_state_now_certified=new['state_certified'],remaining_barriers=new['barriers'],new_path_result_available=False))
        selected=[r for r in dispositions if r['original_disposition']=='DISPATCH_PRIOR_CAP_OR_FAILURE']
        assert len(selected)==36 and len({r['cycle_id']for r in selected})==35
        assert preserved==[ref(r['path'])for r in preserved]
        report=dict(version='source_state_followup_v1',elapsed_seconds=time.monotonic()-start,cap_seconds=60,
            source_projection_ref=v3['source_projection_refs'][0],comparison_library_ref=m['library_ref'],recipe_ref=ref(D/'RECIPE.md'),preserved_refs=preserved,
            train_cycles=len(new_by),old_certified=sum(c['state_certified']for c in old_by.values()),new_certified=sum(c['state_certified']for c in new_by.values()),
            selected_36_counts=dict(Counter('SOURCE_STATE_NOW_CERTIFIED'if r['source_state_now_certified']else'SOURCE_EVIDENCE_STILL_REQUIRED'for r in selected)),
            all_65_counts=dict(Counter('SOURCE_STATE_NOW_CERTIFIED'if r['source_state_now_certified']else'SOURCE_EVIDENCE_STILL_REQUIRED'for r in dispositions)),
            remaining_selected_barrier_path_counts=dict(Counter(b for r in selected if not r['source_state_now_certified']for b in set(r['remaining_barriers']))),
            changed_production_cycles=sum(c['production']!=old_by[c['cycle_id']]['production']for c in new_by.values()),
            all_candidates_and_selection_inputs_retained=True,previously_certified_states_preserved=True,source_rows_partitioned=True,
            evidence=evidence,path_dispositions=dispositions,
            code_refs=[ref(p)for p in (Path(__file__),ROOT/'backend/app/product_services/game_state_reconstruction.py',ROOT/'backend/app/product_services/event_boundary_progression.py')],
            simulations=0,fits=0,new_complete_path_claim=False,accuracy_assessed=False,activation=False)
        with (D/'AUDIT.json').open('x')as sink:json.dump(report,sink,indent=2);sink.write('\n')
        print(json.dumps({k:v for k,v in report.items()if k in ('elapsed_seconds','train_cycles','old_certified','new_certified','selected_36_counts','all_65_counts','remaining_selected_barrier_path_counts','changed_production_cycles')}))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

if __name__=='__main__':main()
