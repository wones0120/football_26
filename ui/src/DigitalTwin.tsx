import { useEffect, useMemo, useState } from "react";
import {
  createDigitalTwinImpactPreview,
  createDigitalTwinVariantSet,
  createDigitalTwinBelief,
  createDigitalTwinThoughtCapture,
  decideDigitalTwinImpactPreview,
  decideDigitalTwinThoughtCandidate,
  fetchDigitalTwinBeliefs,
  fetchDigitalTwinImpactPreviews,
  fetchDigitalTwinVariantSets,
  fetchDigitalTwinThoughtCaptures,
  fetchLatestOwnership,
  fetchLatestPredictions,
  fetchNewsMonitorFeedback,
  fetchNewsMonitorReport,
  fetchSlateReadiness,
  reviseDigitalTwinBelief,
  replayDigitalTwinVariantSet,
  setDigitalTwinBeliefStatus,
  type BeliefCreatePayload,
  type BeliefDirection,
  type BeliefImpactPreview,
  type BeliefRevisionPayload,
  type BeliefScope,
  type HumanBelief,
  type DigitalTwinVariantSet,
  type NewsMonitorFeedbackRow,
  type NewsMonitorRunResponse,
  type OptimizerResponse,
  type OwnershipProjectionRow,
  type PredictionRow,
  type SlateReadinessGateKey,
  type SlateReadinessResponse,
  type ThoughtCandidate,
  type ThoughtCapture,
  type ThoughtCaptureContext,
} from "./api";
import type { ViewMode } from "./AppShell";
import "./DigitalTwin.css";

type DigitalTwinProps = {
  season: number;
  week: number;
  slate: string;
  contestFormat: "classic" | "showdown";
  optimizerObjective: "cash" | "gpp";
  optimizerStatus: OptimizerResponse | null;
  onNavigate: (view: ViewMode) => void;
};

type SourceStatus = "loading" | "ready" | "attention";

type OwnershipDiagnostics = {
  mae: number | null;
  baselineMae: number | null;
  rankCorrelation: number | null;
  walkForwardRows: number;
  gateStatus: "passed" | "blocked";
};

type CashLineupSummary = {
  objective_id: string;
  projected_floor_p10: number;
  objective_score: number;
  average_role_certainty: number;
  total_fragility_penalty: number;
  missing_projection_players: Array<{ name?: string; position?: string }>;
};

type ThoughtDraft = {
  scope: BeliefScope;
  seasonContext: number;
  subject: string;
  direction: BeliefDirection;
  strength: number;
  confidence: number;
  thought: string;
  evidence: string;
  expiresOn: string;
  retrospective: boolean;
};

type RawThoughtDraft = {
  context: ThoughtCaptureContext;
  subject: string;
  rawText: string;
};

const THOUGHT_LANES: Array<{ scope: BeliefScope; label: string; shortLabel: string; description: string }> = [
  { scope: "global", label: "My Playbook", shortLabel: "Playbook", description: "Durable principles that should travel from slate to slate." },
  { scope: "contest_profile", label: "Contest Lens", shortLabel: "Contest", description: "How you want to approach Classic, Showdown, cash, or GPP fields." },
  { scope: "season", label: "Season Outlook", shortLabel: "Season", description: "Team, scheme, coaching, rookie, and role priors for the selected season." },
  { scope: "weekly", label: "Weekly Thesis", shortLabel: "Slate", description: "Your high-level interpretation of the selected slate." },
  { scope: "game", label: "Game Take", shortLabel: "Game", description: "Environment, pace, matchup, blowout, and correlation views." },
  { scope: "player", label: "Player Take", shortLabel: "Player", description: "Role, talent, projection, ownership, and uncertainty disagreements." },
];

const THOUGHT_DIRECTIONS: Array<{ value: BeliefDirection; label: string }> = [
  { value: "boost", label: "Boost" },
  { value: "fade", label: "Fade" },
  { value: "prefer", label: "Prefer" },
  { value: "avoid", label: "Avoid" },
  { value: "monitor", label: "Watch" },
  { value: "neutral", label: "Neutral" },
];

const RAW_THOUGHT_CONTEXTS: Array<{ value: ThoughtCaptureContext; label: string; detail: string }> = [
  { value: "auto", label: "Auto-sort", detail: "Current slate + player matching" },
  { value: "general", label: "General", detail: "Durable playbook thinking" },
  { value: "slate", label: "This slate", detail: "Weekly thesis and construction" },
  { value: "player", label: "One player", detail: "Anchor the full note to a player" },
];

function emptyThoughtDraft(season: number): ThoughtDraft {
  return {
    scope: "weekly",
    seasonContext: season,
    subject: "",
    direction: "prefer",
    strength: 3,
    confidence: 65,
    thought: "",
    evidence: "",
    expiresOn: "",
    retrospective: season < new Date().getFullYear(),
  };
}

function emptyRawThoughtDraft(): RawThoughtDraft {
  return { context: "auto", subject: "", rawText: "" };
}

function scopeLabel(scope: BeliefScope) {
  return THOUGHT_LANES.find((lane) => lane.scope === scope)?.shortLabel ?? scope;
}

function beliefContext(belief: HumanBelief) {
  const context = [belief.subject_label];
  if (belief.season) context.push(`${belief.season}${belief.week ? ` · W${belief.week}` : ""}`);
  if (belief.slate) context.push(formatSlate(belief.slate));
  if (belief.contest_format || belief.objective) {
    context.push([belief.contest_format, belief.objective].filter(Boolean).join(" · "));
  }
  return context.filter(Boolean).join(" · ") || "All slates";
}

