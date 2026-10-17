"""Shared, strictly lagged revised-data adapter. Names are display fields only."""
from __future__ import annotations
import gzip,hashlib,importlib.util,json,time
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];SOURCES=HERE/'sources'
s=importlib.util.spec_from_file_location('workload_v2',HERE.parent/'revised_v2/experiment.py');v2=importlib.util.module_from_spec(s);s.loader.exec_module(v2)
TARGETS=v2.TARGETS
DETAIL_RAW=['passing_epa','receiving_epa','rushing_epa','passing_cpoe','passing_air_yards','receiving_yards_after_catch','passing_yards_after_catch','wopr','air_yards_share']
DETAIL=[k+'_mean3' for k in DETAIL_RAW]+['receiving_first_down_rate','rushing_first_down_rate','passing_first_down_rate','lost_fumbles_per_touch','targets_mean8','carries_mean8','fantasy_points_ppr_mean8','fantasy_points_ppr_std8']
ROLE=['offense_pct_mean3','offense_pct_last','offense_pct_trend','offense_snaps_mean3','targets_per_offense_snap','carries_per_offense_snap','redzone_targets_mean3','redzone_carries_mean3','inside5_carries_mean3','deep_targets_mean3','team_plays_mean3','team_neutral_pass_fraction','team_no_huddle_fraction','team_shotgun_fraction','team_redzone_pass_fraction','opponent_plays_mean3','opponent_neutral_pass_fraction','opponent_redzone_plays_mean3']
VARIANTS={'F0_basic':v2.BASE,'F1_production':v2.BASE+v2.EXTRA,'F2_efficiency':v2.BASE+v2.EXTRA+DETAIL,'F3_role_pbp':v2.BASE+v2.EXTRA+DETAIL+ROLE}

def read(path):
 with gzip.open(path,'rt') as f:return json.load(f)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def period(r):return int(r['season']),int(r['week'])
def team(x):return v2.team(x)
def num(x):return v2.number(x)
def utc(x):
 p=pd.Timestamp(x);return p.tz_localize('UTC') if p.tzinfo is None else p.tz_convert('UTC')
def load_sources():
 manifest=json.loads((SOURCES/'manifest.json').read_text())
 for name,item in manifest.items():
  if sha(SOURCES/name)!=item['sha256']:raise ValueError('Immutable source changed: '+name)
 return manifest

def schedule_rows():
 frame=pd.read_parquet(SOURCES/'games.parquet');games={}
 for r in frame[frame.season.isin([2023,2024,2025,2026])&(frame.game_type=='REG')].to_dict('records'):
  if not r.get('gametime') or pd.isna(r['gametime']):continue
  kickoff=pd.Timestamp(str(r['gameday'])+' '+str(r['gametime']),tz='America/New_York').tz_convert('UTC')
  local=kickoff.tz_convert('America/New_York');minutes=local.hour*60+local.minute
  sunday_main=r['weekday']=='Sunday' and 13*60<=minutes<=16*60+30
  cutoff=pd.Timestamp(local.date()).tz_localize('America/New_York')+pd.Timedelta(hours=12) if sunday_main else kickoff-pd.Timedelta(hours=1)
  games[r['game_id']]={'season':int(r['season']),'week':int(r['week']),'game_id':r['game_id'],'kickoff_at':kickoff,'completed_at':kickoff+pd.Timedelta(hours=8),'cutoff_at':cutoff.tz_convert('UTC'),'sunday_main':sunday_main,'home_team':team(r['home_team']),'away_team':team(r['away_team'])}
 return games

def canonical_maps():
 aliases=read(ROOT/'artifacts/all_games_captain_2026/inputs/aliases.json.gz');mapping=defaultdict(set)
 for r in aliases:
  if r['source_system']=='nflreadpy':mapping[str(r['source_key'])].add(r['player_master_id'])
 native={k:next(iter(ids)) for k,ids in mapping.items() if len(ids)==1}
 players=pd.read_parquet(SOURCES/'players.parquet');pfr=defaultdict(set)
 for r in players[['pfr_id','gsis_id']].dropna().to_dict('records'):pfr[r['pfr_id']].add(r['gsis_id'])
 bridge={k:next(iter(ids)) for k,ids in pfr.items() if len(ids)==1}
 return native,bridge,{'ambiguous_gsis_keys':sum(len(ids)>1 for ids in mapping.values()),'ambiguous_pfr_keys':sum(len(ids)>1 for ids in pfr.values())}

