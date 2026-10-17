import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseReportMarkdown } from '../src/analystReportLibrary.ts';

test('saved contrarian reports render exposure and Captain table bodies as rows', () => {
  for (const filename of ['THURSDAY_COMPARISON', 'SUNDAY_COMPARISON']) {
    const markdown = readFileSync(new URL(`../../research/analyst_contrarian_focus_20261014/${filename}.md`, import.meta.url), 'utf8');
    const tables = parseReportMarkdown(markdown).filter(block => block.kind === 'table');
    const exposures = tables.find(table => table.header.join('|') === 'Player|Mixed /5|Focus /5');
    assert.ok(exposures && exposures.rows.length > 0, `${filename} exposure body must render`);
    assert.equal(tables.filter(table => table.header[0] === 'Role/position').length, 10);
    if (filename === 'THURSDAY_COMPARISON') {
      const authority = tables.find(table => table.header[0] === 'Captain');
      assert.ok(authority && authority.rows.length >= 10, 'Captain authority body must render');
    }
  }
});
