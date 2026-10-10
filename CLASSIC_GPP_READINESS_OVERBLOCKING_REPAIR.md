# Classic GPP readiness overblocking repair

Completed October 9, 2026 for Week 5 `SUNDAY_MAIN`, `classic_large_gpp_v1`, under `classic_large_gpp_data_readiness_v1`.

**Final run: `5e51be99-6567-4e85-b1ea-992a475f5eac` — NOT_READY. The solver did not execute.** Five of the original six availability cases now have sourced dispositions. The existing salary CSV is authenticated without reimport. Remaining material uncertainty, salary identity failures, and missing native draft-group evidence still block production.

The prior optimizer run `3e332175-5321-4e4b-a7e6-b89d941ef621` is unchanged. Its saved request, including five entries and opponents facing DEN exclusions, was copied into the new normal service run. [Preservation check](artifacts/classic_gpp_overblocking_repair/preservation_check.json), [new HTML report](artifacts/classic_gpp_overblocking_repair/WEEK5_SUNDAY_MAIN_REPAIR_NOT_READY.html), and [complete readiness JSON](artifacts/classic_gpp_overblocking_repair/rerun_readiness.json) retain the result.

## 1. Root cause

- The projection input builder rejected every unknown availability case before assessing existing role exclusions. It could not distinguish an unresolved offensive player from an objectively excluded specialist or backup QB.
- Coverage used a broader pool than the reported generation population: 273 eligible players but projection and ownership denominators of 332. Unresolved cases were mixed into completeness counts.
- Missing canonical source IDs and outdated team associations prevented current football facts from reaching five otherwise resolvable players. Jackson Meeks also has distinct DraftKings and nflreadpy canonical entities.
- Official roster parsing initially rejected duplicate portrait/name links to the same native profile. The repaired parser requires one distinct profile key and an explicit roster section.
- Legacy salary validation demanded a source snapshot even when the original file, completed import, raw rows, and normalized rows could be authenticated. Replaying that import would not establish new source currency or recover a missing draft group.
- A failed fresh projection could reach the ordinary saved-input selector with a null ID and load an older active projection. Both projection and ownership selection now require explicit new run IDs on normal live runs.
- Malick Meiga was incorrectly labeled unresolved because a derived `target.dim_player` row was missing, despite a valid source-of-truth canonical UUID. Live identity checks now validate `public.player_master` by exact canonical key.

Blank official game designations are also distinct from missing roster/role evidence. A blank designation does not establish ACTIVE; a complete injury-list row is not a final inactive declaration.

## 2. The six original blocking players

Every row below belongs to the authenticated DraftKings ingest `5dd55a4b-b108-433b-bfaf-125c636a1705`. Kickoffs are October 11, 2026, Eastern time. **No saved Week 5 mean/P90 projection exists for these six canonical IDs in `target.player_projection`; the repaired run produced none.** Historical average points are not substituted for a projection. See [projection and identity audit](artifacts/classic_gpp_overblocking_repair/projection_and_identity_audit.json).

| Player | Native DK ID | Canonical UUID | Native team / position / salary | Native game |
| --- | --- | --- | --- | --- |
| Mitch Tinsley | 44392310 | `1d40cef2-c090-462c-adc1-d3916a79a19d` | CIN WR / $3,300 | CIN@MIA, 1:00 PM |
| Ihmir Smith-Marsette | 44448270 | `211132fe-37de-474c-8641-56fa3ad7f76b` | ARI WR / $3,000 | DET@ARI, 4:25 PM |
| Drew Ogletree | 44392770 | `49eb0340-1887-4ee1-a83a-0d1737603348` | IND TE / $2,500 | IND@PIT, 1:00 PM |
| Scotty Miller | 44448280 | `4d46c1b1-f4df-4c35-85cd-8e981af90d61` | CHI WR / $3,000 | CHI@GB, 1:00 PM |
| Lew Nichols | 44392096 | `a24a6760-e0c5-4f56-8285-abb42b848a9b` | PIT RB / $4,000 | IND@PIT, 1:00 PM |
| Jackson Meeks | 44392702 | `ab45216a-e31a-48f3-b389-cf3756e985f9` | DET TE / $2,500 | DET@ARI, 4:25 PM |

