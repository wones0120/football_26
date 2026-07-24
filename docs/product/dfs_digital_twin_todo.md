# DFS Digital Twin Implementation TODO

> Status: imported pre-consolidation roadmap retained for design history. Active and
> incomplete items have been normalized into `docs/TODO.md`, which is the only
> authoritative source for current priority and status.

## Purpose

This was the implementation roadmap for turning the original product into a
replayable, data-informed DFS decision system that can:

- model DraftKings NFL classic and showdown slates;
- build distinct cash and GPP portfolios;
- import many contest and salary files;
- export validated DraftKings upload files;
- capture the user's durable strategy and weekly slate views;
- compare model-only, human-only, and combined decisions after every slate.

Area-specific documents remain useful design references, but status and priority
are tracked here.

## North Star

The system should preserve an auditable chain for every lineup:

`source snapshots -> features -> base projection -> human/rule adjustments -> simulations -> optimizer run -> lineup -> contest entry -> result -> learning`

No model, rule, or human opinion should silently overwrite an earlier belief.
Every run must be reproducible from its point-in-time inputs.

## Status Legend

- `Done`: implemented and verified in the live path.
- `Partial`: useful implementation exists but is incomplete or not wired live.
- `Next`: highest-priority implementation work.
- `Backlog`: ordered future work.
- `Blocked`: requires missing data, authority, or an external decision.

## Working Rules

- Use `football_26_dev` for database work.
- Treat `target` as the canonical analytical schema; legacy tables are source adapters.
- Separate contest `format` (`classic`, `showdown`) from optimization `objective` (`cash`, `gpp`).
- Store `as_of`, source, model version, rule version, and run IDs on point-in-time artifacts.
- Use walk-forward validation only for historical performance claims.
- Persist all generated lineups, including showdown and failed/partial runs.
- Human feedback must be structured, versioned, reversible, and expiring when appropriate.
- Run the narrowest relevant tests after each slice; run all Python tests and `npm run build` before handoff.

## Current Baseline

Confirmed on 2026-07-13:

- `target` foundation and target-native learning layers are populated.
- 14,398 target player projection rows exist after the 2025 DST context backfill.
- 1,852,485 DraftKings contest entries have been loaded across 11 slate labels.
- 2,752 ownership rows, 8,800 historical top lineups, and 79,200 lineup-player rows exist.
- Symbolic rules, applications, evaluations, and learning runs exist.
- Classic stacking, a basic captain solver, and historical ownership ingestion exist.
- The advanced GPP service exists but is disabled in the live optimizer path.
- Optimizer runs and lineup contents now persist for classic and showdown modes.
- Active feature, model, projection, symbolic-rule, and optimizer lineage is durable and API-visible.
- New contest imports receive stable source/contest IDs and normalized optional contest and payout metadata.
- The active prediction service excludes target/future rows from training; broader point-in-time feature consistency remains part of Phase 3.
- The UI now has a persisted bulk contest-to-entry assignment and DraftKings upload workflow, presented inside a shared responsive product shell with consistent navigation and active slate context.
- Completed load events and explicit readiness preflights now persist versioned quality runs/checks and render in the Operations `Quality history` panel.
- The default `Digital Twin` cockpit now includes a responsive Thought Studio. Global playbook, contest-profile, season, weekly, game, and player beliefs persist as immutable versions with structured posture, conviction, confidence, evidence, expiration, and replay context.
- The Raw Thought Inbox preserves free-form brain dumps verbatim and runs the versioned deterministic `raw_thought_extractor_v1` policy to propose review-only global, weekly, or player candidates. Every candidate requires one explicit edited acceptance or rejection, and accepted beliefs retain complete source lineage; extraction alone has no projection or lineup impact.
- Guarded `belief_impact_v1` previews persist a player-specific before/after contract for projection distribution, field ownership, available portfolio exposure, and matching DT-502 optimal-lineup probability. Approval/rejection is immutable, approval creates a separate modifier for DT-703, and the base model is never rewritten.
- `digital_twin_variants_v1` freezes three independent artifacts for one salary-scoped slate and exact projection run: unchanged model projections, explicitly approved DT-702 human modifiers as of a declared cutoff, and the deterministic combination. The responsive `Model × Human × Combined` panel compares every changed player and can hash-verify replay from the persisted inputs.
- DST is now a franchise-level modeled entity: all 876 salary rows resolve to 32 identities and games, 13,998 team-game actuals span 2000–2025, exact downloaded DraftKings scores override audited reconstructions, and `dst_context_v1` blends prior defense, opponent-allowed, and Vegas context into calibrated ranges.

