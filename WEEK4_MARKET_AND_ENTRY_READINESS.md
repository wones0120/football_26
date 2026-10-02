# Week 4 market and entry readiness

## Existing market source audit

| Source/path | Fields and storage | Time evidence | Current Week 4 suitability |
| --- | --- | --- | --- |
| nflreadpy / nflverse schedules | `total_line`, `spread_line`, game ID, teams, kickoff in `public.raw_nfl_schedule`; historical feature matrix and projection reconciliation already use this path | Raw schedule ingest time exists; older historical rows have no individual line observation time | 7,065/7,289 historical/current raw rows have both fields, but the September 22 Week 4 snapshot had 16 schedule rows and zero lines. A fresh September 29 fetch supplied both fields for all 16 games. |
| Manual/public-page market capture | `scripts/record_manual_market_line.py` writes a source snapshot and `public.raw_nfl_schedule` row with total, expected home margin, note, source URI when public, and capture time | Explicit local capture time | One `manual_market` and one `public_market` complete row exist, neither for Week 4. Traceable fallback, one game at a time. |
| Prior sportsbook/verified-web source rows | Sparse `draftkings_sportsbook` and `verified_web_market` raw schedule evidence | Capture metadata varies by row | One and five complete rows, respectively; none for Week 4. |
| Historical feature matrix | Game total/spread and implied totals in `public.player_game_feature_matrix` and later target features | Historical feature creation time does not prove when a market quote was available | Training/reconciliation input only. A zero in a matrix is never treated as a sourced current line. |
| New normalized market snapshots | `target.market_snapshot` with source snapshot and ingest run foreign keys | Explicit `observed_at` capture clock and `ingested_at` | Selected for current pre-lock Classic and shared Showdown projection loading. |

The existing nflverse schedule feed was used because a live fetch supplied complete Week 4 lines; an external odds API key was unnecessary. The feed does not expose a trustworthy per-line change time in this path. `observed_at` therefore means **our capture time**, not when a sportsbook first posted or last changed the quote. The source's `spread_line` is expected home margin; `target.market_snapshot.home_spread` is the conventional home betting spread and is its negative. The projection and optimizer keep the model/data cutoff and market observation/decision times separately. An older frozen projection is not relabeled as if it had seen a later quote; a refreshed projection and optimizer run consume later evidence.

## Capture and lineage

The September 29 capture produced source snapshot `275c194b-c913-5416-9194-53778bc2435f` and ingest run `934b9e3c-ed05-564d-a6de-84047354dddb`. It recorded 16/16 scheduled Week 4 games at **2026-09-29 21:22:11 EDT**, including the 12 Sunday Main DraftKings games. Each normalized row stores season, week, canonical/source game IDs, canonical teams, kickoff, total, home spread, source, observation time, ingestion time, and immutable raw-artifact lineage. A later capture adds new rows; it does not rewrite this evidence. The capture command validates a full requested slate before ingesting any of its rows. `--slate SUNDAY_MAIN` scopes future refreshes to the saved salary slate, even after Thursday kickoff. A Thursday dry run can use `--slate THURSDAY_NIGHT`.

The selected observation must match game ID, teams, season/week, have both plausible values, be ingested by the run cutoff, be observed no later than the decision cutoff, and predate kickoff. Invalid or late quotes are rejected. Broad plumbing bounds are 20–80 total points, absolute home spread at most 30, and positive implied totals. Missing quotes remain null. Readiness uses game coverage and reports each game's age; default display bands are fresh through six hours, aging through 24 hours, and stale thereafter. Stale lines warn by default and block within six hours of first kickoff or with the blocker policy. No post-lock value is silently accepted.

## Week 4 Sunday Main market table

All rows below share source `nflverse_schedules` and observation time **2026-09-29 21:22:11 EDT**. `Home spread` uses the conventional home betting sign; negative means home favored. The implied columns are away and home points, respectively.

| Away @ home | Total | Home spread | Away implied | Home implied |
| --- | ---: | ---: | ---: | ---: |
| ARI @ NYG | 44.5 | +1.5 | 23.0 | 21.5 |
| DAL @ HOU | 48.5 | −2.5 | 23.0 | 25.5 |
| DEN @ SF | 47.5 | −3.0 | 22.25 | 25.25 |
| GB @ TB | 39.5 | +3.5 | 21.5 | 18.0 |
| JAX @ CIN | 51.5 | −2.5 | 24.5 | 27.0 |
| KC @ LV | 47.5 | +4.5 | 26.0 | 21.5 |
| LAC @ SEA | 42.5 | −7.0 | 17.75 | 24.75 |
| LAR @ PHI | 43.5 | +3.0 | 23.25 | 20.25 |
| MIA @ MIN | 38.5 | −10.5 | 14.0 | 24.5 |
| NE @ BUF | 48.5 | −7.0 | 20.75 | 27.75 |
| NYJ @ CHI | 43.5 | −3.5 | 20.0 | 23.5 |
| TEN @ BAL | 43.5 | −11.5 | 16.0 | 27.5 |

