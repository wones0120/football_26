import assert from "node:assert/strict";
import test from "node:test";

import type { PredictionRow, SlateWeatherGame } from "../src/api.ts";
import {
  buildGameMatrixRows,
  formatFreshness,
  formatPrecipitationMm,
  formatTemperatureC,
  formatWindMps,
  shouldShowHistoricalActual,
  weatherWarnings,
} from "../src/weatherPresentation.ts";

function prediction(overrides: Partial<PredictionRow>): PredictionRow {
  return {
    player_id: "player-1",
    player_display_name: "Test Player",
    position: "WR",
    recent_team: "WAS",
    opponent_team: "DAL",
    season: 2025,
    week: 11,
    predicted_mean: 10,
    predicted_p10: 5,
    predicted_p25: 7,
    predicted_p50: 10,
    predicted_p75: 13,
    predicted_p90: 16,
    model: "test",
    last3_points: [],
    last3_avg: 0,
    recent_median: 0,
    recent_robust: 0,
    delta_vs_last3: 0,
    team_pos_avg: 0,
    adj_mean: 0,
    adj_mean_base: 0,
    matchup_factor: 1,
    adj_mean_final: 0,
    ...overrides,
  };
}

function weatherGame(overrides: Partial<SlateWeatherGame>): SlateWeatherGame {
  return {
    game_id: "2025_11_WAS_DAL",
    identity_status: "resolved",
    candidate_game_ids: [],
    home_team: "DAL",
    away_team: "WAS",
    kickoff_at: "2025-11-16T18:00:00Z",
    schedule_status: "REG",
    weather_state: "available",
    venue: null,
    forecast: null,
    actual: null,
    latest_capture_status: "available",
    latest_capture_reason: null,
    quality_flags: [],
    ...overrides,
  };
}

test("unions canonical weather matchups with projection-only games and preserves explicit states", () => {
  const rows = buildGameMatrixRows(
    [
      prediction({ game_id: "2025_11_WAS_DAL", predicted_mean: 12 }),
      prediction({
        player_id: "player-2",
        game_id: "2025_11_WAS_DAL",
        recent_team: "DAL",
        opponent_team: "WSH",
        predicted_mean: 16,
      }),
      prediction({
        player_id: "player-3",
        game_id: "2025_11_BUF_MIA",
        recent_team: "BUF",
        opponent_team: "MIA",
        predicted_mean: 9,
      }),
    ],
    [],
    [
      weatherGame({ weather_state: "stale" }),
      weatherGame({
        game_id: "2025_11_NYG_PHI",
        away_team: "NYG",
        home_team: "PHI",
        weather_state: "indoor",
      }),
    ],
    "missing"
  );

  assert.equal(rows.length, 3);
  assert.equal(rows.find((row) => row.gameId === "2025_11_WAS_DAL")?.avgProjection, "14.0");
  assert.equal(rows.find((row) => row.gameId === "2025_11_WAS_DAL")?.weatherState, "stale");
  assert.equal(rows.find((row) => row.gameId === "2025_11_NYG_PHI")?.weatherState, "indoor");
  assert.equal(rows.find((row) => row.gameId === "2025_11_BUF_MIA")?.weatherState, "missing");
});

test("does not truncate canonical weather matchups from the pressure matrix", () => {
  const games = Array.from({ length: 10 }, (_, index) =>
    weatherGame({
      game_id: `game-${index}`,
      home_team: `H${index}`,
      away_team: `A${index}`,
    })
  );

  assert.equal(buildGameMatrixRows([], [], games).length, 10);
});

test("passes through each canonical weather state without collapsing warnings", () => {
  const states = ["available", "indoor", "stale", "missing", "error"] as const;
  const games = states.map((weather_state, index) =>
    weatherGame({
      game_id: `state-${index}`,
      home_team: `H${index}`,
      away_team: `A${index}`,
      weather_state,
    })
  );

  assert.deepEqual(
    new Set(buildGameMatrixRows([], [], games).map((row) => row.weatherState)),
    new Set(states)
  );
});

test("formats normalized forecast values for a US-facing matchup display", () => {
  assert.equal(formatTemperatureC(20), "68°F");
  assert.equal(formatWindMps(5), "11 mph");
  assert.equal(formatPrecipitationMm(0.25), "0.3 mm");
  assert.equal(formatFreshness(45 * 60), "45m old at cutoff");
  assert.equal(formatFreshness(24 * 60 * 60), "24h old at cutoff");
});

test("keeps historical actuals behind the historical-only display gate", () => {
  const game = weatherGame({
    actual: {
      data_kind: "retrospective_actual_weather",
      observation_basis: "completed_game_summary",
      replay_eligible: false,
      effective_at: "2025-11-16T21:00:00Z",
      weather_status: "available",
      stadium: "Example Stadium",
      roof: "outdoors",
      surface: "grass",
      temperature_f: 48,
      wind_mph: 14,
      source_system: "nflverse",
      quality_flags: [],
    },
  });

  assert.equal(shouldShowHistoricalActual("historical", game), true);
  assert.equal(shouldShowHistoricalActual("current", game), false);
  assert.equal(shouldShowHistoricalActual("historical", weatherGame({ actual: null })), false);
});

test("turns service quality flags and capture failures into readable warnings", () => {
  const warnings = weatherWarnings(
    weatherGame({
      identity_status: "ambiguous",
      latest_capture_reason: "provider timeout",
      quality_flags: ["forecast_stale", "salary_team_pair:DAL-WAS"],
    })
  );

  assert.deepEqual(warnings, [
    "Game identity is ambiguous.",
    "The latest eligible forecast is stale.",
    "Latest capture: provider timeout",
  ]);
});