def load_stats(native,games):
 old=read(ROOT/'artifacts/classic_opportunity_repair/weekly_stats.json.gz');current=read(ROOT/'artifacts/all_games_captain_2026/inputs/stats.json.gz')
 selected={};rejected=Counter();game_index=defaultdict(list)
 for gid,g in games.items():
  for club,opponent in [(g['home_team'],g['away_team']),(g['away_team'],g['home_team'])]:
   game_index[(g['season'],g['week'],club,opponent)].append(gid)
 for r in [*old,*current]:
  if int(r['season']) not in [2023,2024,2025,2026] or int(r['week'])>18 or (r['season']==2026 and r['week']>5) or r['position'] not in {'QB','RB','WR','TE'}:continue
  raw=r['raw_row_json']
  if raw.get('season_type')!='REG':continue
  sid=str(r.get('source_player_id') or r.get('player_id'));pid=native.get(sid)
  if pid is None:rejected['unresolved_or_ambiguous_stats_native_id']+=1;continue
  supplied=r.get('player_master_id')
  if supplied and supplied!=pid:rejected['native_canonical_snapshot_conflict']+=1;continue
  club=team(r['team']);rawclub=team(raw.get('team') or raw.get('recent_team'))
  if club!=rawclub:rejected['stats_team_payload_conflict']+=1;continue
  version=(utc(r['created_at']),int(r['raw_nfl_weekly_stat_id']));key=(pid,int(r['season']),int(r['week']))
  if key in selected and selected[key][0]>=version:continue
  row={'player_master_id':pid,'source_player_id':sid,'raw_source_id':int(r['raw_nfl_weekly_stat_id']),'source_imported_at':r['created_at'],'season':int(r['season']),'week':int(r['week']),'team':club,'opponent':team(raw.get('opponent_team') or r.get('opponent')),'position':r['position'],'game_id':raw.get('game_id') or r.get('game_id'),'name':raw.get('player_display_name') or r.get('player_name') or sid,'source_refs':[f'local_weekly_stat:{r["raw_nfl_weekly_stat_id"]}']}
  if row['game_id'] not in games:
   matches=game_index[(row['season'],row['week'],club,row['opponent'])]
   if len(matches)!=1:rejected['unresolved_schedule_game_link']+=1;continue
   row['game_id']=matches[0];row['source_refs'].append('games.parquet:'+matches[0]+':reconstructed_metadata')
   rejected['resolved_missing_game_id_via_schedule']+=1
  for k in TARGETS+v2.PRODUCTION+DETAIL_RAW+['receiving_first_downs','rushing_first_downs','passing_first_downs','rushing_fumbles_lost','receiving_fumbles_lost']:row[k]=num(raw.get(k))
  row['targets']=num(r.get('targets',raw.get('targets')));row['carries']=num(r.get('carries',raw.get('carries')))
  row['lost_fumbles']=row['rushing_fumbles_lost']+row['receiving_fumbles_lost']
  row['touches']=row['carries']+row['receptions']
  selected[key]=(version,row)
 return {key:r for key,(_,r) in selected.items()},dict(rejected)

def load_snaps(native,bridge,stats):
 selected={};reject=Counter();unresolved=[]
 for year in [2023,2024,2025,2026]:
  path=SOURCES/f'snaps_{year}.parquet'
  if not path.exists():continue
  frame=pd.read_parquet(path)
  for n,r in enumerate(frame[(frame.game_type=='REG')&(frame.week<=18)&((frame.week<=5)|(frame.season<2026))].to_dict('records')):
   if r['position'] not in {'QB','RB','WR','TE'}:continue
   sid=bridge.get(r['pfr_player_id']);pid=native.get(str(sid)) if sid else None
   if pid is None:
    if r['position'] in {'QB','RB','WR','TE'}:reject['unresolved_snap_native_id']+=1;unresolved.append({'season':year,'game_id':r['game_id'],'pfr_player_id':r['pfr_player_id'],'position':r['position']})
    continue
   key=(pid,int(r['season']),int(r['week']));club=team(r['team']);existing=stats.get(key)
   if existing and existing['source_player_id']!=sid:reject['snap_native_identity_conflict']+=1;continue
   if existing and (existing['team']!=club or existing['game_id']!=r['game_id']):reject['snap_stats_game_team_conflict']+=1;continue
   item={'offense_pct':num(r['offense_pct']),'offense_snaps':num(r['offense_snaps']),'source_refs':[f'{path.name}:{r["game_id"]}:{r["pfr_player_id"]}'],'season':year,'week':int(r['week']),'game_id':r['game_id'],'team':club,'opponent':team(r['opponent']),'position':r['position'],'source_player_id':sid,'name':r['player']}
   if key in selected and selected[key]['offense_snaps']!=item['offense_snaps']:raise ValueError('Duplicate conflicting snap entity/game')
   selected[key]=item
 return selected,dict(reject),unresolved

