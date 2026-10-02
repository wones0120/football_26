# Week 3 optimizer effectiveness review

Generated from the saved 2026 Week 3 optimizer runs, canonical contest player
observations, and normalized DraftKings standings. This review is descriptive;
it changes no projection, ownership, correlation, candidate, or selector weights.

## Slate rollup

The winner and top-1% columns show ranges across fully scored imported contests
on the slate. Cash is unavailable because none of the imported contests has a
saved payout tier. “Best entered” covers all imported entries, including entries
without a canonical match to the named optimizer run.

| Slate | Best generated actual | Best selected actual | Best entered actual | Winner range | Top-1% range | Cash | Selection regret |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Thursday Night | unavailable: original candidate pool absent | 131.22 | 131.22 | 147.98–151.10 | 144.33–145.93 | unavailable: no payout tiers | unavailable |
| Sunday Main | at least 157.00 among 192/212 scoreable | 139.20 | 137.10 across all entries; 117.86 from the matched run | 210.74–233.90 | 184.62–190.04 | unavailable: no payout tiers | at least 17.80 |
| Monday Night | pending: no imported standings | pending | pending | pending | pending | pending | pending |

Two Thursday 24-entry contests have an incomplete scored field, so the Thursday
winner/top-1% range uses the other three contests. The Thursday optimizer run
`efd33643-c45f-4ab9-be52-1b7bea7df489` saved three selected lineups with
actuals of 131.22, 99.52, and 111.82. Only the 99.52 entry has a verified
canonical match to that run. Other Thursday entered scores are 131.22, 130.17,
and 113.98 twice; four contests lack resolved player identities, so a matching
score does not establish lineup execution. The run has no complete original
candidate pool and was not reconstructed from later inputs.

Thursday candidate attainment and selection regret are therefore unavailable.
The strongest selected score, 131.22, is below the top-10% line in each of the
three fully scored contests but above each top-20% line. Among submitted entries,
131.22 in contest 196031353 and 130.17 in contest 196032992 reached top 20%;
none of the entered scores reached a known top-10% line. Cash attainment remains
unavailable.

The structured audit separately scores **23 other Thursday** and **four other
Sunday** completed runs with original saved candidate pools. They are research
runs without verified entry links, so their best outcomes are not treated as
the submitted portfolio. It lists **89 other Thursday** and **13 other Sunday**
completed runs whose original generated pools are unavailable. No later replay
is substituted for them.

## Sunday Main: generated versus selected

Run `2ef9ee7e-d2a1-4cc4-bf88-b89e5f40a2c5` saved **212 original candidates**
and five selected lineups. The original pool is intact. Four candidate players
have no resolved DK actual in any imported Sunday contest: Caleb Douglas, Bub
Means, Mason Taylor, and Sincere McCormick. This leaves 20 candidates unscored.
The best **scoreable** candidate reached **157.00** and was ranked **54th
pregame**. Its true actual rank among all 212 lies between 1 and 21; the true
pool best could be higher. No unscored player is assumed to have zero points.

| Selected lineup | Pregame candidate rank | Actual points | Actual-rank bounds among 212 | Entered from this run |
| --- | ---: | ---: | ---: | --- |
| 1 | 1 | 117.86 | 84–104 | yes, in two contests |
| 2 | 3 | 117.60 | 88–108 | no verified match |
| 3 | 7 | 113.50 | 111–131 | no verified match |
| 4 | 10 | 139.20 | 23–43 | no verified match |
| 5 | 58 | 96.46 | 173–193 | no verified match |

The strongest selected lineup scored **17.80 fewer** points than the strongest
scoreable generated candidate. The matched entered lineup scored **39.14 fewer**
points than that generated candidate, and **21.34 fewer** than the strongest
selected lineup. These are lower bounds on generation-to-selection/entry regret
because 20 generated candidates remain unscored. The separate 137.10 Sunday
entry lacks verified optimizer-run lineage; it is included in the slate entry
total but not attributed to this run.

The 157.00 candidate had a pregame objective of **5.3529**, compared with
**5.4383** for the selected rank-1 lineup. Its projected mean was **134.78**
versus **135.96**, and its summed player ceiling was **235.70** versus **239.19**.
Its objective was **0.08536** lower: the summed-ceiling component contributed
**−0.04682**, context **−0.02628**, correlation **−0.01648**, and mean
**−0.01643** relative to rank 1, partly offset by a **+0.02064** QB-stack
component. Projected ownership was 61.31 versus 56.77, but the saved ownership
objective contribution was zero. These terms explain the saved rank; they do
not prove what caused the postgame loss.

