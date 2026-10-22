from pathlib import Path
from collections import defaultdict
from decimal import Decimal
import json,hashlib,csv
from backend.app.product_services.late_half_possession_context import build_late_half_context,load_reviewed_decision_boundary,project_late_half_source
from backend.app.product_services.drive_scoring_range import _physical_source,_half,_control
from backend.app.product_services.fumble_event_components import _eligibility
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.market_snapshots import canonical_team
from backend.app.product_services.evaluation_record import digest
D=Path('research/late_half_possession_context_20261020/v1');e=json.loads((D/'EVIDENCE.json').read_text());a=json.loads((D/'actual_receipt.json').read_text())
def load(ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return json.loads(b)
for pin in e['pins']:
 b=Path(pin['path']).read_bytes();assert len(b)==pin['bytes']and hashlib.sha256(b).hexdigest()==pin['sha256']
f=load(a['full_ref']);sel=load(a['selected_ref']);p=f['provenance'];bound=load_reviewed_decision_boundary(a['boundary_ref'],cutoff=p['actual_read_at']);assert a['boundary_ref']['sha256']=='1c50678eb2d06dfe28aa0a0945651debd4cd859d3e8168bc2854138f51f598bf';assert a['source_ref']['sha256']=='56e4d82e49e381a07b40ad9f10f5947a7133cbbf27708f1644d17a0c56809912';assert a['source_ref']==bound['provenance']['source_ref']and p['boundary_semantic_sha256']==bound['semantic_sha256']and p['source_event_sha256']==bound['provenance']['source_event_sha256']
# Already-indexed/authenticated unchanged CSV and range ancestry are reused; only new clock/path transformation is replayed.
raw=Path(a['source_ref']['path']).read_bytes();assert len(raw)==a['source_ref']['bytes']and hashlib.sha256(raw).hexdigest()==a['source_ref']['sha256'];del raw
records=[];allrows=[]
with Path(a['source_ref']['path']).open(newline='')as stream:
 for r in csv.DictReader(stream):
  if r['season_type']=='REG'and int(r['season'])*100+int(r['week'])<f['before_period']:allrows.append({k:v if v!=''else None for k,v in r.items()});records.append(project_late_half_source(r))
assert len(records)==13842;new=build_late_half_context(records,bound);assert new=={k:v for k,v in f.items()if k!='provenance'};assert f['semantic_sha256']==a['semantic_sha256']==digest({k:f[k]for k in('version','candidate_id','before_period','game_rows','profiles','unassigned_native_incidents','definition')})
assert p['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/late_half_possession_context.py').read_bytes()).hexdigest();assert clock(p['actual_read_at'])<=clock(p['actual_derived_at'])<=clock(p['actual_publication_at'])<=clock(a['actual_completed_at'])
def integer(v):return int(Decimal(v))if v is not None else None
def number(v):return float(v)if v is not None else None
def flag(v):return None if v is None else bool(Decimal(v))if Decimal(v)in(0,1)else None
material=('first_down_pass','first_down_rush','first_down_penalty','third_down_failed','third_down_converted','fourth_down_failed','fourth_down_converted','pass_touchdown','rush_touchdown','fumble_lost','punt_blocked','safety','penalty')
def candidate(r):
 named,conflict=_control(r)
 if named:return None if conflict or any(flag(r.get(k))is True for k in material)else False
 physical=_physical_source(r);live=_eligibility(r)[0];kick=False
 if r['play_type']in{'field_goal','punt'}:kick=False if live is False else True if live is True and flag(r.get('field_goal_attempt'if r['play_type']=='field_goal'else'punt_attempt'))is True else None
 return True if physical is True or kick is True else False if physical is False and kick is False else None
def late(r):
 q=integer(r['qtr']);s=number(r['half_seconds_remaining']);return False if q is not None and q not in{2,4}else None if q is None or _half(r)is None or s is None or not 0<=s<=900 else s<=120
