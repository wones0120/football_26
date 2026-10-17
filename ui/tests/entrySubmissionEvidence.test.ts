import assert from "node:assert/strict";
import test from "node:test";
import { entrySubmissionSections, submissionEvidenceLimitation } from "../src/entrySubmissionEvidence.ts";

test("direct roster exports expose artifacts and limitations without an assignment", () => {
  const sections = entrySubmissionSections({ contest_id: "c1", entry_id: "e1", submission_evidence: {
    intended: { status: "unavailable" },
    exported: [{ kind: "export", artifact_id: "artifact-1", created_at: "2026-10-11T12:00:00Z",
      file_name: "direct.csv", export_row_number: 2, optimizer_run_id: "run-1",
      saved_lineup_ids: ["lineup-1"], linkage: "canonical_roster", roster_equal: true, exact_slot_equal: null }],
    observed: { source_file_id: "standings-1", ingested_at: "2026-10-13T12:00:00Z",
      lineup_text: "CPT Alpha FLEX Beta", identity_complete: true },
    matching_status: "ambiguous_runs", saved_lineup_matches: [
      { lineup_id: "lineup-1", optimizer_run_id: "run-1", exact_slot_equal: false },
      { lineup_id: "lineup-2", optimizer_run_id: "run-2", exact_slot_equal: true },
    ],
  } });
  assert.deepEqual(sections.map(s => s.label), ["Intended", "Exported", "Observed", "Saved roster matches"]);
  assert.match(sections[0].lines.join(" "), /intent and timing: unknown/);
  assert.match(sections[1].lines[0], /Direct download artifact-1.*2026-10-11T12:00:00Z.*export row 2/);
  assert.match(sections[1].lines[0], /Roster equality only; no entry-specific link/);
  assert.match(sections[1].lines[0], /exact slots: unknown/);
  assert.match(sections[2].lines.join(" "), /standings-1.*2026-10-13T12:00:00Z/);
  assert.match(sections[3].lines[0], /Ambiguous.*no proven originating/);
  assert.match(sections[3].lines[1], /run-1.*exact slots different/);
  assert.match(sections[3].lines[2], /run-2/);
  assert.match(submissionEvidenceLimitation, /score differences alone are not execution errors/);
});

test("legacy portfolio evidence remains visible with unknown row and timing", () => {
  const sections = entrySubmissionSections({ contest_id: "c1", entry_id: "e1",
    exports: [{ export_id: "portfolio-1", file_name: "portfolio.csv" }] });
  assert.match(sections[1].lines[0], /Portfolio export portfolio-1/);
  assert.match(sections[1].lines[0], /recorded unknown.*export row unknown/);
  assert.match(sections[1].lines[0], /Portfolio only; row and entry linkage unavailable/);
  assert.match(sections[3].lines.join(" "), /Saved roster linkage unavailable/);
});

test("run-only and missing evidence remain explicit; repeated entry IDs retain contest IDs", () => {
  for (const contest_id of ["c1", "c2"]) {
    const sections = entrySubmissionSections({ contest_id, entry_id: "e1", submission_evidence: {
      exported: [{ kind: "export", artifact_id: "a1", linkage: "optimizer_run_only" }],
    } });
    assert.match(sections[1].lines[0], /Run only; no matching roster row or entry-specific link/);
    assert.match(sections[2].lines[0], new RegExp(`contest ${contest_id}, entry e1`));
  }
  assert.match(entrySubmissionSections({})[1].lines[0], /Export status: unknown/);
});
