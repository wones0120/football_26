# Showdown Optimizer Repair TODO

Goal: prevent backup quarterbacks from entering production Showdown lineups and make the validated captain-archetype research drive Showdown GPP generation.

- [x] Confirm the canonical, ID-based source of QB starter evidence for the selected slate. The weekly roster has no QB1 distinction; the current fallback is recorded as a DraftKings salary inference.
- [x] Filter the canonical Showdown player pool to evidence-backed starting quarterbacks and fail clearly when starter evidence is unavailable or ambiguous.
- [x] Preserve the basic Showdown GPP strategy for historical comparisons and add a versioned captain-informed production strategy using the validated `0.35` prior.
- [x] Switch the Operations/Models UI Showdown GPP default to the captain-informed strategy.
- [x] Persist starter-filter and captain-model inputs in optimizer lineage/explanations.
- [x] Show both roster slot and natural player position in generated lineup results.
- [x] Add regression tests for backup-QB exclusion, missing/ambiguous starter evidence, strategy selection, and captain weighting.
- [x] Run targeted backend and UI checks, then inspect the final diff for regressions.
- [x] Update operator documentation and release notes with the behavior and evidence requirements.
- [x] Record the hard construction rule
  `showdown_qb_captain_same_team_wr_te_v1`: when the captain is a QB, at least one
  same-team WR or TE must occupy a FLEX slot.
- [x] Add the rule to new versioned cash and GPP strategies while preserving the
  baseline and captain-informed v1 contracts for historical comparisons.
- [x] Enforce the rule in both the ILP and independent post-solve validation.
- [x] Persist the enabled rule contract and validation result in optimizer-run and
  lineup lineage, with solver, validator, strategy-selection, and restoration tests.
- [x] Complete live GPP smoke run
  `1639d836-427d-4c62-9ba2-6a7be5208f4d` against projection run
  `4dc8026d-071f-4c7b-86ec-14ecf1f30804`; the v2 strategy, hard rule, and
  independent validation all persisted successfully.
- [x] Pass the full verification gate: 484 backend tests, 13 UI tests, and the
  production UI build.
