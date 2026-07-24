import { useCallback, useEffect, useState } from "react";
import "./App.css";
import { AppShell, type ViewMode } from "./AppShell";
import { DailyNewsBrief } from "./DailyNewsBrief";
import { ContestWorkflow } from "./ContestWorkflow";
import { DesignPreview } from "./DesignPreview";
import { DigitalTwin } from "./DigitalTwin";
import { ModelWorkbench } from "./ModelWorkbench";
import { ResearchWorkspace } from "./ResearchWorkspace";
import { WarRoom } from "./WarRoom";
import type {
  LoadSummary,
  DataQualityHistoryResponse,
  SlateLoadResponse,
  OptimizerResponse,
  SlateReadinessGateKey,
  SlateReadinessResponse,
  SimulationResponse,
} from "./api";
import {
  analyzePastSlate,
  buildFeatures,
  fetchLatestPredictions,
  fetchDataQualityHistory,
  fetchOptimizerResults,
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
  setSymbolicRuleEnabled,
  startPostgres,
  upsertSymbolicRule,
  type AgentRunResponse,
  type BuildFeaturesResponse,
  type OwnershipLoadPayload,
  type OwnershipPayoutTierInput,
  type PredictionRow,
  type SymbolicBacktestResponse,
  type SymbolicRule,
  type StartPostgresResponse,
  type StartingQBResponse,
  type UnmatchedSalaryRow,
  type ValidationRow,
} from "./api";
import { fetchUnmatchedInjuries, type UnmatchedInjuryRow } from "./api";
const SLATE_OPTIONS = [
  "SUNDAY_MAIN",
  "SUNDAY_EARLY",
  "SUNDAY_LATE",
  "MONDAY_NIGHT",
  "TUESDAY_NIGHT",
  "WEDNESDAY_NIGHT",
  "THURSDAY_NIGHT",
  "FRIDAY_NIGHT",
  "SATURDAY_NIGHT",
  "SUNDAY_NIGHT",
  "SUNDAY_MONDAY",
];

const DEFAULT_SEASON = 2025;
const DEFAULT_WEEK = 11;
type CashStackPolicyId =
  | "classic_cash_unconstrained_v1"
  | "classic_cash_qb_pair_v1"
  | "classic_cash_qb_pair_bringback_v1";

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

