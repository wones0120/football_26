# Analyst Reports

Open **Analyst Reports** in the app sidebar or command palette. Main football briefings appear first, newest recorded date first; specialist research and saved lineup reviews follow. Select a report and use **Week**, **Slate** and **Report type** to browse versions. **Refresh report list** picks up newly catalogued editions.

The Wednesday Wones Football Analyst briefing is the current main edition. The library includes the preserved Sunday review, all-game discovery, Thursday preview, Captain mechanism review, defense/kicker review, fitted team/game outlook and actual scenario/discovery/hunter/cheaper-teammate lineup comparisons. Model-training code and unrestricted artifact directories are not part of this reader.

Reading performs no packet import, generation, selection, projection update or entry action. **Readable research — not applied by reading** distinguishes research-only reports from **Documents applied analysis in the listed saved comparison runs**, whose original run IDs remain visible. Preliminary status appears only when explicitly recorded. A missing report date stays **Date not recorded**; filesystem modification time is not substituted for publication or source availability.

## Text and citations

The reader renders headings, paragraphs, emphasis, lists, blockquotes, fenced code and Markdown tables. External HTTP/HTTPS citations open separately. Raw HTML is displayed as escaped text; scripts and unsafe URL schemes are not executed. This is a bounded report renderer, not a complete Markdown/HTML editor.

Links to another catalogued report open that report. Explicitly catalogued JSON/CSV/text evidence opens as read-only text, with a **Back to report** button. Other relative references, HTML artifacts and uncatalogued local files show **local reference unavailable**. The library does not pretend those files were served, and does not expose arbitrary filesystem paths through API requests. Large evidence above 256 KiB returns an explicit unavailable/text-limit error; complete artifacts remain preserved on disk.

## Controlled catalog

`research/analyst_reports/catalog.json` is the versioned allowlist. Add a new immutable edition as a new `report_id`; preserve prior entries. Each entry supplies title, category (`briefing`, `specialist`, `lineup_review`), season/week/slates, version, nullable timezone-aware `recorded_at`, nullable `preliminary`, explicit `application_status`, saved comparison run IDs, summary, a research-relative Markdown path and optional named evidence paths. A recorded clock describes the report record, not proof of when every historical source was available.

Do not classify a new report as applied without actual saved-run evidence. Specialist reports remain research-only unless separately demonstrated otherwise. Register completed report/evidence files only; unavailable catalog files are visibly unavailable. Metadata updates are reviewed code/data changes, not an editable app flow or automatic directory scan.

Read-only API:

- `GET /api/analyst-reports`: bounded catalog metadata, with no serving paths.
- `GET /api/analyst-reports/{report_id}`: metadata, Markdown, content hash and controlled link mapping.
- `GET /api/analyst-reports/{report_id}/evidence/{evidence_id}`: approved source text and content hash.

The API validates IDs and catalog entries, caps the catalog at 100 reports and 20 evidence entries per report, restricts text suffixes, confines paths to the research root after symlink resolution and limits individual text to 256 KiB. Unknown IDs are 404; invalid catalog/escaped paths fail closed. There is no database write or arbitrary path parameter.

## Validation and local activation

```sh
PYTHONPATH=. .venv/bin/python -m pytest backend/app/tests/product/test_analyst_reports.py -q
node --experimental-strip-types --test ui/tests/analystReports.test.ts
npm --prefix ui run build
```

API tests use isolated temporary files and cover catalog/content/evidence, unknown IDs, traversal, symlink escape, missing/oversize files and read-only routes. UI tests cover ordering, filtering, stable selection, application labels, real report table/citation data and actual React server-rendered escaping. Build checks TypeScript and bundle integration. These checks do not constitute browser visual validation.

For the established local launchd stack, coordinate an idle queue and active API calculations before `scripts/restart_local_backend.sh reload-api`. This API-only reload leaves the durable worker running. Verify the served catalog and main report after reload; Vite serves the new tab code. No model/default or projection activation is needed for reading reports.
