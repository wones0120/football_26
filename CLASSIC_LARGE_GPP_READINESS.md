> Live generation now requires the pre-generation contract described in
> [Classic live data readiness](docs/product/classic_live_data_readiness.md).
> The saved-input assessment below remains available for archived reports and
> final entry review; it cannot authorize generation from incomplete evidence.

# Normal Classic Large-GPP readiness completion

Reviewed saved run: `1fdbb3c7-53a4-42c3-a277-c56db54c783c`. No live solve or input refresh.

**Confirmed cause:** normal Large GPP omitted `classic_entry_readiness`; only Small-field execution called it, and HTML read only the Small-field result. This was an unconnected validator plus reporting gap, not missing market values. The October 3 worker had remained running after the prior API-only reload; its historical loaded bytecode hash was not recorded, so process age alone does not establish a different cause.

Actual path: UI submission trace at **15:44:00 UTC** → `/api/optimizer/jobs` → durable queue `1bcee4d7-3a15-40e7-9710-d438ccf54e17` → optimizer worker handler → `OptimizerService.run_job` → saved `target.optimizer_run` → normal results GET → readable HTML. Queue execution was **15:45:53–15:46:18 UTC**. Frozen decision time is **15:45:53.998247 UTC**, taken from explicit UTC snapshot metadata, not the saved row's inconsistent timezone rendering or completion time.

**Narrow fix:** normal execution now saves shared salary/identity, pre-lock, projection, ownership and existing market freshness checks plus independent saved-constraint validation. Small-field candidate-size and automatic injury-cap policies are not imported. Current clearance, salary/source freshness, weather freshness, contest assignment and submission verification stay explicitly unavailable. Normal result responses, the UI and HTML propagate readiness. **Validate saved inputs at current time** assesses frozen artifacts without solving, refreshing or rewriting original readiness.

**Runtime PASS:** idle checks found zero queued/running jobs, zero running optimizer records and no API/worker children. The established backend restart loaded API **19397** and worker **19391** at **16:31:21/16:31:20 UTC**. Both loaded `optimizer.py` hash `e63e2ad6624e4d1bd82ace87e2562a3398464ebbe84fb604d7757fb6d5b424f4` and readiness module hash `af0768dc1e4bb13c7e3fbba35b1f6a792c62aab01c7ce5f33057fe8950119c43`. Health and live OpenAPI passed. Final API-only reload for synchronous response parity loaded API **21942** at **2026-10-04T16:41:47.542564+00:00**, with worker **19391** unchanged and matching hashes. Runtime evidence is retained in `artifacts/classic_large_gpp_readiness/`.

**Actual saved-run verification PASS; entry clearance BLOCKED:** the real app reopened this exact run and validated at **16:32:18.593260 UTC**. Roster/constraints, salary identity, pre-lock evidence, 154/154 projections and ownership coverage pass. Market coverage is **12/12**, missing/invalid **0**, stale **12**. The UI and downloaded HTML show **ENTRY READY: NO / BLOCKED**, original readiness **not evaluated**, and a separate present-time assessment. Current official availability and weather/salary freshness remain unevaluated. No threshold or approval policy was invented.

Market lineage: consumed projection `e56ee32e…` → model run `75be6de1…` → feature run `10eba32a…` → twelve normalized `nflverse_schedules` observations at **October 2, 02:37:35.634345 UTC** → immutable source snapshot `d8730671-75e4-5ffb-b559-a99b12cbe9fe`, SHA256 `8fc8d5a52cbb5f1a4661be5fff6b91bd025470c8953981f95658f746e6ec3b62`. Total, team spread and implied total feed environment/context scoring. Observation basis is `capture_clock`; upstream quote publication time is unavailable. Ingest/completion times were not substituted. Observations were **61.14 hours** old at the original decision; the existing 6/24-hour policy blocks stale evidence within six hours of kickoff. The 392 saved projection-feature rows have no weather provenance fields; current weather readiness remains unavailable, not presumed fresh.

