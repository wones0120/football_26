"""Research-only context: native identities, lagged evidence and strict receipts."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
V3=HERE.parent/'neural_workload_benchmark_20261013/expanded_v3'
ZONES={}
for zone,ids in {
 'America/New_York':'ATL97 BAL00 BOS00 BUF00 CAR00 CIN00 CLE00 DET00 IND00 JAX00 MIA00 NYC01 PHI00 PIT00 TAM00 WAS00',
 'America/Chicago':'CHI98 DAL00 GNB00 HOU00 KAN00 MIN01 NAS00 NOR00',
 'America/Denver':'DEN00', 'America/Phoenix':'PHO00',
 'America/Los_Angeles':'LAX01 SEA00 SFO01 VEG00',
 'Europe/Berlin':'FRA00 GER00 MUN01', 'Europe/London':'LON00 LON02',
 'Europe/Madrid':'MAD01','Australia/Melbourne':'MEL00','America/Mexico_City':'MEX00',
 'Europe/Paris':'PAR00','America/Sao_Paulo':'RIO00 SAO00',
}.items():
 for sid in ids.split():ZONES[sid]=zone
SCHEDULE=['ctx_home','ctx_neutral','ctx_weekday_sin','ctx_weekday_cos','ctx_et_sin','ctx_et_cos','ctx_local_sin','ctx_local_cos','ctx_prime_time','ctx_rest_days','ctx_opponent_rest_days','ctx_short_rest','ctx_opponent_short_rest']
VENUE=['ctx_fixed_indoor','ctx_open_air','ctx_retractable','ctx_venue_unknown']
PROXY_METRICS=['history_games','receiving_absent_last_targets','rushing_absent_last_carries','receiving_returned_last_targets','rushing_returned_last_carries','qb_prior_count','qb_last_count','ol_absent_last_snaps','defense_absent_last_snaps','canonical_snap_coverage']
TEAM=['ctx_teammate_'+k for k in PROXY_METRICS]
OPPONENT=['ctx_opponent_'+k for k in PROXY_METRICS]
FAMILIES={'baseline':[],'schedule':SCHEDULE,'venue':VENUE,'teammate_proxy':TEAM,'opponent_proxy':OPPONENT,'combined':SCHEDULE+VENUE+TEAM+OPPONENT}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def utc(value):
 t=pd.Timestamp(value)
 if pd.isna(t) or t.tzinfo is None:raise ValueError('Evidence clock requires explicit timezone')
 return t.tz_convert('UTC')

def validate_availability(snapshot,*,game_id,cutoff):
 """Fail closed for provenance gaps; absence from injury report is never healthy."""
 cutoff=utc(cutoff)
 required=['source_id','source_sha256','game_id','published_at','observed_at','roster_members']
 if any(not snapshot.get(k) for k in required):raise ValueError('Missing snapshot provenance or roster coverage')
 if snapshot['game_id']!=game_id:raise ValueError('Snapshot game mismatch')
 if len(snapshot['source_sha256'])!=64:raise ValueError('Invalid source hash')
 if utc(snapshot['published_at'])>cutoff or utc(snapshot['observed_at'])>cutoff:raise ValueError('Availability evidence after cutoff')
 members={}
 for r in snapshot['roster_members']:
  if any(not r.get(k) for k in ['player_master_id','team','position','effective_from']):raise ValueError('Canonical effective roster membership required')
  if utc(r['effective_from'])>cutoff or (r.get('effective_until') and utc(r['effective_until'])<=cutoff):raise ValueError('Roster membership not effective at cutoff')
  key=r['player_master_id']
  if key in members:raise ValueError('Duplicate canonical roster membership')
  members[key]=r.copy()|{'status':'unknown'}
 seen=set()
 for r in snapshot.get('reports',[]):
  key=r.get('player_master_id')
  if key not in members or key in seen:raise ValueError('Unresolved/duplicate report identity')
  if r.get('team')!=members[key]['team'] or r.get('position')!=members[key]['position']:raise ValueError('Effective team/position mismatch')
  if r.get('status') not in {'out','doubtful','questionable','available','unknown'}:raise ValueError('Unsupported availability status')
  if not r.get('published_at') or utc(r['published_at'])>cutoff:raise ValueError('Report publication missing/late')
  members[key]['status']=r['status'];seen.add(key)
 return list(members.values())

def aggregate_availability(members,team,history,*,exclude_player=None):
 """Known-status workload at cutoff; revised past performance only, no actual DNP."""
 result={};groups={'qb':{'QB'},'receiving':{'WR','TE'},'rushing':{'RB'},'ol':{'T','OT','G','OG','C','OL'},'defense':{'DE','DT','NT','DL','LB','ILB','OLB','CB','S','SS','FS','DB'}}
 for group,positions in groups.items():
  selected=[r for r in members if r['team']==team and r['position'] in positions and r['player_master_id']!=exclude_player]
  result[group+'_members']=len(selected)
  for status in ['out','doubtful','questionable','available','unknown']:result[group+'_'+status+'_count']=sum(r['status']==status for r in selected)
  metric='targets' if group=='receiving' else 'carries' if group=='rushing' else 'snaps'
  for status in ['out','available']:
   vals=[history.get(r['player_master_id'],{}).get(metric,np.nan) for r in selected if r['status']==status]
   result[group+'_'+status+'_prior_'+metric]=float(np.nansum(vals)) if vals and np.isfinite(vals).any() else np.nan
  # Return = available now and explicit out in prior snapshot; never inferred from missing rows.
  result[group+'_returning_count']=sum(r['status']=='available' and history.get(r['player_master_id'],{}).get('prior_status')=='out' for r in selected)
 return result

def schedule_context(game,club,games):
 kickoff=utc(game['kickoff_at']);et=kickoff.tz_convert('America/New_York');neutral=game.get('location')=='Neutral'
 if club not in [game['home_team'],game['away_team']]:raise ValueError('Effective team not in game')
 sid=game['stadium_id'];zone=ZONES.get(sid);zone=None if sid=='JAX00' and neutral else zone
 local=kickoff.tz_convert(zone) if zone else None
 def cyclic(minutes):return np.sin(2*np.pi*minutes/1440),np.cos(2*np.pi*minutes/1440)
 es,ec=cyclic(et.hour*60+et.minute);ls,lc=cyclic(local.hour*60+local.minute) if local else (np.nan,np.nan)
 opponent=game['away_team'] if club==game['home_team'] else game['home_team']
 def rest(team):
  prior=[g for g in games.values() if g['season']==game['season'] and g['completed_at']<game['cutoff_at'] and team in [g['home_team'],g['away_team']]]
  return (et.date()-max(prior,key=lambda g:g['kickoff_at'])['kickoff_at'].tz_convert('America/New_York').date()).days if prior else np.nan
 rd,od=rest(club),rest(opponent)
 prior=[g for g in games.values() if g['stadium_id']==sid and g['completed_at']<game['cutoff_at']]
 roofs={g.get('roof') for g in prior};kind='retractable' if roofs&{'open','closed'} else 'fixed_indoor' if 'dome' in roofs else 'open_air' if 'outdoors' in roofs else 'unknown'
 if sid=='JAX00' and neutral:kind='unknown'
 out=dict(ctx_home=np.nan if neutral else float(club==game['home_team']),ctx_neutral=float(neutral),ctx_weekday_sin=np.sin(2*np.pi*et.weekday()/7),ctx_weekday_cos=np.cos(2*np.pi*et.weekday()/7),ctx_et_sin=es,ctx_et_cos=ec,ctx_local_sin=ls,ctx_local_cos=lc,ctx_prime_time=float(et.hour>=19),ctx_rest_days=rd,ctx_opponent_rest_days=od,ctx_short_rest=float(rd<=5) if np.isfinite(rd) else np.nan,ctx_opponent_short_rest=float(od<=5) if np.isfinite(od) else np.nan)
 out.update({k:float(kind==k.removeprefix('ctx_venue_') if k=='ctx_venue_unknown' else kind==k.removeprefix('ctx_')) for k in VENUE})
 return out

def participation_proxy(history,*,exclude_player=None):
 """Prior games supplied oldest to newest. Missing last game is NOT future out."""
 out={k:np.nan for k in PROXY_METRICS};out['history_games']=len(history)
 if not history:return out
 past=history[:-1];last={r['player_master_id']:r for r in history[-1] if r['player_master_id']!=exclude_player};older=defaultdict(list)
 for game in past:
  for r in game:
   if r['player_master_id']!=exclude_player:older[r['player_master_id']].append(r)
 def mean(records,field):
  vals=[r.get(field,np.nan) for r in records];finite=[v for v in vals if np.isfinite(v)]
  return float(np.mean(finite)) if finite else np.nan
 for name,metric in [('receiving','targets'),('rushing','carries')]:
  absent=[mean(rs,metric) for pid,rs in older.items() if pid not in last]
  # Returning observed in latest PRIOR game but absent in immediately preceding game.
  preceding={r['player_master_id'] for r in past[-1]} if past else set()
  returned=[r.get(metric,np.nan) for pid,r in last.items() if pid in older and pid not in preceding]
  out[name+'_absent_last_'+metric]=float(np.nansum(absent)) if past else np.nan
  out[name+'_returned_last_'+metric]=float(np.nansum(returned)) if len(past)>=2 else np.nan
 out['qb_prior_count']=len({pid for pid,rs in older.items() if rs[-1]['position']=='QB'}) if past else np.nan
 out['qb_last_count']=sum(r['position']=='QB' for r in last.values())
 for group,positions in [('ol',{'T','OT','G','OG','C','OL'}),('defense',{'DE','DT','NT','DL','LB','ILB','OLB','CB','S','SS','FS','DB'})]:
  vals=[mean(rs,'snaps') for pid,rs in older.items() if pid not in last and rs[-1]['position'] in positions]
  # No canonically identified positional players means unsupported, not zero loss.
  supported=any(r['position'] in positions for g in history for r in g)
  out[group+'_absent_last_snaps']=float(np.nansum(vals)) if past and supported else np.nan
 counts=[r.get('bridge_coverage',np.nan) for r in history[-1]];out['canonical_snap_coverage']=float(np.nanmean(counts)) if np.isfinite(counts).any() else np.nan
 return out

def build_matrix():
 import importlib.util
 spec=importlib.util.spec_from_file_location('context_v3_data',V3/'data.py');data=importlib.util.module_from_spec(spec);spec.loader.exec_module(data)
 manifest=data.load_sources();base_manifest=json.loads((V3/'input_manifest.json').read_text())
 if sha(V3/'feature_matrix.csv')!=base_manifest['matrix_sha256']:raise ValueError('Base matrix changed')
 f=pd.read_csv(V3/'feature_matrix.csv');games=data.schedule_rows();raw=pd.read_parquet(V3/'sources/games.parquet')
 for r in raw.to_dict('records'):
  if r['game_id'] in games:games[r['game_id']].update({k:r[k] for k in ['stadium_id','roof','location']})
 native,bridge,identity=data.canonical_maps();bygame=defaultdict(dict);coverage={};injury_inventory={}
 for year in [2023,2024,2025,2026]:
  snaps=pd.read_parquet(V3/'sources'/f'snaps_{year}.parquet');snaps=snaps[(snaps.game_type=='REG')&(snaps.week<=18)&((snaps.week<=5)|(snaps.season<2026))]
  snaps['canonical']=snaps.pfr_player_id.map(bridge).map(native)
  for (gid,club),g in snaps.groupby(['game_id','team']):
   ratio=float(g.canonical.notna().mean());coverage[f'{gid}/{club}']={'rows':len(g),'resolved':int(g.canonical.notna().sum())}
   for r in g[g.canonical.notna()].to_dict('records'):
    active=r['offense_snaps']+r['defense_snaps']>0
    if active:bygame[(gid,data.team(club))][r['canonical']]={'player_master_id':r['canonical'],'position':r['position'],'snaps':r['offense_snaps']+r['defense_snaps'],'bridge_coverage':ratio}
 for r in f.to_dict('records'):
  if not r['positive_snap_population']:continue
  item=bygame[(r['game_id'],r['team'])].get(r['player_master_id'])
  if item:item.update(targets=r['targets'],carries=r['carries'])
 clubgames=defaultdict(list)
 for gid,g in games.items():
  for club in [g['home_team'],g['away_team']]:clubgames[club].append(g)
 for club in clubgames:clubgames[club].sort(key=lambda g:g['kickoff_at'])
 cache={};contexts=[]
 for r in f.to_dict('records'):
  game=games[r['game_id']];key=(r['game_id'],r['team'])
  if key not in cache:cache[key]=schedule_context(game,r['team'],games)
  out=cache[key].copy()
  for role,club,exclude in [('teammate',r['team'],r['player_master_id']),('opponent',r['opponent'],None)]:
   prior=[g for g in clubgames[club] if g['season']==game['season'] and g['completed_at']<game['cutoff_at']][-3:]
   hist=[list(bygame[(g['game_id'],club)].values()) for g in prior]
   out.update({'ctx_'+role+'_'+k:v for k,v in participation_proxy(hist,exclude_player=exclude).items()})
  contexts.append(out)
 context=pd.DataFrame(contexts,index=f.index);result=pd.concat([f,context],axis=1);result['period']=result.season*100+result.week
 result.to_csv(HERE/'feature_matrix.csv',index=False,float_format='%.10g')
 for year in [2023,2024,2025]:
  path=HERE/'sources'/f'injuries_{year}.parquet';inj=pd.read_parquet(path);injury_inventory[str(year)]={'rows':len(inj),'sha256':sha(path),'has_date_modified':'date_modified' in inj,'canonical_resolved':int(inj.gsis_id.map(native).notna().sum()),'original_predecision_receipt':False,'primary_training_used':False}
 report={'base_matrix_sha256':base_manifest['matrix_sha256'],'context_matrix_sha256':sha(HERE/'feature_matrix.csv'),'source_manifest':manifest,'injury_inventory':injury_inventory,'stadium_timezone_table':ZONES,'identity':identity,'features':{c:{'nonmissing':int(result[c].notna().sum()),'rows':len(result),'coverage':float(result[c].notna().mean()),'kind':'lagged_participation_proxy' if 'teammate' in c or 'opponent' in c and c not in SCHEDULE else 'reconstructed_schedule_or_lagged_venue'} for c in context.columns},'canonical_snap_bridge':coverage,'actual_availability_training_rows':0,'base_features':base_manifest['feature_families']['F3_role_pbp'],'families':FAMILIES}
 (HERE/'coverage.json').write_text(json.dumps(report,indent=2)+'\n');return result,report

if __name__=='__main__':build_matrix()
