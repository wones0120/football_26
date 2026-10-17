import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { tiersSettingsKey, tierChoiceLabel } from "../src/tiersReporting.ts";

test("Tiers settings are per native pool and separate from other formats",()=>{
 assert.equal(tiersSettingsKey("abc"),"tiers:abc");assert.notEqual(tiersSettingsKey("abc"),tiersSettingsKey("def"));
 assert.match(tierChoiceLabel({player_master_id:"p",reason_codes:[]},[{player_master_id:"p"}]),/Selected/);
 assert.equal(tierChoiceLabel({player_master_id:"p",reason_codes:["game_locked"]},[{player_master_id:"p"}]),"game_locked");
 assert.match(tierChoiceLabel({player_master_id:"q",reason_codes:[]},[{player_master_id:"p"}]),/Alternative/);
});

test("Tiers workspace renders native rules and explicit frozen-baseline limitations",async()=>{
 const require=createRequire(import.meta.url);const ts=await import("typescript"),React=await import("react"),{renderToStaticMarkup}=await import("react-dom/server");
 let code=ts.transpileModule(readFileSync(new URL("../src/Tiers.tsx",import.meta.url),"utf8"),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
 code=code.replace(/import "\.\/SingleStat\.css";/,"").replaceAll('"react"',JSON.stringify(pathToFileURL(require.resolve("react")).href)).replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve("react/jsx-runtime")).href)).replaceAll('"./tiersReporting"',JSON.stringify(new URL("../src/tiersReporting.ts",import.meta.url).href)).replaceAll('"./nativeLineupDownload"',JSON.stringify(new URL("../src/nativeLineupDownload.ts",import.meta.url).href)).replaceAll("import.meta.env.VITE_API_BASE_URL",'""');
 const {Tiers}=await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);const html=renderToStaticMarkup(React.createElement(Tiers,{season:2026,week:6}));
 assert.match(html,/one player from every native tier/);assert.match(html,/at least two NFL games/);assert.match(html,/No salary cap, position quotas or Captain/);assert.match(html,/Rare return and offensive fumble-recovery TD forecasts are unverified/);assert.match(html,/Frozen Sunday Main projection source/);assert.match(html,/Import Tiers CSV/);
});
