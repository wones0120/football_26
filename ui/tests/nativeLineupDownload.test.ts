import test from "node:test";
import assert from "node:assert/strict";
import { fetchNativeLineupCsv } from "../src/nativeLineupDownload.ts";

test("native CSV download checks errors, MIME, header and filename before creating a file", async () => {
  const original = globalThis.fetch;
  try {
    for (const status of [400, 409, 422]) {
      globalThis.fetch = async () => new Response(JSON.stringify({detail:"Native player mismatch"}), {status, headers:{"Content-Type":"application/json"}});
      await assert.rejects(fetchNativeLineupCsv("/download", "lineup.csv", ["FLEX","FLEX","FLEX"]), /Native player mismatch/);
    }
    globalThis.fetch = async () => new Response('{"detail":"not CSV"}', {headers:{"Content-Type":"application/json"}});
    await assert.rejects(fetchNativeLineupCsv("/download", "lineup.csv", ["FLEX","FLEX","FLEX"]), /did not return a CSV/);
    globalThis.fetch = async () => new Response("QB,WR\r\n1,2\r\n", {headers:{"Content-Type":"text/csv"}});
    await assert.rejects(fetchNativeLineupCsv("/download", "lineup.csv", ["FLEX","FLEX","FLEX"]), /does not match/);
    globalThis.fetch = async () => new Response("FLEX,FLEX,FLEX\r\n1,2,3\r\n", {headers:{"Content-Type":"text/csv", "Content-Disposition":'attachment; filename="single-stat-research.csv"'}});
    const result = await fetchNativeLineupCsv("/download", "lineup.csv", ["FLEX","FLEX","FLEX"]);
    assert.equal(result.filename,"single-stat-research.csv");
    assert.equal(await result.blob.text(),"FLEX,FLEX,FLEX\r\n1,2,3\r\n");
  } finally { globalThis.fetch = original; }
});
