# Week 1 Projection Context Repair

Goal: allow a newer DraftKings slate download to replace the active curated
salary slice, keep every projection input auditable, and prevent unavailable or
non-starting players from consuming usable projection volume. Raw source rows,
pregame evidence, and completed projection runs remain immutable.

## Completed platform work

- [x] Persist the DraftKings `Status` column on canonical salary rows.
- [x] Keep each raw salary import and ingest run for lineage while replacing the
  active curated season/week/slate slice with the latest valid import.
- [x] Exclude `OUT`, `IR`, `PUP`, `NFI`, reserve, inactive, and suspended salary
  rows before projection scoring.
- [x] Apply the same salary-status gate to optimizer candidate pools.
- [x] Apply current weekly-roster `ACT` eligibility before projection scoring
  when roster evidence is available, retaining DST without a player record.
- [x] Report status exclusions in projection lineage and slate readiness.
- [x] Synchronize scored canonical display records into `target.dim_player` so
  players such as Jadarian Price and Behren Morton render by name.
- [x] Carry strictly prior opportunity into Week 1 from the preceding season,
  including three-game carries and targets plus team carry/target shares.
- [x] Preserve lagged full-team carry/target volume even when the players who
  produced it are no longer eligible for the current slate. Current-player
  history is no longer mistaken for the team total.
- [x] Add append-only, cutoff-safe pregame context runs keyed only by
  `player_master_id`, with availability, QB start probability, RB carry share,
  RB/WR/TE target share, role, injury status, source, observation time, receipt
  time, and evidence JSON.
- [x] Add Models UI controls to restore and save that context for the selected
  season, week, and slate. Saving evidence does not silently rerun projections.
- [x] Apply starter and pregame evidence before point scoring. Backup QBs receive
  zero usable projection, and current team opportunity is reallocated before
  scoring rather than disappearing when an ineligible player is removed.
- [x] Keep historical production features immutable and apply current role
  evidence through a separate, persisted position-specific isotonic opportunity
  anchor trained only on prior rows. Zero-history players now respond to assigned
  workload instead of retaining a generic rookie mean.
- [x] Make the raw projection API expose the actual canonical team, opponent,
  prior-season recency, opportunity, and pregame lineage used for each row.
- [x] Include kickers in feature/scoring inputs. Until canonical historical
  kicker rows exist in the shared model matrix, require prior game history and
  use the disclosed 60/40 roll-three/roll-eight history anchor instead of
  extrapolating the skill-position model.
- [x] Persist and display the complete optimizer pool, including excluded rows
  and reasons, with a full JSON download in the UI.
- [x] Add migration, ingestion, projection, context, optimizer, API, and reload
  regression coverage.
- [x] Import and verify the September 7 Wednesday-night DraftKings salary file.
- [x] Build immutable challenger runs and verify Charbonnet and Boutte are
  absent while Price and Holani remain eligible.

## Remaining evidence and promotion work

- [x] Capture an authoritative point-in-time depth-chart/expected-role source,
  or enter cited evidence through the pregame context editor, for the active
  Wednesday slate.
- [x] Enter and review current target/carry shares for Hollins, Douglas, Doubs,
  Shaheed, Price, Holani, and the other active receivers/backs. The allocation
  run is explicitly labeled as an analyst estimate, not a team-reported share.
- [x] Capture the current Sunday/Monday practice evidence and enter an interim
  availability/workload decision for Henderson and Horton.
- [x] Supersede the interim injury probabilities after the final Tuesday game
  designations are published. Never overwrite the earlier evidence run.
- [ ] Add an automated injury/depth-chart capture adapter if repeated manual
  entry becomes too slow. The durable evidence contract does not require that
  future adapter to change projection or UI interfaces.
- [ ] Backfill canonical historical kicker features and evaluate position-aware
  kicker calibration. The temporary history anchor is explicit and safe, but it
  is not a promotion-quality kicker model.
- [x] Rerun the current slate after evidence is stored and evaluate its complete
  37-player pool plus one Showdown optimizer smoke lineup.
- [x] Create a named governance evaluation and explicitly promote the challenger.

## Next optimizer-rule phase

- [x] Record the user's exact first rule: a QB captain requires at least one
  same-team WR or TE in FLEX.
- [x] Keep the rule as a named hard construction constraint, separate from
  eligibility/roster filters and future strategy preferences.
- [x] Extend the existing captain-informed Showdown strategy rather than silently
  changing the preserved baseline contract.
- [ ] Backtest proposed captain-position, construction, correlation, and punt-role
  constraints against the existing historical Showdown cohort.
- [x] Persist the enabled QB-captain rule and validation result in optimizer lineage
  and add solver, validator, persistence, and strategy-selection regression tests.
- [ ] Expose configurable rule choices and the lineup-feedback path in the UI.

