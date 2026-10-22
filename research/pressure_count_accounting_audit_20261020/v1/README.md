# Pressure-count source cohort and accounting audit

Across 544 matched 2025 team sides, the scored player labels omit **1,892 known source pass attempts and 1,143 rushes** relative to the existing source-role-filtered weekly budgets. Positive omitted-count gaps occur on 91 pass and 196 rush sides. Matching totals on other sides do not prove a complete roster.

There is also error inside the scored cohort. Tree pass/rush biases there are −2.113/−3.657 per side, independently of omitted mass; team biases are +0.775/+0.220. These exactly account for player-minus-team prediction gaps −6.366/−5.978. Neural counterparts are in the machine receipt. This does not identify individual omitted actors or prove all bias comes from log transform.

The player model uses log1p squared-error heads with expm1 inversion. That is not an unbiased arithmetic expected count. Global pass MAE is dominated by non-QB zeros; QB tree is essentially tied with history and neural worse. Do not forbid valid trick-pass or QB-target observations by position. Any genuine correction must preserve channel/role meaning and unknown/cold-start actor mass.

Targets share passing events. On 78 sides, retained actual targets exceed retained actual passing attempts, while none exceeds the source-role-filtered team pass total. A missing passer cohort makes retained-only conservation misleading. Predicted target totals cross independent predicted team passes on 29 tree / 57 neural sides; a shared expected budget is not enforced by independent point heads. Comparisons to realized actual budgets in the detailed receipt are forecast-error diagnostics, **not physical impossibility tests**.

The smallest next step is an explicit per-side source/scored/excluded/unknown ledger accompanying A’s prior-only context adapters, then a declared compatible mean/count or conditional allocation estimand. Never infer omitted mass belongs to retained players, scale all predictions to fit totals, or turn missing participation/stat rows into zero. Existing vacancy allocation is sourced conditional sensitivity, not permission to invent replacements.

`AUDIT.json` names exact immutable parent refs, source cohort code, seven repair constraints and the bounded next proof. `SAVED_PREDICTION_ACCOUNTING.json` binds all four saved prediction refs and decomposes every side. Only these ~11.4MB saved predictions were decoded (0.044s); no matrices/model bundles/raw sources/fits/runtime edits. Inspected 2025 outcomes remain retrospective.
