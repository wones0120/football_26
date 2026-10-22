"""One bounded inventory of remaining clock evidence, without transition changes."""
from collections import Counter
from datetime import datetime,UTC
from pathlib import Path
import importlib.util,json,shutil,signal,time
import pyarrow.parquet as pq
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref,ROOT
from research.game_progression_pilot_20261020.clock_gap_investigation.probe import mentions,field_format,PATTERNS

D=Path(__file__).resolve().parent
FIELDS=('game_id','play_id','order_sequence','qtr','game_half','quarter_seconds_remaining','half_seconds_remaining',
    'game_seconds_remaining','time_of_day','end_clock_time','play_clock','desc','play_type_nfl',
    'play_deleted','replay_or_challenge','replay_or_challenge_result','out_of_bounds','penalty','penalty_type')

def main():
    start=time.monotonic()
    with (D/'STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=30,max_saved_cases=100),s)
    def cap(*_):raise TimeoutError('30-second evidence inventory cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        prior_ref=ref(D.parent/'control_linkage/MANIFEST.json');m=load(prior_ref)
        source=m['source_lineage']['original_source'];source_ref=ref(source['path'])
        assert source_ref['sha256']==source['sha256']and source_ref['bytes']==source['bytes']
        legacy_ref=ref(ROOT/'research/native_clock_coverage_20261020/v1/receipt.json')
        inputs=[prior_ref,source_ref,legacy_ref,ref(D/'RECIPE.md'),ref(D/'SOURCE_REVIEW.json'),ref(D/'probe.py'),ref(__file__)]
        preserved=m['preserved_refs']+m['input_refs']+[m['enrichment_ref']]+[ref(D.parent/'control_linkage'/n)for n in ('RESULTS.md','VALIDATION.json')]
        schema=pq.read_schema(source['path']);rows=pq.read_table(source['path'],columns=list(FIELDS)).to_pylist()
        assert len(rows)==m['rows']==49665
        formats={k:Counter()for k in ('time_of_day','end_clock_time','play_clock')};counts=Counter();cases=[];candidate_ids=set();total_candidate_rows=0
        for ordinal,raw in enumerate(rows):
            for field,counter in formats.items():counter[field_format(field,raw[field])]+=1
            found=mentions(raw)
            if found:
                total_candidate_rows+=1;candidate_ids.update(x['native_id']for x in found if x['native_id'])
                counts.update(x['kind']for x in found)
                if len(cases)<100:cases.append(dict(source_ordinal_zero_based=ordinal,raw=raw,mentions=found))
        overlaps={}
        for name,path,expected in [('original_v3',D.parent/'v3/smoke_attempt_3/paths.jsonl',72),
                                   ('changed_scenario04',D.parent/'scenario_04/changed_smoke_1/results.jsonl',32)]:
            inputs.append(ref(path));stops=[json.loads(line)for line in path.read_text().splitlines()]
            stops=[r for r in stops if r['result']['status']=='UNKNOWN_CENSORED_SUCCESSOR'];assert len(stops)==expected
            overlaps[name]=dict(censored_stop_records=len(stops),candidate_terminal_matches=[dict(game_id=r['game_id'],path=r['path'],arm=r['arm'],cycle_id=r['result']['trace'][-1]['cycle_id'])for r in stops if r['result']['trace'][-1]['cycle_id']in candidate_ids])
        for r in inputs+preserved+m['current_runtime_refs']:assert ref(r['path'])['sha256']==r['sha256']
        report=dict(version='remaining_clock_gap_inventory_v1',elapsed_seconds=time.monotonic()-start,cap_seconds=30,
            input_refs=inputs,preserved_refs=preserved,current_runtime_refs=m['current_runtime_refs'],source_columns=schema.names,
            source_row_count=len(rows),field_format_counts={k:dict(v)for k,v in formats.items()},patterns=PATTERNS,
            narrative_mention_counts=dict(counts),candidate_rows=total_candidate_rows,saved_cases=len(cases),
            unsaved_candidate_rows=total_candidate_rows-len(cases),cases=cases,cohort_overlaps=overlaps,
            rds_reader_availability=dict(Rscript=shutil.which('Rscript'),rdata=bool(importlib.util.find_spec('rdata')),pyreadr=bool(importlib.util.find_spec('pyreadr'))),
            identified_supported_play_end_game_clock_records=0,identified_supported_restart_enforcement_records=0,
            disposition='CACHED_EVIDENCE_INVENTORIED_REQUIRED_OBSERVATIONS_STILL_UNIDENTIFIED',
            raw_release_contents_inspected=False,new_game_data_downloads=0,reconstruction_runs=0,simulation_runs=0,fits=0,activation=False)
        with (D/'INVENTORY.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','source_row_count','field_format_counts','narrative_mention_counts','candidate_rows','cohort_overlaps','rds_reader_availability','disposition')}))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
