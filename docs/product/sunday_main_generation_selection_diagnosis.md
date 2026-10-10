# Sunday Main: improve selection before expanding generation

Rebuilt on 2026-10-10 using immutable DraftKings entry-history snapshot
`085939c693996d30399f17f76f7ac8fa37faf1ccdf586a27e3e34b6a74239eab`.
Detailed results: `artifacts/gpp_historical_baseline/with-entry-history/report.json`
and `report.md`. The app's Sunday Main Learning reports were rebuilt for 2026
Weeks 1, 3 and 4 with personal winnings and exported paid-place counts.

## Decision

Prioritize **candidate ranking and shortlisting**, then the final one-lineup
selection. There is direct evidence of generated paid-finishing candidates being
lost before delivery. There is no demonstrated complete-pool generation failure
in the scoreable, cutoff-verified comparisons. This does not prove that the
current generator is sufficient: missing pools and actuals prevent that claim.
Do not expand generation volume or tune weights from this small sample alone.

The strongest evidence concerns the historical `classic_small_field_gpp` path.
Today's `classic_large_gpp_v1` path has much less saved search-pool evidence and
must be evaluated separately. Its latest eligible Week 3 run cleared two of three
GPP cutoffs; its latest eligible Week 4 run cleared all three. A broad production
ranking replacement is not justified by this retrospective audit alone.

## Evidence by independent slate block

| Week | GPP paid cutoffs | Diagnostic |
|---|---|---|
| 1 | 165.46 | Only one eligible run, with one returned candidate. Replay scored 202.10 and cleared the cutoff; no useful selection comparison. |
| 3 | 142.44, 145.10, 147.14 | In the latest small-field run, replay chose 117.60; best returned was 139.20; best observed search-pool candidate was 157.00. Narrowing the pool removed a candidate that cleared every cutoff. |
| 4 | 131.72, 133.08, 133.78 | All 31 eligible runs' replayed recommendations cleared all three cutoffs. Latest large-GPP replay scored 153.90 versus best returned 158.58. There is upside room, but no paid-finish miss in these comparisons. |

Week 3's 18 related runs produce 54 run/contest comparisons: 20 final-selection
misses, 14 shortlisting misses, 5 paid recommendations, and 15 failures with
insufficient pool evidence to establish a generation miss. Eleven runs have at
least one final-selection miss; five have at least one shortlisting miss. These
are descriptive diagnostics within one slate, not 54 independent trials. All
confirmed selection/shortlisting misses are in the historical small-field path.

The latest Week 3 small-field pool has 212 saved candidates, only 192 scoreable.
Its 157-point observed candidate is still affirmative evidence that a paid
candidate existed, but the true pool maximum is unknown. Older manifest/timestamp
limitations remain; database clocks are screening evidence, not independent proof
of immutable prelock capture.

## Personal results are separate from policy replays

Only imported GPP contests are counted below; two Double Ups are excluded.

| Week | Paid finishes / entered GPPs | Fees | Winnings | Net |
|---|---:|---:|---:|---:|
| 1 | 1 / 1 | $5 | $15 | +$10 |
| 3 | 0 / 3 | $7 | $0 | -$7 |
| 4 | 2 / 3 | $9 | $16 | +$7 |

These are the actual exported entries, not the provisional selector's hypothetical
choices. They cover seven matched contests over three weeks, not every contest
played this year. Week 2 Sunday Main standings are still missing. The policy
replay uses saved projections and the current deterministic selector, never actual
scores to choose a lineup. Hindsight maxima are diagnostics only.

## Recommended next implementation

1. Preserve the full generated candidate set and stage-by-stage selection reasons
   for the active Classic large-GPP path, not just its returned lineups. Pin the
   projection, ownership, constraints, code version, kickoff and completion clocks
   and input/output hashes for reproducible future evaluation.
2. Evaluate a challenger ranker across that same frozen candidate set, in shadow
   mode. Identify exactly why strong candidates are filtered or ranked down. Do
   not reward candidates using the historical outcomes being evaluated.
3. Validate on held-out slate blocks: paid finishes first, with expected-return
   modeling and top-finish outcomes as additional requirements. Full payout ladders
   are still absent, so exact counterfactual return and expected return cannot be
   validated from these exports alone.
4. Expand generation only when sufficiently complete held-out pools show that
   competitive candidates are genuinely absent.

## Scope and validation

The refreshed audit inspected 86 saved GPP runs: 50 exploratory runs across three
weeks and 36 exclusions, including current/future or missing-result slates. Seven
GPP fields have complete standings and exported Places_Paid. Pylon and Daily
Dollar single-entry families are recognized by their exported contest names;
classification remains explicitly name-inferred. Cash-name precedence remains.
No artificial payout tiers are created and no live optimizer weights changed.

The rebuilt app reports retain existing immutable-report behavior. The generation
process emitted its existing process-lifetime peak-memory warning; report writes
completed successfully. Exact counterfactual return is still unavailable. The
reproducible research command is:

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_gpp_recommendation_history.py \
  --output-dir artifacts/gpp_historical_baseline/with-entry-history
```

Validation: 79 targeted historical-audit, entry-history, Learning and optimizer
assessment tests passed, including paid-place-only evaluation, tie uncertainty,
cash exclusion, shortlist/final-selection/generation separation and missing-pool
handling. Documentation whitespace and report consistency checks passed.
