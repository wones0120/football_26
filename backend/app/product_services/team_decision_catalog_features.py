"""Declared called-pass decision rates from verified descriptive source context."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import hashlib
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .offensive_environment_catalog import _count,load_reviewed_environment_context

VERSION='team_decision_catalog_features_v1'
SUBSETS={'G02-M01':'all eligible calls','G02-M02':'qtr1..3 and abs(preplay score differential)<=7',
 'G02-M04':'preplay down1..2','G02-M05':'preplay down1','G02-M06':'preplay down3',
 'G02-M07':'preplay yardline_100<=20','G02-M08':'preplay yardline_100<=5',
 'G02-M09':'preplay score differential<0','G02-M10':'preplay score differential>0'}
DEFINITION='nonspike reported dropback / (nonspike reported dropback + designed nonkneel rush); scramble is dropback once, not an extra rush call'

def _measure(raw):
 den=_count(raw['eligible_events']);known=_count(raw['known_outcome_events']);missing=_count(raw['unknown_outcome_events']);uncertain=_count(raw['unknown_eligibility_events'])
 # Reviewed producer represents an empty KNOWN sample with null sum, not an observed zero outcome.
 n=0 if known==0 and raw['observed_outcome_sum'] is None else _count(raw['observed_outcome_sum'])
 if known+missing!=den or n>known:raise ValueError('Called-pass known outcome/exposure contradiction')
 return dict(value=n/den if den and not(missing or uncertain) else None,numerator=n,known_denominator=den,
  known_outcome_events=known,unknown_outcome_events=missing,unknown_eligibility_events=uncertain,
  known_sample_fraction=n/known if known else None,known_sample_sum_basis='empty_known_sample' if known==0 else 'measured_known_sample',unit='called_pass_fraction')

def build_team_decision_catalog(context,*,before_period,last_n=8):
 if context.get('version')!='environment_context_evidence_v1' or context.get('before_period')!=before_period or context.get('forecast') is not None:raise ValueError('Matched descriptive source context required')
 if type(before_period)is not int or not 200001<=before_period or not 1<=before_period%100<=18 or type(last_n)is not int or not 1<=last_n<=32:raise ValueError('Explicit prior REG scope/window required')
 rows=[];seen=set();teams=defaultdict(list)
 for src in context['game_rows']:
  team=canonical_team(src['team']);gid=src['game_id'];parts=gid.split('_');season=src['season'];week=src['week'];period=season*100+week
  if len(parts)!=4 or parts[:2]!=[str(season),f'{week:02d}'] or team not in {canonical_team(t) for t in parts[2:]} or not 1<=week<=18 or period>=before_period:raise ValueError('Strict prior native team/game scope required')
  if (team,gid) in seen:raise ValueError('Duplicate native team/game')
  seen.add((team,gid));metrics={m:_measure(src['metrics'][m]) for m in SUBSETS}
  base=metrics['G02-M01']
  for mid,m in metrics.items():
   if m['known_denominator']>base['known_denominator'] or m['numerator']>base['numerator']:raise ValueError('Subset exceeds all-call denominator/numerator')
  row=dict(team=team,game_id=gid,season=season,week=week,metrics=metrics);rows.append(row)
  if season==before_period//100:teams[team].append(row)
 rows.sort(key=lambda r:(r['season'],r['week'],r['game_id'],r['team']));windows=[]
 for team,group in sorted(teams.items()):
  group=sorted(group,key=lambda r:(r['week'],r['game_id']))[-last_n:]
  if len({r['week'] for r in group})!=len(group):raise ValueError('Ambiguous same-team period')
  metrics={}
  for mid in SUBSETS:
   metrics[mid]=_measure(dict(observed_outcome_sum=sum(r['metrics'][mid]['numerator'] for r in group),eligible_events=sum(r['metrics'][mid]['known_denominator'] for r in group),known_outcome_events=sum(r['metrics'][mid]['known_outcome_events'] for r in group),unknown_outcome_events=sum(r['metrics'][mid]['unknown_outcome_events'] for r in group),unknown_eligibility_events=sum(r['metrics'][mid]['unknown_eligibility_events'] for r in group)))
  windows.append(dict(team=team,observed_game_ids=[r['game_id'] for r in group],metrics=metrics))
 basis=dict(version=VERSION,before_period=before_period,last_n_same_season_observed_games=last_n,definition=DEFINITION,subsets=SUBSETS,game_rows=rows,team_windows=windows)
 return dict(**basis,semantic_sha256=digest(basis),source_context_semantic_sha256=context['semantic_measurements_sha256'],
  evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
  limitations=['Declared called-pass decision definition; not official passing attempts/(passing+rushing attempts)','Observed prior logs not independently verified complete games; absent logs never become zero','Known-sample fraction is separate from exact all-eligible rate; unknown eligibility/outcomes mask exact rates','G02-M03 vendor expected-pass residual remains separate partial measurement with unknown vendor model chronology'],
  consumer_status='Feature-only; models/optimizer pending')

def read_team_decision_catalog(context_ref,snapshot,*,actual_read_at,context_directory=None,parent_directory=None):
 intake=load_reviewed_environment_context(context_ref,snapshot,actual_read_at=actual_read_at,context_directory=context_directory,parent_directory=parent_directory)
 result=build_team_decision_catalog(intake['context'],before_period=intake['context']['before_period'])
 result['provenance']=deepcopy(intake['provenance']);result['provenance']['producer_code_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 return result
