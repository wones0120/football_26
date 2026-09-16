import { OptimizerControlComparison } from "./OptimizerControlComparison";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { AppShell, type ViewMode } from "./AppShell";
import { DailyNewsBrief } from "./DailyNewsBrief";
import { ContestWorkflow } from "./ContestWorkflow";
import { DesignPreview } from "./DesignPreview";
import { DigitalTwin } from "./DigitalTwin";
import { ModelWorkbench } from "./ModelWorkbench";
import { ResearchWorkspace } from "./ResearchWorkspace";
import { WarRoom } from "./WarRoom";
import {
  DEFAULT_SLATE,
  SLATE_OPTIONS,
  normalizeSlateId,
  slateContextKey,
  updateRunSelection,
  type PersistedRunSelection,
  type PersistedRunSelections,
} from "./workspaceContext";
import {
  CLASSIC_CONTEST_STRATEGIES,
  CLASSIC_LARGE_GPP_STRATEGY_ID,
  SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
  SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID,
  SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID,
  optimizerStrategyId,
  type ClassicContestStrategyId,
} from "./optimizerStrategy";
import {
  contextReadinessLabel,
  individualCeilingSummary,
} from "./optimizerPresentation";
import { downloadOptimizerReport } from "./optimizerReport";
import type {
  LoadSummary,
  DataQualityHistoryResponse,
  SlateLoadResponse,
  OptimizerResponse,
  ContestPreview,
  SlateReadinessGateKey,
  SlateReadinessResponse,
  SimulationResponse,
  SlateLearningReport,
} from "./api";
import {
  analyzePastSlate,
  buildFeatures,
  createWeeklyRun,
  downloadOptimizerLineups,
  fetchCurrentContext,
  fetchLatestPredictions,
  generateSlateLearningReport,
  fetchOperationalJobs,
  fetchWeeklyRuns,
  fetchDataQualityHistory,
  fetchOptimizerResults,
  previewOptimizerContests,
  fetchSlateReadiness,
  fetchSymbolicBacktest,
  fetchSymbolicRules,
  fetchUnmatchedSalaries,
  fetchValidation,
  loadOwnership,
  loadRawInjuries,
  loadRawSalaries,
  loadRawSeason,
  loadRawWeek,
  loadRawWeekRosters,
  loadSlateResource,
  loadStartingQBs,
  processUnmatchedToPlayerMaster,
  runAgent,
  runOptimizer,
  runOwnershipModel,
  runPredictions,
  runSlateSimulation,
  retryWeeklyRun,
  setSymbolicRuleEnabled,
  startPostgres,
  upsertSymbolicRule,
  type AgentRunResponse,
  type BuildFeaturesResponse,
  type OwnershipLoadPayload,
  type OwnershipPayoutTierInput,
  type OperationalJob,
  type PredictionRow,
  type SymbolicBacktestResponse,
  type SymbolicRule,
  type StartPostgresResponse,
  type StartingQBResponse,
  type UnmatchedSalaryRow,
  type ValidationRow,
  type WeeklyRun,
} from "./api";
import { fetchUnmatchedInjuries, type UnmatchedInjuryRow } from "./api";

const FALLBACK_SEASON = 2026;
const FALLBACK_WEEK = 1;
type OwnershipOperationStatus = {
  message: string;
  rows_written: number;
  target_persisted?: boolean;
  contest_id?: string | null;
  source_file_id?: string | null;
  evidence_posture?: string;
  ownership_run_id?: string | null;
  model_metrics?: Record<string, unknown>;
};

type PredictionOperationStatus = {
  message: string;
  rows_written: number;
};

type OwnershipPayoutTierDraft = {
  minRank: string;
  maxRank: string;
  payout: string;
  prizeDescription: string;
};

type OwnershipEvidenceDraft = {
  contestId: string;
  contestName: string;
  contestFormat: "" | "classic" | "showdown";
  contestType: "" | "cash" | "gpp";
  entryFee: string;
  fieldSize: string;
  maxEntriesPerUser: string;
  prizePool: string;
  payoutTiers: OwnershipPayoutTierDraft[];
};

function optionalEvidenceNumber(
  rawValue: string,
  label: string,
  options: { integer?: boolean; minimum?: number } = {},
) {
  const value = rawValue.trim();
  if (!value) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`${label} must be a number.`);
  if (options.integer && !Number.isInteger(parsed)) {
    throw new Error(`${label} must be a whole number.`);
  }
  if (parsed < (options.minimum ?? 0)) {
    throw new Error(`${label} must be at least ${options.minimum ?? 0}.`);
  }
  return parsed;
}

function buildOwnershipEvidencePayload(
  draft: OwnershipEvidenceDraft,
): Omit<OwnershipLoadPayload, "season" | "week" | "slate" | "path"> {
  const fieldSize = optionalEvidenceNumber(draft.fieldSize, "Field size", {
    integer: true,
    minimum: 1,
  });
  const tiers: OwnershipPayoutTierInput[] = draft.payoutTiers.map((tier, index) => {
    const tierNumber = index + 1;
    const minRank = optionalEvidenceNumber(tier.minRank, `Tier ${tierNumber} minimum rank`, {
      integer: true,
      minimum: 1,
    });
    const maxRank = optionalEvidenceNumber(tier.maxRank, `Tier ${tierNumber} maximum rank`, {
      integer: true,
      minimum: 1,
    });
    const payout = optionalEvidenceNumber(tier.payout, `Tier ${tierNumber} payout`);
    const prizeDescription = tier.prizeDescription.trim();
    if (minRank === undefined || maxRank === undefined) {
      throw new Error(`Tier ${tierNumber} requires both minimum and maximum rank.`);
    }
    if (maxRank < minRank) {
      throw new Error(`Tier ${tierNumber} maximum rank cannot be below its minimum rank.`);
    }
    if (fieldSize !== undefined && maxRank > fieldSize) {
      throw new Error(`Tier ${tierNumber} exceeds the declared field size.`);
    }
    if (payout === undefined && !prizeDescription) {
      throw new Error(`Tier ${tierNumber} requires a payout or prize description.`);
    }
    return {
      min_rank: minRank,
      max_rank: maxRank,
      ...(payout !== undefined ? { payout } : {}),
      ...(prizeDescription ? { prize_description: prizeDescription } : {}),
    };
  });
  const sortedTiers = [...tiers].sort((left, right) => left.min_rank - right.min_rank);
  sortedTiers.slice(1).forEach((tier, index) => {
    if (tier.min_rank <= sortedTiers[index].max_rank) {
      throw new Error("Payout tiers cannot overlap.");
    }
  });
  if (sortedTiers.length > 0 && !draft.contestType) {
    throw new Error("Choose Cash or GPP before supplying payout tiers.");
  }

  const contestId = draft.contestId.trim();
  const contestName = draft.contestName.trim();
  const entryFee = optionalEvidenceNumber(draft.entryFee, "Entry fee");
  const maxEntriesPerUser = optionalEvidenceNumber(
    draft.maxEntriesPerUser,
    "Maximum entries per user",
    { integer: true, minimum: 1 },
  );
  const prizePool = optionalEvidenceNumber(draft.prizePool, "Prize pool");
  return {
    ...(contestId ? { contest_id: contestId } : {}),
    ...(contestName ? { contest_name: contestName } : {}),
    ...(draft.contestFormat ? { contest_format: draft.contestFormat } : {}),
    ...(draft.contestType ? { contest_type: draft.contestType } : {}),
    ...(entryFee !== undefined ? { entry_fee: entryFee } : {}),
    ...(fieldSize !== undefined ? { field_size: fieldSize } : {}),
    ...(maxEntriesPerUser !== undefined
      ? { max_entries_per_user: maxEntriesPerUser }
      : {}),
    ...(prizePool !== undefined ? { prize_pool: prizePool } : {}),
    ...(sortedTiers.length > 0 ? { payout_tiers: sortedTiers } : {}),
  };
}

function ownershipMetricSummary(status: OwnershipOperationStatus) {
  const metrics = status.model_metrics as {
    mae?: number;
    baseline_mae?: number;
    rank_correlation?: number;
    walk_forward_rows?: number;
    promotion_gate?: { status?: string };
  } | undefined;
  if (!metrics || typeof metrics.mae !== "number") return null;
  const rank = typeof metrics.rank_correlation === "number" ? ` · ρ ${metrics.rank_correlation.toFixed(2)}` : "";
  const baseline = typeof metrics.baseline_mae === "number" ? ` vs ${metrics.baseline_mae.toFixed(2)} baseline` : "";
  return `${Number(metrics.walk_forward_rows ?? 0).toLocaleString()} replay rows · ${metrics.mae.toFixed(2)} MAE${baseline}${rank} · promotion ${metrics.promotion_gate?.status ?? "blocked"}`;
}

function optimizerReadinessGateKey(
  contestFormat: "classic" | "showdown",
  objective: "cash" | "gpp",
): SlateReadinessGateKey {
  return `${contestFormat}_${objective}` as SlateReadinessGateKey;
}

function readinessFailureMessage(report: SlateReadinessResponse, gateKey: SlateReadinessGateKey) {
  const blocking = new Set(report.gates[gateKey].blocking_checks);
  const messages = report.checks
    .filter((check) => blocking.has(check.check_id))
    .map((check) => check.message);
  return messages.length > 0 ? messages.join(" ") : report.gates[gateKey].message;
}

