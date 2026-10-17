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
export const RUN_SELECTIONS_STORAGE_KEY = "football-26-run-selections";

export function parsePersistedRunSelections(raw: string | null): PersistedRunSelections {
  try {
    const value = JSON.parse(raw ?? "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const selections: PersistedRunSelections = {};
    const fields = ["projectionRunId", "slateSimulationRunId", "researchSimulationRunId", "researchBaselineRunId", "optimizerRunId"];
    for (const [key, selection] of Object.entries(value)) {
      const [season, week, slate] = key.split(":");
      const scope = parsePersistedActiveSlateContext(JSON.stringify({ season: Number(season), week: Number(week), slate }));
      if (!scope || !selection || typeof selection !== "object" || Array.isArray(selection)) continue;
      selections[slateContextKey(scope)] = Object.fromEntries(Object.entries(selection).filter(([field, id]) =>
        fields.includes(field) && typeof id === "string" && id.trim().length > 0 && id.length <= 128));
    }
    return selections;
  } catch { return {}; }
}

export const SLATE_OPTIONS = [
  "WEDNESDAY_NIGHT",
  "THURSDAY_NIGHT",
  "FRIDAY_NIGHT",
  "SATURDAY_NIGHT",
  "SUNDAY_MORNING",
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

export function defaultContestFormatForSlate(slate: string): "classic" | "showdown" {
  return ["THURSDAY_NIGHT", "SUNDAY_MORNING", "SUNDAY_NIGHT", "MONDAY_NIGHT"].includes(normalizeSlateId(slate))
    ? "showdown" : "classic";
}

// Native/imported slates may have more than one game offering on the same day.
// Labels are identifiers, never evidence that a slate is prepared or playable.
export function isValidSlateId(slate: string) {
  return /^[A-Z0-9][A-Z0-9_-]{0,63}$/.test(normalizeSlateId(slate))
    && !["UNKNOWN", "DEFAULT"].includes(normalizeSlateId(slate));
}

export function availableSlateOptions(current: string, discovered: string[] = []) {
  return [...new Set([...SLATE_OPTIONS, current, ...discovered].map(normalizeSlateId).filter(isValidSlateId))];
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
      || !isValidSlateId(slate)
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
