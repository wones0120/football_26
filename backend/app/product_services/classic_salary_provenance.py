"""Authenticate an existing native CSV without reimporting or renewing clocks."""
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path

from sqlalchemy import text

from .slate_preparation import aware


def _cell(value):
    if value is None or str(value).lower() == 'nan':
        return ''
    # Native CSV numeric spelling can differ from JSON's parsed numeric type.
    if isinstance(value, (int, float)):
        return str(value)[:-2] if str(value).endswith('.0') else str(value)
    return str(value).strip()


def verify_existing_import(ingest, raw_rows, salaries, *, cutoff):
    reasons = []
    try:
        content = Path(ingest['source_path']).read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        native = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    except (OSError, KeyError, ValueError, UnicodeError):
        native, checksum = [], None
        reasons.append('salary_original_csv_unreadable')
    if not checksum or checksum != ingest.get('source_checksum'):
        reasons.append('salary_original_csv_checksum_unverified')
    if ingest.get('status') != 'completed':
        reasons.append('salary_original_import_incomplete')
    try:
        if not (aware(ingest['started_at']) <= aware(ingest['completed_at']) <= aware(cutoff)):
            reasons.append('salary_original_import_clock_invalid')
    except (KeyError, AttributeError, TypeError, ValueError):
        reasons.append('salary_original_import_clock_missing')
    if not native or len(native) != len(raw_rows) or len(native) != ingest.get('rows_raw') or len(salaries) != ingest.get('rows_curated'):
        reasons.append('salary_original_row_count_mismatch')
    def signature(row):
        return json.dumps({k: _cell(v) for k, v in row.items()}, sort_keys=True)
    if Counter(signature(r) for r in native) != Counter(signature(r['raw_row_json']) for r in raw_rows):
        reasons.append('salary_raw_row_lineage_mismatch')
    by_key = {str(r.get('ID')): r for r in native}
    if len(by_key) != len(native):
        reasons.append('salary_native_ids_duplicated')
    columns = {'player_name':'Name', 'source_player_key':'ID', 'position':'Position', 'roster_position':'Roster Position',
               'salary':'Salary', 'game_info':'Game Info', 'team':'TeamAbbrev', 'player_status':'Status'}
    from ..services.matching import normalize_position
    for salary in salaries:
        row = by_key.get(str(salary.get('source_player_key')))
        if (not row or salary.get('ingest_run_id') != ingest.get('ingest_run_id')
                or any(_cell(salary.get(k)) != _cell(normalize_position(row.get(v)) if k in {'position', 'roster_position'} else row.get(v))
                       for k, v in columns.items())):
            reasons.append('salary_curated_row_lineage_mismatch')
            break
    return {'verified': not reasons, 'reason_codes': sorted(set(reasons)),
        'ingest_run_id': ingest.get('ingest_run_id'), 'source_path': ingest.get('source_path'),
        'source_checksum': checksum, 'native_row_count': len(native), 'raw_row_count': len(raw_rows),
        'curated_row_count': len(salaries), 'imported_at': ingest.get('started_at'),
        'completed_at': ingest.get('completed_at'), 'observation_basis': 'original_import_receipt_clock',
        'publication_at': None, 'provider_observation_at': None, 'reimported': False}


def read_salary_provenance(session, manifest, *, cutoff):
    result = {}
    for ingest_id in {r['ingest_run_id'] for r in manifest.get('salaries', [])}:
        ingest = dict(session.execute(text('SELECT * FROM public.ingest_run WHERE ingest_run_id=:id'), {'id': ingest_id}).mappings().one())
        raw = [dict(r) for r in session.execute(text('SELECT * FROM public.raw_salary_row WHERE ingest_run_id=:id'), {'id': ingest_id}).mappings()]
        result[str(ingest_id)] = verify_existing_import(ingest, raw,
            [r for r in manifest['salaries'] if r['ingest_run_id'] == ingest_id], cutoff=cutoff)
    return result
