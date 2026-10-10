# Classic Large-GPP UI portfolio controls

The completed [app/Codex parity report](CLASSIC_LARGE_GPP_APP_CODEX_PARITY_AND_GAME_CAP.md) remains authoritative. The immutable reference is `d0e2ff8f-96cd-4fc0-ac7e-8297d4504701`; its evidence archive and original reports were not rewritten. This task adds optional production controls and deterministic verification. It does not select or recommend a new Week 4 portfolio.

## Application controls

The Operations optimizer now uses the full width. Its compact status row explains
that **Run Optimizer** rebuilds projections automatically and provides **Open Model**
for manual projections; **Run Simulation** remains available for Classic slates.

Open **Operations → Portfolio optimizer → Contest Strategy: Large GPP → Portfolio diversification**. Choose the settings yourself, then press **Run Optimizer**. Number of lineups and Max player exposure now sit alongside the optional diversification controls. Their existing new-session defaults remain 20 and 60%; the frozen reference's five entries/80% remain test inputs, not promoted defaults.

| UI label | Options | Default | Request key / accepted range |
|---|---|---|---|
| Number of lineups | Existing numeric control | Existing 20 | `num_lineups` |
| Max player exposure (%) | Existing numeric control | Existing 60% | `max_exposure`, UI percent → rate |
| Max lineups per primary game | No limit / 4 / 3 / 2 / Custom | No limit | `max_lineups_per_primary_game`, positive integer |
| Max shared players between lineups | Strategy default / 7 / 6 / 5 / 4 / Custom | Strategy default | `max_lineup_overlap`, integer 0–8 |
| Max exposure per elevated-risk player | Strategy default / 80% / 60% / 40% / 20% / Custom | Strategy default | `elevated_player_max_exposure`, rate 0–1 |
| Advanced: Max elevated-risk players per lineup | Strategy default / 0 / 1 / 2 / Custom | Strategy default | `max_elevated_players_per_lineup`, integer 0–9 |

Overlap and elevated-risk settings are independent: overlap 5 can be used with per-lineup elevated-risk Strategy default. The collapsed Advanced row displays the separate risk label and current value; expand it to change that dropdown.

Selecting a default omits the new optional field. Null values also mean no optional override. The Large-GPP overlap default remains seven shared players (two-player minimum uniqueness). An explicit overlap overrides the legacy minimum-uniqueness setting. The duplicate legacy uniqueness input is hidden for Large GPP; Small Field retains its separate controls. No minimum-distinct-games control was added.

JAX–CIN and CIN–JAX share the same canonical uppercase, sorted team-pair game budget. This is a selected-portfolio QB-stack constraint. Max players / game remains a separate per-lineup control. Pairwise overlap counts canonical player IDs, so FLEX or roster-slot placement changes cannot bypass it.

## Elevated-risk semantics

The application runs the existing cutoff-safe availability classifier on its eligible solver frame and saves each assessment. Only existing `questionable_elevated` classifications receive the optional caps. Missing injury evidence remains normal; `questionable_full_role`, doubtful and out classifications are not recategorized by these controls. Existing hard availability/eligibility behavior remains authoritative. Projections, P90, football context, weights, ownership and model assessment are preserved.

An explicit elevated-player rate uses **floor(requested entries × rate)**, the product's explicit per-player appearance-limit convention. It intersects stricter individual and global limits. For five entries: 80% → 4, 60% → 3, 40% → 2, 20% → 1; 50% → 2, 19% → 0. Zero is an intentional optional exclusion from selection and retains the model assessment with a user-preference reason. Decimal multiplication protects the new control's mathematical floor at boundaries such as 50 × 58% = 29. The global cap retains its existing **ceil** convention and existing lock/minimum semantics.

A lock/minimum that exceeds an explicit elevated cap is a conflict, not permission to raise that cap. The Advanced per-lineup cap independently limits the count of elevated players inside each nine-player lineup. Both risk controls default to Strategy default, which imports none of Small Field's conservative risk policy.

## Shared execution and persistence

Both **Run Optimizer** and the weekly-run request path serialize the same explicit values. Invalid controls are checked before UI reconciliation/projection side effects and by the optimizer request/service validation. Large-only risk and overlap fields are rejected for other strategies; Small Field continues using its own `portfolio_constraints` and availability policy.

The execution path is:

`UI → requested params → classic_large_gpp_effective_strategy_v1 → resolved config + classified canonical IDs → shared production solver → independent portfolio audit → persisted optimizer JSON → results API → screen + downloaded HTML report`

Production and PARITY use the same builder/executor. RESEARCH_SHADOW retains its explicit mode/deviation guards. Sequential production generation and scoring remain unchanged. New contract fingerprints include the optional-control and classification implementations; old archives retain their original fingerprints and drift protection. The automated baseline test builds a current-code PARITY contract from the original immutable fixture and proves numerical/roster equivalence; it does not overwrite old contracts or disable their drift guard.