def pbp_context(native):
 players={};teams={};coverage={};unresolved=Counter()
 cols=['play_id','game_id','season','season_type','week','posteam','defteam','yardline_100','qtr','score_differential','pass_attempt','rush_attempt','receiver_player_id','rusher_player_id','air_yards','no_huddle','shotgun','play_type']
 for year in [2023,2024,2025,2026]:
  path=SOURCES/f'pbp_{year}.parquet'
  if not path.exists():continue
  f=pd.read_parquet(path,columns=cols);f=f[(f.season_type=='REG')&(f.week<=18)&((f.week<=5)|(f.season<2026))&f.play_type.isin(['run','pass','qb_kneel','qb_spike'])].copy()
  coverage[str(year)]={'plays':len(f),'games':int(f.game_id.nunique()),'weeks':sorted(int(w) for w in f.week.unique())}
  for (season,week,gid,club),g in f.groupby(['season','week','game_id','posteam']):
   key=(int(season),int(week),team(club));neutral=(g.qtr<=3)&(g.score_differential.abs()<=7);rz=g.yardline_100<=20
   teams[key]={'season':int(season),'week':int(week),'game_id':gid,'plays':len(g),'neutral_passes':float(g.loc[neutral,'pass_attempt'].sum()),'neutral_plays':int(neutral.sum()),'no_huddles':float(g.no_huddle.sum()),'shotguns':float(g.shotgun.sum()),'redzone_passes':float(g.loc[rz,'pass_attempt'].sum()),'redzone_plays':int(rz.sum()),'source_refs':[f'{path.name}:{gid}:{club}'],'source_ids':[]}
  for sidfield,mask,counts in [('receiver_player_id',f.pass_attempt==1,['targets','redzone_targets','deep_targets']),('rusher_player_id',f.rush_attempt==1,['carries','redzone_carries','inside5_carries'])]:
   for (season,week,gid,sid),g in f[mask&f[sidfield].notna()].groupby(['season','week','game_id',sidfield]):
    pid=native.get(str(sid))
    if pid is None:unresolved['unresolved_pbp_native_id']+=1;continue
    k=(pid,int(season),int(week));item=players.setdefault(k,{'season':int(season),'week':int(week),'game_id':gid,'source_refs':[f'{path.name}:{gid}:{sid}']})
    if item['game_id']!=gid:raise ValueError('Player PBP spans multiple games in week')
    item[counts[0]]=len(g);item[counts[1]]=int((g.yardline_100<=20).sum());item[counts[2]]=int((g.air_yards>=20).sum()) if counts[2]=='deep_targets' else int((g.yardline_100<=5).sum())
 return players,teams,coverage,dict(unresolved)

def eligible(source,target,games):
 game=games.get(source['game_id']);targetgame=games.get(target['game_id'])
 return bool(game and targetgame and period(source)<period(target) and game['completed_at']<targetgame['cutoff_at'])

