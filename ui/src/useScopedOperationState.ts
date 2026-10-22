import { useCallback, useRef, useState } from "react";
import { nextScopedOperationState, scopedOperationValue } from "./scopedOperationState";

export function useScopedOperationState<T>(scope: string, empty: T): [T, (value: T) => void] {
  const [state, setState] = useState({ scope, value: empty });
  const activeScope = useRef(scope);
  activeScope.current = scope;
  const update = useCallback((value: T) => {
    setState(current => nextScopedOperationState(current, scope, activeScope.current, value));
  }, [scope]);
  return [scopedOperationValue(state, scope, empty), update];
}
