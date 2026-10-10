import { portfolioSettingsRows } from "./classicPortfolioReport";
import type { OptimizerResponse } from "./api";
import { gameAppearancesHtml } from "./classicReadinessReport";

export function ClassicGameConcentrationReport({ optimizer }: { optimizer: OptimizerResponse }) {
  const report = optimizer.primary_game_constraint;
  const contract = optimizer.effective_strategy_contract;
  const rows = portfolioSettingsRows(optimizer);
  const audit = optimizer.portfolio_controls_report;
  if (!report && !contract) return null;
  return <div className="status-card nested-card">
    <h3>{rows.length ? "Saved portfolio settings" : "Primary-game concentration"}</h3>
    {rows.length > 0 && <><div className="table-wrap"><table><thead><tr><th>Setting</th><th>Requested</th><th>Effective</th><th>Source</th><th>Achieved</th></tr></thead><tbody>{rows.map((row) => <tr key={row.setting}><td>{row.setting}</td><td>{row.requested}</td><td>{row.effective}</td><td>{row.source}</td><td>{row.achieved}</td></tr>)}</tbody></table></div>
      <p>Independent validation: {audit?.validation.status} {audit?.validation.violations.join(", ")}. Exposure appearances use requested entries as the denominator.</p>
      {audit?.feasibility.status === "underfilled" && <details open><summary>Underfilled portfolio · no limits relaxed</summary><p>{audit.feasibility.explanation}</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(audit.feasibility, null, 2)}</pre></details>}
    </>}
    {report && <>
      <p>Requested: {report.requested ?? "No limit"} · Effective: {report.effective ?? "No limit"} · Source: {report.source.replaceAll("_", " ")} · Validation: {report.validation}</p>
      <p>Canonical primary games: {Object.entries(report.achieved_game_exposure).map(([game, count]) => `${game}: ${count}`).join(" · ") || "No selected lineups"}.</p>
    </>}
    <p>Opposite QB directions share the same sorted team pair. This limits selected lineups per primary game; Max players / game limits players inside each lineup.</p>
    <div dangerouslySetInnerHTML={{ __html: gameAppearancesHtml(optimizer) }} />
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
