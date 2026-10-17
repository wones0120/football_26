"""Single Stat contracts. No Classic/Showdown projection, salary or eligibility reuse."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from ..models import IngestRun, PlayerAlias, RawNflWeeklyStat, UnresolvedPlayerQueue

LEDGER = Path('artifacts/single_stat_ledger')
CONTRACT = 'nfl_single_stat_v1'
RULES_URL = 'https://support.draftkings.com/dk/en-us/game-style-single-stat?id=kb_article_view&sysparm_article=KB0010273'
COMPONENTS = {
    'touchdowns': ('rushing_tds', 'receiving_tds', 'kick_return_tds', 'missed_fg_return_tds', 'punt_return_tds', 'offensive_fumble_recovery_tds', 'defensive_tds'),
    'total_yards': ('rushing_yards', 'receiving_yards'),
    'passing_yards': ('passing_yards',),
}
UNITS = {'touchdowns': 'touchdowns', 'total_yards': 'yards', 'passing_yards': 'yards'}


def clock(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00')) if not isinstance(value, datetime) else value
    if parsed.tzinfo is None: raise ValueError('Evidence timestamps require an explicit timezone')
    return parsed.astimezone(UTC)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Game(Strict):
    game_id: str = Field(min_length=1, max_length=80)
    teams: list[str] = Field(min_length=2, max_length=2)
    original_start_at: datetime
    scheduled_start_at: datetime
    started_at: datetime | None = None
    disabled: bool = False
    provider_status: Literal['confirmed', 'unknown', 'decision_pending']
    provider_observed_at: datetime
    provider_source: str = Field(min_length=1)

    @model_validator(mode='after')
    def validate_game(self):
        for value in (self.original_start_at, self.scheduled_start_at, self.provider_observed_at, self.started_at):
            if value is not None: clock(value)
        if len(set(self.teams)) != 2: raise ValueError('A game requires two distinct teams')
        return self


class NativePlayerEvidence(Strict):
    status: str
    disabled: bool = False
    source_reference: str = Field(min_length=1)
    observed_at: datetime


class PoolImport(Strict):
    contest_format: Literal['single_stat']
    variant: Literal['touchdowns', 'total_yards', 'passing_yards']
    game_set_id: str = Field(min_length=1, max_length=128)
    season: int = Field(ge=2000, le=2200)
    week: int = Field(ge=1, le=22)
    source_name: str = Field(min_length=1, max_length=200)
    source_reference: str = Field(min_length=1, max_length=1000)
    source_observed_at: datetime
    scoring_period_end_at: datetime
    scoring_period_source: str = Field(min_length=1)
    contest_status: Literal['active', 'cancelled', 'decision_pending', 'unknown']
    games: list[Game] = Field(min_length=1, max_length=32)
    native_csv: str = Field(min_length=1, max_length=4_000_000)
    native_game_ids: dict[str, str] = Field(default_factory=dict)
    player_evidence: dict[str, NativePlayerEvidence] = Field(default_factory=dict)
    source_file_observed_at: datetime | None = None
    columns: dict[Literal['source_player_id', 'name', 'team', 'game_id'], str]
    classification: Literal['native_pool', 'fixture_research'] = 'native_pool'
    evaluation_id: str = Field(default='initial', min_length=1, max_length=128)

    @model_validator(mode='after')
    def validate_scope(self):
        clock(self.source_observed_at); clock(self.scoring_period_end_at)
        for evidence in self.player_evidence.values():
            if clock(evidence.observed_at) > clock(self.source_observed_at): raise ValueError('Player status follows evidence cutoff')
        if self.source_file_observed_at is not None: clock(self.source_file_observed_at)
        if set(self.columns) != {'source_player_id', 'name', 'team', 'game_id'}:
            raise ValueError('Declare the four native CSV column names explicitly')
        if len({g.game_id for g in self.games}) != len(self.games): raise ValueError('Duplicate Game Set game')
        if any(clock(g.provider_observed_at) > clock(self.source_observed_at) for g in self.games):
            raise ValueError('Provider observations cannot follow the pool evidence cutoff')
        if clock(self.scoring_period_end_at) <= max(clock(g.original_start_at) for g in self.games):
            raise ValueError('Scoring period must follow the Game Set games')
        return self


class Optimize(Strict):
    pool_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    allow_partial_touchdown_research: bool = False
    allow_incomplete_pool_research: bool = False


def score(variant, stats, *, disabled=False):
    """Missing measured categories remain unknown; passing TD never contributes."""
    if disabled: return {'value': 0.0, 'missing_components': [], 'reason': 'provider_disabled_game'}
    missing = [key for key in COMPONENTS[variant] if stats.get(key) is None]
    values = [stats[key] for key in COMPONENTS[variant] if stats.get(key) is not None]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('Stat values must be finite numbers')
    return {'value': None if missing else float(sum(values)), 'missing_components': missing}


def _save(value, directory=None):
    root = Path(directory) if directory is not None else LEDGER
    root.mkdir(parents=True, exist_ok=True)
    key = digest(value); record = {**value, 'sha256': key}; path = root / (key + '.json')
    try:
        with path.open('x') as handle: json.dump(record, handle, indent=2, allow_nan=False)
    except FileExistsError:
        if json.loads(path.read_text()) != record: raise ValueError('Immutable Single Stat evidence conflict')
    return record


def load(key, directory=None):
    if not re.fullmatch(r'[0-9a-f]{64}', key): raise ValueError('Invalid Single Stat record hash')
    path = (Path(directory) if directory is not None else LEDGER) / (key + '.json')
    if path.stat().st_size > 16_000_000: raise ValueError('Single Stat record exceeds read limit')
    record = json.loads(path.read_text())
    if record.get('contract_id') != CONTRACT or digest({k: v for k, v in record.items() if k != 'sha256'}) != key:
        raise ValueError('Single Stat evidence hash mismatch')
    return record


def catalog(directory=None):
    root = Path(directory) if directory is not None else LEDGER
    paths = sorted(root.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
    rows = []
    for path in paths:
        try:
            record = load(path.stem, directory)
            rows.append({k: record.get(k) for k in ('sha256', 'kind', 'variant', 'game_set_id', 'classification', 'created_at', 'objective', 'units')})
        except (OSError, ValueError, KeyError): continue
    return rows


def historical_baseline(session, player_id, cutoff, season, week, variant):
    """Last three observed games, not fantasy points. Late imports cannot prove availability."""
    aliases = list(session.scalars(select(PlayerAlias).where(PlayerAlias.player_master_id == player_id)))
    pairs = {(a.source_system, a.source_key) for a in aliases}
    ids = {key for _, key in pairs}
    rows = list(session.scalars(select(RawNflWeeklyStat).where(RawNflWeeklyStat.player_id.in_(ids), RawNflWeeklyStat.season <= season))) if ids else []
    safe = []
    for row in rows:
        created = row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        if (row.source_system, row.player_id) not in pairs or created > cutoff or (row.season, row.week) >= (season, week): continue
        safe.append(row)
    # One immutable observation per game; retain first-known version rather than duplicating reimports.
    safe.sort(key=lambda r: (r.season, r.week, r.created_at, r.raw_nfl_weekly_stat_id))
    unique = {}
    for row in safe: unique.setdefault((row.season, row.week, row.game_id), row)
    window = list(unique.values())[-3:]
    components = {}
    for key in COMPONENTS[variant]:
        values = [r.raw_row_json.get(key) for r in window]
        components[key] = sum(float(v) for v in values) / len(values) if values and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values) else None
    scored = score(variant, components)
    covered = [key for key, value in components.items() if value is not None]
    return dict(method='observed_last_three_games_mean_v1', components=components, **scored,
        covered_value=sum(components[k] for k in covered) if covered else None,
        sample_games=len(window), evidence=[dict(raw_nfl_weekly_stat_id=r.raw_nfl_weekly_stat_id,
            ingest_run_id=r.ingest_run_id, source_system=r.source_system, source_player_id=r.player_id,
            season=r.season, week=r.week, game_id=r.game_id, observed_at=r.created_at.isoformat(),
            stats={k: r.raw_row_json.get(k) for k in COMPONENTS[variant]}) for r in window],
        warning='Descriptive historical mean; no opponent, current workload, injury or calibrated uncertainty adjustment. Missing categories are unknown.')


def import_pool(request, session, *, directory=None, now=None, resolver=None, forecaster=None):
    now = now or datetime.now(UTC); cutoff = clock(request.source_observed_at)
    if cutoff > now: raise ValueError('Pool source clock is in the future')
    root = Path(directory) if directory is not None else LEDGER
    request_sha = digest(request.model_dump(mode='json'))
    receipt = root / 'imports' / (request_sha + '.json')
    if receipt.exists(): return load(json.loads(receipt.read_text())['pool_sha256'], directory)
    rows = list(csv.DictReader(io.StringIO(request.native_csv.lstrip('\ufeff'))))
    if not rows or len(rows) > 2000: raise ValueError('Native pool must contain 1–2000 rows')
    if not set(request.columns.values()).issubset(rows[0]): raise ValueError('Declared columns missing from native CSV')
    games = {g.game_id: g for g in request.games}; players = []; seen = set(); canonical_seen = set()
    for raw in rows:
        row = {key: (raw.get(column) or '').strip() for key, column in request.columns.items()}
        if not row['source_player_id'] or row['source_player_id'] in seen: raise ValueError('Native player IDs must be present and unique')
        seen.add(row['source_player_id'])
        native_game_info = row['game_id']
        row['game_id'] = request.native_game_ids.get(native_game_info, native_game_info)
        row['native_game_info'] = native_game_info
        row['position'] = raw.get('Position')
        row['native_status'] = raw.get('Status') or ''
        row['status_evidence'] = request.player_evidence[row['source_player_id']].model_dump(mode='json') if row['source_player_id'] in request.player_evidence else None
        if row['game_id'] not in games or row['team'] not in games[row['game_id']].teams: raise ValueError('Native player is outside the exact Game Set')
        if resolver is not None: pid = resolver(row['source_player_id'])
        else:
            matches = set(session.scalars(select(PlayerAlias.player_master_id).where(PlayerAlias.source_system == 'draftkings', PlayerAlias.source_key == row['source_player_id'])))
            pid = next(iter(matches)) if len(matches) == 1 else None
            identity_reason = 'alias_source_key' if pid else 'unresolved_native_id'
            if not pid and row['position']:
                from ..services.matching import find_player_master_id, upsert_alias
                pid, identity_reason = find_player_master_id(session, 'draftkings', row['source_player_id'], row['name'], row['team'], row['position'])
                if pid:
                    upsert_alias(session, pid, 'draftkings', row['source_player_id'], row['name'], row['team'], row['position'], request.season, request.week)
        if pid in canonical_seen and pid is not None: raise ValueError('Duplicate canonical player in native pool')
        if pid: canonical_seen.add(pid)
        forecast = (forecaster or historical_baseline)(session, pid, cutoff, request.season, request.week, request.variant) if pid else None
        players.append({**row, 'player_master_id': pid, 'identity_status': 'resolved_native_id' if pid else 'unresolved_native_id', 'identity_reason': identity_reason if resolver is None else 'fixture_resolver', 'forecast': forecast})
    payload = request.model_dump(mode='json')
    record = _save(dict(contract_id=CONTRACT, kind='pool', variant=request.variant, game_set_id=request.game_set_id,
        classification=request.classification, created_at=now.isoformat(), source=payload,
        native_csv_sha256=hashlib.sha256(request.native_csv.encode()).hexdigest(), players=players,
        rules=dict(version='user_supplied_nfl_single_stat_2026_10_15', official_overview=RULES_URL,
            official_overview_verified='2026-10-15', detailed_rules_status='User supplied; full current sport-specific page not independently retrieved',
            roster_size=3, min_teams=2, salary_cap=None, position_requirements=None),
        import_request_sha256=request_sha,
        export=dict(enabled=False, reason='No verified native Single Stat upload template/headers supplied. JSON research report is not a DraftKings entry file.')), directory)
    if session is not None and resolver is None:
        run_id = str(uuid5(NAMESPACE_URL, CONTRACT + request_sha))
        if session.get(IngestRun, run_id) is None:
            session.add(IngestRun(ingest_run_id=run_id, source_system='draftkings', source_table='single_stat_native_pool_v1',
                source_path=str(root / (record['sha256'] + '.json')), source_checksum=record['native_csv_sha256'],
                season=request.season, week=request.week, slate=request.game_set_id[:64], status='completed',
                rows_raw=len(players), rows_curated=len(canonical_seen), rows_unresolved=len(players)-len(canonical_seen),
                started_at=now.replace(tzinfo=None), completed_at=now.replace(tzinfo=None)))
            session.flush()
            for player in players:
                if player['player_master_id'] is None:
                    session.add(UnresolvedPlayerQueue(unresolved_id=str(uuid5(NAMESPACE_URL, run_id + player['source_player_id'])),
                        ingest_run_id=run_id, source_system='draftkings', source_table='single_stat_native_pool_v1',
                        source_player_key=player['source_player_id'], season=request.season, week=request.week, slate=request.game_set_id[:64],
                        raw_row_json=player, normalized_name=player['name'].casefold(), team=player['team'],
                        notes='Single Stat native ID unresolved; retained in immutable pool ' + record['sha256']))
            session.commit()
    receipt.parent.mkdir(parents=True, exist_ok=True)
    try:
        with receipt.open('x') as handle: json.dump({'pool_sha256': record['sha256']}, handle)
    except FileExistsError:
        return load(json.loads(receipt.read_text())['pool_sha256'], directory)
    return record


def readiness(pool, *, now=None, partial=False):
    now = now or datetime.now(UTC); source = pool['source']; reasons = []
    if pool['kind'] != 'pool': raise ValueError('A Single Stat pool record is required')
    if source['contest_status'] != 'active': reasons.append('provider_contest_status_' + source['contest_status'])
    if clock(source['scoring_period_end_at']) <= now: reasons.append('scoring_period_closed')
    games = {g['game_id']: g for g in source['games']}
    if any(g['provider_status'] != 'confirmed' for g in games.values()): reasons.append('provider_game_decision_unresolved')
    players = []
    for player in pool['players']:
        game = games[player['game_id']]; blocks = []; forecast = player['forecast']
        lock_at = clock(game['original_start_at'] if game['disabled'] else game['scheduled_start_at'])
        if game['started_at']: lock_at = min(lock_at, clock(game['started_at']))
        if game['disabled']: blocks.append('provider_disabled_game')
        status = player.get('status_evidence') or {}
        unavailable = {'OUT','IR','O','DOUBTFUL','D','PUP','SUSPENDED','SUSP'}
        if str(player.get('native_status','')).upper() in unavailable or str(status.get('status','')).upper() in unavailable: blocks.append('confirmed_or_doubtful_unavailable')
        if status.get('disabled'): blocks.append('provider_disabled_player')
        if lock_at <= now: blocks.append('player_locked')
        if not player['player_master_id']: blocks.append('unresolved_native_id')
        missing = forecast['missing_components'] if forecast else list(COMPONENTS[pool['variant']])
        value = forecast['value'] if forecast else None
        if missing:
            if partial and pool['variant'] == 'touchdowns' and forecast and all(forecast['components'].get(k) is not None for k in ('rushing_tds', 'receiving_tds')):
                value = forecast['covered_value']
            else: blocks.append('stat_forecast_missing')
        players.append({**player, 'lock_at': lock_at.isoformat(), 'reason_codes': blocks, 'expected_metric': value,
                        'missing_components': missing, 'eligible': not blocks})
    # Unknown identity/data anywhere prevents claiming a complete pool ranking.
    if any(p['reason_codes'] and any(r in p['reason_codes'] for r in ('unresolved_native_id', 'stat_forecast_missing')) for p in players):
        reasons.append('pool_identity_or_stat_coverage_incomplete')
    eligible = [p for p in players if p['eligible']]
    if len(eligible) < 3 or len({p['team'] for p in eligible}) < 2: reasons.append('no_legal_three_player_lineup')
    return dict(status='BLOCKED' if reasons else 'READY_FOR_RESEARCH', reason_codes=reasons, players=players,
        entry_ready=False, export=pool['export'], warning='Provider decisions must be refreshed after schedule/status changes. Saved evidence does not certify current contest eligibility.')


def legal_lineup(players):
    return len(players) == 3 and len({p['player_master_id'] for p in players}) == 3 and all(p['player_master_id'] for p in players) and len({p['team'] for p in players}) >= 2


def optimize(request, *, directory=None, now=None):
    now = now or datetime.now(UTC); pool = load(request.pool_sha256, directory)
    ready = readiness(pool, now=now, partial=request.allow_partial_touchdown_research)
    blockers = [r for r in ready['reason_codes'] if not (request.allow_incomplete_pool_research and r == 'pool_identity_or_stat_coverage_incomplete')]
    if blockers: raise ValueError('Single Stat blocked: ' + ', '.join(blockers))
    incomplete_pool = 'pool_identity_or_stat_coverage_incomplete' in ready['reason_codes']
    # With only the >=2 team condition, an optimum uses at most the top three from each team.
    teams = {}
    for p in sorted([p for p in ready['players'] if p['eligible']], key=lambda p: (-p['expected_metric'], p['player_master_id'])):
        bucket = teams.setdefault(p['team'], [])
        if len(bucket) < 3: bucket.append(p)
    candidates = [p for group in teams.values() for p in group]
    best = max((c for c in combinations(candidates, 3) if legal_lineup(c)), key=lambda c: (sum(p['expected_metric'] for p in c), tuple(p['player_master_id'] for p in c)))
    partial = pool['variant'] == 'touchdowns' and any(p['missing_components'] for p in ready['players'] if p['eligible'])
    return _save(dict(contract_id=CONTRACT, kind='report', variant=pool['variant'], game_set_id=pool['game_set_id'],
        classification='INCOMPLETE_POOL_RESEARCH' if incomplete_pool else 'PARTIAL_STAT_RESEARCH' if partial else 'BASELINE_RESEARCH', created_at=now.isoformat(),
        pool_classification=pool['classification'], pool_sha256=pool['sha256'], objective='highest_expected_covered_touchdowns' if partial else 'highest_expected_' + pool['variant'],
        units=UNITS[pool['variant']], expected_metric=sum(p['expected_metric'] for p in best), players=list(best),
        objective_scope='measured_eligible_subset_only' if incomplete_pool else 'complete_imported_pool',
        incomplete_pool_research_explicitly_accepted=request.allow_incomplete_pool_research,
        excluded_players=[p for p in ready['players'] if not p['eligible']],
        solver_status='OPTIMAL', requested_lineup_size=3, achieved_lineup_size=3,
        distinct_canonical_rosters=1, entry_ready=False, readiness=ready,
        forecast_coverage='Partial categories explicitly accepted for research' if partial else 'All requested stat categories measured in selected history',
        source_provenance=dict(pool_sha256=pool['sha256'], native_csv_sha256=pool['native_csv_sha256'], source_reference=pool['source']['source_reference'], source_observed_at=pool['source']['source_observed_at']),
        rules=pool['rules'], export=pool['export'], assumptions=['No salary cap or position constraint.', 'Historical means are baseline forecasts, not trained stat heads or contest-win probabilities.', 'No current injury/workload clearance or calibrated uncertainty. Research report only.']), directory)


class ActualPlayer(Strict):
    player_master_id: str
    stats: dict[str, float | None]


class ActualResult(Strict):
    report_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_reference: str = Field(min_length=1)
    source_observed_at: datetime
    # Explicit source attestation, not inferred from a saved date or raw box score.
    official_nfl_statistics: Literal[True]
    original_scoring_period_only: Literal[True]
    suspended_game_resumption_stats_excluded: Literal[True]
    disabled_game_ids: list[str] = Field(default_factory=list)
    players: list[ActualPlayer] = Field(min_length=3, max_length=3)


def actual_result(request, *, directory=None, now=None):
    now = now or datetime.now(UTC)
    if clock(request.source_observed_at) > now: raise ValueError('Actual-result source clock is in the future')
    report = load(request.report_sha256, directory)
    if report['kind'] != 'report': raise ValueError('Actual results require a saved Single Stat lineup report')
    pool = load(report['pool_sha256'], directory)
    expected = {p['player_master_id'] for p in report['players']}
    if len({p.player_master_id for p in request.players}) != 3 or {p.player_master_id for p in request.players} != expected:
        raise ValueError('Actual results must match all three saved canonical players exactly')
    native = {p['player_master_id']: p for p in report['players']}
    games = {g['game_id']: g for g in pool['source']['games']}
    if not set(request.disabled_game_ids).issubset(games): raise ValueError('Disabled game is outside the saved Game Set')
    rows = []
    for player in request.players:
        game = games[native[player.player_master_id]['game_id']]
        if pool['classification'] != 'fixture_research' and not (game['disabled'] or game['game_id'] in request.disabled_game_ids):
            start_at = min(clock(game['scheduled_start_at']), clock(game['started_at'])) if game['started_at'] else clock(game['scheduled_start_at'])
            if clock(request.source_observed_at) < start_at: raise ValueError('Actual statistics cannot predate the observed/scheduled game start')
        rows.append(dict(player_master_id=player.player_master_id, name=native[player.player_master_id]['name'], team=native[player.player_master_id]['team'], source_player_id=native[player.player_master_id]['source_player_id'],
            stats=player.stats, **score(pool['variant'], player.stats, disabled=game['disabled'] or game['game_id'] in request.disabled_game_ids)))
    complete = all(p['value'] is not None for p in rows)
    return _save(dict(contract_id=CONTRACT, kind='actual_result', variant=pool['variant'], game_set_id=pool['game_set_id'],
        classification='FIXTURE_ACTUALS' if pool['classification'] == 'fixture_research' else 'SOURCE_ATTESTED_ACTUALS' if complete else 'INCOMPLETE_ACTUALS', pool_classification=pool['classification'], created_at=now.isoformat(),
        report_sha256=report['sha256'], pool_sha256=pool['sha256'], units=UNITS[pool['variant']],
        actual_metric=sum(p['value'] for p in rows) if complete else None, players=rows,
        source=request.model_dump(mode='json'), evidence_warning='Source-supplied scoring-period and official-stat attestations retained; app does not independently adjudicate provider settlement decisions.',
        entry_ready=False, export=pool['export'], rules=pool['rules']), directory)
