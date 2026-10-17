import { useEffect, useState } from "react";
import { fetchWeeklyResults, type WeeklyResultsReport, type WeeklyResultTotals } from "./api";
import { resultCoverage, resultMoney, resultPercent, resultRoi, weeklyResultsForSlate } from "./weeklyResultsFormat";
import { ALL_LEARNING_SLATES } from "./learningContext";
import "./WeeklyResults.css";

function ResultCells({ totals }: { totals: WeeklyResultTotals }) {
  return <><td>{totals.entries}</td><td>{resultMoney(totals.fees)}</td><td>{resultMoney(totals.winnings)}</td>
    <td>{resultMoney(totals.net_profit)}</td><td>{resultRoi(totals)}</td>
    <td>{resultPercent(totals.cash_rate)} ({totals.known_cash_entries}/{totals.entries} known cashes)</td></>;
}
function ResultHeaders() {
  return <><th>Entries</th><th>Fees</th><th>Cash winnings</th><th>Net profit</th><th>ROI</th><th>Cash rate</th></>;
}

export function WeeklyResults({ season, week, slate = ALL_LEARNING_SLATES, entryUser, onWeekChange, onEntryUserChange }: {
  season: number; week: number; slate?: string; entryUser: string; onWeekChange: (week: number) => void;
  onEntryUserChange: (value: string) => void;
}) {
  const [weekReport, setReport] = useState<WeeklyResultsReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setReport(null); setError(""); setBusy(false);
    if (!entryUser.trim()) return;
    setBusy(true);
    void fetchWeeklyResults(season, week, entryUser.trim())
      .then(result => { if (active) setReport(result); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [season, week, entryUser, refresh]);
  const report = weekReport ? weeklyResultsForSlate(weekReport, slate) : null;
  const weeks = [...new Set([week, ...(report?.available_weeks ?? [])])].sort((a, b) => b - a);
  return <section className="panel operations-panel weekly-results" aria-labelledby="weekly-results-title">
    <div className="operations-panel-heading"><h2 id="weekly-results-title">Weekly Results</h2>
      <p>View imported entry results by week. Viewing and refreshing results do not build learning reports or change data.</p>
    </div>
    <div className="form-row">
      <label>Results username<input type="text" value={entryUser} onChange={e => onEntryUserChange(e.target.value)} /></label>
      <label>Results week<select value={week} onChange={e => onWeekChange(Number(e.target.value))}>
        {weeks.map(w => <option value={w} key={w}>Week {w}</option>)}
      </select></label>
      <button disabled={busy || !entryUser.trim()} onClick={() => setRefresh(n => n + 1)}>Refresh results</button>
    </div>
    {!entryUser.trim() && <p>Enter your DraftKings username to view imported results.</p>}
    {busy && <p role="status">Loading weekly results…</p>}
    {error && <p role="alert">{error}</p>}
    {report && <>
      <h3>{report.season} Week {report.week} · {slate === ALL_LEARNING_SLATES ? "All slates" : slate.replaceAll("_", " ")} · {report.entry_user}</h3>
      {report.summary.entries === 0 ? <p>No imported standings entries for this user and review scope. Results remain unknown.</p> : <>
        <p>{resultCoverage(report.summary)} · {report.summary.fees_known_entries}/{report.summary.entries} fees known · {report.summary.winnings_known_entries}/{report.summary.entries} winnings known.</p>
        <dl className="weekly-result-metrics" role="group" aria-label="Weekly financial totals">
          {[
            ["Entries", String(report.summary.entries)], ["Fees", resultMoney(report.summary.fees)],
            ["Cash winnings", resultMoney(report.summary.winnings)], ["Net profit", resultMoney(report.summary.net_profit)],
            ["ROI", resultRoi(report.summary)], ["Cash rate", `${resultPercent(report.summary.cash_rate)} (${report.summary.known_cash_entries}/${report.summary.entries} known cashes)`],
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl>
        {report.summary.financial_complete_entries < report.summary.entries && <p role="status">
          Incomplete financial evidence. Known fees {resultMoney(report.summary.known_fees)};
          known winnings {resultMoney(report.summary.known_winnings)};
          net for the {report.summary.financial_complete_entries} entries with both amounts {resultMoney(report.summary.known_net_profit)}.
          ROI for this review scope is unavailable. Missing winnings are not treated as zero.
        </p>}
        <p>Cash rate counts positive cash payouts per entry. {report.summary.known_free_entries} known zero-fee entries included;
          known ticket prizes {resultMoney(report.summary.ticket_winnings)} are separate from cash. ROI uses recorded fees.</p>
        <div className="scroll-table"><table className="compact-table"><caption>Slate results</caption>
          <thead><tr><th>Slate</th><ResultHeaders /></tr></thead><tbody>
            {report.slates.map(s => <tr key={s.slate}><td>{s.slate.replaceAll("_", " ")}</td><ResultCells totals={s.summary} /></tr>)}
          </tbody></table></div>
        {report.slates.map(s => <details key={s.slate} style={{ overflowWrap: "anywhere" }}>
          <summary>{s.slate.replaceAll("_", " ")} · {s.contests.length} contests · {resultCoverage(s.summary)}</summary>
          <div className="scroll-table"><table className="compact-table"><caption>{s.slate.replaceAll("_", " ")} contest results</caption>
            <thead><tr><th>Contest</th><ResultHeaders /></tr></thead><tbody>
              {s.contests.map(c => <tr key={c.contest_id}><td>{c.contest_name} ({c.contest_id})</td><ResultCells totals={c.summary} /></tr>)}
            </tbody></table></div>
          {s.contests.map(c => <details key={c.contest_id}>
            <summary>Contest {c.contest_id} · entry evidence</summary>
            <ul>{c.entries.map(e => <li key={`${e.contest_id}:${e.entry_id}`}>
              Entry {e.entry_id}: fee {resultMoney(e.entry_fee)} · cash winnings {resultMoney(e.cash_winnings)} · source {e.financial_source.replaceAll("_", " ")}.
              {e.source_hashes.length > 0 && <details><summary>Source hashes</summary><ul>{e.source_hashes.map(h => <li key={h}>{h}</li>)}</ul></details>}
              {e.warnings.length > 0 && <ul>{e.warnings.map(w => <li key={w}>{w}</li>)}</ul>}
            </li>)}</ul>
          </details>)}
          {s.report_id && <p>Saved learning review {s.report_id} · {s.report_created_at}</p>}
          {s.missing_evidence.length > 0 && <details><summary>Saved learning warnings ({s.missing_evidence.length})</summary>
            <p>These warnings belong to the saved review. Financial totals above use current imported entry history.</p>
            <ul>{s.missing_evidence.map(w => <li key={w}>{w}</li>)}</ul>
          </details>}
        </details>)}
      </>}
      {report.warnings.length > 0 && <div role="alert"><strong>Week-wide evidence gaps</strong><ul>{report.warnings.map(w => <li key={w}>{w}</li>)}</ul></div>}
      <details><summary>Coverage and calculation limits</summary><ul>{report.limitations.map(w => <li key={w}>{w}</li>)}</ul></details>
    </>}
  </section>;
}
