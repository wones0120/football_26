import type { PreparationScope, PreparationStatus } from "./api";
const sameScope = (left: PreparationScope, right: PreparationScope) => left.season === right.season && left.week === right.week && left.slate.toUpperCase() === right.slate.toUpperCase();

// Direct action refreshes and background polls share one monotonic receipt clock.
export function nextPreparationStatus(current: PreparationStatus | null, next: PreparationStatus | null, active: PreparationScope): PreparationStatus | null {
  if (!next) return current && sameScope(current.scope, active) ? current : null;
  if (!sameScope(next.scope, active)) return current;
  if (current && sameScope(current.scope, active) && Date.parse(next.server_time) < Date.parse(current.server_time)) return current;
  return next;
}
