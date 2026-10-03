/** Render frozen parity/sensitivity responses through the production HTML renderer. */
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { buildOptimizerReportHtml } from "../src/optimizerReport.ts";
import type { OptimizerResponse } from "../src/api.ts";

const directory = resolve(process.argv[2] ?? "../artifacts/classic_large_gpp_parity/d0e2ff8f");
for (const name of ["A_no_cap", "B_cap4", "C_cap3", "D_cap2"]) {
  const contract = JSON.parse(readFileSync(resolve(directory, `${name}_contract.json`), "utf8"));
  const audit = JSON.parse(readFileSync(resolve(directory, `${name}_audit.json`), "utf8"));
  const fixture = JSON.parse(readFileSync(resolve(directory, "app_fixture.json"), "utf8"));
  const players = new Map<string, Record<string, unknown>>(contract.effective.players.map((p: Record<string, unknown>) => [p.player_id, p]));
  const response = {
    job_id: `${fixture.job_id} / ${name}`, status: audit.status, strategy: contract.strategy_label,
    strategy_config: fixture.params.strategy_config, contest_format: "classic", objective: "gpp", enforce_single_te: true,
    exclude_opponent_teams: fixture.params.exclude_opponent_teams, message: `Frozen ${contract.execution_mode} comparison; ${audit.portfolio_optimality}.`,
    effective_strategy_contract: contract,
    primary_game_constraint: { requested: contract.requested.max_lineups_per_primary_game, effective: audit.effective_max_lineups_per_primary_game,
      source: contract.sources.max_lineups_per_primary_game, validation: audit.validation.status, achieved_game_exposure: audit.canonical_primary_games },
    results: audit.candidate_rosters.map((row: Record<string, unknown>) => (row.player_ids as string[]).map((id) => {
      const p = players.get(id)!;
      return { ...p, projection: p.projection, p90: p.ceiling, player_team: p.team,
        opponent_team: p.opponent, roster_position: p.position,
        lineup_stack_summary: { label: (row.stack as Record<string, unknown>).type },
        lineup_correlation_summary: { total_adjustment: (row.correlation_rules as Record<string, unknown>[]).reduce((sum, rule) => sum + Number(rule.objective_contribution ?? 0), 0),
          triggered_rules: row.correlation_rules },
      };
    })),
  } as OptimizerResponse;
  writeFileSync(resolve(directory, `${name}_readable_report.html`), buildOptimizerReportHtml(response, { season: fixture.season, week: fixture.week, slate: fixture.slate }));
}
