from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Prefer this repo's .env values over inherited shell environment variables.
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    pghost: str = "localhost"
    pgport: int = 5432
    pgdatabase: str = "football_26_dev"
    pguser: str = "postgres"
    pgpassword: str = "postgres"

    database_url: str | None = None
    auto_create_tables: bool = True
    optimizer_result_cache_max_entries: int = Field(default=1, ge=0)
    optimizer_result_cache_ttl_seconds: float = Field(default=60, ge=0)
    # Remains legacy until the archived opportunity repair passes promotion review.
    player_opportunity_allocation_policy: Literal["legacy_v1", "team_window_v2"] = "legacy_v1"
    showdown_captain_model_path: str = "docs/showdown_captain_model_2024_2025.json"
    showdown_captain_prior_strength: float = 0.35
    # Market uses preparation's existing six-hour fresh band. Other clocks
    # remain independently configurable; rebuilding never resets source age.
    showdown_market_max_age_hours: float = Field(default=6, gt=0)
    showdown_projection_max_age_hours: float = Field(default=24, gt=0)
    showdown_player_status_max_age_hours: float = Field(default=24, gt=0)
    showdown_starting_qb_max_age_hours: float = Field(default=24, gt=0)
    showdown_salary_pool_max_age_hours: float = Field(default=168, gt=0)
    showdown_ownership_max_age_hours: float = Field(default=24, gt=0)
    # Classic source clocks are independent of Showdown and strategy tuning.
    classic_market_max_age_hours: float = Field(default=6, gt=0)
    classic_projection_max_age_hours: float = Field(default=24, gt=0)
    classic_player_status_max_age_hours: float = Field(default=24, gt=0)
    classic_salary_pool_max_age_hours: float = Field(default=168, gt=0)
    classic_ownership_max_age_hours: float = Field(default=24, gt=0)
    classic_value_driver_model_path: str = "docs/main_slate_value_driver_analysis_2024_2025.json"
    classic_value_driver_prior_strength: float = 0.45
    matchup_outcome_model_path: str = "docs/matchup_outcome_intelligence_2024_2025.json"
    matchup_outcome_prior_strength: float = 0.15
    matchup_prior_gate_model_path: str = "docs/matchup_prior_gate_20slates_5000.json"
    # Input support is separate from model activation; no live means are changed.
    dst_feature_support_manifest_path: str = ""
    dst_feature_support_manifest_sha256: str = ""
    dst_feature_support_output_root: str = "artifacts/dst_feature_support"
    dst_deployment_manifest_path: str = ""
    dst_deployment_manifest_sha256: str = ""
    source_snapshot_root: str = "artifacts/source_snapshots"
    weather_forecast_snapshot_root: str = "artifacts/weather_forecasts"
    weather_forecast_provider: str = "open_meteo_previous_runs"
    open_meteo_base_url: str = "https://previous-runs-api.open-meteo.com/v1/forecast"
    current_weather_forecast_provider: str = "open_meteo_forecast"
    open_meteo_forecast_base_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_api_key: str | None = None
    open_meteo_model: str = "ncep_gfs_seamless"
    open_meteo_fixed_lead_hours: int = 24
    open_meteo_min_request_interval_seconds: float = 0.11
    weather_forecast_refresh_interval_minutes: int = 60
    weather_forecast_stale_after_minutes: int = 120

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.pguser}:{self.pgpassword}"
            f"@{self.pghost}:{self.pgport}/{self.pgdatabase}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