Known data-quality warnings:

- 1,010 non-DST legacy salary rows remain unresolved; all are explicitly quarantined as 979 no-match and 31 ambiguous records, and all DST salary rows are resolved.
- 2,182 legacy injury rows lack `player_master_id`.
- 0 target salary rows lack `game_id` after canonical team alias and schedule matching.
- 405 target injury rows lack `game_id`.

## Critical Path

### Phase 0: Trusted Baseline And Data Quality

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-000 | Done | Establish this canonical roadmap and redirect legacy roadmaps to it. | None | One document owns status and priority. | GPT-5.6 Terra High |
| DT-001 | Done | Review and checkpoint the accumulated implementation before cross-cutting changes. Commit `031ac41` captures the reviewed digital-twin foundation and is pushed to `origin/main`. | DT-000 | The worktree baseline is understood; unrelated user changes are preserved. | GPT-5.6 Sol High |
| DT-002 | Done | Added the authoritative `slate_readiness_v1` report and API. Sixteen named checks cover identities, game context, salary/position integrity, injury snapshots, exact projection lineage and coverage, ownership, pre-lock cutoffs, replay actuals, and normalized contest linkage. Separate prediction, classic cash/GPP, showdown cash/GPP, and replay gates expose scores, warnings, and blocking check IDs; the Digital Twin renders the selected gate and `Operations` preflights prediction/optimizer execution. | DT-001 | A slate receives explicit pass/warn/fail results before prediction or optimization. | GPT-5.6 Sol High |
| DT-003 | Done | Canonicalized DST franchises and repaired 876/876 DST salaries; built 13,998 audited component-level DST actuals with exact DraftKings overrides and `dst_context_v1` projections. The non-DST repair then processed all 2,909 unresolved legacy salary rows: 1,899 deterministic matches were repaired and the remaining 1,010 rows were persisted as 979 no-match and 31 ambiguous quarantine records. Week 11 Sunday Main now passes identity readiness at 549/556 (98.74%); all seven exceptions are quarantined, optimizer/replay inputs require canonical IDs, and a fresh classic lineup verified 9/9 canonical players including modeled DST. | DT-002 | Required coverage thresholds are met; quarantined rows cannot enter a lineup silently. | GPT-5.6 Sol High |
| DT-004 | Done | Added versioned `target.data_quality_run` and `target.data_quality_check` persistence. Completed season/week/raw/slate/ownership/batch/feature/starting-QB loads and identity repairs record dataset-level outcomes; explicit projection and optimizer preflights persist the full readiness contract without turning passive dashboard reads into writes. `GET /api/data/quality/history` and the responsive Operations `Quality history` panel expose values, thresholds, status, scope, timestamps, score, and actionable messages. | DT-002 | Every completed load records check name, value, threshold, status, and affected scope; explicit readiness preflights preserve all 16 checks. | GPT-5.6 Terra High |

