import { entrySubmissionSections, submissionEvidenceLimitation } from "./entrySubmissionEvidence";

export function LearningEntryEvidence({ entry }: { entry: Record<string, unknown> }) {
  return <details style={{ overflowWrap: "anywhere" }}>
    <summary>Intended / Exported / Observed evidence</summary>
    {entrySubmissionSections(entry).map(section => <div key={section.label}>
      <strong>{section.label}</strong>
      <ul>{section.lines.map((line, index) => <li key={index}>{line}</li>)}</ul>
    </div>)}
    <p>{submissionEvidenceLimitation}</p>
  </details>;
}
