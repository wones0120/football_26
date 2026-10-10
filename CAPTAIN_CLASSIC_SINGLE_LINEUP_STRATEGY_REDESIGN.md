# Captain and Classic single-lineup strategy redesign

Historical design: the normal defaults were restored to GPP on October 9, 2026.
Operations and weekly requests now use `classic_large_gpp_v1` or
`showdown_gpp_portfolio_v3`, with five lineups by default. The Cash strategies
described below remain for explicit requests and historical reports; they are
not the current normal optimizer defaults. See README and
`artifacts/gpp_default_verification/` for the current workflow and validation.

Implemented October 9, 2026. The normal workflow is **Choose Captain or Classic → Prepare verified slate data → Run Optimizer → Receive the primary cash-oriented lineup and any explicitly requested additional lineups**. Lineup and player controls remain available; only strategy variants are consolidated.

## Active strategies and migration

| Format | Active strategy | Default / requested output count | Objective status |
| --- | --- | ---: | --- |
| Captain / Showdown | `captain_single_lineup_v1` | 1 / configurable 1–50 | Transparent, unvalidated cash-oriented proxy |
| Classic | `classic_single_lineup_v1` | 1 / configurable 1–50 | Transparent, unvalidated cash-oriented proxy |

A readiness-blocked run produces no lineups. An underfilled request saves partial diagnostics, is marked failed and cannot export a complete verified CSV. Both retain their blockers. It never relaxes readiness to manufacture a lineup.

The audit found Classic Head-to-Head, Large GPP, Small Field GPP, generic/baseline GPP and Showdown baseline cash/GPP, Captain-informed portfolio, single-entry, multiple-contest, 3-max and small-max policies. Operations previously exposed contest objectives, strategy variants, lineup counts, exposure, overlap, portfolio concentration and scenario diversity. Both the standalone run and weekly pipeline submitted those controls. Classic live source preparation was specifically routed through Large GPP. Saved history filtered by cash/GPP, hiding older runs when the objective changed. AI packets assumed 2–5 entries.

The two new IDs have a separate selection engine, `cash_oriented_single_lineup_selector`. They are not aliases for `showdown_gpp_portfolio_v3` or `classic_large_gpp_v1`. All existing IDs, explicit legacy API requests, saved reports, candidate archives, research routes and immutable decisions remain readable with their original objectives. Resolved explicit strategies identify their lifecycle as active or historical research. No database migration, historical row rewrite, dependency addition or source-file replacement is required; the new reports use existing JSON persistence. The Classic source contracts retain their historical `classic_large_gpp_*` IDs for compatible frozen-evidence validation; those IDs describe source readiness, not the new selection objective.

## Intended paid-position objective

The desired decision is the legal lineup with the highest probability of finishing in paid positions for the supplied contest. A defensible future estimator needs verified contest/slate identity, field size and complete payout ladder, a supported opponent-lineup model, shared correlated player outcomes for the candidate and field, and out-of-sample validation of the resulting paid-score threshold. Estimate paid finishes over joint draws with official tie/payout handling, rather than first-place probability, uniform finishing ranks or portfolio expected value.

Those conditions are **not currently met**. Production simulation uses independent player draws. The separate joint simulation research module has structural correlation assumptions but no supported contest-field model or calibrated paid-cutoff estimator. Marginal projected ownership cannot establish an opponent lineup distribution. Consequently both strategies always save `cash_probability: null` and display **Cash probability unavailable**. Neither observed paid places nor a payout ladder is translated into an invented fantasy-point cutoff.

## Implemented cash-oriented proxy

Policy: `cash_oriented_selection_proxy_v1`. Fixed preferences were defined before the historical comparison; no Week 4–5 outcomes were used to set or tune them.

For each lineup, let:

- **M** be the sum of unchanged, slot-adjusted expected fantasy points.
- **D** be `1.2815515655 × sqrt(assumed correlated lineup variance)`.
- **A** be the sum of nonnegative player means multiplied by sourced availability uncertainty, `1 − availability`. Missing/invalid availability receives an explicitly disclosed 10% mean uncertainty penalty.
- **C** be the sum of nonnegative player means multiplied by `1 − slot ownership / 100`, only when fresh, eligible ownership evidence supports every candidate slot. Otherwise the competition term is disabled and disclosed.

Selection score:

```text
M − 0.45 × D + 0.10 × min(D, 0.25 × max(M, 0)) − A − 0.05 × C
```

Report downside is `M − D`; upside is `M + D`. These are **unvalidated normal-spread diagnostics**, not calibrated lineup P10/P90. Upside credit is capped, so extreme summed player ceilings do not dominate selection. The weak popularity penalty represents potential risk of falling behind commonly held players; it is not a measured opponent-field advantage. The availability term expresses additional risk aversion and never rewrites projections or injury truth.