### Phase 1: Leakage-Safe Replay And Run Contracts

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-101 | Done | Make the active prediction service cutoff-safe. | DT-001 | A week N replay trains only on observations available before week N; regression tests fail if future rows enter training. | GPT-5.6 Sol XHigh |
| DT-102 | Done | Persist feature, model, projection, symbolic, and optimizer run lineage in the target schema. Active prediction and symbolic APIs expose their durable run IDs, and optimizer runs resolve the latest compatible lineage when IDs are not supplied. | DT-101 | Every lineup traces back to immutable run IDs and `data_cutoff_at`. | GPT-5.6 Sol XHigh |
| DT-103 | Done | Replaced the active service's legacy delete-and-rewrite output with append-only target projection versions. Every completed run now persists an immutable manifest and atomically advances one explicit season/week/slate active pointer; exact-run reads and a guarded selection API can restore an earlier version without changing projection rows. The symbolic agent, optimizer, ownership model, digital-twin variants, and readiness checks resolve the same active/exact contract. The `football_26_dev` backfill retained 14,398 projection rows across 37 run IDs and created 37 valid active scope pointers. | DT-102 | Re-running a slate preserves earlier projections and selects an explicit active run. | GPT-5.6 Sol High |
| DT-104 | Done | Split optimizer `format` from `objective`. | DT-102 | APIs and persistence represent classic cash, classic GPP, showdown cash, and showdown GPP independently. | GPT-5.6 Sol High |
| DT-105 | Done | Persist lineups, lineup players, constraints, and failures for every format and reload them after restart. | DT-104 | Results survive application restart; showdown is not excluded. | GPT-5.6 Sol High |
| DT-106 | Done | Added `classic_cash_stack_replay_v2` orchestration through CLI and API. It resolves one exact projection run, proves prior-period training lineage, rejects post-lock cutoffs, hashes salary/projection/actual/field inputs, versions objective and solver configuration, keeps postgame actuals outside optimization, and returns stable replay and artifact hashes for one or many weeks. Two identical live week-11 runs produced identical hashes; the 2025 Sunday Main replay completed all 12 available weeks. | DT-101, DT-105 | Replaying the same cutoff and configuration produces the same artifacts. | GPT-5.6 Sol XHigh |

### Phase 2: Bulk Contest Ingestion And DraftKings Uploads

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-201 | Done | Normalize contest metadata, entry fees, field sizes, payout tiers, entry limits, and source files. New standings imports are content-addressed, preserve multiple contests per slate, and accept validated optional contest/payout metadata. | DT-105 | Imported contests have stable IDs and structured payout information. | GPT-5.6 Sol High |
| DT-202 | Done | Batch-import salary, contest standings, and entry-template files from a directory. Classification is content-based, filename scope inference has request fallbacks, unrelated files are skipped, successful content/scope pairs are deduplicated, and every file receives a durable status report. | DT-201 | Files are deduplicated by hash/contest ID and produce an inspectable import report. | GPT-5.6 Terra High |
| DT-203 | Done | Add persistent portfolio and entry-assignment records. Portfolio creation validates optimizer/template scope, requires a completed optimizer run, assigns one unique lineup per paid entry, rejects missing/duplicate entry IDs and count mismatches, and reloads after restart. | DT-201 | Each paid entry points to exactly one generated lineup and contest. | GPT-5.6 Sol High |
| DT-204 | Done | Generate DraftKings-compatible classic and showdown upload CSVs. Exports preserve all entry-template metadata, restore repeated roster headers, order classic/showdown slots exactly, require DraftKings site IDs, persist content and hash, and expose a download endpoint. | DT-203 | Export preserves site player IDs, roster-slot order, entry count, and contest identifiers. | GPT-5.6 Terra High |
| DT-205 | Done | Add pre-export validation. Every attempt persists a coded validation report; entry count/mapping, DraftKings IDs, roster size/eligibility, repeated players/lineups, positive salary/cap, template slots, and optimizer max exposure are checked before export, and downloads require a passed report. | DT-204 | Invalid salary, eligibility, duplicate, exposure, slot, or entry mappings block export with actionable errors. | GPT-5.6 Sol High |
| DT-206 | Done | Add UI workflow for batch imports, portfolio selection, validation, and download. The responsive Contest Delivery workspace guides a safe dry-run/import, exposes per-file artifacts, accepts or inherits optimizer/template IDs, creates assignments, renders coded blockers, gates export, previews CSV, and downloads the persisted artifact. | DT-202, DT-205 | A user can generate and download a valid multi-entry upload without manual row editing. | GPT-5.6 Terra High |

