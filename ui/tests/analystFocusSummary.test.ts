import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

test("saved focus summary distinguishes failed and missing evidence and labels explicit what-if", async () => {
  const require = createRequire(import.meta.url);
  const ts = await import("typescript"), React = await import("react"), { renderToStaticMarkup } = await import("react-dom/server");
  let code = ts.transpileModule(readFileSync(new URL("../src/AnalystFocusSummary.tsx", import.meta.url), "utf8"), { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  code = code.replaceAll('"react/jsx-runtime"', JSON.stringify(pathToFileURL(require.resolve("react/jsx-runtime")).href));
  const { AnalystFocusSummary, focusCompliance } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
  const results = [[{}, { analyst_focus_story_compliance: true }], [{ analyst_focus_story_compliance: false }], [{}]];
  assert.deepEqual(focusCompliance(results), { passed: 1, failed: 1, unknown: 1 });
  const focus = { mode: "SELECTED_ONLY", selected_scenario_ids: ["denver_40"], generic_fallback: false, requirements: [{ scenario_id: "denver_40", team: "DEN", script: "passing", authority: "user_what_if", finding: { team_points_target: 40 } }] };
  const html = renderToStaticMarkup(React.createElement(AnalystFocusSummary, { focus, results }));
  assert.match(html, /40 team points: explicit user what-if/);
  assert.match(html, /1 passed.*1 failed.*1 unavailable/);
  assert.match(html, /Generic fallback:.*disabled/);
  assert.match(html, /probability and ownership leverage are not inferred/);
  const mixed = renderToStaticMarkup(React.createElement(AnalystFocusSummary, { focus: { mode: "MIXED", selected_scenario_ids: [] }, results }));
  assert.match(mixed, /Mixed football portfolio/);
  assert.doesNotMatch(mixed, /Saved construction checks/);
});
