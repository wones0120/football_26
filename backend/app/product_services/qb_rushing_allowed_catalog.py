"""Official QB rushing production allowed, native weekly/schedule grain."""
from collections import defaultdict
from copy import deepcopy
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from .schedule_context_features import VERSION as SCHEDULE_VERSION
from .evaluation_record import digest
from .market_snapshots import canonical_team
VERSION='qb_rushing_allowed_catalog_v1'
def build_qb_rushing_allowed(weekly,schedule,*,before_period,excluded_source_rows=()):
 if weekly.get('version')!=WEEKLY_VERSION or weekly.get('before_period')!=before_period or schedule.get('version')!=SCHEDULE_VERSION or any(s.get('pregame_serving_eligible') is not False for s in (weekly,schedule)):raise ValueError('Matched retrospective weekly/schedule sources required')
 if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=18:raise ValueError('Explicit prior REG period required')
 games={}
 for s in schedule['game_rows']:
  if s['game_type']!='REG' or s['season']*100+s['week']>=before_period:continue
  for team,opponent in ((s['home_team'],s['away_team']),(s['away_team'],s['home_team'])):
   key=(s['season'],s['week'],canonical_team(team))
   if key in games:raise ValueError('Ambiguous native team/week schedule')
   games[key]=dict(game_id=s['game_id'],offense_team=canonical_team(team),defense_team=canonical_team(opponent))
 groups=defaultdict(list);unbound=[];period_unknown=defaultdict(list)
 for row in weekly['rows']:
  period=row['season']*100+row['week'];team=row['team'];m=row['metrics']['G07-M01'];sourceQB=row['QB_scope_source_proven']
  if period>=before_period or row['season_type']!='REG':raise ValueError('Nonprior weekly evidence')
  if sourceQB and row['source_position']!='QB':raise ValueError('Contradictory native QB role')
  unknown_role=row['source_position'] in (None,'') or 'QB_role' in row['source_quality']
  if not sourceQB and not unknown_role:continue
  # A proved zero official production cannot change the QB total, regardless of unknown position.
  if not sourceQB and m['numerator']==0 and m['denominator']==0:continue
  key=(row['season'],row['week'],canonical_team(team)) if team else None
  if key not in games:
   item=dict(period=period,native_player_id=row['source_player_id'],reason='Unknown team or unavailable unique native schedule; no guessed opponent');unbound.append(item)
   if team is None:period_unknown[period].append(item)
   continue
  if row['native_game_id'] not in (None,'',games[key]['game_id']):raise ValueError('Supplied weekly native game contradicts schedule')
  groups[key].append(dict(native_player_id=row['source_player_id'],player_master_id=row['player_master_id'],sourceQB=sourceQB,role_unknown=unknown_role,yards=m['numerator'],carries=m['denominator']))
 # Quarantined malformed-native source rows are not silently erased from possible QB budgets.
 for r in excluded_source_rows:
  if r.get('position') not in (None,'','QB'):continue
  period=r['season']*100+r['week']
  if period>=before_period:raise ValueError('Excluded-source period is not prior')
  try:team=canonical_team(r.get('team'))
  except ValueError:team=None
  key=(r['season'],r['week'],team);item=dict(native_player_id=r.get('source_player_id'),player_master_id=None,sourceQB=False,role_unknown=True,yards=None,carries=None)
  if key in games:groups[key].append(item)
  else:period_unknown[period].append(item)
 rows=[]
 for key,actors in sorted(groups.items()):
  known=[a for a in actors if a['sourceQB']];period=key[0]*100+key[1]
  uncertain=sum(a['role_unknown'] or a['player_master_id'] is None for a in actors)+len(period_unknown[period])
  yards=sum(a['yards'] for a in known if a['yards'] is not None);carries=sum(a['carries'] for a in known if a['carries'] is not None)
  missing_yards=sum(a['yards'] is None for a in known);missing_carries=sum(a['carries'] is None for a in known)
  y=yards if known and not(uncertain or missing_yards) else None;c=carries if known and not(uncertain or missing_carries) else None
  rows.append(dict(**games[key],season=key[0],week=key[1],metrics={'G15-M10':dict(value=y,unit='signed_official_QB_rushing_yards_allowed',exact_total_yards=y,exact_official_carries=c,yards_per_official_carry=y/c if y is not None and c is not None and c>0 else None,known_source_QB_yards_sum=yards,known_source_QB_carries_sum=carries,observed_native_QB_rows=len(known),unknown_identity_or_role_rows=uncertain,unknown_yards_rows=missing_yards,unknown_carry_rows=missing_carries)},native_QB_evidence=actors))
 basis=dict(version=VERSION,before_period=before_period,definition='Sum signed official rushing yards and carries of explicitly source-proven QBs on the scheduled opposing offense; includes kneels/scrambles, no absent-player zeros',game_rows=rows,unbound_rows=unbound,unknown_team_or_schedule_role_evidence=dict(period_unknown))
 return dict(**basis,semantic_sha256=digest(basis),source_semantic_hashes=dict(weekly=weekly['semantic_sha256'],schedule=schedule['semantic_sha256']),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,provenance=dict(weekly=deepcopy(weekly['provenance']),schedule=deepcopy(schedule['provenance'])),limitations=['Revised full-source weekly cohort, not independently verified complete game participation','Unknown native/canonical identity, position, yardage, carry exposure or opponent binding stays explicit','Native schedule joins use team/season/week only; no raw player names','Signed official totals include kneels/scrambles; previous nonkneel-only rate remains a separate variant'],consumer_status='Features-only; models/optimizer pending')