`home_implied = (total − home_spread)/2` and `away_implied = (total + home_spread)/2`. For JAX @ CIN, `(51.5 − (−2.5))/2 = 27.0` home and `(51.5 + (−2.5))/2 = 24.5` away; they sum to 51.5 and differ by the 2.5 point spread magnitude. The same check is enforced for each sourced game. There are **12**, not 11, games in the saved Sunday Main salary slate. The remaining Week 4 schedule games are outside that DraftKings slate.

## New projection evidence

New projection run `9701cb0a-a28d-4b20-9de6-2ca5b8b2e29b` uses model run `3375487a-03f4-41c8-b424-e098974c2d35`, feature run `247c1b78-fd66-4901-bc27-d252d22c1c95`, and cutoff `2026-09-30 01:33:59 UTC`. It persisted 538 player records. A database check found sourced market fields on 538/538 feature rows covering the 12/12 Sunday Main games. The new ownership run is `94bf38a7-74bb-44e4-a610-ac11f4bd2440` with 601 saved forecasts. The earlier no-market projection and optimizer runs remain unchanged.

Against the prior no-market projection `aa6bdf5c-2b6b-4790-b8ac-a889545cda44`, 528 records match on canonical player ID and game ID; 479 of those changed mean by more than 0.01. Mean change among matched records is +0.025 points, with a range from −1.757 to +5.539. Ten old records did not match by game ID, including the DST game-ID repair, so the paired summary does not claim 538 exact pairs. Named canonical-ID checks: Jacoby Brissett mean 14.580 → 16.400, Cade Otton 9.866 → 9.631, Kyren Williams 13.171 → 15.766, and Puka Nacua 16.099 → 19.896. These are changes between complete projection runs; they are not a controlled attribution of each point to the market feature alone.

## Completed optimizer decision

The new saved optimizer run is **`264c7133-fe50-450e-a7e4-6bc1110b145b`**, using the new projection and ownership runs above. Its decision began September 29 at 23:19:52 EDT, about 1.96 hours after market capture. It saved five legal lineups and a frozen pre-lock prospective shadow. The original hardened no-market run `532ff446-8261-4be2-b26e-3e44837e556a` and earlier run `40f1c849-07cf-4346-994c-04b9663e662d` remain unchanged. The failed diagnostic run `8e40333a-a4c0-4d4b-a024-512331b66f03` is retained as failed lineage; interrupted local attempts did not save lineups.

The measured full run took **347.6 seconds** on the local machine, including the optional prospective shadow. The seed generator took 219.9 seconds across four deterministic QB groups, exact candidate discovery 27.5 seconds, and production admission 0.27 seconds. It generated **205/205 cap-safe seeds**, expanded to **285** distinct legal candidates, admitted **205/205** under all production caps, and made **zero refill attempts**. The prior serial attempt exceeded six minutes before completing initial generation, and its sequential refill attempt ran over an hour before interruption. This is a material latency improvement, but a roughly six-minute local run still merits future profiling. CBC CPU time is local process time; Codex model usage comes from this conversation and tool interactions, not CBC's elapsed time.

The admission funnel's `rejected_by_player_cap=64` is the count of eligible candidates not selected by the joint 205-slot solve. It includes candidates left out because the target is 205, so it is **not** a count of 64 individual cap violations. The actual cap-violation check is zero.

### Entry readiness at this decision

| Check | Saved result |
| --- | --- |
| Source-backed market | **12/12** Sunday Main games; fresh 12, aging/stale/missing/invalid 0; latest observation September 29, 21:22:11 EDT |
| Projection and salary identity | 466/466 eligible projections; saved salary identity PASS |
| Candidate pool and risk | **205/205**, no player-cap or questionable-risk violation; no unexplained >80% concentration |
| Ownership | 458/466 eligible players; **205/205 candidates** and **22/22 distinct selected players** complete. Eight unused eligible players still lack ownership, a warning. |
| Portfolio | Five legal lineups; three QB/game paths; maximum pairwise overlap **6/9** |
| Exposure approval | **Chase Brown, RB, 5/5** requires an explicit pre-lock decision |
| Overall | **ENTRY_READY_WITH_APPROVAL_REQUIRED** at the saved decision time |

