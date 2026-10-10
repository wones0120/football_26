// Real built app with isolated saved candidate evidence; no live API writes.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync } from 'node:fs';
import { createServer } from 'node:http';
import { resolve } from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = resolve(import.meta.dirname, '../..');
const server = createServer((req,res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  const file = resolve(root, 'ui/dist', '.' + (path === '/' ? '/index.html' : path));
  if (!file.startsWith(resolve(root,'ui/dist')+'/')) return res.writeHead(403).end();
  try { res.setHeader('content-type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html'); res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
  for (const width of [1440,390]) {
    const context=await browser.newContext({viewport:{width,height:1000},serviceWorkers:'block'});
    const page=await context.newPage();const errors=[];const downloads=[];
    page.on('pageerror',e=>errors.push(e.message));
    const scope={season:2026,week:5,slate:'SUNDAY_MAIN'};
    const candidates=[1,2].map(n=>({candidate_id:`candidate-${n}`,lineup_number:n,rank:3-n,projected_points:100+n,marginal_upside_sum:170+n,salary:45000,availability_exceptions:n===2?[{player_id:'q',name:'Questionable receiver',designation:'Q'}]:[]}));
    const report={policy_id:'gpp_projection_first_recommendation_v1',status:'provisional',recommended:candidates[1],candidates:[candidates[1],candidates[0]],exceptions:[],reason:'Highest projected points among valid generated GPP candidates.',limitations:['Upside is the sum of player P90s, not a lineup percentile.']};
    const lineups=[1,2].map(n=>['QB','RB','RB','WR','WR','WR','TE','RB','DST'].map((position,i)=>({player_id:`p-${n}-${i}`,name:`Player ${n}-${i}`,position,roster_position:position,salary:5000,projection:10+n,p90:20,player_team:'AAA',opponent_team:'BBB'})));
    await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
    await context.route('**/api/**',route=>{
      const url=new URL(route.request().url());const path=url.pathname.replace(/^\/api/,'');
      assert.equal(route.request().method(),'GET');
      const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
      if(path.endsWith('/draftkings/download')) { downloads.push(url.searchParams.get('recommended_only')); return route.fulfill({status:200,contentType:'text/csv',headers:{'Content-Disposition':'attachment; filename="recommended.csv"'},body:'QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n1,2,3,4,5,6,7,8,9\n'}); }
      if(path==='/meta/current') return reply(scope);
      if(path==='/optimizer/runs') return reply({runs:[{...scope,optimizer_run_id:'fixture',contest_format:'classic',strategy:'classic_large_gpp_v1',objective:'gpp',status:'completed',saved_report_available:true,lineup_count:2,created_at:'2026-10-10T12:00:00Z'}]});
      if(path==='/optimizer/results/fixture') return reply({...scope,job_id:'fixture',status:'completed',strategy:'classic_large_gpp_v1',strategy_config:{},contest_format:'classic',objective:'gpp',lineage_persisted:true,results:lineups,gpp_recommendation:report});
      if(path==='/optimizer/projections') return reply({runs:[]});
      if(path==='/jobs'||path==='/weekly/runs') return reply({rows:[]});
      if(path==='/slate/preparation') return reply({scope,inputs:{},jobs:[],build_current:false,entry_ready:false,limitations:[]});
      return reply({detail:'Unavailable in isolated fixture'},503);
    });
    await page.addInitScript(scope=>{localStorage.setItem('football-26-active-slate-context',JSON.stringify(scope));localStorage.setItem('football-26-run-selections',JSON.stringify({'2026:5:SUNDAY_MAIN':{optimizerRunId:'fixture'}}));},scope);
    await page.goto(base);await page.getByRole('button',{name:width===390?'Ops':'Operations',exact:true}).click();
    const card=page.getByRole('region',{name:'GPP lineup recommendation'});
    await card.getByRole('heading',{name:'Recommended GPP lineup: #2'}).waitFor({timeout:8000}).catch(async e=>{ console.log('ERRORS',errors); console.log((await page.locator('body').innerText()).slice(-18000)); throw e; });
    await card.getByText(/Expected return: unavailable/).waitFor();
    await card.getByText(/Questionable receiver: Q/).waitFor();
    await card.getByRole('link',{name:'View recommended lineup'}).click();
    assert.equal(await page.locator('#optimizer-lineup-2').count(),1);
    const download=page.waitForEvent('download');await card.getByRole('button',{name:'Download recommended lineup for DraftKings'}).click();await download;
    assert.deepEqual(downloads,['true']);
    await card.getByText('Compare candidates and selection limits',{exact:true}).click();
    assert.equal(await card.locator('tbody tr').count(),2);
    assert.ok(await card.evaluate(e=>e.getBoundingClientRect().right<=innerWidth+1));
    const dir=resolve(root,'artifacts/gpp_recommendation');mkdirSync(dir,{recursive:true});
    await card.screenshot({path:resolve(dir,`recommendation-${width}.png`)});
    assert.deepEqual(errors,[]);await context.close();
  }
  console.log('PASS: recommended candidate, uncertainty labels, risk exception, alternatives, exact export request, desktop/mobile.');
} finally {await browser.close();await new Promise(r=>server.close(r));}
