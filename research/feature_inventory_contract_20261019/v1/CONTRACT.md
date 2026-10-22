# Shared football metric inventory contract

Contract: `football_metric_inventory_v1` · 2026-10-19 · design and audit only.

The [240-item catalog](CATALOG.md) is a set of candidates to investigate, not a claim that the data exists or a commitment to train 240 predictors. This contract supplies common definitions and an evidence rubric for the eight workstreams. It does not introduce a table, migration, dependency, runtime API, model, or activation policy. Do not change code, collect new sources, fit models, or alter operational settings during this inventory phase.

## 1. Deliverables and ownership

Each workstream returns an audit using [AUDIT_TEMPLATE.md](AUDIT_TEMPLATE.md), plus evidence references. Preserve catalog IDs `G01-M01` through `G24-M10` permanently. A renamed definition retains its ID and records the change; a genuinely new candidate gets a new ID after review. Do not replace an unsupported candidate with a convenient proxy under the same definition.

| Workstream | Groups | Primary responsibility |
|---|---|---|
| Game environment | G01, G02, G19, G20, G21 | Pace, play decisions, markets, venue/weather, situational splits |
| Quarterbacks | G03–G05 | Passing workload/effectiveness and QB rushing |
| Rushing and protection | G06, G07, G13 | RB rushing, efficiency and offensive-line context |
| Receiving | G08–G10 | Opportunity, efficiency and deployment |
| Scoring opportunities | G11, G12, G23 | Field position, TD opportunity, K/DST |
| Defense and matchups | G14–G16 | Opponent defense and specifically defined matchups |
| Availability and role changes | G17, G18, G22 | Status, personnel, history gaps, role/coaching changes |
| Lineup integration | G24 | Shared events/opportunities, salary tradeoffs, joint outcomes and portfolio exposure |

Cross-workstream dependencies reference the owning metric ID rather than creating another supposedly independent signal. For example, receiver target share references the same team target budget used by the QB and scoring workstreams. G13 owns line continuity; G18 can consume it. G24 audits actual consumption and dependence; it does not invent missing upstream forecasts.

## 2. Semantic record: what a value means

Use the following fields in audit records or existing JSON evidence. This is a documentation envelope, not a request to retrofit storage now. Map existing fields explicitly; record missing metadata as a gap.

| Required concept | Definition |
|---|---|
| `metric_id`, `definition_version`, `variant_id` | Stable catalog identity, exact definition version and optional channel/grain variant. One catalog item may need several explicit variants; it still counts as one audited candidate. |
| `kind` | Exactly one of `observed_fact`, `derived_feature`, `forecast`, `analyst_judgment`. Training outcomes are separately identified `target_label` records. A field may have several records of different kinds. |
| `definition`, `formula`, `unit` | What is counted/measured, inclusion/exclusion rules, aggregation formula, and unit. Declare proportion 0–1 versus percentage 0–100; attempts/game versus total attempts; EPA/play versus total EPA. |
| `grain`, `entity_keys`, `scope` | Event, player-game, team-game, opponent unit, player-window, game forecast, lineup or portfolio; canonical identities and applicable season/week/game/slate/format. |
| `applicability` | Positions/actors/channels and game types to which the definition applies. `not_applicable` is distinct from unknown and zero. G11 target/rush/pass variants apply to every relevant offensive actor, not just RBs or QBs by assumption. |
| `denominator`, `actor_universe`, `window` | Exact exposure definition, who is included, and ordered periods/plays used. A share without its denominator and universe is incomplete. |
| `value`, `coverage_state`, `missing_reason` | Finite value or null and explicit coverage semantics from section 5. Retain any stored/imputed value separately. |
| `source_refs`, `transform_refs`, `clocks` | Immutable source identifiers and content hashes, producer/parser version, input identities and availability evidence. |
| `conditioning`, `uncertainty`, `sample` | Forecast estimand, any role/availability assumptions, interval/probability status and supporting sample/exposure counts. |
| `consumer_refs`, `activation` | Exact code path, field mapping and saved evidence showing whether the value is actually consumed; defaults and scope. |

