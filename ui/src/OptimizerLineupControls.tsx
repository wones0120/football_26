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
      {format === "classic" && <>
        <label>Max players / team<input type="number" min={1} max={4} step={1} value={value.maxPlayersPerTeam} onChange={event => set("maxPlayersPerTeam", Number(event.target.value))} /></label>
        <label>Max players / game<input type="number" min={1} max={9} step={1} value={value.maxPlayersPerGame} onChange={event => set("maxPlayersPerGame", Number(event.target.value))} /></label>
      </>}
    </div>
    <p>Request 1–{MAX_LINEUPS} tournament lineups; five is the default. Team and game limits are maximums, not required counts.</p>
    <details><summary>Exposure, overlap and risk limits</summary>
      <div className="form-row">
        <OptionalNumber label="Max shared players between lineups" field="max_lineup_overlap" value={value.maxLineupOverlap} onChange={next => set("maxLineupOverlap", next)} choices={format === "classic" ? [7, 6, 5, 4] : [5, 4, 3, 2]} maximum={size} defaultLabel="No additional limit" helper="Counts shared players regardless of Captain/FLEX slot. Each lineup must still be distinct." />
        {format === "classic" && <OptionalNumber label="Max lineups per primary game" field="max_lineups_per_primary_game" value={value.primaryGameCap} onChange={next => set("primaryGameCap", next)} choices={[4, 3, 2, 1]} minimum={1} maximum={MAX_LINEUPS} defaultLabel="No limit" helper="Counts each quarterback's game; opposite quarterback directions count together." />}
        <OptionalNumber label="Max exposure per elevated-risk player" field="elevated_player_max_exposure" value={value.elevatedExposurePercent} onChange={next => set("elevatedExposurePercent", next)} choices={[80, 60, 40, 20]} maximum={100} percent defaultLabel="No additional limit" />
        <OptionalNumber label="Max elevated-risk players per lineup" field="max_elevated_players_per_lineup" value={value.maxElevatedPerLineup} onChange={next => set("maxElevatedPerLineup", next)} choices={[0, 1, 2]} maximum={size} defaultLabel="No additional limit" />
      </div>
      {format === "showdown" && <div className="form-row">
        {percent("CPT max (%)", "captainMaxExposure")}{percent("Core max (%)", "coreMaxExposure")}
        {percent("Starting QB max (%)", "startingQbMaxExposure")}{percent("Cheap punt max (%)", "cheapPuntMaxExposure")}
      </div>}
      <p>Ordinary exposure caps round up to whole appearances; elevated-risk caps round down. Caps use the requested lineup count. Locks require a player in every lineup and override ordinary player caps. Conflicting hard limits may prevent the full count; limits are never relaxed.</p>
      {format === "showdown" && <small>Starting QB limits apply to verified starters; cheap punts have base salary ≤ $1,000. Core limits apply to the remaining players.</small>}
    </details>
  </fieldset>;
}
