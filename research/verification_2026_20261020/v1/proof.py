"""Bounded retained-source credit/zero proofs; no model or role inference."""
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import re
from backend.app.product_services.contact_cohort_reconciliation import official_rush_eligibility
from backend.app.product_services.coverage_receiver_performance import _target_eligible
from backend.app.product_services.fumble_event_components import _eligibility,_flag
from backend.app.product_services.market_snapshots import canonical_team
CHANNELS=('pass_attempts','rush_attempts','targets')
NATIVE=re.compile(r'00-\d{7}')

def num(v):
 if v in(None,'')or type(v)is bool:return None
 try:n=Decimal(str(v))
 except InvalidOperation:return None
 return int(n)if n.is_finite()and n>=0 and n==n.to_integral_value()else None

def valid(n):return isinstance(n,str)and NATIVE.fullmatch(n)is not None

def pass_eligible(raw):
 live,_=_eligibility(raw)
 if live is False:return False
 p,r,s,sc=(_flag(raw.get(k))for k in('pass_attempt','rush_attempt','sack','qb_scramble'))
 if p is True and r is True or sc is True and(r is not True or p is True or s is True):return None
 if p is False or s is True:return False
 return True if live is True and p is True and r is False and s is False and sc is False else None

def build_census(rows,schedule):
 games={g['game_id']:g for g in schedule};groups={};seen=set();events=[]
 def cell():return dict(known_events=0,credits={},unknown_events=[],unknown_credit_events=[],source_offense_rows=0)
 for gid,g in games.items():
  for t in[g['home_team'],g['away_team']]:groups[gid,canonical_team(t)]={c:cell()for c in CHANNELS}
 for raw in rows:
  if raw.get('season_type')!='REG':continue
  gid=raw['game_id'];play=num(raw['play_id'])
  if gid not in games or play is None:raise ValueError('Unknown native game/play')
  g=games[gid];pair={canonical_team(g['home_team']),canonical_team(g['away_team'])}
  if num(raw.get('season'))!=2026 or num(raw.get('week'))!=g['week']:raise ValueError('Native source period mismatch')
  if(gid,play)in seen:raise ValueError('Duplicate native event')
  seen.add((gid,play));off=canonical_team(raw['posteam'])if raw.get('posteam')else None;defense=canonical_team(raw['defteam'])if raw.get('defteam')else None
  if any(t is not None and t not in pair for t in(off,defense))or off is not None and off==defense:raise ValueError('Conflicting native side')
  elig=dict(pass_attempts=pass_eligible(raw),rush_attempts=official_rush_eligibility(raw),targets=_target_eligible(raw)[0]);natives=dict(pass_attempts=raw.get('passer_player_id')or None,rush_attempts=raw.get('rusher_player_id')or None,targets=raw.get('receiver_player_id')or None)
  p,r,sa,sc,sp,kn=(_flag(raw.get(k))for k in('pass_attempt','rush_attempt','sack','qb_scramble','qb_spike','qb_kneel'))
  contradiction=(p is True and r is True)or(r is True and sa is True)or(sc is True and(r is not True or p is True or sa is True))or(kn is True and(r is not True or p is True or sa is True or sc is True or sp is True))or(sp is True and(p is not True or r is True or sa is True or sc is True or kn is True))
  physical_class=raw.get('play_type')in{'run','pass','qb_kneel','qb_spike'}or raw.get('play_type_nfl')in{'RUSH','PASS','SACK','QB_KNEEL','QB_SPIKE'}
  zero_union=all(_flag(raw.get(k))is False for k in('pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','qb_kneel','qb_spike'))
  # Explicit no-play/two-point exclusions win; a purported physical snap with
  # contradictory all-zero official evidence is unknown, never a source zero.
  explicit_exclusion=raw.get('play_type')=='no_play'or _flag(raw.get('no_play'))is True or _flag(raw.get('two_point_attempt'))is True
  if not explicit_exclusion and(contradiction or physical_class and zero_union):elig=dict.fromkeys(CHANNELS)
  lateral=_flag(raw.get('lateral_rush'));yards=raw.get('lateral_rushing_yards')
  try:lateral_yards_unknown_or_nonzero=yards not in(None,'')and(not Decimal(str(yards)).is_finite()or Decimal(str(yards))!=0)
  except InvalidOperation:lateral_yards_unknown_or_nonzero=True
  lateral_bad=lateral is not False or bool(raw.get('lateral_rusher_player_id'))or lateral_yards_unknown_or_nonzero
  for t in pair:
   if off is not None and t!=off:continue
   for ch in CHANNELS:
    c=groups[gid,t][ch]
    if off is not None and defense is not None:c['source_offense_rows']+=1
    if elig[ch]is False:continue
    if elig[ch]is None or off is None or defense is None:c['unknown_events'].append(play);continue
    # A target requires a known initial recipient. Missing receiver never means throwaway/zero.
    if ch=='targets'and not valid(natives[ch]):c['unknown_events'].append(play);continue
    c['known_events']+=1
    if not valid(natives[ch])or ch=='rush_attempts'and lateral_bad:c['unknown_credit_events'].append(play)
    if valid(natives[ch]):c['credits'][natives[ch]]=c['credits'].get(natives[ch],0)+1
  events.append(dict(game_id=gid,play_id=play,offense=off,defense=defense,eligibility=elig,native_credits=natives,rush_lateral_or_unknown=lateral_bad,source_fields=dict(raw)))
 for group in groups.values():
  for c in group.values():
   c['event_count_exact']=bool(c['source_offense_rows']and not c['unknown_events'])
   c['native_credit_census_exact']=bool(c['event_count_exact']and not c['unknown_credit_events']and sum(c['credits'].values())==c['known_events'])
 return groups,events

