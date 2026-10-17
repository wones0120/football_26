import type { AnalystHandoff } from './analystPreparation';
import type { OptimizerResponse, PreparedBuild } from './api';
export type OptimizationIntent = 'EXPECTED_GAME' | 'CONTRARIAN' | 'MIXED';
export const intentLabel = (intent: string) => intent === 'EXPECTED_GAME' ? 'Expected Game' : intent === 'CONTRARIAN' ? 'Contrarian' : 'Mixed research';
export type IntentScope = { intent: Exclude<OptimizationIntent, 'MIXED'>; assessment: string; scenario_ids: string[]; story_requirements?: {team: string; minimum_receivers: number}; scope: {season: number; week: number; slate: string; format: string} };
export function intentHandoff(build: Pick<PreparedBuild, "analyst_handoff" | "analyst_intent_handoffs"> | null | undefined, intent: OptimizationIntent): AnalystHandoff | null {
  return (intent === 'MIXED' ? build?.analyst_handoff : build?.analyst_intent_handoffs?.[intent]) ?? null;
}
export type ComparePlayer = {player_id: string; name: string; player_team: string; roster_position: string; salary: number; ownership_run_id?: string | null; analyst_thesis_ids?: string[]};
export function resultLineups(run: OptimizerResponse | undefined): ComparePlayer[][] {
  return Array.isArray(run?.results) ? run.results as ComparePlayer[][] : [];
}
export function captainExposure(run: OptimizerResponse | undefined): string[] {
  const lineups = resultLineups(run); const counts = new Map<string, {name: string; count: number}>();
  for (const lineup of lineups) for (const row of lineup.filter(row => row.roster_position === 'CPT')) {
    const old = counts.get(row.player_id); counts.set(row.player_id, {name: row.name, count: (old?.count ?? 0) + 1});
  }
  return [...counts.values()].map(row => `${row.name} ${row.count}/${lineups.length} (${Math.round(100 * row.count / lineups.length)}%)`);
}
export function sharedCore(run: OptimizerResponse | undefined): string[] {
  const lineups = resultLineups(run); if (!lineups.length) return [];
  return lineups[0].filter(player => lineups.every(lineup => lineup.some(row => row.player_id === player.player_id))).map(player => player.name);
}
export function intentComparisonIssue(expected?: OptimizerResponse, contrarian?: OptimizerResponse): string | null {
  if (!expected || !contrarian) return 'Generate each intent from this prepared build to compare saved results.';
  const a = expected.football_analyst?.preparation_compatibility, b = contrarian.football_analyst?.preparation_compatibility;
  if (!a?.prepared_source_sha256 || a.prepared_source_sha256 !== b?.prepared_source_sha256 || expected.projection_run_id !== contrarian.projection_run_id) return 'Inputs differ. These runs are not a matched-input comparison; prepare and generate both from the same build.';
  const ownerA = new Set(resultLineups(expected).flat().map(row => row.ownership_run_id).filter(Boolean));
  const ownerB = new Set(resultLineups(contrarian).flat().map(row => row.ownership_run_id).filter(Boolean));
  if (ownerA.size !== 1 || ownerB.size !== 1 || [...ownerA][0] !== [...ownerB][0]) return 'Ownership lineage is missing or differs; this is not a matched-input comparison.';
  return null;
}
