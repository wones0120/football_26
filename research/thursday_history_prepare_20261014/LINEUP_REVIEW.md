# Thursday research lineups — saved and reopened

**PASS: 4/4 saved and reopened in Chrome**, run `b5fd2141-302d-4005-9456-d46d8f7173c2`. Only the DEN opponent exclusion was turned off. The 25% Captain cap, 4 lineups, 100% player cap, $1,700 base salary minimum, WR/RB Captains, non-QB leader requirement and other settings remain unchanged.

Each Captain appears once. Every roster is 3 DEN / 3 SEA, under $50,000, and includes Jaylen Waddle as the qualifying season-average DEN leader (10.34 DK PPG over five prior games). Both WR Captains are paired with Bo Nix. No Q player is selected. Final entry readiness remains false.

| Lineup | Captain | Total salary | Model mean | Scenario generation lineage |
|---|---|---:|---:|---|
| 1 | J.K. Dobbins | $49,200 | 74.49 | current_prepared_reference, sea_run_control_conditional |
| 2 | Jaylen Waddle | $48,500 | 74.40 | current_prepared_reference, den_breakout_conditional |
| 3 | Courtland Sutton | $49,600 | 72.95 | den_breakout_conditional |
| 4 | RJ Harvey | $47,200 | 73.78 | current_prepared_reference |

The model mean is the saved base projection sum including the Captain multiplier. Scenario generation lineage identifies which conditional world produced a candidate; it is not a calibrated probability or proof that the story will happen.

## Lineup 1 — J.K. Dobbins Captain

Dobbins rushing payoff with both QBs; DEN leader Waddle is the receiving anchor. This roster was generated under the reference and SEA run-control worlds.

| Slot | Player | Salary |
|---|---|---:|
| CPT | J.K. Dobbins | $12,600 |
| FLEX | Bo Nix | $9,600 |
| FLEX | Sam Darnold | $9,800 |
| FLEX | Cooper Kupp | $3,200 |
| FLEX | Jason Myers | $5,000 |
| FLEX | Jaylen Waddle | $9,000 |
| **Total** | | **$49,200** |

## Lineup 2 — Jaylen Waddle Captain

DEN passing upside through Waddle Captain and Nix, with Darnold/Barner on SEA. It was generated under the reference and DEN breakout worlds.

| Slot | Player | Salary |
|---|---|---:|
| CPT | Jaylen Waddle | $13,500 |
| FLEX | Bo Nix | $9,600 |
| FLEX | Sam Darnold | $9,800 |
| FLEX | Jason Myers | $5,000 |
| FLEX | AJ Barner | $4,200 |
| FLEX | RJ Harvey | $6,400 |
| **Total** | | **$48,500** |

## Lineup 3 — Courtland Sutton Captain

DEN passing-upside alternative through Sutton Captain plus Nix/Waddle; Darnold/Barner provide SEA receiving linkage. Generated in the DEN breakout world.

| Slot | Player | Salary |
|---|---|---:|
| CPT | Courtland Sutton | $12,000 |
| FLEX | Bo Nix | $9,600 |
| FLEX | Sam Darnold | $9,800 |
| FLEX | Jason Myers | $5,000 |
| FLEX | AJ Barner | $4,200 |
| FLEX | Jaylen Waddle | $9,000 |
| **Total** | | **$49,600** |

## Lineup 4 — RJ Harvey Captain

Harvey Captain supplies the fourth legal exposure choice, with Nix/Waddle and Darnold/Barner. Added under the current reference world; his backup role makes this a more speculative Captain branch, not an asserted promotion.

| Slot | Player | Salary |
|---|---|---:|
| CPT | RJ Harvey | $9,600 |
| FLEX | Bo Nix | $9,600 |
| FLEX | Sam Darnold | $9,800 |
| FLEX | Jason Myers | $5,000 |
| FLEX | AJ Barner | $4,200 |
| FLEX | Jaylen Waddle | $9,000 |
| **Total** | | **$47,200** |

## Portfolio review

Bo Nix, Sam Darnold, Jason Myers and Jaylen Waddle appear in all four. Captain exposure is diversified, but the portfolio still shares a four-player core and every Captain is DEN. These four legal rosters therefore do not represent four independent game outcomes. The research packet includes SEA run-control, but this small selected portfolio does not directly express that branch with a SEA RB Captain. The current model favors the selected combinations under the declared constraints; this is not evidence that Denver is likely to score 40.

Dobbins is the app’s provisional recommendation because it has the highest saved model mean among these four. Waddle/Sutton are the clearest DEN passing what-if constructions. Harvey is the weaker role-based Captain expression: he remains an expected backup in source evidence, and the extra candidate is an exposure-feasibility alternative, not new football evidence.

Ownership fields are modeled estimates; paid-finish probability, duplication-adjusted value, expected return and the scenario likelihoods are not validated here. Final injury/active checks and entry clearance remain separate. No contest entry or export was performed.

## Automatic lineage

- Prepared run: `3944590c-b011-4f61-a4ee-9bdb301c026f`
- Projection: `c9dbf8c9-6c35-4de3-88cd-a7f2855b81e0`
- Authored packet: `004b4fbbf16f2a60c6f4efa657abb72492750624b51446f8cf8741e7548d43fa`
- Checked packet: `69627a8fb629f8f6c429f7a8ef9af551a8dc69c7a806bd65e18bf1fa19662915`
- Compatibility: `ccbe86986b0b7d376fcd98277df5bd402a29f907a07ac1a6bc2c593f3c7944fc`
- Prepared source hash: `a731a02fdfc3858981373d6d85c6652e1a8bf748202ec65552d16e8d8ed5298d`

The saved job parameters, runtime prepared-research receipt, checked packet, compatibility artifact and selected lineup tags match. Chrome Reopen results loaded this same saved run. Full machine assertions are in `verify_final.py` and `FINAL_ACCEPTANCE.json`.
