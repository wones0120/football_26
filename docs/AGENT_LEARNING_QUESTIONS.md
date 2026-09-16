# Targeted learning questions

`LEARN-002` turns a frozen `digital_twin_variants_v1` bundle into a short list of
questions worth interrupting the user for. In the Digital Twin, first freeze the
**Model × Human × Combined** bundle, then select **Find high-value questions**.

The versioned `agent_question_voi_v1` policy has two triggers:

- `model_human_disagreement` requires an approved human projection multiplier
  at least 4% from the model and a value-of-information score of at least 25.
- `high_value_uncertainty` requires an unchanged player with a model mean of at
  least 8 points, a P90-minus-P10 range of at least 12 points, and a score of at
  least 40.

The disagreement score combines the point difference and projection range. The
uncertainty score combines the range and projected mean. Priority sorts human
disagreements ahead of ordinary uncertainty, then the policy retains at most five
questions. Identical policy inputs produce the same evidence hash and question
ID, so repeated generation is idempotent.

Disagreement questions accept **Use model view**, **Keep human view**, or **No
change**. Uncertainty questions accept **Lean upside**, **Lean downside**, or
**No change**. Every response is final for that question. The stored resulting
modifier is an audit proposal marked `recorded_not_applied`; it cannot alter the
base projection or an active variant. Applying a view still requires the existing
belief impact preview and explicit approval workflow.

Migration `0033_agent_learning_questions.sql` creates `target.agent_question`
and `target.agent_question_answer` and refreshes the governed schema contract.
