# Generation versus selection audit: 2026 Weeks 1–4

Completed October 10, 2026 (October 11 UTC). **Live selectors, projections, user defaults and optimizer settings are unchanged.** All database access used read-only transactions. The refreshed baseline contains 251 completed GPP runs: 175 pass recorded-clock screening and 76 are excluded. Related runs are not independent trials.

## Decision

Prioritize Sunday Main **shortlisting and single-lineup ranking**, not simply generating more lineups. For Captain, test **quality-screen calibration and shortlisting together**, under the current WR/RB Captain preference. There is not enough evidence to promote a replacement selector or change the user's constraints.

The active recommendation is `gpp_projection_first_recommendation_v1`: expected projected points first, summed marginal P90 as a tie breaker. It is a provisional surrogate, not a calibrated paid-finish probability or tournament-return estimator.

## Sunday Main first

Latest clock-eligible run per week, selected by timestamp before looking at actual performance:

| Week | Recommended actual points | Best returned | Best observed saved pool | Verified GPP paid finishes |
|---|---:|---:|---:|---:|
| 1 | 202.10 | 202.10 | Unavailable | 1/1 |
| 3 | 117.60 | 139.20 | 157.00 | 0/3 |
| 4 | 153.90 | 158.58 | Unavailable | 3/3 |

Week 3's paid cutoffs were 142.44, 145.10 and 147.14. Its best observed generated candidate cleared all three but was ranked 54 and never reached the five returned choices. The pool had 212 candidates; 192 have complete actuals. This establishes that a paid-scoring roster was generated, not that all historical constraints would have allowed its delivery. Eligibility flags were not retained for this older path.

Across the related Week 3 small-field runs, 20 run/contest comparisons are clearer final-selection misses: a paid-scoring candidate was already among the valid returned choices, but the projection-first replay chose a nonpaid one. These are repeated observations on one slate, not 20 independent failures.

All 31 eligible Week 4 Sunday Main runs' replayed recommendations clear their three verified GPP cutoffs. The historic small-field and current large-GPP paths must be evaluated separately. The primary Week 4 large-GPP run retains five returned candidates but no separate complete search pool; do not interpret this as proof of adequate generation coverage. Week 2 Sunday Main standings remain missing.

## Captain: distinguish ranking from the quality screen

| Slate | Recommended actual points | Best returned | Best saved pool | Best recorded quality-eligible pool | Verified GPP paid finishes |
|---|---:|---:|---:|---:|---:|
| W3 Thursday | 130.17 | 130.17 | 147.99 | Eligibility not recorded | 3/3 |
| W4 Thursday | 106.73 | 106.73 | 114.96 | 106.73 | 2/2 |
| W4 Sunday | 111.37 | 111.37 | 164.74 | 132.57 | 0/2 |

Week 4 Sunday has 136 saved scenario rows, representing 113 distinct rosters/Captain assignments; all have actual scores. The two paid cutoffs were 130.05 and 130.63.

- The 164.74-point maximum used Jake Bates at Captain and failed the recorded quality screen. It is not a valid replacement under today's WR/RB Captain preference.
- The best recorded quality-eligible candidate scored 132.57 with Bryce Young at Captain, rank 49. It cleared both cutoffs but also conflicts with today's WR/RB Captain preference. Recorded quality eligibility alone does not establish full portfolio feasibility.
- Among WR/RB Captains passing the recorded screen, the best actual score was only 108.14 (Jameson Williams).
- A Tetairoa McMillan Captain candidate scored 147.84 but failed the screen. Thus reranking only the existing quality-approved WR/RB set could not have produced a paid finish on this saved pool. Investigate whether the screen removes too much useful uncertainty before expanding generation.

The saved screen used a 0.95 quality fraction with a common-baseline comparison. This one outcome does **not** establish a better threshold. The WR/RB subset is a Captain-position diagnostic only; it does not reconstruct every current minimum-salary, WR/QB stack, team-leader or team-split preference.

Seven related W3 Thursday portfolio runs also have final-selection misses against all three verified fields (21 run/contest comparisons). Conversely, two W3 Thursday single-entry runs have fully scored saved pools with no paid candidate (six comparisons). Generation can fail too; this is evidence about those particular old pools, not a reason to expand every current run.

## What to validate next

1. Sunday Main: retain full generated candidates, shortlist/eligibility reasons and the one recommendation separately. Freeze the current controls and compare shortlisting/ranking alternatives on the same pool. Measure diversity of actual candidate coverage rather than just increasing the requested count.
2. Captain: freeze a paired comparison of the existing quality screen and a predeclared challenger, retaining all current user constraints. Compare both screens and their resulting single-lineup recommendations; do not select historical winners or tune the threshold to this one game.
3. Evaluate untouched slate blocks after kickoff. Primary outcome: paid finish against the same verified GPP contests. Secondary: top-10% and top-1% placement. Require complete payout evidence before claiming return improvement.
4. Keep production unchanged until the challenger demonstrates a repeatable benefit. Weeks 1–4 are diagnosis/development data now, not an untouched test set for changes designed from these findings.

## Evidence limits

“Paid” uses complete imported standings and verified DraftKings entry-history Places_Paid. Counterfactual lineups are compared with the unchanged field using conservative tie handling; exact boundary ties can remain unknown. These are current-policy historical replays, **not the user's actual entered lineups or realized winnings**.

Candidate actuals use canonical player IDs and normalize Captain points before applying the Captain multiplier exactly once. Missing/conflicting actuals remain unknown. No name-only joins or invented zero scores were used.

Only three Sunday Main and three Captain slate blocks have both a clock-eligible recommendation replay and verified paid-cutoff evidence. Earlier Captain fields lack verified paid places; other scopes lack standings or eligible historical runs. Full payout ladders are missing, so expected return, exact counterfactual winnings and duplication-adjusted ROI are unvalidated. The latest projection audit is separate from the projection snapshot used by each optimizer run. Database timestamps screen chronology but do not prove immutable prelock provenance.

## Reproduction and validation

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_weekly_validation.py --output-dir artifacts/generation_selection_audit/NEW_RUN
PYTHONPATH=. .venv/bin/python scripts/audit_generation_selection.py --source artifacts/generation_selection_audit/NEW_RUN/report.json
```

The second command verifies saved candidate-pool hashes before scoring, distinguishes recorded eligibility from unknown flags, deduplicates scenario variants within each group, and writes only research artifacts. It never trains, promotes or writes optimizer records.

Reviewed evidence: `artifacts/generation_selection_audit/20261011/reviewed/report.json`, `report.md`, `stage_audit.json`, and `stage_audit.md`. The JSON includes per-run strategy, pool hashes, coverage, cutoff evidence and stage diagnoses. The initial unrefined outputs are retained separately for audit history; use the reviewed stage report for conclusions.

Validation: 32 targeted tests passed for paid-cutoff evidence, conservative ties, chronological screening, missing actuals, stage classification and scenario deduplication. No backend restart or production deployment was needed.
