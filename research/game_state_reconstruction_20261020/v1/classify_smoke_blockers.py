"""Single <=5s inspection of saved projections/index/policy; no reconstruction."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,UTC
import json,gzip,hashlib,signal,time

OUT=Path('research/game_state_reconstruction_20261020/v1')
PILOT=Path('research/game_progression_pilot_20261020/v1')
def n(v):
 try:return float(v) if v not in(None,'') else None
 except(TypeError,ValueError):return None
def flag(v):
 x=n(v);return bool(x)if x in(0,1)else None
def read(ref):
 b=Path(ref['path']).read_bytes()
 if hashlib.sha256(b).hexdigest()!=ref['sha256']:raise ValueError('Frozen ref changed')
 return json.loads(gzip.decompress(b)if ref.get('encoding')=='gzip_json_v1'else b)
def brief(raw,ordinal=None):
 fields=('game_id','play_id','order_sequence','drive','play_type','play_type_nfl','qtr','game_half',
 'quarter_seconds_remaining','half_seconds_remaining','game_seconds_remaining','posteam','defteam','yardline_100',
 'posteam_score','defteam_score','posteam_score_post','defteam_score_post','total_home_score','total_away_score',
 'pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','kickoff_attempt','touchdown','fumble','penalty','replay_or_challenge','quarter_end')
 return dict(source_ordinal=ordinal,fields={k:raw.get(k)for k in fields})
def main():
 started=time.monotonic();result=dict(version='saved_smoke_source_blocker_classification_v1',recorded_at=datetime.now(UTC).isoformat(),status='RUNNING',raw_source_reads=0,recomposes=0,fits=0,model_changes=0)
 def cap(*_):raise TimeoutError('Absolute5second cachedclassification cap')
 old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,5)
 try:
  receipt=json.loads((OUT/'CACHED_RECOMPOSE_RECEIPT.json').read_text());integrated=json.loads((PILOT/'INTEGRATED_MANIFEST.json').read_text())
  train=next(x for x in receipt['outputs']if x['season']==2023);current=next(x for x in receipt['outputs']if x['season']==2026)
  projection=read(train['projection_ref']);columns=projection['columns'];values=projection['rows'];position={k:i for i,k in enumerate(columns)}
  raw=lambda ordinal:dict(zip(columns,values[ordinal]))
  index=read(train['reconstruction_ref']);policy=read(integrated['policy_ref']);openings=read(train['openings_ref'])['rows']
  # Exact source block ordinal grouping, using only the saved native index and marker proofs.
  groups={};row_index={};by_game=defaultdict(list)
  for game in index['games']:
   runs=[];split=False
   for item in game['rows']:
    row_index[(game['game_id'],item['play_id'])]=item;by_game[game['game_id']].append(item)
    if item.get('typed_admin_marker',{}).get('certified'):split=True;continue
    if split or not runs or item['original_drive'] is None or runs[-1][0]['original_drive']!=item['original_drive']:runs.append([])
    runs[-1].append(item);split=False
   for ordinal,run in enumerate(runs):groups[game['game_id']+'|'+str(ordinal)]=run
  threats=[];counts=Counter();reasons=Counter()
  material=('pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','qb_kneel','qb_spike','touchdown','fumble','penalty','kickoff_attempt','punt_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt')
  for threat in policy['unscopable_threats']:
   bid=threat.get('block_id');run=groups.get(bid,[]);rows=[raw(x['source_ordinal'])for x in run];first=rows[0]if rows else{}
   q=n(first.get('qtr'));kind=first.get('play_type_nfl');positive=[k for r in rows for k in material if flag(r.get(k))is True]
   if q is not None and q>=5:category='EXPLICIT_OVERTIME_OUTSIDE_REGULATION_CANDIDATE'
   elif rows and kind in{'END_QUARTER','END_GAME'}and q in(1,3,4)and not positive:category='REMAINING_TYPED_ADMIN_NULL_SCHEMA_CANDIDATE'
   elif positive:category='POSSIBLE_OR_POSITIVE_ACTION_NEEDS_SIDE_FIELD_PROOF'
   else:category='UNRESOLVED_START_SIDE_FIELD_OR_SOURCE_SCOPE'
   counts[category]+=1;reasons[threat['reason']]+=1
   threats.append(dict(block_id=bid,reason=threat['reason'],category=category,native_classes=dict(Counter(r.get('play_type_nfl')or'NULL'for r in rows)),row_count=len(rows),positive_material=sorted(set(positive)),representative=brief(first,run[0]['source_ordinal'])if rows else None,source_row_barriers=sorted({r for x in run for r in x['barriers']})))
  result['unscopable_policy_threats']=dict(total=len(threats),categories=dict(counts),policy_reason_counts=dict(reasons),native_start_class_counts=dict(Counter(t['representative']['fields']['play_type_nfl']if t['representative']else'NO_SOURCE_GROUP'for t in threats)),rows=threats)
  pair=defaultdict(list)
  for o in openings:pair[o['game_id']].append(o)
  failed=[]
  for gid,halves in pair.items():
   if len(halves)==2 and all(h['certified']for h in halves):continue
   details=[]
   for o in halves:
    if o['certified']:continue
    key=(gid,o['row_id']);item=row_index.get(key);rr=raw(item['source_ordinal'])if item else{}
    end_candidates=[x for x in by_game[gid]if raw(x['source_ordinal']).get('play_type_nfl')=='END_QUARTER'and n(raw(x['source_ordinal']).get('qtr'))==2]
    marker=end_candidates[-1]if end_candidates else None
    details.append(dict(half=o['source_half'],reasons=o['barriers'],opening=brief(rr,item['source_ordinal'])if item else None,halftime_marker=brief(raw(marker['source_ordinal']),marker['source_ordinal'])if marker else None))
   failed.append(dict(game_id=gid,failed_halves=details))
  result['uncertified_opening_pairs']=dict(total=len(failed),reason_counts=dict(Counter(r for x in failed for h in x['failed_halves']for r in h['reasons'])),games=failed)
  # Kickoff prefix structural vs remaining independent blockers; no block is repaired.
  kicks=[b for b in policy['blocks']if b['start']['phase']=='kickoff'];structural={'unproven_offensive_possession_start','unknown_runtime_production_vector','Unknown explicit production credits'}
  kickcases=[];other_counts=Counter();physical_seen=Counter()
  for b in kicks:
   other=sorted(set(b['source_barriers'])-structural);other_counts.update(other)
   run=groups[b['block_id']];prefix=[];first_physical=None
   for item in run:
    rr=raw(item['source_ordinal'])
    if any(flag(rr.get(k))is True for k in('pass_attempt','rush_attempt','sack'))and flag(rr.get('two_point_attempt'))is not True and rr.get('play_type')!='no_play':first_physical=item;break
    prefix.append(item)
   physical_seen['first_physical_found'if first_physical else'zero_or_unknown_physical_group']+=1
   if not other:
    first=raw(run[0]['source_ordinal']);physical=raw(first_physical['source_ordinal'])if first_physical else{}
    kickcases.append(dict(block_id=b['block_id'],prefix_rows=len(prefix),first_physical_play_id=first_physical['play_id']if first_physical else None,source_start_possession=first.get('posteam'),first_physical_possession=physical.get('posteam'),source_first_link=first.get('drive_play_id_started'),source_first_id=first.get('play_id')))
  result['kickoff_prefixed_blocks']=dict(total=len(kicks),certified=sum(b['certified']for b in kicks),has_structural_possession_guard=sum('unproven_offensive_possession_start'in b['source_barriers']for b in kicks),otherwise_no_recorded_independent_barrier=len(kickcases),other_barriers=dict(other_counts),physical_prefix_counts=dict(physical_seen),otherwise_known_candidates=kickcases,
    exact_future_proof_requirements=['Source first-play link must be the kickoff and all original-drive rows/order retained, rather than ignoring prefix.', 'Every kickoff/return/penalty/control prefix row must have known phase, native receiving/possession side, clock, native score/points, zero official P/R/T and source proven production. Fumble/lateral/replay/unknown possible action remains a barrier.', 'First eligible physical offensive snap must have proven same incoming native offense and original-drive membership; no earlier possible physical opportunity. Credit exactly one original offensive possession on this first physical snap, zero on prefix. Pure kick/returnTD group without such snap stays zero only under complete prefix proof.', 'Preserve exact source start kickoff field/phase, return, signed points and all elapsed segments; do not borrow first offensive LOS for kickoff support. Source role/team meaning must be verified, not inferred from usage.'])
  # Selected 2026 regulation labels: evidence only, not admitted scores or metrics.
  selected=json.loads((PILOT/'SMOKE_GAME_SELECTION.json').read_text())['selected'];wanted={g['game_id']for g in selected}
  p26=read(current['projection_ref']);c26=p26['columns'];gididx=c26.index('game_id');raw26=defaultdict(list)
  for ordinal,vals in enumerate(p26['rows']):
   if vals[gididx]in wanted:raw26[vals[gididx]].append((ordinal,dict(zip(c26,vals))))
  cases=[]
  for selected_game in selected:
   gid=selected_game['game_id'];rr=raw26[gid];q4=[x for x in rr if n(x[1].get('qtr'))==4]
   markers=[x for x in q4 if x[1].get('play_type_nfl')in{'END_QUARTER','END_GAME'}and n(x[1].get('half_seconds_remaining'))==0]
   live=[x for x in q4 if any(flag(x[1].get(k))is True for k in('pass_attempt','rush_attempt','sack','kickoff_attempt','punt_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt'))]
   last=live[-1]if live else None;scores=None
   if last:
    r=last[1];off=r.get('posteam');home=r.get('home_team');away=r.get('away_team');p=n(r.get('posteam_score_post'));d=n(r.get('defteam_score_post'))
    if off in(home,away)and p is not None and d is not None:scores=[p,d]if off==home else[d,p]
   cases.append(dict(game_id=gid,week=selected_game['week'],source_rows=len(rr),q4_rows=len(q4),q4_zero_native_markers=[brief(x[1],x[0])for x in markers],last_live_postscore_evidence=brief(last[1],last[0])if last else None,last_live_postscore_home_away=scores,
    any_OT_rows=any(n(x[1].get('qtr'))is not None and n(x[1].get('qtr'))>=5 for x in rr),
    marker_totals_match_last_live_POST=bool(scores is not None and markers and all([n(m[1].get('total_home_score')),n(m[1].get('total_away_score'))]==scores for m in markers)),
    status='UNADMITTED_REGULATION_TRUTH_CANDIDATE_EVIDENCE_ONLY'if markers and scores is not None else'GENUINE_MISSING_Q4_MARKER_OR_POSTSCORE_EVIDENCE'))
  result['selected_2026_regulation_evidence']=cases
  result['refs']=dict(train_projection=train['projection_ref'],train_index=train['reconstruction_ref'],train_openings=train['openings_ref'],policy=integrated['policy_ref'],current_projection=current['projection_ref'])
  result['status']='COMPLETED_CLASSIFICATION_ONLY_NO_REPAIR_OR_METRICS'
 except Exception as exc:result.update(status='FAILED_BOUNDED_NO_AUTORETRY',error_type=type(exc).__name__,error=str(exc))
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old);result['elapsed_seconds']=time.monotonic()-started
  (OUT/'SMOKE_BLOCKER_CLASSIFICATION.json').write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps({k:result[k]for k in('status','elapsed_seconds')}))
 return 0 if result['status'].startswith('COMPLETED')else 1
if __name__=='__main__':raise SystemExit(main())
