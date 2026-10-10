import { SCENARIO_ACCOUNTING_HEADERS, scenarioAccountingDescription, scenarioAccountingRows, scenarioCreditExplanations } from "./scenarioPortfolioAccounting";

export function ScenarioPortfolioAccounting({ report }: { report: Record<string, unknown> }) {
  const rows = scenarioAccountingRows(report);
  return <section className="scenario-portfolio-accounting"><h3>Scenario portfolio accounting</h3><p>{scenarioAccountingDescription(report)}</p>
    {rows.length > 0 && <div className="scroll-table"><table className="compact-table"><thead><tr>
      {SCENARIO_ACCOUNTING_HEADERS.map(header => <th key={header}>{header}</th>)}
    </tr></thead><tbody>{rows.map((cells, i) => <tr key={i}>{cells.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>}
    {scenarioCreditExplanations(report).map((reason, i) => <p key={i}>{reason}</p>)}
  </section>;
}
