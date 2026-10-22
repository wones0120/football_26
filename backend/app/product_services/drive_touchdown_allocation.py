"""Observed used-actor/field-position conditional physical TD allocation.

Passing and receiving are linked credits for one physical event. This is not a
roster counterfactual, an all-onfield census or a fitted future scoring law.
"""
from collections import defaultdict
from copy import deepcopy
import re,math
from uuid import UUID
from .evaluation_record import digest
from .original_drive_field_context import VERSION as DRIVE_VERSION
from .drive_scoring_range import VERSION as TERMINAL_VERSION
from .scoring_share_components import VERSION as SCORING_VERSION
from .market_snapshots import canonical_team

VERSION='drive_touchdown_allocation_v1'
OFFICIAL_VERSION='sourcewide_official_channel_component_v1'
NATIVE=re.compile(r'00-\d{7}')
BINS=('inside20','opponent_half_outside20','own_half')
CHANNELS=('pass_attempts','rush_attempts','targets')
NON_TD_TERMINALS={'FIELD_GOAL','MISSED_FG','BLOCKED_FG','BLOCKED_FG,_DOWNS','PUNT','BLOCKED_PUNT,_DOWNS','DOWNS','INTERCEPTION','FUMBLE','END_HALF','END_GAME'}
PAIRS=('physical_pass_vs_rush','actor_pass_vs_rush','actor_receiving_vs_rush','actor_linked_pass_vs_rush')


def _native(value):return isinstance(value,str)and bool(NATIVE.fullmatch(value))


def project_original_drive_links(records,order,*,before_period,max_rows=200000):
    """Minimal native CSV fields only, bound to the approved complete order map."""
    if order['version']!='validated_native_order_map_v1'or order['before_period']!=before_period:raise ValueError('Matched reviewed native timeline required')
    timeline={(r['game_id'],str(r['play_id'])):r['order_sequence']for r in order['rows']}
    if len(timeline)!=len(order['rows']):raise ValueError('Unique reviewed timeline keys required')
    def number(v):
        if v is None or v=='':return None
        try:n=float(v)
        except(TypeError,ValueError):raise ValueError('Explicit numeric native source field required')
        return n if math.isfinite(n)else None
    def integer(v,optional=False):
        n=number(v)
        if n is None and optional:return None
        if n is None or int(n)!=n:raise ValueError('Integral native original scope required')
        return int(n)
    rows=[];seen=set()
    for index,r in enumerate(records):
        if index>=max_rows:raise ValueError('Bounded original source rows required')
        if r['season_type']!='REG':continue
        year=integer(r['season']);week=integer(r['week'])
        if year*100+week>=before_period:continue
        gid=r['game_id'];parts=gid.split('_');pid=str(integer(r['play_id']));key=(gid,pid)
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']or not 1<=week<=18 or key in seen:raise ValueError('Unique exact native event period required')
        seen.add(key);team=canonical_team(r['posteam'])if r.get('posteam')not in(None,'')else None
        if team is not None and team not in{canonical_team(t)for t in parts[2:]}:raise ValueError('Native source offense differs from game')
        sequence=number(r['order_sequence'])
        if key not in timeline or sequence!=timeline[key]:raise ValueError('Source link differs from approved native order')
        rows.append(dict(game_id=gid,play_id=pid,team=team,original_drive_id=integer(r['drive'],True),source_order=sequence))
    if seen!=set(timeline):raise ValueError('Complete reviewed timeline key coverage required')
    return rows


def _bin(value):
    if value is None:return None
    if type(value)not in(int,float)or not math.isfinite(value)or not 0<=value<=100:raise ValueError('Native starting-yardline distance required')
    return 'inside20'if value<=20 else'opponent_half_outside20'if value<=50 else'own_half'


def resolve_actor_identity(rows):
    """All source candidate edges, including nonselected/ambiguous actor keys."""
    edges=defaultdict(set);reverse=defaultdict(set);prior_withheld=set();positions=defaultdict(set)
    for r in rows:
        n=r['native_GSIS']
        if not _native(n):raise ValueError('Native GSIS actor identity required')
        edges[n].update(r['canonical_candidate_ids'])
        if r.get('player_master_id')is not None:edges[n].add(r['player_master_id'])
        if r.get('identity_proven')is not True:prior_withheld.add(n)
        if r.get('source_position'):positions[n].add(r['source_position'])
    for n,values in edges.items():
        for pid in values:
            if str(UUID(str(pid)))!=pid:raise ValueError('Canonical UUID spelling required')
            reverse[pid].add(n)
    conflict={n for group in reverse.values()if len(group)>1 for n in group}|{n for n,v in edges.items()if len(v)>1}
    return {n:dict(player_master_id=next(iter(v))if len(v)==1 and n not in conflict|prior_withheld else None,canonical_qualified=len(v)==1 and n not in conflict|prior_withheld,canonical_candidates=sorted(v),conflicted=n in conflict,inherited_withheld=n in prior_withheld,source_positions=sorted(positions[n]))for n,v in edges.items()}


