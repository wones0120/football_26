from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")
BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class IngestRun(Base):
    __tablename__ = "ingest_run"

    ingest_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_table: Mapped[str] = mapped_column(String(64), nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text)
    source_checksum: Mapped[str | None] = mapped_column(String(128))
    season: Mapped[int | None] = mapped_column(Integer)
    week: Mapped[int | None] = mapped_column(Integer)
    slate: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running")
    rows_raw: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_curated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_unresolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class PlayerMaster(Base):
    __tablename__ = "player_master"

    player_master_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))
    primary_team: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class PlayerAlias(Base):
    __tablename__ = "player_alias"
    __table_args__ = (
        UniqueConstraint("source_system", "source_key", name="uq_player_alias_source_key"),
        Index(
            "idx_player_alias_name_team_pos",
            "source_system",
            "normalized_alias",
            "team",
            "position",
        ),
    )

    alias_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    player_master_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player_master.player_master_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(128), nullable=False)
    alias_name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(128), nullable=False)
    team: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    first_seen_season: Mapped[int | None] = mapped_column(Integer)
    first_seen_week: Mapped[int | None] = mapped_column(Integer)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class PlayerMappingRule(Base):
    __tablename__ = "player_mapping_rule"

    rule_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    match_pattern_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    player_master_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player_master.player_master_id", ondelete="CASCADE"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class UnresolvedPlayerQueue(Base):
    __tablename__ = "unresolved_player_queue"
    __table_args__ = (
        Index("idx_unresolved_status", "resolution_status", "source_system", "season", "week"),
    )

    unresolved_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_table: Mapped[str] = mapped_column(String(64), nullable=False)
    source_player_key: Mapped[str | None] = mapped_column(String(128))
    season: Mapped[int | None] = mapped_column(Integer)
    week: Mapped[int | None] = mapped_column(Integer)
    slate: Mapped[str | None] = mapped_column(String(64))
    raw_row_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    team: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    candidate_player_master_id: Mapped[str | None] = mapped_column(String(36))
    resolution_status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    resolved_player_master_id: Mapped[str | None] = mapped_column(String(36))
    resolved_by: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class RawSalaryRow(Base):
    __tablename__ = "raw_salary_row"

    raw_salary_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    source_player_key: Mapped[str | None] = mapped_column(String(128))
    raw_row_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class RawInjuryRow(Base):
    __tablename__ = "raw_injury_row"

    raw_injury_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    source_player_key: Mapped[str | None] = mapped_column(String(128))
    raw_row_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class CuratedSalary(Base):
    __tablename__ = "curated_salary"
    __table_args__ = (
        UniqueConstraint(
            "season",
            "week",
            "slate",
            "source_system",
            "source_player_key",
            name="uq_curated_salary_row",
        ),
        Index("idx_curated_salary_player_master", "player_master_id", "season", "week"),
    )

    curated_salary_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    source_player_key: Mapped[str] = mapped_column(String(128), nullable=False)
    player_master_id: Mapped[str | None] = mapped_column(String(36))
    player_name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    team: Mapped[str | None] = mapped_column(String(16))
    opponent: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    roster_position: Mapped[str | None] = mapped_column(String(16))
    salary: Mapped[int | None] = mapped_column(Integer)
    game_info: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class CuratedInjury(Base):
    __tablename__ = "curated_injury"
    __table_args__ = (
        UniqueConstraint(
            "season",
            "week",
            "slate",
            "source_system",
            "source_player_key",
            name="uq_curated_injury_row",
        ),
        Index("idx_curated_injury_player_master", "player_master_id", "season", "week"),
    )

    curated_injury_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    source_player_key: Mapped[str] = mapped_column(String(128), nullable=False)
    player_master_id: Mapped[str | None] = mapped_column(String(36))
    player_name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    team: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    injury_status: Mapped[str | None] = mapped_column(String(64))
    injury_details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class RawNflSchedule(Base):
    __tablename__ = "raw_nfl_schedule"
    __table_args__ = (
        Index("idx_raw_nfl_schedule_season_week", "season", "week"),
        Index("idx_raw_nfl_schedule_game_id", "game_id"),
    )

    raw_nfl_schedule_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int | None] = mapped_column(Integer)
    game_id: Mapped[str | None] = mapped_column(String(64))
    home_team: Mapped[str | None] = mapped_column(String(16))
    away_team: Mapped[str | None] = mapped_column(String(16))
    game_type: Mapped[str | None] = mapped_column(String(32))
    kickoff: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(64))
    stadium: Mapped[str | None] = mapped_column(String(128))
    raw_row_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class RawNflWeeklyStat(Base):
    __tablename__ = "raw_nfl_weekly_stat"
    __table_args__ = (
        Index("idx_raw_nfl_weekly_stat_season_week", "season", "week"),
        Index("idx_raw_nfl_weekly_stat_player_id", "player_id"),
    )

    raw_nfl_weekly_stat_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[str | None] = mapped_column(String(64))
    player_name: Mapped[str | None] = mapped_column(String(128))
    team: Mapped[str | None] = mapped_column(String(16))
    opponent: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    game_id: Mapped[str | None] = mapped_column(String(64))
    raw_row_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class PlayerGameFeatureMatrix(Base):
    __tablename__ = "player_game_feature_matrix"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "season",
            "week",
            "game_id",
            "player_id",
            "position",
            name="uq_player_game_feature_row",
        ),
        Index("idx_pgfm_slice", "source_system", "season", "week"),
        Index("idx_pgfm_player", "source_system", "player_master_id", "season", "week"),
        Index("idx_pgfm_team_pos", "source_system", "team", "opponent", "position", "season", "week"),
    )

    player_game_feature_matrix_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    game_id: Mapped[str | None] = mapped_column(String(64))
    player_id: Mapped[str] = mapped_column(String(64), nullable=False)
    player_master_id: Mapped[str | None] = mapped_column(String(36))
    source_player_key: Mapped[str | None] = mapped_column(String(128))
    player_name: Mapped[str | None] = mapped_column(String(128))
    team: Mapped[str | None] = mapped_column(String(16))
    opponent: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str] = mapped_column(String(16), nullable=False)
    dk_points: Mapped[float] = mapped_column(Float, nullable=False)
    salary: Mapped[int | None] = mapped_column(Integer)
    slate: Mapped[str | None] = mapped_column(String(64))
    is_home: Mapped[bool | None] = mapped_column(Boolean)
    kickoff_bucket: Mapped[str | None] = mapped_column(String(16))
    game_total_line: Mapped[float | None] = mapped_column(Float)
    team_spread_line: Mapped[float | None] = mapped_column(Float)
    team_implied_total: Mapped[float | None] = mapped_column(Float)
    opponent_implied_total: Mapped[float | None] = mapped_column(Float)
    player_games_history: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    player_roll3_mean: Mapped[float | None] = mapped_column(Float)
    player_roll8_mean: Mapped[float | None] = mapped_column(Float)
    player_roll8_std: Mapped[float | None] = mapped_column(Float)
    player_vs_opp_roll4: Mapped[float | None] = mapped_column(Float)
    defense_pos_allowed_roll3: Mapped[float | None] = mapped_column(Float)
    defense_pos_allowed_roll8: Mapped[float | None] = mapped_column(Float)
    defense_pos_allowed_p90_roll8: Mapped[float | None] = mapped_column(Float)
    player_injury_status: Mapped[str | None] = mapped_column(String(24))
    team_skill_out_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    team_position_out_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class SimulationRun(Base):
    __tablename__ = "simulation_run"

    simulation_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    random_seed: Mapped[int | None] = mapped_column(Integer)
    parameters_json: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    players_considered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    players_simulated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class UltimateLineupRun(Base):
    __tablename__ = "ultimate_lineup_run"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_ultimate_lineup_run_idempotency_key",
        ),
        Index(
            "idx_ultimate_lineup_run_slice",
            "source_system",
            "season",
            "week",
            "slate",
            "created_at",
        ),
        Index(
            "idx_ultimate_lineup_run_status",
            "status",
            "updated_at",
        ),
    )

    ultimate_lineup_run_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="queued",
    )
    stage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="queued",
    )
    progress_current: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    progress_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    progress_message: Mapped[str | None] = mapped_column(Text)
    checkpoint_path: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    result_json: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class SimulatedPlayerOutcome(Base):
    __tablename__ = "simulated_player_outcome"
    __table_args__ = (
        UniqueConstraint("simulation_run_id", "source_player_key", name="uq_sim_outcome_run_source_key"),
        Index("idx_sim_outcome_run_p90", "simulation_run_id", "p90_points"),
    )

    simulated_player_outcome_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("simulation_run.simulation_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    player_master_id: Mapped[str | None] = mapped_column(String(36))
    source_player_key: Mapped[str | None] = mapped_column(String(128))
    player_name: Mapped[str] = mapped_column(String(128), nullable=False)
    team: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    salary: Mapped[int | None] = mapped_column(Integer)
    history_games: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean_points: Mapped[float] = mapped_column(Float, nullable=False)
    median_points: Mapped[float] = mapped_column(Float, nullable=False)
    p75_points: Mapped[float] = mapped_column(Float, nullable=False)
    p90_points: Mapped[float] = mapped_column(Float, nullable=False)
    p95_points: Mapped[float] = mapped_column(Float, nullable=False)
    ceiling_prob_20: Mapped[float] = mapped_column(Float, nullable=False)
    ceiling_prob_25: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class SimulationCalibrationFactor(Base):
    __tablename__ = "simulation_calibration_factor"
    __table_args__ = (
        Index(
            "idx_sim_calibration_lookup",
            "source_system",
            "slate",
            "scope",
            "scope_key",
            "calibrated_season",
            "calibrated_week",
        ),
        Index(
            "idx_sim_calibration_week",
            "source_system",
            "calibrated_season",
            "calibrated_week",
        ),
        Index(
            "idx_sim_calibration_low_salary",
            "source_system",
            "slate",
            "low_salary_threshold",
            "low_salary_hit_points",
        ),
    )

    simulation_calibration_factor_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)  # position | salary_bucket
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    calibrated_season: Mapped[int] = mapped_column(Integer, nullable=False)
    calibrated_week: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    low_salary_threshold: Mapped[int | None] = mapped_column(Integer)
    low_salary_hit_points: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class ProjectionResidualSnapshot(Base):
    __tablename__ = "projection_residual_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "season",
            "week",
            "slate",
            name="uq_projection_residual_snapshot_slice",
        ),
        Index(
            "idx_projection_residual_snapshot_lookup",
            "source_system",
            "slate",
            "season",
            "week",
            "status",
        ),
    )

    projection_residual_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    feature_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_version: Mapped[str] = mapped_column(String(64), nullable=False)
    observations_json: Mapped[list[dict]] = mapped_column(JSON_DOCUMENT, nullable=False)
    observations_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="completed",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
    )


