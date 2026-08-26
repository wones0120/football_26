import { useEffect, useMemo, useState } from "react";
import {
  fetchNewsMonitorReport,
  fetchLatestOwnership,
  fetchLatestPredictions,
  fetchLatestSlateSimulation,
  fetchSlateWeather,
  runNewsMonitor,
  type NewsMonitorHeadline,
  type NewsMonitorRunResponse,
  type NewsMonitorSignal,
  type OptimizerResponse,
  type OwnershipProjectionRow,
  type PredictionRow,
  type SimulationPlayerRow,
  type SlateWeatherResponse,
} from "./api";
import {
  buildGameMatrixRows,
  formatDateTime,
  formatForecastSource,
  formatForecastTimestamp,
  formatFreshness,
  formatPrecipitationMm,
  formatRoof,
  formatTemperatureC,
  formatWeatherWarning,
  formatWindMps,
  shouldShowHistoricalActual,
  weatherStateLabel,
  weatherWarnings,
} from "./weatherPresentation";
import "./WarRoom.css";

type WarRoomProps = {
  season: number;
  week: number;
  slate: string;
  slateOptions: string[];
  pendingAction: string | null;
  optimizerStatus: OptimizerResponse | null;
  projectionRunId?: string;
  onProjectionRunChange: (runId: string | null) => void;
  onSeasonChange: (season: number) => void;
  onWeekChange: (week: number) => void;
  onSlateChange: (slate: string) => void;
  onOpenOperations: () => void;
  onOpenModelWorkbench: () => void;
  onOpenBrief: () => void;
  onOpenPreview: () => void;
};

function formatSlateName(value: string) {
  return value.replaceAll("_", " ");
}

function formatLocalDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function titleCase(value: string | null | undefined) {
  if (!value) return "Unknown";
  return value
    .replaceAll("_", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function extractSourceLabel(signal: NewsMonitorSignal, headlines: NewsMonitorHeadline[]) {
  if (signal.source_link) {
    try {
      const hostname = new URL(signal.source_link).hostname.replace(/^www\./, "");
      return hostname;
    } catch {
      // Fall through to headline/source metadata.
    }
  }
  const matchingHeadline = headlines.find((headline) => headline.link === signal.source_link);
  if (matchingHeadline?.source_id) {
    return titleCase(matchingHeadline.source_id);
  }
  return titleCase(signal.signal_type);
}

function extractTimestamp(signal: NewsMonitorSignal, report: NewsMonitorRunResponse | null) {
  const matchingHeadline = report?.report.team_headlines.find(
    (headline) => headline.link === signal.source_link
  );
  const publishedAt = matchingHeadline?.published_at;
  if (publishedAt) {
    const published = new Date(publishedAt);
    if (!Number.isNaN(published.getTime())) {
      return published.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
  }
  return report?.report.date ?? formatLocalDate(new Date());
}

function formatSignalTitle(signal: NewsMonitorSignal) {
  const details = [signal.player_name, signal.team].filter(Boolean).join(" · ");
  if (!details) {
    return signal.signal_text;
  }
  return `${details}: ${signal.signal_text}`;
}

function loadNewsMonitorReport(runDate: string): Promise<NewsMonitorRunResponse | null> {
  return fetchNewsMonitorReport(runDate);
}

function formatSalary(value: number | null | undefined) {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return `$${Number(value).toLocaleString()}`;
}

type DecisionRow = {
  key: string;
  player: string;
  team: string;
  pos: string;
  salary: string;
  proj: string;
  ceiling: string;
  own: string;
  optimal: string;
  leverage: string;
  leverageValue: number | null;
  stance: "Core" | "Over" | "Under" | "Debate";
  reason: string;
};

type DecisionBoardMode = "leverage" | "ceiling" | "risk";

const DECISION_BOARD_MODES: Array<{
  id: DecisionBoardMode;
  label: string;
  summary: string;
}> = [
  { id: "leverage", label: "Leverage", summary: "Ownership-adjusted opportunities" },
  { id: "ceiling", label: "Ceiling", summary: "Highest modeled ceilings" },
  { id: "risk", label: "Risk", summary: "Widest modeled downside gaps" },
];

type DebateStance = "Core" | "Over" | "Under" | "Fade" | "Need more info";

type OptimizerLineupPlayer = {
  player_id?: string;
  player_display_name?: string;
  player_name?: string;
  name?: string;
  player_team?: string;
  team?: string;
  recent_team?: string;
  roster_position?: string;
  position?: string;
  projection?: number;
  predicted_mean?: number;
  ownership?: number;
  salary?: number;
};

type LineupCardRow = {
  name: string;
  ceiling: string;
  own: string;
  salary: string;
  build: string;
};

type ExposureRow = {
  label: string;
  value: number;
  tone: "green" | "blue" | "amber" | "red";
};

const NEWS_PROCESSING_ENABLED = false;

function projectionValue(row: PredictionRow) {
  return row.adj_mean_final || row.adj_mean || row.predicted_mean || 0;
}

function findOwnershipMatch(
  prediction: PredictionRow,
  ownershipByPlayerId: Map<string, OwnershipProjectionRow>
) {
  return ownershipByPlayerId.get(String(prediction.player_id));
}

function buildDecisionRows(
  predictions: PredictionRow[],
  ownershipRows: OwnershipProjectionRow[],
  simulationRows: SimulationPlayerRow[],
  mode: DecisionBoardMode
): DecisionRow[] {
  const ownershipByPlayerId = new Map(
    ownershipRows.map((row) => [String(row.player_id), row] as const)
  );
  const simulationByPlayerId = new Map(
    simulationRows.map((row) => [String(row.player_id), row] as const)
  );
  const ranked = predictions
    .map((prediction) => {
      const ownership = findOwnershipMatch(prediction, ownershipByPlayerId);
      const simulation = simulationByPlayerId.get(String(prediction.player_id));
      const ownValue = simulation?.field_ownership ?? ownership?.projected_ownership ?? null;
      const optimalValue = simulation?.optimal_lineup_probability ?? null;
      const projValue = projectionValue(prediction);
      const ceilingValue = prediction.predicted_p90;
      const floorValue = prediction.predicted_p10;
      return {
        prediction,
        ownValue,
        projValue,
        ceilingValue,
        floorValue,
        optimalValue,
        leverageValue: simulation?.leverage_score ?? null,
        downsideGap: Math.max(0, projValue - floorValue),
        outcomeRange: Math.max(0, ceilingValue - floorValue),
      };
    })
    .sort((left, right) => {
      if (mode === "ceiling") {
        return right.ceilingValue - left.ceilingValue || right.projValue - left.projValue;
      }
      if (mode === "risk") {
        return right.downsideGap - left.downsideGap || right.outcomeRange - left.outcomeRange;
      }
      return (
        (right.leverageValue ?? Number.NEGATIVE_INFINITY) -
          (left.leverageValue ?? Number.NEGATIVE_INFINITY) ||
        right.projValue - left.projValue
      );
    })
    .slice(0, 18);

  return ranked.map((candidate) => {
    const {
      prediction,
      ownValue,
      projValue,
      ceilingValue,
      floorValue,
      optimalValue,
      leverageValue,
      downsideGap,
      outcomeRange,
    } = candidate;
    const leverageKnown = leverageValue !== null;

    let stance: DecisionRow["stance"] = "Debate";
    if (leverageKnown && leverageValue < -2) {
      stance = "Under";
    } else if (leverageKnown && leverageValue >= 4) {
      stance = "Over";
    } else if (leverageKnown && leverageValue >= 0) {
      stance = "Core";
    }

    let reason = `Projection ${projValue.toFixed(1)}.`;
    if (mode === "ceiling") {
      reason = `P90 ceiling ${ceilingValue.toFixed(1)}, ${Math.max(0, ceilingValue - projValue).toFixed(1)} above projection.`;
    } else if (mode === "risk") {
      reason = `P10 floor ${floorValue.toFixed(1)}, ${downsideGap.toFixed(1)} below projection; ${outcomeRange.toFixed(1)}-point outcome range.`;
    }
    if (ownValue === null) {
      reason += " Ownership not loaded for this slate yet.";
    } else if (!leverageKnown) {
      reason += " Run the DT-502 slate simulation to measure optimal-lineup leverage.";
    } else if (stance === "Over") {
      reason += ` Optimal-lineup probability ${optimalValue?.toFixed(1)}% exceeds ${ownValue.toFixed(1)}% field ownership.`;
    } else if (stance === "Core") {
      reason += ` Balanced ownership at ${ownValue.toFixed(1)}% keeps the play live.`;
    } else if (stance === "Under") {
      reason += ` Field exposure at ${ownValue.toFixed(1)}% is too rich for the current edge.`;
    } else {
      reason += ` Ownership at ${ownValue.toFixed(1)}% keeps the stance unresolved.`;
    }

    return {
      key: String(prediction.player_id),
      player: prediction.player_display_name,
      team: prediction.recent_team || "--",
      pos: prediction.position || "--",
      salary: formatSalary(prediction.salary),
      proj: projValue.toFixed(1),
      ceiling: ceilingValue.toFixed(1),
      own: ownValue === null ? "--" : `${ownValue.toFixed(1)}%`,
      optimal: optimalValue === null ? "--" : `${optimalValue.toFixed(1)}%`,
      leverage: leverageValue === null ? "--" : `${leverageValue >= 0 ? "+" : ""}${leverageValue.toFixed(1)}`,
      leverageValue,
      stance,
      reason,
    };
  });
}

function optimizerPlayerTeam(player: OptimizerLineupPlayer) {
  return player.player_team || player.team || player.recent_team || "";
}

function optimizerPlayerProjection(player: OptimizerLineupPlayer) {
  return Number(player.projection ?? player.predicted_mean ?? 0) || 0;
}

function optimizerPlayerOwnership(player: OptimizerLineupPlayer) {
  const value = Number(player.ownership ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function optimizerPlayerSalary(player: OptimizerLineupPlayer) {
  return Number(player.salary ?? 0) || 0;
}

function buildLineupSummary(lineup: OptimizerLineupPlayer[]) {
  const teamCounts = new Map<string, number>();
  lineup.forEach((player) => {
    const team = optimizerPlayerTeam(player);
    if (!team) {
      return;
    }
    teamCounts.set(team, (teamCounts.get(team) ?? 0) + 1);
  });
  return Array.from(teamCounts.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3)
    .map(([team, count]) => `${team} x${count}`)
    .join(", ");
}

function extractOptimizerLineups(optimizerStatus: OptimizerResponse | null): OptimizerLineupPlayer[][] {
  if (!optimizerStatus || !Array.isArray(optimizerStatus.results)) {
    return [];
  }
  return optimizerStatus.results.filter((lineup): lineup is OptimizerLineupPlayer[] => Array.isArray(lineup));
}

function buildLineupCard(lineup: OptimizerLineupPlayer[], index: number): LineupCardRow {
  const totalProjection = lineup.reduce((sum, player) => sum + optimizerPlayerProjection(player), 0);
  const totalOwnership = lineup.reduce((sum, player) => sum + optimizerPlayerOwnership(player), 0);
  const totalSalary = lineup.reduce((sum, player) => sum + optimizerPlayerSalary(player), 0);
  return {
    name: `Lineup ${index + 1}`,
    ceiling: totalProjection.toFixed(1),
    own: `${totalOwnership.toFixed(1)}%`,
    salary: `$${(totalSalary / 1000).toFixed(1)}K`,
    build: buildLineupSummary(lineup) || "No stack summary",
  };
}

function buildExposureRows(lineups: OptimizerLineupPlayer[][]): ExposureRow[] {
  const teamCounts = new Map<string, number>();
  const totalSlots = lineups.reduce((sum, lineup) => sum + lineup.length, 0);
  if (totalSlots === 0) {
    return [];
  }

  lineups.flat().forEach((player) => {
    const team = optimizerPlayerTeam(player);
    if (!team) {
      return;
    }
    teamCounts.set(team, (teamCounts.get(team) ?? 0) + 1);
  });

  return Array.from(teamCounts.entries())
    .map(([label, count]) => {
      const value = Math.round((count / totalSlots) * 100);
      const tone: ExposureRow["tone"] =
        value >= 20 ? "green" : value >= 14 ? "blue" : value >= 9 ? "amber" : "red";
      return { label, value, tone };
    })
    .sort((left, right) => right.value - left.value)
    .slice(0, 6);
}

function buildSignalTape(report: NewsMonitorRunResponse | null) {
  if (!report) {
    return [];
  }

  const rankedSignals = [
    ...report.report.high_priority_signals,
    ...report.report.injury_updates,
    ...report.report.roster_moves,
    ...report.report.depth_chart_notes,
    ...report.report.manual_review,
  ].filter((signal) => {
    const relevance = signal.dfs_relevance?.toLowerCase();
    return relevance === "high" || relevance === "medium";
  });

  const seen = new Set<string>();
  return rankedSignals
    .filter((signal) => {
      const key = [signal.signal_type, signal.signal_text, signal.source_link ?? ""].join("|");
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    })
    .map((signal) => ({
      key: [signal.signal_type, signal.signal_text, signal.source_link ?? ""].join("|"),
      time: extractTimestamp(signal, report),
      source: extractSourceLabel(signal, report.report.team_headlines),
      tag: titleCase(signal.signal_type),
      title: formatSignalTitle(signal),
      impact: titleCase(signal.dfs_relevance),
      confidence: titleCase(signal.confidence),
      sourceLink: signal.source_link ?? null,
    }));
}

export function WarRoom({
  season,
  week,
  slate,
  slateOptions,
  pendingAction,
  optimizerStatus,
  projectionRunId,
  onProjectionRunChange,
  onSeasonChange,
  onWeekChange,
  onSlateChange,
  onOpenOperations,
  onOpenModelWorkbench,
  onOpenBrief,
  onOpenPreview,
}: WarRoomProps) {
  const [newsReport, setNewsReport] = useState<NewsMonitorRunResponse | null>(null);
  const [signalError, setSignalError] = useState<string | null>(null);
  const [signalLoading, setSignalLoading] = useState(true);
  const [newsRunLoading, setNewsRunLoading] = useState(false);
  const [newsRunMessage, setNewsRunMessage] = useState<string | null>(null);
  const [projectionRows, setProjectionRows] = useState<PredictionRow[]>([]);
  const [ownershipRows, setOwnershipRows] = useState<OwnershipProjectionRow[]>([]);
  const [simulationRows, setSimulationRows] = useState<SimulationPlayerRow[]>([]);
  const [decisionBoardMode, setDecisionBoardMode] = useState<DecisionBoardMode>("leverage");
  const [decisionLoading, setDecisionLoading] = useState(true);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [weatherReport, setWeatherReport] = useState<SlateWeatherResponse | null>(null);
  const [weatherLoading, setWeatherLoading] = useState(true);
  const [weatherError, setWeatherError] = useState<string | null>(null);
  const [selectedGameKey, setSelectedGameKey] = useState("");
  const [selectedDebatePlayer, setSelectedDebatePlayer] = useState<string>("");
  const [debateStance, setDebateStance] = useState<DebateStance>("Need more info");
  const [debateNote, setDebateNote] = useState("");
  const runDate = formatLocalDate(new Date());

  useEffect(() => {
    let cancelled = false;

    async function loadSignalTape() {
      if (!NEWS_PROCESSING_ENABLED) {
        setNewsReport(null);
        setSignalError(null);
        setSignalLoading(false);
        return;
      }
      setSignalLoading(true);
      setSignalError(null);
      try {
        const report = await loadNewsMonitorReport(runDate);
        if (!cancelled) {
          setNewsReport(report);
        }
      } catch (error) {
        if (!cancelled) {
          setSignalError(error instanceof Error ? error.message : String(error));
          setNewsReport(null);
        }
      } finally {
        if (!cancelled) {
          setSignalLoading(false);
        }
      }
    }

    loadSignalTape().catch(() => {
      // The awaited call already sets a compact UI error state.
    });

    return () => {
      cancelled = true;
    };
  }, [runDate]);

  const handleRunNewsMonitor = async () => {
    if (!NEWS_PROCESSING_ENABLED) {
      setNewsRunMessage("News processing is paused while the model workbench is the focus.");
      setSignalLoading(false);
      return;
    }
    setNewsRunLoading(true);
    setNewsRunMessage(null);
    setSignalError(null);
    try {
      const result = await runNewsMonitor({
        run_date: runDate,
        force: true,
      });
      setNewsReport(result);
      setNewsRunMessage(result.message);
    } catch (error) {
      setNewsRunMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setNewsRunLoading(false);
      setSignalLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    setWeatherLoading(true);
    setWeatherError(null);
    setWeatherReport(null);
    fetchSlateWeather({ season, week, slate })
      .then((response) => {
        if (!cancelled) setWeatherReport(response);
      })
      .catch((error) => {
        if (!cancelled) {
          setWeatherError(error instanceof Error ? error.message : String(error));
        }
      })
      .finally(() => {
        if (!cancelled) setWeatherLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [season, week, slate]);

  const liveSignals = useMemo(() => buildSignalTape(newsReport), [newsReport]);
  const matrixSignals = useMemo(
    () => newsReport?.report.high_priority_signals ?? [],
    [newsReport]
  );
  const gameMatrixRows = useMemo(
    () => buildGameMatrixRows(
      projectionRows,
      matrixSignals,
      weatherReport?.games ?? [],
      weatherLoading ? "loading" : weatherError ? "error" : "missing"
    ),
    [matrixSignals, projectionRows, weatherError, weatherLoading, weatherReport]
  );
  const decisionRows = useMemo(
    () => buildDecisionRows(projectionRows, ownershipRows, simulationRows, decisionBoardMode),
    [projectionRows, ownershipRows, simulationRows, decisionBoardMode]
  );
  const decisionBoardSummary =
    DECISION_BOARD_MODES.find((mode) => mode.id === decisionBoardMode)?.summary ?? "Decision signals";

  useEffect(() => {
    let cancelled = false;

    async function loadDecisionBoard() {
      setDecisionLoading(true);
      setDecisionError(null);
      try {
        const [predictionResponse, ownershipResponse] = await Promise.all([
          fetchLatestPredictions({ season, week, slate, limit: 1000, projectionRunId }),
          fetchLatestOwnership({ season, week, slate, limit: 1000 }),
        ]);
        const simulationResponse = await fetchLatestSlateSimulation({
          season,
          week,
          slate,
          projectionRunId: predictionResponse.projection_run_id ?? undefined,
        });
        if (!cancelled) {
          setProjectionRows(predictionResponse.rows);
          onProjectionRunChange(predictionResponse.projection_run_id ?? null);
          setOwnershipRows(ownershipResponse.rows);
          setSimulationRows(simulationResponse?.rows ?? []);
        }
      } catch (error) {
        if (!cancelled) {
          setDecisionError(error instanceof Error ? error.message : String(error));
          setProjectionRows([]);
          setOwnershipRows([]);
          setSimulationRows([]);
        }
      } finally {
        if (!cancelled) {
          setDecisionLoading(false);
        }
      }
    }

    loadDecisionBoard().catch(() => {
      // The awaited call already writes to the compact error state.
    });

    return () => {
      cancelled = true;
    };
  }, [onProjectionRunChange, projectionRunId, season, week, slate]);

  useEffect(() => {
    if (gameMatrixRows.length === 0) {
      if (selectedGameKey) setSelectedGameKey("");
      return;
    }
    if (!gameMatrixRows.some((row) => row.key === selectedGameKey)) {
      setSelectedGameKey(gameMatrixRows[0].key);
    }
  }, [gameMatrixRows, selectedGameKey]);

  useEffect(() => {
    if (decisionRows.length === 0) {
      if (selectedDebatePlayer) {
        setSelectedDebatePlayer("");
      }
      return;
    }
    if (!decisionRows.some((row) => row.player === selectedDebatePlayer)) {
      setSelectedDebatePlayer(decisionRows[0].player);
    }
  }, [decisionRows, selectedDebatePlayer]);

  const selectedDecision =
    decisionRows.find((row) => row.player === selectedDebatePlayer) ?? decisionRows[0] ?? null;
  const selectedGame =
    gameMatrixRows.find((row) => row.key === selectedGameKey) ?? gameMatrixRows[0] ?? null;
  const selectedWeather = selectedGame?.weather ?? null;
  const selectedWeatherWarnings = selectedWeather ? weatherWarnings(selectedWeather) : [];
  const optimizerLineups = extractOptimizerLineups(optimizerStatus);
  const lineupCards = optimizerLineups.map((lineup, index) => buildLineupCard(lineup, index));
  const exposureRows = buildExposureRows(optimizerLineups);
  const portfolioStatus =
    optimizerLineups.length > 0
      ? `${optimizerLineups.length} lineup${optimizerLineups.length === 1 ? "" : "s"} loaded`
      : optimizerStatus?.status === "running"
        ? "Optimizer running"
        : "No portfolio loaded";
  const buildPosture =
    selectedDecision
      ? `${debateStance} · ${selectedDecision.player}`
      : "Awaiting board data";

  return (
    <main className="war-room">
      <header className="war-command">
        <div className="war-brand">
          <span className="war-mark">FO</span>
          <div>
            <p>Football Opt</p>
            <h1>Slate War Room</h1>
          </div>
        </div>

        <div className="war-controls" aria-label="Slate controls">
          <label>
            Season
            <input
              type="number"
              value={season}
              onChange={(event) => onSeasonChange(Number(event.target.value))}
            />
          </label>
          <label>
            Week
            <input
              type="number"
              min={1}
              max={25}
              value={week}
              onChange={(event) => onWeekChange(Number(event.target.value))}
            />
          </label>
          <label>
            Slate
            <select value={slate} onChange={(event) => onSlateChange(event.target.value)}>
              {slateOptions.map((option) => (
                <option key={option} value={option}>
                  {formatSlateName(option)}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="war-actions">
          {pendingAction && <span className="war-pending">{pendingAction}</span>}
          <button type="button" onClick={handleRunNewsMonitor} disabled={newsRunLoading}>
            {newsRunLoading ? "Running News" : "News Paused"}
          </button>
          <button type="button" onClick={onOpenOperations}>
            Operations
          </button>
          <button type="button" className="war-secondary" onClick={onOpenModelWorkbench}>
            Models
          </button>
          <button type="button" className="war-secondary" onClick={onOpenBrief}>
            Brief
          </button>
          <button type="button" className="war-secondary" onClick={onOpenPreview}>
            Concept
          </button>
        </div>
      </header>

      <section className="war-status-grid" aria-label="Slate status">
        <article>
          <span>Replay Context</span>
          <strong>{season} · Week {week}</strong>
          <small>{formatSlateName(slate)}</small>
        </article>
        <article>
          <span>Portfolio Status</span>
          <strong>{portfolioStatus}</strong>
          <small>{optimizerStatus?.message ?? "Run optimizer in Operations to populate candidate builds."}</small>
        </article>
        <article>
          <span>News Heat</span>
          <strong>{signalError ? "Offline" : liveSignals.length > 0 ? "Active" : "Quiet"}</strong>
          <small>
            {signalLoading
              ? "Loading report"
              : `${liveSignals.length} slate-moving signal${liveSignals.length === 1 ? "" : "s"}`}
          </small>
        </article>
        <article>
          <span>Build Posture</span>
          <strong>{buildPosture}</strong>
          <small>
            {selectedDecision
              ? selectedDecision.reason
              : "Pick a player in the Debate Rail once the board has live rows."}
          </small>
        </article>
      </section>

      <section className="war-layout">
        <aside className="war-panel signal-tape">
          <div className="war-panel-title">
            <span>Live Signal Tape</span>
            <strong>{newsReport ? `Report ${newsReport.report.date}` : "Filtered for DFS impact"}</strong>
          </div>
          {newsRunMessage && (
            <div className={`signal-banner ${signalError ? "signal-banner-error" : ""}`} aria-live="polite">
              {newsRunMessage}
            </div>
          )}
          <div className="signal-list">
            {signalLoading && (
              <article className="signal-row signal-row-state" aria-live="polite">
                <div className="signal-headline">
                  <span>Loading</span>
                  <strong>Fetching the latest news-monitor report.</strong>
                </div>
              </article>
            )}

            {!signalLoading && signalError && (
              <article className="signal-row signal-row-state signal-row-error" aria-live="polite">
                <div className="signal-headline">
                  <span>Signal Tape Unavailable</span>
                  <strong>{signalError}</strong>
                </div>
              </article>
            )}

            {!signalLoading && !signalError && liveSignals.length === 0 && (
              <article className="signal-row signal-row-state">
                <div className="signal-headline">
                  <span>No Reported Pressure</span>
                  <strong>No slate-moving signals found yet.</strong>
                </div>
              </article>
            )}

            {!signalLoading && !signalError && liveSignals.map((signal) => (
              <article className="signal-row" key={signal.key}>
                <div className="signal-meta">
                  <span>{signal.time}</span>
                  <span>{signal.source}</span>
                </div>
                <div className="signal-headline">
                  <span>{signal.tag}</span>
                  <strong>{signal.title}</strong>
                </div>
                <div className="signal-score">
                  <strong>{signal.impact}</strong>
                  <span>
                    {signal.confidence}
                    {signal.sourceLink ? (
                      <>
                        {" "}
                        <a href={signal.sourceLink} target="_blank" rel="noreferrer">
                          Source
                        </a>
                      </>
                    ) : null}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </aside>

        <section className="war-center">
          <div className="war-panel decision-board">
            <div className="war-panel-title board-title">
              <div className="board-title-copy">
                <span>Decision Board</span>
                <strong>{decisionBoardSummary}</strong>
              </div>
              <div className="board-tabs" role="group" aria-label="Rank Decision Board by">
                {DECISION_BOARD_MODES.map((mode) => (
                  <button
                    type="button"
                    key={mode.id}
                    className={decisionBoardMode === mode.id ? "active" : ""}
                    aria-pressed={decisionBoardMode === mode.id}
                    onClick={() => setDecisionBoardMode(mode.id)}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="decision-table" aria-label={`Decision Board: ${decisionBoardSummary}`}>
              <div className="decision-table-head">
                <span>Player</span>
                <span>Salary</span>
                <span>Proj</span>
                <span>Ceil</span>
                <span>Own</span>
                <span>Opt</span>
                <span>Lev</span>
                <span>Stance</span>
              </div>

              {decisionLoading && (
                <article className="decision-row decision-row-state" aria-live="polite">
                  <p>Loading projection and ownership data for the board.</p>
                </article>
              )}

              {!decisionLoading && decisionError && (
                <article className="decision-row decision-row-state decision-row-error" aria-live="polite">
                  <p>{decisionError}</p>
                </article>
              )}

              {!decisionLoading && !decisionError && decisionRows.length === 0 && (
                <article className="decision-row decision-row-state">
                  <p>No projection rows are available for 2025 week 11 yet.</p>
                </article>
              )}

              {!decisionLoading && !decisionError && decisionRows.map((row) => (
                <article className="decision-row" key={row.key}>
                  <div className="player-cell">
                    <strong>{row.player}</strong>
                    <span>{row.team} · {row.pos}</span>
                  </div>
                  <span>{row.salary}</span>
                  <span>{row.proj}</span>
                  <span>{row.ceiling}</span>
                  <span>{row.own}</span>
                  <span>{row.optimal}</span>
                  <span
                    className={
                      row.leverageValue === null
                        ? ""
                        : row.leverageValue < 0
                          ? "negative"
                          : "positive"
                    }
                  >
                    {row.leverage}
                  </span>
                  <span className={`stance stance-${row.stance.toLowerCase()}`}>
                    {row.stance}
                  </span>
                  <p>{row.reason}</p>
                </article>
              ))}
            </div>
          </div>

          <div className="war-panel game-matrix">
            <div className="war-panel-title">
              <span>Game Pressure Matrix</span>
              <strong>Where the slate can break</strong>
            </div>
            {weatherLoading && (
              <div className="weather-banner" aria-live="polite">
                Loading cutoff-safe weather for every slate matchup.
              </div>
            )}
            {!weatherLoading && weatherError && (
              <div className="weather-banner weather-banner-error" aria-live="polite">
                Weather service unavailable: {weatherError}
              </div>
            )}
            {!weatherLoading && !weatherError && weatherReport && weatherReport.quality_flags.length > 0 && (
              <div className="weather-banner weather-banner-warning" aria-live="polite">
                <strong>Slate weather warnings:</strong>{" "}
                {weatherReport.quality_flags.map(formatWeatherWarning).join(" ")}
              </div>
            )}
            <div className="game-grid">
              {!decisionLoading && !weatherLoading && gameMatrixRows.length === 0 && (
                <article className="game-card-empty">
                  <span>No Active Games</span>
                  <p>No projection or canonical weather matchups are available for this slate.</p>
                </article>
              )}

              {gameMatrixRows.map((game) => (
                <article
                  key={game.key}
                  className={selectedGame?.key === game.key ? "selected" : ""}
                >
                  <button
                    type="button"
                    className="game-card-button"
                    aria-pressed={selectedGame?.key === game.key}
                    onClick={() => setSelectedGameKey(game.key)}
                  >
                    <div className="game-card-head">
                      <span>{game.matchup}</span>
                      <span className={`weather-state weather-state-${game.weatherState}`}>
                        {weatherStateLabel(game.weatherState)}
                      </span>
                    </div>
                    <div className="game-pressure-grade">
                      <strong>{game.pressure}</strong>
                      <span>Pressure</span>
                    </div>
                    <dl>
                      <div>
                        <dt>Avg Proj</dt>
                        <dd>{game.avgProjection}</dd>
                      </div>
                      <div>
                        <dt>Signals</dt>
                        <dd>{game.affectedPlayers}</dd>
                      </div>
                      <div>
                        <dt>Risk</dt>
                        <dd>{game.risk}</dd>
                      </div>
                    </dl>
                    <div className="game-weather-quick">
                      <span>{formatTemperatureC(game.weather?.forecast?.temperature_c)}</span>
                      <span>{formatWindMps(game.weather?.forecast?.wind_speed_mps)} wind</span>
                      <span>{formatPrecipitationMm(game.weather?.forecast?.precipitation_mm)} precip</span>
                    </div>
                  </button>
                </article>
              ))}
            </div>

            {selectedGame && (
              <section className="matchup-weather-detail" aria-label={`${selectedGame.matchup} weather detail`}>
                <div className="matchup-weather-head">
                  <div>
                    <span>Matchup Weather Detail</span>
                    <h3>{selectedGame.matchup}</h3>
                    <p>
                      {selectedGame.kickoffAt
                        ? `Kickoff ${formatDateTime(selectedGame.kickoffAt)}`
                        : "Kickoff unavailable"}
                    </p>
                  </div>
                  <span className={`weather-state weather-state-${selectedGame.weatherState}`}>
                    {weatherStateLabel(selectedGame.weatherState)}
                  </span>
                </div>

                {!selectedWeather && (
                  <div className="weather-detail-empty">
                    {weatherLoading
                      ? "Waiting for the canonical slate weather response."
                      : weatherError
                        ? "The weather request failed; this matchup is explicitly marked Error."
                        : "No canonical weather row matched this projection matchup; it is explicitly marked Missing."}
                  </div>
                )}

                {selectedWeather && (
                  <>
                    <div className="weather-metrics">
                      <article>
                        <span>Temperature</span>
                        <strong>{formatTemperatureC(selectedWeather.forecast?.temperature_c)}</strong>
                      </article>
                      <article>
                        <span>Wind</span>
                        <strong>{formatWindMps(selectedWeather.forecast?.wind_speed_mps)}</strong>
                      </article>
                      <article>
                        <span>Gusts</span>
                        <strong>{formatWindMps(selectedWeather.forecast?.wind_gusts_mps)}</strong>
                      </article>
                      <article>
                        <span>Precipitation</span>
                        <strong>{formatPrecipitationMm(selectedWeather.forecast?.precipitation_mm)}</strong>
                      </article>
                      <article>
                        <span>Roof</span>
                        <strong>{formatRoof(selectedWeather.venue?.default_roof)}</strong>
                        <small>Venue registry default</small>
                      </article>
                    </div>

                    <div className="weather-lineage">
                      <div>
                        <span>Forecast Source</span>
                        <strong>{formatForecastSource(selectedWeather)}</strong>
                      </div>
                      <div>
                        <span>Forecast Timestamp</span>
                        <strong>{formatForecastTimestamp(selectedWeather)}</strong>
                      </div>
                      <div>
                        <span>Forecast Valid For</span>
                        <strong>{formatDateTime(selectedWeather.forecast?.valid_at)}</strong>
                      </div>
                      <div>
                        <span>Freshness</span>
                        <strong>{formatFreshness(selectedWeather.forecast?.age_seconds)}</strong>
                      </div>
                      <div>
                        <span>Venue</span>
                        <strong>{selectedWeather.venue?.name ?? "Unknown venue"}</strong>
                      </div>
                    </div>

                    <div className={`weather-warnings ${selectedWeatherWarnings.length > 0 ? "has-warnings" : ""}`}>
                      <span>Warnings & Quality</span>
                      {selectedWeatherWarnings.length === 0 ? (
                        <p>No weather quality warnings.</p>
                      ) : (
                        <ul>
                          {selectedWeatherWarnings.map((warning) => (
                            <li key={warning}>{warning}</li>
                          ))}
                        </ul>
                      )}
                    </div>

                    {shouldShowHistoricalActual(weatherReport?.request_kind, selectedWeather) &&
                      selectedWeather.actual && (
                        <section className="historical-actual" aria-label="Historical actual weather">
                          <div>
                            <span>Historical Actual · Replay-Ineligible</span>
                            <strong>{titleCase(selectedWeather.actual.weather_status)}</strong>
                          </div>
                          <p>
                            Observed conditions are shown only for completed historical games and are never
                            used as the forecast.
                          </p>
                          <dl>
                            <div>
                              <dt>Temperature</dt>
                              <dd>
                                {selectedWeather.actual.temperature_f === null
                                  ? "--"
                                  : `${Math.round(selectedWeather.actual.temperature_f)}°F`}
                              </dd>
                            </div>
                            <div>
                              <dt>Wind</dt>
                              <dd>
                                {selectedWeather.actual.wind_mph === null
                                  ? "--"
                                  : `${Math.round(selectedWeather.actual.wind_mph)} mph`}
                              </dd>
                            </div>
                            <div>
                              <dt>Roof</dt>
                              <dd>{formatRoof(selectedWeather.actual.roof)}</dd>
                            </div>
                            <div>
                              <dt>Source</dt>
                              <dd>{selectedWeather.actual.source_system}</dd>
                            </div>
                          </dl>
                        </section>
                      )}
                  </>
                )}
              </section>
            )}
          </div>
        </section>

        <aside className="war-panel debate-rail">
          <div className="war-panel-title">
            <span>Lineup Debate</span>
            <strong>Human decision log</strong>
          </div>
          <div className="debate-card locked">
            <span>Current focus</span>
            <p>
              {selectedDecision
                ? `${selectedDecision.player} (${selectedDecision.team} ${selectedDecision.pos}) is currently tagged ${debateStance}.`
                : "Select a live decision-board player once projections are available."}
            </p>
          </div>
          <div className="debate-card">
            <span>Decision context</span>
            <p>
              {selectedDecision
                ? selectedDecision.reason
                : "Projection, ownership, and slate signal context will appear here once the board is populated."}
            </p>
          </div>
          <div className="debate-card">
            <span>Working stance</span>
            <div className="debate-controls">
              <label>
                Player
                <select
                  value={selectedDecision?.player ?? ""}
                  onChange={(event) => setSelectedDebatePlayer(event.target.value)}
                  disabled={decisionRows.length === 0}
                >
                  {decisionRows.length === 0 ? (
                    <option value="">No players loaded</option>
                  ) : (
                    decisionRows.map((row) => (
                      <option key={row.key} value={row.player}>
                        {row.player} · {row.team} · {row.pos}
                      </option>
                    ))
                  )}
                </select>
              </label>

              <div className="debate-stance-group" role="group" aria-label="Debate stance">
                {(["Core", "Over", "Under", "Fade", "Need more info"] as DebateStance[]).map((stance) => (
                  <button
                    key={stance}
                    type="button"
                    className={stance === debateStance ? "active" : ""}
                    onClick={() => setDebateStance(stance)}
                  >
                    {stance}
                  </button>
                ))}
              </div>

              <label>
                Notes
                <textarea
                  rows={4}
                  value={debateNote}
                  onChange={(event) => setDebateNote(event.target.value)}
                  placeholder="Record the argument, trigger, or exposure rule before final optimizer run."
                />
              </label>
            </div>
          </div>
          <button type="button" className="debate-button">
            {selectedDecision ? `Hold ${debateStance} on ${selectedDecision.player}` : "Await board data"}
          </button>
        </aside>
      </section>

      <section className="war-bottom">
        <div className="war-panel exposure-strip">
          <div className="war-panel-title">
            <span>Portfolio Exposure</span>
            <strong>Team pressure by build set</strong>
          </div>
          <div className="exposure-bars">
            {exposureRows.length === 0 && (
              <div className="exposure-empty">
                Run the optimizer in Operations to populate team exposure.
              </div>
            )}
            {exposureRows.map((item) => (
              <div className="exposure-row" key={item.label}>
                <span>{item.label}</span>
                <div>
                  <i className={`tone-${item.tone}`} style={{ width: `${item.value}%` }} />
                </div>
                <strong>{item.value}%</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="war-panel lineup-stack">
          <div className="war-panel-title">
            <span>Candidate Lineups</span>
            <strong>Compare arguments, not just projections</strong>
          </div>
          <div className="lineup-cards">
            {lineupCards.length === 0 && (
              <article className="lineup-empty">
                <div>
                  <span>No Optimizer Portfolio</span>
                  <strong>--</strong>
                </div>
                <p>Run the optimizer in Operations, then return here to compare candidate builds.</p>
                <footer>
                  <span>Status</span>
                  <span>{optimizerStatus?.status ?? "idle"}</span>
                </footer>
              </article>
            )}
            {lineupCards.map((lineup) => (
              <article key={lineup.name}>
                <div>
                  <span>{lineup.name}</span>
                  <strong>{lineup.ceiling}</strong>
                </div>
                <p>{lineup.build}</p>
                <footer>
                  <span>Own {lineup.own}</span>
                  <span>{lineup.salary}</span>
                </footer>
              </article>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
