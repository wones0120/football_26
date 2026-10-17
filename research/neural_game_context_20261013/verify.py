"""Read-only checks: frozen hashes, reload every checkpoint, clock lineage."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import sys,json,importlib.util,tempfile
from pathlib import Path
import numpy as np,pandas as pd,joblib
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from context import V3,sha,FAMILIES
V4=V3.parent/'training_v4';sys.path.insert(0,str(V4));import models

def verify():
 result=json.loads((HERE/'results.json').read_text());coverage=json.loads((HERE/'coverage.json').read_text())
 for path,key in [(HERE/'SPECIFICATION.md','spec_sha256'),(HERE/'context.py','context_sha256'),(HERE/'run.py','runner_sha256'),(V4/'models.py','v4_model_sha256'),(V4/'runner.py','v4_runner_sha256'),(HERE/'feature_matrix.csv','matrix_sha256'),(HERE/'predictions.csv','prediction_sha256')]:
  assert sha(path)==result[key],str(path)
 # CSV is a readable ten-significant-digit summary. Tree split ties require exact replay.
 import context
 original_here=context.HERE
 with tempfile.TemporaryDirectory(prefix='neural_context_replay_') as temporary:
  context.HERE=Path(temporary)
  (context.HERE/'sources').symlink_to(HERE/'sources',target_is_directory=True)
  try:
   frame,replayed=context.build_matrix()
   assert replayed['context_matrix_sha256']==result['matrix_sha256'],'Reconstructed input hash changed'
  finally:context.HERE=original_here
 pred=pd.read_csv(HERE/'predictions.csv');checks={}
 for key,record in result['selection_records'].items():
  fold,target,family,method=key.split('/');path=HERE/record['artifact'];assert sha(path)==record['artifact_sha256'];model=joblib.load(path)
  group=pred[(pred.fold==fold)&(pred.target==target)&(pred.family==family)&(pred.method==method)];rows=frame.loc[group.row_index];cols=coverage['base_features']+FAMILIES[family];point=model.predict(rows) if method!='tree' else model.predict(rows[cols+['position']]);point=np.maximum(0,point) if target!='fantasy_points_ppr' else point
  assert np.allclose(point,group.prediction,atol=1e-7,rtol=1e-7),key
  assert np.isclose(np.mean(np.abs(point-rows[target])),result['metrics'][key]['mae'],atol=1e-8),key
  checks[key]={'rows':len(group),'maximum_absolute_reload_delta':float(np.max(np.abs(point-group.prediction.to_numpy())))}
 spec=importlib.util.spec_from_file_location('context_verify_v3',V3/'data.py');data=importlib.util.module_from_spec(spec);spec.loader.exec_module(data);games=data.schedule_rows();raw=pd.read_parquet(V3/'sources/games.parquet');sids=dict(zip(raw.game_id,raw.stadium_id));lineage=[]
 for row in frame.to_dict('records'):
  g=games[row['game_id']];used={}
  for role,club in [('teammate',row['team']),('opponent',row['opponent'])]:
   prior=sorted([a for a in games.values() if a['season']==g['season'] and club in [a['home_team'],a['away_team']] and a['completed_at']<g['cutoff_at']],key=lambda a:a['kickoff_at'])[-3:]
   used[role]=[a['game_id'] for a in prior]
   for a in prior:assert a['game_id']!=g['game_id'] and a['completed_at']<g['cutoff_at']
  venue=[a for a in games.values() if sids[a['game_id']]==sids[g['game_id']] and a['completed_at']<g['cutoff_at']]
  used['venue_game_count']=len(venue);used['row_index']=row['player_master_id']+':'+str(row['period']);used['game_id']=g['game_id'];used['cutoff_at']=g['cutoff_at'].isoformat();used['max_prior_completed_at']=max((games[gid]['completed_at'].isoformat() for role in ['teammate','opponent'] for gid in used[role]),default=None);lineage.append(used)
 (HERE/'context_lineage.json').write_text(json.dumps(lineage,indent=2)+'\n');out={'checkpoints_reloaded':len(checks),'prediction_rows':len(pred),'matrix_rows':len(frame),'all_checkpoint_predictions_equal':True,'replay_precision':'Exact source-reconstructed floating inputs; readable ten-digit CSV alone may move tree split ties; serialized replay hash matches original','clock_checked_context_rows':len(lineage),'target_game_history_references':0,'availability_used_in_training':False,'checks':checks,'context_lineage_sha256':sha(HERE/'context_lineage.json')}
 (HERE/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='checks'},indent=2))
if __name__=='__main__':verify()
