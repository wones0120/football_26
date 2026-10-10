export function startSingleFlightPolling<T>(options: {
  fetch: () => Promise<T>; onValue: (value: T) => void; onError: (error: unknown) => void;
  intervalMs?: number; maxDelayMs?: number;
  schedule?: (callback: () => void, delay: number) => unknown;
  cancel?: (timer: unknown) => void; now?: () => number;
}) {
  const interval = options.intervalMs ?? 2500;
  const maxDelay = options.maxDelayMs ?? 30_000;
  const schedule = options.schedule ?? ((callback, delay) => window.setTimeout(callback, delay));
  const cancel = options.cancel ?? ((timer) => window.clearTimeout(timer as number));
  const now = options.now ?? Date.now;
  let stopped = false;
  let timer: unknown;
  let pending: Promise<T> | null = null;
  let failures = 0;
  const refresh = (): Promise<T> => {
    if (pending) return pending;
    if (stopped) return Promise.reject(new Error("Polling stopped"));
    if (timer != null) { cancel(timer); timer = undefined; }
    const started = now();
    pending = Promise.resolve().then(options.fetch).then(value => {
      failures = 0;
      if (!stopped) options.onValue(value);
      return value;
    }).catch(error => {
      failures += 1;
      if (!stopped) options.onError(error);
      throw error;
    }).finally(() => {
      pending = null;
      if (!stopped) {
        const delay = Math.min(maxDelay, Math.max(interval * 2 ** Math.min(failures, 4), (now() - started) * 1.5));
        timer = schedule(() => { void refresh().catch(() => {}); }, delay);
      }
    });
    return pending;
  };
  void refresh().catch(() => {});
  return { refresh, stop: () => { stopped = true; if (timer != null) cancel(timer); } };
}
