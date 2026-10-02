# Sunday preparation evidence

These archives preserve the October 2 Sunday readiness, frozen contest decision,
source refresh, and actual UI acceptance evidence. Large raw/readback files are
compressed for GitHub; original file bytes are unchanged. `manifest.json` records
each archive and file SHA-256. Source capture manifests retain their provenance.

From the repository root after cloning:

```sh
python3 scripts/restore_sunday_preparation_evidence.py
```

The restore verifies archive checksums, writes missing files, verifies identical
existing files, and refuses to overwrite different evidence. It restores the
paths referenced by the Sunday reports. It does not restore the application
database or run ingestion, modeling, optimization, or contest entry actions.

Replay the preserved comparison after restoration:

```sh
PYTHONPATH=. PYTHONHASHSEED=0 .venv/bin/python artifacts/week4_sunday_decision/20261002T143300Z/verify_frozen_runtime.py
```

The original freeze includes absolute paths from its capture host. That command
runs unchanged at `/Users/wones/git/football_26`; another checkout location needs
a separate path-mapping replay adapter rather than edits to the frozen files.

UI validation, test logs, native CSV review copies, readable reports, and the
two historical runtime-hash guard failures are preserved in the source-update
archive. These are unassigned planning outputs, not submitted contest entries.
