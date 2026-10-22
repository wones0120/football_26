type ObjectValue = Record<string, unknown>;
const object = (value: unknown): ObjectValue => value && typeof value === "object" && !Array.isArray(value) ? value as ObjectValue : {};
const text = (value: unknown): string => typeof value === "string" ? value : "";
const texts = (value: unknown): string[] => Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];

export function analystResearchEvidence(value: unknown, results: unknown = []) {
  const receipt = object(value);
  const coverage = object(receipt.coverage ?? value);
  const state = text(coverage.status) || "unrecorded";
  const closed = coverage.producer_loop_closed === true;
  const titles: Record<string, string> = {
    unrecorded: "Authored research not recorded",
    reference_only: "Reference evidence only · no authored review",
    refresh_pending: "Research refresh pending",
    mechanisms_partial: "Authored research partially supported",
    mechanisms_current: closed ? "Authored research · prepared and closed" : "Authored research · preparation closure pending",
  };
  const lines = [titles[state] ?? state.replaceAll("_", " ")];
  const closure = object(coverage.closure_receipt);
  if (closed) lines.push(`Closure: ${text(closure.publication_id) || "recorded"} · checked ${text(closure.checked_at) || "time unavailable"}`);
  else lines.push(coverage.producer_executed === true
    ? "Authored publication recorded; fresh preparation closure remains pending."
    : "Source compatibility alone does not mean a research worker completed an assessment.");
  if (receipt.portfolio_dependency) lines.push(text(receipt.portfolio_dependency));
  const gameValues = Array.isArray(receipt.games) ? receipt.games : Array.isArray(coverage.games) ? coverage.games : [];
  const games = gameValues.map(raw => {
    const game = object(raw); const assessment = object(game.authored_assessment);
    const disposition = text(assessment.disposition);
    const consumed = texts(game.material_scenario_ids_consumed);
    const details = [text(assessment.mechanism) || "No sourced authored mechanism is recorded."];
    if (disposition === "no_change") details.push("Sourced no-change assessment · no numerical scenario change claimed.");
    if (disposition === "material") details.push(consumed.length ? `Conditional inputs consumed: ${consumed.join(", ")}. This does not by itself prove the selected roster changed.` : "Material assessment recorded; no nonneutral scenario consumption is recorded here.");
    if (assessment.authored_at) details.push(`Authored: ${text(assessment.authored_at)}`);
    const sources = texts(assessment.source_ids);
    if (sources.length) details.push(`Source evidence: ${sources.join(", ")}`);
    return { game: text(game.game_id) || "Game unavailable", state: text(game.state), disposition,
      details, counterevidence: texts(assessment.counterevidence), unknowns: texts(assessment.unknowns) };
  });
  const rosters = (Array.isArray(results) ? results : []).flatMap((raw, index) => {
    if (!Array.isArray(raw) || !raw.length) return [];
    const explanation = object(object(raw[0]).analyst_research_explanation);
    if (!Object.keys(explanation).length) return [];
    const names = raw.map(v => {
      const p = object(v);return `${text(p.roster_position) || "SELECTED"}: ${text(p.name) || text(p.player_name) || text(p.player_id) || "Unknown player"}`;
    });
    const scenarioIds = texts(explanation.selected_scenario_ids);
    return [{ number: index + 1, names, scenarios: scenarioIds.join(", ") || "not recorded",
      salary: typeof explanation.salary === "number" ? explanation.salary : null,
      mean: typeof explanation.base_mean_sum === "number" ? explanation.base_mean_sum : null }];
  });
  return { state, closed, lines, games, rosters,
    probability: text(coverage.probability_status) || "Scenario occurrence probabilities are not calibrated." };
}

export function analystResearchHtml(value: unknown, results: unknown = []): string {
  const summary = analystResearchEvidence(value, results);
  const escape = (v: unknown) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  return `<section class="lineup"><h2>Authored football research</h2>${summary.lines.map(v=>`<p>${escape(v)}</p>`).join("")}${summary.games.map(g=>`<h3>${escape(g.game)} · ${escape(g.disposition || g.state || "unrecorded")}</h3>${g.details.map(v=>`<p>${escape(v)}</p>`).join("")}${g.counterevidence.map(v=>`<p>Counterevidence: ${escape(v)}</p>`).join("")}${g.unknowns.map(v=>`<p>Unknown: ${escape(v)}</p>`).join("")}`).join("")}${summary.rosters.map(r=>`<h3>Saved lineup ${r.number}</h3><p>${r.names.map(escape).join(" · ")}</p><p>Selected scenarios: ${escape(r.scenarios)} · Salary: ${escape(r.salary ?? "unknown")} · Saved lineup mean: ${escape(r.mean ?? "unknown")}</p>`).join("")}<p>${escape(summary.probability)}</p></section>`;
}
