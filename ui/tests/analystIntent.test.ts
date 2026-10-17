import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { intentHandoff, intentComparisonIssue, resultLineups, sharedCore, captainExposure } from '../src/analystIntent.ts';
import type { OptimizerResponse, PreparedBuild } from '../src/api.ts';

function run(intent: 'EXPECTED_GAME' | 'CONTRARIAN'): OptimizerResponse {
  return {job_id:intent,status:'completed',projection_run_id:'same-projection',football_analyst:{requested_portfolio_size:1,
    preparation_compatibility:{prepared_source_sha256:'same-source'},
    optimization_intent:{intent,assessment:intent==='EXPECTED_GAME'?'Primary competitive game and upside':'Conditional DEN breakout, not a prediction',scenario_ids:[intent],scope:{season:2026,week:6,slate:'THURSDAY_NIGHT',format:'SHOWDOWN'}}},
    results:[[{player_id:'a',name:'Captain A',roster_position:'CPT',player_team:'DEN',salary:9000,ownership_run_id:'same-owner'},{player_id:'b',name:'Flex B',roster_position:'FLEX',player_team:'SEA',salary:5000,ownership_run_id:'same-owner'}]]} as OptimizerResponse;
}

test('intent handoff cannot fall back to mixed research when an intent is missing',()=>{
  const mixed={checked_packet_sha256:'mixed'}, expected={checked_packet_sha256:'expected'};
  const build={analyst_handoff:mixed,analyst_intent_handoffs:{EXPECTED_GAME:expected}} as PreparedBuild;
  assert.equal(intentHandoff(build,'EXPECTED_GAME'),expected);
  assert.equal(intentHandoff(build,'CONTRARIAN'),null);
  assert.equal(intentHandoff(build,'MIXED'),mixed);
});

test('comparison requires matched source/projection and reports actual saved rows/shared core',()=>{
  const a=run('EXPECTED_GAME'),b=run('CONTRARIAN');
  assert.equal(intentComparisonIssue(a,b),null);
  assert.match(intentComparisonIssue(a,{...b,projection_run_id:'other'})!,/not a matched/);
  assert.match(intentComparisonIssue(a)!,/Generate each intent/);
  assert.match(intentComparisonIssue(a,{...b,results:[[{...resultLineups(b)[0][0],ownership_run_id:'different-owner'}]]})!,/Ownership lineage/);
  assert.equal(resultLineups(a).length,1);
  assert.deepEqual(sharedCore(a),['Captain A','Flex B']);
  assert.deepEqual(captainExposure(a),['Captain A 1/1 (100%)']);
});

test('app selects scoped intent receipt and persists intent independently from lineup controls',()=>{
  const app=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  assert.match(app,/aria-label="Optimization intent"/);
  assert.match(app,/intentHandoff\(preparationStatus\?\.latest_build, optimizationIntent\)/);
  assert.match(app,/analyst_optimization_intent: optimizationIntent/);
  assert.match(app,/dfs-optimization-intents-v1/);
  assert.match(app,/<AnalystIntentComparison key=\{activeContextKey\}/);
});

test('saved comparison renders both distinct intents with actual Captain/FLEX salaries',async()=>{
  const {createRequire}=await import('node:module'),{pathToFileURL}=await import('node:url');const require=createRequire(import.meta.url);
  const ts=await import('typescript'),React=await import('react'),{renderToStaticMarkup}=await import('react-dom/server');
  let code=ts.transpileModule(readFileSync(new URL('../src/AnalystIntentComparison.tsx',import.meta.url),'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  code=code.replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href))
    .replaceAll("'react'",JSON.stringify(pathToFileURL(require.resolve('react')).href))
    .replaceAll("'./api'",JSON.stringify('data:text/javascript,export async function fetchOptimizerResults(){}'))
    .replaceAll("'./analystIntent'",JSON.stringify(new URL('../src/analystIntent.ts',import.meta.url).href))
    .replace(/import ['"]\.\/AnalystIntentComparison.css['"];?/,'');
  const {IntentComparisonView}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const html=renderToStaticMarkup(React.createElement(IntentComparisonView,{runs:{EXPECTED_GAME:run('EXPECTED_GAME'),CONTRARIAN:run('CONTRARIAN')}}));
  assert.match(html,/Expected Game/);assert.match(html,/Contrarian/);assert.match(html,/Separate candidate generation pools/);
  assert.match(html,/CPT/);assert.match(html,/FLEX/);assert.match(html,/\$9,000/);assert.match(html,/\$14,000/);
  assert.match(html,/Conditional DEN breakout, not a prediction/);
});

test('Classic preliminary snapshots select only their exact checked intent', () => {
  const expected={checked_packet_sha256:'expected-classic'},contrarian={checked_packet_sha256:'contrarian-classic'};
  const snapshot={analyst_handoff:{checked_packet_sha256:'mixed-classic'},analyst_intent_handoffs:{EXPECTED_GAME:expected,CONTRARIAN:contrarian}} as PreparedBuild;
  assert.equal(intentHandoff(snapshot,'EXPECTED_GAME'),expected);
  assert.equal(intentHandoff(snapshot,'CONTRARIAN'),contrarian);
  const app=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  assert.match(app,/const snapshotHandoff = highestProjection \? null : intentHandoff\(snapshot, optimizationIntent\)/);
  assert.match(app,/optimizationIntent=\{highestProjection \? "MIXED" : optimizationIntent\}/);
});
