# Verified DST input support in the normal workflow

Normal canonical input loading now prepares a separately versioned, verified DST
support artifact while leaving the incumbent model's numerical training and
prediction frames unchanged. The support contains corrected event-derived labels,
canonical game/home fields and strictly prior defense/opponent histories.
**This is input plumbing in place; it does not activate a replacement defense
model or repair the incumbent's forecast values silently.**

The [ranking study](../../research/dst_rank_stability_20261016/v1/REVIEW.md) did not
demonstrate reliable ranking improvement. The dedicated model policy's earlier
retrospective point noninferiority pass does not establish a differentiated
ranking: its selected full-history artifact is a flat five-point median.
Neither that artifact nor the failed ensemble/tree ranking policy is promoted.

## Explicit contracts and compatibility

- Active model input contract: `incumbent_dst_matrix_legacy_v1`.
- Verified support feature contract: `verified_dst_features_candidate_v1`.
- Support manifest contract: `verified_dst_input_support_manifest_v1`.

New fitted incumbent artifacts record the active contract and
`candidate_model_activation=false`. Serialization rejects candidate-tagged DST
frames under that incumbent contract; loading rejects incompatible declared
contracts. Older fitted artifacts without the new field retain their original
legacy semantics and reproduce their stored raw predictions. No table/schema
change is required: existing run/source/model JSON metadata holds these audits.

Candidate matrix generation still requires `persist=False`; candidate training
and scoring use explicit adapters. No default or live route switches to a
candidate forecast. Source correction, input delivery, model validation and model
promotion remain independently identified steps.

## Local configuration

These keys enable support generation only, with no model switch:

```dotenv
DST_FEATURE_SUPPORT_MANIFEST_PATH=artifacts/dst_feature_support/registration_20261016/v1/manifest.json
DST_FEATURE_SUPPORT_MANIFEST_SHA256=419513d9e05d23a8dca3c829cdd1021349efee125897c6f12155aea336b78a56
DST_FEATURE_SUPPORT_OUTPUT_ROOT=artifacts/dst_feature_support/generated
```

`.env.example` provides empty manifest/checksum placeholders; paths are configured,
not embedded in application code. The registered manifest pins verified event
outcome and canonical UUID identity sources by SHA256 and explicitly prohibits
model activation. Historical pregame capture clocks remain marked incomplete.
Current support files are separately reconstructed inputs, not original matrix
snapshots or retroactively captured pregame evidence.

Load configuration/code in both the API and durable worker when idle before a
new Prepare/prediction job. An API-only route reload does not update an already
running worker. Coordinate service restarts with active jobs; do not interrupt
an optimizer or preparation run to apply this support.

## Results and failure handling

Normal `load_inputs` adds `dst_feature_support` to source metadata. Prediction
metrics copy that same audit. Persisted run/source JSON therefore identifies
which support artifact was prepared and the incumbent contract actually used.

Statuses:

- `ready_inactive`: verified support exists; active model still uses its recorded
  incumbent contract. It never means a candidate model was promoted.
- `not_configured`: no support manifest was configured.
- `not_applicable`: no DST training/target cohort exists for the request.
- `unavailable`: checksum, source coverage, identity, configuration or artifact
  generation failed; the error is explicit and incumbent inputs are preserved.

Artifacts are content-addressed JSON files. Repeating the same inputs/cutoff
returns the same artifact; existing content is never overwritten. Each support
retains original training labels separately, reconstructed corrected labels,
current matrix identities, source hashes, home/history fields, cutoff and
explicit timing limitations. Future prediction rows carry no claimed outcome.
Unknown prior history is JSON null; genuine observed zero remains zero.

The normal current player availability/depth/source guards run before support
creation. Support does not bypass those gates. A stale slate needs its ordinary
source Prepare refresh before a current full canonical load can complete.

## Verified rollout evidence

[Operational verification](../../artifacts/dst_feature_support/operational_20261016/v1/verification.json)
confirms exact training/target frame and incumbent raw-prediction parity on the
preserved complete10,659-training/288-target artifact. Verified support contains
804DST training rows and20prediction rows, including402 repaired home flags.
The initial read-only current full load correctly stopped at the existing stale
player availability/depth guard; that is a source-preparation prerequisite,
not permission to bypass it. A current fresh job's run lineage is the authority
for whether its support status is `ready_inactive`.

Tests cover immutable/idempotent support, checksum/activation/source coverage
rejection, failure status, original frame preservation, old artifact compatibility,
candidate-contract rejection, and normal prediction workflow metadata with exact
unchanged forecast outputs. The focused combined suite has59passing tests.

## What remains blocked

The verified plumbing and artifact contracts can safely run now. New defense
forecast/ranking activation remains blocked by the failed ranking reliability
study and incomplete prospective/source-clock validation. A later explicit
promotion must select a validated versioned scorer, match its feature contract,
retain offense parity and atomic rollback, and disclose any point-only fallback.
A normal Sunday refresh continues to use the incumbent until that separate
promotion happens. Do not describe its defense values as corrected-candidate
predictions merely because support was prepared successfully.

Rollout status: both API and durable worker were refreshed while idle. The first
fresh normal Sunday Main Prepare (`fadbc87c-921c-473f-8248-0538ed52aa26`) correctly
stopped before projection creation because Max Klare, CJ Daniels, Joshua Palmer
and DJ Moore still need current availability/depth evidence. Their facts were
not overridden. Consequently current-run support lineage awaits a source-ready
Prepare; preserved-artifact support/parity is verified, and there is no new
projection to describe as candidate-based. See [rollout receipt](../../artifacts/dst_feature_support/operational_20261016/v1/rollout_status.json).
