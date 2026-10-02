import type { OptimizerProjectionRun } from "./api";

export function optimizerProjectionOverrideForRequest(
  runs: OptimizerProjectionRun[],
  override?: string,
): string | undefined {
  if (!runs.length) throw new Error("No completed projection is available for this slate.");
  if (override && !runs.some((run) => run.projection_run_id === override)) {
    throw new Error("The selected older projection is no longer available for this slate.");
  }
  return override;
}

export function optimizerProjectionRunIdForRequest(
  runs: OptimizerProjectionRun[],
  override?: string,
): string {
  return optimizerProjectionOverrideForRequest(runs, override) ?? runs[0].projection_run_id;
}
