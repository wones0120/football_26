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

export function normalizeSlateId(slate: string) {
  return slate.trim().replaceAll(" ", "_").toUpperCase();
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
