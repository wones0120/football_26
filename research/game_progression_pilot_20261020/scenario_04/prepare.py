"""One bounded cached derivation/dispatch plan; no simulation or fit."""
from collections import Counter
from datetime import datetime,UTC
from pathlib import Path
import json,signal,time
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref,publish,ROOT
from research.game_progression_pilot_20261020.scenario_04.common import apply_audit,plan_paths,DISPATCH,RUN_ID,REPAIRED,UNFINISHED

D=Path(__file__).resolve().parent

def main():
    sentinel=D/'PREPARE_STARTED.json';destination=D/'MANIFEST.json'
    if sentinel.exists()or destination.exists():raise ValueError('No preparation retry or overwrite')
    start=time.monotonic();stamp=datetime.now(UTC).isoformat()
    with sentinel.open('x')as sink:sink.write(json.dumps(dict(started_at=stamp,cap_seconds=30))+'\n')
    def cap(*_):raise TimeoutError('30-second preparation cap; no automatic retry')
    previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        p=D.parent;v3=p/'v3';old=load(ref(v3/'MANIFEST.json'));audit_ref=ref(p/'scenario_02/AUDIT_KICKOFF_ORIENTATION.json');audit=load(audit_ref)
        validation=load(ref(p/'scenario_02/VALIDATION.json'))
        for r in validation['final_file_refs'][:2]:
            if ref(ROOT/r['path'])['sha256']!=r['sha256']:raise ValueError('Audited source/runtime changed')
        if old['library_ref']!=audit['original_library_ref']:raise ValueError('Original TRAIN binding differs')
        library=load(old['library_ref']);changed=apply_audit(library,audit)
        if len(changed['cycles'])!=43852 or sum(c['state_certified']for c in changed['cycles'])!=43197:raise ValueError('Fixed audited TRAIN coverage differs')
        library_ref=publish(changed,'SCENARIO04_AUDITED_TRAIN_EVENT_RENEWAL')
        baseline_ref=ref(v3/'smoke_attempt_3/paths.jsonl');prior=[json.loads(line)for line in Path(baseline_ref['path']).read_text().splitlines()]
        games=load(old['games_ref']);plan=plan_paths(prior,audit['path_dispositions'],games)
        counts=Counter(r['disposition']for r in plan)
        if len(plan)!=320 or counts[REPAIRED]!=56 or counts[UNFINISHED]!=50 or sum(r['disposition']in DISPATCH for r in plan)!=106:raise ValueError('Frozen population/disposition differs')
        files=[v3/name for name in ('MANIFEST.json','CHECKPOINT.json','RESULTS.json','RESULTS.md','RECIPE.md','HANDOFF.json','smoke_attempt_3/SUMMARY.json','smoke_attempt_3/paths.jsonl')]
        files += [p/'scenario_01'/name for name in ('TIMING.json','VALIDATION.json','RESULTS.md')]
        files += [p/'scenario_02'/name for name in ('AUDIT.json','AUDIT_KICKOFF_ORIENTATION.json','VALIDATION.json','SOURCE_GAPS.json','RESULTS.md','RECIPE.md')]
        files += [p/'scenario_03'/name for name in ('RECONCILIATION.json','GAMEBOOK_EVIDENCE.json','VALIDATION.json','RESULTS.md','RECIPE.md')]
        preserved=[ref(path)for path in files]
        report=dict(version='scenario04_frozen_changed_smoke_manifest_v1',run_id=RUN_ID,started_at=stamp,completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,
            reason='Validate newly source-proven terminal transitions and separately dispatch prior cap/failure slots; skip unchanged known failures and completions',
            bounds=dict(preparation_seconds=30,whole_run_seconds=30,max_dispatched_paths=106,max_actions_per_path=400,uniforms_per_path=401),seed=17,paths_per_original_game_arm=32,
            original_manifest_ref=ref(v3/'MANIFEST.json'),baseline_paths_ref=baseline_ref,audit_ref=audit_ref,library_ref=library_ref,openings_ref=old['openings_ref'],games_ref=old['games_ref'],
            plan=plan,disposition_counts=dict(counts),preserved_refs=preserved,recipe_ref=ref(D/'RECIPE.md'),
            code_refs=[ref(path)for path in (D/'common.py',D/'prepare.py',D/'run.py',ROOT/'backend/app/product_services/event_boundary_progression.py',ROOT/'backend/app/product_services/game_progression_policy.py',ROOT/'backend/app/product_services/game_progression_runtime.py')],
            original_unknown_opening_and_source_mass_retained=True,actual_labels_generation_inputs=False,raw_reconstruction_runs=0,fits=0,simulations=0,activation=False)
        if preserved!=[ref(r['path'])for r in preserved]:raise ValueError('Preserved evidence changed during preparation')
        with destination.open('x')as sink:sink.write(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(seconds=report['elapsed_seconds'],disposition_counts=report['disposition_counts'],manifest_ref=ref(destination))))
    except Exception as exc:
        with (D/'PREPARE_FAILURE.json').open('x')as sink:sink.write(json.dumps(dict(error=type(exc).__name__+': '+str(exc),elapsed_seconds=time.monotonic()-start,no_retry=True),indent=2)+'\n')
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

if __name__=='__main__':main()
