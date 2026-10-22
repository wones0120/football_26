"""Observed five source-position OL units on dropbacks, not blocker assignments."""
from collections import Counter, defaultdict
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .participation_source_components import _int
from .personnel_package_continuity import (
    VERSION as PERSONNEL_VERSION, PHYSICAL_VERSION, globally_qualified_identity,
    _comparison, _canonical, ROLES,
)
from .pfr_pressure_cohort import nonspike_dropback

VERSION = 'protection_ol_package_continuity_v1'


def _unit(unit, identity):
    """The parent already proves eleven unique aligned native participant roles."""
    reported = unit.get('native_participant_roles') if unit else None
    if not isinstance(reported, list) or len(reported) != 11 or len({n for n, _ in reported}) != 11:
        return None
    if any(role not in ROLES for _, role in reported):
        return None
    members = sorted((n, role) for n, role in reported if role in {'C', 'G', 'T'})
    if len(members) != 5:
        return None
    canonical = []; missing = []
    for native, role in members:
        proof = identity.get(native, {})
        pid = _canonical(proof.get('player_master_id')) if proof.get('status') == 'unique_native_alias' else None
        if pid is None:
            missing.append(native)
        else:
            canonical.append((pid, role))
    if len({p for p, _ in canonical}) != len(canonical):
        missing = [n for n, _ in members]
    return dict(unit_id=digest(members), native_participant_roles=members,
        canonical_participant_roles=sorted(canonical) if not missing else None,
        role_count_tuple=sorted(Counter(r for _, r in members).items()),
        identity_unknown_native_ids=sorted(missing))


def _eligible(raw, physical):
    eligible, reason = nonspike_dropback(raw)
    # Positive/control contradictions from the corrected physical parent cannot be
    # discarded merely because the older official-union recipe returned False.
    if physical is None and reason not in ('known_spike', 'explicit_exclusion'):
        return None, 'possible_physical_source_contradiction'
    return eligible, reason


