// Real built App with isolated API fixtures; backend queue/solver tests are separate.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync,mkdtempSync,writeFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {resolve} from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=resolve(import.meta.dirname,'../..');
const format=process.env.SCENARIO_FORMAT==='showdown'?'showdown':'classic';
const artifacts=mkdtempSync(resolve(root,'artifacts/optimizer-scenario-ui-'));
const server=createServer((req,res)=>{
 const path=new URL(req.url,'http://localhost').pathname;
 const file=resolve(root,'ui/dist','.'+(path==='/'?'/index.html':path));
 if (!file.startsWith(resolve(root,'ui/dist')+'/')) return res.writeHead(403).end();
 try {res.setHeader('content-type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(readFileSync(file));}
 catch {res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1100}});page.setDefaultTimeout(15000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const scope={season:2026,week:4,slate:format==='showdown'?'THURSDAY_NIGHT':'SUNDAY_MAIN'};let ready=false,prepared=null,runId=null,result=null;
 const writes=[];
 const build={...scope,action:'prepare',contest_format:format,prepared_input_job_id:'scenario-prep',projection_run_id:'fixture-projection',feature_run_id:'fixture-features',source_sha256:'fixture',data_readiness:{status:'READY'},availability_overrides:[],assume_questionable_out:false,limitations:[],consumption:{}};
 const player={player_id:'00000000-0000-0000-0000-000000000001',name:'Fixture QB',position:'QB',player_team:'BUF',opponent_team:'NYJ',salary:6000,projection:20};
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname.replace(/^\/api/,'');
  const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  if(req.method()!=='GET')writes.push({path,body:req.postDataJSON()});
  if(path==='/meta/current')return reply(scope);
  if(path==='/slate/imported-scopes')return reply({scopes:[scope]});
  if(path==='/slate/preparation')return reply({scope,server_time:new Date().toISOString(),inputs:{salaries:[{team:'BUF',player_master_id:player.player_id,player_name:player.name,position:'QB'}]},jobs:[],prelock:true,build_current:ready,latest_build:ready?{...build,scenario_mode:prepared}:null,entry_ready:false,limitations:[]});
  if(path==='/slate/preparation/jobs'){
   const config=req.postDataJSON().scenario_mode;
   prepared=config?{version:'prepared_optimizer_scenario_v1',sha256:'fixture-sha',config,new_model_primary:config.scoring_mode==='new_model_primary',status:'NEW_MODELS_PRIMARY',issue:null,changed_player_count:1,limitations:['Synthetic fixture: complete score head; calibration unproven'],players:[{player_master_id:player.player_id,name:player.name,team:'BUF',baseline_mean:20,conditional_mean:22,delta:2,supported_components:['passing_yards'],missing_evidence:['No end-to-end accuracy claim']}]}:null;
   return reply({created:true,job:{job_id:'scenario-prep',status:'queued'}},202);
  }
  if(path==='/jobs/scenario-prep'){ready=true;return reply({job_id:'scenario-prep',status:'completed',result:{...build,scenario_mode:prepared}});}
  if(path==='/optimizer/jobs'){
   runId=req.postDataJSON().optimizer_run_id;
   result={job_id:runId,status:'completed',...scope,strategy:format==='classic'?'classic_large_gpp_v1':'showdown_gpp_portfolio_v3',strategy_config:{},contest_format:format,objective:'gpp',projection_run_id:'fixture-projection',lineage_persisted:true,created_at:new Date().toISOString(),updated_at:new Date().toISOString(),results:[],highest_projection:{objective_label:'Experimental scenario mean',solver_status:'Optimal',base_mean:140,salary:49000,optimal:true,locked_player_ids:[],input_snapshot_sha256:'fixture'},scenario_mode:{prepared,baseline_solver_status:'Optimal',baseline_mean:141,conditional_mean:143,scenario_lineup_baseline_mean:140,baseline_lineup:[player]}};
   return reply({created:true,job:{job_id:'scenario-worker',status:'queued'}},202);
  }
  if(path==='/jobs/scenario-worker')return reply({job_id:'scenario-worker',status:'completed',result:{optimizer_run_id:runId}});
  if(path.startsWith('/optimizer/results/'))return result?reply(result):reply({},404);
  if(path==='/optimizer/runs')return reply({runs:runId?[{...result,optimizer_run_id:runId,num_lineups:1,lineup_count:1,started_at:result.created_at,completed_at:result.updated_at}]:[]});
  if(path==='/optimizer/projections')return reply({runs:[]});
  if(path==='/weekly/runs')return reply({rows:[]});
  return reply({detail:'Unavailable in isolated fixture'},503);
 });
 await page.addInitScript(scope=>localStorage.setItem('football-26-active-slate-context',JSON.stringify(scope)),scope);
 await page.goto(base);await page.getByRole('button',{name:'Operations',exact:true}).click();
 await page.getByLabel('Strategy',{exact:true}).selectOption(format);
 const toggle=page.getByRole('checkbox',{name:'Compare one scenario lineup with a matched baseline lineup'});
 await toggle.waitFor();assert.equal(await toggle.isChecked(),false);
 await toggle.check();await page.getByLabel('Scenario team',{exact:true}).selectOption('BUF');
 await page.getByLabel('Scenario assumption',{exact:true}).fill('Fixture passing pace increase');
 await page.getByRole('button',{name:'Prepare slate for optimization',exact:true}).click();
 const run=page.getByRole('button',{name:'Run Optimizer',exact:true});await run.waitFor();
 await page.waitForFunction(()=>!document.querySelector('button[data-test-nonexistent]')&&[...document.querySelectorAll('button')].some(b=>b.textContent==='Run Optimizer'&&!b.disabled));
 await page.getByLabel('Passing volume factor',{exact:true}).fill('1.25');assert.equal(await run.isDisabled(),true);
 await page.getByRole('button',{name:'Prepare slate for optimization',exact:true}).click();
 await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='Run Optimizer'&&!b.disabled));
 await run.click();await page.getByRole('heading',{name:'Experimental scenario · matched baseline comparison'}).waitFor();
 const submitted=writes.find(w=>w.path==='/optimizer/jobs').body;
 assert.equal(writes.find(w=>w.path==='/slate/preparation/jobs').body.analyst_mode,'BASELINE');
 assert.equal(submitted.params.scenario_mode.passing_factor,1.25);
 assert.equal(submitted.params.scenario_mode.scoring_mode,'new_model_primary');
 assert.equal(writes.find(w=>w.path==='/slate/preparation/jobs').body.scenario_mode.passing_factor,1);
 assert.equal(submitted.params.prepared_input_job_id,'scenario-prep');assert.equal(submitted.params.num_lineups,1);
 assert.equal(submitted.params.analyst_handoff_mode,'BASELINE');
 assert.equal(submitted.contest_format,format);
 assert.equal(submitted.params.classic_selection_objective,format==='classic'?'baseline_mean':undefined);
 await page.reload();await page.getByRole('button',{name:'Operations',exact:true}).click();
 await page.getByRole('heading',{name:'Experimental scenario · matched baseline comparison'}).waitFor();
 const saved=page.getByRole('region',{name:'Saved scenario comparison'});
 await saved.getByText(/Prepared scenario/).click();await saved.getByText('No end-to-end accuracy claim').waitFor();
 await saved.screenshot({path:resolve(artifacts,'saved-desktop.png')});
 await page.setViewportSize({width:390,height:844});await saved.screenshot({path:resolve(artifacts,'saved-mobile.png')});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile page overflow');
 assert.deepEqual(errors,[]);writeFileSync(resolve(artifacts,'validation.json'),JSON.stringify({synthetic_api:true,public_controls:true,assumption_edits_require_prepare:true,submitted,read_only_reopen:true,errors},null,2));
 console.log('PASS: opt-in controls → Prepare → changed assumption invalidation → Optimize → saved reopen; desktop/mobile fixtures. '+artifacts);
} finally {await browser.close();await new Promise(r=>server.close(r));}
