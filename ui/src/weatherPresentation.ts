import type {
  NewsMonitorSignal,
  PredictionRow,
  SlateWeatherGame,
  SlateWeatherResponse,
  SlateWeatherState,
} from "./api";

export type WeatherDisplayState = SlateWeatherState | "loading";

export type GameMatrixRow = {
  key: string;
  gameId: string | null;
  matchup: string;
  pressure: string;
  avgProjection: string;
  affectedPlayers: number;
  risk: string;
  kickoffAt: string | null;
  weatherState: WeatherDisplayState;
  weather: SlateWeatherGame | null;
};

const TEAM_ALIASES: Record<string, string> = {
  JAC: "JAX",
  LA: "LAR",
  OAK: "LV",
  SD: "LAC",
  STL: "LAR",
  WFT: "WAS",
  WSH: "WAS",
};

const WEATHER_WARNING_LABELS: Record<string, string> = {
  actual_conditions_missing: "Completed game actual conditions are unavailable.",
  forecast_capture_error: "The latest forecast refresh failed.",
  forecast_missing: "No cutoff-safe forecast is available.",
  forecast_partial: "The provider forecast is missing one or more required values.",
  forecast_stale: "The latest eligible forecast is stale.",
  kickoff_missing: "Kickoff time is unavailable.",
  schedule_missing: "The canonical schedule row is unavailable.",
  slate_game_identity_incomplete: "The slate contains unresolved game identity.",
  venue_mapping_ambiguous: "Venue mapping is ambiguous.",
  venue_mapping_missing: "Venue mapping is unavailable.",
  venue_mapping_unresolved: "Venue mapping is unresolved.",
  venue_missing: "Venue metadata is unavailable.",
};

