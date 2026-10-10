# Sunday Main GPP historical baseline

The read-only audit replays the current provisional recommendation policy on saved
returned GPP candidates and compares its frozen choice with canonical actuals and
imported standings. It does not change the optimizer, projections, live settings,
or saved pregame rows. It does not enter contests or restart the running worker.

Run from the repository root with database access:

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_gpp_recommendation_history.py
```

Outputs are `artifacts/gpp_historical_baseline/report.json` and `report.md`.
Use `--output-dir` to retain separate dated audit runs. The database transaction is
read-only and repeatable-read. The audit covers completed Sunday Main Classic
runs explicitly saved with the GPP objective. This first baseline does not certify
Captain or other Classic slates.

## Evidence and interpretation

- The existing deployed selector validates returned candidates and freezes its
  projection-first choice before outcomes are joined. Historical selections are
  policy replays, not claims about which entries were actually played.
- Saved creation, last-update and data-cutoff timestamps must precede saved game
  kickoff. Every returned player needs saved kickoff evidence. Upcoming slates
  and slates without imported results are excluded. All eligible results remain
  exploratory: mutable database timestamps cannot independently prove immutable
  prelock capture or historical information availability.
- Canonical IDs match actual scores. Missing or conflicting actuals remain
  unavailable. The audit never substitutes a different candidate because its
  actuals are easier to obtain. Postgame-contaminated candidate records are rejected.
- A hindsight best returned score diagnoses selection opportunity. The best
  observed saved search-pool score diagnoses candidate coverage. These are not
  deployable policies or proof of an optimal generator. Coverage counts accompany
  every ceiling; incomplete coverage yields only a lower bound. Saved search-pool
  manifests are checked when available; mismatches prevent use of that pool.
- Complete standings support field placement independently of payouts. Synthetic
  insertion into an unchanged field produces conservative rank bounds for ties;
  it does not simulate removing an existing entry or exact platform tie splitting.
- Paid-finish and payout claims require verified GPP classification, complete
  standings, contiguous nonoverlapping payout tiers, and a payout sum matching the
  contest prize pool. A tie spanning the paid cutoff remains uncertain. Net return
  additionally requires a known entry fee. Counterfactual return is not expected
  return or actual winnings.
- Runs and contests sharing a slate are grouped, not treated as independent
  observations. No pooled paid-finish rate or model promotion is produced.
- Separate hashes record the replay inputs, frozen choice, saved search pool and
  contest evidence. They identify this audit's inputs; hashes calculated now are
  not proof that the inputs were immutable before historical kickoff.

## Next acceptance gate

Import verified historical contest types, entry fees, prize totals and full payout
ladders. This historical evidence does **not** require choosing or saving contests
before generating the next slate's one recommended lineup. Resolve actual-score
coverage, retain independently timestamped prelock snapshots for future slates,
and evaluate paid finishes first, then net return and top-finish outcomes across
held-out slate blocks. Only then compare a proposed paid-finish selector with the
provisional projection-first baseline. Automated settlement and model promotion
are not implemented by this research audit.

## Baseline captured 2026-10-10

The initial run inspected 85 saved GPP runs and 15 complete Sunday Main fields.
Fifty runs passed recorded-clock and candidate screening across three slate
blocks: 2026 Week 1 (one run), Week 3 (18), and Week 4 (31). Thirty-five were
excluded; reasons can overlap. None of the 15 contests has imported payout tiers
or verified GPP classification, so verified paid-finish evaluations remain zero.

An illustrative Week 3 run (`2ef9ee7e-d2a1-4cc4-bf88-b89e5f40a2c5`) gives the
projection-first replay 117.6 points versus a best returned score of 139.2. The
best observed search-pool score is 157.0, with only 192 of 212 candidates
scoreable. This demonstrates measurable selection opportunity within that run;
it does not establish that another pregame selector can reliably capture it.

Validation: 54 targeted historical-audit, recommendation and optimizer-evidence
tests passed. The database-backed command completed in a read-only transaction;
Python compilation and documentation whitespace checks passed. No service
activation is needed: this is an offline research command, not a new app screen
or automatic postgame settlement job.

The entry-history rebuild and stage diagnosis are documented in [Sunday Main generation/selection diagnosis](sunday_main_generation_selection_diagnosis.md). The audit now accepts verified exported Places_Paid for paid-finish comparisons; full payout ladders remain required for counterfactual monetary return.
