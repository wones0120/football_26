# Sunday Morning — Stroud and Lawrence Captain comparison

**Result: 5/5 normal lineups saved and reopened in both arms.** Treatment adds only the two named canonical QB Captain exceptions to WR/RB eligibility. All other referenced Morning settings remain identical. Final entry clearance remains false.

Houston at Jacksonville, standard DraftKings Showdown **154948**, Sunday October 18, **7:30 a.m. MDT / 9:30 a.m. EDT**. Native IDs, CPT/FLEX roles and salaries match the supplied immutable CSV and fresh public download. No contest entries were assigned, exported or submitted.

## What changed

| | Existing positions, fresh control | Named-QB treatment |
|---|---|---|
| Saved run | daa8d8f4-bae5-4233-922e-e05741adbd50 | 97f08df1-7e3e-4742-bdfe-6c42e52d61e9 |
| Captain eligibility | WR/RB | WR/RB plus C.J. Stroud and Trevor Lawrence only |
| Requested / achieved | 5 / 5 | 5 / 5 |
| Captain counts | Tuten 3, Boutte 1, Meyers 1 | Lawrence 2, Tuten 2, Cameron 1 |
| Mean of unchanged baseline lineup projections | 82.15 | 83.68 |
| Best selected reference-world upside score | 105.79 | 109.07 |
| Best selected passing-envelope upside score | 110.69 | 114.10 |
| Candidate variants / distinct candidate rosters | 55 / 55 | 63 / 63 |
| Distinct selected canonical rosters | 5 | 5 |
| Solver / relaxation | Optimal / none | Optimal / none |

Two selected rosters are shared. The treatment changes three of the five Captain-sensitive rosters; it is a **controlled generation comparison**, because eligibility changes the candidate pool. It is not a fixed-pool selector ablation. The upside score is `conditional mean + 0.35 × (conditional P90 − conditional mean)`, with Captain ×1.5. It is an objective score, not projected fantasy points, ROI or calibrated scenario probability. The portfolio policy rewards best-roster coverage in each equally weighted sensitivity and average conditional upside. Pool-normalized internal utility totals are not compared across the two different candidate pools.

Both arms use one fresh salary/model/ownership/source build, the same automatic Expected Game checked packet, actual deterministic Analyst seed **7**, four candidates per thesis, the same broad Captain support search, and the same reference/1.10 passing-volume sensitivity definitions. Exact request equality excluding `captain_position_exception_ids`, identical numeric model-truth hash and source/packet hashes are preserved in [verification](comparison_verification.json). The legal-model and candidate hashes differ as expected because named Captain eligibility changes.

Other preserved settings: **5 lineups, 80% player exposure (max4/5), 60% Captain exposure (max3/5), $1,700 base FLEX salary minimum, max4/team, require a non-QB season-average team leader, no offense against opposing DST, Q excluded, two QBs and two TEs allowed, no locks, no player exclusions, no availability assumptions**. No DEN opponent exclusion or Thursday player exception was copied. The app’s shared Showdown sliders displayed 4/100%/50%; these runs preserve the referenced saved Morning run’s 5/80%/60% request instead of importing those unrelated shared values. Only the Morning-specific named exception list was persisted in the UI.

## All six roster slots, side by side

Baseline mean includes the actual 1.5× Captain multiplier. Entry numbers identify saved order, not matched twins. Both tables use identical fresh base projections and objective definitions.

### Fresh control — WR/RB Captain

| Entry | Captain (actual CPT salary) | Five FLEX players (actual FLEX salaries) | Total salary | Baseline mean | Reference / passing upside score |
|---|---|---|---:|---:|---:|
| 1 | Bhayshul Tuten ($12,900) | Dare Ogunbowale $2,000; C.J. Stroud $9,600; Parker Washington $10,400; Trevor Lawrence $10,000; Ka'imi Fairbairn $5,000 | $49,900 | 85.24 | 105.79 / 110.69 |
| 2 | Bhayshul Tuten ($12,900) | C.J. Stroud $9,600; Parker Washington $10,400; Cam Little $5,400; Brenton Strange $5,800; Ka'imi Fairbairn $5,000 | $49,100 | 83.66 | 105.39 / 109.60 |
| 3 | Bhayshul Tuten ($12,900) | Kayshon Boutte $3,400; Parker Washington $10,400; Trevor Lawrence $10,000; Brenton Strange $5,800; Ka'imi Fairbairn $5,000 | $47,500 | 81.71 | 104.43 / 109.19 |
| 4 | Kayshon Boutte ($5,100) | Nico Collins $11,200; C.J. Stroud $9,600; Bhayshul Tuten $8,600; Trevor Lawrence $10,000; Ka'imi Fairbairn $5,000 | $49,500 | 81.49 | 103.50 / 108.22 |
| 5 | Jakobi Meyers ($10,500) | Kayshon Boutte $3,400; C.J. Stroud $9,600; Parker Washington $10,400; Trevor Lawrence $10,000; Brenton Strange $5,800 | $49,700 | 78.66 | 103.03 / 108.47 |

### Treatment — Stroud/Lawrence additionally eligible

