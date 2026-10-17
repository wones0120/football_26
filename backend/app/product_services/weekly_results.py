"""Read-only weekly personal results from native entry IDs and saved evidence."""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import text

from .entry_history import load_history
from .target_schema import validate_target_schema


def _amount(value):
    return Decimal(str(value)) if value is not None else None


def financial_totals(entries):
    count = len(entries)
    fees = [e['entry_fee'] for e in entries if e['entry_fee'] is not None]
    cash = [e['cash_winnings'] for e in entries if e['cash_winnings'] is not None]
    complete = [e for e in entries if e['entry_fee'] is not None and e['cash_winnings'] is not None]
    known_fees = sum((_amount(v) for v in fees), Decimal(0))
    known_cash = sum((_amount(v) for v in cash), Decimal(0))
    fee_total = known_fees if count and len(fees) == count else None
    cash_total = known_cash if count and len(cash) == count else None
    net = cash_total - fee_total if fee_total is not None and cash_total is not None else None
    cashed = sum(v > 0 for v in cash)
    return dict(entries=count, fees_known_entries=len(fees), winnings_known_entries=len(cash),
        financial_complete_entries=len(complete), known_fees=float(known_fees),
        known_winnings=float(known_cash),
        known_net_profit=float(sum((_amount(e['cash_winnings']) - _amount(e['entry_fee']) for e in complete), Decimal(0))),
        fees=float(fee_total) if fee_total is not None else None,
        winnings=float(cash_total) if cash_total is not None else None,
        net_profit=float(net) if net is not None else None,
        roi=float(net / fee_total) if net is not None and fee_total else None,
        cash_rate=cashed / count if count and len(cash) == count else None,
        known_cash_entries=cashed, known_free_entries=sum(v == 0 for v in fees),
        ticket_winnings=float(sum((_amount(e['ticket_winnings']) for e in entries if e['ticket_winnings'] is not None), Decimal(0))))


def build_weekly_results(observed, history, conflicts, snapshots, reports, *, season, week, entry_user, available_weeks):
    history_by_key = {(e['contest_id'], e['entry_id']): e for e in history if e['sport'] == 'NFL'}
    conflict_keys = set(map(tuple, conflicts))
    sources = defaultdict(list)
    for snapshot in snapshots:
        for e in snapshot['entries_json']:
            sources[(e['contest_id'], e['entry_id'])].append(snapshot['content_sha256'])
    report_by_slate = {r['slate'].upper(): r for r in reports}
    entries = []
    seen = set()
    for observed_entry in observed:
        key = (str(observed_entry['contest_id']), str(observed_entry['entry_id']))
        if key in seen:
            continue
        seen.add(key)
        h = history_by_key.get(key) if key not in conflict_keys else None
        warnings = []
        if key in conflict_keys:
            warnings.append('Conflicting entry-history versions; financial amounts withheld.')
        elif h is None:
            warnings.append('Entry-history winnings unavailable; zero winnings are not assumed.')
        fee = h['entry_fee'] if h else observed_entry.get('entry_fee') if key not in conflict_keys else None
        if fee is None:
            warnings.append('Entry fee unavailable.')
        saved = report_by_slate.get(observed_entry['slate'].upper())
        if saved is None:
            warnings.append('Saved learning review unavailable for this slate.')
        elif not any((str(e['contest_id']), str(e['entry_id'])) == key for e in saved.get('entries') or []):
            warnings.append('This imported entry is absent from the saved learning review.')
        entries.append(dict(contest_id=key[0], entry_id=key[1], slate=observed_entry['slate'].upper(),
            contest_name=h['contest_name'] if h else observed_entry['contest_name'],
            entry_fee=fee, cash_winnings=h['cash_winnings'] if h else None,
            ticket_winnings=h['ticket_winnings'] if h else None,
            financial_source='entry_history' if h else 'contest_metadata_fee_only' if fee is not None else 'unavailable',
            source_hashes=sorted(set(sources[key])), warnings=warnings))
    slates = []
    for slate in sorted({e['slate'] for e in entries}):
        slate_entries = [e for e in entries if e['slate'] == slate]
        contests = []
        for cid in sorted({e['contest_id'] for e in slate_entries}):
            contest_entries = [e for e in slate_entries if e['contest_id'] == cid]
            contests.append(dict(contest_id=cid, contest_name=contest_entries[0]['contest_name'],
                                 summary=financial_totals(contest_entries), entries=contest_entries))
        saved = report_by_slate.get(slate)
        slates.append(dict(slate=slate, summary=financial_totals(slate_entries), contests=contests,
            report_id=saved['report_id'] if saved else None,
            report_created_at=saved['created_at'] if saved else None,
            missing_evidence=saved.get('missing_evidence') or [] if saved else []))
    return dict(season=season, week=week, entry_user=entry_user, available_weeks=available_weeks,
        summary=financial_totals(entries), slates=slates,
        warnings=sorted({w for e in entries for w in e['warnings']}),
        limitations=[
            'Scope: this user’s imported standings entries. Account-wide entry coverage is unverified.',
            'Financial totals read current imported history; saved learning warnings retain their report date.',
            'ROI uses exported fees and cash winnings. Refunds, credits, funding source and settlement status are unmodeled.',
            'Ticket prizes are separate from cash. A zero fee does not identify ticket funding.',
            'Exports and roster equality do not establish submission intent or timing.',
        ])


