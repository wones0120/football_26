import type { OptimizerResponse } from "./api.ts";

type Row = Record<string, any>;
const escape = (value: unknown) => String(value ?? "Unavailable").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const json = (value: unknown) => `<pre style="white-space:pre-wrap;overflow-wrap:anywhere">${escape(JSON.stringify(value, null, 2))}</pre>`;

export function largeGppReadinessHtml(optimizer: OptimizerResponse): string {
  const preliminary = optimizer.preliminary_report as Row | undefined;
  if (preliminary) {
    const assumptions = preliminary.assumption_manifest ?? {};
    const normal = preliminary.normal_readiness ?? optimizer.data_readiness ?? {};
    const sourceChecks = normal.required_sources ?? {};
    const sourceLabels: Record<string, string> = {salary_pool: "Salary identity and freshness", market: "Spreads and totals", projection: "Current projections", ownership: "Ownership", player_status: "Player availability and roles"};
    const analyst = optimizer.analyst_handoff_applied ?? optimizer.football_analyst?.prepared_research ?? {};
    return `<h3>Preliminary research · not entry cleared</h3>
      <p><strong>Research optimizer: ${escape(optimizer.status)} · ${Array.isArray(optimizer.results) ? optimizer.results.length : 0} ${optimizer.status === "completed" ? "saved" : "reported"} lineups · ENTRY READY: NO</strong></p>
      <p>Normal source readiness: ${escape(normal.status)}. Missing evidence below remains unresolved; research assumptions do not establish current game-day clearance. Contest CSV export is blocked.</p>
      <table><thead><tr><th>Retained source check</th><th>Status</th></tr></thead><tbody>${Object.entries(sourceChecks).map(([name,value]) => `<tr><td>${escape(sourceLabels[name] ?? name)}</td><td>${escape((value as Row).status)}</td></tr>`).join("")}</tbody></table>
      <p>Normal source blockers: ${escape((normal.reason_codes ?? []).join(", "))}</p>
      <p style="overflow-wrap:anywhere">Research snapshot: ${escape(preliminary.snapshot_sha256)}<br>Assumption receipt: ${escape(preliminary.assumption_manifest_sha256)}<br>Checked Analyst packet: ${escape((analyst as Row).checked_packet_sha256)}<br>Compatibility receipt: ${escape((analyst as Row).compatibility_sha256)}</p>
      <p>Frozen assumptions: ${escape(assumptions.declared_at)} · ${escape(assumptions.exclude_player_ids?.length ?? 0)} conservative exclusions.</p>
      <p>${escape(assumptions.practice_assumption)} ${escape(assumptions.source_truth)}</p>
      <details><summary>Per-player research decisions and original unknown evidence</summary><table><thead><tr><th>Player</th><th>Original source assessment / missing checks</th><th>Research decision</th></tr></thead><tbody>${(assumptions.players ?? []).map((player:Row) => `<tr><td>${escape(player.player ?? player.player_id)}</td><td>${escape(player.availability)} · ${escape((player.reason_codes ?? []).join(", "))}</td><td>Excluded from research; original facts unchanged</td></tr>`).join("")}</tbody></table></details>
      <details><summary>Immutable research receipt and retained normal readiness</summary>${json(preliminary)}</details>`;
  }
  const readiness = (optimizer.readiness_assessment ?? optimizer.entry_readiness) as Row | undefined;
  const checks = readiness?.checks ?? {};
  const generation = optimizer.data_readiness as Row | undefined;
  const sources = generation?.required_sources ?? {};
  const weather = sources.weather ?? generation?.optional_sources?.weather;
  const coverage = generation?.market_coverage;
  const projection = generation?.projection_coverage;
  const ownership = generation?.ownership_coverage;
  const populations = generation?.pool_populations;
  const populationReport = populations ? `<h4>Player populations</h4><table><thead><tr><th>Population</th><th>Count</th></tr></thead><tbody>${[
    ["Full native DraftKings salary rows", populations.native_salary_rows],
    ["Canonically resolved salary rows", populations.canonically_resolved_salary_rows],
    ["Confirmed unavailable", populations.confirmed_unavailable],
    ["Role ineligible", populations.role_ineligible],
    ["Unresolved blocking players", populations.unresolved],
    ["Quarantined unresolved evidence", populations.quarantined_unresolved_evidence],
    ["Certified generation pool", populations.certified_generation_eligible],
  ].map(([label, count]) => `<tr><td>${escape(label)}</td><td>${escape(count)}</td></tr>`).join("")}</tbody></table>
    <p>Projection and ownership completeness use the certified generation pool. Quarantine preserves unknown status and requires fresh evidence of an existing role exclusion; material or unassessable uncertainty still blocks.</p>
    <p>Source-level blockers: ${escape((generation?.blocker_groups?.source_level ?? []).join(", ") || "None")}</p>
    <details><summary>Material player blockers and quarantine evidence</summary>${json({blocking: generation?.blocker_groups?.material_players ?? [], quarantined: (generation?.players ?? []).filter((p: Row) => p.disposition === "quarantined_unresolved_evidence")})}</details>` : "";
  const yesNo = (value: unknown) => value === true ? "yes" : value === false ? "no" : "unrecorded";
  const generationSummary = generation ? `<p><strong>Solver called: ${yesNo(generation.solver_called)} · Override used: ${yesNo(generation.override_used)}</strong></p>
    ${generation.override_used ? "<p><strong>DEVELOPMENT_PREVIEW — explicit incomplete-evidence override. These lineups are not entry-ready.</strong></p>" : ""}
    <table><thead><tr><th>Generation check</th><th>Status</th></tr></thead><tbody>
    <tr><td>Salary freshness / lineage</td><td>${escape(sources.salary_pool?.status)}</td></tr>
    <tr><td>Market coverage / freshness</td><td>${coverage ? `${coverage.covered_game_ids.length}/${coverage.required_game_ids.length} games · ` : ""}${escape(sources.market?.status)}</td></tr>
    <tr><td>Projection completeness</td><td>${projection ? `${projection.complete_players}/${projection.required_players} players · ` : ""}${escape(sources.projection?.status)}</td></tr>
    <tr><td>Ownership completeness</td><td>${ownership ? `${ownership.complete_players}/${ownership.required_players} players · ` : ""}${escape(sources.ownership?.status)}</td></tr>
    <tr><td>Availability / roles</td><td>${escape(sources.player_status?.status)}</td></tr>
    <tr><td>Current game-day clearance</td><td>${escape(generation.optional_sources?.final_game_day_clearance?.status ?? "UNEVALUATED")}</td></tr>
    <tr><td>Weather required?</td><td>${yesNo(weather?.required)} · ${escape(weather?.status)}</td></tr>
    <tr><td>Frozen evidence timestamp</td><td>${escape(generation.frozen_at ?? "Not frozen")}</td></tr>
    <tr><td>Readiness snapshot ID / SHA256</td><td>${escape(generation.snapshot_id ?? "Not frozen")} / ${escape(generation.snapshot_sha256 ?? "Not frozen")}</td></tr>
    </tbody></table><p>Exact blocker reason codes: ${escape((generation.reason_codes ?? []).join(", ") || "None")}</p>` : "";
  const qualified = readiness?.entry_ready === true && readiness.current_entry_clearance === "VERIFIED"
    && Object.keys(checks).length > 0 && Object.values(checks).every((check: any) => ["PASS", "WARNING"].includes(check.status));
  const market = readiness?.market_coverage;
  return `<h3>${optimizer.strategy === "classic_single_lineup_v1" ? "Classic readiness" : "Classic Large-GPP readiness"}</h3><p><strong>Generation evidence: ${escape(generation?.status ?? "UNVERIFIED ARCHIVED RUN")}</strong> · ${escape(generation?.contract_id ?? "No pre-generation contract saved")}</p>
    ${generationSummary}${populationReport}${generation ? `<details><summary>Pre-generation source checks and frozen evidence lineage</summary>${json(generation)}</details>` : ""}<p><strong>ENTRY READY: ${qualified && (!generation || generation.status === "READY") ? "YES" : "NO"}</strong> · ${escape(readiness?.status ?? (generation?.status === "NOT_READY" || generation?.status === "ERROR" ? "BLOCKED" : "DEVELOPMENT_PREVIEW"))}</p>
    <p>Original saved readiness: ${escape(optimizer.entry_readiness?.status ?? "not evaluated")}. ${optimizer.readiness_assessment ? "Present-time assessment shown separately; saved history unchanged." : ""}</p>
    <p>Scope: ${escape(readiness?.scope)} · Assessed: ${escape(readiness?.assessed_at)} · Original decision: ${escape(readiness?.original_decision_at)} · Freshness assessed as of: ${escape(readiness?.freshness_as_of)}</p>
    <p>Legal roster / requested constraints: ${escape(readiness?.portfolio_validation?.status)} · Preview validity: ${readiness?.preview_valid === true ? "verified" : "unavailable"} · Current entry clearance: ${escape(readiness?.current_entry_clearance ?? "UNEVALUATED")} · Contest assignment: ${escape(readiness?.contest_assignment ?? "UNEVALUATED")} · Submission verification: ${readiness?.submission_verified === true ? "verified" : "PENDING"}</p>
    <table><thead><tr><th>Check</th><th>Status / evidence</th></tr></thead><tbody>${Object.entries(checks).map(([name, check]: [string, any]) => `<tr><td>${escape(name)}</td><td>${escape(check.status)} · ${escape(check.reason)}</td></tr>`).join("") || "<tr><td>Readiness</td><td>Not evaluated for this saved run</td></tr>"}</tbody></table>
    <h4>Market evidence consumed by scoring</h4><p>${market ? `Coverage ${escape(market.sourced_games)}/${escape(market.total_games)} games; existing freshness bands ${escape(market.fresh_hours)}/${escape(market.stale_hours)} hours, policy ${escape(market.stale_policy)}.` : "Readiness metadata unavailable; this does not establish that scoring inputs were absent."}</p>
    ${market ? `<table><thead><tr><th>Game</th><th>Source</th><th>Observation time</th><th>Age hours</th><th>Status</th></tr></thead><tbody>${(market.games ?? []).map((row: Row) => `<tr><td>${escape(row.game_id)}</td><td>${escape(row.source)}</td><td>${escape(row.observed_at)}</td><td>${escape(row.age_hours)}</td><td>${escape(row.status)}</td></tr>`).join("")}</tbody></table>` : ""}
    <details><summary>Frozen availability and practice evidence</summary><p>Source observation times below are separate from fetch and job completion times. Consumed frozen practice evidence does not establish current entry clearance.</p><table><thead><tr><th>Player / frozen risk</th><th>Injury observation</th><th>Practice / observation</th><th>Context source / observation</th><th>Frozen practice consumed / current clearance consumed</th></tr></thead><tbody>${(readiness?.availability_evidence ?? []).map((row: Row) => `<tr><td>${escape(row.name ?? row.player_id)} · ${escape(row.frozen_bucket)}</td><td>${escape(row.injury_observed_at)}</td><td>${escape(row.practice_status)} · ${escape(row.practice_observed_at)}</td><td>${escape(row.context_source)} · ${escape(row.context_observed_at)}</td><td>${escape(row.source_evidence_consumed)} / ${escape(row.current_evidence_consumed)}</td></tr>`).join("")}</tbody></table></details>
    <details><summary>Salary lineage, explicit risk limits, and complete assessment</summary>${json(readiness ?? { status: "UNEVALUATED" })}</details>
    <p>Validation uses frozen inputs and performs no refresh or solve. Use Operations → Prepare slate inputs to import/capture evidence and rebuild dependencies. Review material blockers, preserve your chosen controls and exclusions, then initiate Run Optimizer yourself. Reload projection list only reloads the list.</p>`;
}

