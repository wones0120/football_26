# Versioned DST scoring corrections

`backend/app/product_services/dst_scoring_reconciliation.py` implements `draftkings_classic_dst_event_scoring_v1` for research label repair. `score_game` requires a complete final NFL/nflverse play-by-play game, expected canonical game/teams, an existing canonical DST UUID map and optional independent final scores. It refuses missing coverage, identity conflicts, duplicate plays, missing statistical counters and inconsistent score timelines. A computed zero remains a valid observation.

The scorer retains each contributing play ID and separates sacks, INTs, opposing fumble recoveries, defensive and special-teams TDs, safeties, blocked kicks, conversion returns and charged points. Offensive recovery after an opponent's defensive possession can earn the team's DST a recovery. TDs are counted once. Allowed points are attributed per event; XP after a defensive TD still counts, rather than subtracting seven points per return TD. Replay chronology uses `order_sequence`, not numeric `play_id`. Explicitly nullified plays do not become observed statistical events. Safeties against the offense are not charged points. Scoring is independently defined by the retained DraftKings primary scoring guide and possession notes.

`apply_research_corrections` creates a separate dataset and old→new receipt for every physical row. It requires canonical UUID, team, opponent and game agreement; unresolved identities are reported rather than joined by player name or dropped silently. Original matrix rows are not rewritten. Logical dataset hashes cover contract/classification/rows/receipts; source snapshot checksums additionally cover the complete version metadata/file.

The existing historical aggregate builder now refuses completed-date games with missing final scores or absent weekly-stat team coverage, preventing those unknown outcomes from becoming zero labels. A conservative scheduled-kickoff+24h boundary leaves future target placeholders intact. Postponed/uncertain games block pending final evidence. The legacy aggregate calculation is still approximate; exact corrected labels are a separately selected research input, not automatically activated in normal training.

The [October15 audit](../../research/dst_scoring_repair_20261015/v1/REVIEW.md) reconciles all 33 original flags and the wider affected coverage. All 148 unique 2026 team/week records were checked against complete event data and all 79 official gamebooks: 114 totals change, 34 match, including six valid original zeros. Including duplicate slate copies and neighboring seasons, 319 of 848 physical matrix row versions are corrected. No unresolved mappings remain in that correction version. The exact matched ablation cohort has 804 deduplicated rows.

Published correction datasets are append-only `source_snapshot` artifacts. The full physical-row version is `e81b5772-5d81-505b-a44c-0660480098c4`; the exact experiment cohort is `b1f073be-94d9-5702-806b-82f4448d80b8`. Receipts retain immutable paths, source hashes, original row IDs, new values, scoring contract and code hashes. The original database matrix, previous reports and live projections are preserved.

Reproduction uses the captured inputs:

```sh
PYTHONPATH=. .venv/bin/python research/dst_scoring_repair_20261015/v1/reconcile.py
# Official PDF extraction uses the existing bundled Python/pypdf runtime:
# <bundled-python> research/dst_scoring_repair_20261015/v1/verify_gamebooks.py
PYTHONPATH=. .venv/bin/python research/dst_scoring_repair_20261015/v1/rerun_ablation.py
PYTHONPATH=. .venv/bin/python -m pytest backend/app/tests/product/test_dst_scoring_reconciliation.py -q
```

The rerun keeps frozen features/model/splits/seed and compares both feature arms on the same corrected truth. It also separates the effect of replacing training labels. Opponent-QB features still fail to improve DST point MAE in every evaluated block. Historical source clocks and starter-decision archives remain incomplete; these are retrospective chronological experiments, not fresh prospective validation. Live projection values/models/features remain unchanged pending explicit review.

No migration, dependency, UI change, export or contest entry was introduced.

## Corrected-label production retrain (October 16)

The [production-path comparison](../../research/dst_retrain_20261016/v1/REVIEW.md) retains the shared v4.2 gradient boosting model and its 27 explicit features. Opponent-QB features remain excluded. On 446 identical corrected outcomes, chronological incumbent-policy refits score MAE 4.3225 versus 4.4484 with corrected training labels (+0.1259, week-cluster 95% interval +0.0287 to +0.2374). This exceeds the frozen +0.10 tolerance, so no candidate was promoted and no Sunday live projections were refreshed.