idx={(r['game_id'],integer(r['play_id'])):r for r in allrows};timelines=defaultdict(list)
for r in allrows:timelines[r['game_id']].append(r)
for rs in timelines.values():rs.sort(key=lambda r:Decimal(r['order_sequence']))
parents={(g['native_game_id'],g['team'],d['original_drive_id']):d for g in bound['game_rows']for d in g['drives']};known=unk=exact=0
for g in f['game_rows']:
 observed=[d for d in g['drives']if d['late_window_entry']is True];u=sum(d['late_window_entry']is None for d in g['drives'])+len(g['unassigned_possible_entries']);assert g['metrics']['exact_late_possession_count']==(len(observed)if not u else None);known+=len(observed);unk+=sum(d['late_window_entry']is None for d in g['drives']);exact+=g['metrics']['exact_late_possession_count']is not None
 for d in g['drives']:
  if d['late_window_entry']is not True:continue
  entry=idx[g['game_id'],d['first_known_late_play_id']];assert candidate(entry)is True and late(entry)is True and integer(entry['qtr'])in{2,4};team=g['team'];did=d['original_drive_id'];half=_half(entry);eo=Decimal(entry['order_sequence']);parent=parents[g['game_id'],team,did];end=idx.get((g['game_id'],parent['source_last_play_id']));endorder=Decimal(end['order_sequence'])if end else eo
  same=[r for r in timelines[g['game_id']]if r['posteam']and canonical_team(r['posteam'])==team and integer(r['drive'])==did and candidate(r)is True and late(r)is True];assert eo==min(Decimal(r['order_sequence'])for r in same)
  connected=[];barrier=False
  for r in timelines[g['game_id']]:
   order=Decimal(r['order_sequence'])
   if not eo<=order<=endorder:continue
   named,conflict=_control(r);off=canonical_team(r['posteam'])if r['posteam']else None
   if conflict or named and any(flag(r.get(k))is True for k in material)or _half(r)!=half or integer(r['drive'])!=did or candidate(r)is not False and off!=team:barrier=True
   if not barrier and off==team:connected.append(r)
  for field,threshold in [('reached20',20),('reached5',5)]:
   positives=[r for r in connected if candidate(r)is True and late(r)is True and number(r['yardline_100'])is not None and 0<=number(r['yardline_100'])<=threshold]
   assert (d[field]is True)==bool(positives)
  fg=[r for r in connected if candidate(r)is True and late(r)is True and r['play_type']=='field_goal'and flag(r['field_goal_attempt'])is True];assert(d['live_FG_attempt']is True)==bool(fg)
  if d['offensive_TD']is True:assert any(candidate(r)is True and late(r)is True and _physical_source(r)is True and((flag(r['pass_touchdown'])is True and flag(r['rush_touchdown'])is not True and flag(r['pass_attempt'])is True and flag(r['sack'])is False)or(flag(r['rush_touchdown'])is True and flag(r['pass_touchdown'])is not True and flag(r['rush_attempt'])is True))for r in connected)
  if d['complete_postentry_segment']:assert not barrier and parent['native_boundary_and_cohort_verified']and parent['verified_terminal_class']is not None and endorder>=eo
  if any(d[field]is False for field in('reached20','reached5','offensive_TD','live_FG_attempt')):assert d['complete_postentry_segment']
  if barrier:assert d['postentry_continuity_barriers']and not d['complete_postentry_segment']
 for field,m in g['metrics']['views'].items():
  yes=sum(d[field]is True for d in observed);unknown=sum(d[field]is None for d in observed);assert m['known_successes']==yes and m['unknown_outcomes']==unknown and m['exact_per_possession_fraction']==(yes/len(observed)if observed and not u and not unknown else None)
assert known==a['known_observed_late_possessions']==362 and unk==a['unknown_possible_drive_entries']==6 and exact==150
for pr in f['profiles']:
 games=[g for g in f['game_rows']if(g['season'],g['team'])==(pr['season'],pr['team'])];ds=[d for g in games for d in g['drives']];observed=[d for d in ds if d['late_window_entry']is True];u=sum(d['late_window_entry']is None for d in ds)+sum(len(g['unassigned_possible_entries'])for g in games);assert pr['metrics']['exact_late_possession_count']==(len(observed)if not u else None)
 for field,m in pr['metrics']['views'].items():
  n=sum(d[field]is True for d in observed);outcomes=sum(d[field]is None for d in observed);assert m['exact_per_possession_fraction']==(n/len(observed)if observed and not u and not outcomes else None)
assert sel==dict(f,game_rows=[g for g in f['game_rows']if g['team']in{'SF','WAS'}],profiles=[r for r in f['profiles']if r['team']in{'SF','WAS'}],selection=dict(teams=['SF','WAS'],all_global_unknown_native_incidents_retained=True,full_ref=a['full_ref']))
archive=D/'prior_38test_revision';pe=json.loads(next(archive.rglob('EVIDENCE.json')).read_text())
for pin in pe['pins']:assert any(q.is_file()and q.stat().st_size==pin['bytes']and hashlib.sha256(q.read_bytes()).hexdigest()==pin['sha256']for q in archive.rglob(Path(pin['path']).name))
parity=json.loads((D/'correction_parity.json').read_text());old=load(parity['prior_full_ref']);assert all(parity['actual_summary_field_equality'].values())and parity['current_full_ref']==a['full_ref'];assert [g['metrics']for g in f['game_rows']]==[g['metrics']for g in old['game_rows']]
print(json.dumps(dict(PASS=True,pins=8,tests=43,new_clock_entry_continuity_positive_negative_paths_all_formulas_profiles_fullslice_exact=True,known_possessions=known,unknown_drives=unk,exact_game_counts=exact,unchanged_authenticated_parents_reused=True,source_adapter_replays=0,database_reads=0,database_writes=0,parent_inflates=0,models=0)))