export function gameAppearancesHtml(optimizer: OptimizerResponse): string {
  const summary = optimizer.game_appearances as Row | undefined;
  if (!summary) return "";
  return `<h3>Actual player appearances by game</h3><p>Primary QB-game allocation: ${escape(Object.entries(summary.primary_qb_games ?? {}).map(([game, count]) => `${game}: ${count}`).join(" · "))}</p><table><thead><tr><th>Game</th><th>Entries containing game</th><th>Per entry including DST</th><th>Total including DST</th><th>Per entry offense only</th><th>Total offense only</th></tr></thead><tbody>${(summary.games ?? []).map((row: Row) => `<tr><td>${escape(row.game)}</td><td>${escape(row.entries_containing_game)}/${escape(summary.entries)}</td><td>${escape(row.per_entry_including_dst.join(", "))}</td><td>${escape(row.appearances_including_dst)}/${escape(summary.roster_appearances)}</td><td>${escape(row.per_entry_offense.join(", "))}</td><td>${escape(row.offensive_appearances)}/${escape(summary.offensive_appearances)}</td></tr>`).join("")}</tbody></table><p>All player appearances include secondary stacks. The primary QB-game cap counts a different quantity. A DAL-HOU primary label can coexist with a four-player CIN-JAX secondary stack; these counts alone do not imply a cap violation.</p>`;
}