function App() {
  const [viewMode, setViewMode] = useState<ViewMode>("digital-twin");
  const [season, setSeason] = useState(DEFAULT_SEASON);
  const [week, setWeek] = useState(DEFAULT_WEEK);
  const [slate, setSlate] = useState("THURSDAY_NIGHT");
  const [injuryPath, setInjuryPath] = useState<string>("~/Downloads/Injuries.csv");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadSummaries, setLoadSummaries] = useState<LoadSummary[]>([]);
  const [lastLoadType, setLastLoadType] = useState<string | null>(null);
  const [slateStatus, setSlateStatus] = useState<SlateLoadResponse | null>(null);
  const [optimizerStatus, setOptimizerStatus] = useState<OptimizerResponse | null>(
    null
  );
  const [slateReadiness, setSlateReadiness] = useState<SlateReadinessResponse | null>(null);
  const [dataQualityHistory, setDataQualityHistory] = useState<DataQualityHistoryResponse | null>(null);
  const [dataQualityLoading, setDataQualityLoading] = useState(false);
  const [dataQualityError, setDataQualityError] = useState<string | null>(null);
  const [numLineups, setNumLineups] = useState(1);
  const [maxExposure, setMaxExposure] = useState(100);
  const [contestFormat, setContestFormat] = useState<"classic" | "showdown">("classic");
  const [optimizerObjective, setOptimizerObjective] = useState<"cash" | "gpp">("gpp");
  const [cashStackPolicyId, setCashStackPolicyId] = useState<CashStackPolicyId>(
    "classic_cash_unconstrained_v1"
  );
  const [enforceSingleTE, setEnforceSingleTE] = useState(true);
  const [avoidDstOpponents, setAvoidDstOpponents] = useState(true);
  const [predictionStatus, setPredictionStatus] = useState<{
    message: string;
    rows_written: number;
  } | null>(null);
  const [predictionRows, setPredictionRows] = useState<PredictionRow[]>([]);
  const [simulationStatus, setSimulationStatus] = useState<SimulationResponse | null>(null);
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
  const [agentStatus, setAgentStatus] = useState<AgentRunResponse | null>(null);
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
    // Keep the UI pinned to the agreed replay workbench context unless the user changes it.
    setSeason(DEFAULT_SEASON);
    setWeek(DEFAULT_WEEK);
    setFutureWeek(DEFAULT_WEEK);
  }, []);

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
    setOptimizerStatus(null); // clear prior results while new job runs
    setError(null);
    setPendingAction("Checking slate readiness...");
    try {
      const readiness = await fetchSlateReadiness({ season, week, slate, record: true });
      setSlateReadiness(readiness);
      const gateKey = optimizerReadinessGateKey(contestFormat, optimizerObjective);
      if (readiness.gates[gateKey].status === "fail") {
        throw new Error(`Optimizer blocked by slate readiness: ${readinessFailureMessage(readiness, gateKey)}`);
      }
      setPendingAction("Running optimizer...");
      const response = await runOptimizer({
        season,
        week,
        slate,
        strategy: "gpp",
        contest_format: contestFormat,
        objective: optimizerObjective,
        params: {
          num_lineups: numLineups,
          max_exposure: maxExposure / 100,
          enforce_single_te: enforceSingleTE,
          avoid_dst_opponents: avoidDstOpponents,
          ...(contestFormat === "classic" && optimizerObjective === "cash"
            ? { stack_policy_id: cashStackPolicyId }
            : {}),
          exclude_players: excludePlayers
            .split(",")
            .map((s) => s.trim())
            .filter((s) => s.length > 0),
        },
      });
      setOptimizerStatus(response);
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
      const projections = await fetchLatestPredictions({ season, week, limit: 1000, slate });
      setPredictionRows(projections.rows);
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
      });
      setSimulationStatus(response);
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
      const resp = await runAgent(season, week, slate);
      setAgentStatus(resp);
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
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} pendingAction={pendingAction} onNavigate={setViewMode}>
        <DigitalTwin
          season={season}
          week={week}
          slate={slate}
          contestFormat={contestFormat}
          optimizerObjective={optimizerObjective}
          optimizerStatus={optimizerStatus}
          onNavigate={setViewMode}
        />
      </AppShell>
    );
  }

  if (viewMode === "preview") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} pendingAction={pendingAction} onNavigate={setViewMode}>
        <DesignPreview onBack={() => setViewMode("war-room")} />
      </AppShell>
    );
  }

  if (viewMode === "news-brief") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} pendingAction={pendingAction} onNavigate={setViewMode}>
        <DailyNewsBrief onBack={() => setViewMode("war-room")} />
      </AppShell>
    );
  }

  if (viewMode === "contest-workflow") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} pendingAction={pendingAction} onNavigate={setViewMode}>
        <ContestWorkflow
          season={season}
          week={week}
          slate={slate}
          slateOptions={SLATE_OPTIONS}
          optimizerRunId={optimizerStatus?.job_id}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          onSlateChange={setSlate}
          onOpenModelWorkbench={() => setViewMode("model-workbench")}
          onOpenOperations={() => setViewMode("workspace")}
        />
      </AppShell>
    );
  }

  if (viewMode === "model-workbench") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} pendingAction={pendingAction} onNavigate={setViewMode}>
        <ModelWorkbench
          season={season}
          week={week}
          slate={slate}
          slateOptions={SLATE_OPTIONS}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          onSlateChange={setSlate}
          onOpenWarRoom={() => setViewMode("war-room")}
          onOpenOperations={() => setViewMode("workspace")}
          onOpenContestWorkflow={() => setViewMode("contest-workflow")}
        />
      </AppShell>
    );
  }

  if (viewMode === "war-room") {
    return (
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} pendingAction={pendingAction} onNavigate={setViewMode}>
        <WarRoom
          season={season}
          week={week}
          slate={slate}
          slateOptions={SLATE_OPTIONS}
          pendingAction={pendingAction}
          optimizerStatus={optimizerStatus}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          onSlateChange={setSlate}
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
      <AppShell activeView={viewMode} season={season} week={week} slate={slate} pendingAction={pendingAction} onNavigate={setViewMode}>
        <ResearchWorkspace />
      </AppShell>
    );
  }

  return (
    <AppShell activeView={viewMode} season={season} week={week} slate={slate} pendingAction={pendingAction} onNavigate={setViewMode}>
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
                onChange={(event) => setSlate(event.target.value)}
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
              <label>
                Lineups
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={numLineups}
                  onChange={(event) => setNumLineups(Number(event.target.value))}
                />
              </label>
              <label>
                Max Exposure (%)
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={maxExposure}
                  onChange={(event) => setMaxExposure(Number(event.target.value))}
                />
              </label>
              <label>
                Format
                <select
                  value={contestFormat}
                  onChange={(event) => setContestFormat(event.target.value as "classic" | "showdown")}
                >
                  <option value="classic">Classic</option>
                  <option value="showdown">Showdown</option>
                </select>
              </label>
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
            </div>
            {contestFormat === "classic" && optimizerObjective === "cash" && (
              <div className="form-row">
                <label>
                  Cash Stacking Policy
                  <select
                    value={cashStackPolicyId}
                    onChange={(event) =>
                      setCashStackPolicyId(event.target.value as CashStackPolicyId)
                    }
                  >
                    <option value="classic_cash_unconstrained_v1">
                      Unconstrained replay baseline
                    </option>
                    <option value="classic_cash_qb_pair_v1">
                      QB + pass catcher
                    </option>
                    <option value="classic_cash_qb_pair_bringback_v1">
                      QB + pass catcher + bring-back
                    </option>
                  </select>
                  <small>
                    Candidate rules remain unvalidated until DT-402 walk-forward replay is complete.
                  </small>
                </label>
              </div>
            )}
            {slateReadiness && (() => {
              const gateKey = optimizerReadinessGateKey(contestFormat, optimizerObjective);
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
                    <span>Slate preflight · {contestFormat} {optimizerObjective}</span>
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
            <label className="text-label">
              Exclude players (comma-separated names)
              <input
                type="text"
                value={excludePlayers}
                onChange={(event) => setExcludePlayers(event.target.value)}
                placeholder="e.g. George Kittle, Skyy Moore"
              />
            </label>
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
              <h3>Optimizer</h3>
              <p>Job ID: {optimizerStatus.job_id}</p>
              <p>Status: {optimizerStatus.status}</p>
              <p>{optimizerStatus.message}</p>
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
                          <span>Proj: {totalProj.toFixed(2)}</span>
                        </div>
                        <table className="compact-table">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>Pos</th>
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
                                  <td>{player.roster_position || player.position}</td>
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
          {loadSummaries.length === 0 && !slateStatus && !optimizerStatus && !error && (
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
