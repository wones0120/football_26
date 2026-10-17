# DraftKings entry history in Learning

Open **Learning → Entry history and winnings**. Save DraftKings' **Download Entry
History** CSV in the contest-results folder. Choose **Scan history folder**,
review the matched files, then **Import selected history and move to Processed**.
The folder starts from the configured contest-results directory and can be edited.
Scan reads CSV headers and validates all rows, including files in subfolders;
it skips `Processed` folders and symbolic links. Unrelated salary and standings
CSVs are ignored. A selected file changed since scanning is rejected until rescanned.

The manual **Entry-history CSV path**, **Validate history**, and **Import entry
history** controls remain available. The manual path is remembered by the browser;
manual imports preserve the source file. Repeating or overlapping
exports does not double-count entries. Future imports require no Codex request.
Downloading from DraftKings and pressing Import remain user actions; this is not
an account scraper or background folder monitor.

The import reads all dates and sports in the export. The dashboard shows NFL
entries for the selected calendar year, independent of the selected week/slate.
Personal paid-entry results include actual cash winnings, fees, cash net return,
paid-finish frequency and separately reported ticket value. Free entries are
excluded from paid-entry metrics. The verified GPP subset excludes unclassified
contests; overall totals can include cash contests. Unmatched contest IDs remain
visible and still contribute to personal results. Matching standings are required
for lineup/field evaluation.

## Persistence and correctness

Migration `0048_draftkings_entry_history.sql` stores immutable original bytes,
content SHA256, normalized entry records, path and import timestamp. No raw file
is overwritten. Manual path imports keep their source; selected folder imports
move successfully committed files into `Processed`, retaining nested folders.
Archive names include the full content SHA256, so different downloads with the
same name are preserved. A sibling `.receipt.json` records original/archive paths,
content hash, row count, import status and archive timestamp; the database retains
the original bytes, original path and import timestamp.

Each file has an independent result. Invalid or failed imports stay in place.
If persistence succeeds but archiving fails, the result explicitly says **Import
saved; archive pending**. Retry the selected pending file or scan again: the
existing content-hash import deduplicates before retrying the move. Existing
archive content and receipts are never overwritten. Native contest and entry IDs
match records; no player name or display-name joins are introduced. Identical and overlapping rows
collapse. Conflicting versions of an entry are excluded and reported, rather
than silently replacing financial history. All rows validate before persistence;
invalid IDs, dates, ranks, paid-place counts or monetary values reject the file
with its row number. Preview does not write to the database.

- `POST /api/imports/draftkings/entry-history`: `{path, year, dry_run}`.
- `GET /api/imports/draftkings/entry-history?year=2026`: saved summary and entries.
- `POST /api/imports/draftkings/entry-history/folder`: `{directory, year,
  dry_run: true}` scans without database writes or file moves. Import uses
  `dry_run: false` and explicit `files: [{path, content_sha256}]` from the scan.

Rebuilding a Learning report automatically uses matched personal history for
actual winnings and entry fees, even without imported payout tiers. Saved reports
remain immutable. New financial evidence is included in the report hash.
Ticket value is separate from cash return, while a ticket prize counts as a paid
finish. Existing projection, optimizer and training policies are unchanged.

Where all exported rows agree on contest metadata and the field size matches,
Learning also uses the exported contest name, missing fee/prize information and
Places_Paid. Complete standings plus Places_Paid supply a paid score cutoff to
optimizer diagnostics. This does not create a payout ladder: exact earnings of
unplayed candidates and expected return remain unavailable without additional
evidence. No screenshots are required for this import or cutoff calculation.

## Validation

Targeted tests cover malformed inputs, overlap deduplication, conflict exclusion,
free/ticket/non-NFL handling, strict contest matching, paid cutoff evidence, API
errors and learning-report financial integration. Built-app browser checks cover
preview/import wiring, saved totals and desktop/mobile rendering.

Folder-import checks (2026-10-16): `test_entry_history.py` covers content-based
scanning, invalid and changed files, processed/link exclusions, native-ID overlap,
commit-before-move receipts, archive failures/retries and collision preservation.
Its HTTP API fixture exercises scan → import → Processed → idempotent retry with
a mocked database transaction and real temporary files. `ui/tests/entryHistory.e2e.mjs`
uses the built app and installed Google Chrome with intercepted fixture APIs;
it checks selected import payloads, row errors, focused text/caret colors and
layout at 1440px and 390px. Screenshots are written to a fresh temporary folder.
Run after `npm --prefix ui run build`; set `PLAYWRIGHT_MODULE` to the installed
Playwright module path when it is not on Node's module lookup path.

Activation on 2026-10-10: migration applied; API activated without restarting the
optimizer worker. The supplied 2,716-row export imported once and returned
`deduplicated` on repeat through the live API. All four imported 2026 Week 4
Sunday Main contests matched history and gained exported paid-place evidence.
Sixty-one targeted backend/schema tests, the UI production build, and desktop /
mobile browser checks passed. The build retains its existing bundle-size warning.
