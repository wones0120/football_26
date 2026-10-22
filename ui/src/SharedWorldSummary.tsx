import { sharedWorldEvidence } from "./sharedWorldPolicy";

export function SharedWorldSummary({value, players}: {value: unknown; players?: unknown}) {
  const r=sharedWorldEvidence(value,players); if(!r)return null;
  return <section aria-label="Whole-lineup game-world selection" style={{overflowWrap:"anywhere"}}>
    <h4>Whole-lineup game-world selection</h4>
    <p>{r.status} · {String(r.achieved)}/{String(r.requested)} saved · Anchor: {r.anchor}</p>
    <p><strong>{r.coverageSummary}</strong></p>
    <p>{r.anchorBasis}</p><p>{r.probability}</p><p>{r.completion}</p>
    <p>Bounded generation: {String(r.limits.max_candidates)} candidate rosters, {String(r.limits.max_solver_calls)} solver calls, {String(r.limits.seconds)} seconds. Pool failure does not prove the full legal model infeasible.</p>
    <p>Strategy-owned mandatory QB/receiver stacks and starting-QB rules are omitted. Your explicit eligibility, locks, exposure, team, salary, quarterback and leader controls remain binding.</p>
    {r.steps.map(s=><div key={String(s.rank)}>
      <h5>Saved lineup {String(s.rank)}</h5><p>{s.roster}</p><p>{s.reason}</p>
      {s.paths.map((p,i)=><p key={`path${i}`}>Success path: {p}</p>)}
      {s.roles.map((p,i)=><p key={`role${i}`}>{p}</p>)}
      {s.couplings.map((p,i)=><p key={`coupling${i}`}>Shared opportunity: {p}</p>)}
      <p>Anchor conditional mean: {s.anchorMean} · unchanged base mean: {s.baseMean} · incremental conditional points: {s.gain}</p>
      {s.worlds.map(w=><p key={w.label}>{w.label}: {w.points} conditional points · remaining candidate-pool gap {w.gap}</p>)}
      <p>{s.risk}</p>
      {s.alternative&&<details><summary>Strongest admissible full-roster alternative</summary><p>{s.alternative}</p><p>Anchor conditional mean: {s.alternativeAnchor}</p><p>{s.alternativeTradeoff}</p></details>}
    </div>)}
    <details><summary>Supported worlds, counterevidence and unknowns</summary>
      {r.worlds.map(w=><div key={w.id}><strong>{w.id}</strong><p>{w.mechanism}</p>
        {w.components.map((v,i)=><p key={`component${i}`}>Count/component response: {v}</p>)}
        {w.counter.map((v,i)=><p key={`c${i}`}>Counterevidence: {v}</p>)}
        {w.unknowns.map((v,i)=><p key={`u${i}`}>Unknown: {v}</p>)}<p>Source lineage: {w.sources}</p></div>)}
    </details>
  </section>;
}
