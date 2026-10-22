"""One capped schema/native-linkage inventory of the already acquired game."""
from collections import Counter,defaultdict
from pathlib import Path
from datetime import datetime,UTC
import json,re,signal,time
import pyarrow.parquet as pq
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref
from research.game_progression_pilot_20261020.raw_source_feasibility.linkage import table_records,compare
from research.game_progression_pilot_20261020.control_linkage.linkage import clock_format

D=Path(__file__).resolve().parent

def scalar(value):return value[0]if isinstance(value,list)and len(value)==1 else None

def main():
    start=time.monotonic()
    with (D/'INVENTORY_STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=30),s)
    def cap(*_):raise TimeoutError('30-second cached inventory cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        prior_ref=ref(D.parent/'clock_gap_investigation/INVENTORY.json');prior=load(prior_ref)
        inspection=load(ref(D/'CACHED_INSPECTION.json'));root=load(inspection['decoded_ref']);game=root['data']['viewer']['gameDetail']
        raw=table_records(game['plays']);gid='2023_06_NO_HOU'
        source_ref=prior['input_refs'][1]
        columns=['game_id','nfl_api_id','play_id','order_sequence','qtr','quarter_seconds_remaining','play_type_nfl','play_deleted','desc']
        processed=pq.read_table(source_ref['path'],columns=columns,filters=[('game_id','=',gid)]).to_pylist()
        raw_game_uuid=scalar(game['id']);assert raw_game_uuid and all(r['nfl_api_id']==raw_game_uuid for r in processed)
        result=compare(raw,processed)
        ordered=sorted(raw,key=lambda r:r['orderSequence']);index=next(i for i,r in enumerate(ordered)if r['playId']==1890)
        fields=['playId','orderSequence','clockTime','quarter','endClockTime','timeOfDay','playClock','playType','playReviewStatus','playDeleted','prePlayByPlay','nextPlayType','playDescription']
        neighborhood=[{k:r.get(k)for k in fields}for r in ordered[max(0,index-1):index+2]]
        schema=defaultdict(Counter)
        def walk(value,path):
            if isinstance(value,dict):
                if value.get('__r_container__')=='DataFrame':
                    schema[path]['DataFrame']+=1
                    for r in table_records(value):
                        for key,v in r.items():walk(v,path+'.'+key)
                else:
                    schema[path]['dict']+=1
                    for key,v in value.items():walk(v,path+'.'+key)
            elif isinstance(value,list):
                schema[path]['list']+=1
                for v in value:walk(v,path+'[]')
            else:schema[path][type(value).__name__]+=1
        walk(root,'$')
        clock_paths={k:dict(v)for k,v in schema.items()if re.search(r'clock|restart|runoff|time|untimed|enforc',k,re.I)}
        own_refs=[ref(D/n)for n in ('RECIPE.md','ACQUISITION.json','DECODE.json','FRAME_INSPECTION_STARTED.json','CACHED_INSPECTION.json','READER.json','READER_INSTALL_REPORT.json','linkage.py','containers.py','inventory.py')]+[inspection['decoded_ref'],inspection['source_ref']]
        preserved=prior['preserved_refs']+prior['input_refs']+[prior_ref]+[ref(D.parent/'clock_gap_investigation'/n)for n in ('RESULTS.md','VALIDATION.json')]
        for r in own_refs+preserved+prior['current_runtime_refs']:assert ref(r['path'])['sha256']==r['sha256']
        report=dict(version='one_game_raw_source_gate_v1',elapsed_seconds=time.monotonic()-start,cap_seconds=30,game_id=gid,
            native_game_uuid=raw_game_uuid,game_uuid_matches_processed=True,comparison=result,original_path_types={k:dict(v)for k,v in schema.items()},
            timing_paths=clock_paths,play_clock_formats=dict(Counter(clock_format(r.get('endClockTime'))for r in raw)),
            start_wall_time_formats=dict(Counter(clock_format(r.get('timeOfDay'))for r in raw)),
            reported_play_clock_values=dict(Counter(str(r.get('playClock'))for r in raw)),runoff_neighborhood=neighborhood,
            game_snapshot=dict(gameClock=game['gameClock'],phase=game['phase'],period=game['period']),
            game_snapshot_is_per_play_end=False,new_supported_play_end_game_clock_records=0,new_supported_restart_enforcement_records=0,
            feasibility_gate_passed=False,disposition='RAW_GAME_REPEATS_SNAP_CLOCKS_WALL_TIMESTAMPS_AND_NARRATIVE;REQUIRED_OBSERVATIONS_NOT_ESTABLISHED',
            source_refs=own_refs,preserved_refs=preserved,current_runtime_refs=prior['current_runtime_refs'],
            original_pregame_availability_proven=False,total_game_downloads=1,reconstruction_runs=0,simulation_runs=0,fits=0,activation=False,
            inspection_deviations=['Generic JSON export rejected a nested DataFrame after successful RDS conversion.',
                'First dataframe inspection incorrectly assumed the root itself was a DataFrame.',
                'Corrected nested-container exporter tested and used once on cached bytes; no source refetch or cap increase.'])
        with (D/'INVENTORY.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','comparison','play_clock_formats','reported_play_clock_values','game_snapshot','feasibility_gate_passed')}))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