`dst_training_labels.py` provides explicit candidate-only selection from a checksum-verified scoring snapshot. It rejects missing labels, nonfinite values, wrong scoring versions and canonical/source identity mismatches; verified zeros remain valid and target-week placeholders remain untouched. It is not wired into live Prepare. Legacy missing game IDs remain explicit; source row ID plus canonical UUID/team/opponent/week matches against the verified correction and its independently checked game identity.

The preserved rejected shadow artifact includes source/feature/training/code hashes. The exact frozen Sunday Main comparison changes only DST means: 13/20 rank numbers change, while the Optimal $49,800 Stafford/Kyren/Henry/Puka/Odunze/Tate/Higbee/Wan'Dale/Panthers lineup remains the same (133.1430 to 134.9537 shadow points). This is a model impact illustration, not improved historical performance or a live refresh. Existing readiness remains preliminary and final entry is not cleared.

Reproduce with `research/dst_retrain_20261016/v1/validate_candidate.py`, `shadow_impact.py` and `diagnostics.py` against the retained captured artifacts. The live pointer was never changed, so rollback is unnecessary. Any future promotion must first pass a separately declared comparison and integrate exact event scoring into future historical input builds; no automatic fallback to approximate or missing-as-zero labels should be introduced.


## Dedicated DST research follow-up (2026-10-16)

The [dedicated DST experiment](../../research/dst_dedicated_20261016/v1/REVIEW.md)
rebuilds verified preweek defense/opponent histories and canonical home flags,
keeps missing values explicit, and fits DST separately from offense. The frozen
three-learner chronological comparison failed its MAE improvement gate:
4.32247→4.35703 on the same446 corrected outcomes. RMSE, rank correlation and bias
improve, but no live activation occurs. Full-history inner selection chooses a
5-point median for all20 Sunday defenses; the matched $49,800 roster is unchanged.
Current live pointers/means and original historical evidence remain preserved.


## Inactive feature-pipeline repair (2026-10-16)

[Pipeline report](../../research/dst_pipeline_repair_20261016/v1/REVIEW.md): the
actual DST matrix branch wrote missing home/history fields, then canonical
preprocessing converted those to zeros. The new explicit `dst_candidate_context`
requires `persist=False` for matrix generation. A shared verified adapter repairs
training/prediction fields, and `load_dst_candidate_inputs` requires corrected
labels explicitly. `score_dst_candidate_bundle` produces only a read-only DST
overlay and rejects scoring within its training window. No live route or default
activates this path.

The repaired dedicated policy passes the frozen retrospective noninferiority
criteria: MAE4.32941 versus incumbent4.32247 and corrected/unrepaired4.44840.
This is not proof of better incumbent accuracy; paired uncertainty includes no
gain. Shared/history alternatives fail. The selected full-history artifact is a
5-point median for all20 Sunday defenses, so ranking remains unvalidated. All
matched lineups remain the same $49,800 roster. Current live pointers/means are
verified unchanged; original source clocks and prospective validation remain
incomplete. Candidate matrix/feature/model artifacts stay separate from live.


## Ranking stability follow-up (2026-10-16)

[Ranking report](../../research/dst_rank_stability_20261016/v1/REVIEW.md): the
full-history median wins the old three-week MAE selector by just0.0026points over
the tree. Repaired inputs vary and artifact inference matches; flat forecasts
are a selection/objective outcome. Two predeclared alternatives (fixed shrunk
ensemble and guarded pairwise selector) fail ranking reliability on five rolling
2026weeks. Tie-aware top5 avoids arbitrary favorable team tie breaks. Historical
outcomes are explicitly reused retrospective evidence, and historical capture
clocks remain incomplete. All20Sunday shadow scores and matched rosters are
preserved; every arm keeps the same $49,800 roster. No alternative is promoted,
and live pointers/projection means remain unchanged.


## Operational support without model promotion

[Verified DST input support](dst_feature_support.md) now runs in the normal
canonical loader when a checksum-pinned support manifest is configured. It writes
a separate corrected-label/home/history artifact, records source/run lineage,
and preserves all incumbent numerical input cells. Fitted artifacts declare
`incumbent_dst_matrix_legacy_v1`; explicitly candidate-tagged frames cannot be
silently serialized under that contract. Old artifacts remain compatible.
Support `ready_inactive` means inputs are prepared, not that a defense model was
promoted. Current source freshness guards remain authoritative, and failed
ranking validation still blocks a replacement forecast policy.
