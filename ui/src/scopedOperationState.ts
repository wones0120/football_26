export type ScopedOperationState<T> = { scope: string; value: T };

// A response belongs to the scope that submitted it, even after navigation.
export function nextScopedOperationState<T>(current: ScopedOperationState<T>, submittedScope: string,
  activeScope: string, value: T): ScopedOperationState<T> {
  return submittedScope === activeScope ? { scope: submittedScope, value } : current;
}

export function scopedOperationValue<T>(state: ScopedOperationState<T>, activeScope: string, empty: T): T {
  return state.scope === activeScope ? state.value : empty;
}
