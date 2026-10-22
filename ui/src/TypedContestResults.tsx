import { useEffect, useState } from "react";
import { getJson } from "./typedResultsApi";

export type TypedChoice = { contest_format?: string; scoring_variant?: string; pool_sha256?: string; source_reference?: string; correction_of?: string };
export type TypedGroup = { record_id: string; season: number; week: number; slate: string; contest_id: string; contest_format: string; variant: string; units: string; source_name: string; scope_status: string; reconciliation_status: string; classification: string; entries?: Array<{ entry_id: string; entry_name: string; rank: number; observed_score: number; identity_status: string; players: Array<{ display_name: string; role: string; identity_status: string }>; forecast_comparison: { status: string; matches?: Array<{ forecast: number; units: string; report_sha256: string; objective: string }> } }> };
export function typedChoiceReady(choice: TypedChoice) {
  return !["tiers", "single_stat"].includes(choice.contest_format ?? "") || Boolean(choice.source_reference?.trim() && (choice.contest_format === "tiers" || ["touchdowns", "total_yards", "passing_yards"].includes(choice.scoring_variant ?? "")));
}
export function TypedAssignment({ choice, onChange, label }: { choice: TypedChoice; onChange: (value: TypedChoice) => void; label: string }) {
  if (!["tiers", "single_stat"].includes(choice.contest_format ?? "")) return <span>{choice.contest_format ?? "Classic / Showdown"}</span>;
  return <fieldset><legend>{choice.contest_format === "tiers" ? "Tiers · DK fantasy points" : "Single Stat · verify metric"}</legend>
    {choice.contest_format === "single_stat" && <label>Scoring variant<select aria-label={`Scoring variant for ${label}`} value={choice.scoring_variant ?? ""} onChange={e => onChange({ scoring_variant: e.target.value })}><option value="">Choose verified metric</option><option value="touchdowns">Touchdowns (no passing TD)</option><option value="total_yards">Rushing + receiving yards</option><option value="passing_yards">Passing yards only</option></select></label>}
    <label>Scope/scoring evidence<input aria-label={`Scope evidence for ${label}`} value={choice.source_reference ?? ""} onChange={e => onChange({ source_reference: e.target.value })} placeholder="Contest source URL/reference; fixture: for synthetic data" /></label>
    <label>Native pool hash (optional)<input aria-label={`Native pool hash for ${label}`} value={choice.pool_sha256 ?? ""} onChange={e => onChange({ pool_sha256: e.target.value || undefined })} /></label>
    <label>Correction record (optional)<input aria-label={`Correction record for ${label}`} value={choice.correction_of ?? ""} onChange={e => onChange({ correction_of: e.target.value || undefined })} /></label>
    <small>Three FLEX slots do not identify a scoring metric. Names alone remain unverified; fees and payouts stay in Entry History.</small>
  </fieldset>;
}
export function TypedGroups({ groups }: { groups: TypedGroup[] }) {
  return <>{groups.map(g => <section className="status-card" key={g.record_id}><h3>{g.contest_format === "tiers" ? "Tiers" : "Single Stat"} · {g.variant.replaceAll("_", " ")} · {g.slate.replaceAll("_", " ")}</h3>
    <p>Contest {g.contest_id} · observed {g.units} · {g.classification} · {g.scope_status}</p><small>{g.record_id} · components {g.reconciliation_status}. No inferred fee, payout or ROI.</small>
    {g.entries?.map(e => <div key={e.entry_id}><p>{e.entry_name}: rank {e.rank} · observed score {e.observed_score} {g.units} · identity {e.identity_status}</p><p>{e.players.map(p => `${p.role} ${p.display_name} (${p.identity_status})`).join("; ")}</p><p>Forecast: {e.forecast_comparison.status.replaceAll("_", " ")}. Roster correspondence does not prove origin, submission or pre-lock chronology.</p>{e.forecast_comparison.matches?.map((m,i) => <p key={i}>Saved forecast {m.forecast.toFixed(3)} {m.units} · {m.objective} · {m.report_sha256}. Coverage and chronology require review; no complete-stat error or submission claim is inferred.</p>)}</div>)}
  </section>)}</>;
}
export function TypedResultsLibrary({ refreshKey, entryUser, season, week }: { refreshKey: string; entryUser: string; season: number; week: number }) {
  const [records,setRecords]=useState<TypedGroup[]>([]),[opened,setOpened]=useState<TypedGroup|null>(null),[error,setError]=useState("");
  useEffect(() => { setOpened(null); },[entryUser,season,week]);
  useEffect(() => { let active=true; getJson<{records:TypedGroup[]}>("/learning/typed-results").then(r=>{if(active)setRecords(r.records.filter(x=>x.season===season&&x.week===week));}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;}; },[refreshKey,season,week]);
  return <section className="status-card"><h3>Saved Tiers / Single Stat results</h3>{error && <p role="alert">{error}</p>}{!records.length&&<p>No typed contest results saved for this week.</p>}{records.map(r=><p key={r.record_id}>{r.source_name} · {r.variant} · {r.slate} <button onClick={async()=>{try{const v=await getJson<{record:TypedGroup;entries:TypedGroup["entries"]}>(`/learning/typed-results/${r.record_id}?entry_user=${encodeURIComponent(entryUser)}`);setOpened({...v.record,entries:v.entries});setError("");}catch(e){setError(String(e));}}}>Reopen {r.contest_id} results</button></p>)}{opened&&<TypedGroups groups={[opened]}/>}</section>;
}
