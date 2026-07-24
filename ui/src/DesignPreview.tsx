import "./DesignPreview.css";

type DesignPreviewProps = {
  onBack: () => void;
};

const pulseSignals = [
  {
    team: "BUF",
    headline: "Stevenson downgraded to limited in red-zone installs",
    impact: "High",
    note: "Usage risk shifted from neutral to caution. Final practice status will decide pool exposure.",
  },
  {
    team: "KC",
    headline: "Second tight end elevated into first-team seam package",
    impact: "Medium",
    note: "Cheap leverage stack appears if camp reports stay consistent through Friday.",
  },
  {
    team: "PHI",
    headline: "Wind event building for prime-time kick window",
    impact: "Medium",
    note: "Passing efficiency penalty likely. Rush share and short-area targets gain priority.",
  },
];

const slateRows = [
  { game: "BUF @ MIA", total: "51.0", leverage: "+7.4", signal: "Fragile chalk" },
  { game: "PHI @ DAL", total: "47.5", leverage: "+5.9", signal: "Weather pivot" },
  { game: "KC @ LAC", total: "49.0", leverage: "+4.2", signal: "Tight-end value" },
  { game: "BAL @ CIN", total: "50.5", leverage: "+3.8", signal: "Late hammer" },
];

const researchLanes = [
  {
    eyebrow: "Research Pulse",
    title: "Noise stripped out. Only slate-moving information survives.",
    body:
      "National feeds, official team notes, and historical imports resolve into one calm, high-trust surface with source lineage and explicit relevance rules.",
  },
  {
    eyebrow: "Portfolio Studio",
    title: "The optimizer should feel like a trading desk, not a form dump.",
    body:
      "Projection shifts, ownership tension, and game-stack posture are framed as investment decisions with a clear visual hierarchy.",
  },
  {
    eyebrow: "Replay Loop",
    title: "Historical imports become a training ground for better judgment.",
    body:
      "Backfilled news can be replayed through the same filters to compare what the system would have surfaced before lock.",
  },
];

export function DesignPreview({ onBack }: DesignPreviewProps) {
  return (
    <div className="design-preview">
      <div className="preview-chrome">
        <button className="preview-back" onClick={onBack}>
          Return To Workspace
        </button>
        <span className="preview-badge">Concept Preview</span>
      </div>

      <section className="preview-hero">
        <div className="preview-hero-copy">
          <p className="preview-kicker">NFL Research Operating System</p>
          <h1>Classical tone. Modern control. Zero dashboard clutter.</h1>
          <p className="preview-lead">
            This direction treats the app like a premium research desk: editorial restraint,
            crisp hierarchy, and one clear goal of turning volatile NFL information into usable
            DFS decisions.
          </p>
          <div className="preview-metrics">
            <div>
              <span>Slate Status</span>
              <strong>Sunday Main / 12 critical signals</strong>
            </div>
            <div>
              <span>Market Shape</span>
              <strong>Condensed chalk, weather distortion</strong>
            </div>
            <div>
              <span>Portfolio Posture</span>
              <strong>Lean contrarian in Tier 2 totals</strong>
            </div>
          </div>
        </div>

        <div className="preview-hero-panel">
          <div className="preview-panel-topline">
            <span>Live Research Pulse</span>
            <strong>06:40 ET</strong>
          </div>
          {pulseSignals.map((signal) => (
            <article className="signal-card" key={signal.headline}>
              <div className="signal-card-row">
                <span className="signal-team">{signal.team}</span>
                <span className={`signal-impact signal-impact-${signal.impact.toLowerCase()}`}>
                  {signal.impact}
                </span>
              </div>
              <h3>{signal.headline}</h3>
              <p>{signal.note}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="preview-lanes">
        {researchLanes.map((lane) => (
          <article className="lane-card" key={lane.title}>
            <span>{lane.eyebrow}</span>
            <h2>{lane.title}</h2>
            <p>{lane.body}</p>
          </article>
        ))}
      </section>

      <section className="preview-board">
        <div className="board-header">
          <div>
            <p className="preview-kicker">Decision Board</p>
            <h2>Slate leverage should feel curated, not dumped from a spreadsheet.</h2>
          </div>
          <div className="board-callout">
            <span>Primary Read</span>
            <strong>Reduce broad-analysis noise. Let structured signals drive the board.</strong>
          </div>
        </div>

        <div className="board-grid">
          <div className="board-card board-card-table">
            <div className="board-card-header">
              <h3>Game Pressure Matrix</h3>
              <span>Updated from injuries, totals, and role volatility</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Game</th>
                  <th>Total</th>
                  <th>Leverage</th>
                  <th>Signal</th>
                </tr>
              </thead>
              <tbody>
                {slateRows.map((row) => (
                  <tr key={row.game}>
                    <td>{row.game}</td>
                    <td>{row.total}</td>
                    <td>{row.leverage}</td>
                    <td>{row.signal}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="board-card board-card-stack">
            <div className="board-card-header">
              <h3>Lineup Intelligence</h3>
              <span>Portfolio framing rather than raw controls</span>
            </div>
            <div className="stack-metric">
              <span>Primary Build</span>
              <strong>Balanced core with one asymmetric late-window stack</strong>
            </div>
            <div className="stack-metric">
              <span>Ownership Tilt</span>
              <strong>Underweight top-three wideout chalk by 11%</strong>
            </div>
            <div className="stack-metric">
              <span>Manual Review</span>
              <strong>2 unresolved beat-writer notes before lock</strong>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
