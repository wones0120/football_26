import { useEffect, useState } from "react";
import { fetchShowdownSelectionResearch } from "../api";

export function ShowdownSelectionLearning() {
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof fetchShowdownSelectionResearch>> | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let cancelled = false;
    void fetchShowdownSelectionResearch().then(value => { if (!cancelled) { setSummary(value); setError(""); } })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [refresh]);
  return <details aria-label="Showdown prospective selection learning">
    <summary>Showdown prospective selection learning</summary>
    <p>Research only · showdown_ai_selection_review_v1 · legacy unrecorded picks: AI_SELECTION_UNKNOWN. Frozen decisions precede outcome joins.</p>
    <button type="button" onClick={() => setRefresh(n => n + 1)}>Refresh selection research</button>
    {error && <p role="alert">{error}</p>}
    {summary && <>
      <p>{summary.recorded_runs} recorded runs · {summary.valid_prelock_slates} valid prelock slates. {summary.limitations}</p>
      <div className="saved-contest-scroll"><table><thead><tr><th>Slate / status</th><th>Attention coverage</th><th>Overlap / outsider</th><th>Postgame evaluation</th></tr></thead>
        <tbody>{summary.runs.map(r => <tr key={r.decision_id}><td>{r.run_identity.season} W{r.run_identity.week} {r.run_identity.slate}<br />{r.status}<br /><small>{r.run_identity.optimizer_run_id}</small></td>
          <td>{r.tracking.explicitly_considered} / {r.tracking.quality_eligible} ({(100 * r.tracking.attention_coverage_fraction).toFixed(1)}%)</td>
          <td>Proposed {r.proposed_pair_overlap}/6 · alternative {r.alternative_pair_overlap ?? "UNAVAILABLE"}<br />Nonfinalist selected: {String(r.tracking.outsider_selected)} · ceiling outsider selected: {String(r.tracking.ceiling_outsider_selected)}</td>
          <td><details><summary>{r.outcome ? "Saved evaluation" : "UNAVAILABLE"}</summary><pre style={{ maxWidth: 500, whiteSpace: "pre-wrap" }}>{JSON.stringify(r.outcome, null, 2)}</pre></details></td></tr>)}</tbody>
      </table></div>
      <p>Overlap buckets: {Object.entries(summary.outcomes_by_overlap_bucket).map(([bucket, b]) => `${bucket}/6: ${b.slates} slates, ${b.evaluated_slates} evaluated, mean regret ${b.mean_regret == null ? "UNAVAILABLE" : b.mean_regret.toFixed(2)}`).join(" · ") || "No valid observations yet"}.</p>
    </>}
  </details>;
}
