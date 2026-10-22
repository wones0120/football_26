# Candidate metric catalog — 240 metrics

Planning inventory, not implemented features or verified data availability. Within each group, the ten semicolon-separated entries retain their original order. Stable IDs: G01-M01 through G24-M10. Observed measures, pregame context, and forecasting targets must be classified separately during audit.

1. Team pace and play volume: Offensive plays/game; plays/drive; possessions/game; seconds between plays; neutral-situation pace; no-huddle rate; first-half pace; second-half pace; trailing pace; leading pace.
2. Team passing and rushing decisions: Pass rate; neutral pass rate; pass rate over expectation; early-down pass rate; first-down pass rate; third-down pass rate; red-zone pass rate; goal-line pass rate; trailing pass rate; leading pass rate.
3. Quarterback passing workload: Dropbacks; pass attempts; completions; sacks taken; throwaways; spikes; scrambles per dropback; designed rollout rate; play-action rate; QB share of team dropbacks.
4. Quarterback passing effectiveness: Completion percentage; completion percentage over expectation; yards/attempt; air yards/attempt; yards/completion; passing EPA/dropback; passing success rate; interception rate; sack rate; passing touchdown rate.
5. Quarterback rushing: Designed rushing attempts; scrambles; kneel-downs; scramble rate under pressure; rushing yards/attempt; rushing success rate; first-down rushes; red-zone rushes; inside-five rushes; rushing touchdowns.
6. Running-back rushing workload: Carries; team carry share; early-down carries; third-down carries; short-yardage carries; two-minute carries; first-half carries; fourth-quarter carries; carries while leading; carries while trailing.
7. Rushing effectiveness and style: Yards/carry; rushing EPA; rushing success rate; explosive-run rate; stuffed-run rate; first-down conversion rate; yards before contact; yards after contact; missed tackles forced; rushing yards over expectation.
8. Receiving opportunity: Targets; target share; routes run; route participation; targets/route; first-read target share; air yards; air-yard share; average target depth; catchable-target rate.
9. Receiving effectiveness: Catch rate; catch rate over expectation; yards/target; yards/reception; yards/route; receiving EPA/target; receiving success rate; yards after catch/reception; drops/catchable target; explosive-reception rate.
10. Receiving role and deployment: Slot alignment rate; outside alignment rate; backfield alignment rate; inline TE alignment rate; pre-snap motion rate; screen-target share; short-target share; intermediate-target share; deep-target share; contested-target share.
11. Field-position opportunity: Carries outside the 20; carries from the 6–20; carries inside the five; targets outside the 20; targets from the 6–20; targets inside the five; pass attempts outside the 20; pass attempts from the 6–20; pass attempts inside the five; goal-to-go opportunity share.
12. Touchdown and scoring opportunity: Team offensive TDs/drive; team rushing-TD rate; team passing-TD rate; player rushing-TD share; player receiving-TD share; red-zone TD conversion; inside-five TD conversion; end-zone targets; explosive-play TD rate; touchdowns versus expected scoring opportunities.
13. Offensive line and protection: Starting-line continuity; missing starting linemen; pressure allowed/dropback; sack rate allowed; time to pressure; pass-block win rate; run-block win rate; short-yardage rushing success; runs stopped behind the line; rushing success by direction.
14. Opponent pass defense: Pressure rate; blitz rate; sack conversion; man-coverage rate; zone-coverage rate; completion percentage allowed over expectation; explosive passes allowed; yards after catch allowed; passing success rate allowed; passing touchdowns allowed per red-zone trip.
15. Opponent run defense: Rushing success allowed; rushing EPA allowed; explosive runs allowed; stuff rate; yards before contact allowed; yards after contact allowed; missed-tackle rate; short-yardage conversion allowed; inside-five TD conversion allowed; QB rushing production allowed.
16. Matchup-specific advantages: Slot receiver versus slot coverage; outside receiver versus boundary coverage; TE versus coverage personnel; receiving back versus linebacker coverage; deep passing versus deep coverage; screen offense versus screen defense; pressure versus protection; run direction versus defensive front; mobile QB versus containment; player performance versus man/zone tendencies.
17. Player availability and replacement roles: Official game designation; practice participation trend; verified inactive history; return-from-absence status; current depth position; recent snap trend; replacement route share; replacement carry share; missing teammate opportunity; documented workload restriction.
18. Team availability and personnel: Starting-QB availability; backup-QB experience; offensive-line starters unavailable; defensive-line starters unavailable; cornerbacks unavailable; safeties unavailable; linebackers unavailable; receiving production unavailable; backfield production unavailable; personnel-package continuity.
19. Market and expected game environment: Pregame total; opening total; total movement; point spread; opening spread; spread movement; team implied points; opponent implied points; moneyline-implied win probability; disagreement between market and internal team projection.
20. Venue, weather and scheduling: Home/away; indoor/outdoor; retractable-roof status; temperature; sustained wind; wind gusts; precipitation; playing surface; rest days; travel/time-zone change.
21. Situational workload splits: Home/away workload difference; workload versus expected total; workload versus expected spread; workload versus implied team points; workload on short rest; workload in prime time; workload indoors/outdoors; workload in high wind; workload against strong/weak defenses; workload with the current starting QB.
22. Recent form and coaching changes: One-game versus longer-term workload; three-game versus season workload; recent efficiency trend; recent snap trend; recent route trend; recent scoring-role trend; coordinator change; play-caller change; publicly supported depth-chart change; post-fumble usage change.
23. Kicker and team-defense opportunities: Field-goal attempts; field-goal distance distribution; field-goal accuracy by distance; extra-point attempts; drives ending in scoring range; offensive red-zone stall rate; defensive sack opportunities; defensive interception opportunities; defensive fumble-recovery opportunities; opponent expected points allowed.
24. Complete-lineup and portfolio relationships: QB–receiver shared scoring; receiver–receiver target competition; RB–RB carry competition; rushing-versus-passing TD competition; opponent keep-pace dependence; player–opposing-DST conflict; salary opportunity cost; dependence on uncertain replacement roles; shared game-failure exposure; probability of multiple players reaching useful ceiling outcomes.

## Ownership

- Game environment: G01, G02, G19, G20, G21.
- Quarterbacks: G03–G05.
- Rushing and protection: G06, G07, G13.
- Receiving: G08–G10.
- Scoring opportunities: G11, G12, G23.
- Defense and matchups: G14–G16.
- Availability and role changes: G17, G18, G22.
- Lineup integration: G24.

## Constraints

- No metric implementation or model training authorized in this inventory phase.
- Source availability must be verified, especially tracking, coverage, pressure and route metrics.
- Zones are mutually exclusive; goal-to-go is a separate overlapping condition, not an extra zone.
- Realized game context is not a pregame predictor. Historical splits require sample sizes and smoothing design.
- Counts, model outputs, judgments and probabilities are distinct; joint ceiling probability requires validation.
- Shared QB/receiver events and correlated workload signals must not be double counted.
