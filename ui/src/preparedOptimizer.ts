import {scenarioKey as opportunityScenarioKey,type ScenarioMode} from "./scenarioMode.ts";
import type { PreparationScope, PreparationStatus } from "./api";

export function optimizerWaitingStatus(status: PreparationStatus | null, scope: PreparationScope,
  prepared: boolean, pending: string | null, checkError: string | null, scenarioError: string | null) {
  if (pending) return { busy: true, message: pending };
  if (scenarioError) return { busy: false, message: scenarioError };
  if (checkError) return { busy: false, message: `Unable to check slate readiness: ${checkError}. Retrying automatically; you can also select Refresh Status.` };
  if (!status || status.scope.season !== scope.season || status.scope.week !== scope.week
    || status.scope.slate.toUpperCase() !== scope.slate.toUpperCase()) {
    return { busy: true, message: "Checking saved slate readiness… This can take 1–2 minutes. Run Optimizer will become available when the check confirms the prepared inputs are ready." };
  }
  const job = status.jobs.find(j => j.status === "running" || j.status === "queued");
  if (job) return { busy: true, message: `Preparing slate… ${job.message || (job.status === "queued" ? "Waiting for a worker." : job.stage)}` };
  if (prepared) return { busy: false, message: "Ready to optimize — prepared inputs verified." };
  if (status.prelock === false) return { busy: false, message: "This slate has locked. Live optimization is unavailable." };
  return { busy: false, message: status.build_issue || "Preparation required. Select Prepare slate for optimization above; changed availability or scenario assumptions, or a lower salary minimum, also require preparation again." };
}

// Compare semantic scenario fields, ignoring JSON key order and server null defaults.
function scenarioKey(rows: unknown[]) {
  return JSON.stringify(rows.map(value => {
    const row = value as Record<string, unknown>;
    return [row.player_id || null, row.player_name || null, row.availability ?? "default"];
  }).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))));
}

export function optimizerHasPreparedInputs(status: PreparationStatus | null, scope: PreparationScope,
  format: "classic" | "showdown", overrides: unknown[] | null, minimumPlayerSalary: number | null = null, scenario?: ScenarioMode): boolean {
  const build = status?.latest_build;
  return Boolean(overrides && status?.build_current && status.prelock !== false
    && !status.jobs.some(j => j.status === "queued" || j.status === "running")
    && build?.action === "prepare" && build.data_readiness?.status === "READY"
    && build.contest_format === format && build.season === scope.season && build.week === scope.week
    && build.slate.toUpperCase() === scope.slate.toUpperCase()
    && scenarioKey(build.availability_overrides ?? []) === scenarioKey(overrides)
    && (format !== "showdown" || (minimumPlayerSalary ?? 0) >= (build.minimum_player_salary ?? 0))
    && opportunityScenarioKey(build.scenario_mode?.config) === opportunityScenarioKey(scenario)
    && !build.assume_questionable_out);
}
