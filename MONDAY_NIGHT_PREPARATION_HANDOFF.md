# Monday Night Showdown Preparation Handoff

**Preparation remains blocked on native DraftKings confirmation.** The reference is saved run `c9a9a25c-e31c-4cca-b662-9ee3cd71b1fb`, strategy `showdown_gpp_portfolio_v3`, for ATL at NO on October 5, 2026, at 8:15 PM ET. This review accepts the Sunday-night application fixes. It performed read-only API requests, source-file verification and public-source review; no application imports, live captures, feature rebuilds, scoring changes, optimizer runs, replacement portfolios or submissions occurred.

The existing Operations preparation UI was inspected at **2026 / Week 4 / MONDAY_NIGHT**. Its current prepared projection is still the reference projection, `c35151e0-d1c2-4da6-b00e-c0aefbf3e40f`, feature run `f0bbcf22-a183-4aa0-b549-1c27f0363c59`, preparation job `99a404e8-356a-42b9-a465-1003889510fd`. “Verified current” means that the prepared build matches the stored inputs; it does not establish their current real-world accuracy or final entry clearance. The read-only preparation snapshot was returned at October 4, 9:01:40 PM ET.

## Native slate verification

The canonical preparation game is `2026_04_ATL_NO`, ATL away and NO home, kickoff `2026-10-06T00:15:00Z`. The [Saints Week 4 game page](https://www.neworleanssaints.com/tickets/2026/falcons-at-saints-tickets-information-history-week-4-october-5-2026) independently confirms October 5 at 7:15 PM CT, equivalent to 8:15 PM ET, at Caesars Superdome.

| Check | Result |
| --- | --- |
| Canonical game and kickoff | Verified against the salary text and official team schedule |
| Native DraftKings draft group | **Unconfirmed**; no linked salary snapshot retaining an operator-confirmed group |
| Old file integrity | Original file checksum matches retained ingest checksum `cbaa10b29e0bfe24adeaf779faa2b444426fbe18064104e0a8085ca1d1983ad1` |
| Old file scope | 112 rows, only `ATL@NO 10/05/2026 08:15PM ET`; 56 CPT and 56 FLEX |
| Old CPT/FLEX pairing | 56 pairs; distinct native slot IDs, CPT salary exactly 1.5 times FLEX, native ID/position/team/salary values match curated rows |
| Canonical identity coverage | 110/112 salary rows resolved; all ten priority players have canonical IDs and CPT/FLEX pairs |
| Unresolved salary rows | Cal Adomitis: CPT `44358656`, FLEX `44358600`, NO, file position TE |
| Injury identity coverage | 54/55 resolved; Cal Adomitis native key `134982-92056` remains unresolved |
| Current native salary compatibility | **Blocked** until a current download is compared with authoritative group metadata |

The old file is `/Users/wones/NFL/DKSalaries_2026_4_MONDAY_NIGHT.csv`; its original ingest is `d252c147-26e6-49df-b3f2-b808bb403afb`. It has no retained source observation/publication clock or linked snapshot. Its filename and player IDs do not identify a draft group. Internal pairing checks do not prove native compatibility.

DraftKings' public lobby redirected to sign-in, the public metadata request failed, and the computer-use tool denied Chrome access. No native group was inferred. **Required user action:** open the actual October 5 ATL@NO Monday Night Showdown contest in DraftKings, copy its contest URL and the explicitly displayed/authoritative draft-group ID, and download its current salary CSV. Supply that URL, confirmed group ID and exact local CSV path. If the group ID is not visible, supply the contest URL for a read-only metadata check; do not substitute a number from the filename or player IDs. This dependent verification stops here.

Adomitis is listed as LS on the [Saints unofficial chart](https://www.neworleanssaints.com/team/depth-chart), while the old salary file calls him TE. Preserve quarantine and resolve through the existing identity review path with source-native identity/team/position evidence. Do not force the match solely to reach zero unresolved rows.

## User preparation actions

After native verification, use **Operations → Prepare slate inputs**, scope **2026 / Week 4 / MONDAY_NIGHT**. Confirm Showdown for the eventual report, retaining the user's existing preferences and v3 policy. These are user actions; none was executed in this review.

1. **Salary evidence:** put the verified current CSV's absolute path in **Salary file**, enter the confirmed value in **Native DraftKings draft-group ID (operator confirmed)**, then click **Import DraftKings salary evidence**. Wait for the durable job to complete. Inspect **Observation, import, identities, source checksums and consumption** for the snapshot, group, checksum, exact game/kickoff, CPT/FLEX IDs and unresolved identities. Use this preparation import rather than **Load Raw Salaries (CSV)** to retain native evidence. Compare the current file's native IDs and values before considering it compatible; the old pairing count is not a required row count for a newer file.
2. **Supported injury/designation evidence:** choose **FanDuel** or **DraftKings** in **Injury CSV source**, provide the corresponding supported file in **Injury file**, and click **Import injury CSV evidence**. The current FanDuel file contains 55 rows with one unresolved identity; its ten priority-player designation/detail fields are null. Neither those nulls nor an absent report entry mean healthy or active. CSV evidence is not consumed canonical availability and does not establish game-day clearance.
3. **Canonical pregame evidence:** expand **Load sourced pregame availability evidence (manual JSON)**. Supply actual `source`, `source_uri`, original `observed_at`, and `players` with the canonical UUIDs in the priority-player evidence file. Use `injury_status` only for a sourced designation; keep `evidence.practice_participation`, `evidence.practice_observed_at`, `evidence.expected_workload_status`, and `evidence.expected_workload_observed_at` separate. Keep source-backed depth/starter facts and historical involvement with their own provenance. Omit unsupported numerical probabilities/shares/expected opportunities and unsupported status fields. Then click **Load sourced pregame evidence**. Do not paste a speculative template or convert a photo, depth chart, or “not listed” into FULL practice or confirmed active status.
4. **Starting QBs:** click **Review starting-QB evidence**. Inspect each team's candidates/source/tier. If the existing candidate review is presented, select the evidence-backed canonical QB, choose **Confirmed by source** only when supported, enter **Source URL** and a provenance note, then **Save Starting-QB Evidence**. A successful automatic load may retain inferred QB1 evidence without presenting that form; do not describe it as confirmed. The manual form stamps `observed_at` with the browser review time and has no original-time input: retain the original source publication/observation time and basis in the note and timestamped canonical evidence. Do not relabel the generated review clock as source publication time. If exact original starter observation cannot be retained in the required structured field through the existing path, leave that confirmation requirement incomplete and report the limitation; this task does not reopen the UI fix.
5. **Markets:** click **Capture nflverse markets** and wait for completion. Inspect the selected `2026_04_ATL_NO` market snapshot, source, original observation, capture basis and source checksum. A new capture clock does not establish sportsbook quote publication freshness; unchanged values alone do not establish either stale or current quotes. Preserve any retained earlier observation instead of replacing it with an import timestamp.
6. **Weather:** inspect **Forecast basis, receipt time, venue/roof, coverage and freshness**. The existing report resolves Caesars Superdome as `fixed_indoor`, state `indoor`, with no forecast/actual and `forecast_missing`. Use **Capture current weather** only where supported/relevant. A roof registry default is venue evidence, not a new roof observation or final weather clearance. Weather is not consumed by the projection contract; no weather scoring adjustment is requested.
7. **Dependencies:** after the source/identity/starter issues are addressed, click **Rebuild slate features and projections**, wait for completion, then **Reload preparation status**. Inspect **Exact persisted source → feature → projection consumption**, the new projection/feature IDs and current source hash. Require the confirmed native group, intended salary row IDs, current market snapshot ID, starter player IDs and the actual imported availability row IDs. Nonempty availability IDs prove consumption, not complete player coverage. Rebuilding unchanged inputs does not repair missing evidence. Stop after preparation; **Run Optimizer** and contest entry are separate tasks.

Preserve original observation, source publication, capture, import/receipt and review times as different clocks. For an undated dynamic page, publication time stays unknown; a new retrieval time cannot backdate its content. For multiple facts, retain each fact's original provenance/time. The loader selects the newest context row per player rather than merging all earlier rows; inspect the resulting row for coverage and retain still-applicable supporting evidence with its original nested clocks.

## Quarterback consumed inputs

Current preparation with refreshed sources is unavailable. These values describe **only the frozen reference projection**, with cutoff October 4, 8:41:37 PM ET. They are not an updated Monday forecast.

| Consumed input | Tyler Shough | Michael Penix Jr. |
| --- | ---: | ---: |
| Canonical UUID | `5b526bc4-52b4-4f6e-95eb-cf9e30358da6` | `62c84f93-8880-41fd-b5fe-98214b76c567` |
| Saved FLEX mean | 21.2961 | 12.6562 |
| Saved marginal P90 | 32.0217 | 23.4679 |
| Historical fantasy roll3 mean | 26.1267 | 11.6400 |
| Historical fantasy roll8 mean | 23.3150 | 14.2500 |
| History game count | 14 | 15 |
| Historical carries mean3 | 4.6667 | 1.3333 |
| Historical snap share mean3 | 1.0000 | 0.8733 |
| Historical team carries mean3 | 21.6667 | 32.0000 |
| Historical team targets mean3 | 41.3333 | 24.3333 |
| Consumed game total | 48.5 | 48.5 |
| Consumed team spread | −3.0 | +3.0 |
| Consumed team implied total | 25.75 | 22.75 |
| Canonical availability/practice/workload evidence | Missing | Missing |
| Consumed starter tier | Inferred | Inferred |

Both starters were consumed from `provisional_nflverse_depth_chart_qb1`, source `nflreadpy://depth_charts/2026`, original observation **October 4, 9:09:16 AM ET**. This is inspectable expected-starter evidence, not confirmed game-day starter/dressing status. Both saved model availability and start probability fields are `1.0`; these are existing model defaults in the absence of canonical context, **not sourced clearance**. No default was changed here.

Both use market snapshot `f1fc8132-2b7f-566c-8e85-772fc8264312`, observed/captured **September 29, 9:22:11.632067 PM ET**, basis `capture_clock`, source `nflverse_schedules`. Its observation age was **119.34 hours at the saved assessment**, not necessarily its age when this handoff is read. Upstream quote publication time is unknown. Supported current usage fields such as expected carries, snaps and explicit pregame role remain absent.

The consumed aggregates differ substantially; that is descriptive evidence, not a validated causal explanation for the projection gap. Historical game-by-game rows and their individual source publication times were not independently reconstructed here. **Both existing Player why responses flag `projection_parity=failed` and suppress counterfactuals because the reloaded mean differs from the saved production mean.** Keep their saved means, P90s and immutable feature values inspectable, but do not use their model-driver attributions as validated explanations. This finding records a limitation; it does not authorize a model fix.

After the user rebuilds, inspect the two UUIDs against the **new** run in the existing **Model disagreement → Player why** panel where available, or the existing read-only `/api/predict/audit/{new_projection_run_id}/player/{canonical_uuid}` endpoint. Compare confirmed starter identity/tier/time, historical inputs, sourced availability/practice/workload, saved mean/marginal P90, market/team inputs and per-player context/snapshot IDs. Repeat parity assessment and retain any failure. Do not change either forecast to reduce the difference. A player's marginal P90 is not a lineup joint P90 or win probability.

## Priority status and role review

None of the ten priority players is individually listed in the [Saints Saturday injury table](https://www.neworleanssaints.com/news/injury-report-atlanta-falcons-vs-new-orleans-saints-2026-nfl-week-4-saturday), published October 3 at 1:55 PM as displayed, or the [Falcons Saturday report](https://www.atlantafalcons.com/news/falcons-injury-report-monday-night-football-saints-divine-deablo-samson-ebukam), published October 3 at 1:02 PM as displayed. The reviewed pages do not identify a timezone for those publication labels. Preserve them as displayed rather than inventing a UTC publication time. These reports do not establish individual practice participation or final active status for unlisted players. No final Monday inactive/elevation reconciliation was verified.

NO depth facts below come from the **undated dynamic** [Saints unofficial chart](https://www.neworleanssaints.com/team/depth-chart), reviewed in this task; its original update time is unknown. ATL facts come from the dated [Week 4 unofficial chart](https://www.atlantafalcons.com/news/atlanta-falcons-week-4-depth-chart-vs-new-orleans-saints), September 29 at 4:00 PM as displayed. ATL practice-photo captions on the Saturday report document October 1 presence for all five ATL priority players, not FULL/LIMITED participation or unrestricted workload.

| Player | Starter or depth evidence | Historical involvement and remaining review |
| --- | --- | --- |
| Chris Olave | First WR on NO chart | Saved targets feature 9.414, snap share .847. Verify current routes, targets and workload; final active status missing. |
| Tyler Shough | First QB on NO chart; saved inferred QB1 | Consumed history above. Confirm Monday starter and game-day availability independently. |
| Juwan Johnson | First TE on NO chart | Saved targets feature 4.875, snap share .663. Dated team article reports 15 catches, 19 targets and three TDs through three games; historical red-zone involvement is supported, current receiving/blocking split is not established. |
| Devaughn Vele | First WR on NO chart | Saved targets feature 5.747, snap share .917. Verify current routes/receiving role and workload independently of chart placement. |
| Charlie Smyth | **Conflict:** saved NO kicker, but dynamic chart lists Daniel Carlson | Current kicking responsibility, roster/elevation and dressing need authoritative reconciliation. Do not infer inactive/zero workload or silently replace Smyth. |
| Michael Penix Jr. | First QB on dated ATL chart; saved inferred QB1 | October 1 practice presence; consumed history above. Confirm Monday starter and game-day availability independently. |
| Bijan Robinson | First RB on dated ATL chart | Practice presence; saved carries/targets features 17.002/5.416, snap share .667. Verify current committee, goal-line role and any limits. |
| Brian Robinson Jr. | Backup RB on dated ATL chart | Practice presence; saved carries/targets features 8.048/.471, snap share .333. Backup placement does not establish a current zero workload; verify rotation and rushing role. |
| Kyle Pitts Sr. | First TE on dated ATL chart | Practice presence; saved targets feature 1.725, snap share .533. Verify routes/targets versus blocking and TE rotation. |
| Jahan Dotson | First WR on dated ATL chart | Practice presence; saved targets feature 3.045, snap share .680. Verify receiving packages and current routes/targets. |

The saved carries/targets values are consumed historical allocation features, not sourced Monday expected opportunities; no current workload is manufactured from them. Null injury fields stay null. Depth, practice presence, designation, final inactive status, historical involvement and expected workload answer different questions.

Juwan's historical figures are supported by the [October 3 team article](https://www.neworleanssaints.com/news/new-orleans-saints-tight-ends-have-been-red-hot-in-the-red-zone-this-season), displayed at 1:30 PM; consumption of this newly reviewed article is not demonstrated. Noah Fant's questionable designation in the Saturday report is relevant to Johnson's TE context, but it does not establish an automatic target transfer. The [dated Week 4 preview](https://www.neworleanssaints.com/news/atlanta-falcons-vs-new-orleans-saints-preview-monday-night-football-2026-nfl-season-week-4-series-history-stats-connections) also refers to Carlson as a Saints kicker; Smyth references found in its photos describe January 4, 2026, historical game action and do not settle Monday's kicker. Keep this conflict pending until current native salary and team roster/role evidence agree.

Preserve the existing low-opportunity gate and its saved reasons. Its current exclusions remain visible in the reference player pool; no cheap player's unknown opportunity was converted to healthy status, supported workload, or eligibility. New dated evidence should enter canonical preparation and be consumed by the unchanged gate, not be used to bypass it.

## Saved strategy and evidence files

The reference remains a development preview. Its New Orleans concentration explains which players require priority review; it is not evaluated as final Monday strategy. Role ownership remains unavailable and its selector term uniformly disabled. No captain redistribution, exposure adjustment, leverage claim, duplication estimate, alternative portfolio or entry recommendation is made.

Read-only evidence is saved in [the evidence folder](/Users/wones/git/football_26/artifacts/monday_night_preparation_c9a9a25c): [reference run](/Users/wones/git/football_26/artifacts/monday_night_preparation_c9a9a25c/reference-run.json), [preparation status and source manifest](/Users/wones/git/football_26/artifacts/monday_night_preparation_c9a9a25c/preparation-status.json), [salary checks](/Users/wones/git/football_26/artifacts/monday_night_preparation_c9a9a25c/salary-validation.json), [priority canonical IDs and saved evidence](/Users/wones/git/football_26/artifacts/monday_night_preparation_c9a9a25c/priority-players.json), [Shough consumed inputs](/Users/wones/git/football_26/artifacts/monday_night_preparation_c9a9a25c/shough-consumed-inputs.json), and [Penix consumed inputs](/Users/wones/git/football_26/artifacts/monday_night_preparation_c9a9a25c/penix-consumed-inputs.json).

The request text ends at “Shough CPT.” Any remaining item 5 requirements have not been received. Native verification, current preparation and post-preparation QB review remain incomplete for the specific blockers above; the independent read-only review and user action handoff are complete.
