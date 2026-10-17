import assert from "node:assert/strict";
import test from "node:test";
import { nextPreparationStatus } from "../src/preparationStatus.ts";
import type { PreparationStatus } from "../src/api.ts";
const scope = {season:2026,week:6,slate:"THURSDAY_NIGHT"};
const receipt = (server_time:string, running:boolean, slate=scope.slate) => ({scope:{...scope,slate},server_time,jobs:running ? [{status:"running"}] : [],build_current:!running} as PreparationStatus);
test("slow preparation poll cannot overwrite the newer completed action refresh",()=>{
 const ready=receipt("2026-10-14T15:02:00Z",false), stale=receipt("2026-10-14T15:01:00Z",true);
 assert.equal(nextPreparationStatus(ready,stale,scope),ready);
 assert.equal(nextPreparationStatus(stale,ready,scope),ready);
});
test("old scope replies cannot affect the selected slate, while fresh same-scope jobs remain visible",()=>{
 const ready=receipt("2026-10-14T15:02:00Z",false);
 assert.equal(nextPreparationStatus(ready,receipt("2026-10-14T15:03:00Z",true,"SUNDAY_MAIN"),scope),ready);
 const fresh=receipt("2026-10-14T15:03:00Z",true);
 assert.equal(nextPreparationStatus(ready,fresh,scope),fresh);
 assert.equal(nextPreparationStatus(ready,null,{...scope,slate:"SUNDAY_MAIN"}),null);
});
