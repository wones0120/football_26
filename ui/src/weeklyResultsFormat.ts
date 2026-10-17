import type { WeeklyResultTotals, WeeklyResultsReport } from "./api.ts";
import { ALL_LEARNING_SLATES } from "./learningContext.ts";
import { normalizeSlateId } from "./workspaceContext.ts";

export function weeklyResultsForSlate(report: WeeklyResultsReport, slate: string): WeeklyResultsReport {
  if (slate === ALL_LEARNING_SLATES) return report;
  const slates = report.slates.filter(row => normalizeSlateId(row.slate) === slate);
  return { ...report, slates, summary: slates[0]?.summary ?? {
    entries: 0, fees_known_entries: 0, winnings_known_entries: 0, financial_complete_entries: 0,
    known_fees: 0, known_winnings: 0, known_net_profit: 0,
    fees: null, winnings: null, net_profit: null, roi: null, cash_rate: null,
    known_cash_entries: 0, known_free_entries: 0, ticket_winnings: 0,
  } };
}

export const resultMoney = (value: number | null): string => value == null ? "Unknown" :
  value.toLocaleString("en-US", { style: "currency", currency: "USD" });
export const resultPercent = (value: number | null): string => value == null ? "Unknown" : `${(value * 100).toFixed(2)}%`;
export function resultRoi(totals: WeeklyResultTotals): string {
  return totals.entries && totals.fees === 0 && totals.winnings != null ? "N/A (zero fees)" : resultPercent(totals.roi);
}
export function resultCoverage(totals: WeeklyResultTotals): string {
  return `${totals.financial_complete_entries}/${totals.entries} entries with both fee and winnings evidence`;
}
