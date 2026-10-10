# Classic production decision — October 10, 2026

Retain the current Classic production projection, generation and recommendation
policies. No tested challenger has established better GPP paid finishes. This is
the current deployment decision, not a pending request for approval.

| Change | Evidence | Decision |
| --- | --- | --- |
| One recommendation from validated candidates | Existing app path; targeted checks pass | Already live |
| Imported-outcome shadow comparisons | Live API exposes registered experiments | Already live |
| Mean-guarded upside ranker | Primary historical comparisons fell from 2/3 and 3/3 paid finishes to 0/3 in each week | Reject promotion |
| Mean-led generation and stack-template rotation | Both retained the original Sunday Main recommendation | No demonstrated reason to replace production |
| Current-team workload repair | Improved accounting; prospective outcomes pending and historical source parity insufficient | Keep in shadow |
| Captain expanded shortlist | Higher projected mean; paid-finish results pending | Keep in shadow; not Classic evidence |

The configured opportunity policy remains `legacy_v1`. The saved Sunday Main
recommendation uses `gpp_projection_first_recommendation_v1`; its recommendation,
projection reference and strategy hash match the frozen control. No production
weights, model settings or live choices were changed in this review.

Shadow mode preserves pregame control and challenger choices. Importing standings
or account entry history refreshes comparisons automatically. The live API still
reports `pending_actuals` for Sunday Main workload and both Captain experiments.
There is no automatic DraftKings results download, automatic promotion, or claim
that a single winning slate establishes a better policy. Paid finishes are the
primary outcome; returns require sufficient payout evidence and upside is
reported separately.

Remaining Classic work is evidence and validation: obtain timestamped workload
inputs, import postgame results, evaluate projection calibration and paid finishes
on additional untouched slates, and validate opponent-field/payout modeling before
presenting paid probabilities or expected returns. Refresh slate preparation and
availability before actual entry; a completed software test is not final player
availability clearance.

Validation for this review: 38 targeted recommendation, Classic ranking-shadow,
workload-shadow and outcome-learning tests passed. The live comparison endpoint
responded, and the user's latest Sunday Night optimizer job was completed.

Supporting reports: [ranking](current_classic_gpp_ranking_audit.md),
[generation](sunday_projection_generation_results.md),
[workload](sunday_workload_shadow.md), and
[outcome tracking](gpp_shadow_outcome_tracking.md).