### Phase 3: Projection And Ownership Modeling

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-301 | Done | Replace the active single-model/constant-sigma output with position- and role-aware calibrated distributions. The active v2 path builds strictly chronological out-of-fold residuals, derives workload roles only from lagged usage, fits monotonic P10/P25/P50/P75/P90 quantiles hierarchically by position and role, shrinks sparse roles to position parents and positions to a global fallback, persists diagnostics and explicit promotion checks with model lineage, and exposes coverage/MAE in the API and Model Workbench. | DT-101, DT-102 | Walk-forward P10/P25/P50/P75/P90 coverage is measured by position and role. | GPT-5.6 Sol XHigh |
| DT-302 | Partial | DST now uses `dst_context_v1`: eight-game defense and opponent-allowed component rates, market-implied opponent scoring, regressed event scoring, empirical ceiling probability, and calibrated P10/P25/P75/P90 ranges. The 2025 diagnostic lowers MAE 7.2% versus the prior rolling average with 79.1% P10–P90 and 53.2% P25–P75 coverage; this is diagnostic, not a promotion-grade untouched holdout. QB/RB/WR/TE opportunity-efficiency decomposition and formal DST ablations remain. | DT-301 | Ablations show which role and efficiency features improve out-of-sample results. | GPT-5.6 Sol XHigh |
| DT-303 | Done | Replace prior-contest player averages with the `slate_aware_ownership_v1` challenger. It uses salary/projection ranks, value, slate size, contest format, roster slot, and strictly lagged player/slot/format ownership; evaluates strict earlier-week folds against the prior-player baseline; reports MAE, rank correlation, and classic/showdown slot calibration; persists run/cutoff/feature lineage; and exposes its diagnostic promotion gate in Operations and the Digital Twin cockpit. | DT-201, DT-301 | Ownership is evaluated by MAE, rank correlation, and calibration by format/slot. | GPT-5.6 Sol XHigh |
| DT-304 | Backlog | Add point-in-time Vegas, props, weather, depth chart, and role snapshots. | DT-002 | Historical replay uses only snapshots available before lock. | GPT-5.6 Sol High |
| DT-305 | Backlog | Add model registry, champion/challenger evaluation, and promotion rules. | DT-301, DT-303 | A new model cannot become active without beating its baseline on declared walk-forward gates. | GPT-5.6 Sol XHigh |

### Phase 4: Classic Cash Engine

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-401 | Done | Define `classic_cash_v1`: 25% mean, 35% median, 40% calibrated P10 floor, a bounded role-certainty bonus, and a normalized downside-fragility penalty. Projection-only rows preserve the old score; the exact config, player terms, lineup summary, and target-schema explanation are persisted and returned. The optimizer also resolves active `curated_salary` plus target projections when legacy plural views are absent. | DT-301 | Objective terms are versioned and explainable per lineup. | GPT-5.6 Sol XHigh |
| DT-402 | Partial | Added versioned classic cash policies for an unconstrained baseline, QB plus pass catcher, and QB plus pass catcher with bring-back; wired the selector into `Operations`; persisted the exact policy; and ran all three through deterministic replay across 12 available 2025 Sunday Main slates. Complete actuals and six normalized full-field comparisons are now available. Bring-back improved mean margin versus the field median by 3.10 points over unconstrained and QB pairing by 0.864, but no policy is promoted because historical salary availability is not proven pre-lock and the source files do not establish cash contest type or payouts. | DT-106, DT-401 | Walk-forward replay compares each rule against the unconstrained baseline using proven point-in-time inputs, complete lineup actuals, and normalized cash-line or defensible field-proxy outcomes. | GPT-5.6 Sol High |
| DT-403 | Partial | Normalized field evidence now reports exact field median, quartiles, winner, percentile, and lineup margin. Policy aggregates include win/double-up rates, explicit cash-line ties, worst/P10/P25/median margins, lower-quartile mean, and below-median rate; exact or ranged ROI never fabricates missing payouts. Operations now exposes a guarded `Contest evidence` editor for explicit type, fees, field size, entry limits, prize pool, and non-overlapping payout tiers. Six Sunday Main fields show no dominant policy: bring-back improves median margin but worsens lower-quartile mean by 4.19 points, while QB pairing produces the only above-median result but worsens lower-quartile mean by 2.0. Real historical cash files with verified metadata remain. | DT-201, DT-401 | Reports include win rate, double-up rate, median margin, and downside distribution. | GPT-5.6 Sol XHigh |
| DT-404 | Backlog | Build cash portfolio diversification and late-news replacement rules. | DT-403 | Multiple cash lineups remain legal and controlled when a player becomes unavailable. | GPT-5.6 Sol High |