function titleCase(value: string | null | undefined) {
  if (!value) return "Unknown";
  return value
    .replaceAll("_", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function projectionValue(row: PredictionRow) {
  return row.adj_mean_final || row.adj_mean || row.predicted_mean || 0;
}

function canonicalTeam(value: string | null | undefined) {
  const normalized = value?.trim().toUpperCase() ?? "";
  return TEAM_ALIASES[normalized] ?? normalized;
}

function teamPair(left: string | null | undefined, right: string | null | undefined) {
  const teams = [canonicalTeam(left), canonicalTeam(right)].filter(Boolean);
  if (teams.length !== 2 || teams[0] === teams[1]) return null;
  return teams.sort().join("|");
}

function unresolvedTeamPair(game: SlateWeatherGame) {
  const flag = game.quality_flags.find((value) => value.startsWith("salary_team_pair:"));
  if (!flag) return null;
  const [left, right] = flag.slice("salary_team_pair:".length).split("-", 2);
  return teamPair(left, right);
}

function weatherTeamPair(game: SlateWeatherGame) {
  return teamPair(game.home_team, game.away_team) ?? unresolvedTeamPair(game);
}

function matchupLabel(game: SlateWeatherGame, pair: string | null) {
  if (game.away_team && game.home_team) {
    return `${canonicalTeam(game.away_team)} @ ${canonicalTeam(game.home_team)}`;
  }
  if (pair) {
    return pair.replace("|", " vs ");
  }
  return game.identity_status === "ambiguous" ? "Ambiguous Matchup" : "Unresolved Matchup";
}

type ProjectionGroup = {
  key: string;
  gameId: string | null;
  pair: string;
  teams: [string, string];
  projections: number[];
};

function gamePressure(
  projections: number[],
  teams: [string, string],
  signals: NewsMonitorSignal[]
) {
  const relatedSignals = signals.filter((signal) => {
    const signalTeam = canonicalTeam(signal.team);
    return Boolean(signalTeam) && teams.includes(signalTeam);
  });
  const avgProjection =
    projections.length === 0
      ? 0
      : projections.reduce((sum, current) => sum + current, 0) / projections.length;
  const highSignalCount = relatedSignals.filter(
    (signal) => signal.dfs_relevance?.toLowerCase() === "high"
  ).length;

  let pressure = "C";
  if (avgProjection >= 14 || highSignalCount >= 2) {
    pressure = "A";
  } else if (avgProjection >= 10 || relatedSignals.length >= 1) {
    pressure = "B";
  }

  return {
    pressure,
    avgProjection: avgProjection.toFixed(1),
    affectedPlayers: relatedSignals.length,
    risk: relatedSignals[0]?.signal_type ? titleCase(relatedSignals[0].signal_type) : "Stable",
  };
}

export function buildGameMatrixRows(
  predictions: PredictionRow[],
  signals: NewsMonitorSignal[],
  weatherGames: SlateWeatherGame[],
  fallbackState: WeatherDisplayState = "missing"
): GameMatrixRow[] {
  const groups = new Map<string, ProjectionGroup>();
  const groupsByGameId = new Map<string, ProjectionGroup>();
  const groupsByPair = new Map<string, ProjectionGroup>();

  predictions.forEach((prediction) => {
    const pair = teamPair(prediction.recent_team, prediction.opponent_team);
    if (!pair) return;
    const gameId = prediction.game_id || null;
    const key = `pair:${pair}`;
    const teams = pair.split("|") as [string, string];
    const group = groups.get(key) ?? { key, gameId, pair, teams, projections: [] };
    if (!group.gameId && gameId) group.gameId = gameId;
    group.projections.push(projectionValue(prediction));
    groups.set(key, group);
    if (gameId) groupsByGameId.set(gameId, group);
    groupsByPair.set(pair, group);
  });

  const usedGroups = new Set<string>();
  const rows: GameMatrixRow[] = weatherGames.map((weather, index) => {
    const pair = weatherTeamPair(weather);
    const group =
      (weather.game_id ? groupsByGameId.get(weather.game_id) : undefined) ??
      (pair ? groupsByPair.get(pair) : undefined);
    if (group) usedGroups.add(group.key);
    const teams = pair ? (pair.split("|") as [string, string]) : (["", ""] as [string, string]);
    return {
      key: weather.game_id ?? `weather:${weather.identity_status}:${pair ?? index}`,
      gameId: weather.game_id,
      matchup: matchupLabel(weather, pair),
      ...gamePressure(group?.projections ?? [], teams, signals),
      kickoffAt: weather.kickoff_at,
      weatherState: weather.weather_state,
      weather,
    };
  });

  groups.forEach((group) => {
    if (usedGroups.has(group.key)) return;
    rows.push({
      key: group.key,
      gameId: group.gameId,
      matchup: group.teams.join(" vs "),
      ...gamePressure(group.projections, group.teams, signals),
      kickoffAt: null,
      weatherState: fallbackState,
      weather: null,
    });
  });

  return rows.sort(
    (left, right) =>
      Number(right.avgProjection) - Number(left.avgProjection) || left.matchup.localeCompare(right.matchup)
  );
}

export function weatherStateLabel(state: WeatherDisplayState) {
  return titleCase(state);
}

export function formatTemperatureC(value: number | null | undefined) {
  if (!Number.isFinite(value)) return "--";
  return `${Math.round((Number(value) * 9) / 5 + 32)}°F`;
}

export function formatWindMps(value: number | null | undefined) {
  if (!Number.isFinite(value)) return "--";
  return `${Math.round(Number(value) * 2.236936)} mph`;
}

export function formatPrecipitationMm(value: number | null | undefined) {
  if (!Number.isFinite(value)) return "--";
  return `${Number(value).toFixed(1)} mm`;
}

export function formatRoof(value: string | null | undefined) {
  if (!value) return "Unknown";
  const labels: Record<string, string> = {
    fixed_indoor: "Fixed indoor",
    outdoor: "Outdoor",
    retractable: "Retractable (default)",
  };
  return labels[value] ?? titleCase(value);
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

export function formatFreshness(ageSeconds: number | null | undefined) {
  if (!Number.isFinite(ageSeconds)) return "Unknown";
  const seconds = Math.max(0, Number(ageSeconds));
  if (seconds < 60) return "Less than 1m old at cutoff";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m old at cutoff`;
  if (seconds < 172800) return `${(seconds / 3600).toFixed(seconds < 7200 ? 1 : 0)}h old at cutoff`;
  return `${(seconds / 86400).toFixed(seconds < 172800 ? 1 : 0)}d old at cutoff`;
}

export function formatForecastSource(game: SlateWeatherGame) {
  const forecast = game.forecast;
  if (!forecast) return "No eligible forecast";
  return `${titleCase(forecast.provider)} · ${forecast.provider_model}`;
}

export function formatForecastTimestamp(game: SlateWeatherGame) {
  const forecast = game.forecast;
  if (!forecast) return "No cutoff-safe timestamp";
  return forecast.data_kind === "current_forecast_capture"
    ? `Captured ${formatDateTime(forecast.received_at)}`
    : `24h basis ${formatDateTime(forecast.forecast_basis_at)}`;
}

export function formatWeatherWarning(flag: string) {
  return WEATHER_WARNING_LABELS[flag] ?? `${titleCase(flag)}.`;
}

export function weatherWarnings(game: SlateWeatherGame) {
  const warnings = game.quality_flags
    .filter((flag) => !flag.startsWith("salary_team_pair:"))
    .map(formatWeatherWarning);
  if (game.identity_status !== "resolved") {
    warnings.unshift(`Game identity is ${game.identity_status}.`);
  }
  if (game.latest_capture_reason) {
    warnings.push(`Latest capture: ${game.latest_capture_reason}`);
  }
  return [...new Set(warnings)];
}

export function shouldShowHistoricalActual(
  requestKind: SlateWeatherResponse["request_kind"] | null | undefined,
  game: SlateWeatherGame | null | undefined
) {
  return requestKind === "historical" && game?.actual !== null && game?.actual !== undefined;
}
