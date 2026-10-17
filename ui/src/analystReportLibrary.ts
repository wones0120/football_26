export type AnalystReport = {
  report_id: string; title: string; category: "briefing" | "specialist" | "lineup_review";
  season: number | null; week: number | null; slates: string[]; version: string;
  recorded_at: string | null; preliminary: boolean | null;
  application_status: "research_only" | "saved_run_comparison" | "unknown";
  saved_run_ids: string[]; summary: string; available: boolean;
};
export type ReportLink = { target: string; kind: "report" | "evidence" | "unavailable"; report_id?: string; evidence_id?: string; fragment?: string };
export type AnalystReportContent = { report: AnalystReport; markdown: string; sha256: string; links: ReportLink[] };
export type ReportEvidence = { report_id: string; evidence_id: string; label: string; content: string; sha256: string };
export type ReportFilters = { week: string; slate: string; category: string };
const CATEGORY_ORDER = { briefing: 0, specialist: 1, lineup_review: 2 };
export function filteredReports(reports: AnalystReport[], filters: ReportFilters): AnalystReport[] {
  return reports.filter(r => (!filters.week || `${r.season}-W${r.week}` === filters.week) && (!filters.slate || r.slates.includes(filters.slate)) && (!filters.category || r.category === filters.category))
    .sort((a, b) => CATEGORY_ORDER[a.category] - CATEGORY_ORDER[b.category] || (Date.parse(b.recorded_at ?? "") || 0) - (Date.parse(a.recorded_at ?? "") || 0) || a.title.localeCompare(b.title));
}
export function selectedReportId(reports: AnalystReport[], selected: string | null): string | null {
  return reports.some(r => r.report_id === selected && r.available) ? selected : reports.find(r => r.available)?.report_id ?? null;
}
export function reportApplicationLabel(report: AnalystReport): string {
  return report.application_status === "saved_run_comparison" ? "Documents applied analysis in the listed saved comparison runs" : report.application_status === "research_only" ? "Readable research — not applied by reading" : "Application status not recorded";
}
export function safeExternalUrl(target: string): string | null {
  try { const url = new URL(target); return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch { return null; }
}
export function headingId(text: string): string { return text.toLowerCase().replace(/[^a-z0-9\s-]/g, "").trim().replace(/\s+/g, "-"); }
export type MarkdownBlock = { kind: "heading"; level: number; text: string } | { kind: "paragraph" | "quote" | "code"; text: string } | { kind: "list"; ordered: boolean; items: string[] } | { kind: "table"; header: string[]; rows: string[][] } | { kind: "rule" };
function tableCells(line: string): string[] { return line.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, "|")); }
export function parseReportMarkdown(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n"), blocks: MarkdownBlock[] = [];
  const isStart = (i: number) => /^(#{1,6}\s|```|>\s?|\s*[-*+]\s|\s*\d+\.\s|\s*([-*_])\1\1+\s*$)/.test(lines[i] ?? "") || (lines[i]?.includes("|") && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1] ?? ""));
  for (let i = 0; i < lines.length;) {
    const line = lines[i]; if (!line.trim()) { i++; continue; }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) { blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] }); i++; continue; }
    if (/^```/.test(line)) { const text: string[] = []; i++; while (i < lines.length && !/^```/.test(lines[i])) text.push(lines[i++]); i++; blocks.push({ kind: "code", text: text.join("\n") }); continue; }
    if (/^\s*([-*_])\1\1+\s*$/.test(line)) { blocks.push({ kind: "rule" }); i++; continue; }
    if (line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1] ?? "")) { const header = tableCells(line), rows: string[][] = []; i += 2; while (i < lines.length && lines[i].trim() && lines[i].includes("|")) rows.push(tableCells(lines[i++])); blocks.push({ kind: "table", header, rows }); continue; }
    const list = /^\s*(?:([-*+])|\d+\.)\s+(.*)$/.exec(line);
    if (list) { const ordered = !list[1], items: string[] = []; while (i < lines.length) { const item = /^\s*(?:([-*+])|\d+\.)\s+(.*)$/.exec(lines[i]); if (!item || !item[1] !== ordered) break; items.push(item[2]); i++; } blocks.push({ kind: "list", ordered, items }); continue; }
    if (/^>/.test(line)) { const text: string[] = []; while (i < lines.length && /^>/.test(lines[i])) text.push(lines[i++].replace(/^>\s?/, "")); blocks.push({ kind: "quote", text: text.join(" ") }); continue; }
    const text = [line]; i++; while (i < lines.length && lines[i].trim() && !isStart(i)) text.push(lines[i++]); blocks.push({ kind: "paragraph", text: text.join(" ") });
  }
  return blocks;
}
export type InlineToken = { kind: "text" | "strong" | "emphasis" | "code"; text: string } | { kind: "link"; text: string; target: string };
export function inlineTokens(text: string): InlineToken[] {
  const tokens: InlineToken[] = [], pattern = /\[([^\]]+)\]\(([^\s)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) { const at = match.index!; if (at > cursor) tokens.push({ kind: "text", text: text.slice(cursor, at) }); tokens.push(match[1] !== undefined ? { kind: "link", text: match[1], target: match[2] } : match[3] !== undefined ? { kind: "code", text: match[3] } : match[4] !== undefined ? { kind: "strong", text: match[4] } : { kind: "emphasis", text: match[5] }); cursor = at + match[0].length; }
  if (cursor < text.length) tokens.push({ kind: "text", text: text.slice(cursor) });
  return tokens;
}
