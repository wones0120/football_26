"""Immutable weekly report storage; reopening never rebuilds historical evidence."""
from datetime import UTC,datetime
import hashlib
import json
from pathlib import Path
import re
from fastapi.encoders import jsonable_encoder

LEDGER=Path('artifacts/weekly_learning_reports')
CONTRACT='saved_weekly_learning_report_v1'
MAX_BYTES=16_000_000


def _root(directory):return Path(directory) if directory is not None else LEDGER


def _validate(report):
    required={'report_id','season','week','entry_user','generated_at','status','summary','slate_reports','evidence_hash','missing_evidence','interpretation'}
    if not isinstance(report,dict) or not required<=report.keys() or report.get('contract_id') not in {'weekly_learning_report_v1','weekly_learning_report_v2'}:raise ValueError('A complete saved weekly learning report is required')
    at=datetime.fromisoformat(report['generated_at'].replace('Z','+00:00'))
    if at.tzinfo is None:raise ValueError('Weekly report generation timestamp requires timezone')
    if not str(report['entry_user']).strip() or not isinstance(report['season'],int) or not isinstance(report['week'],int):raise ValueError('Weekly report scope is missing')
    return report


def save_report(report,*,directory=None,original_bytes=None,recovered_from=None):
    _validate(report);report=jsonable_encoder(report)
    raw=original_bytes if original_bytes is not None else json.dumps(report,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>MAX_BYTES or json.loads(raw)!=report:raise ValueError('Weekly report source bytes mismatch or exceed limit')
    key=hashlib.sha256(raw).hexdigest();root=_root(directory);root.mkdir(parents=True,exist_ok=True);path=root/(key+'.json');receipt_path=root/(key+'.receipt.json')
    if receipt_path.exists():return metadata(key,directory=directory)
    try:
        with path.open('xb') as stream:stream.write(raw)
    except FileExistsError:
        if path.read_bytes()!=raw:raise ValueError('Immutable weekly report content conflict')
    receipt=dict(contract_id=CONTRACT,sha256=key,report_id=report['report_id'],season=report['season'],week=report['week'],entry_user=report['entry_user'],generated_at=report['generated_at'],status=report['status'],evidence_hash=report['evidence_hash'],saved_at=datetime.now(UTC).isoformat(),bytes=len(raw),storage_provenance='recovered_original' if recovered_from else 'saved_on_generation',original_reference=str(recovered_from) if recovered_from else None)
    try:
        with receipt_path.open('x') as stream:json.dump(receipt,stream,indent=2)
    except FileExistsError:return metadata(key,directory=directory)
    return receipt


def metadata(key,*,directory=None):
    if not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('Invalid saved weekly report key')
    receipt=json.loads((_root(directory)/(key+'.receipt.json')).read_text())
    if receipt.get('sha256')!=key or receipt.get('contract_id')!=CONTRACT:raise ValueError('Invalid saved weekly report receipt')
    return receipt


def load_report(key,*,entry_user,directory=None):
    receipt=metadata(key,directory=directory)
    if receipt['entry_user'].casefold()!=entry_user.strip().casefold():raise ValueError('Saved weekly report belongs to another username')
    path=_root(directory)/(key+'.json')
    if path.stat().st_size>MAX_BYTES:raise ValueError('Saved weekly report exceeds read limit')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=key:raise ValueError('Saved weekly report hash mismatch')
    report=_validate(json.loads(raw))
    for k in ('season','week','entry_user','generated_at','report_id','status','evidence_hash'):
        if report[k]!=receipt[k]:raise ValueError('Saved weekly report scope/receipt mismatch')
    return receipt,report,raw


def list_reports(*,entry_user,season=None,week=None,latest_per_week=True,directory=None):
    username=entry_user.strip().casefold()
    if not username:raise ValueError('DraftKings username is required')
    records=[]
    for path in _root(directory).glob('*.receipt.json'):
        try:
            key=path.name.removesuffix('.receipt.json');row=metadata(key,directory=directory)
            if row['entry_user'].casefold()!=username or (season is not None and row['season']!=season) or (week is not None and row['week']!=week):continue
            # List only original payloads that can actually be reopened.
            load_report(key,entry_user=entry_user,directory=directory);records.append(row)
        except (OSError,ValueError,KeyError):continue
    records.sort(key=lambda row:(row['season'],row['week'],datetime.fromisoformat(row['generated_at']),row['saved_at'],row['sha256']),reverse=True)
    counts={}
    for row in records:counts[(row['season'],row['week'])]=counts.get((row['season'],row['week']),0)+1
    seen=set();result=[]
    for row in records:
        scope=(row['season'],row['week'])
        if latest_per_week and scope in seen:continue
        result.append({**row,'version_count':counts[scope],'latest_for_week':scope not in seen});seen.add(scope)
    return result
