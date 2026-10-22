# Learning Tiers and Single Stat results — implemented and verified

The Learning folder workflow now supports Tiers and Single Stat touchdown, total-yard and passing-yard contest results. Real Tiers and TD files were loaded through the actual app, reopened, included in a new weekly report and reopened from the immutable weekly library. Yardage variants also passed the same app workflow with explicitly synthetic, isolated fixtures. No contest submissions or browser CSV downloads occurred.

## Real imported results

| Contest | Format / units | User entry | Observed rank / score | Immutable result ID |
|---|---|---|---|---|
|196709356|Tiers / normal DK fantasy points|5298422179|4744 / 86.32001|51ad89e511774534883dc2cfe095d700bd865fe97eb42a77daef165ab0674cb6|
|196806516|Single Stat Touchdowns / touchdowns|5298424284|2 / 3|d464fe2bd54c2c33d398012f72eb5d263502982e3e05134f34f1b738fd602cbc|

Both are explicitly scoped to2026Week6SundayMain. Native DraftKings contest metadata identifies196709356 as TiersGameType51/group154973, and196806516 as SingleStatTouchdownsGameType353/group154975, with SundayOctober18 13:00ET start. The original bare public response is preserved in original_lobby.json and hashed in native_contest_scope.json; its missing observation clock is explicit, not relabelled as fresh receipt. Operator review supplied that evidence reference through the actual UI controls. Selected exact saved native pool hashes are retained in each result. The native Tiers workspace's SUNDAY_MAIN_TIERS label is retained as native_pool_slate while the Learning review groups under SUNDAY_MAIN.

Your Tiers roster was Josh Allen /Derrick Henry /Puka Nacua /Kyren Williams /Kirk Cousins /Ashton Jeanty in T1–T6. Your TD roster was Kenneth WalkerIII /James CookIII /Brian RobinsonJr. Standings contain display names but no native player IDs, so **canonical identity and saved-forecast origin remain unverified/unmatched**. Neither a name match nor roster resemblance is promoted into canonical linkage or submission evidence.

Tiers imported successfully in batch **d1bfbf96-478f-4fcf-8b1f-a869d73f7223**, preserving5945observed entries including five blank field rosters explicitly counted as unavailable. The initial batch **4193b57e-51c5-419e-9510-83572ce43335** imported TD successfully but rejected Tiers on those blank rows. That failed source stayed in place; the focused correction retained unavailable participants without inventing rosters, then the normal UI retry succeeded. Partial nonempty malformed tier rosters still fail.

Both successful source files moved to `/Users/wones/NFL/Processed/` through the existing importer. Raw ledger bytes and Processed bytes were verified identical, including the original ZIP. Unrelated `contest-standings-171680612.zip` remains untouched. Financial Entry History stayed **99paid entries,17paid finishes,$167.50fees,$99.50cash winnings** before/after. Typed standings did not create or duplicate financial records.

## Saved weekly report

Actual UI Scan contest folder → select only relevant files → assign scope/format/metric/evidence/pool → Load → Reopen each result → Build Week Learning Report → Open saved report passed. The Learning username/folder/context were restored to wones0120,~/NFL,2026Week6,Allslates. The app remains on the real reopened report.

- Report ID: **weekly-learning-report-efd9d150-a619-5ab4-bed1-91a79932cfe5**.
- Original report SHA256: **79ed8cfd122b11306a35af961d6e174aa3fcb51ed61a2cfd02bf905aea3da56a**.
- Generated2026-10-19T01:43:15.569654UTC; original saved content reopens with `rebuild_performed=false`.
- Summary:15Classic/Showdown entries across3contests, plus **2typed contests /2typed entries in separate groups**. Typed units are never mixed into Classic projection MAE, ownership or financial ROI.
- Prior weekly reports remain immutable versions; TD-only and both-format evaluations were saved separately. `batch_receipts.json`, `verification.json` and reopened public responses retain exact lineage.

## Scoring and limitations

