# football_26 Canonical Backlog

Last reviewed: 2026-09-12

This is the single source of truth for active product, data, modeling, simulation,
and operational work in `football_26`. Completed implementation history belongs in
`RELEASE_NOTES.md`, with durable architecture and model decisions in
`docs/DECISIONS.md` and `docs/MODEL_REGISTRY.md`.

Imported roadmaps under `docs/product/` are design references. They do not set
priority or status after repository consolidation.

## North Star

Produce an auditable DFS decision chain for every contest entry:

`source snapshots -> canonical identity -> features -> projections -> human/rule adjustments -> simulations -> optimizer -> portfolio -> export -> results -> learning`

Every stage must be point-in-time safe, reproducible by run ID, operationally
observable, and reversible without overwriting earlier evidence.

## How To Use This Backlog

- Work in priority order unless a dependency or external-data blocker is explicit.
- Keep no more than two tasks marked `In progress` at once.
- A task is not complete until its acceptance check and relevant tests pass.
- Move completed tasks to `RELEASE_NOTES.md`; do not let this file become a completion ledger.
- New work requires a stable ID, priority, status, dependency, and acceptance check.
- Model candidates never become production defaults automatically.

Status values:

- `Ready`: sufficiently defined and unblocked.
- `In progress`: active implementation work.
- `Blocked`: waiting on named data, authority, or another task.
- `Research`: evidence must be produced before implementation or promotion.
- `Parked`: intentionally outside the current execution horizon.

## Verified Combined Baseline

Application behavior was reverified during the 2026 preseason readiness pass on
2026-08-26:

- `football_26` is the canonical repository and application.
- Digital Twin, Model Workbench, War Room, Research Lab, Contest Delivery,
  Intelligence, and Operations run in one Vite application.
- One FastAPI process exposes 116 route contracts without method/path collisions.
- The local PostgreSQL ledger contains all 23 numbered migrations through
  `0023_current_weather_forecast.sql`; the schema-smoke workflow remains the
  empty-PostgreSQL and no-op-second-pass gate.
- The combined suite passes 433 Python tests, all 12 UI tests, and the production
  UI type-check/build. Application CI now runs those checks for pushes and pull requests.
- The first immutable 2026 schedule snapshot contains all 272 regular-season games. The
  source-authorized Week 1 Sunday Main salary snapshot contains 719 rows across 12/12 resolved
  games; 531 player identities resolve and 188 remain in the explicit review queue. The first
  provider attempt retained 12 horizon errors, so successful real weather receipts remain
  outstanding.
- Development weekly run `aeb1e82f-ab0d-4ffe-a38b-88db355e7f3e` persisted six
  stages through optimization and stopped explicitly at the `CON-001` real-template
  validation gate; completed ingest/readiness writes were skipped on resume.
- A persisted 1,000-iteration Week 11 simulation and optimizer lineage reload through
  the consolidated API.
- Runtime scans contain no import or filesystem dependency on `football_opt`.

See `docs/CONSOLIDATION.md` for the complete contract and verification evidence.

## Execution Order

1. Preserve the time-sensitive 2026 prospective cohort and close its live acceptance gates
   (`WTHR-007`, `DATA-002`).
2. Close the one-repository consolidation gates (`CON-*`).
3. Make long-running and weekly workflows production-safe (`OPS-*`, `ENG-*`).
4. Finish the live cash, GPP, and showdown engines (`OPT-*`).
5. Strengthen point-in-time data, model governance, and correlated simulations
   (`DATA-*`, `MODEL-*`, `SIM-*`).
6. Close the outcome and personal-learning loop (`LEARN-*`).

## P0 — Consolidation Closeout

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| CON-001 | Blocked | Run one real DraftKings entry-template workflow through import, completed optimizer selection, portfolio assignment, validation, CSV generation, download, and persisted reload. | A real DK entry template for a populated slate | Entry count, site IDs, roster slots, salary, contest IDs, content hash, and reloaded artifact all match; validation has no errors. |
| CON-004 | Blocked | Review and checkpoint the consolidation branch, then make `football_opt` read-only or archive it. Deletion remains a separate explicit decision. | CON-001 | Diff is reviewed, combined checks pass, branch is committed, recovery reference is recorded, and daily development uses only `football_26`. |

