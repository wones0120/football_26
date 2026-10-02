export const CLASSIC_GPP_BASELINE_STRATEGY_ID = "classic_gpp_baseline_v1";
export const CLASSIC_GPP_ADVANCED_STRATEGY_ID = "classic_gpp_slate_aware_v1";
export const CLASSIC_HEAD_TO_HEAD_STRATEGY_ID = "classic_head_to_head_v1";
export const CLASSIC_LARGE_GPP_STRATEGY_ID = "classic_large_gpp_v1";
export const CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID = "classic_small_field_gpp";
export const CLASSIC_SMALL_FIELD_CANDIDATE_TARGET = 205;
export const SHOWDOWN_CASH_BASELINE_STRATEGY_ID = "showdown_cash_baseline_v1";
export const SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID =
  "showdown_cash_qb_captain_stack_v1";
export const SHOWDOWN_GPP_BASELINE_STRATEGY_ID = "showdown_gpp_baseline_v1";
export const SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID =
  "showdown_gpp_portfolio_v3";
export const SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID = "showdown_single_entry_gpp";
export const SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID = "showdown_single_entry_portfolio";
export const SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID = "showdown_3max_gpp";
export const SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID = "showdown_small_max_gpp";

export type ClassicGppStrategyId =
  | typeof CLASSIC_GPP_BASELINE_STRATEGY_ID
  | typeof CLASSIC_GPP_ADVANCED_STRATEGY_ID;

export type ClassicContestStrategyId =
  | typeof CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
  | typeof CLASSIC_LARGE_GPP_STRATEGY_ID
  | typeof CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID;

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
  {
    id: CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID,
    objective: "gpp",
    label: "Small-field GPP · diagnostic baseline",
    detail: "Classic GPP scoring with legal candidate generation, global selection, and construction diagnostics.",
  },
];

export function classicSmallFieldCandidateParams(longShotMode: boolean, slate: string, numLineups: number) {
  return longShotMode || slate !== "SUNDAY_MAIN" || numLineups !== 5 ? {} : {
    classic_candidate_pool_size: CLASSIC_SMALL_FIELD_CANDIDATE_TARGET,
    classic_production_candidate_pool_size: CLASSIC_SMALL_FIELD_CANDIDATE_TARGET,
  };
}

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
      classicStrategy === CLASSIC_LARGE_GPP_STRATEGY_ID ||
      classicStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID
    ) {
      return classicStrategy;
    }
    return objective === "gpp" ? classicStrategy : "gpp";
  }
  return objective === "cash"
    ? SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID
    : SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID;
}
