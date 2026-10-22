import { analystResearchEvidence } from "./analystResearchEvidence";

export function AnalystResearchSummary({ value, results = [] }: { value: unknown; results?: unknown }) {
  const summary = analystResearchEvidence(value, results);
  return <section aria-label="Authored football research" style={{ overflowWrap: "anywhere" }}>
    <h4>Authored football research</h4>
    {summary.lines.map((line, i) => <p key={i}>{line}</p>)}
    {summary.games.map(game => <div key={game.game}>
      <strong>{game.game} · {game.disposition || game.state || "unrecorded"}</strong>
      {game.details.map((line, i) => <p key={i}>{line}</p>)}
      {game.counterevidence.map((line, i) => <p key={`counter-${i}`}>Counterevidence: {line}</p>)}
      {game.unknowns.map((line, i) => <p key={`unknown-${i}`}>Unknown: {line}</p>)}
    </div>)}
    {summary.rosters.length > 0 && <details><summary>Research across complete saved rosters</summary>
      {summary.rosters.map(roster => <div key={roster.number}><strong>Saved lineup {roster.number}</strong>
        <p>{roster.names.join(" · ")}</p><p>Selected scenarios: {roster.scenarios} · Salary: {roster.salary ?? "unknown"} · Saved lineup mean: {roster.mean?.toFixed(2) ?? "unknown"}</p>
      </div>)}
    </details>}
    <p>{summary.probability}</p>
  </section>;
}
