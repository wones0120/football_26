import { useEffect, useMemo, useState } from "react";
import {
  autoDiscoverInjuryFiles,
  autoDiscoverSalaryFiles,
  backtestWeek,
  bootstrapNflreadpy,
  fetchCuratedSalarySlices,
  fetchSeasonCoverage,
  fetchRuns,
  fetchUnresolved,
  ingestNflreadpySchedules,
  ingestNflreadpyWeeklyStats,
  ingestInjuries,
  ingestSalaries,
  runOptimalVsPredictedBacktest,
  resolveUnresolved,
  simulateWeek,
  upsertPlayerMaster,
  type BacktestWeekResult,
  type IngestResult,
  type CuratedSalarySliceRow,
  type OptimalVsPredictedBacktestResult,
  type SeasonCoverageRow,
  type SimulatedPlayerOutcome,
  type UnresolvedRow,
} from "./api";

function App() {
  const slateOptions = ["sunday_main", "sunday_night", "monday_night", "thursday_night"] as const;
  const [sourceSystem, setSourceSystem] = useState<"draftkings" | "fanduel">("draftkings");
  const [season, setSeason] = useState(2025);
  const [week, setWeek] = useState(1);
  const [slate, setSlate] = useState<string>(slateOptions[0]);
  const [historyStartSeason, setHistoryStartSeason] = useState(2018);
  const [historyEndSeason, setHistoryEndSeason] = useState(2025);
  const [salaryPath, setSalaryPath] = useState("~/Downloads/DKSalaries.csv");
  const [injuryPath, setInjuryPath] = useState("~/Downloads/DKInjuries.csv");
  const [discoverDirectory, setDiscoverDirectory] = useState("~/Downloads");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isIngesting, setIsIngesting] = useState(false);
  const [simulationIterations, setSimulationIterations] = useState(5000);
  const [simulationTopN, setSimulationTopN] = useState(40);
  const [simulationMinHistoryGames, setSimulationMinHistoryGames] = useState(4);
  const [simulationPriorWeight, setSimulationPriorWeight] = useState(12);
  const [simulationNoiseScale, setSimulationNoiseScale] = useState(0.12);
  const [backtestTopN, setBacktestTopN] = useState(25);
  const [backtestLowSalaryThreshold, setBacktestLowSalaryThreshold] = useState(4500);
  const [backtestLowSalaryHitPoints, setBacktestLowSalaryHitPoints] = useState(15);
  const [lineupBacktestMode, setLineupBacktestMode] = useState<"classic" | "showdown">("classic");
  const [lineupBacktestLineupsPerSlate, setLineupBacktestLineupsPerSlate] = useState(600);
  const [lineupBacktestTrainingWindowSlates, setLineupBacktestTrainingWindowSlates] = useState(24);
  const [lineupBacktestMinTrainingSlates, setLineupBacktestMinTrainingSlates] = useState(2);
  const [lineupBacktestMinTrainingRows, setLineupBacktestMinTrainingRows] = useState(500);
  const [lineupBacktestLimitSlates, setLineupBacktestLimitSlates] = useState(0);
  const [simulationRows, setSimulationRows] = useState<SimulatedPlayerOutcome[]>([]);
  const [simulationRunId, setSimulationRunId] = useState<string | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestWeekResult | null>(null);
  const [lineupBacktestClassicResult, setLineupBacktestClassicResult] =
    useState<OptimalVsPredictedBacktestResult | null>(null);
  const [lineupBacktestShowdownResult, setLineupBacktestShowdownResult] =
    useState<OptimalVsPredictedBacktestResult | null>(null);
  const [runs, setRuns] = useState<IngestResult[]>([]);
  const [coverage, setCoverage] = useState<SeasonCoverageRow[]>([]);
  const [salarySlices, setSalarySlices] = useState<CuratedSalarySliceRow[]>([]);
  const [salarySliceSeasonFilter, setSalarySliceSeasonFilter] = useState("");
  const [showUnresolvedQueue, setShowUnresolvedQueue] = useState(false);
  const [showSeasonCoverage, setShowSeasonCoverage] = useState(false);
  const [showCuratedSalarySlices, setShowCuratedSalarySlices] = useState(false);
  const [showRecentRuns, setShowRecentRuns] = useState(false);
  const [unresolved, setUnresolved] = useState<UnresolvedRow[]>([]);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});

  const unresolvedCount = unresolved.length;
  const completionPct = useMemo(() => {
    const total = runs.reduce((acc, row) => acc + row.rows_curated, 0);
    const unresolvedRows = runs.reduce((acc, row) => acc + row.rows_unresolved, 0);
    if (total === 0) return 0;
    return Math.max(0, Math.round(((total - unresolvedRows) / total) * 100));
  }, [runs]);
  const lineupBacktestPanels = [
    { mode: "classic" as const, result: lineupBacktestClassicResult },
    { mode: "showdown" as const, result: lineupBacktestShowdownResult },
  ];

  const refresh = async () => {
    const [runsResp, unresolvedResp, coverageResp] = await Promise.all([
      fetchRuns(),
      fetchUnresolved(),
      fetchSeasonCoverage(),
    ]);
    setRuns(runsResp.rows);
    setUnresolved(unresolvedResp.rows);
    setCoverage(coverageResp.rows);
  };

  const refreshCuratedSalarySlices = async () => {
    const seasonText = salarySliceSeasonFilter.trim();
    if (seasonText.length > 0) {
      const parsed = Number(seasonText);
      if (!Number.isFinite(parsed) || parsed < 2000) {
        throw new Error("Season filter must be a year like 2024");
      }
      const response = await fetchCuratedSalarySlices({
        season: parsed,
        source_system: sourceSystem,
        limit: 5000,
      });
      setSalarySlices(response.rows);
      return;
    }
    const response = await fetchCuratedSalarySlices({
      source_system: sourceSystem,
      limit: 5000,
    });
    setSalarySlices(response.rows);
  };

  useEffect(() => {
    refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    if (!showCuratedSalarySlices) return;
    refreshCuratedSalarySlices().catch((err) =>
      setError(err instanceof Error ? err.message : String(err))
    );
  }, [sourceSystem, showCuratedSalarySlices]);

  const runSalaries = async () => {
    setIsIngesting(true);
    setStatus("Ingesting salaries...");
    setError(null);
    try {
      const result = await ingestSalaries({
        source_system: sourceSystem,
        season,
        week,
        slate,
        path: salaryPath,
      });
      setStatus(
        `Salaries loaded: curated=${result.rows_curated} unresolved=${result.rows_unresolved}`
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runInjuries = async () => {
    setIsIngesting(true);
    setStatus("Ingesting injuries...");
    setError(null);
    try {
      const result = await ingestInjuries({
        source_system: sourceSystem,
        season,
        week,
        slate,
        path: injuryPath,
      });
      setStatus(
        `Injuries loaded: curated=${result.rows_curated} unresolved=${result.rows_unresolved}`
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runAutoDiscoverSalaries = async () => {
    setIsIngesting(true);
    setStatus(`Discovering ${sourceSystem} salary files in ${discoverDirectory}...`);
    setError(null);
    try {
      const result = await autoDiscoverSalaryFiles({
        source_system: sourceSystem,
        directory: discoverDirectory,
      });
      setStatus(
        `Salary auto-import: completed=${result.files_completed}/${result.files_attempted} failed=${result.files_failed} curated=${result.rows_curated} unresolved=${result.rows_unresolved}`
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runAutoDiscoverInjuries = async () => {
    setIsIngesting(true);
    setStatus(`Discovering ${sourceSystem} injury files in ${discoverDirectory}...`);
    setError(null);
    try {
      const result = await autoDiscoverInjuryFiles({
        source_system: sourceSystem,
        directory: discoverDirectory,
      });
      setStatus(
        `Injury auto-import: completed=${result.files_completed}/${result.files_attempted} failed=${result.files_failed} curated=${result.rows_curated} unresolved=${result.rows_unresolved}`
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runBootstrap = async () => {
    setIsIngesting(true);
    setStatus("Bootstrapping player master from nflreadpy...");
    setError(null);
    try {
      const result = await bootstrapNflreadpy({ season });
      setStatus(
        `nflreadpy bootstrap completed: curated=${result.rows_curated} unresolved=${result.rows_unresolved}`
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runNflSchedules = async () => {
    setIsIngesting(true);
    setStatus(`Loading nflreadpy schedules for ${season}...`);
    setError(null);
    try {
      const result = await ingestNflreadpySchedules({ season });
      setStatus(`Schedules loaded: rows=${result.rows_curated}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runNflWeeklyStats = async () => {
    setIsIngesting(true);
    setStatus(`Loading nflreadpy weekly stats for ${season}...`);
    setError(null);
    try {
      const result = await ingestNflreadpyWeeklyStats({ season });
      setStatus(`Weekly stats loaded: rows=${result.rows_curated} unresolved=${result.rows_unresolved}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runHistoricalBootstrap = async () => {
    const start = Math.min(historyStartSeason, historyEndSeason);
    const end = Math.max(historyStartSeason, historyEndSeason);
    let activeSeason = start;
    let totalRaw = 0;
    let totalCurated = 0;
    let totalUnresolved = 0;
    setIsIngesting(true);
    setStatus(`Bootstrapping nflreadpy seasons ${start}-${end}...`);
    setError(null);
    try {
      for (let value = start; value <= end; value += 1) {
        activeSeason = value;
        setStatus(`Bootstrapping nflreadpy season ${value} (${value - start + 1}/${end - start + 1})...`);
        const result = await bootstrapNflreadpy({ season: value });
        totalRaw += result.rows_raw;
        totalCurated += result.rows_curated;
        totalUnresolved += result.rows_unresolved;
      }
      setStatus(
        `Historical bootstrap completed (${start}-${end}): raw=${totalRaw} curated=${totalCurated} unresolved=${totalUnresolved}`
      );
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Season ${activeSeason} failed: ${message}`);
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runHistoricalGameData = async () => {
    const start = Math.min(historyStartSeason, historyEndSeason);
    const end = Math.max(historyStartSeason, historyEndSeason);
    const totalSeasons = end - start + 1;
    let activeSeason = start;
    let totalScheduleRows = 0;
    let totalWeeklyStatRows = 0;
    setIsIngesting(true);
    setStatus(`Loading nflreadpy schedules + weekly stats for ${start}-${end}...`);
    setError(null);
    try {
      for (let value = start; value <= end; value += 1) {
        activeSeason = value;
        setStatus(`Season ${value} (${value - start + 1}/${totalSeasons}): loading schedules...`);
        const scheduleResult = await ingestNflreadpySchedules({ season: value });
        totalScheduleRows += scheduleResult.rows_curated;

        setStatus(`Season ${value} (${value - start + 1}/${totalSeasons}): loading weekly stats...`);
        const weeklyResult = await ingestNflreadpyWeeklyStats({ season: value });
        totalWeeklyStatRows += weeklyResult.rows_curated;
      }
      setStatus(
        `Historical game data completed (${start}-${end}): schedule_rows=${totalScheduleRows} weekly_stat_rows=${totalWeeklyStatRows}`
      );
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Season ${activeSeason} failed: ${message}`);
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runSimulation = async () => {
    setIsIngesting(true);
    setSimulationRows([]);
    setSimulationRunId(null);
    setStatus(`Simulating ${sourceSystem} season ${season} week ${week} (${slate})...`);
    setError(null);
    try {
      const result = await simulateWeek({
        source_system: sourceSystem,
        season,
        week,
        slate,
        iterations: simulationIterations,
        top_n: simulationTopN,
        min_history_games: simulationMinHistoryGames,
        prior_weight: simulationPriorWeight,
        noise_scale: simulationNoiseScale,
      });
      setSimulationRows(result.top_rows);
      setSimulationRunId(result.simulation_run_id);
      setStatus(
        `Simulation completed: players=${result.players_simulated}/${result.players_considered} iterations=${result.iterations}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runBacktest = async () => {
    setIsIngesting(true);
    setBacktestResult(null);
    setStatus(`Backtesting ${sourceSystem} season ${season} week ${week} (${slate})...`);
    setError(null);
    try {
      const result = await backtestWeek({
        source_system: sourceSystem,
        season,
        week,
        slate,
        iterations: simulationIterations,
        min_history_games: simulationMinHistoryGames,
        prior_weight: simulationPriorWeight,
        noise_scale: simulationNoiseScale,
        evaluation_top_n: backtestTopN,
        low_salary_threshold: backtestLowSalaryThreshold,
        low_salary_hit_points: backtestLowSalaryHitPoints,
      });
      setBacktestResult(result);
      setStatus(
        `Backtest completed: matched=${result.players_with_actuals}/${result.players_simulated} mae=${result.mae.toFixed(2)} rmse=${result.rmse.toFixed(2)}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runLineupBacktest = async () => {
    const seasonStart = Math.min(historyStartSeason, historyEndSeason);
    const seasonEnd = Math.max(historyStartSeason, historyEndSeason);
    setIsIngesting(true);
    setStatus(
      `Running ${lineupBacktestMode} lineup backtest for ${sourceSystem} seasons ${seasonStart}-${seasonEnd}...`
    );
    setError(null);
    try {
      const result = await runOptimalVsPredictedBacktest({
        source_system: sourceSystem,
        season_start: seasonStart,
        season_end: seasonEnd,
        slate_type: lineupBacktestMode,
        lineups_per_slate: lineupBacktestLineupsPerSlate,
        training_window_slates: lineupBacktestTrainingWindowSlates,
        min_training_slates: lineupBacktestMinTrainingSlates,
        min_training_rows: lineupBacktestMinTrainingRows,
        learned_only: true,
        limit_slates: lineupBacktestLimitSlates,
      });
      if (lineupBacktestMode === "classic") {
        setLineupBacktestClassicResult(result);
      } else {
        setLineupBacktestShowdownResult(result);
      }
      const meanGap = result.mean_gap_points == null ? "n/a" : result.mean_gap_points.toFixed(2);
      setStatus(
        `${lineupBacktestMode} lineup backtest completed: slates=${result.slates_completed}/${result.slates_total} mean_gap=${meanGap}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const downloadLineupBacktestResult = (
    mode: "classic" | "showdown",
    result: OptimalVsPredictedBacktestResult
  ) => {
    const payload = {
      exported_at: new Date().toISOString(),
      mode,
      source_system: result.source_system,
      summary: {
        season_start: result.season_start,
        season_end: result.season_end,
        slate_filter: result.slate_filter,
        slate_type: result.slate_type,
        lineups_per_slate: result.lineups_per_slate,
        training_window_slates: result.training_window_slates,
        learned_only: result.learned_only,
        slates_total: result.slates_total,
        slates_completed: result.slates_completed,
        slates_failed_or_skipped: result.slates_failed_or_skipped,
        mean_gap_points: result.mean_gap_points,
        median_gap_points: result.median_gap_points,
        best_case_gap_points: result.best_case_gap_points,
        worst_case_gap_points: result.worst_case_gap_points,
      },
      rows: result.rows,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    a.href = url;
    a.download = `lineup_backtest_${mode}_${result.season_start}_${result.season_end}_${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const createAndResolve = async (row: UnresolvedRow) => {
    setStatus(`Resolving ${row.normalized_name}...`);
    setError(null);
    try {
      const player = await upsertPlayerMaster({
        full_name: row.normalized_name
          .split(" ")
          .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : part))
          .join(" "),
        team: row.team ?? undefined,
        position: row.position ?? undefined,
      });
      await resolveUnresolved(row.unresolved_id, {
        player_master_id: player.player_master_id,
        resolved_by: "ui_auto",
        create_alias: true,
      });
      setStatus(`Resolved ${row.normalized_name} -> ${player.player_master_id}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    }
  };

  const manualResolve = async (row: UnresolvedRow) => {
    const playerMasterId = resolutions[row.unresolved_id];
    if (!playerMasterId) {
      setError("player_master_id is required for manual resolve");
      return;
    }
    setStatus(`Applying manual resolve for ${row.normalized_name}...`);
    setError(null);
    try {
      await resolveUnresolved(row.unresolved_id, {
        player_master_id: playerMasterId,
        resolved_by: "ui_manual",
        create_alias: true,
      });
      setStatus(`Resolved ${row.normalized_name}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    }
  };

  const toggleCuratedSalarySlices = async () => {
    const next = !showCuratedSalarySlices;
    setShowCuratedSalarySlices(next);
    if (!next) return;
    try {
      await refreshCuratedSalarySlices();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">football_26</p>
          <h1>Data Ops Control Plane</h1>
          <p className="subtitle">
            Deterministic identity mapping, ingestion lineage, and unresolved-player triage.
          </p>
        </div>
        <div className="stats">
          <div className="stat-card">
            <span>Resolution</span>
            <strong>{completionPct}%</strong>
          </div>
          <div className="stat-card">
            <span>Open Unresolved</span>
            <strong>{unresolvedCount}</strong>
          </div>
        </div>
      </header>

      <main className="layout">
        <section className="panel">
          <h2>Ingestion</h2>
          <div className="grid">
            <label>
              Source
              <select
                value={sourceSystem}
                onChange={(event) => setSourceSystem(event.target.value as "draftkings" | "fanduel")}
              >
                <option value="draftkings">DraftKings</option>
                <option value="fanduel">FanDuel</option>
              </select>
            </label>
            <label>
              Season
              <input
                type="number"
                value={season}
                onChange={(event) => setSeason(Number(event.target.value))}
              />
            </label>
            <label>
              Week
              <input
                type="number"
                value={week}
                onChange={(event) => setWeek(Number(event.target.value))}
              />
            </label>
            <label>
              Slate
              <select value={slate} onChange={(event) => setSlate(event.target.value)}>
                {slateOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="form-stack">
            <label>
              Salary CSV Path
              <input
                className="wide"
                type="text"
                value={salaryPath}
                onChange={(event) => setSalaryPath(event.target.value)}
              />
            </label>
            <label>
              Injury CSV Path
              <input
                className="wide"
                type="text"
                value={injuryPath}
                onChange={(event) => setInjuryPath(event.target.value)}
              />
            </label>
          </div>
          <div className="button-row">
            <button onClick={runSalaries} disabled={isIngesting}>
              Load Salaries
            </button>
            <button onClick={runInjuries} disabled={isIngesting}>
              Load Injuries
            </button>
            <button onClick={runBootstrap} disabled={isIngesting}>
              Bootstrap nflreadpy
            </button>
            <button onClick={runNflSchedules} disabled={isIngesting}>
              Load Schedules
            </button>
            <button onClick={runNflWeeklyStats} disabled={isIngesting}>
              Load Weekly Stats
            </button>
            <button onClick={() => refresh()} disabled={isIngesting}>
              Refresh
            </button>
          </div>

          <div className="subsection">
            <h3>Auto-Discover Local CSVs</h3>
            <p className="hint">Bulk import files by filename pattern from one directory.</p>
            <label>
              Discovery Directory
              <input
                className="wide"
                type="text"
                value={discoverDirectory}
                onChange={(event) => setDiscoverDirectory(event.target.value)}
              />
            </label>
            <div className="button-row">
              <button onClick={runAutoDiscoverSalaries} disabled={isIngesting}>
                Auto Import Salaries
              </button>
              <button onClick={runAutoDiscoverInjuries} disabled={isIngesting}>
                Auto Import Injuries
              </button>
            </div>
          </div>

          <div className="subsection">
            <h3>Historical nflreadpy Loads</h3>
            <p className="hint">Run season-range identity bootstrap and game-data backfills from one panel.</p>
            <div className="range-grid">
              <label>
                Start Season
                <input
                  type="number"
                  value={historyStartSeason}
                  onChange={(event) => setHistoryStartSeason(Number(event.target.value))}
                />
              </label>
              <label>
                End Season
                <input
                  type="number"
                  value={historyEndSeason}
                  onChange={(event) => setHistoryEndSeason(Number(event.target.value))}
                />
              </label>
            </div>
            <div className="button-row">
              <button onClick={runHistoricalBootstrap} disabled={isIngesting}>
                Bootstrap Season Range
              </button>
              <button onClick={runHistoricalGameData} disabled={isIngesting}>
                Load Historical Game Data
              </button>
            </div>
          </div>
          {status && <p className="status">{status}</p>}
          {error && <p className="error">{error}</p>}
        </section>

        <section className="panel">
          <h2>Projection Simulation</h2>
          <p className="hint">
            Monte Carlo outcomes from historical nflreadpy player-game distributions, joined to the selected
            salary slate.
          </p>
          <div className="simulation-grid">
            <label>
              Iterations
              <input
                type="number"
                min={500}
                max={50000}
                step={500}
                value={simulationIterations}
                onChange={(event) => setSimulationIterations(Number(event.target.value))}
              />
            </label>
            <label>
              Top Results
              <input
                type="number"
                min={5}
                max={300}
                step={5}
                value={simulationTopN}
                onChange={(event) => setSimulationTopN(Number(event.target.value))}
              />
            </label>
            <label>
              Min History Games
              <input
                type="number"
                min={1}
                max={30}
                value={simulationMinHistoryGames}
                onChange={(event) => setSimulationMinHistoryGames(Number(event.target.value))}
              />
            </label>
            <label>
              Prior Weight
              <input
                type="number"
                min={0}
                max={100}
                step={0.5}
                value={simulationPriorWeight}
                onChange={(event) => setSimulationPriorWeight(Number(event.target.value))}
              />
            </label>
            <label>
              Noise Scale
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={simulationNoiseScale}
                onChange={(event) => setSimulationNoiseScale(Number(event.target.value))}
              />
            </label>
          </div>
          <div className="button-row">
            <button onClick={runSimulation} disabled={isIngesting}>
              Run Simulation
            </button>
            <button onClick={runBacktest} disabled={isIngesting}>
              Run Historical Backtest
            </button>
            <button
              onClick={() => {
                setSimulationRows([]);
                setSimulationRunId(null);
                setBacktestResult(null);
              }}
              disabled={isIngesting || (simulationRows.length === 0 && backtestResult == null)}
            >
              Clear Results
            </button>
          </div>
          {simulationRunId && <p className="hint">Run ID: {simulationRunId}</p>}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Player</th>
                  <th>Team</th>
                  <th>Pos</th>
                  <th>Salary</th>
                  <th>Hist</th>
                  <th>Mean</th>
                  <th>P75</th>
                  <th>P90</th>
                  <th>P95</th>
                  <th>P(20+)</th>
                  <th>P(25+)</th>
                </tr>
              </thead>
              <tbody>
                {simulationRows.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="empty-row">
                      Run a simulation to populate projected player outcomes.
                    </td>
                  </tr>
                ) : (
                  simulationRows.map((row, index) => (
                    <tr key={`${row.player_master_id ?? row.source_player_key ?? row.player_name}-${index}`}>
                      <td>{index + 1}</td>
                      <td>{row.player_name}</td>
                      <td>{row.team ?? "-"}</td>
                      <td>{row.position ?? "-"}</td>
                      <td>{row.salary != null ? `$${row.salary.toLocaleString()}` : "-"}</td>
                      <td>{row.history_games}</td>
                      <td>{row.mean_points.toFixed(2)}</td>
                      <td>{row.p75_points.toFixed(2)}</td>
                      <td>{row.p90_points.toFixed(2)}</td>
                      <td>{row.p95_points.toFixed(2)}</td>
                      <td>{(row.ceiling_prob_20 * 100).toFixed(1)}%</td>
                      <td>{(row.ceiling_prob_25 * 100).toFixed(1)}%</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="subsection">
            <h3>Backtest Learning Controls</h3>
            <p className="hint">
              Runs the same simulation settings for a historical week, compares to actual DK points, and reports
              learnings for future projection adjustments.
            </p>
            <div className="backtest-grid">
              <label>
                Evaluation Top N
                <input
                  type="number"
                  min={5}
                  max={300}
                  step={5}
                  value={backtestTopN}
                  onChange={(event) => setBacktestTopN(Number(event.target.value))}
                />
              </label>
              <label>
                Low Salary Threshold
                <input
                  type="number"
                  min={500}
                  max={20000}
                  step={100}
                  value={backtestLowSalaryThreshold}
                  onChange={(event) => setBacktestLowSalaryThreshold(Number(event.target.value))}
                />
              </label>
              <label>
                Low Salary Hit Points
                <input
                  type="number"
                  min={1}
                  max={80}
                  step={0.5}
                  value={backtestLowSalaryHitPoints}
                  onChange={(event) => setBacktestLowSalaryHitPoints(Number(event.target.value))}
                />
              </label>
            </div>
          </div>

          {backtestResult && (
            <div className="subsection">
              <h3>Backtest Results</h3>
              <div className="metric-grid">
                <div className="mini-card">
                  <span>Players w/Actuals</span>
                  <strong>
                    {backtestResult.players_with_actuals}/{backtestResult.players_simulated}
                  </strong>
                </div>
                <div className="mini-card">
                  <span>MAE / RMSE</span>
                  <strong>
                    {backtestResult.mae.toFixed(2)} / {backtestResult.rmse.toFixed(2)}
                  </strong>
                </div>
                <div className="mini-card">
                  <span>Top-N Hits (20+)</span>
                  <strong>
                    {backtestResult.top_n_hits}/{backtestResult.evaluation_top_n}
                  </strong>
                </div>
                <div className="mini-card">
                  <span>Low Salary Hit Rate</span>
                  <strong>{(backtestResult.low_salary_hit_rate * 100).toFixed(1)}%</strong>
                </div>
                <div className="mini-card">
                  <span>Bias (Mean Error)</span>
                  <strong>{backtestResult.mean_error.toFixed(2)}</strong>
                </div>
                <div className="mini-card">
                  <span>Correlation</span>
                  <strong>
                    {backtestResult.correlation == null ? "-" : backtestResult.correlation.toFixed(3)}
                  </strong>
                </div>
              </div>

              <ul className="learning-list">
                {backtestResult.learning_notes.map((note, index) => (
                  <li key={`${note}-${index}`}>{note}</li>
                ))}
              </ul>

              <div className="dual-tables">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Position</th>
                        <th>Players</th>
                        <th>Pred</th>
                        <th>Actual</th>
                        <th>Error</th>
                        <th>Adj Mult</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backtestResult.position_learning.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="empty-row">
                            No position learnings.
                          </td>
                        </tr>
                      ) : (
                        backtestResult.position_learning.map((row) => (
                          <tr key={row.position}>
                            <td>{row.position}</td>
                            <td>{row.players}</td>
                            <td>{row.mean_prediction.toFixed(2)}</td>
                            <td>{row.mean_actual.toFixed(2)}</td>
                            <td>{row.mean_error.toFixed(2)}</td>
                            <td>{row.adjustment_multiplier.toFixed(3)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Salary Bucket</th>
                        <th>Players</th>
                        <th>Pred</th>
                        <th>Actual</th>
                        <th>Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backtestResult.salary_bucket_learning.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="empty-row">
                            No salary bucket learnings.
                          </td>
                        </tr>
                      ) : (
                        backtestResult.salary_bucket_learning.map((row) => (
                          <tr key={row.bucket}>
                            <td>{row.bucket}</td>
                            <td>{row.players}</td>
                            <td>{row.mean_prediction.toFixed(2)}</td>
                            <td>{row.mean_actual.toFixed(2)}</td>
                            <td>{row.mean_error.toFixed(2)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Player</th>
                      <th>Pos</th>
                      <th>Salary</th>
                      <th>Pred Mean</th>
                      <th>Pred P90</th>
                      <th>Actual</th>
                      <th>Error</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtestResult.rows.map((row, index) => (
                      <tr key={`${row.player_master_id ?? row.source_player_key ?? row.player_name}-${index}`}>
                        <td>{index + 1}</td>
                        <td>{row.player_name}</td>
                        <td>{row.position ?? "-"}</td>
                        <td>{row.salary != null ? `$${row.salary.toLocaleString()}` : "-"}</td>
                        <td>{row.predicted_mean_points.toFixed(2)}</td>
                        <td>{row.predicted_p90_points.toFixed(2)}</td>
                        <td>{row.actual_points.toFixed(2)}</td>
                        <td>{row.error.toFixed(2)}</td>
                        <td>{row.salary_value_actual == null ? "-" : `${row.salary_value_actual.toFixed(2)}x`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        <section className="panel wide-panel">
          <h2>Lineup Backtests (Optimal vs Predicted)</h2>
          <p className="hint">
            Runs walk-forward lineup backtests against actual-optimal lineups. Classic and showdown are tracked
            separately.
          </p>
          <div className="backtest-grid">
            <label>
              Mode
              <select
                value={lineupBacktestMode}
                onChange={(event) => setLineupBacktestMode(event.target.value as "classic" | "showdown")}
              >
                <option value="classic">classic</option>
                <option value="showdown">showdown</option>
              </select>
            </label>
            <label>
              Candidate Lineups / Slate
              <input
                type="number"
                min={100}
                max={20000}
                step={100}
                value={lineupBacktestLineupsPerSlate}
                onChange={(event) => setLineupBacktestLineupsPerSlate(Number(event.target.value))}
              />
            </label>
            <label>
              Training Window (Slates)
              <input
                type="number"
                min={2}
                max={120}
                value={lineupBacktestTrainingWindowSlates}
                onChange={(event) => setLineupBacktestTrainingWindowSlates(Number(event.target.value))}
              />
            </label>
            <label>
              Min Training Slates
              <input
                type="number"
                min={1}
                max={80}
                value={lineupBacktestMinTrainingSlates}
                onChange={(event) => setLineupBacktestMinTrainingSlates(Number(event.target.value))}
              />
            </label>
            <label>
              Min Training Rows
              <input
                type="number"
                min={100}
                max={2000000}
                step={100}
                value={lineupBacktestMinTrainingRows}
                onChange={(event) => setLineupBacktestMinTrainingRows(Number(event.target.value))}
              />
            </label>
            <label>
              Limit Slates (0 = all)
              <input
                type="number"
                min={0}
                max={2000}
                value={lineupBacktestLimitSlates}
                onChange={(event) => setLineupBacktestLimitSlates(Number(event.target.value))}
              />
            </label>
          </div>
          <div className="button-row">
            <button onClick={runLineupBacktest} disabled={isIngesting}>
              Run {lineupBacktestMode} Lineup Backtest
            </button>
            <button
              onClick={() => {
                setLineupBacktestClassicResult(null);
                setLineupBacktestShowdownResult(null);
              }}
              disabled={isIngesting || (!lineupBacktestClassicResult && !lineupBacktestShowdownResult)}
            >
              Clear Lineup Backtest Results
            </button>
          </div>

          {lineupBacktestPanels.map(({ mode, result }) => {
            if (!result) return null;
            const topGaps = result.rows
              .filter((row) => row.status === "ok" && row.gap_points != null)
              .sort((a, b) => (b.gap_points ?? -999999) - (a.gap_points ?? -999999))
              .slice(0, 12);
            const issues = result.rows.filter((row) => row.status !== "ok");
            return (
              <div className="subsection" key={mode}>
                <h3>{mode === "classic" ? "Classic Metrics" : "Showdown Metrics"}</h3>
                <div className="button-row">
                  <button onClick={() => downloadLineupBacktestResult(mode, result)} disabled={isIngesting}>
                    Download {mode} JSON
                  </button>
                </div>
                <div className="metric-grid">
                  <div className="mini-card">
                    <span>Slates Completed</span>
                    <strong>
                      {result.slates_completed}/{result.slates_total}
                    </strong>
                  </div>
                  <div className="mini-card">
                    <span>Mean Gap</span>
                    <strong>{result.mean_gap_points == null ? "-" : result.mean_gap_points.toFixed(2)}</strong>
                  </div>
                  <div className="mini-card">
                    <span>Median Gap</span>
                    <strong>{result.median_gap_points == null ? "-" : result.median_gap_points.toFixed(2)}</strong>
                  </div>
                  <div className="mini-card">
                    <span>Best Gap</span>
                    <strong>{result.best_case_gap_points == null ? "-" : result.best_case_gap_points.toFixed(2)}</strong>
                  </div>
                  <div className="mini-card">
                    <span>Worst Gap</span>
                    <strong>{result.worst_case_gap_points == null ? "-" : result.worst_case_gap_points.toFixed(2)}</strong>
                  </div>
                  <div className="mini-card">
                    <span>Failed/Skipped</span>
                    <strong>{result.slates_failed_or_skipped}</strong>
                  </div>
                </div>

                <div className="dual-tables">
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Season</th>
                          <th>Week</th>
                          <th>Slate</th>
                          <th>Gap</th>
                          <th>Optimal</th>
                          <th>Predicted</th>
                        </tr>
                      </thead>
                      <tbody>
                        {topGaps.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="empty-row">
                              No completed rows yet.
                            </td>
                          </tr>
                        ) : (
                          topGaps.map((row) => (
                            <tr key={`${mode}-${row.season}-${row.week}-${row.slate}`}>
                              <td>{row.season}</td>
                              <td>{row.week}</td>
                              <td>{row.slate}</td>
                              <td>{row.gap_points == null ? "-" : row.gap_points.toFixed(2)}</td>
                              <td>
                                {row.optimal_actual_points == null ? "-" : row.optimal_actual_points.toFixed(2)}
                              </td>
                              <td>
                                {row.predicted_actual_points == null ? "-" : row.predicted_actual_points.toFixed(2)}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Season</th>
                          <th>Week</th>
                          <th>Slate</th>
                          <th>Status</th>
                          <th>Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {issues.length === 0 ? (
                          <tr>
                            <td colSpan={5} className="empty-row">
                              No failed or warmup rows.
                            </td>
                          </tr>
                        ) : (
                          issues.map((row) => (
                            <tr key={`${mode}-issue-${row.season}-${row.week}-${row.slate}`}>
                              <td>{row.season}</td>
                              <td>{row.week}</td>
                              <td>{row.slate}</td>
                              <td>{row.status}</td>
                              <td>{row.error_message ?? "-"}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            );
          })}
        </section>

        <section className="panel wide-panel">
          <div className="section-header">
            <h2>
              Unresolved Queue <span className="section-badge">{unresolved.length}</span>
            </h2>
            <button
              className="toggle-button"
              onClick={() => setShowUnresolvedQueue((prev) => !prev)}
              disabled={isIngesting}
            >
              {showUnresolvedQueue ? "Collapse" : "Expand"}
            </button>
          </div>
          {!showUnresolvedQueue ? (
            <p className="hint">Collapsed. Expand to review and resolve open identity matches.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Team</th>
                    <th>Pos</th>
                    <th>Source Key</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {unresolved.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="empty-row">
                        Queue is clean.
                      </td>
                    </tr>
                  ) : (
                    unresolved.map((row) => (
                      <tr key={row.unresolved_id}>
                        <td>{row.normalized_name}</td>
                        <td>{row.team ?? "-"}</td>
                        <td>{row.position ?? "-"}</td>
                        <td>{row.source_player_key ?? "-"}</td>
                        <td>
                          <div className="action-row">
                            <button onClick={() => createAndResolve(row)}>Create + Resolve</button>
                            <input
                              type="text"
                              placeholder="existing player_master_id"
                              value={resolutions[row.unresolved_id] ?? ""}
                              onChange={(event) =>
                                setResolutions((prev) => ({
                                  ...prev,
                                  [row.unresolved_id]: event.target.value,
                                }))
                              }
                            />
                            <button onClick={() => manualResolve(row)}>Manual Resolve</button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel wide-panel">
          <div className="section-header">
            <h2>
              Curated Salary Slices <span className="section-badge">{salarySlices.length}</span>
            </h2>
            <button className="toggle-button" onClick={toggleCuratedSalarySlices} disabled={isIngesting}>
              {showCuratedSalarySlices ? "Collapse" : "Expand"}
            </button>
          </div>
          {!showCuratedSalarySlices ? (
            <p className="hint">Collapsed. Expand to inspect season/week/slate coverage for curated salaries.</p>
          ) : (
            <>
              <div className="inline-controls">
                <label>
                  Season Filter (Optional)
                  <input
                    type="number"
                    placeholder="e.g. 2025"
                    value={salarySliceSeasonFilter}
                    onChange={(event) => setSalarySliceSeasonFilter(event.target.value)}
                  />
                </label>
                <button
                  onClick={() =>
                    refreshCuratedSalarySlices().catch((err) =>
                      setError(err instanceof Error ? err.message : String(err))
                    )
                  }
                  disabled={isIngesting}
                >
                  Refresh Slices
                </button>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Season</th>
                      <th>Week</th>
                      <th>Slate</th>
                      <th>Rows</th>
                    </tr>
                  </thead>
                  <tbody>
                    {salarySlices.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="empty-row">
                          No curated salary slices found for this filter/source.
                        </td>
                      </tr>
                    ) : (
                      salarySlices.map((row) => (
                        <tr key={`${row.source_system}-${row.season}-${row.week}-${row.slate}`}>
                          <td>{row.source_system}</td>
                          <td>{row.season}</td>
                          <td>{row.week}</td>
                          <td>{row.slate}</td>
                          <td>{row.rows.toLocaleString()}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        <section className="panel wide-panel">
          <div className="section-header">
            <h2>Season Coverage</h2>
            <button
              className="toggle-button"
              onClick={() => setShowSeasonCoverage((prev) => !prev)}
              disabled={isIngesting}
            >
              {showSeasonCoverage ? "Collapse" : "Expand"}
            </button>
          </div>
          {!showSeasonCoverage ? (
            <p className="hint">Collapsed. Expand for dataset-level season row counts.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Season</th>
                    <th>Rows</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="empty-row">
                        No season-level data loaded yet.
                      </td>
                    </tr>
                  ) : (
                    coverage.map((row) => (
                      <tr key={`${row.dataset}-${row.season ?? "na"}`}>
                        <td>{row.dataset}</td>
                        <td>{row.season ?? "-"}</td>
                        <td>{row.rows.toLocaleString()}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel wide-panel">
          <div className="section-header">
            <h2>Recent Runs</h2>
            <button className="toggle-button" onClick={() => setShowRecentRuns((prev) => !prev)} disabled={isIngesting}>
              {showRecentRuns ? "Collapse" : "Expand"}
            </button>
          </div>
          {!showRecentRuns ? (
            <p className="hint">Collapsed. Expand to review ingest run history.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Started</th>
                    <th>Source</th>
                    <th>Table</th>
                    <th>Status</th>
                    <th>Curated</th>
                    <th>Unresolved</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="empty-row">
                        No ingest runs yet.
                      </td>
                    </tr>
                  ) : (
                    runs.map((row) => (
                      <tr key={row.ingest_run_id}>
                        <td>{new Date(row.started_at).toLocaleString()}</td>
                        <td>{row.source_system}</td>
                        <td>{row.source_table}</td>
                        <td>{row.status}</td>
                        <td>{row.rows_curated}</td>
                        <td>{row.rows_unresolved}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
