# Shared-event player opportunity assignment and accounting

Completed **eight explicitly synthetic fixture cases** with 17 retained event records. One bounded audit took **0.235 seconds** under a 10-second internal cap and 30-second external timeout. **196 targeted tests passed in 1.85 seconds**, including 34 new shared-event tests. All **675 preservation hashes** match; prior pilot results and backend product-service Python files are unchanged.

A targeted pass retains **one physical event identity**, with its passer attempt and receiver target as two nested channel credits. It does not become two physical plays. Each event/channel has at most one actor credit; canonical UUIDs, team membership and explicit actor capabilities/conditional participation govern fixture assignment. No player selection probability is estimated or sampled. Prior authored vacancy fractions are not consumed.

| Fixture case | Retained accounting |
| --- | --- |
| Mixed supported mechanisms | 7 official-scope physical plays, 3 pass attempts, 3 carries, 1 target; 3 excluded/control records retained |
| Unresolved receiver on known targeted pass | 1 assigned pass attempt, 1 unassigned residual target |
| Unknown target eligibility | 1 pass attempt; exact target count remains null |
| Unknown event mechanism | Physical count and exact opportunity totals remain null |
| Unknown receiver role | Target remains residual; no alternative receiver gets it |
| Unknown receiver participation | Target remains residual |
| Unavailable receiver | Target remains residual |
| Unmapped receiver UUID | Requested UUID retained with identity reason; target remains residual |

The mixed case includes a targeted pass, an explicitly no-target pass, spike, sack, designed/other rush, scramble, kneel, no-play, two-point try and control. Sacks remain physical plays without official pass attempts or carries. Spikes count as attempts without targets; scrambles and kneels count as carries. No-play, two-point and control records remain outside these official count/physical-play denominators. The physical count is an official offensive-play counting scope, not a count of every football action.

For each known eligible team opportunity, **assigned player credit + residual credit = known eligible count**. Unknown eligibility is tracked separately and prevents an exact total; it is not converted into an unassigned known unit or zero. Per-player assigned counts are explicitly lower bounds, with team-channel eligibility-unknown flags. Missing actor, role or participation evidence preserves requested identity and reason in the unresolved-assignment ledger. No salary-pool renormalization or preference-driven reassignment occurs. Declared fixture participation is a conditional assumption, not evidence of actual game dressing.

[ASSIGNMENTS.json](ASSIGNMENTS.json) retains input events/rosters, shared-event credits, residual reasons, unknown eligibility, physical scope and player lower bounds. [SUMMARY.json](SUMMARY.json) retains case counts; [MANIFEST.json](MANIFEST.json) binds the code, fixtures, recipe, outputs and unchanged production event module. [VALIDATION.json](VALIDATION.json) records final checks.

Tests cover shared physical identity, sack/spike/scramble/kneel and excluded scope, known residual versus unknown eligibility, UUID/team/mechanism conflicts, duplicate events/actors, multiple receivers per slot, one-game scope, missing passer with known receiver, omitted actors, unavailable/unknown participants and user-preference isolation. Existing observed-event and prior vacancy/workload/role/accounting tests also passed. No UI/full-suite run was needed for this research-only module.

No network, source refresh, database/service, alias write, fit, probability draw, simulation rerun, production/scoring consumer or live projection/settings change ran. This establishes fixture assignment mechanics, not empirical actor-event probabilities, a player forecast or improved full-game accuracy. Event-linked yards, completions, touchdowns and fantasy scoring remain absent. The next independent mechanics slice can test those production/scoring relationships with explicit fixtures and unknowns before empirical integration. Timing investigations remain deferred; calibrated assignment, predictive validation and live promotion remain gated.
