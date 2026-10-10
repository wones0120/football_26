import { useEffect, useState } from "react";
import { fetchClassicEnvironmentResearch } from "../api";
import type { ClassicEnvironmentResearch as Notes } from "../classicGameEnvironment";

export function ClassicEnvironmentResearch() {
  const [notes, setNotes] = useState<Notes | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void fetchClassicEnvironmentResearch().then(value => { if (!cancelled) setNotes(value); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { cancelled = true; };
  }, []);
  return <section className="panel wide-panel" id="classic-environment-research" aria-label="Classic game environment research">
    <h2>Classic game environment research</h2>
    {error && <p role="alert">Research notes unavailable: {error}</p>}
    {!notes && !error && <p>Loading research notes…</p>}
    {notes && <>
      <h3>{notes.title}</h3><p><strong>{notes.label}</strong></p>
      <p>{notes.verification} · {notes.sample_period} · {notes.sample.contests} contests · {notes.sample.independent_slates} independent slates · {notes.sample.top_10_entries.toLocaleString()} top-10% entries / {notes.sample.field_entries.toLocaleString()} classified field entries.</p>
      <p>{notes.success_definition}</p>
      <div style={{ overflowX: "auto" }}><table><thead><tr><th>Slate game-total tier</th><th>Top-10% offensive selections</th><th>Field</th></tr></thead><tbody>{notes.rows.map(r => <tr key={r.tier}><td>{r.tier}</td><td>{(100*r.top_10).toFixed(1)}%</td><td>{(100*r.field).toFixed(1)}%</td></tr>)}</tbody></table></div>
      <p><strong>Actual cash outcomes: {notes.cash_outcomes}.</strong> Historical shares are not recommended targets.</p>
      <details><summary>Historical observations by position</summary><ul>{notes.findings.map(x => <li key={x}>{x}</li>)}</ul></details>
      <details><summary>Controlled comparisons and evidence limits</summary><ul>{notes.controlled_comparisons.map(x => <li key={x}>{x}</li>)}</ul><ul>{notes.limitations.map(x => <li key={x}>{x}</li>)}</ul></details>
      <details><summary>Reproduction and source provenance</summary><p>{notes.source.path} · reproduced {notes.source.reproduced_at}</p><p style={{ overflowWrap: "anywhere" }}>SHA-256: {notes.source.sha256}</p></details>
    </>}
  </section>;
}