### Phase 5: Classic GPP Engine

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-501 | Partial | Wire the advanced GPP path into the live optimizer behind an explicit strategy flag. | DT-104, DT-105 | The selected strategy is executed, validated, persisted, and visible in results. | GPT-5.6 Sol High |
| DT-502 | Done | Added immutable `independent_quantile_lineup_v1` classic simulations. Exact calibrated projection marginals are sampled with a persisted seed, every draw solves a legal DK roster, and player optimal-lineup probability is stored with projection/ownership lineage. War Room and classic GPP consume optimal % minus ownership % in percentage points; missing runs stay unavailable. Belief impacts replay the same draws after changing only the selected distribution. The versioned replay gate passed on three ownership-complete 2025 Sunday Main weeks: top-20 historical top-lineup exposure improved from 3.25 to 7.17 (+3.92), while weaker global rank correlation remains visible. | DT-301, DT-303 | Leverage has consistent units and improves top-percentile replay results. | GPT-5.6 Sol XHigh |
| DT-503 | Backlog | Add joint game/player simulations with shared latent game states and correlations. | DT-301, DT-304 | Simulated marginal distributions remain calibrated and observed correlations are reproduced. | GPT-5.6 Sol Max |
| DT-504 | Backlog | Sample realistic opponent fields from ownership and construction behavior. | DT-303, DT-503 | Simulated fields match historical ownership, stacks, salary usage, and duplication patterns. | GPT-5.6 Sol XHigh |
| DT-505 | Backlog | Optimize expected payout/top-percentile probability rather than summed player P90. | DT-201, DT-503, DT-504 | Historical reports include top 1%, top 0.1%, cash rate, payout, ROI, and uncertainty intervals. | GPT-5.6 Sol Max |
| DT-506 | Backlog | Add contest-aware portfolio exposure, diversification, and entry assignment. | DT-203, DT-505 | Portfolios respect risk limits and vary by field size, payout structure, and entry count. | GPT-5.6 Sol XHigh |

### Phase 6: Showdown Cash And GPP Engines

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-601 | Partial | Move the basic captain solver into the persistent format/objective architecture. | DT-104, DT-105 | Showdown cash and GPP runs are distinct, persisted, and reloadable. | GPT-5.6 Sol High |
| DT-602 | Backlog | Build captain- and flex-specific ownership models. | DT-303, DT-601 | Ownership calibration is reported separately for CPT and FLEX. | GPT-5.6 Sol XHigh |
| DT-603 | Backlog | Add showdown game-script simulations and construction features. | DT-503, DT-601 | Simulations cover 5-1/4-2/3-3 structures, role changes, kickers/DST, and scoring scripts. | GPT-5.6 Sol Max |
| DT-604 | Backlog | Estimate lineup duplication and prize splitting. | DT-504, DT-602, DT-603 | Expected payout accounts for duplicated lineup counts and split prizes. | GPT-5.6 Sol XHigh |
| DT-605 | Backlog | Optimize showdown cash stability and GPP expected payout separately. | DT-603, DT-604 | Both engines beat simple P90 maximization on declared replay metrics. | GPT-5.6 Sol Max |

