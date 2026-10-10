export const PORTFOLIO_TRACE_STORAGE_KEY = "football-26-last-portfolio-submission-trace";
export const PORTFOLIO_TRACE_EVENT = "football-26-portfolio-submission-trace";
export type PortfolioSubmissionTrace = Record<string, unknown>;
const fields = ["num_lineups", "max_exposure", "max_lineups_per_primary_game", "max_lineup_overlap", "elevated_player_max_exposure", "max_elevated_players_per_lineup"];

export function recordPortfolioTrace(trace: PortfolioSubmissionTrace) {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(PORTFOLIO_TRACE_STORAGE_KEY, JSON.stringify(trace)); } catch { /* Diagnostics never change submission behavior. */ }
  window.dispatchEvent(new CustomEvent(PORTFOLIO_TRACE_EVENT, { detail: trace }));
}

export function captureVisiblePortfolio(root: HTMLElement, parentOverlap: number | null, summary: Record<string, number | null>, longShot: boolean) {
  const visible: Record<string, number | null> = {};
  for (const key of fields) {
    const select = root.querySelector<HTMLSelectElement>(`select[data-portfolio-field="${key}"]`);
    const input = root.querySelector<HTMLInputElement>(`input[data-portfolio-field="${key}"]`);
    const raw = select?.value ?? input?.value;
    if (raw === undefined) throw new Error(`Portfolio control missing: ${key}. Submission blocked.`);
    const value = raw === "default" ? null : raw === "custom" ? input?.valueAsNumber ?? NaN : raw === "" ? NaN : Number(raw);
    visible[key] = value === null ? null : ["max_exposure", "elevated_player_max_exposure"].includes(key) ? value / 100 : value;
  }
  if (longShot) visible.num_lineups = 1;
  const overlap = root.querySelector<HTMLSelectElement>('select[data-portfolio-field="max_lineup_overlap"]')!;
  const controlled = overlap.dataset.controlledValue;
  const trace: PortfolioSubmissionTrace = {
    trace_version: "large_gpp_submit_v1", captured_at: new Date().toISOString(), origin: window.location.origin,
    rendered_dropdown_raw: overlap.value, rendered_dropdown_value: visible.max_lineup_overlap,
    local_component_state_value: controlled === "default" ? null : Number(controlled),
    local_component_custom_mode: overlap.dataset.customMode === "true",
    parent_form_state_value: parentOverlap, summary_value: summary.max_lineup_overlap,
    submit_handler_value: summary.max_lineup_overlap, request_builder_input_value: parentOverlap,
    serialized_request_object_value: summary.max_lineup_overlap, visible_controls: visible,
    summary_controls: { ...summary },
  };
  recordPortfolioTrace(trace);
  if (trace.local_component_state_value !== parentOverlap || visible.max_lineup_overlap !== parentOverlap) {
    throw new Error(`Portfolio dropdown/state mismatch: dropdown shows ${String(visible.max_lineup_overlap)}, controlled React value ${String(trace.local_component_state_value)}, parent value ${String(parentOverlap)}. Submission blocked; reselect the control and check Portfolio settings to submit.`);
  }
  for (const key of fields) {
    if (visible[key] !== (summary[key] ?? null)) {
      throw new Error(`Portfolio control/summary mismatch: ${key} shows ${String(visible[key])}, summary/request contains ${String(summary[key] ?? null)}. Submission blocked.`);
    }
  }
  return trace;
}