def build_protection_ol_continuity(personnel, physical, identity_receipts):
    if personnel.get('version') != PERSONNEL_VERSION or physical.get('version') != PHYSICAL_VERSION:
        raise ValueError('Approved personnel and corrected physical component versions required')
    if any(p.get('pregame_serving_eligible') is not False for p in (personnel, physical)) or personnel['season'] != physical['season']:
        raise ValueError('Same historical nonserving season required')
    identity, withheld = globally_qualified_identity(identity_receipts)
    season = personnel['season']; games = {}; sides = defaultdict(set)
    for source in personnel['game_rows']:
        key = source['game_id'], source['team']
        if key in games:
            raise ValueError('Unique scheduled native game/team required')
        games[key] = dict(game_id=key[0], team=key[1], season=season, week=source['week'],
            observed_offense_rows=source['observed_offense_rows'], known_physical_snaps=0,
            unknown_physical_or_side=0, unknown_units=0, identity_unknown_snaps=0, unit_snaps=Counter())
        sides[key[0]].add(key[1])
    if any(len(value) != 2 for value in sides.values()):
        raise ValueError('Native paired scheduled sides required')
    events = {}; raw_index = {}; units = {}; basis = []; affected = set()
    for event in personnel['event_basis']:
        key = event['game_id'], event['play_id']
        if key in events:
            raise ValueError('Duplicate approved personnel event')
        events[key] = event
    for raw in physical['rows']:
        if raw.get('season_type') != 'REG' or _int(raw.get('season')) != season:
            raise ValueError('Native physical REG season differs')
        gid = raw['game_id']; week = _int(raw['week']); native_play = _int(raw['play_id'])
        if week is None or native_play is None:
            raise ValueError('Native week/play key required')
        play = str(native_play)
        if gid.split('_')[:2] != [str(season), f'{week:02d}'] or gid not in sides:
            raise ValueError('Native period/scheduled game differs')
        if season * 100 + week >= personnel['before_period']:
            continue
        key = gid, play
        if key in raw_index:
            raise ValueError('Duplicate physical event')
        raw_index[key] = raw
    for key in sorted(set(raw_index) | set(events)):
        gid, play = key; raw = raw_index.get(key); event = events.get(key)
        if gid not in sides:
            raise ValueError('Personnel event outside scheduled cohort')
        team = (canonical_team(raw.get('posteam')) if raw.get('posteam') else None) if raw is not None else event.get('team') if event else None
        if team is not None and team not in sides[gid]:
            raise ValueError('Native offense outside game')
        if raw and event and event['team'] != team:
            raise ValueError('Approved personnel/physical native offense differs')
        if raw is None:
            eligible, reason = None, 'source_only_participation_without_physical_row'
        else:
            membership = event['physical_membership'] if event else False
            eligible, reason = _eligible(raw, membership)
            if eligible is True and (event is None or membership is not True):
                eligible, reason = None, 'eligible_DB_without_verified_physical_event'
        if eligible is False:
            continue
        unit = None
        if eligible is True and team is not None and event and event['unit_id']:
            unit = _unit(personnel['unit_registry'][event['unit_id']], identity)
        for side in sides[gid] if team is None else {team}:
            game = games[gid, side]
            if eligible is None or team is None:
                game['unknown_physical_or_side'] += 1
            else:
                game['known_physical_snaps'] += 1
                if unit is None:
                    game['unknown_units'] += 1
                else:
                    uid = unit['unit_id']; units[uid] = unit; game['unit_snaps'][uid] += 1
                    if unit['canonical_participant_roles'] is None:
                        game['identity_unknown_snaps'] += 1
                        affected.update(unit['identity_unknown_native_ids'])
        basis.append(dict(game_id=gid, play_id=play, team=team, eligible_nonspike_dropback=eligible,
            eligibility_reason=reason, unit_id=unit['unit_id'] if unit else None))
    comparisons = []
    for parent in personnel['continuity_rows']:
        gid, team = parent['game_id'], parent['team']; current = games[gid, team]
        previous = parent['prior_scheduled_game_id']
        if previous is not None and (previous, team) not in games:
            raise ValueError('Immediate scheduled predecessor missing from cohort')
        if previous is not None and not parent['scheduled_predecessor_order_proven']:
            raise ValueError('Unproven predecessor cannot be used')
        row = {k: parent[k] for k in ('game_id', 'team', 'season', 'week', 'prior_scheduled_game_id', 'scheduled_predecessor_order_proven', 'first_game_not_applicable')}
        if row['first_game_not_applicable']:
            row.update(catalog_value=None, native_variant=None, canonical=None)
        else:
            prior = games[previous, team] if previous is not None else None
            native = _comparison(current, prior, units, canonical=False)
            canonical = _comparison(current, prior, units, canonical=True)
            row.update(catalog_value=canonical['value'], native_variant=native, canonical=canonical)
        comparisons.append(row)
    profiles = []
    for team in sorted({t for _, t in games}):
        rows = [r for r in comparisons if r['team'] == team and not r['first_game_not_applicable']]
        metrics = {}
        for kind in ('canonical', 'native_variant'):
            values = [r[kind] for r in rows]
            retained = sum(v['known_retained_snaps'] for v in values)
            comparable = sum(v['known_comparable_snaps'] for v in values)
            sample = sum(v['known_retained_snaps'] + v['known_nonretained_snaps'] for v in values)
            known = all(v['full_comparable_cohort_known'] for v in values)
            metrics[kind] = dict(value=retained/comparable if known and comparable else None,
                known_retained_snaps=retained, known_comparable_snaps=comparable,
                known_classified_sample_fraction=retained/sample if sample else None,
                unknown_game_comparisons=sum(not v['full_comparable_cohort_known'] for v in values))
        profiles.append(dict(team=team, season=season, scheduled_comparisons=len(rows), **metrics))
    for game in games.values():
        game['unit_snaps'] = dict(game['unit_snaps'])
    core = dict(version=VERSION, candidate_ids=['X04-M05'], season=season, before_period=personnel['before_period'],
        game_rows=sorted(games.values(), key=lambda r: (r['game_id'], r['team'])), continuity_rows=comparisons,
        profiles=profiles, unit_registry=units, event_basis=basis, identity_request_native_ids=sorted(affected),
        global_identity_withheld_native_ids=withheld,
        definition='Same literal C/G/T count tuple totaling five; snap-weighted exact native/canonical member-to-source-role retention on nonspike physical dropbacks versus immediate scheduled predecessor',
        source_coverage='Observed eligible source dropbacks; not complete NFL logs or actual blocking assignments')
    return dict(**core, semantic_sha256=digest(core), pregame_serving_eligible=False, model_consumed=False,
        optimizer_consumed=False, evidence_use='Historical postseason source positions; no TE/RB blockers, routes, side alignment, expected starters or causal protection claim')
