"""Observed source/scored/excluded budget accounting; never redistribution.

This target-game ledger is validation evidence only. It must not enter features
for that game, and source-observed sums are not a complete active-roster census.
"""
from collections import defaultdict
from uuid import UUID
import math
from .market_snapshots import canonical_team

VERSION='model_source_budget_ledger_v1'
CHANNELS=('pass_attempts','rush_attempts','targets')


def build_source_budget_ledger(records,*,scored_subjects=(),positive_missing=(),unscoped_threats=()):
    scored={(r['game_id'],canonical_team(r['team']),str(UUID(str(r['player_master_id'])))):set(r.get('channels',CHANNELS))for r in scored_subjects}
    groups=defaultdict(list);seen=set();native=set()
    for row in records:
        gid=row['game_id'];team=canonical_team(row['team']);parts=gid.split('_');source_id=str(row['source_id'])
        if len(parts)!=4 or team not in {canonical_team(t)for t in parts[2:]}or source_id in seen:raise ValueError('Unique source row/native game/team required')
        seen.add(source_id);pid=row.get('player_master_id');pid=str(UUID(str(pid)))if pid is not None else None
        sid=row.get('source_player_id')
        if sid is not None:
            key=(gid,team,sid)
            if key in native:raise ValueError('Duplicate native actor/game source')
            native.add(key)
        counts=row['counts']
        if set(counts)!=set(CHANNELS)or any(v is not None and(type(v)not in(int,float)or not math.isfinite(v)or v<0 or int(v)!=v)for v in counts.values()):raise ValueError('Known nonnegative official count or explicit unknown required')
        groups[(gid,team)].append(dict(row,team=team,player_master_id=pid))
    threats=defaultdict(list)
    for r in positive_missing:
        if type(r.get('offense_snaps'))not in(int,float)or not r['offense_snaps']>0:raise ValueError('Positive source participation proof required')
        key=(r['native_game_id'],canonical_team(r['team']));threats[key].append(r)
    uncertain=defaultdict(list)
    for threat in unscoped_threats:
        gid=threat['game_id'];pair={canonical_team(t)for t in gid.split('_')[2:]}
        possible={canonical_team(t)for t in threat['possible_teams']}
        if not possible or not possible<=pair:raise ValueError('Unscoped source contribution needs compatible native sides')
        for team in possible:uncertain[(gid,team)].append(threat)
    result=[]
    for (gid,team),rows in sorted(groups.items()):
        metrics={}
        for channel in CHANNELS:
            known=[r for r in rows if r['counts'][channel]is not None]
            included=[r for r in known if r['player_master_id']is not None and channel in scored.get((gid,team,r['player_master_id']),set())]
            excluded=[r for r in known if r['player_master_id']is not None and channel not in scored.get((gid,team,r['player_master_id']),set())]
            unresolved=[r for r in known if r['player_master_id']is None]
            total=sum(r['counts'][channel]for r in known);a,b,c=(sum(r['counts'][channel]for r in group)for group in(included,excluded,unresolved))
            if total!=a+b+c:raise ValueError('Source partition must conserve known observed mass')
            unknown_scope=sum(r['counts'].get(channel)!=0 for r in uncertain[(gid,team)])
            complete=len(known)==len(rows)and not threats[(gid,team)]and not unknown_scope
            metrics[channel]=dict(known_source_sum=total,exact_source_total=total if complete else None,known_scored_sum=a,known_excluded_canonical_sum=b,known_unresolved_sum=c,unknown_source_rows=len(rows)-len(known),unscoped_possible_contribution_rows=unknown_scope,positive_missing_participant_rows=len(threats[(gid,team)]),source_complete_within_declared_records=complete,missing_actor_mass_donated=False)
        result.append(dict(game_id=gid,team=team,source_actor_rows=len(rows),scored_source_actors=sum(r['player_master_id']is not None and(gid,team,r['player_master_id'])in scored for r in rows),channels=metrics))
    unlinked_threats=[dict(game_id=g,team=t,positive_missing_rows=len(v))for(g,t),v in threats.items()if(g,t)not in groups]
    return dict(version=VERSION,team_game_rows=result,unlinked_positive_missing=unlinked_threats,unlinked_unscoped=[dict(game_id=g,team=t,threats=v)for(g,t),v in uncertain.items()if(g,t)not in groups],usage='Target-game validation evidence only; forbidden same-game predictor',completeness='Complete within declared retained records and explicit positive-missing threats only; not independently complete NFL roster/source acquisition')