Tiers uses observed normal DK fantasy points with one player per native tier, no Captain multiplier. Single StatTD counts rushing/receiving/kick-return/missed-FG-return/punt-return/offensive-fumble-recovery/defensiveTDs; passingTD contributes nothing. Totalyards=rushing+receiving, excluding passing/PPR. Passingyards uses passingyards only.

Imported Points/Rank are observed source standings, **not reconstructed component stats or independently certified final settlement**. Source TimeRemaining is preserved; both real own entries show0. Missing rare TD categories remain unknown, never zero. Component actuals in the Single Stat workspace remain separately immutable and require their original complete-category/official-stat attestations. Observed contest totals do not require unavailable NFL components just to be retained.

Canonical/native/tier identity, duplicates and two-game/two-team rules are validated when native IDs resolve. Name-only and unavailable rosters stay explicit. Compatible exact saved-pool/canonical role rosters support unique or ambiguous forecast correspondence, retaining objective/coverage and unknown pre-lock chronology; correspondence never proves origin/assignment/submission. Name-only real imports therefore correctly remain unmatched. No financial return is inferred from rank.

## Yardage app acceptance — explicitly synthetic

No verified real yardage standings file was imported. Separate2020Week1`fixture-learning-user` files used SYNTHETIC Alpha/Beta/Gamma and FIXTURE entry IDs, with `fixture:` source references and `fixture_research` classification. They do not represent real contests, players or financial records.

- Totalyards observed220; record **5ca82f29fa473ee501779a66c0b119e6e9a0a0210a44c8576d06d390f642c018**.
- Passingyards observed317; record **3d4c9a2f5b46055a6d980bdd76bba0a7a22b6b6a3140e6f7ffb2e046c5d1a8d1**.
- App import batch **355667b6-477f-4452-b1bb-bfe3bb1082d4**; both reopens and saved weekly reopen passed.
- Fixture report **weekly-learning-report-95f24eec-4cc2-5964-8596-d0d0a74eab52**, savedSHA **f7333385bb8c5a4913e6ed547805654eebc7f91aa5824796d680da6cd9161ab8**.
- Financial entries0; fee/return/net/ROI all unknown, not invented zeros. Actual UI Load remained disabled until a scoring variant was selected.

## Implementation and validation

The bounded addition uses `special_contest_results.py` for immutable typed result records, exact raw source hashing, assignments, idempotency, corrections and forecast correspondence. Existing batch import dispatches typed formats before Classic ownership; Classic/Showdown detection stays separate. Two read-only result APIs and typed weekly groups extend the existing workflow. Native pools/projections/settings and the Single Stat component-actuals contract are unchanged. No schema migration or dependency was needed because this follows the existing immutable research-ledger pattern; batch metadata still uses the existing target tables.

UI changes are in `TypedContestResults.tsx`, `typedResultsApi.ts`, relevant App/API types and folder controls. Scope/variant/evidence inputs and saved result/weekly groups inherit the existing navy/white/teal styling. A review placeholder cannot be treated as a valid slate. Context changes clear stale opened typed results. README, release notes, Tiers/SingleStat docs and `docs/product/typed_contest_learning.md` document the behavior.

**71focused backend tests passed** across typed results, batch import, slate learning and immutable weekly library. Cases cover native identities, wrong tier/duplicate player, format ambiguity, unsupported metric, wrong units/scope/game pools, missingTDcomponents/noPPR/noPassingTD, blank participants, exact ZIP preservation, duplicate imports, failed-file recovery, correction chains/branch rejection, unique/ambiguous forecast correspondence, Classic/Showdown regression, public API reopen and financial separation. UI TypeScript/Vite build passed; only the existing bundle-size warning remains. `git diff --check` passed on affected tracked files. Visual inspection confirmed readable real/fixture groups.

Final API/worker activation occurred only after fresh empty running/queued checks and completion of current weekly requests. No active job was interrupted; no broad test/training sweep or direct lineup DB write occurred. Preexisting parent/agent changes were preserved. Monday's separately accepted named-Captain run3cefbcab and Sundayee5d9a9f are preserved; this Learning work did not change any lineup/settings.

![Real reopened weekly groups](completed_real_groups.png)
