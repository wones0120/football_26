# Thursday Analyst normal-generation test

**The imported packet entered normal construction generation and the existing selector. This replay used exported real inputs and in-memory checkpoints; live readiness remains unapproved.**

Packet: `bbbb7249093a0c0382f3c2654cd5b0a568b4d328c061d272ba09a3e31d1f88b2`. Stored base projection cutoff and analyst analysis time are retained independently in source/packet artifacts. Later opinions are evaluated at the current research decision, not backdated to the projection cutoff.

Without Analyst: NON-PRODUCTION incomplete-evidence override; Selected 4 of 5 Showdown lineups from 41 distinct candidates; joint mean/P90 floor=95% of common baseline raw maxima; role ownership diagnostic only: incomplete or not explicitly approved for Showdown; selector term disabled uniformly; strategy=showdown_gpp_portfolio_v3; showdown lineup validation=passed
With Analyst: NON-PRODUCTION incomplete-evidence override; Selected 4 of 5 Showdown lineups from 41 distinct candidates; joint mean/P90 floor=95% of common baseline raw maxima; role ownership diagnostic only: incomplete or not explicitly approved for Showdown; selector term disabled uniformly; strategy=showdown_gpp_portfolio_v3; showdown lineup validation=passed

| Analyst thought | Typed construction | Requested / generated | Outcome |
|---|---|---|---|
| Investigate SEA passing-led script and receiving Captain before an unsupported lead-runner Captain; conditional Seattle win lean only if JSN usual role and DEN coverage absences are confirmed. No defensible unconditional winner call yet. | explicit_roles | 2 / 2 | selected; quality True, selected; quality True |
| Investigate SEA passing-led script and receiving Captain before an unsupported lead-runner Captain; conditional Seattle win lean only if JSN usual role and DEN coverage absences are confirmed. No defensible unconditional winner call yet. | explicit_roles | 2 / 2 | selected; quality True, not selected; quality True |
| Tentative KC home win with controlled-game branch ahead of a forced shootout; first investigate Walker + KC DST construction versus Mahomes-led passing alternative. | rb_dst_scenario | 2 / 0 | unknown_or_ineligible_identity, wrong_format, wrong_slate_game |
| Tentative KC home win with controlled-game branch ahead of a forced shootout; first investigate Walker + KC DST construction versus Mahomes-led passing alternative. | player_emphasis | 2 / 0 | unknown_or_ineligible_identity, wrong_format, wrong_slate_game |

## Generated Analyst candidates

| Candidate | Captain | FLEX | Salary | Mean | Original objective |95% screen | Selected |
|---|---|---|---:|---:|---:|---|---|
| 1 | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Jason Myers, AJ Barner, Evan Engram | 50000 | 92.91 | 112.2354 | True | True |
| 2 | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Rashid Shaheed, Jason Myers, AJ Barner | 49600 | 92.78 | 112.1068 | True | True |
| 3 | Sam Darnold | Bo Nix, Jaxon Smith-Njigba, Jason Myers, AJ Barner, Broncos | 49900 | 94.31 | 110.758 | True | True |
| 4 | Sam Darnold | Bo Nix, Jaxon Smith-Njigba, Jason Myers, AJ Barner, Evan Engram | 49100 | 93.98 | 110.4243 | True | False |

## Selected normal portfolio

| Lineup | Captain | FLEX | Salary | Mean | Analyst thesis attribution | Baseline selected roster? |
|---|---|---|---:|---:|---|---|
| 1 | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Jason Myers, AJ Barner, Evan Engram | 50000 | 92.91 | SEA_passing_construction_lean:0 | True |
| 2 | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Rashid Shaheed, Jason Myers, AJ Barner | 49600 | 92.78 | SEA_passing_construction_lean:0 | True |
| 3 | Jaxon Smith-Njigba | Bo Nix, Sam Darnold, Cooper Kupp, Jason Myers, AJ Barner | 49200 | 92.74 |  | True |
| 4 | Sam Darnold | Bo Nix, Jaxon Smith-Njigba, Jason Myers, AJ Barner, Broncos | 49900 | 94.31 | SEA_passing_construction_lean:1 | True |

The two SEA role branches anchor JSN and Darnold in opposite Captain/FLEX constructions. Their remaining FLEX players are chosen by the unchanged baseline objective. The original pool already discovered these four rosters, so the test proves ingestion, generation, attribution and unchanged-rule evaluation, not a new performance improvement.
The five-entry portfolio retains its existing joint95% common-baseline mean/P90 screen and Captain/player caps. It achieved4/5 without relaxing those constraints. No fresh market or missing salary chronology was invented to claim READY.
A Darnold-Captain branch can include Broncos DST alongside opposing SEA offensive players when existing avoid_dst_opponents is false. This is a football-coherence concern to review; simple Analyst anchors do not automatically fix every FLEX pairing.
The saved readiness display says DEN @ SEA; verified packet schedule identifies SEA @ DEN. The generator binds the canonical two-team game scope and does not adopt the reversed display as venue evidence.
