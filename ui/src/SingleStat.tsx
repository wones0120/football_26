import { useEffect, useState } from "react";
import "./SingleStat.css";
import { downloadNativeLineupCsv } from "./nativeLineupDownload";

type Player = { source_player_id: string; player_master_id: string | null; name?: string; team?: string; native_status?: string; status_evidence?: {status:string}; value?: number | null; expected_metric?: number | null; missing_components?: string[]; reason_codes?: string[]; forecast?: { components: Record<string, number | null>; sample_games: number; warning: string } };
type RecordRow = { sha256: string; kind: string; variant: string; game_set_id: string; classification: string; created_at: string };
type Saved = RecordRow & { players: Player[]; expected_metric?: number; actual_metric?: number | null; units?: string; objective?: string; assumptions?: string[]; pool_sha256?: string; current_readiness?: { status: string; reason_codes: string[]; players: Player[] }; export: { reason: string }; forecast_coverage?: string; pool_classification?: string; source_provenance?: {source_reference?: string}; source?: {source_name?: string}; objective_scope?: string; excluded_players?: Player[]; rules: unknown };
const BASE = `${import.meta.env.VITE_API_BASE_URL || "/api"}/single-stat`;
async function request(path: string, payload?: unknown) {
  const response = await fetch(BASE + path, payload === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
  return body;
}
const label = (value: string) => value.replaceAll("_", " ");

export function SingleStat() {
  const [rows, setRows] = useState<RecordRow[]>([]);
  const [selected, setSelected] = useState<Saved | null>(null);
  const [input, setInput] = useState("");
  const [actualInput, setActualInput] = useState("");
  const [templateText, setTemplateText] = useState("");
  const [templateName, setTemplateName] = useState("DraftKings Single Stat template.csv");
  const [csvReady, setCsvReady] = useState<{enabled:boolean; reason_codes:string[]; template_sha256:string|null; warning:string}|null>(null);
  const [incomplete, setIncomplete] = useState(false);
  const [partial, setPartial] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function refresh() { setRows((await request("/records")).rows.filter((row:RecordRow) => ["pool","report","actual_result"].includes(row.kind))); }
  useEffect(() => { refresh().catch(e => setError(String(e))); }, []);
  async function run(action: () => Promise<Saved>) {
    setBusy(true); setError("");
    try { setSelected(await action()); await refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  useEffect(() => {
    let active=true;
    setCsvReady(null);
    if (selected?.kind === "report") request(`/records/${selected.sha256}/export-readiness`).then(value => {if(active)setCsvReady(value);}).catch(e => {if(active)setError(String(e));});
    return () => {active=false;};
  }, [selected?.sha256]);
  async function verifyTemplate() {
    if (!selected?.pool_sha256) return;
    setBusy(true); setError("");
    try {
      await request("/templates", {pool_sha256:selected.pool_sha256,source_name:templateName,source_reference:templateName,source_observed_at:new Date().toISOString(),template_csv:templateText});
      setCsvReady(await request(`/records/${selected.sha256}/export-readiness`));
    } catch (e) {setError(String(e));} finally {setBusy(false);}
  }
  const players = selected?.current_readiness?.players || selected?.players || [];
  return <section className="single-stat" aria-label="Single Stat workspace">
    <header><h2>NFL Single Stat</h2><p>Touchdowns · Total Yards · Passing Yards. Select exactly three distinct players from the actual contest pool, representing at least two NFL teams. No salary cap or position requirement.</p></header>
    <div className="single-stat-grid"><section className="panel"><h3>Import native contest pool</h3>
      <p>Upload a Single Stat evidence package containing the unchanged native CSV, its column mapping, exact Game Set and provider status clocks. Classic and Showdown pools cannot establish Single Stat eligibility.</p>
      <p>Import the actual Single Stat contest pool. Missing identity or stat history is shown explicitly. Forecasts use the last three observed games available before the source cutoff; they do not use fantasy-point projections.</p>
      <label>Evidence package JSON<input aria-label="Evidence package JSON file" type="file" accept=".json,application/json" disabled={busy} onChange={async e => { const file = e.target.files?.[0]; if (file) setInput(await file.text()); }} /></label>
      <label>Package contents<textarea aria-label="Single Stat package contents" value={input} onChange={e => setInput(e.target.value)} placeholder="Paste a Single Stat evidence package JSON" rows={8} /></label>
      <button disabled={busy || !input.trim()} onClick={() => run(async () => request("/pools", JSON.parse(input)))}>Import and check readiness</button>
      <p><a href="https://support.draftkings.com/dk/en-us/game-style-single-stat?id=kb_article_view&sysparm_article=KB0010273" target="_blank" rel="noreferrer">DraftKings Single Stat overview</a> · Package specification: docs/product/single_stat.md</p>
    </section><section className="panel"><h3>Saved pools and reports</h3>
      <button disabled={busy} onClick={() => refresh().catch(e => setError(String(e)))}>Refresh library</button>
      {rows.length === 0 && <p>No Single Stat imports yet. Supply the actual contest pool to start.</p>}
      <ul>{rows.map(row => <li key={row.sha256}><button disabled={busy} onClick={() => run(() => request(`/records/${row.sha256}`))}>{label(row.variant)} · {row.game_set_id} · {row.kind} · {row.sha256.slice(0, 8)}</button><small>{row.classification}</small></li>)}</ul>
    </section></div>
    {busy && <p role="status">Processing Single Stat evidence…</p>}{error && <p role="alert">{error}</p>}
    {selected && <section className="panel"><h3>{label(selected.variant)} · {selected.game_set_id}</h3>
      <p><strong>{selected.classification}</strong>{selected.pool_classification && ` · Source pool: ${selected.pool_classification}`} · {selected.sha256.slice(0, 12)} · {selected.current_readiness?.status || "Saved research report"}</p>
      <p>{selected.source?.source_name || selected.source_provenance?.source_reference}</p>
      {selected.objective_scope && <p><strong>Ranking scope: {label(selected.objective_scope)}</strong> · {selected.excluded_players?.length || 0} players excluded with preserved reasons in the evidence report.</p>}
      {selected.current_readiness && <><p>Blockers: {selected.current_readiness.reason_codes.join(", ") || "None for baseline research"}</p>
        {selected.variant === "touchdowns" && <label><input type="checkbox" checked={partial} onChange={e => setPartial(e.target.checked)} />Allow explicitly partial touchdown research: optimize measured categories; unsupported return, fumble and defensive TD categories remain unknown.</label>}
        <label><input type="checkbox" checked={incomplete} onChange={e => setIncomplete(e.target.checked)} />Allow research among measured players only. Unknown players remain excluded with explicit reasons; the complete pool optimum is unknown.</label>
        <button disabled={busy} onClick={() => run(() => request("/optimize", { pool_sha256: selected.sha256, allow_partial_touchdown_research: partial, allow_incomplete_pool_research: incomplete }))}>Generate highest expected stat lineup</button></>}
      {selected.expected_metric !== undefined && <p><strong>{selected.expected_metric.toFixed(3)} expected {selected.units}</strong> · {label(selected.objective || "")} · {selected.forecast_coverage}</p>}
      {selected.kind === "actual_result" && <p><strong>{selected.actual_metric == null ? "Unknown actual total: missing stat categories" : `${selected.actual_metric.toFixed(3)} actual ${selected.units}`}</strong></p>}
      <div className="single-stat-table"><table><thead><tr><th>Player / native ID</th><th>Team</th><th>Captured status</th><th>{selected.kind === "actual_result" ? "Actual stat" : "Expected stat"}</th><th>Measured history</th><th>Coverage / readiness</th></tr></thead><tbody>{players.map(p => <tr key={p.source_player_id}><td>{p.name || p.player_master_id}<small>{p.source_player_id} · {p.player_master_id || "Identity unresolved"}</small></td><td>{p.team || "Saved roster"}</td><td>{p.native_status || p.status_evidence?.status || "No designation"}</td><td>{(p.expected_metric ?? p.value) == null ? "Unknown" : (p.expected_metric ?? p.value)!.toFixed(3)}</td><td>{selected.kind === "actual_result" ? "Source attested" : `${p.forecast?.sample_games ?? 0} games`}</td><td>{[...(p.reason_codes || []), ...(p.missing_components || []).map(c => `Unknown ${label(c)}`)].join("; ") || "Requested categories covered"}</td></tr>)}</tbody></table></div>
      <p>Research only. Baseline estimates have no current injury/workload adjustment or calibrated uncertainty. Confirm current provider eligibility and lock status before any real contest decision.</p>
      {selected.kind === "report" ? <section aria-label="Verified Single Stat CSV download">
        <h4>Lineup CSV</h4>
        <p>Uses the player IDs from this pool. No extra template needed.</p>
        <details><summary>Optional template compatibility check</summary>
          <label>Native template CSV<input type="file" accept=".csv,text/csv" aria-label="Native template CSV file" onChange={async e=>{const file=e.target.files?.[0];if(file){setTemplateName(file.name);setTemplateText(await file.text());}}}/></label>
          <label>Template source name<input aria-label="Template source name" value={templateName} onChange={e=>setTemplateName(e.target.value)}/></label>
          <textarea aria-label="Native template CSV contents" rows={6} value={templateText} onChange={e=>setTemplateText(e.target.value)} placeholder="Paste the complete unchanged native template CSV"/>
          <button disabled={busy || !templateText.trim()} onClick={verifyTemplate}>Verify exact native template</button>
        </details>
        <p>{csvReady?.enabled ? "Player IDs and lineup format checked. Ready to download." : `CSV blocked: ${csvReady?.reason_codes.join(", ") || "Checking native pool evidence"}`}</p>
        <p>Uses recent averages.{selected.excluded_players?.some(p => p.reason_codes?.includes("stat_forecast_missing")) ? " Some player history is missing." : ""}{selected.variant === "touchdowns" ? " Return and recovery touchdown estimates are incomplete." : ""}</p>
        {csvReady?.enabled ? <button className="native-csv-download" disabled={busy} onClick={async () => {
          setBusy(true); setError("");
          try { await downloadNativeLineupCsv(`${BASE}/records/${selected.sha256}/download`, `single-stat-${selected.variant}-${selected.sha256.slice(0,12)}.csv`, ["FLEX","FLEX","FLEX"]); }
          catch (e) { setError(String(e)); } finally { setBusy(false); }
        }}>Download lineup CSV</button> : <button disabled>Download lineup CSV</button>}
      </section> : <><button disabled title={selected.export.reason}>DraftKings CSV unavailable</button><p>{selected.export.reason}</p></>}
      {selected.assumptions?.map(a => <p key={a}>{a}</p>)}
      {selected.kind === "report" && <details><summary>Record official actual stat evidence</summary>
        <p>Supply source-attributed actuals for these three canonical players and the required scoring-period attestations. Missing TD categories remain unknown. See the package specification for /actual-results.</p>
        <textarea aria-label="Official actual stat evidence" rows={6} value={actualInput} onChange={e => setActualInput(e.target.value)} placeholder="Actual-result evidence JSON, excluding report_sha256" />
        <button disabled={busy || !actualInput.trim()} onClick={() => run(() => request("/actual-results", {...JSON.parse(actualInput), report_sha256:selected.sha256}))}>Save source-attested actual results</button>
      </details>}
      <details><summary>Stat components, rules and immutable provenance</summary><pre>{JSON.stringify(selected, null, 2)}</pre></details>
    </section>}
  </section>;
}
