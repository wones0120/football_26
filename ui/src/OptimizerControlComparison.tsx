type Comparison = {
  selection_changed: boolean;
  selection_effect: string;
  selected_only: Player[];
  control_only: Player[];
  control_lineup: Player[];
  scored_metrics: Record<string, number | null>;
  control_metrics: Record<string, number | null>;
  deltas_scored_minus_control: Record<string, number | null>;
  base_objective_opportunity_cost: number;
  rule_contributions: { rule_id: string; scored: number; control_if_enabled: number; delta: number }[];
};
type Player = { player_id: string; name?: string; roster_position?: string; position?: string };
const metrics = [
  ["mean", "Mean"], ["individual_ceiling_sum", "Individual Ceiling Sum"],
  ["salary", "Salary"], ["ownership_sum", "Ownership sum"], ["leverage_sum", "Leverage sum"],
];
const number = (value: number | null | undefined) => value == null ? "Unavailable" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const players = (rows: Player[]) => rows.map(p => `${p.name || p.player_id} (${p.roster_position || p.position})`).join(", ") || "None";

export function OptimizerControlComparison({ comparison }: { comparison?: Comparison }) {
  if (!comparison) return <p className="muted">Control comparison unavailable for this saved run. Generate a new run to compare soft scoring rules.</p>;
  return <details>
    <summary>Compare with rules disabled · {comparison.selection_effect === "alternate_optimum" ? "Tied alternative" : comparison.selection_changed ? "Selection changed" : "Same selection"}</summary>
    <p>Same candidate pool and hard constraints at this selection step. Context and correlation scoring are disabled in the control. Deltas are scored minus control.</p>
    <p><strong>Selected instead:</strong> {players(comparison.selected_only)}<br />
      <strong>Control alternatives:</strong> {players(comparison.control_only)}</p>
    <div style={{ overflowX: "auto", maxWidth: "100%" }}>
      <table className="compact-table">
        <thead><tr><th>Metric</th><th>Scored</th><th>Control</th><th>Delta</th></tr></thead>
        <tbody>{metrics.map(([key, label]) => <tr key={key}><td>{label}</td>
          <td>{number(comparison.scored_metrics[key])}</td><td>{number(comparison.control_metrics[key])}</td>
          <td>{number(comparison.deltas_scored_minus_control[key])}</td></tr>)}</tbody>
      </table>
    </div>
    <p>Base objective opportunity cost: {number(comparison.base_objective_opportunity_cost)}. Individual Ceiling Sum is not a jointly simulated lineup quantile.</p>
    <p><strong>Full control lineup:</strong> {players(comparison.control_lineup)}</p>
    <p>These are alternatives at each portfolio step, not a separate playable portfolio. Contributions below describe the joint rule ablation; they do not prove an individual rule caused a swap.</p>
    <div style={{ overflowX: "auto", maxWidth: "100%" }}>
      <table className="compact-table">
        <thead><tr><th>Rule</th><th>Scored contribution</th><th>Control if enabled</th><th>Delta</th></tr></thead>
        <tbody>{comparison.rule_contributions.map(rule => <tr key={rule.rule_id}>
          <td style={{ overflowWrap: "anywhere" }}>{rule.rule_id}</td><td>{number(rule.scored)}</td>
          <td>{number(rule.control_if_enabled)}</td><td>{number(rule.delta)}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <details><summary>Comparison JSON and reproducible solver inputs</summary>
      <pre style={{ maxHeight: 360, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(comparison, null, 2)}</pre>
    </details>
  </details>;
}
