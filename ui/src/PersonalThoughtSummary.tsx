export type PersonalContext = {
  packet_sha256?: string | null;
  considered: { belief_id:string; belief_version_id:string; thought_text:string; status:string; related_scenario_ids:string[]; not_applied_reason:string; conditional_mechanism?:string; resolved_scope?:{team?:string;game_ids?:string[]}; decision_id?:string; supporting_evidence?:unknown[]; challenging_evidence?:unknown[]; evidence_limitation?:string }[];
  rejected: {belief_version_id:string;reasons:string[]}[];
  affected_construction:boolean; changed_selected_rosters:boolean;
};

export function PersonalThoughtSummary({ context }: { context: PersonalContext | null | undefined }) {
  if (!context) return null;
  return <details className="operations-disclosure" data-testid="personal-thought-summary">
    <summary>Personal thoughts: {context.considered.length} read · {context.rejected.length} excluded · construction {context.affected_construction ? "affected" : "unchanged"}</summary>
    <p>Selected rosters: {context.changed_selected_rosters ? "change measured" : "no change attributed to personal thoughts"}.</p>
    {context.considered.map(item => <div key={item.belief_version_id} style={{overflowWrap:"anywhere"}}>
      <p><strong>{item.thought_text}</strong> · {item.status.replaceAll("_"," ")}</p>
      <p>{item.belief_version_id} · approval {item.decision_id} · {item.resolved_scope?.team} · {item.resolved_scope?.game_ids?.join(", ")}</p>
      <p>Conditional mechanism: {item.conditional_mechanism}</p>
      <p>Related scenarios: {item.related_scenario_ids.join(", ") || "none"}. {item.not_applied_reason}</p>
      <p>{item.evidence_limitation}</p>
      <details><summary>Team research supporting and contrary context</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify({supporting:item.supporting_evidence,contrary:item.challenging_evidence},null,2)}</pre></details>
    </div>)}
    {context.rejected.map(item => <p key={item.belief_version_id} style={{overflowWrap:"anywhere"}}>{item.belief_version_id}: {item.reasons.join(", ")}</p>)}
    <p style={{overflowWrap:"anywhere"}}>Checked research: {context.packet_sha256 ?? "unavailable"}</p>
  </details>;
}
