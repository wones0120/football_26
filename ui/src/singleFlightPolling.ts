export function startSingleFlightPolling<T>(options: {
  fetch: () => Promise<T>; onValue: (value: T) => void; onError: (error: unknown) => void;
  intervalMs?: number | ((value: T | undefined) => number); maxDelayMs?: number;
  isVisible?: () => boolean;
  subscribeVisibility?: (callback: () => void) => () => void;
  schedule?: (callback: () => void, delay: number) => unknown;
  cancel?: (timer: unknown) => void; now?: () => number;
}) {
  const maxDelay = options.maxDelayMs ?? 60_000;
  const schedule = options.schedule ?? ((callback, delay) => window.setTimeout(callback, delay));
  const cancel = options.cancel ?? ((timer) => window.clearTimeout(timer as number));
  const now = options.now ?? Date.now;
  const visible = options.isVisible ?? (() => typeof document === "undefined" || !document.hidden);
  const subscribe = options.subscribeVisibility ?? (callback => {
    if (typeof document === "undefined") return () => {};
    document.addEventListener("visibilitychange", callback);
    return () => document.removeEventListener("visibilitychange", callback);
  });
  let stopped = false;
  let timer: unknown;
  let pending: Promise<T> | null = null;
  let failures = 0;
  let lastValue: T | undefined;
  const refresh = (): Promise<T> => {
    if (pending) return pending;
    if (stopped) return Promise.reject(new Error("Polling stopped"));
    if (timer != null) { cancel(timer); timer = undefined; }
    const started = now();
    pending = Promise.resolve().then(options.fetch).then(value => {
      failures = 0;
      lastValue = value;
      if (!stopped) options.onValue(value);
      return value;
    }).catch(error => {
      failures += 1;
      if (!stopped) options.onError(error);
      throw error;
    }).finally(() => {
      pending = null;
      if (!stopped && visible()) {
        const interval = typeof options.intervalMs === "function" ? options.intervalMs(lastValue) : options.intervalMs ?? 2500;
        const delay = Math.min(maxDelay, Math.max(interval * 2 ** Math.min(failures, 4), (now() - started) * 1.5));
        timer = schedule(() => { void refresh().catch(() => {}); }, delay);
      }
    });
    return pending;
  };
  const unsubscribe = subscribe(() => {
    if (timer != null) { cancel(timer); timer = undefined; }
    if (!stopped && visible()) void refresh().catch(() => {});
  });
  if (visible()) void refresh().catch(() => {});
  return { refresh, stop: () => { stopped = true; if (timer != null) cancel(timer); unsubscribe(); } };
}
