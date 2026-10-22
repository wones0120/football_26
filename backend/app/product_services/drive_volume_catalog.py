"""Observed native-drive volume; an observed drive is not certified possession coverage."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import hashlib
from .environment_context_evidence import DEFINITIONS
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .offensive_environment_catalog import _count, load_reviewed_environment_context

VERSION = 'drive_volume_catalog_v1'

def _metrics(snaps, attached, drives, missing_drive, unknown, logs):
    exact = not (missing_drive or unknown)
    return {
        'G01-M02': dict(value=attached / drives if drives and exact else None,
            unit='physical_offensive_snaps_per_observed_native_drive',
            known_physical_snaps=snaps, known_attached_snaps=attached,
            observed_native_drives=drives, unknown_drive_snap_ids=missing_drive,
            unknown_snap_eligibility=unknown,
            known_attached_sample_mean=attached / drives if drives else None,
            exact_within_observed_log=exact),
        'G01-M03': dict(value=None, unit='possessions_per_complete_game',
            observed_offensive_native_drive_lower_bound=drives,
            observed_game_logs=logs,
            observed_drives_per_log=drives / logs if logs else None,
            complete_game_possession_coverage='unverified',
            status='partial_observed_offensive_native_drive_variant'),
    }

def build_drive_volume_catalog(context, *, before_period, last_n=8):
    if (context.get('version') != 'environment_context_evidence_v1'
            or context.get('before_period') != before_period
            or context.get('forecast') is not None
            or context.get('definitions', {}).get('G01-M02') != DEFINITIONS['G01-M02']):
        raise ValueError('Matched reviewed descriptive drive source required')
    if (type(before_period) is not int or before_period < 200001
            or not 1 <= before_period % 100 <= 18
            or type(last_n) is not int or not 1 <= last_n <= 32):
        raise ValueError('Explicit prior REG scope/window required')
    rows = []; seen = set(); teams = defaultdict(list)
    for src in context['game_rows']:
        season = src['season']; week = src['week']; gid = src['game_id']
        team = canonical_team(src['team']); parts = gid.split('_')
        if (type(season) is not int or type(week) is not int or not 1 <= week <= 18
                or len(parts) != 4 or parts[:2] != [str(season), f'{week:02d}']
                or team not in {canonical_team(x) for x in parts[2:]}
                or season * 100 + week >= before_period or (gid, team) in seen):
            raise ValueError('Unique prior native game/team scope required')
        seen.add((gid, team)); native = []
        for value in src['native_drive_ids']:
            if isinstance(value, bool):raise ValueError('Native numeric drive ID required')
            try:number = float(value)
            except (TypeError, ValueError):raise ValueError('Native numeric drive ID required') from None
            native.append(_count(number))
        if len(native) != len(set(native)):
            raise ValueError('Duplicate native drive ID, including equivalent spellings')
        snaps = _count(src['known_offensive_snaps']); attached = _count(src['known_drive_snaps'])
        missing = _count(src['unknown_drive_snap_ids']); unknown = _count(src['unknown_snap_eligibility'])
        drives = len(native)
        if snaps != attached + missing or attached < drives or (attached and not drives):
            raise ValueError('Native drive/snap accounting differs')
        row = dict(game_id=gid, season=season, week=week, team=team,
            native_drive_ids=sorted(native), metrics=_metrics(snaps, attached, drives, missing, unknown, 1))
        rows.append(row)
        if season == before_period // 100:teams[team].append(row)
    rows.sort(key=lambda r:(r['game_id'], r['team'])); windows = []
    for team, group in sorted(teams.items()):
        group = sorted(group, key=lambda r:(r['week'], r['game_id']))[-last_n:]
        if len({r['week'] for r in group}) != len(group):raise ValueError('Ambiguous same-team period')
        sums = [sum(r['metrics']['G01-M02'][field] for r in group) for field in
            ('known_physical_snaps','known_attached_snaps','observed_native_drives','unknown_drive_snap_ids','unknown_snap_eligibility')]
        windows.append(dict(team=team, observed_game_ids=[r['game_id'] for r in group],
            metrics=_metrics(*sums, len(group))))
    basis = dict(version=VERSION, before_period=before_period,
        last_n_same_season_observed_games=last_n, game_rows=rows, team_windows=windows,
        definitions={'G01-M02':DEFINITIONS['G01-M02'],
            'G01-M03':'Complete-game possessions unavailable; retain distinct observed offensive native-drive lower bound only'})
    return dict(**basis, semantic_sha256=digest(basis),
        source_context_semantic_sha256=context['semantic_measurements_sha256'],
        evidence_use='postlock_descriptive_not_pregame_or_serving', pregame_serving_eligible=False,
        forecast=None, limitations=['Distinct IDs, never maximum native drive ID',
            'Physical offensive snaps are a union; pass/rush/targets are not additive votes',
            'Observed logs and offensive native drives do not certify complete possessions or unseen games',
            'No chronological ordering is inferred from numeric drive or play IDs; controls are not offensive snaps'],
        consumer_status='Features only; model/optimizer/current serving pending')

def read_drive_volume_catalog(context_ref, snapshot, *, actual_read_at,
        context_directory=None, parent_directory=None):
    intake = load_reviewed_environment_context(context_ref, snapshot, actual_read_at=actual_read_at,
        context_directory=context_directory, parent_directory=parent_directory)
    result = build_drive_volume_catalog(intake['context'], before_period=intake['context']['before_period'])
    result['provenance'] = deepcopy(intake['provenance'])
    result['provenance']['producer_code_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result
