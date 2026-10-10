import { useState } from "react";
import { CONSTRUCTION_COLUMNS, constructionValue } from "./classicConstruction";
import { reviewClassicConstructions, type OptimizerResponse } from "./api";
import { ConstructionReviewError } from "./classicConstructionReview";
import { lowerConcentrationEvidenceHtml, downloadConstructionReview } from "./classicConstructionEvidence";

export function ClassicConstructionReport({ optimizer, enforceSingleTE }: { optimizer: OptimizerResponse; enforceSingleTE: boolean }) {
  // Keyed by job_id and the single-TE choice in App: a result can never migrate into a different pinned run.
  const [review, setReview] = useState<any>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ConstructionReviewError | null>(null);
  const [entry, setEntry] = useState(1);
  const summary = optimizer.construction_summary;
  if (optimizer.contest_format !== "classic") return null;
  const runReview = async () => {
    setPending(true); setError(null); setReview(null);
    try { setReview(await reviewClassicConstructions(optimizer.job_id, entry, enforceSingleTE)); }
    catch (e) { setError(e instanceof ConstructionReviewError ? e : new ConstructionReviewError("calculation_failure", "The diagnostic did not produce a usable response.")); }
    finally { setPending(false); }
  };
  const metric = (result: any) => result.status !== "feasible" ? `${result.status.replaceAll("_", " ")}: ${result.reason} · solver ${result.solver?.solver_status ?? "Not searched"}` :
    `Feasible · mean ${result.mean.toFixed(3)} · summed marginal P90 ${result.p90.toFixed(3)} · objective ${result.objective_score.toFixed(6)} · solver ${result.solver?.solver_status} (${result.solver?.solution_status})`;
  return <div className="status-card nested-card">
    <h3>Classic construction summary</h3>
    <p>Saved Enforce single TE: {optimizer.enforce_single_te == null ? "Unavailable" : optimizer.enforce_single_te ? "On · TE excluded from FLEX" : "Off · TE FLEX permitted, not required"}.</p>
    {!summary ? <p>Construction taxonomy unavailable for this saved response. Reopen the saved report with the updated backend.</p> : <>
      <p>{summary.definitions}</p>
      <div className="table-wrap"><table><thead><tr><th>Entry</th>{CONSTRUCTION_COLUMNS.map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead><tbody>{summary.lineups.map((row, i) => <tr key={i}><td>{i + 1}</td>{row.status === "available" ? CONSTRUCTION_COLUMNS.map(([key]) => <td key={key}>{constructionValue(row[key])}</td>) : <td colSpan={CONSTRUCTION_COLUMNS.length}>{String(row.reason)}</td>}</tr>)}</tbody></table></div>
      <details><summary>{optimizer.strategy === "classic_single_lineup_v1" ? "Lineup composition" : `Selected portfolio distributions (${summary.selected_count} entries)`}</summary><ul>{Object.entries(summary.distributions).map(([key, values]) => <li key={key}>{CONSTRUCTION_COLUMNS.find(([k]) => k === key)?.[1] ?? key}: {constructionValue(values) || "Unavailable"}</li>)}</ul></details>
      <p>{summary.coverage}</p><p>{summary.research_scope}</p>
    </>}
    <p>Team cap limits players from one team per lineup, including DST. Game cap limits players from one game per lineup, including DST. {optimizer.strategy !== "classic_single_lineup_v1" && "Primary-game cap limits QB-game appearances across the portfolio."}</p>
    {optimizer.strategy === "classic_large_gpp_v1" && optimizer.status === "completed" && <>
      <label>Entry to review <select disabled={pending} value={entry} onChange={e => { setEntry(Number(e.target.value)); setReview(null); setError(null); }}>{Array.from({ length: (optimizer.results as unknown[][])?.length ?? 0 }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}</select></label>
      <button disabled={pending} onClick={runReview}>{pending ? "Reviewing constructions…" : "Review construction tradeoffs"}</button>
      <p>Review Enforce single TE: {enforceSingleTE ? "On · TE FLEX excluded" : "Off · TE FLEX permitted"}. {enforceSingleTE !== optimizer.enforce_single_te && "This explicitly changes the saved construction setting for the review only."}</p>
      <p>Runs only when clicked, on this saved run's frozen input and scoring frame. Uses the existing single-TE checkbox's current choice; every other saved constraint remains pinned. Each alternative retains scoring rules and does not save a new portfolio.</p>
    </>}
    {error && <div role="alert"><p>{error.message}. Saved job: <code>{optimizer.job_id}</code>; entry {entry}.</p><p>{error.nextAction}</p><details><summary>Technical details</summary><p>{error.technical}</p></details></div>}
    {review && <>
      <p>{review.status === "unavailable" ? review.reason : review.interpretation}</p>
      {review.comparisons && <>
        <button onClick={() => downloadConstructionReview(review, "html")}>Download construction review evidence</button>
        <button onClick={() => downloadConstructionReview(review, "json")}>Download captured construction review JSON</button>
        <div dangerouslySetInnerHTML={{ __html: lowerConcentrationEvidenceHtml(review) }} />
        <p>Reviewed Enforce single TE: {review.review_enforce_single_te ? "On" : "Off"}; saved: {review.saved_enforce_single_te ? "On" : "Off"}. {Object.keys(review.changed_settings).length > 0 ? "Explicit changed construction setting: Enforce single TE only. All other saved settings retained." : "No saved settings changed."}</p>
        <p>{review.ceiling_label}. Pinned entry {review.entry}; template minimums {review.active_template_minimums.join(" / ")}. Baseline mean {review.baseline.mean.toFixed(3)}, summed marginal P90 {review.baseline.p90.toFixed(3)}, composite objective {review.baseline.objective_score.toFixed(6)}.</p>
        <p>Saved implementation matches current production: {review.implementation_matches_saved ? "Yes" : "No · current production builder on saved inputs; historical replay parity is unverified"}. {review.scoring_frame}</p>
        <div className="table-wrap"><table><thead><tr><th>Precise changed construction</th><th>Individually feasible</th><th>Replacement preserving other entries</th></tr></thead><tbody>{review.comparisons.map((row: any) => <tr key={row.family}><td>{row.family}</td>{[row.individual, row.replacement].map((r, i) => <td key={i}>{metric(r)}{r.status === "feasible" && <><p>{r.selection_treatment.replaceAll("_", " ")}. Δ mean {r.deltas_vs_saved_entry.mean.toFixed(3)} · Δ summed P90 {r.deltas_vs_saved_entry.p90.toFixed(3)} · Δ objective {r.deltas_vs_saved_entry.objective_score.toFixed(6)}.</p><details><summary>Roster, components and structural bonuses</summary><p>{r.roster.map((p: any) => `${p.position} ${p.name}`).join(" · ")}</p><p>{constructionValue(r.components)}</p><p>Component sum matches solver: {r.component_sum_matches_solver ? "Yes" : "No"}</p><pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify({ actual_construction: r.construction, structural_rules: r.correlation_rules, solver: r.solver }, null, 2)}</pre></details></>}</td>)}</tr>)}</tbody></table></div>
        <details><summary>Pinned inputs, active limits and full review</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 420, overflow: "auto" }}>{JSON.stringify(review, null, 2)}</pre></details>
      </>}
    </>}
  </div>;
}