| Player | Resolution and current football evidence | GPP relevance and final disposition |
| --- | --- | --- |
| Tinsley | Current CIN official roster ACT and WR backup depth. Initial canonical identity lacked a usable nflreadpy native alias. A unique team/position/normalized-name match to the official profile was persisted as an `nfl_official` native alias. | An active backup WR can receive material opportunity; depth rank does not prove irrelevance. `generation_eligible`, pending global source readiness. |
| Smith-Marsette | Canonical master retained MIN; native GSIS `00-0036635` has a CAR alias. Saved roster history shows CAR DEV in Week 4 and ARI CUT in Week 2, not matching current Week 5 Arizona facts. The current captured Arizona roster/depth tables provide no matching affirmative row. | Materiality cannot be bounded reliably. Status and role remain UNKNOWN. `unresolved`; NOT_READY remains. Absence from a page is not proof of unavailability. |
| Ogletree | Current IND official roster ACT and backup TE depth, behind Warren and Mo Alie-Cox. Initial canonical entity lacked a usable native roster alias; the official profile supplies persistent identity and role lineage. | An active backup TE can be relevant at this salary. `generation_eligible`; no low-salary exclusion. |
| Miller | Master retained PIT while the salary row is CHI. The current Bears official roster explicitly lists him in Practice Squad. | `unavailable` under the existing sourced practice-squad policy, not an invented injury designation or unresolved quarantine. Reassess after new elevation/roster evidence. |
| Nichols | Master had blank team and FLEX position; the native salary is PIT RB. Current Steelers official roster explicitly lists him in Practice Squad. | `unavailable` under the existing sourced practice-squad policy. No unfamiliar-name rule was introduced. |
| Meeks | Current DET official roster ACT and backup TE depth. GSIS `00-0040390` points to separate nflreadpy UUID `f46e7def-5ee6-4d42-8bba-73bc9c4ea6fd`. The official profile supplies affirmative facts for the existing DraftKings UUID through unique team/position/name evidence. The canonical entities were not silently merged. | An active backup TE remains potentially material. `generation_eligible`. The duplicate identity remains visible in the audit. |

Roster observations for the five resolved cases are October 9, **11:59:46–11:59:48 UTC**, before the final run's information cutoff. Source snapshot IDs, native profile URLs, source positions, independent clocks, and composed facts are retained in [final canonical evidence](artifacts/classic_gpp_overblocking_repair/evidence_after.json). The source pages are the official [Bengals roster](https://www.bengals.com/team/players-roster/) and [depth chart](https://www.bengals.com/team/depth-chart), [Colts roster](https://www.colts.com/team/players-roster/) and [depth chart](https://www.colts.com/team/depth-chart), [Bears roster](https://www.chicagobears.com/team/players-roster/), [Steelers roster](https://www.steelers.com/team/players-roster/), and [Lions roster](https://www.detroitlions.com/team/players-roster/) and [depth chart](https://www.detroitlions.com/team/depth-chart). The missing Arizona facts were checked against captured official [roster](https://www.azcardinals.com/team/players-roster/) and [depth](https://www.azcardinals.com/team/depth-chart) tables.

ACT in these facts establishes baseline roster membership. Final game-day active/inactive clearance is still UNEVALUATED.

## 3. The five salary identity failures

The standard idempotent salary identity repair was run. All five still require explicit resolution; no arbitrary identity was selected.

| Native player / DK ID | Salary team / role / game | Finding |
| --- | --- | --- |
| Nick Singleton / 44392078 | TEN RB $4,000 / HOU@TEN | `no_match`; no canonical candidate or native roster key found in the saved evidence. |
| Al-Jay Henderson / 44392108 | NYJ RB $4,000 / CLE@NYJ | `no_match`; Week 5 NYJ RB DEV roster rows exist, but GSIS is null and there is no canonical candidate. The display name alone cannot create a join. |
| Audric Estime / 44392128 | MIN RB $4,000 / MIN@NO | `ambiguous`: `74b76939-bd32-477c-b61c-897c52ccdc42` has older NO DFS aliases; `b03d4c85-4da9-4191-8370-37de35a00c85` has MIN nflreadpy `00-0039373` and PFR aliases. These are separate canonical entities requiring an audited cross-source identity correction. |
| AJ Henning / 44392576 | MIA WR $3,000 / CIN@MIA | `ambiguous`: `54543399-c0e0-4790-b31f-c33fe44d06d7` has nflreadpy `00-0040302` for MIA; `dff6f854-d55b-45a4-9c6f-76a9d7af3124` is a second normalized-name canonical entity. No silent merge or tie-break by UUID order. |
| Cal Adomitis / 44392804 | NO TE $2,500 / MIN@NO | `no_match` with a candidate: `823bb58d-3530-4a40-9153-919e41fdc3a8`, GSIS `00-0037412`, current NO football LS. Historical DK aliases list him as TE. The current TE-versus-LS source conflict needs an explicit identity/role rule rather than adaptation into a scoring TE. |

