"""One new two-game native team transformation, all prior immutable caches reused."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,time,os
from backend.app.product_services.play_caller_package_choices import build_play_caller_package_choices
from backend.app.product_services.personnel_package_continuity import load_package_physical_component
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
OUT=Path('research/play_caller_package_choices_20261020/v1')


def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc)
def event(stage,evidence):
    row=dict(package='play_caller_package_choices_20261020/v1',agent='B',stage=stage,timestamp=now().isoformat(),evidence=evidence)
    fd=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
    try:os.write(fd,(json.dumps(row)+'\n').encode())
    finally:os.close(fd)


def read(ref,kind,cutoff):
    path=Path(ref['path']).resolve();raw=path.read_bytes()
    assert path.parent==Path('artifacts',kind).resolve() and path.name==ref['sha256']+'.json'
    assert len(raw)==ref['bytes']<=64*1024*1024 and sha(raw)==ref['sha256'];v=json.loads(raw)
    assert v['pregame_serving_eligible'] is False and clock(v['provenance']['actual_publication_at'])<=cutoff
    return v


def save(v):
    raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
    p=Path('artifacts/play_caller_package_choices')/(sha(raw)+'.json');p.parent.mkdir(exist_ok=True)
    if p.exists():assert p.read_bytes()==raw
    else:
        with p.open('xb') as f:f.write(raw)
        p.chmod(0o444)
    return dict(path=str(p.resolve()),sha256=sha(raw),bytes=len(raw))


def main():
    started=now();timer=time.monotonic();event('source_start','New two-game transform; approved caller/personnel/physical caches only')
    caller_receipt=json.loads(Path('research/documented_playcaller_change_20261020/v1/actual_receipt.json').read_text())
    parent_path=Path('research/personnel_package_continuity_20261020/v1/actual_receipt.json');parent=json.loads(parent_path.read_text())
    caller=read(caller_receipt['full_ref'],'documented_playcaller_change',started)
    assert digest({k:v for k,v in caller.items() if k not in {'semantic_sha256','pregame_serving_eligible','model_consumed','optimizer_consumed','provenance'}})==caller['semantic_sha256']==caller_receipt['semantic_sha256']
    for field in ('producer_ref','article_parser_helper_ref','kickoff_helper_ref'):
        proof=caller['provenance'][field];raw=Path(proof['path']).read_bytes();assert len(raw)==proof['bytes'] and sha(raw)==proof['sha256']
    output=next(o for o in parent['outputs'] if o['season']==2023);source=next(o for o in parent['source_inputs'] if o['season']==2023)
    p=read(output['full_ref'],'personnel_package_continuity',started)
    assert digest({k:v for k,v in p.items() if k not in {'semantic_sha256','provenance','model_consumed','optimizer_consumed','pregame_serving_eligible','evidence_use'}})==p['semantic_sha256']
    assert p['provenance']['producer_code_sha256']==sha(Path('backend/app/product_services/personnel_package_continuity.py').read_bytes())
    physical=load_package_physical_component(source['physical_component_ref'],cutoff=started)
    assert source['physical_component_ref']==p['provenance']['physical_component_ref']
    result=build_play_caller_package_choices(caller,p,physical)
    result['provenance']=dict(caller_ref=caller_receipt['full_ref'],personnel_ref=output['full_ref'],physical_ref=source['physical_component_ref'],frozen_identity_ref=p['provenance']['frozen_identity_ref'],
        source_receipt_ref=dict(path=str(parent_path),bytes=parent_path.stat().st_size,sha256=sha(parent_path.read_bytes())),source_schedule_ref=p['provenance']['schedule_ref'],
        actual_read_at=started.isoformat(),actual_publication_at=now().isoformat(),producer_code_hashes={str(path):sha(path.read_bytes()) for path in [Path('backend/app/product_services')/(name+'.py') for name in ('play_caller_package_choices','documented_playcaller_change','personnel_package_continuity','environment_context_evidence','fumble_event_components')]},
        chronology='Observed two-game retrospective source comparison; original source contents not captured before2023decision, no contemporaneous input or causal coach effect')
    full=save(result)
    affected={native for unit in result['source_unit_registry'].values() for native in unit['identity_unknown_native_ids']}
    inherited=[r for r in parent['queue']['durable_readback_records'] if r['source_player_key'] in affected]
    assert affected<={r['source_player_key'] for r in inherited}
    receipt=dict(status='awaiting_High_review',actual_started_at=started.isoformat(),actual_completed_at=now().isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=full,semantic_sha256=result['semantic_sha256'],
        source_refs=dict(caller=caller_receipt['full_ref'],personnel=output['full_ref'],physical=source['physical_component_ref']),
        game_ids=[g['game_id'] for g in result['games']],physical_snap_counts=[g['known_physical_snaps'] for g in result['games']],
        package_union=len(result['package_registry']),exact_package_use_comparisons=sum(r['package_use_fraction_difference'] is not None for r in result['comparisons']),exact_within_package_call_comparisons=sum(r['within_package_pass_call_fraction_difference'] is not None for r in result['comparisons']),
        unknown_physical_or_side=[g['unknown_physical_or_side'] for g in result['games']],unknown_package=[g['unknown_package_snaps'] for g in result['games']],canonical_member_unknown_snaps=[g['canonical_member_unknown_snaps'] for g in result['games']],
        inherited_identity_cases=inherited,inherited_readback_at=parent['queue']['actual_readback_at'],fresh_DB_readback=False,new_identity_cases=0,
        raw_source_reads=0,source_adapter_replays=0,DB_reads=0,DB_writes=0,source_captures=0,alias_queries=0,parent_inflations=0,model_runs=0)
    with (OUT/'actual_receipt.json').open('x') as f:json.dump(receipt,f,indent=2,sort_keys=True);f.write('\n')
    event('source_end',str(full));print(json.dumps(receipt))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        event('source_failed',type(exc).__name__+': '+str(exc));raise
