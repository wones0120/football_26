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
        out[g['game_id'],g['team']]=dict(cross_credit_conflicts=[],observed_source_offense_rows=g['observed_offense_rows'],known_physical_snaps=g['known_physical_snaps'],unknown_possible_physical=g['unknown_physical_or_side'],unknown_units=g['unknown_units'],all_physical_units_known=complete,native_on_field_union=union,unit_ids=sorted(g['unit_snaps']))
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
    if channel=='rush_attempts'and rush and rush['actors'].get(native,{}).get('official_carries',0)>0:
        return dict(zero=False,reason='POSITIVE_OFFICIAL_RUSH_CREDIT_NOT_ZERO',reported_count=rush['actors'][native]['official_carries'])
    if channel=='targets'and target and target['counts'].get(native,0)>0:
        return dict(zero=False,reason='POSITIVE_NATIVE_TARGET_CREDIT_NOT_ZERO',reported_count=target['counts'][native])
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


def corroborate_native_credits(physical,block,rush_events,target_events):
    """Material credits cannot leave incomplete/mismatched eleven proof usable."""
    import re
    units=block['unit_registry'];events={(e['game_id'],e['play_id']):e for e in block['event_basis']}
    for source,rows in [('rush',rush_events),('target',target_events)]:
        for r in rows:
            if source=='rush':
                if r['eligible']is False or r['offense']is None:continue
                natives=[]
                if r['native_rusher_valid']:natives.append(r['native_rusher'])
                lateral=r.get('reported_lateral_rusher')
                if isinstance(lateral,str)and re.fullmatch(r'00-\d{7}',lateral):natives.append(lateral)
                off=r['offense'];reported_conflict=False
            else:
                if r['offense']is None or r['native_receiver_id']is None:continue
                natives=[r['native_receiver_id']];off=r['offense'];reported_conflict=r['attribution_conflict']
            e=events.get((r['game_id'],r['play_id']));key=r['game_id'],off
            if key not in physical:
                physical[key]=dict(observed_source_offense_rows=0,known_physical_snaps=0,unknown_possible_physical=1,unknown_units=1,all_physical_units_known=False,native_on_field_union=set(),unit_ids=[],cross_credit_conflicts=[])
            for native in set(natives):
                reasons=[]
                if not e or e['unit_id']is None or e.get('physical_membership')is not True:
                    reasons.append('missing_matching_source_physical_event_or_unit')
                else:
                    ids={x[0]for x in units[e['unit_id']]['native_participant_roles']}
                    if e['team']!=off:reasons.append('same_key_source_side_conflict')
                    if native not in ids:reasons.append('reported_native_credit_outside_eleven')
                if reported_conflict:reasons.append('source_attribution_conflict')
                if reasons:
                    physical[key]['all_physical_units_known']=False
                    physical[key]['cross_credit_conflicts'].append(dict(play_id=r['play_id'],native_actor=native,credit=source,reasons=reasons))


def credit_compatibility(channel,candidates,budget,rush=None,target=None,outside_rest=None):
    """Compare known source labels; never overwrite a contradiction or fill it."""
    conflicts=[];known=[r for r in candidates if r['counts'][channel]is not None]
    if channel=='rush_attempts':
        if not rush or not rush['source_offense_rows']or any(rush[k]for k in('unknown_official_rush_membership','unknown_rusher_events','lateral_or_unknown_lateral_events')):
            return dict(status='UNKNOWN_OFFICIAL_RUSH_CREDIT_CENSUS',conflicts=[],budget_compatible=None)
        credits={n:r['official_carries']for n,r in rush['actors'].items()};credit_total=sum(credits.values())
        if credit_total!=rush['known_official_carries']:raise ValueError('Rush census count identity differs')
        for r in known:
            n=r['source_player_id'];v=credits.get(n,0)
            if r['counts'][channel]!=v:conflicts.append(dict(native=n,weekly_source_count=r['counts'][channel],native_event_credit_count=v,source_id=r['target_source_id']))
        outside_credit=sum(v for n,v in credits.items()if n not in {r['source_player_id']for r in candidates})
        if outside_rest is not None and outside_rest!=outside_credit:conflicts.append(dict(scope='OUTSIDE_CANDIDATE_REST',weekly_source_count=outside_rest,native_event_credit_count=outside_credit))
        match=budget is not None and budget==credit_total
        return dict(status='CONTRADICTED'if conflicts or budget is not None and not match else'COMPATIBLE_RECORDED_CREDIT_COUNTS'if match else'UNKNOWN_WEEKLY_BUDGET',conflicts=conflicts,source_observed_budget=budget,native_known_credit_sum=credit_total,budget_compatible=match,independent_NFL_census='UNKNOWN')
    if channel=='targets':
        if not target or not target['observed_game']:return dict(status='UNKNOWN_TARGET_SOURCE_GAME',conflicts=[],budget_compatible=None)
        credits=target['counts'];credit_total=sum(credits.values());unassessed=0
        for r in known:
            n=r['source_player_id'];v=credits.get(n,0);exact=not target['unknown_all']and n not in target['unknown_native']
            if r['counts'][channel]<v or exact and r['counts'][channel]!=v:
                conflicts.append(dict(native=n,weekly_source_count=r['counts'][channel],native_known_credit_count=v,exact_credit_membership=exact,source_id=r['target_source_id']))
            if not exact:unassessed+=1
        outside_credit=sum(v for n,v in credits.items()if n not in {r['source_player_id']for r in candidates})
        if outside_rest is not None and outside_rest<outside_credit:conflicts.append(dict(scope='OUTSIDE_CANDIDATE_REST',weekly_source_count=outside_rest,native_known_credit_count=outside_credit))
        match=budget is not None and budget==credit_total
        contradiction=bool(conflicts or budget is not None and budget<credit_total)
        return dict(status='CONTRADICTED'if contradiction else'COMPATIBLE_KNOWN_TARGET_CREDITS'if match else'UNKNOWN_UNASSIGNED_TARGET_BUDGET',conflicts=conflicts,source_observed_budget=budget,native_known_credit_sum=credit_total,budget_compatible=match,known_weekly_candidate_exact_event_credit_unassessed=unassessed,unknown_recipient_or_eligibility_membership_retained=bool(target['unknown_all']or target['unknown_native']),independent_NFL_census='UNKNOWN')
    return dict(status='NO_PASSER_CREDIT_CENSUS_IN_INSPECTED_CACHES',conflicts=[],budget_compatible=None)
