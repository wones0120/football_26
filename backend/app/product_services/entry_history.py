"""Account-owned realized results from immutable DraftKings entry-history exports."""
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path

from sqlalchemy import text
from .contest_evidence import classify_contest_type
from .target_schema import validate_target_schema

REQUIRED = {'Sport','Game_Type','Entry_Key','Entry','Contest_Key','Contest_Date_EST','Place','Points',
            'Winnings_Non_Ticket','Winnings_Ticket','Contest_Entries','Entry_Fee','Prize_Pool','Places_Paid'}


def money(value):
    try:
        number = Decimal(str(value).replace('$','').replace(',','').strip())
        if not number.is_finite() or number < 0:
            raise ValueError('Money must be finite and nonnegative')
        if number != number.quantize(Decimal('.01')):
            raise ValueError('Money must have at most two decimal places')
        return float(number)
    except InvalidOperation as exc:
        raise ValueError('Invalid monetary amount') from exc


def parse_history(raw):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not REQUIRED.issubset(reader.fieldnames or []):
        raise ValueError('Expected DraftKings Download Entry History CSV with fees, winnings and Places_Paid')
    rows = {}
    for number, row in enumerate(reader, 2):
        try:
            entry_id, contest_id = row['Entry_Key'].strip(), row['Contest_Key'].strip()
            if not entry_id.isdigit() or not contest_id.isdigit():
                raise ValueError('Missing or invalid native entry/contest ID')
            date = datetime.strptime(row['Contest_Date_EST'], '%Y-%m-%d %H:%M:%S')
            size, rank, paid = (int(row[k]) for k in ('Contest_Entries','Place','Places_Paid'))
            if not 1 <= rank <= size or not 0 <= paid <= size:
                raise ValueError('Invalid rank, field size or paid-place count')
            points = Decimal(row['Points'])
            if not points.is_finite():
                raise ValueError('Invalid points')
            item = dict(entry_id=entry_id,contest_id=contest_id,contest_name=row['Entry'],
                sport=row['Sport'].upper(),game_type=row['Game_Type'],contest_date_est=date.isoformat(),
                rank=rank,points=float(points),field_size=size,places_paid=paid,
                entry_fee=money(row['Entry_Fee']),cash_winnings=money(row['Winnings_Non_Ticket']),
                ticket_winnings=money(row['Winnings_Ticket']),prize_pool=money(row['Prize_Pool']))
            key = (contest_id,entry_id)
            if key in rows and rows[key] != item:
                raise ValueError('Conflicting duplicate entry')
            rows[key] = item
        except (ValueError,TypeError,KeyError,InvalidOperation) as exc:
            raise ValueError(f'Entry history row {number}: {exc}') from exc
    if not rows:
        raise ValueError('Entry history is empty')
    return list(rows.values())


def merge_history(snapshots):
    """Overlapping exports deduplicate; conflicting versions require review, never silent replacement."""
    entries, conflicts = {}, set()
    for snapshot in snapshots:
        for item in snapshot['entries_json']:
            key = (item['contest_id'], item['entry_id'])
            if key in entries and entries[key] != item:
                conflicts.add(key)
            entries[key] = item
    return [v for k,v in entries.items() if k not in conflicts], sorted(conflicts)


def load_history(connection):
    snapshots = [dict(r) for r in connection.execute(text('''
        SELECT content_sha256, entries_json, imported_at FROM target.dk_entry_history_snapshot
        ORDER BY imported_at, content_sha256
    ''')).mappings()]
    entries, conflicts = merge_history(snapshots)
    return entries, conflicts, snapshots


def summarize(entries, contests, year, conflicts):
    contest_map = {str(c['contest_id']):c for c in contests}
    rows = [dict(e) for e in entries if e['sport']=='NFL' and int(e['contest_date_est'][:4])==year]
    for e in rows:
        contest = contest_map.get(e['contest_id'])
        e['slate'] = contest.get('slate_id') if contest else None
        e['week'] = contest.get('week') if contest else None
        e['contest_type'] = classify_contest_type(e['contest_name'],
            contest.get('contest_type') if contest else None)['contest_type']
        e['paid_finish'] = e['cash_winnings'] > 0 or e['ticket_winnings'] > 0
        e['cash_net_return'] = round(e['cash_winnings'] - e['entry_fee'],2)
    paid = [e for e in rows if e['entry_fee'] > 0]
    def totals(items):
        fee = round(sum(e['entry_fee'] for e in items),2)
        cash = round(sum(e['cash_winnings'] for e in items),2)
        return dict(entries=len(items),paid_finishes=sum(e['paid_finish'] for e in items),
            paid_finish_rate=sum(e['paid_finish'] for e in items)/len(items) if items else None,
            entry_fees=fee,cash_winnings=cash,cash_net_return=round(cash-fee,2),
            ticket_winnings=round(sum(e['ticket_winnings'] for e in items),2))
    return dict(year=year,summary=totals(paid),gpp_summary=totals([e for e in paid if e['contest_type']=='gpp']),
        unknown_type_entries=sum(e['contest_type']=='unknown' for e in paid),
        free_entries=len(rows)-len(paid),unmatched_contest_ids=sorted({e['contest_id'] for e in rows if e['slate'] is None}),
        conflicts=[dict(contest_id=c,entry_id=e) for c,e in conflicts],
        entries=sorted(rows,key=lambda e:(e['contest_date_est'],e['entry_id']),reverse=True),
        limitations=['Realized personal entry results, not counterfactual or expected returns.',
                    'Ticket value is separate from cash. Free entries are excluded from paid-entry metrics.',
                    'Unclassified contests are excluded from the GPP-only summary.',
                    'Places_Paid supplies a cutoff, not a complete payout ladder.'])


