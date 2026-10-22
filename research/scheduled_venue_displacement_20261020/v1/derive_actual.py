"""Bounded new transformation over approved schedule and versioned venue inputs."""
from pathlib import Path
from datetime import datetime, UTC
from collections import Counter
from zoneinfo import TZPATH
import csv, hashlib, json, time, sys
from backend.app.product_services.scheduled_venue_displacement import build_scheduled_venue_displacement
from backend.app.services.venue_registry import load_venue_registry_seed

ROOT=Path('research/scheduled_venue_displacement_20261020/v1')
start=time.monotonic(); now=datetime.now(UTC)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def ref(path):
    raw=path.read_bytes();return dict(path=str(path.resolve()),sha256=sha(raw),bytes=len(raw))
def save_raw(raw,kind,suffix):
    path=Path('artifacts')/kind/(sha(raw)+suffix);path.parent.mkdir(exist_ok=True)
    if path.exists():assert path.read_bytes()==raw
    else:
        with path.open('xb') as f:f.write(raw)
        path.chmod(0o444)
    return ref(path)
def save(value):return save_raw(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode(),'scheduled_venue_displacement','.json')
parent_receipt=Path('research/late_game_market_response_20261020/v1/actual_receipt.json')
parent=json.loads(parent_receipt.read_text())['full_ref']; path=Path(parent['path']).resolve()
assert path.parent==Path('artifacts/late_game_market_response').resolve() and path.name==parent['sha256']+'.json'
b=path.read_bytes();assert len(b)==parent['bytes'] and sha(b)==parent['sha256']
approved=json.loads(b);source=approved['provenance']['market_source']
# Reuse the approved exact source identity; no DB or adapter re-execution.
source_dir=Path('artifacts/source_snapshots/nflreadpy/schedule_context/season=2026/week=07/slate=offline_schedule_feature_inventory')/source['snapshot_id']
manifest_path=source_dir/'manifest.json';manifest=json.loads(manifest_path.read_text());csv_path=source_dir/'games_all_provider_seasons.csv'
b=csv_path.read_bytes();assert sha(b)==manifest['content_sha256']==source['sha256'] and len(b)==manifest['byte_count']<=32*1024*1024
assert manifest['snapshot_id']==source['snapshot_id'] and manifest['dataset']=='schedule_context' and manifest['source_system']=='nflreadpy'
assert manifest['metadata']['contract']=='native_schedule_context_features_v1'
assert manifest['observed_at']==manifest['captured_at'] and manifest['captured_at'].replace('Z','+00:00')==source['captured_at']
records=list(csv.DictReader(b.decode().splitlines()));assert len(records)==manifest['row_count']<=50000
assert {'stadium_id','location','gameday','gametime','season','week','game_type','game_id','home_team','away_team'}<=set(records[0])
selected=[r for r in records if r['season'] in {'2024','2025'} and r['game_type']=='REG']
assert Counter(r['season'] for r in selected)=={'2024':272,'2025':272}
# The old seed loader validates definitions only; no assess/apply/seed DB method is called.
registry_path=Path('backend/app/data/venue_registry_v1.json');seed=load_venue_registry_seed(registry_path)
registry=json.loads(registry_path.read_text());assert len(seed.records)==len(registry['venues'])==37
registry_ref=save_raw(registry_path.read_bytes(),'scheduled_venue_registry','.json')
result=build_scheduled_venue_displacement(records,registry)
assert len(result['profiles'])==64 and all(p['scheduled_games']==17 for p in result['profiles'])
assert all(len({r['week'] for r in result['game_rows'] if r['season']==p['season'] and r['team']==p['team']})==17 for p in result['profiles'])
zones=sorted({g['venue']['timezone'] for g in result['games'] if g['venue']})
tzrefs={}
for zone in zones:
    candidates=[Path(root)/zone for root in TZPATH if (Path(root)/zone).is_file()]
    assert candidates
    raw=candidates[0].read_bytes();assert raw.startswith(b'TZif')
    tzrefs[zone]=save_raw(raw,'scheduled_venue_timezone_rules','.tzif')
result['provenance']=dict(schedule_source=source,schedule_manifest_ref=ref(manifest_path),schedule_csv_ref=ref(csv_path),
    approved_parent_ref=parent,registry_ref=registry_ref,registry_reviewed_at=registry['reviewed_at'],
    registry_definition_loader_ref=ref(Path('backend/app/services/venue_registry.py')),
    prior_registry_review_document_ref=ref(Path('docs/WEATHER_VENUE_REGISTRY.md')),
    timezone_rules_refs=tzrefs,python_version=sys.version,
    producer_code_sha256=sha(Path('backend/app/product_services/scheduled_venue_displacement.py').read_bytes()),
    actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
    source_availability='revised schedule captured postlock; registry reviewed source definitions not original-pregame observation',
    coordinate_evidence='Per-record reviewed Wikidata URI and native PFR/game-override evidence retained; no new coordinate observation',
    source_fetches=0,database_reads=0,database_writes=0,parent_adapter_replays=0,parent_inflations=0,models=0)
full=save(result);selection=dict(result,game_rows=[r for r in result['game_rows'] if r['team'] in {'SF','WAS'}],
    profiles=[p for p in result['profiles'] if p['team'] in {'SF','WAS'}],selection=dict(teams=['SF','WAS'],full_ref=full,all_native_game_venue_proofs_retained=True));sel=save(selection)
out=dict(actual_started_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,
    full_ref=full,selected_ref=sel,registry_ref=registry_ref,semantic_sha256=result['semantic_sha256'],native_games=len(result['games']),
    team_games=len(result['game_rows']),first_game_not_applicable=sum(r['first_game_not_applicable'] for r in result['game_rows']),
    known_displacements=sum(r['great_circle_km'] is not None for r in result['game_rows']),
    unknown_displacements=sum(r['great_circle_km'] is None and not r['first_game_not_applicable'] for r in result['game_rows']),
    native_game_overrides=sum(g['venue_mapping']=='reviewed_native_game_override' for g in result['games']),
    known_profiles=sum(p['total_displacement_km'] is not None for p in result['profiles']),
    unknown_reasons=dict(Counter(reason for r in result['game_rows'] if not r['first_game_not_applicable'] for reason in r['unknown_reasons'])),
    source_fetches=0,database_reads=0,database_writes=0,parent_adapter_replays=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