| Entry | Captain (actual CPT salary) | Five FLEX players (actual FLEX salaries) | Total salary | Baseline mean | Reference / passing upside score |
|---|---|---|---:|---:|---:|
| 1 | Trevor Lawrence ($15,000) | Kayshon Boutte $3,400; C.J. Stroud $9,600; Parker Washington $10,400; Brenton Strange $5,800; Ka'imi Fairbairn $5,000 | $49,200 | 86.55 | 109.07 / 114.10 |
| 2 | Trevor Lawrence ($15,000) | Xavier Hutchinson $4,200; C.J. Stroud $9,600; Parker Washington $10,400; Brenton Strange $5,800; Ka'imi Fairbairn $5,000 | $50,000 | 87.92 | 109.00 / 114.08 |
| 3 | Bhayshul Tuten ($12,900) | C.J. Stroud $9,600; Parker Washington $10,400; Cam Little $5,400; Brenton Strange $5,800; Ka'imi Fairbairn $5,000 | $49,100 | 83.66 | 105.39 / 109.60 |
| 4 | Bhayshul Tuten ($12,900) | Kayshon Boutte $3,400; Parker Washington $10,400; Trevor Lawrence $10,000; Brenton Strange $5,800; Ka'imi Fairbairn $5,000 | $47,500 | 81.71 | 104.43 / 109.19 |
| 5 | Josh Cameron ($3,300) | Nico Collins $11,200; C.J. Stroud $9,600; Bhayshul Tuten $8,600; Trevor Lawrence $10,000; Jakobi Meyers $7,000 | $49,700 | 78.56 | 100.15 / 105.50 |

## Why Lawrence Captain, and why Stroud remains FLEX

The same fresh model gives Lawrence **19.69 mean / 30.50 P90** at $10,000 FLEX ($15,000 CPT), versus Stroud **16.74 / 27.56** at $9,600 FLEX ($14,400 CPT). With both quarterbacks on a roster, moving Captain from Stroud to Lawrence costs only **$200 net**: Lawrence’s Captain premium is $5,000 versus Stroud’s $4,800. It adds **1.47 baseline projected points** by arithmetic on those unchanged moments. This explains a natural Lawrence preference without altering either QB projection. It does not prove Lawrence will outscore Stroud.

Lawrence’s two selected Captain rosters keep Washington and Strange, with Stroud/Fairbairn and either Boutte or Hutchinson. These use Jacksonville receiving support and Houston production to keep pace. The Hutchinson version uses the entire $50,000 and has the higher mean (87.92); Boutte’s lower salary and wider modeled spread give the $49,200 version slightly better conditional upside coverage. Their difference is a full-roster mean-versus-tail tradeoff, not a claim Boutte has a larger role than Hutchinson.

Stroud was genuinely eligible and generated **four Captain candidates**. His best saved Captain roster costs **$49,800**, projects **83.87**, and contains Collins, Boutte, Lawrence, Strange and Fairbairn. Its reference/passing scores are **105.65 / 110.51**, below the best Lawrence roster’s **109.07 / 114.10**. Read-only arithmetic on the same 63-candidate pool found **eight** single-lineup replacements using a Stroud Captain candidate that respect the exposure limits. Even the best replacement lowers the existing normalized coverage-plus-utility term by **0.0062053**. Thus Stroud is not secretly blocked or forced out by a global QB switch; the saved optimum prefers other combinations under this particular model and bounded candidate pool. This is a local candidate diagnostic, not exhaustive football proof. [Diagnostic](stroud_replacement_diagnostic.json).

## Captain salary relief and the cheaper players

The old five had Tuten Captain three times, Boutte once, Meyers once. Cheap Boutte Captain was a budget mechanism: with the same five FLEX names from old entry4, moving Captain to Tuten and Boutte to FLEX adds **$2,600**, making a $49,500 roster cost $52,100. His wide modeled P90 spread also helps this ceiling-sensitive objective; low salary does not establish strong receiving volume.

In the new fifth lineup, Cameron Captain costs **$3,300**, allowing Collins $11,200, Stroud $9,600, Tuten $8,600, Lawrence $10,000 and Meyers $7,000 at FLEX, total **$49,700**. Replacing Cameron Captain with Boutte Captain while retaining those five FLEX would cost **$51,500**, so it would be illegal. This is why a cheaper Captain can be selected after allowing QB Captains. Cameron is not represented as a star: his modeled base mean is **4.52** and the recent snap evidence is modest. Exposure limits also shape that fifth roster: Washington, Strange and Fairbairn each already occupy four of the first four treatment entries, so they cannot simply be added again.

