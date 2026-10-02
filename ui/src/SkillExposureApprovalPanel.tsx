import { useEffect, useState } from "react";
import type { OptimizerResponse } from "./api";
import { decideSkillExposure, fetchSkillExposureStatus, type SkillExposureStatus } from "./api";

type Row = Record<string, unknown>;

const fmt = (value: unknown, digits = 2) => value == null ? "Unavailable" : Number(value).toFixed(digits);

export function SkillExposureApprovalPanel({ optimizer, onNewRun }: {
  optimizer: OptimizerResponse;
  onNewRun: (runId: string) => Promise<void>;
}) {
  const lineups = optimizer.results as Row[][] | undefined;
  const report = (lineups?.[0]?.[0]?.classic_small_field_report ?? {}) as Row;
  const readiness = (report.entry_readiness ?? {}) as Row;
  const coverage = (readiness.market_coverage ?? {}) as Row;
  const marketGames = Array.isArray(coverage.games) ? coverage.games as Row[] : [];
  const cases = (report.skill_exposure_approvals ?? []) as Row[];
  const [status, setStatus] = useState<SkillExposureStatus | null>(null);
  const [reason, setReason] = useState<Record<string, string>>({});
  const [customCap, setCustomCap] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setStatus(null);
    fetchSkillExposureStatus(optimizer.job_id).then((value) => {
      if (active) setStatus(value);
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : String(cause));
    });
    return () => { active = false; };
  }, [optimizer.job_id]);

  if (!report.entry_readiness) return null;

  const submit = async (playerId: string, decision: "approve" | "cap", cap?: number) => {
    setBusy(true);
    setError(null);
    try {
      const saved = await decideSkillExposure(optimizer.job_id, {
        player_id: playerId, decision,
        reason: (reason[playerId] ?? "").trim(),
        ...(cap == null ? {} : { requested_cap: cap }),
      });
      setStatus(await fetchSkillExposureStatus(optimizer.job_id));
      if (saved.new_optimizer_run_id) await onNewRun(saved.new_optimizer_run_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return <section className="card">
    <h3>Entry readiness</h3>
    <p><strong>{String(readiness.status ?? "Unavailable")}</strong></p>
    <h4>Market</h4>
    <p>Market coverage: {String(coverage.sourced_games ?? 0)}/{String(coverage.total_games ?? 0)} games ·
      Fresh: {Array.isArray(coverage.fresh_games) ? coverage.fresh_games.length : 0} ·
      Aging: {Array.isArray(coverage.aging_games) ? coverage.aging_games.length : 0} ·
      Stale: {Array.isArray(coverage.stale_games) ? coverage.stale_games.length : 0} ·
      Missing: {Array.isArray(coverage.missing_games) ? coverage.missing_games.length : 0} ·
      Latest refresh: {String(coverage.newest_observed_at ?? "Unavailable")}</p>
    {marketGames.length > 0 && <details><summary>Per-game market age</summary>
      <table><thead><tr><th>Game</th><th>Status</th><th>Source</th><th>Observed</th><th>Age at decision</th></tr></thead>
        <tbody>{marketGames.map((game) => <tr key={String(game.game_id)}><td>{String(game.game_id)}</td>
          <td>{String(game.status)}</td><td>{String(game.source ?? "Unavailable")}</td>
          <td>{String(game.observed_at ?? "Unavailable")}</td>
          <td>{game.age_hours == null ? "Unavailable" : `${fmt(game.age_hours, 1)} h`}</td></tr>)}</tbody></table>
    </details>}
    <h4>Approval required</h4>
    {cases.length === 0 ? <p>None.</p> : cases.map((row) => {
      const playerId = String(row.player_id);
      const capped = (row.capped_80 ?? {}) as Row;
      const original = (row.original ?? {}) as Row;
      const approved = status?.approved.some((item) => item.player_id === playerId);
      const decision = status?.decisions?.find((item) => item.player_id === playerId);
      return <div key={playerId} className="card">
        <p><strong>{String(row.player)} — 100% skill exposure</strong> ({String(row.position)}, {String(row.selected_count)}/{String(row.selected_total)})
          {approved ? " · Approved pre-lock" : decision?.decision === "cap" ? " · Capped in a new run" : " · Approval required before export"}</p>
        <p>Mean {fmt(row.mean)} · P90 {fmt(row.p90)} · Salary ${fmt(row.salary, 0)} · Value {fmt(row.value)} ·
          Ownership {fmt(row.ownership)} · Core {String(row.core_classification ?? "Unavailable")} ·
          Availability {String(row.availability ?? "Unavailable")} · Candidate exposure {String(row.candidate_count)}/{String(row.candidate_total)}</p>
        <p>The optimizer prefers 100% exposure. Here is the cost of reducing it.</p>
        <table><thead><tr><th>Portfolio</th><th>Selector sum</th><th>Mean sum</th><th>P90 sum</th><th>Overlap</th><th>QB paths</th></tr></thead>
          <tbody>{[["Original", original], ["Capped at 80%", capped]].map(([label, metrics]) => {
            const item = metrics as Row;
            return <tr key={String(label)}><td>{String(label)}</td><td>{fmt(item.selector_sum, 3)}</td>
              <td>{fmt(item.mean_sum)}</td><td>{fmt(item.p90_sum)}</td><td>{fmt(item.max_overlap, 0)}</td>
              <td>{Array.isArray(item.qb_paths) ? item.qb_paths.join(", ") : "Unavailable"}</td></tr>;
          })}</tbody></table>
        <p>Cost to cap at 80%: selector {fmt(row.selector_cost, 3)} · mean {fmt(row.mean_cost)} · P90 {fmt(row.p90_cost)}</p>
        {!decision && <div>
          <label>Reason <input value={reason[playerId] ?? ""}
            onChange={(event) => setReason((current) => ({ ...current, [playerId]: event.target.value }))}
            placeholder="Explain your exposure decision" /></label>
          <div className="button-row">
            <button disabled={busy || !reason[playerId]?.trim()} onClick={() => submit(playerId, "approve")}>Approve 100%</button>
            <button disabled={busy || !reason[playerId]?.trim()} onClick={() => submit(playerId, "cap", 0.8)}>Cap at 80% in a new run</button>
            <label>Custom cap % <input type="number" min="0" max="80" step="1"
              value={customCap[playerId] ?? ""}
              onChange={(event) => setCustomCap((current) => ({ ...current, [playerId]: event.target.value }))} /></label>
            <button disabled={busy || !reason[playerId]?.trim() || customCap[playerId] === undefined ||
              !Number.isFinite(Number(customCap[playerId])) || Number(customCap[playerId]) < 0 || Number(customCap[playerId]) > 80}
              onClick={() => submit(playerId, "cap", Number(customCap[playerId]) / 100)}>Apply custom cap in a new run</button>
          </div>
        </div>}
      </div>;
    })}
    {error && <p role="alert">{error}</p>}
  </section>;
}
