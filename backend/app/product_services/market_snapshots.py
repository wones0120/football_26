"""Canonical, append-only NFL market observations and point-in-time selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any, Iterable

from Database.dst import normalize_team


NFL_TEAM_NAMES = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}
CANONICAL_TEAMS = frozenset(NFL_TEAM_NAMES.values())


def load_current_markets(connection, *, season, week, cutoff):
    """Canonical game observations, independent of any player/feature join."""
    from sqlalchemy import text
    return [dict(r) for r in connection.execute(text("""
        SELECT market.* FROM target.market_snapshot market
        JOIN public.ingest_run run ON run.ingest_run_id=market.ingest_run_id
        WHERE market.season=:season AND market.week=:week AND run.status='completed'
          AND market.observed_at <= :cutoff AND market.ingested_at <= :cutoff
        ORDER BY market.observed_at,market.market_snapshot_id
    """), {"season":season,"week":week,"cutoff":cutoff}).mappings()]


def attach_pool_market_context(frame, observations, *, season, week, cutoff):
    """Apply the projection transform through canonical game/team relationships.

    Native DK game_info remains available for slate-lock validation. The model
    transform uses the matched canonical game ID, never a player projection ID.
    """
    import pandas as pd
    from .canonical_projection_inputs import apply_latest_market_context, MARKET_FEATURE_COLUMNS
    from .replay import parse_slate_lock
    rows = frame.copy()
    target = rows.rename(columns={"player_team":"recent_team"}).copy()
    target["season"], target["week"] = season,week
    target["game_id"] = None
    for field in MARKET_FEATURE_COLUMNS:
        if field not in target:
            target[field] = float("nan")
    safe = []
    for observation in observations:
        native = rows.loc[rows["player_team"].map(normalize_team).isin({observation["home_team"],observation["away_team"]}),"game_id"]
        lock = parse_slate_lock(native)
        if lock and abs((utc_time(observation["kickoff_at"]) - utc_time(lock)).total_seconds()) <= 60:
            safe.append(observation)
    target,audit = apply_latest_market_context(target,pd.DataFrame(safe),cutoff=cutoff)
    for field in ("game_total_line","team_spread_line","team_implied_total","opponent_implied_total",
                  "market_source_system","market_snapshot_row_id","market_observed_at"):
        if field in target: rows[field] = target[field]
    rows["canonical_game_id"] = target["game_id"]
    rows["market_context_point_in_time_safe"] = target["market_snapshot_row_id"].notna()
    snapshots = {str(r["market_snapshot_id"]):r.get("source_snapshot_id") for r in safe}
    rows["market_source_snapshot_id"] = rows["market_snapshot_row_id"].astype(str).map(snapshots)
    rows.attrs["canonical_market_association"] = audit
    return rows


def utc_time(value: datetime | str) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Market timestamps must include a timezone")
    return result.astimezone(UTC)


def canonical_team(value: str) -> str:
    team = NFL_TEAM_NAMES.get(value.strip(), normalize_team(value))
    if team not in CANONICAL_TEAMS:
        raise ValueError(f"Unknown NFL team: {value}")
    return team


@dataclass(frozen=True)
class MarketSnapshot:
    season: int
    week: int
    game_id: str
    home_team: str
    away_team: str
    kickoff_at: datetime
    game_total: float
    home_spread: float  # conventional bet sign: a favored home team is negative
    source: str
    source_game_id: str | None
    observed_at: datetime
    ingested_at: datetime
    snapshot_id: str | None = None
    provider_updated_at: datetime | None = None

    @property
    def home_implied_total(self) -> float:
        return (self.game_total - self.home_spread) / 2

    @property
    def away_implied_total(self) -> float:
        return (self.game_total + self.home_spread) / 2

    def sanity_errors(self) -> list[str]:
        errors = []
        if not isfinite(self.game_total) or not 20 <= self.game_total <= 80:
            errors.append("game_total_outside_20_80")
        if not isfinite(self.home_spread) or abs(self.home_spread) > 30:
            errors.append("home_spread_outside_plus_minus_30")
        if self.home_implied_total <= 0 or self.away_implied_total <= 0:
            errors.append("nonpositive_implied_total")
        if self.home_team == self.away_team or not self.game_id:
            errors.append("invalid_game_identity")
        return errors


def parse_nflverse_schedules(events: Iterable[dict[str, Any]], *, schedule: Iterable[dict[str, Any]],
                             season: int, week: int, captured_at: datetime) -> tuple[list[MarketSnapshot], list[dict]]:
    """Match a captured schedule version to canonical games; retain rejected rows."""
    captured_at = utc_time(captured_at)
    games = {(canonical_team(str(row["home_team"])), canonical_team(str(row["away_team"]))): row
             for row in schedule}
    snapshots: list[MarketSnapshot] = []
    rejected: list[dict] = []
    for event in events:
        source_game_id = str(event.get("game_id") or "")
        try:
            home, away = canonical_team(event["home_team"]), canonical_team(event["away_team"])
            game = games[(home, away)]
            kickoff = utc_time(game["kickoff_at"])
            if source_game_id != str(game["game_id"]):
                raise ValueError("provider game ID differs from canonical schedule")
            if int(event["season"]) != season or int(event["week"]) != week:
                raise ValueError("provider season/week differs from requested slate")
            total = float(event["total_line"])
            home_margin = float(event["spread_line"])
            snapshot = MarketSnapshot(
                season=season, week=week, game_id=str(game["game_id"]), home_team=home,
                away_team=away, kickoff_at=kickoff, game_total=total,
                home_spread=-home_margin, source="nflverse_schedules",
                source_game_id=source_game_id, observed_at=captured_at,
                ingested_at=captured_at,
            )
            if snapshot.sanity_errors():
                raise ValueError(", ".join(snapshot.sanity_errors()))
            snapshots.append(snapshot)
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({"source_game_id": source_game_id, "reason": str(exc)})
    return snapshots, rejected


def select_market_snapshots(games: Iterable[dict[str, Any]], observations: Iterable[MarketSnapshot],
                            *, decision_at: datetime, fresh_hours: float = 6,
                            stale_hours: float = 24) -> dict:
    """Select latest fully valid observation for each game, never after decision/lock."""
    decision_at = utc_time(decision_at)
    if not 0 < fresh_hours < stale_hours:
        raise ValueError("Require 0 < fresh_hours < stale_hours")
    by_game: dict[str, list[MarketSnapshot]] = {}
    rejected: list[dict] = []
    for row in observations:
        by_game.setdefault(row.game_id, []).append(row)
    selected: list[MarketSnapshot] = []
    coverage: list[dict] = []
    for game in games:
        game_id = str(game["game_id"])
        home, away = canonical_team(str(game["home_team"])), canonical_team(str(game["away_team"]))
        kickoff = utc_time(game["kickoff_at"])
        valid = []
        for row in by_game.get(game_id, []):
            reason = ("team_or_week_mismatch" if (row.home_team, row.away_team, row.season, row.week)
                      != (home, away, int(game["season"]), int(game["week"])) else
                      "invalid" if row.sanity_errors() else
                      "late_or_post_lock" if row.observed_at > decision_at or row.observed_at >= kickoff
                      or row.ingested_at > decision_at else None)
            if reason:
                rejected.append({"game_id": game_id, "snapshot_id": row.snapshot_id, "reason": reason})
            else:
                valid.append(row)
        choice = max(valid, key=lambda row: (row.observed_at, row.ingested_at, row.snapshot_id or ""),
                     default=None)
        if choice:
            selected.append(choice)
            age = (decision_at - choice.observed_at).total_seconds() / 3600
            status = "fresh" if age <= fresh_hours else "aging" if age <= stale_hours else "stale"
        else:
            age, status = None, "missing"
        coverage.append({"game_id": game_id, "home_team": home, "away_team": away,
                         "status": status, "age_hours": age,
                         "snapshot_id": choice.snapshot_id if choice else None})
    return {"selected": selected, "games": coverage, "total_games": len(coverage),
            "sourced_games": len(selected), "missing_games": sum(r["status"] == "missing" for r in coverage),
            "stale_games": sum(r["status"] == "stale" for r in coverage),
            "rejected": rejected,
            "oldest_observed_at": min((r.observed_at for r in selected), default=None),
            "newest_observed_at": max((r.observed_at for r in selected), default=None)}
