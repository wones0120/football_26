export const CLASSIC_GPP_BASELINE_STRATEGY_ID = "classic_gpp_baseline_v1";
export const CLASSIC_GPP_ADVANCED_STRATEGY_ID = "classic_gpp_slate_aware_v1";
export const SHOWDOWN_CASH_BASELINE_STRATEGY_ID = "showdown_cash_baseline_v1";
export const SHOWDOWN_GPP_BASELINE_STRATEGY_ID = "showdown_gpp_baseline_v1";

export type ClassicGppStrategyId =
  | typeof CLASSIC_GPP_BASELINE_STRATEGY_ID
  | typeof CLASSIC_GPP_ADVANCED_STRATEGY_ID;

export const CLASSIC_GPP_STRATEGIES: ReadonlyArray<{
  id: ClassicGppStrategyId;
  label: string;
  detail: string;
}> = [
  {
    id: CLASSIC_GPP_BASELINE_STRATEGY_ID,
    label: "Legacy baseline · v1",
    detail: "P90/leverage ILP with the production double-stack policy.",
  },
  {
    id: CLASSIC_GPP_ADVANCED_STRATEGY_ID,
    label: "Slate-aware GPP · v1",
    detail: "Ownership templates, correlation, leverage, uniqueness, and exposure controls.",
  },
];

export function optimizerStrategyId(
  contestFormat: "classic" | "showdown",
  objective: "cash" | "gpp",
  classicGppStrategy: ClassicGppStrategyId,
): string {
  if (contestFormat === "classic") {
    return objective === "gpp" ? classicGppStrategy : "gpp";
  }
  return objective === "cash"
    ? SHOWDOWN_CASH_BASELINE_STRATEGY_ID
    : SHOWDOWN_GPP_BASELINE_STRATEGY_ID;
}
