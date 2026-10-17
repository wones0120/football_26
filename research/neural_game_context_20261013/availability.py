"""Scoring-only entry point for genuinely predecision availability receipts.

Historical experiment does not invoke this contract. A snapshot receipt is externally
verified evidence; caller must retain the original hashed payload. No forecast of
DNP or clearing of injury designations occurs here.
"""
from __future__ import annotations
from context import validate_availability,aggregate_availability,utc

def availability_inputs(snapshot,history,*,game_id,cutoff,team,player_master_id):
 members=validate_availability(snapshot,game_id=game_id,cutoff=cutoff)
 cutoff=utc(cutoff)
 if utc(snapshot['observed_at'])<utc(snapshot['published_at']):raise ValueError('Receipt predates publication')
 for report in snapshot.get('reports',[]):
  if utc(report['published_at'])>utc(snapshot['observed_at']):raise ValueError('Report published after the snapshot receipt')
 try:int(snapshot['source_sha256'],16)
 except ValueError as error:raise ValueError('Source hash must be hex') from error
 if not any(r['player_master_id']==player_master_id and r['team']==team for r in members):raise ValueError('Scored player missing from effective roster')
 cleaned={}
 for pid,item in history.items():
  if not item.get('game_id') or item.get('game_id')==game_id or not item.get('completed_at') or utc(item['completed_at'])>=cutoff:raise ValueError('Workload history must precede decision cutoff and target game')
  if item.get('prior_status') and (not item.get('prior_status_observed_at') or utc(item['prior_status_observed_at'])>=cutoff):raise ValueError('Prior status requires predecision receipt')
  cleaned[pid]=item
 opponent_teams={r['team'] for r in members if r['team']!=team}
 if len(opponent_teams)!=1:raise ValueError('Game roster must distinguish exactly one opponent')
 opponent=next(iter(opponent_teams))
 coverage=snapshot.get('roster_coverage',{})
 for club in [team,opponent]:
  if coverage.get(club,{}).get('universe_complete') is not True:raise ValueError('Complete point-in-time roster coverage required for each team')
 return {'teammate':aggregate_availability(members,team,cleaned,exclude_player=player_master_id),'opponent':aggregate_availability(members,opponent,cleaned),'actual_availability_evidence_source_id':snapshot['source_id'],'actual_availability_evidence_sha256':snapshot['source_sha256'],'actual_availability_observed_at':snapshot['observed_at'],'actual_availability_unknown_members':sum(r['status']=='unknown' for r in members),'interpretation':'Official statuses and known missing/returning workload only; no realized participation or DNP probability'}

GROUPS={'qb':{'QB'},'receiving':{'WR','TE'},'rushing':{'RB'},'ol':{'T','OT','G','OG','C','OL'},'defense':{'DE','DT','NT','DL','LB','ILB','OLB','CB','S','SS','FS','DB'}}

def availability_feature_row(snapshot,history,*,game_id,cutoff,team,player_master_id):
 """Flat numeric neural-input contract. No historical fitted head uses it yet."""
 import numpy as np
 result=availability_inputs(snapshot,history,game_id=game_id,cutoff=cutoff,team=team,player_master_id=player_master_id)
 members=validate_availability(snapshot,game_id=game_id,cutoff=cutoff)
 opponent=next(r['team'] for r in members if r['team']!=team)
 row={}
 for role,club in [('teammate',team),('opponent',opponent)]:
  row.update({'availability_'+role+'_'+k:v for k,v in result[role].items()})
  for group,positions in GROUPS.items():
   metric='targets' if group=='receiving' else 'carries' if group=='rushing' else 'snaps'
   selected=[r for r in members if r['team']==club and r['position'] in positions and (role=='opponent' or r['player_master_id']!=player_master_id)]
   vals=[history.get(r['player_master_id'],{}).get(metric,np.nan) for r in selected if r['status']=='available' and history.get(r['player_master_id'],{}).get('prior_status')=='out']
   row['availability_'+role+'_'+group+'_returning_prior_'+metric]=float(np.nansum(vals)) if vals and np.isfinite(vals).any() else np.nan
   row['availability_'+role+'_'+group+'_prior_workload_known_count']=sum(np.isfinite(history.get(r['player_master_id'],{}).get(metric,np.nan)) for r in selected)
 return row