Optional choices, lineup count and global exposure survive a browser reload. Large-GPP volume and optional controls are stored separately from Small-field policy choices; switching back restores the saved Large-GPP volume. Primary-game choice retains its existing Classic storage key and canonical semantics.

Each new saved Large-GPP report includes a compact table:

| Setting | Requested | Effective | Source | Achieved |
|---|---|---|---|---|
| Entry count | Saved request | Requested entry count | Request/default | Selected count |
| Max player exposure | Saved rate | Executed global rate | Request/default | Max appearances / requested entries and global appearance limit |
| Max primary-game appearances | Value or No limit | Executed value or No limit | Request/default | Independently counted canonical game counts |
| Max lineup overlap | Value or Strategy default | Explicit value or existing overlap | Request/default/legacy uniqueness request | Independently counted maximum shared canonical IDs |
| Elevated-player max exposure | Rate or Strategy default | Explicit rate or existing player/global caps | Request/default | Max elevated appearances / requested entries; category limit; stricter caps also apply |
| Per-lineup elevated max | Value or Strategy default | Explicit value or no additional cap | Request/default | Independently counted maximum elevated players per lineup |

The full saved contract retains ordered model inputs and classifications. The audit additionally retains each elevated player's effective appearance limit, user-preference reason, overlap matrix, per-lineup elevated counts and validation violations. API fields are `effective_strategy_contract`, `primary_game_constraint`, and `portfolio_controls_report`. Persistence uses existing optimizer JSON, so no database migration or environment key is required.

## Feasibility and recovering failures

An underfilled sequential solve is **failed**, never a completed five-entry portfolio. No game, overlap, player or risk cap is automatically loosened. The report shows active constraints, saturated game/player budgets, overlap pairs at the limit and failed solver steps. These identify exhausted budgets and the combination under which the next solve failed; they do not claim a proven minimal infeasible set or that a joint solver could never find a portfolio.

**Recent optimizer runs → Open results** now also opens persisted failed/underfilled reports. Refresh and watching a run restore those diagnostics. An unsaved failure has no Open results action. Retrying clears the old displayed report while the queue runs, so a later saved result with the same run ID can load correctly. Existing reports predating this feature remain readable and are not retrospectively relabeled as enforcing new controls.

## Verification

- **196 backend tests passed** across deterministic controls, contract/API, queue/recovery, existing Large/Small-field scoring/policy and strategies. Coverage includes defaults, game 4/3/2, opposite directions, overlap 7/6/5/4, exposure conversions and decimal floor, stricter individual limits, per-lineup 0/1/2, combined constraints, lock conflicts, infeasible/no-relaxation behavior, independent violation detection and saved fields.
- The original no-cap reference reproduces **exactly five ordered roster sets**, resolved config, eligible IDs, all five feasible-region and objective coefficient fingerprints, primary solver objectives and reconstructed report scores (tolerance 1e-9). This is the only historical replay; no new sensitivities or expanded discovery were run.
- **60 UI tests passed**, covering omission/preset/custom serialization, invalid inputs, reload restoration, both request paths, strategy separation, all six report rows and failed report recovery. TypeScript and Vite build pass; the existing bundle-size warning remains.
- Actual localhost UI checked: defaults, Custom overlap including a preset number, fractional custom exposure, optional zero per-lineup cap, reload restoration, strategy switch and restoration of Large volume. Desktop 1440×1000 and mobile 390×844 show no clipped controls. Temporary test choices were reset to their initial defaults; viewport override was removed. No Run Optimizer click occurred.
- The local API and worker were reloaded only after checking the queue was idle. No source ingest, projection build, live optimizer job, user portfolio, final recommendation, entry submission or new sensitivity was performed for this task.

Validation logs and desktop/mobile UI proof are in [artifacts/classic_large_gpp_ui_controls](artifacts/classic_large_gpp_ui_controls/). The standalone regression test is `backend/app/tests/product/test_classic_large_gpp_controls.py::test_omitted_controls_exactly_reproduce_immutable_production_fixture`.

![Large-GPP controls at their defaults](artifacts/classic_large_gpp_ui_controls/desktop.png)

The independent overlap/risk combination was also verified in the actual UI: overlap 5 with per-lineup elevated Strategy default survived reload. The collapsed Advanced row now exposes the risk control label/value. Both fit at mobile width 390; prior settings were restored and no optimization was launched.

![Independent overlap and risk settings example](artifacts/classic_large_gpp_ui_controls/independent_overlap_risk.png)

### Max lineups per primary game available in UI?
YES

### Max lineup overlap available in Large-GPP UI?
YES

### Elevated-risk player exposure available in Large-GPP UI?
YES

### Are explicit user values persisted into the strategy contract?
YES

### Are explicit user values honored by the production solver?
YES

### Are achieved values independently validated and displayed?
YES

### Does omitting all new controls reproduce the frozen production parity fixture exactly?
YES

### Did Codex generate a new user portfolio?
NO
