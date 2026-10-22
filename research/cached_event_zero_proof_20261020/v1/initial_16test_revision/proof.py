"""Source-log zero proofs only; no roster/position inferred zeros or fitting."""
from collections import defaultdict
from backend.app.product_services.market_snapshots import canonical_team

def physical_scope(block):
    units=block['unit_registry'];out={}
    for g in block['game_rows']:
        union=set();valid=True
        for uid,n in g['unit_snaps'].items():
            members=units[uid]['native_participant_roles'];ids=[r[0]for r in members]
            if n<=0 or len(ids)!=11 or len(set(ids))!=11:valid=False
            union.update(ids)
        complete=bool(valid and g['observed_offense_rows']>0 and g['known_physical_snaps']>0 and not g['unknown_physical_or_side']and not g['unknown_units']and sum(g['unit_snaps'].values())==g['known_physical_snaps'])
        out[g['game_id'],g['team']]=dict(observed_source_offense_rows=g['observed_offense_rows'],known_physical_snaps=g['known_physical_snaps'],unknown_possible_physical=g['unknown_physical_or_side'],unknown_units=g['unknown_units'],all_physical_units_known=complete,native_on_field_union=union,unit_ids=sorted(g['unit_snaps']))
    return out

def target_scope(block):
    out={}
    for g in block['expected_games']:
        for t in g['sides']:out[g['game_id'],t]=dict(counts=defaultdict(int),unknown_all=False,unknown_native=set(),events=0,observed_game=g['game_id']not in block['missing_PBP_game_ids'],play_ids=[])
    seen=set()
    for e in block['event_basis']:
        key=e['game_id'],e['play_id']
        if key in seen:raise ValueError('Duplicate native target proof event')
        seen.add(key)
        pair={canonical_team(t)for t in e['game_id'].split('_')[2:]}
        for t in pair:
            if e['offense']is not None and e['offense']!=t:continue
            g=out[e['game_id'],t];g['events']+=1;g['play_ids'].append(e['play_id'])
            if e['eligible_target_attempt']is True and e['attributed_receiver_id']is not None and e['offense']is not None:
                g['counts'][e['attributed_receiver_id']]+=1
            elif e['verified_offensive_eleven']and not e['attribution_conflict']:
                ids=e['native_offensive_players']
                if not isinstance(ids,list)or len(ids)!=11 or len(set(ids))!=11:raise ValueError('Exact11 target off-field proof differs')
                g['unknown_native'].update(ids)
            else:g['unknown_all']=True
    return out

def proof_zero(native,channel,physical,rush=None,target=None):
    """Return qualified zero evidence or explicit unknown reason, never positive fill."""
    if not physical or not physical['observed_source_offense_rows']or physical['unknown_possible_physical']:
        return dict(zero=False,reason='UNKNOWN_POSSIBLE_PHYSICAL_PLAY_OR_SOURCE_SIDE_CENSUS')
    if physical['all_physical_units_known']and native not in physical['native_on_field_union']:
        return dict(zero=True,reason='EXACT11_OFF_FIELD_EVERY_POSSIBLE_SOURCE_PHYSICAL_PLAY')
    if channel=='rush_attempts':
        if not rush or not rush['source_offense_rows']or any(rush[k]for k in('unknown_official_rush_membership','unknown_rusher_events','lateral_or_unknown_lateral_events')):
            return dict(zero=False,reason='UNKNOWN_OFFICIAL_RUSH_ELIGIBILITY_OR_CREDIT_CENSUS')
        if sum(a['official_carries']for a in rush['actors'].values())!=rush['known_official_carries']:raise ValueError('Full rusher credit census does not conserve')
        if native in rush['actors']and rush['actors'][native]['official_carries']>0:
            return dict(zero=False,reason='POSITIVE_OFFICIAL_RUSH_CREDIT_NOT_ZERO',reported_count=rush['actors'][native]['official_carries'])
        return dict(zero=True,reason='COMPLETE_OFFICIAL_RUSH_CREDIT_CENSUS_ZERO')
    if channel=='targets':
        if not target or not target['observed_game']or not target['events']or target['unknown_all']or native in target['unknown_native']:
            return dict(zero=False,reason='UNKNOWN_TARGET_ELIGIBILITY_RECIPIENT_OR_ON_FIELD_POSSIBILITY')
        if target['counts'].get(native,0)>0:return dict(zero=False,reason='POSITIVE_NATIVE_TARGET_CREDIT_NOT_ZERO',reported_count=target['counts'][native])
        return dict(zero=True,reason='COMPLETE_COMPATIBLE_TARGET_EVENT_CREDIT_OR_EXACT11_OFF_FIELD_ZERO')
    return dict(zero=False,reason='NO_PASSER_CREDIT_CENSUS_FOR_ON_FIELD_CANDIDATE_IN_INSPECTED_CACHES')
