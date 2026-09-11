import { useEffect, useMemo, useRef, useState } from "react";
import {
  createPregameContext,
  fetchLatestPredictions,
  fetchModelPipelineStatus,
  fetchPregameContext,
  fetchSymbolicBacktest,
  fetchSymbolicRules,
  fetchValidation,
  queueAgent,
  queueFeatureMatrix,
  queuePredictions,
  type ModelPipelineSummary,
  type PipelineOperationSummary,
  type PregameContextCurrentResponse,
  type PregamePlayerContextInput,
  type PredictionResponse,
  type PredictionRow,
  type SymbolicBacktestResponse,
  type SymbolicRule,
  type ValidationResponse,
} from "./api";
import "./ModelWorkbench.css";

type ModelWorkbenchProps = {
  season: number;
  week: number;
  slate: string;
  slateOptions: string[];
  projectionRunId?: string;
  onProjectionRunChange: (runId: string | null) => void;
  onSeasonChange: (season: number) => void;
  onWeekChange: (week: number) => void;
  onSlateChange: (slate: string) => void;
  onOpenWarRoom: () => void;
  onOpenOperations: () => void;
  onOpenContestWorkflow: () => void;
};

type WorkbenchStatus = "idle" | "loading" | "ready" | "error";

type PregameContextDraft = {
  availability: string;
  start: string;
  carry: string;
  target: string;
  role: string;
  injury: string;
};

const EMPTY_CONTEXT_DRAFT: PregameContextDraft = {
  availability: "",
  start: "",
  carry: "",
  target: "",
  role: "",
  injury: "",
};

function percentageDraft(value: number | null | undefined) {
  return value === null || value === undefined ? "" : String(Number(value) * 100);
}

type CoverageState = {
  table: string;
  label: string;
  status: WorkbenchStatus;
  response: ValidationResponse | null;
  error: string | null;
};

const COVERAGE_DATASETS = [
  { table: "fact_player_game_actual", label: "Historical actuals", scope: "history" },
  { table: "curated_salary", label: "Slate salaries", scope: "slate" },
  { table: "player_game_feature_matrix", label: "Slate features", scope: "slate" },
  { table: "player_projection", label: "Slate projections", scope: "slate" },
] as const;

function initialCoverage(): CoverageState[] {
  return COVERAGE_DATASETS.map(({ table, label }) => ({
    table,
    label,
    status: "idle",
    response: null,
    error: null,
  }));
}

function formatSlateName(value: string) {
  return value.replaceAll("_", " ");
}

function projectionValue(row: PredictionRow) {
  return row.adj_mean_final || row.adj_mean || row.predicted_mean || 0;
}

function formatNumber(value: number | null | undefined, digits = 1) {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : "0.0";
}

function coverageSummary(state: CoverageState) {
  if (state.status === "loading") {
    return { label: "Checking", detail: "Coverage request in flight", tone: "neutral" };
  }
  if (state.status === "error") {
    return { label: "Unavailable", detail: state.error ?? "Could not load coverage", tone: "red" };
  }
  if (!state.response) {
    return { label: "Not checked", detail: "Run coverage checks", tone: "neutral" };
  }

  const rows = state.response.results ?? [];
  const current = rows.at(-1);
  const missing = rows.filter((row) => row.status === "missing").length;
  const partial = rows.filter((row) => row.status === "partial").length;
  const ok = rows.filter((row) => row.status === "ok").length;
  const totalRows = rows.reduce((sum, row) => sum + Number(row.rows || 0), 0);

  if (missing > 0) {
    return {
      label: "Missing",
      detail: `${missing} missing check${missing === 1 ? "" : "s"} across ${rows.length || 0} windows`,
      tone: "red",
    };
  }
  if (partial > 0) {
    return {
      label: "Partial",
      detail: `${partial} partial check${partial === 1 ? "" : "s"}; ${totalRows.toLocaleString()} rows found`,
      tone: "amber",
    };
  }
  if (ok > 0) {
    return {
      label: "Ready",
      detail: current
        ? `${totalRows.toLocaleString()} rows; latest check week ${current.week ?? "all"}`
        : `${totalRows.toLocaleString()} rows found`,
      tone: "green",
    };
  }
  return { label: "Empty", detail: "No validation rows returned", tone: "amber" };
}

