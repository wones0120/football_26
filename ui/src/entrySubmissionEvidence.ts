type Row = Record<string, unknown>;
const object = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
const rows = (value: unknown): Row[] => Array.isArray(value) ? value.map(object) : [];
const value = (item: unknown): string => item == null || item === "" ? "unknown" : String(item);
const equality = (item: unknown): string => item === true ? "equal" : item === false ? "different" : "unknown";

export function entrySubmissionSections(entry: Row): { label: string; lines: string[] }[] {
  const evidence = object(entry.submission_evidence);
  const intended = object(evidence.intended);
  const assignment = object(intended.assignment);
  const observed = object(evidence.observed);
  const exports: Row[] = evidence.exported == null ? rows(entry.exports).map(row => ({
    ...row, artifact_id: row.export_id, kind: "portfolio_export", linkage: "portfolio_only",
  })) : rows(evidence.exported);
  const matches = rows(evidence.saved_lineup_matches);
  return [
    { label: "Intended", lines: intended.status === "explicit_assignment" ? [
      `Recorded assignment ${value(assignment.assignment_id)}: contest ${value(entry.contest_id)}, entry ${value(entry.entry_id)}, lineup ${value(assignment.lineup_id)}; recorded ${value(assignment.created_at)}.`,
      `Roster comparison: ${value(intended.roster_comparison)}. Original submission timing: unknown.`,
    ] : ["Explicit contest/entry assignment details unavailable in this report. Original submission intent and timing: unknown."] },
    { label: "Exported", lines: exports.length ? exports.map(row => {
      const linkage = row.linkage === "native_contest_entry_ids" ? "Native contest/entry IDs in the export artifact"
        : row.linkage === "canonical_roster" ? "Roster equality only; no entry-specific link"
        : row.linkage === "portfolio_only" ? "Portfolio only; row and entry linkage unavailable"
        : "Run only; no matching roster row or entry-specific link";
      const ids = Array.isArray(row.saved_lineup_ids) ? row.saved_lineup_ids.join(", ") : "unknown";
      return `${row.kind === "export" ? "Direct download" : "Portfolio export"} ${value(row.artifact_id)} · file ${value(row.file_name)} · recorded ${value(row.created_at)} · export row ${value(row.export_row_number)} · run ${value(row.optimizer_run_id)} · saved lineups ${ids || "unknown"}. ${linkage}. Roster: ${equality(row.roster_equal)}; exact slots: ${equality(row.exact_slot_equal)}.`;
    }) : ["No linked export evidence recorded. Export status: unknown."] },
    { label: "Observed", lines: [
      `Imported standings: contest ${value(entry.contest_id)}, entry ${value(entry.entry_id)} · source ${value(observed.source_file_id)} · imported ${value(observed.ingested_at)}.`,
      `Roster: ${value(observed.lineup_text)}. Canonical identity: ${observed.identity_complete === true ? "complete" : "unknown"}. Original submission timing: unknown.`,
    ] },
    { label: "Saved roster matches", lines: [
      evidence.matching_status === "ambiguous_runs" || evidence.matching_status === "ambiguous_lineups"
        ? "Ambiguous saved-lineup matches; no proven originating lineup or run."
        : "Retrospective roster comparison; equality does not prove originating lineup or run.",
      ...matches.map(row => `Lineup ${value(row.lineup_id)} · run ${value(row.optimizer_run_id)} · saved ${value(row.created_at)} · roster equal · exact slots ${equality(row.exact_slot_equal)}.`),
      ...(matches.length ? [] : ["Saved roster linkage unavailable in this report."]),
    ] },
  ];
}

export const submissionEvidenceLimitation = "Exports, roster equality, and imported standings do not prove original submission intent or timing. Saved-versus-entered score differences alone are not execution errors.";
