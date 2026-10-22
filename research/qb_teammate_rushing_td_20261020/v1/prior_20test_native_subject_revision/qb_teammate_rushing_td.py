"""Observed QB/teammate rushing-TD allocation; never a forward TD law."""
from collections import Counter,defaultdict
from copy import deepcopy
from itertools import product
from uuid import UUID
from .shared_scoring_pair_covariance import _count,_stats,NATIVE
from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION='qb_teammate_rushing_td_v1'


def summarize(rows):
    if len(rows)<2:return None
    q=[r['QB_rushing_TDs']for r in rows];t=[r['teammate_rushing_TDs']for r in rows];n=len(rows)
    for r in rows:
        if any(type(r[k])is not int or r[k]<0 for k in ('QB_rushing_TDs','teammate_rushing_TDs','team_rushing_TDs','rest_rushing_TDs'))or r['QB_rushing_TDs']+r['teammate_rushing_TDs']+r['rest_rushing_TDs']!=r['team_rushing_TDs']:raise ValueError('One conserved physical rushing-TD budget required')
    px=sum(v>=1 for v in q)/n;py=sum(v>=1 for v in t)/n;joint=sum(a>=1 and b>=1 for a,b in zip(q,t))/n
    cells=defaultdict(list)
    for r in rows:cells[r['team_rushing_TDs']].append(r)
    return dict(samples=n,rushing_TD_counts=_stats(list(zip(q,t))),coexceedance=dict(QB_threshold=1,teammate_threshold=1,observed_joint=joint,QB_marginal=px,teammate_marginal=py,independence_marginal_product=px*py,observed_minus_independence=joint-px*py),budget_strata=[dict(team_rushing_TD_budget=b,samples=len(rs),weight=len(rs)/n,QB_TDs=sum(r['QB_rushing_TDs']for r in rs),teammate_TDs=sum(r['teammate_rushing_TDs']for r in rs),rest_TDs=sum(r['rest_rushing_TDs']for r in rs),QB_share=sum(r['QB_rushing_TDs']for r in rs)/(b*len(rs))if b else None,teammate_share=sum(r['teammate_rushing_TDs']for r in rs)/(b*len(rs))if b else None)for b,rs in sorted(cells.items())],physical_TD_budget=sum(r['team_rushing_TDs']for r in rows),QB_TDs=sum(q),teammate_TDs=sum(t),rest_TDs=sum(r['rest_rushing_TDs']for r in rows))


