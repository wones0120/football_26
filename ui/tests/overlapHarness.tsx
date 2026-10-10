import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { ClassicLargeGppPortfolioControls } from "../src/ClassicLargeGppPortfolioControls";
import { parseSavedLargeGppControls } from "../src/classicLargeGppControls";
import { portfolioSettingsRows } from "../src/classicPortfolioReport";
import type { OptimizerResponse } from "../src/api";
import { overlapFixtureRequest } from "./overlapFixtureRequest";
import "../src/index.css";
import "../src/App.css";

function Harness() {
  const [strategy, setStrategy] = useState("classic_small_field_gpp");
  const [numLineups, setNumLineups] = useState(20);
  const [maxExposure, setMaxExposure] = useState(60);
  const [gameCap, setGameCap] = useState<number | null>(null);
  const [controls, setControls] = useState(() => parseSavedLargeGppControls(localStorage.getItem("overlap-fixture-controls")));
  const [response, setResponse] = useState<{ api_request: unknown; report: OptimizerResponse } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => localStorage.setItem("overlap-fixture-controls", JSON.stringify(controls)), [controls]);
  return <main className="operations-workspace" style={{padding:24}}>
    <h1>Overlap propagation · synthetic fixture</h1>
    <p>72 synthetic players · season 2000 · in-memory SQLite. This page cannot run a user portfolio.</p>
    <label>Contest Strategy<select value={strategy} disabled={pending} onChange={e => setStrategy(e.target.value)}>
      <option value="classic_small_field_gpp">Classic Small-field GPP</option>
      <option value="classic_large_gpp_v1">Classic Large GPP</option>
      <option value="showdown_gpp_v1">Showdown (isolation check)</option>
    </select></label>
    {strategy === "classic_large_gpp_v1" && <ClassicLargeGppPortfolioControls
      numLineups={numLineups} setNumLineups={setNumLineups} maxExposure={maxExposure} setMaxExposure={setMaxExposure}
      gameCap={gameCap} setGameCap={setGameCap} controls={controls} setControls={setControls} disabled={pending} />}
    <button disabled={pending || strategy !== "classic_large_gpp_v1"} onClick={async () => {
      const payload = overlapFixtureRequest(strategy, numLineups, maxExposure, gameCap, controls);
      setPending(true); setError("");
      try {
        const r = await fetch("http://127.0.0.1:8001/fixture/submit", {
          method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload),
        });
        if (!r.ok) throw new Error(await r.text());
        const result = await r.json();
        if (result.api_request.params.max_lineup_overlap !== controls.maxLineupOverlap) {
          if (controls.maxLineupOverlap !== null) throw new Error("Overlap omitted or changed in API JSON");
        }
        setResponse(result);
      } catch (e) { setError(String(e)); } finally { setPending(false); }
    }}>Submit synthetic fixture</button>
    {error && <p role="alert">{error}</p>}
    {response && <>
      <h2>Saved fixture report</h2>
      <table><thead><tr>{["Setting","Requested","Effective","Source","Achieved"].map(s => <th key={s}>{s}</th>)}</tr></thead>
        <tbody>{portfolioSettingsRows(response.report).map(r => <tr key={r.setting}>
          <td>{r.setting}</td><td>{r.requested}</td><td>{r.effective}</td><td>{r.source}</td><td>{r.achieved}</td>
        </tr>)}</tbody></table>
      <p>Independent validation: {response.report.portfolio_controls_report?.validation?.status}</p>
      <h2>Saved API request</h2><pre>{JSON.stringify(response.api_request, null, 2)}</pre>
    </>}
  </main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
