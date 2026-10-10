export type GppCandidate = {
  candidate_id: string; lineup_number: number; rank: number;
  projected_points: number; marginal_upside_sum: number | null; salary: number;
  availability_exceptions: { player_id: string; name: string; designation: string }[];
};
export type GppRecommendationReport = {
  policy_id: string; status: "provisional" | "unavailable"; reason: string;
  recommended: GppCandidate | null; candidates: GppCandidate[];
  exceptions: { lineup_number: number; reason: string }[]; limitations: string[];
};

export function GppRecommendation({ report, pending, onDownload }: {
  report: GppRecommendationReport; pending: boolean; onDownload: () => void;
}) {
  const selected = report.recommended;
  return <section className="card" aria-label="GPP lineup recommendation">
    <h3>{selected ? `Recommended GPP lineup: #${selected.lineup_number}` : "No supported GPP recommendation"}</h3>
    <p><strong>Provisional · paid-finish performance not yet validated.</strong> {report.reason}</p>
    <p>One lineup to reuse across this slate’s GPPs. Compared {report.candidates.length} valid candidates.</p>
    {selected && <>
      <p>Projected points: {selected.projected_points.toFixed(2)} · Sum of player P90s: {selected.marginal_upside_sum?.toFixed(2) ?? "Unavailable"} · Salary: ${selected.salary.toLocaleString()}</p>
      <p>Paid-finish probability: unavailable · Expected return: unavailable. These require a calibrated field model and contest payout evidence.</p>
      <div className="button-row">
        <a href={`#optimizer-lineup-${selected.lineup_number}`}>View recommended lineup</a>
        <button disabled={pending} onClick={onDownload}>{pending ? "Preparing download…" : "Download recommended lineup for DraftKings"}</button>
      </div>
      {selected.availability_exceptions.length > 0 && <><h4>Availability to review</h4><ul>
        {selected.availability_exceptions.map(p => <li key={p.player_id}>{p.name}: {p.designation}. Recheck before lock.</li>)}
      </ul></>}
    </>}
    {report.exceptions.length > 0 && <details><summary>Candidate exceptions ({report.exceptions.length})</summary><ul>
      {report.exceptions.map((e, i) => <li key={i}>Lineup #{e.lineup_number}: {e.reason}</li>)}
    </ul></details>}
    <details><summary>Compare candidates and selection limits</summary>
      <div className="table-wrap"><table><thead><tr><th>Rank</th><th>Lineup</th><th>Projected points</th><th>Sum of player P90s</th><th>Salary</th></tr></thead><tbody>
        {report.candidates.map(c => <tr key={c.candidate_id}><td>{c.rank}</td><td><a href={`#optimizer-lineup-${c.lineup_number}`}>#{c.lineup_number}</a></td><td>{c.projected_points.toFixed(2)}</td><td>{c.marginal_upside_sum?.toFixed(2) ?? "Unavailable"}</td><td>${c.salary.toLocaleString()}</td></tr>)}
      </tbody></table></div>
      <ul>{report.limitations.map(text => <li key={text}>{text}</li>)}</ul>
    </details>
    <p>Final prelock checks still apply. Downloading does not enter a contest.</p>
  </section>;
}
