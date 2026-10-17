import { OptionalNumber } from "./ClassicLargeGppPortfolioControls";
import { MAX_LINEUPS, type LineupControls } from "./lineupControls";

export function OptimizerLineupControls({ value, onChange, format, disabled }: {
  value: LineupControls; onChange: (value: LineupControls) => void; format: "classic" | "showdown"; disabled: boolean;
}) {
  const set = (key: keyof LineupControls, next: number | null) => onChange({ ...value, [key]: next });
  const size = format === "classic" ? 9 : 6;
  const percent = (label: string, key: keyof LineupControls) => <label>{label}<input type="number" min={0} max={100} value={value[key] ?? ""} onChange={event => set(key, Number(event.target.value))} /></label>;
  return <fieldset disabled={disabled} className="portfolio-controls-fields" aria-label="Lineup options">
    <h3>Lineup options</h3>
    <div className="form-row">
      <label>Number of lineups<input data-portfolio-field="num_lineups" type="number" min={1} max={MAX_LINEUPS} step={1} value={value.numLineups} onChange={event => set("numLineups", Number(event.target.value))} /></label>
      {percent("Max player exposure (%)", "maxExposure")}
      {format === "showdown" && <>
        {percent("Max Captain exposure (%)", "captainMaxExposure")}
        <label>Minimum player salary ($)<input aria-label="Minimum player salary ($)" type="number" min={0} max={50000} step={1} placeholder="No minimum" value={value.minimumPlayerSalary ?? ""} onChange={event => set("minimumPlayerSalary", event.target.value === "" ? null : Number(event.target.value))} />
          <small>Uses base FLEX salary for both slots. Enter 1,700 to exclude players priced at $1,600 or less. Blank means no additional minimum.</small>
        </label>
      </>}
      {format === "classic" && <>
        {([['Minimum QB salary ($)', 'minimumQbSalary'], ['Minimum RB salary ($)', 'minimumRbSalary']] as const).map(([label, key]) => <label key={key}>{label}<input aria-label={label} type="number" min={0} max={50000} step={1} placeholder="No position minimum" value={value[key] ?? ""} onChange={event => set(key, event.target.value === "" ? null : Number(event.target.value))} />
          <small>Defaults to $4,500. {key === "minimumRbSalary" ? "Includes RBs in FLEX. " : ""}Blank removes this position minimum. The higher of this and the offensive minimum applies.</small>
        </label>)}
        <label>Minimum offensive player salary ($)<input aria-label="Minimum offensive player salary ($)" type="number" min={0} max={50000} step={1} placeholder="No minimum" value={value.minimumPlayerSalary ?? ""} onChange={event => set("minimumPlayerSalary", event.target.value === "" ? null : Number(event.target.value))} />
          <small>Applies to QB, RB, WR, TE and FLEX. DST is exempt. Blank means no additional minimum.</small>
        </label>
        <label>Max players / team<input type="number" min={1} max={4} step={1} value={value.maxPlayersPerTeam} onChange={event => set("maxPlayersPerTeam", Number(event.target.value))} /></label>
        <label>Max players / game<input type="number" min={1} max={9} step={1} value={value.maxPlayersPerGame} onChange={event => set("maxPlayersPerGame", Number(event.target.value))} /></label>
      </>}
    </div>
    {format === "classic" && <>
      <h4>Require favored teams</h4>
      <div className="form-row">
        {([["QB", "favoredQb"], ["RB", "favoredRb"], ["WR", "favoredWr"], ["TE", "favoredTe"], ["DST", "favoredDst"]] as const).map(([pos, key]) => <label key={key}>
          <input type="checkbox" checked={value[key] === 1} onChange={event => set(key, event.target.checked ? 1 : 0)} aria-label={`Require favored team for ${pos}`} />{pos} on favored team
        </label>)}
      </div>
      <small>Defaults: RB, TE and DST on; QB and WR off. All five options are editable. Every player at a selected position must have a negative team spread in the prepared inputs. RB/WR/TE includes FLEX. Pick’em and missing spreads do not qualify. Projections stay unchanged.</small>
      <div className="form-row">
        {([["QB", "seasonRankQb"], ["RB", "seasonRankRb"], ["WR", "seasonRankWr"], ["TE", "seasonRankTe"]] as const).map(([pos, key]) => <label key={key}>Season-average {pos} rank
          <select aria-label={`Season-average ${pos} rank`} value={value[key] ?? ""} onChange={event => set(key, event.target.value === "" ? null : Number(event.target.value))}>
            <option value="">No restriction</option>
            {[25, 50, 75, 100].map(pct => <option key={pct} value={pct}>Top {pct}%{pct === 100 ? " with history" : ""}</option>)}
          </select>
        </label>)}
      </div>
      <small>Season DraftKings points per participating game through the prior week, ranked across the NFL. Defaults: QB/WR top 50%, RB/TE top 25%. Includes FLEX by natural position; ties qualify. Players without usable history are excluded when a limit is enabled. Week 1 requires No restriction. Incomplete history blocks the run. Projections stay unchanged.</small>
    </>}
    <p>Request 1–{MAX_LINEUPS} tournament lineups; five is the default. Team and game limits are maximums, not required counts.</p>
    {format === "showdown" && <p>Max Captain exposure limits how often any one player can be Captain; it does not limit that player’s FLEX appearances. At {value.captainMaxExposure}% across {value.numLineups} requested lineups, each player can captain at most {Math.ceil(value.numLineups * value.captainMaxExposure / 100 - 1e-9)} lineup(s). Fractional appearances round up. Use 40% for at most 2 of 5, or 60% for at most 3 of 5.</p>}
    <details><summary>Exposure, overlap and risk limits</summary>
      <div className="form-row">
        <OptionalNumber label="Max shared players between lineups" field="max_lineup_overlap" value={value.maxLineupOverlap} onChange={next => set("maxLineupOverlap", next)} choices={format === "classic" ? [7, 6, 5, 4] : [5, 4, 3, 2]} maximum={size} defaultLabel="No additional limit" helper="Counts shared players regardless of Captain/FLEX slot. Each lineup must still be distinct." />
        {format === "classic" && <OptionalNumber label="Max lineups per primary game" field="max_lineups_per_primary_game" value={value.primaryGameCap} onChange={next => set("primaryGameCap", next)} choices={[4, 3, 2, 1]} minimum={1} maximum={MAX_LINEUPS} defaultLabel="No limit" helper="Counts each quarterback's game; opposite quarterback directions count together." />}
        <OptionalNumber label="Max exposure per elevated-risk player" field="elevated_player_max_exposure" value={value.elevatedExposurePercent} onChange={next => set("elevatedExposurePercent", next)} choices={[80, 60, 40, 20]} maximum={100} percent defaultLabel="No additional limit" />
        <OptionalNumber label="Max elevated-risk players per lineup" field="max_elevated_players_per_lineup" value={value.maxElevatedPerLineup} onChange={next => set("maxElevatedPerLineup", next)} choices={[0, 1, 2]} maximum={size} defaultLabel="No additional limit" />
      </div>
      {format === "showdown" && <div className="form-row">
        {percent("Core max (%)", "coreMaxExposure")}
        {percent("Starting QB max (%)", "startingQbMaxExposure")}{percent("Cheap punt max (%)", "cheapPuntMaxExposure")}
      </div>}
      <p>Ordinary exposure caps round up to whole appearances; elevated-risk caps round down. Caps use the requested lineup count. Locks require a player in every lineup and override ordinary player caps. Conflicting hard limits may prevent the full count; limits are never relaxed.</p>
      {format === "showdown" && <small>Starting QB limits apply to verified starters; cheap punts have base salary ≤ $1,000. Core limits apply to the remaining players.</small>}
    </details>
  </fieldset>;
}
