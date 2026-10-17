# Thursday SEA at DEN — live Analyst app test

**Generation READY; entry clearance remains DEVELOPMENT_PREVIEW, not certified.**
Kickoff: Thursday October 15, 2026, 8:15 PM Eastern / 6:15 PM Denver time (00:15 UTC October 16).

The running app imported the versioned packet, refreshed/prepared real inputs and persisted a normal Analyst-influenced optimizer run. There was no incomplete-evidence override, contest submission, payment, or inference that generated lineups were entered. These lineups are available for the user’s possible contest review.

## Current saved runs

- Preparation job: `42bfc75a-570e-4fd7-8880-33887c2cea6c`.
- Projection: `563946a2-32b6-467e-a2e9-2c3ad7569927`; cutoff `2026-10-13T12:49:22.001893-04:00`.
- Baseline optimizer: `454412f0-2923-43ea-914d-ee9425923b84`.
- Final Analyst optimizer: `6b2f7acd-dec5-4fcf-9cd8-6508d2a256ba`.
- Packet: `20261013_SEA_DEN_SUNDAY_preview_v3` / `bbbb7249093a0c0382f3c2654cd5b0a568b4d328c061d272ba09a3e31d1f88b2`.
- Earlier Analyst run `670a7f44-9145-4920-b6f4-a1b92d61a0c9` is retained but superseded: its merge collapsed scenario variants. The corrected final run preserves the original 59 candidate variants.

## What entered generation

| Analyst thought | Typed directive | Requested / generated | Screen / selection |
|---|---|---|---|
| Investigate SEA passing-led script and receiving Captain before an unsupported lead-runner Captain; conditional Seattle win lean only if JSN usual role and DEN coverage absences are confirmed. No defensible unconditional winner call yet. | CPT: Jaxon Smith-Njigba; FLEX: Sam Darnold | 2 / 2 | 95% pass; selected roster, 95% pass; selected roster |
| Investigate SEA passing-led script and receiving Captain before an unsupported lead-runner Captain; conditional Seattle win lean only if JSN usual role and DEN coverage absences are confirmed. No defensible unconditional winner call yet. | CPT: Sam Darnold; FLEX: Jaxon Smith-Njigba | 2 / 2 | 95% pass; selected roster, 95% pass; not selected |
| Tentative KC home win with controlled-game branch ahead of a forced shootout; first investigate Walker + KC DST construction versus Mahomes-led passing alternative. | RB: 5169c450-ece6-4729-8952-ba040d3f64f2; DST: f57e0806-3a25-44b1-9bcc-295699cb9536 | 2 / 0 | unknown_or_ineligible_identity; wrong_format; wrong_slate_game |
| Tentative KC home win with controlled-game branch ahead of a forced shootout; first investigate Walker + KC DST construction versus Mahomes-led passing alternative. | PLAYER: 3b2fed31-d793-46d1-949b-18caac632e63 | 2 / 0 | unknown_or_ineligible_identity; wrong_format; wrong_slate_game |

The two Thursday branches each generated two candidates. Sunday KC opinions remained separate and abstained from this Thursday slate. No numeric opinion bonus, exposure forecast, or projection adjustment was introduced. Typed anchors control Captain/FLEX identities; remaining FLEX players follow the existing model and rules.

## Generated Analyst candidates

| Canonical candidate ID | Captain | FLEX | Salary | Mean | Original solver objective | 95% / selected |
|---|---|---|---:|---:|---:|---|
| `f94def806c55fc60e780a2f84b99d85f6efade00996fd2e756f52c0a33a8bbc0` | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Rashid Shaheed, Jason Myers, AJ Barner | $49,600 | 91.69 | 111.2816 | Pass / True |
| `92ade6027ed66831a4492a684bddd17896785474f8a95c48a6c0393728c90a66` | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Jason Myers, AJ Barner, Evan Engram | $50,000 | 91.67 | 111.2541 | Pass / True |
| `edcdb2502e3abe8a929cbe336d3a9dea42a490b6f9dae7cb4140c6d38012b3f8` | Sam Darnold | Bo Nix, Jaxon Smith-Njigba, Rashid Shaheed, Jason Myers, AJ Barner | $48,700 | 91.64 | 108.2093 | Pass / True |
| `16bfe45153d6441877b8b2bd495354775e5accf3ccdf981ca54b2cacc0a3cea4` | Sam Darnold | Bo Nix, Jaxon Smith-Njigba, Jason Myers, AJ Barner, Broncos | $49,900 | 91.64 | 108.2076 | Pass / False |

The unselected Darnold-Captain / Broncos-DST construction includes opposing Seattle offensive players. It passes the existing mathematical legality and quality screen because `avoid_dst_opponents` is false; it remains a football-coherence concern, not a new exclusion inferred from fandom.

## Selected normal portfolio

