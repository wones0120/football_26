# Human outcome learning

`LEARN-003` extends `slate_learning_report_v1` with time-safe scoring of human
beliefs, belief impact decisions, and LEARN-002 answers. It appends evaluations
to a new immutable report version and never rewrites the original belief,
question, answer, preview, or decision.

Belief theses are evaluated as `supported`, `contradicted`,
`no_measurable_effect`, or `unscored` from the realized player result and the
matched pre-lock projection residual. This describes whether the stated view was
directionally consistent with the outcome. It does not claim that an unapplied
belief changed a lineup.

Approved and rejected belief impact decisions use their exact stored baseline
and proposed projection means. LEARN-002 answers use the exact model, human, and
resulting-modifier values stored with the question. The selected choice is
compared with its counterfactual and classified as `helped`, `hurt`, or
`no_measurable_effect`; error differences within 0.25 DraftKings points are
treated as no measurable effect. An explicit `no_change` answer is retained as
no measurable intervention.

Only answers and impact decisions recorded at or before the earliest matched
optimizer decision cutoff are scored. Retrospective beliefs, unanswered
questions, late decisions, missing canonical outcomes, and missing
counterfactuals remain `unscored`. Showdown CPT outcomes are divided by 1.5 when
compared with the underlying player projection, avoiding a second captain
multiplier.

Each report summarizes belief theses and intervention effects overall, by belief
scope, and by confidence band. A report can diagnose one slate, but policy or
model changes still require repeated comparable outcomes and the existing
approval gates.
