import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

test('saved personal context distinguishes read, scenario linkage and actual construction effect', async () => {
  const require=createRequire(import.meta.url),ts=await import('typescript'),React=await import('react'),{renderToStaticMarkup}=await import('react-dom/server');
  let code=ts.transpileModule(readFileSync(new URL('../src/PersonalThoughtSummary.tsx',import.meta.url),'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  code=code.replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href));
  const {PersonalThoughtSummary}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const context={considered:[{belief_id:'belief',belief_version_id:'version2',thought_text:'PHI concern <script>',status:'read_qualitative_only',decision_id:'approved1',related_scenario_ids:['phi-branch'],not_applied_reason:'No typed effect approved',conditional_mechanism:'If pressure rises, efficiency may fall.',resolved_scope:{team:'PHI',game_ids:['CAR_PHI']}}],rejected:[{belief_version_id:'draft1',reasons:['no_current_version_context_approval']}],affected_construction:false,changed_selected_rosters:false,packet_sha256:'checkedpacket'};
  const html=renderToStaticMarkup(React.createElement(PersonalThoughtSummary,{context}));
  assert.match(html,/1 read/);assert.match(html,/construction unchanged/);assert.match(html,/no change attributed/);
  assert.match(html,/version2/);assert.match(html,/approved1/);assert.match(html,/CAR_PHI/);assert.match(html,/phi-branch/);assert.match(html,/checkedpacket/);assert.match(html,/No typed effect approved/);
  assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});


test('portable saved report retains thought provenance and honest effect statement', async () => {
  const {personalThoughtReportHtml}=await import('../src/optimizerReport.ts');
  const html=personalThoughtReportHtml({analyst_handoff_applied:{personal_context:{considered:[{belief_version_id:'v2',thought_text:'PHI <concern>',decision_id:'approval',related_scenario_ids:['phi-alternate'],not_applied_reason:'Qualitative approval only',resolved_scope:{team:'PHI'}}],rejected:[],affected_construction:false,changed_selected_rosters:false,packet_sha256:'hash'}}} as any);
  assert.match(html,/PHI &lt;concern&gt;/);assert.match(html,/v2/);assert.match(html,/approval/);assert.match(html,/phi-alternate/);assert.match(html,/unchanged/);assert.match(html,/no change attributed/);
});
