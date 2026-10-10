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
    const totals={entries:5,paid_finishes:2,paid_finish_rate:.4,entry_fees:15,cash_winnings:20,cash_net_return:5,ticket_winnings:0};
    const report={year:2026,snapshot_count:1,summary:totals,gpp_summary:totals,unknown_type_entries:0,free_entries:1,unmatched_contest_ids:['123'],conflicts:[],limitations:[]};
    const calls=[]; let refreshed=false;
    await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
    await context.route('**/api/**',route=>{
      const url=new URL(route.request().url());const path=url.pathname.replace(/^\/api/,'');
      const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
      if(path.startsWith('/learning/shadow-comparisons')) {
        if(route.request().method()==='POST') { refreshed=true; calls.push(path); }
        return reply({experiments:[{experiment_id:'frozen',label:'Sunday Main workload shadow',slate:'SUNDAY_MAIN',evaluated_at:null,
          report_json:{status:refreshed?'evaluated_from_imports':'pending_actuals',interpretation:'Counterfactual comparison; live selections stay unchanged.',
          arms:[{label:'control',forecast_points:100,projection_error:refreshed?40:null,actual_points:refreshed?140:null,missing_player_ids:refreshed?[]:['canonical'],known_paid_finishes:refreshed?1:0,known_non_paid_finishes:0,unknown_finishes:0,
          contests:refreshed?[{contest_id:'123',contest_name:'Sunday GPP',paid_finish:true,net_return_bounds:null,top_one_percent:false}]:[]}]
        }}]});
      }
      if(path==='/meta/current') return reply(scope);
      if(path==='/optimizer/runs'||path==='/optimizer/projections') return reply({runs:[]});
      if(path==='/jobs'||path==='/weekly/runs') return reply({rows:[]});
      return reply({detail:'Unavailable in isolated fixture'},503);
    });
    await page.addInitScript(scope=>{localStorage.setItem('football-26-active-slate-context',JSON.stringify(scope));localStorage.setItem('football-26-run-selections',JSON.stringify({'2026:5:SUNDAY_MAIN':{optimizerRunId:'fixture'}}));},scope);
    await page.goto(base);await page.getByRole('button',{name:width===390?'Learn':'Learning',exact:true}).click();
    const card=page.getByRole('region',{name:'GPP shadow comparisons'});
    await card.getByText('Status: pending actuals').waitFor();
    await card.getByText(/Actual points: Pending/).waitFor();
    await card.getByRole('button',{name:'Retry comparison'}).click();
    await card.getByText('Status: evaluated from imports').waitFor();
    await card.getByText(/Sunday GPP:\s+Paid finish/).waitFor();
    assert.ok((await card.innerText()).includes('Return unavailable'));
    assert.deepEqual(calls,['/learning/shadow-comparisons/refresh']);
    assert.ok(await card.evaluate(e=>e.getBoundingClientRect().right<=innerWidth+1));
    const dir=resolve(root,'artifacts/sunday_main_followthrough');mkdirSync(dir,{recursive:true});
    await card.screenshot({path:resolve(dir,`shadow-comparisons-${width}.png`)});
    assert.deepEqual(errors,[]);await context.close();
  }
  console.log('PASS: pending/result views, refresh, unavailable return, desktop/mobile.');
} finally {await browser.close();await new Promise(r=>server.close(r));}
