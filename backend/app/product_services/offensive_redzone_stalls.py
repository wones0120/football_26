"""Observed entered-drive non-touchdown outcomes, not projected kicker opportunity."""
from collections import defaultdict
from copy import deepcopy
from .evaluation_record import digest
from .redzone_drive_catalog import build_redzone_drive_catalog

VERSION = 'offensive_redzone_stalls_v1'
TOUCHDOWNS = {'observed_passing_touchdown', 'observed_rushing_touchdown'}
DEFINITION = 'Proven non-touchdown terminal outcomes after observed preplay inside20 native-drive entry / all observed entered drives; passing or rushing TD is success once'

def _metric(entered, stalls, touchdowns, unknown, uncertain_entry, missing_keys):
    known = stalls + touchdowns
    if known + unknown != entered:raise ValueError('Entered-drive outcome partition differs')
    return dict(value=stalls / entered if entered and not (unknown or uncertain_entry or missing_keys) else None,
        unit='non_touchdown_terminal_fraction_per_observed_redzone_entered_drive',
        observed_entered_drives=entered, known_stall_drives=stalls,
        known_touchdown_drives=touchdowns, known_terminal_outcomes=known,
        unknown_terminal_outcomes=unknown, unknown_entry_eligibility=uncertain_entry,
        entry_events_missing_native_drive=missing_keys,
        known_terminal_sample_fraction=stalls / known if known else None)

def build_offensive_redzone_stalls(source, *, before_period, last_n=8):
    if (type(before_period) is not int or before_period < 200001
            or not 1 <= before_period % 100 <= 18
            or type(last_n) is not int or not 1 <= last_n <= 32):
        raise ValueError('Explicit prior REG scope/window required')
    validated = build_redzone_drive_catalog(source, before_period=before_period)
    rows = []; teams = defaultdict(list)
    for src in validated['game_rows']:
        quality = src['drive_quality']; original = src['metrics']['G14-M10']
        outcomes = quality['drive_outcomes']; known = [r for r in outcomes if r['outcome_known']]
        touchdowns = sum(r['completion_basis'] in TOUCHDOWNS for r in known)
        stalls = len(known) - touchdowns
        # All supported non-TD terminal bases were validated by the reviewed drive wrapper.
        m = _metric(len(outcomes), stalls, touchdowns, len(outcomes)-len(known),
            original['unknown_eligibility_events'], original['unknown_trip_count_due_missing_native_drive'])
        season, week = map(int, src['game_id'].split('_')[:2])
        row = dict(game_id=src['game_id'], season=season, week=week,
            team=src['offense_team'], opponent=src['defense_team'], metrics={'G23-M06':m},
            drive_outcomes=deepcopy(outcomes))
        rows.append(row)
        if season == before_period // 100:teams[row['team']].append(row)
    rows.sort(key=lambda r:(r['game_id'], r['team'])); windows = []
    fields = ('observed_entered_drives','known_stall_drives','known_touchdown_drives',
        'unknown_terminal_outcomes','unknown_entry_eligibility','entry_events_missing_native_drive')
    for team, group in sorted(teams.items()):
        group = sorted(group, key=lambda r:(r['week'], r['game_id']))[-last_n:]
        if len({r['week'] for r in group}) != len(group):raise ValueError('Ambiguous same-team period')
        totals = [sum(r['metrics']['G23-M06'][f] for r in group) for f in fields]
        windows.append(dict(team=team, observed_game_ids=[r['game_id'] for r in group],
            metrics={'G23-M06':_metric(*totals)}))
    basis = dict(version=VERSION, before_period=before_period,
        last_n_same_season_observed_games=last_n, definition=DEFINITION, game_rows=rows, team_windows=windows)
    return dict(**basis, semantic_sha256=digest(basis),
        source_semantic_sha256=source['semantic_measurements_sha256'],
        provenance=deepcopy(source['provenance']), evidence_use=source['evidence_use'],
        pregame_serving_eligible=False, forecast=None,
        limitations=['Observed native drive entries are not certified complete-game possession coverage',
            'A field goal or turnover proves a non-TD terminal only with the native sourced terminal proof',
            'No end-of-source or all-zero TD flags imply a stalled drive; unknowns mask exact rate',
            'No expected field-goal/scoring-range probability, causal effect or forecast is inferred',
            'Pure source validation requires independently authenticated immutable raw source/parent intake'],
        consumer_status='Features only; models/optimizer/current serving pending')