def _stats(logs):
    values=[r for r in logs if r['starting_field_bin']is not None and r['known_used']is True and r['outcome']is not None and r['credit_known']]
    n=len(values);unknown=[dict(game_id=r['game_id'],original_drive_id=r['original_drive_id'])for r in logs if r not in values]
    def moments(a,b):
        if not n:return dict(samples=0,mean_a=None,mean_b=None,cooccurrence=None,marginal_product=None,covariance=None)
        av=[r[a]for r in values];bv=[r[b]for r in values];ma=sum(av)/n;mb=sum(bv)/n
        return dict(samples=n,mean_a=ma,mean_b=mb,cooccurrence=sum(x*y for x,y in zip(av,bv))/n,marginal_product=ma*mb,covariance=sum((x-ma)*(y-mb)for x,y in zip(av,bv))/n if n>=2 else None)
    sample=dict(drives=n,physical_pass_vs_rush=moments('team_pass_TD','team_rush_TD'),actor_pass_vs_rush=moments('actor_passing_TD','actor_rushing_TD'),actor_receiving_vs_rush=moments('actor_receiving_TD','actor_rushing_TD'),actor_linked_pass_vs_rush=moments('actor_linked_pass_TD','actor_rushing_TD'),receiving_TD_credits=sum(r['actor_receiving_TD']for r in values),neither_drives=sum(r['outcome']=='neither'for r in values))
    return dict(eligible_or_possible_actor_drives=len(logs),unknown_drive_membership_or_outcome_ids=unknown,known_complete_sample=sample,exact=deepcopy(sample)if logs and not unknown else None)


