"""Declared scheduled-venue displacement, never a measured team itinerary."""
from collections import defaultdict
from datetime import datetime, UTC
import math
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION = 'scheduled_venue_displacement_v1'
EARTH_MEAN_RADIUS_KM = 6371.0088


def kickoff_utc(day, time):
    """Native schedule gametime is Eastern; ambiguous/nonexistent wall times unknown."""
    if not isinstance(day, str) or not isinstance(time, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) or not re.fullmatch(r'\d{2}:\d{2}', time):
        return None
    try:
        naive = datetime.fromisoformat(day+'T'+time)
        zone = ZoneInfo('America/New_York')
        candidates = set()
        for fold in (0, 1):
            value = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
            if value.astimezone(zone).replace(tzinfo=None) == naive:
                candidates.add(value)
        return next(iter(candidates)) if len(candidates) == 1 else None
    except (TypeError, ValueError):
        return None


def _coordinate(value, limit):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and abs(value) <= limit else None


def _valid_venue(record):
    try:
        zone = ZoneInfo(record['timezone'])
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
        return False
    return bool(zone and _coordinate(record.get('latitude'), 90) is not None
        and _coordinate(record.get('longitude'), 180) is not None
        and record.get('registry_record_id') and record.get('venue_id')
        and record.get('coordinate_source_uri')
        and (record.get('source_evidence_uri') or record.get('game_override_evidence_uri')))


def _effective(record, season):
    start, end = record.get('effective_from_season'), record.get('effective_to_season')
    return type(start) is int and start <= season and (end is None or type(end) is int and season <= end)


def venue_for_game(game, registry):
    """Names never select venues; reviewed native-game overrides take precedence."""
    records = registry['venues']
    overrides = [o for o in registry.get('game_overrides', []) if o.get('game_id') == game['game_id']]
    if overrides:
        if len(overrides) != 1 or not overrides[0].get('evidence_uri'):
            return None, 'ambiguous_or_unproven_game_override'
        candidates = [v for v in records if v.get('registry_record_id') == overrides[0].get('registry_record_id')]
        method = 'reviewed_native_game_override'
    else:
        # International/neutral source rows can retain nominal home stadium IDs.
        if game.get('location') != 'Home':
            return None, 'neutral_or_unknown_location_requires_reviewed_game_override'
        native = game.get('stadium_id')
        if not native:
            return None, 'missing_native_stadium_id'
        candidates = [v for v in records if v.get('source_system') == 'pfr' and v.get('source_venue_id') == native]
        method = 'native_pfr_stadium_id'
    candidates = [v for v in candidates if _effective(v, game['season'])]
    if len(candidates) != 1:
        return None, 'missing_or_ambiguous_effective_venue'
    candidate = dict(candidates[0])
    if overrides:
        candidate['game_override_evidence_uri'] = overrides[0]['evidence_uri']
        candidate['game_override_id'] = overrides[0].get('override_id')
    if not _valid_venue(candidate):
        return None, 'unproven_coordinates_or_timezone'
    return candidate, method


def great_circle_km(origin, destination):
    a, b = math.radians(float(origin['latitude'])), math.radians(float(destination['latitude']))
    delta_lat = b-a
    delta_lon = math.radians(float(destination['longitude'])-float(origin['longitude']))
    h = math.sin(delta_lat/2)**2 + math.cos(a)*math.cos(b)*math.sin(delta_lon/2)**2
    return 2*EARTH_MEAN_RADIUS_KM*math.asin(math.sqrt(min(1, max(0, h))))


