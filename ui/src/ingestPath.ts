/** Resolve a local CSV path while keeping the source filename visible to the user. */
export function resolveCsvIngestPath(input: string, expectedFilename: string): string | null {
  const path = input.trim();
  if (!path) return null;
  if (path === "~/NFL" || path.endsWith("/")) {
    return `${path.replace(/\/$/, "")}/${expectedFilename}`;
  }
  const basename = path.split("/").pop() ?? "";
  if (!basename) return null;
  if (/\.csv$/i.test(basename)) return path;
  if (!basename.includes(".")) return `${path}.csv`;
  return null;
}