class EntryHistoryService:
    def __init__(self, engine):
        self.engine=engine

    def _ensure_schema(self):
        validate_target_schema(self.engine,consumer=type(self).__name__,required_tables=('dk_entry_history_snapshot',))

    def report(self, year):
        self._ensure_schema()
        with self.engine.connect() as c:
            entries, conflicts, snapshots = load_history(c)
            contests=[dict(r) for r in c.execute(text('SELECT contest_id,slate_id,week,contest_type FROM target.dfs_contest')).mappings()]
        return dict(summarize(entries,contests,year,conflicts),snapshot_count=len(snapshots))

    def import_file(self, path, year, dry_run=False, expected_sha256=None):
        path=Path(path).expanduser()
        if not path.is_file() or path.suffix.lower() != '.csv':
            raise ValueError('Choose an existing entry-history CSV file')
        raw=path.read_bytes()
        sha=hashlib.sha256(raw).hexdigest()
        if expected_sha256 is not None and sha != expected_sha256:
            raise ValueError("File changed since scanning; scan the folder again")
        rows=parse_history(raw)
        if dry_run:
            return dict(status='validated',rows=len(rows),content_sha256=sha)
        self._ensure_schema()
        with self.engine.begin() as c:
            inserted=c.execute(text('''
                INSERT INTO target.dk_entry_history_snapshot(content_sha256,original_path,raw_content,entries_json)
                VALUES (:sha,:path,:raw,CAST(:entries AS JSONB)) ON CONFLICT DO NOTHING
                RETURNING content_sha256
            '''),dict(sha=sha,path=str(path),raw=raw,entries=json.dumps(rows,allow_nan=False))).scalar()
        from .gpp_shadow_learning import refresh_after_import
        warnings = []
        try:
            message = refresh_after_import(self.engine)
        except Exception as exc:
            message = 'Saved; shadow comparison refresh pending'
            warnings.append(str(exc))
        try:
            report = self.report(year)
        except Exception as exc:
            report = None
            warnings.append(f'Saved; summary refresh pending: {exc}')
        return dict(status='imported' if inserted else 'deduplicated',rows=len(rows),content_sha256=sha,
                    report=report, shadow_comparison_status=message, warnings=warnings)


    @staticmethod
    def _root(directory):
        root = Path(directory).expanduser().absolute()
        if not root.is_dir():
            raise ValueError('Choose an existing entry-history folder')
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError('Symlinked entry-history folders are not supported')
        if any(part.casefold() == 'processed' for part in root.parts):
            raise ValueError('Choose the download folder, not Processed')
        return root

    @staticmethod
    def _source(root, path):
        source = Path(path).expanduser().absolute()
        relative = source.relative_to(root)
        if '..' in relative.parts or any(part.casefold() == 'processed' for part in relative.parts):
            raise ValueError('Choose a CSV inside the download folder, outside Processed')
        if any(p.is_symlink() for p in (source, *source.parents)):
            raise ValueError('Symlinked entry-history files are not supported')
        if source.suffix.lower() != '.csv' or not source.is_file():
            raise ValueError('Choose an existing entry-history CSV file')
        return source

    def scan_directory(self, directory, year):
        root = self._root(directory)
        files = []
        # Match content, not the export filename. Never follow links or scan archives.
        for base, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d.casefold() != 'processed'
                             and not (Path(base) / d).is_symlink())
            for name in sorted(names):
                path = Path(base) / name
                if path.suffix.lower() != '.csv' or path.is_symlink():
                    continue
                item = dict(path=str(path), status='unrecognized', rows=0)
                try:
                    raw = path.read_bytes()
                    item['content_sha256'] = hashlib.sha256(raw).hexdigest()
                    headers = next(csv.reader(io.StringIO(raw.decode('utf-8-sig'))), [])
                    if not REQUIRED.issubset(headers):
                        continue
                    rows = parse_history(raw)
                    item.update(status='validated', rows=len(rows))
                except (ValueError, OSError, UnicodeError, csv.Error) as exc:
                    item.update(status='failed', error=str(exc))
                files.append(item)
        return dict(directory=str(root), year=year, dry_run=True, files=files)

    @staticmethod
    def _archive(source, root, sha, result):
        # The immutable DB snapshot is committed before creating this archive receipt.
        # A hard link reserves the destination without ever overwriting another export.
        archive = root / 'Processed' / source.relative_to(root).parent
        if any(p.is_symlink() for p in (archive, *archive.parents)):
            raise ValueError('Symlinked archive folders are not supported')
        archive.mkdir(parents=True, exist_ok=True)
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != sha:
            raise ValueError('Source changed after import; original left in place')
        destination = archive / f'{source.stem}__{sha}{source.suffix}'
        receipt = destination.with_suffix(destination.suffix + '.receipt.json')
        if destination.exists():
            if destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest() != sha:
                raise FileExistsError('Archive collision; existing file preserved')
        else:
            os.link(source, destination)
        payload = dict(original_path=str(source), archive_path=str(destination),
                       content_sha256=sha, rows=result['rows'], import_status=result['status'],
                       archived_at=datetime.now(timezone.utc).isoformat())
        # Preserve the first receipt on retries, including its original timestamp.
        try:
            with receipt.open('x') as handle:
                json.dump(payload, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if receipt.is_symlink():
                raise ValueError('Symlinked archive receipt is not supported')
            saved = json.loads(receipt.read_text())
            if any(saved.get(k) != payload[k] for k in ('original_path', 'archive_path', 'content_sha256')):
                raise ValueError('Archive receipt collision; source preserved')
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != sha:
            raise ValueError('Source changed during archiving; source preserved')
        directory_fd = os.open(archive, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        source.unlink()
        return str(destination), str(receipt)

    def import_directory(self, directory, year, files):
        root = self._root(directory)
        results = []
        for selected in files:
            item = dict(path=selected['path'], content_sha256=selected['content_sha256'], rows=0)
            try:
                source = Path(selected['path']).expanduser().absolute()
                if not source.exists():
                    relative = source.relative_to(root)
                    if '..' in relative.parts or any(p.casefold() == 'processed' for p in relative.parts):
                        raise ValueError('Choose a source inside the download folder')
                    sha = selected['content_sha256']
                    destination = root / 'Processed' / relative.parent / f'{source.stem}__{sha}{source.suffix}'
                    receipt = destination.with_suffix(destination.suffix + '.receipt.json')
                    if any(p.is_symlink() for p in (destination, receipt, *destination.parents)):
                        raise ValueError('Symlinked archives are not supported')
                    saved = json.loads(receipt.read_text())
                    if saved.get('original_path') != str(source) or saved.get('content_sha256') != sha:
                        raise ValueError('Archive receipt does not match this request')
                    raw = destination.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != sha:
                        raise ValueError('Archive content does not match this request')
                    self._ensure_schema()
                    with self.engine.connect() as connection:
                        committed = connection.execute(text('''
                            SELECT content_sha256 FROM target.dk_entry_history_snapshot
                            WHERE content_sha256=:sha
                        '''), dict(sha=sha)).scalar()
                    if not committed:
                        raise ValueError('Archive has no committed entry-history snapshot')
                    item.update(status='deduplicated', rows=len(parse_history(raw)),
                                archive_status='processed', archive_path=str(destination), receipt_path=str(receipt))
                    results.append(item)
                    continue
                source = self._source(root, selected['path'])
                result = self.import_file(source, year, expected_sha256=selected['content_sha256'])
                item.update({k: v for k, v in result.items() if k != 'report'})
            except Exception as exc:
                item.update(status='failed', error=str(exc))
                results.append(item)
                continue
            try:
                destination, receipt = self._archive(source, root, result['content_sha256'], result)
                item.update(archive_status='processed', archive_path=destination, receipt_path=receipt)
            except Exception as exc:
                item.update(archive_status='pending', error=f'Import saved; archive pending: {exc}')
            results.append(item)
        response = dict(directory=str(root), year=year, dry_run=False, files=results)
        try:
            response['report'] = self.report(year)
        except Exception as exc:
            response['warning'] = f'Summary refresh pending: {exc}'
        return response


def enrich_contests(contests, entries):
    """Add exported financial context only when all personal rows agree and sizes match.

No synthetic payout tiers are created. This is postgame evidence only.
"""
    output=[]
    for contest in contests:
        item=dict(contest)
        matches=[e for e in entries if e['contest_id']==str(item['contest_id']) and e['sport']=='NFL']
        fields=('field_size','places_paid','entry_fee','prize_pool','contest_name')
        if matches and len({tuple(e[k] for k in fields) for e in matches}) == 1:
            row=matches[0]
            if int(item.get('field_size') or 0)==row['field_size']:
                for key in ('entry_fee','prize_pool'):
                    if item.get(key) is None:
                        item[key]=row[key]
                item['places_paid']=row['places_paid']
                item['paid_places_source']='draftkings_entry_history'
                item['contest_name']=row['contest_name']
                classification=classify_contest_type(row['contest_name'],item.get('contest_type'))
                item['contest_type']=classification['contest_type']
                item['contest_type_source']=classification['contest_type_source']
        output.append(item)
    return output
