import { createElement, type ReactNode } from "react";
import { headingId, inlineTokens, parseReportMarkdown, safeExternalUrl, type ReportLink } from "./analystReportLibrary";

export function AnalystReportMarkdown({ markdown, links, onReport, onEvidence }: { markdown: string; links: ReportLink[]; onReport: (id: string) => void; onEvidence: (id: string) => void }) {
  const inline = (text: string): ReactNode => inlineTokens(text).map((token, index) => {
    if (token.kind === "strong") return <strong key={index}>{token.text}</strong>;
    if (token.kind === "emphasis") return <em key={index}>{token.text}</em>;
    if (token.kind === "code") return <code key={index}>{token.text}</code>;
    if (token.kind !== "link") return token.text;
    const external = safeExternalUrl(token.target);
    if (external) return <a key={index} href={external} target="_blank" rel="noopener noreferrer">{token.text}</a>;
    if (/^#[a-zA-Z0-9_-]+$/.test(token.target)) return <a key={index} href={token.target}>{token.text}</a>;
    const link = links.find(l => l.target === token.target);
    if (link?.kind === "report" && link.report_id) return <button key={index} className="report-inline-link" onClick={() => onReport(link.report_id!)}>{token.text}</button>;
    if (link?.kind === "evidence" && link.evidence_id) return <button key={index} className="report-inline-link" onClick={() => onEvidence(link.evidence_id!)}>{token.text}</button>;
    return <span key={index} className="report-unavailable-link" title={`Local reference is not included in this read-only library: ${token.target}`}>{token.text} <small>(local reference unavailable)</small></span>;
  });
  const headingCounts = new Map<string, number>(), usedHeadingIds = new Set<string>();
  return <article className="report-markdown">{parseReportMarkdown(markdown).map((block, index) => {
    if (block.kind === "heading") {
      const base = headingId(block.text) || "report-heading";
      let count = headingCounts.get(base) ?? 0, id = count ? `${base}-${count}` : base;
      while (usedHeadingIds.has(id)) { count++; id = `${base}-${count}`; }
      headingCounts.set(base, count + 1);
      usedHeadingIds.add(id);
      return createElement(`h${block.level}`, { key: index, id }, inline(block.text));
    }
    if (block.kind === "rule") return <hr key={index} />;
    if (block.kind === "code") return <pre key={index}><code>{block.text}</code></pre>;
    if (block.kind === "quote") return <blockquote key={index}>{inline(block.text)}</blockquote>;
    if (block.kind === "paragraph") return <p key={index}>{inline(block.text)}</p>;
    if (block.kind === "list") return createElement(block.ordered ? "ol" : "ul", { key: index }, block.items.map((item, i) => <li key={i}>{inline(item)}</li>));
    if (block.kind === "table") return <div key={index} className="scroll-table"><table><thead><tr>{block.header.map((cell, i) => <th key={i}>{inline(cell)}</th>)}</tr></thead><tbody>{block.rows.map((row, i) => <tr key={i}>{block.header.map((_, j) => <td key={j}>{inline(row[j] ?? "")}</td>)}</tr>)}</tbody></table></div>;
    return null;
  })}</article>;
}
