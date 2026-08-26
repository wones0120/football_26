from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

# These modules are the production entry points that create projection,
# simulation, or optimizer decisions. Weather remains read-only War Room
# context until a separate, explicitly reviewed feature contract is approved.
DECISION_INPUT_MODULES = (
    "backend/app/product_services/predictions.py",
    "backend/app/product_services/simulations.py",
    "backend/app/product_services/optimizer.py",
    "backend/app/product_services/gpp_optimizer.py",
    "backend/app/services/simulation.py",
    "backend/app/services/ultimate_lineup_runs.py",
)

FORBIDDEN_WEATHER_INPUT_REFERENCES = (
    "CuratedGameWeather",
    "WeatherForecastSnapshot",
    "curated_game_weather",
    "weather_forecast_snapshot",
    "services.current_weather_forecast",
    "services.slate_weather",
    "services.weather_forecast_backfill",
    "slate_game_weather_v1",
)


def test_weather_tables_are_not_decision_inputs() -> None:
    violations: dict[str, list[str]] = {}
    for relative_path in DECISION_INPUT_MODULES:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        matched = [
            reference
            for reference in FORBIDDEN_WEATHER_INPUT_REFERENCES
            if reference in source
        ]
        if matched:
            violations[relative_path] = matched

    assert violations == {}