function normalizedPlayerName(value: string | null | undefined) {
  return (value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function impactValue(value: number | null, suffix = "") {
  return value === null ? "Unavailable" : `${value.toFixed(2)}${suffix}`;
}

function formatSlate(value: string) {
  return value.replaceAll("_", " ");
}

function localDateKey(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function projectionMean(row: PredictionRow) {
  return Number(row.adj_mean_final || row.adj_mean || row.predicted_mean || 0);
}

function normalizedName(value: string) {
  return value.trim().toLowerCase().replaceAll(/[^a-z0-9]/g, "");
}

function findOwnership(
  prediction: PredictionRow,
  byId: Map<string, OwnershipProjectionRow>,
  byName: Map<string, OwnershipProjectionRow>,
) {
  return byId.get(prediction.player_id) ?? byName.get(normalizedName(prediction.player_display_name));
}

function lineupCount(status: OptimizerResponse | null) {
  const results = status?.results;
  if (Array.isArray(results)) return results.length;
  if (results && typeof results === "object" && "lineups" in results) {
    const lineups = (results as { lineups?: unknown }).lineups;
    return Array.isArray(lineups) ? lineups.length : 0;
  }
  return 0;
}

function sourceTone(status: SourceStatus) {
  return status === "ready" ? "ready" : status === "loading" ? "loading" : "attention";
}

function readOwnershipDiagnostics(rows: OwnershipProjectionRow[]): OwnershipDiagnostics | null {
  const encoded = rows.find((row) => row.model_metrics_json)?.model_metrics_json;
  if (!encoded) return null;
  try {
    const metrics = JSON.parse(encoded) as {
      mae?: number | null;
      baseline_mae?: number | null;
      rank_correlation?: number | null;
      walk_forward_rows?: number;
      promotion_gate?: { status?: string };
    };
    return {
      mae: typeof metrics.mae === "number" ? metrics.mae : null,
      baselineMae: typeof metrics.baseline_mae === "number" ? metrics.baseline_mae : null,
      rankCorrelation: typeof metrics.rank_correlation === "number" ? metrics.rank_correlation : null,
      walkForwardRows: Number(metrics.walk_forward_rows ?? 0),
      gateStatus: metrics.promotion_gate?.status === "passed" ? "passed" : "blocked",
    };
  } catch {
    return null;
  }
}

function readCashLineupSummary(status: OptimizerResponse | null): CashLineupSummary | null {
  if (status?.contest_format !== "classic" || status.objective !== "cash" || !Array.isArray(status.results)) return null;
  const firstLineup = status.results[0];
  if (!Array.isArray(firstLineup) || typeof firstLineup[0] !== "object" || firstLineup[0] === null) return null;
  const summary = (firstLineup[0] as { lineup_cash_summary?: Partial<CashLineupSummary> }).lineup_cash_summary;
  if (!summary || typeof summary.projected_floor_p10 !== "number") return null;
  return {
    objective_id: String(summary.objective_id ?? "classic_cash_v1"),
    projected_floor_p10: summary.projected_floor_p10,
    objective_score: Number(summary.objective_score ?? 0),
    average_role_certainty: Number(summary.average_role_certainty ?? 0),
    total_fragility_penalty: Number(summary.total_fragility_penalty ?? 0),
    missing_projection_players: Array.isArray(summary.missing_projection_players) ? summary.missing_projection_players : [],
  };
}

export function DigitalTwin({ season, week, slate, contestFormat, optimizerObjective, optimizerStatus, onNavigate }: DigitalTwinProps) {
  const [predictions, setPredictions] = useState<PredictionRow[]>([]);
  const [ownership, setOwnership] = useState<OwnershipProjectionRow[]>([]);
  const [newsReport, setNewsReport] = useState<NewsMonitorRunResponse | null>(null);
  const [feedback, setFeedback] = useState<NewsMonitorFeedbackRow[]>([]);
  const [beliefs, setBeliefs] = useState<HumanBelief[]>([]);
  const [thoughtCaptures, setThoughtCaptures] = useState<ThoughtCapture[]>([]);
  const [impactPreviews, setImpactPreviews] = useState<BeliefImpactPreview[]>([]);
  const [variantSets, setVariantSets] = useState<DigitalTwinVariantSet[]>([]);
  const [readiness, setReadiness] = useState<SlateReadinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [thoughtDraft, setThoughtDraft] = useState<ThoughtDraft>(() => emptyThoughtDraft(season));
  const [rawThoughtDraft, setRawThoughtDraft] = useState<RawThoughtDraft>(emptyRawThoughtDraft);
  const [editingBeliefId, setEditingBeliefId] = useState<string | null>(null);
  const [reviewingCandidateId, setReviewingCandidateId] = useState<string | null>(null);
  const [thoughtCaptureBusy, setThoughtCaptureBusy] = useState(false);
  const [thoughtCaptureMessage, setThoughtCaptureMessage] = useState<{ tone: "saved" | "error"; text: string } | null>(null);
  const [beliefScopeFilter, setBeliefScopeFilter] = useState<BeliefScope | "all">("all");
  const [beliefStatusFilter, setBeliefStatusFilter] = useState<"current" | "all">("current");
  const [beliefSaving, setBeliefSaving] = useState(false);
  const [beliefMessage, setBeliefMessage] = useState<{ tone: "saved" | "error"; text: string } | null>(null);
  const [impactBeliefId, setImpactBeliefId] = useState<string | null>(null);
  const [impactTargetPlayerId, setImpactTargetPlayerId] = useState("");
  const [impactDecisionNote, setImpactDecisionNote] = useState("");
  const [impactBusy, setImpactBusy] = useState(false);
  const [impactMessage, setImpactMessage] = useState<{ tone: "saved" | "error"; text: string } | null>(null);
  const [variantBusy, setVariantBusy] = useState(false);
  const [variantMessage, setVariantMessage] = useState<{ tone: "saved" | "error"; text: string } | null>(null);
  const reportDate = localDateKey();

  useEffect(() => {
    let cancelled = false;

    async function loadCockpit() {
      setLoading(true);
      setErrors([]);
      const results = await Promise.allSettled([
        fetchLatestPredictions({ season, week, slate, limit: 1000 }),
        fetchLatestOwnership({ season, week, slate, limit: 1000 }),
        fetchNewsMonitorReport(reportDate),
        fetchNewsMonitorFeedback(reportDate),
        fetchSlateReadiness({ season, week, slate }),
        fetchDigitalTwinBeliefs({ season, week, slate, include_inactive: true }),
        fetchDigitalTwinThoughtCaptures({ season, week, slate }),
        fetchDigitalTwinImpactPreviews({ season, week, slate }),
        fetchDigitalTwinVariantSets({ season, week, slate, limit: 1 }),
      ]);
      if (cancelled) return;

      const nextErrors: string[] = [];
      const [predictionResult, ownershipResult, newsResult, feedbackResult, readinessResult, beliefResult, captureResult, impactResult, variantResult] = results;

      if (predictionResult.status === "fulfilled") setPredictions(predictionResult.value.rows);
      else {
        setPredictions([]);
        nextErrors.push("Projection source unavailable");
      }

      if (ownershipResult.status === "fulfilled") setOwnership(ownershipResult.value.rows);
      else {
        setOwnership([]);
        nextErrors.push("Ownership source unavailable");
      }

      if (newsResult.status === "fulfilled") setNewsReport(newsResult.value);
      else {
        setNewsReport(null);
        nextErrors.push("Intelligence source unavailable");
      }

      if (feedbackResult.status === "fulfilled") setFeedback(feedbackResult.value.rows);
      else setFeedback([]);

      if (readinessResult.status === "fulfilled") setReadiness(readinessResult.value);
      else {
        setReadiness(null);
        nextErrors.push("Readiness contract unavailable");
      }

      if (beliefResult.status === "fulfilled") setBeliefs(beliefResult.value.rows);
      else {
        setBeliefs([]);
        nextErrors.push("Twin memory unavailable");
      }

      if (captureResult.status === "fulfilled") setThoughtCaptures(captureResult.value.rows);
      else {
        setThoughtCaptures([]);
        nextErrors.push("Thought inbox unavailable");
      }

      if (impactResult.status === "fulfilled") setImpactPreviews(impactResult.value.rows);
      else {
        setImpactPreviews([]);
        nextErrors.push("Belief impact history unavailable");
      }

      if (variantResult.status === "fulfilled") setVariantSets(variantResult.value.rows);
      else {
        setVariantSets([]);
        nextErrors.push("Digital Twin variants unavailable");
      }

      setErrors(nextErrors);
      setLoading(false);
    }

    loadCockpit().catch(() => {
      if (!cancelled) {
        setErrors(["The cockpit could not refresh its live sources"]);
        setLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [reportDate, season, slate, week]);

  useEffect(() => {
    if (editingBeliefId || reviewingCandidateId) return;
    setThoughtDraft((current) => ({
      ...current,
      seasonContext: current.scope === "season" ? current.seasonContext : season,
      retrospective: current.scope === "global" || current.scope === "contest_profile"
        ? false
        : (current.scope === "season" ? current.seasonContext : season) < new Date().getFullYear(),
    }));
  }, [editingBeliefId, reviewingCandidateId, season]);

  const optimizerReady = optimizerStatus?.status === "completed";
  const readinessGateKey = `${contestFormat}_${optimizerObjective}` as SlateReadinessGateKey;
  const readinessGate = readiness?.gates[readinessGateKey];
  const readinessAttention = useMemo(() => {
    if (!readiness || !readinessGate) return [];
    const attention = new Set(readinessGate.attention_checks);
    return readiness.checks
      .filter((check) => attention.has(check.check_id))
      .sort((left, right) => Number(right.status === "fail") - Number(left.status === "fail"))
      .slice(0, 4);
  }, [readiness, readinessGate]);
  const generatedLineups = lineupCount(optimizerStatus);
  const signalCount = newsReport?.signals_extracted ?? 0;
  const highPrioritySignals = newsReport?.report.high_priority_signals.length ?? 0;
  const ownershipDiagnostics = useMemo(() => readOwnershipDiagnostics(ownership), [ownership]);
  const cashLineupSummary = useMemo(() => readCashLineupSummary(optimizerStatus), [optimizerStatus]);
  const ownershipQuality = ownershipDiagnostics && ownershipDiagnostics.mae !== null && ownershipDiagnostics.rankCorrelation !== null
    ? `${ownershipDiagnostics.mae.toFixed(2)} MAE · ρ ${ownershipDiagnostics.rankCorrelation.toFixed(2)}`
    : null;
  const sourceStates = useMemo(
    () => [
      {
        label: "Projection distribution",
        status: loading ? "loading" as const : predictions.length > 0 ? "ready" as const : "attention" as const,
        value: loading ? "Refreshing" : predictions.length > 0 ? `${predictions.length} players` : "Run required",
        detail: predictions.length > 0 ? "Latest player outcomes are available." : "Build features and establish the slate baseline.",
        action: "model-workbench" as ViewMode,
      },
      {
        label: "Field ownership",
        status: loading ? "loading" as const : ownership.length > 0 && ownershipDiagnostics?.gateStatus !== "blocked" ? "ready" as const : "attention" as const,
        value: loading ? "Refreshing" : ownershipQuality ?? (ownership.length > 0 ? `${ownership.length} players` : "Not modeled"),
        detail: ownershipDiagnostics
          ? `Slate-aware challenger · ${ownershipDiagnostics.walkForwardRows.toLocaleString()} replay rows · promotion ${ownershipDiagnostics.gateStatus}.`
          : ownership.length > 0 ? "Expected field behavior is attached." : "Run the ownership model before GPP decisions.",
        action: "workspace" as ViewMode,
      },
      {
        label: "Slate intelligence",
        status: loading ? "loading" as const : newsReport ? "ready" as const : "attention" as const,
        value: loading ? "Refreshing" : newsReport ? `${signalCount} signals` : "No daily brief",
        detail: newsReport ? `${highPrioritySignals} high-priority items need context.` : "Review or run today's intelligence brief.",
        action: "news-brief" as ViewMode,
      },
      {
        label: "Candidate portfolio",
        status: optimizerReady ? "ready" as const : "attention" as const,
        value: optimizerReady ? `${generatedLineups} lineups` : optimizerStatus?.status ?? "Not generated",
        detail: optimizerReady ? `${optimizerStatus?.contest_format} ${optimizerStatus?.objective} run is in session.` : "Generate candidates after projections and ownership are ready.",
        action: "workspace" as ViewMode,
      },
    ],
    [generatedLineups, highPrioritySignals, loading, newsReport, optimizerReady, optimizerStatus, ownership.length, ownershipDiagnostics, ownershipQuality, predictions.length, signalCount],
  );

  const readySources = sourceStates.filter((source) => source.status === "ready").length;
  const readinessScore = readinessGate?.score ?? Math.round((readySources / sourceStates.length) * 100);

  const decisionWatchlist = useMemo(() => {
    const ownershipById = new Map(ownership.map((row) => [row.player_id, row]));
    const ownershipByName = new Map(ownership.map((row) => [normalizedName(row.player_display_name), row]));
    return predictions
      .map((prediction) => {
        const matchedOwnership = findOwnership(prediction, ownershipById, ownershipByName);
        const projectedOwnership = Number(matchedOwnership?.projected_ownership ?? 0);
        const ceilingGap = Math.max(0, Number(prediction.predicted_p90 || 0) - projectionMean(prediction));
        return {
          player: prediction.player_display_name,
          position: prediction.position,
          team: prediction.recent_team,
          mean: projectionMean(prediction),
          ceilingGap,
          ownership: projectedOwnership,
          rankValue: ceilingGap - projectedOwnership * 0.08,
        };
      })
      .filter((row) => row.ceilingGap > 0)
      .sort((left, right) => right.rankValue - left.rankValue)
      .slice(0, 4);
  }, [ownership, predictions]);

  const averageMedian = predictions.length > 0
    ? predictions.reduce((sum, row) => sum + Number(row.predicted_p50 || projectionMean(row)), 0) / predictions.length
    : 0;
  const ceilingPool = predictions.filter((row) => Number(row.predicted_p90 || 0) >= 20).length;
  const lowOwnedCeiling = decisionWatchlist.filter((row) => row.ownership > 0 && row.ownership < 12).length;

  const feedbackSummary = useMemo(() => {
    const count = (choice: string) => feedback.filter((row) => row.feedback_choice === choice).length;
    return {
      valuable: count("Valuable"),
      relevant: count("Relevant"),
      monitor: count("Monitor"),
      noise: count("Noise"),
      total: feedback.filter((row) => row.feedback_choice).length,
    };
  }, [feedback]);

  const activeBeliefs = beliefs.filter((belief) => belief.status === "active" && !belief.is_expired);
  const beliefVersionCount = beliefs.reduce((sum, belief) => sum + belief.belief_version, 0);
  const pendingThoughtCandidates = thoughtCaptures
    .flatMap((capture) => capture.candidates)
    .filter((candidate) => candidate.status === "pending");
  const latestThoughtCapture = thoughtCaptures[0] ?? null;
  const visibleBeliefs = beliefs.filter((belief) => {
    if (beliefScopeFilter !== "all" && belief.scope_type !== beliefScopeFilter) return false;
    if (beliefStatusFilter === "current" && (belief.status !== "active" || belief.is_expired)) return false;
    return true;
  });
  const selectableImpactPlayers = useMemo(
    () => [...predictions].sort((left, right) => left.player_display_name.localeCompare(right.player_display_name)),
    [predictions],
  );
  const activeLane = THOUGHT_LANES.find((lane) => lane.scope === thoughtDraft.scope) ?? THOUGHT_LANES[0];
  const subjectRequired = thoughtDraft.scope === "game" || thoughtDraft.scope === "player";
  const canSaveThought = thoughtDraft.thought.trim().length > 0 && (!subjectRequired || thoughtDraft.subject.trim().length > 0);
  const canCaptureRawThought = rawThoughtDraft.rawText.trim().length > 0
    && (rawThoughtDraft.context !== "player" || rawThoughtDraft.subject.trim().length > 0);

  async function refreshBeliefs() {
    const result = await fetchDigitalTwinBeliefs({ season, week, slate, include_inactive: true });
    setBeliefs(result.rows);
  }

  async function refreshThoughtCaptures() {
    const result = await fetchDigitalTwinThoughtCaptures({ season, week, slate });
    setThoughtCaptures(result.rows);
  }

  async function captureRawThought(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCaptureRawThought || thoughtCaptureBusy) return;
    setThoughtCaptureBusy(true);
    setThoughtCaptureMessage(null);
    const scopedToSlate = rawThoughtDraft.context !== "general";
    const matchedSubject = predictions.find(
      (player) => normalizedPlayerName(player.player_display_name) === normalizedPlayerName(rawThoughtDraft.subject),
    );
    try {
      const capture = await createDigitalTwinThoughtCapture({
        context_type: rawThoughtDraft.context,
        raw_text: rawThoughtDraft.rawText.trim(),
        subject_label: rawThoughtDraft.context === "player" ? rawThoughtDraft.subject.trim() : null,
        subject_id: rawThoughtDraft.context === "player" ? matchedSubject?.player_id ?? null : null,
        season: scopedToSlate ? season : null,
        week: scopedToSlate ? week : null,
        slate: scopedToSlate ? slate : null,
        contest_format: scopedToSlate ? contestFormat : null,
        objective: scopedToSlate ? optimizerObjective : null,
        source: "thought_inbox",
      });
      setThoughtCaptures((current) => [capture, ...current]);
      setRawThoughtDraft(emptyRawThoughtDraft());
      setThoughtCaptureMessage({
        tone: "saved",
        text: `${capture.candidates.length} review-only candidate${capture.candidates.length === 1 ? "" : "s"} extracted. Your original text is preserved.`,
      });
    } catch (error) {
      setThoughtCaptureMessage({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to preserve this thought capture.",
      });
    } finally {
      setThoughtCaptureBusy(false);
    }
  }

  function reviewThoughtCandidate(candidate: ThoughtCandidate) {
    setEditingBeliefId(null);
    setReviewingCandidateId(candidate.candidate_id);
    setThoughtDraft({
      scope: candidate.scope_type,
      seasonContext: candidate.season ?? season,
      subject: candidate.subject_label ?? "",
      direction: candidate.direction,
      strength: candidate.strength,
      confidence: candidate.confidence,
      thought: candidate.thought_text,
      evidence: "",
      expiresOn: "",
      retrospective: Boolean(candidate.season && candidate.season < new Date().getFullYear()),
    });
    setBeliefMessage({ tone: "saved", text: "Candidate loaded. Review every field before accepting it into memory." });
    window.requestAnimationFrame(() => document.getElementById("thought-composer")?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }

  function cancelCandidateReview() {
    setReviewingCandidateId(null);
    setThoughtDraft(emptyThoughtDraft(season));
    setBeliefMessage(null);
  }

  async function rejectThoughtCandidate(candidate: ThoughtCandidate) {
    if (thoughtCaptureBusy) return;
    setThoughtCaptureBusy(true);
    setThoughtCaptureMessage(null);
    try {
      await decideDigitalTwinThoughtCandidate(candidate.candidate_id, "rejected");
      await refreshThoughtCaptures();
      if (reviewingCandidateId === candidate.candidate_id) cancelCandidateReview();
      setThoughtCaptureMessage({ tone: "saved", text: "Candidate rejected. The original raw capture remains in the audit trail." });
    } catch (error) {
      setThoughtCaptureMessage({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to reject this candidate.",
      });
    } finally {
      setThoughtCaptureBusy(false);
    }
  }

  function buildThoughtPayload(): BeliefCreatePayload {
    const contextualScope = ["season", "weekly", "game", "player"].includes(thoughtDraft.scope);
    const weeklyScope = ["weekly", "game", "player"].includes(thoughtDraft.scope);
    const contestScope = ["contest_profile", "weekly", "game", "player"].includes(thoughtDraft.scope);
    return {
      scope_type: thoughtDraft.scope,
      subject_label: subjectRequired ? thoughtDraft.subject.trim() : null,
      season: thoughtDraft.scope === "season" ? thoughtDraft.seasonContext : contextualScope ? season : null,
      week: weeklyScope ? week : null,
      slate: weeklyScope ? slate : null,
      contest_format: contestScope ? contestFormat : null,
      objective: contestScope ? optimizerObjective : null,
      direction: thoughtDraft.direction,
      strength: thoughtDraft.strength,
      confidence: thoughtDraft.confidence,
      thought_text: thoughtDraft.thought.trim(),
      evidence_text: thoughtDraft.evidence.trim() || null,
      expires_at: thoughtDraft.expiresOn ? `${thoughtDraft.expiresOn}T23:59:59Z` : null,
      is_retrospective: contextualScope ? thoughtDraft.retrospective : false,
      source: "thought_studio",
      metadata: { capture_surface: "digital_twin", impact_guardrail: "not_applied" },
    };
  }

  async function saveThought(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSaveThought || beliefSaving) return;
    setBeliefSaving(true);
    setBeliefMessage(null);
    try {
      const payload = buildThoughtPayload();
      if (reviewingCandidateId) {
        await decideDigitalTwinThoughtCandidate(reviewingCandidateId, "accepted", payload);
      } else if (editingBeliefId) {
        const revision = Object.fromEntries(
          Object.entries(payload).filter(([key]) => key !== "scope_type"),
        ) as BeliefRevisionPayload;
        await reviseDigitalTwinBelief(editingBeliefId, revision);
      } else {
        await createDigitalTwinBelief(payload);
      }
      await Promise.all([refreshBeliefs(), reviewingCandidateId ? refreshThoughtCaptures() : Promise.resolve()]);
      setBeliefMessage({
        tone: "saved",
        text: reviewingCandidateId
          ? "Candidate accepted as a versioned belief. It still has no model impact until previewed and approved."
          : editingBeliefId ? "Revision saved as a new memory version." : "Thought saved to Twin memory.",
      });
      setEditingBeliefId(null);
      setReviewingCandidateId(null);
      setThoughtDraft(emptyThoughtDraft(season));
    } catch (error) {
      setBeliefMessage({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to save this thought.",
      });
    } finally {
      setBeliefSaving(false);
    }
  }

  function beginBeliefRevision(belief: HumanBelief) {
    setReviewingCandidateId(null);
    setEditingBeliefId(belief.belief_id);
    setThoughtDraft({
      scope: belief.scope_type,
      seasonContext: belief.season ?? season,
      subject: belief.subject_label ?? "",
      direction: belief.direction,
      strength: belief.strength,
      confidence: belief.confidence,
      thought: belief.thought_text,
      evidence: belief.evidence_text ?? "",
      expiresOn: belief.expires_at?.slice(0, 10) ?? "",
      retrospective: belief.is_retrospective,
    });
    setBeliefMessage(null);
    window.requestAnimationFrame(() => document.getElementById("thought-studio")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function cancelBeliefRevision() {
    setEditingBeliefId(null);
    setThoughtDraft(emptyThoughtDraft(season));
    setBeliefMessage(null);
  }

  async function changeBeliefStatus(belief: HumanBelief) {
    if (beliefSaving) return;
    setBeliefSaving(true);
    setBeliefMessage(null);
    const nextStatus = belief.status === "active" ? "inactive" : "active";
    try {
      await setDigitalTwinBeliefStatus(belief.belief_id, nextStatus);
      await refreshBeliefs();
      setBeliefMessage({
        tone: "saved",
        text: nextStatus === "active" ? "Belief restored as a new version." : "Belief deactivated; its history remains intact.",
      });
    } catch (error) {
      setBeliefMessage({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to update this belief.",
      });
    } finally {
      setBeliefSaving(false);
    }
  }

  function openImpactPreview(belief: HumanBelief) {
    if (impactBeliefId === belief.belief_id) {
      setImpactBeliefId(null);
      return;
    }
    const existingPreview = impactPreviews.find((preview) => preview.belief_version_id === belief.belief_version_id);
    const matchedPlayer = predictions.find((player) =>
      player.player_id === existingPreview?.target_player_id
      || (belief.subject_id && player.player_id === belief.subject_id)
      || normalizedPlayerName(player.player_display_name) === normalizedPlayerName(belief.subject_label)
    );
    setImpactBeliefId(belief.belief_id);
    setImpactTargetPlayerId(matchedPlayer?.player_id ?? "");
    setImpactDecisionNote(existingPreview?.note_text ?? "");
    setImpactMessage(null);
  }

  async function generateImpactPreview(belief: HumanBelief) {
    if (!impactTargetPlayerId || impactBusy) return;
    setImpactBusy(true);
    setImpactMessage(null);
    try {
      const preview = await createDigitalTwinImpactPreview(belief.belief_id, {
        target_player_id: impactTargetPlayerId,
        season,
        week,
        slate,
        contest_format: belief.contest_format ?? contestFormat,
        objective: belief.objective ?? optimizerObjective,
      });
      setImpactPreviews((current) => [preview, ...current]);
      setImpactMessage({ tone: "saved", text: "Guarded preview saved. Nothing has been applied." });
    } catch (error) {
      setImpactMessage({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to build this impact preview.",
      });
    } finally {
      setImpactBusy(false);
    }
  }

  async function decideImpactPreview(preview: BeliefImpactPreview, decision: "approved" | "rejected") {
    if (impactBusy) return;
    setImpactBusy(true);
    setImpactMessage(null);
    try {
      const updated = await decideDigitalTwinImpactPreview(preview.preview_id, decision, impactDecisionNote);
      setImpactPreviews((current) => current.map((row) => row.preview_id === updated.preview_id ? updated : row));
      setImpactMessage({
        tone: "saved",
        text: decision === "approved"
          ? "Modifier approved for DT-703. The base model remains unchanged."
          : "Preview rejected. No modifier will be used.",
      });
    } catch (error) {
      setImpactMessage({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to record this decision.",
      });
    } finally {
      setImpactBusy(false);
    }
  }

  async function freezeVariantSet() {
    if (variantBusy || predictions.length === 0) return;
    setVariantBusy(true);
    setVariantMessage(null);
    try {
      const variantSet = await createDigitalTwinVariantSet({
        season,
        week,
        slate,
        contest_format: contestFormat,
        objective: optimizerObjective,
        projection_run_id: predictions.find((row) => row.projection_run_id)?.projection_run_id ?? null,
      });
      setVariantSets((current) => [variantSet, ...current]);
      setVariantMessage({
        tone: "saved",
        text: `Three immutable variants saved with ${variantSet.comparison.players_with_human_input} approved human input${variantSet.comparison.players_with_human_input === 1 ? "" : "s"}.`,
      });
    } catch (error) {
      setVariantMessage({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to persist the comparison bundle.",
      });
    } finally {
      setVariantBusy(false);
    }
  }

  async function verifyVariantSet(variantSet: DigitalTwinVariantSet) {
    if (variantBusy) return;
    setVariantBusy(true);
    setVariantMessage(null);
    try {
      const replay = await replayDigitalTwinVariantSet(variantSet.variant_set_id);
      setVariantMessage({
        tone: replay.status === "verified" ? "saved" : "error",
        text: replay.status === "verified"
          ? "Replay verified all three stored content hashes."
          : "Replay found an artifact mismatch. Do not use this bundle for comparison.",
      });
    } catch (error) {
      setVariantMessage({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to replay this comparison bundle.",
      });
    } finally {
      setVariantBusy(false);
    }
  }

  const firstReadinessBlocker = readinessAttention.find((check) => readinessGate?.blocking_checks.includes(check.check_id));
  const nextAction = !loading && readinessGate?.status === "fail"
    ? { step: "01", eyebrow: "Resolve the contract", title: `Repair ${contestFormat} ${optimizerObjective} readiness`, detail: firstReadinessBlocker?.message ?? readinessGate.message, label: "Open Operations", view: "workspace" as ViewMode }
    : !loading && predictions.length === 0
    ? { step: "01", eyebrow: "Establish the baseline", title: "Build the slate projection set", detail: "The twin needs a current player distribution before it can reason about risk or opportunity.", label: "Open Model Workbench", view: "model-workbench" as ViewMode }
    : !loading && ownership.length === 0
      ? { step: "02", eyebrow: "Model the field", title: "Add expected ownership", detail: "GPP posture is incomplete until the system understands how the field is likely to behave.", label: "Open Operations", view: "workspace" as ViewMode }
      : !loading && !newsReport
        ? { step: "03", eyebrow: "Add live context", title: "Review today's intelligence", detail: "Capture the slate-moving information that projections alone cannot explain.", label: "Open Intelligence", view: "news-brief" as ViewMode }
        : !optimizerReady
          ? { step: "04", eyebrow: "Create candidates", title: "Generate the first portfolio", detail: "Turn the current model and field assumptions into inspectable cash or GPP candidates.", label: "Open Operations", view: "workspace" as ViewMode }
          : { step: "05", eyebrow: "Prepare execution", title: "Validate and deliver the portfolio", detail: "Map candidates to paid entries, resolve blockers, and generate the upload artifact.", label: "Open Delivery", view: "contest-workflow" as ViewMode };

  return (
    <main className="digital-twin">
      <section className="twin-hero">
        <div className="twin-hero-copy">
          <p className="twin-kicker"><i /> Digital Twin · Live slate intelligence</p>
          <h1>Your slate,<br /><em>interpreted.</em></h1>
          <p className="twin-lead">A single decision layer combining what the models know, what the field may do, and what you have taught the system to value.</p>
          <div className="twin-context-row">
            <span>{season} season</span><b>·</b><span>Week {week}</span><b>·</b><span>{formatSlate(slate)}</span>
          </div>
        </div>

        <div className="twin-orbit-card">
          <div className="twin-score" style={{ "--twin-score": `${readinessScore * 3.6}deg` } as React.CSSProperties}>
            <div><strong>{loading ? "—" : readinessScore}</strong><span>Slate readiness</span></div>
          </div>
          <div className="twin-layer-list">
            <div><span>Model layer</span><strong className={predictions.length > 0 ? "good" : ""}>{predictions.length > 0 ? "Online" : "Waiting"}</strong></div>
            <div><span>Human layer</span><strong className={activeBeliefs.length > 0 || feedbackSummary.total > 0 ? "good" : ""}>{activeBeliefs.length > 0 ? `${activeBeliefs.length} beliefs active` : feedbackSummary.total > 0 ? `${feedbackSummary.total} signals taught` : "Listening"}</strong></div>
            <div><span>Combined layer</span><strong className={readinessGate?.status === "pass" ? "good" : ""}>{readinessGate?.status === "fail" ? "Blocked" : readinessGate?.status === "warn" ? "Ready with warnings" : readinessGate?.status === "pass" ? "Decision ready" : "Building context"}</strong></div>
          </div>
        </div>
      </section>

      <section className="twin-next-action">
        <span className="twin-next-number">{nextAction.step}</span>
        <div><small>{nextAction.eyebrow}</small><strong>{nextAction.title}</strong><p>{nextAction.detail}</p></div>
        <button type="button" onClick={() => onNavigate(nextAction.view)}>{nextAction.label}<span aria-hidden="true">→</span></button>
      </section>

      {errors.length > 0 && <div className="twin-source-note" role="status"><span>Partial context</span>{errors.join(" · ")}</div>}

      <section className="twin-grid">
        <article className="twin-panel twin-readiness-panel">
          <div className="twin-panel-head"><div><span>System state</span><h2>Decision readiness</h2></div><strong className={`twin-gate-status ${readinessGate?.status ?? "loading"}`}>{readinessGate ? `${readinessGate.status} · ${readinessGate.score}` : "refreshing"}</strong></div>
          {readiness && readinessGate && (
            <div className="twin-readiness-contract">
              <div className="twin-contract-summary">
                <span>{contestFormat} {optimizerObjective} gate</span>
                <div>
                  <b className="pass">{readinessGate.summary.pass} pass</b>
                  <b className="warn">{readinessGate.summary.warn} warn</b>
                  <b className="fail">{readinessGate.summary.fail} fail</b>
                </div>
              </div>
              {readinessAttention.length > 0 ? (
                <div className="twin-contract-checks">
                  {readinessAttention.map((check) => (
                    <div key={check.check_id}>
                      <i className={check.status} />
                      <span><strong>{check.category}</strong><small>{check.message}</small></span>
                      <b>{check.status}</b>
                    </div>
                  ))}
                </div>
              ) : <div className="twin-contract-clear"><i>✓</i><span><strong>All applicable checks pass</strong><small>{readinessGate.message}</small></span></div>}
            </div>
          )}
          <div className="twin-source-list">
            {sourceStates.map((source) => (
              <button type="button" key={source.label} onClick={() => onNavigate(source.action)}>
                <i className={sourceTone(source.status)} />
                <span><strong>{source.label}</strong><small>{source.detail}</small></span>
                <b>{source.value}</b><em aria-hidden="true">↗</em>
              </button>
            ))}
          </div>
        </article>

        <article className="twin-panel twin-posture-panel">
          <div className="twin-panel-head"><div><span>Portfolio lens</span><h2>Cash & GPP posture</h2></div><button type="button" onClick={() => onNavigate("war-room")}>Open War Room ↗</button></div>
          <div className="twin-posture-grid">
            <section>
              <span>Cash stability</span><strong>{cashLineupSummary ? cashLineupSummary.projected_floor_p10.toFixed(1) : predictions.length > 0 ? averageMedian.toFixed(1) : "—"}</strong><small>{cashLineupSummary ? `Lineup P10 floor · ${cashLineupSummary.objective_id}` : "Average player median in the loaded pool"}</small>
              <div className="posture-meter"><i style={{ width: `${Math.min(100, cashLineupSummary ? cashLineupSummary.projected_floor_p10 / 1.5 : averageMedian * 4)}%` }} /></div>
              <p>{cashLineupSummary
                ? `${(cashLineupSummary.average_role_certainty * 100).toFixed(0)}% average role certainty · ${cashLineupSummary.total_fragility_penalty.toFixed(1)} total fragility penalty${cashLineupSummary.missing_projection_players.length ? ` · ${cashLineupSummary.missing_projection_players.length} missing projection input` : ""}.`
                : predictions.length > 0 ? "Calibrated floors are ready. Generate a classic cash lineup to inspect stability, role certainty, and fragility." : "Waiting for a projection distribution."}</p>
            </section>
            <section className="gpp">
              <span>GPP ceiling pool</span><strong>{predictions.length > 0 ? ceilingPool : "—"}</strong><small>Players at 20+ projected P90</small>
              <div className="posture-meter"><i style={{ width: `${Math.min(100, ceilingPool * 5)}%` }} /></div>
              <p>{ownership.length > 0
                ? `${lowOwnedCeiling} low-owned ceiling candidates lead the watchlist.${ownershipDiagnostics?.gateStatus === "blocked" ? " Ownership remains a challenger until its sparse format/slot gate clears." : ""}`
                : "Ownership is required before leverage can be interpreted."}</p>
            </section>
          </div>
        </article>

        <article className="twin-panel twin-watchlist-panel">
          <div className="twin-panel-head"><div><span>Model × field</span><h2>Decision watchlist</h2></div><small>Ceiling gap with ownership pressure</small></div>
          <div className="twin-watchlist">
            {decisionWatchlist.length > 0 ? decisionWatchlist.map((row, index) => (
              <button type="button" key={`${row.player}-${row.position}`} onClick={() => onNavigate("war-room")}>
                <b>{String(index + 1).padStart(2, "0")}</b>
                <span><strong>{row.player}</strong><small>{row.position} · {row.team}</small></span>
                <span><strong>+{row.ceilingGap.toFixed(1)}</strong><small>ceiling gap</small></span>
                <span><strong>{row.ownership > 0 ? `${row.ownership.toFixed(1)}%` : "—"}</strong><small>ownership</small></span>
                <em aria-hidden="true">↗</em>
              </button>
            )) : <div className="twin-empty"><strong>No combined watchlist yet</strong><p>Load projections and ownership to reveal decision candidates.</p></div>}
          </div>
        </article>

        <aside className="twin-panel twin-memory-panel">
          <div className="twin-panel-head"><div><span>Personal layer</span><h2>Twin memory</h2></div><strong>{activeBeliefs.length} active</strong></div>
          <div className="twin-memory-statement"><span>Memory contract</span><strong>Record → preview → approve</strong><p>Your beliefs remain versioned evidence. Nothing changes a model or portfolio until you approve an impact preview.</p></div>
          <div className="twin-feedback-grid">
            <div><span>Playbook</span><strong>{activeBeliefs.filter((belief) => belief.scope_type === "global").length}</strong></div>
            <div><span>Slate views</span><strong>{activeBeliefs.filter((belief) => belief.scope_type === "weekly").length}</strong></div>
            <div><span>Game + player</span><strong>{activeBeliefs.filter((belief) => belief.scope_type === "game" || belief.scope_type === "player").length}</strong></div>
            <div><span>Signals taught</span><strong>{feedbackSummary.total}</strong></div>
          </div>
          <button className="twin-teach-button" type="button" onClick={() => document.getElementById("thought-studio")?.scrollIntoView({ behavior: "smooth" })}><span>Open Thought Studio</span><i aria-hidden="true">→</i></button>
          <div className="twin-guardrail"><i>✓</i><span><strong>Approval guardrail</strong><small>Preview consequences first; only approved modifiers can enter a future combined variant.</small></span></div>
        </aside>
      </section>

      <section className="twin-thought-studio" id="thought-studio">
        <header className="thought-studio-head">
          <div>
            <span>Human intelligence workspace</span>
            <h2>Thought Studio</h2>
            <p>Give the Twin your principles, slate interpretation, and points of disagreement—in your own words.</p>
          </div>
          <div className="thought-studio-metrics" aria-label="Twin memory summary">
            <div><strong>{thoughtCaptures.length}</strong><span>Raw captures</span></div>
            <div><strong>{pendingThoughtCandidates.length}</strong><span>Review queue</span></div>
            <div><strong>{activeBeliefs.length}</strong><span>Active beliefs</span></div>
            <div><strong>{beliefVersionCount}</strong><span>Memory versions</span></div>
          </div>
        </header>

        <section className="raw-thought-inbox" aria-labelledby="raw-thought-title">
          <form className="raw-thought-capture" onSubmit={captureRawThought}>
            <div className="raw-thought-head">
              <div><span>Zero-friction capture</span><h3 id="raw-thought-title">Brain dump inbox</h3></div>
              <i aria-hidden="true">RAW</i>
            </div>
            <p className="raw-thought-lead">Write naturally. One sentence or an entire slate thesis—the original is preserved before anything is interpreted.</p>

            <div className="raw-context-switch" role="group" aria-label="Raw thought context">
              {RAW_THOUGHT_CONTEXTS.map((context) => (
                <button
                  type="button"
                  key={context.value}
                  className={rawThoughtDraft.context === context.value ? "active" : ""}
                  onClick={() => setRawThoughtDraft((current) => ({ ...current, context: context.value, subject: context.value === "player" ? current.subject : "" }))}
                >
                  <strong>{context.label}</strong><small>{context.detail}</small>
                </button>
              ))}
            </div>

            {rawThoughtDraft.context === "player" && (
              <label className="raw-player-field">
                <span>Player anchor</span>
                <input
                  list="thought-inbox-players"
                  value={rawThoughtDraft.subject}
                  onChange={(event) => setRawThoughtDraft((current) => ({ ...current, subject: event.target.value }))}
                  placeholder="Type or choose a player"
                  maxLength={160}
                  required
                />
                <datalist id="thought-inbox-players">
                  {selectableImpactPlayers.map((player) => <option value={player.player_display_name} key={player.player_id} />)}
                </datalist>
              </label>
            )}

            <label className="raw-thought-field">
              <span>Unfiltered thinking</span>
              <textarea
                value={rawThoughtDraft.rawText}
                onChange={(event) => setRawThoughtDraft((current) => ({ ...current, rawText: event.target.value }))}
                placeholder={"Example:\nI think this slate is more concentrated than the field expects.\nLove the expanded role for a specific player.\nI want fewer lineups built around fragile chalk."}
                rows={7}
                maxLength={20000}
                required
              />
              <small>{rawThoughtDraft.rawText.length.toLocaleString()} / 20,000</small>
            </label>

            <div className="raw-capture-actions">
              <div><b>Guarded intake</b><span>Drafts only · no projection or lineup impact</span></div>
              <button type="submit" disabled={!canCaptureRawThought || thoughtCaptureBusy}>{thoughtCaptureBusy ? "Preserving…" : "Preserve & extract"}<i aria-hidden="true">↗</i></button>
            </div>
            {thoughtCaptureMessage && <p className={`raw-thought-message ${thoughtCaptureMessage.tone}`} aria-live="polite">{thoughtCaptureMessage.text}</p>}
          </form>

          <article className="raw-thought-queue">
            <div className="raw-thought-head">
              <div><span>Human review gate</span><h3>Extraction queue</h3></div>
              <b>{pendingThoughtCandidates.length} pending</b>
            </div>
            <p className="raw-thought-lead">The extractor suggests scope and posture. You decide what deserves a place in memory.</p>

            <div className="thought-candidate-list">
              {pendingThoughtCandidates.length > 0 ? pendingThoughtCandidates.slice(0, 8).map((candidate) => (
                <section className={`thought-candidate ${reviewingCandidateId === candidate.candidate_id ? "reviewing" : ""}`} key={candidate.candidate_id}>
                  <div className="thought-candidate-tags">
                    <span>{scopeLabel(candidate.scope_type)}</span>
                    {candidate.subject_label && <strong>{candidate.subject_label}</strong>}
                    <i className={candidate.direction}>{candidate.direction}</i>
                  </div>
                  <p>{candidate.thought_text}</p>
                  <small>{candidate.extraction_reason}</small>
                  <div className="thought-candidate-actions">
                    <span>Starter calibration · {candidate.strength}/5 · {candidate.confidence}%</span>
                    <div>
                      <button type="button" className="reject" onClick={() => rejectThoughtCandidate(candidate)} disabled={thoughtCaptureBusy}>Reject</button>
                      <button type="button" className="review" onClick={() => reviewThoughtCandidate(candidate)} disabled={thoughtCaptureBusy}>Review & edit</button>
                    </div>
                  </div>
                </section>
              )) : (
                <div className="thought-queue-empty"><span>✓</span><strong>Review queue clear</strong><p>Paste a brain dump and the Twin will stage candidates here without applying them.</p></div>
              )}
              {pendingThoughtCandidates.length > 8 && <p className="thought-queue-overflow">{pendingThoughtCandidates.length - 8} more candidates are safely preserved in the queue.</p>}
            </div>

            {latestThoughtCapture && (
              <details className="raw-capture-receipt">
                <summary><span>Latest raw capture preserved</span><time>{new Date(latestThoughtCapture.created_at).toLocaleString()}</time></summary>
                <p>{latestThoughtCapture.raw_text}</p>
                <div><span>{latestThoughtCapture.extraction_policy_id}</span><span>{latestThoughtCapture.candidates.length} candidates</span></div>
                {latestThoughtCapture.notices.map((notice) => <small key={notice}>{notice}</small>)}
              </details>
            )}
          </article>
        </section>

        <div className="thought-studio-layout">
          <form className="thought-composer" id="thought-composer" onSubmit={saveThought}>
            <div className="thought-composer-head">
              <div><span>{reviewingCandidateId ? "Review gate" : editingBeliefId ? "Revising memory" : "Capture a belief"}</span><h3>{reviewingCandidateId ? "Confirm the extracted meaning" : editingBeliefId ? `Create version ${beliefs.find((belief) => belief.belief_id === editingBeliefId)?.belief_version ? (beliefs.find((belief) => belief.belief_id === editingBeliefId)?.belief_version ?? 0) + 1 : 2}` : "What do you see?"}</h3></div>
              {reviewingCandidateId && <button type="button" onClick={cancelCandidateReview}>Cancel review</button>}
              {editingBeliefId && <button type="button" onClick={cancelBeliefRevision}>Cancel revision</button>}
            </div>

            <div className="thought-lanes" role="group" aria-label="Belief scope">
              {THOUGHT_LANES.map((lane) => (
                <button
                  type="button"
                  key={lane.scope}
                  className={thoughtDraft.scope === lane.scope ? "active" : ""}
                  disabled={Boolean(editingBeliefId)}
                  onClick={() => setThoughtDraft((current) => ({
                    ...current,
                    scope: lane.scope,
                    seasonContext: lane.scope === "season" ? Math.max(season, new Date().getFullYear()) : season,
                    subject: "",
                    retrospective: lane.scope === "global" || lane.scope === "contest_profile" ? false : (lane.scope === "season" ? Math.max(season, new Date().getFullYear()) : season) < new Date().getFullYear(),
                  }))}
                >
                  {lane.shortLabel}
                </button>
              ))}
            </div>
            <p className="thought-lane-description"><strong>{activeLane.label}</strong>{activeLane.description}</p>

            {thoughtDraft.scope === "season" && (
              <label className="thought-field thought-season-field">
                <span>Season</span>
                <input
                  type="number"
                  min="2000"
                  max="2100"
                  value={thoughtDraft.seasonContext}
                  onChange={(event) => {
                    const nextSeason = Number(event.target.value);
                    setThoughtDraft((current) => ({
                      ...current,
                      seasonContext: nextSeason,
                      retrospective: nextSeason < new Date().getFullYear(),
                    }));
                  }}
                  required
                />
              </label>
            )}

            {subjectRequired && (
              <label className="thought-field">
                <span>{thoughtDraft.scope === "player" ? "Player" : "Game or matchup"}</span>
                <input
                  value={thoughtDraft.subject}
                  onChange={(event) => setThoughtDraft((current) => ({ ...current, subject: event.target.value }))}
                  placeholder={thoughtDraft.scope === "player" ? "Player name" : "Example: BUF at KC"}
                  maxLength={160}
                  required
                />
              </label>
            )}

            <label className="thought-field thought-primary-field">
              <span>Your thought</span>
              <textarea
                value={thoughtDraft.thought}
                onChange={(event) => setThoughtDraft((current) => ({ ...current, thought: event.target.value }))}
                placeholder="Write what you believe, why the market or model may be wrong, and what would change your mind."
                rows={5}
                maxLength={5000}
                required
              />
              <small>{thoughtDraft.thought.length.toLocaleString()} / 5,000</small>
            </label>

            <div className="thought-direction-block">
              <span>Decision posture</span>
              <div role="group" aria-label="Belief direction">
                {THOUGHT_DIRECTIONS.map((direction) => (
                  <button
                    type="button"
                    key={direction.value}
                    className={thoughtDraft.direction === direction.value ? `active ${direction.value}` : ""}
                    onClick={() => setThoughtDraft((current) => ({ ...current, direction: direction.value }))}
                  >
                    {direction.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="thought-calibration-grid">
              <label>
                <span>Conviction <b>{thoughtDraft.strength} / 5</b></span>
                <input type="range" min="1" max="5" step="1" value={thoughtDraft.strength} onChange={(event) => setThoughtDraft((current) => ({ ...current, strength: Number(event.target.value) }))} />
              </label>
              <label>
                <span>Confidence <b>{thoughtDraft.confidence}%</b></span>
                <input type="range" min="0" max="100" step="5" value={thoughtDraft.confidence} onChange={(event) => setThoughtDraft((current) => ({ ...current, confidence: Number(event.target.value) }))} />
              </label>
            </div>

            <div className="thought-context-strip">
              <span>{thoughtDraft.scope === "global" ? "All future slates" : thoughtDraft.scope === "contest_profile" ? `${contestFormat} · ${optimizerObjective}` : thoughtDraft.scope === "season" ? `${thoughtDraft.seasonContext} season outlook` : `${season} · Week ${week} · ${formatSlate(slate)}`}</span>
              <i>{thoughtDraft.direction}</i>
              <b>No model impact</b>
            </div>

            <label className="thought-field">
              <span>Evidence or conditions <em>Optional</em></span>
              <textarea
                className="thought-evidence"
                value={thoughtDraft.evidence}
                onChange={(event) => setThoughtDraft((current) => ({ ...current, evidence: event.target.value }))}
                placeholder="News, matchup evidence, data, or the condition that would invalidate this view."
                rows={2}
                maxLength={5000}
              />
            </label>

            <div className="thought-governance-row">
              <label><span>Expires after</span><input type="date" value={thoughtDraft.expiresOn} onChange={(event) => setThoughtDraft((current) => ({ ...current, expiresOn: event.target.value }))} /></label>
              {!["global", "contest_profile"].includes(thoughtDraft.scope) && (
                <label className="thought-check"><input type="checkbox" checked={thoughtDraft.retrospective} onChange={(event) => setThoughtDraft((current) => ({ ...current, retrospective: event.target.checked }))} /><span>Retrospective replay thought</span></label>
              )}
            </div>

            <div className="thought-submit-row">
              <div aria-live="polite">{beliefMessage && <span className={beliefMessage.tone}>{beliefMessage.text}</span>}</div>
              <button type="submit" disabled={!canSaveThought || beliefSaving}>{beliefSaving ? "Saving…" : reviewingCandidateId ? "Accept into memory" : editingBeliefId ? "Save new version" : "Commit to memory"}<i aria-hidden="true">→</i></button>
            </div>
          </form>

          <article className="thought-library">
            <div className="thought-library-head">
              <div><span>Versioned memory</span><h3>Your decision record</h3></div>
              <div className="thought-status-toggle" role="group" aria-label="Belief status filter">
                <button type="button" className={beliefStatusFilter === "current" ? "active" : ""} onClick={() => setBeliefStatusFilter("current")}>Current</button>
                <button type="button" className={beliefStatusFilter === "all" ? "active" : ""} onClick={() => setBeliefStatusFilter("all")}>All statuses</button>
              </div>
            </div>

            <div className="thought-library-filters" role="group" aria-label="Belief scope filter">
              <button type="button" className={beliefScopeFilter === "all" ? "active" : ""} onClick={() => setBeliefScopeFilter("all")}>All</button>
              {THOUGHT_LANES.map((lane) => <button type="button" key={lane.scope} className={beliefScopeFilter === lane.scope ? "active" : ""} onClick={() => setBeliefScopeFilter(lane.scope)}>{lane.shortLabel}</button>)}
            </div>

            <div className="thought-card-list">
              {visibleBeliefs.length > 0 ? visibleBeliefs.map((belief) => {
                const latestImpact = impactPreviews.find((preview) => preview.belief_version_id === belief.belief_version_id);
                const impactOpen = impactBeliefId === belief.belief_id;
                return (
                  <section className={`thought-card ${belief.status === "inactive" || belief.is_expired ? "inactive" : ""} ${impactOpen ? "impact-open" : ""}`} key={belief.belief_id}>
                    <div className="thought-card-topline">
                      <div><span>{scopeLabel(belief.scope_type)}</span><i className={belief.direction}>{belief.direction}</i>{belief.is_retrospective && <em>Replay</em>}</div>
                      <b>{belief.is_expired ? "Expired" : belief.status}</b>
                    </div>
                    <p>{belief.thought_text}</p>
                    {belief.evidence_text && <blockquote>{belief.evidence_text}</blockquote>}
                    <div className="thought-card-context"><span>{beliefContext(belief)}</span><span>Conviction {belief.strength}/5 · {belief.confidence}% confidence</span></div>
                    <div className="thought-card-foot">
                      <span>v{belief.belief_version} · {latestImpact?.status ?? belief.impact_status.replaceAll("_", " ")}</span>
                      <div>
                        {belief.status === "active" && !belief.is_expired && (
                          <button type="button" className="impact-preview-trigger" onClick={() => openImpactPreview(belief)} disabled={impactBusy || (!latestImpact && predictions.length === 0)}>{impactOpen ? "Close impact" : latestImpact ? "View impact" : "Preview impact"}</button>
                        )}
                        <button type="button" onClick={() => beginBeliefRevision(belief)} disabled={beliefSaving}>Revise</button>
                        <button type="button" onClick={() => changeBeliefStatus(belief)} disabled={beliefSaving}>{belief.status === "active" ? "Deactivate" : "Restore"}</button>
                      </div>
                    </div>

                    {impactOpen && (
                      <div className="belief-impact-panel">
                        <div className="belief-impact-head">
                          <div><span>Guarded simulation</span><strong>Belief consequence preview</strong></div>
                          <b className={latestImpact?.status ?? "draft"}>{latestImpact?.status ?? "Draft"}</b>
                        </div>
                        <div className="belief-impact-target">
                          <label>
                            <span>Apply this thought to</span>
                            <select value={impactTargetPlayerId} onChange={(event) => setImpactTargetPlayerId(event.target.value)} disabled={impactBusy}>
                              <option value="">Select a projected player</option>
                              {selectableImpactPlayers.map((player) => (
                                <option value={player.player_id} key={player.player_id}>{player.player_display_name} · {player.position} · {player.recent_team}</option>
                              ))}
                            </select>
                          </label>
                          <button type="button" onClick={() => generateImpactPreview(belief)} disabled={!impactTargetPlayerId || impactBusy}>{impactBusy ? "Calculating…" : latestImpact ? "Run new preview" : "Calculate impact"}</button>
                        </div>

                        {latestImpact ? (
                          <>
                            <div className="belief-impact-summary">
                              <div><span>Player</span><strong>{latestImpact.target_label}</strong></div>
                              <div><span>Policy move</span><strong className={latestImpact.adjustment_pct >= 0 ? "positive" : "negative"}>{latestImpact.adjustment_pct >= 0 ? "+" : ""}{(latestImpact.adjustment_pct * 100).toFixed(2)}%</strong></div>
                              <div><span>Model safety</span><strong>Base untouched</strong></div>
                            </div>
                            <div className="belief-impact-metrics">
                              {[
                                ["Mean projection", latestImpact.baseline.projection_mean, latestImpact.proposed.projection_mean, " pts"],
                                ["Floor · P10", latestImpact.baseline.projection_p10, latestImpact.proposed.projection_p10, " pts"],
                                ["Ceiling · P90", latestImpact.baseline.projection_p90, latestImpact.proposed.projection_p90, " pts"],
                                ["Field ownership", latestImpact.baseline.field_ownership_pct, latestImpact.proposed.field_ownership_pct, "%"],
                                ["Portfolio exposure", latestImpact.baseline.portfolio_exposure_pct, latestImpact.proposed.portfolio_exposure_pct, "%"],
                                ["Optimal probability", latestImpact.baseline.optimal_lineup_probability, latestImpact.proposed.optimal_lineup_probability, "%"],
                              ].map(([label, before, after, suffix]) => (
                                <div key={String(label)}>
                                  <span>{String(label)}</span>
                                  <p><del>{impactValue(before as number | null, String(suffix))}</del><i>→</i><strong>{impactValue(after as number | null, String(suffix))}</strong></p>
                                </div>
                              ))}
                            </div>
                            <div className="belief-impact-notices">
                              {latestImpact.notices.map((notice) => <p key={notice}>{notice}</p>)}
                            </div>
                            {latestImpact.status === "pending" ? (
                              <label className="belief-impact-note">
                                <span>Decision note <em>Optional</em></span>
                                <textarea value={impactDecisionNote} onChange={(event) => setImpactDecisionNote(event.target.value)} placeholder="Why does this consequence match—or miss—your intent?" rows={2} maxLength={5000} />
                              </label>
                            ) : latestImpact.note_text ? (
                              <blockquote className="belief-impact-recorded-note">{latestImpact.note_text}</blockquote>
                            ) : null}
                            <div className="belief-impact-actions">
                              <span>{latestImpact.status === "pending" ? "Approve only if this consequence matches your intent." : `Decision recorded · ${latestImpact.status}`}</span>
                              {latestImpact.status === "pending" && (
                                <div>
                                  <button type="button" className="reject" onClick={() => decideImpactPreview(latestImpact, "rejected")} disabled={impactBusy}>Reject</button>
                                  <button type="button" className="approve" onClick={() => decideImpactPreview(latestImpact, "approved")} disabled={impactBusy}>Approve modifier</button>
                                </div>
                              )}
                            </div>
                          </>
                        ) : (
                          <div className="belief-impact-empty"><strong>No assumptions have moved.</strong><p>Select one player to see the deterministic before/after contract before any modifier can be approved.</p></div>
                        )}
                        {impactMessage && <p className={`belief-impact-message ${impactMessage.tone}`}>{impactMessage.text}</p>}
                      </div>
                    )}
                  </section>
                );
              }) : (
                <div className="thought-library-empty">
                  <span>Memory is listening</span>
                  <strong>{beliefs.length > 0 ? "No beliefs match this view." : "Your first belief starts the Twin."}</strong>
                  <p>Capture one strong principle or disagreement. The original wording will remain in the audit trail.</p>
                </div>
              )}
            </div>
          </article>
        </div>

        <article className="twin-variant-lab">
          <div className="twin-variant-head">
            <div><span>DT-703 · immutable comparison</span><h3>Model × Human × Combined</h3><p>Freeze the exact model snapshot, approved human modifiers, and their computed combination without changing the base projection.</p></div>
            <button type="button" onClick={freezeVariantSet} disabled={variantBusy || predictions.length === 0}>{variantBusy ? "Working…" : "Freeze three variants"}</button>
          </div>

          {variantSets[0] ? (
            <div className="twin-variant-body">
              <div className="twin-variant-cards">
                <div><span>Model only</span><strong>{variantSets[0].comparison.player_count} players</strong><small>Exact {variantSets[0].projection_run_id}</small></div>
                <div><span>Human only</span><strong>{variantSets[0].comparison.players_with_human_input} approved</strong><small>Decision modifiers remain a separate artifact</small></div>
                <div><span>Combined</span><strong>{variantSets[0].comparison.players_unchanged} unchanged</strong><small>Only approved player inputs are composed</small></div>
              </div>
              <div className="twin-variant-comparison">
                <div className="twin-variant-meta"><span>Latest bundle · {new Date(variantSets[0].created_at).toLocaleString()}</span><button type="button" onClick={() => verifyVariantSet(variantSets[0])} disabled={variantBusy}>Verify replay</button></div>
                {variantSets[0].comparison.changed_players.length > 0 ? (
                  <div className="twin-variant-rows">
                    {variantSets[0].comparison.changed_players.slice(0, 6).map((row) => (
                      <div key={row.player_id}>
                        <strong>{row.player_label}</strong>
                        <span>{row.model_projection_mean?.toFixed(2) ?? "—"}</span>
                        <i>× {row.projection_multiplier.toFixed(4)}</i>
                        <b>{row.combined_projection_mean?.toFixed(2) ?? "—"}</b>
                      </div>
                    ))}
                  </div>
                ) : <p className="twin-variant-empty">No approved DT-702 modifiers existed at this bundle's decision cutoff. Model and combined projections are intentionally identical.</p>}
              </div>
            </div>
          ) : <p className="twin-variant-empty">No comparison bundle has been frozen for this slate and mode.</p>}
          {variantMessage && <p className={`twin-variant-message ${variantMessage.tone}`} aria-live="polite">{variantMessage.text}</p>}
        </article>
      </section>
    </main>
  );
}
