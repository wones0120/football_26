export type ScenarioMode = { team: string; passing_factor: number; rushing_factor: number; rationale: string; scoring_mode?:"sensitivity"|"new_model_primary" };
export type PreparedScenario = {
  version: string; sha256: string; config: ScenarioMode; status: string; issue: string | null;
  changed_player_count: number; limitations: string[];
  primary_model_forecast?:Record<string,any>;
  scoring_basis?: string; new_model_primary?: boolean; full_game_simulator_consumed?: boolean;
  players: Array<{player_master_id:string; name?:string; team:string; baseline_mean:number|null;
    conditional_mean:number|null; delta:number|null; supported_components:string[]; missing_evidence:string[]}>;
};
export type ScenarioResult = {prepared:PreparedScenario; baseline_solver_status:string; baseline_mean?:number;
  conditional_mean?:number; scenario_lineup_baseline_mean?:number; baseline_lineup_conditional_mean?:number;
  model_coverage_exclusions?:Array<{player_id:string;name?:string;reason:string}>;
  baseline_lineup:Array<{player_id:string; name:string; position:string; roster_position?:string; salary:number; projection:number}>};

export function scenarioKey(value?: ScenarioMode | null): string {
  return value ? JSON.stringify([value.team,value.passing_factor,value.rushing_factor,value.rationale.trim(),value.scoring_mode??"sensitivity"]) : "baseline";
}
export function scenarioIssue(value?: ScenarioMode): string | null {
  if (!value) return null;
  if (!value.team || !value.rationale.trim()) return "Choose the scenario team and describe your assumption.";
  if (![value.passing_factor,value.rushing_factor].every(n => Number.isFinite(n) && n>=.5 && n<=1.5)) return "Scenario volume factors must be between 0.5 and 1.5.";
  if (value.passing_factor===1 && value.rushing_factor===1 && value.scoring_mode!=="new_model_primary") return "Change at least one scenario volume factor.";
  return null;
}
export function scenarioParams(params:Record<string,unknown>,value?:ScenarioMode,format="classic"):Record<string,unknown> {
  if (!value) return {...params};
  const issue=scenarioIssue(value); if (issue) throw new Error(issue);
  const copy={...params}; for (const key of Object.keys(copy)) if (key.startsWith("analyst_")) delete copy[key];
  // Retain explicit locks; the bounded backend rejects unsupported locks rather than silently clearing them.
  if (format==="showdown") delete copy.classic_selection_objective;
  return {...copy,scenario_mode:value,...(format==="classic"?{classic_selection_objective:"baseline_mean"}:{}),num_lineups:1,
    analyst_handoff_mode:"BASELINE",analyst_optimization_intent:"MIXED"};
}
