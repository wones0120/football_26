import { OptimizerControlComparison } from "./OptimizerControlComparison";
import { optimizerAvailabilityOverrides } from "./optimizerProjectionScenario";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { AppShell, type ViewMode } from "./AppShell";
import { DailyNewsBrief } from "./DailyNewsBrief";
import { ContestWorkflow } from "./ContestWorkflow";
import { ContestLibrary } from "./ContestLibrary";
import { DesignPreview } from "./DesignPreview";
import { DigitalTwin } from "./DigitalTwin";
import { ModelWorkbench } from "./ModelWorkbench";
import { ResearchWorkspace } from "./ResearchWorkspace";
import { WarRoom } from "./WarRoom";
import {
  ACTIVE_SLATE_CONTEXT_STORAGE_KEY,
  DEFAULT_SLATE,
  SLATE_OPTIONS,
  normalizeSlateId,
  parsePersistedActiveSlateContext,
  serializeActiveSlateContext,
  slateContextKey,
  updateRunSelection,
  type PersistedRunSelection,
  type PersistedRunSelections,
} from "./workspaceContext";
import {
  CLASSIC_CONTEST_STRATEGIES,
  CLASSIC_LARGE_GPP_STRATEGY_ID,
  CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID,
  SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
  SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID,
  SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID,
  SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID,
  SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID,
  classicSmallFieldCandidateParams,
  optimizerStrategyId,
  type ClassicContestStrategyId,
} from "./optimizerStrategy";
import {
  contextReadinessLabel,
  individualCeilingSummary,
} from "./optimizerPresentation";
import { downloadOptimizerReport } from "./optimizerReport";
import { classicContestUrls } from "./classicContestUrl";
import { resolveCsvIngestPath } from "./ingestPath";
import { RbDstDiagnosticsPanel } from "./RbDstDiagnosticsPanel";
import { ModelDisagreementPanel } from "./ModelDisagreementPanel";
import { SkillExposureApprovalPanel } from "./SkillExposureApprovalPanel";
import { downloadWeeklyLearningReport } from "./learningExport";
import type {
  LoadSummary,
  DataQualityHistoryResponse,
  SlateLoadResponse,
  OptimizerResponse,
  OptimizerProjectionRun,
  ContestPreview,
  SlateReadinessGateKey,
  SlateReadinessResponse,
  SimulationResponse,
  WeeklyLearningReport,
  DraftKingsBatchFile,
} from "./api";
import {
  analyzePastSlate,
  buildFeatureMatrix,
  buildFeatures,
  createWeeklyRun,
  downloadOptimizerLineups,
  fetchCurrentContext,
  fetchLatestPredictions,
  fetchOptimizerProjectionRuns,
  generateWeeklyLearningReport,
  importWeeklyContestFolder,
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
  reconcileSlateSalaryIdentities,
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
  type StartingQBCandidate,
  type UnmatchedSalaryRow,
  type ValidationRow,
  type WeeklyRun,
} from "./api";
import { fetchUnmatchedInjuries, type UnmatchedInjuryRow } from "./api";
import {
  autoDiscoverInjuryFiles,
  autoDiscoverSalaryFiles,
  bootstrapNflreadpy,
  ingestNflreadpySchedules,
  ingestNflreadpyWeeklyStats,
} from "./research/api";

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
  model_id?: string | null;
};

type PredictionOperationStatus = {
  message: string;
  rows_written: number;
};

type StartingQBDraft = {
  playerMasterId: string;
  evidenceTier: "confirmed" | "inferred";
  sourceUri: string;
  note: string;
};