function toError(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function formatStatus(value: string) {
  return value === "not_run"
    ? "Not run"
    : value.charAt(0).toUpperCase() + value.slice(1);
}

function formatStatusTime(value: string | null | undefined) {
  if (!value) return null;
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(timestamp);
}

function shortRunId(value: string) {
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function PipelineResultCard({
  label,
  summary,
  loadState,
  loadError,
  selectedProjection,
  onOpenOperations,
}: {
  label: string;
  summary: PipelineOperationSummary | null;
  loadState: "loading" | "ready" | "error";
  loadError: string | null;
  selectedProjection?: ModelPipelineSummary["selected_projection"];
  onOpenOperations: () => void;
}) {
  if (loadState === "loading") {
    return (
      <article className="pipeline-result-card status-loading">
        <span>{label}</span>
        <strong>Loading</strong>
        <small>Loading persisted status…</small>
      </article>
    );
  }
  if (loadState === "error" || !summary) {
    return (
      <article className="pipeline-result-card status-unavailable">
        <span>{label}</span>
        <strong>Status unavailable</strong>
        <small>{loadError ?? "The stored pipeline history could not be loaded."}</small>
      </article>
    );
  }

  const attempt = summary.latest_attempt;
  const reachedAt = formatStatusTime(summary.status_at);
  const active = summary.status === "queued" || summary.status === "running";
  const failed = summary.status === "failed";
  const interrupted = summary.status === "interrupted";
  const latestMessage = attempt?.error_message || attempt?.message;
  const rows = attempt?.rows_written;
  const lastSuccess = summary.last_success;
  const showLastSuccess = Boolean(
    lastSuccess && (summary.status !== "completed" || lastSuccess.run_id !== attempt?.run_id)
  );

  return (
    <article className={`pipeline-result-card status-${summary.status}`}>
      <span>{label}</span>
      <strong>{formatStatus(summary.status)}</strong>
      {reachedAt && <time dateTime={summary.status_at ?? undefined}>{reachedAt}</time>}
      {summary.status === "not_run" ? (
        <small>No stored attempt exists for this season, week, and slate.</small>
      ) : (
        <small>
          {failed ? "Latest attempt failed. " : ""}
          {interrupted ? "Latest attempt interrupted. " : ""}
          {active && attempt ? `${Math.round(attempt.progress_percent)}% · ` : ""}
          {rows !== null && rows !== undefined && summary.status === "completed"
            ? `${rows.toLocaleString()} rows · `
            : ""}
          {latestMessage}
        </small>
      )}
      {attempt?.scope === "season" && (
        <small className="pipeline-result-meta">
          Season-wide build
          {attempt.slice_outcome
            ? ` · selected slate ${String(attempt.slice_outcome.status ?? "recorded")}`
            : " · selected-slate outcome pending"}
        </small>
      )}
      {showLastSuccess && lastSuccess && (
        <small className="pipeline-last-success">
          Last usable result: {lastSuccess.rows_written?.toLocaleString() ?? "stored"} rows
          {formatStatusTime(lastSuccess.status_at)
            ? ` · ${formatStatusTime(lastSuccess.status_at)}`
            : ""}
        </small>
      )}
      {selectedProjection && (
        <small className="pipeline-selection" title={selectedProjection.run_id}>
          Selected run {shortRunId(selectedProjection.run_id)} · {formatStatus(selectedProjection.status)}
          {!selectedProjection.is_latest_success && selectedProjection.status !== "not_run"
            ? selectedProjection.status === "queued"
              || selectedProjection.status === "running"
              || selectedProjection.status === "interrupted"
              ? " · still in progress"
              : " · not the latest usable run"
            : ""}
          {selectedProjection.status === "not_run" ? " · unavailable for this slate" : ""}
        </small>
      )}
      {attempt?.job_id && (
        <button type="button" className="pipeline-run-link" onClick={onOpenOperations}>
          View run details
        </button>
      )}
    </article>
  );
}

type CalibrationCoverageRow = {
  position: string;
  samples: number;
  intervalCoverage: number;
  mae: number;
};

function calibrationReport(result: PredictionResponse | null) {
  const metrics = result?.calibration_metrics;
  const empty = { method: "", walkForwardRows: 0, rows: [] as CalibrationCoverageRow[], roleRows: [] as CalibrationCoverageRow[], promotionStatus: "" };
  if (!metrics || typeof metrics !== "object") {
    return empty;
  }
  const method = typeof metrics.method === "string" ? metrics.method : "";
  const walkForwardRows = typeof metrics.walk_forward_rows === "number" ? metrics.walk_forward_rows : 0;
  const readCoverage = (coverage: unknown) => {
    if (!coverage || typeof coverage !== "object" || Array.isArray(coverage)) return [];
    return Object.entries(coverage).flatMap(([position, value]) => {
      if (!value || typeof value !== "object" || Array.isArray(value)) return [];
      const row = value as Record<string, unknown>;
      return [{
        position,
        samples: Number(row.samples ?? 0),
        intervalCoverage: Number(row.p10_p90_coverage ?? 0),
        mae: Number(row.mae ?? 0),
      }];
    }).sort((left, right) => right.samples - left.samples);
  };
  const promotionGate = metrics.promotion_gate;
  const promotionStatus = promotionGate && typeof promotionGate === "object" && !Array.isArray(promotionGate)
    ? String((promotionGate as Record<string, unknown>).status ?? "")
    : "";
  return {
    method,
    walkForwardRows,
    rows: readCoverage(metrics.coverage_by_position),
    roleRows: readCoverage(metrics.coverage_by_role),
    promotionStatus,
  };
}

export function ModelWorkbench({
  season,
  week,
  slate,
  slateOptions,
  projectionRunId,
  onProjectionRunChange,
  onSeasonChange,
  onWeekChange,
  onSlateChange,
  onOpenWarRoom,
  onOpenOperations,
  onOpenContestWorkflow,
}: ModelWorkbenchProps) {
  const [coverage, setCoverage] = useState<CoverageState[]>(initialCoverage);
  const [coverageRunStatus, setCoverageRunStatus] = useState<"idle" | "loading" | "complete">("idle");
  const [projections, setProjections] = useState<PredictionRow[]>([]);
  const [projectionStatus, setProjectionStatus] = useState<WorkbenchStatus>("idle");
  const [projectionError, setProjectionError] = useState<string | null>(null);
  const [pipelineSummary, setPipelineSummary] = useState<ModelPipelineSummary | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<"loading" | "ready" | "error">("loading");
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<SymbolicBacktestResponse | null>(null);
  const [rules, setRules] = useState<SymbolicRule[]>([]);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pregameContext, setPregameContext] = useState<PregameContextCurrentResponse | null>(null);
  const [pregameStatus, setPregameStatus] = useState<WorkbenchStatus>("loading");
  const [pregameError, setPregameError] = useState<string | null>(null);
  const [pregameDrafts, setPregameDrafts] = useState<Record<string, PregameContextDraft>>({});
  const [pregameSource, setPregameSource] = useState("manual_ui");
  const [pregameNotes, setPregameNotes] = useState("");
  const [pregameNotice, setPregameNotice] = useState<string | null>(null);
  const pipelineRequestRef = useRef("");
  const artifactRequestRef = useRef("");
  const pipelineSummaryRef = useRef<ModelPipelineSummary | null>(null);

  const contextPlayers = useMemo(
    () => (pregameContext?.player_pool ?? [])
      .filter((row) => ["QB", "RB", "WR", "TE"].includes(row.position))
      .sort((left, right) => (
        left.team.localeCompare(right.team)
        || left.position.localeCompare(right.position)
        || left.player_display_name.localeCompare(right.player_display_name)
      )),
    [pregameContext],
  );

  const topProjections = useMemo(
    () => [...projections].sort((left, right) => projectionValue(right) - projectionValue(left)).slice(0, 12),
    [projections]
  );

  const projectionMetrics = useMemo(() => {
    if (projections.length === 0) {
      return { rows: 0, avgMean: 0, avgP90: 0, highCeiling: 0 };
    }
    const avgMean =
      projections.reduce((sum, row) => sum + projectionValue(row), 0) / projections.length;
    const avgP90 =
      projections.reduce((sum, row) => sum + Number(row.predicted_p90 || 0), 0) / projections.length;
    const highCeiling = projections.filter((row) => Number(row.predicted_p90 || 0) >= 20).length;
    return { rows: projections.length, avgMean, avgP90, highCeiling };
  }, [projections]);

  const activeRules = rules.filter((rule) => rule.enabled).length;
  const backtestDelta = backtest?.overall?.mae_delta ?? null;
  const predictionRunResult = (
    pipelineSummary?.projections.last_success?.result ?? null
  ) as PredictionResponse | null;
  const calibration = useMemo(() => calibrationReport(predictionRunResult), [predictionRunResult]);
  const coverageReady = coverage.filter((item) => coverageSummary(item).tone === "green").length;
  const coverageNeedsAttention = coverage.filter((item) => {
    const summary = coverageSummary(item);
    return item.status !== "idle" && item.status !== "loading" && summary.tone !== "green";
  }).length;

  const refreshCoverage = async () => {
    setCoverageRunStatus("loading");
    setCoverage((current) =>
      current.map((item) => ({ ...item, status: "loading", error: null }))
    );
    const results = await Promise.allSettled(
      COVERAGE_DATASETS.map((dataset) => fetchValidation(
        dataset.table,
        dataset.scope === "slate" ? { season, week, slate } : undefined,
      ))
    );
    setCoverage(
      COVERAGE_DATASETS.map(({ table, label }, index) => {
        const result = results[index];
        if (result.status === "fulfilled") {
          return { table, label, status: "ready", response: result.value, error: null };
        }
        return { table, label, status: "error", response: null, error: toError(result.reason) };
      })
    );
    setCoverageRunStatus("complete");
  };

  const refreshModelArtifacts = async (
    requestedRunId = projectionRunId,
    showLoading = true,
  ) => {
    if (showLoading) {
      setProjectionStatus("loading");
      setProjectionError(null);
    }
    const requestKey = `${season}:${week}:${slate}:${requestedRunId ?? ""}`;
    artifactRequestRef.current = requestKey;
    const [predictionsResult, rulesResult] = await Promise.allSettled([
      fetchLatestPredictions({
        season,
        week,
        slate,
        limit: 1000,
        projectionRunId: requestedRunId,
      }),
      fetchSymbolicRules({ include_disabled: true }),
    ]);
    if (artifactRequestRef.current !== requestKey) return;

    if (predictionsResult.status === "fulfilled") {
      setProjections(predictionsResult.value.rows);
      if (!requestedRunId && predictionsResult.value.projection_run_id) {
        onProjectionRunChange(predictionsResult.value.projection_run_id);
      }
      setProjectionStatus("ready");
    } else {
      setProjections([]);
      setProjectionError(toError(predictionsResult.reason));
      setProjectionStatus("error");
    }
    if (rulesResult.status === "fulfilled") {
      setRules(rulesResult.value.rows);
    }
  };

  const refreshPregameContext = async (showLoading = true) => {
    if (showLoading) setPregameStatus("loading");
    setPregameError(null);
    try {
      const response = await fetchPregameContext({ season, week, slate });
      setPregameContext(response);
      const drafts = Object.fromEntries(response.rows.map((row) => [
        row.player_master_id,
        {
          availability: percentageDraft(row.availability_probability),
          start: percentageDraft(row.start_probability),
          carry: percentageDraft(row.carry_share),
          target: percentageDraft(row.target_share),
          role: row.role_label ?? "",
          injury: row.injury_status ?? "",
        },
      ]));
      setPregameDrafts(drafts);
      setPregameStatus("ready");
    } catch (error) {
      setPregameContext(null);
      setPregameError(toError(error));
      setPregameStatus("error");
    }
  };

  const refreshPipelineStatus = async (
    requestedRunId = projectionRunId,
    showLoading = true,
  ) => {
    if (showLoading) setPipelineStatus("loading");
    setPipelineError(null);
    const requestKey = `${season}:${week}:${slate}:${requestedRunId ?? ""}`;
    pipelineRequestRef.current = requestKey;
    try {
      const response = await fetchModelPipelineStatus({
        season,
        week,
        slate,
        selectedProjectionRunId: requestedRunId,
      });
      if (pipelineRequestRef.current !== requestKey) return null;
      const previous = pipelineSummaryRef.current;
      pipelineSummaryRef.current = response;
      setPipelineSummary(response);
      setPipelineStatus("ready");
      const operationCompleted = (["features", "projections", "symbolic"] as const).some(
        (key) => {
          const before = previous?.[key].status;
          const after = response[key].status;
          return (
            (before === "queued" || before === "running" || before === "interrupted")
            && (after === "completed" || after === "failed")
          );
        },
      );
      return { response, operationCompleted };
    } catch (error) {
      if (pipelineRequestRef.current !== requestKey) return null;
      setPipelineError(toError(error));
      setPipelineStatus("error");
      return null;
    }
  };

  const refreshModelState = async (requestedRunId = projectionRunId) => {
    await Promise.all([
      refreshModelArtifacts(requestedRunId),
      refreshPipelineStatus(requestedRunId),
      refreshPregameContext(),
    ]);
  };

  useEffect(() => {
    setCoverage(initialCoverage());
    setCoverageRunStatus("idle");
    setProjections([]);
    setProjectionStatus("loading");
    setProjectionError(null);
    setPipelineSummary(null);
    pipelineSummaryRef.current = null;
    setPipelineStatus("loading");
    setPipelineError(null);
    setBacktest(null);
    setActionStatus(null);
    setActionError(null);
    setPregameContext(null);
    setPregameStatus("loading");
    setPregameError(null);
    setPregameDrafts({});
    setPregameNotice(null);
    void refreshModelState(projectionRunId);
    // Context changes are the restoration boundary; projection selection is passed explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, slate, week]);

  useEffect(() => {
    if (!pipelineSummary?.has_active_jobs) return undefined;
    const timer = window.setInterval(() => {
      void refreshPipelineStatus(projectionRunId, false).then((result) => {
        if (result?.operationCompleted) {
          void refreshModelArtifacts(projectionRunId, false);
        }
      });
    }, 2_000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineSummary?.has_active_jobs, projectionRunId, season, slate, week]);

  useEffect(() => {
    if (
      !projectionRunId
      || pipelineSummary?.selected_projection?.run_id === projectionRunId
    ) return;
    void refreshPipelineStatus(projectionRunId, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectionRunId]);

  const runAction = async (label: string, action: () => Promise<void>) => {
    setActionStatus(label);
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(toError(error));
    } finally {
      setActionStatus(null);
    }
  };

  const handleBuildFeatures = (scope: "current" | "all") =>
    runAction(scope === "current" ? "Queueing current-slate features" : "Queueing season features", async () => {
      await queueFeatureMatrix({
        season,
        weeks: scope === "current" ? [week] : undefined,
        slate: scope === "current" ? slate : undefined,
      });
      await refreshModelState();
    });

  const handleRunPredictions = () =>
    runAction("Queueing projection model", async () => {
      const queued = await queuePredictions({ season, week, slate });
      const queuedRunId = queued.job.run_id ?? undefined;
      if (queuedRunId) onProjectionRunChange(queuedRunId);
      await refreshModelState(queuedRunId);
    });

  const handleRunAgent = () =>
    runAction("Queueing symbolic adjustments", async () => {
      await queueAgent(season, week, slate, projectionRunId);
      await refreshModelState();
    });

  const handleBacktest = () =>
    runAction("Backtesting symbolic rules", async () => {
      const result = await fetchSymbolicBacktest({ season, week, slate });
      setBacktest(result);
    });

  const updatePregameDraft = (
    playerId: string,
    field: keyof PregameContextDraft,
    value: string,
  ) => {
    setPregameDrafts((current) => ({
      ...current,
      [playerId]: {
        ...(current[playerId] ?? EMPTY_CONTEXT_DRAFT),
        [field]: value,
      },
    }));
    setPregameNotice(null);
  };

  const handleSavePregameContext = () =>
    runAction("Saving pregame context", async () => {
      const probability = (value: string, label: string) => {
        if (!value.trim()) return undefined;
        const parsed = Number(value);
        if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) {
          throw new Error(`${label} must be between 0 and 100.`);
        }
        return parsed / 100;
      };
      const players: PregamePlayerContextInput[] = contextPlayers.flatMap((player) => {
        const draft = pregameDrafts[player.player_id];
        if (!draft) return [];
        const availability = probability(draft.availability, `${player.player_display_name} availability`);
        const start = probability(draft.start, `${player.player_display_name} start probability`);
        const carry = probability(draft.carry, `${player.player_display_name} carry share`);
        const target = probability(draft.target, `${player.player_display_name} target share`);
        const role = draft.role.trim() as PregamePlayerContextInput["role_label"];
        const injury = draft.injury.trim();
        if (
          availability === undefined
          && start === undefined
          && carry === undefined
          && target === undefined
          && !role
          && !injury
        ) return [];
        return [{
          player_id: player.player_id,
          team: player.team,
          position: player.position,
          availability_probability: availability,
          start_probability: start,
          carry_share: carry,
          target_share: target,
          role_label: role || undefined,
          injury_status: injury || undefined,
          evidence: {
            entered_via: "model_workbench",
            projection_run_id: projectionRunId ?? null,
          },
        }];
      });
      if (players.length === 0) {
        throw new Error("Enter at least one availability, starter, role, carry, target, or injury value.");
      }
      const result = await createPregameContext({
        season,
        week,
        slate,
        source: pregameSource,
        observed_at: new Date().toISOString(),
        notes: pregameNotes || undefined,
        players,
      });
      await refreshPregameContext(false);
      setPregameNotice(
        `Saved immutable context run ${shortRunId(result.context_run_id)}. Run projections to use it.`,
      );
    });

  return (
    <main className="model-workbench">
      <header className="model-command">
        <div className="model-brand">
          <span className="model-mark">MW</span>
          <div>
            <p>Football Opt</p>
            <h1>Model Workbench</h1>
          </div>
        </div>

        <div className="model-controls" aria-label="Model context controls">
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

        <div className="model-actions">
          <span className="model-pending">{actionStatus ?? ""}</span>
          <button type="button" onClick={onOpenContestWorkflow}>
            Contest Delivery
          </button>
          <button type="button" onClick={onOpenWarRoom}>
            War Room
          </button>
          <button type="button" onClick={onOpenOperations}>
            Operations
          </button>
        </div>
      </header>

      {actionError && <div className="model-banner error">{actionError}</div>}
      {projectionError && <div className="model-banner error">{projectionError}</div>}
      {pipelineError && <div className="model-banner error">Pipeline status: {pipelineError}</div>}

      <section className="model-status-grid" aria-label="Model status">
        <article>
          <span>Projection Rows</span>
          <strong>{projectionMetrics.rows.toLocaleString()}</strong>
          <small>
            {projectionStatus === "loading"
              ? "Loading latest predictions"
              : `Avg mean ${formatNumber(projectionMetrics.avgMean)} / avg p90 ${formatNumber(projectionMetrics.avgP90)}`}
          </small>
        </article>
        <article>
          <span>High Ceiling Pool</span>
          <strong>{projectionMetrics.highCeiling}</strong>
          <small>Players at 20+ p90 in the active context</small>
        </article>
        <article>
          <span>Symbolic Rules</span>
          <strong>{activeRules} / {rules.length}</strong>
          <small>Enabled rules over total loaded rules</small>
        </article>
        <article>
          <span>Rule Backtest</span>
          <strong>{backtestDelta === null ? "Not run" : formatNumber(backtestDelta, 2)}</strong>
          <small>{backtest ? "MAE delta, positive means improved" : "Run backtest after projections and actuals exist"}</small>
        </article>
      </section>

      <section className="model-layout">
        <aside className="model-panel model-flow">
          <div className="model-panel-title">
            <span>Runbook</span>
            <h2>Model workflow</h2>
          </div>
          <div className="model-step-list">
            <article>
              <b>1</b>
              <div>
                <strong>Check coverage</strong>
                <p>Verify curated rows, predictive features, and stored projections before changing logic.</p>
              </div>
            </article>
            <article>
              <b>2</b>
              <div>
                <strong>Build features</strong>
                <p>Regenerate current-week or full-season features after ingest or identity changes.</p>
              </div>
            </article>
            <article>
              <b>3</b>
              <div>
                <strong>Run projections</strong>
                <p>Create the baseline player distribution used by rules and optimizer decisions.</p>
              </div>
            </article>
            <article>
              <b>4</b>
              <div>
                <strong>Evaluate rules</strong>
                <p>Run symbolic adjustments and backtest them against actuals before trusting changes.</p>
              </div>
            </article>
          </div>
        </aside>

        <section className="model-panel model-main">
          <div className="model-panel-title">
            <span>Controls</span>
            <h2>Projection pipeline</h2>
          </div>
          <div className="model-pipeline" aria-label="Projection pipeline actions">
            <article className="pipeline-stage">
              <div className="pipeline-stage-head">
                <b>01</b>
                <div><strong>Inspect</strong><small>Confirm the slate is ready</small></div>
              </div>
              <div className="pipeline-stage-actions">
                <button type="button" onClick={() => refreshModelState()}>
                  <span>Refresh model state</span><i aria-hidden="true">↗</i>
                </button>
                <button
                  type="button"
                  onClick={refreshCoverage}
                  disabled={coverageRunStatus === "loading"}
                >
                  <span>{coverageRunStatus === "loading" ? "Checking coverage…" : "Check data coverage"}</span>
                  <i aria-hidden="true">↗</i>
                </button>
              </div>
            </article>

            <article className="pipeline-stage">
              <div className="pipeline-stage-head">
                <b>02</b>
                <div><strong>Build</strong><small>Refresh predictive inputs</small></div>
              </div>
              <div className="pipeline-stage-actions">
                <button type="button" onClick={() => handleBuildFeatures("current")}>
                  <span>Current slate features</span><i aria-hidden="true">↗</i>
                </button>
                <button type="button" onClick={() => handleBuildFeatures("all")}>
                  <span>Full-season features</span><i aria-hidden="true">↗</i>
                </button>
              </div>
            </article>

            <article className="pipeline-stage pipeline-stage-primary">
              <div className="pipeline-stage-head">
                <b>03</b>
                <div><strong>Project</strong><small>Generate player outcomes</small></div>
              </div>
              <div className="pipeline-stage-actions">
                <button type="button" onClick={handleRunPredictions}>
                  <span>Run projections</span><i aria-hidden="true">→</i>
                </button>
              </div>
            </article>

            <article className="pipeline-stage">
              <div className="pipeline-stage-head">
                <b>04</b>
                <div><strong>Evaluate</strong><small>Adjust and test your rules</small></div>
              </div>
              <div className="pipeline-stage-actions">
                <button type="button" onClick={handleRunAgent}>
                  <span>Run symbolic layer</span><i aria-hidden="true">↗</i>
                </button>
                <button type="button" onClick={handleBacktest}>
                  <span>Backtest rules</span><i aria-hidden="true">↗</i>
                </button>
              </div>
            </article>
          </div>

          {coverageRunStatus !== "idle" && (
            <div
              className={`coverage-feedback ${coverageRunStatus === "complete" && coverageNeedsAttention > 0 ? "attention" : ""}`}
              role="status"
              aria-live="polite"
            >
              {coverageRunStatus === "loading"
                ? `Checking historical inputs and ${formatSlateName(slate)} slate data…`
                : `Coverage check complete: ${coverageReady} ready, ${coverageNeedsAttention} need attention. Review the cards below.`}
            </div>
          )}

          <div className="model-result-grid">
            <PipelineResultCard
              label="Features"
              summary={pipelineSummary?.features ?? null}
              loadState={pipelineStatus}
              loadError={pipelineError}
              onOpenOperations={onOpenOperations}
            />
            <PipelineResultCard
              label="Projections"
              summary={pipelineSummary?.projections ?? null}
              loadState={pipelineStatus}
              loadError={pipelineError}
              selectedProjection={pipelineSummary?.selected_projection}
              onOpenOperations={onOpenOperations}
            />
            <PipelineResultCard
              label="Symbolic Run"
              summary={pipelineSummary?.symbolic ?? null}
              loadState={pipelineStatus}
              loadError={pipelineError}
              onOpenOperations={onOpenOperations}
            />
          </div>

          <details className="pregame-context-editor">
            <summary>
              <span>
                Pregame role &amp; availability
                <small>
                  {pregameStatus === "loading"
                    ? "Loading persisted context…"
                    : pregameStatus === "error"
                      ? "Status unavailable"
                      : `${pregameContext?.rows.length ?? 0} saved records · ${contextPlayers.length} editable players`}
                </small>
              </span>
              <b>{pregameContext?.rows.length ? "Configured" : "Needs evidence"}</b>
            </summary>
            {pregameError && <div className="model-banner error">Pregame context: {pregameError}</div>}
            <p className="pregame-context-help">
              Enter sourced pregame facts as percentages. Carry share is the team RB workload;
              target share is the team RB/WR/TE workload. Blank values are not inferred as facts.
              Saving creates an immutable evidence run; projections do not change until you run them again.
            </p>
            <div className="pregame-context-meta">
              <label>
                Evidence source
                <input
                  value={pregameSource}
                  onChange={(event) => setPregameSource(event.target.value)}
                  placeholder="official_depth_chart"
                />
              </label>
              <label>
                Notes
                <input
                  value={pregameNotes}
                  onChange={(event) => setPregameNotes(event.target.value)}
                  placeholder="What changed and why"
                />
              </label>
              <button type="button" onClick={handleSavePregameContext}>
                Save context
              </button>
            </div>
            {pregameNotice && <div className="pregame-context-notice" role="status">{pregameNotice}</div>}
            <div className="model-table-wrap pregame-context-table">
              <table>
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Pos</th>
                    <th>Avail %</th>
                    <th>Start %</th>
                    <th>Carry %</th>
                    <th>Target %</th>
                    <th>Role</th>
                    <th>Injury/status</th>
                  </tr>
                </thead>
                <tbody>
                  {contextPlayers.map((player) => {
                    const draft = pregameDrafts[player.player_id] ?? EMPTY_CONTEXT_DRAFT;
                    const percentInput = (
                      field: "availability" | "start" | "carry" | "target",
                      disabled = false,
                    ) => (
                      <input
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        value={draft[field]}
                        disabled={disabled}
                        onChange={(event) => updatePregameDraft(player.player_id, field, event.target.value)}
                        aria-label={`${player.player_display_name} ${field} percent`}
                      />
                    );
                    return (
                      <tr key={player.player_id}>
                        <td><strong>{player.player_display_name}</strong><small>{player.team}</small></td>
                        <td>{player.position}</td>
                        <td>{percentInput("availability")}</td>
                        <td>{percentInput("start", player.position !== "QB")}</td>
                        <td>{percentInput("carry", player.position !== "RB")}</td>
                        <td>{percentInput("target", !["RB", "WR", "TE"].includes(player.position))}</td>
                        <td>
                          <select
                            value={draft.role}
                            onChange={(event) => updatePregameDraft(player.player_id, "role", event.target.value)}
                            aria-label={`${player.player_display_name} role`}
                          >
                            <option value="">—</option>
                            {(["STARTER", "BACKUP", "LEAD", "COMMITTEE", "PRIMARY", "SECONDARY", "ROTATION"] as const).map((role) => (
                              <option key={role} value={role}>{role}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            value={draft.injury}
                            onChange={(event) => updatePregameDraft(player.player_id, "injury", event.target.value)}
                            aria-label={`${player.player_display_name} injury status`}
                            placeholder="Healthy / Q / Out"
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </details>

          {calibration.rows.length > 0 && (
            <div className="calibration-diagnostics">
              <div className="calibration-diagnostics-head">
                <div><span>Walk-forward calibration</span><strong>Position interval coverage</strong></div>
                <div className="calibration-run-meta"><em className={calibration.promotionStatus}>{calibration.promotionStatus || "diagnostic"} gate</em><small>{calibration.walkForwardRows.toLocaleString()} out-of-fold rows · {calibration.method.replaceAll("_", " ")}</small></div>
              </div>
              <div className="calibration-position-grid">
                {calibration.rows.map((row) => (
                  <article key={row.position}>
                    <span>{row.position}</span>
                    <strong>{formatNumber(row.intervalCoverage * 100, 1)}%</strong>
                    <small>P10–P90 · {row.samples} samples · {formatNumber(row.mae, 2)} MAE</small>
                  </article>
                ))}
              </div>
              {calibration.roleRows.length > 0 && (
                <div className="calibration-role-grid">
                  {calibration.roleRows.slice(0, 8).map((row) => (
                    <span key={row.position}><b>{row.position.replace("|", " · ")}</b><small>{formatNumber(row.intervalCoverage * 100, 0)}% · n{row.samples}</small></span>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="model-section-head">
            <div>
              <span>Coverage</span>
              <h3>Data readiness</h3>
            </div>
          </div>
          <div className="coverage-grid">
            {coverage.map((item) => {
              const summary = coverageSummary(item);
              return (
                <article key={item.table} className={`coverage-card ${summary.tone}`} title={item.table}>
                  <span>{item.label}</span>
                  <strong>{summary.label}</strong>
                  <small>{summary.detail}</small>
                </article>
              );
            })}
          </div>
        </section>

        <aside className="model-panel model-eval">
          <div className="model-panel-title">
            <span>Evaluation</span>
            <h2>Rule scorecard</h2>
          </div>
          {backtest ? (
            <>
              <div className="score-card">
                <span>Overall</span>
                <strong>{formatNumber(backtest.overall.adjusted_mae, 2)} MAE</strong>
                <small>
                  Base {formatNumber(backtest.overall.base_mae, 2)} / delta{" "}
                  {formatNumber(backtest.overall.mae_delta, 2)} / hit rate{" "}
                  {formatNumber(Number(backtest.overall.hit_rate || 0) * 100, 1)}%
                </small>
              </div>
              <div className="model-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Rule</th>
                      <th>Rows</th>
                      <th>Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtest.by_rule.slice(0, 8).map((row) => (
                      <tr key={row.rule_id}>
                        <td>{row.rule_id}</td>
                        <td>{row.rows}</td>
                        <td>{formatNumber(row.mae_delta, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="model-empty">
              <strong>No backtest loaded.</strong>
              <p>Run the rule backtest after projections and actuals are available for this context.</p>
            </div>
          )}
        </aside>
      </section>

      <section className="model-bottom">
        <div className="model-panel">
          <div className="model-section-head">
            <div>
              <span>Projection Sample</span>
              <h3>Top projected players</h3>
            </div>
            <button type="button" onClick={() => refreshModelState()}>
              Refresh
            </button>
          </div>
          {topProjections.length > 0 ? (
            <div className="model-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Pos</th>
                    <th>Team</th>
                    <th>Mean</th>
                    <th>P10</th>
                    <th>P50</th>
                    <th>P90</th>
                    <th>Calibration</th>
                  </tr>
                </thead>
                <tbody>
                  {topProjections.map((row) => (
                    <tr key={row.player_id}>
                      <td>{row.player_display_name}</td>
                      <td>{row.position}</td>
                      <td>{row.recent_team}</td>
                      <td>{formatNumber(projectionValue(row), 2)}</td>
                      <td>{formatNumber(row.predicted_p10, 2)}</td>
                      <td>{formatNumber(row.predicted_p50, 2)}</td>
                      <td>{formatNumber(row.predicted_p90, 2)}</td>
                      <td>{row.calibration_position || row.position} / {row.calibration_role || "role"} · n{row.calibration_sample_size ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="model-empty">
              <strong>No projections loaded.</strong>
              <p>Build features and run projections for the active season, week, and slate.</p>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
