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


class SourceSnapshot(Base):
    """Content-addressed evidence captured at a trustworthy observation time."""

    __tablename__ = "source_snapshot"
    __table_args__ = (
        Index(
            "idx_source_snapshot_scope_observed",
            "source_system",
            "dataset",
            "season",
            "week",
            "slate",
            "observed_at",
        ),
        Index("idx_source_snapshot_content_sha256", "content_sha256"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int | None] = mapped_column(Integer)
    slate: Mapped[str | None] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slate_lock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observation_basis: Mapped[str] = mapped_column(String(48), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_path: Mapped[str | None] = mapped_column(Text)
    source_uri: Mapped[str | None] = mapped_column(Text)
    source_license: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)


class SourceSnapshotIngestRun(Base):
    """Append-only link from immutable source evidence to a downstream ingest run."""

    __tablename__ = "source_snapshot_ingest_run"

    snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("source_snapshot.snapshot_id"),
        primary_key=True,
    )
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


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


class RawNflWeeklyRoster(Base):
    __tablename__ = "raw_nfl_weekly_roster"
    __table_args__ = (
        Index("idx_raw_nfl_weekly_roster_slice", "season", "week", "team"),
        Index("idx_raw_nfl_weekly_roster_gsis", "gsis_id"),
        Index("idx_raw_nfl_weekly_roster_pfr", "pfr_id"),
    )

    raw_nfl_weekly_roster_id: Mapped[int] = mapped_column(
        BIGINT_ID, primary_key=True, autoincrement=True
    )
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    game_type: Mapped[str | None] = mapped_column(String(16))
    team: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    depth_chart_position: Mapped[str | None] = mapped_column(String(16))
    roster_status: Mapped[str | None] = mapped_column(String(32))
    player_name: Mapped[str | None] = mapped_column(String(128))
    gsis_id: Mapped[str | None] = mapped_column(String(64))
    pfr_id: Mapped[str | None] = mapped_column(String(64))
    raw_row_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class RawNflSnapCount(Base):
    __tablename__ = "raw_nfl_snap_count"
    __table_args__ = (
        Index("idx_raw_nfl_snap_count_slice", "season", "week", "team"),
        Index("idx_raw_nfl_snap_count_player", "pfr_player_id", "season", "week"),
    )

    raw_nfl_snap_count_id: Mapped[int] = mapped_column(
        BIGINT_ID, primary_key=True, autoincrement=True
    )
    ingest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ingest_run.ingest_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    game_type: Mapped[str | None] = mapped_column(String(16))
    game_id: Mapped[str | None] = mapped_column(String(64))
    pfr_game_id: Mapped[str | None] = mapped_column(String(64))
    pfr_player_id: Mapped[str | None] = mapped_column(String(64))
    player_name: Mapped[str | None] = mapped_column(String(128))
    team: Mapped[str | None] = mapped_column(String(16))
    opponent: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    offense_snaps: Mapped[int | None] = mapped_column(Integer)
    offense_pct: Mapped[float | None] = mapped_column(Float)
    defense_snaps: Mapped[int | None] = mapped_column(Integer)
    defense_pct: Mapped[float | None] = mapped_column(Float)
    st_snaps: Mapped[int | None] = mapped_column(Integer)
    st_pct: Mapped[float | None] = mapped_column(Float)
    raw_row_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class CuratedPlayerGameParticipation(Base):
    __tablename__ = "curated_player_game_participation"
    __table_args__ = (
        UniqueConstraint(
            "season", "week", "game_id", "player_master_id", "team",
            name="uq_curated_player_game_participation",
        ),
        Index("idx_curated_participation_slice", "season", "week", "team"),
        Index("idx_curated_participation_player", "player_master_id", "season", "week"),
    )

    curated_player_game_participation_id: Mapped[int] = mapped_column(
        BIGINT_ID, primary_key=True, autoincrement=True
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False)
    game_type: Mapped[str | None] = mapped_column(String(16))
    player_master_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("player_master.player_master_id"), nullable=False
    )
    player_name: Mapped[str | None] = mapped_column(String(128))
    team: Mapped[str] = mapped_column(String(16), nullable=False)
    opponent: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(String(16))
    roster_status: Mapped[str | None] = mapped_column(String(32))
    participation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    participation_reason: Mapped[str] = mapped_column(String(48), nullable=False)
    offense_snaps: Mapped[int | None] = mapped_column(Integer)
    offense_snap_share: Mapped[float | None] = mapped_column(Float)
    defense_snaps: Mapped[int | None] = mapped_column(Integer)
    defense_snap_share: Mapped[float | None] = mapped_column(Float)
    st_snaps: Mapped[int | None] = mapped_column(Integer)
    st_snap_share: Mapped[float | None] = mapped_column(Float)
    box_score_activity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    roster_ingest_run_id: Mapped[str | None] = mapped_column(String(36))
    snap_ingest_run_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class TeamGameAvailabilityFeature(Base):
    __tablename__ = "features_team_game_availability"
    __table_args__ = (
        UniqueConstraint(
            "season", "week", "game_id", "team",
            name="uq_features_team_game_availability",
        ),
        Index("idx_features_team_game_availability_slice", "season", "week", "team"),
    )

    features_team_game_availability_id: Mapped[int] = mapped_column(
        BIGINT_ID, primary_key=True, autoincrement=True
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team: Mapped[str] = mapped_column(String(16), nullable=False)
    opponent: Mapped[str] = mapped_column(String(16), nullable=False)
    team_offense_missing_share_lag1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    team_defense_missing_share_lag1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    team_offense_missing_count_lag1: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    team_defense_missing_count_lag1: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opponent_offense_missing_share_lag1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opponent_defense_missing_share_lag1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opponent_offense_missing_count_lag1: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opponent_defense_missing_count_lag1: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    team_source_game_id: Mapped[str | None] = mapped_column(String(64))
    team_source_week: Mapped[int | None] = mapped_column(Integer)
    opponent_source_game_id: Mapped[str | None] = mapped_column(String(64))
    opponent_source_week: Mapped[int | None] = mapped_column(Integer)
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
    team_offense_missing_share_lag1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    team_defense_missing_share_lag1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opponent_offense_missing_share_lag1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opponent_defense_missing_share_lag1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
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


class OperationalJob(Base):
    """Durable work item claimed by the standalone worker process."""

    __tablename__ = "operational_job"
    __table_args__ = (
        UniqueConstraint(
            "job_type",
            "idempotency_key",
            name="uq_operational_job_type_idempotency_key",
        ),
        Index(
            "idx_operational_job_dispatch",
            "status",
            "available_at",
            "created_at",
        ),
        Index(
            "idx_operational_job_lease",
            "status",
            "lease_expires_at",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="queued",
    )
    stage: Mapped[str] = mapped_column(
        String(64),
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
    run_id: Mapped[str | None] = mapped_column(String(255))
    checkpoint_json: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    result_json: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
    )
    locked_by: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
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


class WeeklyRun(Base):
    """One durable end-to-end weekly workflow execution."""

    __tablename__ = "weekly_run"
    __table_args__ = (
        Index(
            "idx_weekly_run_scope",
            "season",
            "week",
            "slate",
            "created_at",
        ),
        Index("idx_weekly_run_status", "status", "updated_at"),
    )

    weekly_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operational_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operational_job.job_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slate: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="queued",
    )
    current_stage: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="queued",
    )
    data_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime)
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


class WeeklyRunStage(Base):
    """Inspectable checkpoint for one stage of a weekly workflow."""

    __tablename__ = "weekly_run_stage"
    __table_args__ = (
        UniqueConstraint(
            "weekly_run_id",
            "stage_order",
            name="uq_weekly_run_stage_order",
        ),
        Index("idx_weekly_run_stage_status", "status", "updated_at"),
    )

    weekly_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("weekly_run.weekly_run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    stage: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="pending",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    message: Mapped[str | None] = mapped_column(Text)
    counts_json: Mapped[dict] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        default=dict,
    )
    logs_json: Mapped[list] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        default=list,
    )
    warnings_json: Mapped[list] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        default=list,
    )
    errors_json: Mapped[list] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        default=list,
    )
    artifact_ids_json: Mapped[dict] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        default=dict,
    )
    result_json: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
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
