# Classic construction research application

October 4, 2026. This bounded application change applies the taxonomy and questions in
[the historical study](docs/classic_historical_lineup_construction_study.md), without
retuning projections, scoring weights, default constructions, or portfolio allocation.

The study's primary success population is **top 10%**, not first place or ROI. It covers
15 contests across 10 distinct slates. Entry limits and payout categories are unknown;
qualified pre-lock historical markets cover only three slates. Historical ownership is
realized contest ownership. These are descriptive associations, not a validated
Large-GPP strategy, causal scoring parameters, or an optimizer backtest. The application
and downloadable construction summaries repeat these limitations.

## Application behavior

- The existing **Enforce single TE (exclude TE from FLEX)** checkbox explains that on
  excludes TE FLEX; off permits, but never requires, a second TE. Its explicit choice
  now survives browser reloads. The existing default remains on. No saved optimizer
  request or user setting was changed. Both Run Optimizer and the weekly pipeline
  still serialize `enforce_single_te` from this same control.
- Classic reports and readable HTML downloads count actual selected rosters: natural
  FLEX, full positional composition, QB-team offense including QB, same-team WR/TE,
  same-team RB presence, offensive bring-back counts/positions, QB-game players,
  secondary opposing games, true unrelated one-offs, and maximum team concentration
  including DST and offense only. Selected portfolio distributions use those counts.
- **Review construction tradeoffs** is a separate, explicit action on a completed
  saved Large-GPP report. Opening or downloading a report does not solve anything.
  The endpoint is `POST /api/optimizer/results/{job_id}/construction-review?entry=1`.
  It uses the saved eligible canonical Player frame, saved resolved config, and the
  current choice from the existing single-TE checkbox. A difference from the saved
  single-TE setting is explicitly labelled; every other saved setting stays pinned.
  It uses the shared production `_build_lineup` implementation. It neither refreshes inputs nor
  saves/selects a portfolio. The original request and saved run remain immutable.
- Reviews compare RB/WR/TE FLEX, exact one/two WR/TE stacks, zero/one/two offensive
  bring-backs, QB + two WR/TE + one bring-back, opposing RB, same-team QB/RB,
  unrelated one-offs and secondary opposing mini-stacks. The selected step's
  minimum stack template remains active. Conflicting exact-count requests are
  explained as template exclusions; QB/RB without WR/TE is explained as a strategy
  exclusion. TE FLEX is explained as a user-preference exclusion when the reviewed
  single-TE choice is on. Turn off the existing checkbox and explicitly review again
  to compare TE FLEX on the same frozen input without generating a portfolio.
- Individual alternatives retain lineup constraints and applicable player bans,
  locks and risk groups. Replacement alternatives additionally retain all other
  entries, player/global/elevated exposure budgets, minimum exposure requirements,
  overlap and primary-game limits, and receive independent portfolio validation.
  An underfilled saved portfolio cannot receive a certified full replacement.
- Mean, **summed marginal P90 (NOT a lineup percentile)**, composite objective,
  numerical components, structural rule contributions, actual roster, solver and
  solution status, construction restrictions, input checksums and source fingerprints
  are inspectable. Combined infeasibility is reported without inventing a minimal
  binding constraint set. Missing inputs are unavailable; unsolved cases are not searched.

No broader candidate universe is retained by production Large-GPP: it sequentially
accepts the selected entries. These summaries are selected-roster distributions,
not discovery coverage. Five absent selections cannot establish that a family is
uncompetitive. The review searches a finite set of restrictions, not an exhaustive frontier.

The review retains current soft scoring and fixed full-frame normalization. The existing
**Compare with rules disabled** control removes context and correlation/format scoring,
while retaining that selection step's hard constraints. It is a joint soft-rule ablation,
not a same-rule construction comparison or independently playable portfolio.

Old saved implementation hashes intentionally cease to match after source edits. The
review explicitly labels current-production-on-saved-inputs when this happens, preserves
both saved and current lineage, and does not claim old replay parity. Standard exact
replay still enforces its implementation/checksum guard.

## Reachability audit

Default Large-GPP templates `(1,0), (1,1), (2,0), (2,1)` are **minimum** WR/TE and
RB/WR/TE opponent counts. Neither count is an exact roster label. Team/game limits,
salary, risk, player eligibility and portfolio budgets may restrict any family.
The candidate policy still ranks/filters players by position and team, with existing
safety addbacks. A removed player is not evidence against an entire construction family.

