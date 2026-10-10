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
    const calls=[];
    await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
    await context.route('**/api/**',route=>{
      const url=new URL(route.request().url());const path=url.pathname.replace(/^\/api/,'');
      const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
      if(path==='/imports/draftkings/entry-history') {
        if(route.request().method()==='GET') return reply(report);
        const request=route.request().postDataJSON();calls.push(request);
        return reply(request.dry_run?{status:'validated',rows:5}:{status:'deduplicated',rows:5,report});
      }
      if(path==='/meta/current') return reply(scope);
      if(path==='/optimizer/runs'||path==='/optimizer/projections') return reply({runs:[]});
      if(path==='/jobs'||path==='/weekly/runs') return reply({rows:[]});
      return reply({detail:'Unavailable in isolated fixture'},503);
    });
    await page.addInitScript(scope=>{localStorage.setItem('football-26-active-slate-context',JSON.stringify(scope));localStorage.setItem('football-26-run-selections',JSON.stringify({'2026:5:SUNDAY_MAIN':{optimizerRunId:'fixture'}}));},scope);
    await page.goto(base);await page.getByRole('button',{name:width===390?'Learn':'Learning',exact:true}).click();
    const card=page.getByRole('region',{name:'Entry history and winnings'});
    await card.getByText(/5 paid entries/).waitFor();
    await card.getByRole('textbox',{name:'Entry-history CSV path'}).fill('/tmp/history.csv');
    await card.getByRole('button',{name:'Validate history'}).click();
    await card.getByRole('status').filter({hasText:'validated:'}).waitFor();
    await card.getByRole('button',{name:'Import entry history'}).click();
    await card.getByRole('status').filter({hasText:'deduplicated:'}).waitFor();
    assert.deepEqual(calls,[{path:'/tmp/history.csv',year:2026,dry_run:true},{path:'/tmp/history.csv',year:2026,dry_run:false}]);
    assert.ok(await card.evaluate(e=>e.getBoundingClientRect().right<=innerWidth+1));
    const dir=resolve(root,'artifacts/entry_history');mkdirSync(dir,{recursive:true});
    await card.screenshot({path:resolve(dir,`entry-history-${width}.png`)});
    assert.deepEqual(errors,[]);await context.close();
  }
  console.log('PASS: entry-history summary, preview/import requests, dedup status, desktop/mobile.');
} finally {await browser.close();await new Promise(r=>server.close(r));}
