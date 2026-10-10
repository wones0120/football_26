import { useEffect, useRef, useState } from 'react';
import { fetchEntryHistory, importEntryHistory, type EntryHistoryReport } from './api';

export function EntryHistory({ year, directory }: {year: number; directory: string}) {
  const [path, setPath] = useState(() => localStorage.getItem('football-26-entry-history-path') || `${directory.replace(/\/$/, '')}/draftkings-contest-entry-history.csv`);
  const [report, setReport] = useState<EntryHistoryReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const requestVersion = useRef(0);
  useEffect(() => {
    let active = true;
    const version = ++requestVersion.current;
    setReport(null); setError(''); setMessage('');
    fetchEntryHistory(year).then(r => { if (active && version === requestVersion.current) setReport(r); })
      .catch(e => { if (active && version === requestVersion.current) setError(String(e.message || e)); });
    return () => { active = false; };
  }, [year]);
  const load = async (preview: boolean) => {
    ++requestVersion.current;
    localStorage.setItem('football-26-entry-history-path', path);
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await importEntryHistory(path, year, preview);
      if (result.report) setReport(result.report);
      setMessage(`${result.status}: ${result.rows} entry records. ${preview ? 'Preview only; nothing saved.' : 'Results saved. Repeated and overlapping exports are deduplicated.'} ${result.shadow_comparison_status ?? ''}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const dollars = (v: number) => v.toLocaleString('en-US', {style: 'currency', currency: 'USD'});
  return <section className="panel operations-panel" aria-labelledby="entry-history-title">
    <h2 id="entry-history-title">Entry history and winnings</h2>
    <p>Download Entry History from DraftKings, save the CSV, then import it here. No screenshots needed.
      Each import records actual results across all dates in the file; the summary below shows NFL contests in calendar year {year}.</p>
    <div className="form-row column"><label>Entry-history CSV path<input className="full-width" value={path} disabled={busy}
      onChange={e => setPath(e.target.value)} /></label></div>
    <div className="button-row">
      <button disabled={busy || !path.trim()} onClick={() => void load(true)}>Validate history</button>
      <button disabled={busy || !path.trim()} onClick={() => void load(false)}>Import entry history</button>
    </div>
    {busy && <p role="status">Processing entry history…</p>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
    {report && <>
      <h3>Your paid-entry results</h3>
      <p>{report.summary.entries} paid entries · {report.summary.paid_finishes} paid finishes
        {report.summary.paid_finish_rate !== null && ` (${(100 * report.summary.paid_finish_rate).toFixed(1)}%)`}</p>
      <p>Fees: {dollars(report.summary.entry_fees)} · Cash winnings: {dollars(report.summary.cash_winnings)} ·
        Cash net return: {dollars(report.summary.cash_net_return)} · Ticket value: {dollars(report.summary.ticket_winnings)}</p>
      <p>Verified GPPs: {report.gpp_summary.entries} entries · {report.gpp_summary.paid_finishes} paid finishes.
        {' '}{report.unknown_type_entries} paid entries have an unverified contest type. Overall totals include any cash contests.</p>
      <p>{report.free_entries} free entries excluded · {report.snapshot_count} saved file snapshots.</p>
      {report.unmatched_contest_ids.length > 0 && <details><summary>{report.unmatched_contest_ids.length} contests need matching standings for lineup evaluation</summary>
        <p style={{overflowWrap: 'anywhere'}}>{report.unmatched_contest_ids.join(', ')}</p></details>}
      {report.conflicts.length > 0 && <p role="alert">{report.conflicts.length} conflicting entry records excluded; review the exports before using these totals.</p>}
      <p>Personal winnings are exact exported results. Places Paid identifies the paid cutoff;
        unplayed lineups’ exact returns still require full payout tables. Rebuild a learning report to include newly imported results.</p>
    </>}
  </section>;
}
