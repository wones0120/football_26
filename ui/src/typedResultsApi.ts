export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);
  if (!response.ok) throw new Error(`Results could not be loaded (${response.status})`);
  return response.json() as Promise<T>;
}