An observed count is not a next-game forecast. A rolling mean is a derived historical feature unless a producer explicitly declares it a baseline forecast. Allocated fantasy-point opportunity proxies are not measured targets or carries. An Analyst statement about a replacement role is not an observed role or a calibrated probability. A descriptive matchup split is not evidence of an individual matchup assignment.

The same label can mask incompatible definitions. Resolve or report these before marking a match: pass attempts versus dropbacks; sacks versus QB hits/pressures; scrambles versus designed runs; routes versus pass-play snaps; target rate per route versus team target share; a mean of game shares versus a ratio of aggregate counts; rushing EPA/play versus EPA/rush excluding kneels. Do not infer provider definitions from column names.

## 3. Identity, grain and scope

- Player identity is `player_master_id` (canonical UUID). Keep source system, dataset and native player ID alongside it. Raw display name alone is never a join key. Unresolved IDs remain represented and queued, including volume from unmapped source actors.
- Use an explicitly resolved canonical game ID with season, season type, week, team and opponent. Preserve native schedule/event IDs and any legacy synthetic game key separately. A native `Game Info` string or generated legacy ID does not by itself prove canonical game identity.
- Team is the actor's team **at the event or decision time**, with normalized code and evidence. `PlayerMaster.primary_team` is not sufficient historical membership proof. Current membership and historical membership are separate.
- Slate, contest format, native draft-group/Game Set and roster slot are serving scope, not intrinsic player identity. Captain and FLEX share one physical player forecast; native IDs, salary and fantasy multiplier remain slot-specific. Preserve Classic, Showdown, Tiers and Single Stat boundaries.
- Team/unit rows may have no player UUID; identify them by canonical game/team/unit. Use the existing canonical DST identity where already present rather than creating fictional player mappings. Event-level records also retain provider game/play identifiers and revision identity.
- Do not collapse multiple games, regular/postseason weeks, source revisions or multiple native roles with a loose `(name, week)` or `(player, season)` join. Audit cardinality, duplicates and join losses explicitly.

## 4. Time and availability: five clocks are not interchangeable

| Clock | Meaning and audit requirement |
|---|---|
| Event/effective time | When the play/game occurred or the reported fact applies. A historical game date does not prove the data was available then. |
| Original publication / modification | When the source released or substantively revised the information. Preserve both if available; absence remains explicit. A later recapture does not rewrite original publication. |
| Observed / captured | When the application or documented source observation actually obtained the content. Preserve observation basis and immutable bytes/hash. File modification time or an operator's date assertion alone is weaker evidence, not a recovered original receipt. |
| Received / ingested | When this system stored/curated the fact. An old observation imported later is not automatically usable in a historical production replay. |
| Decision / freeze / lock | The information cutoff for feature/prediction/Analyst construction and the actual game/contest decision lock. Record both; do not substitute today's evaluation clock. |

For current inference, require the relevant observed/received inputs to be visible by the decision cutoff, source facts effective for that scope, and freshness under the consumer's actual policy. Preserve late corrections as new versions. A row's `created_at <= cutoff` is evidence about database availability, not proof of original upstream publication or original historical feature construction.

Classify historical availability evidence as `original_predecision_receipt`, `documented_upstream_release`, `retrospective_reconstruction`, or `unknown`, with supporting references. Record local ingest availability independently. A retrospectively repaired dataset may support a useful conditional evaluation, but must not be presented as an untouched pregame snapshot. The current point-in-time helper only tests an observation clock; audit the remaining clocks at each producer/consumer instead of assuming that helper proves the whole chain.

Training features for game t use only inputs available for that prediction decision. Labels may be recorded after game t, but must remain outside the feature vector and come only from completed periods before the training cutoff. Each training/evaluation fold records feature cutoffs, eligible label periods, label scoring version, source revision, fit cutoff, and fitted preprocessing. Market closing lines, realized score margin/pace/weather, postgame injury/inactive facts and actual QB usage are not pregame features for that same game. The audit can identify these risks without running a model.

Recapture and recomputation clocks do not silently renew old source facts or change their semantic identity. Execution time may be excluded from a semantic hash only when factual fields, source provenance, material clocks and live freshness checks remain separately preserved and validated.

## 5. Missingness, zeros and coverage

Use a value state appropriate to the actual evidence:

