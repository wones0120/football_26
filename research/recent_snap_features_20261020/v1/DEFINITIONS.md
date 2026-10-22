# Recent observed snap trends v1

**G17-M06 and G22-M04** use one explicitly versioned measured trend definition: latest observed same-team REG game snaps/share minus the mean of exactly three preceding observed team logs. Offense, defense and special teams remain separate channels, with count changes and source-share changes reported separately. These are historical participation measurements, not expected workloads, active designations or role forecasts.

Team-game windows come from the full retained source before user preferences. An actor missing from a selected game has unknown participation; absence never becomes DNP or zero and no last-positive-game fallback applies. Genuine source zeros remain zero. No same-player history crosses team or season. An incomplete three-game reference masks its mean and delta. Player snap counts overlap across teammates and are never summed as physical team plays.

## Source and identity boundary

The initial source is a **new immutable freeze of the current retained DB revision**, not the original provider HTTP snapshot. A repeatable-read transaction extracts only 15 native scope/role/stat fields, preserving original field presence and nulls, original row and ingest IDs, import clocks, native PFR aliases and current typed identity-block evidence. The legacy DB can replace or retain multiple imported revisions, so DB row IDs alone are not described as immutable source proof. The actual freeze is captured by SourceCaptureService, with source origin and actual extraction/capture clocks retained.

The reader verifies immutable bytes/manifests and the exact source contract, completed original ingest clocks, selected source scope and row cardinality. Alias and row availability are bounded by the original extraction time even on a later read; elapsed time cannot make a future alias inside an old freeze available. Only native PFR aliases attach UUIDs. Current typed identity conflicts and native/canonical collisions withhold implicated canonical attachments across the batch without changing source facts or existing aliases.

Repeated native player/game records collapse only when the complete selected native payload is byte-equivalent, their ingest runs differ and row identities differ. All original row/ingest/clock receipts remain in provenance. Same-ingest duplicates or conflicting payloads reject the batch; there is no newest-record assumption or averaging of conflicting values. Unidentified native rows cannot be merged by display name or similar counts.

## Actual coverage and review workflow

The 4,369,960-byte indexed freeze contains 8,955 retained rows. There are 1,574 equivalent prior-REG revision groups after retaining unknown-native rows separately. Derived output has 1,809 native actor/team profiles and 1,492 canonical profiles. Each channel has 1,188 known count/share changes, including 965 canonical known changes; other actor windows remain unknown. There are 362 durable identity review records: 46 missing/malformed native rows, 314 unresolved native IDs, and two existing typed canonical conflict records. Readback confirms all 362 are open; this does not claim aliases were resolved.

Person review keys are stable native PFR keys; malformed source rows use immutable source-hash plus row-ID keys. Existing conflict records are referenced without reopening earlier decisions. New contradictory evidence uses distinct evidence keys. No alias or canonical player is guessed or overwritten. The frozen projection excludes display names; native IDs or immutable source-row references remain explicit rather than fabricating names.

Run `derive_actual.py` only to capture a new retained revision. `capture_checkpoint.json` identifies the frozen source even when subsequent feature validation fails. Run `derive_frozen.py` to revalidate that exact source, persist/read back identity requests, and create the final content-addressed feature artifact. It never re-reads mutable source rows. All previous raw and derived artifacts remain unchanged.

Original historical availability is unknown. Current output is postlock descriptive, explicitly not pregame serving. Models, projections, scenarios, optimizer and app activation remain pending separately.
