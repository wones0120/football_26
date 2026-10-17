export async function fetchNativeLineupCsv(url: string, fallbackFilename: string, headers: string[]) {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.text();
    let message = body;
    try { const parsed = JSON.parse(body); message = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail || parsed); } catch { /* Non-JSON server error. */ }
    throw new Error(message || `Download failed (${response.status})`);
  }
  if (!response.headers.get("Content-Type")?.toLowerCase().includes("text/csv")) {
    throw new Error("The server did not return a CSV. Please retry; no file was downloaded.");
  }
  const text = await response.text();
  if (text.replace(/^\uFEFF/, "").split(/\r?\n/, 1)[0] !== headers.join(",")) {
    throw new Error("The CSV format does not match this lineup. No file was downloaded.");
  }
  const supplied = response.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/i)?.[1];
  const filename = supplied?.toLowerCase().endsWith(".csv") ? supplied.replace(/[\/\\]/g, "_") : fallbackFilename;
  return { blob: new Blob([text], { type: "text/csv;charset=utf-8" }), filename };
}

export async function downloadNativeLineupCsv(url: string, fallbackFilename: string, headers: string[]) {
  const { blob, filename } = await fetchNativeLineupCsv(url, fallbackFilename, headers);
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
