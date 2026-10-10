import { useEffect, useRef, useState } from "react";
import { compareShowdownSelection, confirmShowdownSelectionExecution, downloadShowdownSelectionArtifact,
  evaluateShowdownSelection, fetchShowdownSelectionReview, recordShowdownSelection } from "./api";
import { candidateIds, parseRecommendation, type CoverageRow, type DecisionInput, type PairComparison,
  type PairDiagnostic, type ReviewCandidate, type ReviewResponse, type SelectionDecision } from "./showdownSelectionContracts";
import "./ShowdownSelectionReview.css";

const num = (n: number | null | undefined, digits = 2) => n == null ? "UNAVAILABLE" : n.toFixed(digits);
const fraction = (n: number) => `${(n * 100).toFixed(2)}%`;

function PairDetails({ pair }: { pair: PairDiagnostic }) {
  return <div className="selection-pair">
    <p><strong>{pair.overlap_message}</strong></p>
    <p>Shared: {pair.shared_player_names.join(", ") || "None"}. Unique physical players: {pair.unique_players_across_pair}.
      {" "}Shared FLEX slots: {pair.shared_flex_player_count}. {pair.same_captain ? "Same Captain" : "Different Captains"}.</p>
    <p>Different Captain labels do not establish independent football exposure.</p>
    <p>Scenario overlap: {pair.scenario_overlap.join(", ") || "None"}.</p>
    <div className="saved-contest-scroll"><table>
      <thead><tr><th>Entry</th><th>Captain / script</th><th>Split / QB</th><th>Mean / P90 proxy</th><th>Normalized mean / ceiling</th><th>Salary / ownership</th></tr></thead>
      <tbody>{pair.candidate_ids.map((id, i) => <tr key={id}><td><small>{id}</small></td>
        <td>{pair.captains[i].captain_player_name} ({pair.captains[i].captain_position}, {pair.captains[i].captain_team})<br />{pair.primary_scripts[i]}</td>
        <td>{pair.team_splits[i]}<br />{pair.qb_structures[i]}</td>
        <td>{num(pair.means[i])} / {num(pair.p90_proxies[i])}</td><td>{fraction(pair.mean_fractions[i])} / {fraction(pair.ceiling_fractions[i])}</td>
        <td>{pair.salary_used[i] == null ? "UNAVAILABLE" : `$${pair.salary_used[i]!.toLocaleString()}`}<br />Ownership {pair.ownership_availability[i] === "AVAILABLE" ? `${num(pair.projected_total_ownership[i])}% sum` : "UNAVAILABLE"}</td></tr>)}</tbody>
    </table></div>
    <p>Market: {pair.market_compatibilities.join(" / ")}. Risk flags: {pair.risk_flags.map(r => r.join(", ") || "None").join(" / ")}.</p>
    <p>Shared-core projected FLEX ownership: {pair.shared_core_projected_flex_ownership.map(n => num(n)).join(" / ")}.</p>
  </div>;
}