Player spread uses finite, ordered marginal P10/mean/P90, with `sigma = (P90 − P10) / (2 × 1.2815515655)`. Missing or invalid quantiles use the disclosed fallback `max(3 × slot multiplier, 0.60 × abs(slot mean))`. Captain means/P90 and salaries arrive already multiplied by 1.5; retained base P10 is multiplied exactly once.

A positive-semidefinite factor model aggregates game loading 0.25, team offense 0.35, and team passing 0.35 for QB/WR/TE. DST has −0.35 loading on opposing offense. Residual variance completes each player's variance. Shared factors affect spread, not expected points. These are structural assumptions, not learned correlations. The symmetric spread approximation omits distribution skew, discrete touchdowns, nonlinear injury mixtures and many football interactions.

Tests demonstrate that the selector can reject both the highest-mean and highest summed-P90 candidate. Canonical roster signatures resolve score ties deterministically. No lineup overlap, exposure target, multi-entry expected value or portfolio diversification contributes to the selected score.

## Candidate discovery and selection

Existing legal ILP construction is retained. Discovery targets 60 unique Captain candidates and 120 Classic candidates, or fewer if constraints exhaust the feasible pool. It explores balanced marginal utility, mean, floor and capped-upside scoring views, with Captain-family or quarterback-family seeds. Legacy GPP value/ceiling shortlist pruning does not restrict the new Captain or Classic discovery pool. Existing starter, role/opportunity, legal salary, team, position and explicit player constraints still apply.

Discovery deduplicates roster signatures to find distinct alternatives; it imposes no final portfolio overlap or exposure objective. Existing soft rule scoring can inform discovery, but the independent final proxy ranks the whole generated pool. The result is the best **generated** candidate; this does not certify a global optimum of the nonlinear correlated proxy. The unnecessary Classic control replay is skipped when discovery explicitly disables it; historical callers retaining control comparisons keep that behavior.

`single_lineup.py` owns normalization, discovery, diagnostics, selection and contest provenance. `optimizer.py` wires the distinct engine into the source gates, freezes the new objective configuration before solving, independently validates the final roster and saves the full candidate manifest and decision snapshot. Public requests default to `num_lineups=1` and 100% exposure, preserve explicit user counts from 1–50 and hard lineup controls, and retain exclusion-as-preference semantics. Legacy portfolio objective weights and scenario-diversification rewards remain research only and are recorded as ignored. Long-shot requests are rejected for the active strategies. Explicit legacy requests remain available for research.

## Restored controls after user clarification

The user clarified that the simplification concerns strategy variants, while lineup counts and player controls should remain available. The two IDs remain unchanged. **One is the default and there is always at most one primary recommendation; explicitly requested additional lineups are supported.** This supersedes the initial restriction to exactly one returned roster per run. Existing ranking weights were not changed or tuned.

Restored controls:

- **Number of lineups:** 1–50 for either format. Shared player exposure and optional overlap limits apply across these outputs.
- **Classic:** maximum players per team (default 4) and per game (restored default 5), optional maximum lineups per primary QB game, overlap and elevated-risk limits. Opposite QB directions share one canonical game.
- **Captain:** CPT/core/starting-QB/cheap-punt exposure settings (defaults 100%). Core applies to players outside verified starting QB and base-salary ≤ $1,000 punt groups. Captain position, maximum players per team (default 5), No QB Captain, No 2 QBs and No QBs remain available.
- Existing locks, exclusions, FLEX-only players, Questionable exclusion, availability assumptions, single-TE and offense-against-DST controls remain available.

Settings persist separately by format; existing saved Classic volume, overlap and risk preferences migrate. Both direct and weekly runs submit the same validated controls. Locks require inclusion in every output and bypass ordinary player caps, matching historical behavior; explicit canonical per-player caps and elevated-risk caps still apply and can conflict with a lock. Ordinary exposure limits round up to appearances, while explicit elevated-risk caps round down; both use the requested count. Risk classification reuses existing cutoff-safe availability evidence; it does not alter model projections.

Selection first finds the maximum feasible count within the generated pool, bounded by the request. It then walks the individual cash ranks and keeps each highest-ranked candidate that can coexist with that feasible count and all prior selections. This preserves the best compatible primary recommendation without greedy underfill. **No summed portfolio utility, diversification reward, first-place objective or portfolio expected value is introduced.** A top-ranked candidate may be rejected when it prevents the requested count under explicit limits; the saved report explains this.

