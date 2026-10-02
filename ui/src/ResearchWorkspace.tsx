import { ResearchControlPlane } from "./research";
import "./research/styles.css";
import { researchSlateId } from "./workspaceContext";

type ResearchWorkspaceProps = {
  season: number;
  week: number;
  slate: string;
  slateOptions: string[];
  selectedSimulationRunId: string;
  selectedBaselineRunId: string;
  onSeasonChange: (value: number) => void;
  onWeekChange: (value: number) => void;
  onSlateChange: (value: string) => void;
  onSelectedSimulationRunIdChange: (runId: string) => void;
  onSelectedBaselineRunIdChange: (runId: string) => void;
};

export function ResearchWorkspace({
  season,
  week,
  slate,
  slateOptions,
  selectedSimulationRunId,
  selectedBaselineRunId,
  onSeasonChange,
  onWeekChange,
  onSlateChange,
  onSelectedSimulationRunIdChange,
  onSelectedBaselineRunIdChange,
}: ResearchWorkspaceProps) {
  return (
    <div className="research-workspace">
      <ResearchControlPlane
        season={season}
        week={week}
        slate={researchSlateId(slate)}
        slateOptions={slateOptions.map(researchSlateId)}
        selectedLineupSimulationRunId={selectedSimulationRunId}
        selectedBaselineSimulationRunId={selectedBaselineRunId}
        onSeasonChange={onSeasonChange}
        onWeekChange={onWeekChange}
        onSlateChange={onSlateChange}
        onSelectedLineupSimulationRunIdChange={onSelectedSimulationRunIdChange}
        onSelectedBaselineSimulationRunIdChange={onSelectedBaselineRunIdChange}
      />
    </div>
  );
}
