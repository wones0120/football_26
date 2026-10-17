import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";

test("weekly library exposes persisted original reports and versions without rebuild",async()=>{
 const require=createRequire(import.meta.url),ts=await import("typescript"),React=await import("react"),{renderToStaticMarkup}=await import("react-dom/server");
 let code=ts.transpileModule(readFileSync(new URL("../src/WeeklyLearningLibrary.tsx",import.meta.url),"utf8"),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
 code=code.replace(/import "\.\/WeeklyLearningLibrary\.css";/,"").replaceAll('"react"',JSON.stringify(pathToFileURL(require.resolve("react")).href)).replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve("react/jsx-runtime")).href)).replaceAll("import.meta.env.VITE_API_BASE_URL",'""');
 const {WeeklyLearningLibrary}=await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
 const html=renderToStaticMarkup(React.createElement(WeeklyLearningLibrary,{entryUser:"",onOpen:()=>{}}));
 assert.match(html,/Saved week learning reports/);assert.match(html,/Show previous versions/);assert.match(html,/does not rebuild/);assert.match(html,/Enter a DraftKings username/);
 const source=readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");assert.match(source,/updateLearningContext\(\{ season: report.season, week: report.week \}\)/);assert.match(source,/current\?\.season === learningSeason && current.week === learningWeek/);
});
