import { useCallback, useState } from "react";
import { createPortal } from "react-dom";

import { ResearchControlPlane } from "./research";
import researchStyles from "./research/styles.css?inline";
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
  const [portalTarget, setPortalTarget] = useState<HTMLDivElement | null>(null);

  const attachWorkspace = useCallback((host: HTMLDivElement | null) => {
    if (!host) return;
    const shadowRoot = host.shadowRoot ?? host.attachShadow({ mode: "open" });
    let style = shadowRoot.querySelector("style[data-research-styles]");
    if (!style) {
      style = document.createElement("style");
      style.setAttribute("data-research-styles", "true");
      style.textContent = researchStyles;
      shadowRoot.append(style);
    }
    let mount = shadowRoot.querySelector<HTMLDivElement>("[data-research-root]");
    if (!mount) {
      mount = document.createElement("div");
      mount.setAttribute("data-research-root", "true");
      shadowRoot.append(mount);
    }
    setPortalTarget(mount);
  }, []);

  return (
    <div className="research-shadow-host" ref={attachWorkspace}>
      {portalTarget && createPortal(
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
        />,
        portalTarget,
      )}
    </div>
  );
}