| Construction | Production treatment | Deterministic evidence and interpretation |
| --- | --- | --- |
| RB FLEX / three RBs | Reachable | Shared solver fixture produces legal three-RB rosters; single TE does not exclude RB FLEX. |
| WR FLEX / four WRs | Reachable | Shared solver fixture and all five saved reference entries. |
| TE FLEX / two TEs | Explicit user exclusion when single TE is on | Shared solver fixture reaches it with off; otherwise reports preference exclusion without relaxing another constraint. |
| QB + one WR/TE | Reachable on minimum-one template steps | Fixture exact-one solve and reference entry 5; minimum-two steps intentionally exclude exact one. |
| QB + two WR/TE | Reachable | Fixture and reference entries 1–4. Minimum-two may also produce three when team cap permits. |
| Zero/one/multiple offensive bring-backs | Reachable, depending on step minimum | Fixtures reach each; reference includes 0, 1 and 2. Exact zero conflicts with a minimum-one step. |
| Opposing RB bring-back | Reachable, classified separately from WR/TE | Fixtures and reference entries 1–3. Structural membership does not imply a pass-catcher bonus. |
| QB + same-team RB with WR/TE | Reachable | Fixture and reference entry 5. Team cap 3 allows QB + RB + one WR/TE. |
| QB + same-team RB without WR/TE | Intentional strategy exclusion | Minimum-one WR/TE stack; RB does not replace a pass catcher. No new study-derived prohibition or penalty. |
| Standalone true unrelated one-offs | Reachable | Fixtures and every reference entry; DST relationships excluded from the true-one-off count. |
| Secondary opposing mini-stacks | Reachable | Fixtures and reference entries 4–5; no mandate or new bonus. |
| Four players from one team | User exclusion with cap 3; optional cap 4 remains available | Existing team control includes DST; neither historical frequencies nor this change override it. |

One confirmed defect was corrected: when a QB had **no** eligible same-team WR/TE or
opponent bring-back option, the old builder omitted its positive minimum constraint.
It now explicitly excludes that QB for the affected solve. Named guards preserve all
other constraint names/coefficients. This closes a minimum-enforcement bypass; it does
not lower the strategy floor, alter defaults, or change scoring. The archived baseline
selected rosters and objective scores remain identical; feasible-region fingerprints
match after adding precisely these documented guards to the old captured model.

## Saved five-entry reference

`0400342a-d274-4ff5-8667-c729652b4a1f` was inspected read-only, without replaying,
regenerating, or running its alternatives. Saved controls are 5 entries / 80% exposure /
primary-game cap 3 / overlap 5 / team cap 3 / game cap 5 / single TE on.

| Entry | FLEX / composition | QB-team offense / WR-TE / same RB | Offensive bring-backs | QB game incl. DST | Secondary opposing games | True unrelated one-offs | Max team incl. DST / offense |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | WR / QB1 RB2 WR4 TE1 DST1 | 3 / 2 / no | 2: RB + WR | 5 | 0 | 2 | 3 / 3 |
| 2 | WR / QB1 RB2 WR4 TE1 DST1 | 3 / 2 / no | 2: RB + WR | 5 | 0 | 2 | 3 / 3 |
| 3 | WR / QB1 RB2 WR4 TE1 DST1 | 3 / 2 / no | 2: RB + WR | 5 | 0 | 2 | 3 / 3 |
| 4 | WR / QB1 RB2 WR4 TE1 DST1 | 3 / 2 / no | 1: TE | 4 | 1 | 2 | 3 / 3 |
| 5 | WR / QB1 RB2 WR4 TE1 DST1 | 3 / 1 / yes | 0 | 3 | 1 | 1 | 3 / 3 |

Three CIN–JAX and two DAL–HOU primary-game appearances are portfolio counts.
They are distinct from players from one game inside an entry and players from one team
inside an entry. DST counts in the latter two limits. Natural FLEX follows position
counts, not arbitrary assignment of interchangeable roster slots.

RB FLEX was legal but unselected in these five entries. Read-only inspection confirms
that saved rules-disabled controls for entries 1 and 2 contain three-RB alternatives. Those controls do not
prove same-rule relative value or replacement feasibility. TE FLEX was forbidden by
explicit preference. Other absent families are not assumed infeasible or uncompetitive.

Ownership audit: the frozen eligible frame contains 154/154 ownership values, with
range 0–26.021558 in percent points (0–100). The loader uses
`target.ownership_projection`, forecast run `a1391496-f291-4cd2-814b-78f6c2652db2`.
The model clips projected ownership to 0–100 and ownership calculations divide by 100.
This is forecast ownership, not the historical study's realized contest percentages.
Coverage does not establish calibration or predictive validity. No floor, quota,
contrarian requirement, or ownership scoring change was added.

## Evidence to action

| Evidence/question | Bounded action | Scoring/default implication |
| --- | --- | --- |
| FLEX variety | Permit legal alternatives through the existing control and shared solver; inspect counts | No allocation quotas |
| QB + two pass catchers + one bring-back | Retain reachability; inspect exact counts and template restrictions | No bonus derived from reported lift |
| Opposing RB bring-backs | Count as offensive bring-backs; inspect existing receiving-role/market-conditioned rule contributions | Not automatically equivalent to opposing WR/TE |
| Same-team QB/RB | Retain additive stack reachability; document existing WR/TE minimum | No new blanket prohibition or penalty from this study |
| Four-player team constructions | Preserve optional team cap 4; respect user's cap 3 | No claim that max-team-three is universally superior |
| Secondary mini-stacks | Available and explicitly countable | Not mandatory; no new automatic bonus |
| Game totals | Keep qualified scope visible | No weight change from three covered slates |
| Ownership | Audit forecast source/units/coverage before comparison | No ownership floor or contrarian quota |

