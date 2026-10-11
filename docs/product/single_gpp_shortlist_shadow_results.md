# Classic and Captain single-lineup shortlist shadows

Completed October 10, 2026 against the current saved Week 5 Sunday Main and
Sunday Night baselines. Both experiments are registered before kickoff in
**Learning → GPP shadow comparisons**. Live selectors, model projections,
user settings and optimizer-run configurations remain unchanged.

## Result

| Format | Expanded comparison | Control → shadow projected points | Decision |
|---|---|---:|---|
| Classic Sunday Main | Original five plus five projection-focused candidates; nine unique rosters | 133.07 → 133.07 | Same recommended lineup; no demonstrated improvement |
| Captain Sunday Night | 150 saved candidates; 35 pass existing quality/feasibility checks; 33 unique compared rosters including incumbent | 79.09 → 80.33 | Different Captain assignment; outcome advantage unproven |

Classic's extra pass reproduces the original player pool and every non-objective
constraint. Its projection objective weight is 1, with ceiling, leverage and
correlation objective weights 0; hard stacking and other lineup/portfolio rules
remain active. Both five-lineup portfolios pass the **original** constraint audit.
The combined nine candidates are research alternatives for one recommendation,
not a proposed nine-lineup portfolio. This differs from Captain shortlisting:
Classic's current sequential generator has no larger hidden pool to reuse.

Classic still recommends Jacoby Brissett, Chase Brown, Jaylen Warren,
Amon-Ra St. Brown, Michael Wilson, DK Metcalf, Michael Mayer, Luther Burden III
and Commanders DST, salary **$49,900**. The added candidate coverage does not
change this recommendation. Identical control/shadow rosters will necessarily
have identical paid-finish outcomes against the same contest evidence; this is
one null comparison, not additional independent performance evidence.

Captain's shadow uses **Michael Penix Jr. CPT**, with Bijan Robinson, Drake London,
Derrick Henry, Matt Hibner and Austin Hooper at FLEX. It costs **$49,700**, compared
with the live London-Captain lineup's **$49,900**. The six player identities are
unchanged; Captain switches from London to Penix. Summed marginal P90 increases
145.41 → 145.62, but this is not a calibrated lineup percentile or win probability.
The challenger was rank 54 under the saved portfolio scoring order.

The current user run excludes questionable players. That preference and all other
captured controls are preserved, as are the existing joint quality screen and
full-portfolio feasibility flags. Every eligible Captain roster is reconstructed
from frozen base forecasts and the checksum-verified native salary CSV. Native
CPT/FLEX IDs and salaries, one-time scoring multipliers, mean/P90 aggregate parity,
canonical identities and export legality pass. No ownership term is enabled and
no favorable scenario score replaces the common baseline.

## How it will be evaluated

Paid finishes against the same verified GPP fields are primary. Net-return bounds
require adequate payout evidence; top-1% and top-10% outcomes are secondary. Unknown
actuals and returns remain unknown. Projected-point gains alone do not qualify
for promotion. The Weeks 1–4 hindsight winners were not used to tune this challenger.

Both new experiments currently report `pending_actuals`. Existing import hooks
refresh their reports when standings or account history are imported. There is
no automatic DraftKings download or automatic model promotion.

- Classic experiment: `125c27abc02ab721fcb61be5b1e575b305771fb1d6ce42d419911bdb259bae9a`
- Captain experiment: `1ef709d364718de19e6352b264ed5d91572b41c39dfeea501242b3e219538a4b`

The Captain choice repeats the earlier frozen expanded-shortlist hypothesis,
now verified against the latest user-generated run and its questionable-player
exclusion. It is **not** a second independent slate or independent success.
Additional untouched slates are needed before production promotion.

## Implementation, evidence and checks

`scripts/shadow_single_gpp_shortlist.py` is offline research tooling. Runtime
services do not import it. It rejects outcome-contaminated candidate inputs,
checks control parity, and refuses to overwrite existing output. Classic is
explicitly scoped to this predeclared Week 5 experiment; this pass does not install
automatic candidate-generation shadows for every future optimizer run.

Sources:
- Classic optimizer `eb324261-7630-492a-ad78-cad5f72bb43b`, projection `506c698c-a09c-4665-a79c-058c578de453`.
- Captain optimizer `cb89369f-dd5d-401b-96c5-8a6815033498`, projection `b2cb7c1f-3777-49c1-a4ab-3251db063dce`.

Artifacts under `artifacts/single_gpp_shortlist_shadow/` contain captured Captain
inputs, complete Classic control/probe contracts and portfolio proofs, compared
candidates, frozen two-arm snapshots, registration receipts, source hashes and
before/after live configuration hashes. Both live hashes and projection references
match exactly after registration.

Reproduction (use new output filenames; completion timestamps are not backdated):

```sh
PYTHONPATH=. .venv/bin/python scripts/shadow_single_gpp_shortlist.py \
  --format classic --source artifacts/sunday_projection_generation/replay_source.json \
  --output /tmp/classic-single-gpp-shadow.json
PYTHONPATH=. .venv/bin/python scripts/shadow_single_gpp_shortlist.py \
  --format showdown --source artifacts/single_gpp_shortlist_shadow/captain_input.json \
  --output /tmp/captain-single-gpp-shadow.json
```

The command does not write database rows or register automatically; the validated
snapshots above were explicitly registered through `ShadowLearningService`.
The [protocol](single_gpp_shortlist_shadow_protocol.md) was saved before execution.
All **41 targeted tests passed**, covering constraint isolation, preferences, identity/salary integrity,
Captain scoring, invalid forecasts, outcome rejection, recommendation and existing
shadow-learning contracts. No production deployment or restart is needed.