| State | Meaning |
|---|---|
| `measured` | Defined component/exposure was observed from an identified source. A measured zero requires positive evidence of complete measurement for that eligible component, not simply a missing row. |
| `derived` | Reproducible transformation of identified inputs; coverage and assumptions remain attached. |
| `estimated` / `proxy` | Numeric estimate or substitute with a declared method. Never relabel as direct measurement or claim exact parity. |
| `unknown` | Definition applies but evidence is absent, incomplete, stale, conflicted or unverified; retain the reason. |
| `not_applicable` | Definition does not apply to the actor/format/channel. This is not a zero-valued observation. |

Additionally retain sample/exposure coverage: expected and observed actors/games/plays, numerator and denominator coverage, unmapped actors, missing components, source revisions and exclusions. A complete selected lineup does not establish complete source-pool coverage. `available=true` must not be inferred from a numeric zero-filled feature.

Keep availability state distinct from football status. Verified final no game designation, roster ACT, practice participation and game-day dressing are different facts. Blank native/FD cells do not establish healthy or active. Inferred `roster_without_snap` nonparticipation is not authoritative inactive proof.

## 6. Windows, denominators and actor universe

Every historical value declares: ordered included game IDs; calendar/team/participating-game window; minimum sample; current-season versus cross-season rule; same-team versus cross-team rule; regular/postseason rule; weighting; denominator and any role conditions. `last3` without these is not an adequate definition. Declared existing legacy behavior is audit evidence, not permission to silently change it.

- Distinguish a verified inactive/DNP, a verified participant with measured zero opportunities, a bye, and a missing/unknown game. Retain these states rather than filling every omitted period with zero.
- An **active-conditional** role history may skip nonparticipation only under an explicit rule with each intervening gap verified, current role supported, and source IDs retained. Unknown gaps cannot be bridged as inactive. Cross-team/season transport requires an explicit supported contract; it is never the default interpretation of same-team role.
- An **unconditional** scheduled-game label can include verified nonparticipation as zero only if that is its stated estimand and availability measurement is complete. Do not insert those zeros into an active-conditional target or infer participation probability from them without a model.
- Player shares use the same periods and component definitions as their team denominator. Team budgets include the full source universe, reserves and non-QB trick passers where applicable, even if actors have no salary or canonical mapping. Record unattributed volume. User exclusions never shrink a football denominator or donate workload.
- Define neutral/leading/trailing, hurry-up, two-minute, short-yardage, high-wind, strong-defense and all similar bins by exact predeclared rules. Historical realized context may define a historical outcome split; only pregame-available forecasts/context may condition the next-game predictor. Label hindsight groupings explicitly.
- Report numerator/exposure counts and shrinkage design for sparse splits and interactions. Do not create hundreds of free coefficients merely because hundreds of candidate metrics exist. No fitting is authorized in this phase.

## 7. Physical accounting and field position

Conserve the relevant **physical event** budget before any salary/preferences/roster multiplier. Team pass attempts, dropbacks, targets and rushing attempts are different denominators; document no-play, penalty, spike, kneel, sack, scramble, throwaway, two-point and lateral treatment according to the source/scoring definition.

For each pass-attempt, target and rush-attempt channel, G11 partitions valid distance-to-opponent-goal observations into mutually exclusive bins on the same pre-play coordinate:

| Zone ID | Rule | Notes |
|---|---|---|
| `outside20` | distance >20 and within valid field range | Includes an offense in its own territory; not just opponent territory. |
| `six_to_twenty` | 5 < distance <=20 | Integer-yard label 6–20; declare provider precision. |
| `inside5` | 0 <= distance <=5 when a valid provider coordinate | Includes the five. Zero is accepted only if valid under that provider definition. |
| `unknown_zone` | Missing/invalid coordinate | Explicit residual; never placed outside20 by default. |

Zone counts plus unknown-zone counts equal the same channel's eligible total. A red-zone total is `six_to_twenty + inside5`, not an additional independent opportunity budget. Goal-to-go is a separate, potentially overlapping play predicate from verified down/distance semantics; not a fourth additive zone or a synonym for inside-five. Keep the units of a goal-to-go **share** explicit. A target split uses the play's line of scrimmage; end-zone target location is a different metric. Touchdowns are outcomes conditional on opportunities, not extra carries or targets.

