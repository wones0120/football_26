import { parsePersistedActiveSlateContext, type ActiveSlateContext } from "./workspaceContext.ts";

export const LEARNING_CONTEXT_STORAGE_KEY = "football-26-learning-context";
export const ALL_LEARNING_SLATES = "ALL";

// Review context starts from the live week once, then has its own persistence.
export function initialLearningContext(active: ActiveSlateContext): ActiveSlateContext {
  return { season: active.season, week: active.week, slate: ALL_LEARNING_SLATES };
}

export const parseLearningContext = parsePersistedActiveSlateContext;
