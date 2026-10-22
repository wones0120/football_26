"""Declared observed defensive catalog rates; no causal grades or forecast."""
from copy import deepcopy
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .defense_context_evidence import DEFINITIONS as BASE
from .defense_context_extensions import DEFINITIONS as EXT
VERSION='defensive_catalog_features_v1'
BASE_IDS=('G14-M07','G14-M09','G15-M01','G15-M02','G15-M03','G15-M04')
EXT_IDS=('G14-M06','G14-M08','G15-M08')
DEFINITIONS={mid:deepcopy((BASE if mid in BASE_IDS else EXT)[mid]) for mid in (*BASE_IDS,*EXT_IDS)}

def _rate(src,mid):
 m=deepcopy(src)
 for key in ('eligible_events','known_outcome_events','unknown_outcome_events','unknown_eligibility_events'):
  n=m[key]
  if type(n) not in {int,float} or not math.isfinite(n) or n<0 or n!=int(n):raise ValueError('Nonnegative source exposure required')
 if m['known_outcome_events']+m['unknown_outcome_events']!=m['eligible_events']:raise ValueError('Source exposure partition differs')
 total=m['observed_outcome_sum'];known=m['known_outcome_events'];den=m['eligible_events']
 if total is not None and (type(total) not in {int,float} or not math.isfinite(total)):raise ValueError('Finite source outcome required')
 if mid not in {'G14-M06','G14-M08','G15-M02'} and total is not None and not 0<=total<=known:raise ValueError('Binary source outcome exceeds known exposure')
 if mid=='G14-M06' and total is not None and not -100*known<=total<=100*known:raise ValueError('CPOE percentage-point source bounds differ')
 value=total/den if total is not None and den and not(m['unknown_eligibility_events'] or m['unknown_outcome_events']) else None
 if value!=m['all_eligible_mean']:raise ValueError('Source all-eligible rate differs')
 m.update(value=value,known_sample_fraction_or_mean=m['observed_known_mean'])
 if mid in {'G14-M08','G15-M02'}:
  exact_total=(total if total is not None else 0 if den==0 and known==0 else None) if not(m['unknown_eligibility_events'] or m['unknown_outcome_events']) else None
  m.update(exact_within_log_total=exact_total,catalog_value=exact_total,catalog_unit='YAC_yards' if mid=='G14-M08' else 'expected_points',rate_value=value,rate_unit='yards_per_completion' if mid=='G14-M08' else 'provider_expected_points_per_rush')
 return m