For forecasts, player allocations must fit the corresponding team channel after explicit reconciliation, with unallocated/unknown residuals visible. A receiver target can consume one QB/team pass event; QB pass and receiver target projections must not be added as independent team volume. Passing and receiving TDs are two fantasy scorers on one physical touchdown. Reconcile incompatible source definitions visibly; do not hide mismatches by silently forcing totals to match. Preserve any declared downward reconciliation and pre-reconciliation values.

Yards and efficiency must use compatible definitions; team net passing yards may include sack adjustments absent from individual passing/receiving yards. Correlations and source reconciliation errors are not interchangeable. Captain multipliers affect salary/scoring/declared utility only, never physical counts.

## 8. Forecasts, judgments and uncertainty

Every forecast declares its next-game target, horizon and estimand: `unconditional`, `conditional_active`, `conditional_role`, or an explicit scenario condition. Preserve current availability uncertainty independently. An active-conditional count is not an unconditional expectation until a supported participation model connects them; do not invent an activation probability or turn unknown status into zero.

Record producer/model ID, version/code hash, exact features and transforms, fitted preprocessing, training window/cutoff, labels, input hash and source lineage. Historical/current inference must use the same feature meaning and preprocessing, or explicitly identify a different baseline. Reusing saved model names without full input parity is not model reuse. A simpler declared baseline is acceptable as an audited existing implementation, with its measured limitations.

Sample metadata includes games, plays/exposure, distinct actors and independent games/slates; large repeated lineup counts are not independent football samples. State whether a range is a descriptive historical spread, conditional sensitivity, prediction interval or confidence interval. Store calibration evidence and cohort/version if available. Otherwise state `uncertainty_unavailable` or `probability_uncalibrated`; no invented percentages. Preserve covariance/shared scenario dependencies where supported. Marginal P90 sums are not joint lineup P90 or simultaneous ceiling probabilities.

Analyst judgments retain source citations, canonical subjects, scope, authored and expiry clocks, mechanism, assumptions, contrary evidence and unknown likelihood. A neutral/no-op packet and a materially consumed scenario must be distinguished. A packet schema accepting a field is not proof that a producer populated it or that a serving consumer used it.

## 9. Existing storage and consumer interfaces to reuse

These are inspected entry points, not assertions that all catalog metrics exist there. Line anchors refer to the working tree at this audit start; HEAD was `56dc1ebb7f8a06075b2f2ce14aa4d574728eb6c1`, with extensive pre-existing modifications. Each worker records its own examined code hash/line span when evidence matters.

| Existing path | What it establishes / audit boundary |
|---|---|
| `backend/app/models.py:36`, `:56`, `:96` | `IngestRun`, immutable-source metadata in `SourceSnapshot`, append-only snapshot/ingest linkage. Source-specific clocks may live in metadata; do not claim every publication/receipt clock is a column. |
| `backend/app/services/source_capture.py:247`, `:253` | Pre-lock observation check and artifact verification. Retain original bytes/manifests/checksums; no recapture is needed just to inventory them. |
| `backend/app/models.py:116`, `:130`, `:179` | Canonical master, source aliases, unresolved queue. Audit actual native-ID coverage and alias uniqueness. |
| `backend/app/models.py:748`, `:774`, `:805`, `:841`, `:958` | Weekly stats/roster/snaps, participation and historical feature matrix structures. Presence of a table does not prove a field, period or complete cohort is populated. Matrix identity includes both legacy/source and canonical IDs. |
| `backend/app/product_services/point_in_time.py:11` | Existing observation-at-cutoff predicate; not a proof of all upstream clocks. |
| `backend/app/product_services/canonical_projection_inputs.py:650`, `:1388`, `:1948` | Lagged opportunity policies, canonical pregame construction and loader. Identify active policy, available flags, source filters, allocation and fallback separately. |
| `backend/app/product_services/workload_evidence.py:16`, `:80` | `workload_evidence_v2` separates original history, explicit pregame inputs and allocated proxies; serialization alone does not forecast or affect eligibility. |
| `backend/app/product_services/workload_count_forecast.py:84`, `:126`, `:273` | Existing explicit count model, conditional forecasts and frozen Prepare receipt. Audit exact channel/role coverage and residuals. |
| `backend/app/product_services/predictions.py:70`, `:943`, `:1323` | Prior-period labels, prediction context and persisted feature/model artifacts. Inspect actual feature columns, training cohorts, code/feature hashes and fallback behavior. |
| `backend/app/product_services/model_artifacts.py:38`, `:69` | Saved artifact features, calibration and reload contract. Existing zero-filling is an imputation to disclose, not proof the underlying component was measured zero. |
| `backend/app/product_services/slate_preparation.py:116`, `:226`, `:432` | Source manifest, consumption verification and saved preparation binding. Standard and count controls must reference the same declared frozen inputs when compared. |
| `backend/app/product_services/analyst_scenarios.py:28`, `:102`, `:179` | Typed scenario validation, construction and actual merged consumer. Audit material effects instead of assuming a badge or published packet changes predictions. |
| `backend/app/product_services/analyst_shadow.py:33`, `:54` | Existing frozen model/scope/variable mapping and hash validation. Preserve canonical roster and CPT identity. |

