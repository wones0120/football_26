import { useEffect, useState } from "react";
import { fetchLearningCandidates, type LearningCandidatePage, type SlateLearningReport } from "./api";

export function LearningCandidateDetails({ report }: { report: SlateLearningReport }) {
  const runs = report.optimizer_effectiveness?.runs ?? [];
  const policy = report.optimizer_effectiveness?.inclusion_policy;
  const [open, setOpen] = useState(false);
  const [runId, setRunId] = useState(String(runs[0]?.optimizer_run_id ?? ""));
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<LearningCandidatePage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setPage(null); setError("");
    if (!open || !runId) return;
    let cancelled = false;
    setBusy(true);
    void fetchLearningCandidates(report.report_id, runId, offset)
      .then(result => { if (!cancelled) setPage(result); })
      .catch(e => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [open, runId, offset, report.report_id]);
  return <>
    {policy && <p>{String(policy.included_run_count)} optimizer runs evaluated · {String(policy.excluded_run_count)} unrelated completed runs excluded. Entry-linked runs are retained.</p>}
    {runs.length > 0 && <details onToggle={event => setOpen(event.currentTarget.open)}>
      <summary>Inspect saved candidate details</summary>
      <label>Optimizer run <select value={runId} disabled={busy} onChange={event => { setRunId(event.target.value); setOffset(0); }}>
        {runs.map(run => <option key={String(run.optimizer_run_id)} value={String(run.optimizer_run_id)}>{String(run.strategy ?? "Optimizer")} · {String(run.optimizer_run_id)}</option>)}
      </select></label>
      <p>Frozen postgame evidence for this report. Pages contain up to 100 candidates.</p>
      {busy && <p role="status">Loading saved candidates…</p>}
      {error && <p role="alert">{error}</p>}
      {page && <>
        <p>{page.total ? `${page.offset + 1}–${page.offset + page.rows.length} of ${page.total}` : "No complete saved candidate pool for this run."}</p>
        <div className="scroll-table"><table className="compact-table"><thead><tr><th>Candidate ID</th><th>Saved lineup number</th><th>Selector rank</th><th>Projected mean</th><th>Actual points</th><th>Selected</th><th>Entered</th></tr></thead><tbody>
          {page.rows.map((row, index) => <tr key={String(row.pregame.candidate_id ?? index)}>
            <td>{String(row.pregame.candidate_id ?? "—")}</td>
            <td>{Array.isArray(row.pregame.saved_lineups) ? row.pregame.saved_lineups.map((saved: Record<string, unknown>) => String(saved.saved_lineup_number)).join(", ") || "—" : "—"}</td>
            <td>{String(row.pregame.selector_rank ?? "—")}</td><td>{typeof row.pregame.mean === "number" ? row.pregame.mean.toFixed(2) : "—"}</td>
            <td>{typeof row.postgame.actual_points === "number" ? row.postgame.actual_points.toFixed(2) : "Unscored"}</td><td>{row.postgame.selected ? "Yes" : "No"}</td><td>{row.postgame.entered ? "Yes" : "No"}</td>
          </tr>)}
        </tbody></table></div>
        <div className="button-row"><button disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Previous candidates</button>
          <button disabled={busy || page.next_offset == null} onClick={() => setOffset(page.next_offset ?? offset)}>Next candidates</button></div>
      </>}
    </details>}
  </>;
}