export function ShowdownSelectionReview({ runId }: { runId: string }) {
  const [value, setValue] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [ids, setIds] = useState<[string, string]>(["", ""]);
  const [considered, setConsidered] = useState<string[]>([]);
  const [displayed, setDisplayed] = useState<string[]>([]);
  const [alternativeIds, setAlternativeIds] = useState("");
  const [rejections, setRejections] = useState("[]");
  const [reasoning, setReasoning] = useState("");
  const [theses, setTheses] = useState<[string, string]>(["", ""]);
  const [complementarity, setComplementarity] = useState("");
  const [exception, setException] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [model, setModel] = useState("");
  const [reviewerType, setReviewerType] = useState("HUMAN");
  const [recommendation, setRecommendation] = useState("");
  const [comparison, setComparison] = useState<PairComparison | null>(null);
  const [inspected, setInspected] = useState<ReviewCandidate | null>(null);
  const [approved, setApproved] = useState(false);
  const [reportId, setReportId] = useState("");
  const [entries, setEntries] = useState<[string, string, string, string]>(["", "", "", ""]);
  const saveRetry = useRef<{ signature: string; key: string } | null>(null);
  const executionRetry = useRef<{ signature: string; key: string } | null>(null);
  const comparisonSequence = useRef(0);
  useEffect(() => {
    let cancelled = false;
    void fetchShowdownSelectionReview(runId).then(v => {
      if (cancelled) return;
      if (v.review.run_identity.optimizer_run_id !== runId) throw new Error("Frozen review belongs to another run.");
      setValue(v);
      const latest = v.decision_history.at(-1);
      if (latest) {
        setIds(latest.proposed_candidate_ids as [string, string]); setConsidered(latest.attention.explicitly_considered_ids);
        setDisplayed(latest.attention.other_displayed_candidate_ids); setReasoning(latest.reasoning);
        setTheses(latest.football_theses as [string, string]); setComplementarity(latest.complementarity_reason);
        setException(latest.accepted_high_overlap_exception || ""); setComparison(latest);
        setRejections(JSON.stringify(latest.rejected_candidates)); setAlternativeIds(latest.alternative_candidate_ids_considered.join("\n"));
      }
    }).catch(e => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; comparisonSequence.current += 1; };
  }, [runId]);
  const review = value?.review;
  const latest = value?.decision_history.at(-1);
  const byId = new Map(review?.candidates.map(c => [c.candidate_id, c]) || []);
  const shortlist = new Set(review?.attention_shortlist.rows.map(r => r.candidate_id) || []);
  const action = async (work: () => Promise<void>) => {
    setBusy(true); setError(null); setFeedback("");
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  const choose = (index: number, id: string) => {
    const next = [...ids] as [string, string]; next[index] = id; setIds(next); setComparison(null); setApproved(false);
    comparisonSequence.current += 1;
  };
  const inspect = (c: ReviewCandidate) => {
    setInspected(c);
    if (!shortlist.has(c.candidate_id)) setDisplayed(old => [...new Set([...old, c.candidate_id])]);
  };
  const compare = () => action(async () => {
    const request = ++comparisonSequence.current;
    const result = await compareShowdownSelection(runId, value!.review_hash, ids);
    if (request === comparisonSequence.current) setComparison(result);
  });
  const importRecommendation = () => {
    try {
      const r = parseRecommendation(recommendation, new Set(byId.keys()));
      setIds(r.proposed_candidate_ids as [string, string]); setConsidered(r.explicitly_considered_ids);
      setReasoning(r.reasoning); setTheses(r.football_theses as [string, string]); setComplementarity(r.complementarity_reason);
      setException(r.accepted_high_overlap_exception || ""); setRejections(JSON.stringify(r.rejected_candidates || []));
      setAlternativeIds((r.alternative_candidate_ids_considered || []).join("\n")); setComparison(null); setApproved(false);
      setReviewerType("AI_ASSISTED"); setModel(old => old || "ChatGPT");
      comparisonSequence.current += 1; setError(null); setFeedback("Recommendation loaded for comparison. No decision has been saved.");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };
  const saved = (record: SelectionDecision) => {
    setValue(v => v ? { ...v, selection_status: record.status,
      decision_history: v.decision_history.some(d => d.decision_id === record.decision_id) ? v.decision_history : [...v.decision_history, record] } : v);
    setFeedback(`Saved immutable revision ${record.revision}: ${record.status}.`); saveRetry.current = null; setApproved(false);
  };
  const save = (status: DecisionInput["status"]) => action(async () => {
    const base = { previous_decision_id: latest?.decision_id || null, review_hash: value!.review_hash, status,
      proposed_candidate_ids: ids, explicitly_considered_ids: considered, other_displayed_candidate_ids: displayed,
      alternative_candidate_ids_considered: candidateIds(alternativeIds), rejected_candidates: JSON.parse(rejections),
      reasoning, football_theses: theses, complementarity_reason: complementarity, accepted_high_overlap_exception: exception || null,
      reviewer_type: reviewerType, reviewer_identity: reviewer || null, model_name: model || null };
    const signature = JSON.stringify(base);
    if (saveRetry.current?.signature !== signature) saveRetry.current = { signature, key: crypto.randomUUID() };
    saved(await recordShowdownSelection(runId, { ...base, idempotency_key: saveRetry.current!.key }));
  });
  const candidateTable = (rows: { candidate_id: string; attention_group: string }[]) => <div className="saved-contest-scroll"><table>
    <thead><tr><th>Candidate / group</th><th>Captain / construction</th><th>Mean / P90 proxy</th><th>Quality mean / ceiling</th><th>Salary left / ownership</th><th>Review</th></tr></thead>
    <tbody>{rows.map(row => { const c = byId.get(row.candidate_id)!; const x = c.construction;
      return <tr key={row.candidate_id} data-candidate-id={row.candidate_id}>
        <td>Rank {c.metrics.selector_rank}<br /><small>{c.candidate_id}</small><br /><small>{row.attention_group}</small></td>
        <td>{x.captain_player_name} ({x.captain_team} {x.captain_position})<br />{x.team_split} · {x.qb_structure}<br />{x.primary_football_scenario}<br />Market {c.market_compatibility}</td>
        <td>{num(c.metrics.projected_mean)} / {num(c.metrics.summed_marginal_p90_proxy)}</td>
        <td>{fraction(c.quality_eligibility.mean_fraction)} / {fraction(c.quality_eligibility.ceiling_fraction)}</td>
        <td>{x.salary_remaining == null ? "UNAVAILABLE" : `$${x.salary_remaining.toLocaleString()}`}<br />Ownership {c.ownership_availability === "AVAILABLE" ? num(c.metrics.projected_total_ownership) : "UNAVAILABLE"}</td>
        <td><button type="button" onClick={() => inspect(c)}>Inspect rank {c.metrics.selector_rank}</button>
          <label><input type="checkbox" checked={considered.includes(c.candidate_id)} onChange={e => setConsidered(old => e.target.checked ? [...new Set([...old, c.candidate_id])] : old.filter(id => id !== c.candidate_id))} />Explicitly considered</label>
          <button type="button" onClick={() => choose(0, c.candidate_id)}>Propose entry 1</button><button type="button" onClick={() => choose(1, c.candidate_id)}>Propose entry 2</button></td>
      </tr>; })}</tbody>
  </table></div>;
  if (!value || !review) return <section aria-label="AI Candidate Review"><h3>AI Candidate Review</h3><p role={error ? "alert" : "status"}>{error || "Loading frozen review…"}</p></section>;
  const stalePair = latest?.proposed_candidate_ids.join() !== ids.join();
  return <section className="showdown-selection-review status-card" aria-label="AI Candidate Review">
    <h3>AI Candidate Review</h3>
    <p>Research only · nonbinding · {review.run_identity.game_id}<br />Frozen run <strong>{runId}</strong> · cutoff {review.run_identity.evidence_cutoff}</p>
    <p>{review.counts.quality_eligible} quality-eligible candidates · {review.counts.finalists} deterministic finalists · {review.counts.ceiling_outsiders} ceiling outsiders.</p>
    <p>The shortlist is a review aid. The complete eligible universe remains available. Rendering a candidate does not mark it considered.</p>
    {!value.can_record_prelock && <p><strong>Historical display / replay or incomplete evidence. New prelock selections are unavailable.</strong> Historical AI selection: {value.selection_status}.</p>}
    <button type="button" disabled={busy} onClick={() => void action(() => downloadShowdownSelectionArtifact(runId))}>Export compact review JSON</button>
    <button type="button" disabled={busy} onClick={() => void action(() => downloadShowdownSelectionArtifact(runId, true))}>Download decision history</button>
    {error && <p role="alert">{error}</p>}{feedback && <p role="status">{feedback}</p>}
    <details open><summary>Attention shortlist: finalists and ceiling outsiders</summary>{candidateTable(review.attention_shortlist.rows)}</details>
    <details onToggle={e => { if (e.currentTarget.open) setDisplayed(old => [...new Set([...old, ...review.candidates.filter(c => !shortlist.has(c.candidate_id)).map(c => c.candidate_id)])]); }}>
      <summary>Complete eligible universe ({review.candidates.length})</summary>
      {candidateTable(review.candidates.map(c => ({ candidate_id: c.candidate_id, attention_group: shortlist.has(c.candidate_id) ? "SHORTLIST" : "COMPLETE_UNIVERSE" })))}
    </details>
    {inspected && <details open><summary>Candidate detail: rank {inspected.metrics.selector_rank} · {inspected.candidate_id}</summary>
      <p>{inspected.players.map(p => `${p.slot} ${p.name} (${p.team} ${p.position}; ${p.player_id})`).join(" · ")}</p>
      <p>Projection rank {inspected.metrics.projection_rank} · ceiling rank {inspected.metrics.ceiling_proxy_rank} · primary thesis {inspected.construction.primary_thesis_signature}.</p>
      <p>Scenarios: {inspected.construction.scenario_tags.join(", ")}. Risks: {inspected.construction.risk_flags.join(", ") || "None"}.</p>
      <p>Market reasons: {inspected.market_compatibility_reason_codes.join(", ")}. Ownership: {inspected.ownership_availability}.</p>
    </details>}
    <details><summary>Captain / Script Coverage</summary>
      <p>Counts use the complete eligible universe. Absence from a saved pool does not establish a defect or infeasibility.</p>
      {Object.entries(review.coverage).map(([dimension, rows]) => Array.isArray(rows) ? <details key={dimension}><summary>{dimension.replaceAll("_", " ")}</summary>
        <div className="saved-contest-scroll"><table><thead><tr><th>Construction</th><th>Generated</th><th>Eligible</th><th>Finalists</th><th>Stage / strongest ceiling outsider</th></tr></thead>
          <tbody>{(rows as CoverageRow[]).map(r => <tr key={r.family}><td>{r.label}</td><td>{r.generated}</td><td>{r.quality_eligible}</td><td>{r.finalists}</td><td>{r.absence_stage}
            {r.highest_ceiling_nonfinalist_id && <><br /><button type="button" onClick={() => inspect(byId.get(r.highest_ceiling_nonfinalist_id!)!)}>{r.highest_ceiling_nonfinalist_id}</button> ({fraction(r.highest_ceiling_nonfinalist_fraction!)})</>}</td></tr>)}</tbody></table></div>
      </details> : <p key={dimension}>Ownership evidence: {Object.entries(rows).map(([k, n]) => `${k}: ${n}`).join(" · ")}</p>)}
    </details>
    <h4>Two-Lineup Comparison</h4>
    <div className="selection-input-grid">{ids.map((id, i) => <label key={i}>Exact candidate ID for entry {i + 1}
      <input type="text" aria-label={`Exact candidate ID for entry ${i + 1}`} value={id} onChange={e => choose(i, e.target.value.trim())} />
      <small>{byId.get(id)?.construction.captain_player_name || "Choose or paste an exact ID from this run"}</small>
    </label>)}</div>
    <button type="button" disabled={busy || !ids.every(id => byId.has(id)) || ids[0] === ids[1]} onClick={() => void compare()}>Compare proposed pair</button>
    {comparison && <><PairDetails pair={comparison.proposed_pair} />
      <details open><summary>Alternative Portfolio</summary>
        <p>{comparison.alternative_portfolio.ordering}. Informational alternatives; no overlap cap or penalty is imposed.</p>
        {comparison.alternative_portfolio.status === "NOT_NEEDED" && <p>The proposed pair shares fewer than five physical players.</p>}
        {comparison.alternative_portfolio.status === "NO_ELIGIBLE_LOWER_OVERLAP_PAIR" && <p>No quality-eligible pair with four or fewer shared physical players exists.</p>}
        {comparison.alternative_portfolio.alternatives.map((pair, index) => <details key={pair.candidate_ids.join()} open={index === 0}><summary>Alternative {index + 1}: {pair.shared_player_count}/6 shared</summary>
          <PairDetails pair={pair} /><p>Quality opportunity cost (current − alternative):</p>
          <ul>{Object.entries(pair.quality_opportunity_cost || {}).map(([key, cost]) => <li key={key}>{key}: {fraction(cost.current)} → {fraction(cost.alternative)} ({(cost.current_minus_alternative * 100).toFixed(2)} percentage points)</li>)}</ul>
          <p>Removed: {pair.player_substitutions?.removed.map(p => p.name).join(", ") || "None"}. Added: {pair.player_substitutions?.added.map(p => p.name).join(", ") || "None"}.</p>
          {pair.candidate_ids.map(cid => <button type="button" key={cid} onClick={() => inspect(byId.get(cid)!)}>Inspect {cid}</button>)}
        </details>)}
      </details></>}
    <details><summary>Import ChatGPT recommendation</summary>
      <p>Share the AI Selection Packet and compact review JSON. Request exactly two exact IDs, written theses/reasoning, explicitly considered IDs and rejections. Importing fills the form; saving is a separate action.</p>
      <pre>{JSON.stringify({ proposed_candidate_ids: ["exact ID 1", "exact ID 2"], explicitly_considered_ids: ["exact ID 1", "exact ID 2", "other IDs actually considered"], reasoning: "Why these entries", football_theses: ["Entry 1 thesis", "Entry 2 thesis"], complementarity_reason: "Portfolio fit", accepted_high_overlap_exception: "Reason if 5+ shared", alternative_candidate_ids_considered: [], rejected_candidates: [{ candidate_id: "exact ID", reason: "Written reason" }] }, null, 2)}</pre>
      <label>Recommendation JSON<textarea value={recommendation} onChange={e => setRecommendation(e.target.value)} rows={7} /></label>
      <button type="button" onClick={importRecommendation}>Load recommendation into review</button>
    </details>
    <details open><summary>Decision Record</summary>
      <p>Saved status: {value.selection_status}. {considered.length} explicitly considered; {displayed.length} other candidates displayed.</p>
      <div className="selection-input-grid">
        <label>Review reasoning<textarea value={reasoning} onChange={e => setReasoning(e.target.value)} /></label>
        {theses.map((t, i) => <label key={i}>Football thesis for entry {i + 1}<textarea value={t} onChange={e => { const next = [...theses] as [string, string]; next[i] = e.target.value; setTheses(next); }} /></label>)}
        <label>Why the football theses are complementary<textarea value={complementarity} onChange={e => setComplementarity(e.target.value)} /></label>
        <label>Accepted high-overlap exception<textarea value={exception} onChange={e => setException(e.target.value)} placeholder="Record deliberate acceptance when sharing 5+ players" /></label>
        <label>Alternative IDs explicitly considered<textarea value={alternativeIds} onChange={e => setAlternativeIds(e.target.value)} /></label>
        <label>Explicit rejections JSON<textarea value={rejections} onChange={e => setRejections(e.target.value)} /></label>
        <label>Reviewer type<select aria-label="Reviewer type" value={reviewerType} onChange={e => setReviewerType(e.target.value)}><option>AI_ASSISTED</option><option>HUMAN</option><option>AI</option></select></label>
        <label>Reviewer identity (self reported)<input type="text" value={reviewer} onChange={e => setReviewer(e.target.value)} /></label>
        <label>Model name, when available<input type="text" value={model} onChange={e => setModel(e.target.value)} /></label>
      </div>
      <button type="button" disabled={busy || !value.can_record_prelock || !comparison} onClick={() => void save("PROPOSED")}>Record PROPOSED</button>
      <button type="button" disabled={busy || !value.can_record_prelock || !comparison} onClick={() => void save("SELECTED")}>Record SELECTED</button>
      <label><input type="checkbox" checked={approved} onChange={e => setApproved(e.target.checked)} />I approve exactly this proposed pair</label>
      <button type="button" disabled={busy || !value.can_record_prelock || !comparison || !approved || stalePair || latest?.status !== "SELECTED"} onClick={() => void save("USER_APPROVED")}>Record USER_APPROVED</button>
      {value.decision_history.map(d => <details key={d.decision_id}><summary>Revision {d.revision}: {d.status} · {d.decision_timestamp}</summary>
        <p>{d.reasoning}</p><p>Record hash: {d.record_hash}</p><p>Prior revision: {d.previous_decision_id || "None"}</p>
        {d.execution && <p>Actual entries: {d.execution.entries.map(e => `${e.contest_id}/${e.entry_id}`).join(", ")} · matches approved pair: {String(d.execution.matches_approved_pair)}</p>}
      </details>)}
    </details>
    <details><summary>Confirm actual entries / join postgame learning</summary>
      <p>After the game, import the actual DraftKings results and generate a slate learning report in Learning. Exporting a lineup never confirms submission. Provide the report ID and two actual contest/entry IDs below.</p>
      <label>Learning report ID<input type="text" value={reportId} onChange={e => setReportId(e.target.value.trim())} /></label>
      <div className="selection-input-grid">{entries.map((entry, i) => <label key={i}>Entry {Math.floor(i / 2) + 1} {i % 2 === 0 ? "contest ID" : "entry ID"}<input type="text" value={entry} onChange={e => { const next = [...entries] as typeof entries; next[i] = e.target.value.trim(); setEntries(next); }} /></label>)}</div>
      <button type="button" disabled={busy || value.can_record_prelock || !reportId || !entries.every(Boolean) || !latest || !["USER_APPROVED", "ENTERED_CONFIRMED"].includes(latest.status)} onClick={() => void action(async () => {
        const request = { previous_decision_id: latest!.decision_id, learning_report_id: reportId,
          entries: [{ contest_id: entries[0], entry_id: entries[1] }, { contest_id: entries[2], entry_id: entries[3] }] };
        const signature = JSON.stringify(request);
        if (executionRetry.current?.signature !== signature) executionRetry.current = { signature, key: crypto.randomUUID() };
        saved(await confirmShowdownSelectionExecution(runId, { ...request, idempotency_key: executionRetry.current!.key }));
        executionRetry.current = null;
      })}>Confirm ENTERED_CONFIRMED from imported evidence</button>
      <button type="button" disabled={busy || value.can_record_prelock || !reportId || !latest || latest.status === "PROPOSED"} onClick={() => void action(async () => {
        await evaluateShowdownSelection(latest!.decision_id, reportId); setFeedback("Saved separate postgame research evaluation. View prospective tracking in Research Lab.");
      })}>Join frozen decision to outcomes</button>
    </details>
    <p className="hint">{review.limitations.join(" ")}</p>
  </section>;
}