The saved market fields are non-null on every selected player; no zero placeholder is used. The projection/model cutoff, captured market time, and optimizer decision time remain distinct. This is a Tuesday decision snapshot. Its market freshness cannot be carried forward to Sunday without a new capture and run.

### Hardened preview versus market-complete decision

| Measure | Hardened preview `532ff446` | Market-complete `264c7133` |
| --- | ---: | ---: |
| Sourced slate games | 0/12 | **12/12** |
| Accepted candidates | 205/205 | **205/205** |
| Selected lineups / maximum overlap | 5 / 6 | **5 / 6** |
| Distinct QB paths | 3 | **3** |
| Selected projected mean sum | 541.90 | 656.42 |
| Selected player P90 sum | 1,045.40 | 1,134.18 |
| Selected selector-score sum | 27.982 | 27.714 |
| Candidate cap violations | 0 | **0** |
| Selected questionable elevated appearances | 2 across five lineups | **3 across five lineups; at most one per lineup** |
| Readiness | DEVELOPMENT_PREVIEW | **ENTRY_READY_WITH_APPROVAL_REQUIRED** |

No selected roster is identical between these saved runs. The new run changes projection/ownership inputs, market context, and candidate-generation method. The mean, P90, and selector differences are descriptive; they are **not** a controlled causal estimate of market data's value or a claim of better realized results.

The old selector labeled context, bring-back, correlation, and game environment **UNAVAILABLE** when markets were missing. The new selected lineups have context contributions of **0.068–0.141**, QB-stack **0.134–0.196**, and correlation **0.054–0.129**. Four JAX–CIN constructions receive **0.045** game-environment contribution from a sourced 51.5 total; the ARI–NYG construction correctly reports **ACTIVE_ZERO** for that term despite having a valid 44.5 total. Representative new rank-1 components are P90 **3.068**, mean **2.016**, context **0.133**, QB stack **0.184**, bring-back **0.037**, correlation **0.124**, and game environment **0.045**, summing to selector **5.607** after rounding. Ownership-chalk and duplication remain disabled selector terms; leverage is unavailable without its own evidence. Markets activate the existing context rules, not a new speculative strategy.

### Candidate and selected exposure

Each candidate pool contains 205 lineups. `Candidate` is appearances in that pool; `selected` is appearances among five entries.

| Player | Preview candidate | New candidate | Preview selected | New selected |
| --- | ---: | ---: | ---: | ---: |
| Chase Brown | 142 | **184** | 4 | **5** |
| Parker Washington | 134 | **171** | 3 | **4** |
| Dolphins DST | 97 | **126** | 3 | **5** |
| Kyren Williams | 159 | **120** | 5 | **4** |
| Kenneth Walker III | 153 | **99** | 4 | **1** |
| Ja'Marr Chase | 4 | **88** | 0 | **4** |
| Michael Wilson | 141 | **78** | 4 | **2** |
| Cade Otton | 116 | **20** | 5 | **2** |
| Puka Nacua | 51 | **51** | 2 | **2** |
| Jacoby Brissett | 134 | **10** | 3 | **1** |
| Trevor Lawrence | 49 | **51** | 1 | **3** |
| Caleb Douglas | 24 | **16** | 0 | **1** |

Chase Brown's candidate exposure is **184/205 = 89.8%**, within his 90% elite-core cap. Puka remains **51/205 = 24.9%**, within his 25% elevated-questionable cap. All candidate player caps pass. The Dolphins DST appears in 5/5 selected lineups; the requested approval gate applies only to RB/WR/TE.

The complete new five-lineup exposure is: 5/5 Chase Brown and Dolphins DST; 4/5 Kyren Williams, Parker Washington, and Ja'Marr Chase; 3/5 Trevor Lawrence; 2/5 Puka Nacua, Derrick Henry, Cade Otton, and Michael Wilson; 1/5 each Travis Kelce, Travis Hunter, Caleb Douglas, Brenton Strange, Brian Thomas Jr., Kenneth Walker III, Tee Higgins, Rhamondre Stevenson, Joe Burrow, Elic Ayomanor, Trey McBride, and Jacoby Brissett.