class WeeklyResultsService:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _rows(connection, sql, params):
        return [dict(row) for row in connection.execute(text(sql), params).mappings()]

    def report(self, *, season, week, entry_user):
        entry_user = entry_user.strip()
        if not entry_user:
            raise ValueError('DraftKings username is required')
        validate_target_schema(self.engine, consumer=type(self).__name__, required_tables=(
            'dfs_contest', 'dfs_contest_entry_result', 'dk_entry_history_snapshot', 'slate_learning_report'))
        params = dict(season=season, week=week, entry_user=entry_user.casefold())
        user_filter = "lower(regexp_replace(coalesce(entry.entry_name,''), '\\s+\\([0-9]+/[0-9]+\\)$', ''))=:entry_user"
        with self.engine.connect() as connection:
            weeks = self._rows(connection, '''SELECT DISTINCT contest.week
                FROM target.dfs_contest contest JOIN target.dfs_contest_entry_result entry USING(contest_id)
                WHERE contest.season=:season AND ''' + user_filter + ' ORDER BY contest.week DESC', params)
            observed = self._rows(connection, '''SELECT entry.contest_id,entry.entry_id,
                contest.slate_id AS slate,contest.contest_name,contest.entry_fee
                FROM target.dfs_contest contest JOIN target.dfs_contest_entry_result entry USING(contest_id)
                WHERE contest.season=:season AND contest.week=:week AND ''' + user_filter +
                ' ORDER BY contest.slate_id,entry.contest_id,entry.entry_id', params)
            reports = self._rows(connection, '''SELECT DISTINCT ON (upper(report.slate))
                report.report_id,report.slate,report.created_at,
                report.report_json->'missing_evidence' AS missing_evidence,
                (SELECT jsonb_agg(jsonb_build_object('contest_id',e.value->'contest_id','entry_id',e.value->'entry_id'))
                 FROM jsonb_array_elements(report.report_json->'entries') e(value)) AS entries
                FROM target.slate_learning_report report
                WHERE report.season=:season AND report.week=:week AND lower(report.entry_user)=:entry_user
                ORDER BY upper(report.slate),report.created_at DESC,report.report_id DESC''', params)
            history, conflicts, snapshots = load_history(connection)
        return build_weekly_results(observed, history, conflicts, snapshots, reports,
            season=season, week=week, entry_user=entry_user, available_weeks=[r['week'] for r in weeks])
