import { canOpenSavedOptimizerReport, sameOptimizerRunScope } from "./optimizerHistory";
import { useCallback, useEffect, useRef, useState } from "react";
import { downloadAiShowdownPacket, fetchAiShowdownChecklist, fetchOptimizerRuns, retryOptimizerJob, type OptimizerRunSummary } from "./api";
import { ShowdownPrelockChecklist } from "./ShowdownPrelockChecklist";
import { ShowdownSelectionReview } from "./ShowdownSelectionReview";
import type { ShowdownPrelockChecklist as Checklist } from "./showdownResearch";

type Props = {
  season: number; week: number; slate: string;
  contestFormat: "classic" | "showdown"; objective: "cash" | "gpp";
  selectedRunId?: string; loadedRunId?: string;
  onOpen: (run: OptimizerRunSummary, scrollToResults: boolean) => Promise<void>;
};

const timestamp = (value: string) => new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString();

export function RecentOptimizerRuns({ season, week, slate, contestFormat, objective, selectedRunId, loadedRunId, onOpen }: Props) {
  const [runs, setRuns] = useState<OptimizerRunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [aiRequestedEntries, setAiRequestedEntries] = useState(2);
  const [exportFeedback, setExportFeedback] = useState<{ runId: string; message: string; error: boolean } | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [checklist, setChecklist] = useState<{ runId: string; value: Checklist } | null>(null);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [selectionReviewRunId, setSelectionReviewRunId] = useState<string | null>(null);
  const reviewRequest = useRef(0);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    reviewRequest.current += 1;
    setRuns([]); setError(null); setLoading(true); setExportFeedback(null); setChecklist(null); setReviewing(null); setSelectionReviewRunId(null);
    const refresh = async () => {
      let delay = 15_000;
      try {
        const response = await fetchOptimizerRuns({ season, week, slate, contest_format: contestFormat });
        if (!cancelled) { setRuns(response.runs); setError(null); }
        if (response.runs.some((run) => ["queued", "running"].includes(run.status))) delay = 3000;
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        if (!cancelled) { setLoading(false); timer = window.setTimeout(refresh, delay); }
      }
    };
    void refresh();
    return () => { cancelled = true; reviewRequest.current += 1; if (timer !== undefined) window.clearTimeout(timer); };
  }, [season, week, slate, contestFormat, objective, refreshKey, selectedRunId, loadedRunId]);

  const open = useCallback(async (run: OptimizerRunSummary, scrollToResults = true) => {
    setOpening(run.optimizer_run_id); setError(null);
    try { await onOpen(run, scrollToResults); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setOpening(null); }
  }, [onOpen]);

  const exportPacket = async (runId: string, format: "md" | "json") => {
    setExporting(runId);
    setExportFeedback({ runId, message: "Preparing packet…", error: false });
    try {
      await downloadAiShowdownPacket(runId, format, runs.find(run => run.optimizer_run_id === runId)?.strategy === "captain_single_lineup_v1" ? 1 : aiRequestedEntries);
      setExportFeedback({ runId, message: "Download requested. Check your browser’s downloads.", error: false });
    } catch (reason) {
      setExportFeedback({ runId, message: `Export failed: ${reason instanceof Error ? reason.message : String(reason)}`, error: true });
    } finally {
      setExporting(null);
    }
  };

  const reviewChecklist = async (runId: string) => {
    const request = ++reviewRequest.current;
    setReviewing(runId); setChecklist(null); setError(null);
    try {
      const packet = await fetchAiShowdownChecklist(runId, runs.find(run => run.optimizer_run_id === runId)?.strategy === "captain_single_lineup_v1" ? 1 : aiRequestedEntries);
      if (request === reviewRequest.current) setChecklist({ runId, value: packet.prelock_review_checklist });
    } catch (reason) {
      if (request === reviewRequest.current) setError(reason instanceof Error ? reason.message : String(reason));
    } finally { if (request === reviewRequest.current) setReviewing(null); }
  };

  useEffect(() => {
    const selected = runs.find((run) => run.optimizer_run_id === selectedRunId
      && sameOptimizerRunScope(run, {season, week, slate, contest_format: contestFormat}));
    if (selected && canOpenSavedOptimizerReport(selected) && selectedRunId !== loadedRunId && !opening && !error) void open(selected, false);
  }, [runs, selectedRunId, loadedRunId, opening, error, open, contestFormat, season, week, slate]);

  return <div className="status-card">
    <h3>Recent optimizer runs</h3>
    <p>{season} Week {week} · {slate.replaceAll("_", " ")} · {contestFormat === "classic" ? "Classic" : "Captain / Showdown"}. Includes historical strategies. Reopen saved results without running the optimizer again.</p>
    <button type="button" onClick={() => setRefreshKey((key) => key + 1)}>Refresh recent runs</button>
    {contestFormat === "showdown" && runs.some(run => run.strategy === "showdown_gpp_portfolio_v3") && <details><summary>Historical AI portfolio review settings</summary><label>AI requested entries
      <select value={aiRequestedEntries} onChange={(event) => setAiRequestedEntries(Number(event.target.value))}>
        {[2, 3, 4, 5].map((count) => <option key={count} value={count}>{count}</option>)}
      </select>
    </label></details>}
    {error && <p role="alert">{error}</p>}
    {loading && <p>Loading recent runs…</p>}
    {!loading && !error && runs.length === 0 && <p>No saved or queued optimizer runs found for this scope.</p>}
    {runs.length > 0 && <div className="saved-contest-scroll"><table className="optimizer-history-table">
      <thead><tr><th>Run</th><th>Strategy</th><th>Status / lineups</th><th>Duration</th><th>Actions</th></tr></thead>
      <tbody>{runs.map((run) => {
        const end = run.completed_at ?? (run.status === "running" ? new Date().toISOString() : null);
        const seconds = run.started_at && end ? Math.round(Math.max(0, (Date.parse(end) - Date.parse(run.started_at)) / 1000)) : null;
        return <tr key={run.optimizer_run_id}>
          <td>{timestamp(run.created_at)}<br /><small title={run.optimizer_run_id}>{run.optimizer_run_id.slice(0, 8)}</small></td>
          <td>{run.strategy.replaceAll("_", " ")}{run.expanded_discovery && <><br /><small>Expanded discovery</small></>}</td>
          <td>{run.status}<br /><small>{canOpenSavedOptimizerReport(run) ? `${run.lineup_count} saved ${run.lineup_count === 1 ? "lineup" : "lineups"}` : `${run.requested_lineups ?? "Unknown"} requested`}</small>
            {run.status === "failed" ? <details><summary>Error details</summary><p>{run.message}</p></details>
              : run.status !== "completed" && <><br /><small>{run.message}</small></>}</td>
          <td>{seconds == null ? "Unavailable" : `${Math.floor(seconds / 60)}m ${seconds % 60}s${run.completed_at ? "" : " elapsed"}`}</td>
          <td>{canOpenSavedOptimizerReport(run) ? <button type="button" disabled={Boolean(opening)} onClick={() => void open(run)}>{opening === run.optimizer_run_id ? "Loading…" : loadedRunId === run.optimizer_run_id ? "Reopen results" : "Open results"}</button>
            : ["queued", "running"].includes(run.status) ? <button type="button" onClick={() => void open(run)} disabled={selectedRunId === run.optimizer_run_id}>{selectedRunId === run.optimizer_run_id ? "Watching run" : "Watch run"}</button>
              : null}
            {run.status === "completed" && run.saved_report_available && ["showdown_gpp_portfolio_v3", "captain_single_lineup_v1"].includes(run.strategy) && <>
              <button type="button" disabled={Boolean(exporting)} onClick={() => void exportPacket(run.optimizer_run_id, "md")}>Export AI Selection Packet</button>
              <button type="button" disabled={Boolean(exporting)} onClick={() => void exportPacket(run.optimizer_run_id, "json")}>Export packet JSON</button>
              <button type="button" disabled={Boolean(reviewing)} onClick={() => void reviewChecklist(run.optimizer_run_id)}>{reviewing === run.optimizer_run_id ? "Loading checklist…" : "Prelock review checklist"}</button>
              {run.strategy === "showdown_gpp_portfolio_v3" && <button type="button" onClick={() => { setAiRequestedEntries(2); setSelectionReviewRunId(run.optimizer_run_id); }}>Historical AI Candidate Review</button>}
              <small>Experimental manual review</small>
              {exportFeedback?.runId === run.optimizer_run_id && <p role={exportFeedback.error ? "alert" : "status"}>{exportFeedback.message}</p>}
            </>}
            {run.status === "failed" && run.operational_job_id && <button type="button" onClick={async () => {
                try { await retryOptimizerJob(run.operational_job_id!); await open({ ...run, status: "queued", saved_report_available: false }); setRefreshKey((key) => key + 1); }
                catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
              }}>Retry saved request</button>}</td>
        </tr>;
      })}</tbody>
    </table></div>}
    {checklist && <><p>Reviewing saved run {checklist.runId}</p><ShowdownPrelockChecklist checklist={checklist.value} /></>}
    {selectionReviewRunId && <ShowdownSelectionReview key={selectionReviewRunId} runId={selectionReviewRunId} />}
  </div>;
}
