export const SHARED_WORLD_POLICY = "expected_anchor_incremental_world_gain_v1";
type Row = Record<string, unknown>;
const obj = (v: unknown): Row => v && typeof v === "object" && !Array.isArray(v) ? v as Row : {};
const arr = (v: unknown): Row[] => Array.isArray(v) ? v.map(obj) : [];
const str = (v: unknown) => typeof v === "string" ? v : "";
const num = (v: unknown) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(2) : "unknown";

export function sharedWorldEvidence(value: unknown, players: unknown = []) {
  const report = obj(value);
  if (report.policy_id !== SHARED_WORLD_POLICY) return null;
  const names = new Map(arr(players).map(p => [str(p.player_id ?? p.player_master_id), str(p.name ?? p.player_name)]));
  const roster = (v: unknown) => arr(v).map(p => `${str(p.role)}: ${names.get(str(p.player_master_id)) || str(p.player_master_id)}`).join(" · ");
  const worlds = arr(report.frozen_world_inputs);
  return {
    status: str(report.status), anchor: str(report.anchor_world_id), anchorBasis: str(report.anchor_selection_reason),
    coverageSummary:arr(report.selection_steps).length>0 && !arr(report.selection_steps).slice(1).some(s=>typeof s.maximum_incremental_gain_points==="number" && s.maximum_incremental_gain_points>0)
      ? "No incremental scenario coverage achieved; entries differ under hard controls, not demonstrated scenario diversification."
      : "Incremental conditional coverage, where present, measures saved common-world point gains; world likelihoods remain unknown.",
    achieved: report.achieved, requested: report.requested,
    probability: str(report.probability_status), completion: str(report.completion_status),
    limits: obj(report.generation_limits), controls: obj(report.user_controls),
    omitted: arr(report.omitted_strategy_construction_rules).map(r => str(r.rule_id)),
    worlds: worlds.map(w => ({id:str(w.world_id), mechanism:str(w.mechanism),
      components:arr(obj(obj(w.count_component_response).response).players).filter(p=>names.has(str(p.player_master_id))).map(p=>{
        const response=obj(obj(w.count_component_response).response);
        const before=arr(obj(obj(response.semantic_values).reference).players).find(a=>a.player_master_id===p.player_master_id);
        const after=arr(obj(obj(response.semantic_values).new).players).find(a=>a.player_master_id===p.player_master_id);
        const counts=(a:Row|undefined)=>`${num(obj(a?.counts).pass_attempts)} pass attempts / ${num(obj(a?.counts).rush_attempts)} rush attempts / ${num(obj(a?.counts).targets)} targets`;
        return `${names.get(str(p.player_master_id))}: conditional expected physical counts reference ${counts(before)} → world ${counts(after)} (unmultiplied at Captain); base FP ${num(p.base_fp)} → conditional FP ${num(p.conditional_mean)} (change ${num(p.conditional_delta_points)}; matched linear change ${num(p.linear_component_delta_points)}). Supported: ${Array.isArray(p.supported_components)?p.supported_components.join(", "):"unknown"}. ${str(p.assumption)}${p.inactive_override?" Factual OUT: all world production zero; base assessment preserved.":""}${p.anchor_inconsistency?" Reference linear points exceed base: anchoring inconsistency flagged.":""}`;}),
      counter: Array.isArray(w.counterevidence) ? w.counterevidence.map(String) : [],
      unknowns: Array.isArray(w.unknowns) ? w.unknowns.map(String) : [],
      sources: Array.isArray(w.source_refs) ? w.source_refs.map(String).join(", ") : "unavailable"})),
    steps: arr(report.selection_steps).map(s => ({rank:s.rank, roster:roster(s.roster),
      reason:str(s.reason), anchorMean:num(s.anchor_conditional_mean_points), baseMean:num(s.original_base_expected_points),
      gain:num(s.maximum_incremental_gain_points), risk:str(s.shared_risk),
      paths:arr(s.football_paths).map(p=>`${str(p.world_id)}: ${str(p.mechanism)}${Array.isArray(p.counterevidence)&&p.counterevidence.length?` Counterevidence: ${p.counterevidence.join("; ")}`:""}${Array.isArray(p.unknowns)&&p.unknowns.length?` Unknowns: ${p.unknowns.join("; ")}`:""}`),
      roles:arr(s.roster_roles).map(p=>`${str(p.role)} ${str(p.name)} · ${str(p.team)||"team unknown"} ${str(p.position)||"position unknown"} · current role: ${str(p.current_role)||"unknown"} · role proof: ${str(p.role_evidence_status)}${Object.entries(obj(p.role_source_lineage)).map(([k,v])=>` · ${k}: ${Array.isArray(v)?v.join(", "):String(v)}`).join("")}`),
      couplings:arr(s.team_role_couplings).map(p=>`${str(p.team)}: ${arr(p.actors).map(a=>`${str(a.name)} (${str(a.position)})`).join(", ")}. ${str(p.interpretation)}`),
      alternative:roster(obj(s.strongest_admissible_alternative).roster),
      alternativeAnchor:num(obj(s.strongest_admissible_alternative).anchor_conditional_mean_points),
      alternativeTradeoff: s.strongest_admissible_alternative ? `Alternative salary ${num(obj(s.strongest_admissible_alternative).salary)}; original mean ${num(obj(s.strongest_admissible_alternative).original_base_expected_points)}. Selected minus alternative: salary ${num(obj(s.strongest_admissible_alternative).selected_minus_alternative_salary)}, anchor mean ${num(obj(s.strongest_admissible_alternative).selected_minus_alternative_anchor_mean)}, original mean ${num(obj(s.strongest_admissible_alternative).selected_minus_alternative_base_mean)}, incremental gain ${num(obj(s.strongest_admissible_alternative).selected_minus_alternative_maximum_incremental_gain)}. Entering selected roster: ${arr(obj(s.strongest_admissible_alternative).entering_actors).map(a=>str(a.name)).join(", ")||"none (slot role may change)"}; leaving alternative: ${arr(obj(s.strongest_admissible_alternative).leaving_actors).map(a=>str(a.name)).join(", ")||"none (slot role may change)"}.`: "",
      worlds:arr(s.world_assessments).map(w=>({label:arr(w.world_aliases).map(a=>str(a.world_id)).join(" / "),
        points:num(w.full_roster_points), gap:num(w.remaining_portfolio_gap_points)}))})),
  };
}

