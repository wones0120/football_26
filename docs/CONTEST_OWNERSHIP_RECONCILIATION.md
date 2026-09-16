# Contest ownership reconciliation

Apply migrations with `python -m scripts.apply_migrations`. Migrations 0029 and 0030
add append-only ownership observations and the older ownership table's source lineage.
Migration 0031 refreshes the recorded target schema contract.

A manifest records each contest's `contest_id`, `slate`, `archive`, archive `sha256`,
and registered decompressed `source_file_id`. Reconciliation verifies both checksums.
It reads the exact slate's DraftKings salary evidence, never creates canonical players,
and preserves unresolved/ambiguous observations for review. The SQL review table and
exported `review/*_unresolved.json` files contain every candidate and source ID.

Dry run (the default):

```sh
python scripts/product/reconcile_contest_ownership.py \
  artifacts/source_snapshots/contest_results/2026_week1/manifest.json \
  --season 2026 --week 1
```

Add `--apply` to append identity decisions and atomically refresh each manifest
contest's resolved labels in `dk_ownership`. Other contests, standings, metadata,
payouts, projections, and raw archives are untouched. Repeated identical decisions
use content-derived IDs and are not inserted twice. New evidence produces a new
historical decision; inspect the latest decision when following up on an old review.
Resolved labels have null `projected_ownership`; only `actual_ownership` is populated.
Do not enable model retraining until the intended time windows and identity coverage
have been checked. The manifest's initial quarantine status is historical; consult
`review/summary.json` for the reconciliation status.

Build the read-only report JSON after reconciliation:

```sh
python scripts/product/build_contest_postmortem.py \
  artifacts/source_snapshots/contest_results/2026_week1/manifest.json \
  --season 2026 --week 1
```

This uses the manifest's `own_entries`, `format`, and `field_size`. It validates
player-point sums and matches saved lineups by canonical IDs plus CPT assignment.
Without a matching saved lineup, it explicitly uses a prelock reference projection.
The Markdown findings for this run are in [the Week 1 postmortem](WEEK_1_CONTEST_POSTMORTEM.md).
Fees/payouts remain unknown until supplied. Historic target actuals may be incomplete;
the displayed last-three average describes displayed records and is not a substitute
for the model's saved `feature_inputs.player_roll3_mean`.
