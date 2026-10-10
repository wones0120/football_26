// Real UI with isolated API fixtures: no application data or external requests.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync } from 'node:fs';
import { createServer } from 'node:http';
import { resolve } from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = resolve(import.meta.dirname, '../..');
const server = createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  const file = resolve(root, 'ui/dist', '.' + (path === '/' ? '/index.html' : path));
  if (!file.startsWith(resolve(root, 'ui/dist') + '/')) return res.writeHead(403).end();
  try { res.setHeader('content-type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html'); res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const slates = [['SUNDAY_MAIN','classic'],['SUNDAY_EARLY','classic'],['SUNDAY_LATE','classic'],
  ['THURSDAY_NIGHT','showdown'],['SUNDAY_NIGHT','showdown'],['MONDAY_NIGHT','showdown'],['DK_SECOND_SUNDAY_GAME','showdown']];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  const errors = [], writes = [], jobs = new Map(), builds = new Map();
  page.on('pageerror', e => errors.push(e.message));
  await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname.replace(/^\/api/, '');
    const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const scope = { season: 2026, week: 5, slate: url.searchParams.get('slate') || 'SUNDAY_MAIN' };
    if (req.method() !== 'GET') writes.push({ path, body: req.postDataJSON() });
    if (path === '/optimizer/contests/saved/scopes') return reply({ scopes: [{ ...scope, slate: 'DK_SECOND_SUNDAY_GAME', contest_format:'showdown', contest_type:'gpp', contest_count:1 }] });
    if (path === '/slate/preparation') return reply({ scope, server_time: new Date().toISOString(), inputs:{}, jobs:[],
      prelock:true, build_current:builds.has(scope.slate), latest_build:builds.get(scope.slate) || null, entry_ready:false, limitations:[] });
    if (path === '/optimizer/projections') return reply({ runs: [] });
    if (path === '/optimizer/runs') return reply({ runs: [] });
    if (path === '/weekly/runs') return reply({ rows: [] });
    if (path === '/slate/preparation/jobs') {
      const body = req.postDataJSON(), id = `prepare-${body.slate}`;
      const build = { ...body, prepared_input_job_id:id, projection_run_id:`proj-${body.slate}`, feature_run_id:`features-${body.slate}`,
        source_sha256:'fixture', data_readiness:{status:'READY'}, availability_overrides:[], assume_questionable_out:false, limitations:[], consumption:{} };
      builds.set(body.slate, build); jobs.set(id, { job_id:id, status:'completed', result:build });
      return reply({ created:true, job:jobs.get(id) },202);
    }
    if (path === '/simulations/run') {
      const body = req.postDataJSON(), id = `sim-${body.slate}-${body.contest_format}`;
      const result = { ...body, simulation_run_id:id, message:`Completed fixture ${id}`, rows:[], successful_simulations:1000,
        projection_run_id:`proj-${body.slate}`, status:'completed', simulation_model_id:'fixture' };
      jobs.set(id,{ job_id:id, status:'completed', result });
      return reply({ created:true, job:jobs.get(id) },202);
    }
    if (path.startsWith('/jobs/')) return reply(jobs.get(path.slice(6)));
    if (path === '/optimizer/jobs') return reply({ detail:'Fixture validated optimizer dispatch' },409);
    return reply({ detail:'Unavailable in isolated fixture' },503);
  });
  await page.addInitScript(() => {
    if (!localStorage.getItem('football-26-active-slate-context')) localStorage.setItem('football-26-active-slate-context',JSON.stringify({season:2026,week:5,slate:'SUNDAY_MAIN'}));
  });
  await page.goto(base);
  await page.getByRole('button',{name:'Operations',exact:true}).click();
  for (const [slate,format] of slates) {
    await page.getByLabel('Active slate',{exact:true}).selectOption(slate);
    await page.getByLabel('Strategy',{exact:true}).selectOption(format);
    await page.getByRole('button',{name:'Prepare slate for optimization',exact:true}).click();
    await page.getByText('Prepared — ready to optimize',{exact:true}).waitFor();
    const prepared = writes.filter(w => w.path === '/slate/preparation/jobs').at(-1).body;
    assert.equal(prepared.slate,slate); assert.equal(prepared.contest_format,format);
    await page.getByRole('button',{name:'Run Optimizer',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Fixture validated optimizer dispatch'}).waitFor();
    const optimizer = writes.filter(w => w.path === '/optimizer/jobs').at(-1).body;
    assert.equal(optimizer.slate,slate); assert.equal(optimizer.contest_format,format); assert.equal(optimizer.objective,'gpp');
    assert.equal(optimizer.projection_run_id,`proj-${slate}`);
    assert.equal(optimizer.strategy,format === 'classic' ? 'classic_large_gpp_v1' : 'showdown_gpp_portfolio_v3');
    const tools = page.getByTestId('preparation-tools');
    if (!(await tools.evaluate(el => el.open))) await tools.locator(':scope > summary').click();
    const simulation = page.getByRole('button',{name:'Run Simulation',exact:true});
    assert.equal(await simulation.isEnabled(),true);
    await simulation.click();
    await page.getByText(`Completed fixture sim-${slate}-${format}`,{exact:false}).waitFor();
    const sim = writes.filter(w => w.path === '/simulations/run').at(-1).body;
    assert.equal(sim.slate,slate); assert.equal(sim.contest_format,format);
  }
  // The active imported slate and its projection survive reload.
  await page.reload();
  await page.getByRole('button',{name:'Operations',exact:true}).click();
  assert.equal(await page.getByLabel('Active slate',{exact:true}).inputValue(),'DK_SECOND_SUNDAY_GAME');
  await page.getByLabel('Strategy',{exact:true}).selectOption('showdown');
  await page.getByTestId('preparation-tools').locator(':scope > summary').click();
  const artifacts = resolve(root,'artifacts/shared_slate_paths'); mkdirSync(artifacts,{recursive:true});
  await page.getByRole('button',{name:'Run Simulation',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:resolve(artifacts,'desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Run Simulation',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:resolve(artifacts,'mobile.png')});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: seven slate dispatches, both GPP formats, preparation/projection lineage, simulation enabled, custom scope reload, desktop/mobile');
} finally { await browser.close(); await new Promise(r => server.close(r)); }
