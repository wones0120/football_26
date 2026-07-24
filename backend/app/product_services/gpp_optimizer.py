"""GPP-focused lineup optimizer with slate-aware config and feedback loop."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import pulp
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string


Position = str


@dataclass
class Player:
    player_id: str
    name: str
    team: str
    opponent: str
    position: Position
    salary: int
    projection: float
    ceiling: float
    ownership: float
    optimal_lineup_probability: float | None = None
    game_id: str | None = None
    spread: float | None = None
    game_total: float | None = None
    team_total: float | None = None
    tags: set[str] = field(default_factory=set)
    value_per_k: float = 0.0
    ceiling_per_k: float = 0.0
    leverage: float = 0.0


OWNERSHIP_BUCKET_ORDER = ["mega_chalk", "chalk", "popular", "mid", "low", "dart", "unknown"]


def ownership_bucket(ownership: float | None) -> str:
    if ownership is None or not math.isfinite(float(ownership)):
        return "unknown"
    pct = float(ownership)
    if pct >= 30:
        return "mega_chalk"
    if pct >= 20:
        return "chalk"
    if pct >= 15:
        return "popular"
    if pct >= 10:
        return "mid"
    if pct >= 5:
        return "low"
    if pct >= 0:
        return "dart"
    return "unknown"


@dataclass
class SlateAnalysis:
    game_count: int
    chalk_concentration: float
    feature_games: List[Tuple[str, float]]


@dataclass
class StackRules:
    min_pass_catchers: int = 1
    min_bring_backs: int = 1
    max_from_team: int = 4
    pass_catcher_positions: Sequence[Position] = field(default_factory=lambda: ["WR", "TE", "RB"])


@dataclass
class TagThresholds:
    chalk_proj: float = 15.0
    chalk_own: float = 15.0
    leverage_proj: float = 10.0
    leverage_own: float = 12.0
    leverage_min: float = 0.0
    punt_salary: int = 3500


@dataclass
class ObjectiveWeights:
    projection: float = 1.0
    leverage: float = 0.25
    correlation: float = 0.2


@dataclass
class LineupTagCaps:
    max_chalk: int = 4
    min_leverage: int = 2
    max_punts: int = 2
    max_total_ownership: float | None = None


@dataclass
class PortfolioTargets:
    max_avg_ownership: float | None = 140.0
    min_leverage_count: int = 2
    max_chalk_count: int = 4
    player_exposure_caps: Dict[str, float] = field(default_factory=dict)  # player_id -> max exposure (0-1)


@dataclass
class SlateConfig:
    stack_rules: StackRules
    tag_thresholds: TagThresholds
    objective_weights: ObjectiveWeights
    tag_caps: LineupTagCaps
    salary_cap: int = 50000
    roster_size: int = 9
    portfolio_targets: PortfolioTargets = field(default_factory=PortfolioTargets)
    correlation_bonus: float = 0.5
    uniqueness_overlap: int = 7  # max shared players between lineups


@dataclass
class PortfolioStats:
    exposures: Dict[str, float]
    tag_counts: Dict[str, int]
    avg_total_ownership: float
    stack_summary: Dict[str, int]
    avg_template_score: float = 0.0
    template_score_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class GPPOptimizerResult:
    job_id: str
    status: str
    message: str
    created_at: datetime
    updated_at: datetime
    lineups: List[List[Player]]
    config: SlateConfig
    analysis: SlateAnalysis
    portfolio: PortfolioStats
    iterations: int


VALID_POSITIONS = {"QB", "RB", "WR", "TE", "DST", "D", "DEF"}


def _normalize_position(pos: str | None) -> str:
    return (pos or "").upper().split("/")[0].strip()


def _normalize_alias(name: str) -> str:
    """Map common aliases to canonical forms (e.g., Hollywood Brown -> Marquise Brown)."""
    key = " ".join(name.lower().replace("'", " ").split())
    if "hollywood brown" in key or ("hollywood" in key and "brown" in key):
        return "marquise brown"
    if key == "marquise brown":
        return "marquise brown"
    return key


def _coalesce_projection(df: pd.DataFrame) -> pd.Series:
    """
    Build a numeric projection column using priority:
    1) projection (post-merge / name-team match)
    2) predicted_mean
    3) adj_mean_final
    4) average_points_per_game / AvgPointsPerGame (from salaries)
    """
    def _col(name: str) -> pd.Series:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce")
        return pd.Series([pd.NA] * len(df), index=df.index)

    proj = _col("projection")
    pred_mean = _col("predicted_mean")
    adj_mean = _col("adj_mean_final")
    avg_pts = _col("average_points_per_game")
    if avg_pts.isna().all() and "AvgPointsPerGame" in df.columns:
        avg_pts = _col("AvgPointsPerGame")

    filled = proj.copy()
    filled = filled.fillna(pred_mean)
    filled = filled.fillna(adj_mean)
    filled = filled.fillna(avg_pts)
    return filled.fillna(0)


def load_player_pool(engine: Engine, season: int, week: int, slate: str) -> tuple[List[Player], dict]:
    """Load salaries + projections + ownership for a slate, with diagnostic counts."""
    with engine.begin() as connection:
        salaries = pd.read_sql(
            text(
                "SELECT * FROM curated_salaries WHERE season = :season AND week = :week AND slate = :slate"
            ),
            connection,
            params={"season": season, "week": week, "slate": slate},
        )
        if "player_id" not in salaries.columns and "ID" in salaries.columns:
            salaries["player_id"] = salaries["ID"]
        projections = pd.read_sql(
            text(
                "SELECT player_id, player_master_id, player_display_name, recent_team, "
                "predicted_mean, predicted_p90, predicted_p50, adj_mean_final "
                "FROM player_expected_points "
                "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL)"
            ),
            connection,
            params={"season": season, "week": week, "slate": slate},
        )
        try:
            adjusted = pd.read_sql(
                text(
                    "SELECT DISTINCT ON (player_id) player_id, rule_run_id, adjusted_mean, adjusted_p90, reason "
                    "FROM player_expected_points_adjusted "
                    "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL) "
                    "ORDER BY player_id, created_at DESC"
                ),
                connection,
                params={"season": season, "week": week, "slate": slate},
            )
        except Exception:
            adjusted = pd.DataFrame()
        if not projections.empty and not adjusted.empty:
            projections = projections.merge(adjusted, on="player_id", how="left")
            projections["adj_mean_final"] = projections["adjusted_mean"].fillna(
                projections.get("adj_mean_final", projections.get("predicted_mean"))
            )
            projections["predicted_p90"] = projections["adjusted_p90"].fillna(
                projections.get("predicted_p90")
            )
        injuries = pd.read_sql(
            text(
                "SELECT player_id, player_master_id, nickname, first_name, last_name, team, injury_indicator "
                "FROM weekly_injuries "
                "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL)"
            ),
            connection,
            params={"season": season, "week": week, "slate": slate},
        )
        try:
            ownership = pd.read_sql(
                text(
                    "SELECT player_id, projected_ownership FROM dk_ownership "
                    "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL)"
                ),
                connection,
                params={"season": season, "week": week, "slate": slate},
            )
        except Exception:
            ownership = pd.DataFrame(columns=["player_id", "projected_ownership"])

    counts = {
        "salaries": len(salaries),
        "projections": len(projections),
        "ownership": len(ownership),
    }

    if salaries.empty:
        return [], counts

    # Normalize ids/types
    salaries["player_id"] = salaries["player_id"].astype(str)
    if "player_master_id" in salaries.columns:
        salaries["player_id"] = salaries["player_master_id"].fillna(salaries["player_id"])
    if "dk_player_id" not in salaries.columns:
        if "ID" in salaries.columns:
            salaries["dk_player_id"] = salaries["ID"]
        else:
            salaries["dk_player_id"] = salaries["player_id"]
    # Normalize salary numeric column
    if "salary" not in salaries.columns:
        if "Salary" in salaries.columns:
            salaries["salary"] = pd.to_numeric(salaries["Salary"], errors="coerce")
        else:
            salaries["salary"] = 0
    else:
        salaries["salary"] = pd.to_numeric(salaries["salary"], errors="coerce")
    projections["player_id"] = projections["player_id"].astype(str) if not projections.empty else pd.Series([], dtype=str)
    ownership["player_id"] = ownership["player_id"].astype(str) if not ownership.empty else pd.Series([], dtype=str)
    injuries["player_id"] = injuries["player_id"].astype(str) if not injuries.empty else pd.Series([], dtype=str)

    def _norm_name(series: pd.Series) -> pd.Series:
        return series.astype(str).str.lower().str.replace(r"\\s+", " ", regex=True).str.strip().map(_normalize_alias)

    salaries["name_norm"] = _norm_name(
        salaries.get("name", salaries.get("player_name", pd.Series("", index=salaries.index)))
    )
    salaries["team_norm"] = salaries.get("player_team", salaries.get("team", pd.Series("", index=salaries.index))).astype(str).str.upper()

    projections["name_norm"] = _norm_name(
        projections.get(
            "player_display_name",
            projections.get("player_name", pd.Series("", index=projections.index)),
        )
    )
    projections["team_norm"] = projections.get("recent_team", pd.Series("", index=projections.index)).astype(str).str.upper()

    if not projections.empty:
        projections = projections.sort_values(by=["adj_mean_final", "predicted_mean"], ascending=False)
        projections = projections.drop_duplicates(subset=["player_id"], keep="first")

    merged = salaries.merge(projections, on="player_id", how="left", suffixes=("", "_proj"))
    merged = merged.merge(ownership, on="player_id", how="left")

    # Secondary match on normalized name + team if projection missing
    if "projection" not in merged.columns:
        merged["projection"] = merged.get("predicted_mean")
    missing_proj_mask = merged["projection"].isna()
    if missing_proj_mask.any():
        proj_lookup = projections.set_index(["name_norm", "team_norm"])
        for idx in merged[missing_proj_mask].index:
            key = (merged.at[idx, "name_norm"], str(merged.at[idx, "team_norm"]).upper())
            if key in proj_lookup.index:
                matched = proj_lookup.loc[key]
                merged.at[idx, "projection"] = matched.get("adj_mean_final") or matched.get("predicted_mean")
                merged.at[idx, "predicted_p90"] = matched.get("predicted_p90")
                merged.at[idx, "predicted_p50"] = matched.get("predicted_p50")

    merged["projection"] = _coalesce_projection(merged)
    # Prefer readable names for downstream display
    if "player_display_name" in merged.columns:
        merged["name"] = merged["player_display_name"]
        merged["player_name"] = merged["player_display_name"]
    elif "name" not in merged.columns and "player_name" in merged.columns:
        merged["name"] = merged["player_name"]

    # Build injury filters (block IR/OUT)
    block_tokens = ("OUT", "IR", "PUP", "NFI", "RESERVE")
    injured = injuries.copy()
    if not injured.empty:
        injured["injury_indicator"] = injured["injury_indicator"].astype(str).str.upper().fillna("")
        injured = injured[injured["injury_indicator"].str.contains("|".join(block_tokens))]
        injured["name_norm"] = _norm_name(
            injured.get(
                "nickname",
                injured.get("first_name", pd.Series("", index=injured.index))
                + " "
                + injured.get("last_name", pd.Series("", index=injured.index)),
            )
        )
        injured["team_norm"] = injured.get("team", pd.Series("", index=injured.index)).astype(str).str.upper()
        blocked_ids = set(injured["player_id"].dropna().astype(str))
        if "player_master_id" in injured.columns:
            blocked_ids |= set(injured["player_master_id"].dropna().astype(str))
        blocked_name_team = {(r.name_norm, r.team_norm) for r in injured.itertuples() if r.name_norm}
    else:
        blocked_ids = set()
        blocked_name_team = set()

    def _proj(row: pd.Series) -> float:
        for key in ("adj_mean_final", "predicted_mean", "average_points_per_game"):
            if key in row and pd.notna(row[key]):
                try:
                    val = float(row[key])
                    if val > 0:
                        return val
                except Exception:
                    continue
        return 0.0

    def _ceiling(row: pd.Series) -> float:
        if "predicted_p90" in row and pd.notna(row["predicted_p90"]):
            try:
                val = float(row["predicted_p90"])
                return val if math.isfinite(val) else 0.0
            except Exception:
                return 0.0
        if "predicted_p50" in row and pd.notna(row["predicted_p50"]):
            try:
                val = float(row["predicted_p50"]) * 1.15
                return val if math.isfinite(val) else 0.0
            except Exception:
                return 0.0
        try:
            val = float(getattr(row, "projection", 0.0) or 0.0)
            return val if math.isfinite(val) else 0.0
        except Exception:
            return 0.0

    players: List[Player] = []
    dropped_salary = 0
    dropped_pos = 0
    dropped_proj = 0
    no_proj_match = 0
    if "projection" in merged.columns:
        predicted_missing = merged.get("predicted_mean").isna() if "predicted_mean" in merged else pd.Series(True, index=merged.index)
        projection_missing = merged["projection"].isna()
        no_proj_match = int(merged[predicted_missing & projection_missing].shape[0])
    for row in merged.itertuples():
        pos = _normalize_position(getattr(row, "position", "") or getattr(row, "roster_position", ""))
        if pos not in VALID_POSITIONS:
            dropped_pos += 1
            continue
        salary = int(getattr(row, "salary", 0) or 0)
        if salary <= 0:
            dropped_salary += 1
            continue
        # Skip blocked injuries
        name_team_key = (
            getattr(row, "name_norm", None),
            getattr(row, "team_norm", None),
        )
        if str(row.player_id) in blocked_ids or name_team_key in blocked_name_team:
            dropped_proj += 1
            continue
        try:
            projection = float(getattr(row, "projection", 0) or 0)
        except Exception:
            projection = 0.0
        if not math.isfinite(projection) or projection <= 0:
            dropped_proj += 1
            continue
        ceiling = _ceiling(row)
        try:
            ownership_val = float(getattr(row, "projected_ownership", 0.0) or 0.0)
            if not math.isfinite(ownership_val):
                ownership_val = 0.0
        except Exception:
            ownership_val = 0.0
        player = Player(
            player_id=str(row.player_id),
            name=str(getattr(row, "name", getattr(row, "player_name", row.player_id))),
            team=str(getattr(row, "player_team", getattr(row, "team", ""))).upper(),
            opponent=str(getattr(row, "opponent_team", getattr(row, "opponent", ""))).upper(),
            position=pos,
            salary=salary,
            projection=projection,
            ceiling=ceiling,
            ownership=ownership_val,
            game_id=str(getattr(row, "game_info", getattr(row, "game_id", ""))),
            spread=float(getattr(row, "spread", 0.0) or 0.0)
            if hasattr(row, "spread")
            else None,
            game_total=float(getattr(row, "game_total", 0.0) or 0.0)
            if hasattr(row, "game_total")
            else None,
            team_total=float(getattr(row, "team_total", 0.0) or 0.0)
            if hasattr(row, "team_total")
            else None,
        )
        players.append(player)
    counts.update(
        {
            "kept": len(players),
            "dropped_salary": dropped_salary,
            "dropped_pos": dropped_pos,
            "dropped_proj": dropped_proj,
            "missing_projection_match": no_proj_match,
        }
    )
    return players, counts


def tag_players(players: List[Player], thresholds: TagThresholds) -> None:
    for p in players:
        p.value_per_k = p.projection / max(1, p.salary / 1000)
        p.ceiling_per_k = p.ceiling / max(1, p.salary / 1000)
        p.leverage = (
            p.optimal_lineup_probability - p.ownership
            if p.optimal_lineup_probability is not None
            else 0.0
        )
        p.tags = set()
        if p.projection >= thresholds.chalk_proj and p.ownership >= thresholds.chalk_own:
            p.tags.add("chalk")
        if (
            p.optimal_lineup_probability is not None
            and p.leverage > thresholds.leverage_min
        ):
            p.tags.add("leverage")
        if p.salary <= thresholds.punt_salary:
            p.tags.add("punt")
        p.tags.add(f"own_{ownership_bucket(p.ownership)}")


def classic_template_score(lineup: List[Player]) -> int:
    buckets: Dict[str, int] = {bucket: 0 for bucket in OWNERSHIP_BUCKET_ORDER}
    for player in lineup:
        buckets[ownership_bucket(player.ownership)] += 1
    total_ownership = sum(player.ownership for player in lineup)
    score = 0
    if len(lineup) == 9:
        score += 1
    if 120 <= total_ownership <= 180:
        score += 2
    elif 100 <= total_ownership <= 200:
        score += 1
    if 1 <= buckets["mega_chalk"] <= 3:
        score += 2
    if 2 <= buckets["mega_chalk"] + buckets["chalk"] <= 4:
        score += 1
    if 2 <= buckets["low"] + buckets["dart"] <= 4:
        score += 2
    if 1 <= buckets["dart"] <= 3:
        score += 1
    if any(player.position == "RB" and ownership_bucket(player.ownership) in {"chalk", "mega_chalk"} for player in lineup):
        score += 1
    if any(player.position in {"DST", "D", "DEF"} and player.ownership < 20 for player in lineup):
        score += 1
    if any(player.position == "WR" and ownership_bucket(player.ownership) in {"low", "dart"} for player in lineup):
        score += 1
    return score


def template_score_bucket(score: int) -> str:
    if score >= 8:
        return "strong"
    if score <= 4:
        return "weak"
    return "neutral"


def analyze_slate(players: List[Player], chalk_threshold: float = 20.0) -> SlateAnalysis:
    game_ids = {p.game_id for p in players if p.game_id}
    totals = {}
    for p in players:
        if p.game_id and p.game_total:
            totals[p.game_id] = max(totals.get(p.game_id, 0.0), p.game_total)
    feature_games = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:3]
    chalky = [p for p in players if p.ownership >= chalk_threshold]
    chalk_concentration = len(chalky) / max(1, len(players))
    return SlateAnalysis(
        game_count=len(game_ids) if game_ids else math.ceil(len(players) / 18),  # rough estimate
        chalk_concentration=chalk_concentration,
        feature_games=feature_games,
    )


def build_slate_config(analysis: SlateAnalysis) -> SlateConfig:
    # Stack defaults adjust with slate size: shorter slates -> more stacking
    if analysis.game_count <= 3:
        stacks = StackRules(min_pass_catchers=2, min_bring_backs=1, max_from_team=5)
        tag_caps = LineupTagCaps(max_chalk=3, min_leverage=3, max_punts=1, max_total_ownership=140.0)
        weights = ObjectiveWeights(projection=1.0, leverage=0.35, correlation=0.25)
    elif analysis.game_count <= 6:
        stacks = StackRules(min_pass_catchers=2, min_bring_backs=1, max_from_team=4)
        tag_caps = LineupTagCaps(max_chalk=4, min_leverage=2, max_punts=2, max_total_ownership=150.0)
        weights = ObjectiveWeights(projection=1.0, leverage=0.3, correlation=0.2)
    else:
        stacks = StackRules(min_pass_catchers=1, min_bring_backs=1, max_from_team=4)
        tag_caps = LineupTagCaps(max_chalk=5, min_leverage=1, max_punts=2, max_total_ownership=160.0)
        weights = ObjectiveWeights(projection=1.0, leverage=0.25, correlation=0.15)

    tag_thresholds = TagThresholds()
    targets = PortfolioTargets(
        max_avg_ownership=tag_caps.max_total_ownership or 150.0,
        min_leverage_count=tag_caps.min_leverage,
        max_chalk_count=tag_caps.max_chalk,
    )
    return SlateConfig(
        stack_rules=stacks,
        tag_thresholds=tag_thresholds,
        objective_weights=weights,
        tag_caps=tag_caps,
        portfolio_targets=targets,
    )


def _position_indices(players: List[Player], positions: Iterable[Position]) -> List[int]:
    allowed = {p.upper() for p in positions}
    return [i for i, p in enumerate(players) if p.position in allowed]


def _add_stack_bonus_vars(model: pulp.LpProblem, x: dict, players: List[Player], weight: float) -> pulp.LpAffineExpression:
    """Create pairwise QB-pass catcher variables for correlation bonus."""
    bonus_terms: List[pulp.LpAffineExpression] = []
    for i, qb in enumerate(players):
        if qb.position != "QB":
            continue
        for j, pc in enumerate(players):
            if i == j:
                continue
            if pc.position not in ("WR", "TE", "RB"):
                continue
            if qb.team != pc.team:
                continue
            y = pulp.LpVariable(f"stack_{i}_{j}", lowBound=0, upBound=1, cat="Binary")
            model += y <= x[i]
            model += y <= x[j]
            model += y >= x[i] + x[j] - 1
            bonus_terms.append(weight * y)
    return pulp.lpSum(bonus_terms)


def _build_lineup(
    players: List[Player],
    config: SlateConfig,
    exposure_remaining: Dict[str, int] | None,
    exclude_lineups: List[set],
) -> Optional[List[int]]:
    if not players:
        return None

    idx_range = range(len(players))
    x = pulp.LpVariable.dicts("p", idx_range, lowBound=0, upBound=1, cat="Binary")
    model = pulp.LpProblem("GPP", pulp.LpMaximize)

    # Objective
    proj_term = pulp.lpSum(players[i].projection * x[i] for i in idx_range)
    lev_term = pulp.lpSum(players[i].leverage * x[i] for i in idx_range)
    stack_bonus = _add_stack_bonus_vars(model, x, players, config.correlation_bonus)
    weights = config.objective_weights
    model += weights.projection * proj_term + weights.leverage * lev_term + weights.correlation * stack_bonus

    # Salary + roster
    model += pulp.lpSum(players[i].salary * x[i] for i in idx_range) <= config.salary_cap
    model += pulp.lpSum(x[i] for i in idx_range) == config.roster_size

    qb_idx = _position_indices(players, ["QB"])
    rb_idx = _position_indices(players, ["RB"])
    wr_idx = _position_indices(players, ["WR"])
    te_idx = _position_indices(players, ["TE"])
    dst_idx = _position_indices(players, ["DST", "D", "DEF"])
    model += pulp.lpSum(x[i] for i in qb_idx) == 1
    model += pulp.lpSum(x[i] for i in dst_idx) == 1
    model += pulp.lpSum(x[i] for i in rb_idx) >= 2
    model += pulp.lpSum(x[i] for i in wr_idx) >= 3
    model += pulp.lpSum(x[i] for i in te_idx) >= 1

    # Team limits
    for team in {p.team for p in players}:
        team_idx = [i for i, p in enumerate(players) if p.team == team]
        model += pulp.lpSum(x[i] for i in team_idx) <= config.stack_rules.max_from_team

    # Stacking: pass catchers and bring-backs
    for i in qb_idx:
        qb = players[i]
        same_team = [j for j, p in enumerate(players) if p.team == qb.team and p.position in config.stack_rules.pass_catcher_positions and j != i]
        opp_team = [j for j, p in enumerate(players) if p.opponent == qb.team or (p.team == qb.opponent)]
        if same_team:
            model += pulp.lpSum(x[j] for j in same_team) >= config.stack_rules.min_pass_catchers * x[i]
        if opp_team:
            model += pulp.lpSum(x[j] for j in opp_team) >= config.stack_rules.min_bring_backs * x[i]

    # Tag constraints
    tag_caps = config.tag_caps
    chalk_idx = [i for i, p in enumerate(players) if "chalk" in p.tags]
    lev_idx = [i for i, p in enumerate(players) if "leverage" in p.tags]
    punt_idx = [i for i, p in enumerate(players) if "punt" in p.tags]
    if chalk_idx:
        model += pulp.lpSum(x[i] for i in chalk_idx) <= tag_caps.max_chalk
    if lev_idx:
        model += pulp.lpSum(x[i] for i in lev_idx) >= tag_caps.min_leverage
    if punt_idx:
        model += pulp.lpSum(x[i] for i in punt_idx) <= tag_caps.max_punts
    if tag_caps.max_total_ownership:
        model += pulp.lpSum(players[i].ownership * x[i] for i in idx_range) <= tag_caps.max_total_ownership

    # Exposure caps
    if exposure_remaining:
        for i in idx_range:
            pid = players[i].player_id
            remaining = exposure_remaining.get(pid)
            if remaining is not None and remaining <= 0:
                model += x[i] == 0

    # Prevent the solver from selecting the same player multiple times when duplicate rows exist
    by_id: Dict[str, List[int]] = {}
    for i, p in enumerate(players):
        by_id.setdefault(p.player_id, []).append(i)
    for pid, idxs in by_id.items():
        if len(idxs) > 1:
            model += pulp.lpSum(x[i] for i in idxs) <= 1
    # Extra guard: collapse duplicate name+team combos that slipped through id mismatches
    by_name_team: Dict[tuple[str, str], List[int]] = {}
    for i, p in enumerate(players):
        key = (p.name.lower().strip(), p.team.upper().strip())
        by_name_team.setdefault(key, []).append(i)
    for key, idxs in by_name_team.items():
        if len(idxs) > 1:
            model += pulp.lpSum(x[i] for i in idxs) <= 1

    # Uniqueness
    for lineup in exclude_lineups:
        model += pulp.lpSum(x[i] for i in lineup) <= config.uniqueness_overlap

    solver = pulp.PULP_CBC_CMD(msg=False)
    status = model.solve(solver)
    if status != pulp.LpStatusOptimal:
        return None

    return [i for i in idx_range if pulp.value(x[i]) >= 0.9]


def _lineup_stats(players: List[Player], idxs: List[int]) -> Tuple[float, int, int, int]:
    total_ownership = sum(players[i].ownership for i in idxs)
    chalk = sum(1 for i in idxs if "chalk" in players[i].tags)
    leverage = sum(1 for i in idxs if "leverage" in players[i].tags)
    punts = sum(1 for i in idxs if "punt" in players[i].tags)
    return total_ownership, chalk, leverage, punts


def _portfolio_stats(players: List[Player], lineups: List[List[int]]) -> PortfolioStats:
    exposure_counts: Dict[str, int] = {}
    tag_counts: Dict[str, int] = {"chalk": 0, "leverage": 0, "punt": 0}
    ownership_totals = []
    template_scores = []
    template_score_counts: Dict[str, int] = {"strong": 0, "neutral": 0, "weak": 0}
    stack_summary: Dict[str, int] = {}

    for idxs in lineups:
        lineup_players = [players[i] for i in idxs]
        for i in idxs:
            pid = players[i].player_id
            exposure_counts[pid] = exposure_counts.get(pid, 0) + 1
            for tag in players[i].tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        ownership_totals.append(sum(players[i].ownership for i in idxs))
        template_score = classic_template_score(lineup_players)
        template_scores.append(template_score)
        template_score_counts[template_score_bucket(template_score)] += 1
        # Stack type summary: count pass catchers/bring backs for QB
        qbs = [i for i in idxs if players[i].position == "QB"]
        if qbs:
            qb = players[qbs[0]]
            same_team = sum(1 for i in idxs if players[i].team == qb.team and players[i].position in ("WR", "TE", "RB") and i != qbs[0])
            bring_back = sum(1 for i in idxs if players[i].team == qb.opponent)
            key = f"{same_team}-with-qb_{bring_back}-bringback"
            stack_summary[key] = stack_summary.get(key, 0) + 1

    total_lineups = max(1, len(lineups))
    exposures = {pid: count / total_lineups for pid, count in exposure_counts.items()}
    avg_total_ownership = sum(ownership_totals) / total_lineups if ownership_totals else 0.0
    avg_template_score = sum(template_scores) / total_lineups if template_scores else 0.0
    return PortfolioStats(
        exposures=exposures,
        tag_counts=tag_counts,
        avg_total_ownership=avg_total_ownership,
        stack_summary=stack_summary,
        avg_template_score=avg_template_score,
        template_score_counts=template_score_counts,
    )


def _adjust_config_for_targets(config: SlateConfig, stats: PortfolioStats, targets: PortfolioTargets) -> SlateConfig:
    cfg = config
    # Adjust lineup ownership cap if average too high
    if targets.max_avg_ownership and stats.avg_total_ownership > targets.max_avg_ownership and cfg.tag_caps.max_total_ownership:
        cfg = SlateConfig(**{**cfg.__dict__})
        cfg.tag_caps = LineupTagCaps(**{**cfg.tag_caps.__dict__})
        cfg.tag_caps.max_total_ownership = max(100.0, cfg.tag_caps.max_total_ownership - 10.0)
    return cfg


def generate_portfolio(
    season: int,
    week: int,
    slate: str,
    num_lineups: int,
    engine: Engine | None = None,
    config_builder: Callable[[SlateAnalysis], SlateConfig] = build_slate_config,
) -> GPPOptimizerResult:
    engine = engine or create_engine(get_connection_string())
    players, counts = load_player_pool(engine, season, week, slate)
    if not players:
        raise RuntimeError(
            "No player pool found for slate "
            f"(salaries={counts.get('salaries', 0)}, projections={counts.get('projections', 0)}, "
            f"ownership={counts.get('ownership', 0)}, kept={counts.get('kept', 0)}, "
            f"dropped_salary={counts.get('dropped_salary', 0)}, "
            f"dropped_pos={counts.get('dropped_pos', 0)}, dropped_proj={counts.get('dropped_proj', 0)})."
        )

    # Tag + analysis + config
    base_config = config_builder(analyze_slate(players))
    tag_players(players, base_config.tag_thresholds)
    analysis = analyze_slate(players)
    config = config_builder(analysis)
    # If no ownership data, relax tag constraints so the solver can build lineups
    if counts.get("ownership", 0) == 0:
        config = SlateConfig(
            stack_rules=config.stack_rules,
            tag_thresholds=config.tag_thresholds,
            objective_weights=config.objective_weights,
            tag_caps=LineupTagCaps(
                max_chalk=len(players),
                min_leverage=0,
                max_punts=len(players),
                max_total_ownership=None,
            ),
            salary_cap=config.salary_cap,
            roster_size=config.roster_size,
            portfolio_targets=config.portfolio_targets,
            correlation_bonus=config.correlation_bonus,
            uniqueness_overlap=config.uniqueness_overlap,
        )
    # Small slates (few teams) need a higher per-team cap to satisfy a 9-man roster
    unique_teams = {p.team for p in players if p.team}
    min_team_cap = math.ceil(config.roster_size / max(1, len(unique_teams) or 1))
    if config.stack_rules.max_from_team < min_team_cap:
        config = SlateConfig(**{**config.__dict__})
        config.stack_rules = StackRules(**{**config.stack_rules.__dict__})
        config.stack_rules.max_from_team = min_team_cap

    exclude_lineups: List[set] = []
    used_counts: Dict[str, int] = {}
    lineups: List[List[int]] = []

    iterations = 0
    max_iterations = 3
    while iterations < max_iterations and len(lineups) < num_lineups:
        iterations += 1
        exposure_limit = max(1, math.ceil(num_lineups * 0.5))  # default 50% cap unless overridden
        remaining = {p.player_id: exposure_limit - used_counts.get(p.player_id, 0) for p in players}

        new_lineups: List[List[int]] = []
        for _ in range(num_lineups - len(lineups)):
            lineup_idxs = _build_lineup(players, config, remaining, exclude_lineups)
            if not lineup_idxs:
                break
            new_lineups.append(lineup_idxs)
            for idx in lineup_idxs:
                pid = players[idx].player_id
                used_counts[pid] = used_counts.get(pid, 0) + 1
            exclude_lineups.append(set(lineup_idxs))
            remaining = {p.player_id: exposure_limit - used_counts.get(p.player_id, 0) for p in players}

        lineups.extend(new_lineups)
        stats = _portfolio_stats(players, lineups)
        config = _adjust_config_for_targets(config, stats, config.portfolio_targets)

    status = "completed" if lineups else "failed"
    message = f"Generated {len(lineups)} lineup(s) after {iterations} iteration(s)"
    result = GPPOptimizerResult(
        job_id=str(uuid.uuid4()),
        status=status,
        message=message,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        lineups=[[players[i] for i in idxs] for idxs in lineups],
        config=config,
        analysis=analysis,
        portfolio=_portfolio_stats(players, lineups),
        iterations=iterations,
    )
    return result


def export_lineups_to_csv(result: GPPOptimizerResult, path: str) -> None:
    rows = []
    for i, lineup in enumerate(result.lineups, start=1):
        for p in lineup:
            rows.append(
                {
                    "lineup": i,
                    "player_id": p.player_id,
                    "name": p.name,
                    "position": p.position,
                    "team": p.team,
                    "opponent": p.opponent,
                    "salary": p.salary,
                    "projection": p.projection,
                    "ownership": p.ownership,
                    "ownership_bucket": ownership_bucket(p.ownership),
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def export_summary_to_md(result: GPPOptimizerResult, path: str) -> None:
    lines = [
        "# Portfolio Summary",
        f"- Status: {result.status}",
        f"- Message: {result.message}",
        f"- Lineups: {len(result.lineups)}",
        f"- Avg total ownership: {result.portfolio.avg_total_ownership:.2f}",
        f"- Avg ownership-template score: {result.portfolio.avg_template_score:.2f}",
        "",
        "## Stack Types",
    ]
    for key, count in sorted(result.portfolio.stack_summary.items(), key=lambda kv: kv[0]):
        lines.append(f"- {key}: {count}")
    lines.append("")
    lines.append("## Tag Counts")
    for tag, count in result.portfolio.tag_counts.items():
        lines.append(f"- {tag}: {count}")
    lines.append("")
    lines.append("## Ownership Template Fit")
    for bucket, count in result.portfolio.template_score_counts.items():
        lines.append(f"- {bucket}: {count}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def summarize_slate(players: List[Player], analysis: SlateAnalysis) -> dict:
    return {
        "game_count": analysis.game_count,
        "chalk_concentration": analysis.chalk_concentration,
        "feature_games": analysis.feature_games,
        "player_count": len(players),
    }


def summarize_portfolio(result: GPPOptimizerResult) -> dict:
    return {
        "status": result.status,
        "lineups": len(result.lineups),
        "avg_total_ownership": result.portfolio.avg_total_ownership,
        "avg_template_score": result.portfolio.avg_template_score,
        "template_score_counts": result.portfolio.template_score_counts,
        "stack_summary": result.portfolio.stack_summary,
        "tag_counts": result.portfolio.tag_counts,
        "config": result.config,
    }


def run_gpp_pipeline(
    season: int,
    week: int,
    slate: str,
    num_lineups: int = 20,
    export_dir: str | None = None,
    engine: Engine | None = None,
) -> GPPOptimizerResult:
    """End-to-end entry point: load slate, build config, generate portfolio, export results."""
    result = generate_portfolio(season, week, slate, num_lineups, engine=engine)
    if export_dir:
        csv_path = f"{export_dir}/lineups_{slate}_{season}w{week}.csv"
        md_path = f"{export_dir}/summary_{slate}_{season}w{week}.md"
        export_lineups_to_csv(result, csv_path)
        export_summary_to_md(result, md_path)
    return result
