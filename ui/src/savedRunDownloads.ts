import type { OptimizerRunSummary } from "./api.ts";
import { sameOptimizerRunScope } from "./optimizerHistory.ts";

type Scope = Pick<OptimizerRunSummary, "season" | "week" | "slate" | "contest_format">;
export type SavedDownloadMode = "recommended" | "all";

export function savedDownloadBlocker(run: OptimizerRunSummary, scope: Scope, mode: SavedDownloadMode): string | null {
  if (!sameOptimizerRunScope(run, scope)) return "This run belongs to a different slate. Refresh recent runs.";
  if (run.status !== "completed") return "DraftKings downloads require a completed saved run.";
  if (run.lineup_count < 1) return "This saved run has no lineups to download.";
  if ((run.preliminary_export_blocked || run.entry_ready === false) && !(run.upload_ready === true && Date.parse(run.upload_valid_until ?? "") > Date.now())) {
    return "This saved research run is not entry cleared. Use Check upload readiness for this saved run; final inactives remain a separate review.";
  }
  if (mode === "recommended" && (run.objective !== "gpp" || run.saved_recommendation_available !== true)) {
    return "This run has no saved GPP recommendation. Download All remains available if the run passes export validation.";
  }
  return null;
}

export async function downloadSavedRun(run: OptimizerRunSummary, scope: Scope, mode: SavedDownloadMode,
  download: (runId: string, recommendedOnly: boolean) => Promise<void>): Promise<void> {
  const blocker = savedDownloadBlocker(run, scope, mode);
  if (blocker) throw new Error(blocker);
  // Always use the clicked saved row, independently of the loaded results panel.
  await download(run.optimizer_run_id, mode === "recommended");
}
