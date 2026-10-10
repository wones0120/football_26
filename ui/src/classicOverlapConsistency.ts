import type { OptimizerResponse } from "./api";

// Called on the exact serialized string passed to fetch, before any submission.
export function assertPortfolioSummaryMatchesRequest(summaryParams: Record<string, number | null>, serializedRequest: string) {
  const request = JSON.parse(serializedRequest) as { params?: Record<string, unknown> };
  for (const key of ["num_lineups", "max_exposure", "max_lineups_per_primary_game", "max_lineup_overlap", "elevated_player_max_exposure", "max_elevated_players_per_lineup"]) {
    const expected = summaryParams[key] ?? null;
    // Default overlap intentionally sends explicit null; omission is a mismatch.
    const actual = key === "max_lineup_overlap" ? request.params?.[key] : request.params?.[key] ?? null;
    if (actual !== expected) {
      throw new Error(`Portfolio settings to submit mismatch: ${key} displays ${expected ?? "Strategy default"}, but serialized request contains ${String(actual)}. Submission blocked.`);
    }
  }
}

// Compare against the submitted snapshot, never the current editable form.
export function assertLargeGppOverlapResult(strategy: string, params: Record<string, unknown>, response: OptimizerResponse) {
  const requested = params.max_lineup_overlap;
  if (strategy !== "classic_large_gpp_v1" || requested == null) return;
  const contract = response.effective_strategy_contract;
  const row = response.portfolio_controls_report?.settings?.find(row => row.key === "max_lineup_overlap");
  const savedRequested = contract?.requested as Record<string, unknown> | undefined;
  const effective = contract?.effective as Record<string, unknown> | undefined;
  const sources = contract?.sources as Record<string, unknown> | undefined;
  if (savedRequested?.max_lineup_overlap !== requested
    || effective?.max_lineup_overlap !== requested
    || sources?.max_lineup_overlap !== "request"
    || row?.requested !== requested || row?.effective !== requested || row?.source !== "request"
    || typeof row?.achieved !== "number" || row.achieved > Number(requested)) {
    throw new Error(`Optimizer overlap consistency failure: submitted ${requested}; saved requested/effective/source/achieved disagree. Do not use this portfolio.`);
  }
  if (!Array.isArray(response.results)) throw new Error("Optimizer overlap consistency failure: saved rosters are missing.");
  const rosters = response.results.map((lineup: unknown) => {
    if (!Array.isArray(lineup)) throw new Error("Optimizer overlap consistency failure: invalid saved roster.");
    return new Set(lineup.map((player: { player_id?: unknown }) => {
      if (typeof player?.player_id !== "string" || !player.player_id) throw new Error("Optimizer overlap consistency failure: canonical player ID missing.");
      return player.player_id;
    }));
  });
  let achieved = 0;
  for (let i = 0; i < rosters.length; i++) for (let j = 0; j < i; j++) {
    achieved = Math.max(achieved, [...rosters[i]].filter(id => rosters[j].has(id)).length);
    if (achieved > Number(requested)) {
      throw new Error(`Optimizer overlap consistency failure: saved rosters exceed submitted cap ${requested}. Do not use this portfolio.`);
    }
  }
  if (achieved !== row.achieved) throw new Error("Optimizer overlap consistency failure: saved achieved value disagrees with canonical rosters.");
}
