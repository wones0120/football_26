import { useEffect, useState } from "react";
import { fetchAnalystPacket, importAnalystPacket, fetchAvailableAnalystPackets } from "./api";
import { analystPacketScopeIssue, captainAnalystEnabled, type AnalystPacketMetadata } from "./analystPacket";

type Props = { season: number; week: number; format: "classic" | "showdown"; disabled: boolean;
  selected: AnalystPacketMetadata | null; onSelect: (packet: AnalystPacketMetadata | null) => void };

export function AnalystPacketControls({ season, week, format, disabled, selected, onSelect }: Props) {
  const [available, setAvailable] = useState<AnalystPacketMetadata[]>([]);
  useEffect(() => { let active = true; void fetchAvailableAnalystPackets({season,week,format}).then(result => { if (active) setAvailable(result.rows); }).catch(() => { if (active) setAvailable([]); }); return () => { active = false; }; }, [season,week,format]);
  const [hash, setHash] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const select = (packet: AnalystPacketMetadata) => {
    const issue = analystPacketScopeIssue(packet, season, week, format);
    if (issue) throw new Error(issue);
    onSelect({ ...packet, selected_strategy: packet.selected_strategy ?? (packet.scenario_count ? "MERGED_SCENARIOS" : "CONSTRUCTION") });
    setHash(packet.analyst_packet_sha256);
  };
  const run = async (action: () => Promise<AnalystPacketMetadata>) => {
    setBusy(true); setError(null);
    try { select(await action()); } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };
  return <details className="operations-disclosure" data-testid="analyst-packet-controls">
    <summary>Wones Football Analyst · {selected ? "packet active" : "optional"}</summary>
    <button type="button" disabled={disabled || busy} onClick={() => { void fetchAvailableAnalystPackets({season,week,format}).then(result => setAvailable(result.rows)); if (selected) void run(async () => ({...await fetchAnalystPacket(selected.analyst_packet_sha256),selected_strategy:selected.selected_strategy,focus_mode:selected.focus_mode,focus_ids:selected.focus_ids,challenger_enabled:selected.challenger_enabled,teammate_enabled:selected.teammate_enabled,joint_opportunity_enabled:selected.joint_opportunity_enabled})); }}>Refresh available packets and active metadata</button>
    <p>Import an Analyst packet, then choose how its assumptions influence generation and portfolio selection. Base model projections remain available in every report.</p>
    {available.length > 0 && <div className="button-row"><button type="button" disabled={disabled || busy} onClick={() => { const usable = available.find(packet => (packet.scenario_count ?? 0) > 0); if (usable) select({ ...usable, selected_strategy: "MERGED_SCENARIOS", challenger_enabled: format === "classic", teammate_enabled: format === "classic" }); else setError("No scenario-capable packet is available for this scope."); }}>Use available experimental Analyst tools</button><select aria-label="Available imported Analyst packet" disabled={disabled || busy} value={selected?.analyst_packet_sha256 ?? ""} onChange={event => { const packet = available.find(p => p.analyst_packet_sha256 === event.target.value); if (packet) select(packet); }}><option value="">Choose an imported packet</option>{available.map(packet => <option key={packet.analyst_packet_sha256} value={packet.analyst_packet_sha256}>{packet.packet_id} · {packet.decision_at}</option>)}</select></div>}
    <label>Import Analyst JSON
      <input type="file" accept=".json,application/json" disabled={disabled || busy} onChange={event => {
        const file = event.target.files?.[0];
        if (file) void run(async () => importAnalystPacket(JSON.parse(await file.text())));
        event.target.value = "";
      }} />
    </label>
    <label>Previously imported packet hash
      <input value={hash} onChange={event => setHash(event.target.value)} placeholder="64-character SHA-256" disabled={disabled || busy} />
    </label>
    <div className="button-row">
      <button type="button" disabled={disabled || busy || !/^[0-9a-f]{64}$/.test(hash.trim())} onClick={() => void run(() => fetchAnalystPacket(hash.trim()))}>Select imported packet</button>
      <button type="button" disabled={disabled || busy || !selected} onClick={() => { onSelect(null); setHash(""); setError(null); }}>Clear Analyst · run baseline</button>
    </div>
    {busy && <p role="status">Validating Analyst packet…</p>}
    {selected && <div role="status">
      <label>Analyst strategy
        <select disabled={disabled || busy} value={selected.selected_strategy ?? "CONSTRUCTION"}
          onChange={event => onSelect({ ...selected, selected_strategy: event.target.value as "CONSTRUCTION" | "MERGED_SCENARIOS" })}>
          <option value="CONSTRUCTION">Original construction comparison</option>
          <option value="MERGED_SCENARIOS" disabled={!selected.scenario_count}>Merged Analyst + math scenarios</option>
        </select>
      </label>
      <p>{selected.selected_strategy === "MERGED_SCENARIOS"
        ? "Requires a GPP strategy. Classic allocates sourced football ideas before roster optimization and audits shared outcome dependence. Showdown uses Captain-conditioned scenarios when supplied. No 95% mean/P90 screen; all priorities and sensitivities are uncalibrated."
        : "Original construction candidates compete under the existing scoring and quality screens."}</p>
      {selected.selected_strategy === "MERGED_SCENARIOS" && <label><input type="checkbox" checked={selected.joint_opportunity_enabled ?? false} disabled={true} onChange={event => onSelect({ ...selected, joint_opportunity_enabled: event.target.checked })}/> Shared-opportunity construction prototype · inactive pending evidence review</label>}
      {selected.joint_opportunity_enabled && <p>Optimizes the full legal roster in sourced football worlds, with shared target/carry capacity for upside credit. Same-team players can succeed together; no teammate ban or game-total cutoff. This is an uncalibrated sensitivity, not a lineup P90 or win probability. Exact highest baseline projection remains unchanged.</p>}
      {format === "classic" && selected.selected_strategy === "MERGED_SCENARIOS" && <label><input type="checkbox" checked={selected.challenger_enabled ?? false} disabled={disabled || busy} onChange={event => onSelect({ ...selected, challenger_enabled: event.target.checked })} /> Enable bounded blind-spot hunter after initial candidates (optional)</label>}
      {format === "classic" && selected.selected_strategy === "MERGED_SCENARIOS" && <label><input type="checkbox" checked={selected.teammate_enabled ?? false} disabled={disabled || busy} onChange={event => onSelect({ ...selected, teammate_enabled: event.target.checked })} /> Compare cheaper teammates under sourced game-flow assumptions (paired research)</label>}
      {selected.selected_strategy === "MERGED_SCENARIOS" && <fieldset><legend>Football scenario focus</legend>
        <label><select value={selected.focus_mode ?? "MIXED"} disabled={disabled || busy} onChange={event => onSelect({ ...selected, focus_mode: event.target.value as "MIXED" | "SELECTED_ONLY", focus_ids: [] })}><option value="MIXED">Mixed football portfolio</option><option value="SELECTED_ONLY" disabled={!selected.scenario_options?.some(option => option.focus_applicable)}>Only selected football stories</option></select></label>
        {selected.focus_mode === "SELECTED_ONLY" && <><p>Every lineup must express a selected story. Unsupported or infeasible stories report failure/underfill; no generic fallback. Other hunter/teammate branches are inactive in this explicit mode. Football contrarian is not a claim of low ownership or calibrated likelihood.</p>
          {(selected.scenario_options ?? []).map(option => <label key={option.scenario_id}><input type="checkbox" disabled={disabled || busy || !option.focus_applicable} checked={selected.focus_ids?.includes(option.scenario_id) ?? false} onChange={event => onSelect({ ...selected, focus_ids: event.target.checked ? [...(selected.focus_ids ?? []), option.scenario_id] : (selected.focus_ids ?? []).filter(id => id !== option.scenario_id) })} /> {option.label}{!option.focus_applicable ? " · composite stress only" : ""}</label>)}
          {!selected.focus_ids?.length && <p role="alert">Choose at least one selectable story before building.</p>}</>}
      </fieldset>}
      {!selected.scenario_count && <p>This packet needs a validated scenario_assumptions block to use the merged strategy.</p>}
      {format === "classic" && selected.selected_strategy === "MERGED_SCENARIOS" && selected.discovery_contract === "analyst_discovery_v1" && <p>Discovery investigation active: {selected.discovery_finding_count} sourced findings reviewed before allocation; only supported provisional model gaps can reserve bounded construction slots. Watchlists do not change forecasts.</p>}
      {captainAnalystEnabled(selected, format) && <p>Captain-specific Analyst active: assesses the current eligible Captain choices, compares whether the opponent can score competitively, pass productively while trailing, or stall, then builds supporting FLEX alternatives. Missing research stays unknown. Opponent selections follow workload and roster rules.</p>}
      <p><strong>{selected.analyst_name}</strong> · {selected.packet_id} · {selected.assessment_count} assessment(s)</p>
      <p>Scope: {selected.games.map(game => `${game.teams.join(" at ")} · ${game.season} W${game.week}`).join("; ")}</p>
      <p>Decision: {selected.decision_at}</p>
      <p style={{ overflowWrap: "anywhere" }}>Active hash: {selected.analyst_packet_sha256}</p>
    </div>}
    {error && <p role="alert" className="error inline-error">{error}</p>}
  </details>;
}
