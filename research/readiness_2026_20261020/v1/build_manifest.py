from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict,Counter
from decimal import Decimal,InvalidOperation
import json,re,hashlib
from backend.app.product_services.market_snapshots import canonical_team
out=Path('research/readiness_2026_20261020/v1');cache=json.loads((out/'CACHE_2026_PROJECTION.json').read_text());db=json.loads((out/'DB_READONLY_PROJECTION.json').read_text())['results'];snap=json.loads((out/'DB_SOURCE_INVENTORY_COMPLETE.json').read_text())['snapshots'];schedule={g['game_id']:g for g in cache['schedule_rows']};native_schedule=defaultdict(list)
for g in schedule.values():
 for t in[g['home_team'],g['away_team']]:native_schedule[(g['week'],canonical_team(t))].append(g['game_id'])
byalias=defaultdict(set);inverse=defaultdict(set)
for x in db['aliases']:byalias[x['source_key']].add(x['player_master_id']);inverse[x['player_master_id']].add(x['source_key'])
def identity(n):
 ids=byalias[n]
 return next(iter(ids))if len(ids)==1 and len(inverse[next(iter(ids))])==1 else None
def number(a,b=None):
 v=a if a is not None else b
 if v is None:return None
 try:n=Decimal(str(v));return int(n)if n.is_finite()and n>=0 and n==n.to_integral_value()else None
 except InvalidOperation:return None
latest=[];bad=[]
for r in db['latest_weekly']:
 try:t=canonical_team(r['team'])
 except ValueError:bad.append(dict(r,reason='unknown_team'));continue
 ids=native_schedule.get((r['week'],t),[]);n=r['player_id'];counts=dict(pass_attempts=number(r['attempts'],r['passing_attempts']),rush_attempts=number(r['carries'],r['rushing_attempts']),targets=number(r['targets']))
 row=dict(game_id=ids[0]if len(ids)==1 else None,week=r['week'],team=t,source_player_id=n,native_valid=bool(isinstance(n,str)and re.fullmatch(r'00-\d{7}',n)),current_unique_canonical_id=identity(n),counts=counts,source_id=r['raw_nfl_weekly_stat_id'],ingest_run_id=r['ingest_run_id'],imported_at=r['created_at'],role=r['position'],present_reported_native_game_ids=[v for v in[r['game_id'],r['gameid']]if v is not None])
 if len(ids)!=1:bad.append(dict(row,reason='no_unique_native_schedule'))
 latest.append(row)
old={(r['week'],r['team'],r['source_player_id']):r for r in cache['actor_rows']if r['source_player_id']is not None};new={(r['week'],r['team'],r['source_player_id']):r for r in latest if r['native_valid']};added=[r for k,r in new.items()if k not in old];changed=[dict(old_source_id=old[k]['source_id'],new_source_id=r['source_id'],game_id=r['game_id'],team=r['team'],native=r['source_player_id'],old_counts=old[k]['counts'],new_counts=r['counts'])for k,r in new.items()if k in old and old[k]['counts']!=r['counts']]
weeks=[];matchups=[]
complete_ids={g['game_id']for g in cache['completed_score_games']}
for w in range(1,8):
 games=[g for g in schedule.values()if g['week']==w];actors=[r for r in cache['actor_rows']if r['week']==w];teams=[r for r in cache['team_rows']if r['week']==w];now=[r for r in latest if r['week']==w];sources=[s for s in snap if s['week']==w];bydata=defaultdict(list)
 for s in sources:bydata[s['dataset']].append(s)
 channels={ch:dict(cached_known_actor_counts=sum(r['counts'][ch]is not None for r in actors),cached_actor_known_sum=sum(r['counts'][ch]or 0 for r in actors),cached_exact_source_team_sides=sum(r['counts'][ch]is not None for r in teams),DB_latest_known_actor_counts=sum(r['counts'][ch]is not None for r in now),DB_latest_known_native_sum=sum(r['counts'][ch]or 0 for r in now if r['native_valid']),known_native_source_record_sum_is_not_certified_full_NFL=True)for ch in ['pass_attempts','rush_attempts','targets']}
 histories=Counter()
 for g in games:
  for t in[g['home_team'],g['away_team']]:histories[sum(p['week']<w and t in[p['home_team'],p['away_team']]for p in schedule.values())]+=1
 row=dict(week=w,scheduled_games=len(games),completed_status_verified_cached_games=sum(g['game_id']in complete_ids for g in games),schedule_status_only_not_final_proof=True,cache_actor_rows=len(actors),cache_canonical_attached=sum(r['player_master_id']is not None for r in actors),DB_latest_rows=len(now),DB_latest_native_valid=sum(r['native_valid']for r in now),DB_current_unique_native_alias_rows=sum(r['native_valid']and r['current_unique_canonical_id']is not None for r in now),DB_current_alias_mapping_is_not_original_pregame=True,channels=channels,prior_scheduled_game_counts=dict(histories),coldstart_status='EXPLICIT_W1_ZERO_PRIOR_SAME_SEASON'if w==1 else'EXPLICIT_W2_ONE_PRIOR_SAME_SEASON'if w==2 else'EXPLICIT_W3_TWO_PRIOR_SAME_SEASON'if w==3 else'PRIOR3_SUPPORTED_ONLY_WHERE_ALL_THREE_SCHEDULED_SOURCE_GROUPS_KNOWN',joint_label_census='NOT_YET_ASSESSED_2026_EVENT_CACHE_BRIDGE',replacement_status='UNKNOWN_UNTIL_NATIVE_PREGAME_INJURY_PLUS_ROLE_ATTACHMENTS_VERIFIED',source_inventory={k:dict(snapshot_count=len(v),first_capture=min(x['captured_at']for x in v),last_capture=max(x['captured_at']for x in v),native_game_team_canonical_bindings='UNASSESSED_METADATA_ONLY')for k,v in bydata.items()})
 weeks.append(row)
 for g in games:
  pair=[]
  for t in[g['home_team'],g['away_team']]:
   prior=sorted([p for p in schedule.values()if p['week']<w and t in[p['home_team'],p['away_team']]],key=lambda p:p['week'])[-3:];tr=next((x for x in teams if x['game_id']==g['game_id']and x['team']==t),None);ar=[x for x in now if x['game_id']==g['game_id']and x['team']==t]
   pair.append(dict(team=t,opponent=g['away_team']if t==g['home_team']else g['home_team'],prior_scheduled_games=[p['game_id']for p in prior],prior3_achieved=len(prior)==3,cached_source_team=tr,DB_native_label_actor_rows=sum(x['native_valid']for x in ar),DB_canonical_label_actor_rows=sum(x['native_valid']and x['current_unique_canonical_id']is not None for x in ar),known_native_sums={ch:sum(x['counts'][ch]or 0 for x in ar if x['native_valid'])for ch in channels},unknown_channel_rows={ch:sum(x['counts'][ch]is None for x in ar)for ch in channels}))
  matchups.append(dict(game_id=g['game_id'],week=w,game_date=g['game_date'],completion_proven_by_reviewed_scoreboard=g['game_id']in complete_ids,sides=pair))