| Player | FLEX salary / fresh base mean | Observed last / three-game average offensive snap share | Role case and countercase |
|---|---:|---|
| Dare Ogunbowale | $2,000 / 2.12 | 2% / 5.0% | 2% last-game snaps / 5% average is a very thin base. Montgomery absence creates a question, not measured work. Old entry1 needed his $2,000 salary: Cameron at $2,200 with the same five other players would total $50,100. He is absent from all five treatment selections without a new exclusion. |
| Kayshon Boutte | $3,400 / 4.55 | 59% / 63.3% | Cheap Stroud correlation with usable but falling snaps; modeled P90 13.95 is much larger than mean4.55. Harrison integration can reduce routes; no automatic Dell targets assigned. |
| Xavier Hutchinson | $4,200 / 5.93 | 41% / 42.0% | Costs $800 more than Boutte; fresh mean5.93 versus4.55, but lower modeled P90 11.23 versus13.95. The two Lawrence Captain rosters expose that tradeoff. |
| Jakobi Meyers | $7,000 / 9.67 | 85% / 82.7% | Established Jacksonville snap role; $7,000 is midrange, not a punt. Competes with Washington/Strange and has no guaranteed TD allocation. |
| Jaylin Noel | $3,000 / 4.27 | 45% / 44.3% | Lower-cost Houston support, but return involvement does not prove receiving opportunity. Not selected in this bounded optimum. |
| Josh Cameron | $2,200 / 4.52 | 31% / 34.7% | Affordable reserve WR; Washington is ahead on the depth chart. New Captain use is a salary/exposure branch requiring real route/target review. |
| Dalton Schultz | $4,800 / 4.92 | 52% / 56.7% | Affordable Stroud pairing, but current model mean4.92 and recent snaps trail his season receiving totals; Harrison changes distribution. No forced TE preference. |
| Brenton Strange | $5,800 / 10.78 | 81% / 81.7% | Strong recent snap participation and fresh mean10.78 at $5,800 make him efficient support in four treatment entries. Touchdowns/targets still variable. |
| Brian Thomas Jr. | $4,000 / 4.06 | 51% / 50.0% | $4,000 and roughly half the snaps; name recognition does not prove current target dominance. Not selected. |
| Woody Marks | $8,400 / 7.32 | 85% / 55.3% | 85% last-game snaps supports involvement, but $8,400 is expensive and fresh model mean7.32 is modest. Montgomery OUT does not by itself specify carries/goal-line distribution. |
| Marvin Harrison Jr. | $6,600 / 4.64 | 65% / 72.0% | Coach-confirmed Houston debut; historical snaps are from his prior team, not measured Houston routes. $6,600 is not automatic value. Dell OUT removes an activation question but does not quantify Harrison usage. |

Snap shares above are flagged observed in the existing workload evidence. Fractional target/carry model proxies are not relabeled as measured future workload. No numerical injury share transfer or player bonus was authored. [Typed workload evidence](workload_evidence.json). Fairbairn appears in four entries per arm because the model gives 12.55 at $5,000 versus Little9.45 at $5,400; kicking variance and weather remain separate limitations.

## New official news, and separation from yesterday’s baseline

The [Texans travel announcement](https://www.houstontexans.com/news/houston-texans-travel-update-10-15-2026), published October15 16:20EDT, rules **Montgomery, Dell and Pitre OUT** and says they will not travel to London. This is more definitive than the [Wednesday/Thursday practice table](https://www.houstontexans.com/news/week-6-injury-report-texans-at-jaguars). Montgomery/Dell were appended through the sourced canonical pregame context service with immutable snapshot and native salary identity linkage; Pitre is retained as defensive news because he is outside the individual salary pool. The final prepared pool confirms Montgomery OUT with no projection. This is observed availability, not a user availability assumption.

Harrison’s [debut is coach-confirmed](https://www.houstontexans.com/video/demeco-ryans-confirms-marvin-harrison-jr-will-play-in-london). His Houston routes remain unknown. The [Jaguars depth chart](https://www.jaguars.com/team/depth-chart/) lists Tuten/Rodriguez together and Cameron behind Washington. It also retains Anton Harrison at LT despite the separate IR news; the current canonical roster service controls eligibility rather than silently trusting every chart cell. Jacksonville’s [Thursday injury report](https://www.jaguars.com/team/injury-report/) still has multiple secondary/line limitations; no invented coverage edge is granted.

Yesterday’s original run **e1420b83-bf98-4af6-bd0d-17d7d2b886bb** is preserved. The fresh control selects the **same five canonical Captain/FLEX rosters** as yesterday, but its average baseline mean is **82.15**, versus **81.62** originally. The largest player-level base-mean drift is **0.264 points** (Collins); full per-player changes are retained in verification. That refresh effect is separate from the treatment’s **+1.53** average baseline points versus the fresh control. Earlier first attempts in v1 were superseded when the travel announcement was semantically reviewed; their original results remain preserved.

## Readiness and limits

Both saved runs are development previews, not final entry-cleared portfolios. Role ownership is diagnostic and unavailable for supported field selection; publication freshness, weather clearance, final remaining game-day availability and contest assignment are separate checks. The model does not consume weather. The semantic packet expires October17 00:51UTC (October16 18:51MDT); checking compatibility does not renew that clock. No outcome claims or held-out performance validation are made.

The app’s saved QB construction summary now displays named conditional eligibility rather than falsely saying a blanket No/zero. Explicit No QBs/No QB Captain still overrides named position exceptions. This is a display-only correction. **31 targeted UI tests and the TypeScript/Vite build pass.**
