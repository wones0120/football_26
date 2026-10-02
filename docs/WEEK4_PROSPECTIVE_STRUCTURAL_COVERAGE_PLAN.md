# Week 4 prospective Classic structural coverage contract

## Status and scope

The experiment machinery is implemented for the next eligible, pre-lock Classic small-field GPP run. **No Week 4 slate has been frozen or evaluated yet.** On September 29, the local database had zero Week 4 Sunday projection and ownership rows, so a live three-arm run could not yet be verified. Migration `0039_classic_prospective_experiment.sql` was applied to the local `football_26_dev` database on September 29, 2026. The production generator, selector call, projection, ownership, correlation, and selector weights are unchanged. The proposed injury controls run in `SHADOW_GENERATION`; this keeps the production arm a valid baseline. No shadow is promoted automatically.

The three arms are:

| Arm | Candidate source | Selection |
| --- | --- | --- |
| `PRODUCTION` | Current sequential plus exact-family Classic generator | Current selector and portfolio constraints |
| `SHADOW_GENERATION` | Same frozen players and scores, plus bounded structural discovery; risk and core controls below | Same selector weights with shadow risk budgets |
| `SHADOW_PORTFOLIO` | Exact original production candidates and scores | Current exposure limits plus overlap ≤6; no distinct-QB rule |

Every Classic optimizer run now records a hashed final solver frame, source IDs, cutoff and options. Small-field GPP additionally stores the complete GPP `Player` adapter rows, the unfiltered source pool and final eligible source rows, resolved `SlateConfig`, code-file SHA-256 values, policy IDs, and exact generation and portfolio options. `replay_frozen_generation` checks both the data hash and code hashes before rebuilding from the saved rows without querying later slate tables. Exact replay against an actual next-slate run still needs to be demonstrated; older Week 3 runs lack this contract.

`target.classic_prospective_experiment` stores the solver snapshot and three pre-lock arms under one optimizer run ID. A trigger rejects rewrites of frozen columns. Postgame results have a separate mutable column. The snapshot records both the model/projection data cutoff and the optimizer decision time. Injury evidence for the risk overlay must predate the decision; the model cutoff is retained separately because a later pre-lock status refresh can inform a user risk preference without altering the older projection. Shadow creation requires the run, model cutoff, shadow completion, and local database persistence check to precede the earliest kickoff in the full saved salary pool, including games absent from generated lineups. If timing cannot be proved or risk inputs fail validation, the report says so and the production result remains intact.

## Exact availability classification

The classifier uses the saved official availability, pregame injury, injury snapshot, and salary status fields. The most severe explicit designation wins. `OUT`, `INACTIVE`, `IR`, `PUP`, and `SUSPENDED` are **out**. `DOUBTFUL`/`D` is **doubtful**. `QUESTIONABLE`/`Q` is **questionable elevated** unless a timestamped `FULL` practice status **and** a separately timestamped `FULL`, `NORMAL`, or `NO_RESTRICTION` expected-workload status are both saved. Only that combination is **questionable full role**. Other statuses or no material designation are **normal**. A timestamp later than the optimizer decision blocks the shadow; it is never incorporated. Missing practice, workload, or timestamp evidence keeps a questionable player in the elevated bucket. A full-role label is never inferred from a projection or an eventual game appearance.

The final solver pool and the unfiltered source pool are both frozen. Questionable or doubtful players excluded before generation are listed with zero exposure. The report includes designation, evidence time, practice and workload fields, bucket, candidate and selected exposure, configured caps, whether exposure is at a cap, and override reason. An at-cap flag is a numeric constraint status, not a player-level causal effect. Practice trend is captured when present but does not by itself establish a full role. No coach-comment, game-time-decision, snap-restriction, recent-return, or verified practice-trend feed is currently guaranteed. Those missing inputs are displayed as unavailable; they are not invented or scraped.

## Proposed shadow defaults and overrides

| Risk class | Candidate cap | Selected-player cap | Other rule |
| --- | ---: | ---: | --- |
| Out/inactive | 0% | 0% | Excluded |
| Doubtful | 0% | 0% | Explicit reasoned override required |
| Questionable elevated | 25% | 40% | At most one per lineup; no more than 60% of selected lineups contain any |
| Questionable full role | 50% | 60% | Risk remains visible |
| Normal | None from injury | None from injury | Ordinary core control may apply in the shadow |

For all non-elite players, the structural shadow caps candidate exposure at 70%. An elite core must be healthy/normal and rank in the top 20% of its position by **both** mean and P90 and the top 30% by mean per $1,000 salary. Low-owned/value core means ownership below 5% **and** top-30% value. Ownership alone never creates an elite exception. Elite exposure can exceed 80%, but the saved report must state that evidence. An explicit non-elite core exception above 70% needs a reason and saved top-20% position mean or P90 evidence. Candidate underfill and unachieved family minimums are reported; the deterministic admission pass is not an exhaustive proof that the capped pool is infeasible. Caps are never silently relaxed.

