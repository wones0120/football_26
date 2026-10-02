import type { OptimizerResponse } from "./api.ts";

type Row = Record<string, any>;

function decimal(value: unknown, digits = 2): string {
  const parsed = Number(value);
  return value == null || !Number.isFinite(parsed) ? "—" : parsed.toFixed(digits);
}

export function RbDstDiagnosticsPanel({ optimizer }: { optimizer: OptimizerResponse }) {
  const firstLineup = Array.isArray(optimizer.results) ? optimizer.results[0] : null;
  const firstPlayer = Array.isArray(firstLineup) ? firstLineup[0] as Row | undefined : undefined;
  const report = firstPlayer?.classic_small_field_report as Row | undefined;
  const diagnostics = report?.rb_dst_diagnostics as Row | undefined;
  if (!diagnostics) return null;

  const why = (diagnostics.player_why ?? []) as Row[];
  const selectedRanks = new Set((report?.selected_ranks ?? []) as number[]);
  const candidates = (report?.all_candidates ?? []) as Row[];
  const flagged: Row[] = candidates.filter((row) => selectedRanks.has(Number(row.rank)))
    .flatMap((row) => ((row.rb_dst_football_sanity_flags ?? []) as Row[])
      .map((flag): Row => ({ ...flag, rank: row.rank })));
  const exposure = (diagnostics.selected_flag_exposure ?? []) as Row[];

  return <section className="card" aria-label="RB and DST football sanity diagnostics">
    <h3>RB projection and football sanity</h3>
    <p>Warning-only evidence saved with this optimizer run. Flags do not change projections, scores, or player eligibility. Alternatives are the strongest in the saved candidate universe.</p>
    <details>
      <summary>Player why · RB projection and role</summary>
      <p>Saved one-feature role probes are diagnostic model responses, not causal estimates. Market rescoring and SHAP are unavailable without the fitted model artifact.</p>
      <div className="table-wrap"><table><thead><tr><th>RB</th><th>Mean / P90</th><th>Role and usage</th><th>Market</th><th>Model explanation</th><th>External benchmark</th></tr></thead>
        <tbody>{why.map((row) => {
          const grid = (row.model_explanation ?? {}) as Row;
          const deltas = ((grid.importance ?? []) as Row[]).map((item) => Number(item.delta)).filter(Number.isFinite);
          const probe = deltas.length ? `${decimal(Math.min(...deltas))} to ${decimal(Math.max(...deltas))} role-importance probe` : "Probe unavailable";
          const external = (row.external_benchmark ?? {}) as Row;
          return <tr key={row.player_id}>
            <td>{row.name} ({row.team}) · ${decimal(row.salary, 0)}</td>
            <td>{decimal(row.mean)} / {decimal(row.p90)}</td>
            <td>{row.role_class ?? "Role unavailable"}; snap {decimal(row.snap_share_mean_3, 3)}, carries {decimal(row.carries_mean_3)}, targets {decimal(row.targets_mean_3)}, target share {decimal(row.target_share_mean_3, 3)}, receiving strength {decimal(row.receiving_role_strength, 3)}; snap trend {decimal(row.trend?.snap_share_trend, 3)}, target-share trend {decimal(row.trend?.target_share_trend, 3)}</td>
            <td>{decimal(row.team_implied_total)} implied; spread {decimal(row.spread, 1)}; game total {decimal(row.game_total, 1)}</td>
            <td>{row.model_version ?? "Model version unavailable"}; {probe}</td>
            <td>{external.reason ?? external.status ?? "Unavailable"}</td>
          </tr>;
        })}</tbody></table></div>
    </details>
    <details open>
      <summary>Lineup football sanity · warning only</summary>
      {flagged.length ? <div className="table-wrap"><table><thead><tr><th>Lineup</th><th>Flag</th><th>Why</th><th>Production impact</th><th>Strongest alternative and quality cost</th></tr></thead>
        <tbody>{flagged.map((flag, index) => {
          const alternative = flag.strongest_candidate_without_flag as Row | null;
          return <tr key={`${flag.rank}-${flag.key}-${index}`}>
            <td>#{flag.rank}</td><td>{flag.label}</td><td>{flag.why}{flag.kind === "same_team_rb_dst" ? ` Recent carries ${decimal(flag.recent_carries)}, targets ${decimal(flag.recent_targets)}, receiving strength ${decimal(flag.receiving_role_strength, 3)}.` : ""}</td>
            <td>{flag.production_impacting ? "Production impacting" : "Informational only"}</td>
            <td>{alternative ? `#${alternative.rank}: mean ${decimal(alternative.mean_cost)}, P90 ${decimal(alternative.p90_cost)}, selector ${decimal(alternative.selector_cost, 3)} cost` : "No avoiding candidate saved"}</td>
          </tr>;
        })}</tbody></table></div> : <p>No selected lineup triggered a flag.</p>}
    </details>
    <details>
      <summary>Portfolio flagged-construction exposure</summary>
      {exposure.length ? <ul>{exposure.map((row) => <li key={row.key}>{row.key}: {row.appearances}/{row.selected_count} entries</li>)}</ul>
        : <p>No selected flagged constructions.</p>}
    </details>
  </section>;
}
