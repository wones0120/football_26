import { useEffect, useState } from "react";

type Player = { player_master_id: string; name: string; position: string; team: string; game_id: string; salary: number; projection: number };
type Candidate = { candidate_id?: string; allocated_idea_id: string; supporting_idea_id?: string; salary: number; baseline_mean: number; roster: Player[] };
type Comparison = { selected: Candidate[]; achieved: number; requested: number; summed_baseline_mean: number; selection: { solver_status: string }; dependencies: { offense_game_appearance_counts: Record<string, number> } };
type Replay = { saved_v1_comparisons?: Record<string, Comparison>; comparisons?: Record<string, Comparison>; original38_comparisons?: Record<string, Comparison>; original_distinct_roster_count?: number; replay_id: string; source_optimizer_run_id: string; status: string; source_data_cutoff: string; chronology_status: string; requested: number; candidate_variant_count: number; distinct_canonical_roster_count: number; generation: { variants: number; attempts: unknown[] }; original_selected: Candidate[]; candidates: Candidate[]; selected: Candidate[]; highest_baseline_mean_control: Candidate[]; assumptions: string[]; settings_sha256: string; original_dependencies: { offense_game_appearance_counts: Record<string, number> }; selected_dependencies: { offense_game_appearance_counts: Record<string, number> } };
const base = import.meta.env.VITE_API_BASE_URL || "/api";
async function read<T>(path: string, method = "GET", kind = "scenario-breadth"): Promise<T> {
  const response = await fetch(`${base}/learning/research/${kind}${path}`, { method });
  if (!response.ok) { const error = await response.json(); throw new Error(error.detail ?? "Research replay failed"); }
  return response.json();
}
export function ScenarioBreadthReplay() {
  const [run, setRun] = useState("");
  const [parentReplay, setParentReplay] = useState("");
  const [ablationSource, setAblationSource] = useState("");
  const [saved, setSaved] = useState<{ replay_id: string; source_optimizer_run_id: string; kind: string }[]>([]);
  const [result, setResult] = useState<Replay | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const refresh = async () => { const kinds = ["scenario-breadth", "full-game-breadth", "joint-coverage", "lineup-ablations"]; const lists = await Promise.all(kinds.map(kind => read<{ rows: typeof saved }>("", "GET", kind).then(value => value.rows.map(row => ({ ...row, kind }))))); setSaved(lists.flat()); };
  useEffect(() => { void refresh().catch(err => setError(String(err))); }, []);
  const action = async (path: string, method: string, kind = "scenario-breadth") => {
    setBusy(true); setError(null);
    try { setResult(await read<Replay>(path, method, kind)); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };
  const rosters = (title: string, candidates: Candidate[]) => <details><summary>{title} · {candidates.length} rosters</summary>{candidates.map((c, i) => <article key={`${c.candidate_id}-${i}`}><h4>{i + 1}. ${c.salary.toLocaleString()} · baseline mean {c.baseline_mean.toFixed(2)}</h4><p>Primary story: {c.allocated_idea_id}{c.supporting_idea_id && ` · Supporting path: ${c.supporting_idea_id}`}</p><p>{c.roster.map(p => `${p.position} ${p.name} (${p.team}, $${p.salary.toLocaleString()}, ${p.projection.toFixed(2)})`).join(" / ")}</p></article>)}</details>;
  return <details className="report-library-intro scenario-breadth-replay"><summary>Frozen scenario candidate research replay</summary>
    <p>Compare a saved Classic scenario-first run using its frozen legal model, evidence and user settings. Locked slates are retrospective research. This creates no optimizer run, entries or CSV and changes no projections or live defaults.</p>
    <label>Saved source optimizer run ID<input aria-label="Scenario replay source optimizer run ID" value={run} onChange={e => setRun(e.target.value)} /></label>
    <button disabled={busy || !/^[a-f0-9-]{36}$/.test(run)} onClick={() => void action(`/${run}`, "POST")}>Build frozen candidate comparison</button>
    <button disabled={busy || !/^[a-f0-9-]{36}$/.test(run)} onClick={() => void action(`/${run}`, "POST", "full-game-breadth")}>Build full-game and top-decile comparison</button>
    <button disabled={busy || !/^[a-f0-9-]{36}$/.test(run)} onClick={() => void action(`/${run}?corrected_workload=true`, "POST", "full-game-breadth")}>Compare corrected workload game outcomes</button>
    <label>Full-game source replay ID<input aria-label="Joint coverage source replay ID" value={parentReplay} onChange={e => setParentReplay(e.target.value)} /></label>
    <button disabled={busy || !/^[a-f0-9]{64}$/.test(parentReplay)} onClick={() => void action(`/${parentReplay}`, "POST", "joint-coverage")}>Compare shared-outcome portfolio selection</button>
    <label>Ablation source research replay ID<input aria-label="Ablation source research replay ID" value={ablationSource} onChange={e => setAblationSource(e.target.value)} /></label>
    <button disabled={busy || !/^[a-f0-9]{64}$/.test(ablationSource)} onClick={() => void action(`/${ablationSource}`, "POST", "lineup-ablations")}>Compare retrained salary and stacking ablations</button>
    {busy && <p role="status">Building one bounded research comparison…</p>}{error && <p role="alert">{error}</p>}
    <label>Saved research comparisons<select aria-label="Saved scenario research comparison" defaultValue="" disabled={busy} onChange={e => e.target.value && void action(`/saved/${e.target.value.split(":")[1]}`, "GET", e.target.value.split(":")[0])}><option value="">Choose saved comparison</option>{saved.map(r => <option key={r.replay_id} value={`${r.kind}:${r.replay_id}`}>{r.kind === "lineup-ablations" ? "Ablations · " : r.kind === "joint-coverage" ? "Joint coverage · " : r.kind === "full-game-breadth" ? "Full game · " : "Original breadth · "}{r.source_optimizer_run_id.slice(0, 8)} · {r.replay_id.slice(0, 12)}</option>)}</select></label>
    {result && <section aria-label="Frozen scenario comparison results"><h3>Research only · {result.status}</h3><p>Replay ID: {result.replay_id}</p><p>Original stored decision time: {result.source_data_cutoff}</p><p>{result.chronology_status}</p><p>Settings digest: {result.settings_sha256}</p><p>Original selected {result.original_selected.length} · generated variants {result.generation.variants} · combined variants {result.candidate_variant_count} · distinct canonical rosters {result.distinct_canonical_roster_count} · {result.comparisons ? `${Object.keys(result.comparisons).length} selection comparisons; original pool ${result.original_distinct_roster_count}` : `selected ${result.selected.length}/${result.requested}`}</p>
      {rosters("All canonical candidates including original controls", result.candidates)}{rosters("Original saved portfolio", result.original_selected)}
      {result.comparisons ? <><p>Full-game stress generation is research only. Analog outcomes are paired physical realizations; their sampling frequencies are not calibrated probabilities. Top-decile models are frozen before Week 6; prior Week 6 outcomes were already inspected.</p>{Object.entries(result.comparisons).map(([name, comparison]) => <section key={name}><h4>{name} · {comparison.achieved}/{comparison.requested} · {comparison.selection.solver_status} · summed mean {comparison.summed_baseline_mean.toFixed(2)}</h4>{rosters(`${name} complete portfolio`, comparison.selected)}<ul>{Object.entries(comparison.dependencies.offense_game_appearance_counts).map(([game,count]) => <li key={game}>{game}: {count}/{comparison.achieved}</li>)}</ul></section>)}{result.saved_v1_comparisons && <details><summary>Saved v1 workload matched controls</summary>{Object.entries(result.saved_v1_comparisons).map(([name, comparison]) => <section key={name}><h4>{name} · {comparison.achieved}/{comparison.requested} · {comparison.selection.solver_status}</h4>{rosters(`${name} original workload portfolio`, comparison.selected)}</section>)}</details>}<details><summary>Original 38-roster matched controls</summary>{Object.entries(result.original38_comparisons ?? {}).map(([name, comparison]) => rosters(name, comparison.selected))}</details></> : <>{rosters("Ordinal conditional coverage portfolio", result.selected)}{rosters("Highest baseline mean control on same candidate pool", result.highest_baseline_mean_control)}<details><summary>Shared offensive game dependencies</summary><ul>{Object.entries(result.original_dependencies.offense_game_appearance_counts).map(([game, count]) => <li key={game}>{game}: original {count}/{result.original_selected.length}; comparison {result.selected_dependencies.offense_game_appearance_counts[game] ?? 0}/{result.selected.length}</li>)}</ul><p>Game presence alone is not calibrated correlation. Multiple lineups can still depend on the same supporting players.</p></details></>}
      <details><summary>Assumptions and limits</summary><ul>{result.assumptions.map(a => <li key={a}>{a}</li>)}</ul></details>
    </section>}
  </details>;
}
