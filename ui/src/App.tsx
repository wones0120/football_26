import { useEffect, useMemo, useState } from "react";
import {
  autoDiscoverInjuryFiles,
  autoDiscoverSalaryFiles,
  backtestWeek,
  benchmarkArtifactUrl,
  bootstrapNflreadpy,
  fetchBenchmarkRuns,
  fetchCuratedSalarySlices,
  fetchDataFreshness,
  fetchModelDefaults,
  fetchSeasonCoverage,
  fetchRuns,
  fetchUnresolved,
  fetchUnresolvedTriage,
  ingestNflreadpySchedules,
  ingestNflreadpyWeeklyStats,
  ingestInjuries,
  ingestSalaries,
  runBenchmarkSuite,
  runOptimalVsPredictedBacktest,
  resolveUnresolved,
  simulateWeek,
  upsertPlayerMaster,
  type BenchmarkRun,
  type BacktestWeekResult,
  type BootstrapMetricInterval,
  type CuratedSalarySliceRow,
  type DataFreshnessResult,
  type DataFreshnessRow,
  type IngestResult,
  type ModelDefaults,
  type OptimalVsPredictedBacktestResult,
  type SeasonCoverageRow,
  type SimulatedPlayerOutcome,
  type UnresolvedRow,
  type UnresolvedTriageResult,
} from "./api";

type ShowdownCaptainABRow = {
  season: number;
  week: number;
  slate: string;
  baseline_gap_points: number;
  captain_informed_gap_points: number;
  gap_lift_points: number;
  baseline_predicted_actual_points: number;
  captain_informed_predicted_actual_points: number;
  optimal_actual_points: number;
};

type ShowdownCaptainABSummary = {
  source_system: "draftkings" | "fanduel";
  season_start: number;
  season_end: number;
  lineups_per_slate: number;
  training_window_slates: number;
  learned_only: boolean;
  showdown_captain_model_path: string;
  showdown_captain_prior_strength: number;
  paired_slates: number;
  mean_gap_lift_points?: number | null;
  median_gap_lift_points?: number | null;
  captain_informed_win_rate?: number | null;
  baseline_gap_stddev?: number | null;
  captain_informed_gap_stddev?: number | null;
  stability_lift_stddev_reduction?: number | null;
  baseline_near_optimal_rate_90pct?: number | null;
  captain_informed_near_optimal_rate_90pct?: number | null;
  near_optimal_rate_lift_90pct?: number | null;
  baseline_mean_gap_points?: number | null;
  captain_informed_mean_gap_points?: number | null;
};

type ShowdownCaptainABResult = {
  generated_at: string;
  summary: ShowdownCaptainABSummary;
  baseline: OptimalVsPredictedBacktestResult;
  captain_informed: OptimalVsPredictedBacktestResult;
  paired_rows: ShowdownCaptainABRow[];
};

const FALLBACK_MODEL_DEFAULTS: ModelDefaults = {
  showdown_captain_model_path: "docs/showdown_captain_model_2024_2025.json",
  showdown_captain_prior_strength: 0.35,
  classic_value_driver_model_path: "docs/main_slate_value_driver_analysis_2024_2025.json",
  classic_value_driver_prior_strength: 0.45,
  matchup_outcome_model_path: "docs/matchup_outcome_intelligence_2024_2025.json",
  matchup_outcome_prior_strength: 0.15,
  matchup_prior_gate_model_path: "docs/matchup_prior_gate_20slates_5000.json",
};

const FRESHNESS_LABELS: Record<DataFreshnessRow["dataset"], string> = {
  salaries: "Salaries",
  injuries: "Injuries",
  schedules: "Schedules",
  weekly_stats: "Weekly Stats",
};

function formatMetric(value?: number | null, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return value.toFixed(digits);
}