These are **identity-review quarantines**, distinct from the new `quarantined_unresolved_evidence` football disposition. The saved ingest originally reports seven unresolved rows; Bam Knight and James Proche had already been mapped while their old queue records remained open. The current curated identities and `target.identity_quarantine` show five actual failures. [Initial evidence](artifacts/classic_gpp_overblocking_repair/evidence_before.json) and the [candidate audit](artifacts/classic_gpp_overblocking_repair/projection_and_identity_audit.json) preserve that distinction.

Malick Meiga is no longer an additional salary identity blocker: his exact canonical key is valid, and sourced DEV status excludes him as unavailable.

## 4. Salary provenance recovery

- Original CSV: `/Users/wones/NFL/DKSalaries_2026_5_SUNDAY_MAIN.csv`.
- SHA-256: `21aaaeff559a2dc434e38fce457b8f80aed4e245b75732b9e8b07c1073b99655`.
- Completed ingest: `5dd55a4b-b108-433b-bfaf-125c636a1705`.
- Original import started October 9 **01:36:54.998434 UTC** and completed **01:36:56.167376 UTC**. These persisted receipt clocks are retained, not renewed.
- File, raw, and curated row counts are all **587**. Raw payload multisets match the CSV exactly after representation normalization. Native IDs are unique. Curated native IDs, names, positions, salary, game, team, and status match the native rows; canonical game/kickoff checks pass.
- The import has no salary source snapshot and no matching content-hash snapshot. The verified file/raw/import proof now supplies original receipt provenance without reimport. Provider publication and observation times remain unknown, explicitly labeled `original_import_receipt_clock`.
- **Native draft-group ID could not be recovered** from the CSV, file identity, import, or saved snapshots. `salary_native_draft_group_missing` remains a source-level blocker under the retained contract. No group ID is inferred from the slate or filename.

The original CSV is authenticated and does **not** need replacement. Its missing native draft-group metadata is a specific unresolved contract requirement, not a claim that the CSV content is wrong. No raw salary payload was rewritten and no new import clock was created. The persisted proof is included in the final readiness JSON.

## 5. Certified pool and quarantine semantics

Each native row is audited independently of user preferences. Confirmed unavailable and existing role-ineligible players remain visible. Only players with usable availability, role, identity, and game evidence enter the certified generation population; required projection/ownership checks still determine whether that population can be solved.

`quarantined_unresolved_evidence` means football availability remains UNKNOWN. Fresh prelock evidence must prove an **existing** role exclusion: an unsupported non-scoring specialist, or backup QB without a sourced expected package. The report retains unresolved facts, role policy, source IDs, clocks, and reassessment instructions. The next refresh recomputes the disposition from facts rather than reusing an exclusion.

Unknown offensive opportunity, missing/stale/conflicting role facts, a credible QB package, or contradictory starter evidence still block. Backup RB/WR/TE rank, low salary, unfamiliar name, and user exclusions cannot authorize quarantine. Material questionable players retain the existing risk bucket and require current practice/workload evidence.

The projection builder applies the same role proof before feature lookup. Quarantines receive no new projections or ownership and cannot enter the frozen solver pool. Live missing prediction values remain null. Ownership requires a completed same-scope explicit projection and is limited to IDs actually scored by that run; its lineage records that projection ID. The full audited pool is retained separately from the certified frozen pool.

**The live run has zero unresolved football quarantines.** The data did not justify quarantining Smith-Marsette or River Cracraft. The regression fixture proves that six objectively nonmaterial unknown backup QBs can be quarantined without blocking a complete usable pool; it does not relabel these six real offensive players as irrelevant.

## 6. Before/after coverage counts

The before column is the prior immutable run; after is the new run. Canonically resolved salary rows overlap the disposition populations. The five disposition categories partition all 587 rows.

| Population / check | Before | After |
| --- | ---: | ---: |
| Full native DK salary rows | 587 | 587 |
| Canonically resolved salary rows | 582 | 582 |
| Native rows assessed | 587 | 587 |
| Confirmed unavailable, including native salary-ineligible | 210 | 213 |
| Role-ineligible, including specialists | 43 | 44 |
| Unresolved blocking, including invalid identity | 61 | 53 |
| Unresolved football quarantine | 0; unsupported | 0; explicit policy |
| Certified generation-eligible | 273 | 277 |
| Projection coverage | 320/332 | **0/277** |
| Ownership coverage | 326/332 | **0/277** |
| Market environments | 11/11 | **11/11** |