def build_defensive_catalog(base,extensions,*,before_period,last_n=8,yac_lateral_evidence=None):
 if base.get('version')!='defense_context_evidence_v1' or extensions.get('version')!='defense_context_extensions_v1' or any(s.get('before_period')!=before_period for s in (base,extensions)):raise ValueError('Matched defense components required')
 if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=18 or type(last_n)is not int or not 1<=last_n<=32:raise ValueError('Prior REG scope/window required')
 for source,ids in ((base,BASE_IDS),(extensions,EXT_IDS)):
  for mid in ids:
   if source['definitions'][mid]!=DEFINITIONS[mid]:raise ValueError('Reviewed defensive metric definition differs')
 for field in ('snapshot_id','content_sha256'):
  if not base['provenance']['source'].get(field) or base['provenance']['source'][field]!=extensions['provenance']['source'].get(field):raise ValueError('Defense components differ in authenticated source')
 if base['provenance']['event_receipt_sha256']!=extensions['provenance']['event_receipt_sha256']:raise ValueError('Defense event ancestry differs')
 rows={};windows=[]
 for source,ids in ((base,BASE_IDS),(extensions,EXT_IDS)):
  seen=set()
  for src in source['game_rows']:
   gid=src['game_id'];team=canonical_team(src['defense_team']);offense=canonical_team(src['offense_team']);parts=gid.split('_')
   if len(parts)!=4 or {team,offense}!={canonical_team(t) for t in parts[2:]} or team==offense or not 1<=int(parts[1])<=18 or int(parts[0])*100+int(parts[1])>=before_period:raise ValueError('Prior native defense/offense game scope required')
   key=(gid,team)
   if key in seen:raise ValueError('Duplicate native defense game')
   seen.add(key);row=rows.setdefault(key,dict(game_id=gid,defense_team=team,offense_team=offense,metrics={}))
   if row['offense_team']!=offense:raise ValueError('Defense opponent differs')
   row['metrics'].update({mid:_rate(src['metrics'][mid],mid) for mid in ids})
 for row in rows.values():
  if set(row['metrics'])!=set(DEFINITIONS):raise ValueError('Defensive component game coverage mismatch; missing rows are not zero')
 # Initial-catcher YAC is not full-defense YAC on lateral completions.
 proof={(r['game_id'],canonical_team(r['defense_team'])):deepcopy(r) for r in (yac_lateral_evidence or [])}
 if len(proof)!=len(yac_lateral_evidence or []):raise ValueError('Duplicate YAC lateral proof scope')
 for key,row in rows.items():
  m=row['metrics']['G14-M08'];p=proof.get(key) or (dict(game_id=key[0],defense_team=key[1],eligible_completed_passes=0,proven_no_lateral=0,known_lateral=0,unknown_lateral=0) if m['eligible_events']==0 else None);valid=p is not None and p.get('eligible_completed_passes')==m['eligible_events'] and p.get('proven_no_lateral',0)+p.get('known_lateral',0)+p.get('unknown_lateral',0)==m['eligible_events']
  m.update(initial_catcher_yac_sum=m['observed_outcome_sum'],initial_catcher_yac_per_completion=m['value'],lateral_coverage=p if valid else dict(status='missing_or_mismatched_native_completion_proof'))
  if not valid or p.get('known_lateral',0) or p.get('unknown_lateral',0):m['exact_within_log_total']=None;m['catalog_value']=None
 teams=sorted({r['defense_team'] for r in rows.values()})
 for team in teams:
  group=sorted([r for r in rows.values() if r['defense_team']==team and int(r['game_id'].split('_')[0])==before_period//100],key=lambda r:r['game_id'])[-last_n:]
  if not group:continue
  if len({r['game_id'].split('_')[1] for r in group})!=len(group):raise ValueError('Ambiguous defense period')
  metrics={}
  for mid in DEFINITIONS:
   totals={k:sum(r['metrics'][mid][k] for r in group) for k in ('eligible_events','known_outcome_events','unknown_outcome_events','unknown_eligibility_events')};total=sum(r['metrics'][mid]['observed_outcome_sum'] or 0 for r in group);known=totals['known_outcome_events']
   totals.update(observed_outcome_sum=total if known else None,observed_known_mean=total/known if known else None,all_eligible_mean=total/known if known and not(totals['unknown_eligibility_events'] or totals['unknown_outcome_events']) else None);metrics[mid]=_rate(totals,mid)

  ym=metrics['G14-M08'];ym['initial_catcher_yac_sum']=ym['observed_outcome_sum'];ym['initial_catcher_yac_per_completion']=ym['value'];ym['lateral_coverage']=[r['metrics']['G14-M08']['lateral_coverage'] for r in group]
  if any(r['metrics']['G14-M08']['catalog_value'] is None for r in group):ym['exact_within_log_total']=None;ym['catalog_value']=None
  windows.append(dict(defense_team=team,observed_game_ids=[r['game_id'] for r in group],metrics=metrics))
 basis=dict(version=VERSION,before_period=before_period,last_n_observed_same_season_games=last_n,definitions=DEFINITIONS,game_rows=sorted(rows.values(),key=lambda r:(r['game_id'],r['defense_team'])),team_windows=windows)
 return dict(**basis,semantic_sha256=digest(basis),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,source_semantic_hashes=[base['semantic_measurements_sha256'],extensions['semantic_measurements_sha256']],limitations=['Observed prior logs, not verified complete games; missing defense identity is excluded and remains original source quality evidence','Nonspike pass attempts differ from nonspike dropbacks including sacks/scrambles; nonkneel rushing includes scrambles','Known-outcome denominator and unknown exposure are explicit; no unweighted game-rate averaging','Provider EPA/CPOE derived models have unknown original model chronology; no pressure/contact/win-rate proxy'],provenance=dict(original_base=deepcopy(base['provenance']),original_extensions=deepcopy(extensions['provenance'])),consumer_status='Features-only; models/optimizer pending')


def measure_yac_lateral_coverage(native_rows,*,before_period):
 """Native completion/lateral flags; caller verifies immutable CSV bytes."""
 from .defense_context_evidence import _number
 grouped={};seen=set()
 for r in native_rows:
  if r.get('season_type')!='REG':continue
  season=_number(r.get('season'));week=_number(r.get('week'))
  if season is None or week is None or season*100+week>=before_period:continue
  flag=lambda k:_number(r.get(k))
  if not(flag('pass_attempt')==1 and flag('complete_pass')==1 and flag('qb_spike')==0 and flag('two_point_attempt')==0) or r.get('play_type')=='no_play':continue
  gid=r['game_id'];team=canonical_team(r['defteam']);parts=gid.split('_')
  if len(parts)!=4 or parts[:2]!=[str(int(season)),f'{int(week):02d}'] or team not in {canonical_team(t) for t in parts[2:]}:raise ValueError('Lateral proof native game scope differs')
  play=_number(r.get('play_id'))
  if play is None or int(play)!=play:raise ValueError('Integral native lateral play key required')
  event=(gid,str(int(play)))
  if event in seen:raise ValueError('Duplicate native lateral event')
  seen.add(event);p=grouped.setdefault((gid,team),dict(game_id=gid,defense_team=team,eligible_completed_passes=0,proven_no_lateral=0,known_lateral=0,unknown_lateral=0));p['eligible_completed_passes']+=1
  lateral=flag('lateral_reception');native=r.get('lateral_receiver_player_id');yards=flag('lateral_receiving_yards')
  if lateral==1 or native not in (None,'') or yards not in (None,0):p['known_lateral']+=1
  elif lateral==0:p['proven_no_lateral']+=1
  else:p['unknown_lateral']+=1
 return [p for _,p in sorted(grouped.items())]
