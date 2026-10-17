export type AnalystFocus = {
  mode: string;
  selected_scenario_ids: string[];
  generic_fallback?: boolean;
  requirements?: { scenario_id: string; team: string; script: string; authority: string; finding?: { team_points_target?: number } | null }[];
};

export function focusCompliance(results: unknown[]) {
  let passed = 0, failed = 0, unknown = 0;
  for (const lineup of results) {
    const evidence = Array.isArray(lineup) ? lineup.find(row => row && typeof row === "object" && "analyst_focus_story_compliance" in row)?.analyst_focus_story_compliance : undefined;
    if (evidence === true) passed++;
    else if (evidence === false) failed++;
    else unknown++;
  }
  return { passed, failed, unknown };
}

export function AnalystFocusSummary({ focus, results }: { focus: AnalystFocus; results: unknown[] }) {
  const compliance = focusCompliance(results);
  return <div>
    <p>Saved focus: {focus.mode === "SELECTED_ONLY" ? "Only selected football stories" : "Mixed football portfolio"}</p>
    {focus.mode === "SELECTED_ONLY" && <>
      <p>Selected stories: {focus.selected_scenario_ids.join(", ") || "missing saved IDs"} · Generic fallback: {focus.generic_fallback === false ? "disabled" : "not recorded"}</p>
      {focus.requirements?.map(requirement => <p key={requirement.scenario_id}>{requirement.team} · {requirement.script.replaceAll("_", " ")} · {requirement.authority.replaceAll("_", " ")}{requirement.finding?.team_points_target != null ? ` · ${requirement.finding.team_points_target} team points: explicit user what-if` : ""}</p>)}
      <p>Saved construction checks: {compliance.passed} passed · {compliance.failed} failed · {compliance.unknown} unavailable.</p>
      <p>Story compliance checks lineup construction. Scenario probability and ownership leverage are not inferred.</p>
    </>}
  </div>;
}
