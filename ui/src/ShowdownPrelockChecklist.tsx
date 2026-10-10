import type { ShowdownPrelockChecklist as Checklist } from "./showdownResearch";

const counts = (values: Record<string, number>) => Object.entries(values).map(([key, value]) => `${key}: ${value}`).join(" · ");
const money = (value: number | null) => value == null ? "Unavailable" : `$${value.toLocaleString()}`;

export function ShowdownPrelockChecklist({ checklist }: { checklist: Checklist }) {
  const pair = checklist.proposed_pair;
  const proposal = checklist.candidate_details.filter(c => pair.candidate_ids.includes(c.candidate_id));
  return <div className="status-card" aria-label="Nonbinding prelock review checklist">
    <h3>Nonbinding prelock review checklist</h3>
    <p>Frozen cutoff {checklist.data_cutoff_at}. Coverage prompts do not change scores, eligibility or selection.</p>
    {checklist.incomplete_evidence && <p>Incomplete frozen evidence — diagnostic review only.</p>}
    <div className="saved-contest-scroll"><table style={{ minWidth: 760 }}>
      <thead><tr><th>Scope</th><th>Captain archetypes</th><th>Zero / one / two QBs</th><th>3–3 / 4–2 / 5–1</th><th>WR/TE CPT own QB: with / without</th></tr></thead>
      <tbody>{Object.entries(checklist.scopes).map(([scope, s]) => <tr key={scope}>
        <td>{scope.replaceAll("_", " ")} ({s.count})</td><td>{counts(s.captain_archetypes) || "None"}</td>
        <td>{counts(s.qb_counts)}</td><td>{counts(s.team_splits)}</td>
        <td>{s.receiver_captain_pairings.with_own_qb} / {s.receiver_captain_pairings.without_own_qb}</td>
      </tr>)}</tbody>
    </table></div>
    <details><summary>QB families: generation versus quality filtering</summary>
      <ul>{checklist.qb_families.map(f => <li key={f.family}>
        {f.family.replaceAll("_", " ")}: generated {f.generated}, quality eligible {f.quality_eligible}, finalists {f.finalists}, proposal {f.proposal}.
        {" "}{f.absence_stage.replaceAll("_", " ")}; {f.reason_codes.join(", ").replaceAll("_", " ") || "present"}.
      </li>)}</ul>
    </details>
    <p>Projected ownership: {checklist.ownership_provenance.status}. Sources: {checklist.ownership_provenance.sources.join(", ") || "Unavailable"}; observed {checklist.ownership_provenance.observed_at || "Unavailable"}.</p>
    <p>Saved proposal physical-player overlap: {pair.physical_player_overlap == null ? `Unavailable (${pair.unavailable_reason?.replaceAll("_", " ")})` : `${pair.physical_player_overlap} of 6`}.
      {" "}This is the saved optimizer control; an AI decision is not inferred.</p>
    <div className="saved-contest-scroll"><table style={{ minWidth: 560 }}>
      <thead><tr><th>Saved proposal Captain / candidate</th><th>Salary left</th><th>Sourced projected total ownership</th></tr></thead>
      <tbody>{proposal.map(c => <tr key={c.candidate_id}><td>{c.captain}<br /><small>{c.candidate_id}</small></td>
        <td>{money(c.salary_left)}</td><td>{c.projected_total_ownership == null ? "Unavailable" : `${c.projected_total_ownership.toFixed(1)}% sum`}</td></tr>)}</tbody>
    </table></div>
    <details><summary>Salary and ownership across quality-eligible candidates</summary>
      <ul>{checklist.candidate_details.filter(c => c.quality_eligible).map(c => <li key={c.candidate_id}>
        {c.captain} · {c.candidate_id} · salary left {money(c.salary_left)} · ownership {c.projected_total_ownership == null ? "Unavailable" : `${c.projected_total_ownership.toFixed(1)}% sum`}
      </li>)}</ul>
    </details>
    <p className="hint">{checklist.limitations.join(" ")}</p>
  </div>;
}