def build_drive_touchdown_allocation(original,terminal,official,scoring,drive_links,identity_rows):
    for x,version in((original,DRIVE_VERSION),(terminal,TERMINAL_VERSION),(official,OFFICIAL_VERSION),(scoring,SCORING_VERSION)):
        if x.get('version')!=version or x['before_period']!=original['before_period']:raise ValueError('Matched reviewed native parent scope required')
    for x in(original,terminal,scoring):
        if x.get('pregame_serving_eligible')is not False:raise ValueError('Nonserving observed parents required')
    identities=resolve_actor_identity(identity_rows);links={}
    for r in drive_links:
        key=(r['game_id'],str(r['play_id']))
        if key in links:raise ValueError('Unique original source event link required')
        did=r['original_drive_id']
        if did is not None and(type(did)is not int or did<0):raise ValueError('Native original drive ID required')
        links[key]=r
    td_index={};event_groups=defaultdict(list);unbound=[];game_actors=defaultdict(set);seen=set()
    for e in scoring['event_basis']:
        key=(e['game_id'],str(e['play_id']))
        if key in td_index:raise ValueError('Unique physical scoring event required')
        if any(e[k]is not None and type(e[k])is not bool for k in('rush_TD','passing_and_receiving_same_TD')):raise ValueError('Tri-state source TD outcomes required')
        if e['rush_TD']is True and e['passing_and_receiving_same_TD']is True:raise ValueError('One physical TD cannot be rush and pass')
        td_index[key]=e
    for e in official['official_channel_event_basis']:
        key=(e['game_id'],str(e['play_id']))
        if key in seen:raise ValueError('Unique native official event required')
        seen.add(key);link=links.get(key);team=e['team'];actors=set();unknown=bool(e['unknown_channels'])
        for o in e['opportunities']:
            if o['channel']not in CHANNELS:continue
            actor=o.get('source_player_id')
            if actor is None:unknown=True
            elif not _native(actor):raise ValueError('Native opportunity actor GSIS required')
            else:actors.add(actor);game_actors[(e['game_id'],team)].add(actor)
        row=dict(event=deepcopy(e),actors=actors,unknown_actor_membership=unknown,scoring=td_index.get(key))
        if not link or link['original_drive_id']is None or link['team']!=team:
            if actors or unknown:unbound.append(dict(game_id=e['game_id'],team=team,play_id=e['play_id'],possible_actors=sorted(actors),unknown_other_actor_membership=unknown,source_scoring_evidence=deepcopy(row['scoring'])))
            continue
        event_groups[(e['game_id'],team,link['original_drive_id'])].append(row)
    terms={(g['native_game_id'],g['team'],d['original_drive_id']):d for g in terminal['game_rows']for d in g['drives']}
    if len(terms)!=sum(len(g['drives'])for g in terminal['game_rows']):raise ValueError('Unique native terminal drive required')
    drives=[];actor_logs=defaultdict(list);unassigned=[];physical_TD_keys=set();bound_source_keys=set();original_keys=set();game_keys=set()
    for g in original['game_rows']:
        gid,team=g['game_id'],g['team'];parts=gid.split('_')
        if len(parts)!=4 or not 1<=int(parts[1])<=18 or int(parts[0])*100+int(parts[1])>=original['before_period']or team not in{canonical_team(t)for t in parts[2:]}or(gid,team)in game_keys:raise ValueError('Unique strict native original game/team scope required')
        game_keys.add((gid,team));possible_unbound=any(r['game_id']==gid and r['team']==team for r in unbound)or g['unknown_original_drive_events']>0
        for d in g['drives']:
            did=d['original_drive_id'];key=(gid,team,did)
            if key in original_keys:raise ValueError('Unique original native drive required')
            original_keys.add(key);events=event_groups.get(key,[]);bound_source_keys.add(key);term=terms.get(key);actors=set().union(*(r['actors']for r in events))if events else set();uncertain_actor=possible_unbound or any(r['unknown_actor_membership']for r in events)
            candidates=actors|(game_actors[(gid,team)]if uncertain_actor else set());bin_=_bin(d['start_yardline100']);tds=[];unknown_TD=possible_unbound or not events
            for r in events:
                s=r['scoring']
                if s is None:
                    if r['event']['unknown_channels']:unknown_TD=True
                    continue
                if s['team']!=team:raise ValueError('Same native original offense and scoring team required')
                if s['rush_TD']is None or s['passing_and_receiving_same_TD']is None:unknown_TD=True
                if s['rush_TD']is True or s['passing_and_receiving_same_TD']is True:
                    physical=(gid,str(s['play_id']))
                    if physical in physical_TD_keys:raise ValueError('Physical TD bound to multiple original drives')
                    physical_TD_keys.add(physical);passing=s['passing_and_receiving_same_TD']is True
                    passer_ids={o.get('source_player_id')for o in r['event']['opportunities']if o['channel']=='pass_attempts'}
                    passer=next(iter(passer_ids))if len(passer_ids)==1 and None not in passer_ids else None
                    scorer=s['receiver']if passing else s['rusher']
                    if scorer is not None and not _native(scorer):raise ValueError('Native physical TD scorer required')
                    tds.append(dict(game_id=gid,play_id=s['play_id'],type='pass'if passing else'rush',passer=passer if passing else None,scorer=scorer,original_receiver=s['original_receiver'],original_rusher=s['original_rusher'],scorer_outside_observed_used_actor_cohort=scorer is not None and scorer not in actors))
            boundary=bool(term and term['native_boundary_and_cohort_verified']);end=term['verified_terminal_class']if term else None;outcome=None
            if boundary and not unknown_TD and len(tds)==1 and end=='TOUCHDOWN':outcome=tds[0]['type']
            elif boundary and not unknown_TD and not tds and end in NON_TD_TERMINALS:outcome='neither'
            credit_known=outcome is not None and(outcome=='neither'or(tds[0]['scorer']is not None and(outcome=='rush'or tds[0]['passer']is not None)))
            partitions={}
            for role in('passing_TD_credit','receiving_TD_credit','rushing_TD_credit'):
                selected=[t['passer']if role=='passing_TD_credit'else t['scorer']for t in tds if(t['type']=='pass')==(role!='rushing_TD_credit')]
                partitions[role]=dict(physical_event_credit_units=len(selected),observed_used_actor_credit_units=sum(n in actors for n in selected if n is not None),native_rest_credit_units=sum(n not in actors for n in selected if n is not None),unknown_actor_credit_units=sum(n is None for n in selected))
                part=partitions[role]
                assert part['physical_event_credit_units']==sum(part[k]for k in('observed_used_actor_credit_units','native_rest_credit_units','unknown_actor_credit_units'))
            drive=dict(game_id=gid,team=team,original_drive_id=did,source_start_yardline100=d['start_yardline100'],starting_field_bin=bin_,verified_terminal_class=end,native_boundary_verified=boundary,outcome=outcome,known_physical_TD_events=tds,role_typed_credit_partitions=partitions,source_used_native_actors=sorted(actors),unknown_actor_membership=uncertain_actor,eligible_possible_native_actor_ids=sorted(candidates),source_official_event_rows=len(events),credit_known=credit_known,rest_scorer_native_ids=sorted({t['scorer']for t in tds if t['scorer']is not None and t['scorer']not in actors}))
            drives.append(drive)
            if uncertain_actor:unassigned.append(dict(game_id=gid,team=team,original_drive_id=did,known_native_actor_candidates=sorted(candidates),unknown_other_actors=True))
            for actor in sorted(candidates):
                t=tds[0]if outcome in('pass','rush')else None
                log=dict(game_id=gid,team=team,original_drive_id=did,starting_field_bin=bin_,known_used=True if actor in actors else None,outcome=outcome,credit_known=credit_known,team_pass_TD=int(outcome=='pass'),team_rush_TD=int(outcome=='rush'),actor_passing_TD=int(bool(t and t['type']=='pass'and t['passer']==actor)),actor_rushing_TD=int(bool(t and t['type']=='rush'and t['scorer']==actor)),actor_receiving_TD=int(bool(t and t['type']=='pass'and t['scorer']==actor)))
                log['actor_linked_pass_TD']=int(bool(log['actor_passing_TD']or log['actor_receiving_TD']))
                actor_logs[(int(gid[:4]),team,actor)].append(log)
    extra=set(event_groups)-bound_source_keys;excluded_groups=[]
    for key in sorted(extra):
        group=event_groups[key]
        quiet=all(not r['actors']and not r['unknown_actor_membership']and r['scoring']is not None and r['scoring']['rush_TD']is False and r['scoring']['passing_and_receiving_same_TD']is False for r in group)
        if not quiet:raise ValueError('Possible opportunity/TD source references unknown original drive; preserve source gap before publication')
        excluded_groups.append(dict(game_id=key[0],team=key[1],original_drive_id=key[2],source_play_ids=[r['event']['play_id']for r in group],proof='All source rows explicitly have zero official channel opportunities, zero unknown channels, and both eligible TD predicates false; not a physical offensive-drive cohort'))
    profiles=[]
    for(year,team,actor),logs in sorted(actor_logs.items()):
        proof=identities.get(actor,dict(player_master_id=None,canonical_qualified=False,canonical_candidates=[],conflicted=False,inherited_withheld=True,source_positions=[]));cells={b:_stats([r for r in logs if r['starting_field_bin']in(None,b)])for b in BINS};comparisons={}
        for a,b in(('inside20','own_half'),('opponent_half_outside20','own_half')):
            x,y=cells[a]['exact'],cells[b]['exact'];comparisons[a+'_minus_'+b]={channel:dict(pass_rate=x[channel]['mean_a']-y[channel]['mean_a'],rush_rate=x[channel]['mean_b']-y[channel]['mean_b'],covariance=x[channel]['covariance']-y[channel]['covariance']if x[channel]['covariance']is not None and y[channel]['covariance']is not None else None)if x is not None and y is not None and proof['canonical_qualified']else None for channel in PAIRS}
        profiles.append(dict(season=year,team=team,native_GSIS=actor,identity=proof,cells=cells,across_starting_field_bin_comparisons=comparisons,actor_drive_rows=logs))
    unbound_tds=[deepcopy(s)for key,s in td_index.items()if key not in physical_TD_keys and(s['rush_TD']is True or s['passing_and_receiving_same_TD']is True)]
    core=dict(version=VERSION,catalog_id='G24-M04',before_period=original['before_period'],drive_rows=drives,actor_profiles=profiles,unbound_official_source_events=unbound,excluded_known_nonopportunity_nonTD_original_groups=excluded_groups,unbound_physical_TD_events=unbound_tds,unknown_actor_residual=unassigned,global_identity_proofs=identities,definitions=dict(cohort='Native actor with >=1 verified official pass/rush/target opportunity on that ORIGINAL drive, independent of TD outcome; no absent/noopportunity zeros and no allonfield census',physical_budget='One unique originaldrive passTD/rushTD/neither/unknown; linked passer+receiving credits are one physicalTD',field='Source-proven starting distance to opponent goal, <=20/21..50/>50; not terminal or return landing position',actors='Passing, rushing, receiving credits ROLE-TYPED; observed native passer can be nonQB trick passer. Lateral scorer outside cohort retained in native rest',comparison='Same actor/useddrive matched teamtype and actorcredit marginal/cooccurrence/population covariance by fixed starting fieldbin; no fitted causal or future law',unknown='Certified terminal required for neither; uncertain TD, native link, actor cohort, field bin, identity or rest attribution masks compatible full statistics; known complete sample explicit'),pregame_serving_eligible=False,forecast=None)
    return dict(**core,semantic_sha256=digest(core))
