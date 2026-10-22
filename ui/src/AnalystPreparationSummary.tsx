import { PersonalThoughtSummary } from "./PersonalThoughtSummary";
import { AnalystResearchSummary } from "./AnalystResearchSummary";
import type { AnalystHandoff, AnalystHandoffMode } from "./analystPreparation";
export function AnalystPreparationSummary({ handoff, mode, busy, onAutomatic }: { handoff: AnalystHandoff | null; mode: AnalystHandoffMode; busy: boolean; onAutomatic: () => void }) {
  return <div className="readiness-preflight" data-testid="analyst-preparation-handoff">
    <div><strong>Prepared Analyst handoff · {mode === "AUTO" ? "automatic" : mode === "BASELINE" ? "explicit baseline" : "explicit override"}</strong>
      {mode !== "AUTO" && <button type="button" disabled={busy} onClick={onAutomatic}>Use automatic checked Analyst on next preparation</button>}
      {handoff ? <><p>{handoff.packet_id ?? "No checked research packet"} · {handoff.status.replaceAll("_", " ")}</p>
        <p>Checked: {handoff.checked_at} · Research decision: {handoff.research_decision_at ?? "unavailable"}</p>
        <p>Available checked research: {handoff.active_features.join(", ") || "none"}</p>
        <p>{handoff.changes.length} recorded finding/input changes · {handoff.missing_checks.length} missing checks.</p>
        {handoff.changes.filter(change => change.kind !== "unknown").slice(0, 5).map((change, index) => <p key={index}>{change.kind.replaceAll("_", " ")}: {change.reason}</p>)}
        {handoff.changes.length + handoff.missing_checks.length > 0 && <details><summary>All changes and unknown checks</summary>
          {handoff.changes.map((change, index) => <p key={index}>{change.kind.replaceAll("_", " ")}: {change.reason}</p>)}
          {handoff.missing_checks.map((reason, index) => <p key={`missing-${index}`}>Unknown or unverified: {reason}</p>)}
        </details>}
        <PersonalThoughtSummary context={handoff.personal_context} />
        <AnalystResearchSummary value={handoff.research_coverage} />
        <p>Preparation checks compatibility and records changes. Experimental unknowns remain visible; entry clearance is separate.</p>
      </> : <p>Prepare slate to check the latest compatible Analyst research and carry it into optimization. No manual hash is required.</p>}
    </div>
  </div>;
}
