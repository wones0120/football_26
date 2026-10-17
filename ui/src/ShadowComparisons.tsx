import { useEffect, useState } from 'react';
import { ALL_LEARNING_SLATES } from './learningContext';
import { normalizeSlateId } from './workspaceContext';
import { fetchShadowComparisons, refreshShadowComparisons, type ShadowComparison } from './api';

export function ShadowComparisons({season, week, slate = ALL_LEARNING_SLATES}: {season: number; week: number; slate?: string}) {
  const [items, setItems] = useState<ShadowComparison[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const read = () => { void fetchShadowComparisons(season, week).then(r => {
      if (active) { setItems(r.experiments); setError(null); }
    }).catch(e => { if (active) setError(String(e)); }); };
    read(); const timer = window.setInterval(read, 30000);
    return () => { active = false; window.clearInterval(timer); };
  }, [season, week]);
  const retry = async () => {
    setBusy(true); setError(null);
    try { setItems((await refreshShadowComparisons(season, week)).experiments); }
    catch(e) { setError(String(e)); } finally { setBusy(false); }
  };
  const visibleItems = items.filter(item => slate === ALL_LEARNING_SLATES || normalizeSlateId(item.slate) === slate);
  return <section className="panel" aria-label="GPP shadow comparisons">
    <h2>GPP shadow comparisons</h2>
    <p>Frozen live and research choices are compared automatically when contest standings or entry history are imported. Live selections stay unchanged.</p>
    <button disabled={busy} onClick={() => void retry()}>{busy ? 'Evaluating…' : 'Retry comparison'}</button>
    {error && <p role="alert">{error}</p>}
    {!visibleItems.length && !error && <p>No registered experiments for this review scope.</p>}
    {visibleItems.map(item => <article key={item.experiment_id}>
      <h3>{item.label} · {item.slate}</h3>
      <p>Status: {item.report_json?.status.replaceAll('_', ' ') ?? 'Awaiting evaluation'}</p>
      {item.report_json?.arms.map(arm => <div key={arm.label}>
        <h4>{arm.label.replaceAll('_', ' ')}</h4>
        {arm.forecast_points !== undefined && <p>Projected points: {arm.forecast_points.toFixed(2)} · Actual minus projected: {arm.projection_error ?? 'Pending'}</p>}
        <p>Actual points: {arm.actual_points ?? 'Pending'} · Paid finishes: {arm.known_paid_finishes} ·
          Non-paid finishes: {arm.known_non_paid_finishes} · Unknown: {arm.unknown_finishes}</p>
        {arm.missing_player_ids.length > 0 && <p>{arm.missing_player_ids.length} players need resolved, consistent results.</p>}
        {!arm.contests.length && <p>Awaiting verified GPP contest evidence.</p>}
        {arm.contests.map(c => <p key={c.contest_id}>{c.contest_name || c.contest_id}: {' '}
          {c.paid_finish === null ? 'Paid finish unknown' : c.paid_finish ? 'Paid finish' : 'Outside paid places'} · {' '}
          {c.net_return_bounds ? `Net return bounds: $${c.net_return_bounds[0].toFixed(2)} to $${c.net_return_bounds[1].toFixed(2)}` : 'Return unavailable'} · {' '}
          {c.top_one_percent === null ? 'Top 1% unknown' : c.top_one_percent ? 'Top 1%' : 'Outside top 1%'}</p>)}
      </div>)}
      <p>{item.report_json?.interpretation}</p>
    </article>)}
  </section>;
}