The API `params` object accepts `classic_availability_risk_policy` with any named default from `DEFAULT_RISK_POLICY` and `classic_availability_overrides` keyed by canonical player ID. An override must have a nonempty `reason`. It may set `allow_doubtful`, `candidate_cap`, and `selected_cap`; it cannot admit an out/inactive player. Global policy fields also permit a deliberate change to the per-lineup and aggregate risk budgets. Overrides change optimizer eligibility or selection only, never model projections or football evidence. Invalid controls block the shadow and appear in the report without changing production lineups.

Example:

```json
{
  "classic_availability_risk_policy": {"elevated_candidate_cap": 0.25, "selected_lineups_with_elevated_cap": 0.60},
  "classic_availability_overrides": {
    "canonical-player-id": {"reason": "I accept the saved pre-lock workload uncertainty", "selected_cap": 0.60}
  }
}
```

## Structural exploration and diagnostics

A viable QB must have saved starter evidence when the slate has it, must not be out/doubtful, and must rank in the top 60% of eligible QBs by at least one of mean, P90, mean salary value, game total, or implied team total. This is a union, not equal QB exposure. For each viable QB, the shadow seeks two quality-legal candidates in each of `QB+1` with/without one bring-back and `QB+2` with/without one bring-back. Existing production candidates count; only deficits trigger fresh exact-family solves. Configurable floors default to at most 10 mean and 15 summed P90 below the best original candidate. Every request, infeasibility, discovered roster, final family count, and unmet minimum is saved. Overall counts also retain `QB+2+2` and `QB+3` families already present in production.

The pre-lock high-P90 check flags a top-5%-at-position player below 5% candidate exposure. A forced structural solve tests whether a quality-legal lineup exists. If it does not, a second solve without the quality floor distinguishes a legal low-quality construction from salary/roster/other solver infeasibility. No player is forced into the final pool. The saved report includes roster count, effective QB/game/stack family count, overlap, QB and game exposure, family counts, mean/P90 and ownership distributions, core concentration with >80% reasons, and questionable exposure by player, bucket, and 1/2/3+ players per lineup.

The shadow report displays projected mean and summed-ceiling sacrifice against the same discovered candidate universe with the same structural core policy but without questionable/doubtful candidate and selected risk caps. This is a **within-discovered-universe** counterfactual; it cannot measure lineups never generated. The separate overlap shadow reports mean, ceiling, ownership, leverage, player/game/QB and stack exposure, and its overlap matrix against the production selected portfolio.

After contest actuals and field standings are imported, run:

```bash
PYTHONPATH=. .venv/bin/python scripts/finalize_classic_prospective_experiment.py OPTIMIZER_RUN_ID --dry-run
PYTHONPATH=. .venv/bin/python scripts/finalize_classic_prospective_experiment.py OPTIMIZER_RUN_ID
```

The postgame evaluator verifies both pre-lock hashes and requires at least 90% scoreable candidates in every arm before appending. It computes best generated actual, P90/P95/P99 generated actual, counts at top-20/10/5/1% field lines, best/average/median selected actual, selected field attainment, regret lower bound, and selected concentration. Incomplete actuals remain explicit. The frozen pre-lock objects are never changed, and no winner is used to revise a threshold automatically.

## Week 3 Coker evidence

The saved Sunday Main optimizer run `2ef9ee7e-d2a1-4cc4-bf88-b89e5f40a2c5` was created September 27 at 12:41 Eastern. Its saved Coker player-pool row says `Q`, availability probability 1.0, start probability 1.0, and no practice, workload, expected-snap, expected-route, or expected-target evidence. The local pre-lock salary row also says `Q`; a September 26 21:02 Eastern injury snapshot says `Q`. This **would have triggered the elevated-questionable bucket** under the proposed policy because full-role evidence is absent. It does not establish that he was unlikely to start, nor does his in-game exit justify the cap values. The new policy is a broad portfolio-risk preference, not a Coker penalty.

## Files and validation

- `backend/app/product_services/classic_prospective.py`: frozen contracts, availability classification, structural shadow, exposure and postgame evaluator.
- `backend/app/product_services/optimizer.py`: salary/availability source lineage, snapshots for all Classic runs, and small-field shadow invocation.
- `backend/app/product_services/classic_small_field.py` and `gpp_optimizer.py`: optional shadow-only aggregate risk and per-lineup group constraints.
- `migrations/0039_classic_prospective_experiment.sql`: immutable pre-lock storage and separately appendable outcomes.
- `scripts/finalize_classic_prospective_experiment.py`: post-slate scorer.
- `ui/src/optimizerReport.ts` and tests: visible pre-lock risk and shadow section.
- README, post-slate learning notes, release notes, and targeted Python tests were updated.

Targeted Python checks: 118 passed. UI tests: 37 passed. UI TypeScript/Vite build: passed. The full Python suite passed 879 tests and retained four pre-existing Showdown single-TE failures in `test_showdown_single_entry.py` and `test_showdown_three_max.py`; their request normalizer currently forces `enforce_single_te=False`. This task did not change Showdown code. Migration `0039` is applied locally; the migration record, target schema contract, table, and immutable-column trigger were verified. An insert and rejected update were rolled back, leaving the table empty. The broad public-schema drift check still reports unrelated legacy public tables and column types. A live next-slate freeze, exact replay, and postgame comparison remain pending the next eligible slate and imported actuals.
