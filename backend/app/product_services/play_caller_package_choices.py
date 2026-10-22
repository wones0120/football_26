"""Observed team package × called choice around a documented first-calling game."""
from collections import Counter,defaultdict
from copy import deepcopy
from .evaluation_record import digest
from .documented_playcaller_change import VERSION as CALLER_VERSION
from .personnel_package_continuity import VERSION as PERSONNEL_VERSION,PHYSICAL_VERSION,physical_membership,ROLES
from .fumble_event_components import _flag
from .participation_source_components import _int
from .market_snapshots import canonical_team

VERSION='play_caller_package_choices_v1'
CHOICES=('pass','rush','spike','kneel')


def classify_choice(raw,membership):
    if membership is not True:return None
    passing,rush,sack,scramble,spike,kneel,drop=(_flag(raw.get(k)) for k in ('pass_attempt','rush_attempt','sack','qb_scramble','qb_spike','qb_kneel','qb_dropback'))
    if any(value is None for value in (passing,rush,sack,scramble,spike,kneel,drop)):return None
    if spike:
        return 'spike' if passing and not(rush or sack or scramble or kneel) and drop else None
    if kneel:
        return 'kneel' if rush and not(passing or sack or scramble or drop) else None
    if passing and not(rush or sack or scramble) and drop:return 'pass'
    if sack and not(rush or scramble) and drop:return 'pass'  # Pass-attempt flag may also be true on a native sack.
    if scramble and rush and not(passing or sack) and drop:return 'pass'
    if rush and not(passing or sack or scramble or drop):return 'rush'
    return None


def _package(unit):
    roles=unit.get('native_participant_roles') if unit else None
    if not isinstance(roles,list) or len(roles)!=11 or len({native for native,role in roles})!=11 or any(role not in ROLES for native,role in roles):return None
    counts=sorted(Counter(role for native,role in roles).items())
    return dict(package_id=digest(counts),literal_position_count_tuple=counts)


