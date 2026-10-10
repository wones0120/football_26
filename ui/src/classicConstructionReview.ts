const FAILURE_ACTIONS: Record<string, [string, string]> = {
  endpoint_unavailable: ["Construction review endpoint unavailable", "Reload the development API with the updated route, then retry this saved report."],
  saved_run_not_found: ["Saved run not found or inaccessible", "Reopen this saved run in the same backend and authorization context as the report."],
  frozen_inputs_missing: ["Frozen review inputs missing", "Check this run's saved eligible-player frame and portfolio artifacts. Current projections cannot replace them."],
  incompatible_contract: ["Incompatible saved contract", "Check the saved contract version and checksums before retrying."],
  invalid_entry: ["Invalid entry selection", "Select an existing entry, numbered from 1, and retry."],
  calculation_failure: ["Construction calculation failed", "Retry the diagnostic; if it fails again, inspect the backend log using the request ID."],
  backend_unreachable: ["Construction review backend unreachable", "Check that the report's backend is running, then retry."],
};

export class ConstructionReviewError extends Error {
  code: string;
  nextAction: string;
  technical: string;
  constructor(code: string, technical: string) {
    const [message, nextAction] = FAILURE_ACTIONS[code] ?? FAILURE_ACTIONS.calculation_failure;
    super(message);
    this.code = code;
    this.nextAction = nextAction;
    this.technical = technical;
  }
}

// Kept separate from generic API errors so route 404 and saved-resource 404
// remain distinguishable. Uses the same origin/authentication defaults as report GETs.
export async function requestConstructionReview(apiBase: string, jobId: string, entry: number,
  enforceSingleTE: boolean, fetcher: typeof fetch = fetch): Promise<Record<string, any>> {
  const url = `${apiBase}/optimizer/results/${encodeURIComponent(jobId)}/construction-review?entry=${entry}&enforce_single_te=${enforceSingleTE}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 600_000);
  let res: Response;
  try {
    res = await fetcher(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal: controller.signal });
  } catch {
    throw new ConstructionReviewError("backend_unreachable", `POST ${url}`);
  } finally {
    clearTimeout(timeout);
  }
  let payload: any;
  try { payload = await res.json(); } catch { payload = null; }
  const detail = payload?.detail;
  const requestId = res.headers.get("X-Construction-Review-Request-ID") ?? detail?.request_id ?? payload?.request_id;
  const technical = `POST ${url} · HTTP ${res.status}${requestId ? ` · request ID ${requestId}` : ""}`;
  if (!res.ok) {
    let code = typeof detail?.code === "string" ? detail.code : "calculation_failure";
    if (res.status === 404 && !detail?.code) code = detail === "Job not found" ? "saved_run_not_found" : "endpoint_unavailable";
    if (res.status === 422 && Array.isArray(detail) && detail.some(row => row.loc?.includes("entry"))) code = "invalid_entry";
    throw new ConstructionReviewError(code, technical);
  }
  if (payload?.status === "unavailable") throw new ConstructionReviewError(payload.code ?? "frozen_inputs_missing", technical);
  if (payload?.status !== "completed" || !Array.isArray(payload.comparisons) || !payload.comparisons.length) {
    throw new ConstructionReviewError("calculation_failure", `${technical} · unusable review response`);
  }
  return payload;
}
