# G11 field-position measurements

`build_player_scoring_zone_components` consumes a validated prior-only event receipt after the caller authenticates immutable raw and parent artifacts. The actual derivation uses the indexed snapshot and the existing verified parent loader, without another source download.

Each row is one native game/team/player, attached to the authenticated canonical UUID where known. No display-name joins or user eligibility filters apply. Counts describe the observed log, not certified complete games.

| IDs | Channel | Disjoint preplay field-position definitions |
|---|---|---|
| G11-M01–03 | Official rushing attempts, including kneels | Outside20: yardline_100>20; 6–20: >5 through20; inside5:0 through5 |
| G11-M04–06 | Official attributed receiving targets | Same three preplay zones; these are not catch locations |
| G11-M07–09 | Official passing attempts, including spikes, excluding sacks | Same three zones; scramble is a rush rather than an official pass |
| G11-M10 | Declared channel-specific goal-to-go shares | Player known GTG events divided by the full team's same-channel GTG events; no composite opportunity share is claimed |

Goal-to-go uses the source flag, not inferred yardline. Pass and receiver target may describe one physical event; their shares/counts must not be summed as independent opportunities.

`counted_lower_bound` remains available when exactness is unknown. Missing eligibility or field position masks the affected exact count. Missing rusher/passer identity preserves the known team event but masks candidate actor exact attribution; missing receiver identity may also leave target eligibility unknown. Unmapped native actors remain in full-team denominators and identity requests. A zero GTG denominator produces a null share, never a fabricated zero. `all_official` and `unknown_zone` counters make the partition auditable; known zone counts plus unknown-zone counts reconcile to known official events.

The explicit retrospective reader verifies the frozen parent at its original evidence boundary while retaining actual read/derive/publication timestamps. Actual artifacts are marked `postlock_descriptive_not_pregame_or_serving`; current registration, forecast and scenario guards reject them. All earlier source artifacts remain immutable.

The 11-test gate covers zone boundaries, official spike/kneel/sack/scramble semantics, full-source and unmapped budgets, unknown eligibility/identity/zone/GTG, zero denominators, excluded events, native/canonical scope, chronology, material versus recapture changes, and postlock rejection. Actual coverage and hashes are in `actual_derivation_receipt.json` and `actual_QA.json`. Model/optimizer integration is separately pending under the features-only priority.
