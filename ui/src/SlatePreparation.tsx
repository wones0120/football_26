import { useEffect, useRef, useState } from "react";
import { createPregameContext, fetchPreparation, queuePreparation, type PreparationScope, type PreparationStatus } from "./api";
import { nextPreparationStatus } from "./preparationStatus";
import { startSingleFlightPolling } from "./singleFlightPolling";

export type PreparationCheckState = { scope: PreparationScope; loading: boolean; error: string | null };

type Props = { contestFormat: "classic" | "showdown"; scope: PreparationScope; salaryPath: string; injuryPath: string; busy: boolean;
  getAvailabilityOverrides: () => unknown[]; assumeQuestionableOut: boolean; onStartingQbs: () => void; onStatus?: (status: PreparationStatus | null) => void;
  onCheckState?: (state: PreparationCheckState) => void };
const show = (value: unknown) => value == null ? "Unavailable" : typeof value === "object" ? JSON.stringify(value) : String(value);
function EvidenceSummary({ rows }: { rows: Array<Record<string, unknown>> }) {
  const values = (keys: string[]) => Array.from(new Set(rows.flatMap(r => keys.map(k => r[k]).filter(v => v != null)))).map(show).join(" · ") || "Unavailable";
  const unresolved = rows.filter(r => "player_master_id" in r && !r.player_master_id).length;
  return <>
    <p>{rows.length} rows · {unresolved} unresolved player identities</p>
    <p>Source: {values(["source", "source_system"])}</p>
    <p>Observation: {values(["observed_at", "source_observed_at"])}</p>
    <p>Capture / import / receipt: {values(["captured_at", "imported_at", "received_at", "updated_at"])}</p>
    <p>Basis: {values(["observation_basis"])}</p>
    <p>Freshness: {values(["freshness", "quote_freshness"])} (see load-age policy below)</p>
    <p>Consumed by current prepared features/projections: {rows.filter(r => r.consumed_by_latest_prepared_build === true).length}/{rows.length}</p>
  </>;
}

