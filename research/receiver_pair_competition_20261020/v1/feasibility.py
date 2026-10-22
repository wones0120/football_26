"""Bounded immutable-parent coverage inspection; no feature/catalog promotion."""
from pathlib import Path
from datetime import datetime,UTC
from collections import defaultdict,Counter
import hashlib,json,time,gc,os
root=Path('research/receiver_pair_competition_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
receipt=json.loads(Path('research/coverage_receiver_performance_20261020/v1/receipt.json').read_text());assert receipt['review_status']=='High_FINAL_PASS_feature_only'
actual=json.loads(Path('research/coverage_receiver_performance_20261020/v1/actual_receipt.json').read_text());results=[]
for item in actual['outputs']:
 ref=item['native_ref'];p=Path(ref['path']);raw=p.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];block=json.loads(raw);del raw
 events=defaultdict(list)
 for e in block['event_basis']:
  if e['offense']is not None:events[(e['game_id'],e['offense'])].append(e)
  else:
   for team in e['game_id'].split('_')[2:]:events[(e['game_id'],team)].append(e)
 cohorts=defaultdict(set)
 for a in block['game_rows']:cohorts[(a['team'],a['source_player_id'])].add(a['game_id'])
 complete=set();counts=Counter()
 for g in block['expected_games']:
  for t in g['sides']:
   key=(g['game_id'],t);es=events[key]
   unknown=not es or any(e['offense']is None or e['eligible_target_attempt']is not True or e['attributed_receiver_id']is None or e['target_play_EPA']is None for e in es)
   counts['sides']+=1;counts['source_events']+=len(es)
   if not unknown:complete.add(key);counts['complete_team_target_EPA_sides']+=1
 # Conservative all scheduled games per pair: no skipping absent participant games.
 paired=0;knownsample=0;windows=0;positive=0
 for team in {x[0]for x in cohorts}:
  gs=sorted((g for g in block['expected_games']if team in g['sides']),key=lambda g:g['week']);ns=sorted(n for t,n in cohorts if t==team)
  for i,a in enumerate(ns):
   for b in ns[i+1:]:
    mask=[(g['game_id'],team)in complete and g['game_id']in cohorts[(team,a)]&cohorts[(team,b)]for g in gs]
    if sum(mask)>=2:knownsample+=1
    if len(mask)>=2 and all(mask):paired+=1
    for j in range(2,len(gs)+1):
     if all(mask[max(0,j-8):j]):windows+=1
 results.append(dict(season=block['season'],native_ref=ref,**counts,exact_full_season_pair_candidates=paired,known_sample_pair_candidates_ge2=knownsample,exact_trailing_up_to8_pair_windows_ge2=windows))
 del block,events,cohorts;gc.collect()
result=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,source='High-approved coverage_receiver_performance native event bases only; unchanged source adapters not replayed',classification='feasibility_only_0catalogIDs',results=results,new_source_queries=0,models=0)
(root/'feasibility_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