## P1 — Production Operations And Engineering

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| ENG-003 | Ready | Establish a migration-clean sidecar development database and a non-destructive transition plan for the existing legacy public-schema drift. Preserve the current database and immutable artifacts until parity is proven; do not drop legacy tables in place. | None | All 23 migrations apply to the empty sidecar, the second pass is a no-op, public and target drift checks pass, required development evidence is replayed or linked, and rollback to the untouched current database is documented. |
| OPS-003 | Blocked | Add lock-aware news, injury, ownership, projection, and lineup refreshes (`DT-802`). | DATA-002 | Each refresh creates a new cutoff-stamped run, preserves prior versions, and never changes a locked historical snapshot. |
| OPS-004 | Blocked | Add pre-lock and post-result monitoring for data staleness, drift, calibration, failed jobs, and export readiness (`DT-804`). | LEARN-001 | Alerts identify an actionable owner, affected slate/run, threshold, and recovery step. |

## P1 — Complete The Live Decision Engines

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| OPT-003 (`DT-404`) | Blocked | Add diversified cash portfolios and deterministic late-news replacement rules. | OPT-005 | Multiple legal cash lineups respect exposure/risk limits; replacements preserve locked players and produce an auditable before/after report. |
| OPT-004 (`DT-402`) | Research | Complete promotion-grade classic cash stacking replay with proven pre-lock salary inputs and normalized cash outcome evidence. | DATA-001 | Walk-forward comparisons use complete actuals and defensible cash-line/field evidence; promoted policy beats the unconstrained baseline on declared downside and median gates. |
| OPT-005 (`DT-403`) | Blocked | Complete cash contest evaluation with verified contest type, fees, field size, payout tiers, and real historical cash files. | DATA-001 | Reports include win/double-up rate, median and lower-tail margin, ROI only where payouts are exact, and uncertainty across slates. |
| OPT-006 | Blocked | Extend the v3 context-weighted stack score with immutable pre-lock projected pass attempts/TDs, neutral pass rate, team play volume/pace, target concentration, and role-aware QB/RB interaction. Every optional component must abstain when its lineage is unavailable rather than falling back to a structural bonus. | DATA-002 | Each component has an explicit source/cutoff contract, appears in fired-rule evidence, scales continuously, scores zero when unsafe or missing, and passes walk-forward ablation before any promoted weight change. |
| OPT-007 | Ready | Generate matched control lineups with all hard inputs held constant and optimizer context/correlation rules disabled, then report player swaps and opportunity-cost deltas for mean, individual ceiling sum, salary, ownership, leverage, and every rule contribution. | Existing optimizer run lineage | Every scored run can reproduce its control, identifies exactly which soft rules changed selection, never labels the ceiling sum as a lineup quantile, and exposes the comparison in API/UI JSON without changing lineup legality. |

## P2 — Data Quality And Point-In-Time Inputs

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| DATA-001 | Blocked | Import verified historical cash contest files and real entry templates with contest metadata and payout tiers. | User-provided/source-authorized files | Files are content-addressed, identity-safe, cutoff-labeled, deduplicated, and sufficient for CON-001 plus OPT-004/005. |
| DATA-002 (`DT-304`) | Blocked | Add point-in-time Vegas, props, weather, depth-chart, injury, and role snapshots. `point_in_time_cutoff_v1` excludes retrospective injury rows; `prospective_source_snapshot_v1` now retains the real 2026 schedule and Week 1 Sunday Main salary slate. Retrospective actual weather remains replay-ineligible. WTHR-003 supplies the 2024–2025 fixed-24-hour cohort, and WTHR-004 supplies append-only current forecast capture without fabricated provider timing. | Successful prospectively captured weather plus timestamped/source-authorized feeds for the remaining domains | Each pre-lock record has source, cutoff-safe timing semantics, ingest-run lineage, game identity, and a replay test proving post-lock data is excluded. Actual-weather contract: `docs/HISTORICAL_WEATHER_DATA.md`; venue registry: `docs/WEATHER_VENUE_REGISTRY.md`; historical forecast implementation: `docs/HISTORICAL_WEATHER_FORECASTS.md`; current forecast implementation: `docs/CURRENT_WEATHER_FORECASTS.md`; capture contract: `docs/PROSPECTIVE_SOURCE_CAPTURE.md`. |
| DATA-003 | Done | Reassessed all 1,010 legacy unresolved salary identities against 10,972 current masters: zero became deterministic, while 979 `no_match` and 31 `ambiguous` decisions reproduced exactly and remain accepted quarantines. The read-only `salary_identity_audit_v1` command fails on new deterministic matches, reason drift, untracked rows, unexpected reasons, or unresolved DSTs. | None | Readiness reports resolved, ambiguous, no-match, accepted, unaccepted, and untracked counts; the development audit has zero blockers, and target snapshots plus optimizer/replay salary inputs require canonical IDs. Evidence: `docs/DATA-003_IDENTITY_REASSESSMENT.md`. |
| DATA-004 | Ready | Resolve the 188 open 2026 Week 1 Sunday Main salary identities using source-native IDs and current roster aliases first, then unique team + position + normalized-name evidence. Persist every accepted alias or rule; never join by raw display name alone. Prioritize optimizer-eligible and higher-salary players while retaining nondeterministic rows in review. | Source-authorized current roster or registry evidence | All optimizer-eligible and priority salary rows resolve deterministically or remain under an explicitly accepted quarantine; unresolved DSTs remain zero, the identical salary rerun is stable, and readiness reports exact resolved/open counts with no silent drops. Evidence starts in `docs/PROSPECTIVE_SOURCE_CAPTURE.md`. |

