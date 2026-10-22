"""One <=60s saved-library selector parity/timing check; no simulation or fit."""
from datetime import datetime,UTC
from pathlib import Path
import hashlib,json,random,signal,time
from backend.app.product_services.event_boundary_progression import choose,index_library
from research.game_progression_pilot_20261020.scenario_01.scan_reference import choose as scan_choose
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref,ROOT

D=Path(__file__).resolve().parent

def main():
    destination=D/'TIMING.json'
    if destination.exists():raise ValueError('No overwrite or unchanged rerun')
    start=time.monotonic();stamp=datetime.now(UTC).isoformat()
    def cap(*_):raise TimeoutError('60 second whole parity/timing cap; no retry')
    previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        manifest_path=D.parent/'v3/MANIFEST.json'
        manifest=json.loads(manifest_path.read_text());library=load(manifest['library_ref'])
        # Bind the preserved scan oracle to the implementation recorded by v3.
        handoff=json.loads((D.parent/'v3/HANDOFF.json').read_text())
        runtime_ref=next(r for r in handoff['current_code_refs']if r['path'].endswith('/event_boundary_progression.py'))
        original=load_source=D/'scan_reference.py'
        assert runtime_ref['sha256']=='baa43bc645c8188a1cd74b021021abc67a979312cc28eb0c2f2875cdc56a869f'
        preserved=[manifest_path,D.parent/'v3/CHECKPOINT.json',D.parent/'v3/RESULTS.json',D.parent/'v3/smoke_attempt_3/SUMMARY.json',D.parent/'v3/smoke_attempt_3/paths.jsonl']
        before=[ref(p)for p in preserved]
        t=time.perf_counter();indexed=index_library(library);build_seconds=time.perf_counter()-t
        # Verify every occurrence, input order and unknown mass, not just selected IDs.
        flattened=[c for pool in indexed.physical_index.values()for c in pool]
        assert len(flattened)==len(library['cycles'])==43852
        assert {id(c)for c in flattened}=={id(c)for c in library['cycles']}
        rng=random.Random(17)
        eligible=[c for c in library['cycles']if c['start']['half']in(1,2)and c['start']['remaining']is not None]
        queries=[]
        for c in rng.sample(eligible,128):
            s=dict(c['start'],scores=rng.choice([[0,0],[7,0],[0,7]]),possession_side=rng.randrange(2))
            context=dict(own_pass_share=rng.choice([None,.2,.5,.8]),opponent_pass_share=rng.choice([None,.2,.5,.8]))
            u=rng.random()
            queries.extend((s,context,arm,u)for arm in ('contextual','control'))
        t=time.perf_counter();scanned=[scan_choose(library,*q)for q in queries];scan_seconds=time.perf_counter()-t
        t=time.perf_counter();looked_up=[choose(indexed,*q)for q in queries];indexed_seconds=time.perf_counter()-t
        assert looked_up==scanned
        assert before==[ref(p)for p in preserved]
        report=dict(started_at=stamp,completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,whole_job_cap_seconds=60,
            seed=17,query_count=len(queries),cycle_count=len(flattened),physical_key_count=len(indexed.physical_index),index_build_seconds=build_seconds,
            scan_seconds=scan_seconds,indexed_seconds=indexed_seconds,lookup_speedup=scan_seconds/indexed_seconds,
            speedup_including_build=scan_seconds/(indexed_seconds+build_seconds),
            identical_selected_cycles_tiers_pool_sizes_unknown_mass=True,
            selection_digest=hashlib.sha256(json.dumps([(r[0]['cycle_id']if r[0]else None,*r[1:])for r in scanned]).encode()).hexdigest(),
            manifest_ref=ref(manifest_path),library_ref=manifest['library_ref'],original_runtime_ref=runtime_ref,scan_reference_ref=ref(original),
            implementation_ref=ref(ROOT/'backend/app/product_services/event_boundary_progression.py'),runner_ref=ref(__file__),preserved_evidence_refs=before,
            simulations=0,fits=0,accuracy_assessed=False,activation=False,
            limitation='Selector-only fixed sample timing; not full rollout throughput or a forecast accuracy claim')
        with destination.open('x')as sink:sink.write(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report[k]for k in ('query_count','cycle_count','index_build_seconds','scan_seconds','indexed_seconds','lookup_speedup','speedup_including_build','elapsed_seconds')}))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

if __name__=='__main__':main()