### Phase 7: Human Digital Twin

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-701 | Done | Add versioned global playbook, contest-profile, season, weekly, game, and player belief records plus the Digital Twin Thought Studio. Create, revise, deactivate, and restore operations append immutable versions; original wording, subject, direction, strength, confidence, evidence, expiration, retrospective context, and non-operative impact status remain auditable. | DT-102 | Beliefs store scope, direction, strength, confidence, reason, evidence, and expiration. | GPT-5.6 Sol XHigh |
| DT-702 | Done | Added guarded, persisted `belief_impact_v1` previews and explicit approval/rejection. The Thought Studio selects a projected player, shows projection floor/mean/ceiling, field ownership, available portfolio exposure, matching DT-502 optimal probability, complete lineage/safety notices, and never mutates the base model. Approval stores only the exact modifier for DT-703. | DT-701 | UI shows before/after projections, ownership, exposure, and simulation-backed optimal probability when DT-502 exists; unavailable lineage is explicit and never fabricated. | GPT-5.6 Sol High |
| DT-707 | Done | Added the Raw Thought Inbox for free-form general, slate, and player brain dumps. It preserves original text, runs versioned deterministic draft extraction with projected-player matching and weekly fallback, and presents every candidate for editing plus one immutable acceptance or rejection. Accepted candidates become ordinary non-operative beliefs with full capture lineage; raw text and drafts never affect the model directly. | DT-701 | Original text is durable; proposed scope and calibration are inspectable; every candidate has an explicit decision; accepted beliefs trace to their source; extraction cannot silently affect a projection or lineup. | GPT-5.6 Sol High |
| DT-703 | Done | Added immutable `digital_twin_variants_v1` sets with separate model-only, human-only, and combined JSON artifacts. Creation uses one exact salary-scoped projection run, consumes only approved DT-702 modifiers with matching projection lineage before the decision cutoff, composes multiple player modifiers deterministically, and stores a SHA-256 identity for each artifact. Create/list/replay APIs and the responsive `Model × Human × Combined` panel expose changed-player comparisons and verify all three artifacts from persisted inputs without mutating the base model. | DT-701, DT-105 | All three variants can be replayed and compared after the slate. | GPT-5.6 Sol XHigh |
| DT-704 | Backlog | Add targeted agent questions for high-value uncertainty and disagreement. | DT-703 | Questions are triggered by defined value-of-information rules and every answer is recorded. | GPT-5.6 Sol XHigh |
| DT-705 | Backlog | Score human beliefs and accepted/rejected/no-change answers after outcomes. | DT-703 | Reports show when human intervention helped, hurt, or had no measurable effect. | GPT-5.6 Sol XHigh |
| DT-706 | Backlog | Learn a guarded personal-policy model from accumulated feedback. | DT-705 | Recommendations require minimum evidence and never silently change active rules. | GPT-5.6 Sol Max |

### Phase 8: Weekly Automation And Post-Slate Learning

| ID | Status | Work | Dependencies | Acceptance check | Recommended model |
| --- | --- | --- | --- | --- | --- |
| DT-801 | Backlog | Add a weekly run orchestrator with resumable stages and health checks. | DT-106, DT-205 | Ingest, predict, adjust, simulate, optimize, validate, and export stages are individually inspectable. | GPT-5.6 Sol High |
| DT-802 | Backlog | Add lock-aware news, injury, ownership, and lineup refreshes. | DT-304, DT-801 | Updates produce new versioned runs and never mutate a locked historical snapshot. | GPT-5.6 Sol XHigh |
| DT-803 | Backlog | Load contest results and evaluate projections, rules, beliefs, lineups, and portfolios. | DT-201, DT-703, DT-801 | Every completed slate produces an auditable learning report. | GPT-5.6 Sol XHigh |
| DT-804 | Backlog | Add monitoring for data staleness, drift, calibration, failures, and export readiness. | DT-801, DT-803 | Alerts identify actionable failures before lock and model drift after results. | GPT-5.6 Terra High |

## Required Validation Matrix

Before a phase is considered complete, the relevant checks must include:

- unit tests for calculations and constraints;
- database integration tests for lineage and persistence;
- deterministic replay tests with explicit cutoffs;
- classic cash end-to-end generation;
- classic GPP end-to-end generation;
- showdown cash end-to-end generation;
- showdown GPP end-to-end generation;
- DraftKings CSV fixture validation;
- walk-forward metrics compared with a transparent baseline;
- negative tests for missing IDs, stale data, illegal lineups, and invalid entry assignments.

## Immediate Execution Order

1. Add DT-704 value-of-information questions using the replayable DT-703 disagreement artifacts as input; continue gathering `DT-402`/`DT-403` provenance when authoritative source evidence becomes available.
2. Add DT-503 joint game/player states and correlation on top of the independent DT-502 marginals.

## Definition Of Done

The program reaches its intended end state when a user can import multiple
contests, capture a weekly thesis, generate separately optimized classic/showdown
cash/GPP portfolios, inspect why each lineup exists, download validated DraftKings
upload files, and later measure whether the base model, symbolic rules, and human
judgment each improved real contest outcomes.