### Weather Data And Slate Visibility

Complete these tasks in order unless a dependency explicitly allows parallel work. Retrospective
actual conditions and pre-lock forecasts remain separate contracts throughout storage, API, UI,
modeling, and replay.

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| WTHR-001 | Done | Added `nfl_venue_registry_v1` with 37 versioned venue records, effective seasons, coordinates, IANA timezones, roof defaults, evidence, review notes, immutable-definition checks, and explicit unresolved/ambiguous mapping states. All 570 games from 2024–2025 resolve: 555 by PFR `stadium_id` and 15 by reviewed game-ID override. | Existing nflverse schedules | Zero unresolved, ambiguous, source-conflicting, or unreviewed-neutral games; display names are diagnostic only. Evidence: `docs/WEATHER_VENUE_REGISTRY.md`. |
| WTHR-002 | Done | Approved `weather_forecast_source_contract_v1`: Open-Meteo Previous Runs, exact 24-hour `*_previous_day1`, pinned `ncep_gfs_seamless`, six core variables, Professional-or-higher production boundary, CC BY 4.0 attribution, immutable local retention, and direct NOAA HRRR CONUS fallback. | None | Costs, limits, licence, fallback, config, and production boundaries are explicit. Provider issued/availability times remain null because the fixed-lead API does not expose them; `forecast_basis_at` is derived and cannot be relabeled as observed. Evidence: `docs/WEATHER_FORECAST_SOURCE_CONTRACT.md`. |
| WTHR-003 | Done | Migration `0022` and `weather_forecast_source_contract_v1` retain immutable 2024–2025 fixed-24-hour Open-Meteo forecasts, raw responses/manifests, resolved venue records, requested/returned coordinates, pinned model/variables, valid/received/basis times, null provider timing, units, redacted URIs, checksums, and per-run results. The acceptance cohort has 570/570 fully available forecasts and verified artifacts with zero issues; a rerun reuses natural-key snapshots without provider traffic. | WTHR-001, WTHR-002 | Leakage tests prove cutoff-basis behavior, missing/error reporting, timing non-fabrication, and no actual-weather substitution. Evidence: `docs/HISTORICAL_WEATHER_FORECASTS.md`. |
| WTHR-004 | Done | Migration `0023` adds append-only current Forecast API versions using actual receipt-time cutoff semantics, explicit canonical game IDs, scheduled watch-mode refreshes, request spacing, freshness/stale/error reporting, immutable artifacts, and separate current-run lineage. Post-lock versions remain retained but cannot replace the as-of-lock selection. | WTHR-002, WTHR-003 | Focused tests retain multiple timestamped current-slate versions, reconstruct the exact pre-lock view, report stale/provider-failure states, enforce pinned/redacted requests, and verify request throttling. A real 2026 prospective slate remains part of DATA-002/WTHR-007 acceptance. Evidence: `docs/CURRENT_WEATHER_FORECASTS.md`. |
| WTHR-005 | Done | Added typed `slate_game_weather_v1` through `GET /api/weather/slate`. It resolves salary team/opponent pairs to canonical schedule game IDs, unions canonical current-capture lineage, and returns every resolved, unresolved, or ambiguous matchup with kickoff, versioned venue/roof basis, cutoff-safe forecast source/age/values, explicit weather/quality states, and separately labeled historical actuals. | WTHR-003; WTHR-004 for live refresh behavior | Tests prove historical as-of-lock reconstruction, post-lock exclusion, current receipt-only selection, stale and indoor states, actual/forecast separation, timezone enforcement, alias reconciliation, and unresolved-matchup retention without display-name joins. Evidence: `docs/SLATE_GAME_WEATHER_API.md`. |
| WTHR-006 | Done | The War Room now consumes `slate_game_weather_v1`, retains all canonical and unresolved API matchups in the Game Pressure Matrix, shows a five-state weather badge plus compact forecast conditions, and opens selectable detail for temperature, wind/gusts, precipitation, venue-registry roof default, source/timestamp, valid time, cutoff-age freshness, and quality warnings. Completed historical actuals render only in a separate replay-ineligible panel. | WTHR-005 | Focused tests cover canonical-ID-first association, alias fallback, non-truncation, five-state presentation, formatting, warnings, and the historical-only actual gate. All 12 UI tests and the production build pass; desktop and 390px fallback/error renders have no page overflow or browser diagnostics. Data-rich past/current rendering remains WTHR-007. Evidence: `docs/WAR_ROOM_WEATHER.md`. |
| WTHR-007 | In progress | The real DraftKings 2025 Week 11 `SUNDAY_MAIN` database/API/UI run passes 11/11 games with 9 available, 2 indoor, 2 retractable venue defaults, zero cutoff violations, and zero replay-eligible actuals. The real 2026 Week 1 Sunday Main salary capture has 719 rows and resolves 12/12 canonical games with no quarantine. Its first provider attempt retained 12 HTTP 400 horizon errors because September 13 was one day outside the provider window; no forecast was fabricated. Focused tests prove historical/current idempotency, append-only pre/post-lock selection, missing/unresolved retention, neutral/international overrides, indoor/retractable behavior, stale/error states, actual separation, and a weather-free projection/simulation/optimizer boundary. | September 13 entering the provider horizon and scheduled successful real receipts | Close only after the Sunday Main slate passes reproducible data/API/UI checks with at least two pre-lock receipts and a retained post-lock version excluded from the lock view. Evidence: `docs/WTHR-007_ACCEPTANCE.md`. |