After: 48 material-player cases plus five salary identity failures form the 53 blocking unresolved rows. Projection and ownership denominators are both exactly the 277 certified IDs. Zero completeness is intentional: the newly attempted projection failed, and older projections/ownership cannot count. Reducing the denominator did not make readiness pass. No evidence was frozen.

## 7. Remaining material-player blockers

**Smith-Marsette:** current Arizona availability and role remain unresolved; materiality is unknown.

**River Cracraft:** native salary and FanDuel facts retain Q, but no current matching WAS role evidence was found. His practice/workload evidence is also missing. Page absence did not establish unavailability. These two role/availability cases stop the projection dependency builder.

**47 questionable players** lack the current practice and/or expected-workload evidence required by the unchanged risk policy. They remain visible and are not promoted to ACTIVE, automatically excluded, or safely quarantined:

Caleb Douglas, Ashton Jeanty, Jaylen Wright, Noah Fant, Jeremiyah Love, Tee Higgins, Jacory Croskey-Merritt, Carsen Ryan, Justin Jefferson, George Holani, Charlie Kolar, Gunnar Helm, Alec Ingold, Ashton Dulin, Terry McLaurin, Cam Skattebo, Rico Dowdle, River Cracraft, Ladd McConkey, Justin Joly, Reggie Gilliam, D'Andre Swift, Stefon Diggs, Mike Evans, Jalen Nailor, Barion Brown, Chris Manhertz, Chris Olave, Tylan Wallace, Quentin Johnston, David Martin-Robinson, Cody White, Kyle Monangai, Carnell Tate, Alvin Kamara, Mack Hollins, Chris Bell, Chig Okonkwo, Rhamondre Stevenson, Rachaad White, Isaiah Likely, Malik Nabers, Jordan Addison, Chris Brooks, Ja'Marr Chase, Brenen Thompson, Keenan Allen.

The final official NFL refresh retained 249 rows, all with blank game designations, and missing ARI injury-list coverage. That does not invalidate independent sourced roster membership, nor does it supply final active status or the missing Q workload evidence. Baseline generation readiness remains separate from final inactive and entry clearance. Individual reason codes and risk fields appear in `blocker_groups.material_players` in the saved report.

Source-level problems are reported separately: missing native draft group; the five unresolved salary identities; and projection/ownership dependency failures resulting from incomplete material evidence. Missing projection/ownership timestamps are consequences of the blocked new builds, not separate demands to fetch older predictions.

## 8. Changes and files modified

Production changes:

- `backend/app/product_services/classic_player_pool.py`: shared conservative materiality and quarantine proof.
- `classic_official_context.py`: official roster/depth supplement, native profile resolution, immutable HTTP capture, and persisted identity rules. Failed parsing retains the captured body; unresolved relevant mappings enter the existing review queue.
- `classic_salary_provenance.py`: original CSV/hash/raw/curated/clock authentication without reimport.
- `classic_data_readiness.py`: provenance, populations, certified denominators, all-game checks, explicit dependency validation, separate blocker groups, and certified-only freeze.
- `canonical_projection_inputs.py`: apply the role proof before projection preparation; preserve original unresolved salary keys and source assessments.
- `ownership.py`: scope ownership to the completed explicit new projection and its scored IDs; distinguish prediction creation from its information cutoff.
- `optimizer.py`: prevent saved-run fallback after live refresh failure, use canonical identity authority, and preserve null live predictions.
- `showdown_player_context.py`: retain sourced expected QB-package facts. `showdown_data_readiness.py`: optional shared refresh supplement hook. Existing Showdown contract checks remain in place.
- `ui/src/classicReadinessReport.ts` and `classicLiveReadiness.ts`: explicit populations/blocker evidence and original-file recovery wording.

Tests: new `backend/app/tests/product/test_classic_overblocking_repair.py`, focused updates to `test_classic_data_readiness.py` and `test_ownership_model.py`, and UI readiness/report regression tests. Audit/rerun helpers are `scripts/audit_classic_overblocking.py` and `scripts/run_classic_overblocking_repair.py`. README, release notes, and `docs/product/classic_live_data_readiness.md` describe the behavior.