## Validation and limits

Synthetic tests cover legal distinct identity, each natural FLEX, exact stack/bring-back
families, opposing RB, same-team QB/RB, one-offs, mini-stacks, TE explicit exclusion,
unchanged salary/team/game/risk/overlap/exposure conditions, component-to-solver sums,
API serialization/persistence, app/replay parity, unavailable/not-searched statuses,
no diagnostic solve on GET, and unchanged default weights. The true-one-off and DST
semantics match immutable research roster exports across all 15 contests; outcomes
are never used to tune current inputs. The immutable app baseline checks exact selected
rosters/objectives and the documented feasibility guard delta.

Validation: 148 targeted backend checks passed before the final review refinements;
the final 16 focused construction checks and all 71 UI tests pass. The production build
succeeds with its existing bundle-size advisory.

Browser validation uses the actual built App/Operations form, intercepts every API
request and runs only synthetic backend fixtures. It checks checkbox persistence,
exact 5/80/game3/overlap5/team3/game5 request values, backend/save/report propagation,
explicit review clicks, no review from opening a report, an explicitly labelled single-TE override on the
same saved frame without optimizer submission, and desktop/mobile rendering.
Evidence: [saved reference audit](artifacts/classic_construction_application/saved_reference_audit.json),
[browser evidence](artifacts/classic_construction_application/browser-evidence.json),
and screenshots alongside those files. No live Sunday solve was executed.

Current-slate family feasibility under the requested TE-off settings, globally optimal
portfolio selection, predictive improvement, ROI, ownership calibration, and strategy
validity remain unvalidated. Current implementation review of old contracts is labelled,
not historical parity. Later predictive tests require genuinely held-out later slates.

## Answers and next user action

**What changed in the application?** The existing single-TE preference persists and
explains FLEX; reports show actual constructions and distributions; an explicit pinned
construction review shows same-rule individual and replacement tradeoffs. A missing
eligible-set stack-minimum bypass was fixed.

**Which constructions were forbidden, unavailable, or merely unselected?** TE FLEX is
forbidden by the saved single-TE preference; four-player teams by its cap 3; QB/RB
without WR/TE by the strategy floor. Exact counts below a step minimum are unavailable
on that template. RB FLEX is reachable but absent from the five selected entries.
Missing pinned inputs are unavailable and underfilled full replacement is not searched.
Other missing selections do not prove a family uncompetitive.

**Can the user enable TE FLEX from the existing UI?** Yes: uncheck **Enforce single TE
(exclude TE from FLEX)**. No new conflicting field is present.

**Can the user inspect construction tradeoffs through the shared app path?** Yes: reopen
a completed saved Large-GPP report, set the existing single-TE checkbox for the review,
choose **Entry to review**, then click **Review construction tradeoffs**. It labels any
single-TE change and retains every other saved constraint, frozen input and scoring term.
Inspect the independent individual/replacement columns and component details.

**What remains unvalidated?** Current-slate TE-off outcomes, predictive/ROI benefit,
held-out generalization, ownership calibration and joint portfolio optimality.

**Exact UI steps for the next controlled comparison:**

1. Open **Operations → Portfolio optimizer**, Classic, Large GPP. Reopen reference
   `0400342a-d274-4ff5-8667-c729652b4a1f` from Recent optimizer runs to inspect its
   saved controls and projection lineage. Opening it performs no optimization.
2. Verify **5 entries / 80% exposure / primary-game cap 3 / overlap 5 / team cap 3 /
   game cap 5**, and preserve all other player decisions, risk controls, no-offense-vs-DST
   and refresh preferences. Change only **Enforce single TE (exclude TE from FLEX)**
   to off. Leave the existing projection selector at **Latest completed (automatic)**:
   Run Optimizer currently rebuilds projections and rejects a manual projection override.
3. For a genuinely pinned comparison **before** running a portfolio, keep the reference
   report open, select **Entry to review → 1**, and explicitly click **Review construction
   tradeoffs**. The report labels saved single TE on versus reviewed off. Every other
   saved constraint, player frame, ownership value, normalizer and weight is retained.
   This action compares alternatives; it does not generate or save a new portfolio.
4. For the proposed next portfolio, review **Portfolio settings to submit** and the
   single-TE checkbox. The **user** clicks **Run Optimizer** when ready. Codex has
   not clicked it for this comparison. Keep automatic feature/projection preparation
   and the existing **Refresh ownership before optimizing** preference unchanged.
5. Inspect the new saved controls, input lineage and construction distributions. A fresh
   Run Optimizer may rebuild projections/ownership or refresh eligibility, so differences
   from the old portfolio cannot be attributed solely to the TE switch unless the frozen
   player/scoring frames also match. Its own **Review construction tradeoffs** compares
   constructions on one pinned frame. Inspect components, exact restrictions, solver
   status and individual versus replacement feasibility. Later template steps have
   different minimums; do not read those as exact counts or substitute rules-disabled
   comparisons for this same-rule review.

Production scoring/default changes: **NONE**.

New user portfolio generated by Codex: **NO**.
