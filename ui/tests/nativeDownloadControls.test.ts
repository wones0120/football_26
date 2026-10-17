import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

for (const name of ["SingleStat", "Tiers"]) {
  test(`${name} native download is available without an acknowledgment checkbox`, () => {
    const source = readFileSync(new URL(`../src/${name}.tsx`, import.meta.url), "utf8");
    assert.match(source, /Download lineup CSV/);
    assert.doesNotMatch(source, /acceptResearch|acceptDownload|accept_research=true/);
    assert.match(source, /(?:csvReady|exportReady)\?\.enabled\s*\?/);
    assert.doesNotMatch(source, /I accept the displayed research limitations|Accept research limitations for download/);
  });
}
