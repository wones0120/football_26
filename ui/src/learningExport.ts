import type { WeeklyLearningReport } from "./api.ts";

type Row = Record<string, unknown>;
const obj = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
const rows = (value: unknown): Row[] => Array.isArray(value) ? value.map(obj) : [];

const cell = (value: unknown): string => value == null || value === ""
  ? "—"
  : String(value).replaceAll("|", "\\|").replace(/[\r\n]+/g, " ");

const points = (value: unknown): string => typeof value === "number" && Number.isFinite(value)
  ? value.toFixed(2)
  : "—";

const list = (values: string[]): string[] => values.length
  ? values.map((value) => `- ${value.replace(/[\r\n]+/g, " ")}`)
  : ["- None recorded"];

const table = (headers: string[], rows: unknown[][]): string[] => [
  `| ${headers.join(" | ")} |`,
  `| ${headers.map(() => "---").join(" | ")} |`,
  ...rows.map((row) => `| ${row.map(cell).join(" | ")} |`),
];

export function weeklyLearningReportMarkdown(report: WeeklyLearningReport): string {
  const lines: string[] = [
    `# NFL Week ${report.week}, ${report.season}: post-slate learning report`,
    "",
    `DraftKings user: ${cell(report.entry_user)}  `,
    `Generated: ${cell(report.generated_at)}  `,
    `Status: ${report.status}  `,
    `Report ID: ${report.report_id}  `,
    `Evidence hash: ${report.evidence_hash}`,
    "",
    "## How to analyze this report",
    "",
    "Compare predictions with observed results, identify recurring misses and lineup patterns, and prioritize testable hypotheses. Treat a single week's outcomes as diagnostic, not proof of a model defect. Account for missing evidence and repeated player observations across entries. Recommend model or rule changes only with time-safe validation; do not use post-game information as a pre-game feature.",
    "",
    "## Week summary",
    "",
    ...table(["Metric", "Value"], [
      ["Slates", report.summary.slates],
      ["Contests entered", report.summary.contests_entered],
      ["Entries", report.summary.entries],
      ["Weekly stats records pulled", report.summary.weekly_stats?.rows_raw ?? "Unavailable"],
      ["Weekly stats ingest run", report.summary.weekly_stats?.ingest_run_id ?? "Unavailable"],
      ["Identity complete entries", report.summary.identity_complete_entries],
      ["Matched optimizer entries", report.summary.matched_optimizer_entries],
      ["Entries with OPT-007 control", report.summary.entries_with_opt_007],
      ["Duplicate entries", report.summary.duplicate_entries],
      ["Entry-weighted projection observations", report.summary.entry_weighted_projection_observations],
      ["Entry-weighted projection MAE", points(report.summary.entry_weighted_projection_mae)],
      ["Entry-weighted projection RMSE", points(report.summary.entry_weighted_projection_rmse)],
    ]),
    "",
    report.interpretation,
    "",
    "Entry-weighted projection observations can count the same player in multiple entries; they are not independent training examples.",
  ];

  lines.push("", "## Optimizer effectiveness", "",
    "Original saved candidate pools are scored with canonical player actuals. `Unscored` candidates and missing field evidence remain explicit; observed best and regret are bounds when actuals are incomplete.", "");
  const effectivenessRows: unknown[][] = [];
  for (const slate of report.slate_reports) {
    const effectiveness = slate.optimizer_effectiveness;
    if (!effectiveness) {
      effectivenessRows.push([slate.slate, "unavailable", "no effectiveness report", "—", "—", "—", "—", "—", "—", "—", "—"]);
      continue;
    }
    const runRows = rows(effectiveness.runs).filter((run) => run.run_scope == null || run.run_scope === "entry_linked");
    if (!runRows.length) {
      effectivenessRows.push([slate.slate, "unavailable", "no canonical run match", "—", "—", "—", points(effectiveness.best_entered_slate_actual), "—", "—", "—", "—"]);
    }
    for (const run of runRows) {
      const fields = obj(run.field);
      const firstField = obj(Object.values(fields)[0]);
      effectivenessRows.push([
        slate.slate, String(run.optimizer_run_id ?? "unavailable").slice(0, 8),
        `${cell(run.status)} (${cell(obj(run.candidate_pool).status)})`,
        run.generated_count == null ? "—" : `${run.unique_scored_roster_count ?? run.scored_count ?? 0} / ${run.unique_roster_count ?? run.generated_count}`,
        points(run.best_generated_actual), points(run.best_selected_actual), points(run.best_entered_actual),
        points(firstField.winner), points(obj(firstField.thresholds).top_1_percent),
        points(firstField.cash_line), points(run.selection_regret_observed),
      ]);
    }
  }
  lines.push(...table(["Slate", "Run", "Pool status", "Scored / generated rosters", "Best generated", "Best selected", "Best entered", "Winner", "Top 1%", "Cash", "Observed selection regret"], effectivenessRows));

  for (const slate of report.slate_reports) {
    const effectiveness = slate.optimizer_effectiveness;
    if (!effectiveness) continue;
    if (effectiveness.entered_field_comparisons?.length) lines.push("", `### ${slate.slate.replaceAll("_", " ")} entered field gaps`, "",
      ...table(["Contest", "Entry", "Actual", "From winner", "From top 1%", "From top 5%", "From top 10%", "From cash"],
        effectiveness.entered_field_comparisons.map((entry) => [entry.contest_id, entry.entry_id,
          points(entry.entry_points), points(entry.points_from_winner), points(entry.points_from_top_1_percent),
          points(entry.points_from_top_5_percent), points(entry.points_from_top_10_percent),
          points(entry.points_from_cash)])), "");
    const otherRunCount = rows(effectiveness.runs).filter((run) => run.run_scope === "other_completed_saved_pool").length;
    const policy = obj(effectiveness.inclusion_policy);
    if (policy.policy_id) lines.push(`${cell(policy.included_run_count)} entry-linked or requested diagnostic runs included; ${cell(policy.excluded_run_count)} unrelated completed runs excluded. Policy: ${cell(policy.policy_id)}.`, "");
    if (otherRunCount) lines.push("", `${otherRunCount} additional completed runs with original saved pools were evaluated for this slate; their candidate-level diagnostics are in the structured JSON.`, "");
    for (const run of rows(effectiveness.runs).filter((item) => item.run_scope == null || item.run_scope === "entry_linked")) {
      const candidates = rows(run.candidates ?? run.candidate_preview);
      const detail = obj(run.candidate_detail);
      if (detail.url) lines.push(`Saved candidate drilldown: ${cell(detail.url)} · ${cell(detail.candidate_count)} candidates · evidence hash ${cell(detail.evidence_hash)}.`, "");
      const selected = candidates.filter((candidate) => obj(candidate.postgame).selected === true);
      const best = [...candidates].filter((candidate) => typeof obj(candidate.postgame).actual_points === "number")
        .sort((a, b) => Number(obj(b.postgame).actual_points) - Number(obj(a.postgame).actual_points))[0];
      lines.push("", `### ${slate.slate.replaceAll("_", " ")} · ${cell(run.strategy)} · ${cell(run.optimizer_run_id)}`, "",
        `Candidate generation: ${cell(run.generated_count)} saved variants, ${cell(run.unique_roster_count)} distinct rosters; ${cell(run.unique_scored_roster_count ?? run.scored_count)} distinct rosters scoreable; best scoreable ${points(run.best_generated_actual)}.`,
        `Candidate selection: best selected ${points(run.best_selected_actual)}; observed regret ${points(run.selection_regret_observed)}.`,
        `Entry execution: best matched entered ${points(run.best_entered_actual)}; observed entry regret ${points(run.entry_regret_observed)}.`, "");
      if (best) lines.push(`Best scoreable candidate: pregame rank ${cell(obj(best.pregame).selector_rank)}, actual ${points(obj(best.postgame).actual_points)}, projected mean ${points(obj(best.pregame).mean)}, summed player ceiling ${points(obj(best.pregame).p90)}, selector ${points(obj(best.pregame).objective_score)}.`, "");
      const comparison = obj(run.best_candidate_pregame_rank_comparison);
      if (Object.keys(comparison).length) lines.push(
        `Pregame rank comparison with selected rank ${cell(comparison.reference_selected_rank)}: selector delta ${points(comparison.objective_score_delta)}, mean delta ${points(comparison.mean_delta)}, summed player ceiling delta ${points(comparison.p90_sum_delta)}.`,
        "",
        ...table(["Objective component", "Candidate minus selected"],
          Object.entries(obj(comparison.objective_component_deltas)).map(([name, delta]) => [name, points(delta)])),
        "",
      );
      if (selected.length) lines.push(...table(["Selected pregame rank", "Actual", "Actual rank among scoreable", "Entered"],
        selected.map((candidate) => [obj(candidate.pregame).selector_rank, points(obj(candidate.postgame).actual_points),
          obj(candidate.postgame).actual_rank ?? (Array.isArray(obj(candidate.postgame).actual_rank_bounds)
            ? `${(obj(candidate.postgame).actual_rank_bounds as number[]).join("–")} (bounds)` : "unavailable"),
          obj(candidate.postgame).entered === true ? "yes" : "no"])), "");
      const topK = obj(run.top_k_capture);
      if (Object.keys(topK).length) lines.push(...table(["Selector top K", "Best eventual actual", "Scored / group"],
        [1, 3, 5, 10, 20].map((k) => [k, points(obj(topK[String(k)]).best_scored_actual),
          `${cell(obj(topK[String(k)]).scored)} / ${cell(obj(topK[String(k)]).size)}`])), "");
      const correlations = obj(run.correlations);
      if (Object.keys(correlations).length) lines.push(...table(["Pregame metric", "N", "Pearson", "Spearman"],
        Object.entries(correlations).map(([metric, values]) => [metric, obj(values).n,
          points(obj(values).pearson), points(obj(values).spearman)])), "");
      for (const [contestId, value] of Object.entries(obj(run.field))) {
        const field = obj(value);
        lines.push(`Contest ${contestId}: winner ${points(field.winner)}, top 1% ${points(obj(field.thresholds).top_1_percent)}, cash ${points(field.cash_line)}.`, "");
        const attainment = obj(field.attainment);
        if (Object.keys(attainment).length) lines.push(...table(["Threshold", "Generated scoreable", "Selected scoreable", "Entered scoreable"],
          Object.entries(attainment).map(([name, counts]) => [name, obj(counts).generated_scored,
            obj(counts).selected_scored, obj(counts).entered_scored])), "");
        const topField = obj(obj(run.top_field_constructions)[contestId]);
        const groups = obj(topField.groups);
        if (Object.keys(groups).length) lines.push("Top-field construction coverage:", "",
          ...table(["Field band", "Lineups incl. ties", "Canonically summarized", "Most common QB/Captain", "Most common stack/split"],
            Object.entries(groups).map(([band, raw]) => {
              const group = obj(raw);
              const leader = group.qb_stack_status === "not_applicable_showdown"
                ? (Array.isArray(group.captain_frequency) ? group.captain_frequency[0] as unknown[] | undefined : undefined)
                : (Array.isArray(group.qb_frequency) ? group.qb_frequency[0] as unknown[] | undefined : undefined);
              const construction = group.qb_stack_status === "not_applicable_showdown"
                ? (Array.isArray(group.showdown_team_split_frequency) ? group.showdown_team_split_frequency[0] as unknown[] | undefined : undefined)
                : (Array.isArray(group.qb_stack_family_frequency) ? group.qb_stack_family_frequency[0] as unknown[] | undefined : undefined);
              return [band, group.field_lineups_including_ties, group.canonical_lineups_summarized,
                leader ? `${cell(leader[0])} (${cell(leader[1])})` : "—",
                construction ? `${cell(construction[0])} (${cell(construction[1])})` : "—"];
            })), "");
        const constructions = obj(obj(run.construction_comparison)[contestId]);
        if (Object.keys(constructions).length) lines.push("Construction comparison:", "",
          ...table(["Group", "Lineups", "Avg salary left", "Avg actual ownership", "Avg <10% players", "Context coverage"],
            Object.entries(constructions).map(([name, raw]) => {
              const group = obj(raw);
              return [name, group.lineups, points(group.average_salary_left),
                points(group.average_total_actual_ownership),
                points(group.average_low_owned_players_under_10pct), group.context_complete_lineups];
            })), "");
      }
      const diagnostic = rows(run.diagnostic);
      if (diagnostic.length) lines.push("Diagnostic:", "", ...diagnostic.map((item) => `- ${cell(item.stage)}: ${cell(item.evidence)}`), "");
      if (run.status !== "complete") lines.push(`Evidence limit: ${cell(run.status)}; missing actual IDs ${cell((run.missing_actual_player_ids as string[] | undefined)?.length ?? 0)}.`, "");
    }
  }

  const history = rows(report.optimizer_effectiveness_history);
  lines.push("", "### Multi-week optimizer learning", "",
    "Classic and Showdown rows remain separate. Rates are descriptive and retain each contest strategy and evidence status.", "",
    ...(history.length ? table(["Week", "Slate", "Format", "Strategy", "Contest", "Status", "Best generated top %", "Best selected top %", "Best entered top %", "Regret", "Selector Spearman", "Pool cash rate", "Pool top 10%", "Pool top 1%", "Selected top 10%", "Selected top 1%"],
      history.map((item) => [`${cell(item.season)} W${cell(item.week)}`, item.slate, item.contest_format,
        item.strategy, item.contest_id, item.status, points(item.best_generated_top_percent),
        points(item.best_selected_top_percent), points(item.best_entered_top_percent),
        points(item.selection_regret_observed), points(item.selector_spearman),
        points(item.candidate_cash_rate_scored), points(item.candidate_top_10_rate_scored),
        points(item.candidate_top_1_rate_scored), points(item.selected_top_10_rate_scored),
        points(item.selected_top_1_rate_scored)])) : ["No comparable saved optimizer reports yet."]));
  const aggregate = obj(report.optimizer_correlation_aggregate);
  if (Object.keys(aggregate).length) lines.push("", "### Chronologically valid aggregate correlations", "",
    ...table(["Format", "Status", "Slates", "Candidates", "Selector Pearson", "Selector Spearman", "Mean Spearman", "Ceiling Spearman"],
      Object.entries(aggregate).map(([format, raw]) => {
        const group = obj(raw);
        const metrics = obj(group.correlations);
        return [format, group.status, group.slates, group.candidate_count,
          points(obj(metrics.objective_score).pearson), points(obj(metrics.objective_score).spearman),
          points(obj(metrics.mean).spearman), points(obj(metrics.p90).spearman)];
      })), "");

  for (const slate of report.slate_reports) {
    lines.push(
      "",
      `## ${slate.slate.replaceAll("_", " ")} (${slate.status})`,
      "",
      `${slate.summary.contests} contests · ${slate.summary.entries} entries · ${slate.summary.matched_optimizer_entries} optimizer matches · ${slate.summary.identity_complete_entries} identity complete · ${slate.summary.duplicate_entries} duplicates · projection MAE ${points(slate.summary.projection_mae)} from ${slate.summary.projection_player_observations} player observations.`,
      "",
      "### Entries",
      "",
      ...table(
        ["Contest ID", "Entry ID", "Rank / field", "Top %", "Actual pts", "Projected pts", "Difference", "Lineup match", "Identity", "Profit"],
        slate.entries.map((entry) => {
          const actual = typeof entry.entry_points === "number" ? entry.entry_points : null;
          const projected = typeof entry.projected_points === "number" ? entry.projected_points : null;
          const financial = (entry.financial ?? {}) as Row;
          return [
            entry.contest_id, entry.entry_id,
            entry.rank == null ? "—" : `${entry.rank} / ${entry.field_size ?? "—"}`,
            points(entry.top_percent), points(actual), points(projected),
            actual != null && projected != null ? points(actual - projected) : "—",
            entry.lineup_match_basis, entry.identity_complete === true ? "yes" : "no",
            points(financial.profit),
          ];
        }),
      ),
    );
    for (const entry of slate.entries) {
      const players = Array.isArray(entry.players) ? entry.players as Row[] : [];
      lines.push("", `### Entry ${cell(entry.entry_id)} · contest ${cell(entry.contest_id)}`, "");
      const entryEvidence = obj(entry.entry_evidence);
      if (entryEvidence.url) lines.push(`Saved decision and control evidence: ${cell(entryEvidence.url)} · hash ${cell(entryEvidence.evidence_hash)}.`, "");
      if (players.length) {
        lines.push(
          ...table(
            ["Slot", "Player", "Canonical ID", "Base projected", "Projected", "Base actual", "Actual", "Difference", "Actual ownership"],
            players.map((player) => [
              player.roster_position, player.player_display_name, player.player_id,
              points(player.projected_base_points), points(player.projected_points),
              points(player.actual_base_points), points(player.actual_points),
              points(player.projection_residual), points(player.actual_ownership),
            ]),
          ),
          "",
          "CPT projected and actual columns include the 1.5 multiplier. Base columns show the unmultiplied values. Difference is actual minus projected in roster-slot points.",
        );
      } else {
        lines.push("Player-level comparison unavailable.");
      }
      if (Array.isArray(entry.unresolved_players) && entry.unresolved_players.length) {
        lines.push("", "Unresolved players:", "", ...entry.unresolved_players.map((player) =>
          `- ${JSON.stringify(player)}`));
      }
    }
    lines.push(
      "",
      "### Slate evidence gaps",
      "",
      ...list(slate.missing_evidence),
    );
  }

  lines.push(
    "",
    "## Week evidence gaps",
    "",
    ...list(report.missing_evidence),
    "",
    "## Source and run lineage",
    "",
    `Source file IDs: ${report.source_file_ids.length ? report.source_file_ids.map(cell).join(", ") : "none recorded"}`,
    "",
    ...Object.entries(report.run_ids).map(([kind, ids]) => `- ${kind}: ${ids.length ? ids.map(cell).join(", ") : "none recorded"}`),
    "",
    "## Complete structured report",
    "",
    "The JSON below preserves contest metadata, finances, ownership, belief and agent outcomes, optimizer control outcomes, player rule evaluations, and lineage. Compact v2 reports link to frozen candidate pages and exact decision/control evidence instead of embedding large replay payloads. Those links require access to the football app.",
    "",
    "~~~~json",
    JSON.stringify(report, null, 2),
    "~~~~",
    "",
  );
  return lines.join("\n");
}

export function downloadWeeklyLearningReport(report: WeeklyLearningReport): void {
  const username = report.entry_user.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "") || "user";
  const filename = `week-learning-${report.season}-w${String(report.week).padStart(2, "0")}-${username}.md`;
  const blob = new Blob([weeklyLearningReportMarkdown(report)], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