## P2 — Projection And Model Governance

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| MODEL-001 (`DT-302`) | Blocked | The locked `model_001_opportunity_efficiency_ablation_v1` experiment completed QB/RB/WR/TE opportunity-efficiency and formal DST group ablations. Its reserved 2025 W12-W18 holdout rejected the combined candidate at `2.978` MAE versus `2.976` baseline; RB improved `0.35%`, QB/WR/TE regressed slightly, and added DST groups failed validation. Production was unchanged. | Prospectively captured 2026 salary/source cohort with proven pre-lock observation time and enough completed holdout weeks | Re-run the content-locked contract on untouched 2026 evidence; MAE and interval calibration must pass by position and lagged role, and any challenger must use MODEL-002 approval. Evidence: `docs/MODEL-001_CANDIDATE_LOCK.md`, `docs/MODEL-001_HOLDOUT_EVIDENCE.md`. |
| MODEL-002 (`DT-305`) | Done | Added immutable `model_challenger_evaluation_v1` and `model_promotion_decision_v1` contracts. New projection runs remain challengers once a scope has a champion; promotion requires ordered time windows, exact feature/code lineage, at least one strict improvement gate, all gates passing, a named approval, and an atomic compare-and-set pointer change. Rollback records a second approval and restores the exact champion. | Existing immutable projection runs | Focused tests cover invalid windows, blocked gates, API contracts, approval-only selection, atomic promotion, and exact rollback. PostgreSQL migration `0017` applies idempotently with 57 expected/actual target tables and preserves the current Week 11 champion. Evidence: `docs/MODEL-002_PROMOTION_GOVERNANCE.md`. |
| MODEL-003 | Research | Re-evaluate accepted default-off online residual learning on new completed slates and decide whether it should remain experimental, be promoted, or be retired. | LEARN-001, enough new post-cutoff slates | Later-window MAE, RMSE, calibration, slice stability, and identity coverage are compared with the unchanged production baseline. |