function formatRate(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function formatBootstrapInterval(
  interval?: BootstrapMetricInterval | null,
  asRate = false
): string | null {
  if (!interval) return null;
  const level = `${(interval.confidence_level * 100).toFixed(0)}% CI`;
  const lower = asRate ? formatRate(interval.lower) : formatMetric(interval.lower);
  const upper = asRate ? formatRate(interval.upper) : formatMetric(interval.upper);
  return `${level} ${lower}–${upper} · SE ${formatMetric(interval.standard_error)}`;
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function findArtifact(run: BenchmarkRun | null, name: string) {
  return run?.artifacts.find((artifact) => artifact.name === name) ?? null;
}

function runLabel(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function hasBenchmarkMetrics(run: BenchmarkRun): boolean {
  return (
    run.status === "ok" &&
    [
      run.metrics.classic_mean_gap_points,
      run.metrics.showdown_mean_gap_points,
      run.metrics.captain_informed_win_rate,
    ].every((value) => value != null && Number.isFinite(value))
  );
}

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
  const [lineupBacktestShowdownCaptainModelPath, setLineupBacktestShowdownCaptainModelPath] = useState(
    FALLBACK_MODEL_DEFAULTS.showdown_captain_model_path
  );
  const [lineupBacktestShowdownCaptainPriorStrength, setLineupBacktestShowdownCaptainPriorStrength] =
    useState(FALLBACK_MODEL_DEFAULTS.showdown_captain_prior_strength);
  const [lineupBacktestClassicValueModelPath, setLineupBacktestClassicValueModelPath] = useState(
    FALLBACK_MODEL_DEFAULTS.classic_value_driver_model_path
  );
  const [lineupBacktestClassicValuePriorStrength, setLineupBacktestClassicValuePriorStrength] = useState(
    FALLBACK_MODEL_DEFAULTS.classic_value_driver_prior_strength
  );
  const [lineupBacktestMatchupOutcomeModelPath, setLineupBacktestMatchupOutcomeModelPath] = useState(
    FALLBACK_MODEL_DEFAULTS.matchup_outcome_model_path
  );
  const [lineupBacktestMatchupOutcomePriorStrength, setLineupBacktestMatchupOutcomePriorStrength] =
    useState(FALLBACK_MODEL_DEFAULTS.matchup_outcome_prior_strength);
  const [lineupBacktestMatchupPriorGateModelPath, setLineupBacktestMatchupPriorGateModelPath] =
    useState(FALLBACK_MODEL_DEFAULTS.matchup_prior_gate_model_path);
  const [simulationRows, setSimulationRows] = useState<SimulatedPlayerOutcome[]>([]);
  const [simulationRunId, setSimulationRunId] = useState<string | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestWeekResult | null>(null);
  const [lineupBacktestClassicResult, setLineupBacktestClassicResult] =
    useState<OptimalVsPredictedBacktestResult | null>(null);
  const [lineupBacktestShowdownResult, setLineupBacktestShowdownResult] =
    useState<OptimalVsPredictedBacktestResult | null>(null);
  const [lineupBacktestShowdownABResult, setLineupBacktestShowdownABResult] =
    useState<ShowdownCaptainABResult | null>(null);
  const [runs, setRuns] = useState<IngestResult[]>([]);
  const [coverage, setCoverage] = useState<SeasonCoverageRow[]>([]);
  const [salarySlices, setSalarySlices] = useState<CuratedSalarySliceRow[]>([]);
  const [dataFreshness, setDataFreshness] = useState<DataFreshnessResult | null>(null);
  const [salarySliceSeasonFilter, setSalarySliceSeasonFilter] = useState("");
  const [showUnresolvedQueue, setShowUnresolvedQueue] = useState(false);
  const [showSeasonCoverage, setShowSeasonCoverage] = useState(false);
  const [showCuratedSalarySlices, setShowCuratedSalarySlices] = useState(false);
  const [showRecentRuns, setShowRecentRuns] = useState(false);
  const [unresolved, setUnresolved] = useState<UnresolvedRow[]>([]);
  const [unresolvedTriage, setUnresolvedTriage] = useState<UnresolvedTriageResult | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});
  const [modelDefaults, setModelDefaults] = useState<ModelDefaults>(FALLBACK_MODEL_DEFAULTS);
  const [benchmarkRuns, setBenchmarkRuns] = useState<BenchmarkRun[]>([]);
  const [showBenchmarkRuns, setShowBenchmarkRuns] = useState(true);
  const [benchmarkLimitSlates, setBenchmarkLimitSlates] = useState(0);
  const [benchmarkClassicLineupsPerSlate, setBenchmarkClassicLineupsPerSlate] = useState(1000);
  const [benchmarkShowdownLineupsPerSlate, setBenchmarkShowdownLineupsPerSlate] = useState(1000);
  const [benchmarkShowdownAbLineupsPerSlate, setBenchmarkShowdownAbLineupsPerSlate] = useState(2500);
  const [benchmarkLastRun, setBenchmarkLastRun] = useState<BenchmarkRun | null>(null);

  const unresolvedCount = unresolvedTriage?.open_total ?? unresolved.length;
  const newUnresolvedCount = unresolvedTriage?.new_total ?? 0;
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
  const latestBenchmarkRun = benchmarkLastRun ?? benchmarkRuns[0] ?? null;
  const classicGapInterval = formatBootstrapInterval(
    latestBenchmarkRun?.metrics.classic_mean_gap_interval
  );
  const showdownGapInterval = formatBootstrapInterval(
    latestBenchmarkRun?.metrics.showdown_mean_gap_interval
  );
  const captainWinRateInterval = formatBootstrapInterval(
    latestBenchmarkRun?.metrics.captain_win_rate_interval,
    true
  );

  const applyModelDefaults = (defaults: ModelDefaults) => {
    setLineupBacktestShowdownCaptainModelPath(defaults.showdown_captain_model_path);
    setLineupBacktestShowdownCaptainPriorStrength(defaults.showdown_captain_prior_strength);
    setLineupBacktestClassicValueModelPath(defaults.classic_value_driver_model_path);
    setLineupBacktestClassicValuePriorStrength(defaults.classic_value_driver_prior_strength);
    setLineupBacktestMatchupOutcomeModelPath(defaults.matchup_outcome_model_path);
    setLineupBacktestMatchupOutcomePriorStrength(defaults.matchup_outcome_prior_strength);
    setLineupBacktestMatchupPriorGateModelPath(defaults.matchup_prior_gate_model_path);
  };

  const refreshOperationalData = async () => {
    const [runsResp, unresolvedResp, triageResp, coverageResp] = await Promise.all([
      fetchRuns(),
      fetchUnresolved(),
      fetchUnresolvedTriage(24),
      fetchSeasonCoverage(),
    ]);
    setRuns(runsResp.rows);
    setUnresolved(unresolvedResp.rows);
    setUnresolvedTriage(triageResp);
    setCoverage(coverageResp.rows);
  };

  const refreshDataFreshness = async () => {
    const response = await fetchDataFreshness({
      source_system: sourceSystem,
      season,
      week,
      slate,
    });
    setDataFreshness(response);
  };

  const refresh = async () => {
    await Promise.all([refreshOperationalData(), refreshDataFreshness()]);
  };

  const refreshBenchmarkRuns = async () => {
    const response = await fetchBenchmarkRuns(10);
    setBenchmarkRuns(response.rows);
    setBenchmarkLastRun(
      (current) =>
        (current && hasBenchmarkMetrics(current) ? current : null) ??
        response.rows.find(hasBenchmarkMetrics) ??
        response.rows.find((run) => run.status === "ok") ??
        response.rows[0] ??
        null
    );
  };

  const refreshModelDefaults = async () => {
    const defaults = await fetchModelDefaults();
    setModelDefaults(defaults);
    applyModelDefaults(defaults);
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
    Promise.all([refreshOperationalData(), refreshModelDefaults(), refreshBenchmarkRuns()]).catch(
      (err) =>
        setError(err instanceof Error ? err.message : String(err))
    );
  }, []);

  useEffect(() => {
    let cancelled = false;
    setDataFreshness(null);
    fetchDataFreshness({
      source_system: sourceSystem,
      season,
      week,
      slate,
    })
      .then((response) => {
        if (!cancelled) setDataFreshness(response);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [sourceSystem, season, week, slate]);

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
      const shouldUseCaptainPrior =
        lineupBacktestMode === "showdown" &&
        lineupBacktestShowdownCaptainPriorStrength > 0 &&
        lineupBacktestShowdownCaptainModelPath.trim().length > 0;
      const shouldUseClassicPrior =
        lineupBacktestMode === "classic" &&
        lineupBacktestClassicValuePriorStrength > 0 &&
        lineupBacktestClassicValueModelPath.trim().length > 0;
      const shouldUseMatchupPrior =
        lineupBacktestMode === "classic" &&
        lineupBacktestMatchupOutcomePriorStrength > 0 &&
        lineupBacktestMatchupOutcomeModelPath.trim().length > 0;
      const shouldUseMatchupGate =
        shouldUseMatchupPrior && lineupBacktestMatchupPriorGateModelPath.trim().length > 0;
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
        showdown_captain_model_path: shouldUseCaptainPrior
          ? lineupBacktestShowdownCaptainModelPath.trim()
          : null,
        showdown_captain_prior_strength: shouldUseCaptainPrior
          ? lineupBacktestShowdownCaptainPriorStrength
          : 0,
        classic_value_driver_model_path: shouldUseClassicPrior
          ? lineupBacktestClassicValueModelPath.trim()
          : null,
        classic_value_driver_prior_strength: shouldUseClassicPrior
          ? lineupBacktestClassicValuePriorStrength
          : 0,
        matchup_outcome_model_path: shouldUseMatchupPrior
          ? lineupBacktestMatchupOutcomeModelPath.trim()
          : null,
        matchup_outcome_prior_strength: shouldUseMatchupPrior
          ? lineupBacktestMatchupOutcomePriorStrength
          : 0,
        matchup_prior_gate_model_path: shouldUseMatchupGate
          ? lineupBacktestMatchupPriorGateModelPath.trim()
          : null,
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

  const runShowdownCaptainAB = async () => {
    const seasonStart = Math.min(historyStartSeason, historyEndSeason);
    const seasonEnd = Math.max(historyStartSeason, historyEndSeason);
    const modelPath = lineupBacktestShowdownCaptainModelPath.trim();
    const priorStrength = Math.min(1, Math.max(0, lineupBacktestShowdownCaptainPriorStrength));
    if (modelPath.length === 0) {
      setError("Showdown captain model path is required for A/B runs");
      return;
    }
    setIsIngesting(true);
    setError(null);
    setStatus(
      `Running showdown captain A/B for ${sourceSystem} seasons ${seasonStart}-${seasonEnd}...`
    );
    try {
      const baseline = await runOptimalVsPredictedBacktest({
        source_system: sourceSystem,
        season_start: seasonStart,
        season_end: seasonEnd,
        slate_type: "showdown",
        lineups_per_slate: lineupBacktestLineupsPerSlate,
        training_window_slates: lineupBacktestTrainingWindowSlates,
        min_training_slates: lineupBacktestMinTrainingSlates,
        min_training_rows: lineupBacktestMinTrainingRows,
        learned_only: true,
        limit_slates: lineupBacktestLimitSlates,
        showdown_captain_model_path: null,
        showdown_captain_prior_strength: 0,
      });
      const captainInformed = await runOptimalVsPredictedBacktest({
        source_system: sourceSystem,
        season_start: seasonStart,
        season_end: seasonEnd,
        slate_type: "showdown",
        lineups_per_slate: lineupBacktestLineupsPerSlate,
        training_window_slates: lineupBacktestTrainingWindowSlates,
        min_training_slates: lineupBacktestMinTrainingSlates,
        min_training_rows: lineupBacktestMinTrainingRows,
        learned_only: true,
        limit_slates: lineupBacktestLimitSlates,
        showdown_captain_model_path: modelPath,
        showdown_captain_prior_strength: priorStrength,
      });

      const baselineByKey = new Map(
        baseline.rows
          .filter((row) => row.status === "ok" && row.gap_points != null)
          .map((row) => [`${row.season}-${row.week}-${row.slate}`, row] as const)
      );
      const captainByKey = new Map(
        captainInformed.rows
          .filter((row) => row.status === "ok" && row.gap_points != null)
          .map((row) => [`${row.season}-${row.week}-${row.slate}`, row] as const)
      );

      const pairedRows: ShowdownCaptainABRow[] = [];
      for (const [key, baselineRow] of baselineByKey.entries()) {
        const informedRow = captainByKey.get(key);
        if (!informedRow) continue;
        pairedRows.push({
          season: baselineRow.season,
          week: baselineRow.week,
          slate: baselineRow.slate,
          baseline_gap_points: Number(baselineRow.gap_points ?? 0),
          captain_informed_gap_points: Number(informedRow.gap_points ?? 0),
          gap_lift_points: Number(baselineRow.gap_points ?? 0) - Number(informedRow.gap_points ?? 0),
          baseline_predicted_actual_points: Number(baselineRow.predicted_actual_points ?? 0),
          captain_informed_predicted_actual_points: Number(informedRow.predicted_actual_points ?? 0),
          optimal_actual_points: Number(baselineRow.optimal_actual_points ?? 0),
        });
      }

      const gapLifts = pairedRows.map((row) => row.gap_lift_points);
      const mean = (values: number[]) =>
        values.length === 0 ? null : values.reduce((acc, value) => acc + value, 0) / values.length;
      const median = (values: number[]) => {
        if (values.length === 0) return null;
        const sorted = [...values].sort((a, b) => a - b);
        const middle = Math.floor(sorted.length / 2);
        return sorted.length % 2 === 0
          ? (sorted[middle - 1] + sorted[middle]) / 2
          : sorted[middle];
      };
      const stddev = (values: number[]) => {
        if (values.length === 0) return null;
        const mu = mean(values);
        if (mu == null) return null;
        const variance = values.reduce((acc, value) => acc + (value - mu) ** 2, 0) / values.length;
        return Math.sqrt(variance);
      };
      const nearOptimalRate = (
        rows: OptimalVsPredictedBacktestResult["rows"],
        thresholdRatio: number
      ) => {
        const okRows = rows.filter((row) => row.status === "ok");
        if (okRows.length === 0) return null;
        const hits = okRows.filter((row) => {
          const optimal = Number(row.optimal_actual_points ?? 0);
          const predicted = Number(row.predicted_actual_points ?? 0);
          if (optimal <= 0) return false;
          return predicted / optimal >= thresholdRatio;
        }).length;
        return hits / okRows.length;
      };

      const baselineGaps = baseline.rows
        .filter((row) => row.status === "ok" && row.gap_points != null)
        .map((row) => Number(row.gap_points));
      const informedGaps = captainInformed.rows
        .filter((row) => row.status === "ok" && row.gap_points != null)
        .map((row) => Number(row.gap_points));
      const baselineStd = stddev(baselineGaps);
      const informedStd = stddev(informedGaps);
      const baselineNearOptimal = nearOptimalRate(baseline.rows, 0.9);
      const informedNearOptimal = nearOptimalRate(captainInformed.rows, 0.9);
      const summary: ShowdownCaptainABSummary = {
        source_system: sourceSystem,
        season_start: seasonStart,
        season_end: seasonEnd,
        lineups_per_slate: lineupBacktestLineupsPerSlate,
        training_window_slates: lineupBacktestTrainingWindowSlates,
        learned_only: true,
        showdown_captain_model_path: modelPath,
        showdown_captain_prior_strength: priorStrength,
        paired_slates: pairedRows.length,
        mean_gap_lift_points: mean(gapLifts),
        median_gap_lift_points: median(gapLifts),
        captain_informed_win_rate:
          pairedRows.length === 0
            ? null
            : pairedRows.filter((row) => row.gap_lift_points > 0).length / pairedRows.length,
        baseline_gap_stddev: baselineStd,
        captain_informed_gap_stddev: informedStd,
        stability_lift_stddev_reduction:
          baselineStd == null || informedStd == null ? null : baselineStd - informedStd,
        baseline_near_optimal_rate_90pct: baselineNearOptimal,
        captain_informed_near_optimal_rate_90pct: informedNearOptimal,
        near_optimal_rate_lift_90pct:
          baselineNearOptimal == null || informedNearOptimal == null
            ? null
            : informedNearOptimal - baselineNearOptimal,
        baseline_mean_gap_points: baseline.mean_gap_points,
        captain_informed_mean_gap_points: captainInformed.mean_gap_points,
      };
      setLineupBacktestShowdownResult(captainInformed);
      setLineupBacktestShowdownABResult({
        generated_at: new Date().toISOString(),
        summary,
        baseline,
        captain_informed: captainInformed,
        paired_rows: pairedRows,
      });
      const meanLiftText =
        summary.mean_gap_lift_points == null ? "n/a" : summary.mean_gap_lift_points.toFixed(2);
      setStatus(
        `Showdown captain A/B completed: paired_slates=${summary.paired_slates} mean_gap_lift=${meanLiftText}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const runBenchmarkSuiteFromUi = async () => {
    const seasonStart = Math.min(historyStartSeason, historyEndSeason);
    const seasonEnd = Math.max(historyStartSeason, historyEndSeason);
    const captainModelPath =
      lineupBacktestShowdownCaptainModelPath.trim() || modelDefaults.showdown_captain_model_path;
    setIsIngesting(true);
    setError(null);
    setStatus(`Running benchmark suite for ${sourceSystem} seasons ${seasonStart}-${seasonEnd}...`);
    try {
      const result = await runBenchmarkSuite({
        source_system: sourceSystem,
        season_start: seasonStart,
        season_end: seasonEnd,
        lineups_per_slate_classic: benchmarkClassicLineupsPerSlate,
        lineups_per_slate_showdown: benchmarkShowdownLineupsPerSlate,
        lineups_per_slate_showdown_ab: benchmarkShowdownAbLineupsPerSlate,
        limit_slates: benchmarkLimitSlates,
        analysis_limit_slates: benchmarkLimitSlates,
        quiet_progress: true,
        showdown_captain_model_path: captainModelPath,
        showdown_captain_prior_strength: lineupBacktestShowdownCaptainPriorStrength,
      });
      if (result.status !== "ok" || !result.run) {
        throw new Error(result.error_message || "Benchmark suite failed");
      }
      setBenchmarkLastRun(result.run);
      await refreshBenchmarkRuns();
      setStatus(`Benchmark suite completed: ${result.run.run_directory}`);
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
        showdown_captain_model_path: result.showdown_captain_model_path ?? null,
        showdown_captain_prior_strength: result.showdown_captain_prior_strength ?? 0,
        classic_value_driver_model_path: result.classic_value_driver_model_path ?? null,
        classic_value_driver_prior_strength: result.classic_value_driver_prior_strength ?? 0,
        matchup_outcome_model_path: result.matchup_outcome_model_path ?? null,
        matchup_outcome_prior_strength: result.matchup_outcome_prior_strength ?? 0,
        matchup_prior_gate_model_path: result.matchup_prior_gate_model_path ?? null,
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

  const downloadShowdownCaptainABResult = (result: ShowdownCaptainABResult) => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    a.href = url;
    a.download = `showdown_captain_ab_${result.summary.season_start}_${result.summary.season_end}_${stamp}.json`;
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
          <div className="stat-card">
            <span>New Unresolved (24h)</span>
            <strong>{newUnresolvedCount}</strong>
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

          <div className="subsection freshness-section">
            <div className="section-header">
              <h3>Data Freshness</h3>
              {dataFreshness && (
                <span className="freshness-context">
                  {dataFreshness.season} W{dataFreshness.week} · {dataFreshness.slate}
                </span>
              )}
            </div>
            <p className="hint">
              Exact selected slice. Schedule and weekly-stat checks use nflreadpy season/week data.
            </p>
            {dataFreshness ? (
              <div className="freshness-grid">
                {dataFreshness.rows.map((row) => (
                  <article
                    className={`freshness-card freshness-card-${row.status}`}
                    key={row.dataset}
                  >
                    <div className="freshness-card-header">
                      <strong>{FRESHNESS_LABELS[row.dataset]}</strong>
                      <span className={`freshness-status freshness-status-${row.status}`}>
                        {row.status}
                      </span>
                    </div>
                    <span className="freshness-source">{row.source_system}</span>
                    <div className="freshness-count">
                      <strong>{row.rows.toLocaleString()}</strong>
                      <span>rows</span>
                    </div>
                    <p>
                      {row.latest_loaded_at && row.age_hours != null
                        ? `${row.age_hours.toFixed(1)}h old · ${formatDateTime(row.latest_loaded_at)}`
                        : "No rows loaded for this slice"}
                    </p>
                    <small>Stale after {row.stale_after_hours}h</small>
                  </article>
                ))}
              </div>
            ) : (
              <p className="hint">Checking selected slice...</p>
            )}
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
          <div className="subsection">
            <div className="section-header">
              <h3>Current Model Card</h3>
              <button
                className="toggle-button"
                onClick={() => applyModelDefaults(modelDefaults)}
                disabled={isIngesting}
              >
                Reset To Defaults
              </button>
            </div>
            <div className="metric-grid model-card-grid">
              <div className="mini-card">
                <span>Source / Range</span>
                <strong>
                  {sourceSystem} {Math.min(historyStartSeason, historyEndSeason)}-{Math.max(historyStartSeason, historyEndSeason)}
                </strong>
              </div>
              <div className="mini-card">
                <span>Classic Mean / Median Gap</span>
                <strong>
                  {formatMetric(latestBenchmarkRun?.metrics.classic_mean_gap_points)} /{" "}
                  {formatMetric(latestBenchmarkRun?.metrics.classic_median_gap_points)}
                </strong>
                {classicGapInterval && <small>{classicGapInterval}</small>}
              </div>
              <div className="mini-card">
                <span>Showdown Mean / Median Gap</span>
                <strong>
                  {formatMetric(latestBenchmarkRun?.metrics.showdown_mean_gap_points)} /{" "}
                  {formatMetric(latestBenchmarkRun?.metrics.showdown_median_gap_points)}
                </strong>
                {showdownGapInterval && <small>{showdownGapInterval}</small>}
              </div>
              <div className="mini-card">
                <span>Captain Win Rate / Lift</span>
                <strong>
                  {formatRate(latestBenchmarkRun?.metrics.captain_informed_win_rate)} /{" "}
                  {formatMetric(latestBenchmarkRun?.metrics.captain_mean_gap_lift_points)}
                </strong>
                {captainWinRateInterval && <small>{captainWinRateInterval}</small>}
              </div>
            </div>
            <div className="info-grid">
              <div className="info-card">
                <span>Showdown Captain Default</span>
                <code>{lineupBacktestShowdownCaptainModelPath || "-"}</code>
                <strong>strength={lineupBacktestShowdownCaptainPriorStrength.toFixed(2)}</strong>
              </div>
              <div className="info-card">
                <span>Classic Value Default</span>
                <code>{lineupBacktestClassicValueModelPath || "-"}</code>
                <strong>strength={lineupBacktestClassicValuePriorStrength.toFixed(2)}</strong>
              </div>
              <div className="info-card">
                <span>Matchup Default</span>
                <code>{lineupBacktestMatchupOutcomeModelPath || "-"}</code>
                <strong>strength={lineupBacktestMatchupOutcomePriorStrength.toFixed(2)}</strong>
              </div>
              <div className="info-card">
                <span>Matchup Gate Default</span>
                <code>{lineupBacktestMatchupPriorGateModelPath || "-"}</code>
                <strong>{latestBenchmarkRun?.status ?? "no benchmark run"}</strong>
              </div>
            </div>
            <p className="hint">
              Latest successful benchmark with metrics: {latestBenchmarkRun?.run_directory ?? "none"}
            </p>
            <div className="artifact-list">
              {[findArtifact(latestBenchmarkRun, "summary.md"), findArtifact(latestBenchmarkRun, "delta_vs_previous.md"), findArtifact(latestBenchmarkRun, "run.log")]
                .flatMap((artifact) => (artifact ? [artifact] : []))
                .map((artifact) => (
                  <div className="artifact-pill" key={artifact.name}>
                    <span>{artifact.name}</span>
                    {artifact.exists && artifact.download_url ? (
                      <a
                        href={benchmarkArtifactUrl(artifact.download_url)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <code>{artifact.path}</code>
                      </a>
                    ) : (
                      <code>{`${artifact.path} (missing)`}</code>
                    )}
                  </div>
                ))}
            </div>
          </div>

          <div className="subsection">
            <div className="section-header">
              <h3>Benchmark Suite</h3>
              <button
                className="toggle-button"
                onClick={() => setShowBenchmarkRuns((prev) => !prev)}
                disabled={isIngesting}
              >
                {showBenchmarkRuns ? "Collapse Runs" : "Expand Runs"}
              </button>
            </div>
            <p className="hint">
              Runs the canonical benchmark stack and records artifacts under `docs/benchmarks`.
            </p>
            <div className="backtest-grid">
              <label>
                Limit Slates (0 = all)
                <input
                  type="number"
                  min={0}
                  max={2000}
                  value={benchmarkLimitSlates}
                  onChange={(event) => setBenchmarkLimitSlates(Number(event.target.value))}
                />
              </label>
              <label>
                Classic Lineups / Slate
                <input
                  type="number"
                  min={100}
                  max={20000}
                  step={100}
                  value={benchmarkClassicLineupsPerSlate}
                  onChange={(event) => setBenchmarkClassicLineupsPerSlate(Number(event.target.value))}
                />
              </label>
              <label>
                Showdown Lineups / Slate
                <input
                  type="number"
                  min={100}
                  max={20000}
                  step={100}
                  value={benchmarkShowdownLineupsPerSlate}
                  onChange={(event) => setBenchmarkShowdownLineupsPerSlate(Number(event.target.value))}
                />
              </label>
              <label>
                Showdown A/B Lineups / Slate
                <input
                  type="number"
                  min={100}
                  max={20000}
                  step={100}
                  value={benchmarkShowdownAbLineupsPerSlate}
                  onChange={(event) => setBenchmarkShowdownAbLineupsPerSlate(Number(event.target.value))}
                />
              </label>
            </div>
            <div className="button-row">
              <button onClick={runBenchmarkSuiteFromUi} disabled={isIngesting}>
                Run Benchmark Suite
              </button>
              <button
                onClick={() =>
                  refreshBenchmarkRuns().catch((err) =>
                    setError(err instanceof Error ? err.message : String(err))
                  )
                }
                disabled={isIngesting}
              >
                Refresh Benchmark Runs
              </button>
            </div>

            {showBenchmarkRuns && (
              <div className="table-wrap benchmark-table">
                <table>
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Status</th>
                      <th>Classic Mean</th>
                      <th>Showdown Mean</th>
                      <th>Captain Win Rate</th>
                      <th>Artifacts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {benchmarkRuns.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="empty-row">
                          No benchmark runs found.
                        </td>
                      </tr>
                    ) : (
                      benchmarkRuns.map((run) => (
                        <tr key={run.run_directory}>
                          <td>
                            <div className="run-cell">
                              <strong>{runLabel(run.run_directory)}</strong>
                              <code>{run.run_directory}</code>
                            </div>
                          </td>
                          <td>{run.status}</td>
                          <td>{formatMetric(run.metrics.classic_mean_gap_points)}</td>
                          <td>{formatMetric(run.metrics.showdown_mean_gap_points)}</td>
                          <td>{formatRate(run.metrics.captain_informed_win_rate)}</td>
                          <td>
                            <div className="artifact-links">
                              {run.artifacts
                                .filter((artifact) =>
                                  ["summary.md", "delta_vs_previous.md", "run.log"].includes(artifact.name)
                                )
                                .map((artifact) => (
                                  artifact.exists && artifact.download_url ? (
                                    <a
                                      href={benchmarkArtifactUrl(artifact.download_url)}
                                      key={`${run.run_directory}-${artifact.name}`}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      <code>{artifact.name}</code>
                                    </a>
                                  ) : (
                                    <code key={`${run.run_directory}-${artifact.name}`}>
                                      {artifact.name} missing
                                    </code>
                                  )
                                ))}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>

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
            {lineupBacktestMode === "showdown" && (
              <>
                <label>
                  Captain Model Path
                  <input
                    type="text"
                    value={lineupBacktestShowdownCaptainModelPath}
                    onChange={(event) => setLineupBacktestShowdownCaptainModelPath(event.target.value)}
                  />
                </label>
                <label>
                  Captain Prior Strength
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={lineupBacktestShowdownCaptainPriorStrength}
                    onChange={(event) =>
                      setLineupBacktestShowdownCaptainPriorStrength(Number(event.target.value))
                    }
                  />
                </label>
              </>
            )}
            {lineupBacktestMode === "classic" && (
              <>
                <label>
                  Classic Value Model Path
                  <input
                    type="text"
                    value={lineupBacktestClassicValueModelPath}
                    onChange={(event) => setLineupBacktestClassicValueModelPath(event.target.value)}
                  />
                </label>
                <label>
                  Classic Prior Strength
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={lineupBacktestClassicValuePriorStrength}
                    onChange={(event) =>
                      setLineupBacktestClassicValuePriorStrength(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  Matchup Outcome Model Path
                  <input
                    type="text"
                    value={lineupBacktestMatchupOutcomeModelPath}
                    onChange={(event) => setLineupBacktestMatchupOutcomeModelPath(event.target.value)}
                  />
                </label>
                <label>
                  Matchup Prior Strength
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={lineupBacktestMatchupOutcomePriorStrength}
                    onChange={(event) =>
                      setLineupBacktestMatchupOutcomePriorStrength(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  Matchup Gate Model Path
                  <input
                    type="text"
                    value={lineupBacktestMatchupPriorGateModelPath}
                    onChange={(event) => setLineupBacktestMatchupPriorGateModelPath(event.target.value)}
                  />
                </label>
              </>
            )}
          </div>
          <div className="button-row">
            <button onClick={runLineupBacktest} disabled={isIngesting}>
              Run {lineupBacktestMode} Lineup Backtest
            </button>
            <button onClick={runShowdownCaptainAB} disabled={isIngesting || lineupBacktestMode !== "showdown"}>
              Run Showdown Captain A/B
            </button>
            <button
              onClick={() => {
                setLineupBacktestClassicResult(null);
                setLineupBacktestShowdownResult(null);
                setLineupBacktestShowdownABResult(null);
              }}
              disabled={
                isIngesting ||
                (!lineupBacktestClassicResult &&
                  !lineupBacktestShowdownResult &&
                  !lineupBacktestShowdownABResult)
              }
            >
              Clear Lineup Backtest Results
            </button>
          </div>

          {lineupBacktestShowdownABResult && (
            <div className="subsection">
              <h3>Showdown Captain A/B Metrics</h3>
              <div className="button-row">
                <button onClick={() => downloadShowdownCaptainABResult(lineupBacktestShowdownABResult)} disabled={isIngesting}>
                  Download showdown A/B JSON
                </button>
              </div>
              <div className="metric-grid">
                <div className="mini-card">
                  <span>Paired Slates</span>
                  <strong>{lineupBacktestShowdownABResult.summary.paired_slates}</strong>
                </div>
                <div className="mini-card">
                  <span>Mean Gap Lift</span>
                  <strong>
                    {lineupBacktestShowdownABResult.summary.mean_gap_lift_points == null
                      ? "-"
                      : lineupBacktestShowdownABResult.summary.mean_gap_lift_points.toFixed(2)}
                  </strong>
                </div>
                <div className="mini-card">
                  <span>Median Gap Lift</span>
                  <strong>
                    {lineupBacktestShowdownABResult.summary.median_gap_lift_points == null
                      ? "-"
                      : lineupBacktestShowdownABResult.summary.median_gap_lift_points.toFixed(2)}
                  </strong>
                </div>
                <div className="mini-card">
                  <span>Captain Win Rate</span>
                  <strong>
                    {lineupBacktestShowdownABResult.summary.captain_informed_win_rate == null
                      ? "-"
                      : `${(lineupBacktestShowdownABResult.summary.captain_informed_win_rate * 100).toFixed(1)}%`}
                  </strong>
                </div>
                <div className="mini-card">
                  <span>Baseline Mean Gap</span>
                  <strong>
                    {lineupBacktestShowdownABResult.summary.baseline_mean_gap_points == null
                      ? "-"
                      : lineupBacktestShowdownABResult.summary.baseline_mean_gap_points.toFixed(2)}
                  </strong>
                </div>
                <div className="mini-card">
                  <span>Captain Mean Gap</span>
                  <strong>
                    {lineupBacktestShowdownABResult.summary.captain_informed_mean_gap_points == null
                      ? "-"
                      : lineupBacktestShowdownABResult.summary.captain_informed_mean_gap_points.toFixed(2)}
                  </strong>
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Season</th>
                      <th>Week</th>
                      <th>Slate</th>
                      <th>Gap Lift</th>
                      <th>Baseline Gap</th>
                      <th>Captain Gap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lineupBacktestShowdownABResult.paired_rows.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="empty-row">
                          No paired showdown rows yet.
                        </td>
                      </tr>
                    ) : (
                      [...lineupBacktestShowdownABResult.paired_rows]
                        .sort((a, b) => b.gap_lift_points - a.gap_lift_points)
                        .slice(0, 12)
                        .map((row) => (
                          <tr key={`ab-${row.season}-${row.week}-${row.slate}`}>
                            <td>{row.season}</td>
                            <td>{row.week}</td>
                            <td>{row.slate}</td>
                            <td>{row.gap_lift_points.toFixed(2)}</td>
                            <td>{row.baseline_gap_points.toFixed(2)}</td>
                            <td>{row.captain_informed_gap_points.toFixed(2)}</td>
                          </tr>
                        ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

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
              Unresolved Queue <span className="section-badge">{unresolvedCount}</span>
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
            <p className="hint">
              Collapsed. {newUnresolvedCount} new in the last 24 hours across{" "}
              {unresolvedTriage?.groups_returned ?? 0} source/week/slate groups.
            </p>
          ) : (
            <>
              <div className="metric-grid">
                <div className="mini-card">
                  <span>Open Total</span>
                  <strong>{unresolvedCount}</strong>
                </div>
                <div className="mini-card">
                  <span>New in 24h</span>
                  <strong>{newUnresolvedCount}</strong>
                </div>
                <div className="mini-card">
                  <span>Groups Shown</span>
                  <strong>{unresolvedTriage?.groups_returned ?? 0}</strong>
                </div>
              </div>

              <div className="subsection">
                <h3>Automated Triage by Source / Week / Slate</h3>
                <p className="hint">
                  Open identity failures are grouped automatically; newest and highest-volume groups appear first.
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Source</th>
                        <th>Table</th>
                        <th>Season</th>
                        <th>Week</th>
                        <th>Slate</th>
                        <th>New 24h</th>
                        <th>Open</th>
                        <th>Newest</th>
                      </tr>
                    </thead>
                    <tbody>
                      {!unresolvedTriage || unresolvedTriage.rows.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="empty-row">
                            No open unresolved groups.
                          </td>
                        </tr>
                      ) : (
                        unresolvedTriage.rows.map((row) => (
                          <tr
                            key={[
                              row.source_system,
                              row.source_table,
                              row.season ?? "none",
                              row.week ?? "none",
                              row.slate ?? "none",
                            ].join("-")}
                          >
                            <td>{row.source_system}</td>
                            <td>{row.source_table}</td>
                            <td>{row.season ?? "-"}</td>
                            <td>{row.week ?? "-"}</td>
                            <td>{row.slate ?? "-"}</td>
                            <td>{row.new_count}</td>
                            <td>{row.open_count}</td>
                            <td>{formatDateTime(row.newest_created_at)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="subsection">
                <h3>Detailed Repair Queue</h3>
                <p className="hint">
                  Showing the newest {unresolved.length} open records for create-or-link resolution.
                </p>
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
              </div>
            </>
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