Across the 192 scoreable candidates, selector score versus actual points had
Pearson **−0.013** and Spearman **0.027**. Projected mean had Pearson **0.075**
and Spearman **0.110**; summed player ceiling had Pearson **0.210** and
Spearman **0.257**. These are one-slate diagnostics from a restricted candidate
pool, not evidence for changing weights. Selector top-K captured best actuals
of 117.86 (K=1/3/5), 146.90 (K=10), and 147.40 (K=20; 19 scoreable).

## Field thresholds and attainment

Thresholds are the actual score at the ceiling of each field-percent rank.
Every entry tied at a threshold is counted in attainment. Cash cannot be
calculated without a paid-rank cutoff; percentile lines do not require payout
data.

| Sunday contest | Winner | Top 0.1% | Top 1% | Top 5% | Top 10% | Top 20% | Scoreable generated reaching top 20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 195921989 | 233.90 | 202.90 | 188.94 | 171.60 | 162.14 | 149.94 | 7 |
| 195921990 | 219.20 | 208.02 | 190.04 | 173.00 | 164.16 | 152.18 | 4 |
| 195921991 | 210.74 | 199.94 | 184.62 | 169.64 | 160.04 | 147.80 | 8 |

Of the 192 scoreable Sunday candidates, **zero** reached top 10%, top 5%, or
top 1% in any of the three contests. Zero selected or entered lineups reached
those thresholds. The best scoreable generated lineup missed the top-10% lines
by **3.04–7.16** points and the top-1% lines by **27.62–33.04**. Generated,
selected, and entered cash counts are **unavailable**, not zero.

| Thursday contest | Winner | Top 1% | Top 5% | Top 10% | Top 20% | Field status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 195943257 | 151.10 | 145.33 | 137.93 | 132.62 | 126.08 | complete |
| 196031353 | 147.98 | 145.93 | 137.93 | 135.02 | 128.08 | complete; field player identities unresolved |
| 196032992 | 150.53 | 144.33 | 137.73 | 133.08 | 126.82 | complete; field player identities unresolved |
| 196034096 | unavailable | unavailable | unavailable | unavailable | unavailable | incomplete scored field |
| 196034453 | unavailable | unavailable | unavailable | unavailable | unavailable | incomplete scored field |

The structured report also includes actual-score percentiles, per-entry point
gaps to each line, tie-aware candidate attainment, and top 0.1/1/5% field
construction frequencies. All three Sunday contests have canonical identity
coverage for their top 5% lineups (793/793, 407/407, and 893/893 including
ties). Thursday's largest contest resolves 449/449 top-5% lineups; two other
fully scored contests resolve 0 top-5% lineups because their ownership identity
observations remain unresolved. Salary/game context is used only when its
snapshot predates the matched optimizer cutoff.

One descriptive construction difference is large: Geno Smith appeared at QB
in **87/159, 48/80, and 84/179** top-1% field lineups across the three Sunday
contests, versus **4/212** generated rosters and **0/5** selected. All five
selected lineups had no opposing bring-back; the top-1% field contained many
QB+2 lineups with one or two bring-backs (for example, 25 plus 16 of 80 in
contest 195921990). This is a retrospective frequency comparison, not a
recommendation to force Geno or a bring-back in future slates.

## Pipeline diagnosis

- **Candidate generation:** The strongest observed Sunday candidate, 157.00,
  fell below every contest's top-10% line. This is evidence that the *scoreable*
  pool lacked a near-winning lineup. The 20 unscored candidates prevent a final
  generation-ceiling judgment.
- **Candidate selection:** A 157.00 lineup existed in the saved pool at pregame
  rank 54, while the best selected scored 139.20. The selector's Spearman 0.027
  on scoreable candidates supports a ranking concern for this slate.
- **Execution:** Of the five saved selected Sunday lineups, the strongest
  scored 139.20; the verified entered lineup from this run scored 117.86. The
  137.10 entered lineup has no verified run match, so its origin remains open.
- **Projection and ownership:** The mean/P90 correlations and frozen Week 3
  ownership audit warrant separate chronological review. This report does not
  isolate a causal projection or ownership failure from one slate.
- **Portfolio concentration:** Selected roster and game exposures are retained
  in the structured report. The 0/5 selected Geno exposure and 5/5 selected
  no-bring-back construction contrast with top-field frequencies, but their
  contribution to the score gap is not isolated by this single-slate comparison.
- **Outcome variance:** It remains possible; the saved evidence does not justify
  classifying it as the sole cause.

The most useful next experiment is a **prospective, frozen-pool selector
comparison** across multiple completed slates: retain each original candidate
pool, shadow-rank the same candidates by the existing selector and by the
already saved mean and summed ceiling, then compare top-K actual capture and
field attainment without changing production weights. Complete the four missing
Sunday actuals first so the Week 3 baseline is exact.
