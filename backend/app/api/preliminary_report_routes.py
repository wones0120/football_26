"""Read-only discovery of immutable preliminary snapshots for scoped UI selection."""
from itertools import islice
from pathlib import Path
import re
from fastapi import APIRouter, HTTPException, Query
from ..product_services import preliminary_optimizer as snapshots

MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_SCAN_BYTES = 128 * 1024 * 1024

router = APIRouter(prefix='/api/optimizer/preliminary/snapshots', tags=['preliminary-research'])

def _public(snapshot):
    from ..product_services.analyst_preparation import load_snapshot_handoff
    return {key: snapshot[key] for key in ['scope','projection_run_id','ownership_run_id','preparation_job_id','data_cutoff_at','assumption_manifest','assumption_manifest_sha256','source_sha256','pool_sha256']} | {
        'snapshot_sha256': snapshot['sha256'], 'classification': 'PRELIMINARY_RESEARCH', 'entry_ready': False,
        'analyst_handoff': load_snapshot_handoff(snapshot['sha256']),
        "analyst_intent_handoffs": (load_snapshot_handoff(snapshot["sha256"]) or {}).get("analyst_intent_handoffs", {}),
        'normal_reason_codes': snapshot['normal_readiness']['reason_codes']}

def _read(key):
    ledger = Path(snapshots.LEDGER).resolve()
    path = (ledger / (key + '.json')).resolve()
    if not re.fullmatch(r'[0-9a-f]{64}', key) or not path.is_relative_to(ledger) or not path.is_file() or path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError('Unavailable controlled snapshot')
    return _public(snapshots.load_snapshot(key))

@router.get('')
def snapshot_catalog(season: int, week: int = Query(ge=1,le=22), slate: str = Query(min_length=1,max_length=80)):
    ledger = Path(snapshots.LEDGER)
    if not ledger.is_dir(): return {'rows': [], 'warnings': []}
    files = list(islice(ledger.iterdir(), 51)); warnings = []
    if len(files) > 50: warnings.append('Snapshot library scan limited to 50 files; older or additional snapshots may not be shown.')
    rows = []; scanned_bytes = 0
    for path in files[:50]:
        if not re.fullmatch(r'[0-9a-f]{64}\.json', path.name): continue
        try:
            # Bound aggregate work as well as per-file size; real immutable pools carry full lineage.
            scanned_bytes += path.stat().st_size
            if scanned_bytes > MAX_SCAN_BYTES:
                warnings.append('Snapshot library scan byte budget exhausted; additional snapshots may not be shown.'); break
            row = _read(path.stem)
            if row['scope']['season']==season and row['scope']['week']==week and row['scope']['slate']==slate: rows.append(row)
        except (ValueError, OSError, KeyError): warnings.append('A snapshot record was invalid or unavailable and was not listed.')
    rows.sort(key=lambda r:r['assumption_manifest'].get('declared_at',''),reverse=True)
    return {'rows': rows, 'warnings': warnings}

@router.get('/{snapshot_sha256}')
def snapshot_metadata(snapshot_sha256: str):
    try: return _read(snapshot_sha256)
    except (ValueError, OSError, KeyError) as exc: raise HTTPException(status_code=404,detail='Preliminary snapshot unavailable') from exc