def resolve_all_edges(alias_rows):
 f=defaultdict(set);rev=defaultdict(set)
 for r in alias_rows:f[r['source_key']].add(r['player_master_id']);rev[r['player_master_id']].add(r['source_key'])
 return {n:next(iter(ids))if len(ids)==1 and len(rev[next(iter(ids))])==1 else None for n,ids in f.items()}

def group_proof(candidates,weekly,budget_cell,channel,identities,positive_missing=()):
 """Fixed candidates unchanged. Event proof can fill only unknown zero labels."""
 full=budget_cell['native_credit_census_exact'];credits=budget_cell['credits'];labels=[];conflicts=[];unknown_positive=[]
 source_sum=0;source_unknown=0
 for n,r in weekly.items():
  v=r['counts'][channel]
  if v is None:source_unknown+=1
  else:
   source_sum+=v
   if v<credits.get(n,0)or full and v!=credits.get(n,0):conflicts.append(dict(native=n,weekly=v,event=credits.get(n,0)))
 inverse={pid:n for n,pid in identities.items()if pid is not None}
 for pid in positive_missing:
  n=inverse.get(pid)
  if n in weekly:continue
  if n is None or not full or credits.get(n,0)!=0:unknown_positive.append(dict(player_master_id=pid,native=n,reason='missing_positive_participant_not_proven_zero'))
 for n in sorted(candidates):
  v=weekly.get(n,{}).get('counts',{}).get(channel);basis='retained_weekly_count'
  if v is None:
   if full and credits.get(n,0)==0:v=0;basis='complete_same_source_native_credit_census_zero'
   else:basis='unknown_missing_weekly_or_positive_credit_without_weekly_label'
  labels.append(dict(native=n,player_master_id=identities.get(n),count=v,basis=basis))
 outside=[r['counts'][channel]for n,r in weekly.items()if n not in candidates];rest=sum(outside)if all(v is not None for v in outside)else None
 budget=source_sum if weekly and not source_unknown and not unknown_positive else None
 if budget is not None and full and budget!=budget_cell['known_events']:conflicts.append(dict(scope='budget',weekly=budget,event=budget_cell['known_events']))
 all_known=all(r['count']is not None for r in labels);identity=sum(r['count']for r in labels)+rest==budget if all_known and rest is not None and budget is not None else False
 native=bool(candidates and all_known and full and identity and not conflicts and not unknown_positive)
 return dict(candidate_count=len(candidates),candidate_labels=labels,source_budget=budget,known_source_sum=source_sum,unknown_source_rows=source_unknown,unknown_positive_participants=unknown_positive,outside_rest=rest,native_event_count=budget_cell['known_events'],event_count_exact=budget_cell['event_count_exact'],native_credit_census_exact=full,unknown_event_play_ids=budget_cell['unknown_events'],unknown_credit_play_ids=budget_cell['unknown_credit_events'],conflicts=conflicts,candidate_sum_plus_rest_matches_budget=identity,native_group_complete=native,canonical_group_complete=native and all(r['player_master_id']is not None for r in labels),source_log_only=True,independent_NFL_census='UNKNOWN')
