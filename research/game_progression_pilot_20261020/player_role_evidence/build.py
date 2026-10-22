"""One matchup, three immutable local snapshots; no DB/network/live writes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.player_role_source_features import extract_retained_role_sources
from backend.app.product_services.official_role_report_features import extract_official_role_report
from .evidence import build_evidence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ROLE = ROOT/'research/player_role_features_20261020/v1'
CAP = 10


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_snapshot(manifest_path):
    value = json.loads(manifest_path.read_text())
    value['metadata_json'] = value.pop('metadata')
    for key in ('observed_at','effective_at','captured_at','slate_lock_at'):
        if value.get(key): value[key] = datetime.fromisoformat(value[key].replace('Z','+00:00'))
    value['artifact_path'] = str(manifest_path.parent/Path(value['artifact_path']).name)
    value['manifest_path'] = str(manifest_path)
    snapshot = SimpleNamespace(**value)
    verify_snapshot_artifact(snapshot)
    return snapshot


def main():
    start=time.monotonic()
    with (HERE/'RUN_STARTED.json').open('x') as f:
        json.dump(dict(cap_seconds=CAP, automatic_retry=False),f);f.write('\n')
    receipt_path=ROLE/'actual_retained_feature_receipt.json'
    receipt=json.loads(receipt_path.read_text());ref=receipt['artifact_ref']
    parent_path=ROOT/'artifacts/player_role_features'/Path(ref['path']).name
    if parent_path.stat().st_size!=ref['bytes'] or digest(parent_path)!=ref['sha256']:
        raise ValueError('Retained source/identity parent bytes differ')
    parent=json.loads(parent_path.read_text());cutoff=parent['original_source_cutoff']
    source_paths=[];snapshots={}
    for row in json.loads((ROLE/'retained_source_inventory.json').read_text()):
        if row['snapshot_id'] not in receipt['source_snapshot_ids']:continue
        path=ROOT/Path(row['artifact_path']).relative_to(ROOT)
        snapshot=load_snapshot(path.parent/'manifest.json')
        if snapshot.content_sha256!=row['content_sha256']:raise ValueError('Source inventory hash differs')
        snapshots[snapshot.dataset]=snapshot
        source_paths += [Path(snapshot.manifest_path),Path(snapshot.artifact_path)]
    # Canonical UUIDs come from the frozen native-ID map, not display names.
    aliases={a['source_player_id']:a['player_master_id'] for a in parent['extracted']['actors']}
    extracted=extract_retained_role_sources(snapshots['weekly_rosters'],snapshots['player_depth_charts'],aliases,
        season=2026,week=6,teams=['SF','WAS'],cutoff=cutoff)
    if extracted['actors']!=parent['extracted']['actors']:
        raise ValueError('Full provider actor universe changed')
    official_path=ROOT/'artifacts/source_snapshots/nfl_official/official_final_game_report/season=2026/week=06/slate=monday_night/2d243b31-20c8-5176-83c1-5fc46fb102f0/manifest.json'
    official_snapshot=load_snapshot(official_path)
    source_paths += [official_path,Path(official_snapshot.artifact_path)]
    identity_path=ROLE/'actual_official_identity_persistence_receipt.json'
    identity=json.loads(identity_path.read_text())
    official_aliases=[dict(r,source_system='nfl_official',alias_name='') for r in identity['after']]
    # Names are intentionally absent: only a retained exact source-key alias
    # may link an official report row. Later alias time remains explicit.
    official=extract_official_role_report(official_snapshot,extracted['actors'],official_aliases,cutoff=cutoff)
    if any(a['method']!='source_native_id' for a in official['identity_resolution_actions']):
        raise ValueError('Unexpected name-based identity resolution')
    result=build_evidence(extracted,official,cutoff=cutoff,alias_recorded_at=identity['actual_persisted_at'])
    baseline=json.loads((HERE/'PRESERVATION_BASELINE.json').read_text())
    changed=[name for name,sha in baseline.items() if digest(ROOT/name)!=sha]
    if changed:raise ValueError(f'Preserved files changed: {changed}')
    elapsed=time.monotonic()-start
    if elapsed>=CAP:raise TimeoutError('Bounded role evidence audit cap exceeded')
    def save(name,value):
        with (HERE/name).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    save('SOURCE_EXTRACT.json',dict(roster_depth=extracted,official_report=official))
    save('EVIDENCE.json',result)
    counts=dict(actors=len(result['actors']),official_native_links=len(official['identity_resolution_actions']),
        identity_review_requests=len(result['identity_review_requests']),team_coverage=result['team_coverage'])
    refs=source_paths+[receipt_path,parent_path,identity_path,ROLE/'retained_source_inventory.json']
    refs += [HERE/n for n in ('evidence.py','build.py','RECIPE.md','PRESERVATION_BASELINE.json','SOURCE_EXTRACT.json','EVIDENCE.json')]
    refs += [ROOT/'backend/app/tests/product/test_player_role_evidence.py']
    save('MANIFEST.json',dict(status='RETROSPECTIVE_ROLE_EVIDENCE_ONLY',recorded_at=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=elapsed,cap_seconds=CAP,counts=counts,preservation_files=len(baseline),changed_preserved_files=changed,
        sources=3,matchups=1,network_requests=0,fits=0,simulations=0,activation=False,
        files=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p)) for p in refs]))
    print(json.dumps(dict(elapsed_seconds=elapsed,preserved=len(baseline),**counts)))


if __name__=='__main__':main()