type PlayerDecisionControl = {
  playerName: string;
  availability: "default" | "assume_active" | "assume_out";
  excludeFromLineups: boolean;
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
  const [startupContext] = useState(() => {
    try {
      return parsePersistedActiveSlateContext(window.localStorage.getItem(ACTIVE_SLATE_CONTEXT_STORAGE_KEY));
    } catch {
      return null;
    }
  });
  const [season, setSeason] = useState(startupContext?.season ?? FALLBACK_SEASON);
  const [week, setWeek] = useState(startupContext?.week ?? FALLBACK_WEEK);
  const [slate, setSlate] = useState(startupContext?.slate ?? DEFAULT_SLATE);
  const [activeContextReady, setActiveContextReady] = useState(Boolean(startupContext));
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
  const [injuryPath, setInjuryPath] = useState<string>("~/NFL/");
  const [ingestDirectory, setIngestDirectory] = useState("~/NFL");
  const [historyStartSeason, setHistoryStartSeason] = useState(2018);
  const [historyEndSeason, setHistoryEndSeason] = useState(2025);
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
  const [classicMaxLineupOverlap, setClassicMaxLineupOverlap] = useState("");
  const [classicPrimaryGameCap, setClassicPrimaryGameCap] = useState("");
  const [classicSkillMaxAppearances, setClassicSkillMaxAppearances] = useState("");
  const [classicExpandedDiscovery, setClassicExpandedDiscovery] = useState(false);
  const [classicDistinctQbPaths, setClassicDistinctQbPaths] = useState(false);
  const [classicMaxObjectiveLoss, setClassicMaxObjectiveLoss] = useState("");
  const [captainMaxExposure, setCaptainMaxExposure] = useState(60);
  const captainMaxExposureInputRef = useRef<HTMLInputElement>(null);
  const [coreMaxExposure, setCoreMaxExposure] = useState(80);
  const [startingQbMaxExposure, setStartingQbMaxExposure] = useState(100);
  const [cheapPuntMaxExposure, setCheapPuntMaxExposure] = useState(40);
  const [showdownDecisiveMargin, setShowdownDecisiveMargin] = useState(14);
  const [requireScenarioDiversity, setRequireScenarioDiversity] = useState(false);
  const [contestFormat, setContestFormat] = useState<"classic" | "showdown">("classic");
  const [optimizerObjective, setOptimizerObjective] = useState<"cash" | "gpp">("gpp");
  const [refreshOwnershipBeforeOptimize, setRefreshOwnershipBeforeOptimize] = useState<boolean>(
    () => window.localStorage.getItem("dfs-refresh-ownership-before-optimize") !== "false",
  );
  const [showdownGppStrategy, setShowdownGppStrategy] = useState(SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID);
  const [singleEntryContestUrls, setSingleEntryContestUrls] = useState("");
  const [classicSmallFieldContestUrl, setClassicSmallFieldContestUrl] = useState("");
  const [classicQbFamilyDiagnostics, setClassicQbFamilyDiagnostics] = useState(false);
  const [smallMaxContestUrl, setSmallMaxContestUrl] = useState("");
  const [smallMaxManual, setSmallMaxManual] = useState("");
  const [smallMaxMaximumEntries, setSmallMaxMaximumEntries] = useState(5);
  const [smallMaxEntriesToUse, setSmallMaxEntriesToUse] = useState("auto");
  const [smallMaxCaptainMaxExposure, setSmallMaxCaptainMaxExposure] = useState(100);
  const [smallMaxPlayerMaxExposure, setSmallMaxPlayerMaxExposure] = useState(100);
  const [smallMaxStartingQbMaxExposure, setSmallMaxStartingQbMaxExposure] = useState(100);
  const [smallMaxCheapPuntMaxExposure, setSmallMaxCheapPuntMaxExposure] = useState(100);
  const [singleEntryContestMode, setSingleEntryContestMode] = useState<"auto" | "enter_all">("auto");
  const [singleEntryBudget, setSingleEntryBudget] = useState("");
  const [singleEntryMaximum, setSingleEntryMaximum] = useState("");
  const [singleEntryManual, setSingleEntryManual] = useState("");
  const [contestPreview, setContestPreview] = useState<ContestPreview | null>(null);
  const [contestPreviewError, setContestPreviewError] = useState<string | null>(null);
  const [contestPreviewPending, setContestPreviewPending] = useState(false);
  const [optimizerProjectionMessage, setOptimizerProjectionMessage] = useState<string | null>(null);
  const [optimizerProjectionPending, setOptimizerProjectionPending] = useState(false);
  const [optimizerProjectionRunsByContext, setOptimizerProjectionRunsByContext] = useState<Record<string, OptimizerProjectionRun[]>>({});
  const [optimizerProjectionOverrides, setOptimizerProjectionOverrides] = useState<Record<string, string>>({});
  const optimizerProjectionRuns = optimizerProjectionRunsByContext[activeContextKey] ?? [];
  const optimizerProjectionOverride = optimizerProjectionOverrides[activeContextKey];
  useEffect(() => {
    window.localStorage.setItem(
      "dfs-refresh-ownership-before-optimize",
      String(refreshOwnershipBeforeOptimize),
    );
  }, [refreshOwnershipBeforeOptimize]);
  const refreshOptimizerProjectionRuns = async () => {
    setOptimizerProjectionPending(true);
    setOptimizerProjectionMessage(null);
    try {
      const response = await fetchOptimizerProjectionRuns({ season, week, slate });
      setOptimizerProjectionRunsByContext((current) => ({ ...current, [activeContextKey]: response.runs }));
      if (!response.runs.length) setOptimizerProjectionMessage("No completed projection is available for this slate.");
      return response.runs;
    } catch (err) {
      setOptimizerProjectionMessage(err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      setOptimizerProjectionPending(false);
    }
  };
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
  const classicPortfolioParams = () => {
    const constraints: Record<string, number | boolean> = {};
    if (classicMaxLineupOverlap.trim()) {
      const value = Number(classicMaxLineupOverlap);
      if (!Number.isInteger(value) || value < 0 || value > 8) throw new Error("Maximum lineup overlap must be 0–8 players.");
      constraints.max_lineup_overlap = value;
    }
    for (const [key, input] of [["canonical_game_cap", classicPrimaryGameCap], ["skill_max_appearances", classicSkillMaxAppearances]]) {
      if (input.trim()) {
        const value = Number(input);
        if (!Number.isInteger(value) || value < 1 || value > numLineups) throw new Error(`${key} must be 1 through the requested lineup count.`);
        constraints[key] = value;
      }
    }
    if (classicDistinctQbPaths) constraints.distinct_qb_paths = true;
    if (classicMaxObjectiveLoss.trim()) {
      const value = Number(classicMaxObjectiveLoss);
      if (!Number.isFinite(value) || value < 0) throw new Error("Maximum selector loss must be non-negative.");
      constraints.max_objective_loss = value;
    }
    return { ...(Object.keys(constraints).length ? { portfolio_constraints: constraints } : {}),
      ...(classicExpandedDiscovery ? { classic_expanded_discovery: true } : {}) };
  };
  const smallMaxContestParams = () => {
    const url = smallMaxContestUrl.trim();
    if (!url && selectedOptimizerStrategy === SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID) {
      throw new Error("Paste one DraftKings 3-max contest URL.");
    }
    let manual: Array<Record<string, unknown>> = [];
    if (url && smallMaxManual.trim()) {
      const parsed = JSON.parse(smallMaxManual);
      if (!Array.isArray(parsed)) throw new Error("Manual small-max contest metadata must be a JSON array.");
      manual = parsed;
    }
    return {
      contest_urls: url ? [url] : [], entries_to_use: smallMaxEntriesToUse,
      manual_contest_metadata: manual,
      small_max_maximum_entries: smallMaxMaximumEntries,
      captain_max_exposure: smallMaxCaptainMaxExposure / 100,
      core_player_max_exposure: smallMaxPlayerMaxExposure / 100,
      starting_qb_max_exposure: smallMaxStartingQbMaxExposure / 100,
      cheap_punt_max_exposure: smallMaxCheapPuntMaxExposure / 100,
    };
  };
  const [classicContestStrategy, setClassicContestStrategy] =
    useState<ClassicContestStrategyId>(CLASSIC_LARGE_GPP_STRATEGY_ID);
  const [minimumUniqueness, setMinimumUniqueness] = useState(2);
  const [maxPlayersPerTeam, setMaxPlayersPerTeam] = useState(4);
  const [maxPlayersPerGame, setMaxPlayersPerGame] = useState(5);
  const [enforceSingleTE, setEnforceSingleTE] = useState(true);
  const [avoidDstOpponents, setAvoidDstOpponents] = useState(true);
  const [longShotMode, setLongShotMode] = useState(false);
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
  useEffect(() => {
    let cancelled = false;
    setOptimizerProjectionPending(true);
    setOptimizerProjectionMessage(null);
    fetchOptimizerProjectionRuns({ season, week, slate })
      .then((response) => {
        if (cancelled) return;
        setOptimizerProjectionRunsByContext((current) => ({ ...current, [activeContextKey]: response.runs }));
        if (!response.runs.length) setOptimizerProjectionMessage("No completed projection is available for this slate.");
      })
      .catch((err) => { if (!cancelled) setOptimizerProjectionMessage(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (!cancelled) setOptimizerProjectionPending(false); });
    return () => { cancelled = true; };
  }, [activeContextKey, season, week, slate]);
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
  const [startingQBCandidates, setStartingQBCandidates] = useState<StartingQBCandidate[]>([]);
  const [startingQBDrafts, setStartingQBDrafts] = useState<Record<string, StartingQBDraft>>({});
  const [salaryPath, setSalaryPath] = useState<string>("~/NFL/");
  const [ownershipPath, setOwnershipPath] = useState<string>("~/NFL/");
  const salaryFileToLoad = resolveCsvIngestPath(salaryPath, `DKSalaries_${season}_${week}_${activeContext.slate}.csv`);
  const injuryFileToLoad = resolveCsvIngestPath(injuryPath, `FanDuel_injuries_${season}_${week}_${activeContext.slate}.csv`);
  const [weeklyContestDirectory, setWeeklyContestDirectory] = useState("~/NFL");
  const [weeklyContestImport, setWeeklyContestImport] = useState<{
    discovered: number;
    imported: number;
    deduplicated: number;
    staged: number;
    skipped: number;
    failed: number;
    dry_run: boolean;
    files: DraftKingsBatchFile[];
  } | null>(null);
  const weeklyContestFiles = weeklyContestImport?.files.filter((file) => file.file_type === "contest_standings") ?? [];
  const [weeklyContestSelections, setWeeklyContestSelections] = useState<Record<string, {
    selected: boolean; season: number; week: number; slate: string;
  }>>({});
  const selectedWeeklyContestFiles = weeklyContestFiles.filter((file) => weeklyContestSelections[file.path]?.selected);
  const selectedWeeklyContestReady = selectedWeeklyContestFiles.length > 0 && selectedWeeklyContestFiles.every((file) => {
    const choice = weeklyContestSelections[file.path];
    return Boolean(file.source_file_id && choice && Number.isInteger(choice.season)
      && choice.season >= 2000 && Number.isInteger(choice.week)
      && choice.week >= 1 && choice.week <= 25 && SLATE_OPTIONS.includes(choice.slate));
  });
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
  const [learningReport, setLearningReport] = useState<WeeklyLearningReport | null>(null);
  const [learningError, setLearningError] = useState<string | null>(null);
  const learningScopeRef = useRef(`${season}:${week}`);
  learningScopeRef.current = `${season}:${week}`;
  useEffect(() => {
    setWeeklyContestImport(null);
    setWeeklyContestSelections({});
    setLearningReport(null);
    setLearningError(null);
  }, [season, week]);
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
  const [excludeQuestionable, setExcludeQuestionable] = useState(false);
  const [excludeOpponentTeams, setExcludeOpponentTeams] = useState<string>("DEN");
  const [excludePlayerIds, setExcludePlayerIds] = useState<string>("");
  const [lockedPlayers, setLockedPlayers] = useState<string>("");
  const [lockedPlayerIds, setLockedPlayerIds] = useState<string>("");
  const [flexOnlyPlayers, setFlexOnlyPlayers] = useState<string>("");
  const [playerDecisionControls, setPlayerDecisionControls] = useState<PlayerDecisionControl[]>([
    { playerName: "", availability: "default", excludeFromLineups: false },
  ]);
  const configuredAvailabilityOverrides = () => optimizerAvailabilityOverrides(
    playerDecisionControls, excludePlayers, excludePlayerIds,
  );
  const preferenceExcludedPlayers = playerDecisionControls
    .filter((row) => row.playerName.trim() && row.excludeFromLineups)
    .map((row) => row.playerName.trim());
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
    if (!salaryFileToLoad) return;
    setError(null);
    setPendingAction("Loading raw salaries...");
    try {
      const resp = await loadRawSalaries({ season, week, slate, path: salaryFileToLoad });
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
    if (!injuryFileToLoad) return;
    setError(null);
    setPendingAction("Loading raw injuries...");
    try {
      const resp = await loadRawInjuries({ season, week, slate, path: injuryFileToLoad });
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
    if (startupContext) {
      setFutureWeek(startupContext.week);
      return;
    }
    let cancelled = false;
    fetchCurrentContext()
      .then((context) => {
        if (cancelled) return;
        setSeason(context.season);
        setWeek(context.week);
        setFutureWeek(context.week);
        setActiveContextReady(true);
      })
      .catch(() => {
        if (cancelled) return;
        setSeason(FALLBACK_SEASON);
        setWeek(FALLBACK_WEEK);
        setFutureWeek(FALLBACK_WEEK);
        setActiveContextReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [startupContext]);

  useEffect(() => {
    if (!activeContextReady) return;
    try {
      window.localStorage.setItem(
        ACTIVE_SLATE_CONTEXT_STORAGE_KEY,
        serializeActiveSlateContext(activeContext),
      );
    } catch {
      // Browser storage can be unavailable; the active session remains usable.
    }
  }, [activeContext, activeContextReady]);

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
      const availabilityOverrides = configuredAvailabilityOverrides();
      const classicReportingUrls = selectedOptimizerStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID
        ? classicContestUrls(classicSmallFieldContestUrl) : [];
      const response = await createWeeklyRun({
        season,
        week,
        slate,
        draftkings_directory: weeklyDirectory.trim() || undefined,
        availability_overrides: availabilityOverrides,
        assume_questionable_out: excludeQuestionable,
        refresh_projections: true,
        contest_format: contestFormat,
        objective: effectiveOptimizerObjective,
        strategy: selectedOptimizerStrategy,
        num_simulations: 1000,
        optimizer_params: {
          num_lineups: longShotMode && effectiveOptimizerObjective === "gpp" ? 1 : selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID ? 1 : selectedOptimizerStrategy === SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID ? 5 : selectedOptimizerStrategy === SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID ? 3 : selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestUrls.split(/\r?\n/).filter((url) => url.trim()).length : numLineups,
          long_shot_mode: longShotMode && effectiveOptimizerObjective === "gpp",
          ...(selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestParams() : {}),
          ...(classicReportingUrls.length ? { contest_urls: classicReportingUrls } : {}),
          ...(selectedOptimizerStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID ? {
            classic_qb_family_diagnostics: classicQbFamilyDiagnostics,
            classic_solver_backend: "auto",
            classic_candidate_workers: 4,
            ...classicSmallFieldCandidateParams(longShotMode, slate, numLineups),
            ...classicPortfolioParams(),
          } : {}),
          ...((selectedOptimizerStrategy === SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID || selectedOptimizerStrategy === SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID) ? smallMaxContestParams() : {}),
          max_exposure: selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID || selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? 1 : maxExposure / 100,
          ...(contestFormat === "showdown" && effectiveOptimizerObjective === "gpp" && (showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID) ? {
            captain_max_exposure: requestedCaptainMaxExposure / 100,
            core_player_max_exposure: coreMaxExposure / 100,
            starting_qb_max_exposure: startingQbMaxExposure / 100,
            cheap_punt_max_exposure: cheapPuntMaxExposure / 100,
            showdown_decisive_margin: showdownDecisiveMargin,
            require_scenario_diversity: requireScenarioDiversity,
          } : {}),
          enforce_single_te: contestFormat === "showdown" ? false : enforceSingleTE,
          avoid_dst_opponents: avoidDstOpponents,
          ...(contestFormat === "classic" && (classicContestStrategy === CLASSIC_LARGE_GPP_STRATEGY_ID || classicContestStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID)
            ? {
                minimum_uniqueness: minimumUniqueness,
                max_players_per_team: maxPlayersPerTeam,
                max_players_per_game: maxPlayersPerGame,
              }
            : {}),
          availability_overrides: availabilityOverrides,
          exclusions_assumed_out: true,
          exclude_players: Array.from(new Set([
            ...excludePlayers.split(",").map((value) => value.trim()).filter(Boolean),
            ...preferenceExcludedPlayers,
          ])),
          exclude_opponent_teams: excludeOpponentTeams.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean),
          exclude_questionable: excludeQuestionable,
          exclude_player_ids: excludePlayerIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          locked_player_ids: lockedPlayerIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          locked_players: lockedPlayers
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

  const runAutoDiscover = async (resource: "salaries" | "injuries") => {
    setLoading(true);
    setError(null);
    setLoadError(null);
    setPendingAction(`Discovering ${resource} files...`);
    try {
      const response = resource === "salaries"
        ? await autoDiscoverSalaryFiles({ source_system: "draftkings", directory: ingestDirectory })
        : await autoDiscoverInjuryFiles({ source_system: "fanduel", directory: ingestDirectory });
      setLastLoadType(
        `${resource === "salaries" ? "Salary" : "Injury"} discovery: ${response.files_completed}/${response.files_attempted} files`
      );
      setLoadSummaries([
        {
          dataset: `auto_discover_${resource}`,
          season,
          week: null,
          rows_written: response.rows_curated,
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setLoadError(`Auto-discovery failed: ${msg}`);
    } finally {
      setLoading(false);
      setPendingAction(null);
    }
  };

  const runHistoricalLoad = async (resource: "bootstrap" | "game_data") => {
    const start = Math.min(historyStartSeason, historyEndSeason);
    const end = Math.max(historyStartSeason, historyEndSeason);
    const summaries: LoadSummary[] = [];
    setLoading(true);
    setError(null);
    setLoadError(null);
    setPendingAction(
      resource === "bootstrap"
        ? `Bootstrapping ${start}-${end}...`
        : `Loading schedules and weekly stats for ${start}-${end}...`
    );
    try {
      for (let value = start; value <= end; value += 1) {
        if (resource === "bootstrap") {
          const result = await bootstrapNflreadpy({ season: value });
          summaries.push({
            dataset: "nflreadpy_bootstrap",
            season: value,
            week: null,
            rows_written: result.rows_curated,
          });
        } else {
          const [schedules, weeklyStats] = await Promise.all([
            ingestNflreadpySchedules({ season: value }),
            ingestNflreadpyWeeklyStats({ season: value }),
          ]);
          summaries.push(
            {
              dataset: "nflreadpy_schedules",
              season: value,
              week: null,
              rows_written: schedules.rows_curated,
            },
            {
              dataset: "nflreadpy_weekly_stats",
              season: value,
              week: null,
              rows_written: weeklyStats.rows_curated,
            },
          );
        }
      }
      setLoadSummaries(summaries);
      setLastLoadType(
        resource === "bootstrap"
          ? `nflreadpy bootstrap ${start}-${end}`
          : `nflreadpy schedules + weekly stats ${start}-${end}`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setLoadError(`Historical load failed: ${msg}`);
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
    setError(null);
    setPendingAction("Reconciling slate player identities...");
    try {
      const availabilityOverrides = configuredAvailabilityOverrides();
      if (optimizerProjectionOverride) {
        throw new Error("Run Optimizer rebuilds current projections. Select Latest completed (automatic) before running.");
      }
      const classicReportingUrls = selectedOptimizerStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID
        ? classicContestUrls(classicSmallFieldContestUrl) : [];
      await reconcileSlateSalaryIdentities({ season, week, slate });
      setPendingAction("Refreshing slate features before projections...");
      await buildFeatureMatrix({ season, weeks: [week], slate });
      setPendingAction("Checking slate readiness...");
      const readiness = await fetchSlateReadiness({ season, week, slate, record: true });
      setSlateReadiness(readiness);
      const gateKey = optimizerReadinessGateKey(contestFormat, effectiveOptimizerObjective);
      if (readiness.gates.prediction.status === "fail") {
        throw new Error(`Projection rebuild blocked by slate readiness: ${readinessFailureMessage(readiness, "prediction")}`);
      }
      setPendingAction("Resolving starting QBs before projections...");
      const starterResponse = await loadStartingQBs({ season, week, slate });
      setStartingQBStatus(starterResponse);
      if (starterResponse.rows_written <= 0) {
        stageStartingQBCandidates(starterResponse.candidates);
        throw new Error(starterResponse.message || "No starting-QB evidence could be resolved for this slate.");
      }
      setPendingAction("Rebuilding projections using configured assumed-out players...");
      const scenarioProjection = await runPredictions({
        season,
        week,
        slate,
        availability_overrides: availabilityOverrides,
        assume_questionable_out: excludeQuestionable,
      });
      const projectionRunId = scenarioProjection.projection_run_id ?? undefined;
      if (!projectionRunId || scenarioProjection.rows_written <= 0 || !scenarioProjection.target_persisted) {
        throw new Error("Projection rebuild did not produce a persisted projection run. Optimization was not started.");
      }
      setPredictionStatus({ message: scenarioProjection.message, rows_written: scenarioProjection.rows_written });
      updateActiveRunSelection({ projectionRunId });
      await refreshOptimizerProjectionRuns();
      let ownershipRunId: string | undefined;
      if (effectiveOptimizerObjective === "gpp" && refreshOwnershipBeforeOptimize) {
        setPendingAction("Refreshing ownership before optimization...");
        const ownership = await runOwnershipModel({
          season,
          week,
          slate,
          projection_run_id: projectionRunId,
        });
        setOwnershipStatus(ownership);
        if (ownership.rows_written <= 0 || !ownership.ownership_run_id) {
          throw new Error(
            ownership.message || "Ownership refresh did not produce current-slate projections.",
          );
        }
        ownershipRunId = ownership.ownership_run_id;
      }
      const finalReadiness = await fetchSlateReadiness({ season, week, slate, record: true });
      setSlateReadiness(finalReadiness);
      if (finalReadiness.gates[gateKey].status === "fail") {
        throw new Error(`Optimizer blocked by slate readiness: ${readinessFailureMessage(finalReadiness, gateKey)}`);
      }
      const optimizerRunId = globalThis.crypto?.randomUUID?.()
        ?? `optimizer-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setPendingAction("Running optimizer...");
      const response = await runOptimizer({
        season,
        week,
        slate,
        strategy: selectedOptimizerStrategy,
        optimizer_run_id: optimizerRunId,
        contest_format: contestFormat,
        objective: effectiveOptimizerObjective,
        projection_run_id: projectionRunId,
        params: {
          num_lineups: longShotMode && effectiveOptimizerObjective === "gpp" ? 1 : selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID ? 1 : selectedOptimizerStrategy === SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID ? 5 : selectedOptimizerStrategy === SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID ? 3 : selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestUrls.split(/\r?\n/).filter((url) => url.trim()).length : numLineups,
          long_shot_mode: longShotMode && effectiveOptimizerObjective === "gpp",
          ...(ownershipRunId ? { ownership_run_id: ownershipRunId } : {}),
          ...(selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestParams() : {}),
          ...(classicReportingUrls.length ? { contest_urls: classicReportingUrls } : {}),
          ...(selectedOptimizerStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID ? {
            classic_qb_family_diagnostics: classicQbFamilyDiagnostics,
            classic_solver_backend: "auto",
            classic_candidate_workers: 4,
            ...classicSmallFieldCandidateParams(longShotMode, slate, numLineups),
            ...classicPortfolioParams(),
          } : {}),
          ...((selectedOptimizerStrategy === SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID || selectedOptimizerStrategy === SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID) ? smallMaxContestParams() : {}),
          max_exposure: selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID || selectedOptimizerStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? 1 : maxExposure / 100,
          ...(contestFormat === "showdown" && effectiveOptimizerObjective === "gpp" && (showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID) ? {
            captain_max_exposure: requestedCaptainMaxExposure / 100,
            core_player_max_exposure: coreMaxExposure / 100,
            starting_qb_max_exposure: startingQbMaxExposure / 100,
            cheap_punt_max_exposure: cheapPuntMaxExposure / 100,
            showdown_decisive_margin: showdownDecisiveMargin,
            require_scenario_diversity: requireScenarioDiversity,
          } : {}),
          enforce_single_te: contestFormat === "showdown" ? false : enforceSingleTE,
          avoid_dst_opponents: avoidDstOpponents,
          ...(contestFormat === "classic" && (classicContestStrategy === CLASSIC_LARGE_GPP_STRATEGY_ID || classicContestStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID)
            ? {
                minimum_uniqueness: minimumUniqueness,
                max_players_per_team: maxPlayersPerTeam,
                max_players_per_game: maxPlayersPerGame,
              }
            : {}),
          availability_overrides: availabilityOverrides,
          exclusions_assumed_out: true,
          exclude_players: Array.from(new Set([
            ...excludePlayers.split(",").map((s) => s.trim()).filter((s) => s.length > 0),
            ...preferenceExcludedPlayers,
          ])),
          exclude_opponent_teams: excludeOpponentTeams.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean),
          exclude_questionable: excludeQuestionable,
          exclude_player_ids: excludePlayerIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          locked_player_ids: lockedPlayerIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          locked_players: lockedPlayers
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
      }, () => setPendingAction("Optimizer is still running locally; waiting for its saved result..."));
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
    setPendingAction("Reconciling slate player identities...");
    try {
      const availabilityOverrides = configuredAvailabilityOverrides();
      await reconcileSlateSalaryIdentities({ season, week, slate });
      setPendingAction("Refreshing slate features...");
      await buildFeatureMatrix({ season, weeks: [week], slate });
      setPendingAction("Checking slate readiness...");
      const readiness = await fetchSlateReadiness({ season, week, slate, record: true });
      setSlateReadiness(readiness);
      if (readiness.gates.prediction.status === "fail") {
        throw new Error(`Prediction blocked by slate readiness: ${readinessFailureMessage(readiness, "prediction")}`);
      }
      setPendingAction("Resolving starting QBs...");
      const starterResponse = await loadStartingQBs({ season, week, slate });
      setStartingQBStatus(starterResponse);
      if (starterResponse.rows_written <= 0) {
        stageStartingQBCandidates(starterResponse.candidates);
        throw new Error(starterResponse.message || "No starting-QB evidence could be resolved for this slate.");
      }
      setStartingQBCandidates([]);
      setPendingAction("Running projections...");
      const response = await runPredictions({
        season,
        week,
        slate,
        availability_overrides: availabilityOverrides,
        assume_questionable_out: excludeQuestionable,
      });
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
      await refreshOptimizerProjectionRuns();
      setSlateReadiness(await fetchSlateReadiness({ season, week, slate, record: true }));
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
      if (response.rows_written <= 0) stageStartingQBCandidates(response.candidates);
      else setStartingQBCandidates([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingAction(null);
    }
  };

  const stageStartingQBCandidates = (candidates: StartingQBCandidate[]) => {
    setStartingQBCandidates(candidates);
    setStartingQBDrafts((current) => {
      const next = { ...current };
      for (const team of new Set(candidates.map((candidate) => candidate.team))) {
        if (!next[team]) {
          next[team] = {
            playerMasterId: "",
            evidenceTier: "inferred",
            sourceUri: "",
            note: "",
          };
        }
      }
      return next;
    });
  };

  const resolveStartingQBs = async () => {
    const teams = [...new Set(startingQBCandidates.map((candidate) => candidate.team))].sort();
    const drafts = teams.map((team) => ({ team, draft: startingQBDrafts[team] }));
    if (drafts.some(({ draft }) => !draft?.playerMasterId || !draft.sourceUri.trim())) {
      setError("Choose one QB and provide the supporting source URL for every unresolved team.");
      return;
    }
    setError(null);
    setPendingAction("Saving starting-QB evidence...");
    try {
      const response = await loadStartingQBs({
        season,
        week,
        slate,
        starters: drafts.map(({ team, draft }) => ({
          player_master_id: draft.playerMasterId,
          team,
          source: draft.evidenceTier === "confirmed"
            ? "operator_confirmed_source"
            : "provisional_operator_report",
          source_uri: draft.sourceUri.trim(),
          observed_at: new Date().toISOString(),
          evidence_tier: draft.evidenceTier,
          ...(draft.note.trim() ? { note: draft.note.trim() } : {}),
        })),
      });
      setStartingQBStatus(response);
      if (response.rows_written <= 0) {
        stageStartingQBCandidates(response.candidates);
        setError(response.message);
        return;
      }
      setStartingQBCandidates([]);
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
        const requestScope = `${season}:${week}`;
        window.localStorage.setItem("dfs-learning-entry-user", entryUser);
        setPendingAction("Refreshing post-slate learning report...");
        try {
          const report = await generateWeeklyLearningReport({
            season,
            week,
            entry_user: entryUser,
          });
          if (learningScopeRef.current === requestScope) {
            setLearningReport(report);
            setLearningError(null);
          }
        } catch (learningFailure) {
          if (learningScopeRef.current === requestScope) {
            setLearningError(
              learningFailure instanceof Error
                ? learningFailure.message
                : String(learningFailure),
            );
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setOwnershipError(msg);
    } finally {
      setPendingAction(null);
    }
  };

  const runWeeklyContestFolderImport = async (dryRun: boolean) => {
    const requestScope = `${season}:${week}`;
    setLearningError(null);
    if (dryRun) {
      setWeeklyContestImport(null);
      setWeeklyContestSelections({});
    }
    setPendingAction(dryRun ? "Checking weekly contest folder..." : "Loading weekly contest results...");
    try {
      const result = await importWeeklyContestFolder({
        directory: weeklyContestDirectory.trim(), season, week, dry_run: dryRun,
        ...(!dryRun ? { selected_files: selectedWeeklyContestFiles.map((file) => ({
          path: file.path,
          source_file_id: file.source_file_id ?? "",
          season: weeklyContestSelections[file.path].season,
          week: weeklyContestSelections[file.path].week,
          slate: weeklyContestSelections[file.path].slate,
        })) } : {}),
      });
      if (learningScopeRef.current !== requestScope) return;
      setWeeklyContestImport(result);
      if (dryRun) {
        setWeeklyContestSelections(Object.fromEntries(result.files
          .filter((file) => file.file_type === "contest_standings")
          .map((file) => [file.path, {
            selected: false, season: file.season, week: file.week,
            slate: SLATE_OPTIONS.includes(file.slate) ? file.slate : "",
          }])));
      } else {
        setWeeklyContestSelections({});
      }
      const selectedWeekLoaded = result.files.some((file) =>
        file.file_type === "contest_standings" &&
        ["imported", "deduplicated"].includes(file.status) &&
        file.season === season && file.week === week
      );
      if (!dryRun && learningEntryUser.trim() && selectedWeekLoaded) {
        setPendingAction("Building week learning report...");
        try {
          const report = await generateWeeklyLearningReport({
            season, week, entry_user: learningEntryUser.trim(),
          });
          if (learningScopeRef.current === requestScope) {
            setLearningReport(report);
            setLearningError(null);
          }
        } catch (learningFailure) {
          if (learningScopeRef.current === requestScope) {
            setLearningError(learningFailure instanceof Error ? learningFailure.message : String(learningFailure));
          }
        }
      }
    } catch (err) {
      if (learningScopeRef.current === requestScope) {
        setLearningError(err instanceof Error ? err.message : String(err));
      }
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

  const runWeeklyLearningReport = async () => {
    const entryUser = learningEntryUser.trim();
    if (!entryUser) return;
    const requestScope = `${season}:${week}`;
    setLearningError(null);
    setPendingAction("Pulling weekly stats and building post-slate learning report...");
    try {
      window.localStorage.setItem("dfs-learning-entry-user", entryUser);
      const report = await generateWeeklyLearningReport({
        season,
        week,
        entry_user: entryUser,
      });
      if (learningScopeRef.current === requestScope) setLearningReport(report);
    } catch (err) {
      if (learningScopeRef.current === requestScope) {
        setLearningError(err instanceof Error ? err.message : String(err));
        setLearningReport(null);
      }
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

  if (viewMode === "learning") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <div className="operations-workspace learning-workspace">
          <section className="operations-command" aria-labelledby="learning-command-title">
            <div className="operations-command-copy">
              <span className="operations-eyebrow"><i aria-hidden="true" /> Post-slate review</span>
              <h2 id="learning-command-title">Learn from a completed week.</h2>
              <p>Load your contest results and inspect where forecasts and lineups differed from the field.</p>
            </div>
            <div className="operations-context" aria-label="Learning week controls">
              <label>
                Season
                <input type="number" value={season} onChange={(event) => setSeason(Number(event.target.value))} />
              </label>
              <label>
                Week
                <input type="number" min={1} max={25} value={week} onChange={(event) => setWeek(Number(event.target.value))} />
              </label>
            </div>
          </section>
          <section className="panel operations-panel operations-data-panel" aria-labelledby="learning-import-title">
            <div className="operations-panel-heading">
              <span>01 · Import</span>
              <h2 id="learning-import-title">Contest results</h2>
              <p>Review downloaded standings, then load each contest under its verified week and slate.</p>
            </div>
            <div className="status-card">
              <p className="helper-text">
                Scan the folder and check the contest files you want. A unique match to a salary slate fills in
                the slate automatically; choose a slate only when the match is missing or ambiguous.
                Only checked files load. Files with no verified slate stay outside the report until you assign one.
                Loaded files move to Processed.
              </p>
              <div className="form-row column">
                <label>
                  Contest results folder
                  <input
                    className="full-width"
                    type="text"
                    value={weeklyContestDirectory}
                    onChange={(event) => setWeeklyContestDirectory(event.target.value)}
                    placeholder="~/NFL"
                  />
                </label>
                <div className="button-row">
                  <button onClick={() => runWeeklyContestFolderImport(true)} disabled={Boolean(pendingAction)}>
                    Scan contest folder
                  </button>
                  {weeklyContestImport?.dry_run && (
                    <button onClick={() => runWeeklyContestFolderImport(false)}
                      disabled={Boolean(pendingAction) || !selectedWeeklyContestReady}>
                      Load {selectedWeeklyContestFiles.length} selected {selectedWeeklyContestFiles.length === 1 ? "file" : "files"}
                    </button>
                  )}
                </div>
              </div>
              {weeklyContestImport && (
                <div className="table-wrap">
                  <p>
                    {weeklyContestImport.dry_run ? "Scan" : "Import"}: {weeklyContestFiles.length} contest files ·{" "}
                    {weeklyContestImport.discovered - weeklyContestFiles.length} other files ignored ·{" "}
                    {weeklyContestImport.imported} loaded · {weeklyContestImport.deduplicated} already loaded ·{" "}
                    {weeklyContestImport.dry_run
                      ? weeklyContestFiles.filter((file) => file.status === "would_stage").length
                      : weeklyContestImport.staged} {weeklyContestImport.dry_run ? "need scope" : "raw files staged"} ·{" "}
                    {weeklyContestFiles.filter((file) => file.status === "skipped").length} skipped ·{" "}
                    {weeklyContestImport.failed} failed
                  </p>
                  {weeklyContestImport.dry_run && <p className="helper-text">
                    “Needs slate” means no unique salary-player match was found. Check the files you want and
                    review their suggested season, week, and slate before loading. Leave unrelated files unchecked.
                  </p>}
                  <table className="compact-table learning-contest-table">
                    <thead><tr>{weeklyContestImport.dry_run && <th>Load</th>}<th>File</th><th>Season</th><th>Week</th><th>Slate</th><th>Status</th><th>Contest</th><th>Details</th></tr></thead>
                    <tbody>
                      {weeklyContestFiles.map((file) => (
                        <tr key={file.path}>
                          {weeklyContestImport.dry_run && <td><input type="checkbox" aria-label={`Load ${file.path.split("/").pop()}`}
                            checked={weeklyContestSelections[file.path]?.selected ?? false}
                            disabled={!file.source_file_id || file.status === "skipped" || file.status === "failed"}
                            onChange={(event) => setWeeklyContestSelections((current) => ({
                              ...current, [file.path]: { ...current[file.path], selected: event.target.checked },
                            }))} /></td>}
                          <td title={file.path}>{file.path.split("/").pop()}</td>
                          <td>{weeklyContestImport.dry_run ? <input type="number" min={2000} aria-label={`Season for ${file.path.split("/").pop()}`}
                            value={weeklyContestSelections[file.path]?.season ?? file.season}
                            onChange={(event) => setWeeklyContestSelections((current) => ({ ...current,
                              [file.path]: { ...current[file.path], season: Number(event.target.value) },
                            }))} /> : file.season}</td>
                          <td>{weeklyContestImport.dry_run ? <input type="number" min={1} max={25} aria-label={`Week for ${file.path.split("/").pop()}`}
                            value={weeklyContestSelections[file.path]?.week ?? file.week}
                            onChange={(event) => setWeeklyContestSelections((current) => ({ ...current,
                              [file.path]: { ...current[file.path], week: Number(event.target.value) },
                            }))} /> : file.week}</td>
                          <td>{weeklyContestImport.dry_run ? <select aria-label={`Slate for ${file.path.split("/").pop()}`}
                            value={weeklyContestSelections[file.path]?.slate ?? ""}
                            onChange={(event) => setWeeklyContestSelections((current) => ({ ...current,
                              [file.path]: { ...current[file.path], slate: event.target.value },
                            }))}>
                            <option value="">Choose slate</option>
                            {SLATE_OPTIONS.map((option) => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}
                          </select> : file.slate.replaceAll("_", " ")}</td>
                          <td>{file.status === "would_stage" || file.status === "staged"
                            ? weeklyContestSelections[file.path]?.slate ? "Ready to load" : "Needs slate"
                            : file.status === "would_import" ? "Ready to load"
                              : file.status === "deduplicated" ? "Already loaded"
                                : file.status.replaceAll("_", " ")}</td>
                          <td>{file.contest_id ?? "—"}</td>
                          <td title={file.message}>{weeklyContestImport.dry_run && file.status === "would_stage"
                            ? file.message || "Choose slate, then load"
                            : weeklyContestImport.dry_run && file.status === "would_import"
                              ? file.message ? "Matched salary slate; select to load" : "Verified; select to load"
                              : file.message || (file.source_file_id ? `Source ${file.source_file_id.slice(0, 16)}` : "—")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
          <section className="panel operations-panel" aria-labelledby="learning-report-title">
            <div className="operations-panel-heading">
              <span>02 · Review</span>
              <h2 id="learning-report-title">Week learning report</h2>
              <p>Compare entries with their predictions and inspect missing evidence by slate.</p>
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
                onClick={runWeeklyLearningReport}
                disabled={!learningEntryUser.trim() || pendingAction !== null}
              >
                Build Week Learning Report
              </button>
            </div>
            {learningError && <div className="error inline-error">{learningError}</div>}
            {learningReport && (
              <div className="status-card">
                <strong>
                  Week {learningReport.week} learning report: {learningReport.status} · {learningReport.summary.slates} slates · {learningReport.summary.contests_entered} contests · {learningReport.summary.entries} entries
                </strong>
                {learningReport.summary.weekly_stats && (
                  <p>Weekly stats pulled: {learningReport.summary.weekly_stats.rows_raw} player records for {learningReport.season}, week {learningReport.week}.</p>
                )}
                <p>
                  <button type="button" onClick={() => downloadWeeklyLearningReport(learningReport)}>
                    Download report for ChatGPT
                  </button>
                </p>
                <p>
                  {learningReport.summary.matched_optimizer_entries} optimizer matches ·{" "}
                  {learningReport.summary.entries_with_opt_007} OPT-007 controls ·{" "}
                  {learningReport.summary.duplicate_entries} duplicate entries
                </p>
                <p>
                  Entry-weighted projection MAE: {learningReport.summary.entry_weighted_projection_mae == null
                    ? "Unavailable"
                    : learningReport.summary.entry_weighted_projection_mae.toFixed(2)} ·{" "}
                  {learningReport.summary.entry_weighted_projection_observations} lineup-player observations ·{" "}
                  {learningReport.missing_evidence.length} missing-evidence notices
                </p>
                <p className="helper-text">{learningReport.interpretation}</p>
                {learningReport.slate_reports.map((report) => (
                  <details className="learning-entry-results" key={report.report_id}>
                    <summary>
                      {report.slate.replaceAll("_", " ")} · {report.summary.entries} entries ·{" "}
                      {report.summary.projection_mae == null ? "projection MAE unavailable" : `projection MAE ${report.summary.projection_mae.toFixed(2)}`}
                    </summary>
                    <p>
                      {report.summary.matched_optimizer_entries} optimizer matches ·{" "}
                      {report.summary.duplicate_entries} duplicate entries ·{" "}
                      {report.missing_evidence.length} evidence gaps
                    </p>
                    {report.portfolio_analysis.captain_exposure?.length ? (
                      <p>
                        Captain exposure: {report.portfolio_analysis.captain_exposure
                          .map((row) => `${row.player_display_name} ${row.pct.toFixed(0)}%`)
                          .join(" · ")}
                      </p>
                    ) : null}
                    <p>
                      Belief theses: {report.learning_outcomes.beliefs.supported} supported ·{" "}
                      {report.learning_outcomes.beliefs.contradicted} contradicted ·{" "}
                      {report.learning_outcomes.beliefs.theses_scored} scored
                    </p>
                    <ul>
                      {report.entries.map((entry, index) => {
                        const rank = typeof entry.rank === "number" ? entry.rank : null;
                        const fieldSize = typeof entry.field_size === "number" ? entry.field_size : null;
                        const topPercent = typeof entry.top_percent === "number" ? entry.top_percent : null;
                        const actualPoints = typeof entry.entry_points === "number" ? entry.entry_points : null;
                        const projectedPoints = typeof entry.projected_points === "number" ? entry.projected_points : null;
                        const players = Array.isArray(entry.players) ? entry.players as Array<Record<string, unknown>> : [];
                        return (
                          <li key={`${String(entry.contest_id ?? "contest")}:${String(entry.entry_id ?? index)}`}>
                            Entry {String(entry.entry_id ?? index)} ·{" "}
                            {rank != null && fieldSize != null ? `${rank.toLocaleString()} / ${fieldSize.toLocaleString()}` : "Rank unavailable"}
                            {topPercent != null ? ` · top ${topPercent.toFixed(2)}%` : ""}
                            {actualPoints != null ? ` · actual ${actualPoints.toFixed(2)} pts` : ""}
                            {projectedPoints != null ? ` · projected ${projectedPoints.toFixed(2)} pts${actualPoints != null ? ` · difference ${(actualPoints - projectedPoints).toFixed(2)} pts` : ""}` : " · projection unavailable"}
                            {entry.lineup_match_basis ? ` · ${String(entry.lineup_match_basis).replaceAll("_", " ")}` : ""}
                            {players.length > 0 && (
                              <details>
                                <summary>Player predictions and results</summary>
                                <ul>
                                  {players.map((player, playerIndex) => {
                                    const isCaptain = player.roster_position === "CPT";
                                    return (
                                      <li key={`${String(player.player_id ?? playerIndex)}:${String(player.roster_position ?? "")}`}>
                                        {String(player.roster_position ?? "")} {String(player.player_display_name ?? "Player")}: {isCaptain && typeof player.projected_base_points === "number" ? `${player.projected_base_points.toFixed(2)} base × 1.5 = ` : ""}{typeof player.projected_points === "number" ? player.projected_points.toFixed(2) : "—"} projected · {isCaptain && typeof player.actual_base_points === "number" ? `${player.actual_base_points.toFixed(2)} base × 1.5 = ` : ""}{typeof player.actual_points === "number" ? player.actual_points.toFixed(2) : "—"} actual
                                        {typeof player.projection_residual === "number" ? ` · difference ${player.projection_residual.toFixed(2)}` : ""}
                                      </li>
                                    );
                                  })}
                                </ul>
                              </details>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                ))}
                {learningReport.missing_evidence.length > 0 && (
                  <details>
                    <summary>Review missing evidence</summary>
                    <ul>
                      {learningReport.missing_evidence.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </details>
                )}
                <small>Report {learningReport.report_id}</small>
              </div>
            )}
          </section>
        </div>
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
              placeholder="~/NFL"
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
                placeholder="~/NFL/DKSalaries_2026_3_SUNDAY_MAIN.csv"
              />
            </label>
            <small>{salaryFileToLoad ? `Will load: ${salaryFileToLoad}` : "Enter a CSV filename."}</small>
            <button disabled={!salaryFileToLoad} onClick={runLoadRawSalaries}>Load Raw Salaries (CSV)</button>
          </div>
          <div className="form-row column">
            <label>
              Injury file
              <input
                className="full-width"
                type="text"
                value={injuryPath}
                onChange={(event) => setInjuryPath(event.target.value)}
                placeholder="~/NFL/FanDuel_injuries_2026_3_SUNDAY_MAIN.csv"
              />
            </label>
            <small>{injuryFileToLoad ? `Will load: ${injuryFileToLoad}` : "Enter a CSV filename."}</small>
            <button disabled={!injuryFileToLoad} onClick={runLoadRawInjuries}>Load Raw Injuries (CSV)</button>
          </div>
          <details className="contest-evidence-editor">
            <summary>
              <span>
                <strong>Bulk and historical ingestion</strong>
                <small>Auto-discover local source files or backfill nflreadpy history.</small>
              </span>
              <span className="evidence-posture">Operations only</span>
            </summary>
            <div className="contest-evidence-body">
              <div className="form-row column">
                <label>
                  DraftKings download directory
                  <input
                    className="full-width"
                    type="text"
                    value={ingestDirectory}
                    onChange={(event) => setIngestDirectory(event.target.value)}
                    placeholder="~/NFL"
                  />
                </label>
                <div className="button-row">
                  <button disabled={loading} onClick={() => runAutoDiscover("salaries")}>
                    Auto Import Salaries
                  </button>
                  <button disabled={loading} onClick={() => runAutoDiscover("injuries")}>
                    Auto Import Injuries
                  </button>
                </div>
              </div>
              <div className="form-row">
                <label>
                  Start season
                  <input
                    type="number"
                    value={historyStartSeason}
                    onChange={(event) => setHistoryStartSeason(Number(event.target.value))}
                  />
                </label>
                <label>
                  End season
                  <input
                    type="number"
                    value={historyEndSeason}
                    onChange={(event) => setHistoryEndSeason(Number(event.target.value))}
                  />
                </label>
              </div>
              <div className="button-row">
                <button disabled={loading} onClick={() => runHistoricalLoad("bootstrap")}>
                  Bootstrap Season Range
                </button>
                <button disabled={loading} onClick={() => runHistoricalLoad("game_data")}>
                  Load Historical Game Data
                </button>
              </div>
            </div>
          </details>
          <div className="form-row column">
            <label>
              Ownership file
              <input
                className="full-width"
                type="text"
                value={ownershipPath}
                onChange={(event) => setOwnershipPath(event.target.value)}
                placeholder="~/NFL/ownership.csv"
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
                disabled={!/\.(csv|tsv|tab|zip)$/i.test(ownershipPath.trim()) || pendingAction !== null}
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
                {ownershipStatus.ownership_run_id && <small>Run {ownershipStatus.ownership_run_id.slice(0, 8)} · model {ownershipStatus.model_id ?? "version unavailable"} · target lineage {ownershipStatus.target_persisted ? "persisted" : "unavailable"}</small>}
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
              <button disabled={!/\.(csv|tsv|tab|zip)$/i.test(ownershipPath.trim())} onClick={runPastSlateAnalysis}>Analyze Past Slate (Top N)</button>
            </div>
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
          {startingQBCandidates.length > 0 && (
            <div className="status-card">
              <h3>Starting-QB review required</h3>
              <p>
                Automatic evidence could not select one QB for every team. Choose a
                candidate only with a supporting source. “Provisional” records the
                uncertainty and can be replaced when the team confirms its starter.
              </p>
              {[...new Set(startingQBCandidates.map((candidate) => candidate.team))]
                .sort()
                .map((team) => {
                  const draft = startingQBDrafts[team] ?? {
                    playerMasterId: "",
                    evidenceTier: "inferred" as const,
                    sourceUri: "",
                    note: "",
                  };
                  const updateDraft = (change: Partial<StartingQBDraft>) => {
                    setStartingQBDrafts((current) => ({
                      ...current,
                      [team]: { ...draft, ...change },
                    }));
                  };
                  return (
                    <div className="form-row" key={team}>
                      <label>
                        {team} QB
                        <select
                          value={draft.playerMasterId}
                          onChange={(event) => updateDraft({ playerMasterId: event.target.value })}
                        >
                          <option value="">Select evidence-backed QB</option>
                          {startingQBCandidates
                            .filter((candidate) => candidate.team === team)
                            .map((candidate) => (
                              <option key={candidate.player_master_id} value={candidate.player_master_id}>
                                {candidate.player_name} · ${candidate.salary.toLocaleString()}
                                {candidate.depth_chart_position ? ` · ${candidate.depth_chart_position}` : ""}
                              </option>
                            ))}
                        </select>
                      </label>
                      <label>
                        Evidence
                        <select
                          value={draft.evidenceTier}
                          onChange={(event) => updateDraft({
                            evidenceTier: event.target.value as StartingQBDraft["evidenceTier"],
                          })}
                        >
                          <option value="confirmed">Confirmed by source</option>
                          <option value="inferred">Provisional — team undecided</option>
                        </select>
                      </label>
                      <label>
                        Source URL
                        <input
                          type="url"
                          value={draft.sourceUri}
                          onChange={(event) => updateDraft({ sourceUri: event.target.value })}
                          placeholder="https://…"
                        />
                      </label>
                      <label>
                        Note (optional)
                        <input
                          value={draft.note}
                          onChange={(event) => updateDraft({ note: event.target.value })}
                          placeholder="Why this QB is expected to start"
                        />
                      </label>
                    </div>
                  );
                })}
              <div className="button-row">
                <button onClick={resolveStartingQBs}>Save Starting-QB Evidence</button>
              </div>
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
            <div className="optimizer-injury-preference">
              <label>
                <input
                  type="checkbox"
                  checked={excludeQuestionable}
                  onChange={(event) => setExcludeQuestionable(event.target.checked)}
                />
                <span>Exclude questionable (Q) players</span>
              </label>
              <small>Assumes questionable players are out. Run Optimizer rebuilds projections and redistributes their workload before selecting lineups.</small>
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
              </label> : <p>{showdownGppStrategy === SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID ? "1 single-entry contest" : showdownGppStrategy === SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID ? "One small-max contest; entry count selected below" : showdownGppStrategy === SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID ? "One 3-max contest; entries selected below" : "Contest count selected from pasted single-entry contests"}</p>}
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
            {selectedOptimizerStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID && <div className="form-row classic-portfolio-controls">
              <label>
                Max shared players (optional)
                <input type="number" min={0} max={8} value={classicMaxLineupOverlap}
                  onChange={(event) => setClassicMaxLineupOverlap(event.target.value)}
                  placeholder="Default: 6 shared players" />
              </label>
              <label>
                Max selector loss (optional)
                <input type="number" min={0} step="0.01" value={classicMaxObjectiveLoss}
                  onChange={(event) => setClassicMaxObjectiveLoss(event.target.value)}
                  placeholder="No quality floor" />
              </label>
              <label>Max primary QB stacks per game (optional)
                <input type="number" min={1} max={numLineups} value={classicPrimaryGameCap}
                  onChange={(event) => setClassicPrimaryGameCap(event.target.value)} placeholder="No game cap" />
              </label>
              <label>Max appearances per skill player (optional)
                <input type="number" min={1} max={numLineups} value={classicSkillMaxAppearances}
                  onChange={(event) => setClassicSkillMaxAppearances(event.target.value)} placeholder="Existing caps" />
              </label>
              <label className="checkbox-label">
                <input type="checkbox" checked={classicExpandedDiscovery}
                  onChange={(event) => setClassicExpandedDiscovery(event.target.checked)} />
                Expanded candidate discovery (slower)
              </label>
              <label className="checkbox-label">
                <input type="checkbox" checked={classicDistinctQbPaths}
                  onChange={(event) => setClassicDistinctQbPaths(event.target.checked)} />
                Different QB in each lineup
              </label>
            </div>}
            <ContestLibrary
              season={season} week={week} slate={slate} contestFormat={contestFormat}
              onActivateScope={(scope) => {
                if (scope.season !== season || scope.week !== week || scope.slate !== slate || scope.contest_format !== contestFormat) {
                  setSingleEntryContestUrls("");
                  setSmallMaxContestUrl("");
                  setContestPreview(null);
                }
                setSeason(scope.season);
                setWeek(scope.week);
                setActiveSlate(scope.slate);
                setContestFormat(scope.contest_format);
                if (scope.contest_format === "showdown") setOptimizerObjective(scope.contest_type === "gpp" ? "gpp" : "cash");
              }}
              optimizerUrls={contestFormat === "showdown" && optimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? singleEntryContestUrls : showdownGppStrategy === SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID ? smallMaxContestUrl : showdownGppStrategy === SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID ? smallMaxContestUrl : undefined}
              allowUseAll={showdownGppStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID}
              onUseUrls={contestFormat === "showdown" && optimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID ? (urls) => {
                const current = singleEntryContestUrls.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
                setSingleEntryContestUrls([...new Set([...current, ...urls])].join("\n"));
                setContestPreview(null);
              } : contestFormat === "showdown" && optimizerObjective === "gpp" && (showdownGppStrategy === SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID || showdownGppStrategy === SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID) ? (urls) => {
                if (urls.length !== 1) { setContestPreviewError("Small-max uses one contest; choose a single saved URL."); return; }
                setSmallMaxContestUrl(urls[0]);
                setSmallMaxEntriesToUse("auto");
                setContestPreview(null);
                setContestPreviewError(null);
              } : contestFormat === "showdown" && optimizerObjective === "gpp" && (showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID) ? (urls, contests) => {
                const maximumEntries = contests[0]?.latest_contest?.maximum_entries ?? contests[0]?.latest_successful_contest?.maximum_entries;
                if (maximumEntries != null && (Number(maximumEntries) < 2 || Number(maximumEntries) > 5)) { setContestPreviewError("Choose a saved 2–5 max contest for this mode."); return; }
                if (urls.length !== 1) { setContestPreviewError("Small-max uses one contest; choose a single saved URL."); return; }
                setSmallMaxContestUrl(urls[0]);
                setSmallMaxEntriesToUse("auto");
                setShowdownGppStrategy(SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID);
                setContestPreview(null);
                setContestPreviewError(null);
              } : undefined}
            />
            {contestFormat === "showdown" && optimizerObjective === "gpp" && (
              <div className="form-row">
                <label>Showdown GPP strategy
                  <select value={showdownGppStrategy} onChange={(event) => { setShowdownGppStrategy(event.target.value); setContestPreview(null); setContestPreviewError(null); }}>
                    <option value={SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID}>Multi-entry GPP portfolio</option>
                    <option value={SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID}>Single-entry GPP</option>
                    <option value={SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID}>Single-entry contest portfolio</option>
                    <option value={SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID}>Small-max GPP</option>
                  </select>
                </label>
              </div>
            )}
            {contestFormat === "showdown" && optimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID && contestPreviewError && <p role="alert">{contestPreviewError}</p>}
            {contestFormat === "showdown" && optimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID && <div className="status-card nested-card">
              <h3>Small-max GPP</h3>
              <label>DraftKings contest URL (optional)<input className="full-width" value={smallMaxContestUrl} onChange={(event) => { setSmallMaxContestUrl(event.target.value); setSmallMaxEntriesToUse("auto"); setContestPreview(null); }} placeholder="https://www.draftkings.com/draft/contest/195677836" /></label>
              {!smallMaxContestUrl.trim() && <label>Entry limit for generic lineup building<select value={smallMaxMaximumEntries} onChange={(event) => { setSmallMaxMaximumEntries(Number(event.target.value)); setSmallMaxEntriesToUse("auto"); }}>{[2, 3, 4, 5].map((count) => <option key={count} value={count}>{count}</option>)}</select></label>}
              <div className="form-row"><label>Entries to use<select value={smallMaxEntriesToUse} onChange={(event) => setSmallMaxEntriesToUse(event.target.value)}><option value="auto">{smallMaxContestUrl.trim() ? "Auto · compare 1 through contest maximum" : "Auto · strongest single lineup"}</option>{Array.from({ length: Math.min(5, Number(smallMaxContestUrl.trim() ? contestPreview?.contests[0]?.maximum_entries ?? 5 : smallMaxMaximumEntries)) }, (_, index) => index + 1).map((count) => <option key={count} value={count}>{count}</option>)}</select></label></div>
              <button disabled={!smallMaxContestUrl.trim() || contestPreviewPending} onClick={async () => { setContestPreviewPending(true); setContestPreviewError(null); try { const params = smallMaxContestParams(); setContestPreview(await previewOptimizerContests({ urls: params.contest_urls, manual_contest_metadata: params.manual_contest_metadata })); } catch (error) { setContestPreviewError(error instanceof Error ? error.message : String(error)); } finally { setContestPreviewPending(false); } }}>{contestPreviewPending ? "Refreshing contest…" : "Preview / refresh contest details"}</button>
              {contestPreviewError && <p role="alert">{contestPreviewError}</p>}
              {contestPreview && <p>{String(contestPreview.contests[0]?.name ?? "Contest details unavailable")} · maximum entries: {String(contestPreview.contests[0]?.maximum_entries ?? "unavailable")} · entry fee: {String(contestPreview.contests[0]?.entry_fee ?? "unavailable")} · payout tiers: {(contestPreview.contests[0]?.payout_ladder as unknown[] | undefined)?.length ?? 0} · missing: {(contestPreview.contests[0]?.unavailable_fields as string[] | undefined)?.join(", ") || "none"}</p>}
              {smallMaxContestUrl.trim() && <details><summary>Manual metadata for unavailable contest fields</summary><p>JSON array keyed by contest_id. Missing fields are listed by preview; the optimizer verifies a 2–5 entry limit and the full payout ladder.</p><textarea className="full-width" rows={4} value={smallMaxManual} onChange={(event) => setSmallMaxManual(event.target.value)} placeholder='[{"contest_id":"123","maximum_entries":3}]' /></details>}
              <div className="form-row">
                <label>CPT max (%)<input type="number" min={1} max={100} value={smallMaxCaptainMaxExposure} onChange={(event) => setSmallMaxCaptainMaxExposure(Number(event.target.value))} /></label>
                <label>Player max (%)<input type="number" min={1} max={100} value={smallMaxPlayerMaxExposure} onChange={(event) => setSmallMaxPlayerMaxExposure(Number(event.target.value))} /></label>
                <label>Starting QB max (%)<input type="number" min={1} max={100} value={smallMaxStartingQbMaxExposure} onChange={(event) => setSmallMaxStartingQbMaxExposure(Number(event.target.value))} /></label>
                <label>Cheap punt max (%)<input type="number" min={1} max={100} value={smallMaxCheapPuntMaxExposure} onChange={(event) => setSmallMaxCheapPuntMaxExposure(Number(event.target.value))} /></label>
              </div>
              <p>{smallMaxContestUrl.trim() ? "Contest must allow 2–5 entries per user. Auto compares every entry count through the verified limit." : "Without a contest, Auto returns the strongest single lineup. Choose an explicit count to build more entries; payout, fees, field size, and ROI are unavailable."} Exposures default to 100%.</p>
            </div>}
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
            {contestFormat === "showdown" && optimizerObjective === "gpp" && (showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID) && (
              <div className="form-row">
                <label>CPT max (%)<input ref={captainMaxExposureInputRef} type="number" min={1} max={100} value={captainMaxExposure} onChange={(event) => setCaptainMaxExposure(Number(event.target.value))} /></label>
                <label>Core max (%)<input type="number" min={1} max={100} value={coreMaxExposure} onChange={(event) => setCoreMaxExposure(Number(event.target.value))} /></label>
                <label>Starting QB max (%)<input type="number" min={1} max={100} value={startingQbMaxExposure} onChange={(event) => setStartingQbMaxExposure(Number(event.target.value))} /></label>
                <label>Cheap punt max (%)<input type="number" min={1} max={100} value={cheapPuntMaxExposure} onChange={(event) => setCheapPuntMaxExposure(Number(event.target.value))} /></label>
              </div>
            )}
            {contestFormat === "showdown" && optimizerObjective === "gpp" && showdownGppStrategy === SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID && <div className="form-row">
              <label>Decisive-win margin (points)<input type="number" min={7} max={35} step={1} value={showdownDecisiveMargin} onChange={(event) => setShowdownDecisiveMargin(Number(event.target.value))} /></label>
              <label><input type="checkbox" checked={requireScenarioDiversity} onChange={(event) => setRequireScenarioDiversity(event.target.checked)} /> Require scenario diversity</label>
              <small>Off by default. When on, qualifying scenario families are represented where possible under the existing quality and exposure limits.</small>
            </div>}
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
                      } else if (next === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID) {
                        setNumLineups(5);
                        setMaxExposure(100);
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
            {contestFormat === "classic" && classicContestStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID && (
              <div className="status-card nested-card">
                <h3>Classic contest context</h3>
                <label>DraftKings contest URL (optional, one URL, reporting only)
                  <input className="full-width" value={classicSmallFieldContestUrl} onChange={(event) => { setClassicSmallFieldContestUrl(event.target.value); setContestPreview(null); setContestPreviewError(null); }} placeholder="https://www.draftkings.com/draft/contest/123456789" />
                </label>
                <label><input type="checkbox" checked={classicQbFamilyDiagnostics} onChange={(event) => setClassicQbFamilyDiagnostics(event.target.checked)} /> Compute exact top-10 QB stack families (up to 40 additional solver calls)</label>
                <button disabled={!classicSmallFieldContestUrl.trim() || contestPreviewPending} onClick={async () => {
                  setContestPreviewPending(true); setContestPreviewError(null);
                  try { setContestPreview(await previewOptimizerContests({ urls: classicContestUrls(classicSmallFieldContestUrl) })); }
                  catch (error) { setContestPreviewError(error instanceof Error ? error.message : String(error)); }
                  finally { setContestPreviewPending(false); }
                }}>{contestPreviewPending ? "Refreshing contest…" : "Preview / refresh contest details"}</button>
                {contestPreviewError && <p role="alert">{contestPreviewError}</p>}
                {contestPreview && <p>{String(contestPreview.contests[0]?.name ?? "Contest details unavailable")} · entry fee {String(contestPreview.contests[0]?.entry_fee ?? "unavailable")} · field {String(contestPreview.contests[0]?.capacity ?? "unavailable")} · missing: {(contestPreview.contests[0]?.unavailable_fields as string[] | undefined)?.join(", ") || "none"}</p>}
              </div>
            )}
            {contestFormat === "classic" && (classicContestStrategy === CLASSIC_LARGE_GPP_STRATEGY_ID || classicContestStrategy === CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID) && (
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
              const ownershipRefreshPending = effectiveOptimizerObjective === "gpp"
                && refreshOwnershipBeforeOptimize && attention.has("ownership_projection");
              const visibleWarnings = gate.attention_checks.length - Number(ownershipRefreshPending);
              const checks = slateReadiness.checks
                .filter((check) => attention.has(check.check_id)
                  && !(ownershipRefreshPending && check.check_id === "ownership_projection"))
                .sort((left, right) => Number(blocking.has(right.check_id)) - Number(blocking.has(left.check_id)))
                .slice(0, 3);
              return (
                <div className={`readiness-preflight ${gate.status}`} role="status">
                  <div>
                    <span>Slate preflight · {contestFormat} {effectiveOptimizerObjective}</span>
                    <strong>{gate.status === "fail" ? "Blocked" : visibleWarnings > 0 ? "Ready with warnings" : ownershipRefreshPending ? "Ready pending ownership refresh" : "Ready"}</strong>
                    <small>{gate.score}/100{ownershipRefreshPending ? " before ownership refresh" : ""} · {gate.status === "fail" ? gate.message : `${visibleWarnings} warning${visibleWarnings === 1 ? "" : "s"}${ownershipRefreshPending ? "; ownership refresh scheduled" : ""}.`}</small>
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
              {effectiveOptimizerObjective === "gpp" && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={longShotMode}
                    onChange={(event) => setLongShotMode(event.target.checked)}
                  />
                  Create one standalone long-shot lineup
                  <small>Strongly favors low ownership when complete ownership data is available. Otherwise the report marks contrarian confidence unavailable.</small>
                </label>
              )}
              {contestFormat === "classic" && <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={enforceSingleTE}
                  onChange={(event) => setEnforceSingleTE(event.target.checked)}
                />
                Enforce single TE (no double-TE lineups)
              </label>}
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={avoidDstOpponents}
                  onChange={(event) => setAvoidDstOpponents(event.target.checked)}
                />
                No offense vs DST
              </label>
            </div>
            <section className="player-decision-controls" aria-label="Player availability and lineup preferences">
              <div className="player-decision-header">
                <div>
                  <strong>Player decisions</strong>
                  <small>Excluded players are assumed out when projections rebuild. Exposure, overlap, and Captain controls apply when selecting lineups.</small>
                </div>
                <button
                  type="button"
                  onClick={() => setPlayerDecisionControls((current) => [
                    ...current,
                    { playerName: "", availability: "default", excludeFromLineups: false },
                  ])}
                >Add player</button>
              </div>
              {playerDecisionControls.map((control, index) => (
                <div className="player-decision-row" key={`player-decision-${index}`}>
                  <label>
                    Player
                    <input
                      type="text"
                      value={control.playerName}
                      onChange={(event) => setPlayerDecisionControls((current) => current.map((row, rowIndex) => (
                        rowIndex === index ? { ...row, playerName: event.target.value } : row
                      )))}
                      placeholder="e.g. Puka Nacua"
                    />
                  </label>
                  <label>
                    Availability
                    <select
                      value={control.availability}
                      onChange={(event) => setPlayerDecisionControls((current) => current.map((row, rowIndex) => (
                        rowIndex === index ? {
                          ...row,
                          availability: event.target.value as PlayerDecisionControl["availability"],
                        } : row
                      )))}
                    >
                      <option value="default">Default</option>
                      <option value="assume_active">Assume Active</option>
                      <option value="assume_out">Assume Out</option>
                    </select>
                  </label>
                  <label className="checkbox-label player-preference-checkbox">
                    <input
                      type="checkbox"
                      checked={control.excludeFromLineups}
                      onChange={(event) => setPlayerDecisionControls((current) => current.map((row, rowIndex) => (
                        rowIndex === index ? { ...row, excludeFromLineups: event.target.checked } : row
                      )))}
                    />
                    Exclude and assume out
                  </label>
                  <button
                    type="button"
                    disabled={playerDecisionControls.length === 1}
                    onClick={() => setPlayerDecisionControls((current) => current.filter((_, rowIndex) => rowIndex !== index))}
                  >Remove</button>
                </div>
              ))}
            </section>
            <div className="form-row optimizer-player-controls">
              <label className="text-label">
                Hard exclude players facing teams (comma-separated codes)
                <input
                  type="text"
                  value={excludeOpponentTeams}
                  onChange={(event) => setExcludeOpponentTeams(event.target.value)}
                  placeholder="e.g. DEN"
                />
              </label>
              <label className="text-label">
                Exclude and assume out players (comma-separated names)
                <input
                  type="text"
                  value={excludePlayers}
                  onChange={(event) => setExcludePlayers(event.target.value)}
                  placeholder="e.g. George Kittle, Skyy Moore"
                />
              </label>
              <label className="text-label">
                Exclude and assume out canonical player IDs
                <input
                  type="text"
                  value={excludePlayerIds}
                  onChange={(event) => setExcludePlayerIds(event.target.value)}
                  placeholder="Comma-separated player_master_id values"
                />
              </label>
              <label className="text-label">
                Lock players in every lineup (comma-separated names)
                <input
                  type="text"
                  value={lockedPlayers}
                  onChange={(event) => setLockedPlayers(event.target.value)}
                  placeholder="e.g. Derrick Henry, Trey McBride"
                />
              </label>
              <label className="text-label">
                Lock canonical player IDs (advanced)
                <input
                  type="text"
                  value={lockedPlayerIds}
                  onChange={(event) => setLockedPlayerIds(event.target.value)}
                  placeholder="Required in every lineup"
                />
              </label>
              {contestFormat === "showdown" && (
                <label className="text-label">
                  Exclude from Captain (FLEX still allowed; comma-separated names)
                  <input
                    type="text"
                    value={flexOnlyPlayers}
                    onChange={(event) => setFlexOnlyPlayers(event.target.value)}
                    placeholder="e.g. Malik Nabers, Wan'Dale Robinson"
                  />
                  <small>Applies to every generated lineup in this run. The players remain eligible at FLEX.</small>
                </label>
              )}
            </div>
            <div className="button-row">
              <div className="text-label">
                <label>Optimizer projection
                  <select value={optimizerProjectionOverride ?? ""} onChange={(event) => {
                    const selected = event.target.value;
                    setOptimizerProjectionOverrides((current) => {
                      const next = { ...current };
                      if (selected) next[activeContextKey] = selected;
                      else delete next[activeContextKey];
                      return next;
                    });
                  }}>
                    <option value="">{optimizerProjectionRuns[0] ? `Latest completed (automatic) · ${new Date(optimizerProjectionRuns[0].created_at).toLocaleString()} · ${optimizerProjectionRuns[0].projection_run_id.slice(0, 8)} · model artifact ${optimizerProjectionRuns[0].model_artifact_status ?? "unknown"}` : "Latest completed (automatic)"}</option>
                    {optimizerProjectionRuns.slice(1).map((run) => <option key={run.projection_run_id} value={run.projection_run_id}>{new Date(run.created_at).toLocaleString()} · {run.projection_run_id.slice(0, 8)} · {run.row_count} players · model artifact {run.model_artifact_status ?? "unknown"}</option>)}
                    {optimizerProjectionOverride && !optimizerProjectionRuns.some((run) => run.projection_run_id === optimizerProjectionOverride) && <option value={optimizerProjectionOverride} disabled>Selected projection unavailable</option>}
                  </select>
                </label>
                <button type="button" onClick={() => { refreshOptimizerProjectionRuns().catch(() => undefined); }} disabled={optimizerProjectionPending}>
                  {optimizerProjectionPending ? "Checking projections…" : "Refresh projections"}
                </button>
                <small>{optimizerProjectionOverride ? `Using older projection ${optimizerProjectionOverride}` : optimizerProjectionRuns[0] ? `Automatic latest: ${optimizerProjectionRuns[0].projection_run_id}` : "The optimizer needs a completed projection for this slate."}</small>
                {optimizerProjectionRuns.find((run) => run.projection_run_id === (optimizerProjectionOverride || optimizerProjectionRuns[0]?.projection_run_id))?.model_artifact_status === "missing" && <small role="status">This projection run has no reloadable fitted model artifact. Player market rescoring is unavailable.</small>}
                {optimizerProjectionMessage && <small role="status">{optimizerProjectionMessage}</small>}
              </div>
              {effectiveOptimizerObjective === "gpp" && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={refreshOwnershipBeforeOptimize}
                    onChange={(event) => setRefreshOwnershipBeforeOptimize(event.target.checked)}
                  />
                  Refresh ownership before optimizing
                </label>
              )}
              <small>Run Optimizer rebuilds projections using your player availability and exclusions before generating lineups. Use Latest completed (automatic).</small>
              <button className="operations-primary-action" onClick={runOptimizerJob} disabled={Boolean(pendingAction)}>Run Optimizer</button>
              {pendingAction && <small role="status">{pendingAction}</small>}
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
                const report = (optimizerStatus.results[0] as any[])?.[0]?.long_shot_report;
                if (!report) return null;
                return <div className="status-card nested-card">
                  <h4>Long-shot lineup</h4>
                  <p>{report.note}</p>
                  <p>Ownership evidence: {report.ownership_status} · ownership sum: {report.ownership_sum == null ? "Unavailable" : Number(report.ownership_sum).toFixed(1)} · method: {String(report.method).replaceAll("_", " ")}</p>
                </div>;
              })()}
              {Array.isArray(optimizerStatus.results) && (() => {
                const contest = (optimizerStatus.results[0] as any[])?.[0]?.portfolio_contest_report;
                if (!contest) return null;
                const economics = contest.economics ?? {};
                return <div className="status-card nested-card">
                  <h4>5-max contest: {contest.name}</h4>
                  <p>Verified maximum {contest.maximum_entries} entries · {contest.generated_entries}/{contest.requested_entries} lineups generated · ${Number(contest.generated_entry_cost).toFixed(2)} for generated entries (${Number(contest.requested_entry_cost).toFixed(2)} if all five are entered).</p>
                  <p>Filled {contest.current_entries}/{contest.capacity} · pool ${contest.prize_pool} · paid {(Number(economics.paid_percentage) * 100).toFixed(1)}% · min cash ${economics.minimum_cash} · full-field rake {(Number(economics.full_field_rake) * 100).toFixed(1)}% · lock {contest.lock_time}{economics.near_lock ? ` · near-lock overlay $${Number(economics.current_overlay ?? 0).toFixed(2)}` : ""}</p>
                  <details><summary>Contest payout ladder</summary><ul>{(contest.payout_ladder as any[]).map((tier, index) => <li key={index}>{tier.from}–{tier.to}: ${tier.cash}</li>)}</ul></details>
                  <p>This five-lineup strategy does not compare entry counts or estimate contest-specific payout probability.</p>
                </div>;
              })()}
              {Array.isArray(optimizerStatus.results) && (() => {
                const report = (optimizerStatus.results[0] as any[])?.find((row: any) => row.small_max_report || row.three_max_report)?.small_max_report ?? (optimizerStatus.results[0] as any[])?.find((row: any) => row.three_max_report)?.three_max_report;
                if (!report) return null;
                if (report.contest_mode === "generic") {
                  const configured = report.selection_mode === "configured";
                  return <div className="status-card nested-card">
                    <h4>Generic small-max lineup selection: {report.selected_count} {report.selected_count === 1 ? "entry" : "entries"}</h4>
                    <p>{report.note} Entry limit: {report.maximum_entries}. {configured ? `Requested entries: ${report.configured_entry_count}.` : "Auto selected one lineup; entry-count economics require a contest."} Enforce single TE: {report.enforce_single_te ? "True" : "False"}.</p>
                    <p>Evaluated {report.searched_candidate_count} searched candidates from {report.qualifying_candidate_count} qualified and {report.candidate_count} unique lineups.</p>
                    <div className="table-wrap"><table><thead><tr><th>Entries</th><th>Candidate ranks</th><th>Quality score</th><th>Diversity credit</th><th>Avg / min mean</th><th>Avg / min P90</th><th>Captains</th><th>Scripts</th></tr></thead><tbody>{report.count_comparisons.map((row: any, index: number) => <tr key={index}><td>{index + 1}</td>{row ? <><td>{row.candidate_ranks.join(" / ")}</td><td>{row.lineup_quality_contribution.toFixed(4)}</td><td>{row.diversification_contribution.toFixed(4)}</td><td>{row.average_mean.toFixed(1)} / {row.minimum_mean.toFixed(1)}</td><td>{row.average_p90.toFixed(1)} / {row.minimum_p90.toFixed(1)}</td><td>{row.captains.join(" / ")}</td><td>{row.scripts.join(" / ")}</td></> : <td colSpan={7}>No qualifying portfolio under the quality and exposure rules</td>}</tr>)}</tbody></table></div>
                    {report.selected && <><p>Selected ranks {report.selected.candidate_ranks.join(" / ")} · {report.selected.unique_captains} unique Captains · {report.selected.script_diversity} scripts.</p>
                      <p>Captain exposure: {Object.entries(report.selected.captain_exposures).map(([name, rate]) => `${name} ${(Number(rate) * 100).toFixed(0)}%`).join(" · ")}</p>
                      <p>Player exposure: {Object.entries(report.selected.player_exposures).map(([name, rate]) => `${name} ${(Number(rate) * 100).toFixed(0)}%`).join(" · ")}</p>
                      <ul>{report.selected.pairwise.map((pair: any) => <li key={pair.candidate_ranks.join("-")}>#{pair.candidate_ranks.join(" / #")}: {pair.shared_players} shared · {pair.overlap_percentage.toFixed(0)}% overlap · {pair.same_captain ? "same" : "different"} Captain · {pair.same_script ? "same" : "different"} script</li>)}</ul>
                    </>}
                  </div>;
                }
                const autoCount = report.auto_recommended_count ?? report.count_comparisons.reduce((best: number, row: any, index: number) => row && (!best || row.portfolio_objective > report.count_comparisons[best - 1].portfolio_objective) ? index + 1 : best, 0);
                const configured = report.selection_mode === "configured" || (report.entries_to_use != null && report.entries_to_use !== "auto");
                const configuredCount = Number(report.configured_entry_count ?? report.entries_to_use ?? report.selected_count);
                return <div className="status-card nested-card">
                  <h4>{configured ? configuredCount === report.selected_count ? `Configured portfolio: ${configuredCount} entries` : `Configured target: ${configuredCount} entries; feasible portfolio: ${report.selected_count} entries` : `Small-max recommendation: ${report.selected_count} ${report.selected_count === 1 ? "entry" : "entries"}`}</h4>
                  <p>Configured entry count: {configured ? configuredCount : "Auto"}. Auto recommendation under current heuristic: {autoCount} {autoCount === 1 ? "entry" : "entries"}.</p>
                  <p>{report.contest.name} · ${report.contest.entry_fee} per entry · maximum {report.contest.maximum_entries} · Enforce single TE: {report.enforce_single_te ? "True" : "False"}</p>
                  <p>Field {report.contest.current_entries}/{report.contest.capacity} · prize pool ${report.contest.prize_pool} · paid {(Number(report.contest.economics.paid_percentage) * 100).toFixed(1)}% · min cash ${report.contest.economics.minimum_cash} · first-place share {(Number(report.contest.economics.first_place_share) * 100).toFixed(1)}% · full-field rake {(Number(report.contest.economics.full_field_rake) * 100).toFixed(1)}% · lock {report.contest.lock_time}{report.contest.economics.near_lock ? ` · near-lock overlay $${Number(report.contest.economics.current_overlay ?? 0).toFixed(2)}` : ""}</p>
                  <p>{report.note} Evaluated {report.searched_candidate_count ?? report.qualifying_candidate_count} searched candidates from {report.qualifying_candidate_count} qualified and {report.candidate_count} unique lineups.</p>
                  <div className="table-wrap"><table><thead><tr><th>Entries</th><th>Candidate ranks</th><th>Cost</th><th>Lineup set score</th><th>Count objective</th><th>Payout proxy</th><th>Lineup quality</th><th>Diversity</th><th>Avg / min mean</th><th>Avg / min P90</th><th>Avg chalk</th><th>Captains</th><th>Scripts</th></tr></thead><tbody>{report.count_comparisons.map((row: any, index: number) => <tr key={index}><td>{index + 1}</td>{row ? <><td>{row.candidate_ranks.join(" / ")}</td><td>${row.total_entry_fees.toFixed(2)}</td><td>{row.lineup_selection_score.toFixed(4)}</td><td>{row.portfolio_objective.toFixed(4)}</td><td>{row.payout_proxy.toFixed(4)}</td><td>{row.lineup_quality_contribution.toFixed(4)}</td><td>{row.diversification_contribution.toFixed(4)}</td><td>{row.average_mean.toFixed(1)} / {row.minimum_mean.toFixed(1)}</td><td>{row.average_p90.toFixed(1)} / {row.minimum_p90.toFixed(1)}</td><td>{row.average_relative_chalk.toFixed(1)}</td><td>{row.captains.join(" / ")}</td><td>{row.scripts.join(" / ")}</td></> : <td colSpan={12}>No qualifying portfolio under the quality and exposure rules</td>}</tr>)}</tbody></table></div>
                  {report.selected && <><p>Selected ranks {report.selected.candidate_ranks.join(" / ")}. {configured ? "The configured count determines this portfolio." : "Its count objective is highest among feasible entry counts."} Unique Captains: {report.selected.unique_captains}; scripts: {report.selected.script_diversity}.</p>
                    <p>Captain exposure: {Object.entries(report.selected.captain_exposures).map(([name, rate]) => `${name} ${(Number(rate) * 100).toFixed(0)}%`).join(" · ")}</p>
                    <p>Player exposure: {Object.entries(report.selected.player_exposures).map(([name, rate]) => `${name} ${(Number(rate) * 100).toFixed(0)}%`).join(" · ")}</p>
                    <ul>{report.selected.pairwise.map((pair: any) => <li key={pair.candidate_ranks.join("-")}>#{pair.candidate_ranks.join(" / #")}: {pair.shared_players} shared · {pair.overlap_percentage.toFixed(0)}% overlap · Jaccard {pair.jaccard_similarity.toFixed(3)} · {pair.same_captain ? "same" : "different"} Captain · {pair.same_script ? "same" : "different"} script · {pair.same_team_emphasis ? "same" : "different"} team emphasis · shared punts {pair.same_value_player_ids.join(", ") || "none"} · chalk difference {pair.relative_chalk_difference.toFixed(1)} · repeated Captain materially different: {pair.repeated_captain_materially_different ? "Yes" : "No"}</li>)}</ul>
                    <h4>Best portfolio count comparisons</h4>
                    <ul>{(report.count_marginals ?? []).map((entry: any) => <li key={entry.entry_count}>Best {entry.entry_count}-entry portfolio vs best {entry.from_count ?? entry.entry_count - 1}-entry portfolio · objective delta {entry.objective_change == null ? "baseline" : entry.objective_change.toFixed(4)} · payout-proxy delta {entry.payout_proxy_change == null ? "baseline" : entry.payout_proxy_change.toFixed(4)} · quality delta {entry.lineup_quality_change == null ? "baseline" : entry.lineup_quality_change.toFixed(4)} · diversity delta {entry.diversification_change == null ? "baseline" : entry.diversification_change.toFixed(4)} · fee delta ${(entry.fee_delta ?? entry.additional_entry_fee).toFixed(2)} · candidates added #{entry.added_candidate_ranks.join(", #") || "none"} · removed #{entry.removed_candidate_ranks.join(", #") || "none"}</li>)}</ul>
                    <h4>Selected portfolio leave-one-out</h4>
                    <ul>{(report.leave_one_out ?? []).map((entry: any) => <li key={entry.candidate_rank}>Remove candidate #{entry.candidate_rank} · {entry.captain} CPT · mean {entry.mean.toFixed(2)} · P90 {entry.p90.toFixed(2)} · chalk {Number(entry.relative_chalk).toFixed(1)} · remaining #{entry.remaining_candidate_ranks.join(", #") || "none"} · objective without {entry.objective_without_lineup.toFixed(4)} · change if removed {entry.objective_change_if_removed.toFixed(4)}</li>)}</ul>
                  </>}
                  {report.count_comparisons[2] && <><h4>Best three-entry version</h4><ul>{report.count_comparisons[2].lineups.map((row: any) => <li key={row.rank}>#{row.rank} · {row.captain} CPT · mean {row.mean.toFixed(1)} · P90 {row.p90.toFixed(1)} · chalk {Number(row.relative_chalk).toFixed(1)} · {row.script} · {row.players.map((player: any) => `${player.slot} ${player.name}`).join(" / ")}</li>)}</ul><p>Captain exposure: {Object.entries(report.count_comparisons[2].captain_exposures).map(([name, rate]) => `${name} ${(Number(rate) * 100).toFixed(0)}%`).join(" · ")}. Player exposure: {Object.entries(report.count_comparisons[2].player_exposures).map(([name, rate]) => `${name} ${(Number(rate) * 100).toFixed(0)}%`).join(" · ")}.</p><ul>{report.count_comparisons[2].pairwise.map((pair: any) => <li key={pair.candidate_ranks.join("-")}>#{pair.candidate_ranks.join(" / #")}: {pair.shared_players} shared · {pair.overlap_percentage.toFixed(0)}% overlap · Jaccard {pair.jaccard_similarity.toFixed(3)} · {pair.same_captain ? "same" : "different"} Captain · {pair.same_script ? "same" : "different"} script · {pair.same_team_emphasis ? "same" : "different"} team emphasis · shared punts {pair.same_value_player_ids.join(", ") || "none"} · chalk difference {pair.relative_chalk_difference.toFixed(1)}</li>)}</ul></>}
                  {report.structure_comparisons && <p>Three-entry Captain structures: {Object.entries(report.structure_comparisons).map(([name, row]) => row ? `${name.replaceAll("_", " ")}: #${(row as any).candidate_ranks.join(" / #")} lineup score ${(row as any).lineup_selection_score.toFixed(4)}, count objective ${(row as any).portfolio_objective.toFixed(4)}` : `${name.replaceAll("_", " ")}: unavailable`).join(" · ")}</p>}
                </div>;
              })()}
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
                    <h4>Available contests</h4>
                    <p>Contest selection: {contestSelection.mode === "auto" ? "Auto" : "Enter all"} · {contestSelection.selected_count} of {contestSelection.available_count} contests · ${Number(contestSelection.total_entry_fees).toFixed(2)} total entry fees. {contestSelection.note}</p>
                    {contestSelection.snapshot_fallbacks?.length > 0 && <p><strong>Saved snapshot fallback:</strong> {contestSelection.snapshot_fallbacks.map((item: any) => `${item.contest_id} observed ${item.observed_at}`).join("; ")}. Refresh DraftKings data before lock to evaluate current entries and overlay.</p>}
                    <p>{contestSelection.selection_reason} Search: {contestSelection.search_method}; {contestSelection.evaluated_subsets} subsets evaluated.</p>
                    <h4>Best subset by contest count</h4>
                    <div className="table-wrap"><table><thead><tr><th>Contests</th><th>Best subset</th><th>Entry fees</th><th>Heuristic value</th><th>Independent ranks</th><th>Shared percentile</th></tr></thead><tbody>{contestSelection.count_comparisons.map((row: any) => <tr key={row.contest_count}><td>{row.contest_count}</td><td>{(row.contest_names ?? row.contest_ids).join(", ")}</td><td>${row.total_entry_fees.toFixed(2)}</td><td>{(row.heuristic_value * 100).toFixed(1)}%</td><td>{(row.independent_rank_proxy * 100).toFixed(1)}%</td><td>{(row.shared_percentile_proxy * 100).toFixed(1)}%</td></tr>)}</tbody></table></div>
                    {contestSelection.sensitivity && <><h4>Correlation sensitivity</h4>
                      <p>Fixed shared-rank weights blend independent-rank and fully shared-percentile payout proxies. The best feasible subset may change at each weight.</p>
                      <div className="table-wrap"><table><thead><tr><th>Shared-rank weight</th>{contestSelection.count_comparisons.map((row: any) => <th key={row.contest_count}>{row.contest_count} contest{row.contest_count === 1 ? "" : "s"}</th>)}<th>Preferred count</th></tr></thead><tbody>{contestSelection.sensitivity.map((row: any) => <tr key={row.shared_rank_weight}><td>{(row.shared_rank_weight * 100).toFixed(0)}%</td>{row.by_count.map((value: any) => <td key={value.contest_count}>{(value.profitability_proxy * 100).toFixed(2)}%</td>)}<td>{row.recommended_count}</td></tr>)}</tbody></table></div>
                      <p>{contestSelection.crossovers?.length ? contestSelection.crossovers.map((item: any) => `Around ${(item.shared_rank_weight_approx * 100).toFixed(1)}% shared rank: ${item.from_count} → ${item.to_count} contests`).join(" · ") : "No count crossover from 0% to 100% shared rank."}</p>
                      <h4>Recommended count: {contestSelection.selected_count} · {contestSelection.recommendation_status}</h4>
                      <p>{contestSelection.recommendation_status_reason} This is a heuristic stability label, not statistical confidence.</p>
                      {contestSelection.overlay_changed_recommendation && <p>Near-lock overlay changed the recommended count versus the full-field reference ({contestSelection.full_field_reference_count}).</p>}
                    </>}
                    <div className="table-wrap"><table><thead><tr><th>Selected</th><th>Contest</th><th>Single-contest proxy</th><th>Entry</th><th>Field</th><th>Paid</th><th>Min cash</th><th>Top 1%</th><th>5%</th><th>10%</th><th>20%</th><th>Median paid</th><th>1st share</th><th>Top 10 share</th><th>Flatness</th><th>Full rake</th><th>Near-lock effective rake / overlay</th></tr></thead><tbody>{contestSelection.ranked_contests.map((contest: any) => <tr key={contest.contest_id}>
                      <td>{contestSelection.selected_contest_ids.includes(contest.contest_id) ? "Yes" : "No"}</td><td>{contest.name}</td><td>{(contest.contest_score * 100).toFixed(1)}%</td><td>${contest.entry_fee}</td><td>{contest.capacity}</td><td>{(contest.economics.paid_percentage * 100).toFixed(1)}%</td><td>${contest.economics.minimum_cash} ({contest.economics.minimum_cash_multiple.toFixed(2)}×)</td><td>${contest.economics.payout_at_field_percentiles["1"]}</td><td>${contest.economics.payout_at_field_percentiles["5"]}</td><td>${contest.economics.payout_at_field_percentiles["10"]}</td><td>${contest.economics.payout_at_field_percentiles["20"]}</td><td>${contest.economics.median_paid_payout}</td><td>{(contest.economics.first_place_share * 100).toFixed(1)}%</td><td>{(contest.economics.top_10_share * 100).toFixed(1)}%</td><td>{contest.economics.payout_flatness.toFixed(3)}</td><td>{(contest.economics.full_field_rake * 100).toFixed(1)}%</td><td>{contest.source === "saved_snapshot" ? "Snapshot; not applied" : contest.economics.current_effective_rake == null ? "Too early" : `${(contest.economics.current_effective_rake * 100).toFixed(1)}% / $${contest.economics.current_overlay.toFixed(2)}`}</td>
                    </tr>)}</tbody></table></div>
                  </div>}
                  <p>Weights: mean {report.objective_weights.mean}, P90 {report.objective_weights.p90}, solver {report.objective_weights.solver}, correlation {report.objective_weights.correlation}, context {report.objective_weights.context}, chalk penalty {report.objective_weights.chalk_penalty}.</p>
                  <p>Enforce single TE: {optimizerStatus.enforce_single_te === true ? "True" : optimizerStatus.enforce_single_te === false ? "False" : "Configuration error: saved request value unavailable"}</p>
                  {report.assignments.length > 1 ? <p>{report.unique_lineups} unique lineups · {report.unique_captains} unique Captains · overlap: {report.pairwise_player_overlap.join(", ")} players</p> : <p>One contest selected; lineup A is the highest-ranked single-entry construction.</p>}
                  {report.assignment_comparisons?.length > 0 && <><h4>Lineup assignment and adaptive payout proxy</h4>
                    <p>{report.lineup_correlation_formula}</p>
                    <div className="table-wrap"><table><thead><tr><th>Structure / ranks</th><th>Mean / P90 / chalk by entry</th><th>Cost</th><th>Shared players / overlap / Jaccard</th><th>Captain / script / team</th><th>Quality loss / diversity</th><th>Correlation proxy / adaptive weight</th><th>Independent / shared / adaptive payout proxy</th><th>Joint delta vs all A</th></tr></thead><tbody>{[report.assignment_comparison_aa, report.assignment_comparison_ab, ...report.assignment_comparisons].filter((row: any, index: number, all: any[]) => row && all.findIndex((item: any) => item?.candidate_ranks?.join(",") === row.candidate_ranks.join(",")) === index).slice(0, 12).map((row: any) => <tr key={row.candidate_ranks.join("-")}><td>{row.structure} (#{row.candidate_ranks.join(" / #")})</td><td>{row.mean_by_entry.map((mean: number, index: number) => `${mean.toFixed(1)} / ${row.p90_by_entry[index].toFixed(1)} / ${row.relative_chalk_by_entry[index]?.toFixed(1) ?? "n/a"}`).join("; ")}</td><td>${row.total_entry_fees.toFixed(2)}</td><td>{row.pair_diagnostics.map((pair: any) => `${pair.shared_players}/6 · ${pair.overlap_percentage.toFixed(1)}% · ${pair.jaccard_similarity.toFixed(3)}`).join("; ")}</td><td>{row.pair_diagnostics.map((pair: any) => `${pair.same_captain ? "same" : "different"} / ${pair.same_script ? "same" : "different"} / ${pair.same_team_emphasis ? "same" : "different"}`).join("; ")}</td><td>{row.quality_loss_total.toFixed(3)} / {row.diversification_credit_total.toFixed(3)}</td><td>{row.lineup_correlation_proxy.toFixed(3)} / {(row.adaptive_shared_rank_weight * 100).toFixed(1)}%</td><td>{(row.independent_rank_proxy * 100).toFixed(2)}% / {(row.shared_percentile_proxy * 100).toFixed(2)}% / {(row.adaptive_profitability_proxy * 100).toFixed(2)}%</td><td>{formatDelta(row.joint_heuristic_delta_vs_repeat_a)}</td></tr>)}</tbody></table></div>
                    <p>Selected {selectedComparison?.structure}: highest joint heuristic delta after lineup quality, diversification, and adaptive payout-proxy change. Contest placement below uses field size × top-10 prize share as a restrained tie-break.</p>
                    <h4>Recommended lineup assignment</h4>
                  </>}
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
                      ["Different lineup structure", report.top_alternates.different_game_script],
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
                  {comparisonRows.length > 1 && <p>Candidate #2 versus #1: mean {(comparisonRows[1].mean - comparisonRows[0].mean).toFixed(4)}, summed P90 {(comparisonRows[1].p90 - comparisonRows[0].p90).toFixed(4)}, relative chalk {(comparisonRows[1].relative_chalk - comparisonRows[0].relative_chalk).toFixed(4)}. Selector margin for #1: {(comparisonRows[0].single_entry_score - comparisonRows[1].single_entry_score).toFixed(6)}. Weighted terms below explain the ranking.</p>}
                  {comparisonRows.length > 0 && !comparisonRows.every((candidate: any) => candidate.objective_contributions && candidate.solver_objective_components) && <p>Configuration error: this saved run lacks numerical objective lineage. Rerun the optimizer for a complete decomposition.</p>}
                  {comparisonRows.length > 0 && comparisonRows.every((candidate: any) => candidate.objective_contributions && candidate.solver_objective_components) && <details>
                    <summary>Candidate objective decomposition and quality sacrifice</summary>
                    <p>Weighted selector terms sum to the single-entry score. The solver column contains a separate raw objective; its components below are shown for attribution and are not added twice. The quality reference maximizes weighted mean plus summed P90 before chalk.</p>
                    <div className="table-wrap"><table><thead><tr><th>Candidate</th><th>Total</th><th>Mean</th><th>P90</th><th>Solver</th><th>Correlation</th><th>Context</th><th>Chalk</th><th>Duplication</th><th>Script</th><th>Other</th><th>Mean loss</th><th>P90 loss</th><th>Chalk improvement</th><th>Chalk score gain</th><th>Ceiling trade</th></tr></thead><tbody>{comparisonRows.map((candidate: any) => { const terms = candidate.objective_contributions ?? {}; const trade = candidate.quality_sacrifice_for_chalk ?? {}; return <tr key={candidate.rank}><td>#{candidate.rank} {candidate.captain}</td><td>{candidate.single_entry_score.toFixed(4)}</td>{["mean", "p90", "solver", "correlation", "context", "chalk_penalty", "duplication_uniqueness", "script", "other_penalties"].map((key) => <td key={key}>{Number(terms[key] ?? 0).toFixed(4)}</td>)}<td>{Number(trade.mean_loss_vs_best_mean ?? 0).toFixed(2)}</td><td>{Number(trade.p90_loss_vs_best_p90 ?? 0).toFixed(2)}</td><td>{trade.chalk_improvement_vs_best_quality == null ? "—" : Number(trade.chalk_improvement_vs_best_quality).toFixed(1)}</td><td>{Number(trade.chalk_objective_gain_vs_best_quality ?? 0).toFixed(4)}</td><td>{trade.large_ceiling_sacrifice_for_uniqueness ? "Flag" : "—"}</td></tr>; })}</tbody></table></div>
                    <h4>Nested solver objective</h4><div className="table-wrap"><table><thead><tr><th>Candidate</th><th>Solver total</th><th>Summed P90</th><th>Context</th><th>Captain prior</th><th>Slot ownership</th><th>Correlation / format</th><th>Other / residual</th></tr></thead><tbody>{comparisonRows.map((candidate: any) => { const terms = candidate.solver_objective_components ?? {}; return <tr key={candidate.rank}><td>#{candidate.rank} {candidate.captain}</td><td>{candidate.solver_objective.toFixed(3)}</td>{["p90_ceiling", "context", "captain_prior", "ownership_penalty", "correlation_and_format", "other_or_unattributed"].map((key) => <td key={key}>{Number(terms[key] ?? 0).toFixed(3)}</td>)}</tr>; })}</tbody></table></div>
                    <ul>{comparisonRows.filter((candidate: any) => candidate.quality_sacrifice_for_chalk?.large_ceiling_sacrifice_for_uniqueness).map((candidate: any) => { const trade = candidate.quality_sacrifice_for_chalk; return <li key={candidate.rank}>Candidate #{candidate.rank} reduces summed P90 by {trade.p90_loss_vs_best_p90.toFixed(2)} versus candidate #{trade.best_p90_candidate_rank} in exchange for a {trade.chalk_improvement_vs_best_quality.toFixed(1)}-point relative-chalk improvement versus quality reference #{trade.best_quality_candidate_rank}.</li>; })}</ul>
                  </details>}
                </div>;
              })()}
              <RbDstDiagnosticsPanel optimizer={optimizerStatus} />
              <ModelDisagreementPanel projectionRunId={optimizerStatus.projection_run_id} optimizer={optimizerStatus} />
              {optimizerStatus.status === "completed" && <SkillExposureApprovalPanel optimizer={optimizerStatus} onNewRun={async (runId) => {
                const response = await fetchOptimizerResults(runId);
                setOptimizerStatus(response);
                updateActiveRunSelection({ optimizerRunId: runId,
                  projectionRunId: response.projection_run_id ?? activeRunSelection.projectionRunId });
              }} />}
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
                                      player.flex_only ? "Captain excluded · FLEX allowed" : null,
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
              {Array.isArray(optimizerStatus.results) && optimizerStatus.results.length > 0 && Boolean((optimizerStatus.results[0] as any[])?.[0]?.captain_family_coverage_report?.scenario_family_coverage?.length) && (
                <div className="status-card">
                  {(() => {
                    const report = (optimizerStatus.results[0] as any[])?.[0]?.captain_family_coverage_report;
                    const families = report?.scenario_family_coverage as any[] | undefined;
                    if (!families?.length) return null;
                    const definitions = report.scenario_definitions as any[] | undefined;
                    return <><h3>Showdown game-script scenarios</h3><p>{report.scenario_generation_status} · Scenario diversity {report.require_scenario_diversity ? "on" : "off"}</p><div className="scroll-table"><table className="compact-table"><thead><tr><th>Scenario</th><th>Condition</th><th>Candidates</th><th>Best rank</th><th>Best mean</th><th>Best P90</th><th>Best selector</th><th>Captain</th><th>Team split</th><th>Salary</th><th>Selected</th><th>Reason</th></tr></thead><tbody>{["baseline", "team_a_decisive_win", "team_b_decisive_win"].map((id) => { const family = families.find((item: any) => item.scenario_id === id); const definition = definitions?.find((item: any) => item.scenario_id === id); return <tr key={id}><td>{definition?.label ?? id.replaceAll("_", " ").toUpperCase()}</td><td>{definition?.conditioned_winner ? `${definition.conditioned_winner} by ${definition.decisive_margin_threshold}+` : id === "baseline" ? "Market" : "Unavailable"}</td><td>{family?.candidate_count ?? 0}</td><td>{family ? `#${family.best_rank}` : "—"}</td><td>{family ? Number(family.best_mean).toFixed(1) : "—"}</td><td>{family ? Number(family.best_p90).toFixed(1) : "—"}</td><td>{family ? Number(family.best_selector).toFixed(1) : "—"}</td><td>{family?.best_captain ?? "—"}</td><td>{family?.best_team_split ?? "—"}</td><td>{family ? `$${Number(family.best_salary).toLocaleString()}` : "—"}</td><td>{family?.selected ? "Yes" : "No"}</td><td>{family?.reason ?? report.scenario_generation_status}</td></tr>; })}</tbody></table></div></>;
                  })()}
                </div>
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
                          <strong>{lineup[0]?.lineup_variant === "long_shot" ? "Long-shot lineup" : `Lineup ${idx + 1}`}</strong>
                          <span>Salary: {totalSalary.toLocaleString()}</span>
                          <span>Mean: {totalProj.toFixed(2)}</span>
                          <span>{ceilingSummary.label}: {ceilingSummary.value.toFixed(2)}</span>
                          {lineup[0]?.showdown_scenario && <span>Scenario: {lineup[0].showdown_scenario.label} · winner {lineup[0].showdown_scenario.conditioned_winner ?? "market"} · {lineup[0].showdown_scenario.decisive_margin_threshold}+ points · baseline mean {lineup.reduce((sum: number, row: any) => sum + Number(row.baseline_projection ?? row.projection ?? 0), 0).toFixed(2)} → scenario {totalProj.toFixed(2)} · baseline P90 {lineup.reduce((sum: number, row: any) => sum + Number(row.baseline_p90 ?? row.p90 ?? 0), 0).toFixed(2)} → scenario {lineup.reduce((sum: number, row: any) => sum + Number(row.p90 ?? 0), 0).toFixed(2)}</span>}
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
                          {gameScript && <span>Lineup structure: {gameScript}</span>}
                          {lineup[0]?.showdown_selection_diagnostic && <span>Global rank #{lineup[0].showdown_selection_diagnostic.global_candidate_rank} · mean loss {Number(lineup[0].showdown_selection_diagnostic.mean_loss).toFixed(2)} · P90 loss {Number(lineup[0].showdown_selection_diagnostic.p90_loss).toFixed(2)} · selector loss {Number(lineup[0].showdown_selection_diagnostic.selector_loss).toFixed(2)} · scenario diversity changed selection {lineup[0].showdown_selection_diagnostic.scenario_diversity_changed_selection ? "yes" : "no"}</span>}
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
                              {lineup[0]?.showdown_scenario && <><th>Baseline mean / P90</th><th>Scenario reason</th></>}
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
                                  <td>{(Number(player.p90 ?? player.predicted_p90 ?? player.projection) || 0).toFixed(2)}</td>
                                  {lineup[0]?.showdown_scenario && <><td>{Number(player.baseline_projection ?? player.projection ?? 0).toFixed(2)} / {Number(player.baseline_p90 ?? player.p90 ?? 0).toFixed(2)}</td><td>{player.showdown_scenario_adjustment?.reason ?? "market baseline"}</td></>}
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
