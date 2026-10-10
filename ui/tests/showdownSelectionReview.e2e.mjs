// Actual App bundle with isolated frozen/recommendation fixtures; no external writes.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = fileURLToPath(new URL('../../', import.meta.url)), dist = resolve(root, 'ui/dist');
const out = resolve(root, 'artifacts/showdown_ai_selection_review');
const fixture = JSON.parse(readFileSync(resolve(out, 'ui_review_fixture.json'), 'utf8'));
const pair = JSON.parse(readFileSync(resolve(out, 'week5_comparison.json'), 'utf8'));
const notes = JSON.parse(readFileSync(resolve(root, 'docs/product/showdown_research_notes.json'), 'utf8'));
const runId = fixture.review.run_identity.optimizer_run_id;
let response = structuredClone(fixture);
const calls = [], writes = [], errors = [];
const server = createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  const file = resolve(dist, '.' + (path === '/' ? '/index.html' : path));
  if (!file.startsWith(dist + '/')) return res.writeHead(403).end();
  try { res.writeHead(200, { 'Content-Type': file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html' }); res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: 'block' });
  const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
  await context.route('**/*', route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname.replace(/^\/api/, '');
    if (!url.pathname.startsWith('/api/')) return req.method() === 'GET' && url.origin === base ? route.continue() : route.abort();
    calls.push({ path, method: req.method() });
    const reply = (v, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(v) });
    if (path.endsWith('/selection-review/compare')) {
      assert.deepEqual(req.postDataJSON().candidate_ids, pair.proposed_pair.candidate_ids);
      assert.equal(req.postDataJSON().review_hash, response.review_hash); return reply(pair);
    }
    if (path.endsWith('/selection-review/decisions')) {
      const body = req.postDataJSON(); writes.push(body);
      const record = { ...pair, ...body, decision_id: `SIMULATED-UI-${writes.length}`, revision: writes.length,
        decision_timestamp: '2099-01-01T13:00:00+00:00', record_hash: 'SIMULATED-HASH', execution: null,
        attention: { explicitly_considered_ids: body.explicitly_considered_ids, other_displayed_candidate_ids: body.other_displayed_candidate_ids } };
      response.decision_history.push(record); return reply(record);
    }
    if (req.method() !== 'GET') return route.abort();
    if (path.endsWith('/selection-review')) return reply(response);
    if (path === '/learning/research/showdown') return reply(notes);
    if (path === '/learning/research/showdown-selection-review') return reply({ recorded_runs: 0, valid_prelock_slates: 0, runs: [], outcomes_by_overlap_bucket: {}, limitations: 'Research only, Week4 Sunday excluded.' });
    if (path === '/optimizer/runs') return reply({ runs: url.searchParams.get('contest_format') === 'showdown' ? [{ optimizer_run_id: runId, season: 2026, week: 5,
      slate: 'THURSDAY_NIGHT', contest_format: 'showdown', objective: 'gpp', strategy: 'showdown_gpp_portfolio_v3', status: 'completed',
      created_at: fixture.review.run_identity.created_at, lineup_count: 4, saved_report_available: true, message: 'Frozen display fixture' }] : [] });
    if (path === '/meta/current') return reply({ season: 2026, week: 5, slate: 'THURSDAY_NIGHT' });
    if (path === '/optimizer/projections') return reply({ runs: [] });
    if (path === '/weekly/runs') return reply({ rows: [] });
    if (path === '/model/defaults') return reply({ showdown_captain_model_path: 'docs/showdown_captain_model_2024_2025.json', showdown_captain_prior_strength: .35,
      classic_value_driver_model_path: 'docs/main_slate_value_driver_analysis_2024_2025.json', classic_value_driver_prior_strength: .45,
      matchup_outcome_model_path: 'docs/matchup_outcome_intelligence_2024_2025.json', matchup_outcome_prior_strength: .15, matchup_prior_gate_model_path: 'docs/matchup_prior_gate_20slates_5000.json' });
    return reply({ detail: 'Unavailable in isolated display fixture' }, 503);
  });
  await page.addInitScript(() => localStorage.setItem('football-26-active-slate-context', JSON.stringify({ season: 2026, week: 5, slate: 'THURSDAY_NIGHT' })));
  const openReview = async () => {
    await page.goto(base);
    await page.getByRole('button', { name: 'Operations', exact: true }).click();
    await page.locator('.operations-optimizer-panel').getByLabel('Format').selectOption('showdown');
    await page.getByRole('button', { name: 'AI Candidate Review', exact: true }).click();
    await page.getByRole('region', { name: 'AI Candidate Review', exact: true }).getByText(/75 quality-eligible candidates/).waitFor();
  };
  await openReview();
  const panel = page.getByRole('region', { name: 'AI Candidate Review', exact: true });
  assert.match(await panel.innerText(), /20 deterministic finalists.*10 ceiling outsiders/);
  assert.equal(await panel.getByRole('button', { name: 'Record SELECTED', exact: true }).isDisabled(), true);
  assert.equal(await panel.locator('input[type="checkbox"]:checked').count(), 0);
  assert.equal(await panel.getByLabel('Reviewer type', { exact: true }).inputValue(), 'HUMAN');
  const rank41 = panel.locator('tr[data-candidate-id]').filter({ hasText: 'Rank 41' }).first();
  assert.match(await rank41.innerText(), /Ryan Flournoy.*RESEARCH_CEILING_OUTSIDER|RESEARCH_CEILING_OUTSIDER[\s\S]*Ryan Flournoy/);
  await panel.getByText('Complete eligible universe (75)', { exact: true }).click();
  assert.equal(await panel.locator('tr[data-candidate-id]').count(), 105);
  await panel.getByText('Complete eligible universe (75)', { exact: true }).click();
  const cids = pair.proposed_pair.candidate_ids;
  for (let i = 0; i < 2; i++) await panel.getByLabel(`Exact candidate ID for entry ${i + 1}`, { exact: true }).fill(cids[i]);
  await panel.getByRole('button', { name: 'Compare proposed pair', exact: true }).click();
  await panel.getByText('5/6 physical players shared — concentrated player core', { exact: true }).waitFor();
  assert.match(await panel.innerText(), /Unique physical players: 7/);
  assert.match(await panel.innerText(), /Alternative 1: 4\/6 shared/);
  assert.equal(writes.length, 0);
  await panel.getByText('Attention shortlist: finalists and ceiling outsiders', { exact: true }).click();
  await panel.screenshot({ path: resolve(out, 'review-desktop.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await panel.evaluate(el => el.getBoundingClientRect().width <= 390));
  assert.ok(await panel.locator('.selection-input-grid').first().evaluate(el => el.getBoundingClientRect().width <= 390));
  await panel.screenshot({ path: resolve(out, 'review-mobile.png') });
  // Simulated future response only; no database or service receives these writes.
  response = structuredClone(fixture); response.can_record_prelock = true;
  await page.setViewportSize({ width: 1440, height: 1100 }); await page.reload(); await openReview();
  await panel.getByText('Import ChatGPT recommendation', { exact: true }).click();
  const recommendation = { proposed_candidate_ids: cids, explicitly_considered_ids: [...cids, fixture.review.attention_shortlist.ceiling_outsider_candidate_ids[8]],
    reasoning: 'Synthetic UI test only', football_theses: ['Script one', 'Script two'], complementarity_reason: 'Complementary paths',
    accepted_high_overlap_exception: 'Deliberately accept core after alternatives', alternative_candidate_ids_considered: [], rejected_candidates: [] };
  await panel.getByLabel('Recommendation JSON', { exact: true }).fill(JSON.stringify(recommendation));
  await panel.getByRole('button', { name: 'Load recommendation into review', exact: true }).click();
  assert.equal(writes.length, 0);
  await panel.getByRole('button', { name: 'Compare proposed pair', exact: true }).click();
  await panel.getByText('5/6 physical players shared — concentrated player core', { exact: true }).waitFor();
  await panel.getByRole('button', { name: 'Record SELECTED', exact: true }).click();
  await panel.getByText('Saved immutable revision 1: SELECTED.', { exact: true }).waitFor();
  assert.deepEqual(writes[0].explicitly_considered_ids, recommendation.explicitly_considered_ids);
  assert.deepEqual(writes[0].other_displayed_candidate_ids, []);
  assert.equal(writes[0].decision_timestamp, undefined);
  assert.equal(writes[0].reviewer_type, 'AI_ASSISTED');
  assert.equal(await panel.getByRole('button', { name: 'Record USER_APPROVED', exact: true }).isDisabled(), true);
  await panel.getByRole('checkbox', { name: 'I approve exactly this proposed pair', exact: true }).check();
  await panel.getByRole('button', { name: 'Record USER_APPROVED', exact: true }).click();
  await panel.getByText('Saved immutable revision 2: USER_APPROVED.', { exact: true }).waitFor();
  assert.equal(writes[1].previous_decision_id, 'SIMULATED-UI-1'); assert.deepEqual(errors, []);
  writeFileSync(resolve(out, 'browser-verification.json'), JSON.stringify({ passed: true, errors, calls,
    fixture: 'Frozen Week5 replay and synthetic future UI responses. All writes mocked.', screenshots: ['review-desktop.png', 'review-mobile.png'] }, null, 2) + '\n');
  console.log('PASS: Actual App desktop/mobile replay, universe/alternatives and explicit selection/approval revisions.');
} finally { await browser.close(); await new Promise(r => server.close(r)); }
