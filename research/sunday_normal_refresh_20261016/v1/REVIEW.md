# Sunday Main normal refresh — October 16, 2026

**Normal preparation was attempted and remains blocked. No fresh normal lineup, projection comparison or defense ranking improvement is claimed.**

The shared API and worker were refreshed after all agents reported idle. Job `fadbc87c-921c-473f-8248-0538ed52aa26` used `preliminary_research=false`, ownership required and BASELINE Analyst mode. It refreshed official status/roster/depth/market evidence and built features, then failed before projection creation on the four current availability records below. The failed attempt remains saved; there was no readiness bypass.

| Player | Current evidence | Missing evidence |
|---|---|---|
| Max Klare (LAR TE) | Fresh active roster and backup depth | Current game status; prior native OUT is stale |
| CJ Daniels (LAR WR) | Fresh active roster and depth | Current game status; prior native OUT is stale |
| Joshua Palmer (BUF WR) | Fresh active roster/depth; limited practice | Current game designation |
| DJ Moore (BUF WR) | Fresh active roster/depth; did not practice | Current game designation |

An active roster membership or blank game-status cell does not clear the independent stale/missing game-status fact. The official Rams report does not list Klare or Daniels; last week’s healthy-inactive report cannot establish this week’s dressing status. No invented OUT, active probability or user exclusion was applied. [Exact source audit](unresolved_context.json) and [failed job](preparation_status.json) preserve the facts.

## Current primary QB evidence

- Eagles explicit Week 6 article confirms Tanner McKee as starter, replacing OUT Jalen Hurts. Captured and registered with canonical McKee ID `783b00df-c32b-4054-bff3-906ea6fbc4a7`, snapshot `b06e415d-011e-550e-adbc-cf8572f42929`, observed October 16 14:12:41 UTC. This replaces the earlier provisional depth inference with confirmed club evidence. [Official article](https://www.philadelphiaeagles.com/news/tanner-mckee-will-be-ready-for-his-moment-2026-nfl-week-6-carolina-panthers).
- Bears October 15 report says Caleb Williams practiced in full but game status remains uncertain. Full practice is not starter confirmation. [Official article](https://www.chicagobears.com/news/bears-qb-caleb-williams-practices-in-full-but-game-status-still-uncertain).
- Titans club depth chart, dated October 12, lists Cam Ward first and both Tate/Robinson as first receivers. It is explicitly an unofficial chart, not final dressing evidence. [Official depth](https://www.tennesseetitans.com/team/depth-chart).

[QB snapshot/ingest manifest](qb_refresh.json). No fantasy forecasts were changed by manual news assertions.

## Original saved lineup remains the comparison baseline

Run `f84e75db-b286-48f4-8740-c03d11323889` is a preliminary research run, not a normal entry-cleared run. It was reopened in the actual localhost app.

| Slot | Player | Team | Salary | Saved mean |
|---|---|---|---:|---:|
| QB | Matthew Stafford | LAR | $6,400 | 25.2159 |
| RB | Kyren Williams | LAR | $6,800 | 19.7847 |
| RB | Derrick Henry | BAL | $8,200 | 18.8087 |
| DST | Panthers | CAR | $2,500 | 4.6123 |
| WR | Puka Nacua | LAR | $8,100 | 21.8141 |
| WR | Carnell Tate | TEN | $5,000 | 11.2019 |
| TE | Tyler Higbee | LAR | $3,400 | 9.8587 |
| WR | Wan'Dale Robinson | TEN | $4,500 | 10.3182 |
| WR | Rome Odunze | CHI | $4,900 | 11.5285 |

Total **$49,800 / 133.1430 mean**. These are October 15 saved forecasts, not refreshed October 16 forecasts.

Tate ($5,000, 11.2019) and Wan’Dale ($4,500, 10.3182) combine for $9,500 / 21.5201. They were not forced: locks empty, favored-WR false, stacks optional, BASELINE Analyst. The objective sums individual baseline means and has no extra penalty for shared quarterback/target competition; cheap receiver means help afford Stafford, Kyren, Henry and Puka. Saved TEN market was +7 with 18.75 implied points, so the football concern is material. Opportunity inputs 6.9143/5.7818 are model lagged/redistributed proxies, not asserted raw target averages.

An existing same-input Hubbard-required alternative replaces Henry and Tate with Hubbard and Flowers, leaving only Wan’Dale: **$50,000 / 132.8018**, 0.3412 below the saved baseline. It is an available constrained comparison, not proof of the global optimum under a one-TEN cap.

## Settings and defense limits

The actual current Chrome controls were preserved in [current_controls.txt](current_controls.txt): five lineups, 80% exposure, max three/team and four/game, all favored toggles off, all position season-average ranks top 50%, Analyst scenarios/Mixed; no locks/player exclusions, DEN-opponent exclusion, questionable exclusion, single TE and no offense versus DST. These differ from the old one-lineup highest-baseline preliminary request. No controls were overwritten and no contrarian generation was run.

Defense source-support plumbing is active after the coordinated restart, but candidate ranking promotion failed validation. Incumbent numerical model contract remains `incumbent_dst_matrix_legacy_v1`; no unvalidated model was activated. This failed preparation never reached the projection support hook, so no new per-run defense-support result exists. A normal rerun and valid refreshed lineup comparison remain outstanding until the current player-source evidence passes.
