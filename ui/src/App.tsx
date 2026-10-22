type ScenarioFirstPreferences = {enabled:boolean; rbMinimum:number; receiverMinimum:number; captureTarget:number; referencePlayers:string[]; referenceCaptain:string};
import { ScenarioFirstLineup } from "./ScenarioFirstLineup";
import {ScenarioControls,PreparedScenarioSummary,SavedScenarioSummary} from "./OptimizerScenarioPanel";
import {scenarioIssue,scenarioParams,type ScenarioMode} from "./scenarioMode";
import { TypedAssignment, TypedResultsLibrary, TypedGroups, typedChoiceReady, type TypedChoice } from "./TypedContestResults";
import { JointOpportunitySummary } from "./JointOpportunitySummary";
import { WeeklyLearningLibrary } from "./WeeklyLearningLibrary";
import { PersonalThoughtSummary, type PersonalContext } from "./PersonalThoughtSummary";
import { AnalystResearchSummary } from "./AnalystResearchSummary";
import { SharedWorldSummary } from "./SharedWorldSummary";
import { SHARED_WORLD_POLICY } from "./sharedWorldPolicy";
import { analystResearchEvidence } from "./analystResearchEvidence";
import { AnalystIntentComparison } from "./AnalystIntentComparison";
import { intentHandoff, intentLabel, type OptimizationIntent } from "./analystIntent";
import { AnalystPreparationSummary } from "./AnalystPreparationSummary";
import { checkedAnalystSelection, analystHandoffIssue, scopedAnalystHandoff, type AnalystHandoffMode } from "./analystPreparation";
import { AnalystFocusSummary } from "./AnalystFocusSummary";
import { TeammateOpportunityReview } from "./TeammateOpportunityReview";
import { cheaperPairChoice, type TeammateChoice, type TeammatePair } from "./teammateOpportunity";
import { fetchAnalystPacket } from "./api";
import { PreliminaryClassicControls } from "./PreliminaryClassicControls";
import { CLASSIC_OBJECTIVE_STORAGE_KEY, classicSelectionParams, savedHighestProjectionReport, type ClassicSelectionObjective } from "./classicSelectionObjective";
import { preliminaryRunParams, preliminaryScopeIssue, analystFocusedRunIssue, type PreliminarySnapshot } from "./preliminaryResearch";
import { runPreliminaryOptimizer, freezePreliminarySnapshot } from "./api";
import { nextPreparationStatus } from "./preparationStatus";
import { startSingleFlightPolling } from "./singleFlightPolling";
import { AnalystReports } from "./AnalystReports";
import { SingleStat } from "./SingleStat";
import { Tiers } from "./Tiers";
import { AnalystPacketControls } from "./AnalystPacketControls";
import { analystOptimizerParams, analystPacketScopeIssue, type AnalystPacketMetadata } from "./analystPacket";
import { ShadowComparisons } from "./ShadowComparisons";
import { EntryHistory } from "./EntryHistory";
import { WeeklyResults } from "./WeeklyResults";
import { ALL_LEARNING_SLATES, LEARNING_CONTEXT_STORAGE_KEY, initialLearningContext, parseLearningContext } from "./learningContext";
import { optimizerHasPreparedInputs, optimizerWaitingStatus } from "./preparedOptimizer";
import { OptimizerLineupControls } from "./OptimizerLineupControls";
import { LINEUP_CONTROLS_STORAGE_KEY, lineupControlParams, restoreLineupControls, serializeLineupControls } from "./lineupControls";
import { useScopedOperationState } from "./useScopedOperationState";
import { LARGE_GPP_CONTROLS_STORAGE_KEY } from "./classicLargeGppControls";
import { defaultTournamentStrategyId, DEFAULT_OPTIMIZER_OBJECTIVE, ACTIVE_OPTIMIZER_STRATEGIES } from "./optimizerStrategy";
import { singleLineupReportHtml } from "./singleLineupReport";
import { GppRecommendation } from "./GppRecommendation";
import { ScenarioPortfolioAccounting } from "./ScenarioPortfolioAccountingReport";
import { lineupConditionedTotal, teamLimitDescription, exposureWarning, qbLineupLimit, qbCaptainDescription, qbCaptainLimitDescription, captainPositionsDescription, showdownPreflightLabel } from "./showdownReporting";
import { SlatePreparation, type PreparationCheckState } from "./SlatePreparation";
import { LearningCandidateDetails } from "./LearningCandidateDetails";
import { LearningEntryEvidence } from "./LearningEntryEvidence";
import { fetchPreparation, type PreparationStatus } from "./api";
import { preparationBuildIssue } from "./showdownPreparation";
import { classicLivePreflightLabel, classicLiveReadinessSummary, classicLiveSourceActions } from "./classicLiveReadiness";
import { ClassicConstructionReport } from "./ClassicConstructionReport";
import { SINGLE_TE_STORAGE_KEY, parseSingleTePreference } from "./classicConstruction";
import { OptimizerControlComparison } from "./OptimizerControlComparison";
import { optimizerAvailabilityOverrides } from "./optimizerProjectionScenario";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { AppShell, type ViewMode } from "./AppShell";
import { DailyNewsBrief } from "./DailyNewsBrief";
import { ContestWorkflow } from "./ContestWorkflow";
import { ContestLibrary } from "./ContestLibrary";
import { canOpenSavedOptimizerReport } from "./optimizerHistory";
import { RecentOptimizerRuns } from "./RecentOptimizerRuns";
import { ClassicGameConcentrationReport } from "./ClassicGameConcentrationReport";
import { ClassicLargeGppReadinessReport } from "./ClassicLargeGppReadinessReport";
import { DesignPreview } from "./DesignPreview";
import { DigitalTwin } from "./DigitalTwin";
import { ModelWorkbench } from "./ModelWorkbench";
import { ResearchWorkspace } from "./ResearchWorkspace";
import { WarRoom } from "./WarRoom";
import {
  ACTIVE_SLATE_CONTEXT_STORAGE_KEY,
  RUN_SELECTIONS_STORAGE_KEY,
  parsePersistedRunSelections,
  DEFAULT_SLATE,
  availableSlateOptions,
  defaultContestFormatForSlate,
  isValidSlateId,
  normalizeSlateId,
  parsePersistedActiveSlateContext,
  serializeActiveSlateContext,
  slateContextKey,
  updateRunSelection,
  type PersistedRunSelection,
  type PersistedRunSelections,
} from "./workspaceContext";
import { CLASSIC_CONTEST_STRATEGIES } from "./optimizerStrategy";
import {
  contextReadinessLabel,
  individualCeilingSummary,
} from "./optimizerPresentation";
import { downloadOptimizerReport } from "./optimizerReport";
import { resolveCsvIngestPath, injurySourceSlate } from "./ingestPath";
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
  OptimizerRunSummary,
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
  fetchOptimizerRuns,
  previewOptimizerContests,
  fetchSlateReadiness,
  fetchSavedContestScopes,
  fetchImportedSlateScopes,
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
  queuePreparation,
  waitForOperationalJobCompletion,
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
  const [discoveredSlateNames, setDiscoveredSlateNames] = useState<string[]>([]);
  const [customSlateName, setCustomSlateName] = useState("");
  const [customSlateNames, setCustomSlateNames] = useState<string[]>([]);
  const customSlateStorageKey = `football-26-custom-slates:${season}:${week}`;
  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(window.localStorage.getItem(customSlateStorageKey) ?? "[]");
      setCustomSlateNames(Array.isArray(saved) ? saved.filter((name): name is string => typeof name === "string" && isValidSlateId(name)) : []);
    } catch { setCustomSlateNames([]); }
    setCustomSlateName("");
  }, [customSlateStorageKey]);
  const slateOptions = useMemo(() => availableSlateOptions(slate, [...discoveredSlateNames, ...customSlateNames]), [slate, discoveredSlateNames, customSlateNames]);
  useEffect(() => {
    let cancelled = false;
    setDiscoveredSlateNames([]);
    Promise.allSettled([fetchSavedContestScopes(), fetchImportedSlateScopes(season, week)]).then(results => {
      const scopes = results.flatMap(result => result.status === "fulfilled" ? result.value.scopes : []);
      if (!cancelled) setDiscoveredSlateNames(scopes.filter(row => row.season === season && row.week === week).map(row => row.slate));
    });
    return () => { cancelled = true; };
  }, [season, week]);
  const [activeContextReady, setActiveContextReady] = useState(Boolean(startupContext));
  const [runSelections, setRunSelections] = useState<PersistedRunSelections>(() => {
    try { return parsePersistedRunSelections(window.localStorage.getItem(RUN_SELECTIONS_STORAGE_KEY)); }
    catch { return {}; }
  });
  const activeContext = useMemo(
    () => ({ season, week, slate: normalizeSlateId(slate) }),
    [season, slate, week],
  );
  const [learningContext, setLearningContext] = useState(() => {
    try { return parseLearningContext(window.localStorage.getItem(LEARNING_CONTEXT_STORAGE_KEY)); }
    catch { return null; }
  });
  const reviewContext = learningContext ?? initialLearningContext(activeContext);
  const { season: learningSeason, week: learningWeek, slate: learningSlate } = reviewContext;
  const updateLearningContext = (patch: Partial<typeof reviewContext>) => {
    setLearningContext(current => ({ ...(current ?? initialLearningContext(activeContext)), ...patch }));
  };
  useEffect(() => {
    if (viewMode === "learning" && activeContextReady && !learningContext) setLearningContext(initialLearningContext(activeContext));
  }, [viewMode, learningContext, activeContext, activeContextReady]);
  useEffect(() => {
    if (!learningContext) return;
    try { window.localStorage.setItem(LEARNING_CONTEXT_STORAGE_KEY, serializeActiveSlateContext(learningContext)); }
    catch { /* Review still works without browser storage. */ }
  }, [learningContext]);
  const [learningDiscoveredSlates, setLearningDiscoveredSlates] = useState<string[]>([]);
  useEffect(() => {
    if (viewMode !== "learning") return;
    let active = true;
    setLearningDiscoveredSlates([]);
    void fetchImportedSlateScopes(learningSeason, learningWeek).then(result => {
      if (active) setLearningDiscoveredSlates(result.scopes
        .filter(row => row.season === learningSeason && row.week === learningWeek).map(row => row.slate));
    }).catch(() => { /* Standard and currently selected slates remain available. */ });
    return () => { active = false; };
  }, [viewMode, learningSeason, learningWeek]);
  const learningSlateOptions = availableSlateOptions(learningSlate, learningDiscoveredSlates)
    .filter(option => option !== ALL_LEARNING_SLATES);
  const activeContextKey = slateContextKey(activeContext);
  const activeRunSelection = runSelections[activeContextKey] ?? {};
  const updateActiveRunSelection = useCallback(
    (patch: Partial<PersistedRunSelection>) => {
      setRunSelections((current) => {
        const next = updateRunSelection(current, activeContext, patch);
        try { window.localStorage.setItem(RUN_SELECTIONS_STORAGE_KEY, JSON.stringify(next)); } catch { /* Session still works without storage. */ }
        return next;
      });
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
  const operationScope = `${season}:${week}:${slate.toUpperCase()}`;
  const [error, setError] = useScopedOperationState<string | null>(operationScope, null);
  const [loadError, setLoadError] = useScopedOperationState<string | null>(operationScope, null);
  const [preparationCheck, setPreparationCheck] = useState<PreparationCheckState | null>(null);
  const [preparationStatus, storePreparationStatus] = useState<PreparationStatus | null>(null);
  const preparationScopeRef = useRef({season, week, slate});
  preparationScopeRef.current = {season, week, slate};
  const setPreparationStatus = useCallback((next: PreparationStatus | null) => {
    storePreparationStatus(current => nextPreparationStatus(current, next, preparationScopeRef.current));
  }, []);
  const [loadSummaries, setLoadSummaries] = useScopedOperationState<LoadSummary[]>(operationScope, []);
  const [lastLoadType, setLastLoadType] = useScopedOperationState<string | null>(operationScope, null);
  const [slateStatus, setSlateStatus] = useScopedOperationState<SlateLoadResponse | null>(operationScope, null);
  const [optimizerStatuses, setOptimizerStatuses] = useState<Record<string, OptimizerResponse>>({});
  const optimizerResultsRef = useRef<HTMLDivElement>(null);
  const [optimizerOpenRequest, setOptimizerOpenRequest] = useState(0);
  useEffect(() => {
    if (optimizerOpenRequest > 0) optimizerResultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [optimizerOpenRequest]);
  const setOptimizerStatus = useCallback((status: OptimizerResponse | null) => {
    setOptimizerStatuses((current) => {
      const key = activeContextKey;
      if (status) return { ...current, [key]: status };
      const next = { ...current };
      delete next[key];
      return next;
    });
  }, [activeContextKey]);
  const [slateReadiness, setSlateReadiness] = useState<SlateReadinessResponse | null>(null);
  useEffect(() => {
    if (viewMode !== "workspace") return;
    let cancelled = false;
    fetchSlateReadiness({ season, week, slate }).then(report => {
      if (!cancelled) setSlateReadiness(report);
    }).catch(() => { if (!cancelled) setSlateReadiness(null); });
    return () => { cancelled = true; };
  }, [viewMode, season, week, slate]);
  const [lineupExportPending, setLineupExportPending] = useState(false);
  const [lineupExportError, setLineupExportError] = useState<string | null>(null);
  const [dataQualityHistory, setDataQualityHistory] = useState<DataQualityHistoryResponse | null>(null);
  const [dataQualityLoading, setDataQualityLoading] = useState(false);
  const [dataQualityError, setDataQualityError] = useState<string | null>(null);
  const [noQbCaptain, setNoQbCaptain] = useState(false);
  const [noTwoQbs, setNoTwoQbs] = useState(false);
  const [noQbs, setNoQbs] = useState(false);
  const [requireTeamLeader, setRequireTeamLeader] = useState(true);
  const [requireHomeTeamLeader, setRequireHomeTeamLeader] = useState(false);
  const [captainPositions, setCaptainPositions] = useState("WR,RB");
  const [namedResearchPreferences, setNamedResearchPreferences] = useState<Record<string, {captain: string[]; questionable: string[]; scenario_first?:ScenarioFirstPreferences}>>(() => {
    try { return JSON.parse(window.localStorage.getItem("dfs-named-research-preferences-v1") ?? "{}"); } catch { return {}; }
  });
  const namedResearch = namedResearchPreferences[activeContextKey] ?? {captain: [], questionable: []};
  useEffect(() => { try { window.localStorage.setItem("dfs-named-research-preferences-v1", JSON.stringify(namedResearchPreferences)); } catch { /* Preserve session preferences. */ } }, [namedResearchPreferences]);
  const [constructionComparison, setConstructionComparison] = useState(false);
  const [contestFormat, setContestFormat] = useState<"classic" | "showdown">(() => defaultContestFormatForSlate(slate));
  const [lineupControlsByFormat, setLineupControlsByFormat] = useState(() => {
    try { return restoreLineupControls(window.localStorage.getItem(LINEUP_CONTROLS_STORAGE_KEY), window.localStorage.getItem(LARGE_GPP_CONTROLS_STORAGE_KEY)); }
    catch { return restoreLineupControls(null, null); }
  });
  const lineupControls = lineupControlsByFormat[contestFormat];
  const showdownMaxPlayersPerTeam = lineupControlsByFormat.showdown.maxPlayersPerTeam;
  const setShowdownMaxPlayersPerTeam = (value: number) => setLineupControlsByFormat(current => ({ ...current, showdown: { ...current.showdown, maxPlayersPerTeam: value } }));
  useEffect(() => {
    try { window.localStorage.setItem(LINEUP_CONTROLS_STORAGE_KEY, serializeLineupControls(lineupControlsByFormat)); } catch { /* Preserve session choices. */ }
  }, [lineupControlsByFormat]);
  const [singleLineupContestUrl, setSingleLineupContestUrl] = useState("");
  const setActiveSlate = useCallback((value: string) => {
    const nextSlate = normalizeSlateId(value);
    if (nextSlate === slate) return;
    setSlate(nextSlate);
    setContestFormat(defaultContestFormatForSlate(nextSlate));
    setSingleLineupContestUrl("");
  }, [slate]);
  const [analystPacketsByContext, setAnalystPacketsByContext] = useState<Record<string, AnalystPacketMetadata | null>>(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("dfs-analyst-packets-v1") ?? "{}");
      return saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
    } catch { return {}; }
  });
  useEffect(() => {
    try { window.localStorage.setItem("dfs-analyst-packets-v1", JSON.stringify(analystPacketsByContext)); } catch { /* Session choices remain available. */ }
  }, [analystPacketsByContext]);
  const [analystModes, setAnalystModes] = useState<Record<string, AnalystHandoffMode>>(() => {
    try { return JSON.parse(window.localStorage.getItem("dfs-analyst-handoff-modes-v1") ?? "{}") || {}; } catch { return {}; }
  });
  useEffect(() => { try { window.localStorage.setItem("dfs-analyst-handoff-modes-v1", JSON.stringify(analystModes)); } catch { /* Keep session preferences. */ } }, [analystModes]);
  const analystHandoffMode = analystModes[activeContextKey] ?? (Object.prototype.hasOwnProperty.call(analystPacketsByContext, activeContextKey) ? analystPacketsByContext[activeContextKey] ? "MANUAL" : "BASELINE" : "AUTO");
  const [preliminaryAnalystInputs, setPreliminaryAnalystInputs] = useState<Record<string, PreliminarySnapshot | null>>({});
  const [optimizationIntents, setOptimizationIntents] = useState<Record<string, OptimizationIntent>>(() => {
    try { return JSON.parse(window.localStorage.getItem("dfs-optimization-intents-v1") ?? "{}") || {}; } catch { return {}; }
  });
  useEffect(() => { try { window.localStorage.setItem("dfs-optimization-intents-v1", JSON.stringify(optimizationIntents)); } catch { /* Keep session selection. */ } }, [optimizationIntents]);
  const [classicSelectionObjectives, setClassicSelectionObjectives] = useState<Record<string, ClassicSelectionObjective>>(() => {
    try { return JSON.parse(window.localStorage.getItem(CLASSIC_OBJECTIVE_STORAGE_KEY) ?? "{}") || {}; } catch { return {}; }
  });
  useEffect(() => { try { window.localStorage.setItem(CLASSIC_OBJECTIVE_STORAGE_KEY, JSON.stringify(classicSelectionObjectives)); } catch { /* Keep session selection. */ } }, [classicSelectionObjectives]);
  const optimizationIntent = optimizationIntents[activeContextKey] ?? (contestFormat === "showdown" ? "EXPECTED_GAME" : "MIXED");
  const [workloadComparisonSelection, setWorkloadComparison] = useState<"standard" | "normalized_counts" | "offensive_mean_control" | "learned_counts" | "learned_yards" | "scenario_first">("standard");
  const workloadComparison = contestFormat === "showdown" ? workloadComparisonSelection : "standard";
  const scenarioFirstPreferences:ScenarioFirstPreferences = namedResearch.scenario_first ?? {enabled:true,rbMinimum:6,receiverMinimum:3,captureTarget:.9,referencePlayers:[],referenceCaptain:""};
  const updateScenarioFirstPreferences = (change:Partial<ScenarioFirstPreferences>) => setNamedResearchPreferences(current => ({...current,[activeContextKey]:{...namedResearch,scenario_first:{...scenarioFirstPreferences,...change}}}));

  const [sharedWorldPolicies,setSharedWorldPolicies] = useState<Record<string,boolean>>(()=>{
    try { return JSON.parse(window.localStorage.getItem("dfs-shared-world-policy-v1")??"{}")||{}; } catch { return {}; }
  });
  useEffect(()=>{try{window.localStorage.setItem("dfs-shared-world-policy-v1",JSON.stringify(sharedWorldPolicies));}catch{/* Session choice remains available. */}},[sharedWorldPolicies]);
  const sharedWorldCoverage = contestFormat === "showdown" && workloadComparison === "standard" && sharedWorldPolicies[activeContextKey] === true;
  const normalHandoff = sharedWorldCoverage ? preparationStatus?.latest_build?.analyst_handoff ?? null : intentHandoff(preparationStatus?.latest_build, optimizationIntent);
  const candidateHandoff = sharedWorldCoverage ? normalHandoff : preparationStatus?.build_current && preparationStatus.latest_build?.data_readiness?.status?.toUpperCase() === "READY" ? normalHandoff : intentHandoff(preliminaryAnalystInputs[activeContextKey], optimizationIntent) ?? normalHandoff;
  const preparedAnalystHandoff = scopedAnalystHandoff(candidateHandoff, {season,week,slate,format:contestFormat});
  const [checkedAnalystPackets, setCheckedAnalystPackets] = useState<Record<string, AnalystPacketMetadata>>({});
  const checkedAnalystHash = preparedAnalystHandoff?.checked_packet_sha256;
  useEffect(() => {
    let active = true;
    if (checkedAnalystHash) void fetchAnalystPacket(checkedAnalystHash).then(packet => { if (active) setCheckedAnalystPackets(current => ({...current,[checkedAnalystHash]:packet})); }).catch(() => { /* Request guard reports unavailable checked metadata. */ });
    return () => { active = false; };
  }, [checkedAnalystHash]);
  const selectedAnalystPacket = checkedAnalystSelection(analystHandoffMode, preparedAnalystHandoff, checkedAnalystHash ? checkedAnalystPackets[checkedAnalystHash] ?? null : null, analystPacketsByContext[activeContextKey] ?? null);
  const selectAnalystOverride = (packet: AnalystPacketMetadata | null) => {
    setAnalystModes(current => ({...current,[activeContextKey]:packet ? "MANUAL" : "BASELINE"}));
    setAnalystPacketsByContext(current => ({...current,[activeContextKey]:packet}));
  };
  const [teammateChoices, setTeammateChoices] = useState<Record<string, {choice:TeammateChoice;packetHash:string;label:string} | null>>({});
  const stagedTeammateChoice = teammateChoices[activeContextKey] ?? null;
  const [optimizerProjectionMessage, setOptimizerProjectionMessage] = useState<string | null>(null);
  const [optimizerProjectionPending, setOptimizerProjectionPending] = useState(false);
  const [optimizerProjectionRunsByContext, setOptimizerProjectionRunsByContext] = useState<Record<string, OptimizerProjectionRun[]>>({});
  const optimizerProjectionRuns = optimizerProjectionRunsByContext[activeContextKey] ?? [];
  const refreshOptimizerProjectionRuns = async () => {
    setOptimizerProjectionPending(true);
    setOptimizerProjectionMessage(null);
    try {
      const response = await fetchOptimizerProjectionRuns({ season, week, slate });
      setOptimizerProjectionRunsByContext((current) => ({ ...current, [activeContextKey]: response.runs }));
      setOptimizerProjectionMessage(response.runs.length ? "Reloaded projection list; no source fetch or rebuild occurred." : "Reloaded projection list; no completed projection is available for this slate.");
      return response.runs;
    } catch (err) {
      setOptimizerProjectionMessage(err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      setOptimizerProjectionPending(false);
    }
  };
  const [enforceSingleTE, setEnforceSingleTE] = useState(() => {
    try { return parseSingleTePreference(window.localStorage.getItem(SINGLE_TE_STORAGE_KEY)); }
    catch { return true; }
  });
  useEffect(() => {
    try { window.localStorage.setItem(SINGLE_TE_STORAGE_KEY, String(enforceSingleTE)); } catch { /* Keep session preference. */ }
  }, [enforceSingleTE]);
  const [avoidDstOpponents, setAvoidDstOpponents] = useState(true);
  const effectiveOptimizerObjective = DEFAULT_OPTIMIZER_OBJECTIVE;
  const storedOptimizerStatus = optimizerStatuses[activeContextKey] ?? null;
  const optimizerStatus = storedOptimizerStatus?.contest_format === contestFormat ? storedOptimizerStatus : null;
  const highestProjectionReport = savedHighestProjectionReport(optimizerStatus);
  const selectedOptimizerStrategy = defaultTournamentStrategyId(contestFormat);
  const highestProjection = contestFormat === "classic" && classicSelectionObjectives[activeContextKey] === "baseline_mean";
  const [scenarioModes,setScenarioModes]=useState<Record<string,ScenarioMode|undefined>>({});
  const scenarioMode=scenarioModes[`${activeContextKey}:${contestFormat}`];
  const [predictionStatuses, setPredictionStatuses] = useState<Record<string, PredictionOperationStatus>>({});
  const predictionStatus = predictionStatuses[activeContextKey] ?? null;
  const setPredictionStatus = useCallback((status: PredictionOperationStatus | null) => {
    setPredictionStatuses((current) => {
      const key = activeContextKey;
      if (status) return { ...current, [key]: status };
      const next = { ...current };
      delete next[key];
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
  const simulationStatus = simulationStatuses[`${activeContextKey}:${contestFormat}`] ?? null;
  const setSimulationStatus = useCallback((status: SimulationResponse | null) => {
    setSimulationStatuses((current) => {
      const key = `${activeContextKey}:${contestFormat}`;
      if (status) return { ...current, [key]: status };
      const next = { ...current };
      delete next[key];
      return next;
    });
  }, [activeContextKey, contestFormat]);
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
  const injuryFileToLoad = resolveCsvIngestPath(injuryPath, `FanDuel_injuries_${season}_${week}_${injurySourceSlate(activeContext.slate)}.csv`);
  const [weeklyContestDirectory, setWeeklyContestDirectory] = useState("~/NFL");
  const [weeklyContestImport, setWeeklyContestImport] = useState<{
    batch_id?: string;
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
  } & TypedChoice>>({});
  const selectedWeeklyContestFiles = weeklyContestFiles.filter((file) => weeklyContestSelections[file.path]?.selected);
  const selectedWeeklyContestReady = selectedWeeklyContestFiles.length > 0 && selectedWeeklyContestFiles.every((file) => {
    const choice = weeklyContestSelections[file.path];
    return Boolean(file.source_file_id && choice && Number.isInteger(choice.season)
      && choice.season >= 2000 && Number.isInteger(choice.week)
      && choice.week >= 1 && choice.week <= 25 && isValidSlateId(choice.slate) && !["UNRESOLVED","UNKNOWN","DEFAULT"].includes(choice.slate) && typedChoiceReady(choice));
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
  const [learningTab, setLearningTab] = useState<"review" | "results">("review");
  const [learningError, setLearningError] = useState<string | null>(null);
  const learningScopeRef = useRef(`${learningSeason}:${learningWeek}`);
  learningScopeRef.current = `${learningSeason}:${learningWeek}`;
  useEffect(() => {
    setWeeklyContestImport(null);
    setWeeklyContestSelections({});
    setLearningReport(current => current?.season === learningSeason && current.week === learningWeek ? current : null);
    setLearningError(null);
  }, [learningSeason, learningWeek]);
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
  const [questionableExclusionByFormat, setQuestionableExclusionByFormat] = useState({
    classic: true, showdown: true,
  });
  const excludeQuestionable = questionableExclusionByFormat[contestFormat];
  const setExcludeQuestionable = (enabled: boolean) => setQuestionableExclusionByFormat(
    (current) => ({ ...current, [contestFormat]: enabled }),
  );
  const [opponentExclusionsByContext, setOpponentExclusionsByContext] = useState<Record<string, string>>(() => {
    try { return JSON.parse(window.localStorage.getItem("dfs-opponent-exclusions-by-context-v1") ?? "{}") || {}; } catch { return {}; }
  });
  const excludeOpponentTeams = opponentExclusionsByContext[activeContextKey] ?? "DEN";
  const setExcludeOpponentTeams = (value: string) => setOpponentExclusionsByContext(current => ({...current, [activeContextKey]: value}));
  useEffect(() => { try { window.localStorage.setItem("dfs-opponent-exclusions-by-context-v1", JSON.stringify(opponentExclusionsByContext)); } catch { /* Preserve current choices. */ } }, [opponentExclusionsByContext]);
  const [excludePlayerIds, setExcludePlayerIds] = useState<string>("");
  const [lockedPlayers, setLockedPlayers] = useState<string>("");
  const [lockedPlayerIds, setLockedPlayerIds] = useState<string>("");
  const [flexOnlyPlayers, setFlexOnlyPlayers] = useState<string>("");
  const [playerDecisionControls, setPlayerDecisionControls] = useState<PlayerDecisionControl[]>([
    { playerName: "", availability: "default", excludeFromLineups: false },
  ]);
  const configuredAvailabilityOverrides = () => optimizerAvailabilityOverrides(
    playerDecisionControls, "", "", "showdown",
  );
  const preferenceExcludedPlayers = playerDecisionControls
    .filter((row) => row.playerName.trim() && row.excludeFromLineups)
    .map((row) => row.playerName.trim());
  const availabilityPreview = (() => {
    try { return { overrides: configuredAvailabilityOverrides(), error: null }; }
    catch (failure) { return { overrides: null, error: failure instanceof Error ? failure.message : String(failure) }; }
  })();
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
    setPendingAction("Loading salary CSV...");
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
      try { setPreparationStatus(await fetchPreparation({ season, week, slate })); } catch { setPreparationStatus(null); }
      setPendingAction(null);
    }
  };

  const runLoadRawInjuries = async () => {
    if (!injuryFileToLoad) return;
    setError(null);
    setPendingAction("Loading injury CSV...");
    try {
      const resp = await loadRawInjuries({ season, week, slate: injurySourceSlate(slate), path: injuryFileToLoad });
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
      try { setPreparationStatus(await fetchPreparation({ season, week, slate })); } catch { setPreparationStatus(null); }
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
  const [pendingAction, setPendingAction] = useScopedOperationState<string | null>(operationScope, null);
  const [postgresStatus, setPostgresStatus] = useState<StartPostgresResponse | null>(null);
  const [postgresError, setPostgresError] = useState<string | null>(null);
  const [postgresLoading, setPostgresLoading] = useState(false);
  const [postgresDetails, setPostgresDetails] = useState<string | null>(null);
  const [futureWeek, setFutureWeek] = useState<number | "">("");
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentRunResponse>>({});
  const agentStatus = agentStatuses[activeContextKey] ?? null;
  const setAgentStatus = useCallback((status: AgentRunResponse | null) => {
    setAgentStatuses((current) => {
      const key = activeContextKey;
      if (status) return { ...current, [key]: status };
      const next = { ...current };
      delete next[key];
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
    if (!selectedOptimizerRunId || optimizerStatus?.job_id === selectedOptimizerRunId || pendingAction) return;
    let cancelled = false;
    fetchOptimizerRuns({ season, week, slate, contest_format: contestFormat })
      .then((history) => {
        const selected = history.runs.find((run) => run.optimizer_run_id === selectedOptimizerRunId);
        return selected && !canOpenSavedOptimizerReport(selected) ? null : fetchOptimizerResults(selectedOptimizerRunId);
      })
      .then((response) => {
        if (response && !cancelled && response.contest_format === contestFormat) setOptimizerStatus(response);
      })
      .catch(() => {
        // Delivery performs the authoritative compatibility check when creating a portfolio.
      });
    return () => {
      cancelled = true;
    };
  }, [activeRunSelection.optimizerRunId, optimizerStatus?.job_id, setOptimizerStatus, contestFormat, effectiveOptimizerObjective, pendingAction, season, week, slate]);

  const openRecentOptimizer = useCallback(async (run: OptimizerRunSummary, scrollToResults = true) => {
    updateActiveRunSelection({ optimizerRunId: run.optimizer_run_id,
      ...(run.projection_run_id ? { projectionRunId: run.projection_run_id } : {}) });
    setContestFormat(run.contest_format as "classic" | "showdown");
    if (canOpenSavedOptimizerReport(run)) {
      const response = await fetchOptimizerResults(run.optimizer_run_id);
      setOptimizerStatus(response);
      if (scrollToResults) setOptimizerOpenRequest((current) => current + 1);
    } else {
      setOptimizerStatus(null);
    }
  }, [updateActiveRunSelection, setOptimizerStatus]);

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
    const controller = startSingleFlightPolling({
      fetch: () => Promise.all([
          fetchOperationalJobs(12),
          fetchWeeklyRuns({ season, week, slate, limit: 5 }),
        ]),
      onValue: ([jobs, workflows]) => {
          setOperationalJobs(jobs.rows);
          setWeeklyRuns(workflows.rows);
      },
      intervalMs: value => value?.some(result => result.rows.some(row => row.status === "queued" || row.status === "running")) ? 3000 : 30_000,
      onError: () => {
        // The worker/API may be intentionally offline during local UI-only work.
      },
    });
    return () => controller.stop();
  }, [viewMode, season, week, slate]);

  const optimizerParams = () => ({
    ...lineupControlParams(lineupControls, contestFormat), refresh_ownership: false,
    ...(singleLineupContestUrl.trim() ? { contest_urls: [singleLineupContestUrl.trim()] } : {}),
    enforce_single_te: contestFormat === "classic" && enforceSingleTE,
    avoid_dst_opponents: avoidDstOpponents,
    availability_overrides: configuredAvailabilityOverrides(), exclusions_assumed_out: false,
    exclude_players: Array.from(new Set([...excludePlayers.split(",").map(v => v.trim()).filter(Boolean), ...preferenceExcludedPlayers])),
    exclude_opponent_teams: excludeOpponentTeams.split(",").map(v => v.trim().toUpperCase()).filter(Boolean),
    exclude_questionable: excludeQuestionable,
    exclude_player_ids: excludePlayerIds.split(",").map(v => v.trim()).filter(Boolean),
    locked_player_ids: lockedPlayerIds.split(",").map(v => v.trim()).filter(Boolean),
    locked_players: lockedPlayers.split(",").map(v => v.trim()).filter(Boolean),
    ...(contestFormat === "showdown" ? {
      no_qb_captain: noQbCaptain, no_two_qbs: noTwoQbs, no_qbs: noQbs,
      require_team_leader: requireTeamLeader, require_home_team_leader: requireTeamLeader && requireHomeTeamLeader,
      captain_positions: captainPositions ? captainPositions.split(",") : [],
      captain_position_exception_ids: namedResearch.captain,
      questionable_eligible_player_ids: namedResearch.questionable,
      max_players_per_team: showdownMaxPlayersPerTeam,
      flex_only_players: flexOnlyPlayers.split(",").map(v => v.trim()).filter(Boolean),
    } : {}),
  });

  const launchWeeklyRun = async () => {
    setPendingAction("Queueing weekly run...");
    setWeeklyRunError(null);
    try {
      const availabilityOverrides = configuredAvailabilityOverrides();
      const response = await createWeeklyRun({
        season,
        week,
        slate,
        draftkings_directory: weeklyDirectory.trim() || undefined,
        availability_overrides: availabilityOverrides,
        assume_questionable_out: false,
        refresh_projections: true,
        contest_format: contestFormat,
        objective: effectiveOptimizerObjective,
        strategy: selectedOptimizerStrategy,
        num_simulations: 1000,
        optimizer_params: optimizerParams(),
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

  const preparedBuild = preparationStatus?.latest_build;
  const preparationRunning = Boolean(preparationStatus?.scope.season === season && preparationStatus.scope.week === week && preparationStatus.scope.slate.toUpperCase() === slate.toUpperCase() && preparationStatus.jobs.some(j => j.status === "queued" || j.status === "running"));
  const optimizerPrepared = optimizerHasPreparedInputs(preparationStatus, { season, week, slate },
    contestFormat, availabilityPreview.overrides, lineupControls.minimumPlayerSalary,scenarioMode)
    && (workloadComparison === 'standard' || Boolean(preparedBuild?.workload_forecast?.yardage_model) === (['learned_yards','scenario_first'].includes(workloadComparison)))
    && (workloadComparison === 'standard' || Boolean(preparedBuild?.workload_forecast?.scenario_first) === (workloadComparison === 'scenario_first'))
    && (workloadComparison !== 'scenario_first' || preparedBuild?.workload_forecast?.scenario_first?.version === 'captain_shared_scoring_cases_v6')
    && (!['learned_counts','learned_yards','scenario_first'].includes(workloadComparison) || (preparedBuild?.workload_forecast?.learned_opportunities === true && Boolean(preparedBuild.workload_forecast.yardage_model) === (['learned_yards','scenario_first'].includes(workloadComparison))));
  const currentCheckError = preparationCheck?.scope.season === season && preparationCheck.scope.week === week
    && preparationCheck.scope.slate.toUpperCase() === slate.toUpperCase() ? preparationCheck.error : null;
  const optimizerWait = optimizerWaitingStatus(preparationStatus, { season, week, slate },
    optimizerPrepared, pendingAction, currentCheckError, availabilityPreview.error??scenarioIssue(scenarioMode));


  const prepareOptimizerSlate = async (preliminary = false): Promise<PreliminarySnapshot | undefined> => {
    setError(null);
    setPendingAction("Preparing slate sources, projections and ownership...");
    try {
      if (preliminary) preliminaryRunParams({exclude_questionable: true, availability_overrides: configuredAvailabilityOverrides()}, false);
      const response = await queuePreparation({ season, week, slate, action: "prepare", contest_format: contestFormat, ownership_required: true, preliminary_research: preliminary,
        ...(contestFormat === "showdown" ? { minimum_player_salary: lineupControls.minimumPlayerSalary } : {}),
        availability_overrides: preliminary ? [] : configuredAvailabilityOverrides(), assume_questionable_out: false,
        include_workload_forecast: workloadComparison !== "standard" || sharedWorldCoverage || Boolean(!preliminary&&scenarioMode),
        learned_opportunities: !preliminary && ["learned_counts","learned_yards","scenario_first"].includes(workloadComparison),
        opportunity_yards: !preliminary && ["learned_yards","scenario_first"].includes(workloadComparison),
        scenario_first_captain: !preliminary && workloadComparison === "scenario_first",
        ...(!preliminary&&scenarioMode?{scenario_mode:scenarioMode}:{}),
        analyst_mode: !preliminary&&scenarioMode ? "BASELINE" : analystHandoffMode, ...((preliminary||!scenarioMode) && analystHandoffMode === "MANUAL" && selectedAnalystPacket ? { analyst_packet_sha256:selectedAnalystPacket.analyst_packet_sha256, analyst_strategy:selectedAnalystPacket.selected_strategy ?? "MERGED_SCENARIOS" } : {}) });
      setPreparationStatus(await fetchPreparation({ season, week, slate }));
      setPendingAction(`Preparing slate on the durable worker (${response.job.job_id}). Source checks appear in Preparation and data tools.`);
      await waitForOperationalJobCompletion(response.job.job_id);
      if (preliminary) return await freezePreliminarySnapshot(response.job.job_id, {analyst_mode: analystHandoffMode, ...(analystHandoffMode === "MANUAL" && selectedAnalystPacket ? {analyst_packet_sha256: selectedAnalystPacket.analyst_packet_sha256, analyst_strategy: selectedAnalystPacket.selected_strategy} : {})});
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      if (preliminary) throw err;
    } finally {
      try { setPreparationStatus(await fetchPreparation({ season, week, slate })); } catch { setPreparationStatus(null); }
      if (!preliminary) try { setSlateReadiness(await fetchSlateReadiness({ season, week, slate })); } catch { setSlateReadiness(null); }
      await refreshOptimizerProjectionRuns().catch(() => undefined);
      setPendingAction(null);
    }
  };

  const runOptimizerJob = async () => {
    let submittedRunId: string | undefined;
    setError(null);
    setPendingAction("Checking optimizer request...");
    try {
      const noAnalystObjective = highestProjection || Boolean(scenarioMode) || workloadComparison !== "standard";
      const normalCheckedHandoff = noAnalystObjective ? null : scopedAnalystHandoff(normalHandoff, {season,week,slate,format:contestFormat});
      const normalCheckedMetadata = normalCheckedHandoff?.checked_packet_sha256 ? await fetchAnalystPacket(normalCheckedHandoff.checked_packet_sha256) : null;
      const normalPacket = noAnalystObjective ? null : checkedAnalystSelection(analystHandoffMode,normalCheckedHandoff,normalCheckedMetadata,analystPacketsByContext[activeContextKey] ?? selectedAnalystPacket);
      const handoffIssue = noAnalystObjective ? null : analystHandoffIssue(analystHandoffMode, normalCheckedHandoff, normalPacket); if (handoffIssue) throw new Error(handoffIssue);
      if (normalPacket) {
        const issue = analystPacketScopeIssue(normalPacket, season, week, contestFormat);
        if (issue) throw new Error(issue);
      }
      const focusIssue = analystFocusedRunIssue(normalPacket); if (focusIssue) throw new Error(focusIssue);
      const params = scenarioParams(classicSelectionParams({ ...optimizerParams(), ...analystOptimizerParams(normalPacket, contestFormat), analyst_optimization_intent: optimizationIntent,
        ...(sharedWorldCoverage ? {analyst_selection_policy:SHARED_WORLD_POLICY,analyst_strategy:"MERGED_SCENARIOS"} : {}),
        ...(contestFormat === "showdown" && optimizationIntent === "EXPECTED_GAME" && constructionComparison && !sharedWorldCoverage ? {analyst_strategy: "CONSTRUCTION"} : {}) }, highestProjection&&!scenarioMode),scenarioMode,contestFormat);
      if (!optimizerPrepared || !preparedBuild) throw new Error("Prepare slate for optimization first.");
      if (!scenarioMode && workloadComparison !== "standard" && !preparedBuild.workload_forecast) throw new Error("Select the workload mode, then Prepare to create explicit count forecasts first.");
      if (workloadComparison === "scenario_first" && scenarioFirstPreferences.referencePlayers.length && (scenarioFirstPreferences.referencePlayers.length!==6 || !scenarioFirstPreferences.referencePlayers.includes(scenarioFirstPreferences.referenceCaptain))) throw new Error("Choose six reference players and one Captain among them, or clear the reference.");
      submittedRunId = globalThis.crypto.randomUUID();
      updateActiveRunSelection({ optimizerRunId: submittedRunId });
      setPendingAction("Submitting optimizer request...");
      const response = await runOptimizer({ season, week, slate, strategy: selectedOptimizerStrategy,
        optimizer_run_id: submittedRunId, contest_format: contestFormat,
        objective: effectiveOptimizerObjective, projection_run_id: preparedBuild.projection_run_id,
        params: { ...params, ...(workloadComparison === "scenario_first" ? {scenario_capture_target:scenarioFirstPreferences.captureTarget,scenario_role_preference:{enabled:scenarioFirstPreferences.enabled,rb_min_opportunities:scenarioFirstPreferences.rbMinimum,receiver_min_targets:scenarioFirstPreferences.receiverMinimum},...(scenarioFirstPreferences.referencePlayers.length ? {scenario_reference_roster:{player_ids:scenarioFirstPreferences.referencePlayers,captain_player_id:scenarioFirstPreferences.referenceCaptain}} : {})} : {}), ...(!scenarioMode && workloadComparison !== "standard" ? {workload_comparison: workloadComparison} : {}), ...(["learned_counts","learned_yards","scenario_first"].includes(workloadComparison) ? {require_team_leader:false, require_home_team_leader:false, inactive_point_preferences:{require_team_leader:requireTeamLeader, require_home_team_leader:requireHomeTeamLeader, reason:"explicit learned-opportunity comparison has no points-based gates"}} : {}), prepared_input_job_id: preparedBuild.prepared_input_job_id, analyst_handoff_mode:highestProjection||scenarioMode ? "BASELINE" : analystHandoffMode, ...(normalCheckedHandoff ? {analyst_handoff_compatibility_sha256:normalCheckedHandoff.compatibility_sha256} : {}) } },
        () => setPendingAction("Optimizer queued on the durable worker. Reopen it in Recent optimizer runs."));
      setOptimizerStatus(response);
      updateActiveRunSelection({ optimizerRunId: response.job_id,
        projectionRunId: response.projection_run_id ?? activeRunSelection.projectionRunId });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      if (submittedRunId) {
        setPendingAction("Checking for saved optimizer results after the request error...");
        try { setOptimizerStatus(await fetchOptimizerResults(submittedRunId)); } catch { /* Keep original failure. */ }
      }
    } finally {
      setPendingAction(null);
      try { setSlateReadiness(await fetchSlateReadiness({ season, week, slate })); } catch { setSlateReadiness(null); }
      try { setPreparationStatus(await fetchPreparation({ season, week, slate })); } catch { /* Keep last preparation audit. */ }
      await refreshOptimizerProjectionRuns().catch(() => undefined);
    }
  };

  const stageTeammateAlternative = async (pair: TeammatePair) => {
    if (selectedAnalystPacket?.selected_strategy === "MERGED_SCENARIOS" && selectedAnalystPacket.focus_mode === "SELECTED_ONLY") { setError("Selected-only scenario focus excludes cheaper-teammate application. Choose Mixed scenarios explicitly before staging this branch."); return; }
    if (!optimizerStatus?.football_analyst?.packet_sha256) { setError("The saved pair is missing its original Analyst packet."); return; }
    setPendingAction("Selecting the original Analyst inputs for this cheaper branch..."); setError(null);
    try {
      const packet = await fetchAnalystPacket(optimizerStatus.football_analyst.packet_sha256);
      const issue = analystPacketScopeIssue(packet, season, week, "classic"); if (issue) throw new Error(issue);
      const choice = cheaperPairChoice(optimizerStatus.job_id, pair);
      selectAnalystOverride({...packet,selected_strategy:"MERGED_SCENARIOS",teammate_enabled:true,challenger_enabled:selectedAnalystPacket?.challenger_enabled ?? Boolean(optimizerStatus?.football_analyst?.challenger)});
      setTeammateChoices(current => ({...current,[activeContextKey]:{choice,packetHash:packet.analyst_packet_sha256,label:`${pair.primary_name} → ${pair.backup_name}`}}));
      document.getElementById("preliminary-generation-controls")?.scrollIntoView({behavior:"smooth",block:"start"});
    } catch(err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setPendingAction(null); }
  };

  const generatePreliminaryResearch = async (snapshot: PreliminarySnapshot, noSeasonRankRestriction: boolean) => {
    let submittedRunId: string | undefined;
    setError(null);
    setPendingAction("Checking preliminary research assumptions...");
    try {
      const issue = preliminaryScopeIssue(snapshot, { season, week, slate });
      if (issue) throw new Error(issue);
      if (contestFormat !== "classic" || effectiveOptimizerObjective !== "gpp" || selectedOptimizerStrategy !== "classic_large_gpp_v1") throw new Error("Preliminary research requires Classic Large GPP.");
      const snapshotHandoff = highestProjection ? null : intentHandoff(snapshot, optimizationIntent);
      const checkedPacket = snapshotHandoff?.checked_packet_sha256 ? await fetchAnalystPacket(snapshotHandoff.checked_packet_sha256) : null;
      const preliminaryPacket = highestProjection ? null : checkedAnalystSelection(analystHandoffMode, snapshotHandoff, checkedPacket, analystPacketsByContext[activeContextKey] ?? selectedAnalystPacket);
      if (!highestProjection && (analystHandoffMode === "AUTO" || snapshotHandoff)) { const handoffIssue = analystHandoffIssue(analystHandoffMode,snapshotHandoff,preliminaryPacket); if (handoffIssue) throw new Error(handoffIssue); }
      if (preliminaryPacket) {
        const packetIssue = analystPacketScopeIssue(preliminaryPacket, season, week, contestFormat);
        if (packetIssue) throw new Error(packetIssue);
      }
      const focusIssue = analystFocusedRunIssue(preliminaryPacket); if (focusIssue) throw new Error(focusIssue);
      let params = preliminaryRunParams({ ...optimizerParams(), ...analystOptimizerParams(preliminaryPacket, contestFormat), analyst_optimization_intent: optimizationIntent }, noSeasonRankRestriction);
      params = classicSelectionParams(params, highestProjection);
      if (stagedTeammateChoice && !highestProjection) {
        if (preliminaryPacket?.selected_strategy === "MERGED_SCENARIOS" && preliminaryPacket.focus_mode === "SELECTED_ONLY") throw new Error("Clear the staged cheaper branch before generating selected-only scenarios; no mixed-story fallback is allowed.");
        if (preliminaryPacket?.analyst_packet_sha256 !== stagedTeammateChoice.packetHash || preliminaryPacket.selected_strategy !== "MERGED_SCENARIOS") throw new Error("The staged cheaper branch requires its original Analyst packet and merged strategy; clear it to use another strategy.");
        params.analyst_teammate_enabled = true;
        params.analyst_teammate_choice = stagedTeammateChoice.choice;
      }
      params.analyst_handoff_mode = highestProjection ? "BASELINE" : analystHandoffMode;
      if (snapshotHandoff) params.analyst_handoff_compatibility_sha256 = snapshotHandoff.compatibility_sha256;
      if (noSeasonRankRestriction) params.preliminary_rank_preference = "explicit_no_restriction_for_this_research_run";
      if (workloadComparison === "scenario_first" && scenarioFirstPreferences.referencePlayers.length && (scenarioFirstPreferences.referencePlayers.length!==6 || !scenarioFirstPreferences.referencePlayers.includes(scenarioFirstPreferences.referenceCaptain))) throw new Error("Choose six reference players and one Captain among them, or clear the reference.");
      submittedRunId = globalThis.crypto.randomUUID();
      updateActiveRunSelection({ optimizerRunId: submittedRunId });
      const response = await runPreliminaryOptimizer(snapshot, { season, week, slate, strategy: selectedOptimizerStrategy,
        optimizer_run_id: submittedRunId, contest_format: "classic", objective: "gpp", projection_run_id: snapshot.projection_run_id, params },
        () => setPendingAction("Preliminary optimizer queued. Reopen it in Recent optimizer runs; results remain not entry cleared."));
      setOptimizerStatus(response);
      updateActiveRunSelection({ optimizerRunId: response.job_id, projectionRunId: response.projection_run_id ?? activeRunSelection.projectionRunId });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      if (submittedRunId) try { setOptimizerStatus(await fetchOptimizerResults(submittedRunId)); } catch { /* Preserve original error and saved run ID. */ }
    } finally { setPendingAction(null); }
  };

  const refreshOptimizer = async () => {
    setError(null);
    setSlateReadiness(null);
    setPendingAction("Refreshing readiness and optimizer status...");
    try {
      setSlateReadiness(await fetchSlateReadiness({ season, week, slate }));
      setPreparationStatus(await fetchPreparation({ season, week, slate }));
      await refreshOptimizerProjectionRuns();
      if (optimizerStatus?.job_id) setOptimizerStatus(await fetchOptimizerResults(optimizerStatus.job_id));
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
    const requestScope = `${learningSeason}:${learningWeek}`;
    setLearningError(null);
    if (dryRun) {
      setWeeklyContestImport(null);
      setWeeklyContestSelections({});
    }
    setPendingAction(dryRun ? "Checking weekly contest folder..." : "Loading weekly contest results...");
    try {
      const result = await importWeeklyContestFolder({
        directory: weeklyContestDirectory.trim(), season: learningSeason, week: learningWeek, dry_run: dryRun,
        ...(!dryRun ? { selected_files: selectedWeeklyContestFiles.map((file) => ({
          path: file.path,
          source_file_id: file.source_file_id ?? "",
          season: weeklyContestSelections[file.path].season,
          week: weeklyContestSelections[file.path].week,
          slate: weeklyContestSelections[file.path].slate,
          contest_format: weeklyContestSelections[file.path].contest_format,
          scoring_variant: weeklyContestSelections[file.path].scoring_variant,
          pool_sha256: weeklyContestSelections[file.path].pool_sha256,
          source_reference: weeklyContestSelections[file.path].source_reference,
          correction_of: weeklyContestSelections[file.path].correction_of,
        })) } : {}),
      });
      if (learningScopeRef.current !== requestScope) return;
      setWeeklyContestImport(result);
      if (dryRun) {
        setWeeklyContestSelections(Object.fromEntries(result.files
          .filter((file) => file.file_type === "contest_standings")
          .map((file) => [file.path, {
            selected: false, season: file.season, week: file.week,
            contest_format: file.contest_format ?? undefined, scoring_variant: file.scoring_variant ?? undefined,
            slate: isValidSlateId(file.slate) && !["UNRESOLVED","UNKNOWN","DEFAULT"].includes(file.slate) ? file.slate : "",
          }])));
      } else {
        setWeeklyContestSelections({});
      }
      const selectedWeekLoaded = result.files.some((file) =>
        file.file_type === "contest_standings" &&
        ["imported", "deduplicated"].includes(file.status) &&
        file.season === learningSeason && file.week === learningWeek
      );
      if (!dryRun && learningEntryUser.trim() && selectedWeekLoaded) {
        setPendingAction("Building week learning report...");
        try {
          const report = await generateWeeklyLearningReport({
            season: learningSeason, week: learningWeek, entry_user: learningEntryUser.trim(),
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
    const requestScope = `${learningSeason}:${learningWeek}`;
    setLearningError(null);
    setPendingAction("Pulling weekly stats and building post-slate learning report...");
    try {
      window.localStorage.setItem("dfs-learning-entry-user", entryUser);
      const report = await generateWeeklyLearningReport({
        season: learningSeason,
        week: learningWeek,
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
      <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
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

  if (viewMode === "tiers") {
    return <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}><Tiers season={season} week={week} /></AppShell>;
  }
  if (viewMode === "single-stat") {
    return <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}><SingleStat /></AppShell>;
  }

  if (viewMode === "analyst-reports") {
    return <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}><AnalystReports /></AppShell>;
  }

  if (viewMode === "preview") {
    return (
      <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <DesignPreview onBack={() => setViewMode("war-room")} />
      </AppShell>
    );
  }

  if (viewMode === "news-brief") {
    return (
      <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <DailyNewsBrief onBack={() => setViewMode("war-room")} />
      </AppShell>
    );
  }

  if (viewMode === "contest-workflow") {
    return (
      <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <ContestWorkflow
          season={season}
          week={week}
          slate={slate}
          slateOptions={slateOptions}
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
      <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <ModelWorkbench
          season={season}
          week={week}
          slate={slate}
          slateOptions={slateOptions}
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
      <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <WarRoom
          season={season}
          week={week}
          slate={slate}
          slateOptions={slateOptions}
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
      <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
        <ResearchWorkspace
          season={season}
          week={week}
          slate={slate}
          slateOptions={slateOptions}
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
      <AppShell slateOptions={learningSlateOptions} activeView={viewMode} season={learningSeason} week={learningWeek} slate={learningSlate} pendingAction={pendingAction} onSlateChange={value => updateLearningContext({ slate: value })} onNavigate={setViewMode}>
        <div className="operations-workspace learning-workspace">
          <section className="operations-command" aria-labelledby="learning-command-title">
            <div className="operations-command-copy">
              <span className="operations-eyebrow"><i aria-hidden="true" /> Post-slate review</span>
              <h2 id="learning-command-title">Learn from a completed week.</h2>
              <p>Choose a review season, week and slate. These selections are remembered separately from the rest of the app.</p>
            </div>
            <div className="operations-context" aria-label="Learning week controls">
              <label>
                Season
                <input type="number" value={learningSeason} onChange={(event) => updateLearningContext({ season: Number(event.target.value) })} />
              </label>
              <label>
                Week
                <input type="number" min={1} max={25} value={learningWeek} onChange={(event) => updateLearningContext({ week: Number(event.target.value) })} />
              </label>
              <label>
                Review slate
                <select value={learningSlate} onChange={event => updateLearningContext({ slate: event.target.value })}>
                  <option value={ALL_LEARNING_SLATES}>All slates</option>
                  {learningSlateOptions.map(option => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}
                </select>
              </label>
            </div>
          </section>
          <div className="button-row" role="tablist" aria-label="Learning sections" onKeyDown={event => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const tabs = event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]');
            const target = event.key === "Home" ? 0 : event.key === "End" ? 1 : learningTab === "review" ? 1 : 0;
            tabs[target].focus(); tabs[target].click();
          }}>
            <button role="tab" id="learning-review-tab" aria-controls="learning-review-panel" tabIndex={learningTab === "review" ? 0 : -1} aria-selected={learningTab === "review"} onClick={() => setLearningTab("review")}>Review &amp; Imports</button>
            <button role="tab" id="learning-results-tab" aria-controls="learning-results-panel" tabIndex={learningTab === "results" ? 0 : -1} aria-selected={learningTab === "results"} onClick={() => setLearningTab("results")}>Weekly Results</button>
          </div>
          {learningTab === "results" ? <div className="learning-workspace" style={{ minWidth: 0 }} role="tabpanel" id="learning-results-panel" aria-labelledby="learning-results-tab">
            <WeeklyResults season={learningSeason} week={learningWeek} slate={learningSlate} entryUser={learningEntryUser} onWeekChange={value => updateLearningContext({ week: value })}
              onEntryUserChange={value => { setLearningEntryUser(value); window.localStorage.setItem("dfs-learning-entry-user", value); }} />
          </div> : <div className="learning-workspace" style={{ minWidth: 0 }} role="tabpanel" id="learning-review-panel" aria-labelledby="learning-review-tab">
          <EntryHistory key={learningSeason} year={learningSeason} directory={weeklyContestDirectory} />
          <ShadowComparisons key={`${learningSeason}-${learningWeek}`} season={learningSeason} week={learningWeek} slate={learningSlate} />
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
                    <thead><tr>{weeklyContestImport.dry_run && <th>Load</th>}<th>File</th><th>Season</th><th>Week</th><th>Slate</th><th>Format / scoring</th><th>Status</th><th>Contest</th><th>Details</th></tr></thead>
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
                            {learningSlateOptions.map((option) => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}
                          </select> : file.slate.replaceAll("_", " ")}</td>
                          <td>{weeklyContestImport.dry_run ? <TypedAssignment label={file.path.split("/").pop() ?? file.path} choice={weeklyContestSelections[file.path] ?? {contest_format:file.contest_format ?? undefined}} onChange={value => setWeeklyContestSelections(current => ({...current,[file.path]:{...current[file.path],...value}}))} /> : `${file.contest_format ?? "Classic / Showdown"} ${file.scoring_variant ?? ""}`}</td>
                          <td>{file.status === "would_stage" || file.status === "staged"
                            ? !weeklyContestSelections[file.path]?.slate ? "Needs slate" : typedChoiceReady(weeklyContestSelections[file.path]) ? "Ready to load" : "Needs scoring evidence"
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
          <TypedResultsLibrary refreshKey={weeklyContestImport?.batch_id ?? ""} entryUser={learningEntryUser} season={learningSeason} week={learningWeek} />
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
            <WeeklyLearningLibrary entryUser={learningEntryUser} reportId={learningReport ? `${learningReport.report_id}:${learningReport.generated_at}` : undefined} onOpen={report => {
              updateLearningContext({ season: report.season, week: report.week });
              setLearningReport(report);
              setLearningError(null);
            }} />
            {learningError && <div className="error inline-error">{learningError}</div>}
            {learningReport && (
              <div className="status-card">
                <strong>
                  Week {learningReport.week} learning report: {learningReport.status} · {learningReport.summary.slates} slates · {learningReport.summary.contests_entered} contests · {learningReport.summary.entries} Classic / Showdown entries · {learningReport.summary.typed_contest_groups ?? 0} typed contests · {learningReport.summary.typed_contest_entries ?? 0} typed entries
                </strong>
                <p>Classic / Showdown totals above; typed standings below retain separate scoring units and have no inferred financial result.</p>
                <TypedGroups groups={(learningReport.format_results ?? []).filter(g => learningSlate === ALL_LEARNING_SLATES || g.slate === learningSlate)} />
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
                {learningSlate !== ALL_LEARNING_SLATES && <p className="helper-text">
                  Summary and downloaded report cover the whole week. Review details below show {learningSlate.replaceAll("_", " ")} only.
                  {!learningReport.slate_reports.some(report => normalizeSlateId(report.slate) === learningSlate) && " No saved review for this slate; evidence remains unknown."}
                </p>}
                {learningReport.slate_reports.filter(report => learningSlate === ALL_LEARNING_SLATES || normalizeSlateId(report.slate) === learningSlate).map((report) => (
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
                    <LearningCandidateDetails key={report.report_id} report={report} />
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
                            {entry.entry_evidence != null && typeof entry.entry_evidence === "object" && "url" in entry.entry_evidence && (
                              <> · <a href={String(entry.entry_evidence.url)} target="_blank" rel="noreferrer">Open saved decision and control evidence</a></>
                            )}
                            <LearningEntryEvidence entry={entry} />
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
          </div>}
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell slateOptions={slateOptions} activeView={viewMode} season={season} week={week} slate={slate} runSelection={activeRunSelection} pendingAction={pendingAction} onSlateChange={setActiveSlate} onNavigate={setViewMode}>
      <div className="operations-workspace">
      <section className="operations-command" aria-labelledby="operations-command-title">
        <div className="operations-command-copy">
          <span className="operations-eyebrow"><i aria-hidden="true" /> Live pipeline</span>
          <h2 id="operations-command-title">Choose your lineup.</h2>
          <p>
            Choose Captain or Classic, load slate files, prepare verified inputs, then run with your lineup and player settings.
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

      <section className="panel operations-panel operations-basic-inputs" aria-labelledby="basic-inputs-title">
        <details>
          <summary>Add a custom slate</summary>
          <form className="form-row" onSubmit={event => {
            event.preventDefault();
            if (pendingAction || !isValidSlateId(customSlateName)) return;
            const name = normalizeSlateId(customSlateName);
            const names = [...new Set([...customSlateNames, name])];
            setCustomSlateNames(names);
            try { window.localStorage.setItem(customSlateStorageKey, JSON.stringify(names)); } catch { /* Keep the session selection. */ }
            setActiveSlate(name);
            setCustomSlateName("");
          }}>
            <label>Custom slate name<input type="text" value={customSlateName} maxLength={64}
              placeholder="SUNDAY_LATE_SF_SEA" onChange={event => setCustomSlateName(event.target.value)} /></label>
            <button type="submit" disabled={Boolean(pendingAction) || !isValidSlateId(customSlateName)}>Select custom slate</button>
          </form>
          <p>Use a separate name for each game or contest slate, then choose Classic or Captain in Strategy and load its salary CSV. Names can contain letters, numbers, underscores and hyphens; spaces become underscores.</p>
        </details>
        <div className="operations-panel-heading">
          <span>01 · Load files</span>
          <h2 id="basic-inputs-title">Slate files</h2>
          <p>Download the slate’s DraftKings salary CSV and FanDuel injury CSV, enter their local paths, then load each file. Sunday Early and Sunday Late share the Sunday Main injury file; no separate injury file is needed. Files already loaded do not need to be loaded again.</p>
          {slate === "SUNDAY_MORNING" && <p>For a single-game CSV with CPT/FLEX rows, select Captain format. Enter the actual salary filename even if it differs from the slate label. If you have no Morning injury CSV, use Prepare slate to fetch sourced player-status evidence; missing or stale evidence will still block readiness. Sunday Morning does not inherit Sunday Main injuries.</p>}
        </div>
        <div className="basic-file-grid">
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
            <button disabled={!salaryFileToLoad || Boolean(pendingAction)} onClick={runLoadRawSalaries}>Load salary CSV</button>
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
            <button disabled={!injuryFileToLoad || Boolean(pendingAction)} onClick={runLoadRawInjuries}>Load injury CSV</button>
          </div>
        </div>
        {preparationStatus?.scope.season === season && preparationStatus.scope.week === week && preparationStatus.scope.slate.toUpperCase() === slate.toUpperCase() ? <div className="basic-loaded-inputs" role="status">
          <strong>Loaded for {slate.replaceAll("_", " ")}</strong>
          <span>Salary rows: {preparationStatus.inputs.salaries?.length ?? 0} · Injury rows: {preparationStatus.inputs.injuries?.length ?? 0}</span>
          {(preparationStatus.inputs.salaries ?? []).some(row => !row.player_master_id) && <p className="error inline-error">
            Unresolved salary identities: {(preparationStatus.inputs.salaries ?? []).filter(row => !row.player_master_id).map(row => `${row.player_name} (${row.team} · ${row.position})`).join(", ")}. Preparation must resolve or report these before optimization.
          </p>}
          <small>Files are imported, but optimizer readiness has not been certified. Complete Prepare slate below; contest compatibility and final game-day clearance are separate checks.</small>
        </div> : <p className="placeholder">Checking loaded slate files…</p>}
        {loadSummaries.length > 0 && <div role="status">
          <p>{lastLoadType} imported. {loadSummaries.find(summary => summary.dataset.startsWith("curated_"))?.rows_written ?? 0} rows stored. Preparation is still required.</p>
          {loadSummaries.filter(summary => summary.dataset.startsWith("unmatched_") && summary.rows_written > 0).map(summary =>
            <p className="error inline-error" key={summary.dataset}>{summary.rows_written} unresolved {summary.dataset.includes("salaries") ? "salary" : "injury"} identities. These records are not ready for use. Prepare slate applies saved matching rules and reports any identities that still need review.</p>)}
        </div>}
      </section>

      <section className="panel operations-panel" aria-labelledby="prepare-slate-title">
        <div className="operations-panel-heading">
          <span>02 · Prepare</span>
          <h2 id="prepare-slate-title">Prepare slate</h2>
          <ScenarioControls value={scenarioMode} disabled={Boolean(pendingAction)||preparationRunning} teams={[...new Set((preparationStatus?.inputs.salaries??[]).map(r=>String(r.team??"")).filter(Boolean))].sort()} onChange={v=>setScenarioModes(current=>({...current,[`${activeContextKey}:${contestFormat}`]:v}))}/>
          {preparedBuild?.scenario_mode&&<PreparedScenarioSummary report={preparedBuild.scenario_mode}/>}
          {contestFormat === "showdown" && <label>Optimizer comparison
            <select aria-label="Optimizer comparison" value={workloadComparison} onChange={event => setWorkloadComparison(event.target.value as typeof workloadComparison)}>
              <option value="standard">Standard optimizer (unchanged)</option>
              <option value="scenario_first">Scenario-first Captain · market primary · 3–3 · conditional v6</option>
              <option value="learned_yards">Learned opportunities → projected yards · experimental</option>
              <option value="learned_counts">Learned opportunities · no points selection gates</option>
              <option value="normalized_counts">Reference offensive workload forecasts</option>
              <option value="offensive_mean_control">Comparison · FP mean on same offensive domain</option>
            </select>
          </label>}
          {workloadComparison === "scenario_first" && <div aria-label="Scenario-first selection controls">
            <p>Market-first shared scoring cases → team opportunities → player/kicker roles → complete Captain roster. Explicit 3–3 construction. Current-starter-compatible prior games vary workloads, observed zero roles, completions and shared yards. Passing follows sourced full-team passer shares; a player/team forecast gap cannot create an unknown passer. Observed relief/trick-play work remains explicit. The market total and spread determine the primary scoring environment. Only four market-centered cases select the whole roster, including the mean-relative-capture tie-break; sixteen alternative-script cases are diagnostic only. Case likelihood is unknown. Worst-case protection is diagnostic only. Current user QB/Captain restrictions remain binding.</p>
            <label><input type="checkbox" aria-label="Exclude low-involvement backups" disabled={Boolean(pendingAction)} checked={scenarioFirstPreferences.enabled} onChange={e=>updateScenarioFirstPreferences({enabled:e.target.checked})}/>Exclude low-involvement backups (user preference; projections retained)</label>
            <label>Backup RB minimum carries + targets<input aria-label="Backup RB minimum carries and targets" disabled={Boolean(pendingAction)} type="number" min="0" step=".5" value={scenarioFirstPreferences.rbMinimum} onChange={e=>updateScenarioFirstPreferences({rbMinimum:Number(e.target.value)})}/></label>
            <label>Backup WR/TE minimum targets<input aria-label="Backup receiver minimum targets" disabled={Boolean(pendingAction)} type="number" min="0" step=".5" value={scenarioFirstPreferences.receiverMinimum} onChange={e=>updateScenarioFirstPreferences({receiverMinimum:Number(e.target.value)})}/></label>
            <p>Prepare applies supported availability/role adjustments before these cutoffs. Injury flags alone do not waive the preference or donate workload; missing expansion evidence remains explicit.</p>
            <label>Competitive case target (%)<input aria-label="Competitive case target percentage" disabled={Boolean(pendingAction)} type="number" min="1" max="100" value={scenarioFirstPreferences.captureTarget*100} onChange={e=>updateScenarioFirstPreferences({captureTarget:Number(e.target.value)/100})}/></label>
            <small>Declared decision rule: count complete-roster cases reaching this fraction of that case’s best legal score. 90% is the initial policy setting, not a learned probability or a guaranteed contest threshold.</small>
            <label>Reference players (six; comparison only)<select aria-label="Scenario reference players" disabled={Boolean(pendingAction)} multiple value={scenarioFirstPreferences.referencePlayers} onChange={e=>updateScenarioFirstPreferences({referencePlayers:Array.from(e.target.selectedOptions,o=>o.value)})}>
              {(optimizerStatus?.player_pool?.rows??[]).map(player=><option key={player.player_id} value={player.player_id}>{player.player_name} · {player.position} · {player.team}</option>)}
            </select></label>
            <label>Reference Captain<select aria-label="Scenario reference Captain" disabled={Boolean(pendingAction)} value={scenarioFirstPreferences.referenceCaptain} onChange={e=>updateScenarioFirstPreferences({referenceCaptain:e.target.value})}><option value="">Choose Captain</option>
              {(optimizerStatus?.player_pool?.rows??[]).filter(player=>scenarioFirstPreferences.referencePlayers.includes(player.player_id)).map(player=><option key={player.player_id} value={player.player_id}>{player.player_name} · {player.position} · {player.team}</option>)}
            </select></label>
            <button type="button" disabled={Boolean(pendingAction)} onClick={()=>updateScenarioFirstPreferences({referencePlayers:[],referenceCaptain:""})}>Clear scenario reference</button>
            <small>The reference never locks the selected roster or adds Captain exceptions. Preference conflicts are reported; its Captain is also evaluated with five reoptimized FLEX players when eligible. One different-Captain comparison is retained.</small>
          </div>}

          {workloadComparison === "learned_yards" && <p>Experimental role-aware efficiency × latest learned attempts/targets. Selection weights: passing yard 0.04; rushing yard 0.10; receiving yard 0.10. These are partial DraftKings yard points, not learned optimum weights or a complete points forecast: receptions, touchdowns and bonuses are omitted. No positional count normalization or full-points/P90 selection gates. Points-based team-leader preferences are inactive for this comparison request. Same-team passing/receiving yards reconcile with explicit unallocated actors. Conditional role/availability and small-sample uncertainty remain; no proven lineup improvement. Stored settings remain unchanged.</p>}
          {workloadComparison === "learned_counts" && <p>Latest published team/player models forecast attempts and targets. Fixed prior position count scales normalize selection; fantasy points and P90 are report-only. Points-based team-leader preferences are inactive for this run; stored settings remain unchanged. Captain salary/utility multiply by 1.5, physical opportunities do not. K/DST and unsupported counts are outside this comparison.</p>}
          {workloadComparison !== "standard" && workloadComparison !== "scenario_first" && <p>Count forecasts, conditional on active participation and stable observed role. K/DST and unknown forecasts are outside this comparison domain. Salary is a constraint; full fantasy projections and ownership do not enter selection; the yard arm uses declared partial DK yard weights. Prepare creates a frozen forecast receipt. Standard settings and projections remain unchanged.</p>}
          {preparationStatus?.latest_build?.workload_forecast && <details><summary>Prepared offensive count forecasts · {preparationStatus.latest_build.workload_forecast.version}</summary>
            <p>{preparationStatus.latest_build.workload_forecast.domain} · {preparationStatus.latest_build.workload_forecast.source_cutoff_at}</p>
            {preparationStatus.latest_build.workload_forecast.learned_opportunities&&!preparationStatus.latest_build.workload_forecast.yardage_model&&<><p>Latest learned opportunities · points heads unused. Team publication: {preparationStatus.latest_build.workload_forecast.learned_model_consumption?.team?.model_publication_record_id}; player publication: {preparationStatus.latest_build.workload_forecast.learned_model_consumption?.player?.model_publication_record_id}.</p><p>Utility averages pass/rush components for QBs and target/rush components for RB/WR/TE. Each component is divided by its prior position mean, with divisor floor 1. These are transparent comparison weights, not fantasy values or independent play totals.</p><details><summary>Fixed prior count normalization divisors</summary><pre>{JSON.stringify(preparationStatus.latest_build.workload_forecast.scales,null,2)}</pre></details></>}
            {preparationStatus.latest_build.workload_forecast.scenario_first&&<><p>Shared scoring cases: {preparationStatus.latest_build.workload_forecast.scenario_first.world_count} · Likelihood: unknown · Explicit policy: 3–3. Market-implied team points: {JSON.stringify(preparationStatus.latest_build.workload_forecast.scenario_first.implied_points)}. Case-mean utility below is display only.</p><details><summary>Scenario assumptions and source-role limits</summary><p>{preparationStatus.latest_build.workload_forecast.scenario_first.assumptions.join(" ")}</p></details></>}
            {preparationStatus.latest_build.workload_forecast.yardage_model&&!preparationStatus.latest_build.workload_forecast.scenario_first&&<><p>Yard weights: {JSON.stringify(preparationStatus.latest_build.workload_forecast.yardage_model.selection_weights)}. Physical yards are unmultiplied; Captain selection utility ×1.5. Unknown forecasts remain excluded; not zeros.</p><p>{preparationStatus.latest_build.workload_forecast.yardage_model.limitations.join(" ")}</p><details><summary>Forecast validation · retrospective diagnostic</summary><p>Uses actual historical attempts/targets to evaluate efficiency only; not end-to-end lineup validation. Revised history and previously inspected outcomes are not fresh held-out evidence. Mixed errors; no proven improvement.</p><pre>{JSON.stringify(preparationStatus.latest_build.workload_forecast.yardage_model.validation,null,2)}</pre></details><details><summary>Shared-yard accounting and residuals</summary><pre>{JSON.stringify(preparationStatus.latest_build.workload_forecast.yardage_model.accounting,null,2)}</pre></details><table><thead><tr><th>Player</th><th>Pass yards</th><th>Rush yards</th><th>Receiving yards</th><th>Efficiency evidence</th></tr></thead><tbody>{preparationStatus.latest_build.workload_forecast.players.filter(row=>row.native_salary_actor).map(row=><tr key={row.player_master_id}><td>{row.name}</td>{['passing_yards','rushing_yards','receiving_yards'].map(key=><td key={key}>{row.projected_yards?.[key]?.toFixed(2)??"Unknown / outside role"}</td>)}<td><details><summary>Prior efficiency and role</summary><pre>{JSON.stringify(row.efficiency,null,2)}</pre></details></td></tr>)}</tbody></table></>}
            <table><thead><tr><th>Player / native ID</th><th>Position</th><th>Pass attempts</th><th>Rush attempts</th><th>Targets</th><th>Utility</th><th>Limitations</th></tr></thead><tbody>
              {preparationStatus.latest_build.workload_forecast.players.filter(row => row.native_salary_actor).map(row => <tr key={row.player_master_id}><td>{row.name ?? row.player_master_id} · {row.native_id ?? "—"}</td><td>{row.position}</td><td>{row.counts.pass_attempts?.toFixed(2) ?? "Unknown"}</td><td>{row.counts.rush_attempts?.toFixed(2) ?? "Unknown"}</td><td>{row.counts.targets?.toFixed(2) ?? "Unknown"}</td><td>{row.utility?.toFixed(3) ?? "Not modeled"}</td><td>{row.reasons.join("; ")}</td></tr>)}
            </tbody></table></details>}
          <p>After loading files, prepare the selected {contestFormat === "classic" ? "Classic" : "Showdown"} slate. This checks identities, availability, prior-week stats and snaps, spreads, game totals, projections, and ownership together. Missing historical stats or snaps are downloaded automatically before rebuilding. Every game needs valid market data within the freshness limit. Missing, stale or inconsistent spreads/totals block optimization. Running projections alone does not certify readiness.</p>
        </div>
        <div className="button-row">
              <button onClick={() => void prepareOptimizerSlate()} disabled={Boolean(pendingAction) || preparationRunning || Boolean(scenarioIssue(scenarioMode))}>Prepare slate for optimization</button>
              <small>{preparationStatus?.build_issue}</small>
              <strong role="status">{preparationRunning ? "Preparing slate…" : optimizerPrepared ? "Prepared — ready to optimize" : currentCheckError ? "Readiness check unavailable — see status beside Run Optimizer" : !preparationStatus ? "Checking saved slate readiness…" : "Preparation required before optimization"}</strong>
        </div>
            {optimizerPrepared && <div className="readiness-preflight pass" role="status" data-testid="prepared-preflight">
              <div>
                <span>Slate preflight · {contestFormat} {effectiveOptimizerObjective}</span>
                <strong>Ready — prepared inputs verified</strong>
                <small>Sources, projections and ownership are verified for the prepared build used by Run Optimizer. Final game-day entry clearance remains separate.</small>
                <small>Projection: {preparedBuild?.projection_run_id}</small>
              </div>
            </div>}
            {!optimizerPrepared && slateReadiness && slateReadiness.season === season && slateReadiness.week === week
              && slateReadiness.slate.toUpperCase() === slate.toUpperCase() && (() => {
              const gateKey = optimizerReadinessGateKey(contestFormat, effectiveOptimizerObjective);
              const gate = slateReadiness.gates[gateKey];
              const preparationIssue = preparationBuildIssue(preparationStatus, { season, week, slate });
              const requestFailure = availabilityPreview.error ?? (preparationIssue?.status === "failed" ? preparationIssue.message : null);
              const preparingInputs = preparationIssue?.status === "preparing";
              const attention = new Set(gate.attention_checks);
              const blocking = new Set(gate.blocking_checks);
              const visibleWarnings = gate.attention_checks.length;
              const checks = slateReadiness.checks
                .filter((check) => attention.has(check.check_id))
                .sort((left, right) => Number(blocking.has(right.check_id)) - Number(blocking.has(left.check_id)))
                .slice(0, 3);
              const unresolvedPlayers = attention.has("player_identity_coverage")
                && preparationStatus?.scope.season === season && preparationStatus.scope.week === week
                && preparationStatus.scope.slate.toUpperCase() === slate.toUpperCase()
                ? Array.from(new Set((preparationStatus.inputs.salaries ?? [])
                  .filter(row => !row.player_master_id)
                  .map(row => `${row.player_name} (${row.team} · ${row.position})`))) : [];
              return (
                <div className={`readiness-preflight ${requestFailure ? "fail" : preparingInputs ? "warn" : contestFormat === "classic" && slateReadiness.classic_data_readiness?.status !== "READY" ? "fail" : gate.status}`} role="status">
                  <div>
                    <span>Slate preflight · {contestFormat} {effectiveOptimizerObjective}</span>
                    <strong>{requestFailure ? "Blocked" : preparingInputs ? "Preparing inputs" : contestFormat === "showdown" ? showdownPreflightLabel(gate.status, slateReadiness.showdown_data_readiness) : contestFormat === "classic" ? classicLivePreflightLabel(slateReadiness.classic_data_readiness) : gate.status === "fail" ? "Blocked" : visibleWarnings > 0 ? "Ready with warnings" : "Ready"}</strong>
                    {requestFailure ? <small>{requestFailure} This saved preparation attempt failed. After changing inputs, prepare again to get a current assessment.</small> : preparingInputs ? <small>{preparationIssue.message}</small> : contestFormat === "classic" ? <small>{classicLiveReadinessSummary(slateReadiness.classic_data_readiness)}</small> : <small>{gate.score}/100 · {gate.status === "fail" ? gate.message : `${visibleWarnings} warning${visibleWarnings === 1 ? "" : "s"}.`}</small>}
                    {contestFormat === "showdown" && <small>
                      {slateReadiness.showdown_data_readiness?.evaluated_at ? `Saved inputs assessed ${new Date(String(slateReadiness.showdown_data_readiness.evaluated_at)).toLocaleString()}. ` : "Coverage score does not certify generation readiness. "}
                      Prepare slate resolves source checks before generation. Refresh Status rechecks saved inputs.
                    </small>}
                    {contestFormat === "classic" && <small>
                      Saved evidence status: {String(slateReadiness.classic_data_readiness?.status ?? "UNVERIFIED")}. Prepare slate verifies required sources. Run Optimizer consumes the prepared inputs. The coverage score does not certify readiness or final game-day clearance.
                    </small>}
                    {contestFormat === "classic" && Array.isArray(slateReadiness.classic_data_readiness?.reason_codes) && <details><summary>Technical source blockers</summary><small>
                      {(slateReadiness.classic_data_readiness.reason_codes as string[]).join(", ") || "None"}.
                    </small></details>}
                  </div>
                  {contestFormat === "classic" && <ul>
                    {classicLiveSourceActions(slateReadiness.classic_data_readiness).map(action => <li key={action}>{action}</li>)}
                  </ul>}
                  {checks.length > 0 && (
                    <ul>
                      {checks.map((check) => <li key={check.check_id}>{check.message}</li>)}
                    </ul>
                  )}
                  {unresolvedPlayers.length > 0 && <p className="identity-preflight-help">
                    Unresolved salary identities: {unresolvedPlayers.join(", ")}. Prepare slate applies existing matching rules; unresolved identities remain visible for upstream review.
                  </p>}
                </div>
              );
            })()}
      </section>

      <section className="panel wide operations-panel operations-model-panel">
        <div className="optimizer-grid">
          <div className="subpanel operations-optimizer-panel">
            <div className="operations-panel-heading">
              <span>03 · Optimize</span>
              <h2>Captain and Classic optimizer</h2>
              <p>Choose Captain or Classic, configure your lineups and players, and prepare verified slate data. Lineups are optimized for GPP tournaments.</p>
            </div>
            <div className="operations-projection-status">
              <p>Prepare slate for optimization first. Once ready, run as many lineup variations as you need from the verified inputs. Source issues are resolved in preparation.
                {predictionStatus && <small>Latest rebuild: {predictionStatus.rows_written} players · {predictionStatus.message}</small>}
              </p>

            </div>
            <div className="form-row">
              <label>Strategy
                <select aria-label="Strategy" value={contestFormat} disabled={Boolean(pendingAction)}
                  onChange={event => { setContestFormat(event.target.value as "classic" | "showdown"); setSingleLineupContestUrl(""); }}>
                  <option value="showdown">Captain / Showdown GPP</option>
                  <option value="classic">Classic GPP</option>
                </select>
              </label>
              <p>{highestProjection ? "1 unlocked lineup · highest baseline projection · optional stacks and bringbacks" : `${lineupControls.numLineups} requested lineup(s) · GPP tournament strategy · ranked for tournament play.`}</p>
            </div>
            <div className="operations-disclosure optimizer-options" data-testid="optimizer-options">
              <h3>Optimizer options</h3>
              <p>Configure lineup count, exposure, construction, player preferences, availability assumptions, and optional contest evidence.</p>
              <OptimizerLineupControls key={contestFormat} value={lineupControls} format={contestFormat} disabled={Boolean(pendingAction)}
                onChange={value => setLineupControlsByFormat(current => ({ ...current, [contestFormat]: value }))} />
              {contestFormat === "showdown" && <div className="optimizer-injury-preference" aria-label="Showdown lineup preferences">
                <label className="checkbox-label"><input type="checkbox" checked={requireTeamLeader} disabled={Boolean(pendingAction)} onChange={event => { setRequireTeamLeader(event.target.checked); if (!event.target.checked) setRequireHomeTeamLeader(false); }} /><span>Require at least one season-average non-QB team leader</span></label>
                <label className="checkbox-label"><input type="checkbox" checked={requireHomeTeamLeader} disabled={Boolean(pendingAction) || !requireTeamLeader} onChange={event => setRequireHomeTeamLeader(event.target.checked)} /><span>Require the home team’s season-average leader</span></label>
                <small>Highest season DraftKings points per participating game through the prior week on each team among RB, WR, TE and K. Captain or FLEX qualifies; either team is allowed unless home-team-only is selected. Players without usable history cannot be leaders. Week 1 requires turning this option off. Exclusions do not redefine leaders.</small>
                <label className="showdown-team-limit">Captain position
                  <select aria-label="Captain position" value={captainPositions} disabled={Boolean(pendingAction)}
                    onChange={(event) => setCaptainPositions(event.target.value)}>
                    <option value="">Any position</option>
                    <option value="WR,RB">WR/RB only (default)</option>
                    <option value="WR,RB,TE">WR/RB/TE only</option>
                    <option value="WR">WR only</option>
                    <option value="RB">RB only</option>
                    <option value="TE">TE only</option>
                  </select>
                  <small>{sharedWorldCoverage || workloadComparison === "scenario_first" ? "Captain position eligibility applies in every lineup. Shared-case selection adds no mandatory QB/receiver stack. Other positions remain eligible at FLEX; projections remain unchanged." : "Applies to Captain in every lineup. WR Captain requires his team’s QB; RB Captain does not require a QB. Other positions remain eligible at FLEX; projections remain unchanged."}</small>
                </label>
                {([['captain', 'Named Captain position exceptions'], ['questionable', 'Named questionable research eligibility']] as const).map(([key, label]) => <label className="text-label" key={key}>{label}
                  <select aria-label={label} multiple value={namedResearch[key]} disabled={Boolean(pendingAction)} onChange={event => { const values = Array.from(event.target.selectedOptions, option => option.value); setNamedResearchPreferences(current => ({...current, [activeContextKey]: {...namedResearch, [key]: values}})); }}>
                    {(optimizerStatus?.player_pool?.rows ?? []).map(player => <option key={player.player_id} value={player.player_id}>{player.player_name} · {player.position} · {player.team}</option>)}
                  </select><small>{key === 'captain' ? 'Only these named players may bypass the Captain position filter. Other eligibility and QB rules still apply; this does not force selection.' : 'Only these named players bypass your questionable exclusion for research. Raw source status and model projections are unchanged. OUT/inactive and all other safety gates remain binding; this is not entry clearance.'}</small>
                </label>)}
                <label className="showdown-team-limit">Max players per team
                  <select value={showdownMaxPlayersPerTeam} disabled={Boolean(pendingAction)}
                    onChange={(event) => setShowdownMaxPlayersPerTeam(Number(event.target.value))}>
                    <option value={5}>5 — allows 5–1</option>
                    <option value={4}>4 — allows 4–2 and 3–3 (default)</option>
                    <option value={3}>3 — requires 3–3</option>
                  </select>
                  <small>Counts Captain and FLEX together. Applies to either team in every lineup; projections remain unchanged.</small>
                </label>
                <label className="checkbox-label">
                  <input type="checkbox" checked={noQbs} disabled={Boolean(pendingAction)}
                    onChange={(event) => setNoQbs(event.target.checked)} />
                  <span>No QBs in the lineup</span>
                </label>
                <label className="checkbox-label">
                  <input type="checkbox" checked={noQbCaptain} disabled={Boolean(pendingAction) || noQbs}
                    onChange={(event) => setNoQbCaptain(event.target.checked)} />
                  <span>No QB Captain</span>
                </label>
                <label className="checkbox-label">
                  <input type="checkbox" checked={noTwoQbs} disabled={Boolean(pendingAction) || noQbs}
                    onChange={(event) => setNoTwoQbs(event.target.checked)} />
                  <span>No 2 QBs in the lineup</span>
                </label>
                <small>{noQbs
                  ? "Excludes QBs from Captain and FLEX, overriding QB-required constructions. Other quality, exposure and team limits still apply. Projections remain unchanged."
                  : "Lineup preferences only. No QB Captain keeps QBs eligible at FLEX; No 2 QBs allows at most one QB per lineup. Projections remain unchanged."}</small>
              </div>}
            <div className="optimizer-injury-preference">
              <label>
                <input
                  type="checkbox"
                  checked={excludeQuestionable}
                  onChange={(event) => setExcludeQuestionable(event.target.checked)}
                />
                <span>Exclude questionable (Q) players</span>
              </label>
                  <small>Lineup preference only; projections and football opportunity remain unchanged. Use an explicit player Assume Out decision for an availability scenario.</small>
            </div>
            <label>DraftKings contest URL (optional)
              <input type="url" value={singleLineupContestUrl} onChange={event => setSingleLineupContestUrl(event.target.value)}
                placeholder="https://www.draftkings.com/draft/contest/..." />
              <small>Native payout facts are recorded when verifiable. Without a supported contest-field model, selection uses the generic proxy and reports its limitations.</small>
            </label>
            <div className="form-row checkbox-row">
              {contestFormat === "classic" && <><label className="checkbox-label">
                <input
                  type="checkbox"
                  disabled={Boolean(pendingAction)}
                  checked={enforceSingleTE}
                  onChange={(event) => setEnforceSingleTE(event.target.checked)}
                />
                Enforce single TE (exclude TE from FLEX)
              </label>
              <p>On excludes TE from FLEX. Off permits, but does not require, a second TE. Other requested constraints still apply.</p></>}
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
                  <small>{contestFormat === "showdown" ? "Exclusions are lineup preferences. Availability assumptions independently change the football scenario; Run Optimizer rebuilds projections with your selected assumptions." : "Exclusions affect lineup selection only. Explicit availability assumptions change the football scenario."}</small>
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
                    Exclude from lineup
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
                Exclude players from lineup (comma-separated names)
                <input
                  type="text"
                  value={excludePlayers}
                  onChange={(event) => setExcludePlayers(event.target.value)}
                  placeholder="e.g. George Kittle, Skyy Moore"
                />
              </label>
              <label className="text-label">
                Exclude canonical player IDs from lineup
                <input
                  type="text"
                  value={excludePlayerIds}
                  onChange={(event) => setExcludePlayerIds(event.target.value)}
                  placeholder="Comma-separated player_master_id values"
                />
              </label>
              <label className="text-label">
                Lock players in lineup (comma-separated names)
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
                  placeholder="Required in lineup"
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
                <strong>Verified prepared inputs</strong>
                <small>Prepare slate verifies spreads, totals, projections and ownership before optimization.</small>
                <button type="button" onClick={() => { refreshOptimizerProjectionRuns().catch(() => undefined); }} disabled={optimizerProjectionPending}>
                  {optimizerProjectionPending ? "Checking projections…" : "Reload projection list"}
                </button>
                <small>{optimizerProjectionRuns[0] ? `Last completed: ${optimizerProjectionRuns[0].projection_run_id}` : "No previous projection for this slate; verified preparation is required."}</small>
                {optimizerProjectionMessage && <small role="status">{optimizerProjectionMessage}</small>}
              </div>
              <small>Run Optimizer uses the prepared build. Exclusions affect selection only; changing availability assumptions requires preparation again.</small>

            </div>
            </div>
            {contestFormat === "classic" && <div className="readiness-preflight"><label>Classic selection objective
              <select aria-label="Classic selection objective" value={highestProjection ? "baseline_mean" : "scenario"} disabled={Boolean(pendingAction)} onChange={event => setClassicSelectionObjectives(current => ({...current,[activeContextKey]:event.target.value as ClassicSelectionObjective}))}>
                <option value="scenario">Analyst scenarios</option><option value="baseline_mean">Highest baseline projection · optional stacks</option>
              </select></label>
              {highestProjection && <p>One lineup with no player locks. Maximizes unchanged average projected points; QB stacks and opponent bringbacks are optional. Other eligibility, salary and roster settings remain binding. Scenario, ownership and ceiling scores are not added.</p>}
            </div>}
            {contestFormat === "showdown" && workloadComparison === "standard" && <div className="readiness-preflight"><label>Portfolio selection policy
              <select aria-label="Portfolio selection policy" value={sharedWorldCoverage?"shared_world":"legacy"} disabled={Boolean(pendingAction)} onChange={event=>{
                const enabled=event.target.value==="shared_world";
                setSharedWorldPolicies(current=>({...current,[activeContextKey]:enabled}));
                if(enabled){setOptimizationIntents(current=>({...current,[activeContextKey]:"EXPECTED_GAME"}));setAnalystModes(current=>({...current,[activeContextKey]:"AUTO"}));}
              }}><option value="legacy">Existing intent selection</option><option value="shared_world">Expected anchor + shared conditional coverage</option></select></label>
              {sharedWorldCoverage&&<p>First select the strongest completion-feasible expected-game anchor. Later entries add conditional point coverage across the same supported expected and contrary worlds. Likelihoods are unknown. No mandatory strategy stacks or starting-QB construction; your explicit settings and Captain workload eligibility remain binding. Fantasy means remain unchanged.</p>}
            </div>}
            {!highestProjection && <div className="readiness-preflight"><label>Optimization intent
              <select aria-label="Optimization intent" value={optimizationIntent} disabled={Boolean(pendingAction)||sharedWorldCoverage} onChange={event => {
                setOptimizationIntents(current => ({...current, [activeContextKey]: event.target.value as OptimizationIntent}));
                setAnalystModes(current => ({...current, [activeContextKey]: "AUTO"}));
              }}><option value="EXPECTED_GAME">Expected Game</option><option value="CONTRARIAN">Contrarian</option><option value="MIXED">Mixed research (legacy)</option></select></label>
              <p>{sharedWorldCoverage ? "Expected-game anchor plus supported authored conditional coverage; explicit personal what-ifs remain excluded. The common checked parent is used, rather than the legacy expected-only packet." : optimizationIntent === "EXPECTED_GAME" ? "The sourced primary game assessment and its upside. Explicit contrarian what-ifs are excluded; roster and exposure rules remain binding." : optimizationIntent === "CONTRARIAN" ? "Only the authored alternate story. Conditional opportunity and roster requirements remain explicit; this is not a prediction." : "Legacy mixed scenario research; expected and alternate worlds may influence the same portfolio."}</p>
              <p>Both intents use automatic checked Analyst research from the same prepared build. Your lineup settings remain binding. Selected: {intentLabel(optimizationIntent)}.</p>
            </div>}
            {contestFormat === "showdown" && optimizationIntent === "EXPECTED_GAME" && !sharedWorldCoverage && <label className="checkbox-label"><input type="checkbox" checked={constructionComparison} disabled={Boolean(pendingAction)} onChange={event => setConstructionComparison(event.target.checked)} /><span>Original CONSTRUCTION comparison · checked Expected Game evidence recorded only; original generation and scoring policy</span></label>}
            {!highestProjection && <><AnalystPreparationSummary handoff={preparedAnalystHandoff} mode={analystHandoffMode} busy={Boolean(pendingAction)} onAutomatic={() => setAnalystModes(current => ({...current,[activeContextKey]:"AUTO"}))} />
            <AnalystPacketControls season={season} week={week} format={contestFormat} disabled={Boolean(pendingAction) || optimizationIntent !== "MIXED"}
              selected={selectedAnalystPacket} onSelect={selectAnalystOverride} /></>}
            {contestFormat === "classic" && <div id="preliminary-generation-controls">{stagedTeammateChoice && <p role="status">Staged cheaper branch: <strong>{stagedTeammateChoice.label}</strong> · original Analyst inputs selected. <button type="button" disabled={Boolean(pendingAction)} onClick={() => setTeammateChoices(current => ({...current,[activeContextKey]:null}))}>Clear cheaper branch</button></p>}<PreliminaryClassicControls scope={{season,week,slate}} preparation={preparationStatus} onPrepare={() => prepareOptimizerSlate(true)}
              enabled={effectiveOptimizerObjective === "gpp" && selectedOptimizerStrategy === "classic_large_gpp_v1"} busy={Boolean(pendingAction)}
              excludeQuestionable={excludeQuestionable} analystMode={highestProjection ? "BASELINE" : analystHandoffMode} optimizationIntent={highestProjection ? "MIXED" : optimizationIntent} analystOverride={selectedAnalystPacket ? {analyst_packet_sha256:selectedAnalystPacket.analyst_packet_sha256,analyst_strategy:selectedAnalystPacket.selected_strategy} : undefined} onSnapshot={snapshot => setPreliminaryAnalystInputs(current => ({...current,[activeContextKey]:snapshot}))} onAutomatic={() => setAnalystModes(current => ({...current,[activeContextKey]:"AUTO"}))} compatibleSnapshotHash={analystHandoffMode === "MANUAL" ? selectedAnalystPacket?.discovery_snapshot_sha256 : undefined} onGenerate={generatePreliminaryResearch} /></div>}
            <p className="optimizer-settings-summary">{contestFormat === "classic" ? "Classic" : "Captain / Showdown"} · {highestProjection ? 1 : lineupControls.numLineups} requested {highestProjection ? "highest-projection lineup" : "GPP tournament lineup(s)"} · Questionable players: {excludeQuestionable ? "excluded" : "allowed"}</p>
            {error && <div role="alert" className="error inline-error">{error}</div>}
            <div id="optimizer-readiness-status" className="optimizer-readiness-status" role="status" aria-live="polite">
              {optimizerWait.busy && <progress aria-label="Optimizer readiness in progress" />}
              <span>{optimizerWait.message}</span>
            </div>
            <div className="button-row">
              <button aria-describedby="optimizer-readiness-status" className="operations-primary-action" onClick={runOptimizerJob} disabled={Boolean(pendingAction) || !optimizerPrepared}>Run Optimizer</button>
              <button onClick={refreshOptimizer} disabled={Boolean(pendingAction)}>
                Refresh Status
              </button>
            </div>
          </div>

        </div>
      </section>

      <details className="operations-disclosure" data-testid="weekly-pipeline-options">
        <summary>Weekly pipeline</summary>
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

      </details>

      <details className="operations-disclosure" data-testid="preparation-tools">
        <summary>Preparation and data tools</summary>
        <p>Review source evidence, refresh markets, resolve identities and starting QBs, or run individual preparation steps.</p>
        <div className="button-row">
          <button type="button" onClick={() => setViewMode("model-workbench")}>Open Model</button>
          <button type="button" onClick={runSimulationJob} disabled={Boolean(pendingAction)}>Run Simulation</button>
          <small>Simulation measures optimal-roster frequency; GPP paid-finish probability and expected return require contest-field evaluation.</small>
          {simulationStatus && <small className="status-text">{simulationStatus.message} · {simulationStatus.simulation_run_id}</small>}
        </div>
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
          <SlatePreparation contestFormat={contestFormat} onStatus={setPreparationStatus} onCheckState={setPreparationCheck} scope={{ season, week, slate }} salaryPath={salaryFileToLoad ?? ""}
            injuryPath={injuryFileToLoad ?? ""} busy={Boolean(pendingAction)}
            getAvailabilityOverrides={configuredAvailabilityOverrides} assumeQuestionableOut={false}
            onStartingQbs={runStartingQBs} />
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
                      <option value="classic">Classic GPP</option>
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
                {slateOptions.map((option) => (
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

      </details>

      <div className="activity-wrapper">
        <section className="panel summary-panel unified activity-panel operations-panel operations-activity-panel">
          <div className="summary-header">
            <div className="operations-panel-heading">
              <span>05 · Review</span>
              <h2>Run activity</h2>
            </div>
            {lastLoadType && <span className="summary-subtitle">{lastLoadType}</span>}
          </div>
          <RecentOptimizerRuns season={season} week={week} slate={slate}
            contestFormat={contestFormat} objective={effectiveOptimizerObjective}
            selectedRunId={activeRunSelection.optimizerRunId} loadedRunId={optimizerStatus?.job_id}
            onOpen={openRecentOptimizer} />
            {<AnalystIntentComparison key={activeContextKey} contextKey={activeContextKey} current={optimizerStatus} scope={{season,week,slate}} />}
            {optimizerStatus?.preliminary_report && <div className="status-card">
              <h3>Preliminary research · not entry cleared</h3>
              <p>Both current injury assumptions and missing source evidence remain explicit. Use Check upload readiness in Recent optimizer runs to validate the saved players for CSV download.</p>
              <details><summary>Frozen preliminary assumptions and normal readiness failures</summary>
                <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(optimizerStatus.preliminary_report, null, 2)}</pre>
              </details>
            </div>}
            {optimizerStatus?.football_analyst?.teammate_opportunity && <TeammateOpportunityReview report={optimizerStatus.football_analyst.teammate_opportunity} busy={Boolean(pendingAction)} focusOnly={selectedAnalystPacket?.selected_strategy === "MERGED_SCENARIOS" && selectedAnalystPacket.focus_mode === "SELECTED_ONLY"} onChoose={pair => void stageTeammateAlternative(pair)} />}
            {optimizerStatus?.football_analyst && <details className="operations-disclosure">
              <summary>Wones Football Analyst · {analystResearchEvidence(optimizerStatus.football_analyst.research_consumption ?? optimizerStatus.analyst_handoff_applied?.research_coverage).lines[0]}</summary>
              {optimizerStatus.football_analyst.optimization_intent && <p>Intent: {intentLabel(optimizerStatus.football_analyst.optimization_intent.intent)} · {optimizerStatus.football_analyst.optimization_intent.assessment}</p>}
              <PersonalThoughtSummary context={optimizerStatus.analyst_handoff_applied?.personal_context as PersonalContext | undefined} />
              <AnalystResearchSummary value={optimizerStatus.football_analyst.research_consumption ?? optimizerStatus.analyst_handoff_applied?.research_coverage} results={optimizerStatus.results} />
              <SharedWorldSummary value={optimizerStatus.football_analyst.shared_world_selection} players={optimizerStatus.player_pool?.rows} />
              <p>Construction status: {optimizerStatus.football_analyst.status ?? "unavailable"}</p>
              <p>Strategy: {optimizerStatus.football_analyst.mode ?? "ANALYST_CONSTRUCTION"} · {optimizerStatus.football_analyst.portfolio_mode ?? "conditional coverage"}</p>
              {optimizerStatus.football_analyst.focus && <AnalystFocusSummary focus={optimizerStatus.football_analyst.focus} results={Array.isArray(optimizerStatus.results) ? optimizerStatus.results : []} />}
              {optimizerStatus.football_analyst.challenger && <details><summary>Blind-spot hunter · {optimizerStatus.football_analyst.challenger.status}</summary><p>Targeted solves: {optimizerStatus.football_analyst.challenger.solver_calls} · New candidates: {optimizerStatus.football_analyst.challenger.accepted_candidate_count}</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(optimizerStatus.football_analyst.challenger, null, 2)}</pre></details>}
              {optimizerStatus.football_analyst.discovery && <div><p>Discovery: {optimizerStatus.football_analyst.discovery.scanned_games.length} games screened before allocation.</p>{optimizerStatus.football_analyst.discovery.findings.map(finding => <p key={finding.finding_id}>{finding.finding_id}: {finding.action_status} · {finding.decision_reason} · Constructed slots: {finding.actual_allocation_slots?.join(", ") || "none"}</p>)}</div>}
              {optimizerStatus.football_analyst.scenario_allocation_plan && <details><summary>Football ideas allocated before construction · actual dependence audit</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(optimizerStatus.football_analyst.scenario_allocation_plan, null, 2)}</pre></details>}
              <p style={{ overflowWrap: "anywhere" }}>Packet: {optimizerStatus.football_analyst.packet_sha256}</p>
              {optimizerStatus.football_analyst.mode === "MERGED_SCENARIOS" && <>
                <p>Quality screen: none · Baseline veto: disabled · Scenario sensitivities and allocation priorities: uncalibrated</p>
                <p>Portfolio: {optimizerStatus.football_analyst.achieved_portfolio_size}/{optimizerStatus.football_analyst.requested_portfolio_size} · Solver: {optimizerStatus.football_analyst.selection?.solver_status}</p>
                <p>{optimizerStatus.football_analyst.selection?.selection_reason}</p>
                {optimizerStatus.football_analyst.captain_analysis && <details>
                  <summary>Captain-specific Analyst · {optimizerStatus.football_analyst.captain_analysis.eligible_captain_count} assessed</summary>
                  <p>Conditional FLEX comparisons preserve Captain identity. Missing evidence remains unknown; opponent players follow workload paths and roster rules.</p>
                  {optimizerStatus.football_analyst.captain_analysis.assessments.map(assessment => <p key={assessment.player_master_id}>
                    {assessment.player_name} · {assessment.team} {assessment.position} · {assessment.opponent_team}: {assessment.opponent_capability} · Captain mechanism: {assessment.mechanism_status} · {assessment.generated_candidate_count} alternatives, {assessment.selected_lineup_count} selected · {assessment.generation_status}
                  </p>)}
                </details>}
                <details><summary>Scenario assumptions, scores and frozen comparison</summary>
                  <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(optimizerStatus.football_analyst, null, 2)}</pre>
                </details>
              </>}
              <p>Generated: {optimizerStatus.football_analyst.generated_candidate_count ?? optimizerStatus.football_analyst.generated_count ?? optimizerStatus.football_analyst.eligible_generated_count ?? "See per-step report"} · Selected: {optimizerStatus.football_analyst.selected_lineup_count ?? optimizerStatus.football_analyst.selected_count ?? "Recorded with lineup thesis IDs"}</p>
              <p>Requested candidates: {optimizerStatus.football_analyst.requested_candidate_count ?? "See thesis report"} · Abstentions: {optimizerStatus.football_analyst.abstention_count ?? "See thesis report"}</p>
              {optimizerStatus.football_analyst.theses?.map(thesis => <p key={thesis.thesis_id}>
                {thesis.analyst_thought ?? thesis.thesis_id} · {thesis.status} · {thesis.achieved ?? 0}/{thesis.requested ?? 0} requested
                {thesis.reasons?.length ? ` · ${thesis.reasons.join("; ")}` : ""}
              </p>)}
            </details>}
          {optimizerStatus?.contest_format === "showdown" && <div className="status-card">
            <h3>Showdown data readiness</h3>

            <p>Generation readiness: {String(optimizerStatus.data_readiness?.status ?? "Unverified archived run")}</p>
            {optimizerStatus.data_readiness && <details><summary>Frozen generation checks</summary><pre>{JSON.stringify(optimizerStatus.data_readiness, null, 2)}</pre></details>}
            <p>Entry ready: {optimizerStatus.entry_readiness?.entry_ready === true ? "Yes" : "No"} · {String(optimizerStatus.entry_readiness?.status ?? "Not evaluated for this saved run")}</p>
            <p>Current player clearance remains unevaluated by this frozen-input report. Review Operations preparation before the next user-invoked run.</p>
            {optimizerStatus.entry_readiness && <details><summary>Checks and consumed provenance</summary><pre>{JSON.stringify(optimizerStatus.entry_readiness, null, 2)}</pre></details>}
          </div>}
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
              <div style={{ overflowX: "auto" }}><table className="compact-table">
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
              </table></div>
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
            <div className="status-card optimizer-results" ref={optimizerResultsRef}>
              <h3>
                Optimizer · {ACTIVE_OPTIMIZER_STRATEGIES.find(strategy => strategy.id === optimizerStatus.strategy)?.label ?? CLASSIC_CONTEST_STRATEGIES.find(
                  (strategy) => strategy.id === optimizerStatus.strategy
                )?.label ?? optimizerStatus.strategy}
              </h3>
              {optimizerStatus.scenario_mode&&<SavedScenarioSummary report={optimizerStatus.scenario_mode}/>}
              {highestProjectionReport && !optimizerStatus.scenario_mode && <section aria-label="Highest baseline projection result">
                <h4>Highest baseline projection · optional stacks</h4>
                <p>{highestProjectionReport.solver_status} · {highestProjectionReport.base_mean?.toFixed(2)} projected points · ${highestProjectionReport.salary?.toLocaleString()} · No player locks</p>
                <p>Highest among the eligible prepared pool under the remaining user rules. Baseline means only; no scenario, ownership, ceiling or correlation bonuses.</p>
              </section>}
              {singleLineupReportHtml(optimizerStatus) && <div dangerouslySetInnerHTML={{ __html: singleLineupReportHtml(optimizerStatus) }} />}
              {optimizerStatus.status === "completed" && optimizerStatus.objective === "gpp" && !optimizerStatus.gpp_recommendation && !highestProjectionReport && !optimizerStatus.scenario_mode &&
                <p>This saved run predates GPP recommendations. Run the optimizer to save a candidate comparison and one recommendation.</p>}
              {optimizerStatus.status === "completed" && optimizerStatus.objective === "gpp" && optimizerStatus.gpp_recommendation && !highestProjectionReport && !optimizerStatus.preliminary_report &&
                <GppRecommendation report={optimizerStatus.gpp_recommendation} pending={lineupExportPending}
                  onDownload={async () => {
                    setLineupExportPending(true); setLineupExportError(null);
                    try { await downloadOptimizerLineups(optimizerStatus.job_id, true); }
                    catch (error) { setLineupExportError(error instanceof Error ? error.message : String(error)); }
                    finally { setLineupExportPending(false); }
                  }} />}
              <p>Job ID: {optimizerStatus.job_id}</p>
              <p>Status: {optimizerStatus.status}</p>
              <p>Strategy: {((optimizerStatus.results as any[][])?.[0])?.some(row => row.scenario_first_lineup_report) ? 'Scenario-first Captain · whole-roster conditional case selection' : optimizerStatus.strategy}</p>
              <ClassicGameConcentrationReport optimizer={optimizerStatus} />
              <ClassicLargeGppReadinessReport key={optimizerStatus.job_id} optimizer={optimizerStatus}
                onAssessment={value => setOptimizerStatus({ ...optimizerStatus, readiness_assessment: value })} />
              <ClassicConstructionReport key={`${optimizerStatus.job_id}:${enforceSingleTE}`} optimizer={optimizerStatus} enforceSingleTE={enforceSingleTE} />
              {!highestProjectionReport && !optimizerStatus.scenario_mode && !((optimizerStatus.results as any[][])?.[0])?.some(row => row.scenario_first_lineup_report) && typeof optimizerStatus.strategy_config.description === "string" && (
                <p>{optimizerStatus.strategy_config.description}</p>
              )}
              <p>{optimizerStatus.message}</p>
              {optimizerStatus.contest_format === "showdown" && Array.isArray(optimizerStatus.results) && (() => {
                const first = (optimizerStatus.results[0] as any[])?.[0];
                const policy = first?.showdown_qb_preferences;
                return <div className="status-card nested-card">
                  <h4>QB CONSTRUCTION POLICY</h4>
                  <p>QB Captain allowed: {policy ? qbCaptainDescription(policy) : "Unavailable"} · Maximum starting QBs: {policy ? qbLineupLimit(policy) : "Unavailable"}</p>
                  <p>Requested lineup count: {policy?.requested_portfolio_size ?? "Unavailable"} · Effective QB-Captain lineup limit: {policy ? qbCaptainLimitDescription(policy) : "Unavailable"} · Effective starting-QB lineup limit: {policy ? qbLineupLimit(policy) : "Unavailable"}</p>
                  <p>{captainPositionsDescription(first?.showdown_captain_preferences ?? {})}.</p>
                  <p>{teamLimitDescription(first?.showdown_team_constraints ?? {})}. Captain and FLEX count together.</p>
                  <p>User lineup constraints preserve model assessments.</p>
                </div>;
              })()}
              {Array.isArray(optimizerStatus.results) && (() => {
                const report = (optimizerStatus.results[0] as any[])?.[0]?.portfolio_exposure_report;
                const warnings = report?.rows?.filter((row: any) => exposureWarning(row));
                if (!warnings?.length) return null;
                return <div className="status-card nested-card">
                  <h4>Underfilled portfolio exposure</h4>
                  <p>REQUESTED-PORTFOLIO CAP COMPLIANCE uses {report.requested_lineups} requested entries. FINAL-PORTFOLIO REALIZED EXPOSURE uses {report.generated_lineups} generated entries.</p>
                  {warnings.map((row: any) => <p key={`${row.scope}:${row.player_id}`}>
                    <strong>{row.player_name} ({row.scope})</strong>: {row.actual_appearances}/{row.generated_lineups} = {(row.final_generated_portfolio_exposure * 100).toFixed(1)}% realized; {(row.configured_cap * 100).toFixed(0)}% configured. {exposureWarning(row)}
                  </p>)}
                </div>;
              })()}
              {Array.isArray(optimizerStatus.results) && (() => {
                const preferences = (optimizerStatus.results[0] as any[])?.[0]?.showdown_qb_preferences;
                if (!preferences?.exclusions?.length) return null;
                return <p>User lineup preferences: {preferences.exclusions.map((item: any) => item.reason).join(" · ")}. Model assessments preserved.</p>;
              })()}
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
              <details open={!optimizerStatus.scenario_mode}><summary>{optimizerStatus.scenario_mode?"Baseline projection diagnostics · comparison only":"Projection diagnostics"}</summary><ModelDisagreementPanel projectionRunId={optimizerStatus.projection_run_id} optimizer={optimizerStatus} /></details>
              {optimizerStatus.status === "completed" && !optimizerStatus.preliminary_report && <SkillExposureApprovalPanel optimizer={optimizerStatus} onNewRun={async (runId) => {
                const response = await fetchOptimizerResults(runId);
                setOptimizerStatus(response);
                updateActiveRunSelection({ optimizerRunId: runId,
                  projectionRunId: response.projection_run_id ?? activeRunSelection.projectionRunId });
              }} />}
              {optimizerStatus.status === "completed" && Array.isArray(optimizerStatus.results) && optimizerStatus.results.length > 0 && (
                <div>
                  <div className="button-row">
                    <button disabled={lineupExportPending || Boolean(optimizerStatus.preliminary_report)} onClick={async () => {
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
                      {lineupExportPending ? "Preparing download…" : optimizerStatus.results.length === 1 ? "Download lineup for DraftKings" : `Download all ${optimizerStatus.results.length} lineups for DraftKings`}
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
                                      player.captain_user_preference_exclusions?.length
                                        ? player.captain_user_preference_exclusions.map((item) => item.reason).join(", ")
                                        : player.flex_only ? "Captain excluded · FLEX allowed" : null,
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
                    return <><h3>Showdown game-script scenarios</h3><p>{report.scenario_generation_status} · Legacy required coverage {report.require_scenario_diversity ? "on" : "off"}. Conditions discover rosters; baseline quality stays primary; soft coverage is {report.soft_scenario_diversity ? "on" : "off"}. Mean and P90 maxima may come from different rosters. Captain, team split and salary describe the maximum-selector roster.</p><div className="scroll-table"><table className="compact-table"><thead><tr><th>Scenario</th><th>Condition</th><th>Candidates</th><th>Best rank</th><th>Independent maximum baseline mean</th><th>Independent maximum summed marginal P90</th><th>Maximum baseline selector</th><th>Captain at maximum selector</th><th>Team split</th><th>Salary</th><th>Selected</th><th>Reason</th></tr></thead><tbody>{["baseline", "team_a_decisive_win", "team_b_decisive_win"].map((id) => { const family = families.find((item: any) => item.scenario_id === id); const definition = definitions?.find((item: any) => item.scenario_id === id); return <tr key={id}><td>{definition?.label ?? id.replaceAll("_", " ").toUpperCase()}</td><td>{definition?.conditioned_winner ? `${definition.conditioned_winner} by ${definition.decisive_margin_threshold}+` : id === "baseline" ? "Market" : "Unavailable"}</td><td>{family?.candidate_count ?? 0}</td><td>{family ? `#${family.best_rank}` : "—"}</td><td>{family ? Number(family.best_mean).toFixed(1) : "—"}</td><td>{family ? Number(family.best_p90).toFixed(1) : "—"}</td><td>{family ? Number(family.best_selector).toFixed(1) : "—"}</td><td>{family?.best_captain ?? "—"}</td><td>{family?.best_team_split ?? "—"}</td><td>{family ? `$${Number(family.best_salary).toLocaleString()}` : "—"}</td><td>{family?.selected ? "Yes" : "No"}</td><td>{family?.reason ?? report.scenario_generation_status}</td></tr>; })}</tbody></table></div><ScenarioPortfolioAccounting report={report} /></>;
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
                    const cashDiagnostic = lineup.find((row: any) => row.cash_lineup_selection)?.cash_lineup_selection?.diagnostics;
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
                    const workloadLineup = lineup.some((p:any)=>p.workload_forecast);
                    const scenarioFirstLineup = lineup.some((p:any)=>p.scenario_first_lineup_report);
                    return (
                      <div className="lineup-card" id={`optimizer-lineup-${idx + 1}`} key={`lineup-${idx}`}>
                        <JointOpportunitySummary summary={lineup[0]?.analyst_joint_opportunity_summary} />
                        <div className="lineup-header">
                          {!highestProjectionReport && optimizerStatus.gpp_recommendation?.recommended?.lineup_number === idx + 1 && <strong>{lineup.some((row:any) => row.workload_forecast) ? "Workload recommendation" : "Recommended GPP candidate · provisional"}</strong>}
                          <strong>{lineup.some((row: any) => row.cash_lineup_selection) ? idx === 0 ? "Primary recommendation" : `Additional requested lineup ${idx + 1}` : lineup[0]?.lineup_variant === "long_shot" ? "Long-shot lineup" : `Lineup ${idx + 1}`}</strong>
                          <span>Salary: {totalSalary.toLocaleString()}</span>
                          {!lineup.some((p:any)=>p.scenario_first_lineup_report)&&<span>{lineup.some((p:any)=>p.workload_forecast) ? "Incumbent points (report only)" : optimizerStatus.scenario_mode ? "Baseline mean" : "Mean"}: {totalProj.toFixed(2)}</span>}
                          {lineup.some((p:any)=>p.workload_forecast)&&<span>{lineup.some((p:any)=>p.scenario_first_lineup_report)?"Mean conditional case score (display only)":"Opportunity utility"}: {lineup.reduce((sum:number,p:any)=>sum+Number(p.workload_forecast?.utility??0)*(p.roster_position==="CPT"?1.5:1),0).toFixed(3)}</span>}
                          {optimizerStatus.scenario_mode&&<span>Selection forecast: {lineup.reduce((sum:number,p:any)=>sum+Number(p.scenario_mean??0),0).toFixed(2)}</span>}
                          {cashDiagnostic && <span>Downside: {Number(cashDiagnostic.downside_diagnostic).toFixed(2)} · Upside: {Number(cashDiagnostic.upside_diagnostic).toFixed(2)} · Proxy score: {Number(cashDiagnostic.selection_score).toFixed(2)}</span>}
                          {!scenarioFirstLineup&&<span>{optimizerStatus.scenario_mode||workloadLineup?"Baseline individual ceiling sum (report only)":ceilingSummary.label}: {ceilingSummary.value.toFixed(2)}</span>}
                          {lineup[0]?.showdown_scenario && <span>Scenario: {lineup[0].showdown_scenario.label} · winner {lineup[0].showdown_scenario.conditioned_winner ?? "market"} · {lineup[0].showdown_scenario.decisive_margin_threshold}+ points · baseline mean {lineup.reduce((sum: number, row: any) => sum + Number(row.baseline_projection ?? row.projection ?? 0), 0).toFixed(2)} → discovery-conditioned {lineupConditionedTotal(lineup, "mean")} · baseline P90 {lineup.reduce((sum: number, row: any) => sum + Number(row.baseline_p90 ?? row.p90 ?? 0), 0).toFixed(2)} → discovery-conditioned {lineupConditionedTotal(lineup, "p90")}</span>}
                          {hasContextScoring && !highestProjectionReport && !optimizerStatus.scenario_mode && !workloadLineup && (
                            <span>
                              Context: {totalContextAdjustment >= 0 ? "+" : ""}
                              {totalContextAdjustment.toFixed(2)}
                            </span>
                          )}
                          {optimizerStatus.strategy === "classic_head_to_head_v1" && (
                            <span>Floor: {totalFloor.toFixed(2)} · Risk: {(totalProj - totalFloor).toFixed(2)}</span>
                          )}
                          {stackSummary && <span>Stack: {stackSummary}</span>}
                          {correlationSummary && !highestProjectionReport && !optimizerStatus.scenario_mode && !workloadLineup && (
                            <span>
                              Correlation: {correlationAdjustment >= 0 ? "+" : ""}
                              {correlationAdjustment.toFixed(2)}
                            </span>
                          )}
                          {gameScript && !optimizerStatus.scenario_mode && !workloadLineup && <span>Lineup structure: {gameScript}</span>}
                          {lineup[0]?.showdown_selection_diagnostic && <span>Global rank #{lineup[0].showdown_selection_diagnostic.global_candidate_rank} · mean loss {Number(lineup[0].showdown_selection_diagnostic.mean_loss).toFixed(2)} · P90 loss {Number(lineup[0].showdown_selection_diagnostic.p90_loss).toFixed(2)} · selector loss {Number(lineup[0].showdown_selection_diagnostic.selector_loss).toFixed(2)} · scenario diversity changed selection {lineup[0].showdown_selection_diagnostic.scenario_diversity_changed_selection ? "yes" : "no"}</span>}
                          {optimizerStatus.objective === "gpp" && (
                            <>
                              <span>
                                {workloadLineup ? "Ownership not used in opportunity selection" : ownershipAvailable
                                  ? `Ownership: ${totalOwnership.toFixed(2)}`
                                  : optimizerStatus.scenario_mode ? "Ownership not used in this selection objective" : highestProjectionReport ? "Ownership unavailable — not used in baseline objective" : "GPP ownership unavailable — optimizing ceiling/correlation only"}
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
                        {!ACTIVE_OPTIMIZER_STRATEGIES.some(strategy => strategy.id === optimizerStatus.strategy) && <OptimizerControlComparison comparison={lineup[0]?.lineup_control_comparison} />}
                        {correlationRules.length > 0 && !highestProjectionReport && (
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
                        {lineup.some((row:any)=>row.scenario_first_lineup_report)&&<ScenarioFirstLineup report={lineup.find((row:any)=>row.scenario_first_lineup_report).scenario_first_lineup_report} lineup={sortedLineup}/>}
                        {!scenarioFirstLineup&&lineup.some((row:any) => row.workload_forecast) && <details><summary>Saved explicit offensive forecasts and assumptions</summary>
                          <p>Physical counts and yards are unmultiplied, including Captain. Targets and QB pass attempts share the same plays. The yard comparison uses explicit partial DK scoring; count utility uses positional normalization. Neither establishes calibrated tournament value.</p>
                          {lineup.some((row:any)=>row.workload_forecast?.projected_yards)&&<><p>Yard selection: 0.04 × passing + 0.10 × rushing + 0.10 × receiving. Partial DK yard scoring only; no count normalizers, receptions, touchdowns or bonuses. Captain utility ×1.5; physical yards unchanged. Experimental, conditional on role/participation; no proven tournament improvement.</p><table><thead><tr><th>Player</th><th>Pass yards</th><th>Rush yards</th><th>Receiving yards</th><th>Role / efficiency</th></tr></thead><tbody>{sortedLineup.map((row:any)=><tr key={row.player_id}><td>{row.name}</td>{['passing_yards','rushing_yards','receiving_yards'].map(key=><td key={key}>{row.workload_forecast?.projected_yards?.[key]?.toFixed(2)??"Outside role / unknown"}</td>)}<td><details><summary>Prior evidence and reconciliation</summary><pre>{JSON.stringify({efficiency:row.workload_forecast?.efficiency,receiving_factor:row.workload_forecast?.receiving_team_reconciliation_factor},null,2)}</pre></details></td></tr>)}</tbody></table></>}
                          <table className="compact-table"><thead><tr><th>Player</th><th>Pass attempts</th><th>Rush attempts</th><th>Targets</th><th>Selection utility</th><th>Forecast / assumption</th></tr></thead><tbody>
                            {sortedLineup.map((row:any) => <tr key={row.player_id}><td>{row.name}</td><td>{row.workload_forecast?.counts.pass_attempts?.toFixed(2) ?? "N/A"}</td><td>{row.workload_forecast?.counts.rush_attempts?.toFixed(2) ?? "N/A"}</td><td>{row.workload_forecast?.counts.targets?.toFixed(2) ?? "N/A"}</td><td>{row.workload_forecast?.utility?.toFixed(3)}</td><td>{row.workload_forecast?.version} · {row.workload_forecast?.conditional_on}</td></tr>)}
                          </tbody></table>
                        </details>}
                        <table className="compact-table">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>Slot · Pos</th>
                              <th>Team</th>
                              <th>Salary</th>
                              <th>{scenarioFirstLineup?"Case mean · display only":optimizerStatus.scenario_mode?"Baseline proj":"Proj"}</th>
                              {optimizerStatus.scenario_mode&&<th>Selection forecast</th>}
                              {!scenarioFirstLineup&&<th>P90</th>}
                              {lineup[0]?.showdown_scenario && <><th>Baseline mean / P90</th><th>Scenario reason</th></>}
                              <th>Rules</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sortedLineup.map((player: any) => {
                              const displayRosterPosition = highestProjectionReport ? player._slot ?? player.roster_position : player.roster_position;
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
                                    {displayRosterPosition && player.position && displayRosterPosition !== player.position
                                      ? `${displayRosterPosition} · ${player.position}`
                                      : displayRosterPosition || player.position}
                                  </td>
                                  <td>{player.player_team || player.team || player.recent_team}</td>
                                  <td>{Number(player.salary || 0).toLocaleString()}</td>
                                  <td>{scenarioFirstLineup?(Number(player.workload_forecast?.utility??0)*(player.roster_position==="CPT"?1.5:1)).toFixed(2):(Number(player.projection ?? player.predicted_mean) || 0).toFixed(2)}</td>
                                  {optimizerStatus.scenario_mode&&<td>{(player.scenario_mean??player.scenario_mode_player?.conditional_mean)==null?"Unknown":Number(player.scenario_mean??player.scenario_mode_player?.conditional_mean).toFixed(2)}</td>}
                                  {!scenarioFirstLineup&&<td>{(Number(player.p90 ?? player.predicted_p90 ?? player.projection) || 0).toFixed(2)}</td>}
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
