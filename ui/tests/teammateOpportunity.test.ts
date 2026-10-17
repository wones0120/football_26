import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { canStageCheaperPair, cheaperPairChoice, type TeammatePair } from "../src/teammateOpportunity.ts";
const report = JSON.parse(readFileSync(new URL('../../research/analyst_teammate_opportunity_20261014/frozen_model_precheck.json',import.meta.url),'utf8'));
const corum: TeammatePair = report.pairs.find((p:TeammatePair)=>p.backup_name==='Blake Corum');
test("negative full-roster cost is not hidden and requires explicit saved-pair choice",()=>{
  assert.ok(corum.conditional_mean_delta! < 0);assert.ok(canStageCheaperPair(corum));
  assert.deepEqual(cheaperPairChoice('saved-run',corum),{source_optimizer_run_id:'saved-run',pair_id:corum.pair_id,branch:'cheaper'});
  assert.ok(corum.conditional_point_checks!.every(c=>c.delta_vs_primary<0));
});
test("Chicago Q/salary failures remain rejected rather than made applicable",()=>{
  const chicago: TeammatePair[] = report.pairs.filter((p:TeammatePair)=>p.team==='CHI');assert.ok(chicago.length);
  for(const pair of chicago){assert.equal(canStageCheaperPair(pair),false);assert.throws(()=>cheaperPairChoice('saved-run',pair));}
});
test("actual paired report React table renders costs, legal complete rosters and explicit actions",async()=>{
  const {createRequire}=await import('node:module'),{pathToFileURL}=await import('node:url');const require=createRequire(import.meta.url);
  const ts=await import('typescript'),React=await import('react'),{renderToStaticMarkup}=await import('react-dom/server');
  const source=readFileSync(new URL('../src/TeammateOpportunityReview.tsx',import.meta.url),'utf8');
  let code=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  code=code.replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href)).replaceAll('"./teammateOpportunity"',JSON.stringify(new URL('../src/teammateOpportunity.ts',import.meta.url).href));
  const {TeammateOpportunityReview}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const html=renderToStaticMarkup(React.createElement(TeammateOpportunityReview,{report,busy:false,onChoose:()=>{}}));
  assert.match(html,/Blake Corum/);assert.match(html,/Kyle Monangai/);assert.match(html,/Paired conditional mean/);assert.match(html,/Use cheaper branch with original Analyst inputs/);assert.match(html,/disabled=""/);assert.match(html,/complete paired rosters/);assert.match(html,/current questionable exclusion retained/);
  const applied = renderToStaticMarkup(React.createElement(TeammateOpportunityReview,{report:{...report,applied_choice:{source_optimizer_run_id:'source-run',pair_id:corum.pair_id,replaced_allocation_slot:3,constraints_relaxed:false,conditional_assumption:'Explicit saved hypothesis',negative_conditional_cost_accepted_by_explicit_choice:true}},busy:false,onChoose:()=>{}}));
  const focused = renderToStaticMarkup(React.createElement(TeammateOpportunityReview,{report:{...report,pairs:[corum]},busy:false,focusOnly:true,onChoose:()=>{}}));
  assert.match(focused,/Selected-only scenario focus excludes/);assert.match(focused,/<button disabled="">Use cheaper branch/);
  assert.match(applied,/Explicit cheaper branch applied to allocation slot 3/);assert.match(applied,/source-run/);assert.match(applied,/Constraints relaxed:.*no/);
});
