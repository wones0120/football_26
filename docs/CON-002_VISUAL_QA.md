# CON-002 Workspace Visual QA

Validated: 2026-07-24

## Scope

The consolidated Vite application was rendered against the local FastAPI API at:

- Desktop: `1440 × 1000`
- Mobile: `390 × 844`

The pass covered Digital Twin, Models, War Room, Research Lab, Delivery,
Intelligence, Operations, and the command-palette-only Experience Lab.

## Interaction Checks

- Used every desktop rail destination and every mobile navigation destination.
- Opened the workspace command palette at both widths and used it to open
  Experience Lab.
- Verified the 390px palette fits the viewport, closes with Escape, and returns
  focus to the command trigger.
- Confirmed navigation labels match their destination titles.
- Confirmed empty, ready, error, and disabled states remain readable. Disabled
  controls expose the native `disabled` state and visible disabled styling.
- Confirmed Research Lab mounts inside its open Shadow DOM boundary.
- Confirmed wide Research Lab and Operations tables remain usable inside local
  horizontal scrollers instead of widening the page.

No ingest, optimizer, export, or other state-mutating workflow was executed as
part of this layout-focused gate.

## Findings And Resolution

The first 390px pass found page-level horizontal overflow in Models and Delivery:

| Workspace | Viewport width | Initial page scroll width | Cause |
| --- | ---: | ---: | --- |
| Models | 390px | 653px | The shell's desktop command-grid selector outranked the workspace mobile rule. |
| Delivery | 390px | 651px | The shell's desktop command-grid selector outranked the workspace mobile rule. |

`ui/src/AppShell.css` now applies a single-column command grid at the shell mobile
breakpoint. The repeated 390px pass measured a `390px` page scroll width for both
workspaces, with all season, week, and slate controls visible.

## Final Matrix

| Workspace | Desktop page overflow | 390px page overflow | Command surface fits | Table handling |
| --- | --- | --- | --- | --- |
| Digital Twin | None | None | Yes | No table in the tested state |
| Models | None | None | Yes | No table in the tested state |
| War Room | None | None | Yes | Responsive decision board |
| Research Lab | None | None | Yes | Local horizontal scroller (`332px` viewport / `651px` content at mobile) |
| Delivery | None | None | Yes | No populated report table in the tested state |
| Intelligence | None | None | Yes | No table in the tested state |
| Operations | None | None | Yes | Local horizontal scroller (`314px` viewport / `690px` content at mobile) |
| Experience Lab | None | None | Yes | Pressure matrix reflows to `306px` at mobile |

Browser console validation reported no warnings or errors.

## Validation Commands

```bash
cd ui
npm run build
```

Rendered validation used the local Vite and FastAPI development servers with the
in-app browser's explicit desktop and 390px viewport overrides.
