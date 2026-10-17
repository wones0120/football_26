import { useState } from "react";
import { assessSavedOptimizerReadiness, type OptimizerResponse } from "./api";
import { largeGppReadinessHtml } from "./classicReadinessReport";

export function ClassicLargeGppReadinessReport({ optimizer, onAssessment }: {
  optimizer: OptimizerResponse; onAssessment: (value: Record<string, unknown>) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!["classic_large_gpp_v1", "classic_single_lineup_v1"].includes(optimizer.strategy)) return null;
  return <div className="status-card nested-card">
    <div dangerouslySetInnerHTML={{ __html: largeGppReadinessHtml(optimizer) }} />
    {optimizer.strategy === "classic_large_gpp_v1" && !optimizer.preliminary_report && <button type="button" disabled={busy || optimizer.status !== "completed"} onClick={async () => {
      setBusy(true); setError(null);
      try { onAssessment(await assessSavedOptimizerReadiness(optimizer.job_id)); }
      catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
      finally { setBusy(false); }
    }}>{busy ? "Validating saved inputs…" : "Validate saved inputs at current time"}</button>}
    {error && <p role="alert">{error} · Original saved report unchanged.</p>}
  </div>;
}
