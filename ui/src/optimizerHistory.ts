import type { OptimizerRunSummary } from "./api.ts";

type RunScope = Pick<OptimizerRunSummary, "season" | "week" | "slate" | "contest_format">;

export function sameOptimizerRunScope(run: RunScope, scope: RunScope): boolean {
  return run.season === scope.season && run.week === scope.week
    && run.contest_format === scope.contest_format && run.slate.toUpperCase() === scope.slate.toUpperCase();
}

export function canOpenSavedOptimizerReport(run: Pick<OptimizerRunSummary, "status" | "saved_report_available">): boolean {
  return run.status === "completed" || (run.status === "failed" && run.saved_report_available === true);
}

// Finished history is stable. Poll only while a solve can change its status.
export function optimizerHistoryPollDelay(runs: Pick<OptimizerRunSummary, "status">[]): number | null {
  return runs.some(run => ["queued", "running"].includes(run.status)) ? 5000 : null;
}