Limits are never relaxed. Infeasible requests save an explicit failed/underfilled result with achieved count and settings; partial results cannot be exported as a complete verified CSV. Selection has a 30-second total feasibility budget and fails explicitly if it cannot certify the result. Candidate discovery grows to at least six times the requested count, with the original 60 Captain/120 Classic minimums. Search remains finite and does not prove full-slate feasibility under tight limits.

The primary report records requested/selected counts and the saved constraint selection. Additional requested rosters are labelled separately. Captain AI packets still review exactly the primary roster. Historical strategies, reports and their objectives remain intact.

## Contest evidence

The optional input accepts one native DraftKings contest URL. Server parsing records payout tiers, paid places, capacity, current entries, source timestamp and source hash when available; client claims of verification are not trusted. A mismatched native draft group is rejected when frozen salary-group identity is available. Missing native group identity, unavailable facts or incomplete payout tiers prevent a claim that the contest is verified for the slate.

Even verified payout facts currently leave selection on the identified **generic cash-oriented proxy**, because the field model is unsupported. The report states this explicitly. No manually supplied payout, unsupported field size, equal-rank payout expectation or cash percentage silently affects selection.

## UI and preserved safeguards

Operations has one Strategy dropdown containing Captain / Showdown and Classic. It removes normal Large/Small GPP, Single/Multi-Entry strategy variants, diversity rewards and long-shot objectives. **Lineup options** restores lineup count, exposure, overlap, team/game concentration and elevated-risk controls under either strategy. The weekly pipeline uses the same parameter builder; omitted weekly strategy defaults select the active format strategy. Historical projection overrides are excluded from the normal verified-rebuild path.

The result leads with one roster, expected points, downside/upside diagnostics, unavailable cash probability, risk factors, the selection explanation and notable rejection reasons. Additional requested outputs appear below as **Additional requested lineup** cards. Unselected complete rosters and objective contributions remain in a closed **Candidate diagnostics / research** panel, with the same content in the downloadable readable report. Saved history includes both objectives and retains original strategy labels. Recovery checks format and slate scope so an older saved run cannot undo a new strategy choice.

Preserved:

- Canonical player identity and native salary verification; immutable raw evidence and source hashes.
- Current injury/availability, starter, role/opportunity, projection dependency, market and ownership lineage checks.
- Pre-generation evidence freezing, readiness blockers, durable queue status, retries and saved failure reports.
- Legal DraftKings rosters, Captain multiplier/identity handling, existing locks and exclusions, and independent final validation.
- User preference reasons and model assessments for excluded players. Exclusions do not become Assume Out. Explicit availability assumptions remain separate scenario controls.
- Showdown prelock checklist, AI packet export and all historical AI pair-review/immutable decision APIs. Active Captain packets request exactly one entry and carry the new proxy policy; historical finalist quality/pair similarity displays remain research only. Historical two-entry AI review stays under historical controls.
- Candidate manifests, effectiveness extraction, historical learning and audit artifacts. Runtime code fingerprints include the selector module.

Active lineup CSV export additionally requires the complete requested count and checksum-verified frozen READY evidence belonging to that run. Generation READY is distinct from current game-day clearance, contest assignment or submission verification. Classic explicitly reports entry clearance pending; generation does not claim that a lineup has been entered.

## Frozen historical comparison

Reproduce with:

```bash
.venv/bin/python scripts/compare_single_lineup_frozen.py
```

Output: [`artifacts/single_lineup_redesign/frozen_comparison.json`](artifacts/single_lineup_redesign/frozen_comparison.json), including input SHA256s, policy-code hash, canonical rosters, per-candidate contributions, projection run IDs and explicit limitations. The script performs no database writes, source refreshes or outcome reads.

| Frozen case | Selection | Expected | Downside diagnostic | Upside diagnostic | Proxy score |
| --- | --- | ---: | ---: | ---: | ---: |
| 2026 W3 Classic, `classic_small_field_gpp` | Old rank 1 | 135.96 | 94.56 | 177.36 | 120.73 |
| Same archived 120 Classic candidates | New single selector | 141.81 | 101.53 | 182.10 | 127.23 |
| Same frozen Classic audit; new 120-candidate discovery | New recommendation | 142.66 | 102.14 | 183.17 | 127.99 |
| 2026 W3 Monday Captain, `showdown_gpp_portfolio_v3` | Old recommendation 1 | 72.08 | 39.75 | 104.40 | 59.33 |
| Same five saved Captain recommendations | New single selector | 72.05 | 41.82 | 102.28 | 60.25 |
| Same frozen Captain audit; new 60-candidate discovery | New recommendation | 74.22 | 44.53 | 103.92 | 62.72 |