class ActualTopLineup(Base):
    __tablename__ = "actual_top_lineup"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "season",
            "week",
            "slate",
            "lineup_rank",
            name="uq_actual_top_lineup_slice_rank",
        ),
        UniqueConstraint(
            "source_system",
            "season",
            "week",
            "slate",
            "lineup_key",
            name="uq_actual_top_lineup_slice_key",
        ),
        Index(
            "idx_actual_top_lineup_slice",
            "source_system",
            "season",
            "week",
            "slate",
            "lineup_rank",
        ),
    )

    actual_top_lineup_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    lineup_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_points: Mapped[float] = mapped_column(Float, nullable=False)
    salary_used: Mapped[int] = mapped_column(Integer, nullable=False)
    lineup_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class ActualTopLineupPlayer(Base):
    __tablename__ = "actual_top_lineup_player"
    __table_args__ = (
        UniqueConstraint(
            "actual_top_lineup_id",
            "slot_index",
            name="uq_actual_top_lineup_player_slot",
        ),
        Index(
            "idx_actual_top_lineup_player_lineup",
            "actual_top_lineup_id",
            "slot_index",
        ),
    )

    actual_top_lineup_player_id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    actual_top_lineup_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("actual_top_lineup.actual_top_lineup_id", ondelete="CASCADE"),
        nullable=False,
    )
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    roster_slot: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str] = mapped_column(String(16), nullable=False)
    player_master_id: Mapped[str | None] = mapped_column(String(36))
    source_player_key: Mapped[str | None] = mapped_column(String(128))
    player_name: Mapped[str] = mapped_column(String(128), nullable=False)
    team: Mapped[str | None] = mapped_column(String(16))
    salary: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_points: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
