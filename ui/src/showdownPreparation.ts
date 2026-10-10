import type { PreparedBuild, PreparationScope, PreparationStatus } from "./api";
import type { AvailabilityOverride } from "./optimizerProjectionScenario";

type RebuildRequest = PreparationScope & {
  action: "rebuild";
  availability_overrides: AvailabilityOverride[];
  assume_questionable_out: boolean;
};
type PreparationActions = {
  status: (scope: PreparationScope) => Promise<PreparationStatus>;
  reconcile: (scope: PreparationScope) => Promise<unknown>;
  queue: (request: RebuildRequest) => Promise<{ job: { job_id: string } }>;
  wait: (jobId: string) => Promise<unknown>;
  progress: (message: string) => void;
};

export function preparationBuildIssue(status: PreparationStatus | null, scope: PreparationScope): { status: "failed" | "preparing"; message: string } | null {
  if (!status || status.scope.season !== scope.season || status.scope.week !== scope.week ||
      status.scope.slate.toUpperCase() !== scope.slate.toUpperCase()) return null;
  // Jobs are newest first. A later successful rebuild clears the earlier failure.
  const latest = status.jobs.find(job => job.action === "rebuild" || job.action === "prepare");
  if (latest?.status === "failed") return { status: "failed",
    message: `Input preparation failed: ${latest.error || latest.message || "Review the source checks and prepare the slate again."}` };
  if (latest?.status === "queued" || latest?.status === "running") return { status: "preparing",
    message: "Features and projections are being prepared. Readiness will be rechecked when the build completes." };
  return null;
}

function requirePregame(status: PreparationStatus, scope: PreparationScope, label: string) {
  if (status.scope.season !== scope.season || status.scope.week !== scope.week ||
      status.scope.slate.toLowerCase() !== scope.slate.toLowerCase()) {
    throw new Error("Preparation status belongs to another slate. Optimization was not started.");
  }
  if (status.prelock === false) {
    throw new Error(`Pregame preparation is locked at ${status.lock_at}; use the existing late-swap workflow for locked entries.`);
  }
  if (status.prelock !== true) {
    throw new Error(`${label} preparation needs verified game identity and kickoff: ${status.limitations.join(" ") || "Review the native salary and canonical schedule evidence."}`);
  }
}

// Each user click builds from the selected explicit scenario. A latest completed
// projection, including an older assumed-out scenario, is never a substitute.
export async function prepareSlateForOptimizer(
  scope: PreparationScope,
  availabilityOverrides: AvailabilityOverride[],
  actions: PreparationActions,
  options: { label: string; assumeQuestionableOut: boolean },
): Promise<PreparedBuild> {
  const { label, assumeQuestionableOut } = options;
  const target = { ...scope };
  const overrides = structuredClone(availabilityOverrides);
  actions.progress(`Checking ${label} game identity and lock...`);
  let status = await actions.status(target);
  if (status.prelock === false) requirePregame(status, target, label);
  const active = status.jobs.filter(job => job.status === "queued" || job.status === "running");
  for (const job of active) {
    actions.progress(`Waiting for slate preparation ${job.action} (${job.job_id})...`);
    await actions.wait(job.job_id);
  }
  if (active.length) {
    status = await actions.status(target);
    if (status.jobs.some(job => job.status === "queued" || job.status === "running")) {
      throw new Error("Another slate preparation action started. Wait for it before running the optimizer.");
    }
  }
  requirePregame(status, target, label);
  actions.progress("Resolving salary identities; unmatched players remain excluded for review...");
  await actions.reconcile(target);
  actions.progress(`Rebuilding ${label} features and projections from current evidence...`);
  const queued = await actions.queue({ ...target, action: "rebuild",
    availability_overrides: overrides, assume_questionable_out: assumeQuestionableOut });
  actions.progress(`Preparing ${label} inputs (${queued.job.job_id}); optimizer starts after verification...`);
  await actions.wait(queued.job.job_id);
  status = await actions.status(target);
  requirePregame(status, target, label);
  const build = status.latest_build;
  if (!status.build_current || !build || build.prepared_input_job_id !== queued.job.job_id ||
      status.jobs.some(job => job.status === "queued" || job.status === "running")) {
    throw new Error(`${label} preparation was superseded or source inputs changed. Optimization was not started; review preparation status.`);
  }
  if (!build.projection_run_id || !build.feature_run_id || !build.source_sha256) {
    throw new Error("Prepared dependency lineage is incomplete. Optimization was not started.");
  }
  return build;
}

// Keep Showdown's scenario semantics unchanged: Q exclusion is a selection
// preference; only explicit availability assumptions change projections.
export function prepareShowdownForOptimizer(
  scope: PreparationScope,
  availabilityOverrides: AvailabilityOverride[],
  actions: PreparationActions,
): Promise<PreparedBuild> {
  return prepareSlateForOptimizer(scope, availabilityOverrides, actions,
    { label: "Showdown", assumeQuestionableOut: false });
}
