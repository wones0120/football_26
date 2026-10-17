// Isolated built-app check. Every API request is intercepted; no live writes.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createServer } from 'node:http';
import { resolve, join } from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = resolve(import.meta.dirname, '../dist');
const screenshots = mkdtempSync(join(tmpdir(), 'football-weekly-results-'));
const data = [
  ['THURSDAY_NIGHT', 'c1', [[3, 0]]], ['THURSDAY_NIGHT', 'c2', [[3, 0]]], ['THURSDAY_NIGHT', 'c3', [[1, 0]]],
  ['SUNDAY_MORNING', 'c4', [[1, 2]]], ['SUNDAY_EARLY', 'c5', [[1, 1.5]]], ['SUNDAY_MAIN', 'c6', [[3, 0]]],
  ['SUNDAY_LATE', 'c7', [[.5, 0]]], ['SUNDAY_LATE', 'c8', [[1, 1.5]]],
  ['SUNDAY_LATE_SF_SEA', 'c9', [[1, 1.5]]], ['SUNDAY_LATE_SF_SEA', 'c10', [[1, 0]]],
  ['SUNDAY_NIGHT', 'c11', [[3, 0]]], ['MONDAY_NIGHT', 'c12', [[3, 0]]], ['MONDAY_NIGHT', 'c13', [[1, 0], [1, 0], [1, 0], [1, 0]]],
];
function totals(entries) {
  const fees = entries.filter(e => e.entry_fee != null), cash = entries.filter(e => e.cash_winnings != null);
  const complete = entries.filter(e => e.entry_fee != null && e.cash_winnings != null);
  const known_fees = fees.reduce((n, e) => n + e.entry_fee, 0), known_winnings = cash.reduce((n, e) => n + e.cash_winnings, 0);
  const feeTotal = entries.length && fees.length === entries.length ? known_fees : null;
  const cashTotal = entries.length && cash.length === entries.length ? known_winnings : null;
  const net = feeTotal != null && cashTotal != null ? cashTotal - feeTotal : null;
  return { entries: entries.length, fees_known_entries: fees.length, winnings_known_entries: cash.length,
    financial_complete_entries: complete.length, known_fees, known_winnings,
    known_net_profit: complete.reduce((n, e) => n + e.cash_winnings - e.entry_fee, 0),
    fees: feeTotal, winnings: cashTotal, net_profit: net, roi: net != null && feeTotal ? net / feeTotal : null,
    known_cash_entries: cash.filter(e => e.cash_winnings > 0).length,
    cash_rate: entries.length && cash.length === entries.length ? cash.filter(e => e.cash_winnings > 0).length / entries.length : null,
    known_free_entries: fees.filter(e => e.entry_fee === 0).length, ticket_winnings: 0 };
}
function fixture(week) {
  const slates = [];
  if (week !== 3) for (const [slate, id, amounts] of data) {
    let s = slates.find(s => s.slate === slate);
    if (!s) { s = { slate, contests: [], report_id: `saved-${slate}`, report_created_at: '2026-10-13T12:00:00Z',
      missing_evidence: ['entry:c13:e1:contest_entry_assignment', 'entry:c13:e1:ambiguous_saved_lineup_matches'] }; slates.push(s); }
    const entries = amounts.map(([fee, cash], i) => ({ contest_id: id, entry_id: `e${i}`, slate, contest_name: `Contest ${id}`,
      entry_fee: fee, cash_winnings: week === 4 && id === 'c13' ? null : cash, ticket_winnings: 0,
      financial_source: 'entry_history', source_hashes: ['fixture-source-sha'], warnings: week === 4 && id === 'c13' ? ['Entry-history winnings unavailable.'] : [] }));
    s.contests.push({ contest_id: id, contest_name: `Contest ${id}`, entries, summary: totals(entries) });
  }
  for (const s of slates) s.summary = totals(s.contests.flatMap(c => c.entries));
  return { season: 2026, week, entry_user: 'wones0120', available_weeks: [5, 4, 3, 2], slates,
    summary: totals(slates.flatMap(s => s.contests.flatMap(c => c.entries))), warnings: [],
    limitations: ['Imported standings coverage only. Refunds and submission timing remain unknown.'] };
}
const server = createServer((req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  const file = resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
  if (!file.startsWith(root + '/')) return res.writeHead(403).end();
  try { res.setHeader('content-type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html'); res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1100 }, serviceWorkers: 'block' });
    const page = await context.newPage(); const errors = [], requests = []; let fail = true, delayed;
    page.on('pageerror', e => errors.push(e.message));
    await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    await context.route('**/api/**', async route => {
      const url = new URL(route.request().url()), path = url.pathname.replace(/^\/api/, '');
      requests.push({ path, method: route.request().method(), query: Object.fromEntries(url.searchParams), body: route.request().postDataJSON() });
      const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (path === '/learning/results/weekly') {
        const week = Number(url.searchParams.get('week'));
        assert.ok(['2026', '2025'].includes(url.searchParams.get('season'))); assert.equal(url.searchParams.get('entry_user'), 'wones0120');
        if (week === 2 && fail) return reply({ detail: 'Fixture read failure' }, 503);
        if (week === 4 && delayed) await delayed.promise;
        return reply({ ...fixture(week), season: Number(url.searchParams.get('season')) });
      }
      if (path === '/slate/imported-scopes') return reply({ scopes: [{ season: Number(url.searchParams.get('season')), week: Number(url.searchParams.get('week')), slate: 'SUNDAY_LATE_SF_SEA' }] });
      if (path === '/learning/shadow-comparisons') return reply({ experiments: [
        { experiment_id: 'monday-shadow', slate: 'monday_night', label: 'Monday shadow', report_json: null },
        { experiment_id: 'sunday-shadow', slate: 'SUNDAY_MAIN', label: 'Sunday shadow', report_json: null },
      ] });
      if (path === '/learning/reports/weekly') {
        const scope = route.request().postDataJSON();
        return reply({ ...scope, report_id: 'fixture-week-review', status: 'partial', interpretation: 'Intent remains unknown.',
          summary: { slates: 2, contests_entered: 0, entries: 0, matched_optimizer_entries: 0, entries_with_opt_007: 0,
            duplicate_entries: 0, entry_weighted_projection_mae: null, entry_weighted_projection_observations: 0 },
          missing_evidence: ['contest_entry_assignment missing', 'ambiguous_saved_lineup_matches'],
          slate_reports: ['MONDAY_NIGHT', 'SUNDAY_MAIN'].map(slate => ({ slate, report_id: `fixture-${slate}`,
            summary: { entries: 0, projection_mae: null, matched_optimizer_entries: 0, duplicate_entries: 0 },
            missing_evidence: ['intent unknown'], portfolio_analysis: {}, entries: [],
            learning_outcomes: { beliefs: { supported: 0, contradicted: 0, theses_scored: 0 } } })) });
      }
      if (path === '/meta/current') return reply({ season: 2026, week: 5, slate: 'SUNDAY_MAIN' });
      if (path === '/optimizer/runs' || path === '/optimizer/projections') return reply({ runs: [] });
      if (path === '/jobs' || path === '/weekly/runs') return reply({ rows: [] });
      return reply({ detail: 'Isolated fixture only' }, 503);
    });
    await page.addInitScript(() => {
      if (!localStorage.getItem('football-26-active-slate-context')) {
        localStorage.setItem('football-26-active-slate-context', JSON.stringify({ season: 2026, week: 5, slate: 'SUNDAY_MAIN' }));
        localStorage.setItem('football-26-run-selections', JSON.stringify({ '2026:5:SUNDAY_MAIN': { optimizerRunId: 'saved-live-run' } }));
      }
      localStorage.setItem('dfs-learning-entry-user', 'wones0120');
    });
    await page.goto(base); await page.getByRole('button', { name: width === 390 ? 'Learn' : 'Learning', exact: true }).click();
    const activeBefore = await page.evaluate(() => localStorage.getItem('football-26-active-slate-context'));
    const runsBefore = await page.evaluate(() => localStorage.getItem('football-26-run-selections'));
    const tab = page.getByRole('tab', { name: 'Weekly Results' }); await tab.click();
    const region = page.getByRole('region', { name: 'Weekly Results' });
    const table = region.getByRole('group', { name: 'Weekly financial totals' });
    await table.getByText('-$19.00', { exact: true }).waitFor();
    assert.match(await table.innerText(), /\$25.50.*\$6.50.*-\$19.00.*-74.51%.*25.00%/s);
    const monday = region.locator('details').filter({ has: page.locator('summary').filter({ hasText: /^MONDAY NIGHT ·/ }) });
    await monday.locator(':scope > summary').click();
    const entrySummary = monday.getByText('Contest c13 · entry evidence', { exact: true });
    await entrySummary.click();
    assert.equal(await entrySummary.locator('..').locator(':scope > ul > li').count(), 4);
    await monday.getByText('Saved learning warnings (2)', { exact: true }).click();
    await monday.getByText('entry:c13:e1:ambiguous_saved_lineup_matches', { exact: true }).waitFor();
    assert.ok(await region.evaluate(e => e.scrollWidth <= e.clientWidth + 1), 'Weekly panel overflows');
    assert.ok(await region.evaluate(e => e.getBoundingClientRect().right <= innerWidth + 1), 'Weekly panel exceeds viewport');
    await region.screenshot({ path: join(screenshots, `weekly-results-${width}.png`) });
    const reviewControls = page.locator('.operations-context');
    const slateSelect = reviewControls.getByRole('combobox', { name: 'Review slate' });
    await slateSelect.selectOption('MONDAY_NIGHT');
    assert.match(await table.innerText(), /Entries\s*5.*\$7.00.*\$0.00.*-\$7.00.*-100.00%/s);
    assert.equal(await region.getByRole('table', { name: 'Slate results', exact: true }).locator('tbody tr').count(), 1);
    assert.match(await page.locator('.shell-week-chip').innerText(), /MONDAY NIGHT/);
    await slateSelect.selectOption('SUNDAY_LATE_SF_SEA');
    assert.match(await table.innerText(), /-\$0.50.*-25.00%.*50.00%/s);
    await page.locator('.operations-command').screenshot({ path: join(screenshots, `learning-context-${width}.png`) });
    assert.ok(await reviewControls.evaluate(e => e.getBoundingClientRect().right <= innerWidth + 1), 'Review controls exceed viewport');
    await slateSelect.selectOption('WEDNESDAY_NIGHT');
    await region.getByText(/No imported standings entries/).waitFor();
    await slateSelect.selectOption('ALL');
    const select = region.getByRole('combobox', { name: 'Results week' });
    await select.selectOption('4');
    await region.getByText(/Incomplete financial evidence/).waitFor();
    assert.match(await table.innerText(), /Unknown/); assert.doesNotMatch(await table.innerText(), /-74.51%/);
    await select.selectOption('3'); await region.getByText(/No imported standings entries/).waitFor();
    await select.selectOption('2'); await region.getByRole('alert').filter({ hasText: 'Fixture read failure' }).waitFor();
    fail = false; await region.getByRole('button', { name: 'Refresh results' }).click(); await table.waitFor();
    let release; delayed = { promise: new Promise(r => { release = r; }) };
    const requested = page.waitForRequest(r => r.url().includes('/learning/results/weekly') && r.url().includes('week=4'));
    await select.selectOption('4'); await requested;
    await page.locator('.operations-context').getByRole('spinbutton', { name: 'Week', exact: true }).fill('5');
    await table.getByText('-$19.00', { exact: true }).waitFor();
    const slowResponse = page.waitForResponse(r => r.url().includes('/learning/results/weekly') && r.url().includes('week=4'));
    release(); await slowResponse;
    assert.equal(await select.inputValue(), '5'); assert.match(await table.innerText(), /-74.51%/);
    await tab.focus(); await page.keyboard.press('ArrowLeft');
    assert.equal(await page.getByRole('tab', { name: 'Review & Imports' }).getAttribute('aria-selected'), 'true');
    await page.getByRole('region', { name: 'Entry history and winnings' }).waitFor();
    await reviewControls.getByRole('spinbutton', { name: 'Season', exact: true }).fill('2025');
    await reviewControls.getByRole('spinbutton', { name: 'Week', exact: true }).fill('4');
    await slateSelect.selectOption('MONDAY_NIGHT');
    const shadows = page.getByRole('region', { name: 'GPP shadow comparisons' });
    await shadows.getByRole('heading', { name: 'Monday shadow · monday_night' }).waitFor();
    assert.equal(await shadows.getByRole('heading', { name: /Sunday shadow/ }).count(), 0);
    await tab.click(); await region.getByText(/Incomplete financial evidence/).waitFor();
    assert.match(await table.innerText(), /Entries\s*5.*Unknown/s);
    assert.equal(await page.evaluate(() => localStorage.getItem('football-26-active-slate-context')), activeBefore);
    assert.equal(await page.evaluate(() => localStorage.getItem('football-26-run-selections')), runsBefore);
    assert.ok(requests.filter(r => ['/optimizer/runs', '/optimizer/projections'].includes(r.path)).every(r =>
      r.query.season === '2026' && r.query.week === '5'), 'Learning changed optimizer request scope');
    assert.ok(requests.some(r => r.path === '/imports/draftkings/entry-history' && r.query.year === '2025'));
    assert.ok(requests.some(r => r.path === '/learning/shadow-comparisons' && r.query.season === '2025' && r.query.week === '4'));
    assert.ok(requests.every(r => r.method === 'GET'), 'Viewing weekly results made a mutation request');
    await page.getByRole('button', { name: width === 390 ? 'Ops' : 'Operations', exact: true }).click();
    assert.match(await page.locator('.shell-slate-chip').textContent(), /2026 W5/);
    assert.equal(await page.getByRole('combobox', { name: 'Active slate' }).inputValue(), 'SUNDAY_MAIN');
    await page.getByRole('combobox', { name: 'Active slate' }).selectOption('THURSDAY_NIGHT');
    await page.getByRole('button', { name: width === 390 ? 'Learn' : 'Learning', exact: true }).click();
    assert.equal(await slateSelect.inputValue(), 'MONDAY_NIGHT');
    assert.equal(await reviewControls.getByRole('spinbutton', { name: 'Week', exact: true }).inputValue(), '4');
    await page.reload();
    await page.getByRole('button', { name: width === 390 ? 'Learn' : 'Learning', exact: true }).click();
    assert.equal(await slateSelect.inputValue(), 'MONDAY_NIGHT');
    assert.equal(await reviewControls.getByRole('spinbutton', { name: 'Season', exact: true }).inputValue(), '2025');
    assert.equal(await reviewControls.getByRole('spinbutton', { name: 'Week', exact: true }).inputValue(), '4');
    // Requests below use isolated fixtures: exercise action scope without touching live data.
    await page.getByRole('button', { name: 'Scan contest folder', exact: true }).click();
    await page.getByText('Isolated fixture only', { exact: true }).last().waitFor();
    const scan = requests.findLast(r => r.path === '/imports/draftkings/weekly-contests');
    assert.deepEqual([scan.body.season, scan.body.week, scan.body.dry_run], [2025, 4, true]);
    await page.getByRole('button', { name: 'Build Week Learning Report', exact: true }).click();
    await page.getByText(/Week 4 learning report: partial/).waitFor();
    assert.equal(await page.locator('.learning-entry-results').count(), 1);
    assert.match(await page.locator('.learning-entry-results > summary').innerText(), /MONDAY NIGHT/);
    await page.getByText('Review missing evidence', { exact: true }).click();
    await page.getByText('contest_entry_assignment missing', { exact: true }).waitFor();
    await page.getByText('ambiguous_saved_lineup_matches', { exact: true }).waitFor();
    await slateSelect.selectOption('ALL');
    assert.equal(await page.locator('.learning-entry-results').count(), 2);
    await slateSelect.selectOption('WEDNESDAY_NIGHT');
    assert.equal(await page.locator('.learning-entry-results').count(), 0);
    await page.getByText(/No saved review for this slate; evidence remains unknown/).waitFor();
    await reviewControls.getByRole('spinbutton', { name: 'Week', exact: true }).fill('5');
    await page.getByText(/Week 4 learning report: partial/).waitFor({ state: 'hidden' });
    const build = requests.findLast(r => r.path === '/learning/reports/weekly');
    assert.deepEqual(build.body, { season: 2025, week: 4, entry_user: 'wones0120' });
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('football-26-active-slate-context')).slate), 'THURSDAY_NIGHT');

    assert.deepEqual(errors, []); await context.close();
    console.log(`PASS ${width}px: totals, entry/contest drilldowns, warnings, partial/empty/error weeks, stale-response guard, tabs, isolated review context, slate filtering, reload, scoped action payloads.`);
  }
  console.log(`Screenshots: ${screenshots}`);
} finally { await browser.close(); await new Promise(r => server.close(r)); }
