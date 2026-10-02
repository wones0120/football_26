export type ActiveSlateContext = {
  season: number;
  week: number;
  slate: string;
};

export type PersistedRunSelection = {
  projectionRunId?: string;
  slateSimulationRunId?: string;
  researchSimulationRunId?: string;
  researchBaselineRunId?: string;
  optimizerRunId?: string;
};

export type PersistedRunSelections = Record<string, PersistedRunSelection>;

export const DEFAULT_SLATE = "WEDNESDAY_NIGHT";
export const ACTIVE_SLATE_CONTEXT_STORAGE_KEY = "football-26-active-slate-context";

export const SLATE_OPTIONS = [
  "WEDNESDAY_NIGHT",
  "THURSDAY_NIGHT",
  "FRIDAY_NIGHT",
  "SATURDAY_NIGHT",
  "SUNDAY_MAIN",
  "SUNDAY_EARLY",
  "SUNDAY_LATE",
  "SUNDAY_NIGHT",
  "SUNDAY_MONDAY",
  "MONDAY_NIGHT",
  "TUESDAY_NIGHT",
];

export function normalizeSlateId(slate: string) {
  return slate.trim().replaceAll(" ", "_").toUpperCase();
}

export function parsePersistedActiveSlateContext(rawValue: string | null): ActiveSlateContext | null {
  if (!rawValue) return null;
  try {
    const value = JSON.parse(rawValue) as Partial<ActiveSlateContext>;
    const slate = typeof value.slate === "string" ? normalizeSlateId(value.slate) : "";
    if (
      !Number.isInteger(value.season)
      || Number(value.season) < 1900
      || Number(value.season) > 2200
      || !Number.isInteger(value.week)
      || Number(value.week) < 1
      || Number(value.week) > 25
      || !SLATE_OPTIONS.includes(slate)
    ) {
      return null;
    }
    return { season: Number(value.season), week: Number(value.week), slate };
  } catch {
    return null;
  }
}

export function serializeActiveSlateContext(context: ActiveSlateContext) {
  return JSON.stringify({
    season: context.season,
    week: context.week,
    slate: normalizeSlateId(context.slate),
  });
}

export function researchSlateId(slate: string) {
  return normalizeSlateId(slate).toLowerCase();
}

export function slateContextKey(context: ActiveSlateContext) {
  return `${context.season}:${context.week}:${normalizeSlateId(context.slate)}`;
}

export function updateRunSelection(
  selections: PersistedRunSelections,
  context: ActiveSlateContext,
  patch: Partial<PersistedRunSelection>,
): PersistedRunSelections {
  const key = slateContextKey(context);
  const nextSelection = { ...selections[key], ...patch };
  const cleanedSelection = Object.fromEntries(
    Object.entries(nextSelection).filter(([, value]) => Boolean(value)),
  ) as PersistedRunSelection;
  return { ...selections, [key]: cleanedSelection };
}
