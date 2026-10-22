# Offensive environment catalog v1

This package exposes two exact named views of the independently reviewed environment-context producer. It does not recount or double-count physical plays, change source data or add forecasts.

- **G01-M01:** physical official offensive snaps per observed team-game log. The source union counts official passing attempts including spikes, official rushes including kneels and sacks once. Scrambles appear once as physical rushes, never as an additional snap because they are also dropbacks. Known snap counts remain a lower bound whenever eligibility is unknown; the exact value is null then.
- **G01-M06:** no-huddle flags divided by the same physical offensive snap denominator. Unknown eligibility or flags mask the exact rate. A zero denominator remains undefined; known zero no-huddle numerator with a positive complete denominator remains zero.

Same-season last-eight-observed-game windows use a pooled no-huddle numerator/denominator rather than averaging percentages. The volume window is the count per observed log, with all observed game identifiers retained. Missing games are not filled with zero; this is not a calendar-week, complete-season or independently certified full-game estimate. Unknown log eligibility masks exact pooled values while retaining known lower bounds.

The retrospective reader verifies the indexed original source artifact, the managed full-context bytes and compressed parent hash/size, source/period/event ancestry, publication clocks, per-metric lineage and both original producer/helper hashes. It does not inflate the 147MB logical event parent. The original context/parent/source clocks remain provenance alongside the actual postlock read time. These are descriptive revised measurements; original historical availability and complete final-game coverage remain unproven. Current output is explicitly ineligible for pregame serving, with no model, forecast, scenario or optimizer consumer.

The actual extraction has 158 team-game logs: 156 exact values per ID and two logs retaining uncertainty. There are 32 same-season observed team windows, with 30 exact values per ID. The prior artifacts remain immutable; `actual_receipt.json` binds the current code and 98,685-byte result. The new reusable context-verification function supports subsequent catalog views without redundant large-parent inflation.

Empty-known-sample correction: the shared helper legitimately emits a null outcome sum when no flags are known. The catalog retains a null measured numerator, an explicitly labeled zero known lower bound, and an undefined rate. All-missing flags and zero eligible snaps are covered separately, including pooled mixed known/unknown logs. This does not turn unknown no-huddle outcomes into certified zeros.