export function sharedWorldHtml(value: unknown, players: unknown = []): string {
  const r=sharedWorldEvidence(value,players); if(!r)return "";
  const e=(v:unknown)=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
  return `<section class="lineup"><h2>Whole-lineup game-world selection</h2><p>${e(r.status)} · ${e(r.achieved)}/${e(r.requested)} · Anchor: ${e(r.anchor)}</p><p><strong>${e(r.coverageSummary)}</strong></p><p>${e(r.anchorBasis)}</p><p>${e(r.probability)}</p><p>${e(r.completion)}</p>${r.steps.map(s=>`<h3>Saved lineup ${e(s.rank)}</h3><p>${e(s.roster)}</p><p>${e(s.reason)}</p>${s.paths.map(p=>`<p>Success path: ${e(p)}</p>`).join("")}${s.roles.map(p=>`<p>${e(p)}</p>`).join("")}${s.couplings.map(p=>`<p>Shared opportunity: ${e(p)}</p>`).join("")}<p>Anchor mean ${e(s.anchorMean)} · original mean ${e(s.baseMean)} · incremental conditional points ${e(s.gain)}</p><p>${e(s.risk)}</p><p>Strongest admissible alternative: ${e(s.alternative)} · anchor mean ${e(s.alternativeAnchor)}</p><p>${e(s.alternativeTradeoff)}</p>${s.worlds.map(w=>`<p>${e(w.label)}: ${e(w.points)} conditional points; remaining pool gap ${e(w.gap)}</p>`).join("")}`).join("")}${r.worlds.map(w=>`<h3>${e(w.id)}</h3><p>${e(w.mechanism)}</p>${w.components.map(v=>`<p>Count/component response: ${e(v)}</p>`).join("")}${w.counter.map(v=>`<p>Counterevidence: ${e(v)}</p>`).join("")}${w.unknowns.map(v=>`<p>Unknown: ${e(v)}</p>`).join("")}<p>Source lineage: ${e(w.sources)}</p>`).join("")}</section>`;
}
