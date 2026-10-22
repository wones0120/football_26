# X05-M04/M05 — observed called-pass / rush decisions in scoring zones

These are observed preplay-state conditional frequency features, never fitted future decision probabilities or scoring forecasts.

X05-M04 uses preplay yardline_100 in[0,5] and separates native down1–4 and exact integer native yards_to_go (0–100), with no outcome-tuned bins. X05-M05 independently uses source goal_to_go=True and separates down1–4; goal-to-go is not guessed from yardline. The subsets overlap and are never added as independent opportunities.

Use the independently reviewed G02 call classifier: a nonspike reported dropback is a called-pass decision; a designed/other nonkneel official rush with known not-scramble/not-dropback is a rush decision. Scramble is counted once as dropback; sacks remain pass calls. Known spikes, kneels, no-play, two-point and nonoffensive-count events are excluded. No play-call intent beyond this declared operational definition is inferred.

Within each observed native offense/team/game/state cell, report pass calls, rush calls and their fractions of known decisions. Unknown membership or unknown call masks the exact value of its known coordinate. A missing/invalid coordinate could belong to any cell, so it masks all exact cells for that native team game; known samples remain separate. A zero known decision denominator is undefined, not0/0 or a certified zero-pass choice. Unobserved cells are absent rather than fabricated zeros. Native source/team/game keys are before player preferences or eligibility; no player role inference or identity join is performed by these team features.

Actual prior source:158teamlogs/10SF-WASsubset. Inside5 has365observedcells,360exact positive decision cells,163knownpass+245knownrush calls,3unknown-coordinate events. Goal-to-go has360cells all360exact,309knownpass+332knownrush calls and0unknown-coordinate events. The original source itself has unverified full-game coverage; exactness is within observed source logs. Cell n is visible and no shrinkage/calibration/causal claim is made.

One immutable parent read revalidates original prelock boundary against its original source bytes; actual retrospective read/derive/publication are current. No historical pregame reconstruction or current serving readiness is implied. Artifacts are revised/postlock descriptive/nonserving with original source/parent refs. No new fetch, model fit, database write, optimizer/scenario activation or saved lineup/settings change.