def build_play_caller_package_choices(transition,personnel,physical):
    if transition.get('version')!=CALLER_VERSION or personnel.get('version')!=PERSONNEL_VERSION or physical.get('version')!=PHYSICAL_VERSION:
        raise ValueError('Approved caller/personnel/physical contracts required')
    if any(v.get('pregame_serving_eligible') is not False for v in (transition,personnel,physical)):
        raise ValueError('Historical nonserving parents required')
    if transition.get('incoming_first_calling_game_source_proven') is not True or transition.get('outgoing_playcalling_duties_ended_before_this_game') is not True:
        raise ValueError('Direct first-calling game/duty change proof required, not title')
    team=canonical_team(transition['team_id']);current_id=transition['measured_effective_game_id']
    current=[r for r in personnel['continuity_rows'] if (r['game_id'],r['team'])==(current_id,team)]
    if len(current)!=1 or not current[0]['scheduled_predecessor_order_proven'] or not current[0]['prior_scheduled_game_id']:
        raise ValueError('Immediate prior scheduled game proof required')
    previous_id=current[0]['prior_scheduled_game_id'];gids=(previous_id,current_id);season=personnel['season']
    if physical['season']!=season or current[0]['season']!=season:raise ValueError('Same native season required')
    parent_games={}
    for row in personnel['game_rows']:
        key=row['game_id'],row['team']
        if key in parent_games:raise ValueError('Duplicate native scheduled team-game')
        parent_games[key]=row
    if any((gid,team) not in parent_games for gid in gids):raise ValueError('Both scheduled source cohorts required')
    parts=current_id.split('_')
    if parts[:2]!=[str(season),f"{current[0]['week']:02d}"] or any(team not in {canonical_team(t) for t in gid.split('_')[2:]} for gid in gids):raise ValueError('Caller/native team period differs')
    events={};raw_index={}
    for row in personnel['event_basis']:
        if row['game_id'] not in gids:continue
        key=row['game_id'],row['play_id']
        if key in events:raise ValueError('Unique personnel native event required')
        events[key]=row
    for row in physical['rows']:
        if row['game_id'] not in gids:continue
        week,play=_int(row.get('week')),_int(row.get('play_id'))
        if row.get('season_type')!='REG' or _int(row.get('season'))!=season or week is None or play is None or row['game_id'].split('_')[:2]!=[str(season),f'{week:02d}']:
            raise ValueError('Native REG period/play required')
        key=row['game_id'],str(play)
        if key in raw_index:raise ValueError('Unique physical native event required')
        raw_index[key]=row
    for gid in gids:
        owned=sum(bool(row.get('posteam')) and canonical_team(row['posteam'])==team for (game,play),row in raw_index.items() if game==gid)
        if owned!=parent_games[gid,team]['observed_offense_rows']:raise ValueError('Entire observed offense-row universe must match approved personnel parent')
    registry={};units={};basis=[];counters={gid:dict(known_physical_snaps=0,unknown_physical_or_side=0,unknown_package=0,unknown_choices=Counter(),canonical_member_unknown_snaps=0,joint=Counter(),package_snaps=Counter()) for gid in gids}
    for key in sorted(set(events)|set(raw_index)):
        gid,play=key;raw=raw_index.get(key);e=events.get(key)
        offense=(canonical_team(raw['posteam']) if raw.get('posteam') else None) if raw is not None else e.get('team') if e else None
        native_sides={canonical_team(t) for t in gid.split('_')[2:]}
        if offense is not None and offense not in native_sides:raise ValueError('Native offense outside source game')
        if raw is not None and e and e['team']!=offense:raise ValueError('Native source offense join differs')
        if offense is not None and offense!=team:continue
        snap=physical_membership(raw) if raw is not None else None
        if raw is not None and e and e['physical_membership']!=snap:raise ValueError('Approved physical membership differs')
        if snap is False:continue
        c=counters[gid];unit=None;package=None;choice=None
        if snap is None or offense is None:
            c['unknown_physical_or_side']+=1
        else:
            c['known_physical_snaps']+=1
            unit=personnel['unit_registry'].get(e['unit_id']) if e and e.get('unit_id') else None
            package=_package(unit)
            if package is None:c['unknown_package']+=1
            else:
                pid=package['package_id'];registry[pid]=package;units[e['unit_id']]=deepcopy(unit);c['package_snaps'][pid]+=1
                if unit.get('canonical_participant_roles') is None:c['canonical_member_unknown_snaps']+=1
                choice=classify_choice(raw,snap)
                if choice is None:c['unknown_choices'][pid]+=1
                else:c['joint'][pid,choice]+=1
        basis.append(dict(game_id=gid,play_id=play,team=team,source_offense=offense,physical_membership=snap,source_unit_id=e.get('unit_id') if e else None,
            package_id=package['package_id'] if package else None,called_choice=choice,canonical_member_set_known=unit.get('canonical_participant_roles') is not None if unit else None))
    summaries=[]
    for gid in gids:
        c=counters[gid];parent=parent_games[gid,team]
        missing_source=parent['observed_offense_rows']==0
        global_unknown=missing_source or bool(c['unknown_physical_or_side'] or c['unknown_package'])
        rows=[]
        for pid,package in sorted(registry.items()):
            unknown_choice=c['unknown_choices'][pid];joint={choice:c['joint'][pid,choice] for choice in CHOICES}
            n=c['package_snaps'][pid];ordinary=joint['pass']+joint['rush'];exact_calls=not(global_unknown or unknown_choice)
            rows.append(dict(**package,known_physical_snaps=n,exact_physical_snaps=n if not global_unknown else None,
                known_joint_choice_counts=joint,exact_joint_choice_counts=joint if exact_calls else {k:None for k in CHOICES},unknown_choice_snaps=unknown_choice,
                package_use_fraction=n/c['known_physical_snaps'] if c['known_physical_snaps'] and not global_unknown else None,
                known_package_use_sample_fraction=n/sum(c['package_snaps'].values()) if sum(c['package_snaps'].values()) else None,
                ordinary_call_exposures=ordinary if exact_calls else None,pass_call_fraction=joint['pass']/ordinary if ordinary and exact_calls else None,
                known_classified_call_sample_fraction=joint['pass']/ordinary if ordinary else None))
        summaries.append(dict(game_id=gid,season=season,week=parent['week'],team=team,observed_source_offense_rows=parent['observed_offense_rows'],source_log_missing=missing_source,
            known_physical_snaps=c['known_physical_snaps'],unknown_physical_or_side=c['unknown_physical_or_side'],unknown_package_snaps=c['unknown_package'],
            canonical_member_unknown_snaps=c['canonical_member_unknown_snaps'],full_native_package_cohort_known=not global_unknown,packages=rows))
    before,after=summaries;left={r['package_id']:r for r in before['packages']};comparisons=[]
    for right in after['packages']:
        prior=left[right['package_id']]
        comparisons.append(dict(package_id=right['package_id'],literal_position_count_tuple=right['literal_position_count_tuple'],
            package_use_fraction_difference=right['package_use_fraction']-prior['package_use_fraction'] if all(v is not None for v in (right['package_use_fraction'],prior['package_use_fraction'])) else None,
            within_package_pass_call_fraction_difference=right['pass_call_fraction']-prior['pass_call_fraction'] if all(v is not None for v in (right['pass_call_fraction'],prior['pass_call_fraction'])) else None,
            prior_ordinary_call_exposures=prior['ordinary_call_exposures'],current_ordinary_call_exposures=right['ordinary_call_exposures']))
    core=dict(version=VERSION,candidate_id='X04-M10',season=season,team=team,prior_scheduled_game_id=previous_id,first_documented_calling_game_id=current_id,
        source_incoming_person=transition['source_incoming_person'],source_outgoing_person=transition['source_outgoing_person'],prior_game_actual_playcaller=None,
        transition_semantic_sha256=transition['semantic_sha256'],games=summaries,comparisons=comparisons,package_registry=registry,source_unit_registry=units,event_basis=basis,
        definition='TEAM-grain source-position count-tuples of all11 native participants jointly measured on the SAME physical snap with reported pass/rush call; spikes/kneels separate; full two scheduled games and union package universe retained',
        canonical_identity_scope='Native exact11 identity/position proofs establish package counts; unresolved canonical member attachments retained separately, not silently claimed known',
        inherited_global_identity_withheld_native_ids=personnel['global_identity_withheld_native_ids'])
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,model_consumed=False,optimizer_consumed=False,
        limitations=['One retrospective directly documented first-calling-game comparison, no prior caller tenure inferred','Reported positions/count-tuples are not route/block/side assignments or canonical member-set continuity','No causal coaching effect, future tendency, complete NFL-log or original-pregame availability claim'])
