# Workstream audit template

Use [CONTRACT.md](CONTRACT.md) and the unchanged [catalog](CATALOG.md). This phase is read-only except for audit documents/evidence receipts. Do not implement metrics, download new sources, ingest, train, solve, activate a model or change defaults.

## Audit header

- Audit ID/version/date, worker and ownership workstream/groups.
- Examined HEAD, relevant working-tree paths and producer/consumer hashes where needed; distinguish existing uncommitted code from activated serving behavior.
- Scope: seasons/weeks/game types/teams/positions/formats; current and historical sources examined; decision cutoffs and reconstructed/original evidence status.
- Commands/queries run and artifact/output destinations; no database mutations. Note prerequisites or unavailable access explicitly.

## Metric record — repeat for every assigned catalog ID

```
metric_id: Gxx-Myy
catalog_label: unchanged original text
definition_version: audit-v1
variant_id: channel/grain suffix if needed; otherwise default
owner_workstream:
definition: exact measured or intended quantity; unresolved choices explicit
kind: observed_fact | derived_feature | forecast | analyst_judgment | target_label
grain: event | player_game | team_game | player_window | game_forecast | lineup | portfolio | other
unit:
formula:
applicable_actors_positions:
scope_keys: canonical/native identity, game/team/season/type/week/slate/format as applicable
denominator_and_actor_universe:
window: periods/weighting/same-team/cross-season/DNP/unknown-gap rules
semantic_match: exact | partial | proxy | different_definition | unresolved_definition
source_availability: verified_local | derivable_from_verified_local | vendor_unavailable | unknown
coverage: rows, games, actors, dates, exposure/denominator coverage, unresolved identities/missing components
value_missingness: measured/derived/estimated/proxy/unknown/not_applicable; zero/imputation rules
clock_proof: event/pub/modified/observed/captured/received/decision/lock fields and evidence strength
time_safety: proven_for_stated_scope | retrospective_reconstruction | leakage_concern | unverified
forecast_conditioning: not_applicable or explicit unconditional/active/role/scenario estimand
uncertainty_and_sample: interval/probability/calibration status; sample/exposure counts or not evaluated
dependencies: other metric IDs, shared events/budgets, role evidence, source joins
quality_evidence: existing validation/defect/limitations or not_evaluated; never assume source availability proves quality
gap_and_next_decision: smallest unresolved question; proposed later work only
```

Use separate rows/sections for genuinely different existing variants rather than labeling them all exact. Distinguish desired definitions from what the current implementation actually computes. If no source is known, mark unknown and document the scoped search; do not fill a formula or coverage claim from reputation.

Keep the audit compact: common source/window/clock definitions and evidence ledgers may be shared within a workstream and referenced by ID from per-metric rows. The record above is a completeness rubric, not a demand to paste a long empty block for every candidate. Use detailed records for actual implementations, mismatches or important gaps; a clearly scoped unknown/absent row with its search receipt is sufficient for an unsupported candidate. Do not expand the inventory phase into exhaustive source research.

### Mandatory implementation matrix

All nine rows must be assessed. `verified` requires direct evidence, not a matching field name. `partial` includes unsupported cohorts, dormant paths or mismatched semantics. Use `absent_after_scoped_search`, `not_applicable`, or `not_checked` honestly.

| Layer | Status | Actual output / field / grain / definition | Producer and source evidence | Exact consumer or why dormant | Activation/scope | Evidence IDs |
|---|---|---|---|---|---|---|
| Raw | | | | | | |
| Curated | | | | | | |
| Feature | | | | | | |
| Training | | | | | | |
| Serving forecast | | | | | | |
| Analyst | | | | | | |
| Optimizer / selection | | | | | | |
| UI / saved report / export | | | | | | |
| Tests / validation | | | | | | |

Training entries identify exact target versus feature columns, fitted preprocessing, artifact/cohort and cutoff. Serving entries identify the actual public-path model/feature adapter, missing/fallback behavior and frozen receipt. Tests identify the assertion and executed status. UI evidence alone does not prove forecast consumption. A generic numeric matrix or a source table with an arbitrary JSON column does not prove a catalog component is present.

### Evidence ledger

| Evidence ID | Kind | Exact locator | Scope / cutoff / query or command | Observed result | Limits |
|---|---|---|---|---|---|
| E001 | source/code/query/artifact/test/UI | `path.py:line–line`, symbol; table.column; snapshot/run ID and SHA | Keep query/script reproducible and bounded | Counts, distinct keys, null/zero semantics, actual field values where safe | Original versus reconstructed, sample limits, whether executed |

Queries should include scoped periods, canonical and native identity fields, source/run IDs, relevant clocks, missing/duplicate counts and a row bound. Save query text and compact result receipts if they substantiate data claims. Use existing read-only connection patterns; never trigger a repair/feature-build function as an inventory query. “No rows in this bounded scope” is not “provider never supplies this metric.”

### Mechanism and leakage checks

- Full actor universe and identity/alias coverage; no salary/user-filtered team denominators.
- Source definition, component coverage, count conservation and unmapped/unallocated residuals.
- Verified zero, participant zero, verified inactive, roster-inferred absence, bye and unknown gap distinguished.
- Historical event time versus actual predecision receipt/availability; labels and realized future context excluded from features.
- Applicable channels/positions and explicit window transport across team/season; finite value is not measurement proof.
- Shared signal/event dependencies: QB pass and receiver target, nested zones/TDs, correlated FP/count/Analyst ancestry.
- Sparse exposures, sample size and uncertainty claims; descriptive splits are not automatically causal matchup advantages.
- Report current activation and actual propagation; do not infer serving from a research file or passing unit test.

## Workstream summary

Provide a compact table with one summary row per assigned metric ID. Preserve any more detailed variants above.

| Metric ID | Label | Definition/grain resolved? | Source availability | Raw | Curated | Feature | Training | Serving | Analyst | Optimizer | UI/report | Tests | Time proof | Quality evidence | Principal gap/dependency |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

Then list: verified reusable paths; facts present but not consumed; semantic/provenance defects; sources/access not verified; cross-group conflicts; and the smallest questions requiring user choice before later implementation. Separate availability gaps from forecast quality limitations. Do not propose a new paid dependency or claim vendor availability without evidence.

## Handoff acceptance

- Every assigned stable ID appears once in the summary, with detailed variants linked rather than counted as new catalog metrics.
- Each layer has a state and positive claims have exact evidence; searched absence has a scoped search receipt.
- Existing output meaning, scope, consumers/defaults and historical availability limits are explicit.
- No source evidence, settings, models or operational jobs changed.
- Return paths and a concise verified findings/gaps message to the parent. Parent/High reconciles overlap before implementation is considered.