No new dependency, schema migration, or configuration change was introduced. No strategy, stack, exposure, team/game cap, player-selection threshold, projection formula, or P90 formula was changed by this task. The five-entry solver regression retains effective objective weights **projection .35 / ceiling .45 / leverage .05 / correlation .15**. These effective solver weights are distinct from the existing symbolic rule-profile weights, which also remain unchanged. Native request controls and DEN exclusions match the prior run exactly.

Task-start copies and the focused [baseline diff](artifacts/classic_gpp_overblocking_repair/task_diff.patch) preserve the already dirty checkout. The [source hashes](artifacts/classic_gpp_overblocking_repair/final_source_hashes.json) identify the reviewed implementation.

## 9. Tests and results

- **342 backend tests passed** across Classic readiness, repair regressions, canonical projection inputs, specialist roles, ownership, optimizer mode, Showdown readiness, official injuries, strategy contracts, player roles, and slate preparation. [Final log](artifacts/classic_gpp_overblocking_repair/final_regressions.txt).
- Repair tests prove six objective nonmaterial unknowns can coexist with a READY usable pool; material/unknown-materiality/stale/conflicting/package cases still block; fresh facts trigger reassessment; quarantines cannot enter a real five-entry ILP portfolio; and unverified starting QBs are absent from the certified denominator.
- Original-file proof tests cover accepted legacy lineage without snapshot/reimport and rejected checksum, raw-row, curated-row, count, and clock evidence. Named Jeanty/Higgins/Jefferson fixtures remain Q and require usable practice/workload context.
- Failed-live-refresh tests prove no saved projection selector or production solver call; loader regression retains null predictions and exact canonical identity authority. The real PostgreSQL run also exercised null run IDs successfully after typed null checks were added.
- **6 UI tests passed**, including queued API/durable worker/report behavior and visible certified/unresolved/quarantine populations. [Final UI log](artifacts/classic_gpp_overblocking_repair/final_ui_tests.txt).
- Production UI build and TypeScript checking passed. The existing Vite large-bundle advisory remains informational. [Build log](artifacts/classic_gpp_overblocking_repair/ui_build.txt).
- Final read-only audit checks the population partition, matching projection/ownership denominators, canonical Meiga identity, and absence of saved run IDs or invented mean/P90 values. This is a real NOT_READY verification; it does not claim live READY-path success.

## 10. New Week 5 run ID

`5e51be99-6567-4e85-b1ea-992a475f5eac`, created through normal `OptimizerService.run_job` with the copied original request and a fresh optimizer ID. [Request](artifacts/classic_gpp_overblocking_repair/rerun_request.json), [saved optimizer](artifacts/classic_gpp_overblocking_repair/rerun_optimizer.json), and [run log](artifacts/classic_gpp_overblocking_repair/live_run.log).

Earlier repair attempts are retained in `attempt_1`, `attempt_2`, and `attempt_3`; they are not the final result. One exposed the roster-link parsing defect and another the PostgreSQL null-parameter type defect; both were repaired before final verification.

## 11. Final readiness state

**NOT_READY**, with terminal optimizer status `failed`. Salary, projection, player-status, and ownership requirements remain NOT_READY; markets are READY. Weather remains `NOT_REQUIRED_BY_CURRENT_MODEL`. Final game-day clearance remains UNEVALUATED. No `classic_evidence_snapshot` was frozen and no old projection/ownership was consumed. This is the expected safe outcome for the remaining real evidence gaps.

## 12. Solver execution

**`solver_called=false`, `override_used=false`, zero lineups.** Production generation stopped before candidates and solver invocation. The requested five entries were preserved, not reduced. The prior run's full persisted record remained unchanged according to its before/after digest.

## 13. Remaining user action genuinely required

No replacement salary upload is required. To complete the retained contract, recover the **native draft-group ID with authentic evidence from the original download/contest source**, then attach that provenance through the existing source workflow. A filename or assertion alone cannot manufacture it.

Resolve the five genuine native salary identity cases through the review workflow, persisting sourced rules; duplicate canonical entities and the LS/TE conflict require explicit correction. Supply or ingest current Arizona/Washington role/status facts and sourced practice/workload context for the material Q cases. Then create another normal fresh run; the pipeline will reassess, rebuild dependencies, recheck all 11 markets, freeze only on READY, and solve the same five-entry request only after that gate passes. Game-day inactive and entry clearance must still be checked separately at the appropriate time.

Suggested recurring repository rule: **a failed live projection or ownership refresh must never invoke the saved-input fallback selector; persist null dependency IDs and the exact blocking evidence instead.** This can be added to AGENTS.md if desired.
