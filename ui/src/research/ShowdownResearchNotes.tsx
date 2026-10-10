import { useEffect, useState } from "react";
import { fetchShowdownResearchNotes } from "../api";
import type { ShowdownResearchNotes as Notes } from "../showdownResearch";
import { ShowdownSelectionLearning } from "./ShowdownSelectionLearning";

export function ShowdownResearchNotes() {
  const [notes, setNotes] = useState<Notes | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void fetchShowdownResearchNotes().then(value => { if (!cancelled) setNotes(value); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { cancelled = true; };
  }, []);
  return <section className="panel wide-panel" id="showdown-research-notes" aria-label="Showdown research notes">
    <h2>Showdown research notes</h2>
    <ShowdownSelectionLearning />
    {error && <p role="alert">Research notes unavailable: {error}</p>}
    {!notes && !error && <p>Loading research notes…</p>}
    {notes && <>
      <h3>{notes.title}</h3>
      <p><strong>{notes.label}</strong></p>
      <p>{notes.purpose}</p>
      <p>{notes.sample_period} · {notes.sample.games} games · {notes.sample.contests} contests · {notes.sample.entries.toLocaleString()} entries · {notes.sample.unresolved_entries.toLocaleString()} unresolved.</p>
      <p className="hint">{notes.limitations}</p>
      {notes.findings.map(finding => <details key={finding.id}>
        <summary>{finding.title}</summary>
        <p><strong>{finding.label}</strong></p>
        <p>{finding.observation}</p>
        <p><strong>Sample period:</strong> {finding.sample_period}</p>
        <p><strong>Comparison baseline:</strong> {finding.comparison_baseline}</p>
        <p><strong>Limitations:</strong> {finding.limitations}</p>
      </details>)}
      <details><summary>Source and success definition</summary>
        <p>{notes.success_definition}</p>
        <p>Captured {notes.source.captured_at} · {notes.source.path}</p>
        <p style={{ overflowWrap: "anywhere" }}>SHA-256: {notes.source.sha256}</p>
      </details>
    </>}
  </section>;
}
