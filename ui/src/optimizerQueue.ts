export function isOptimizerTransportError(error: unknown): boolean {
  return error instanceof Error && /^(Request timed out while contacting|Could not reach the backend API)/.test(error.message);
}

// The caller must reuse its existing run ID and identical payload. Retrying a
// lost receipt then recovers the same durable job instead of starting a solve.
export async function recoverOptimizerReceipt<T>(submit: () => Promise<T>): Promise<T> {
  try { return await submit(); }
  catch (error) {
    if (!isOptimizerTransportError(error)) throw error;
    return submit();
  }
}