def expanded_matrix(stats,snaps,pp,tp,games):
 rows=[];counts=Counter();label_reliability=Counter()
 for key in sorted(set(stats)|set(snaps),key=lambda k:(k[1],k[2],k[0])):
  st=stats.get(key);sn=snaps.get(key)
  if st is None and sn and sn['position'] in {'QB','RB','WR','TE'} and sn['offense_snaps']>0:
   # Participation exists, workload not observed: preserve missing labels/history.
   counts['positive_snap_participant_without_stats']+=1
   st={k:np.nan for k in TARGETS+v2.PRODUCTION+DETAIL_RAW+['receiving_first_downs','rushing_first_downs','passing_first_downs','lost_fumbles','touches']}
   st.update(player_master_id=key[0],source_player_id=sn['source_player_id'],raw_source_id=None,source_imported_at=None,season=key[1],week=key[2],team=sn['team'],opponent=sn['opponent'],position=sn['position'],game_id=sn['game_id'],name=sn['name'],source_refs=[])
  if st is None:continue
  row=deepcopy(st)
  if sn:row.update(offense_pct=sn['offense_pct'],offense_snaps=sn['offense_snaps']);row['source_refs']+=sn['source_refs']
  else:row.update(offense_pct=np.nan,offense_snaps=np.nan);counts['stats_without_snap_evidence']+=1
  game=games.get(row['game_id'])
  if game is None:counts['missing_schedule_game']+=1;continue
  pbpcovered=(row['season'],row['week'],row['team']) in tp
  pc=pp.get(key,{})
  for field in ['redzone_targets','redzone_carries','inside5_carries','deep_targets']:
   row[field]=float(pc.get(field,0)) if pbpcovered and sn and sn['offense_snaps']>0 else np.nan
  if pc:row['source_refs']+=pc['source_refs']
  row['pbp_game_covered']=pbpcovered;row['sunday_main']=game['sunday_main'];row['decision_cutoff_at']=game['cutoff_at'].isoformat();row['kickoff_at']=game['kickoff_at'].isoformat()
  row['positive_snap_population']=bool(sn and sn['offense_snaps']>0)
  for label in ['targets','carries']:
   if row['season']==2026 and row['week'] in [4,5] and np.isfinite(row[label]) and pbpcovered:
    observed_count=float(pc.get(label,0));label_reliability[f'{row["week"]}/{label}/checked']+=1
    label_reliability[f'{row["week"]}/{label}/exact_match']+=int(observed_count==row[label])
  rows.append(row)
 # Reuse base family implementation on complete weekly history, then add clock-checked families.
 base=v2.build_matrix(deepcopy(rows));hist=defaultdict(list);byperiod=defaultdict(list);teamhist=defaultdict(list)
 for row in rows:byperiod[period(row)].append(row)
 byentity={(r['player_master_id'],*period(r)):r for r in rows}
 extra={}
 for block in sorted(byperiod):
  for row in byperiod[block]:
   prior=[q for q in hist[row['player_master_id']] if eligible(q,row,games)]
   h=prior[-3:];h8=prior[-8:];lastteam=h[-1]['team'] if h else None
   th=[q for q in teamhist[lastteam] if eligible(q,row,games)][-3:] if lastteam else []
   oh=[q for q in teamhist[row['opponent']] if eligible(q,row,games)][-3:]
   out={}
   for field in DETAIL_RAW:out[field+'_mean3']=v2.mean(h,field)
   for name,n,d in [('receiving_first_down_rate','receiving_first_downs','targets'),('rushing_first_down_rate','rushing_first_downs','carries'),('passing_first_down_rate','passing_first_downs','attempts'),('lost_fumbles_per_touch','lost_fumbles','touches')]:out[name]=v2.ratio(h,n,d)
   for field in TARGETS:out[field+'_mean8']=v2.mean(h8,field)
   valid=[q['fantasy_points_ppr'] for q in h8 if np.isfinite(q['fantasy_points_ppr'])];out['fantasy_points_ppr_std8']=float(np.std(valid)) if len(valid)>=2 else np.nan
   out['offense_pct_mean3']=v2.mean(h,'offense_pct');out['offense_pct_last']=h[-1]['offense_pct'] if h else np.nan;out['offense_pct_trend']=out['offense_pct_last']-out['offense_pct_mean3'];out['offense_snaps_mean3']=v2.mean(h,'offense_snaps')
   out['targets_per_offense_snap']=v2.ratio(h,'targets','offense_snaps');out['carries_per_offense_snap']=v2.ratio(h,'carries','offense_snaps')
   for field in ['redzone_targets','redzone_carries','inside5_carries','deep_targets']:out[field+'_mean3']=v2.mean(h,field)
   out['team_plays_mean3']=v2.mean(th,'plays');out['opponent_plays_mean3']=v2.mean(oh,'plays');out['opponent_redzone_plays_mean3']=v2.mean(oh,'redzone_plays')
   for name,n,d in [('team_neutral_pass_fraction','neutral_passes','neutral_plays'),('team_no_huddle_fraction','no_huddles','plays'),('team_shotgun_fraction','shotguns','plays'),('team_redzone_pass_fraction','redzone_passes','redzone_plays')]:out[name]=v2.ratio(th,n,d)
   out['opponent_neutral_pass_fraction']=v2.ratio(oh,'neutral_passes','neutral_plays')
   used=[*h8,*th,*oh];out['expanded_source_refs_json']=json.dumps(sorted({ref for q in used for ref in q.get('source_refs',[])}))
   out['max_expanded_source_period']=max((q['season']*100+q['week'] for q in used),default=np.nan)
   out['max_expanded_completed_at']=max((games[q['game_id']]['completed_at'] for q in used),default=pd.NaT)
   extra[(row['player_master_id'],*period(row))]=out
  for row in byperiod[block]:hist[row['player_master_id']].append(row)
  for key,row in tp.items():
   if key[:2]==block:teamhist[key[2]].append(row)
 # A whole-block clock bound audits every possible base player/team/opponent lag.
 completion_by_block={block:max(games[q['game_id']]['completed_at'] for q in group) for block,group in byperiod.items()}
 prior_complete=None
 for block in sorted(byperiod):
  if prior_complete is not None and any(prior_complete>=games[q['game_id']]['cutoff_at'] for q in byperiod[block]):
   raise ValueError('Base-family lag has unproven completion clock')
  prior_complete=max(prior_complete,completion_by_block[block]) if prior_complete is not None else completion_by_block[block]
 additions=[]
 for r in base.to_dict('records'):
  entity=byentity[(r['player_master_id'],int(r['season']),int(r['week']))]
  r.update(extra[(r['player_master_id'],int(r['season']),int(r['week']))])
  r.update({key:entity[key] for key in ['sunday_main','positive_snap_population','pbp_game_covered','decision_cutoff_at','kickoff_at']})
  r['split']='test' if r['season']==2026 and r['week'] in [4,5] else 'validation' if r['season']==2025 and 13<=r['week']<=17 else 'tuning_train' if r['season']<2025 or (r['season']==2025 and r['week']<=12) else 'refit_only'
  r['final_train']=r['season']<2026 or r['week']<=3
  additions.append(r)
 return pd.DataFrame(additions),dict(counts),dict(label_reliability)