def build_scheduled_venue_displacement(records, registry, *, seasons=(2024, 2025)):
    """Immediate scheduled REG predecessor within season; unknown never skipped."""
    if registry.get('contract_id') != 'nfl_venue_registry_v1' or not registry.get('reviewed_at'):
        raise ValueError('Versioned reviewed venue registry required')
    games = []; seen = set(); schedules = defaultdict(list)
    for raw in records:
        if str(raw.get('season')) not in {str(s) for s in seasons} or raw.get('game_type') != 'REG':
            continue
        try:
            season, week = int(raw['season']), int(raw['week'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Integral native period required') from exc
        if str(raw['season']) != str(season) or str(raw['week']) != str(week) or not 1 <= week <= 18:
            raise ValueError('Integral native period required')
        home, away = canonical_team(raw.get('home_team')), canonical_team(raw.get('away_team'))
        gid = raw.get('game_id')
        expected = f'{season}_{week:02d}_{raw.get("away_team")}_{raw.get("home_team")}'
        if not home or not away or home == away or gid != expected or gid in seen:
            raise ValueError('Unique native game/team binding required')
        seen.add(gid)
        game = dict(raw, season=season, week=week)
        venue, mapping = venue_for_game(game, registry)
        kick = kickoff_utc(game.get('gameday'), game.get('gametime'))
        normalized = dict(game_id=gid, season=season, week=week, home_team=home, away_team=away,
            native_stadium_id=game.get('stadium_id'), source_location=game.get('location'),
            venue=venue, venue_mapping=mapping, kickoff_utc=kick.isoformat() if kick else None)
        games.append(normalized)
        for team in (home, away):
            schedules[season, team].append(normalized)
    rows = []; profiles = []
    for (season, team), group in sorted(schedules.items()):
        group.sort(key=lambda g:(g['week'], g['game_id']))
        duplicate_weeks = {g['week'] for g in group if sum(x['week'] == g['week'] for x in group) > 1}
        team_rows = []
        for i, game in enumerate(group):
            prior = group[i-1] if i else None
            reasons = []
            if prior is None:
                reasons.append('first_observed_scheduled_game_no_within_season_origin')
            elif game['week'] in duplicate_weeks or prior['week'] in duplicate_weeks:
                reasons.append('ambiguous_scheduled_predecessor')
            # A truncated schedule cannot establish a firstgame/prior linkage.
            if group[0]['week'] != 1:
                reasons.append('season_schedule_beginning_unknown')
            if prior and (prior['venue'] is None or game['venue'] is None):
                reasons.append('origin_or_destination_venue_unknown')
            current_kick = datetime.fromisoformat(game['kickoff_utc']) if game['kickoff_utc'] else None
            prior_kick = datetime.fromisoformat(prior['kickoff_utc']) if prior and prior['kickoff_utc'] else None
            if prior and (current_kick is None or prior_kick is None or current_kick <= prior_kick):
                reasons.append('kickoff_or_chronology_unknown')
            km = offset = None
            if prior and not reasons:
                km = great_circle_km(prior['venue'], game['venue'])
                # Evaluate both geographic zones at ONE current instant: DST is not travel.
                origin_offset = current_kick.astimezone(ZoneInfo(prior['venue']['timezone'])).utcoffset()
                destination_offset = current_kick.astimezone(ZoneInfo(game['venue']['timezone'])).utcoffset()
                offset = (destination_offset-origin_offset).total_seconds()/3600
            row = dict(game_id=game['game_id'], season=season, week=game['week'], team=team,
                prior_scheduled_game_id=prior['game_id'] if prior else None,
                origin_venue_record_id=prior['venue']['registry_record_id'] if prior and prior['venue'] else None,
                destination_venue_record_id=game['venue']['registry_record_id'] if game['venue'] else None,
                timezone_evaluation_instant=game['kickoff_utc'], great_circle_km=km,
                signed_destination_minus_origin_utc_offset_hours=offset,
                first_game_not_applicable=prior is None and group[0]['week'] == 1,
                unknown_reasons=reasons)
            team_rows.append(row)
        eligible = [r for r in team_rows if not r['first_game_not_applicable']]
        known = [r for r in eligible if r['great_circle_km'] is not None]
        unknown = len(eligible)-len(known)
        profiles.append(dict(season=season, team=team, scheduled_games=len(group),
            eligible_displacements=len(eligible), known_displacements=len(known), unknown_displacements=unknown,
            total_displacement_km=sum(r['great_circle_km'] for r in known) if known and not unknown else None,
            known_sample_total_displacement_km=sum(r['great_circle_km'] for r in known) if known else None))
        rows.extend(team_rows)
    basis = dict(version=VERSION, candidate_ids=['G20-M10'], seasons=list(seasons),
        origin_definition='immediately preceding scheduled same-team same-season REG venue',
        offset_definition='destination minus origin IANA UTC offset at SAME current kickoff instant',
        distance_definition=f'spherical great-circle km; mean Earth radius {EARTH_MEAN_RADIUS_KM}',
        games=sorted(games,key=lambda g:g['game_id']), game_rows=rows, profiles=profiles)
    return dict(**basis, semantic_sha256=digest(basis), model_consumed=False, optimizer_consumed=False,
        evidence_use='retrospective_scheduled_venue_displacement_not_actual_team_itinerary_or_fatigue',
        original_historical_availability='unknown', pregame_serving_eligible=False)
