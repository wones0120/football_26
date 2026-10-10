import { useState, type Dispatch, type SetStateAction, type Ref } from "react";
import type { LargeGppControls } from "./classicLargeGppControls";

export function OptionalNumber({ label, field, value, onChange, choices, defaultLabel = "Strategy default", minimum = 0, maximum, percent = false, helper }: {
  label: string; value: number | null; onChange: (value: number | null) => void;
  field: string;
  choices: number[]; defaultLabel?: string; minimum?: number; maximum?: number; percent?: boolean; helper?: string;
}) {
  const [custom, setCustom] = useState(value !== null && !choices.includes(value));
  return <div className="portfolio-control">
    <label>{label}
      <select data-portfolio-field={field} data-controlled-value={value === null ? "default" : String(value)} data-custom-mode={custom}
        value={value === null ? "default" : custom || !choices.includes(value) ? "custom" : String(value)}
        onChange={(event) => { const next = event.target.value; setCustom(next === "custom"); onChange(next === "default" ? null : next === "custom" ? value ?? minimum : Number(next)); }}>
        <option value="default">{defaultLabel}</option>
        {choices.map((choice) => <option key={choice} value={choice}>{choice}{percent ? "%" : ""}</option>)}
        <option value="custom">Custom</option>
      </select>
    </label>
    {value !== null && (custom || !choices.includes(value)) && <label>Custom {label.toLowerCase()}
      <input data-portfolio-field={field} type="number" min={minimum} max={maximum} step={percent ? "any" : 1} value={value}
        onChange={(event) => onChange(event.target.value === "" ? NaN : Number(event.target.value))} />
    </label>}
    {helper && <small>{helper}</small>}
  </div>;
}

export function ClassicLargeGppPortfolioControls({ numLineups, setNumLineups, maxExposure, setMaxExposure, gameCap, setGameCap, controls, setControls, disabled = false, rootRef }: {
  numLineups: number; setNumLineups: (value: number) => void; maxExposure: number; setMaxExposure: (value: number) => void;
  gameCap: number | null; setGameCap: (value: number | null) => void;
  controls: LargeGppControls; setControls: Dispatch<SetStateAction<LargeGppControls>>; disabled?: boolean;
  rootRef?: Ref<HTMLElement>;
}) {
  return <section ref={rootRef} className="status-card nested-card classic-large-portfolio-controls">
    <h3>Portfolio diversification</h3>
    <p>Overlap and elevated-risk limits are independent. You can choose a shared-player limit while keeping the risk limits at Strategy default.</p>
    <p role="status">{disabled ? "Submitted choices are locked while the request is prepared." : "Next request"} · {numLineups} lineups · {maxExposure}% max exposure · primary-game cap {gameCap ?? "No limit"} · max shared players {controls.maxLineupOverlap ?? "Strategy default (7)"}</p>
    <fieldset disabled={disabled} className="portfolio-controls-fields">
    <div className="form-row">
      <label>Number of lineups<input data-portfolio-field="num_lineups" type="number" min={1} max={50} step={1} value={numLineups} onChange={(event) => setNumLineups(Number(event.target.value))} /></label>
      <label>Max player exposure (%)<input data-portfolio-field="max_exposure" type="number" min={1} max={100} value={maxExposure} onChange={(event) => setMaxExposure(Number(event.target.value))} /></label>
      <OptionalNumber label="Max lineups per primary game" field="max_lineups_per_primary_game" value={gameCap} onChange={setGameCap} choices={[4, 3, 2]} defaultLabel="No limit" minimum={1}
        helper="Limits how many selected lineups may use the same game as their primary QB-stack game. Opposite QB directions from the same game count together." />
      <OptionalNumber label="Max shared players between lineups" field="max_lineup_overlap" value={controls.maxLineupOverlap} onChange={(value) => setControls((current) => ({ ...current, maxLineupOverlap: value }))} choices={[7, 6, 5, 4]} maximum={8}
        helper="Limits the number of shared players between any two selected lineups." />
      <OptionalNumber label="Max exposure per elevated-risk player" field="elevated_player_max_exposure" value={controls.elevatedExposurePercent} onChange={(value) => setControls((current) => ({ ...current, elevatedExposurePercent: value }))} choices={[80, 60, 40, 20]} maximum={100} percent
        helper="Limits how many selected lineups may contain the same player currently classified as elevated injury/availability risk. Explicit caps round down: floor(requested lineups × percentage)." />
    </div>
    <details><summary>Advanced portfolio constraints · Max elevated-risk players per lineup: {controls.maxElevatedPerLineup ?? "Strategy default"}</summary>
      <div className="form-row">
        <OptionalNumber label="Max elevated-risk players per lineup" field="max_elevated_players_per_lineup" value={controls.maxElevatedPerLineup} onChange={(value) => setControls((current) => ({ ...current, maxElevatedPerLineup: value }))} choices={[0, 1, 2]} maximum={9}
          helper="A separate count limit within each lineup. Strategy default adds no Large-GPP risk cap." />
      </div>
    </details>
    </fieldset>
  </section>;
}