| Lineup | QB / primary game | Stack family | Mean | Sum of player P90s | Ownership sum |
| --- | --- | --- | ---: | ---: | ---: |
| 1 | Trevor Lawrence / JAX–CIN | QB+2+bring-back | 133.32 | 225.60 | 55.25 |
| 2 | Trevor Lawrence / JAX–CIN | QB+2+bring-back | 130.24 | 226.94 | 63.06 |
| 3 | Trevor Lawrence / JAX–CIN | QB+2+bring-back | 129.36 | 228.24 | 54.97 |
| 4 | Joe Burrow / CIN–JAX | QB+2+bring-back | 129.67 | 222.07 | 45.96 |
| 5 | Jacoby Brissett / ARI–NYG | QB+2 | 133.82 | 231.33 | 64.33 |

These are **three distinct QB/game paths** (Lawrence, Burrow, Brissett), two physical games, and two stack families. P90 sums are sums of player quantiles, not simulated lineup P90s. In the selected portfolio, elevated-questionable Puka appears 2/5 and Caleb Douglas 1/5; no lineup carries more than one elevated player, and there are no out/doubtful appearances. The saved prospective shadow remains frozen with status `prelock_frozen`; it does not modify production selection.

### 100% skill-player decision

Only **Chase Brown (RB)** is 100% among selected skill players. He is classified `elite_high_confidence`, projected **18.35 mean / 28.86 P90**, with **6.30%** ownership and normal availability in this snapshot. His 5/5 exposure requires a reasoned, timestamped approval before kickoff. The best saved 80%-cap alternative changes the selected ranks from **1, 3, 6, 49, 83** to **1, 6, 31, 48, 83**. Across five entries it costs **0.02635 selector points**, **7.19 summed mean points**, and **2.24 summed player P90 points**. It retains three QB paths and maximum overlap 6. No other RB/WR/TE currently requires approval. Approving leaves this frozen run intact; capping creates a new optimizer run.

## Implementation and validation

The core changes are the normalized snapshot service and provider capture in `backend/app/product_services/market_snapshots.py`, `scripts/capture_nflverse_markets.py`, and `migrations/0040_market_snapshots.sql`; projection and feature adapters in `backend/app/product_services/canonical_projection_inputs.py` and `Database/features.py`; Classic readiness, candidate controls, and approval flows in `backend/app/product_services/classic_small_field.py`, `backend/app/product_services/skill_exposure_approval.py`, `backend/app/product_services/optimizer.py`, `backend/app/api/product_routes.py`, `backend/app/product_services/draftkings_export.py`, `migrations/0041_skill_exposure_decisions.sql`, and the optimizer UI/report; plus corresponding tests and README, runbook, product, and release-note updates. The performance change uses four fixed QB seed groups, a joint cap-feasible admission solve, and parallel constrained refill only when needed. It adds no package dependency and leaves Showdown strategy logic unchanged.

Final verification: **909 backend tests passed, four failed** in existing Showdown single-TE expectation tests (`test_showdown_single_entry.py` and `test_showdown_three_max.py`); these failures are unrelated to the market/Classic work and were present before the final solver change. **37 UI tests passed**, and TypeScript/Vite build passed. Targeted Classic and optimizer tests passed **107/107**. `git diff --check` passed. The new local run persisted its full decision lineage and validated all five legal lineups. The Thursday salary slate can consume a complete pre-lock total, spread, implied totals, source, and timestamp through the same normalized snapshot path; a Thursday dry run and shared loader test passed. The infrastructure is ready for a **fresh Thursday capture and projection run**; no Showdown strategy policy was changed or entry-ready Thursday lineup claimed.

## Remaining before Sunday

The only saved-run approval outstanding is Chase Brown. Because this is a Tuesday market and availability snapshot, refresh the source markets and pregame evidence nearer Sunday lock, then create a new projection/ownership/optimizer decision and review its readiness and any changed 100% skill exposures. The current run should not be exported at Sunday lock solely on the strength of Tuesday freshness.

### If Sunday kickoff were in five minutes, is this run entry-ready?

**APPROVAL REQUIRED** at this run's recorded decision time. Its saved readiness has no other blocker. At the actual Sunday lock, the Tuesday market observation would require a refresh and new run.

### What exact action should the user take next?

Decide whether to **approve Chase Brown at 100%** with a reason or **cap him at 80% (or a custom lower cap)** and rerun. Before Sunday lock, refresh markets and pregame evidence, rerun, and resolve any approval shown by that final decision.
