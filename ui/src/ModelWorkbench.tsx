import { useMemo, useState } from "react";
import {
  buildFeatures,
  fetchLatestPredictions,
  fetchSymbolicBacktest,
  fetchSymbolicRules,
  fetchValidation,
  runAgent,
  runPredictions,
  type AgentRunResponse,
  type BuildFeaturesResponse,
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
  onSeasonChange: (season: number) => void;
  onWeekChange: (week: number) => void;
  onSlateChange: (slate: string) => void;
  onOpenWarRoom: () => void;
  onOpenOperations: () => void;
  onOpenContestWorkflow: () => void;
};

type WorkbenchStatus = "idle" | "loading" | "ready" | "error";

type CoverageState = {
  table: string;
  status: WorkbenchStatus;
  response: ValidationResponse | null;
  error: string | null;
};

const COVERAGE_TABLES = [
  "curated_weekly_stats",
  "curated_salaries",
  "predictive_features",
  "player_expected_points",
];

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
  const current = rows[0];
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
  onSeasonChange,
  onWeekChange,
  onSlateChange,
  onOpenWarRoom,
  onOpenOperations,
  onOpenContestWorkflow,
}: ModelWorkbenchProps) {
  const [coverage, setCoverage] = useState<CoverageState[]>(
    COVERAGE_TABLES.map((table) => ({ table, status: "idle", response: null, error: null }))
  );
  const [projections, setProjections] = useState<PredictionRow[]>([]);
  const [projectionStatus, setProjectionStatus] = useState<WorkbenchStatus>("idle");
  const [projectionError, setProjectionError] = useState<string | null>(null);
  const [featureResult, setFeatureResult] = useState<BuildFeaturesResponse | null>(null);
  const [predictionRunResult, setPredictionRunResult] = useState<PredictionResponse | null>(null);
  const [agentResult, setAgentResult] = useState<AgentRunResponse | null>(null);
  const [backtest, setBacktest] = useState<SymbolicBacktestResponse | null>(null);
  const [rules, setRules] = useState<SymbolicRule[]>([]);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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
  const calibration = useMemo(() => calibrationReport(predictionRunResult), [predictionRunResult]);

  const refreshCoverage = async () => {
    setCoverage((current) =>
      current.map((item) => ({ ...item, status: "loading", error: null }))
    );
    const results = await Promise.allSettled(COVERAGE_TABLES.map((table) => fetchValidation(table)));
    setCoverage(
      COVERAGE_TABLES.map((table, index) => {
        const result = results[index];
        if (result.status === "fulfilled") {
          return { table, status: "ready", response: result.value, error: null };
        }
        return { table, status: "error", response: null, error: toError(result.reason) };
      })
    );
  };

  const refreshModelState = async () => {
    setProjectionStatus("loading");
    setProjectionError(null);
    try {
      const [predictionResponse, rulesResponse] = await Promise.all([
        fetchLatestPredictions({ season, week, slate, limit: 1000 }),
        fetchSymbolicRules({ include_disabled: true }),
      ]);
      setProjections(predictionResponse.rows);
      setRules(rulesResponse.rows);
      setProjectionStatus("ready");
    } catch (error) {
      setProjections([]);
      setProjectionError(toError(error));
      setProjectionStatus("error");
    }
  };

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
    runAction(scope === "current" ? "Building current-week features" : "Building season features", async () => {
      const result = await buildFeatures({
        season,
        weeks: scope === "current" ? [week] : undefined,
      });
      setFeatureResult(result);
      await refreshModelState();
    });

  const handleRunPredictions = () =>
    runAction("Running projection model", async () => {
      const result = await runPredictions({ season, week, slate });
      setPredictionRunResult(result);
      await refreshModelState();
    });

  const handleRunAgent = () =>
    runAction("Running symbolic adjustments", async () => {
      const result = await runAgent(season, week, slate);
      setAgentResult(result);
      await refreshModelState();
    });

  const handleBacktest = () =>
    runAction("Backtesting symbolic rules", async () => {
      const result = await fetchSymbolicBacktest({ season, week, slate });
      setBacktest(result);
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
                <button type="button" onClick={refreshModelState}>
                  <span>Refresh model state</span><i aria-hidden="true">↗</i>
                </button>
                <button type="button" onClick={refreshCoverage}>
                  <span>Check data coverage</span><i aria-hidden="true">↗</i>
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

          <div className="model-result-grid">
            <article>
              <span>Features</span>
              <strong>{featureResult ? featureResult.rows_written.toLocaleString() : "Not run"}</strong>
              <small>{featureResult?.message ?? "Feature generation result will appear here."}</small>
            </article>
            <article>
              <span>Prediction Run</span>
              <strong>{predictionRunResult ? "Complete" : "Not run"}</strong>
              <small>{predictionRunResult ? `${predictionRunResult.message} (${predictionRunResult.rows_written} rows)` : "Run projections after features are current."}</small>
            </article>
            <article>
              <span>Symbolic Run</span>
              <strong>{agentResult ? agentResult.adjusted_rows.toLocaleString() : "Not run"}</strong>
              <small>{agentResult ? `${agentResult.trace_rows} trace rows from ${agentResult.rule_run_id}` : "No symbolic run loaded."}</small>
            </article>
          </div>

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
                <article key={item.table} className={`coverage-card ${summary.tone}`}>
                  <span>{item.table}</span>
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
            <button type="button" onClick={refreshModelState}>
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
