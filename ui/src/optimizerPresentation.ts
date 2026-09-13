export type OptimizerContextReadiness = {
  scored_count?: number;
  context_evaluable_count?: number;
  offensive_player_count?: number;
  market_context_count?: number;
  adjusted_count?: number;
};

export function contextReadinessLabel(
  context: OptimizerContextReadiness | null | undefined,
): string {
  if (!context) return "Context readiness: unavailable";
  const ready = context?.context_evaluable_count ?? context?.scored_count ?? 0;
  const readyLabel =
    context.offensive_player_count === undefined
      ? String(ready)
      : `${ready}/${context.offensive_player_count}`;
  const marketReady = context?.market_context_count ?? 0;
  const adjusted = context?.adjusted_count ?? 0;
  return `Context-ready: ${readyLabel} · Market-ready: ${marketReady} · Adjusted: ${adjusted}`;
}

export function individualCeilingSummary(lineup: unknown[]): {
  label: "Individual Ceiling Sum";
  value: number;
} {
  const first = lineup[0] as
    | { lineup_ceiling_summary?: { value?: unknown } }
    | undefined;
  const persistedValue = Number(first?.lineup_ceiling_summary?.value);
  const hasPersistedValue =
    first?.lineup_ceiling_summary?.value !== null &&
    first?.lineup_ceiling_summary?.value !== undefined &&
    Number.isFinite(persistedValue);
  const value = hasPersistedValue
    ? persistedValue
    : lineup.reduce<number>((sum, player) => {
        const row = player as {
          p90?: unknown;
          predicted_p90?: unknown;
          projection?: unknown;
        };
        const ceiling = Number(row.p90 ?? row.predicted_p90 ?? row.projection);
        return sum + (Number.isFinite(ceiling) ? ceiling : 0);
      }, 0);
  return { label: "Individual Ceiling Sum", value };
}
