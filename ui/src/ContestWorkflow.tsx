import { useEffect, useMemo, useState } from "react";
import {
  batchImportDraftKings,
  createPortfolio,
  draftKingsExportDownloadUrl,
  generateDraftKingsExport,
  validateDraftKingsExport,
  type DraftKingsBatchFile,
  type DraftKingsExportResponse,
  type ExportValidationResponse,
  type PortfolioResponse,
} from "./api";
import "./ContestWorkflow.css";

type Props = {
  season: number;
  week: number;
  slate: string;
  slateOptions: string[];
  optimizerRunId?: string | null;
  onSeasonChange: (value: number) => void;
  onWeekChange: (value: number) => void;
  onSlateChange: (value: string) => void;
  onOpenModelWorkbench: () => void;
  onOpenOperations: () => void;
};

type BatchResult = Awaited<ReturnType<typeof batchImportDraftKings>>;

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function statusTone(status: string) {
  if (["imported", "deduplicated", "passed"].includes(status)) return "good";
  if (["failed"].includes(status)) return "bad";
  return "neutral";
}

export function ContestWorkflow({
  season,
  week,
  slate,
  slateOptions,
  optimizerRunId,
  onSeasonChange,
  onWeekChange,
  onSlateChange,
  onOpenModelWorkbench,
  onOpenOperations,
}: Props) {
  const [directory, setDirectory] = useState("~/Downloads");
  const [recursive, setRecursive] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [batch, setBatch] = useState<BatchResult | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [optimizerId, setOptimizerId] = useState(optimizerRunId ?? "");
  const [portfolioName, setPortfolioName] = useState(`${season} W${week} ${slate}`);
  const [defaultContestId, setDefaultContestId] = useState("");
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [validation, setValidation] = useState<ExportValidationResponse | null>(null);
  const [exportResult, setExportResult] = useState<DraftKingsExportResponse | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (optimizerRunId) setOptimizerId(optimizerRunId);
  }, [optimizerRunId]);

  useEffect(() => {
    setPortfolioName(`${season} W${week} ${slate}`);
  }, [season, week, slate]);

  const liveTemplates = useMemo(
    () => batch?.files.filter(
      (file) => file.file_type === "entry_template"
        && ["imported", "deduplicated"].includes(file.status)
        && file.template_id
    ) ?? [],
    [batch]
  );

  const runBatch = async () => {
    setPending(dryRun ? "Scanning directory" : "Importing DraftKings files");
    setError(null);
    setPortfolio(null);
    setValidation(null);
    setExportResult(null);
    try {
      const result = await batchImportDraftKings({
        directory,
        season,
        week,
        slate,
        recursive,
        dry_run: dryRun,
      });
      setBatch(result);
      const template = result.files.find(
        (file) => file.file_type === "entry_template"
          && ["imported", "deduplicated"].includes(file.status)
          && file.template_id
      );
      if (template?.template_id) setSelectedTemplateId(template.template_id);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setPending(null);
    }
  };

  const runCreatePortfolio = async () => {
    setPending("Assigning entries to lineups");
    setError(null);
    setValidation(null);
    setExportResult(null);
    try {
      const result = await createPortfolio({
        portfolio_name: portfolioName,
        optimizer_run_id: optimizerId,
        template_id: selectedTemplateId,
        default_contest_id: defaultContestId || undefined,
      });
      setPortfolio(result);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setPending(null);
    }
  };

  const runValidation = async () => {
    if (!portfolio) return;
    setPending("Validating DraftKings upload");
    setError(null);
    setExportResult(null);
    try {
      setValidation(await validateDraftKingsExport(portfolio.portfolio_id));
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setPending(null);
    }
  };

  const runExport = async () => {
    if (!portfolio) return;
    setPending("Generating DraftKings CSV");
    setError(null);
    try {
      const result = await generateDraftKingsExport(portfolio.portfolio_id);
      setExportResult(result);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setPending(null);
    }
  };

  const steps = [
    { label: "Import", complete: Boolean(batch && !batch.dry_run && batch.failed === 0) },
    { label: "Assign", complete: Boolean(portfolio) },
    { label: "Validate", complete: validation?.status === "passed" },
    { label: "Export", complete: Boolean(exportResult) },
  ];

  return (
    <main className="contest-workflow">
      <header className="contest-command">
        <div className="contest-brand">
          <span>DK</span>
          <div><p>Football Opt</p><h1>Contest Delivery</h1></div>
        </div>
        <div className="contest-context">
          <label>Season<input type="number" value={season} onChange={(event) => onSeasonChange(Number(event.target.value))} /></label>
          <label>Week<input type="number" min={1} max={25} value={week} onChange={(event) => onWeekChange(Number(event.target.value))} /></label>
          <label>Slate<select value={slate} onChange={(event) => onSlateChange(event.target.value)}>{slateOptions.map((option) => <option key={option}>{option}</option>)}</select></label>
        </div>
        <div className="contest-nav">
          <button onClick={onOpenModelWorkbench}>Model Workbench</button>
          <button onClick={onOpenOperations}>Operations</button>
        </div>
      </header>

      <section className="contest-progress" aria-label="Delivery progress">
        {steps.map((step, index) => <article className={step.complete ? "complete" : ""} key={step.label}><b>{index + 1}</b><span>{step.label}</span><small>{step.complete ? "Complete" : "Pending"}</small></article>)}
      </section>

      {pending && <div className="contest-banner">{pending}…</div>}
      {error && <div className="contest-banner error" role="alert">{error}</div>}

      <section className="contest-grid">
        <article className="contest-card import-card">
          <div className="contest-title"><span>Step 1</span><h2>Import files</h2><p>Scan a local directory for salaries, standings, and entry templates.</p></div>
          <label className="wide-label">Directory<input value={directory} onChange={(event) => setDirectory(event.target.value)} placeholder="~/Downloads" /></label>
          <div className="contest-checks">
            <label><input type="checkbox" checked={recursive} onChange={(event) => setRecursive(event.target.checked)} /> Include subdirectories</label>
            <label><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /> Dry run first</label>
          </div>
          <button className="primary" disabled={Boolean(pending) || !directory.trim()} onClick={runBatch}>{dryRun ? "Scan Directory" : "Import Files"}</button>
          {batch && <div className="contest-stats"><div><span>Found</span><strong>{batch.discovered}</strong></div><div><span>Imported</span><strong>{batch.imported}</strong></div><div><span>Skipped</span><strong>{batch.skipped}</strong></div><div><span>Failed</span><strong>{batch.failed}</strong></div></div>}
        </article>

        <article className="contest-card assign-card">
          <div className="contest-title"><span>Step 2</span><h2>Assign portfolio</h2><p>Pair a completed optimizer run with the imported paid entries.</p></div>
          <label>Optimizer run ID<input value={optimizerId} onChange={(event) => setOptimizerId(event.target.value)} placeholder="Optimizer job ID" /></label>
          <label>Entry template ID<input value={selectedTemplateId} onChange={(event) => setSelectedTemplateId(event.target.value)} placeholder="Select an imported template below" /></label>
          <label>Portfolio name<input value={portfolioName} onChange={(event) => setPortfolioName(event.target.value)} /></label>
          <label>Contest ID fallback <small>Optional</small><input value={defaultContestId} onChange={(event) => setDefaultContestId(event.target.value)} /></label>
          <button className="primary" disabled={Boolean(pending) || !optimizerId.trim() || !selectedTemplateId.trim() || !portfolioName.trim()} onClick={runCreatePortfolio}>Create Portfolio</button>
          {liveTemplates.length > 0 && <div className="template-picks"><span>Imported templates</span>{liveTemplates.map((file) => <button key={file.template_id} onClick={() => setSelectedTemplateId(file.template_id ?? "")}>{file.path.split("/").pop()}</button>)}</div>}
          {portfolio && <div className="contest-success"><strong>{portfolio.portfolio_name}</strong><span>{portfolio.assignment_count} entries · {portfolio.contest_format} {portfolio.objective}</span><code>{portfolio.portfolio_id}</code></div>}
        </article>

        <article className="contest-card delivery-card">
          <div className="contest-title"><span>Steps 3–4</span><h2>Validate and download</h2><p>Resolve every blocking issue before producing upload-ready bytes.</p></div>
          <div className="delivery-actions">
            <button disabled={Boolean(pending) || !portfolio} onClick={runValidation}>Run Validation</button>
            <button className="primary" disabled={Boolean(pending) || validation?.status !== "passed"} onClick={runExport}>Generate CSV</button>
          </div>
          {!portfolio && <p className="contest-empty">Create a portfolio to unlock validation.</p>}
          {validation && <div className={`validation-summary ${validation.status}`}><strong>{validation.status === "passed" ? "Ready to export" : `${validation.errors.length} blocking issue${validation.errors.length === 1 ? "" : "s"}`}</strong><span>{validation.checks_run} validation groups checked</span></div>}
          {validation?.errors.map((issue, index) => <div className="validation-issue" key={`${issue.code}-${index}`}><b>{issue.code.replaceAll("_", " ")}</b><span>{issue.message}</span>{issue.lineup_number && <small>Lineup {issue.lineup_number}</small>}</div>)}
          {exportResult && <div className="export-ready"><span>Upload ready</span><strong>{exportResult.file_name}</strong><small>{exportResult.row_count} entries · SHA {exportResult.content_sha256.slice(0, 12)}</small><a href={draftKingsExportDownloadUrl(exportResult.export_id)}>Download DraftKings CSV</a></div>}
        </article>
      </section>

      {batch && <section className="contest-card batch-report"><div className="contest-title"><span>Batch {batch.batch_id.slice(0, 8)}</span><h2>File report</h2></div><div className="contest-table-wrap"><table><thead><tr><th>File</th><th>Type</th><th>Status</th><th>Scope</th><th>Rows</th><th>Artifact</th></tr></thead><tbody>{batch.files.map((file: DraftKingsBatchFile) => <tr key={`${file.path}-${file.file_type}`}><td>{file.path}</td><td>{file.file_type.replaceAll("_", " ")}</td><td><span className={`file-status ${statusTone(file.status)}`}>{file.status}</span></td><td>{file.season} W{file.week} · {file.slate.replaceAll("_", " ")}</td><td>{file.rows_written}</td><td>{file.template_id && ["imported", "deduplicated"].includes(file.status) ? <button onClick={() => setSelectedTemplateId(file.template_id ?? "")}>Use template</button> : file.template_id ? "Dry run only" : file.contest_id ? <code>{file.contest_id.slice(0, 16)}</code> : "—"}</td></tr>)}</tbody></table></div></section>}

      {exportResult && <section className="contest-card csv-preview"><div className="contest-title"><span>Preview</span><h2>Generated CSV</h2></div><pre>{exportResult.csv_content.split("\n").slice(0, 8).join("\n")}</pre></section>}
    </main>
  );
}