| Saved lineup ID | Captain | FLEX | Salary | Mean | Sum of marginal P90 | Analyst attribution |
|---|---|---|---:|---:|---:|---|
| `6b2f7acd-dec5-4fcf-9cd8-6508d2a256ba:1` | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Rashid Shaheed, Jason Myers, AJ Barner | $49,600 | 91.69 | 153.33 | SEA_passing_construction_lean:0 |
| `6b2f7acd-dec5-4fcf-9cd8-6508d2a256ba:2` | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Jason Myers, AJ Barner, Evan Engram | $50,000 | 91.67 | 154.93 | SEA_passing_construction_lean:0 |
| `6b2f7acd-dec5-4fcf-9cd8-6508d2a256ba:3` | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Cooper Kupp, Jason Myers, AJ Barner | $49,200 | 91.56 | 153.19 |  |
| `6b2f7acd-dec5-4fcf-9cd8-6508d2a256ba:4` | Sam Darnold | Bo Nix, Jaxon Smith-Njigba, Rashid Shaheed, Jason Myers, AJ Barner | $48,700 | 91.64 | 152.27 | SEA_passing_construction_lean:1 |

Four Captain-aware lineups were selected from three distinct six-player sets; changing Captain is a distinct Showdown roster. Summed marginal P90 is not a calibrated joint lineup P90. The selected roster set is identical to the matched baseline. All four Analyst candidates already existed in baseline discovery; three selected lineups overlap the typed opinions. This proves ingestion, generation and attribution, not improved forecasts or a unique generation origin.

## Constraints and fill

- Requested 5; achieved 4. The unchanged selector reports: **player/captain exposure caps prevent filling from distinct quality-eligible rosters**. No limits were relaxed.
- Original 59 candidate variants preserved; 43 pass the joint 95% screen (31 distinct Captain-aware quality rosters); 16 variants fail it.
- Minimum common-baseline mean: 87.11; minimum summed marginal P90: 147.19. All four Analyst candidates pass.
- Captain shortlist retained: Bo Nix, Jaxon Smith-Njigba, Sam Darnold, J.K. Dobbins.
- Each selected lineup has six distinct canonical identities, one Captain, five FLEX, both teams represented, and salary ≤ $50,000. Captain salary/scoring multiplier remains 1.5.

Exposure caps use the requested five-lineup denominator: Captain maximum three appearances. With only four achieved, JSN Captain exposure is 3/4 (75%) although the requested-count 60% cap passes. AJ Barner, Jason Myers and JSN appear in all four (100% realized), while the requested-count core cap permits four appearances. The existing output retains these underfill warnings; do not read the nominal rates as achieved four-lineup percentages.

## Readiness and lineage

The earlier `market_missing` warning came from older projection `116e6a12…`, which contained no market snapshot. Fresh normal preparation captured ESPN/DraftKings lines (SEA -3, DEN +3, total 40.5) at 2026-10-13T16:48:35Z and proved consumption before the 16:49:22Z projection cutoff. `salary_pool_missing` in the initial offline export came from its missing derived player dimension for Malick Meiga; the normal live loader verifies the canonical player master and passes. The reversed `DEN @ SEA` display was an alphabetical-order bug, now corrected from native salary `SEA@DEN` evidence. Historical records remain untouched.

The official NFL injury collector returned the wrong season/week. That ERROR is retained. Current independently sourced weekly roster/status, depth/starter and canonical context satisfy provisional generation readiness; they do not establish final game-day dressing.

Entry assessment remains false: native draft-group confirmation, final availability, upstream quote/salary publication freshness, weather clearance and contest assignment/submission remain unevaluated; role ownership is diagnostic-only. No contest or entry IDs were supplied or invented.

Saved lineup IDs, packet hashes and canonical Captain-aware candidate IDs are retained for later actual-entry/result linkage. Generated, selected, exported and observed-entry evidence remain separate. An eventual roster match may have multiple origins across these preserved runs.

## App use

Open http://127.0.0.1:5173, refresh, choose 2026 / Week 6 / Thursday Night / Captain GPP. In Recent optimizer runs, open final run `6b2f7acd-dec5-4fcf-9cd8-6508d2a256ba`. For a new run, expand **Wones Football Analyst**, import the packet JSON (idempotent), **Prepare slate for optimization**, then **Run Optimizer**. Clear the packet for the unchanged baseline path. Sources must be refreshed again before later Thursday decisions.

API :8000 and durable worker are launchd-managed; Vite :5173 serves current controls. Saved results were successfully reopened after restart. API/fixture/type/build tests pass; no Chrome or browser interaction was used, and no visual browser check is claimed.

## Sunday Main coverage

Sunday remains the primary ongoing research opportunity. The current salary-scope checklist contains ten games, zero completed full research reviews, and one preliminary KC opinion. This is partial coverage, not a finished slate-wide recommendation. Normal Classic consumers and the app Analyst summary are available; Thursday membership is never mapped into Sunday Main. Next research should inspect every actual Sunday salary game, retain partial-evidence opinions and factual gaps, then deliver selective cross-slate player/game construction theses in the same versioned packet/import path. No Sunday live generation was run in this Thursday activation.

## Independent native-slate verification

After the saved runs, a read-only public DraftKings check uniquely matched native group **154947** to all 112 imported Captain/FLEX slot IDs, teams, natural positions and salaries. Other simultaneously published group types failed exact native membership.
Observed at 2026-10-13T17:29:03.424968+00:00. The 8 current native unavailable designations have 0 conflicts with generation-eligible players; none conflict with the selected rosters. Blank native status is not treated as affirmative availability.
This independent later verification is not backdated or grafted into the original salary import. The saved app entry assessment still marks native-group metadata UNEVALUATED because that import lacked the field. Future normal salary imports can carry this verified group ID; the remaining final-dressing, publication, weather and assignment checks are still separate.