def pin(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
recoverable=[r for r in snap if r['dataset']in ['play_by_play','ftn_charting','weekly_stats','pfr_advstats_week_pass','schedule_context','snap_counts','snap_counts_revision','completed_game_scoreboard']]
record=dict(version='2026_readiness_coverage_v1',recorded_at=datetime.now(timezone.utc).isoformat(),status='READ_ONLY_DATA_READINESS_NOT_MODEL_RESULT_OR_LIVE_APPROVAL',weeks=weeks,matchups=matchups,current_native_actor_projection=latest,latest_DB_vs_frozen_component=dict(added_valid_native_actors=added,changed_existing_counts=changed,invalid_or_unscoped=bad,comparison_basis='Same2026week/team/nativeGSIS; immutable oldcomponent unchanged, DBnewprojection not automatically admitted'),recoverable_source_index=recoverable,source_inventory_count=len(snap),pregame_source_access='Official depth/roster/injury indexed snapshots EXIST for2026W5/W6, with capture clocks before some applicable games; exact game/team/GSIS->UUID and donor/replacement role bindings still UNASSESSED. Prior bounded2025audit does not prove2026sourceabsence.',full_NFL_count_census='UNKNOWN; weekly source rows and explicit positive-missing threats are not independent full physical target/rush census',original_pregame_replay='NOT_ESTABLISHED broadly. Later counts are legitimate labels; predictors require each prior measurement and role attachment available by target kickoff. Earliest imports for W1–3 revised weeklyrows areOct4; cannot backdate them.',coldstart_policy='Keep everyW1–3game/actor scope in coverage. Unchanged same-seasonprior3jointcontract has noW1–3prediction. A separately declared frozen TRAIN-only coldstart or explicitly transported prior-season recipe is needed; no silentwindowrelaxation, historyinvention or droppingearlyweeks.',smallest_actions=['Verify original bytes of latest2026W6 weeklysnapshot cd2fb202 against DB projection; append a new immutable narrow native-count/canonical-scope component rather than overwrite ef9512.','Reuse existing indexed2026PBP snapshot79230705 (37MB,16212rows) through bounded minimal official eligibility/pass/rush/recipient+native order projection. It predates Monday game, so test actual game coverage; do not claimfullW6. No broadredownload required forW1–5census.','Verify existing2026FTNcharting snapshot5eafb584 (2.4MB,13621rows) schema/native keys/actualnonnull coverage; it is a different retainedsource than2023–25position cache, not proof exact11sourcepositions are available.','Obtain/verify completed-game finalstatus W6 after finding indexed reuse; existing79reviewed W1–5scores cannot certifyW6. NativeDBschedule statusNULL and partialscorefields insufficient.','Bounded exactcase mapping of retainedW5/W6officialinjury+roster/depthsource metadata to nativegames andcanonical actors beforepregame times. No usage-derived replacements.','Freeze repairedmodel/recipe first; report reconstructedsource-vintage vs original-vintage2026evaluations separately; no livechanges by coveragealone.'],pins=[pin(out/'DB_READONLY_PROJECTION.json'),pin(out/'DB_SOURCE_INVENTORY_COMPLETE.json'),pin(out/'CACHE_2026_PROJECTION.json')],DB_mutations=0,new_downloads=0,raw_PBP_decodes=0,fits=0,model_or_settings_changes=0)
(out/'MANIFEST.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n');print('newactors',len(added),'changedcounts',len(changed));print([{k:r[k]for k in ['week','scheduled_games','completed_status_verified_cached_games','cache_actor_rows','DB_latest_rows','DB_current_unique_native_alias_rows']}for r in weeks])