Prefer these existing run IDs, JSON evidence, manifests and artifact stores. This inventory's semantic fields may be mapped to several current records. Mark unrepresented metadata as a gap; do not add schema or dependencies to make the inventory look complete.

For every current objective, separate upstream truth from eligibility/preferences and final selection. Record `observed -> feature -> forecast/Analyst -> candidate generation -> selection -> saved explanation/export` links explicitly. Retain reports for excluded actors and their user-preference reasons. A model value that is loaded but overwritten, gated off, default-off or never referenced by a solver is not active consumption.

For later integration design only: FP means, count forecasts and Analyst judgments may share workload/source ancestry. Do not treat them as three independent votes or add them numerically without a defined scale/estimand. Keep baseline FP, workload and Analyst interfaces independently traceable; any future combiner must declare dependencies, shared candidates, full-roster accounting and final recommendation lineage. No combiner or new objective is authorized here.

## 10. Audit evidence and completion rubric

Use independent axes, not a single green/red label:

1. **Source availability:** `verified_local`, `derivable_from_verified_local`, `vendor_unavailable`, or `unknown`. `vendor_unavailable` needs actual access/license/product evidence; a missing local column proves neither global unavailability nor NFLverse coverage. Record partial cohort coverage separately.
2. **Implementation by layer:** raw, curated, feature, training, serving, Analyst, optimizer, UI/report and tests. Each gets `verified`, `partial`, `absent_after_scoped_search`, `not_applicable`, or `not_checked`, with exact evidence. Report research-only/default-off paths explicitly.
3. **Semantic match:** `exact`, `partial`, `proxy`, `different_definition`, or `unresolved_definition`, including formula/grain mismatch. Similar names are not an exact match.
4. **Availability/time safety:** proven for stated cutoff, retrospective reconstruction, leakage concern or unverified; justify clocks/receipt strength.
5. **Quality evidence:** measured validation and limits, observed data-quality defect, or `not_evaluated`. Available data is not a proven useful feature; mixed performance is not absence of data. No fitting or promotion is required to finish an inventory row.

Every positive claim cites a repository-relative file with exact line/span and symbol, SQL/table/column, or immutable artifact/run/path/hash. For nonempty data claims also record the bounded read-only query/script, scope/cutoff, result counts and representative native/canonical linkage. Do not include secrets or full sensitive rows. For absent claims record the searched files/tables/fields and limits of the search. A test name proves only its asserted behavior; separate source inspection, executed tests and actual public-workflow evidence.

Audits may inspect existing source snapshots, database metadata, bounded slices, saved models/feature lists and report receipts. No broad recapture, ingest/repair, solve, benchmark, training or runtime activation. Coordinate any necessary expensive read with the parent so one compute job remains active. Preserve original evidence and working-tree changes; append new audit records rather than editing source evidence or another worker's files.

Completion means every assigned catalog ID has a definition/grain assessment, nine-layer inventory, evidence availability and clock assessment, identified consumers or explicit dormancy, and a concise gap/dependency. It does **not** mean every metric can be sourced, forecast, modeled or recommended. Parent/High synthesis reconciles cross-group definitions and proposes the smallest next phase for user review before implementation.
