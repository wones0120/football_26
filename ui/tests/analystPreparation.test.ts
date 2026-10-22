import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { checkedAnalystSelection, analystHandoffIssue, scopedAnalystHandoff, type AnalystHandoff } from "../src/analystPreparation.ts";
import type { AnalystPacketMetadata } from "../src/analystPacket.ts";
const checked = { analyst_packet_sha256:"checked",packet_id:"checked-v2",scenario_count:1,scenario_options:[{scenario_id:"denver",focus_applicable:true}] } as AnalystPacketMetadata;
const receipt = {mode:"AUTO",status:"needs_review",checked_packet_sha256:"checked",source_packet_sha256:"source",preferred_strategy:"MERGED_SCENARIOS",active_features:["scenario-first"],changes:[{kind:"weakened",reason:"Current role is unverified"}],missing_checks:["Current protection recheck unavailable"],checked_at:"2026-10-14T14:00:00Z",packet_id:"checked-v2"} as AnalystHandoff;
test("Prepare receipt automatically carries checked research despite explicit experimental unknowns",()=>{
  const selected=checkedAnalystSelection("AUTO",receipt,checked,null);
  assert.equal(selected?.analyst_packet_sha256,"checked");assert.equal(selected?.selected_strategy,"MERGED_SCENARIOS");
  assert.equal(analystHandoffIssue("AUTO",receipt,selected),null);
  assert.match(analystHandoffIssue("AUTO",receipt,null)!,/not checked/);
  assert.match(analystHandoffIssue("AUTO",{...receipt,checked_packet_sha256:null},null)!,/no checked/);
});
test("manual strategy, focus and flags survive checked version while explicit baseline stays baseline",()=>{
  const manual={...checked,analyst_packet_sha256:"source",focus_mode:"SELECTED_ONLY",focus_ids:["denver"],selected_strategy:"CONSTRUCTION",challenger_enabled:true} as AnalystPacketMetadata;
  const selected=checkedAnalystSelection("MANUAL",receipt,checked,manual);
  assert.equal(selected?.analyst_packet_sha256,"checked");assert.equal(selected?.selected_strategy,"CONSTRUCTION");assert.deepEqual(selected?.focus_ids,["denver"]);assert.equal(selected?.challenger_enabled,true);
  assert.equal(checkedAnalystSelection("BASELINE",receipt,checked,manual),null);
  assert.equal(analystHandoffIssue("BASELINE",null,null),null);
  const other={...manual,analyst_packet_sha256:"another"};
  assert.equal(checkedAnalystSelection("MANUAL",receipt,checked,other),other);
  assert.match(analystHandoffIssue("MANUAL",receipt,other)!,/Prepare again/);
});
test("normal Prepare and Optimize wire handoff and display actual changes without manual hash",async()=>{
  const app=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  assert.match(app,/analyst_mode: analystHandoffMode/);assert.match(app,/analyst_handoff_compatibility_sha256:normalCheckedHandoff.compatibility_sha256/);assert.match(app,/onSelect=\{selectAnalystOverride\}/);
  const {createRequire}=await import('node:module'),{pathToFileURL}=await import('node:url');const require=createRequire(import.meta.url);
  const ts=await import('typescript'),React=await import('react'),{renderToStaticMarkup}=await import('react-dom/server');
  let code=ts.transpileModule(readFileSync(new URL('../src/AnalystPreparationSummary.tsx',import.meta.url),'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  code=code.replace(/import \{ PersonalThoughtSummary \} from \"\.\/PersonalThoughtSummary\";/, 'const PersonalThoughtSummary=()=>null;');
  let researchCode=ts.transpileModule(readFileSync(new URL('../src/AnalystResearchSummary.tsx',import.meta.url),'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  researchCode=researchCode.replace('"./analystResearchEvidence"',JSON.stringify(new URL('../src/analystResearchEvidence.ts',import.meta.url).href));
  researchCode=researchCode.replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href));
  code=code.replace('"./AnalystResearchSummary"',JSON.stringify(`data:text/javascript;base64,${Buffer.from(researchCode).toString('base64')}`));
  code=code.replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href));
  const {AnalystPreparationSummary}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const html=renderToStaticMarkup(React.createElement(AnalystPreparationSummary,{handoff:receipt,mode:"AUTO",busy:false,onAutomatic:()=>{}}));
  assert.match(html,/Authored football research/);assert.match(html,/automatic/);assert.match(html,/Current role is unverified/);assert.match(html,/Current protection recheck unavailable/);assert.match(html,/checked-v2/);
  let automaticChosen=false;
  const tree=AnalystPreparationSummary({handoff:receipt,mode:"BASELINE",busy:false,onAutomatic:()=>{automaticChosen=true;}});
  const button=tree.props.children.props.children.find((child: {type?:string})=>child?.type==='button');
  assert.equal(button.props.disabled,false);button.props.onClick();assert.equal(automaticChosen,true);
});

test("checked handoff is exact scoped across uppercase server format and UI format",()=>{
  const handoff={...receipt,scope:{season:2026,week:6,slate:"SUNDAY_MAIN",format:"CLASSIC" as const}};
  assert.equal(scopedAnalystHandoff(handoff,{season:2026,week:6,slate:"sunday_main",format:"classic"}),handoff);
  assert.equal(scopedAnalystHandoff(handoff,{season:2026,week:6,slate:"THURSDAY_NIGHT",format:"showdown"}),null);
});
