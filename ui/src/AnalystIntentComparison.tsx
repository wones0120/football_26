import { useEffect, useState } from 'react';
import { fetchOptimizerResults, type OptimizerResponse } from './api';
import { intentComparisonIssue, intentLabel, resultLineups, sharedCore, captainExposure, type OptimizationIntent } from './analystIntent';
import './AnalystIntentComparison.css';
type Intent = Exclude<OptimizationIntent, 'MIXED'>;
const intents: Intent[] = ['EXPECTED_GAME', 'CONTRARIAN'];
export function AnalystIntentComparison({contextKey, current, scope}: {contextKey: string; current: OptimizerResponse | null; scope: {season: number; week: number; slate: string}}) {
  const storageKey = `dfs-intent-comparison-v1:${contextKey}`;
  const [ids, setIds] = useState<Partial<Record<Intent, string>>>(() => { try { return JSON.parse(localStorage.getItem(storageKey) ?? '{}'); } catch { return {}; } });
  const [runs, setRuns] = useState<Partial<Record<Intent, OptimizerResponse>>>({});
  const [error, setError] = useState<string | null>(null);
  const currentIntent = current?.football_analyst?.optimization_intent;
  useEffect(() => {
    if (!current || !currentIntent || !intents.includes(currentIntent.intent) || !['completed', 'partial', 'failed'].includes(current.status)) return;
    const s = currentIntent.scope;
    if (s.season !== scope.season || s.week !== scope.week || s.slate.toUpperCase() !== scope.slate.toUpperCase()) return;
    setRuns(value => ({...value, [currentIntent.intent]: current}));
    setIds(value => value[currentIntent.intent] === current.job_id ? value : {...value, [currentIntent.intent]: current.job_id});
  }, [current?.job_id, current?.status, currentIntent?.intent, contextKey]);
  useEffect(() => { try { localStorage.setItem(storageKey, JSON.stringify(ids)); } catch { /* Saved server runs remain available. */ } }, [ids, storageKey]);
  useEffect(() => {
    let active = true;
    for (const intent of intents) {
      const id = ids[intent]; if (!id || runs[intent]?.job_id === id) continue;
      void fetchOptimizerResults(id).then(run => {
        const frozen = run.football_analyst?.optimization_intent;
        if (!frozen || frozen.intent !== intent || frozen.scope.season !== scope.season || frozen.scope.week !== scope.week || frozen.scope.slate.toUpperCase() !== scope.slate.toUpperCase()) throw new Error('Saved intent run belongs to another scope.');
        if (active) setRuns(value => ({...value, [intent]: run}));
      }).catch(err => { if (active) setError(String(err.message ?? err)); });
    }
    return () => { active = false; };
  }, [ids, contextKey]);
  return <IntentComparisonView runs={runs} error={error} />;
}

export function IntentComparisonView({runs, error = null}: {runs: Partial<Record<Intent, OptimizerResponse>>; error?: string | null}) {
  return <section className="intent-comparison" aria-label="Expected Game and Contrarian comparison">
    <h3>Expected Game vs Contrarian · saved runs</h3>
    <p>{intentComparisonIssue(runs.EXPECTED_GAME, runs.CONTRARIAN) ?? 'Matched salary, projection, ownership and source inputs. Separate candidate generation pools; this is not a frozen-pool selector comparison.'}</p>
    {error && <p role="alert">{error}</p>}
    <div className="intent-comparison-columns">{intents.map(intent => {
      const run = runs[intent], lineups = resultLineups(run), frozen = run?.football_analyst?.optimization_intent;
      return <article key={intent}><h4>{intentLabel(intent)}</h4>{!run ? <p>No saved {intentLabel(intent)} run loaded.</p> : <>
        <p>{run.status} · {lineups.length}/{run.football_analyst?.requested_portfolio_size ?? '?'} saved · {run.job_id}</p>
        <p>{frozen?.assessment}</p><p>Scenarios: {frozen?.scenario_ids.join(', ')}</p>
        <p>100% shared core: {sharedCore(run).join(', ') || 'none'}</p>
        <p>Actual Captain exposure: {captainExposure(run).join('; ') || 'none saved'}</p>
        {frozen?.story_requirements && <p>Story requirement: {frozen.story_requirements.team} QB + at least {frozen.story_requirements.minimum_receivers} WR/TE across Captain and FLEX. Captain team remains open.</p>}
        {lineups.map((lineup, index) => <div key={index}><h5>Lineup {index + 1} · ${lineup.reduce((sum, row) => sum + Number(row.salary), 0).toLocaleString()}</h5>
          <p>Generated in: {lineup[0]?.analyst_thesis_ids?.join(', ') || 'unrecorded'}</p>
          <table><thead><tr><th>Slot</th><th>Player</th><th>Team</th><th>Salary</th></tr></thead><tbody>{lineup.map(row => <tr key={row.player_id}><td>{row.roster_position}</td><td>{row.name}</td><td>{row.player_team}</td><td>${Number(row.salary).toLocaleString()}</td></tr>)}</tbody></table>
        </div>)}
        {!lineups.length && <p>{run.message}</p>}
        <p>Research only · final entry readiness is separate.</p>
      </>}</article>;
    })}</div>
  </section>;
}
