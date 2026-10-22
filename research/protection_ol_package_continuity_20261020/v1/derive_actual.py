"""New OL transform only; SHA reuse of approved personnel/physical/identity caches."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,time,os,gc
from backend.app.product_services.protection_ol_package_continuity import build_protection_ol_continuity
from backend.app.product_services.personnel_package_continuity import load_package_physical_component
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock

OUT=Path('research/protection_ol_package_continuity_20261020/v1')
TIMING=Path('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl')


def now():return datetime.now(timezone.utc)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def event(stage,evidence):
    record=dict(package='protection_ol_package_continuity_20261020/v1',agent='B',stage=stage,timestamp=now().isoformat(),evidence=evidence)
    fd=os.open(TIMING,os.O_WRONLY|os.O_APPEND)
    try:os.write(fd,(json.dumps(record)+'\n').encode())
    finally:os.close(fd)


def read_parent(ref,kind,*,cutoff):
    path=Path(ref['path']).resolve();raw=path.read_bytes()
    assert path.parent==Path('artifacts',kind).resolve() and path.name==ref['sha256']+'.json'
    assert len(raw)==ref['bytes']<=96*1024*1024 and sha(raw)==ref['sha256']
    value=json.loads(raw)
    assert value.get('pregame_serving_eligible') is False and clock(value['provenance']['actual_publication_at'])<=cutoff
    return value


def save(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    assert len(raw)<=96*1024*1024
    p=Path('artifacts/protection_ol_package_continuity')/(sha(raw)+'.json');p.parent.mkdir(exist_ok=True)
    if p.exists():assert p.read_bytes()==raw
    else:
        with p.open('xb') as f:f.write(raw)
        p.chmod(0o444)
    return dict(path=str(p.resolve()),sha256=sha(raw),bytes=len(raw))


def main():
    started=now();tick=time.monotonic();event('source_start','Approved cached personnel/physical/frozen identity only')
    parent_path=Path('research/personnel_package_continuity_20261020/v1/actual_receipt.json')
    parent=json.loads(parent_path.read_bytes());identity_ref=parent['frozen_identity_ref']
    identity=read_parent(identity_ref,'coverage_receiver_performance',cutoff=started)
    identities=identity['native_identity_receipts'];assert len(identities)==2570
    alias_cutoff=clock(identity['provenance']['actual_alias_cutoff_at']);assert alias_cutoff<=clock(identity['provenance']['actual_publication_at'])<=started
    for native,proof in identities.items():
        for e in proof['original_alias_evidence']:
            assert e['source_key']==native and clock(e['created_at'])<=alias_cutoff and clock(e['player_master_created_at'])<=alias_cutoff
    assert digest({k:v for k,v in identity.items() if k not in {'semantic_sha256','provenance','evidence_use','pregame_serving_eligible','forecast'}})==identity['semantic_sha256']
    for path,expected in identity['provenance']['producer_code_hashes'].items():assert sha(Path(path).read_bytes())==expected
    outputs=[];affected=set();source_inputs=[]
    for output,source in zip(parent['outputs'],parent['source_inputs']):
        season=output['season'];assert source['season']==season
        p=read_parent(output['full_ref'],'personnel_package_continuity',cutoff=started)
        assert p['provenance']['producer_code_sha256']==sha(Path('backend/app/product_services/personnel_package_continuity.py').read_bytes())
        assert digest({k:v for k,v in p.items() if k not in {'semantic_sha256','provenance','model_consumed','optimizer_consumed','pregame_serving_eligible','evidence_use'}})==p['semantic_sha256']
        assert p['provenance']['frozen_identity_ref']==identity_ref and p['provenance']['physical_component_ref']==source['physical_component_ref']
        assert clock(p['provenance']['actual_publication_at'])<=started
        physical=load_package_physical_component(source['physical_component_ref'],cutoff=started)
        b=build_protection_ol_continuity(p,physical,identities);affected.update(b['identity_request_native_ids'])
        b['provenance']=dict(personnel_ref=output['full_ref'],physical_ref=source['physical_component_ref'],frozen_identity_ref=identity_ref,
            frozen_alias_cutoff_at=alias_cutoff.isoformat(),source_receipt_ref=dict(path=str(parent_path),bytes=parent_path.stat().st_size,sha256=sha(parent_path.read_bytes())),
            producer_code_sha256=sha(Path('backend/app/product_services/protection_ol_package_continuity.py').read_bytes()),actual_read_at=started.isoformat(),actual_publication_at=now().isoformat(),
            historical_availability='FTN postseason and later revised PBP; original pregame availability unknown, current2026 unsupported')
        full=save(b)
        selected=dict(b,game_rows=[r for r in b['game_rows'] if r['team'] in {'SF','WAS'}],continuity_rows=[r for r in b['continuity_rows'] if r['team'] in {'SF','WAS'}],profiles=[r for r in b['profiles'] if r['team'] in {'SF','WAS'}],event_basis=[r for r in b['event_basis'] if r['team'] in {'SF','WAS'} or r['team'] is None],selection=dict(teams=['SF','WAS'],full_ref=full,global_unit_and_identity_universe_retained=True))
        selected_ref=save(selected)
        counts=dict(season=season,full_ref=full,selected_ref=selected_ref,semantic_sha256=b['semantic_sha256'],scheduled_team_games=len(b['game_rows']),first_games_NA=sum(r['first_game_not_applicable'] for r in b['continuity_rows']),
            exact_canonical_games=sum(r['catalog_value'] is not None for r in b['continuity_rows']),exact_native_games=sum(r['native_variant'] is not None and r['native_variant']['value'] is not None for r in b['continuity_rows']),
            exact_canonical_profiles=sum(r['canonical']['value'] is not None for r in b['profiles']),known_DBs=sum(g['known_physical_snaps'] for g in b['game_rows']),unknown_possible_DBs=sum(g['unknown_physical_or_side'] for g in b['game_rows']),
            unknown_five_OL_units=sum(g['unknown_units'] for g in b['game_rows']),unknown_identity_DBs=sum(g['identity_unknown_snaps'] for g in b['game_rows']),native_units=len(b['unit_registry']),affected_native_ids=b['identity_request_native_ids'])
        outputs.append(counts);source_inputs.append(dict(season=season,personnel_ref=output['full_ref'],physical_ref=source['physical_component_ref']));print(json.dumps(counts),flush=True)
        del p,physical,b,selected;gc.collect()
    # Reuse existing reviewed incident evidence; this is not a fresh DB readback.
    inherited=parent['queue']['durable_readback_records'];covered={r['source_player_key'] for r in inherited}
    assert affected<=covered,('new unresolved OL evidence requires approved queue handling',affected-covered)
    receipt=dict(status='awaiting_High_review',source_start=started.isoformat(),source_end=now().isoformat(),elapsed_seconds=time.monotonic()-tick,outputs=outputs,source_inputs=source_inputs,frozen_identity_ref=identity_ref,
        inherited_identity_case_records=[r for r in inherited if r['source_player_key'] in affected],inherited_readback_at=parent['queue']['actual_readback_at'],fresh_DB_readback=False,
        source_captures=0,raw_adapters=0,raw_PBP_reads=0,raw_participation_reads=0,parent_inflations=0,alias_queries=0,DB_writes=0,new_identity_cases=0,model_runs=0)
    with (OUT/'actual_receipt.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    event('source_end','Three cached OL-specific transforms published');print(json.dumps(dict(stage='END',elapsed_seconds=receipt['elapsed_seconds'],affected=sorted(affected))))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        event('source_failed',type(exc).__name__+': '+str(exc));raise
