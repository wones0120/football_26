export const CLASSIC_GPP_BASELINE_STRATEGY_ID = "classic_gpp_baseline_v1";
export const CLASSIC_GPP_ADVANCED_STRATEGY_ID = "classic_gpp_slate_aware_v1";
export const CLASSIC_HEAD_TO_HEAD_STRATEGY_ID = "classic_head_to_head_v1";
export const CLASSIC_LARGE_GPP_STRATEGY_ID = "classic_large_gpp_v1";
export const SHOWDOWN_CASH_BASELINE_STRATEGY_ID = "showdown_cash_baseline_v1";
export const SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID =
  "showdown_cash_qb_captain_stack_v1";
export const SHOWDOWN_GPP_BASELINE_STRATEGY_ID = "showdown_gpp_baseline_v1";
export const SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID =
  "showdown_gpp_captain_informed_v2";

export type ClassicGppStrategyId =
  | typeof CLASSIC_GPP_BASELINE_STRATEGY_ID
  | typeof CLASSIC_GPP_ADVANCED_STRATEGY_ID;

export type ClassicContestStrategyId =
  | typeof CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
  | typeof CLASSIC_LARGE_GPP_STRATEGY_ID;

export const CLASSIC_CONTEST_STRATEGIES: ReadonlyArray<{
  id: ClassicContestStrategyId;
  objective: "cash" | "gpp";
  label: string;
  detail: string;
}> = [
  {
    id: CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
    objective: "cash",
    label: "Head-to-Head",
    detail: "Broad player pool; projected mean dominates, with ceiling and floor as secondary signals.",
  },
  {
    id: CLASSIC_LARGE_GPP_STRATEGY_ID,
    objective: "gpp",
    label: "Large GPP",
    detail: "Ceiling-weighted portfolio with flexible stacks, exposure limits, and lineup uniqueness.",
  },
];

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
  classicStrategy: ClassicGppStrategyId | ClassicContestStrategyId,
): string {
  if (contestFormat === "classic") {
    if (
      classicStrategy === CLASSIC_HEAD_TO_HEAD_STRATEGY_ID ||
      classicStrategy === CLASSIC_LARGE_GPP_STRATEGY_ID
    ) {
      return classicStrategy;
    }
    return objective === "gpp" ? classicStrategy : "gpp";
  }
  return objective === "cash"
    ? SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID
    : SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID;
}
