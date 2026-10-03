import type { OptimizerResponse } from "./api";

export function ClassicGameConcentrationReport({ optimizer }: { optimizer: OptimizerResponse }) {
  const report = optimizer.primary_game_constraint;
  const contract = optimizer.effective_strategy_contract;
  if (!report && !contract) return null;
  return <div className="status-card nested-card">
    <h3>Primary-game concentration</h3>
    {report && <>
      <p>Requested: {report.requested ?? "No limit"} · Effective: {report.effective ?? "No limit"} · Source: {report.source.replaceAll("_", " ")} · Validation: {report.validation}</p>
      <p>Canonical primary games: {Object.entries(report.achieved_game_exposure).map(([game, count]) => `${game}: ${count}`).join(" · ") || "No selected lineups"}.</p>
    </>}
    <p>Opposite QB directions share the same sorted team pair. This limits selected lineups per primary game; Max players / game limits players inside each lineup.</p>
    {contract && <details><summary>Saved strategy contract</summary>
      <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify({
        contract_id: contract.contract_id, execution_mode: contract.execution_mode,
        strategy_label: contract.strategy_label, deviations: contract.deviations,
        effective_sha256: contract.effective_sha256, requested: contract.requested,
        sources: contract.sources, effective: { ...(contract.effective as Record<string, unknown>), players: "Ordered player inputs retained in the saved replay contract" },
      }, null, 2)}</pre>
    </details>}
  </div>;
}
