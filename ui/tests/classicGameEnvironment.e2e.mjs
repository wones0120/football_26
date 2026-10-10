// Actual App/build; synthetic frozen review and historical notes; no live writes.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {resolve} from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=resolve(import.meta.dirname,'../..'), dist=resolve(root,'ui/dist'), out=resolve(root,'artifacts/classic_game_environment_review');
const fixture=JSON.parse(readFileSync(resolve(out,'ui_fixture.json'),'utf8'));
const notes=JSON.parse(readFileSync(resolve(root,'docs/product/classic_game_environment_research.json'),'utf8'));
const showdown=JSON.parse(readFileSync(resolve(root,'docs/product/showdown_research_notes.json'),'utf8'));
const server=createServer((req,res)=>{
 const path=new URL(req.url,'http://localhost').pathname;
 const file=resolve(dist,'.'+(path==='/'?'/index.html':path));
 if(!file.startsWith(dist+'/'))return res.writeHead(403).end();
 try{res.setHeader('content-type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(readFileSync(file));}catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,channel:'chrome'});
const calls=[],errors=[];
try {
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{
  const req=route.request(),u=new URL(req.url());
  if(u.pathname.startsWith('/api/')){
   calls.push({path:u.pathname,method:req.method()});
   if(req.method()!=='GET')return route.abort();
   const path=u.pathname.replace(/^\/api/,''),reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
   if(path==='/learning/research/classic-game-environment')return reply(notes);
   if(path==='/learning/research/showdown')return reply(showdown);
   if(path==='/optimizer/results/fixture')return reply(fixture);
   if(path==='/optimizer/runs')return reply({runs:u.searchParams.get('contest_format')==='classic'?[{
    optimizer_run_id:'fixture',season:2026,week:5,slate:'SUNDAY_MAIN',contest_format:'classic',objective:'cash',strategy:'classic_single_lineup_v1',
    status:'completed',created_at:fixture.created_at,completed_at:fixture.updated_at,lineup_count:1,saved_report_available:true,message:fixture.message}]:[]});
   if(path==='/optimizer/projections')return reply({runs:[]});
   if(path==='/meta/current')return reply({season:2026,week:5,slate:'SUNDAY_MAIN'});
   if(path==='/weekly/runs')return reply({rows:[]});
   if(path==='/slate/preparation')return reply({scope:{season:2026,week:5,slate:'SUNDAY_MAIN'},inputs:{},jobs:[],prelock:true,build_current:false,entry_ready:false,limitations:[]});
   return reply({detail:'Unavailable in isolated display fixture'},503);
  }
  if(req.method()==='GET'&&u.origin===base)return route.continue();
  return route.abort();
 });
 await page.addInitScript(()=>localStorage.setItem('football-26-active-slate-context',JSON.stringify({season:2026,week:5,slate:'SUNDAY_MAIN'})));
 await page.goto(base);
 await page.getByRole('button',{name:'Research Lab',exact:true}).click();
 const research=page.getByRole('region',{name:'Classic game environment research',exact:true});
 await research.getByText(notes.title,{exact:true}).waitFor();
 assert.match(await research.innerText(),/45\.9%/);
 await research.getByText('Historical observations by position',{exact:true}).click();
 await research.getByText('Controlled comparisons and evidence limits',{exact:true}).click();
 assert.match(await research.innerText(),/51\.7%.*41\.4%/);
 assert.match(await research.innerText(),/Actual cash outcomes: Unavailable/);
 assert.equal(await research.locator('button,input,select').count(),0);
 await research.screenshot({path:resolve(out,'research-desktop.png'),style:'.workspace-nav { visibility: hidden !important; }'});
 await page.setViewportSize({width:390,height:844});
 await research.screenshot({path:resolve(out,'research-mobile.png'),style:'.workspace-nav { visibility: hidden !important; }'});
 assert.ok(await research.evaluate(el=>el.getBoundingClientRect().width<=390));
 await page.setViewportSize({width:1440,height:1100});
 await page.getByRole('button',{name:'Operations',exact:true}).click();
 await page.getByRole('button',{name:'Open results',exact:true}).click();
 await page.getByRole('heading',{name:'Recommended Classic lineup',exact:true}).waitFor();
 const review=page.getByLabel('Classic Game Environment Review',{exact:true});
 await review.locator('summary').first().click();
 assert.match(await review.innerText(),/Eight offensive slots, including FLEX/);
 assert.match(await review.innerText(),/opponent implied points/);
 assert.equal(await page.getByRole('heading',{name:'Recommended Classic lineup',exact:true}).count(),1);
 assert.equal(await review.locator('button,input,select').count(),0);
 await review.screenshot({path:resolve(out,'review-desktop.png')});
 const downloadPromise=page.waitForEvent('download');
 await page.getByRole('button',{name:'Download readable lineup report',exact:true}).click();
 const download=await downloadPromise;const exported=resolve(out,'sample_lineup_report.html');await download.saveAs(exported);
 assert.match(readFileSync(exported,'utf8'),/Classic Game Environment Review/);
 await page.setViewportSize({width:390,height:844});await review.scrollIntoViewIfNeeded();
 assert.ok(await review.evaluate(el=>el.getBoundingClientRect().width<=390));
 assert.ok(await review.locator('div').nth(1).evaluate(el=>el.scrollWidth>el.clientWidth),'Player table scrolls horizontally on mobile');
 await review.screenshot({path:resolve(out,'review-mobile.png')});
 assert.ok(calls.every(c=>c.method==='GET'));
 assert.deepEqual(errors,[]);
 writeFileSync(resolve(out,'browser-verification.json'),JSON.stringify({passed:true,fixture:'Synthetic frozen review; actual App/build; no live solve',viewports:[1440,390],calls,errors},null,2)+'\n');
 console.log('PASS: research, one primary Classic recommendation, expandable frozen review, report export, desktop/mobile; GET requests only.');
} finally {await browser.close();await new Promise(r=>server.close(r));}
