// Real built UI with isolated API responses. No application data or live writes.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../", import.meta.url));
const artifacts = root + "artifacts/showdown_captain_position_preferences/ui_fixture";
mkdirSync(artifacts, { recursive: true });
const server = createServer((req,res) => {
  const path = new URL(req.url,"http://localhost").pathname;
  const file = resolve(root,"ui/dist","."+(path==="/"?"/index.html":path));
  if (!file.startsWith(resolve(root,"ui/dist")+"/")) return res.writeHead(403).end();
  try { res.setHeader("content-type",file.endsWith(".js")?"text/javascript":file.endsWith(".css")?"text/css":"text/html");res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r=>server.listen(0,"127.0.0.1",r));
const base=`http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser=await chromium.launch({headless:true,channel:"chrome"});
  const context=await browser.newContext({viewport:{width:1440,height:1100},serviceWorkers:"block"});
  const page=await context.newPage();const errors=[];const writes=[];
  page.on("pageerror",e=>errors.push(e.message));
  const readiness={status:"pass",score:100,summary:{pass:1,warn:0,fail:0},checks:[],
    gates:Object.fromEntries(["prediction","classic_gpp","classic_cash","showdown_gpp","showdown_cash"].map(k=>[k,{status:"pass",score:100,summary:{pass:1,warn:0,fail:0},blocking_checks:[],attention_checks:[],message:"Synthetic ready"}]))};
  let requestReady;let pendingRoute;let captured;
  await context.route("**/*",route=>new URL(route.request().url()).origin===base && route.request().method()==="GET"?route.continue():route.abort());
  await context.route("**/api/**",route=>{
    const req=route.request();const path=new URL(req.url()).pathname.replace(/^\/api/,"");
    const reply=(data,status=200)=>route.fulfill({status,contentType:"application/json",body:JSON.stringify(data)});
    if(req.method()!=="GET")writes.push({path,body:req.postDataJSON()});
    if(path==="/meta/current")return reply({season:2000,week:1,slate:"SUNDAY_MAIN"});
    if(path==="/slate/readiness")return reply(readiness);
    if(path==="/slate/identity-reconcile")return reply({salary_rows_seen:0,salary_rows_resolved:0,salary_rows_quarantined:0});
    if(path==="/optimizer/runs")return reply({runs:[]});
    if(path==="/optimizer/projections")return reply({runs:[]});
    if(path==="/jobs" || path==="/weekly/runs")return reply({rows:[]});
    if(path==="/slate/preparation")return reply({scope:{season:2000,week:1,slate:"SUNDAY_MAIN"},server_time:"2000-01-01T00:00:00Z",inputs:{salaries:[],injuries:[]},jobs:[],prelock:true,latest_build:null,build_current:false,entry_ready:false,limitations:[]});
    if(path==="/optimizer/jobs") {captured=req.postDataJSON();pendingRoute=route;requestReady();return;}
    if(path==="/weekly-runs")return reply({detail:"Synthetic weekly request captured"},422);
    return reply({detail:"Unavailable in isolated Captain fixture"},503);
  });
  await page.addInitScript(()=>localStorage.setItem("football-26-active-slate-context",JSON.stringify({season:2000,week:1,slate:"SUNDAY_MAIN"})));
  await page.goto(base);await page.getByRole("button",{name:"Operations",exact:true}).click();
  const format=page.locator(".operations-optimizer-panel").getByRole("combobox",{name:"Strategy",exact:true});
  assert.equal(await page.getByLabel("Captain position",{exact:true}).count(),0);
  await format.selectOption("showdown");
  const control=page.getByLabel("Captain position",{exact:true});
  assert.equal(await control.inputValue(),"WR,RB");
  assert.deepEqual(await control.locator("option").allTextContents(),["Any position","WR/RB only (default)","WR/RB/TE only","WR only","RB only","TE only"]);
  await page.getByLabel("Refresh ownership before optimizing").uncheck();
  for(const mode of ["gpp"]) {
    for(const [value,positions] of [["WR,RB",["WR","RB"]],["",[]],["WR,RB,TE",["WR","RB","TE"]],["WR",["WR"]],["RB",["RB"]],["TE",["TE"]]]) {
      await control.selectOption(value);
      const ready=new Promise(r=>requestReady=r);
      await page.getByRole("button",{name:"Run Optimizer",exact:true}).click();
      await Promise.race([ready,new Promise((_,reject)=>setTimeout(()=>reject(new Error("Captain request was not submitted")),8000))]);
      assert.deepEqual(captured.params.captain_positions,positions);
      assert.equal(captured.contest_format,"showdown");assert.equal(captured.objective,mode);
      assert.equal(await control.isDisabled(),true);
      await pendingRoute.fulfill({status:422,contentType:"application/json",body:JSON.stringify({detail:"Synthetic Captain request captured"})});
      await page.getByText("Synthetic Captain request captured",{exact:true}).waitFor();
      await page.waitForFunction(()=>!document.querySelector('select[aria-label="Captain position"]').disabled);
    }
  }
  await format.selectOption("classic");assert.equal(await control.count(),0);
  await format.selectOption("showdown");assert.equal(await control.inputValue(),"TE");
  await page.getByTestId("weekly-pipeline-options").locator(":scope > summary").click();
  await page.getByLabel(/^DraftKings directory/).fill("/synthetic/NFL");
  await page.getByRole("button",{name:"Run Weekly Pipeline",exact:true}).click();
  await page.getByText("Synthetic weekly request captured",{exact:true}).waitFor();
  assert.deepEqual(writes.find(r=>r.path==="/weekly-runs").body.optimizer_params.captain_positions,["TE"]);
  const preferences=page.getByLabel("Showdown lineup preferences",{exact:true});
  await preferences.screenshot({path:artifacts+"/captain-desktop.png"});
  await page.setViewportSize({width:390,height:844});
  await preferences.screenshot({path:artifacts+"/captain-mobile.png"});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),"Controls must fit mobile width");
  assert.deepEqual(errors,[]);
  assert.equal(writes.filter(r=>r.path==="/optimizer/jobs").length,6);
  writeFileSync(artifacts+"/requests.json",JSON.stringify(writes,null,2));
  console.log("PASS: all Captain choices submit in GPP; weekly parameter retained; Classic hidden; choice survives format switches; pending state disabled; desktop/mobile fit; no browser errors. Synthetic API only.");
} finally {await browser?.close();await new Promise(r=>server.close(r));}
