import { useEffect, useState } from "react";
import {
  archiveSavedOptimizerContest,
  fetchSavedContestScopes,
  fetchSavedContestObservations,
  fetchSavedOptimizerContests,
  saveOptimizerContests,
  type SavedContest,
  type SavedContestObservation,
  type SavedContestScope,
  type SavedContestType,
} from "./api";

type Props = {
  season: number;
  week: number;
  slate: string;
  contestFormat: "classic" | "showdown";
  optimizerUrls?: string;
  onUseUrls?: (urls: string[], contests: SavedContest[]) => void;
  allowUseAll?: boolean;
  onActivateScope?: (scope: SavedContestScope) => void;
};

const scopeKey = (scope: Pick<SavedContestScope, "season" | "week" | "slate" | "contest_format" | "contest_type">) =>
  `${scope.season}|${scope.week}|${scope.slate}|${scope.contest_format}|${scope.contest_type}`;

export function ContestLibrary({ season, week, slate, contestFormat, optimizerUrls, onUseUrls, allowUseAll = false, onActivateScope }: Props) {
  const [contestType, setContestType] = useState<SavedContestType>("gpp");
  const [scopes, setScopes] = useState<SavedContestScope[]>([]);
  const [browseKey, setBrowseKey] = useState("");
  const [draftUrls, setDraftUrls] = useState("");
  const [saved, setSaved] = useState<SavedContest[]>([]);
  const [history, setHistory] = useState<Record<string, SavedContestObservation[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const activeScope = { season, week, slate, contest_format: contestFormat, contest_type: contestType };
  const activeKey = scopeKey(activeScope);
  const selectedScope = scopes.find((scope) => scopeKey(scope) === browseKey);
  const browseScope = selectedScope ?? activeScope;
  const browsingCurrent = scopeKey(browseScope) === activeKey;
  const scopeOptions = scopes.some((scope) => scopeKey(scope) === activeKey)
    ? scopes : [{ ...activeScope, contest_count: 0 }, ...scopes];

  useEffect(() => {
    let cancelled = false;
    fetchSavedContestScopes()
      .then((response) => { if (!cancelled) setScopes(response.scopes); })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => { setBrowseKey(""); }, [season, week, slate, contestFormat, contestType]);

  useEffect(() => {
    let cancelled = false;
    setSaved([]);
    fetchSavedOptimizerContests({
      season: browseScope.season, week: browseScope.week, slate: browseScope.slate,
      contest_format: browseScope.contest_format, contest_type: browseScope.contest_type,
    })
      .then((response) => { if (!cancelled) { setSaved(response.contests); setError(null); } })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { cancelled = true; };
  }, [browseScope.season, browseScope.week, browseScope.slate, browseScope.contest_format, browseScope.contest_type]);

  const save = async () => {
    setPending(true);
    setError(null);
    try {
      const urls = draftUrls.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
      if (!urls.length) throw new Error("Paste at least one DraftKings contest URL.");
      const result = await saveOptimizerContests({
        season, week, slate, contest_format: contestFormat, contest_type: contestType, urls,
      });
      setBrowseKey("");
      setSaved(result.contests);
      setScopes((await fetchSavedContestScopes()).scopes);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending(false);
    }
  };

  return <div className="status-card nested-card">
    <h3>Saved DraftKings contests</h3>
    <p>Save contests by season, week, slate, format, and type. Each save records a dated snapshot. Previewing or optimizing a saved URL records another snapshot.</p>
    <label>Browse saved slates
      <select value={scopeKey(browseScope)} onChange={(event) => setBrowseKey(event.target.value === activeKey ? "" : event.target.value)}>
        {scopeOptions.map((scope) => <option key={scopeKey(scope)} value={scopeKey(scope)}>{scope.season} Week {scope.week} · {scope.slate.replaceAll("_", " ")} · {scope.contest_format} · {scope.contest_type.toUpperCase()} ({scope.contest_count})</option>)}
      </select>
    </label>
    {scopes.length === 1 && <p>One saved slate group is in the catalog. Other slates will appear here after their contests are saved.</p>}
    {scopes.length === 0 && <p>No contest slate groups have been saved yet.</p>}
    {!browsingCurrent && <div className="button-row"><p>Viewing {browseScope.season} Week {browseScope.week} · {browseScope.slate}. Saving still uses the active optimizer slate.</p>{selectedScope && onActivateScope && <button type="button" onClick={() => { setContestType(selectedScope.contest_type); onActivateScope(selectedScope); }}>Switch optimizer to this slate</button>}</div>}
    <div className="form-row"><label>Contest type
      <select value={contestType} onChange={(event) => setContestType(event.target.value as SavedContestType)}>
        <option value="gpp">GPP</option><option value="cash">Cash</option>
        <option value="h2h">Head-to-head</option><option value="double_up">Double-up</option>
        <option value="fifty_fifty">50/50</option><option value="other">Other</option>
      </select>
    </label></div>
    <p>Save to active slate: {season} Week {week} · {slate} · {contestFormat} · {contestType.toUpperCase()}</p>
    <label>DraftKings contest URLs to save, one per line
      <textarea className="full-width" rows={3} value={draftUrls} onChange={(event) => setDraftUrls(event.target.value)} placeholder="https://www.draftkings.com/draft/contest/195677817" />
    </label>
    <div className="button-row">
      <button type="button" onClick={save} disabled={pending}>{pending ? "Saving contests…" : "Save contests"}</button>
      {optimizerUrls?.trim() && <button type="button" onClick={() => setDraftUrls(optimizerUrls)}>Copy optimizer URLs</button>}
      {allowUseAll && saved.length > 0 && browsingCurrent && onUseUrls && <button type="button" onClick={() => onUseUrls(saved.map((row) => row.url), saved)}>Use all saved URLs</button>}
    </div>
    {error && <p role="alert">{error}</p>}
    {saved.length > 0 && <div className="table-wrap"><table><thead><tr><th>Contest</th><th>Entries / capacity</th><th>Observations</th><th>Actions</th></tr></thead><tbody>{saved.map((row) => <tr key={row.contest_id}>
      <td>{row.name ?? row.contest_id}<br /><small>{row.contest_id}</small></td>
      <td>{String(row.latest_contest?.current_entries ?? row.latest_successful_contest?.current_entries ?? "—")} / {String(row.latest_contest?.capacity ?? row.latest_successful_contest?.capacity ?? "—")}{row.latest_contest?.current_entries == null && row.latest_successful_contest?.current_entries != null && <><br /><small>Saved snapshot</small></>}</td>
      <td>{row.observation_count}{row.latest_observed_at ? ` · ${new Date(row.latest_observed_at).toLocaleString()}` : ""}{row.latest_error ? ` · ${row.latest_error}` : ""}</td>
      <td>{browsingCurrent && onUseUrls && <button type="button" onClick={() => onUseUrls([row.url], [row])}>Use URL</button>}{" "}<button type="button" onClick={async () => {
        try { await archiveSavedOptimizerContest(row.contest_id); setSaved((current) => current.filter((item) => item.contest_id !== row.contest_id)); setScopes((await fetchSavedContestScopes()).scopes); if (saved.length === 1) setBrowseKey(""); }
        catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
      }}>Archive</button></td>
    </tr>)}</tbody></table>
      {saved.map((row) => <details key={`${row.contest_id}-history`} onToggle={(event) => {
        if (!event.currentTarget.open) return;
        fetchSavedContestObservations(row.contest_id)
          .then((result) => setHistory((current) => ({ ...current, [row.contest_id]: result.observations })))
          .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
      }}><summary>{row.name ?? row.contest_id} observation history</summary>
        <table><thead><tr><th>Observed</th><th>Reason</th><th>Entries / capacity</th><th>Prize pool</th><th>Error</th></tr></thead><tbody>{(history[row.contest_id] ?? []).map((observation) => <tr key={observation.observation_id}>
          <td>{new Date(observation.observed_at).toLocaleString()}</td><td>{observation.observation_reason}</td>
          <td>{String(observation.contest.current_entries ?? "—")} / {String(observation.contest.capacity ?? "—")}</td>
          <td>{observation.contest.prize_pool == null ? "—" : `$${observation.contest.prize_pool}`}</td><td>{observation.error ?? "—"}</td>
        </tr>)}</tbody></table>
      </details>)}
    </div>}
  </div>;
}
