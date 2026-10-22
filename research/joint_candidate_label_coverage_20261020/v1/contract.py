"""Fixed source-history candidate audit, not an allocation trainer."""
CHANNEL_FIELDS={'pass_attempts':'attempts','rush_attempts':'carries','targets':'targets'}

def audit_group(context,actor_index,team_index):
    gid,team=context['game_id'],context['team'];window=context['windows']['own'];ids=window['game_ids'];period=context['period'];prior=[]
    if len(ids)>3 or len(ids)!=len(set(ids)) or any(int(g.split('_')[0])!=period//100 or int(g.split('_')[0])*100+int(g.split('_')[1])>=period for g in ids):raise ValueError('Strict unique same-season prior3 required')
    history_achieved=len(ids)==3 and all(team_index.get((g,team),{}).get('source_rows',0)>0 for g in ids)
    for g in ids:prior.extend(actor_index.get((g,team),[]))
    candidates={}
    for row in prior:
        sid=row['source_player_id']
        if sid is not None:candidates.setdefault(sid,[]).append(row)
    current=actor_index.get((gid,team),[]);by_native={r['source_player_id']:r for r in current if r['source_player_id']is not None}
    if len(by_native)!=sum(r['source_player_id']is not None for r in current):raise ValueError('Unique target native rows required')
    labels=[]
    for sid,rs in sorted(candidates.items()):
        attachment={r['player_master_id']for r in rs if r['player_master_id']is not None};pid=next(iter(attachment))if len(attachment)==1 else None;target=by_native.get(sid)
        counts=dict(target['counts'])if target else dict.fromkeys(CHANNEL_FIELDS)
        labels.append(dict(source_player_id=sid,prior_source_ids=[r['source_id']for r in rs],prior_games=[r['game_id']for r in rs],prior_roles=sorted({r['source_position']for r in rs if r['source_position']is not None}),prior_all_three_channels_known_zero=all(all(r['counts'][c]==0 for c in CHANNEL_FIELDS)for r in rs),canonical_prior_attachment=pid,canonical_prior_attachment_conflict=len(attachment)>1,target_source_id=target['source_id']if target else None,target_canonical_attachment=target['player_master_id']if target else None,counts=counts,canonical_same_native_label_qualified=bool(pid and target and target['player_master_id']==pid),missing_reason=None if target else'NO_CURRENT_RAW_NATIVE_ROW_UNKNOWN_NOT_ZERO'))
    outside=[r for r in current if r['source_player_id']not in candidates];group=team_index[(gid,team)];channels={}
    for channel,field in CHANNEL_FIELDS.items():
        known=[r for r in labels if r['counts'][channel]is not None];unknown=[r for r in labels if r['counts'][channel]is None];restknown=[r for r in outside if r['counts'][channel]is not None];restunknown=[r for r in outside if r['counts'][channel]is None]
        a=sum(r['counts'][channel]for r in known);b=sum(r['counts'][channel]for r in restknown);budget=group['values'][field]
        complete=bool(history_achieved and candidates and budget is not None and not unknown and not restunknown)
        if complete and a+b!=budget:raise ValueError('Disjoint candidate/rest must equal compatible source budget')
        canonical_complete=complete and all(r['canonical_same_native_label_qualified']for r in labels)
        channels[channel]=dict(source_observed_budget=budget,known_candidate_sum=a,unknown_candidate_count=len(unknown),known_candidate_count=len(known),known_zero_candidate_count=sum(r['counts'][channel]==0 for r in known),canonical_unqualified_candidate_count=sum(not r['canonical_same_native_label_qualified']for r in labels),numeric_disjoint_outside_rest=b if not restunknown else None,known_outside_canonical_sum=sum(r['counts'][channel]for r in restknown if r['player_master_id']is not None),known_outside_unresolved_sum=sum(r['counts'][channel]for r in restknown if r['player_master_id']is None),unknown_outside_count=len(restunknown),source_known_candidate_plus_outside_sum=a+b,unidentified_absent_candidate_mass=True if unknown else False,native_source_complete_group=complete,canonical_complete_group=canonical_complete,independent_NFL_census='UNKNOWN',missing_candidate_count_not_inferred_from_source_total=True)
    P,T=channels['pass_attempts']['source_observed_budget'],channels['targets']['source_observed_budget']
    if P is not None and T is not None and T>P:raise ValueError('Source targets exceed compatible source passes')
    return dict(game_id=gid,team=team,period=period,prior_games=ids,history_achieved=history_achieved,candidate_count=len(labels),candidate_prior_all_channels_zero=sum(r['prior_all_three_channels_known_zero']for r in labels),candidate_native_labels=labels,current_outside_candidate_source_ids=[r['source_id']for r in outside],source_target_actor_rows=len(current),channels=channels,source_pass_minus_source_target_remainder=P-T if P is not None and T is not None else None,target_fraction=T/P if P and T is not None else None,participation_census='UNKNOWN',future_unconditional_population_identified=False)
