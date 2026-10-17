import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {analystOptimizerParams} from "../src/analystPacket.ts";

test("joint opportunity is explicit opt-in and absent for baseline/original strategy",()=>{
 const packet:any={selected_strategy:"MERGED_SCENARIOS",joint_opportunity_enabled:true};assert.equal(analystOptimizerParams(packet).analyst_joint_opportunity_enabled,true);
 assert.equal(analystOptimizerParams(null).analyst_joint_opportunity_enabled,undefined);assert.equal(analystOptimizerParams({...packet,selected_strategy:"CONSTRUCTION"}).analyst_joint_opportunity_enabled,undefined);
 assert.equal(analystOptimizerParams({...packet,joint_opportunity_enabled:false},"showdown").analyst_joint_opportunity_enabled,false);
});

test("full-lineup success explanation labels heuristic objective and source limits",async()=>{
 const require=createRequire(import.meta.url),ts=await import("typescript"),React=await import("react"),{renderToStaticMarkup}=await import("react-dom/server");
 let code=ts.transpileModule(readFileSync(new URL("../src/JointOpportunitySummary.tsx",import.meta.url),"utf8"),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
 code=code.replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve("react/jsx-runtime")).href));
 const {JointOpportunitySummary}=await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
 const summary={how_lineup_succeeds:"Competitive drives; QB and receiving roles score together",score:110,conditional_mean_sum:100,independent_tail_sum:40,supported_tail_credit:28.57,credit_weight:.35,key_dependencies:["TD allocation unknown"],relationships:[{players:["QB","WR"],relationship:"Shared passing event"}],budget_balances:[],player_tail_credit:[]};
 const html=renderToStaticMarkup(React.createElement(JointOpportunitySummary,{summary}));assert.match(html,/How this full lineup can succeed/);assert.match(html,/not a lineup P90 or win probability/);assert.match(html,/No teammate ban or game-total cutoff/);assert.match(html,/TD allocation unknown/);assert.match(html,/QB \+ WR/);
});
