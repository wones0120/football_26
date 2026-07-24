# Slate War Room TODO

> Status: historical War Room checklist. Current implementation status and priority are tracked in `docs/TODO.md`; do not execute the old handoff prompt as the active plan.

## Goal

Turn `Slate War Room` from a static mock into the primary DFS analytics workspace.

The War Room should answer:

- What changed?
- Which players/games matter?
- Which lineup decisions are unresolved?
- What portfolio stance are we taking?

Keep data loading and operational utilities behind `Operations`.

## Guardrails

- Preserve the current War Room visual direction.
- Do not turn the UI back into large sections of buttons.
- Do not remove the existing Operations workflow.
- Do not introduce new dependencies unless clearly justified.
- Use `football_26_dev` for backend/database work.
- Use `2025 / week 11` as the default replay/workbench context unless a later task explicitly changes it.
- Work in small slices and run `npm run build` after each slice.
- If `npm run lint` fails only on pre-existing `App.tsx` `any` usage, report it but do not refactor unrelated code.

## Implementation TODO

### 1. Signal Tape

- Add a typed frontend API helper for the news-monitor report.
- Replace static `signals` data in `ui/src/WarRoom.tsx`.
- Show high/medium DFS relevance signals first.
- Include source, signal type, player/team when available, confidence, and source link.
- Add empty state: `No slate-moving signals found yet.`
- Add compact error state without breaking the layout.
- Add a compact War Room control to manually run the news monitor for the active day/context.

Acceptance check:

- `npm run build` passes.
- War Room still renders if no report exists.
- Operations button still opens the legacy workflow.
- Manual news-monitor run button reports loading/success/failure without disrupting the rest of the War Room.

### 1A. Daily News Scheduler

- Add a local daily scheduler for `POST /api/news-monitor/run`.
- Prefer a simple `launchd` or cron-style setup for the local Mac dev workflow before adding backend scheduler complexity.
- Use `PGDATABASE=football_26_dev` when scheduler commands touch backend/database context.
- Document how to install, disable, and manually test the scheduler.
- Keep the scheduler source-aware: default to enabled allowlisted sources, with optional override for specific `source_ids`.

Acceptance check:

- Daily run can be triggered manually from the scheduler command.
- Scheduled run writes a normal news-monitor report.
- Failure mode is inspectable from local logs.

### 2. Decision Board

- Replace mock player rows with projection and ownership data.
- Add typed frontend adapters in `ui/src/api.ts`.
- Show player, team, position, salary, projection, ceiling/P90, ownership, leverage, and stance.
- Compute simple frontend leverage initially if backend does not expose it.
- Derive initial stance:
  - `Core` for strong projection and acceptable ownership.
  - `Over` for strong leverage.
  - `Under` for weak leverage or excessive ownership.
  - `Debate` for conflicting signals.

Acceptance check:

- No fake player rows remain when real data is available.
- Empty state is useful when projections are missing.
- Table remains horizontally usable on narrow screens.

### 3. Game Pressure Matrix

- Group relevant projections/news by game.
- Remove fake betting totals unless real totals are available.
- Show matchup, affected players, stack posture, and primary risk.
- Keep the card compact and analytical.

Acceptance check:

- Game rows are generated from real slate/team data.
- Missing game metadata does not crash the page.

### 4. Debate Rail

- Add local state for human lineup decisions.
- Allow marking players or slate decisions as `Core`, `Over`, `Under`, `Fade`, or `Need more info`.
- Add a notes box for the current slate/player decision.
- Do not persist to backend yet unless the human-feedback API already exists.

Acceptance check:

- User can change stance without page reload.
- Debate state does not interfere with Operations or optimizer controls.

### 5. Candidate Lineups And Exposure

- Read latest optimizer results when available.
- Show candidate lineups with projected score, salary, ownership if available, stack summary, and rule/news explanations.
- Compute exposure by team and player from candidate lineups.
- Add useful empty state when optimizer has not run.

Acceptance check:

- Existing optimizer output still works in Operations.
- War Room does not assume every lineup has ownership or explanation fields.

### 6. Polish And UX Pass

- Keep the screen dense, modern, and analytical.
- Avoid landing-page hero patterns.
- Keep panel radius at or below the current War Room style.
- Validate desktop first, then mobile reflow.
- Do not add decorative assets.

Acceptance check:

- `npm run build` passes.
- No obvious clipping in the command bar, decision table, or debate rail.
- The default page feels like an analytics workstation, not a setup form.

## Handoff Prompt

```text
You are working in the canonical `football_26` repository.

Build the existing Slate War Room UI in small, verifiable slices.

Context:
- The default development database is football_26_dev.
- The current War Room files are:
  - ui/src/WarRoom.tsx
  - ui/src/WarRoom.css
  - ui/src/App.tsx
  - ui/src/api.ts
- War Room is the default UI.
- Legacy data-loading and utility controls must remain available through Operations.

Design requirements:
- Preserve the current War Room visual direction.
- Do not redesign the screen from scratch.
- Do not make it a landing page.
- Do not turn it into a stack of button sections.
- Keep it dense, modern, analytical, and useful for lineup debate.
- Do not add dependencies unless clearly justified.

Execution requirements:
- Work one slice at a time.
- After each slice, run:
  npm run build
- If npm run lint fails only because of pre-existing App.tsx `any` usage, report it but do not refactor unrelated code.
- Keep changes focused.
- Do not delete or break Operations.

First task:
Start with the Signal Tape only.

Replace the static `signals` array in `ui/src/WarRoom.tsx` with data loaded from the news-monitor report endpoint. Add the needed typed API helper in `ui/src/api.ts`.

If there is no existing latest-report endpoint, use the selected/current date if already available. If neither is available cleanly, create a small frontend adapter with a clear TODO and a safe empty state rather than changing backend behavior in this slice.

Signal Tape requirements:
- Show high/medium DFS relevance first.
- Include source, signal type, player/team when available, confidence, and source link.
- Add empty state: No slate-moving signals found yet.
- Add compact error state.
- Keep the existing layout and styling.

Validation:
- npm run build must pass.
- War Room must still render if no report exists.
- Operations button must still open the legacy workflow.
```
