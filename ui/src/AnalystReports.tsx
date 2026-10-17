import { AnalystReportMarkdown } from "./AnalystReportMarkdown";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchAnalystReport, fetchAnalystReportEvidence, fetchAnalystReports } from "./api";
import { filteredReports, reportApplicationLabel, selectedReportId, type AnalystReport, type AnalystReportContent, type ReportEvidence, type ReportFilters } from "./analystReportLibrary";
import "./AnalystReports.css";

const categories = { briefing: "Main briefings", specialist: "Specialist reports", lineup_review: "Saved lineup reviews" };
const emptyFilters: ReportFilters = { week: "", slate: "", category: "" };
export function AnalystReports() {
  const [reports, setReports] = useState<AnalystReport[]>([]), [filters, setFilters] = useState(emptyFilters);
  const [selected, setSelected] = useState<string | null>(null), [content, setContent] = useState<AnalystReportContent | null>(null);
  const [evidence, setEvidence] = useState<ReportEvidence | null>(null), [error, setError] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true), [reading, setReading] = useState(false), [refresh, setRefresh] = useState(0);
  const evidenceSequence = useRef(0);
  useEffect(() => {
    let cancelled = false; setCatalogLoading(true); setError(null);
    fetchAnalystReports().then(result => { if (!cancelled) setReports(result.rows); }).catch(err => { if (!cancelled) setError(String(err.message ?? err)); }).finally(() => { if (!cancelled) setCatalogLoading(false); });
    return () => { cancelled = true; };
  }, [refresh]);
  const visible = useMemo(() => filteredReports(reports, filters), [reports, filters]);
  const reportId = selectedReportId(visible, selected);
  useEffect(() => {
    let cancelled = false; evidenceSequence.current++; setContent(null); setEvidence(null); setError(null);
    if (!reportId) { setReading(false); return; }
    setReading(true);
    fetchAnalystReport(reportId).then(result => { if (!cancelled) setContent(result); }).catch(err => { if (!cancelled) setError(String(err.message ?? err)); }).finally(() => { if (!cancelled) setReading(false); });
    return () => { cancelled = true; };
  }, [reportId, refresh]);
  const choose = (id: string) => { evidenceSequence.current++; setReading(false); if (!visible.some(r => r.report_id === id)) setFilters(emptyFilters); setSelected(id); setEvidence(null); };
  const openEvidence = async (id: string) => {
    if (!content) return; const sequence = ++evidenceSequence.current; setReading(true); setError(null);
    try { const result = await fetchAnalystReportEvidence(content.report.report_id, id); if (sequence === evidenceSequence.current) setEvidence(result); }
    catch (err) { if (sequence === evidenceSequence.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (sequence === evidenceSequence.current) setReading(false); }
  };
  const weeks = [...new Set(reports.filter(r => r.season != null && r.week != null).map(r => `${r.season}-W${r.week}`))].sort().reverse();
  const slates = [...new Set(reports.flatMap(r => r.slates))].sort();
  return <section className="analyst-reports" aria-label="Analyst Reports">
    <div className="report-library-intro"><h2>Analyst Reports</h2><p>Read the main football briefing, specialist research and saved lineup reviews. Reading a report does not apply it to an optimizer run.</p><button onClick={() => setRefresh(r => r + 1)} disabled={catalogLoading}>Refresh report list</button></div>
    <div className="report-library-filters">
      <label>Week<select value={filters.week} onChange={e => setFilters(f => ({ ...f, week: e.target.value }))}><option value="">All weeks</option>{weeks.map(w => <option key={w} value={w}>{w.replace("-W", " · Week ")}</option>)}</select></label>
      <label>Slate<select value={filters.slate} onChange={e => setFilters(f => ({ ...f, slate: e.target.value }))}><option value="">All slates</option>{slates.map(s => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</select></label>
      <label>Report type<select value={filters.category} onChange={e => setFilters(f => ({ ...f, category: e.target.value }))}><option value="">All reports</option>{Object.entries(categories).map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>
    </div>
    {catalogLoading && <p role="status">Loading report library…</p>}
    {error && <p role="alert" className="report-library-error">{error}</p>}
    {!catalogLoading && !visible.length && <p>No reports match these filters. Choose All weeks or All slates to browse the library.</p>}
    <div className="report-library-layout">
      <nav className="report-library-list" aria-label="Available Analyst reports">{Object.entries(categories).map(([category, title]) => {
        const group = visible.filter(r => r.category === category); if (!group.length) return null;
        return <section key={category}><h3>{title}</h3>{group.map(r => <button key={r.report_id} className={r.report_id === reportId ? "report-card selected" : "report-card"} aria-pressed={r.report_id === reportId} disabled={!r.available} onClick={() => choose(r.report_id)}><strong>{r.title}</strong><span>{r.season ?? "Season unknown"} · {r.week != null ? `W${r.week}` : "Week unknown"} · {r.version}</span><span>{r.recorded_at ? `Recorded ${new Date(r.recorded_at).toLocaleString()}` : "Date not recorded"}{r.preliminary === true ? " · Preliminary" : r.preliminary === false ? " · Final research" : ""}</span><span>{r.summary}</span>{!r.available && <span>Report file unavailable</span>}</button>)}</section>;
      })}</nav>
      <div className="report-library-reader" aria-live="polite" aria-busy={reading}>
        {reading && <p role="status">Loading report text…</p>}
        {content && <><header className="report-reader-meta"><h2>{content.report.title}</h2><p>{reportApplicationLabel(content.report)}. {content.report.preliminary === true && <strong>Preliminary; this is not entry clearance.</strong>}</p>{content.report.saved_run_ids.length > 0 && <details><summary>Saved run identifiers</summary>{content.report.saved_run_ids.map(id => <p key={id}><code>{id}</code></p>)}</details>}</header>
          {evidence ? <section><button onClick={() => { evidenceSequence.current++; setEvidence(null); setReading(false); }}>Back to report</button><h3>{evidence.label}</h3><p>Read-only source text</p><pre className="report-evidence">{evidence.content}</pre></section> : <AnalystReportMarkdown markdown={content.markdown} links={content.links} onReport={choose} onEvidence={id => void openEvidence(id)} />}</>}
      </div>
    </div>
  </section>;
}
