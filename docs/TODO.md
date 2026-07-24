# football_26 Canonical Backlog

Last reviewed: 2026-07-24

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

Application behavior was verified during consolidation on 2026-07-22; fresh-database
schema parity was reverified on 2026-07-24:

- `football_26` is the canonical repository and application.
- Digital Twin, Model Workbench, War Room, Research Lab, Contest Delivery,
  Intelligence, and Operations run in one Vite application.
- One FastAPI process exposes 103 route contracts without method/path collisions.
- All 14 numbered migrations apply to PostgreSQL with an exact
  ledger and a no-op second pass; 19 ORM-managed `public` tables have zero drift,
  and all 55 migration-owned `target` tables have a recorded compatibility contract.
- The combined suite passes 339 Python tests and the production UI build passes.
- A persisted 1,000-iteration Week 11 simulation and optimizer lineage reload through
  the consolidated API.
- Runtime scans contain no import or filesystem dependency on `football_opt`.

See `docs/CONSOLIDATION.md` for the complete contract and verification evidence.

## Execution Order

1. Close the one-repository consolidation gates (`CON-*`).
2. Make long-running and weekly workflows production-safe (`OPS-*`, `ENG-*`).
3. Finish the live cash, GPP, and showdown engines (`OPT-*`).
4. Strengthen point-in-time data, model governance, and correlated simulations
   (`DATA-*`, `MODEL-*`, `SIM-*`).
5. Close the outcome and personal-learning loop (`LEARN-*`).

## P0 — Consolidation Closeout

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| CON-001 | Blocked | Run one real DraftKings entry-template workflow through import, completed optimizer selection, portfolio assignment, validation, CSV generation, download, and persisted reload. | A real DK entry template for a populated slate | Entry count, site IDs, roster slots, salary, contest IDs, content hash, and reloaded artifact all match; validation has no errors. |
| CON-004 | Blocked | Review and checkpoint the consolidation branch, then make `football_opt` read-only or archive it. Deletion remains a separate explicit decision. | CON-001 | Diff is reviewed, combined checks pass, branch is committed, recovery reference is recorded, and daily development uses only `football_26`. |

## P1 — Production Operations And Engineering

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| OPS-001 | Ready | Move benchmarks, projection builds, simulations, and ultimate-lineup jobs from API-process background work to a dedicated worker queue while preserving current run IDs, idempotency, progress, retry, checkpoint, and result contracts. | CON-004 recommended | API restarts do not lose work; duplicate dispatch reuses the same request; workers can retry/resume; run status remains UI-visible. |
| OPS-002 | Ready | Implement the resumable weekly orchestrator from imported `DT-801`: ingest, readiness, predict, adjust, simulate, optimize, validate, and export as separately inspectable stages. | OPS-001, CON-001 | A weekly run resumes after an interrupted stage without repeating completed writes and exposes logs, counts, warnings, errors, and artifact IDs. |
| OPS-003 | Blocked | Add lock-aware news, injury, ownership, projection, and lineup refreshes (`DT-802`). | DATA-002, OPS-002 | Each refresh creates a new cutoff-stamped run, preserves prior versions, and never changes a locked historical snapshot. |
| OPS-004 | Blocked | Add pre-lock and post-result monitoring for data staleness, drift, calibration, failed jobs, and export readiness (`DT-804`). | OPS-002, LEARN-001 | Alerts identify an actionable owner, affected slate/run, threshold, and recovery step. |
| ENG-002 | Ready | Share active season/week/slate context and persisted-run selection across Digital Twin, Models, War Room, Research Lab, Delivery, and Operations. | None | Changing the active slate in one workspace updates the shell and destination workspace without silently resetting compatible run selections. |

## P1 — Complete The Live Decision Engines

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| OPT-001 (`DT-501`) | Ready | Wire the advanced classic GPP service into the live optimizer behind an explicit strategy/version flag. | Existing `DT-104`, `DT-105`, `DT-502` foundations | Selected strategy is actually executed, validated, persisted, reloadable, and visible in optimizer explanations and UI results. |
| OPT-002 (`DT-601`) | Ready | Finish the showdown solver’s move into the persistent format/objective architecture. | Existing persistent optimizer contracts | Showdown cash and GPP are distinct run types; lineups, captain/flex slots, failures, and lineage survive restart and reload. |
| OPT-003 (`DT-404`) | Blocked | Add diversified cash portfolios and deterministic late-news replacement rules. | OPT-005 | Multiple legal cash lineups respect exposure/risk limits; replacements preserve locked players and produce an auditable before/after report. |
| OPT-004 (`DT-402`) | Research | Complete promotion-grade classic cash stacking replay with proven pre-lock salary inputs and normalized cash outcome evidence. | DATA-001 | Walk-forward comparisons use complete actuals and defensible cash-line/field evidence; promoted policy beats the unconstrained baseline on declared downside and median gates. |
| OPT-005 (`DT-403`) | Blocked | Complete cash contest evaluation with verified contest type, fees, field size, payout tiers, and real historical cash files. | DATA-001 | Reports include win/double-up rate, median and lower-tail margin, ROI only where payouts are exact, and uncertainty across slates. |

## P2 — Data Quality And Point-In-Time Inputs

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| DATA-001 | Blocked | Import verified historical cash contest files and real entry templates with contest metadata and payout tiers. | User-provided/source-authorized files | Files are content-addressed, identity-safe, cutoff-labeled, deduplicated, and sufficient for CON-001 plus OPT-004/005. |
| DATA-002 (`DT-304`) | Research | Add point-in-time Vegas, props, weather, depth-chart, injury, and role snapshots, starting only with sources whose historical availability can be proven. | Source and usage decisions | Each record has source, observed-at, effective-at, ingest-run lineage, canonical identities, and a replay test proving post-lock data is excluded. |
| DATA-003 | Ready | Reassess legacy identity warnings after consolidation and either resolve deterministic cases or explicitly retain quarantine/waiver reasons. | None | Readiness reports distinguish resolved, ambiguous, no-match, and accepted quarantine; no unresolved record enters modeling or lineups silently. |

## P2 — Projection And Model Governance

| ID | Status | Work | Dependencies | Acceptance check |
| --- | --- | --- | --- | --- |
| MODEL-001 (`DT-302`) | Research | Finish QB/RB/WR/TE opportunity-efficiency decomposition and formal DST ablations with a promotion-grade untouched holdout. | DATA-002 where a feature needs external context | Ablations report walk-forward MAE/calibration by position and role; DST evidence includes an untouched holdout rather than diagnostic-only improvement. |
| MODEL-002 (`DT-305`) | Ready | Complete model-registry champion/challenger evaluation and explicit promotion/rollback rules. | Existing immutable projection runs | A challenger cannot become active without declared data window, feature/code hashes, comparable gates, approval record, and reversible active-pointer change. |
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
| LEARN-001 (`DT-803`) | Blocked | Load contest results and evaluate projections, symbolic rules, beliefs, lineups, portfolios, and exports after every completed slate. | OPS-002, verified result files | Each completed slate produces one auditable report tied to source files and exact run IDs, with missing evidence shown rather than inferred. |
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