def prepare():
 start=time.perf_counter();source_manifest=load_sources();games=schedule_rows();native,bridge,id_audit=canonical_maps();stats,stat_reject=load_stats(native,games);snaps,snap_reject,unresolved=load_snaps(native,bridge,stats);pp,tp,pbpcoverage,pbpreject=pbp_context(native)
 frame,counts,reliability=expanded_matrix(stats,snaps,pp,tp,games)
 frame.to_csv(HERE/'feature_matrix.csv',index=False,float_format='%.10g')
 population=frame[frame.positive_snap_population]
 game_coverage=[]
 for gid,game in games.items():
  if game['season']!=2026 or game['week'] not in [4,5] or not game['sunday_main']:continue
  group=population[population.game_id==gid];allgroup=frame[frame.game_id==gid]
  game_coverage.append({'game_id':gid,'week':game['week'],'positive_snap_players':len(group),'recorded_skill_rows':len(allgroup),'positions':group.groupby('position').size().to_dict(),'missing_targets':int(group.targets.isna().sum()),'missing_carries':int(group.carries.isna().sum()),'missing_ppr':int(group.fantasy_points_ppr.isna().sum()),'pbp_covered':bool(group.pbp_game_covered.all()) if len(group) else False})
 sources=[ROOT/'artifacts/classic_opportunity_repair/weekly_stats.json.gz',ROOT/'artifacts/all_games_captain_2026/inputs/stats.json.gz',ROOT/'artifacts/all_games_captain_2026/inputs/aliases.json.gz',HERE.parent/'revised_v2/experiment.py']
 manifest={'study':'expanded revised-data retrospective v3','row_count':len(frame),'population_rows':len(population),'sample_counts':population.groupby('split').size().to_dict(),'sunday_main_test_counts':population[(population.split=='test')&population.sunday_main].groupby('week').size().to_dict(),'id_audit':id_audit,'stats_rejected':stat_reject,'snaps_rejected':snap_reject,'pbp_rejected':pbpreject,'population_missingness':counts,'label_crosscheck':reliability,'pbp_coverage':pbpcoverage,'games':game_coverage,'feature_families':VARIANTS,'feature_coverage':{s:{col:float(g[col].notna().mean()) for col in VARIANTS['F3_role_pbp']} for s,g in population.groupby('split')},'immutable_public_sources':source_manifest,'local_sources_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sources},'spec_sha256':sha(HERE/'SPECIFICATION.md'),'adapter_sha256':sha(Path(__file__)),'matrix_sha256':sha(HERE/'feature_matrix.csv'),'prepare_seconds':time.perf_counter()-start}
 (HERE/'input_manifest.json').write_text(json.dumps(manifest,indent=2,default=str)+'\n');(HERE/'unresolved_snap_identities.json').write_text(json.dumps(unresolved,indent=2)+'\n')
 print(json.dumps({k:manifest[k] for k in ['sample_counts','sunday_main_test_counts','label_crosscheck','population_missingness','prepare_seconds']},indent=2))
if __name__=='__main__':prepare()