## Acceptance checks

- [x] Reloading a changed CSV keeps prior raw evidence but selects only the new
  curated slate rows.
- [x] DraftKings `OUT` rows never appear in a new projection run or optimizer
  candidate pool.
- [x] Missing/unknown status remains eligible; `Q` and `D` are retained for the
  injury-adjustment layer rather than treated as confirmed absences.
- [x] Every exclusion stores the source status, player identity, ingest run, and
  cutoff-safe lineage.
- [x] Multiple active QBs fail closed without starter evidence; a selected
  starter receives full start probability and backups receive zero.
- [x] Pregame evidence is restored after reload/slate changes and is visible
  only when both its observation and receipt timestamps precede the run cutoff.
- [x] The optimizer audit contains all 37 active salary players, includes both
  kickers with nonzero projections, and excludes four backup QBs plus any player
  with zero availability in the selected projection lineage.
- [x] Full backend suite (481), all UI tests (13), and the production UI build
  pass on September 8, 2026.

## September 8 verification

- Salary snapshot: `b61f0287-177f-5993-98e8-7d216cf5e335`
- Salary ingest: `597fa402-3878-5d31-aee8-cf79193b38ca` (136 raw / 136 curated)
- Eligibility-only projection run: `d8bcafe3-6ed3-4cd4-a363-efd6216e807a`
  (35 rows before kicker support)
- Full opportunity-context challenger:
  `c5955864-6df5-493f-bfa7-5ca557bc1382` (37 rows)
- Optimizer smoke run: `4f9a6f4d-1a8f-46a6-a6a2-a4e5c7ed3139`, completed
  with Showdown validation passed, 33 included rows, and four excluded backup
  quarterbacks.
- Verified absent: Zach Charbonnet and Kayshon Boutte.
- Verified resolved: Jadarian Price, Behren Morton, and every other challenger
  row has a display name.
- Verified backup QBs at zero: Tommy DeVito, Behren Morton, Drew Lock, and Jalen
  Milroe.
- Verified kicker coverage: Jason Myers 12.05 mean / 19.47 P90 and Andy
  Borregales 3.85 / 11.27 under the temporary prior-history contract.
- Base pregame context run:
  `ccd0245f-4482-43f2-98c6-f03e3eaf7d1d` (33 canonical player rows). It combines
  official team depth-chart/practice evidence with explicitly labeled analyst
  shares and interim availability estimates.
- Full-team opportunity/context challenger:
  `6dedb982-87a6-4530-a49d-fa839f08e99e` (37 rows). Seattle preserves 27.0
  prior carries and 28.67 targets; New England preserves 23.0 and 29.0.
- Key means: JSN 14.29, Shaheed 7.46, Price 8.70, Holani 6.59, Douglas 5.67,
  Hollins 4.99, Stevenson 13.90, and Henderson 2.36 after the interim 50%
  availability probability.
- Context challenger optimizer smoke run:
  `feec9455-8e48-4bff-b891-b5e8f0a42045`, completed with 37 initial rows,
  33 included rows, four backup QBs excluded, and Showdown validation passed.
- Governance evaluation `model-evaluation:393ac0fde7b4b9b374b88341` passed
  five structural gates. Promotion decision
  `model-decision:6479c41a92d7331d24536deb` selected the challenger while
  retaining the previous run as the rollback target.
- Final Tuesday injury context run:
  `9378fdde-60a0-461d-aaa4-bf269cbe3fb4`. The official final report changes
  Henderson from an interim 50% estimate to `OUT`/0% and Horton from an interim
  unspecified status to `QUESTIONABLE` with a disclosed 75% analyst estimate.
- Final-injury projection run:
  `4dc8026d-071f-4c7b-86ec-14ecf1f30804` (37 auditable rows). Henderson is 0.00;
  Stevenson rises from 13.90 to 14.95 as unavailable workload is redistributed.
- Final optimizer smoke run:
  `6ad1c235-bed2-46cc-9f7a-26590a8b287e`, completed with Showdown validation
  passed. Its audit contains all 37 salary players, includes 32, and excludes
  Henderson as `pregame_unavailable` plus four backup quarterbacks.
- Final governance evaluation `model-evaluation:681cc8903bf348b9bd298f54`
  passed all six declared gates. Promotion decision
  `model-decision:3e4dfe4a924820ce7577c8c6` selected the final-injury run.

The governed active pointer is now
`4dc8026d-071f-4c7b-86ec-14ecf1f30804`. The prior active run
`6dedb982-87a6-4530-a49d-fa839f08e99e` remains immutable and is the recorded
rollback target; the original `3868cdda-7380-4e99-83a9-80f14894b5b0` run also
remains retained. No UI refresh or newer run silently changes that decision.