def build_qb_teammate_rushing_td(actor_rows,games,events):
    expected={(g['game_id'],g['team']):g for g in games}
    if len(expected)!=len(games):raise ValueError('Unique native scheduled side required')
    for g in games:
        parts=g['game_id'].split('_')
        if len(parts)!=4 or parts[:2]!=[str(g['season']),f"{g['week']:02d}"]or g['team']not in {canonical_team(t)for t in parts[2:]}:raise ValueError('Native scheduled side/period required')
    actors={};native_keys=set();source_identities=defaultdict(set);qualified=defaultdict(list)
    for a in actor_rows:
        key=(a['game_id'],a['team'],a['native_GSIS'])
        if key[:2]not in expected or key in actors or not NATIVE.fullmatch(a['native_GSIS']):raise ValueError('Unique source actor/native game required')
        actors[key]=a;native_keys.add(a['native_GSIS']);qualified[a['native_GSIS']].append(a.get('identity_proven')is True)
        source_identities[a['native_GSIS']].update(a['canonical_candidate_ids'])
        if a['player_master_id']is not None:source_identities[a['native_GSIS']].add(a['player_master_id'])
    reverse=defaultdict(set)
    for native,pids in source_identities.items():
        if any(str(UUID(str(pid)))!=pid for pid in pids):raise ValueError('Canonical UUID spelling required')
        for pid in pids:reverse[pid].add(native)
    conflict={n for ns in reverse.values()if len(ns)>1 for n in ns}|{n for n,ids in source_identities.items()if len(ids)>1}
    identities={n:next(iter(ids))if len(ids)==1 and n not in conflict and all(qualified[n])else None for n,ids in source_identities.items()}
    owned=Counter();known=Counter();unknown=Counter();unattributed=Counter();credited=Counter();requires_carry=Counter();event_ids=defaultdict(set);seen=set();physical=[]
    for e in events:
        key=(e['game_id'],str(e['play_id']))
        if key in seen:raise ValueError('Physical native rushing TD counted once')
        seen.add(key);sides=[k for k in expected if k[0]==e['game_id']]
        if not sides:raise ValueError('Native scoring game absent from schedule')
        team=e['team'];scope=(e['game_id'],team)
        if team is not None and scope not in expected:raise ValueError('Native offense differs')
        if team is not None:owned[scope]+=1
        value=e['rush_TD'];rusher=e.get('rusher')
        if value is not None and type(value)is not bool:raise ValueError('Tri-state physical rushTD required')
        if value is False:continue
        if rusher is not None and rusher not in native_keys:raise ValueError('Every potentially credited native scorer needs frozen global identity evidence')
        physical.append(deepcopy(e))
        if value is None or team is None:
            for s in [scope]if team is not None else sides:unknown[s]+=1
            continue
        known[scope]+=1
        if rusher is None:unattributed[scope]+=1;continue
        credited[(*scope,rusher)]+=1;event_ids[(*scope,rusher)].add(str(e['play_id']))
        if not(e.get('lateral_rush')is True and isinstance(e.get('original_rusher'),str)and NATIVE.fullmatch(e['original_rusher'])and e['original_rusher']!=rusher):requires_carry[(*scope,rusher)]+=1
    qb=defaultdict(set);teammates=defaultdict(set);schedules=defaultdict(list)
    for key,g in expected.items():schedules[(g['season'],g['team'])].append(g)
    for a in actor_rows:
        group=(expected[(a['game_id'],a['team'])]['season'],a['team'])
        if a['source_position']=='QB':qb[group].add(a['native_GSIS'])
        if (_count(a['official_rush_attempts'])or 0)>0 or any(credited[(g['game_id'],group[1],a['native_GSIS'])]>0 for g in schedules[group]):teammates[group].add(a['native_GSIS'])
    profiles=[];pair_rows=[];windows=[]
    for group,gs in sorted(schedules.items()):
        gs.sort(key=lambda g:(g['week'],g['game_id']))
        for q,t in product(sorted(qb[group]),sorted(teammates[group])):
            if q==t:continue
            logs=[]
            for g in gs:
                scope=(g['game_id'],g['team']);qa=actors.get((*scope,q));ta=actors.get((*scope,t));complete=bool(qa and ta and identities[q]and identities[t]and identities[q]!=identities[t]and qa['source_position']=='QB'and all(a['participation']is True and a.get('source_scope_proven',True)is True and _count(a['official_rush_attempts'])is not None for a in (qa,ta))and owned[scope]and not(unknown[scope]or unattributed[scope]))
                carry_sanity=None
                if qa and ta and all(_count(a['official_rush_attempts'])is not None for a in (qa,ta)):
                    carry_sanity=requires_carry[(*scope,q)]<=_count(qa['official_rush_attempts'])and requires_carry[(*scope,t)]<=_count(ta['official_rush_attempts'])
                    if not carry_sanity:complete=False
                r=dict(game_id=g['game_id'],season=g['season'],week=g['week'],team=g['team'],QB_native_GSIS=q,teammate_native_GSIS=t,complete=complete,carry_sanity_compatible=carry_sanity)
                if complete:
                    qn=credited[(*scope,q)];tn=credited[(*scope,t)];assert not event_ids[(*scope,q)]&event_ids[(*scope,t)]
                    assert qn+tn<=known[scope]
                    r.update(QB_rushing_TDs=qn,teammate_rushing_TDs=tn,team_rushing_TDs=known[scope],rest_rushing_TDs=known[scope]-qn-tn,QB_TD_play_ids=sorted(event_ids[(*scope,q)]),teammate_TD_play_ids=sorted(event_ids[(*scope,t)]),QB_official_carries=qa['official_rush_attempts'],teammate_official_carries=ta['official_rush_attempts'])
                logs.append(r);pair_rows.append(r)
            sample=[r for r in logs if r['complete']];profiles.append(dict(season=group[0],team=group[1],QB_native_GSIS=q,teammate_native_GSIS=t,expected_game_ids=[r['game_id']for r in logs],unknown_game_ids=[r['game_id']for r in logs if not r['complete']],exact=summarize(sample)if len(sample)==len(logs)else None,known_complete_sample=summarize(sample)))
            for i,g in enumerate(gs):
                if i<2:continue
                # Both identities/roles/teammate rushing exposure must be evidenced earlier.
                previous=gs[:i]
                if not any((old['game_id'],group[1],q)in actors and actors[(old['game_id'],group[1],q)]['source_position']=='QB'for old in previous):continue
                if not any((old['game_id'],group[1],t)in actors and ((_count(actors[(old['game_id'],group[1],t)]['official_rush_attempts'])or 0)>0 or credited[(old['game_id'],group[1],t)]>0)for old in previous):continue
                prior=logs[max(0,i-8):i];sample=[r for r in prior if r['complete']]
                windows.append(dict(target_game_id=g['game_id'],target_period=g['season']*100+g['week'],team=group[1],season=group[0],QB_native_GSIS=q,teammate_native_GSIS=t,QB_player_master_id=identities[q],teammate_player_master_id=identities[t],contributing_game_ids=[r['game_id']for r in prior],unknown_game_ids=[r['game_id']for r in prior if not r['complete']],exact=summarize(sample)if len(sample)==len(prior)else None,known_complete_sample=summarize(sample)))
    core=dict(version=VERSION,catalog_id='X07-M02',pair_game_rows=pair_rows,profiles=profiles,strict_prior_windows=windows,physical_rushing_TD_evidence=physical,team_game_budget=[dict(game_id=s[0],team=s[1],known_rushing_TDs=known[s],unknown_eligibility=unknown[s],unknown_scorer=unattributed[s],source_owned_rows=owned[s])for s in sorted(expected)],native_identity_conflicts=sorted(conflict),definitions=dict(counts='Source-derived physical rushing-TD credits, NOT reconciled official weekly rushing-TD aggregate',pair='Source-proven QB plus distinct native teammate with observed prior carry/TD exposure; authoritative native scorer and original rusher retained',sample='Identical known source/positive participant/carry/canonical pair/game sample, knownzero budgets retained',window='Up to8immediately prior same-team/season scheduled games, no unknown skipping; prior-only pair evidence',budget='All native rushTD actors inclQB/WR/TE/unmapped rest, one physical TD once; zero budget share undefined',sanity='Non-lateral own credited TDs cannot exceed official carries; source-proven lateral credited TD may have0carries. No official weekly rushing-TD aggregate reconciliation claimed'),pregame_serving_eligible=False,forecast=None)
    return dict(**core,semantic_sha256=digest(core))
