import { intentHandoff, type OptimizationIntent } from "./analystIntent";
import { AnalystPreparationSummary } from "./AnalystPreparationSummary";
import type { AnalystHandoffMode } from "./analystPreparation";
import { useEffect, useState } from "react";
import { fetchPreliminarySnapshots, freezePreliminarySnapshot, type PreparationScope, type PreparationStatus } from "./api";
import { preliminaryScopeIssue, type PreliminarySnapshot } from "./preliminaryResearch";

export function PreliminaryClassicControls({ scope, preparation, enabled, busy, excludeQuestionable, compatibleSnapshotHash, analystMode = "MANUAL", optimizationIntent = "MIXED", analystOverride, onSnapshot, onAutomatic, onPrepare, onGenerate }: {
  scope: PreparationScope; preparation: PreparationStatus | null; enabled: boolean; busy: boolean; excludeQuestionable: boolean;
  optimizationIntent?: OptimizationIntent; analystMode?: AnalystHandoffMode; analystOverride?: {analyst_packet_sha256?:string;analyst_strategy?:"CONSTRUCTION"|"MERGED_SCENARIOS"}; onSnapshot?: (snapshot:PreliminarySnapshot|null)=>void; onAutomatic?:()=>void;
  onPrepare?: () => Promise<PreliminarySnapshot | undefined>;
  compatibleSnapshotHash?: string | null; onGenerate: (snapshot: PreliminarySnapshot, noSeasonRankRestriction: boolean) => Promise<void>;
}) {
  const [rows, setRows] = useState<PreliminarySnapshot[]>([]), [selected, setSelected] = useState("");
  const [preparationId, setPreparationId] = useState(""), [noRankRestriction, setNoRankRestriction] = useState(false);
  const [acceptedAssumptions, setAcceptedAssumptions] = useState(false), [loading, setLoading] = useState(false), [refresh, setRefresh] = useState(0);
  const [error, setError] = useState<string | null>(null), [warnings, setWarnings] = useState<string[]>([]);
  useEffect(() => {
    let cancelled = false; setLoading(true); setRows([]); setPreparationId(""); setAcceptedAssumptions(false); setError(null);
    fetchPreliminarySnapshots(scope).then(result => { if (!cancelled) { setRows(result.rows); setWarnings(result.warnings); setSelected(current => result.rows.some(r => r.snapshot_sha256 === current && (!compatibleSnapshotHash || r.snapshot_sha256 === compatibleSnapshotHash)) ? current : result.rows.find(r => !compatibleSnapshotHash || r.snapshot_sha256 === compatibleSnapshotHash)?.snapshot_sha256 ?? ""); } }).catch(err => { if (!cancelled) setError(String(err.message ?? err)); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [scope.season, scope.week, scope.slate, compatibleSnapshotHash, refresh]);
  const snapshot = rows.find(r => r.snapshot_sha256 === selected);
  useEffect(() => { onSnapshot?.(snapshot ?? null); }, [snapshot]);
  const finished = (preparation?.jobs ?? []).filter(j => j.action === "prepare" && ["completed","failed"].includes(j.status));
  const sourceId = preparationId || finished[0]?.job_id || "";
  const freeze = async () => {
    if (!sourceId) return; setLoading(true); setError(null);
    try { const result = await freezePreliminarySnapshot(sourceId, {analyst_mode:analystMode,...(analystMode === "MANUAL" ? analystOverride : {})}); const issue = preliminaryScopeIssue(result, scope); if (issue) throw new Error(issue); setRows(current => [result,...current.filter(r => r.snapshot_sha256 !== result.snapshot_sha256)]); setSelected(result.snapshot_sha256); setAcceptedAssumptions(false); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  };
  const prepare = async () => {
    if (!onPrepare) return; setLoading(true); setError(null);
    try { const result = await onPrepare(); if (result) { const issue = preliminaryScopeIssue(result, scope); if (issue) throw new Error(issue); setRows(current => [result,...current.filter(r => r.snapshot_sha256 !== result.snapshot_sha256)]); setSelected(result.snapshot_sha256); setAcceptedAssumptions(false); } }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  };
  const handoff = intentHandoff(snapshot, optimizationIntent);
  const compatible = !compatibleSnapshotHash || snapshot?.snapshot_sha256 === compatibleSnapshotHash;
  return <details className="operations-disclosure" open={enabled}>
    <summary>Preliminary Classic research generation</summary>
    <p><strong>Experimental research; not entry cleared.</strong> This separate path uses a verified frozen salary/projection/ownership snapshot while retaining missing official injury/practice errors. Saved lineups can be checked for CSV upload separately; final inactives remain pending.</p>
    <p>Preliminary preparation refreshes markets and builds new research projections. Missing or stale injury/role evidence stays unknown; affected players are excluded from this research pool. Normal entry readiness is never cleared.</p>
    {onPrepare && <button type="button" disabled={!enabled || busy || loading} onClick={() => void prepare()}>Prepare preliminary research inputs</button>}
    {!enabled && <p>Select Classic, GPP and Classic Large GPP to use this workflow.</p>}
    <div className="button-row"><label className="text-label">Frozen research inputs<select value={selected} disabled={busy || loading} onChange={e => { setSelected(e.target.value); setAcceptedAssumptions(false); }}><option value="">Choose a snapshot</option>{rows.map(r => <option key={r.snapshot_sha256} value={r.snapshot_sha256}>{r.assumption_manifest.declared_at} · {r.snapshot_sha256.slice(0,12)}{compatibleSnapshotHash && r.snapshot_sha256 !== compatibleSnapshotHash ? " · different Analyst inputs" : ""}</option>)}</select></label><button type="button" onClick={() => setRefresh(n => n + 1)} disabled={busy || loading}>Refresh frozen inputs</button></div>
    {!rows.length && !loading && <p>No frozen snapshot is available for this slate. Finish a Classic preparation with verified salary, market, projection and ownership evidence, then freeze it below.</p>}
    <details><summary>Freeze a finished preparation as new research inputs</summary><p>A new freeze creates a new assumption receipt. An Analyst discovery packet tied to an older snapshot must continue using its original frozen inputs.</p><label className="text-label">Finished Classic preparation<select value={sourceId} onChange={e => setPreparationId(e.target.value)} disabled={busy || loading}><option value="">Choose a finished preparation</option>{finished.map(j => <option key={j.job_id} value={j.job_id}>{j.job_id.slice(0,12)} · {j.status} · {j.message ?? j.stage}</option>)}</select></label><button type="button" onClick={() => void freeze()} disabled={!enabled || !sourceId || busy || loading}>Freeze preliminary inputs</button></details>
    {snapshot && <div><p>Projection <code>{snapshot.projection_run_id}</code> · Ownership <code>{snapshot.ownership_run_id}</code></p><p>Original normal-readiness reasons: {snapshot.normal_reason_codes.join(", ") || "No source blocker recorded"}. Final entry readiness remains false.</p><details open><summary>Immutable injury assumptions and canonical exclusions ({snapshot.assumption_manifest.exclude_player_ids.length})</summary><p>{snapshot.assumption_manifest.practice_assumption}</p><p>{snapshot.assumption_manifest.other_player_assumption}</p><p>{snapshot.assumption_manifest.known_unavailable_policy}</p><p>{snapshot.assumption_manifest.source_truth}</p><table className="compact-table"><thead><tr><th>Player</th><th>Source status / missing evidence</th><th>Research decision</th></tr></thead><tbody>{snapshot.assumption_manifest.players.map((value, index) => { const player = value as {player?:string;player_id?:string;availability?:string;reason_codes?:string[]}; return <tr key={player.player_id ?? index}><td>{player.player ?? player.player_id}</td><td>{player.availability ?? "Unknown"} · {(player.reason_codes ?? []).join(", ")}</td><td>Excluded from research; original facts unchanged</td></tr>; })}</tbody></table><pre style={{maxHeight:300,overflow:"auto"}}>{JSON.stringify(snapshot.assumption_manifest,null,2)}</pre></details></div>}
    {snapshot && <AnalystPreparationSummary handoff={handoff} mode={analystMode} busy={busy || loading} onAutomatic={onAutomatic ?? (()=>{})} />}
    {snapshot && analystMode === "AUTO" && !handoff?.checked_packet_sha256 && <p role="alert">This original snapshot has no checked Analyst handoff. Freeze a finished preparation below to check research automatically against the new inputs.</p>}
    {!compatible && <p role="alert">The selected Analyst discovery packet was investigated against another snapshot. Choose its matching frozen inputs or a compatible packet.</p>}
    {!excludeQuestionable && <p>Enable <strong>Exclude questionable players</strong> in your controls; this workflow requires that preference.</p>}
    <label><input type="checkbox" checked={noRankRestriction} onChange={e => setNoRankRestriction(e.target.checked)} disabled={busy} /> No season-average rank restriction for this research run only</label><p><small>Incomplete prior-week stats/snap history blocks enabled rank filters. This explicit research choice removes only those rank limits from this request; your saved normal-run preferences stay intact. Other salary, exposure, locks and eligibility rules remain binding.</small></p>
    <label><input type="checkbox" checked={acceptedAssumptions} onChange={e => setAcceptedAssumptions(e.target.checked)} disabled={!snapshot || busy} /> Use the displayed preliminary assumptions; keep final entry readiness false</label>
    {warnings.map((w,i) => <p key={i} role="status">{w}</p>)}{error && <p role="alert" className="error">{error}</p>}{loading && <p role="status">Loading frozen research inputs…</p>}
    <div className="button-row"><button type="button" onClick={() => snapshot && void onGenerate(snapshot,noRankRestriction)} disabled={!enabled || !snapshot || (analystMode === "AUTO" && !handoff?.checked_packet_sha256) || !compatible || !acceptedAssumptions || !excludeQuestionable || busy || loading}>Generate preliminary research lineups</button></div>
  </details>;
}
