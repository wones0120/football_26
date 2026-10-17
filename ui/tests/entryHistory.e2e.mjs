// Isolated built-app workflow: all APIs intercepted; screenshots go to a new temp folder.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createServer } from 'node:http';
import { resolve, join } from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = resolve(import.meta.dirname, '../dist');
const screenshots = mkdtempSync(join(tmpdir(), 'football-entry-history-'));
const server = createServer((req,res) => {
  const file = resolve(root, '.' + (new URL(req.url,'http://localhost').pathname === '/' ? '/index.html' : new URL(req.url,'http://localhost').pathname));
  if (!file.startsWith(root+'/')) return res.writeHead(403).end();
  try { res.setHeader('content-type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(readFileSync(file)); }
  catch {res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,channel:'chrome'});
const totals={entries:1,paid_finishes:1,paid_finish_rate:1,entry_fees:3,cash_winnings:20,cash_net_return:17,ticket_winnings:0};
const report={year:2026,snapshot_count:1,summary:totals,gpp_summary:totals,unknown_type_entries:0,free_entries:0,unmatched_contest_ids:[],conflicts:[],limitations:[]};
try {
  for (const width of [1440,390]) {
    const context=await browser.newContext({viewport:{width,height:1100},serviceWorkers:'block'});
    const page=await context.newPage();let imports=0;
    await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
    await context.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname.replace(/^\/api/,'');
      const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
      if(path==='/imports/draftkings/entry-history')return reply(report);
      if(path==='/imports/draftkings/entry-history/folder'){
        const body=route.request().postDataJSON();
        if(body.dry_run)return reply({directory:'/tmp/history-fixture',year:2026,dry_run:true,files:[
          {path:'/tmp/history-fixture/history.csv',content_sha256:'a'.repeat(64),status:'validated',rows:1},
          {path:'/tmp/history-fixture/invalid.csv',content_sha256:'b'.repeat(64),status:'failed',rows:0,error:'Entry history row 2: Invalid rank'},
        ]});
        imports++;
        assert.deepEqual(body.files,[{path:'/tmp/history-fixture/history.csv',content_sha256:'a'.repeat(64)}]);
        return reply({directory:body.directory,year:2026,dry_run:false,report,files:[
          {path:body.files[0].path,content_sha256:'a'.repeat(64),status:'imported',rows:1,archive_status:'processed',archive_path:'/tmp/history-fixture/Processed/history.csv'},
        ]});
      }
      if(path==='/meta/current')return reply({season:2026,week:5,slate:'SUNDAY_MAIN'});
      if(path==='/optimizer/runs'||path==='/optimizer/projections')return reply({runs:[]});
      if(path==='/jobs'||path==='/weekly/runs')return reply({rows:[]});
      return reply({detail:'Isolated fixture only'},503);
    });
    await page.goto(base);
    await page.getByRole('button',{name:width===390?'Learn':'Learning',exact:true}).click();
    const panel=page.locator('.entry-history-panel');
    await panel.scrollIntoViewIfNeeded();
    const input=panel.getByRole('textbox',{name:'Entry-history CSV path',exact:true});
    await input.fill('/tmp/history-fixture/typing-readable.csv');
    await input.focus();
    const style=await input.evaluate(el=>{const s=getComputedStyle(el);return {color:s.color,caret:s.caretColor,fill:s.webkitTextFillColor};});
    assert.equal(style.color,'rgb(245, 248, 250)');assert.equal(style.caret,style.color);assert.equal(style.fill,style.color);
    await panel.getByRole('textbox',{name:'Entry-history folder',exact:true}).fill('/tmp/history-fixture');
    await panel.getByRole('button',{name:'Scan history folder',exact:true}).click();
    await panel.getByText('Entry history row 2: Invalid rank',{exact:true}).waitFor();
    assert.equal(imports,0);
    assert.equal(await panel.getByRole('checkbox').first().isChecked(),true);
    assert.equal(await panel.getByRole('checkbox').nth(1).isDisabled(),true);
    await panel.getByRole('button',{name:'Import selected history and move to Processed',exact:true}).click();
    await panel.getByText(/1 files moved to Processed/).waitFor();assert.equal(imports,1);
    await input.focus();await input.selectText();
    await page.screenshot({path:join(screenshots,`entry-history-${width}.png`),fullPage:true});
    const overflow=await panel.evaluate(el=>el.scrollWidth>el.clientWidth+1);assert.equal(overflow,false);
    await context.close();
  }
  console.log(JSON.stringify({status:'passed',screenshots}));
} finally {await browser.close();await new Promise(r=>server.close(r));}
