# Post-slate learning reports

`LEARN-001` turns normalized DraftKings contest results into an immutable,
user-specific slate review. In Operations, enter the DraftKings username beside
the ownership controls and select **Build Post-Slate Learning Report**. The
username is retained locally in the browser. A successful **Load Ownership (Past
Slate)** action refreshes the report automatically when a username is present.
An analysis failure is shown separately and never changes a successful result
import into a failed import.

The API equivalents are:

```http
POST /api/learning/reports
{"season": 2026, "week": 1, "slate": "SUNDAY_NIGHT", "entry_user": "example_user"}

GET /api/learning/reports/latest?season=2026&week=1&slate=SUNDAY_NIGHT&entry_user=example_user
```

Each `slate_learning_report_v1` records the exact contest and source-file IDs,
the user's normalized entry results, canonical player identities, actual points
and ownership, projection errors, symbolic-rule comparisons, relevant belief
versions, lineup and optimizer run IDs, entry assignments, portfolios, export
validations, and available OPT-007 controls. Showdown actuals and projections
retain their roster-slot weighting, so the captain multiplier is not applied a
second time. A belief is scored as predictive only when its immutable creation
time is at or before the earliest matched optimizer decision cutoff. Retrospective,
late, or missing-timestamp beliefs remain visible and unscored.

Entry assignments are the strongest lineup provenance. When an assignment is
absent, the report may associate an entry with a saved lineup only when its
canonical player IDs and captain assignment match exactly. This association is
labeled `canonical_lineup_signature`; it proves that the application generated
the same construction but does not prove which saved run was uploaded.

Reports are content addressed. Repeating a run with identical evidence returns
the same report ID for the recorded builder version. New contest files, identity
decisions, saved lineups, rule applications, beliefs, portfolios, or exports
produce a new evidence hash and a new immutable report. A report-logic change
increments the builder version and also creates a new report without rewriting
earlier output. The `partial` status is expected whenever evidence is missing.
`missing_evidence` identifies the exact entry, lineup, contest, or slate gap
instead of filling it from hindsight. Fees and payout tiers are required for
profit and ROI; old optimizer runs without matched controls keep OPT-007
unavailable.

Observed outcomes are diagnostic. A single report cannot promote or retune a
model, ownership forecast, or symbolic rule. Those changes still require their
declared time-safe evaluation and promotion gates.

## Weekly reading order

1. Check evidence coverage. `partial` describes missing evidence, not poor DFS
   performance. Resolve identity and lineup lineage first; fees and payouts are
   needed only for financial evaluation.
2. Read each entry's `top_percent`: smaller is better. Compare Classic with
   Classic and Showdown with Showdown, while accounting for field size and contest
   type.
3. Track projection MAE across several comparable slates. It is the average
   player-level miss in DraftKings points, so lower is better, but one slate is
   too noisy to justify a model change.
4. Check matched optimizer entries. A result can explain projections, rules,
   OPT-007 controls, and portfolio lineage only when it matches a saved lineup.
5. Review duplicate lineups and captain exposure separately from player outcomes.
   These measure construction and diversification decisions even when a player
   outcome was unusually good or bad.
6. Review predecision beliefs. `supported` and `contradicted` score the thesis;
   `helped`, `hurt`, and `no measurable effect` compare an exact selected
   intervention with its stored counterfactual. Retrospective and late evidence
   remains unscored.

LEARN-002 uses the next slate's frozen model/human bundle to ask only high-value
questions. LEARN-003 connects those answers and guarded belief decisions to later
outcomes. See `docs/HUMAN_OUTCOME_LEARNING.md` for timing and scoring rules.

Migration `0032_slate_learning_reports.sql` creates
`target.slate_learning_report` and refreshes the governed target-schema contract.
