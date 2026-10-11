// Isolated built-UI test: shared injury filename and import scope; no live writes.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = resolve(import.meta.dirname, '../..');
const server = createServer((req,res) => {
  const path = new URL(req.url,'http://localhost').pathname;
  const file = resolve(root,'ui/dist','.'+(path==='/'?'/index.html':path));
  if (!file.startsWith(resolve(root,'ui/dist')+'/')) return res.writeHead(403).end();
  try { res.setHeader('content-type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
  for (const slate of ['SUNDAY_EARLY','SUNDAY_LATE']) {
    const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});
    const page=await context.newPage(); const writes=[]; const errors=[];
    const scope={season:2026,week:5,slate};
    page.on('pageerror', e=>errors.push(e.message));
    await page.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
    await page.route('**/api/**',route=> {
      const request=route.request();const path=new URL(request.url()).pathname;
      const reply=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
      if (request.method()!=='GET') writes.push({path,body:request.postDataJSON()});
      if (path==='/api/slate/preparation') return reply({scope,inputs:{},jobs:[],latest_build:null,build_current:false,prelock:true,limitations:[]});
      if (path==='/api/ingest/injuries') return reply({rows_raw:1,rows_curated:1,rows_unresolved:0});
      if (path==='/api/optimizer/projections'||path==='/api/optimizer/runs') return reply({runs:[]});
      return route.fulfill({status:503,contentType:'application/json',body:'{"detail":"Isolated fixture"}'});
    });
    await page.addInitScript(scope=>localStorage.setItem('football-26-active-slate-context',JSON.stringify(scope)),scope);
    await page.goto(base);
    await page.getByRole('button',{name:'Operations',exact:true}).click();
    await page.getByText('Will load: ~/NFL/FanDuel_injuries_2026_5_SUNDAY_MAIN.csv',{exact:true}).waitFor();
    await page.getByText(`Will load: ~/NFL/DKSalaries_2026_5_${slate}.csv`,{exact:true}).waitFor();
    await page.getByRole('button',{name:'Load injury CSV',exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector('button:disabled')?.textContent?.includes('Load injury CSV'));
    assert.equal(writes.length,1);
    assert.equal(writes[0].path,'/api/ingest/injuries');
    assert.equal(writes[0].body.slate,'SUNDAY_MAIN');
    assert.equal(writes[0].body.path,'~/NFL/FanDuel_injuries_2026_5_SUNDAY_MAIN.csv');
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert.deepEqual(errors,[]);
    await context.close();
  }
  console.log('PASS: Early/Late use Main injury filename and import scope; salary paths stay separate; desktop/mobile.');
} finally { await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r)); }
