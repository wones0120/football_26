import { useCallback, useEffect, useState } from "react";
import { fetchOptimizerRuns, retryOptimizerJob, type OptimizerRunSummary } from "./api";

type Props = {
  season: number; week: number; slate: string;
  contestFormat: "classic" | "showdown"; objective: "cash" | "gpp";
  selectedRunId?: string; loadedRunId?: string;
  onOpen: (run: OptimizerRunSummary) => Promise<void>;
};

const timestamp = (value: string) => new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString();

export function RecentOptimizerRuns({ season, week, slate, contestFormat, objective, selectedRunId, loadedRunId, onOpen }: Props) {
  const [runs, setRuns] = useState<OptimizerRunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    setRuns([]); setError(null); setLoading(true);
    const refresh = async () => {
      let delay = 15_000;
      try {
        const response = await fetchOptimizerRuns({ season, week, slate, contest_format: contestFormat, objective });
        if (!cancelled) { setRuns(response.runs); setError(null); }
        if (response.runs.some((run) => ["queued", "running"].includes(run.status))) delay = 3000;
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        if (!cancelled) { setLoading(false); timer = window.setTimeout(refresh, delay); }
      }
    };
    void refresh();
    return () => { cancelled = true; if (timer !== undefined) window.clearTimeout(timer); };
  }, [season, week, slate, contestFormat, objective, refreshKey, selectedRunId, loadedRunId]);

  const open = useCallback(async (run: OptimizerRunSummary) => {
    setOpening(run.optimizer_run_id); setError(null);
    try { await onOpen(run); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setOpening(null); }
  }, [onOpen]);

  useEffect(() => {
    const selected = runs.find((run) => run.optimizer_run_id === selectedRunId);
    if (selected?.status === "completed" && selectedRunId !== loadedRunId && !opening && !error) void open(selected);
  }, [runs, selectedRunId, loadedRunId, opening, error, open]);

  return <div className="status-card">
    <h3>Recent optimizer runs</h3>
    <p>{season} Week {week} · {slate.replaceAll("_", " ")} · {contestFormat === "classic" ? "Classic" : "Showdown"} · {objective.toUpperCase()}. Reopen saved results without running the optimizer again. Queued solves continue on the worker after a page refresh.</p>
    <button type="button" onClick={() => setRefreshKey((key) => key + 1)}>Refresh recent runs</button>
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
          <td>{run.status}<br /><small>{run.status === "completed" ? `${run.lineup_count} saved ${run.lineup_count === 1 ? "lineup" : "lineups"}` : `${run.requested_lineups ?? "Unknown"} requested`}</small>
            {run.status === "failed" ? <details><summary>Error details</summary><p>{run.message}</p></details>
              : run.status !== "completed" && <><br /><small>{run.message}</small></>}</td>
          <td>{seconds == null ? "Unavailable" : `${Math.floor(seconds / 60)}m ${seconds % 60}s${run.completed_at ? "" : " elapsed"}`}</td>
          <td>{run.status === "completed" ? <button type="button" disabled={Boolean(opening)} onClick={() => void open(run)}>{opening === run.optimizer_run_id ? "Loading…" : loadedRunId === run.optimizer_run_id ? "Reopen results" : "Open results"}</button>
            : ["queued", "running"].includes(run.status) ? <button type="button" onClick={() => void open(run)} disabled={selectedRunId === run.optimizer_run_id}>{selectedRunId === run.optimizer_run_id ? "Watching run" : "Watch run"}</button>
              : run.operational_job_id && <button type="button" onClick={async () => {
                try { await retryOptimizerJob(run.operational_job_id!); await open(run); setRefreshKey((key) => key + 1); }
                catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
              }}>Retry saved request</button>}</td>
        </tr>;
      })}</tbody>
    </table></div>}
  </div>;
}