function compactTelemetry(values: Record<string, unknown>) {
  const entries = Object.entries(values);
  if (entries.length === 0) return "—";
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${Array.isArray(value) ? value.length : String(value ?? "—")}`)
    .join(" · ");
}

function App() {
  const [viewMode, setViewMode] = useState<ViewMode>("digital-twin");
  const [season, setSeason] = useState(FALLBACK_SEASON);
  const [week, setWeek] = useState(FALLBACK_WEEK);
  const [slate, setSlate] = useState(DEFAULT_SLATE);
  const [runSelections, setRunSelections] = useState<PersistedRunSelections>({});
  const activeContext = useMemo(
    () => ({ season, week, slate: normalizeSlateId(slate) }),
    [season, slate, week],
  );
  const activeContextKey = slateContextKey(activeContext);
  const activeRunSelection = runSelections[activeContextKey] ?? {};
  const setActiveSlate = useCallback((value: string) => setSlate(normalizeSlateId(value)), []);
  const updateActiveRunSelection = useCallback(
    (patch: Partial<PersistedRunSelection>) => {
      setRunSelections((current) => updateRunSelection(current, activeContext, patch));
    },
    [activeContext, activeContextKey],
  );
  const setActiveProjectionRunId = useCallback(
    (runId: string | null) => updateActiveRunSelection({ projectionRunId: runId ?? undefined }),
    [updateActiveRunSelection],
  );
  const setActiveResearchSimulationRunId = useCallback(
    (runId: string) => updateActiveRunSelection({ researchSimulationRunId: runId || undefined }),
    [updateActiveRunSelection],
  );
  const setActiveResearchBaselineRunId = useCallback(
    (runId: string) => updateActiveRunSelection({ researchBaselineRunId: runId || undefined }),
    [updateActiveRunSelection],
  );
  const setActiveOptimizerRunId = useCallback(
    (runId: string) => updateActiveRunSelection({ optimizerRunId: runId.trim() || undefined }),
    [updateActiveRunSelection],
  );
  const [injuryPath, setInjuryPath] = useState<string>("~/Downloads/Injuries.csv");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadSummaries, setLoadSummaries] = useState<LoadSummary[]>([]);
  const [lastLoadType, setLastLoadType] = useState<string | null>(null);
  const [slateStatus, setSlateStatus] = useState<SlateLoadResponse | null>(null);
  const [optimizerStatuses, setOptimizerStatuses] = useState<Record<string, OptimizerResponse>>({});
  const optimizerStatus = optimizerStatuses[activeContextKey] ?? null;
  const setOptimizerStatus = useCallback((status: OptimizerResponse | null) => {
    setOptimizerStatuses((current) => {
      if (status) return { ...current, [activeContextKey]: status };
      const next = { ...current };
      delete next[activeContextKey];
      return next;
    });
  }, [activeContextKey]);
  const [slateReadiness, setSlateReadiness] = useState<SlateReadinessResponse | null>(null);
  const [lineupExportPending, setLineupExportPending] = useState(false);
  const [lineupExportError, setLineupExportError] = useState<string | null>(null);
  const [dataQualityHistory, setDataQualityHistory] = useState<DataQualityHistoryResponse | null>(null);
  const [dataQualityLoading, setDataQualityLoading] = useState(false);
  const [dataQualityError, setDataQualityError] = useState<string | null>(null);
  const [numLineups, setNumLineups] = useState(20);
  const [maxExposure, setMaxExposure] = useState(60);
  const [captainMaxExposure, setCaptainMaxExposure] = useState(60);
  const captainMaxExposureInputRef = useRef<HTMLInputElement>(null);
  const [coreMaxExposure, setCoreMaxExposure] = useState(80);
  const [startingQbMaxExposure, setStartingQbMaxExposure] = useState(100);
  const [cheapPuntMaxExposure, setCheapPuntMaxExposure] = useState(40);
  const [contestFormat, setContestFormat] = useState<"classic" | "showdown">("classic");
  const [optimizerObjective, setOptimizerObjective] = useState<"cash" | "gpp">("gpp");
  const [showdownGppStrategy, setShowdownGppStrategy] = useState(SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID);
  const [singleEntryContestUrls, setSingleEntryContestUrls] = useState("");
  const [singleEntryContestMode, setSingleEntryContestMode] = useState<"auto" | "enter_all">("auto");
  const [singleEntryBudget, setSingleEntryBudget] = useState("");
  const [singleEntryMaximum, setSingleEntryMaximum] = useState("");
  const [singleEntryManual, setSingleEntryManual] = useState("");
  const [contestPreview, setContestPreview] = useState<ContestPreview | null>(null);
  const [contestPreviewError, setContestPreviewError] = useState<string | null>(null);
  const [contestPreviewPending, setContestPreviewPending] = useState(false);
  const singleEntryContestParams = () => {
    const urls = singleEntryContestUrls.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
    if (!urls.length) throw new Error("Paste at least one DraftKings single-entry contest URL.");
    let manual: Array<Record<string, unknown>> = [];
    if (singleEntryManual.trim()) {
      const parsed = JSON.parse(singleEntryManual);
      if (!Array.isArray(parsed)) throw new Error("Manual contest metadata must be a JSON array.");
      manual = parsed;
    }
    const budget = singleEntryBudget.trim() ? Number(singleEntryBudget) : undefined;
    const maximum = singleEntryMaximum.trim() ? Number(singleEntryMaximum) : undefined;
    if (budget !== undefined && (!Number.isFinite(budget) || budget <= 0)) throw new Error("Maximum budget must be positive.");
    if (maximum !== undefined && (!Number.isInteger(maximum) || maximum < 1)) throw new Error("Maximum contests must be a positive integer.");
    return {
      contest_urls: urls, contest_selection: singleEntryContestMode,
      manual_contest_metadata: manual,
      ...(budget !== undefined ? { maximum_total_entry_budget: budget } : {}),
      ...(maximum !== undefined ? { maximum_contests_to_enter: maximum } : {}),
    };
  };
  const [classicContestStrategy, setClassicContestStrategy] =
    useState<ClassicContestStrategyId>(CLASSIC_LARGE_GPP_STRATEGY_ID);
  const [minimumUniqueness, setMinimumUniqueness] = useState(2);
  const [maxPlayersPerTeam, setMaxPlayersPerTeam] = useState(4);
  const [maxPlayersPerGame, setMaxPlayersPerGame] = useState(5);
  const [enforceSingleTE, setEnforceSingleTE] = useState(true);
  const [avoidDstOpponents, setAvoidDstOpponents] = useState(true);
  const selectedClassicStrategy = CLASSIC_CONTEST_STRATEGIES.find(
    (strategy) => strategy.id === classicContestStrategy
  ) ?? CLASSIC_CONTEST_STRATEGIES[1];
  const effectiveOptimizerObjective =
    contestFormat === "classic"
      ? selectedClassicStrategy.objective
      : optimizerObjective;
  const selectedOptimizerStrategy = contestFormat === "showdown" && optimizerObjective === "gpp"
    ? showdownGppStrategy
    : optimizerStrategyId(contestFormat, effectiveOptimizerObjective, classicContestStrategy);
  const [predictionStatuses, setPredictionStatuses] = useState<Record<string, PredictionOperationStatus>>({});
  const predictionStatus = predictionStatuses[activeContextKey] ?? null;
  const setPredictionStatus = useCallback((status: PredictionOperationStatus | null) => {
    setPredictionStatuses((current) => {
      if (status) return { ...current, [activeContextKey]: status };
      const next = { ...current };
      delete next[activeContextKey];
      return next;
    });
  }, [activeContextKey]);
  const [predictionRowsByContext, setPredictionRowsByContext] = useState<Record<string, PredictionRow[]>>({});
  const predictionRows = predictionRowsByContext[activeContextKey] ?? [];
  const setPredictionRows = useCallback((rows: PredictionRow[]) => {
    setPredictionRowsByContext((current) => ({ ...current, [activeContextKey]: rows }));
  }, [activeContextKey]);
  const [simulationStatuses, setSimulationStatuses] = useState<Record<string, SimulationResponse>>({});
  const simulationStatus = simulationStatuses[activeContextKey] ?? null;
  const setSimulationStatus = useCallback((status: SimulationResponse | null) => {
    setSimulationStatuses((current) => {
      if (status) return { ...current, [activeContextKey]: status };
      const next = { ...current };
      delete next[activeContextKey];
      return next;
    });
  }, [activeContextKey]);
  const [operationalJobs, setOperationalJobs] = useState<OperationalJob[]>([]);
  const [weeklyRuns, setWeeklyRuns] = useState<WeeklyRun[]>([]);
  const [weeklyDirectory, setWeeklyDirectory] = useState("");
  const [weeklyTemplateId, setWeeklyTemplateId] = useState("");
  const [weeklyRunError, setWeeklyRunError] = useState<string | null>(null);
  const [predictionPreview] = useState<PredictionRow[]>([]);
  const [validationTable, setValidationTable] = useState("nfl_weekly_data_with_scores");
  const [validationRows, setValidationRows] = useState<ValidationRow[]>([]);
  const [validationLoading, setValidationLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [startingQBStatus, setStartingQBStatus] = useState<StartingQBResponse | null>(
    null
  );
  const [salaryPath, setSalaryPath] = useState<string>("~/Downloads/DKSalaries.csv");
  const [ownershipPath, setOwnershipPath] = useState<string>("~/Downloads/ownership.csv");
  const [ownershipEvidence, setOwnershipEvidence] = useState<OwnershipEvidenceDraft>({
    contestId: "",
    contestName: "",
    contestFormat: "",
    contestType: "",
    entryFee: "",
    fieldSize: "",
    maxEntriesPerUser: "",
    prizePool: "",
    payoutTiers: [],
  });
  const [ownershipStatus, setOwnershipStatus] = useState<OwnershipOperationStatus | null>(null);
  const [ownershipError, setOwnershipError] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<string | null>(null);
  const [analysisTopN, setAnalysisTopN] = useState<number>(100);
  const [analysisRows, setAnalysisRows] = useState<
    { player_display_name: string; roster_position?: string | null; count: number; pct: number }[]
  >([]);
  const [learningEntryUser, setLearningEntryUser] = useState<string>(
    () => window.localStorage.getItem("dfs-learning-entry-user") ?? "",
  );
  const [learningReport, setLearningReport] = useState<SlateLearningReport | null>(null);
  const [learningError, setLearningError] = useState<string | null>(null);
  const ownershipHasCompletePayoutTiers = ownershipEvidence.payoutTiers.length > 0
    && ownershipEvidence.payoutTiers.every((tier) => (
      tier.minRank.trim()
      && tier.maxRank.trim()
      && (tier.payout.trim() || tier.prizeDescription.trim())
    ));
  const ownershipEvidencePosture = ownershipEvidence.contestType === "cash"
    ? ownershipHasCompletePayoutTiers && ownershipEvidence.entryFee.trim()
      ? "Cash + ROI supplied"
      : ownershipHasCompletePayoutTiers
        ? "Cash payout supplied"
        : "Cash type supplied"
    : ownershipEvidence.contestType === "gpp"
      ? "GPP metadata supplied"
      : "Field proxy only";
  const ownershipEvidenceTone = ownershipEvidence.contestType === "cash"
    ? "cash"
    : ownershipEvidence.contestType === "gpp"
      ? "gpp"
      : "proxy";

  const updateOwnershipEvidence = <Key extends keyof OwnershipEvidenceDraft>(
    key: Key,
    value: OwnershipEvidenceDraft[Key],
  ) => {
    setOwnershipEvidence((current) => ({ ...current, [key]: value }));
  };

  const addOwnershipPayoutTier = () => {
    setOwnershipEvidence((current) => ({
      ...current,
      payoutTiers: [
        ...current.payoutTiers,
        { minRank: "", maxRank: "", payout: "", prizeDescription: "" },
      ],
    }));
  };

  const updateOwnershipPayoutTier = (
    index: number,
    key: keyof OwnershipPayoutTierDraft,
    value: string,
  ) => {
    setOwnershipEvidence((current) => ({
      ...current,
      payoutTiers: current.payoutTiers.map((tier, tierIndex) => (
        tierIndex === index ? { ...tier, [key]: value } : tier
      )),
    }));
  };

  const removeOwnershipPayoutTier = (index: number) => {
    setOwnershipEvidence((current) => ({
      ...current,
      payoutTiers: current.payoutTiers.filter((_, tierIndex) => tierIndex !== index),
    }));
  };
  const [excludePlayers, setExcludePlayers] = useState<string>("");
  const [excludePlayerIds, setExcludePlayerIds] = useState<string>("");
  const [lockedPlayerIds, setLockedPlayerIds] = useState<string>("");
  const [flexOnlyPlayers, setFlexOnlyPlayers] = useState<string>("");
  const [topLineups, setTopLineups] = useState<
    {
      rank: number;
      final_points: number;
      entry_id: string;
      salary_used: number;
      salary_left: number;
      players?: string;
      total_own_sum: number;
      avg_own: number;
      num_chalk: number;
      num_low_owned: number;
      num_sub_4k: number;
      qb_stack_type: string;
      bring_back_count: number;
      notes: string;
    }[]
  >([]);
  const [bucketStats, setBucketStats] = useState<
    { bucket: string; lineups: number; avg_actual_own_sum: number; median_actual_own_sum: number; avg_num_chalk: number; avg_num_low_owned: number; avg_total_salary: number; avg_num_sub_4k: number }[]
  >([]);

  const runLoadRawSalaries = async () => {
    setError(null);
    setPendingAction("Loading raw salaries...");
    try {
      const resp = await loadRawSalaries({ season, week, slate, path: salaryPath });
      let summaries = (resp as any).summaries;
      if (!Array.isArray(summaries)) {
        const rows = (resp as any).rows_written ?? 0;
        summaries = [
          { dataset: "raw_salaries", season, week, rows_written: rows },
          { dataset: "curated_salaries", season, week, rows_written: 0 },
          { dataset: "unmatched_salaries", season, week, rows_written: 0 },
        ];
      }
      setLoadSummaries(summaries);
      setSlateStatus(null);
      setLastLoadType(`Salaries week ${week} (${slate})`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runLoadRawInjuries = async () => {
    setError(null);
    setPendingAction("Loading raw injuries...");
    try {
      const resp = await loadRawInjuries({ season, week, slate, path: injuryPath });
      let summaries = (resp as any).summaries;
      if (!Array.isArray(summaries)) {
        const rows = (resp as any).rows_written ?? 0;
        summaries = [
          { dataset: "raw_injuries", season, week, rows_written: rows },
          { dataset: "curated_injuries", season, week, rows_written: 0 },
          { dataset: "unmatched_injuries", season, week, rows_written: 0 },
        ];
      }
      setLoadSummaries(summaries);
      setSlateStatus(null);
      setLastLoadType(`Injuries week ${week} (${slate})`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };
  const [unmatchedRows, setUnmatchedRows] = useState<UnmatchedSalaryRow[]>([]);
  const [unmatchedError, setUnmatchedError] = useState<string | null>(null);
  const [unmatchedLoading, setUnmatchedLoading] = useState(false);
  const [unmatchedInjuryRows, setUnmatchedInjuryRows] = useState<UnmatchedInjuryRow[]>([]);
  const [unmatchedInjuryError, setUnmatchedInjuryError] = useState<string | null>(null);
  const [unmatchedInjuryLoading, setUnmatchedInjuryLoading] = useState(false);
  const [featureStatus, setFeatureStatus] = useState<BuildFeaturesResponse | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [postgresStatus, setPostgresStatus] = useState<StartPostgresResponse | null>(null);
  const [postgresError, setPostgresError] = useState<string | null>(null);
  const [postgresLoading, setPostgresLoading] = useState(false);
  const [postgresDetails, setPostgresDetails] = useState<string | null>(null);
  const [futureWeek, setFutureWeek] = useState<number | "">("");
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentRunResponse>>({});
  const agentStatus = agentStatuses[activeContextKey] ?? null;
  const setAgentStatus = useCallback((status: AgentRunResponse | null) => {
    setAgentStatuses((current) => {
      if (status) return { ...current, [activeContextKey]: status };
      const next = { ...current };
      delete next[activeContextKey];
      return next;
    });
  }, [activeContextKey]);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [symbolicRules, setSymbolicRules] = useState<SymbolicRule[]>([]);
  const [symbolicRulesError, setSymbolicRulesError] = useState<string | null>(null);
  const [symbolicRulesStatus, setSymbolicRulesStatus] = useState<string | null>(null);
  const [symbolicRulesLoading, setSymbolicRulesLoading] = useState(false);
  const [symbolicBacktest, setSymbolicBacktest] = useState<SymbolicBacktestResponse | null>(null);
  const [symbolicBacktestError, setSymbolicBacktestError] = useState<string | null>(null);
  const [symbolicBacktestLoading, setSymbolicBacktestLoading] = useState(false);
  const [ruleForm, setRuleForm] = useState<{
    rule_id: string;
    rule_name: string;
    rule_type: string;
    enabled: boolean;
    priority: number;
    version: number;
    condition_json: string;
    action_json: string;
  }>({
    rule_id: "",
    rule_name: "",
    rule_type: "injury",
    enabled: true,
    priority: 100,
    version: 1,
    condition_json: "{}",
    action_json: "{}",
  });
  const [unmatchedProcessStatus, setUnmatchedProcessStatus] = useState<string | null>(null);

  const refreshDataQualityHistory = useCallback(async () => {
    setDataQualityLoading(true);
    setDataQualityError(null);
    try {
      const history = await fetchDataQualityHistory({ season, week, slate, limit: 12 });
      setDataQualityHistory(history);
    } catch (err) {
      setDataQualityError(err instanceof Error ? err.message : String(err));
    } finally {
      setDataQualityLoading(false);
    }
  }, [season, week, slate]);

  useEffect(() => {
    let cancelled = false;
    fetchCurrentContext()
      .then((context) => {
        if (cancelled) return;
        setSeason(context.season);
        setWeek(context.week);
        setFutureWeek(context.week);
      })
      .catch(() => {
        if (cancelled) return;
        setSeason(FALLBACK_SEASON);
        setWeek(FALLBACK_WEEK);
        setFutureWeek(FALLBACK_WEEK);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const selectedOptimizerRunId = activeRunSelection.optimizerRunId;
    if (!selectedOptimizerRunId || optimizerStatus?.job_id === selectedOptimizerRunId) return;
    let cancelled = false;
    fetchOptimizerResults(selectedOptimizerRunId)
      .then((response) => {
        if (!cancelled) setOptimizerStatus(response);
      })
      .catch(() => {
        // Delivery performs the authoritative compatibility check when creating a portfolio.
      });
    return () => {
      cancelled = true;
    };
  }, [activeRunSelection.optimizerRunId, optimizerStatus?.job_id, setOptimizerStatus]);

  useEffect(() => {
    if (viewMode !== "workspace") return;
    refreshDataQualityHistory().catch((err) => {
      setDataQualityError(err instanceof Error ? err.message : String(err));
    });
  }, [
    viewMode,
    refreshDataQualityHistory,
    lastLoadType,
    slateStatus,
    ownershipStatus,
    featureStatus,
    predictionStatus,
    startingQBStatus,
    slateReadiness,
  ]);

  useEffect(() => {
    if (viewMode !== "workspace") return;
    let cancelled = false;
    let timer: number | undefined;
    const refreshJobs = async () => {
      try {
        const [jobs, workflows] = await Promise.all([
          fetchOperationalJobs(12),
          fetchWeeklyRuns({ season, week, slate, limit: 5 }),
        ]);
        if (!cancelled) {
          setOperationalJobs(jobs.rows);
          setWeeklyRuns(workflows.rows);
        }
      } catch {
        // The worker/API may be intentionally offline during local UI-only work.
      } finally {
        if (!cancelled) timer = window.setTimeout(refreshJobs, 3000);
      }
    };
    refreshJobs().catch(() => undefined);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [viewMode, season, week, slate]);

  const launchWeeklyRun = async () => {
    const requestedCaptainMaxExposure = Number.isFinite(captainMaxExposureInputRef.current?.valueAsNumber)
      ? Number(captainMaxExposureInputRef.current?.valueAsNumber)
      : captainMaxExposure;
    setPendingAction("Queueing weekly run...");
    setWeeklyRunError(null);
    try {
      const response = await createWeeklyRun({
        season,
        week,
        slate,
        draftkings_directory: weeklyDirectory.trim() || undefined,
        contest_format: contestFormat,
        objective: effectiveOptimizerObjective,
        strategy: selectedOptimizerStrategy,
        num_simulations: 1000,
        optimizer_params: {
          num_lineups: selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID ? 1 : selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestUrls.split(/\r?\n/).filter((url) => url.trim()).length : numLineups,
          ...(selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestParams() : {}),
          max_exposure: selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID || selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? 1 : maxExposure / 100,
          ...(contestFormat === "showdown" && effectiveOptimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID ? {
            captain_max_exposure: requestedCaptainMaxExposure / 100,
            core_player_max_exposure: coreMaxExposure / 100,
            starting_qb_max_exposure: startingQbMaxExposure / 100,
            cheap_punt_max_exposure: cheapPuntMaxExposure / 100,
          } : {}),
          enforce_single_te: enforceSingleTE,
          avoid_dst_opponents: avoidDstOpponents,
          ...(contestFormat === "classic" && classicContestStrategy === CLASSIC_LARGE_GPP_STRATEGY_ID
            ? {
                minimum_uniqueness: minimumUniqueness,
                max_players_per_team: maxPlayersPerTeam,
                max_players_per_game: maxPlayersPerGame,
              }
            : {}),
          exclude_players: excludePlayers
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          exclude_player_ids: excludePlayerIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          locked_player_ids: lockedPlayerIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          ...(contestFormat === "showdown"
            ? {
                flex_only_players: flexOnlyPlayers
                  .split(",")
                  .map((value) => value.trim())
                  .filter(Boolean),
              }
            : {}),
        },
        template_id: weeklyTemplateId.trim() || undefined,
        portfolio_name: `${season} W${week} ${slate}`,
      });
      setWeeklyRuns((current) => [
        response.run,
        ...current.filter((row) => row.weekly_run_id !== response.run.weekly_run_id),
      ]);
    } catch (err) {
      setWeeklyRunError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const retryFailedWeeklyRun = async (weeklyRunId: string) => {
    setPendingAction("Requeueing weekly run...");
    setWeeklyRunError(null);
    try {
      await retryWeeklyRun(weeklyRunId);
      const workflows = await fetchWeeklyRuns({ season, week, slate, limit: 5 });
      setWeeklyRuns(workflows.rows);
    } catch (err) {
      setWeeklyRunError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  useEffect(() => {
    const loadRules = async () => {
      try {
        const response = await fetchSymbolicRules({ include_disabled: true });
        setSymbolicRules(response.rows);
      } catch (err) {
        setSymbolicRulesError(err instanceof Error ? err.message : String(err));
      }
    };
    loadRules().catch((err) => {
      setSymbolicRulesError(err instanceof Error ? err.message : String(err));
    });
  }, []);

  const runLoad = async (type: "season" | "week") => {
    setLoading(true);
    setError(null);
    setLoadError(null);
    setPendingAction(type === "season" ? "Loading season..." : `Loading week ${week}...`);
    try {
      const payload = {
        season,
      };
      const response =
        type === "season"
          ? await loadRawSeason(payload)
          : await loadRawWeek({ ...payload, week });
      setLoadSummaries(response.summaries);
      setLastLoadType(type === "season" ? `Season ${season}` : `Week ${week}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setLoadError(`Load failed: ${msg}`);
    } finally {
      setLoading(false);
      setPendingAction(null);
    }
  };

  const runLoadRawStats = async () => {
    setLoading(true);
    setError(null);
    setLoadError(null);
    setPendingAction(`Loading weekly stats week ${week}...`);
    try {
      const resp = await loadRawWeek({ season, week });
      setLoadSummaries(resp.summaries);
      setLastLoadType(`Weekly stats week ${week}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setLoadError(`Load failed: ${msg}`);
    } finally {
      setLoading(false);
      setPendingAction(null);
    }
  };

  const runLoadRawRosters = async () => {
    setLoading(true);
    setError(null);
    setLoadError(null);
    setPendingAction(`Loading rosters week ${week}...`);
    try {
      const resp = await loadRawWeekRosters({ season, week });
      setLoadSummaries(resp.summaries);
      setLastLoadType(`Rosters week ${week}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setLoadError(`Load failed: ${msg}`);
    } finally {
      setLoading(false);
      setPendingAction(null);
    }
  };

  const runSlateLoad = async (type: "salaries" | "injuries") => {
    setError(null);
    setPendingAction(type === "salaries" ? "Loading salaries..." : "Loading injuries...");
    try {
      const response = await loadSlateResource(type, {
        season,
        week,
        slate,
      });
      setSlateStatus(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runOptimizerJob = async () => {
    const requestedCaptainMaxExposure = Number.isFinite(captainMaxExposureInputRef.current?.valueAsNumber)
      ? Number(captainMaxExposureInputRef.current?.valueAsNumber)
      : captainMaxExposure;
    setOptimizerStatus(null); // clear prior results while new job runs
    setError(null);
    setPendingAction("Checking slate readiness...");
    try {
      const readiness = await fetchSlateReadiness({ season, week, slate, record: true });
      setSlateReadiness(readiness);
      const gateKey = optimizerReadinessGateKey(contestFormat, effectiveOptimizerObjective);
      if (readiness.gates[gateKey].status === "fail") {
        throw new Error(`Optimizer blocked by slate readiness: ${readinessFailureMessage(readiness, gateKey)}`);
      }
      setPendingAction("Running optimizer...");
      const response = await runOptimizer({
        season,
        week,
        slate,
        strategy: selectedOptimizerStrategy,
        contest_format: contestFormat,
        objective: effectiveOptimizerObjective,
        projection_run_id: activeRunSelection.projectionRunId,
        params: {
          num_lineups: selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID ? 1 : selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestUrls.split(/\r?\n/).filter((url) => url.trim()).length : numLineups,
          ...(selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestParams() : {}),
          max_exposure: selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID || selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? 1 : maxExposure / 100,
          ...(contestFormat === "showdown" && effectiveOptimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID ? {
            captain_max_exposure: requestedCaptainMaxExposure / 100,
            core_player_max_exposure: coreMaxExposure / 100,
            starting_qb_max_exposure: startingQbMaxExposure / 100,
            cheap_punt_max_exposure: cheapPuntMaxExposure / 100,
          } : {}),
          enforce_single_te: enforceSingleTE,
          avoid_dst_opponents: avoidDstOpponents,
          ...(contestFormat === "classic" && classicContestStrategy === CLASSIC_LARGE_GPP_STRATEGY_ID
            ? {
                minimum_uniqueness: minimumUniqueness,
                max_players_per_team: maxPlayersPerTeam,
                max_players_per_game: maxPlayersPerGame,
              }
            : {}),
          exclude_players: excludePlayers
            .split(",")
            .map((s) => s.trim())
            .filter((s) => s.length > 0),
          exclude_player_ids: excludePlayerIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          locked_player_ids: lockedPlayerIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          ...(contestFormat === "showdown"
            ? {
                flex_only_players: flexOnlyPlayers
                  .split(",")
                  .map((value) => value.trim())
                  .filter(Boolean),
              }
            : {}),
        },
      });
      setOptimizerStatus(response);
      updateActiveRunSelection({
        optimizerRunId: response.job_id,
        projectionRunId: response.projection_run_id ?? activeRunSelection.projectionRunId,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const refreshOptimizer = async () => {
    if (!optimizerStatus?.job_id) return;
    setError(null);
    setPendingAction("Refreshing optimizer...");
    try {
      const response = await fetchOptimizerResults(optimizerStatus.job_id);
      setOptimizerStatus(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runPredictionJob = async () => {
    setError(null);
    setPendingAction("Checking slate readiness...");
    try {
      const readiness = await fetchSlateReadiness({ season, week, slate, record: true });
      setSlateReadiness(readiness);
      if (readiness.gates.prediction.status === "fail") {
        throw new Error(`Prediction blocked by slate readiness: ${readinessFailureMessage(readiness, "prediction")}`);
      }
      setPendingAction("Running projections...");
      const response = await runPredictions({ season, week, slate });
      setPredictionStatus({
        message: response.message,
        rows_written: response.rows_written,
      });
      // Pull latest projections after run
      const projections = await fetchLatestPredictions({
        season,
        week,
        limit: 1000,
        slate,
        projectionRunId: response.projection_run_id ?? activeRunSelection.projectionRunId,
      });
      setPredictionRows(projections.rows);
      updateActiveRunSelection({
        projectionRunId: projections.projection_run_id ?? response.projection_run_id ?? undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runSimulationJob = async () => {
    setError(null);
    setSimulationStatus(null);
    setPendingAction("Running slate simulation...");
    try {
      const response = await runSlateSimulation({
        season,
        week,
        slate,
        contest_format: contestFormat,
        num_simulations: 1000,
        seed: 502,
        projection_run_id: activeRunSelection.projectionRunId,
      });
      setSimulationStatus(response);
      updateActiveRunSelection({
        projectionRunId: response.projection_run_id,
        slateSimulationRunId: response.simulation_run_id,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runValidation = async () => {
    setValidationLoading(true);
    setValidationError(null);
    setPendingAction("Checking coverage...");
    try {
      const response = await fetchValidation(validationTable);
      setValidationRows(response.results);
    } catch (err) {
      setValidationError(err instanceof Error ? err.message : String(err));
      setValidationRows([]);
    } finally {
      setValidationLoading(false);
      setPendingAction(null);
    }
  };

  const runStartingQBs = async () => {
    setError(null);
    setPendingAction("Loading starting QBs...");
    try {
      const response = await loadStartingQBs({ season, week, slate });
      setStartingQBStatus(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runStartPostgres = async () => {
    setPostgresLoading(true);
    setPostgresError(null);
    setPostgresDetails(null);
    setPendingAction("Starting PostgreSQL...");
    try {
      const response = await startPostgres();
      setPostgresStatus(response);
      const details = [response.stdout, response.stderr].filter(Boolean).join("\n");
      setPostgresDetails(details || null);
      if (!response.ok) {
        setPostgresError(response.stderr || response.message);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setPostgresError(msg);
      setPostgresStatus({
        ok: false,
        message: "Failed to start PostgreSQL",
        stdout: "",
        stderr: msg,
      });
    } finally {
      setPostgresLoading(false);
      setPendingAction(null);
    }
  };

  const runBuildFeatures = async (scope: "all" | "current") => {
    setError(null);
    setPendingAction(scope === "all" ? "Building features (all weeks)..." : "Building features (current)...");
    try {
      const weeks = scope === "all" ? undefined : [week];
      const response = await buildFeatures({ season, weeks });
      setFeatureStatus(response);
      setLoadSummaries([
        {
          dataset: "predictive_features",
          season,
          week: weeks ? week : null,
          rows_written: response.rows_written,
        },
      ]);
      setLastLoadType(scope === "all" ? "Features (all weeks)" : `Features week ${week}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runBuildFutureFeatures = async () => {
    if (futureWeek === "") return;
    setError(null);
    setPendingAction(`Building features for future week ${futureWeek}...`);
    try {
      const response = await buildFeatures({ season, future_week: Number(futureWeek) });
      setFeatureStatus(response);
      setLoadSummaries([
        {
          dataset: "predictive_features_future",
          season,
          week: Number(futureWeek),
          rows_written: response.rows_written,
        },
      ]);
      setLastLoadType(`Features future week ${futureWeek}`);
      setUnmatchedProcessStatus(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runProcessUnmatched = async () => {
    setError(null);
    setPendingAction("Processing unmatched to player master...");
    try {
      const response = await processUnmatchedToPlayerMaster({ season, week });
      setUnmatchedProcessStatus(response.message);
      setLoadSummaries([
        {
          dataset: "process_unmatched",
          season,
          week,
          rows_written: response.added,
        },
      ]);
      setLastLoadType(`Processed unmatched (week ${week})`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runAgentAdjustments = async () => {
    setAgentError(null);
    setPendingAction("Running news/matchup agent...");
    try {
      const resp = await runAgent(season, week, slate, activeRunSelection.projectionRunId);
      setAgentStatus(resp);
      updateActiveRunSelection({
        projectionRunId: resp.projection_run_id ?? activeRunSelection.projectionRunId,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setAgentError(msg);
      setAgentStatus(null);
    } finally {
      setPendingAction(null);
    }
  };

  const refreshSymbolicRules = async () => {
    setSymbolicRulesLoading(true);
    setSymbolicRulesError(null);
    setSymbolicRulesStatus(null);
    setPendingAction("Refreshing symbolic rules...");
    try {
      const response = await fetchSymbolicRules({ include_disabled: true });
      setSymbolicRules(response.rows);
    } catch (err) {
      setSymbolicRulesError(err instanceof Error ? err.message : String(err));
    } finally {
      setSymbolicRulesLoading(false);
      setPendingAction(null);
    }
  };

  const saveSymbolicRule = async () => {
    setSymbolicRulesError(null);
    setSymbolicRulesStatus(null);
    if (!ruleForm.rule_id.trim()) {
      setSymbolicRulesError("rule_id is required.");
      return;
    }
    if (!ruleForm.rule_name.trim()) {
      setSymbolicRulesError("rule_name is required.");
      return;
    }
    let conditionJson: Record<string, unknown> = {};
    let actionJson: Record<string, unknown> = {};
    try {
      conditionJson = JSON.parse(ruleForm.condition_json || "{}");
      actionJson = JSON.parse(ruleForm.action_json || "{}");
    } catch (err) {
      setSymbolicRulesError(
        `Invalid JSON in condition/action: ${err instanceof Error ? err.message : String(err)}`
      );
      return;
    }

    setPendingAction("Saving symbolic rule...");
    try {
      const saved = await upsertSymbolicRule({
        rule_id: ruleForm.rule_id.trim(),
        rule_name: ruleForm.rule_name.trim(),
        rule_type: ruleForm.rule_type.trim().toLowerCase(),
        enabled: ruleForm.enabled,
        priority: Number(ruleForm.priority),
        version: Number(ruleForm.version),
        condition_json: conditionJson,
        action_json: actionJson,
      });
      setSymbolicRulesStatus(`Saved rule ${saved.rule_id}`);
      await refreshSymbolicRules();
    } catch (err) {
      setSymbolicRulesError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const editSymbolicRule = (rule: SymbolicRule) => {
    setRuleForm({
      rule_id: rule.rule_id,
      rule_name: rule.rule_name,
      rule_type: rule.rule_type,
      enabled: rule.enabled,
      priority: rule.priority,
      version: rule.version,
      condition_json: JSON.stringify(rule.condition_json ?? {}, null, 2),
      action_json: JSON.stringify(rule.action_json ?? {}, null, 2),
    });
  };

  const toggleSymbolicRule = async (rule: SymbolicRule) => {
    setSymbolicRulesError(null);
    setSymbolicRulesStatus(null);
    setPendingAction(`${rule.enabled ? "Disabling" : "Enabling"} ${rule.rule_id}...`);
    try {
      await setSymbolicRuleEnabled(rule.rule_id, !rule.enabled);
      setSymbolicRulesStatus(
        `${rule.rule_id} ${rule.enabled ? "disabled" : "enabled"}`
      );
      await refreshSymbolicRules();
    } catch (err) {
      setSymbolicRulesError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const runSymbolicBacktest = async () => {
    setSymbolicBacktestLoading(true);
    setSymbolicBacktestError(null);
    setPendingAction("Backtesting symbolic rules...");
    try {
      const response = await fetchSymbolicBacktest({ season, week, slate });
      setSymbolicBacktest(response);
    } catch (err) {
      setSymbolicBacktestError(err instanceof Error ? err.message : String(err));
      setSymbolicBacktest(null);
    } finally {
      setSymbolicBacktestLoading(false);
      setPendingAction(null);
    }
  };

  const runLoadOwnership = async () => {
    setOwnershipError(null);
    setPendingAction("Validating contest evidence...");
    try {
      const evidencePayload = buildOwnershipEvidencePayload(ownershipEvidence);
      setPendingAction("Loading ownership labels and contest evidence...");
      const resp = await loadOwnership({
        season,
        week,
        slate,
        path: ownershipPath.trim(),
        ...evidencePayload,
      });
      setOwnershipStatus({
        message: resp.message,
        rows_written: resp.rows_written,
        target_persisted: resp.target_persisted,
        contest_id: resp.contest_id,
        source_file_id: resp.source_file_id,
        evidence_posture: ownershipEvidencePosture,
      });
      const entryUser = learningEntryUser.trim();
      if (entryUser) {
        window.localStorage.setItem("dfs-learning-entry-user", entryUser);
        setPendingAction("Refreshing post-slate learning report...");
        try {
          setLearningReport(await generateSlateLearningReport({
            season,
            week,
            slate,
            entry_user: entryUser,
          }));
          setLearningError(null);
        } catch (learningFailure) {
          setLearningError(
            learningFailure instanceof Error
              ? learningFailure.message
              : String(learningFailure),
          );
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setOwnershipError(msg);
    } finally {
      setPendingAction(null);
    }
  };

  const runOwnershipPredict = async () => {
    setOwnershipError(null);
    setPendingAction("Running ownership model...");
    try {
      const resp = await runOwnershipModel({ season, week, slate });
      setOwnershipStatus(resp);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setOwnershipError(msg);
    } finally {
      setPendingAction(null);
    }
  };

  const runPastSlateAnalysis = async () => {
    setOwnershipError(null);
    setAnalysisStatus(null);
    setPendingAction("Analyzing past slate...");
    try {
      const resp = await analyzePastSlate({ season, week, slate, path: ownershipPath, top_n: analysisTopN });
      setAnalysisStatus(`${resp.message} (${resp.lineups} lineups)`);
      setAnalysisRows(resp.exposures.slice(0, 50));
      setBucketStats(resp.bucket_stats || []);
      setTopLineups(resp.top_lineups?.slice(0, analysisTopN) || []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setOwnershipError(msg);
      setAnalysisRows([]);
      setBucketStats([]);
      setTopLineups([]);
    } finally {
      setPendingAction(null);
    }
  };

  const runSlateLearningReport = async () => {
    const entryUser = learningEntryUser.trim();
    if (!entryUser) return;
    setLearningError(null);
    setPendingAction("Building post-slate learning report...");
    try {
      window.localStorage.setItem("dfs-learning-entry-user", entryUser);
      const report = await generateSlateLearningReport({
        season,
        week,
        slate,
        entry_user: entryUser,
      });
      setLearningReport(report);
    } catch (err) {
      setLearningError(err instanceof Error ? err.message : String(err));
      setLearningReport(null);
    } finally {
      setPendingAction(null);
    }
  };

  const loadUnmatched = async () => {
    setUnmatchedLoading(true);
    setUnmatchedError(null);
    setPendingAction("Fetching unmatched salaries...");
    try {
      const response = await fetchUnmatchedSalaries({ season, week, slate, limit: 50 });
      setUnmatchedRows(response.rows);
    } catch (err) {
      setUnmatchedError(err instanceof Error ? err.message : String(err));
    } finally {
      setUnmatchedLoading(false);
      setPendingAction(null);
    }
  };

  const loadUnmatchedInjuries = async () => {
    setUnmatchedInjuryLoading(true);
    setUnmatchedInjuryError(null);
    setPendingAction("Fetching unmatched injuries...");
    try {
      const response = await fetchUnmatchedInjuries({ season, week, slate, limit: 50 });
      setUnmatchedInjuryRows(response.rows);
    } catch (err) {
      setUnmatchedInjuryError(err instanceof Error ? err.message : String(err));
    } finally {
      setUnmatchedInjuryLoading(false);
      setPendingAction(null);
    }
  };

  if (viewMode === "digital-twin") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <DigitalTwin
          season={season}
          week={week}
          slate={slate}
          contestFormat={contestFormat}
          optimizerObjective={effectiveOptimizerObjective}
          optimizerStatus={optimizerStatus}
          projectionRunId={activeRunSelection.projectionRunId}
          onProjectionRunChange={setActiveProjectionRunId}
          onNavigate={setViewMode}
        />
      </AppShell>
    );
  }

  if (viewMode === "preview") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <DesignPreview onBack={() => setViewMode("war-room")} />
      </AppShell>
    );
  }

  if (viewMode === "news-brief") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <DailyNewsBrief onBack={() => setViewMode("war-room")} />
      </AppShell>
    );
  }

  if (viewMode === "contest-workflow") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <ContestWorkflow
          season={season}
          week={week}
          slate={slate}
          slateOptions={SLATE_OPTIONS}
          optimizerRunId={activeRunSelection.optimizerRunId}
          onOptimizerRunIdChange={setActiveOptimizerRunId}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          onSlateChange={setActiveSlate}
          onOpenModelWorkbench={() => setViewMode("model-workbench")}
          onOpenOperations={() => setViewMode("workspace")}
        />
      </AppShell>
    );
  }

  if (viewMode === "model-workbench") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <ModelWorkbench
          season={season}
          week={week}
          slate={slate}
          slateOptions={SLATE_OPTIONS}
          projectionRunId={activeRunSelection.projectionRunId}
          onProjectionRunChange={setActiveProjectionRunId}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          onSlateChange={setActiveSlate}
          onOpenWarRoom={() => setViewMode("war-room")}
          onOpenOperations={() => setViewMode("workspace")}
          onOpenContestWorkflow={() => setViewMode("contest-workflow")}
        />
      </AppShell>
    );
  }

  if (viewMode === "war-room") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <WarRoom
          season={season}
          week={week}
          slate={slate}
          slateOptions={SLATE_OPTIONS}
          pendingAction={pendingAction}
          optimizerStatus={optimizerStatus}
          projectionRunId={activeRunSelection.projectionRunId}
          onProjectionRunChange={setActiveProjectionRunId}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          onSlateChange={setActiveSlate}
          onOpenOperations={() => setViewMode("workspace")}
          onOpenModelWorkbench={() => setViewMode("model-workbench")}
          onOpenBrief={() => setViewMode("news-brief")}
          onOpenPreview={() => setViewMode("preview")}
        />
      </AppShell>
    );
  }

  if (viewMode === "research") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <ResearchWorkspace
          season={season}
          week={week}
          slate={slate}
          slateOptions={SLATE_OPTIONS}
          selectedSimulationRunId={activeRunSelection.researchSimulationRunId ?? ""}
          selectedBaselineRunId={activeRunSelection.researchBaselineRunId ?? ""}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          onSlateChange={setActiveSlate}
          onSelectedSimulationRunIdChange={setActiveResearchSimulationRunId}
          onSelectedBaselineRunIdChange={setActiveResearchBaselineRunId}
        />
      </AppShell>
    );
  }

  return (
    <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
      <div className="operations-workspace">
      <section className="operations-command" aria-labelledby="operations-command-title">
        <div className="operations-command-copy">
          <span className="operations-eyebrow"><i aria-hidden="true" /> Live pipeline</span>
          <h2 id="operations-command-title">Prepare. Project. Generate.</h2>
          <p>
            Move the active slate from raw inputs to validated, upload-ready lineups.
          </p>
        </div>
        <div className="operations-context" aria-label="Active slate controls">
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
              min={1}
              max={25}
              value={week}
              onChange={(event) => setWeek(Number(event.target.value))}
            />
          </label>
          <div className="operations-context-slate">
            <span>Active slate</span>
            <strong>{slate.replaceAll("_", " ")}</strong>
          </div>
        </div>
      </section>

      <section className="panel operations-panel weekly-run-panel" aria-labelledby="weekly-run-title">
        <div className="operations-panel-heading">
          <span>Weekly control</span>
          <h2 id="weekly-run-title">Resumable decision chain</h2>
          <p>Queue all eight stages on the durable worker. Completed stage writes are reused after a retry.</p>
        </div>
        <div className="weekly-run-launch">
          <label>
            DraftKings directory <small>Optional ingest</small>
            <input
              value={weeklyDirectory}
              onChange={(event) => setWeeklyDirectory(event.target.value)}
              placeholder="~/Downloads"
            />
          </label>
          <label>
            Entry template ID <small>Optional when directory contains one</small>
            <input
              value={weeklyTemplateId}
              onChange={(event) => setWeeklyTemplateId(event.target.value)}
              placeholder="template_..."
            />
          </label>
          <button
            className="operations-primary-action"
            onClick={launchWeeklyRun}
            disabled={pendingAction !== null || (!weeklyDirectory.trim() && !weeklyTemplateId.trim())}
          >
            Run Weekly Pipeline
          </button>
        </div>
        {weeklyRunError && <div className="error inline-error">{weeklyRunError}</div>}
        {weeklyRuns.length === 0 ? (
          <p className="placeholder">No weekly workflow has been queued for this slate.</p>
        ) : (() => {
          const run = weeklyRuns[0];
          const queueJob = operationalJobs.find(
            (job) => job.job_id === run.operational_job_id,
          );
          return (
            <div className="weekly-run-detail">
              <div className="weekly-run-summary">
                <div>
                  <span>{run.status} · {run.current_stage.replaceAll("_", " ")}</span>
                  <strong>{run.progress_current}/{run.progress_total} stages · {run.progress_percent.toFixed(0)}%</strong>
                  <small>{run.warning_count} warnings · {run.error_count} errors · run {run.weekly_run_id.slice(0, 12)}</small>
                </div>
                {run.status === "failed" && queueJob?.status === "failed" && (
                  <button onClick={() => retryFailedWeeklyRun(run.weekly_run_id)} disabled={pendingAction !== null}>
                    Resume Failed Stage
                  </button>
                )}
                {run.status === "failed" && queueJob?.status === "queued" && (
                  <small>Automatic retry queued</small>
                )}
              </div>
              <div className="scroll-table">
                <table className="compact-table weekly-stage-table">
                  <thead>
                    <tr><th>Stage</th><th>Status</th><th>Attempt</th><th>Counts</th><th>Artifacts</th><th>Latest detail</th></tr>
                  </thead>
                  <tbody>
                    {run.stages.map((stage) => {
                      const detail = stage.errors[0]
                        ?? stage.warnings[0]
                        ?? stage.logs[stage.logs.length - 1]
                        ?? stage.message
                        ?? "Waiting";
                      return (
                        <tr key={`${run.weekly_run_id}-${stage.stage}`}>
                          <td>{stage.stage}</td>
                          <td className={`status-${stage.status}`}>{stage.status}</td>
                          <td>{stage.attempt_count}</td>
                          <td title={JSON.stringify(stage.counts)}>{compactTelemetry(stage.counts)}</td>
                          <td title={JSON.stringify(stage.artifact_ids)}>{compactTelemetry(stage.artifact_ids)}</td>
                          <td title={detail}>{detail}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })()}
      </section>

      <div className="operations-grid">
        <section className="panel operations-panel operations-data-panel">
          <div className="operations-panel-heading">
            <span>01 · Ingest</span>
            <h2>Data + feature build</h2>
            <p>Load source data, attach contest evidence, and assemble model-ready features.</p>
          </div>
          {loadError && <div className="error inline-error">{loadError}</div>}
          <div className="button-row operations-action-grid">
            <button disabled={loading} onClick={() => runLoad("season")}>
              Load Raw Season
            </button>
            <button disabled={loading} onClick={runLoadRawStats}>
              Load Raw Weekly Stats
            </button>
            <button disabled={loading} onClick={runLoadRawRosters}>
              Load Raw Weekly Rosters
            </button>
            <button onClick={() => runBuildFeatures("all")}>Build Features (All)</button>
            <button onClick={() => runBuildFeatures("current")}>Build Features (Season/Week)</button>
            <button onClick={runBuildFutureFeatures} disabled={futureWeek === ""}>
              Build Features (Future Week)
            </button>
          </div>
          <div className="form-row column">
            <label>
              Salary file
              <input
                className="full-width"
                type="text"
                value={salaryPath}
                onChange={(event) => setSalaryPath(event.target.value)}
                placeholder="~/Downloads/DKSalaries.csv"
              />
            </label>
            <button onClick={runLoadRawSalaries}>Load Raw Salaries (CSV)</button>
          </div>
          <div className="form-row column">
            <label>
              Injury file
              <input
                className="full-width"
                type="text"
                value={injuryPath}
                onChange={(event) => setInjuryPath(event.target.value)}
                placeholder="~/Downloads/Injuries.csv"
              />
            </label>
            <button onClick={runLoadRawInjuries}>Load Raw Injuries (CSV)</button>
          </div>
          <div className="form-row column">
            <label>
              Ownership file
              <input
                className="full-width"
                type="text"
                value={ownershipPath}
                onChange={(event) => setOwnershipPath(event.target.value)}
                placeholder="~/Downloads/ownership.csv"
              />
            </label>
            <details className="contest-evidence-editor">
              <summary>
                <span>
                  <strong>Contest evidence</strong>
                  <small>Optional metadata for defensible replay</small>
                </span>
                <span className={`evidence-posture ${ownershipEvidenceTone}`}>
                  {ownershipEvidencePosture}
                </span>
              </summary>
              <div className="contest-evidence-body">
                <p>
                  Generic standings files remain field proxies. Supply an explicit contest type
                  and payout structure only when you have authoritative contest details.
                </p>
                <div className="contest-evidence-grid">
                  <label>
                    DraftKings contest ID
                    <input
                      type="text"
                      value={ownershipEvidence.contestId}
                      onChange={(event) => updateOwnershipEvidence("contestId", event.target.value)}
                      placeholder="Optional external ID"
                    />
                  </label>
                  <label>
                    Contest name
                    <input
                      type="text"
                      value={ownershipEvidence.contestName}
                      onChange={(event) => updateOwnershipEvidence("contestName", event.target.value)}
                      placeholder="NFL $5 Double Up"
                    />
                  </label>
                  <label>
                    Format
                    <select
                      value={ownershipEvidence.contestFormat}
                      onChange={(event) => updateOwnershipEvidence(
                        "contestFormat",
                        event.target.value as OwnershipEvidenceDraft["contestFormat"],
                      )}
                    >
                      <option value="">Auto-detect from roster</option>
                      <option value="classic">Classic</option>
                      <option value="showdown">Showdown</option>
                    </select>
                  </label>
                  <label>
                    Contest type
                    <select
                      value={ownershipEvidence.contestType}
                      onChange={(event) => updateOwnershipEvidence(
                        "contestType",
                        event.target.value as OwnershipEvidenceDraft["contestType"],
                      )}
                    >
                      <option value="">Unknown · field proxy</option>
                      <option value="cash">Cash</option>
                      <option value="gpp">GPP</option>
                    </select>
                  </label>
                  <label>
                    Entry fee
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={ownershipEvidence.entryFee}
                      onChange={(event) => updateOwnershipEvidence("entryFee", event.target.value)}
                      placeholder="5.00"
                    />
                  </label>
                  <label>
                    Field size
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={ownershipEvidence.fieldSize}
                      onChange={(event) => updateOwnershipEvidence("fieldSize", event.target.value)}
                      placeholder="Observed rows by default"
                    />
                  </label>
                  <label>
                    Max entries per user
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={ownershipEvidence.maxEntriesPerUser}
                      onChange={(event) => updateOwnershipEvidence(
                        "maxEntriesPerUser",
                        event.target.value,
                      )}
                      placeholder="1"
                    />
                  </label>
                  <label>
                    Prize pool
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={ownershipEvidence.prizePool}
                      onChange={(event) => updateOwnershipEvidence("prizePool", event.target.value)}
                      placeholder="Optional total"
                    />
                  </label>
                </div>
                <div className="payout-tier-heading">
                  <span>
                    <strong>Payout tiers</strong>
                    <small>Rank ranges must be complete, non-overlapping evidence.</small>
                  </span>
                  <button
                    type="button"
                    className="evidence-tier-button"
                    onClick={addOwnershipPayoutTier}
                  >
                    Add payout tier
                  </button>
                </div>
                {ownershipEvidence.payoutTiers.length === 0 ? (
                  <div className="payout-tier-empty">
                    No payout tiers supplied. Cash-line and ROI outputs will remain unavailable.
                  </div>
                ) : (
                  <div className="payout-tier-list">
                    {ownershipEvidence.payoutTiers.map((tier, index) => (
                      <div className="payout-tier-row" key={`ownership-tier-${index}`}>
                        <label>
                          Min rank
                          <input
                            type="number"
                            aria-label={`Tier ${index + 1} minimum rank`}
                            min="1"
                            step="1"
                            value={tier.minRank}
                            onChange={(event) => updateOwnershipPayoutTier(
                              index,
                              "minRank",
                              event.target.value,
                            )}
                          />
                        </label>
                        <label>
                          Max rank
                          <input
                            type="number"
                            aria-label={`Tier ${index + 1} maximum rank`}
                            min="1"
                            step="1"
                            value={tier.maxRank}
                            onChange={(event) => updateOwnershipPayoutTier(
                              index,
                              "maxRank",
                              event.target.value,
                            )}
                          />
                        </label>
                        <label>
                          Payout
                          <input
                            type="number"
                            aria-label={`Tier ${index + 1} payout`}
                            min="0"
                            step="0.01"
                            value={tier.payout}
                            onChange={(event) => updateOwnershipPayoutTier(
                              index,
                              "payout",
                              event.target.value,
                            )}
                          />
                        </label>
                        <label className="payout-description">
                          Prize description
                          <input
                            type="text"
                            aria-label={`Tier ${index + 1} prize description`}
                            value={tier.prizeDescription}
                            onChange={(event) => updateOwnershipPayoutTier(
                              index,
                              "prizeDescription",
                              event.target.value,
                            )}
                            placeholder="Optional ticket or award"
                          />
                        </label>
                        <button
                          type="button"
                          className="evidence-tier-remove"
                          onClick={() => removeOwnershipPayoutTier(index)}
                          aria-label={`Remove payout tier ${index + 1}`}
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </details>
            <div className="button-row">
              <button
                onClick={runLoadOwnership}
                disabled={!ownershipPath.trim() || pendingAction !== null}
              >
                Load Ownership (Past Slate)
              </button>
              <button onClick={runOwnershipPredict}>Run Ownership Model</button>
            </div>
            {ownershipError && <div className="error inline-error">{ownershipError}</div>}
            {ownershipStatus && (
              <div className="status-text">
                {ownershipStatus.message} ({ownershipStatus.rows_written} rows)
                {ownershipStatus.contest_id && (
                  <small>
                    Contest {ownershipStatus.contest_id.slice(0, 18)} · {ownershipStatus.evidence_posture}
                    {ownershipStatus.target_persisted ? " · target evidence persisted" : " · target persistence unavailable"}
                  </small>
                )}
                {ownershipMetricSummary(ownershipStatus) && <small>{ownershipMetricSummary(ownershipStatus)}</small>}
                {ownershipStatus.ownership_run_id && <small>Run {ownershipStatus.ownership_run_id.slice(0, 8)} · target lineage {ownershipStatus.target_persisted ? "persisted" : "unavailable"}</small>}
              </div>
            )}
            <div className="button-row">
              <label>
                Top N lineups
                <input
                  type="number"
                  min={10}
                  max={500}
                  value={analysisTopN}
                  onChange={(e) => setAnalysisTopN(Number(e.target.value))}
                />
              </label>
              <button onClick={runPastSlateAnalysis}>Analyze Past Slate (Top N)</button>
            </div>
            <div className="form-row column">
              <label>
                DraftKings username
                <input
                  className="full-width"
                  type="text"
                  value={learningEntryUser}
                  onChange={(event) => setLearningEntryUser(event.target.value)}
                  placeholder="Username used in contest standings"
                />
              </label>
              <button
                onClick={runSlateLearningReport}
                disabled={!learningEntryUser.trim() || pendingAction !== null}
              >
                Build Post-Slate Learning Report
              </button>
            </div>
            {learningError && <div className="error inline-error">{learningError}</div>}
            {learningReport && (
              <div className="status-card">
                <strong>
                  Learning report: {learningReport.status} · {learningReport.summary.entries} entries
                </strong>
                <p>
                  {learningReport.summary.matched_optimizer_entries} optimizer matches ·{" "}
                  {learningReport.summary.entries_with_opt_007} OPT-007 controls ·{" "}
                  {learningReport.summary.duplicate_entries} duplicate entries
                </p>
                <p>
                  Projection MAE: {learningReport.summary.projection_mae == null
                    ? "Unavailable"
                    : learningReport.summary.projection_mae.toFixed(2)} ·{" "}
                  {learningReport.missing_evidence.length} missing-evidence notices
                </p>
                {learningReport.portfolio_analysis.captain_exposure?.length ? (
                  <p>
                    Captain exposure: {learningReport.portfolio_analysis.captain_exposure
                      .map((row) => `${row.player_display_name} ${row.pct.toFixed(0)}%`)
                      .join(" · ")}
                  </p>
                ) : null}
                <details className="learning-interpretation" open>
                  <summary>How to read this report each week</summary>
                  <ol>
                    <li><strong>Check evidence first.</strong> Partial means some lineage, fee, payout, belief, or control evidence is missing; it does not mean the slate performed poorly.</li>
                    <li><strong>Read finishes as percentiles.</strong> A smaller top percentage is better. Compare similar contest formats and field sizes before drawing a conclusion.</li>
                    <li><strong>Track projection MAE over several slates.</strong> It is the average player-level miss in DraftKings points; lower is better, but one slate is noisy.</li>
                    <li><strong>Check optimizer matches.</strong> Only matched entries can explain which projection, rules, controls, and saved lineup produced the result.</li>
                    <li><strong>Review construction.</strong> Duplicate entries and concentrated captain exposure identify portfolio decisions that can be improved independently of player outcomes.</li>
                  </ol>
                </details>
                <div className="learning-outcome-summary">
                  <strong>Human learning</strong>
                  <p>
                    Belief theses: {learningReport.learning_outcomes.beliefs.supported} supported · {learningReport.learning_outcomes.beliefs.contradicted} contradicted · {learningReport.learning_outcomes.beliefs.theses_scored} scored
                  </p>
                  <p>
                    Recorded interventions: {learningReport.learning_outcomes.beliefs.helped + learningReport.learning_outcomes.agent_answers.helped} helped · {learningReport.learning_outcomes.beliefs.hurt + learningReport.learning_outcomes.agent_answers.hurt} hurt · {learningReport.learning_outcomes.beliefs.no_measurable_effect + learningReport.learning_outcomes.agent_answers.no_measurable_effect} no measurable effect
                  </p>
                  {learningReport.learning_outcomes.beliefs.total === 0 && learningReport.learning_outcomes.agent_answers.total === 0 && (
                    <small>No pre-lock beliefs or LEARN-002 answers were recorded for this slate, so human judgment cannot be scored yet.</small>
                  )}
                </div>
                {(learningReport.beliefs.length > 0 || learningReport.agent_questions.length > 0) && (
                  <details className="learning-decision-results">
                    <summary>Review belief and question outcomes</summary>
                    <ul>
                      {learningReport.beliefs.map((belief, index) => (
                        <li key={String(belief.belief_version_id ?? index)}>
                          Belief · {String(belief.thought_text ?? belief.subject_id ?? "Unknown subject")} · {String(belief.scope_type ?? "unknown")} · confidence {String(belief.confidence ?? "—")}% · thesis {String(belief.evaluation ?? "unscored").replaceAll("_", " ")} · intervention {String(belief.outcome_effect ?? "unscored").replaceAll("_", " ")}
                        </li>
                      ))}
                      {learningReport.agent_questions.map((question, index) => (
                        <li key={String(question.question_id ?? index)}>
                          Question · {String(question.subject_label ?? question.subject_player_id ?? "Unknown subject")} · {String(question.answer ?? "unanswered").replaceAll("_", " ")} · {String(question.outcome_effect ?? "unscored").replaceAll("_", " ")}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {learningReport.entries.length > 0 && (
                  <details className="learning-entry-results">
                    <summary>Review entry finishes</summary>
                    <ul>
                      {learningReport.entries.map((entry, index) => {
                        const rank = typeof entry.rank === "number" ? entry.rank : null;
                        const fieldSize = typeof entry.field_size === "number" ? entry.field_size : null;
                        const topPercent = typeof entry.top_percent === "number" ? entry.top_percent : null;
                        return (
                          <li key={String(entry.entry_id ?? index)}>
                            {rank != null && fieldSize != null ? `${rank.toLocaleString()} / ${fieldSize.toLocaleString()}` : "Rank unavailable"}
                            {topPercent != null ? ` · top ${topPercent.toFixed(2)}%` : ""}
                            {entry.lineup_match_basis ? ` · ${String(entry.lineup_match_basis).replaceAll("_", " ")}` : ""}
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                )}
                {learningReport.missing_evidence.length > 0 && (
                  <details>
                    <summary>Review missing evidence</summary>
                    <ul>
                      {learningReport.missing_evidence.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </details>
                )}
                <small>Report {learningReport.report_id}</small>
              </div>
            )}
          </div>
          <div className="form-row">
            <label>
              Future Week
              <input
                type="number"
                min={1}
                max={25}
                value={futureWeek}
                onChange={(event) => setFutureWeek(event.target.value === "" ? "" : Number(event.target.value))}
              />
            </label>
            <button onClick={runAgentAdjustments}>Run News/Matchup Agent</button>
          </div>
          {featureStatus && (
            <div className="status-text">
              {featureStatus.message}
            </div>
          )}
          {analysisStatus && (
            <div className="status-text">
              {analysisStatus}
            </div>
          )}
          {agentError && <div className="error inline-error">{agentError}</div>}
          {agentStatus && (
            <div className="status-card">
              <h3>Agent</h3>
              <p>Rule run: {agentStatus.rule_run_id}</p>
              <p>Adjusted rows: {agentStatus.adjusted_rows}</p>
              <p>Trace rows: {agentStatus.trace_rows}</p>
              {agentStatus.adjustments.length === 0 ? (
                <p>No player-level adjustments recorded.</p>
              ) : (
                <div className="scroll-table">
                  <table className="compact-table">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Reason</th>
                        <th>ΔProj</th>
                        <th>ΔCeil</th>
                      </tr>
                    </thead>
                    <tbody>
                      {agentStatus.adjustments.slice(0, 20).map((adj, idx) => (
                        <tr key={`${adj.player_id}-${idx}`}>
                          <td>{adj.player_id}</td>
                          <td>{adj.reason}</td>
                          <td>{Number(adj.projection_delta || 0).toFixed(4)}</td>
                          <td>{Number(adj.ceiling_delta || 0).toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {agentStatus.traces.length > 0 && (
                <div className="scroll-table">
                  <table className="compact-table">
                    <thead>
                      <tr>
                        <th>Rule</th>
                        <th>Player</th>
                        <th>Reason</th>
                        <th>Mean Before</th>
                        <th>Mean After</th>
                        <th>P90 Before</th>
                        <th>P90 After</th>
                      </tr>
                    </thead>
                    <tbody>
                      {agentStatus.traces.slice(0, 40).map((trace, idx) => (
                        <tr key={`${trace.rule_id}-${trace.player_id}-${idx}`}>
                          <td>{trace.rule_id}</td>
                          <td>{trace.player_id}</td>
                          <td>{trace.reason}</td>
                          <td>{Number(trace.mean_before || 0).toFixed(2)}</td>
                          <td>{Number(trace.mean_after || 0).toFixed(2)}</td>
                          <td>{Number(trace.p90_before || 0).toFixed(2)}</td>
                          <td>{Number(trace.p90_after || 0).toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
          <div className="status-card">
            <h3>Symbolic Rules</h3>
            <div className="button-row">
              <button onClick={refreshSymbolicRules} disabled={symbolicRulesLoading}>
                {symbolicRulesLoading ? "Refreshing..." : "Refresh Rules"}
              </button>
              <button onClick={saveSymbolicRule}>Save Rule</button>
              <button onClick={runSymbolicBacktest} disabled={symbolicBacktestLoading}>
                {symbolicBacktestLoading ? "Backtesting..." : "Backtest Rules"}
              </button>
            </div>
            <div className="form-row column">
              <label>
                Rule ID
                <input
                  className="full-width"
                  type="text"
                  value={ruleForm.rule_id}
                  onChange={(event) =>
                    setRuleForm((prev) => ({ ...prev, rule_id: event.target.value }))
                  }
                  placeholder="matchup_pass_boost"
                />
              </label>
              <label>
                Rule Name
                <input
                  className="full-width"
                  type="text"
                  value={ruleForm.rule_name}
                  onChange={(event) =>
                    setRuleForm((prev) => ({ ...prev, rule_name: event.target.value }))
                  }
                  placeholder="Pass Funnel/Pace Boost"
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                Rule Type
                <select
                  value={ruleForm.rule_type}
                  onChange={(event) =>
                    setRuleForm((prev) => ({ ...prev, rule_type: event.target.value }))
                  }
                >
                  <option value="injury">injury</option>
                  <option value="matchup">matchup</option>
                </select>
              </label>
              <label>
                Priority
                <input
                  type="number"
                  value={ruleForm.priority}
                  onChange={(event) =>
                    setRuleForm((prev) => ({ ...prev, priority: Number(event.target.value) }))
                  }
                />
              </label>
              <label>
                Version
                <input
                  type="number"
                  min={1}
                  value={ruleForm.version}
                  onChange={(event) =>
                    setRuleForm((prev) => ({ ...prev, version: Number(event.target.value) }))
                  }
                />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={ruleForm.enabled}
                  onChange={(event) =>
                    setRuleForm((prev) => ({ ...prev, enabled: event.target.checked }))
                  }
                />
                Enabled
              </label>
            </div>
            <div className="form-row column">
              <label>
                Condition JSON
                <textarea
                  className="full-width"
                  rows={4}
                  value={ruleForm.condition_json}
                  onChange={(event) =>
                    setRuleForm((prev) => ({ ...prev, condition_json: event.target.value }))
                  }
                />
              </label>
              <label>
                Action JSON
                <textarea
                  className="full-width"
                  rows={4}
                  value={ruleForm.action_json}
                  onChange={(event) =>
                    setRuleForm((prev) => ({ ...prev, action_json: event.target.value }))
                  }
                />
              </label>
            </div>
            {symbolicRulesError && <div className="error inline-error">{symbolicRulesError}</div>}
            {symbolicRulesStatus && <div className="status-text">{symbolicRulesStatus}</div>}
            {symbolicBacktestError && <div className="error inline-error">{symbolicBacktestError}</div>}
            {symbolicBacktest && (
              <div className="status-card nested-card">
                <h3>Symbolic Backtest</h3>
                <p>
                  Rows: {symbolicBacktest.overall.rows} | Base MAE:{" "}
                  {Number(symbolicBacktest.overall.base_mae || 0).toFixed(2)} | Adjusted MAE:{" "}
                  {Number(symbolicBacktest.overall.adjusted_mae || 0).toFixed(2)} | Delta:{" "}
                  {Number(symbolicBacktest.overall.mae_delta || 0).toFixed(2)} | Hit Rate:{" "}
                  {(Number(symbolicBacktest.overall.hit_rate || 0) * 100).toFixed(1)}%
                </p>
                {symbolicBacktest.by_rule.length > 0 ? (
                  <div className="scroll-table">
                    <table className="compact-table">
                      <thead>
                        <tr>
                          <th>Rule</th>
                          <th>Rows</th>
                          <th>Base MAE</th>
                          <th>Adjusted MAE</th>
                          <th>Delta</th>
                          <th>Hit Rate</th>
                        </tr>
                      </thead>
                      <tbody>
                        {symbolicBacktest.by_rule.map((row) => (
                          <tr key={row.rule_id}>
                            <td>{row.rule_id}</td>
                            <td>{row.rows}</td>
                            <td>{Number(row.base_mae || 0).toFixed(2)}</td>
                            <td>{Number(row.adjusted_mae || 0).toFixed(2)}</td>
                            <td>{Number(row.mae_delta || 0).toFixed(2)}</td>
                            <td>{(Number(row.hit_rate || 0) * 100).toFixed(1)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p>No rule-level backtest rows matched the selected context yet.</p>
                )}
              </div>
            )}
            <div className="scroll-table">
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Rule ID</th>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Priority</th>
                    <th>Version</th>
                    <th>Enabled</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {symbolicRules.map((rule) => (
                    <tr key={rule.rule_id}>
                      <td>{rule.rule_id}</td>
                      <td>{rule.rule_name}</td>
                      <td>{rule.rule_type}</td>
                      <td>{rule.priority}</td>
                      <td>{rule.version}</td>
                      <td>{rule.enabled ? "yes" : "no"}</td>
                      <td>
                        <div className="button-row">
                          <button onClick={() => editSymbolicRule(rule)}>Edit</button>
                          <button onClick={() => toggleSymbolicRule(rule)}>
                            {rule.enabled ? "Disable" : "Enable"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <div className="operations-side-stack">
        <section className="panel operations-panel operations-utility-panel">
          <div className="operations-panel-heading">
            <span>System</span>
            <h2>Local services</h2>
            <p>Keep the development data layer available.</p>
          </div>
          <div className="button-row operations-action-grid">
            <button onClick={runStartPostgres} disabled={postgresLoading}>
              {postgresLoading ? "Starting..." : "Start PostgreSQL"}
            </button>
          </div>
          {postgresError && <div className="error inline-error">{postgresError}</div>}
          {postgresStatus && (
            <div className="status-card">
              <h3>PostgreSQL</h3>
              <p>{postgresStatus.message}</p>
              {postgresDetails && <pre>{postgresDetails}</pre>}
            </div>
          )}
        </section>

        <section className="panel operations-panel operations-slate-panel">
          <div className="operations-panel-heading">
            <span>02 · Configure</span>
            <h2>Slate inputs</h2>
            <p>Confirm the contest window and load its player context.</p>
          </div>
          <div className="form-row">
            <label>
              Slate
              <select
                value={slate}
                onChange={(event) => setActiveSlate(event.target.value)}
              >
                {SLATE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="button-row operations-action-grid">
            <button onClick={() => runSlateLoad("salaries")}>Load Salaries</button>
            <button onClick={() => runSlateLoad("injuries")}>Load Injuries</button>
            <button onClick={runStartingQBs}>Load Starting QBs</button>
          </div>
          {startingQBStatus && (
            <div className="status-text">
              {startingQBStatus.message} ({startingQBStatus.rows_written} rows)
            </div>
          )}
        </section>
        </div>
      </div>

      <section className="panel wide operations-panel operations-model-panel">
        <div className="optimizer-grid">
          <div className="subpanel operations-projection-panel">
            <div className="operations-panel-heading">
              <span>03 · Model</span>
              <h2>Player projections</h2>
            </div>
            <p className="helper-text">
              Uses all loaded weeks in the season to predict the selected week (future weeks OK).
            </p>
            <div className="button-row">
              <button className="operations-primary-action" onClick={runPredictionJob}>Run Projections</button>
              <button onClick={runSimulationJob} disabled={contestFormat !== "classic"}>Run Simulation</button>
            </div>
            {predictionStatus && (
              <div className="status-text">
                {predictionStatus.message} ({predictionStatus.rows_written} rows)
              </div>
            )}
            {simulationStatus && (
              <div className="status-text">
                {simulationStatus.message} · {simulationStatus.simulation_run_id}
              </div>
            )}
          </div>

          <div className="subpanel operations-optimizer-panel">
            <div className="operations-panel-heading">
              <span>04 · Generate</span>
              <h2>Portfolio optimizer</h2>
              <p>Shape lineup volume, exposure, format, and objective before the build.</p>
            </div>
            <div className="form-row">
              {!(contestFormat === "showdown" && optimizerObjective === "gpp" && showdownGppStrategy !== SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID) ? <label>
                Lineups
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={numLineups}
                  onChange={(event) => setNumLineups(Number(event.target.value))}
                />
              </label> : <p>{showdownGppStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID ? "1 single-entry contest" : "Contest count selected from pasted single-entry contests"}</p>}
              {contestFormat === "classic" && <label>
                Max Exposure (%)
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={maxExposure}
                  onChange={(event) => setMaxExposure(Number(event.target.value))}
                />
              </label>}
              <label>
                Format
                <select
                  value={contestFormat}
                  onChange={(event) => {
                    const next = event.target.value as "classic" | "showdown";
                    setContestFormat(next);
                    if (next === "showdown") setNumLineups(5);
                  }}
                >
                  <option value="classic">Classic</option>
                  <option value="showdown">Showdown</option>
                </select>
              </label>
              {contestFormat === "showdown" && (
                <label>
                  Objective
                  <select
                    value={optimizerObjective}
                    onChange={(event) => setOptimizerObjective(event.target.value as "cash" | "gpp")}
                  >
                    <option value="gpp">GPP</option>
                    <option value="cash">Cash</option>
                  </select>
                </label>
              )}
            </div>
            {contestFormat === "showdown" && optimizerObjective === "gpp" && (
              <div className="form-row">
                <label>Showdown GPP strategy
                  <select value={showdownGppStrategy} onChange={(event) => setShowdownGppStrategy(event.target.value)}>
                    <option value={SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID}>Multi-entry GPP portfolio</option>
                    <option value={SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID}>Single-entry GPP</option>
                    <option value={SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID}>Single-entry contest portfolio</option>
                  </select>
                </label>
              </div>
            )}
            {contestFormat === "showdown" && optimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID && (
              <div className="status-card nested-card">
                <h3>Available single-entry contests</h3>
                <label>DraftKings contest URLs, one per line
                  <textarea className="full-width" rows={4} value={singleEntryContestUrls} onChange={(event) => { setSingleEntryContestUrls(event.target.value); setContestPreview(null); }} placeholder="https://www.draftkings.com/draft/contest/195677817" />
                </label>
                <div className="form-row">
                  <label>Contest selection
                    <select value={singleEntryContestMode} onChange={(event) => setSingleEntryContestMode(event.target.value as "auto" | "enter_all")}>
                      <option value="auto">Auto</option><option value="enter_all">Enter all</option>
                    </select>
                  </label>
                  <label>Maximum total entry budget ($, optional)<input type="number" min={0.01} step={0.01} value={singleEntryBudget} onChange={(event) => setSingleEntryBudget(event.target.value)} /></label>
                  <label>Maximum contests to enter (optional)<input type="number" min={1} step={1} value={singleEntryMaximum} onChange={(event) => setSingleEntryMaximum(event.target.value)} /></label>
                </div>
                <button disabled={contestPreviewPending} onClick={async () => {
                  setContestPreviewPending(true); setContestPreviewError(null);
                  try {
                    const params = singleEntryContestParams();
                    setContestPreview(await previewOptimizerContests({ urls: params.contest_urls, manual_contest_metadata: params.manual_contest_metadata }));
                  } catch (error) { setContestPreviewError(error instanceof Error ? error.message : String(error)); }
                  finally { setContestPreviewPending(false); }
                }}>{contestPreviewPending ? "Refreshing contests…" : "Preview / refresh contest details"}</button>
                {contestPreviewError && <p role="alert">{contestPreviewError}</p>}
                {contestPreview && <div className="table-wrap"><p>Refreshed {new Date(contestPreview.refreshed_at).toLocaleString()}. Counts and potential overlay can change before lock.</p><table><thead><tr><th>Contest</th><th>Slate</th><th>Single entry</th><th>Entry</th><th>Filled / capacity</th><th>Pool</th><th>Paid</th><th>Lock</th><th>Payout tiers</th><th>Missing fields / error</th></tr></thead><tbody>{contestPreview.contests.map((row) => <tr key={String(row.contest_id)}><td>{String(row.name ?? row.contest_id)}</td><td>{String(row.slate ?? "—")}</td><td>{row.single_entry === true ? "Yes" : row.single_entry === false ? "No" : "—"}</td><td>{row.entry_fee == null ? "—" : `$${row.entry_fee}`}</td><td>{String(row.current_entries ?? "—")} / {String(row.capacity ?? "—")}</td><td>{row.prize_pool == null ? "—" : `$${row.prize_pool}`}</td><td>{String(row.paid_places ?? "—")}</td><td>{String(row.lock_time ?? "—")}</td><td>{(row.payout_ladder as unknown[] | undefined)?.length ?? "—"}</td><td>{[...(row.unavailable_fields as string[] ?? []), ...(row.error ? [String(row.error)] : [])].join(", ") || "None"}</td></tr>)}</tbody></table>{contestPreview.contests.map((row) => <details key={`${row.contest_id}-payouts`}><summary>{String(row.name ?? row.contest_id)} payout ladder</summary><table><thead><tr><th>Ranks</th><th>Cash prize</th></tr></thead><tbody>{((row.payout_ladder as Array<Record<string, unknown>> | undefined) ?? []).map((tier, index) => <tr key={index}><td>{String(tier.from)}–{String(tier.to)}</td><td>{tier.cash == null ? "Unavailable" : `$${tier.cash}`}</td></tr>)}</tbody></table></details>)}</div>}
                <details><summary>Manual metadata for unavailable fields</summary><p>JSON array keyed by contest_id. The preview lists exactly which fields need correction. Refresh reruns the source lookup.</p><textarea className="full-width" rows={4} value={singleEntryManual} onChange={(event) => setSingleEntryManual(event.target.value)} placeholder='[{"contest_id":"195677817","entry_fee":5}]' /></details>
              </div>
            )}
            {contestFormat === "showdown" && optimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID && (
              <div className="form-row">
                <label>CPT max (%)<input ref={captainMaxExposureInputRef} type="number" min={1} max={100} value={captainMaxExposure} onChange={(event) => setCaptainMaxExposure(Number(event.target.value))} /></label>
                <label>Core max (%)<input type="number" min={1} max={100} value={coreMaxExposure} onChange={(event) => setCoreMaxExposure(Number(event.target.value))} /></label>
                <label>Starting QB max (%)<input type="number" min={1} max={100} value={startingQbMaxExposure} onChange={(event) => setStartingQbMaxExposure(Number(event.target.value))} /></label>
                <label>Cheap punt max (%)<input type="number" min={1} max={100} value={cheapPuntMaxExposure} onChange={(event) => setCheapPuntMaxExposure(Number(event.target.value))} /></label>
              </div>
            )}
            {contestFormat === "classic" && (
              <div className="form-row">
                <label>
                  Contest Strategy
                  <select
                    value={classicContestStrategy}
                    onChange={(event) => {
                      const next = event.target.value as ClassicContestStrategyId;
                      setClassicContestStrategy(next);
                      if (next === CLASSIC_LARGE_GPP_STRATEGY_ID) {
                        setNumLineups(20);
                        setMaxExposure(60);
                      } else {
                        setNumLineups(6);
                        setMaxExposure(100);
                      }
                    }}
                  >
                    {CLASSIC_CONTEST_STRATEGIES.map((strategy) => (
                      <option key={strategy.id} value={strategy.id}>
                        {strategy.label}
                      </option>
                    ))}
                  </select>
                  <small>
                    {selectedClassicStrategy.detail}
                  </small>
                </label>
              </div>
            )}
            {contestFormat === "classic" && classicContestStrategy === CLASSIC_LARGE_GPP_STRATEGY_ID && (
              <div className="form-row">
                <label>
                  Minimum uniqueness
                  <input type="number" min={1} max={9} value={minimumUniqueness}
                    onChange={(event) => setMinimumUniqueness(Number(event.target.value))} />
                </label>
                <label>
                  Max players / team
                  <input type="number" min={1} max={4} value={maxPlayersPerTeam}
                    onChange={(event) => setMaxPlayersPerTeam(Number(event.target.value))} />
                </label>
                <label>
                  Max players / game
                  <input type="number" min={1} max={9} value={maxPlayersPerGame}
                    onChange={(event) => setMaxPlayersPerGame(Number(event.target.value))} />
                </label>
              </div>
            )}
            {slateReadiness && (() => {
              const gateKey = optimizerReadinessGateKey(contestFormat, effectiveOptimizerObjective);
              const gate = slateReadiness.gates[gateKey];
              const attention = new Set(gate.attention_checks);
              const blocking = new Set(gate.blocking_checks);
              const checks = slateReadiness.checks
                .filter((check) => attention.has(check.check_id))
                .sort((left, right) => Number(blocking.has(right.check_id)) - Number(blocking.has(left.check_id)))
                .slice(0, 3);
              return (
                <div className={`readiness-preflight ${gate.status}`} role="status">
                  <div>
                    <span>Slate preflight · {contestFormat} {effectiveOptimizerObjective}</span>
                    <strong>{gate.status === "fail" ? "Blocked" : gate.status === "warn" ? "Ready with warnings" : "Ready"}</strong>
                    <small>{gate.score}/100 · {gate.message}</small>
                  </div>
                  {checks.length > 0 && (
                    <ul>
                      {checks.map((check) => <li key={check.check_id}>{check.message}</li>)}
                    </ul>
                  )}
                </div>
              );
            })()}
            <div className="form-row checkbox-row">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={enforceSingleTE}
                  onChange={(event) => setEnforceSingleTE(event.target.checked)}
                />
                Enforce single TE (no double-TE lineups)
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={avoidDstOpponents}
                  onChange={(event) => setAvoidDstOpponents(event.target.checked)}
                />
                No offense vs DST
              </label>
            </div>
            <div className="form-row optimizer-player-controls">
              <label className="text-label">
                Exclude players (comma-separated names)
                <input
                  type="text"
                  value={excludePlayers}
                  onChange={(event) => setExcludePlayers(event.target.value)}
                  placeholder="e.g. George Kittle, Skyy Moore"
                />
              </label>
              <label className="text-label">
                Exclude canonical player IDs
                <input
                  type="text"
                  value={excludePlayerIds}
                  onChange={(event) => setExcludePlayerIds(event.target.value)}
                  placeholder="Comma-separated player_master_id values"
                />
              </label>
              <label className="text-label">
                Lock canonical player IDs
                <input
                  type="text"
                  value={lockedPlayerIds}
                  onChange={(event) => setLockedPlayerIds(event.target.value)}
                  placeholder="Required in every lineup"
                />
              </label>
              {contestFormat === "showdown" && (
                <label className="text-label">
                  FLEX-only players (comma-separated names)
                  <input
                    type="text"
                    value={flexOnlyPlayers}
                    onChange={(event) => setFlexOnlyPlayers(event.target.value)}
                    placeholder="e.g. Malik Nabers"
                  />
                </label>
              )}
            </div>
            <div className="button-row">
              <button className="operations-primary-action" onClick={runOptimizerJob}>Run Optimizer</button>
              <button onClick={refreshOptimizer} disabled={!optimizerStatus}>
                Refresh Status
              </button>
            </div>
          </div>

        </div>
      </section>

      <div className="activity-wrapper">
        <section className="panel summary-panel unified activity-panel operations-panel operations-activity-panel">
          <div className="summary-header">
            <div className="operations-panel-heading">
              <span>05 · Review</span>
              <h2>Run activity</h2>
            </div>
            {lastLoadType && <span className="summary-subtitle">{lastLoadType}</span>}
          </div>
          {error && <div className="error inline-error">{error}</div>}
          {operationalJobs.length > 0 && (
            <div className="status-card">
              <h3>Durable worker queue</h3>
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Stage</th>
                    <th>Progress</th>
                    <th>Attempts</th>
                    <th>Run</th>
                  </tr>
                </thead>
                <tbody>
                  {operationalJobs.map((job) => (
                    <tr key={job.job_id}>
                      <td>{job.job_type.replaceAll("_", " ")}</td>
                      <td>{job.status}</td>
                      <td>{job.stage.replaceAll("_", " ")}</td>
                      <td title={job.progress_message ?? undefined}>
                        {job.progress_percent.toFixed(0)}%
                      </td>
                      <td>{job.attempt_count}/{job.max_attempts}</td>
                      <td title={job.run_id ?? job.job_id}>
                        {(job.run_id ?? job.job_id).slice(0, 12)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {loadSummaries.length > 0 && (
            <div className="status-card">
              <h3>Load Results</h3>
              {loadSummaries.some(
                (summary) =>
                  summary.rows_written === 0 && !String(summary.dataset || "").startsWith("unmatched")
              ) && (
                <div className="warning-text">
                  Some datasets returned 0 rows. This usually means the provider has no data for that season/week yet.
                </div>
              )}
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Season</th>
                    <th>Week</th>
                    <th>Rows</th>
                  </tr>
                </thead>
                <tbody>
                  {loadSummaries.map((summary) => (
                    <tr key={`${summary.dataset}-${summary.week ?? "season"}`}>
                      <td>{summary.dataset}</td>
                      <td>{summary.season}</td>
                      <td>{summary.week ?? "All"}</td>
                      <td>{summary.rows_written}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {slateStatus && loadSummaries.length === 0 && (
            <div className="status-card">
              <h3>{slateStatus.resource.toUpperCase()} status</h3>
              <p>{slateStatus.message}</p>
              <p>
                Rows: {slateStatus.rows_written} | Completed:{" "}
                {new Date(slateStatus.completed_at).toLocaleString()}
              </p>
            </div>
          )}
          {optimizerStatus && (
            <div className="status-card">
              <h3>
                Optimizer · {CLASSIC_CONTEST_STRATEGIES.find(
                  (strategy) => strategy.id === optimizerStatus.strategy
                )?.label ?? optimizerStatus.strategy}
              </h3>
              <p>Job ID: {optimizerStatus.job_id}</p>
              <p>Status: {optimizerStatus.status}</p>
              <p>Strategy: {optimizerStatus.strategy}</p>
              {typeof optimizerStatus.strategy_config.description === "string" && (
                <p>{optimizerStatus.strategy_config.description}</p>
              )}
              <p>{optimizerStatus.message}</p>
              {Array.isArray(optimizerStatus.results) && (() => {
                const report = (optimizerStatus.results[0] as any[])?.[0]?.single_entry_report;
                if (!report) return null;
                const comparisonRows = Array.from(new Map(
                  [...(report.candidates ?? []), ...(report.selected_candidates ?? []),
                    ...Object.values(report.top_alternates ?? {}).filter(Boolean)]
                    .map((candidate: any) => [candidate.rank, candidate])
                ).values()).sort((left: any, right: any) => left.rank - right.rank) as any[];
                const comparisons = report.portfolio_comparisons ?? {};
                const contestSelection = report.contest_selection;
                const selectedComparison = report.selected_portfolio_comparison;
                const formatDelta = (value: number) => `${value >= 0 ? "+" : ""}${value.toFixed(3)}`;
                return <div>
                  <h4>Recommended portfolio: {report.recommended_structure ?? "A"}</h4>
                  <p>Contest value is a payout-ladder proxy under stated rank assumptions. Lineup payout probabilities await field and contest simulation.</p>
                  {contestSelection && <div>
                    <p>Contest selection: {contestSelection.mode === "auto" ? "Auto" : "Enter all"} · {contestSelection.selected_count} of {contestSelection.available_count} contests · ${Number(contestSelection.total_entry_fees).toFixed(2)} total entry fees. {contestSelection.note}</p>
                    <p>{contestSelection.selection_reason} Search: {contestSelection.search_method}; {contestSelection.evaluated_subsets} subsets evaluated.</p>
                    <div className="table-wrap"><table><thead><tr><th>Contests</th><th>Best subset</th><th>Entry fees</th><th>Heuristic value</th><th>Independent ranks</th><th>Shared percentile</th></tr></thead><tbody>{contestSelection.count_comparisons.map((row: any) => <tr key={row.contest_count}><td>{row.contest_count}</td><td>{row.contest_ids.join(", ")}</td><td>${row.total_entry_fees.toFixed(2)}</td><td>{(row.heuristic_value * 100).toFixed(1)}%</td><td>{(row.independent_rank_proxy * 100).toFixed(1)}%</td><td>{(row.shared_percentile_proxy * 100).toFixed(1)}%</td></tr>)}</tbody></table></div>
                    <div className="table-wrap"><table><thead><tr><th>Selected</th><th>Contest</th><th>Single-contest proxy</th><th>Entry</th><th>Field</th><th>Paid</th><th>Min cash</th><th>Top 1%</th><th>5%</th><th>10%</th><th>20%</th><th>Median paid</th><th>1st share</th><th>Top 10 share</th><th>Flatness</th><th>Full rake</th><th>Near-lock effective rake / overlay</th></tr></thead><tbody>{contestSelection.ranked_contests.map((contest: any) => <tr key={contest.contest_id}>
                      <td>{contestSelection.selected_contest_ids.includes(contest.contest_id) ? "Yes" : "No"}</td><td>{contest.name}</td><td>{(contest.contest_score * 100).toFixed(1)}%</td><td>${contest.entry_fee}</td><td>{contest.capacity}</td><td>{(contest.economics.paid_percentage * 100).toFixed(1)}%</td><td>${contest.economics.minimum_cash} ({contest.economics.minimum_cash_multiple.toFixed(2)}×)</td><td>${contest.economics.payout_at_field_percentiles["1"]}</td><td>${contest.economics.payout_at_field_percentiles["5"]}</td><td>${contest.economics.payout_at_field_percentiles["10"]}</td><td>${contest.economics.payout_at_field_percentiles["20"]}</td><td>${contest.economics.median_paid_payout}</td><td>{(contest.economics.first_place_share * 100).toFixed(1)}%</td><td>{(contest.economics.top_10_share * 100).toFixed(1)}%</td><td>{contest.economics.payout_flatness.toFixed(3)}</td><td>{(contest.economics.full_field_rake * 100).toFixed(1)}%</td><td>{contest.economics.current_effective_rake == null ? "Too early" : `${(contest.economics.current_effective_rake * 100).toFixed(1)}% / $${contest.economics.current_overlay.toFixed(2)}`}</td>
                    </tr>)}</tbody></table></div>
                  </div>}
                  <p>Weights: mean {report.objective_weights.mean}, P90 {report.objective_weights.p90}, solver {report.objective_weights.solver}, correlation {report.objective_weights.correlation}, context {report.objective_weights.context}, chalk penalty {report.objective_weights.chalk_penalty}.</p>
                  {report.assignments.length > 1 ? <p>{report.unique_lineups} unique lineups · {report.unique_captains} unique Captains · overlap: {report.pairwise_player_overlap.join(", ")} players</p> : <p>One contest selected; lineup A is the highest-ranked single-entry construction.</p>}
                  {report.evaluated_portfolio_count > 0 && <p>Compared {report.evaluated_portfolio_count} candidate combinations with repetition; the table shows the strongest in each structure.</p>}
                  {comparisons.aaa && <p>Letters name distinct lineups within each row; candidate ranks identify the exact lineups.</p>}
                  {selectedComparison && comparisons.aaa && <p>
                    Versus A / A / A, this structure gains {formatDelta(selectedComparison.heuristic_delta_vs_aaa)} heuristic points:
                    {" "}{selectedComparison.diversification_credit_total.toFixed(3)} diversification credit less {selectedComparison.quality_loss_total.toFixed(3)} quality loss.
                    {comparisons.best_two_alternates && <> The best A / B / C scores {formatDelta(comparisons.best_two_alternates.heuristic_delta_vs_aaa)} versus A / A / A,
                    {" "}{(selectedComparison.heuristic_delta_vs_aaa - comparisons.best_two_alternates.heuristic_delta_vs_aaa).toFixed(3)} below the recommendation.</>}
                  </p>}
                  {comparisons.aaa && <div className="table-wrap"><table><thead><tr>
                    <th>Portfolio comparison</th><th>Candidate ranks</th><th>Quality loss</th><th>Diversification credit</th><th>Heuristic delta vs A / A / A</th>
                  </tr></thead><tbody>{[
                    comparisons.aaa, comparisons.best_one_alternate, comparisons.best_repeated_alternate,
                    comparisons.best_two_alternates,
                  ].filter(Boolean).map((comparison: any) => <tr key={comparison.structure}>
                    <td>{comparison.structure}</td><td>{comparison.candidate_ranks.join(" / ")}</td>
                    <td>{comparison.quality_loss_total.toFixed(3)}</td>
                    <td>{comparison.diversification_credit_total.toFixed(3)}</td>
                    <td>{formatDelta(comparison.heuristic_delta_vs_aaa)}</td>
                  </tr>)}</tbody></table></div>}
                  <ul>{report.assignments.map((assignment: any) =>
                    <li key={assignment.contest}>{assignment.contest_name ?? `Contest ${assignment.contest}`} {assignment.contest_id ? `(${assignment.contest_id})` : ""}: candidate #{assignment.candidate_rank}. {assignment.reason}</li>
                  )}</ul>
                  {report.assignments.length > 1 && report.top_alternates && <div>
                    <h4>Closest construction alternatives</h4>
                    <p>“Materially different players” means at least {report.material_player_change_minimum} of six players change. These are candidates for review, not required portfolio slots.</p>
                    <ul>{[
                      ["Different Captain, same six players", report.top_alternates.different_captain_only],
                      ["Different Captain and player combination", report.top_alternates.different_captain_material_players],
                      ["Different game script", report.top_alternates.different_game_script],
                    ].map(([label, candidate]: any) => <li key={label}>
                      {label}: {candidate ? `#${candidate.rank} ${candidate.captain} · ${candidate.game_script.label} · quality loss ${candidate.quality_loss_vs_a.toFixed(3)} · benefit ${candidate.diversification_benefit_vs_a.toFixed(3)}` : "No qualifying candidate in the generated pool"}
                    </li>)}</ul>
                  </div>}
                  <h4>{report.assignments.length > 1 ? "Selected, top 10, and featured alternate lineups" : "Selected lineup and top candidates"}</h4>
                  <div className="table-wrap"><table><thead><tr>
                    <th>Rank</th><th>Captain</th><th>Single-entry score</th><th>Mean</th><th>Sum of P90s</th><th>Solver</th><th>Ownership</th><th>Relative chalk</th><th>Correlation</th><th>Context</th><th>Script</th>{report.assignments.length > 1 && <><th>Shared with A</th><th>Overlap</th><th>Jaccard</th><th>Quality loss</th><th>Diversification benefit</th></>}<th>Players</th>
                  </tr></thead><tbody>{comparisonRows.map((candidate: any) => <tr key={candidate.rank}>
                    <td>{candidate.rank}</td><td>{candidate.captain}</td><td>{candidate.single_entry_score.toFixed(3)}</td><td>{candidate.mean.toFixed(1)}</td><td>{candidate.p90.toFixed(1)}</td>
                    <td>{candidate.solver_objective.toFixed(1)}</td><td>{candidate.ownership_sum.toFixed(1)}</td>
                    <td>{candidate.relative_chalk == null ? "n/a" : candidate.relative_chalk.toFixed(1)}</td>
                    <td>{candidate.correlation_score.toFixed(2)}</td><td>{candidate.context_score.toFixed(2)}</td>
                    <td>{candidate.game_script.label}</td>{report.assignments.length > 1 && <><td>{candidate.shared_players_with_a ?? "—"}/6</td>
                    <td>{candidate.overlap_percentage_vs_a == null ? "—" : `${candidate.overlap_percentage_vs_a.toFixed(1)}%`}</td>
                    <td>{candidate.jaccard_similarity_vs_a == null ? "—" : candidate.jaccard_similarity_vs_a.toFixed(3)}</td>
                    <td>{candidate.quality_loss_vs_a.toFixed(3)}</td><td>{candidate.diversification_benefit_vs_a == null ? "—" : candidate.diversification_benefit_vs_a.toFixed(3)}</td></>}
                    <td>{candidate.players.map((player: any) => `${player.slot} ${player.name}`).join(", ")}</td>
                  </tr>)}</tbody></table></div>
                </div>;
              })()}
              {optimizerStatus.status === "completed" && Array.isArray(optimizerStatus.results) && optimizerStatus.results.length > 0 && (
                <div>
                  <div className="button-row">
                    <button disabled={lineupExportPending} onClick={async () => {
                      setLineupExportPending(true);
                      setLineupExportError(null);
                      try {
                        await downloadOptimizerLineups(optimizerStatus.job_id);
                      } catch (error) {
                        setLineupExportError(error instanceof Error ? error.message : String(error));
                      } finally {
                        setLineupExportPending(false);
                      }
                    }}>
                      {lineupExportPending ? "Preparing download…" : `Download all ${optimizerStatus.results.length} lineups for DraftKings`}
                    </button>
                    <button onClick={() => downloadOptimizerReport(optimizerStatus, { season, week, slate })}>
                      Download readable lineup report
                    </button>
                  </div>
                  <p>No entry template required. Use DraftKings → Lineups → Upload Lineups. More than 500 lineups download as a ZIP of CSV files.</p>
                  {lineupExportError && <p role="alert">{lineupExportError}</p>}
                </div>
              )}
              {optimizerStatus.player_pool && (
                <>
                  {optimizerStatus.player_pool.context_scoring?.gpp_context_warning && (
                    <p className="warning-text">
                      {optimizerStatus.player_pool.context_scoring.gpp_context_warning.message}
                    </p>
                  )}
                  <details className="optimizer-pool-details">
                    <summary>
                      Raw pool: {optimizerStatus.player_pool.raw_pool_count ?? optimizerStatus.player_pool.initial_count} → opportunity eligible: {optimizerStatus.player_pool.opportunity_eligible_count ?? optimizerStatus.player_pool.eligible_count ?? optimizerStatus.player_pool.initial_count} → optimizer eligible: {optimizerStatus.player_pool.optimizer_eligible_count ?? optimizerStatus.player_pool.included_count} · {contextReadinessLabel(optimizerStatus.player_pool.context_scoring)} · Pool warnings: {optimizerStatus.player_pool.warning_player_count ?? 0}
                    </summary>
                    {optimizerStatus.player_pool.removal_reason_counts && Object.keys(optimizerStatus.player_pool.removal_reason_counts).length > 0 && (
                      <p>
                        Removals: {Object.entries(optimizerStatus.player_pool.removal_reason_counts)
                          .map(([reason, count]) => `${reason.replaceAll("_", " ")} (${count})`)
                          .join(" · ")}
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        const blob = new Blob(
                          [JSON.stringify(optimizerStatus.player_pool, null, 2)],
                          { type: "application/json" },
                        );
                        const url = URL.createObjectURL(blob);
                        const link = document.createElement("a");
                        link.href = url;
                        link.download = `optimizer-player-pool-${optimizerStatus.job_id}.json`;
                        link.click();
                        URL.revokeObjectURL(url);
                      }}
                    >
                      Download full player pool JSON
                    </button>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Player</th>
                            <th>Pos</th>
                            <th>Team</th>
                            <th>Salary</th>
                            <th>Proj</th>
                            <th>P90</th>
                            <th>Context</th>
                            <th>Pool status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {optimizerStatus.player_pool.rows.map((player) => (
                            <tr key={player.player_id}>
                              <td>{player.player_name}</td>
                              <td>{player.position}</td>
                              <td>{player.team}</td>
                              <td>{Number(player.salary || 0).toLocaleString()}</td>
                              <td>{Number(player.projection || 0).toFixed(2)}</td>
                              <td>{Number(player.p90 || 0).toFixed(2)}</td>
                              <td>
                                {typeof player.optimizer_context_adjustment === "number" ? (
                                  <span title={(player.optimizer_context_reason_codes ?? []).join(", ")}>
                                    {player.optimizer_context_adjustment >= 0 ? "+" : ""}
                                    {player.optimizer_context_adjustment.toFixed(2)}
                                  </span>
                                ) : (
                                  "—"
                                )}
                              </td>
                              <td>
                                {player.included
                                  ? [
                                      "Included",
                                      player.flex_only ? "FLEX only" : null,
                                      player.warnings?.length
                                        ? player.warnings.map((warning) => warning.reason_code).join(", ")
                                        : null,
                                    ].filter(Boolean).join(" · ")
                                  : player.exclusion_reasons.join(", ") || "Excluded"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </>
              )}
              {Array.isArray(optimizerStatus.results) && optimizerStatus.results.length > 0 && (
                <div className="lineups-grid">
                  {optimizerStatus.results.map((lineup, idx) => {
                    if (!Array.isArray(lineup)) return null;
                    const totalSalary = lineup.reduce(
                      (sum, player: any) => sum + (Number(player?.salary) || 0),
                      0
                    );
                    const totalProj = lineup.reduce(
                      (sum, player: any) => sum + (Number(player?.projection ?? player?.predicted_mean) || 0),
                      0
                    );
                    const ceilingSummary = individualCeilingSummary(lineup);
                    const totalFloor = lineup.reduce(
                      (sum, player: any) => sum + (Number(player?.h2h_floor ?? player?.predicted_p10 ?? player?.projection) || 0),
                      0
                    );
                    const totalContextAdjustment = Number(
                      lineup[0]?.lineup_context_summary?.total_adjustment ??
                        lineup.reduce(
                          (sum, player: any) => sum + (Number(player?.optimizer_context_adjustment) || 0),
                          0
                        )
                    );
                    const hasContextScoring = lineup.some(
                      (player: any) => typeof player?.optimizer_context_adjustment === "number"
                    );
                    const ownershipValues = lineup
                      .map((player: any) => player?.ownership)
                      .filter((value: unknown) => value !== null && value !== undefined && Number.isFinite(Number(value)));
                    const ownershipAvailable = ownershipValues.length === lineup.length;
                    const totalOwnership = ownershipValues.reduce(
                      (sum: number, value: unknown) => sum + Number(value), 0
                    );
                    const duplicationRisk = lineup[0]?.lineup_duplication_risk;
                    const stackSummary = lineup[0]?.lineup_stack_summary?.label;
                    const correlationSummary = lineup[0]?.lineup_correlation_summary;
                    const correlationAdjustment = Number(
                      correlationSummary?.total_adjustment ?? 0
                    );
                    const correlationRules = Array.isArray(correlationSummary?.triggered_rules)
                      ? correlationSummary.triggered_rules
                      : [];
                    const gameScript = correlationSummary?.implied_game_script?.label;
                    const constructionLabel = correlationSummary?.construction_label;
                    const projVal = (p: any) =>
                      Number(p.projection ?? p.predicted_mean ?? p.p90 ?? 0);
                    const normalizePos = (p: any) =>
                      String(p?.roster_position || p?.position || "").toUpperCase();

                    const assignSlots = (players: any[]) => {
                      const hasCaptain = players.some(
                        (p) => normalizePos(p) === "CPT" || (p.is_captain && normalizePos(p) === "FLEX")
                      );
                      if (hasCaptain) {
                        const cpts = players
                          .filter((p) => normalizePos(p) === "CPT" || p.is_captain)
                          .map((p) => ({ ...p, roster_position: "CPT" }));
                        const flex = players
                          .filter((p) => !(normalizePos(p) === "CPT" || p.is_captain))
                          .map((p) => ({ ...p, roster_position: p.roster_position || p.position || "FLEX" }))
                          .sort((a, b) => projVal(b) - projVal(a));
                        return [...cpts, ...flex];
                      }

                      const remaining = players.map((p, idx) => ({
                        ...p,
                        _slot: undefined as string | undefined,
                        _id: `${p.player_id}-${p.roster_position || p.position || idx}`,
                      }));
                      const take = (filterFn: (p: any) => boolean, count: number, label: string) => {
                        const candidates = remaining.filter(filterFn).sort((a, b) => projVal(b) - projVal(a));
                        const chosen = candidates.slice(0, count);
                        for (const pick of chosen) {
                          const idx = remaining.findIndex((r) => r._id === pick._id);
                          if (idx >= 0) {
                            remaining[idx]._slot = label;
                            remaining.splice(idx, 1);
                          }
                        }
                        return chosen;
                      };

                      const qb = take((p) => normalizePos(p).includes("QB"), 1, "QB");
                      const dst = take(
                        (p) => {
                          const pos = normalizePos(p);
                          return pos.includes("DST") || pos === "D" || pos === "DEF";
                        },
                        1,
                        "DST"
                      );
                      const rb = take((p) => normalizePos(p).includes("RB"), 2, "RB");
                      const wr = take((p) => normalizePos(p).includes("WR"), 3, "WR");
                      const te = take((p) => normalizePos(p).includes("TE"), 1, "TE");

                      const fixedCount = qb.length + dst.length + rb.length + wr.length + te.length;
                      const flexCount = Math.max(0, 9 - fixedCount);
                      const flex = take(
                        (p) => {
                          const pos = normalizePos(p);
                          return pos.includes("RB") || pos.includes("WR") || pos.includes("TE");
                        },
                        flexCount,
                        "FLEX"
                      );

                      const ordered = [...qb, ...rb, ...wr, ...te, ...flex, ...dst];
                      // If anything remains, append by projection
                      const remainingSorted = remaining.sort((a, b) => projVal(b) - projVal(a));
                      return ordered.concat(remainingSorted);
                    };

                    const sortedLineup = assignSlots(lineup);
                    return (
                      <div className="lineup-card" key={`lineup-${idx}`}>
                        <div className="lineup-header">
                          <strong>Lineup {idx + 1}</strong>
                          <span>Salary: {totalSalary.toLocaleString()}</span>
                          <span>Mean: {totalProj.toFixed(2)}</span>
                          <span>{ceilingSummary.label}: {ceilingSummary.value.toFixed(2)}</span>
                          {hasContextScoring && (
                            <span>
                              Context: {totalContextAdjustment >= 0 ? "+" : ""}
                              {totalContextAdjustment.toFixed(2)}
                            </span>
                          )}
                          {optimizerStatus.strategy === "classic_head_to_head_v1" && (
                            <span>Floor: {totalFloor.toFixed(2)} · Risk: {(totalProj - totalFloor).toFixed(2)}</span>
                          )}
                          {stackSummary && <span>Stack: {stackSummary}</span>}
                          {correlationSummary && (
                            <span>
                              Correlation: {correlationAdjustment >= 0 ? "+" : ""}
                              {correlationAdjustment.toFixed(2)}
                            </span>
                          )}
                          {gameScript && <span>Script: {gameScript}</span>}
                          {optimizerStatus.objective === "gpp" && (
                            <>
                              <span>
                                {ownershipAvailable
                                  ? `Ownership: ${totalOwnership.toFixed(2)}`
                                  : "GPP ownership unavailable — optimizing ceiling/correlation only"}
                              </span>
                              {duplicationRisk?.ownership_available && (
                                <span>
                                  Relative chalk: {Number(duplicationRisk.relative_chalk_score).toFixed(1)}/100
                                </span>
                              )}
                            </>
                          )}
                          {!stackSummary && constructionLabel && (
                            <span>Construction: {constructionLabel}</span>
                          )}
                        </div>
                        <OptimizerControlComparison comparison={lineup[0]?.lineup_control_comparison} />
                        {correlationRules.length > 0 && (
                          <details>
                            <summary>
                              Correlation rules ({correlationRules.length})
                            </summary>
                            <ul>
                              {correlationRules.map((rule: any, ruleIdx: number) => {
                                const contribution = Number(
                                  rule.objective_contribution ?? rule.score_contribution ?? 0
                                );
                                const players = Array.isArray(rule.players)
                                  ? rule.players
                                      .map((player: any) => player.player_name || player.player_id)
                                      .filter(Boolean)
                                      .join(" + ")
                                  : "";
                                return (
                                  <li key={`${rule.rule_id || rule.reason_code}-${ruleIdx}`}>
                                    {contribution >= 0 ? "+" : ""}
                                    {contribution.toFixed(2)} · {rule.description || rule.reason_code}
                                    {players ? ` · ${players}` : ""}
                                  </li>
                                );
                              })}
                            </ul>
                          </details>
                        )}
                        <table className="compact-table">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>Slot · Pos</th>
                              <th>Team</th>
                              <th>Salary</th>
                              <th>Proj</th>
                              <th>P90</th>
                              <th>Rules</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sortedLineup.map((player: any) => {
                              const explanations = Array.isArray(player.symbolic_explanations)
                                ? player.symbolic_explanations
                                : [];
                              const ruleSummary =
                                player.symbolic_rule_summary ||
                                explanations
                                  .map((item: any) => item.rule_id || item.rule_name)
                                  .filter(Boolean)
                                  .join(", ");
                              return (
                                <tr key={`${idx}-${player.player_id}-${player.roster_position || player.position}`}>
                                  <td>{player.name || player.player_name || player.player_display_name || player.player_id}</td>
                                  <td>
                                    {player.roster_position && player.position && player.roster_position !== player.position
                                      ? `${player.roster_position} · ${player.position}`
                                      : player.roster_position || player.position}
                                  </td>
                                  <td>{player.player_team || player.team || player.recent_team}</td>
                                  <td>{Number(player.salary || 0).toLocaleString()}</td>
                                  <td>{(Number(player.projection ?? player.predicted_mean) || 0).toFixed(2)}</td>
                                  <td>{(Number(player.predicted_p90 ?? player.p90 ?? player.projection) || 0).toFixed(2)}</td>
                                  <td title={explanations.map((item: any) => item.reason).filter(Boolean).join(" | ")}>
                                    {ruleSummary || "-"}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          {analysisRows.length > 0 && (
            <div className="status-card">
              <h3>Past Slate Analysis (Top {analysisTopN})</h3>
              {topLineups.length > 0 && (
                <div className="scroll-table">
                  <table className="compact-table">
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Points</th>
                        <th>Salary</th>
                        <th>Left</th>
                        <th>Total Own</th>
                        <th>Chalk</th>
                        <th>Low-Owned</th>
                        <th>Sub-4k</th>
                        <th>QB Stack</th>
                        <th>Bring-backs</th>
                        <th>Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topLineups.map((l, idx) => (
                        <tr key={`${l.entry_id}-${idx}`}>
                          <td>{l.rank}</td>
                          <td>{l.final_points?.toFixed?.(2) ?? l.final_points}</td>
                          <td>{l.salary_used}</td>
                          <td>{l.salary_left}</td>
                          <td>{l.total_own_sum?.toFixed?.(1) ?? l.total_own_sum}</td>
                          <td>{l.num_chalk}</td>
                          <td>{l.num_low_owned}</td>
                          <td>{l.num_sub_4k}</td>
                          <td>{l.qb_stack_type}</td>
                          <td>{l.bring_back_count}</td>
                          <td>{l.notes}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {bucketStats.length > 0 && (
                <div className="scroll-table">
                  <table className="compact-table">
                    <thead>
                      <tr>
                        <th>Bucket</th>
                        <th>Lineups</th>
                        <th>Avg Own Sum</th>
                        <th>Med Own Sum</th>
                        <th>Avg Chalk</th>
                        <th>Avg Low-Owned</th>
                        <th>Avg Salary</th>
                        <th>Avg Sub-4k</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bucketStats.map((b) => (
                        <tr key={b.bucket}>
                          <td>{b.bucket}</td>
                          <td>{b.lineups}</td>
                          <td>{b.avg_actual_own_sum.toFixed(2)}</td>
                          <td>{b.median_actual_own_sum.toFixed(2)}</td>
                          <td>{b.avg_num_chalk.toFixed(2)}</td>
                          <td>{b.avg_num_low_owned.toFixed(2)}</td>
                          <td>{b.avg_total_salary.toFixed(0)}</td>
                          <td>{b.avg_num_sub_4k.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="scroll-table">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>Player</th>
                      <th>Roster Pos</th>
                      <th>Count</th>
                      <th>%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisRows.map((row, idx) => (
                      <tr key={`${row.player_display_name}-${idx}`}>
                        <td>{row.player_display_name}</td>
                        <td>{row.roster_position || "-"}</td>
                        <td>{row.count}</td>
                        <td>{row.pct.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {predictionRows.length > 0 && (
            <div className="status-card">
              <h3>Projections</h3>
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Pos</th>
                    <th>Team</th>
                    <th>Opp</th>
                    <th>Mean</th>
                    <th>AdjMean</th>
                    <th>P90</th>
                    <th>Model</th>
                    <th>Recent Median</th>
                    <th>Last 3 Avg</th>
                    <th>Last 3</th>
                    <th>Δ vs Last3</th>
                    <th>Team Pos Avg/G</th>
                  </tr>
                </thead>
                <tbody>
                  {predictionRows.map((row) => (
                    <tr key={`${row.player_id}-${row.week}`}>
                      <td>{row.player_display_name}</td>
                      <td>{row.position}</td>
                      <td>{row.recent_team}</td>
                      <td>{row.opponent_team}</td>
                      <td>{row.predicted_mean.toFixed(2)}</td>
                      <td>{row.adj_mean?.toFixed(2)}</td>
                      <td>{row.predicted_p90.toFixed(2)}</td>
                      <td>{row.model}</td>
                      <td>{row.recent_median?.toFixed(2)}</td>
                      <td>{row.last3_avg?.toFixed(2)}</td>
                      <td>{row.last3_points?.map((v) => v.toFixed(1)).join(", ")}</td>
                      <td>{row.delta_vs_last3?.toFixed(2)}</td>
                      <td>{row.team_pos_avg?.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {predictionRows.length === 0 && predictionPreview.length > 0 && (
            <div className="status-card">
              <h3>Projections (Preview)</h3>
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Pos</th>
                    <th>Team</th>
                    <th>Opp</th>
                    <th>Mean</th>
                    <th>P90</th>
                  </tr>
                </thead>
                <tbody>
                  {predictionPreview.map((row) => (
                    <tr key={`${row.player_id}-${row.week}`}>
                      <td>{row.player_display_name}</td>
                      <td>{row.position}</td>
                      <td>{row.recent_team}</td>
                      <td>{row.opponent_team}</td>
                      <td>{row.predicted_mean.toFixed(2)}</td>
                      <td>{row.predicted_p90.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {operationalJobs.length === 0 && loadSummaries.length === 0 && !slateStatus && !optimizerStatus && !error && (
            <p className="placeholder">No activity yet.</p>
          )}
        </section>

        <section className="panel summary-panel unified activity-panel operations-panel operations-coverage-panel">
          <div className="summary-header">
            <div className="operations-panel-heading">
              <span>Quality control</span>
              <h2>Data coverage</h2>
            </div>
            <span className="summary-subtitle">Row counts by season/week</span>
          </div>
          <div className="quality-history" aria-live="polite">
            <div className="quality-history-header">
              <div>
                <span>Persistent audit</span>
                <strong>Quality history</strong>
                <p>Every completed load and slate-readiness check is retained with its scope and threshold.</p>
              </div>
              <button onClick={refreshDataQualityHistory} disabled={dataQualityLoading}>
                {dataQualityLoading ? "Refreshing..." : "Refresh history"}
              </button>
            </div>
            {dataQualityError && <div className="error inline-error">{dataQualityError}</div>}
            {dataQualityHistory && dataQualityHistory.runs.length > 0 ? (
              <>
                <div className="quality-history-metrics">
                  <div>
                    <span>Recorded runs</span>
                    <strong>{dataQualityHistory.runs.length}</strong>
                  </div>
                  <div>
                    <span>Latest score</span>
                    <strong>{dataQualityHistory.runs[0].score}</strong>
                  </div>
                  <div>
                    <span>Latest attention</span>
                    <strong>
                      {(dataQualityHistory.runs[0].summary.warn ?? 0)
                        + (dataQualityHistory.runs[0].summary.fail ?? 0)}
                    </strong>
                  </div>
                </div>
                <div className="quality-history-list">
                  {dataQualityHistory.runs.slice(0, 6).map((run) => {
                    const attention = run.checks.find((check) => check.status !== "pass");
                    return (
                      <article key={run.quality_run_id} className={`quality-history-run ${run.status}`}>
                        <i aria-hidden="true" />
                        <div>
                          <span>{run.trigger.replaceAll("_", " ")}</span>
                          <strong>
                            {attention?.message ?? `${run.checks.length} checks completed without attention.`}
                          </strong>
                          <small>{new Date(run.created_at).toLocaleString()}</small>
                        </div>
                        <div className="quality-history-score">
                          <strong>{run.score}</strong>
                          <span>{run.summary.pass ?? 0}P · {run.summary.warn ?? 0}W · {run.summary.fail ?? 0}F</span>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </>
            ) : !dataQualityLoading && !dataQualityError ? (
              <p className="quality-history-empty">
                No quality history is recorded for this context yet. The next load or readiness check will start it.
              </p>
            ) : null}
          </div>
          <div className="form-row">
            <label>
              Table
              <select
                value={validationTable}
                onChange={(event) => setValidationTable(event.target.value)}
              >
                <optgroup label="Raw">
                  <option value="raw_weekly_stats">raw_weekly_stats</option>
                  <option value="raw_weekly_rosters">raw_weekly_rosters</option>
                  <option value="raw_injuries">raw_injuries</option>
                </optgroup>
                <optgroup label="Curated">
                  <option value="curated_weekly_stats">curated_weekly_stats</option>
                  <option value="curated_weekly_rosters">curated_weekly_rosters</option>
                  <option value="curated_injuries">curated_injuries</option>
                  <option value="curated_salaries">curated_salaries</option>
                </optgroup>
                <optgroup label="Predictive">
                  <option value="predictive_features">predictive_features</option>
                  <option value="player_expected_points">player_expected_points</option>
                </optgroup>
                <optgroup label="Other">
                  <option value="weekly_injuries">weekly_injuries</option>
                </optgroup>
              </select>
            </label>
            <div className="button-row">
              <button onClick={runValidation} disabled={validationLoading}>
                {validationLoading ? "Checking..." : "Check Coverage"}
              </button>
              <button onClick={runProcessUnmatched}>Process Unmatched → Player Master</button>
            </div>
          </div>
          <div className="form-row column">
            <div className="button-row">
              <button onClick={loadUnmatched} disabled={unmatchedLoading}>
                {unmatchedLoading ? "Loading..." : "View Unmatched Salaries"}
              </button>
              <button onClick={loadUnmatchedInjuries} disabled={unmatchedInjuryLoading}>
                {unmatchedInjuryLoading ? "Loading..." : "View Unmatched Injuries"}
              </button>
            </div>
            <p className="helper-text">
              Fetches up to 50 unmatched rows for the selected season/week/slate so you can reconcile names.
            </p>
          </div>
          {validationError && <div className="error inline-error">{validationError}</div>}
          {unmatchedError && <div className="error inline-error">{unmatchedError}</div>}
          {unmatchedInjuryError && <div className="error inline-error">{unmatchedInjuryError}</div>}
          {unmatchedProcessStatus && <div className="status-text">{unmatchedProcessStatus}</div>}
          {unmatchedRows.length > 0 && (
            <div className="status-card">
              <h3>Unmatched Salaries</h3>
              <div className="scroll-table">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>Player</th>
                      <th>Team</th>
                      <th>Slate</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unmatchedRows.map((row, idx) => (
                      <tr key={`${row.name}-${idx}`}>
                        <td>{row.name}</td>
                        <td>{row.player_team}</td>
                        <td>{row.slate}</td>
                        <td>{new Date(row.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {unmatchedInjuryRows.length > 0 && (
            <div className="status-card">
              <h3>Unmatched Injuries</h3>
              <div className="scroll-table">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>Player</th>
                      <th>Team</th>
                      <th>Opponent</th>
                      <th>Status</th>
                      <th>Slate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unmatchedInjuryRows.map((row, idx) => (
                      <tr key={`${row.name}-${idx}`}>
                        <td>{row.name}</td>
                        <td>{row.player_team}</td>
                        <td>{row.opponent}</td>
                        <td>{row.status ?? "—"}</td>
                        <td>{row.slate}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {validationRows.length > 0 && (
            <div className="status-card">
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Season</th>
                    <th>Week</th>
                    <th>Rows</th>
                    <th>Expected</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {validationRows.map((row) => (
                    <tr key={`${row.season}-${row.week}`}>
                      <td>{row.season}</td>
                      <td>{row.week}</td>
                      <td>{row.rows}</td>
                      <td>{row.expected_rows ?? "—"}</td>
                      <td className={`status-${row.status}`}>
                        {row.status}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {validationRows.length === 0 && !validationError && !validationLoading && (
            <p className="placeholder">Run a coverage check to see ingested weeks.</p>
          )}
        </section>

      </div>
      </div>
    </AppShell>
  );
}

export default App;