Material frozen availability includes Meyers: injury observation **September 29, 20:17:58 UTC**; LIMITED practice **October 2, 13:24:40 UTC**; `official_club_sunday_preview_depth_roles` context **October 2, 14:40:53 UTC**. Frozen practice was consumed, but final current clearance was not verified. The full selected-player evidence is inspectable in the UI/export. Achieved elevated exposure **2/5** is an outcome; the saved category cap is **none**, with the existing global limit **4/5**, not an enforced 40% cap.

| Game | Primary QB entries | Players by entry, including DST | Entries containing game | Total / 45 | Offense by entry | Offense / 40 |
| --- | ---: | --- | ---: | ---: | --- | ---: |
| CIN-JAX | 3 | 5, 5, 5, 2, 4 | 5/5 | 21/45 | 5, 5, 5, 2, 4 | 21/40 |
| DAL-HOU | 2 | 1, 1, 2, 4, 3 | 5/5 | 11/45 | 1, 1, 1, 4, 3 | 10/40 |
| ARI-NYG | 0 | 1, 1, 1, 1, 0 | 4/5 | 4/45 | 1, 1, 1, 1, 0 | 4/40 |
| CHI-NYJ | 0 | 0, 0, 0, 1, 0 | 1/5 | 1/45 | 0, 0, 0, 1, 0 | 1/40 |
| GB-TB | 0 | 0, 2, 0, 0, 0 | 1/5 | 2/45 | 0, 1, 0, 0, 0 | 1/40 |
| KC-LV | 0 | 0, 0, 1, 0, 1 | 2/5 | 2/45 | 0, 0, 1, 0, 1 | 2/40 |
| LAR-PHI | 0 | 2, 0, 0, 1, 1 | 3/5 | 4/45 | 1, 0, 0, 0, 0 | 1/40 |

Lineup 5's DAL-HOU primary label coexists with four CIN-JAX offensive players. This is not a primary-game cap violation. No new constraint, penalty or reward was added.

**Tests:** 19 focused backend checks and 26 frontend checks pass; TypeScript/Vite build passes with its existing bundle-size warning. A synthetic fixture covers UI parameters → queued normal API → actual durable optimizer handler → service/solver → persistence/reopen → HTML readiness/game exposure. Separate tests cover freshness policy, missing provenance, checksum rejection, unavailable entry checks, control snapshots and read-only history preservation. Synthetic tests are distinct from the actual saved run, which was never solved again. The real UI validation preserved all form values/checkboxes; only the player-inspection option list changed when opening the different saved report. Full saved optimizer and queue records remain unchanged.

**User actions:**

1. Operations → Recent optimizer runs → `1fdbb3c7` → Open results → **Validate saved inputs at current time** → inspect readiness/source evidence and game appearances → **Download readable lineup report**. Validation leaves original history unchanged.
2. For a rebuild, load fresh files with **Load Raw Salaries (CSV)** / **Load Raw Injuries (CSV)**, review **Load Starting QBs**, and use **Build Features (Season/Week)**. Markets/weather use the established `scripts/capture_nflverse_markets.py` / `scripts/capture_current_weather_forecasts.py` capture workflows. There is **no one-click UI capture or integrated final-current availability/weather clearance**; these remain precise readiness blockers. Refresh projections reloads the list only. No such refresh was performed here.
3. Before initiating **Run Optimizer** yourself, verify Classic / Large GPP, **5 / 80% / primary game 3 / overlap 5 / team 3 / game 5 / single TE off**. The current browser still has team **4**, deliberately preserved; set **3** yourself. Preserve DEN-opponent exclusion and all explicit player/risk preferences. Input preparation snapshots your controls before awaits; a fresh rebuild changes the evidence frame. Inspect the new report's blockers before assigning/verifying contest entries.

No scoring/default changes. No diagnostic replacement applied. No new user portfolio generated. No entries submitted. Saved history preserved.
