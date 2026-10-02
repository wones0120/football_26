import assert from "node:assert/strict";
import test from "node:test";

import { classicContestUrls } from "../src/classicContestUrl.ts";

test("optional Classic contest context accepts one valid URL", () => {
  assert.deepEqual(classicContestUrls(""), []);
  assert.deepEqual(
    classicContestUrls(" https://www.draftkings.com/draft/contest/196088393 "),
    ["https://www.draftkings.com/draft/contest/196088393"],
  );
});

test("two pasted contest URLs fail before starting a run", () => {
  assert.throws(
    () => classicContestUrls("https://www.draftkings.com/draft/contest/196088393\nhttps://www.draftkings.com/draft/contest/195921990"),
    /accepts one DraftKings contest URL/,
  );
});