## P2 — Correlated GPP And Showdown Simulation

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| SIM-001 (`DT-503`) | Research | Replace independent player draws with joint game/player simulations using shared latent game states and learned correlations. | DATA-002, MODEL-001 | Marginal distributions remain calibrated while observed teammate/opponent correlations and game totals are reproduced out of sample. |
| SIM-002 (`DT-504`) | Blocked | Sample realistic opponent fields from ownership and construction behavior. | SIM-001, existing ownership challenger | Generated fields match historical ownership ranks, stacks, salary usage, roster construction, and duplication distributions by contest format. |
| SIM-003 (`DT-505`) | Blocked | Optimize expected payout and top-percentile probability instead of summed player P90. | SIM-001, SIM-002, verified payouts | Replay reports top 1%, top 0.1%, cash rate, expected payout, ROI, and uncertainty against the current objective. |
| SIM-004 (`DT-506`) | Blocked | Add contest-aware GPP portfolio exposure, diversification, and entry assignment. | SIM-003, existing portfolio persistence | Risk/exposure limits and lineup allocation vary explicitly by field size, payout structure, entry count, and user risk budget. |
| SHOW-001 (`DT-602`) | Blocked | Build captain- and flex-specific ownership models. | OPT-002, sufficient showdown ownership data | Calibration and rank metrics are reported separately for CPT and FLEX with strict earlier-slate validation. |
| SHOW-002 (`DT-603`) | Blocked | Add showdown game-script simulations and construction features. | SIM-001, OPT-002 | Replays cover 5-1/4-2/3-3 structures, game scripts, role changes, kicker/DST behavior, and calibrated scoring outcomes. |
| SHOW-003 (`DT-604`) | Blocked | Estimate lineup duplication and prize splitting. | SIM-002, SHOW-001, SHOW-002 | Expected payout incorporates estimated duplicated-lineup counts and split prizes with calibration evidence. |
| SHOW-004 (`DT-605`) | Blocked | Optimize showdown cash stability and GPP expected payout separately. | SHOW-002, SHOW-003 | Both objectives beat simple P90 maximization on declared walk-forward metrics without sharing post-lock data. |

## P2 — Outcome And Personal Learning

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| LEARN-001 (`DT-803`) | Blocked | Load contest results and evaluate projections, symbolic rules, beliefs, lineups, portfolios, and exports after every completed slate. | Verified result files | Each completed slate produces one auditable report tied to source files and exact run IDs, with missing evidence shown rather than inferred. |
| LEARN-002 (`DT-704`) | Blocked | Ask targeted agent questions only for high-value uncertainty or model/human disagreement. | Existing guarded belief modifiers, LEARN-001 recommended | Triggers use versioned value-of-information rules; every question, answer, no-change response, and resulting modifier is persisted. |
| LEARN-003 (`DT-705`) | Blocked | Score human beliefs and accepted/rejected/no-change answers after outcomes. | LEARN-001, LEARN-002 | Reports show where intervention helped, hurt, or had no measurable effect by scope and confidence, without rewriting the original belief. |
| LEARN-004 (`DT-706`) | Blocked | Learn a guarded personal-policy challenger from accumulated feedback. | LEARN-003, minimum evidence thresholds | Recommendations are replayed against model-only and human-only variants, require approval, and cannot silently change an active rule or model. |

## P3 — Parked Horizons

| ID | Status | Work | Revisit when |
| --- | --- | --- | --- |
| PARK-001 | Parked | Best Ball draft, roster, ADP, playoff-correlation, advancement, and payout modeling. | Weekly DFS operations and learning are stable; a separate product/schema decision is approved. |
| PARK-002 | Parked | Fully autonomous symbolic-rule disabling or retuning. | LEARN-001 has sufficient evidence and explicit safety/rollback governance exists. |
| PARK-003 | Parked | Additional paid/vendor feeds. | A source adds measurable point-in-time signal, licensing is clear, and the existing feed cannot meet the need. |
| PARK-004 | Parked | Delete the archived `football_opt` repository. | The user explicitly chooses deletion after the archive/recovery period. |

## Recurring Operating Work

These are routines, not backlog-completion tasks:

- Run classic and showdown benchmarks as separate tracks.
- Track gap metrics, bootstrap intervals, projection coverage, ownership calibration,
  and captain-prior drift after material changes and on the scheduled cadence.
- Preserve production defaults until a declared walk-forward gate beats them.
- Review unresolved identity, data freshness, job failures, and export readiness before lock.
- Record accepted/rejected model decisions in `docs/DECISIONS.md` and
  `docs/MODEL_REGISTRY.md`.

## Definition Of Done

Every completed task must satisfy the applicable requirements:

1. Stable canonical identities; no raw display-name joins.
2. Point-in-time cutoffs and immutable run/source lineage.
3. Idempotent, observable UI/API action with actionable failures.
4. Numbered migration for persistence changes.
5. Targeted tests plus the relevant combined regression/build checks.
6. Replay or walk-forward evidence for performance claims.
7. Documentation and release-note synchronization.
