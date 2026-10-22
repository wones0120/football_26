# Retained roster/depth feature extraction

`retained_role_source_features_v1` reads two actual indexed `SourceSnapshot` records, calls the existing byte/manifest verifier, and checks exact season/week, row cardinality, observed/received cutoffs and REG roster rows. It makes no network call, ingest, model fit, forecast or settings change. Canonical mapping uses native source IDs only; ambiguous/unresolved aliases remain explicit review requests.

Every provider roster actor is retained before salary filtering. Source depth-order and source unit/slot are preserved separately from the weekly roster position. Explicit provider representations DB→CB/S, LILB/RILB→LB, FB→RB and LB/DL hybrid fronts are supported without rewriting the original source position. KR/PR/holder slots are retained as separate non-primary role exclusions, not mistaken for unresolved player identities or used to promote the primary offensive role.

The actual immutable inputs were captured before the original23:00Z boundary. This new derivation occurred after lock and is marked descriptive/non-serving. Current mapping observation and derivation do not become original pregame feature availability. No raw/source artifact was overwritten.

Actual corrected output:168 canonical roster actors,444 scoped roster/depth facts,123 known literal primary-depth orders,9 official game designations and1 known sourced-QB availability. Two source-native depth actors are unresolved in the roster and retained for identity review; requests are emitted, not yet persisted by this pure feature adapter. The first retained-roster/depth adapter revision produced93known depth values; the corrected provider representation revision preserves that immutable artifact and creates a new SHA record.

The NFLverse roster source universe is exhaustively processed, but independent official full-team roster completeness is not certified. Consequently the adapter does not set `complete=true`, and exact team unavailable counts remain unknown. ACT roster membership is not healthy/game-active evidence. Practice dates and documented restrictions remain absent from the verified input; they are not invented from retrieval clocks or missing cells.

42 tests cover the availability feature and source adapter, including actual SQLite `SourceCaptureService` byte/manifest snapshots, tamper/scope/future/cardinality/alias guards, real provider position forms, current rank derivation, special-team role separation and all prior availability invariants. No model/optimizer consumption is implied.
