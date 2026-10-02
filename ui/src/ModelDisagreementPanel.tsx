import { useEffect, useState } from "react";
import {
  fetchModelDisagreements, fetchPlayerWhy, fetchProjectionAudit,
  type ModelDisagreement,
  type OptimizerResponse,
} from "./api";

type Row = Record<string, any>;

const point = (value: unknown, digits = 2) =>
  value == null || !Number.isFinite(Number(value)) ? "—" : Number(value).toFixed(digits);

export function ModelDisagreementPanel({ projectionRunId, optimizer }: {
  projectionRunId?: string | null; optimizer?: OptimizerResponse | null;
}) {
  const [audit, setAudit] = useState<Row | null>(null);
  const [rows, setRows] = useState<ModelDisagreement[]>([]);
  const [selected, setSelected] = useState<Row | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectionRunId) return;
    let active = true;
    setAudit(null);
    setRows([]);
    setSelected(null);
    setError(null);
    Promise.all([fetchProjectionAudit(projectionRunId), fetchModelDisagreements(projectionRunId)])
      .then(([model, disagreements]) => {
        if (active) { setAudit(model); setRows(disagreements.rows); }
      })
      .catch((reason: unknown) => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, [projectionRunId]);

  if (!projectionRunId) return null;
  const players = new Map<string, string>();
  const optimizerPlayers = new Map<string, Row>();
  for (const lineup of (Array.isArray(optimizer?.results) ? optimizer.results : []) as Row[][]) {
    for (const player of lineup) {
      if (player.player_id) {
        players.set(String(player.player_id), String(player.name ?? player.player_name ?? player.player_id));
        optimizerPlayers.set(String(player.player_id), player);
      }
    }
  }
  const openPlayer = (playerId: string) => {
    fetchPlayerWhy(projectionRunId, playerId).then(setSelected)
      .catch((reason: unknown) => setError(String(reason)));
  };
  return <section className="card" aria-label="Model disagreement and player why">
    <h3>Model disagreement</h3>
    <p>External benchmarks are review signals. They do not change projections, optimizer adjustments, or user preferences.</p>
    {error && <p role="alert">Audit unavailable: {error}</p>}
    {audit && <p>Model {audit.model_version} · fitted artifact {audit.artifact_status}
      {audit.artifact_warning ? ` — ${audit.artifact_warning}` : ` · ${audit.artifact_uri}`}</p>}
    {players.size > 0 && <label>Player why <select defaultValue="" onChange={(event) => {
      if (event.target.value) openPlayer(event.target.value);
    }}><option value="">Select a lineup player</option>{Array.from(players).sort((a, b) => a[1].localeCompare(b[1]))
      .map(([id, name]) => <option value={id} key={id}>{name}</option>)}</select></label>}
    {audit && (rows.length ? <div className="table-wrap"><table><thead><tr>
      <th>Player</th><th>Our mean</th><th>External mean</th><th>Delta</th><th>Delta %</th>
      <th>Position percentile</th><th>Source</th><th>Captured</th>
    </tr></thead><tbody>{rows.map((row) => <tr key={`${row.player_id}-${row.source}-${row.captured_at}`}>
      <td><button type="button" onClick={() => openPlayer(row.player_id)}>{row.player}</button>{row.large_disagreement ? " · large disagreement" : ""}</td>
      <td>{point(row.our_mean)}</td><td>{point(row.external_mean)}</td>
      <td>{point(row.delta)}</td><td>{row.delta_pct == null ? "—" : `${point(row.delta_pct, 1)}%`}</td>
      <td>{point(row.position_relative_percentile, 0)}th</td>
      <td>{row.source}</td><td>{new Date(row.captured_at).toLocaleString()}</td>
    </tr>)}</tbody></table></div> : <p>No same-slate external projection benchmark is captured for this run.</p>)}
    {selected && <div className="subpanel" aria-label="Player why">
      <h4>Player why · {selected.full_name}</h4>
      <p>Projection {point(selected.mean)} mean / {point(selected.p90)} P90 · role {selected.calibration_role ?? "—"}</p>
      <p>Opportunity: {selected.feature_json?.offensive_role_class ?? "—"}; role importance {point(selected.feature_json?.offensive_role_importance, 3)}; snap share {point(selected.feature_json?.snap_share_mean_3, 3)}</p>
      <p>Market: spread {point(selected.feature_json?.team_spread_line, 1)}; team total {point(selected.feature_json?.team_implied_total)}; game total {point(selected.feature_json?.game_total_line)}</p>
      <p>Model attribution: {selected.explanation?.attribution_method ?? selected.model?.artifact_warning ?? "Unavailable"}</p>
      {selected.explanation?.validation_warning && <p role="alert">{selected.explanation.validation_warning}</p>}
      <p>Top positive drivers: {(selected.explanation?.top_positive_model_drivers ?? []).map((item: Row) => `${item.feature} ${point(item.blended_mean_points)}`).join(", ") || "Unavailable"}</p>
      <p>Top negative drivers: {(selected.explanation?.top_negative_model_drivers ?? []).map((item: Row) => `${item.feature} ${point(item.blended_mean_points)}`).join(", ") || "Unavailable"}</p>
      <p>Optimizer adjustment: {optimizerPlayers.has(String(selected.player_id))
        ? `${point(optimizerPlayers.get(String(selected.player_id))?.optimizer_context_adjustment)} context points; ${(optimizerPlayers.get(String(selected.player_id))?.optimizer_context_reason_codes ?? []).join(", ") || "no reason codes"}`
        : "Player is not in the displayed lineup; inspect its saved optimizer run for adjustments."}</p>
      <p>User preference: {optimizerPlayers.get(String(selected.player_id))?.user_preference_exclusions?.length
        ? optimizerPlayers.get(String(selected.player_id))?.user_preference_exclusions.join(", ")
        : "No selected-lineup preference exclusion recorded"}</p>
      <div className="table-wrap"><table><thead><tr><th>Diagnostic counterfactual</th><th>Input</th><th>Rescored mean</th><th>Delta</th></tr></thead>
        <tbody>{(selected.explanation?.counterfactuals ?? []).map((item: Row) => <tr key={item.scenario}>
          <td>{item.scenario}</td><td>{point(item.input, 3)}</td><td>{point(item.mean)}</td><td>{point(item.delta)}</td>
        </tr>)}</tbody></table></div>
      <p>Model attribution, optimizer adjustments, and user preferences are separate records. Counterfactuals hold other inputs fixed and are not causal effects.</p>
      <p>External: {(selected.external_benchmarks ?? []).map((item: Row) => `${item.source_name} ${point(item.projection)} (${new Date(item.captured_at).toLocaleString()})`).join(", ") || "Unavailable"}</p>
    </div>}
  </section>;
}
