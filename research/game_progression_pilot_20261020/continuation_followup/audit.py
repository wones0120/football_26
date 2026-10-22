"""One capped cached continuation audit, without model or runtime mutation."""
from collections import Counter,defaultdict
from datetime import datetime,UTC
from pathlib import Path
import json,signal,time
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref
from research.game_progression_pilot_20261020.continuation_followup.support import joint_key,diagnose,action_kind

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic()
    with (D/'STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=30),s)
    def cap(*_):raise TimeoutError('30-second continuation audit cap; no retry')
    previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        m=load(ref(D.parent/'scenario_04/MANIFEST.json'));v3=load(m['original_manifest_ref'])
        inputs=[ref(D/'RECIPE.md'),ref(D/'support.py'),ref(__file__),ref(D.parent/'scenario_04/MANIFEST.json'),m['original_manifest_ref'],m['library_ref'],v3['source_projection_refs'][0]]
        preserved=m['preserved_refs']+[ref(D.parent/'scenario_04'/name)for name in ('VALIDATION.json','changed_smoke_1/results.jsonl','changed_smoke_1/paths.jsonl','changed_smoke_1/SUMMARY.json')]
        preserved += [ref(D.parent/'source_state_followup'/name)for name in ('AUDIT.json','VALIDATION.json','RESULTS.md','DEFERRED.json')]
        lib=load(m['library_ref']);by={c['cycle_id']:c for c in lib['cycles']}
        projection=load(v3['source_projection_refs'][0]);raw={}
        for values in projection['rows']:
            r=dict(zip(projection['columns'],values));cid=r['game_id']+':'+str(int(r['play_id']))
            if cid in by:
                if cid in raw:raise ValueError('Unique native play identity required')
                raw[cid]=r
        assert set(raw)==set(by)
        buckets=defaultdict(list)
        for c in lib['cycles']:buckets[joint_key(c,raw[c['cycle_id']])].append(c)
        reports={}
        cohorts={'original_v3':(D.parent/'v3/smoke_attempt_3/paths.jsonl',72),
                 'changed_scenario04':(D.parent/'scenario_04/changed_smoke_1/results.jsonl',32)}
        for name,(path,expected)in cohorts.items():
            inputs.append(ref(path));paths=[json.loads(line)for line in path.read_text().splitlines()]
            paths=[r for r in paths if r['result']['status']=='UNKNOWN_CENSORED_SUCCESSOR'];assert len(paths)==expected
            rows=[]
            for path_row in paths:
                trace=path_row['result']['trace'][-1];c=by[trace['cycle_id']];r=raw[c['cycle_id']]
                info=diagnose(c,buckets[joint_key(c,r)],trace['pre_remaining'])
                rows.append(dict(game_id=path_row['game_id'],path=path_row['path'],arm=path_row['arm'],cycle_id=c['cycle_id'],
                    source_native_game=r['game_id'],source_native_play=r['play_id'],source_action=action_kind(r),selector_tier=trace['tier'],
                    source_timeout_counts={k:r[k]for k in ('home_timeouts_remaining','away_timeouts_remaining')},
                    generated_timeout_state_available=False,**info))
            reports[name]=dict(records=len(rows),unique_source_cycles=len({r['cycle_id']for r in rows}),
                action_counts=dict(Counter(r['source_action']for r in rows)),selector_tiers=dict(Counter(r['selector_tier']for r in rows)),
                cross_120_second_strata=sum(r['crosses_120_second_stratum']is True for r in rows),
                with_horizon_matched_exact_followup_beyond_censor=sum(r['source_start_covers_generated_horizon']['counts'].get('exact_wait_beyond_censor',0)>0 for r in rows),
                minimum_gap_seconds=min(r['unobserved_seconds']for r in rows),maximum_gap_seconds=max(r['unobserved_seconds']for r in rows),
                rows=rows)
        for reference in inputs+preserved:assert ref(reference['path'])['sha256']==reference['sha256']
        report=dict(version='continuation_evidence_audit_v1',elapsed_seconds=time.monotonic()-start,cap_seconds=30,
            input_refs=inputs,preserved_refs=preserved,train_cycle_count=len(by),source_columns=projection['columns'],
            available_pre_snap_timeout_rows=sum(all(r[k]is not None for k in ('home_timeouts_remaining','away_timeouts_remaining'))for r in raw.values()),
            compiled_timeout_state_available=False,
            missing_bound_observations=['play_end_clock_and_terminal_state','clock_running_or_stopped_reason','restart_and_runoff_enforcement','generated_timeout_state_and_policy'],
            cohorts=reports,simulation_runs=0,fits=0,continuation_model_implemented=False,continuation_supported=False,activation=False)
        with (D/'AUDIT.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps(dict(seconds=report['elapsed_seconds'],cohorts={k:{f:v for f,v in r.items()if f!='rows'}for k,r in reports.items()})))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

if __name__=='__main__':main()