The old strategies requested five recommendations; this comparison uses the new strategies’ one-lineup default. Explicit requests can now return additional ranked lineups under user limits. All proxy columns above, including old controls, are recomputed using the new policy; original GPP objective scores have different units. Both new discoveries returned exactly one independently validated legal roster. Classic source reconstruction exactly matches every archived candidate's mean and summed P90. Captain reconstruction exactly matches all five old recommendation means with slot multipliers.

**Exploratory limitations:** the saved audits lack marginal P10, so all compared rosters use the same documented fallback. Historical ownership support at the cutoff is not established, so its term is disabled. The full original Captain discovery universe is unavailable; its same-pool comparison is limited to five saved recommendations. The Classic input artifact is explicitly a reconstruction archive. Captain generation timestamps and missing historical evidence do not establish a complete prelock readiness replay. This compares projected ranking behavior, not realized cash rates, payout performance or probability calibration. No Week 4–5 outcomes are consumed or tuned against. Existing chronology tests may use frozen pregame reference fixtures; they do not fit these weights.

## Validation results

- **304 backend tests passed**. Targeted checks cover new ranking and normalization, correlated risk, Captain multiplier, missing evidence, deterministic manifests, real legal ILP discovery, final roster validation, successful freeze-before-solve flows, both source gates blocking before solve, historical history scope, AI/prelock exports, DraftKings export and weekly orchestration.
- **129 UI tests passed**. UI checks cover active strategy IDs, escaped single recommendations, closed research views, updated run-path contracts and historical report helpers; TypeScript and production Vite build pass. The existing Vite bundle-size advisory remains.
- Actual compiled App inspected through an isolated local API fixture at desktop and mobile widths. The browser verifies the two choices, one-lineup defaults and explicit multiple-lineup requests, disabled controls, settings reload, desktop/mobile form layout, historical reopen behavior and reports. Fixture results are synthetic, not live slate recommendations. Captured requests preserve exclusions and use the new cash strategy IDs with requested count and user controls. The restored-controls browser fixture returned three Classic and two Captain outputs, each with one primary recommendation.
- The running local UI also shows the restored controls, including the existing saved Classic 20-lineup/80% exposure preferences. API and worker were reloaded after confirming no running jobs; health and the current API contract were verified. No live optimizer run was triggered.
- `git diff --check` passes. Existing unrelated workspace changes were retained. No live contest entry or source-history rewrite was performed.

Original validation is recorded in [`validation.json`](artifacts/single_lineup_redesign/validation.json). Restored-control checks, captured requests and current asset hashes are recorded in [`controls_restored/validation.json`](artifacts/single_lineup_redesign/controls_restored/validation.json). Screenshots show synthetic fixture results: [desktop](artifacts/single_lineup_redesign/ui-desktop.jpg), [mobile](artifacts/single_lineup_redesign/ui-mobile.jpg).

## Normal run instructions

1. Start PostgreSQL and the repository API and durable worker using the existing setup. After updating code, reload/restart both API and worker; restart scripts are documented in README Quick Start. Start the UI with `cd ui` then `npm run dev` (or serve the built bundle).
2. In Operations, select season/week/slate and choose **Captain / Showdown** or **Classic**.
3. Load the correct native DraftKings salary CSV and availability/injury evidence. Resolve canonical identity issues. Use **Prepare slate inputs** in Preparation and data tools when repair is needed; inspect source blockers. Run Optimizer also refreshes, rebuilds, verifies and freezes its required inputs.
4. Under **Optimizer options → Lineup options**, keep the default one lineup or request 1–50. Set optional exposure/overlap, team/game and risk limits. Set exclusions/locks, explicit availability assumptions and legal construction preferences. Optionally supply one contest URL. Review the displayed preference summary.
5. Click **Run Optimizer**. A source gate failure saves a blocked run; repair the stated sources and initiate a new run. Do not use an incomplete-evidence preview for entry.
6. Review the primary recommendation, any additional requested lineups, uncertainty/risk, saved limits, notable alternatives and contest limitations. An underfilled request is marked failed; inspect the explanation and start a new run with revised settings if needed. Open candidate research only if needed. For Captain, use the saved run's prelock checklist/one-entry AI packet. Confirm current game-day availability and entry clearance separately.
7. Download the lineup or readable report. Old runs remain accessible in Recent optimizer runs with their original strategies and counts.

## Remaining modeling work

Build and prospectively validate a contest-field generator, point-in-time joint player distributions, paid-cutoff/tie handling and cash-probability calibration before enabling percentages. Validate downside/availability/popularity preferences on independently chosen historical periods and prospective slates; keep Week 4–5 outcomes outside weight tuning. Improve skew/injury mixture modeling and candidate-search coverage. These are modeling follow-ups, not claims supported by the current proxy comparison.