export function SlatePreparation(props: Props) {
  const { scope } = props;
  const key = JSON.stringify(scope);
  const active = useRef(key); active.current = key;
  const [status, setStatus] = useState<PreparationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [draftGroup, setDraftGroup] = useState("");
  const [freeWeather, setFreeWeather] = useState(false);
  const [injurySource, setInjurySource] = useState<"fanduel" | "draftkings">("fanduel");
  const [evidence, setEvidence] = useState("");
  const [message, setMessage] = useState("");
  const polling = useRef<{ key: string; refresh: () => Promise<PreparationStatus>; stop: () => void } | null>(null);
  const load = async () => {
    if (polling.current?.key !== key) throw new Error("Preparation scope changed");
    return polling.current.refresh();
  };
  useEffect(() => {
    setStatus(null); setError(null); props.onStatus?.(null);
    const controller = startSingleFlightPolling({ fetch: () => {
      props.onCheckState?.({ scope, loading: true, error: null });
      return fetchPreparation(scope);
    },
      intervalMs: r => r?.jobs.some(j => j.status === "queued" || j.status === "running") ? 3000 : 30_000,
      onValue: r => { setStatus(current => nextPreparationStatus(current, r, scope)); setError(null); props.onStatus?.(r);
        props.onCheckState?.({ scope, loading: false, error: null }); },
      onError: e => { setError(String(e)); props.onCheckState?.({ scope, loading: false, error: String(e) }); },
    });
    polling.current = { key, ...controller };
    return () => { controller.stop(); if (polling.current?.key === key) polling.current = null; };
  }, [key]); // Scope is frozen for each asynchronous operation.
  const disabled = working || props.busy || status?.prelock === false || Boolean(status?.jobs.some(j => j.status === "queued" || j.status === "running"));
  const run = async (action: Parameters<typeof queuePreparation>[0]["action"]) => {
    setWorking(true); setError(null);
    try {
      const queued = await queuePreparation({ ...scope, action, contest_format: props.contestFormat,
        ...(action === "salary" ? { path: props.salaryPath, native_draft_group: draftGroup } : {}),
        ...(action === "injuries" ? { path: props.injuryPath, injury_source: injurySource } : {}),
        allow_free_weather_evaluation: freeWeather,
        availability_overrides: structuredClone(props.getAvailabilityOverrides()),
        assume_questionable_out: props.assumeQuestionableOut });
      if (active.current === key) {
        setMessage(`${action} queued as ${queued.job.job_id}. Follow its status below; no lineups are generated.`);
        await load();
      }
    } catch (e) { if (active.current === key) setError(e instanceof Error ? e.message : String(e)); }
    finally { setWorking(false); }
  };
  const importEvidence = async () => {
    setWorking(true); setError(null);
    try {
      const parsed = JSON.parse(evidence);
      if (!parsed.source_uri || !parsed.observed_at || !Array.isArray(parsed.players)) throw new Error("Supply source_uri, original observed_at and canonical player IDs in players.");
      const result = await createPregameContext({ ...parsed, ...scope });
      if (active.current === key) { setMessage(`Imported sourced pregame evidence: ${result.context_run_id}. Rebuild dependent features/projections next.`); await load(); }
    } catch (e) { if (active.current === key) setError(e instanceof Error ? e.message : String(e)); }
    finally { setWorking(false); }
  };
  const sources = [
    { key: "salaries", label: "DraftKings salaries", next: "Confirm the native draft group, then import the correct CSV. Publication freshness unverified." },
    { key: "injuries", label: "Injury CSV", next: "Import supported designation data. CSV import does not establish final game clearance or feed canonical pregame context." },
    { key: "availability", label: "Sourced availability / practice / workload", next: "Load supported pregame evidence below using canonical IDs and original source time; final inactive clearance remains unverified." },
    { key: "starters", label: "Starting QBs", next: "Review Load Starting QBs and resolve candidates with sourced starter evidence; roster membership is not game clearance." },
    { key: "markets", label: "Required spreads and game totals", next: "Every game must have sourced spreads/totals within the configured freshness limit (default 6 hours), with consistent team implied totals. Preparation fetches DraftKings lines from ESPN. The displayed time is our retrieval time; the sportsbook’s update time is not provided." },
  ];
  return <div className="slate-preparation" data-testid="slate-preparation">
    <h3>Prepare slate inputs</h3>
    <p>Status updates every 30 seconds while idle and every 3 seconds during a job. Background tabs pause updates and refresh when visible again. Reload preparation status checks immediately.</p>
    <p>{scope.season} · Week {scope.week} · {scope.slate} · Server time: {status?.server_time ?? "Checking…"}</p>
    {status?.lock_at && <p>First game lock: {status.lock_at} · {status.prelock ? "Pregame" : "LOCKED: pregame preparation blocked. Use the existing late-swap workflow for locked entries."}</p>}
    <p>Preparation imports/captures evidence and rebuilds dependencies. Run Optimizer is a separate user action. Entry clearance remains unverified.</p>
    <p>Enter local CSV paths in the Salary file and Injury file fields in Slate files above, then use these canonical evidence import actions.</p>
    <label>Native DraftKings draft-group ID (operator confirmed)<input value={draftGroup} onChange={e => setDraftGroup(e.target.value)} /></label>
    <div className="button-row">
      <button disabled={disabled || !props.salaryPath || !draftGroup.trim()} onClick={() => run("salary")}>Import DraftKings salary evidence</button>
      <label>Injury CSV source<select value={injurySource} onChange={e => setInjurySource(e.target.value as typeof injurySource)}><option value="fanduel">FanDuel</option><option value="draftkings">DraftKings</option></select></label>
      <button disabled={disabled || !props.injuryPath} onClick={() => run("injuries")}>Import injury CSV evidence</button>
      <button disabled={disabled} onClick={props.onStartingQbs}>Review starting-QB evidence</button>
      <button disabled={disabled} onClick={() => run("markets")}>Refresh sportsbook lines</button>
      <button disabled={disabled} onClick={() => run("weather")}>Capture current weather</button>
      <button disabled={disabled} onClick={() => run("rebuild")}>Rebuild slate features and projections</button>
      <button disabled={working} onClick={() => load().then(() => setMessage("Validated preparation status; no new source evidence fetched.")).catch(e => setError(String(e)))}>Reload preparation status</button>
    </div>
    <label><input type="checkbox" checked={freeWeather} onChange={e => setFreeWeather(e.target.checked)} /> Acknowledge keyless Open-Meteo use for local non-commercial evaluation (existing source terms)</label>
    <details><summary>Load sourced pregame availability evidence (manual JSON)</summary>
      <p>Uses the existing pregame context loader. Supply source, source_uri, original observed_at, and players with canonical player_id. Keep injury_status (designation), evidence.practice_participation, evidence.expected_workload_status and sourced starter evidence separate. Do not infer final active status from practice or roster membership.</p>
      <pre>{'{"source":"official_team_report","source_uri":"https://…","observed_at":"YYYY-MM-DDTHH:mm:ssZ","players":[{"player_id":"canonical UUID","injury_status":"QUESTIONABLE","evidence":{"practice_participation":"LIMITED"}}]}'}</pre>
      <textarea aria-label="Sourced pregame evidence JSON" rows={8} value={evidence} onChange={e => setEvidence(e.target.value)} />
      <button disabled={disabled || !evidence.trim()} onClick={importEvidence}>Load sourced pregame evidence</button>
    </details>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status">{message}</p>}
    {status && <>
      <div className="scroll-table"><table className="compact-table"><thead><tr><th>Input / source scope</th><th>Coverage / evidence</th><th>Next action / limitation</th></tr></thead><tbody>
        {sources.map(s => <tr key={s.key}><td>{s.label}<br />{scope.season}/{scope.week}/{scope.slate}</td><td><EvidenceSummary rows={status.inputs[s.key] ?? []} />
          <details><summary>Observation, import, identities, source checksums and consumption</summary><pre>{JSON.stringify(status.inputs[s.key] ?? [], null, 2)}</pre></details>
        </td><td>{s.next}</td></tr>)}
        <tr><td>Weather / game and venue</td><td><details><summary>Forecast basis, receipt time, venue/roof, coverage and freshness</summary><pre>{JSON.stringify(status.weather ?? {}, null, 2)}</pre></details></td><td>Capture current weather. Evidence is not consumed by projections; final weather clearance unavailable.</td></tr>
      </tbody></table></div>
      <details><summary>Existing load-age freshness policy (import age, separate from publication freshness)</summary><pre>{JSON.stringify(status.load_freshness ?? {}, null, 2)}</pre></details>
      <p>{status.latest_build ? `${status.build_current ? "Verified current" : "Older or superseded"} prepared projection: ${status.latest_build.projection_run_id} · feature: ${status.latest_build.feature_run_id}` : "No current verified dependent build. Rebuild slate features and projections."}</p>
      <p>Source and model details below are display summaries. Full evidence remains in the saved preparation audit; original receipt hashes identify the full records.</p>
      <details><summary>Prepared build and consumption summary</summary><pre>{JSON.stringify(status.latest_build, null, 2)}</pre>
        {status.latest_build?.audit_url && <a href={status.latest_build.audit_url} target="_blank" rel="noreferrer">Open full saved preparation audit</a>}</details>
      <ul>{status.limitations.map(v => <li key={v}>{v}</li>)}</ul>
      {status.jobs.map(j => <details key={j.job_id} open={j.status === "failed"}><summary>{j.action}: {j.status} · {j.stage} · {j.job_id.slice(0, 12)}</summary><p>{j.message}</p>{j.error && <p role="alert">{j.error}</p>}<pre>{show(j.result ?? j.checkpoint)}</pre>
        {j.audit_url && <a href={j.audit_url} target="_blank" rel="noreferrer">Open saved job audit</a>}</details>)}
    </>}
  </div>;
}
