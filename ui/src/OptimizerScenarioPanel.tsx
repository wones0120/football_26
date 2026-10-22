import type { PreparedScenario, ScenarioMode, ScenarioResult } from "./scenarioMode";

export function ScenarioControls({value,teams,onChange,disabled}:{value?:ScenarioMode;teams:string[];onChange:(v?:ScenarioMode)=>void;disabled:boolean}) {
  return <fieldset disabled={disabled}><legend>Experimental scenario mode</legend>
    <label className="checkbox-label"><input type="checkbox" checked={Boolean(value)} onChange={e=>onChange(e.target.checked?{team:teams[0]??"",passing_factor:1,rushing_factor:1,rationale:"New-model primary forecast; no authored volume change",scoring_mode:"new_model_primary"}:undefined)} />
      <span>Compare one scenario lineup with a matched baseline lineup</span></label>
    {value&&<><p>One team, one lineup, two bounded solves. Player locks must be cleared explicitly. Your stored optimizer choices remain available when this mode is off.</p>
      <label>Scoring mode<select aria-label="Scenario scoring mode" value={value.scoring_mode??"sensitivity"} onChange={e=>onChange({...value,scoring_mode:e.target.value as "sensitivity"|"new_model_primary"})}><option value="new_model_primary">New models drive selection · complete score heads</option><option value="sensitivity">Legacy anchored sensitivity · comparison only</option></select></label>
      <p>Primary mode requires published team and player tree/neural forecasts, complete DK scoring heads and a current DST expert. Missing scores never fall back to old projections. Volume factors of 1 use the model forecast unchanged.</p>
      <label>Scenario team<select aria-label="Scenario team" value={value.team} onChange={e=>onChange({...value,team:e.target.value})}><option value="">Choose team</option>{teams.map(t=><option key={t}>{t}</option>)}</select></label>
      <label>Passing volume factor<input aria-label="Passing volume factor" type="number" min="0.5" max="1.5" step="0.05" value={value.passing_factor} onChange={e=>onChange({...value,passing_factor:Number(e.target.value)})} /></label>
      <label>Rushing volume factor<input aria-label="Rushing volume factor" type="number" min="0.5" max="1.5" step="0.05" value={value.rushing_factor} onChange={e=>onChange({...value,rushing_factor:Number(e.target.value)})} /></label>
      <label>Your assumption<input aria-label="Scenario assumption" maxLength={500} value={value.rationale} onChange={e=>onChange({...value,rationale:e.target.value})} /></label>
      <p>These factors are authored assumptions, with unknown likelihood. Prepare freezes supported count/component changes and lists missing evidence. {value.scoring_mode==='new_model_primary'?'Missing complete scores remain unknown and cannot enter the primary lineup.':'Unsupported components retain baseline values.'} Re-prepare after changing an assumption.</p></>}
  </fieldset>;
}

export function PreparedScenarioSummary({report}:{report:PreparedScenario}) {
  return <details><summary>Prepared scenario · {report.config.team} · {report.changed_player_count} player means changed</summary>
    {report.new_model_primary?<p><strong>New models drive selection.</strong> Team/player tree-neural forecasts feed complete DK score heads; DST uses its separately versioned current expert. Old projections are comparison values only. Full game-clock simulation is not active.</p>:<p><strong>Scoring basis: incumbent projection plus supported component changes.</strong> Standalone new-model primary scoring and full-game simulation are not active in this sensitivity mode.</p>}
    {report.primary_model_forecast&&<details><summary>Consumed models, source and team budgets</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify({version:report.primary_model_forecast.version,source:report.primary_model_forecast.source,team_model_publication:report.primary_model_forecast.team_model_consumption?.model_publication_record_id,team_models:report.primary_model_forecast.team_model_consumption?.model_refs,player_model_publication:report.primary_model_forecast.player_model_consumption?.model_publication_record_id,player_models:report.primary_model_forecast.player_model_consumption?.model_refs,scoring_head_version:report.primary_model_forecast.scoring_head?.version,scoring_features:report.primary_model_forecast.scoring_head?.feature_columns,physical_count_budgets:report.primary_model_forecast.physical_count_budgets,dst_expert:report.primary_model_forecast.dst_expert},null,2)}</pre></details>}
    <p>{report.config.rationale} · Passing ×{report.config.passing_factor}; rushing ×{report.config.rushing_factor}. {report.new_model_primary?'Complete new-model point forecast':report.status==='UNAVAILABLE_BASELINE_RETAINED'?'Missing workload evidence; baseline retained':'Partial component sensitivity'}</p>
    {report.issue&&<p role="status">Missing evidence: {report.issue}. Baseline values retained.</p>}
    {report.changed_player_count===0&&<p>No supported numerical change. A run will compare baseline-equivalent scores.</p>}
    <ul>{report.limitations.map(l=><li key={l}>{l}</li>)}</ul>
    <div style={{overflowX:"auto"}} tabIndex={0} aria-label="Scenario player evidence table"><table style={{minWidth:640}}><thead><tr><th>Player</th><th>Baseline mean</th><th>Conditional mean</th><th>Evidence / missing components</th></tr></thead><tbody>
      {report.players.map(p=><tr key={p.player_master_id}><td>{p.name??p.player_master_id} · {p.team}</td><td>{p.baseline_mean?.toFixed(2)??"Unknown"}</td><td>{p.conditional_mean?.toFixed(2)??"Unknown"}</td><td>{p.supported_components.map(c=>c.replaceAll('_',' ')).join(", ")||"No matched component"}{p.missing_evidence.length>0&&<ul>{p.missing_evidence.map((m,i)=><li key={i}>{m}</li>)}</ul>}</td></tr>)}
    </tbody></table></div>
  </details>;
}

export function SavedScenarioSummary({report}:{report:ScenarioResult}) {
  return <section aria-label="Saved scenario comparison"><h4>Experimental scenario · matched baseline comparison</h4>
    <p>Baseline lineup: {report.baseline_mean?.toFixed(2)??"Unavailable"} baseline points ({report.baseline_solver_status}). Scenario lineup: {report.conditional_mean?.toFixed(2)??"Unavailable"} conditional points, {report.scenario_lineup_baseline_mean?.toFixed(2)??"Unavailable"} baseline points.</p>
    <p>{report.prepared.new_model_primary?'The comparison retains incumbent Captain P90/FLEX mean scoring and its shortlist. The primary uses new scores and model coverage under the same user preferences and existing football eligibility gates; this changes forecasting and generation policy, rather than being a selector-only comparison.':'The matched baseline maximizes baseline mean over the same eligible pool and hard rules.'} Your existing optimizer remains available with scenario mode off. No win probability or superiority is established.</p>
    {Boolean(report.model_coverage_exclusions?.length)&&<p role="status"><strong>Primary coverage exclusions:</strong> {report.model_coverage_exclusions!.map(p=>`${p.name??p.player_id}: ${p.reason}`).join("; ")}. Their old-model assessments remain in the comparison. Inspect the prepared evidence below.</p>}
    <details><summary>Matched baseline lineup</summary><ul>{report.baseline_lineup.map(p=><li key={p.player_id}>{p.roster_position??p.position} · {p.name} · ${p.salary} · {p.projection.toFixed(2)} baseline points</li>)}</ul></details>
    <PreparedScenarioSummary report={report.prepared}/>
  </section>;
}
