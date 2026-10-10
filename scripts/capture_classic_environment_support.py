"""Read-only supplement to immutable historical study; never overwrite original inputs."""
import json
from pathlib import Path
from sqlalchemy import create_engine,text
from Database.config import get_connection_string
from scripts.analyze_classic_historical_study import salary_lock

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/classic_historical_study'
OUT=ROOT/'artifacts/classic_game_environment_review/historical_support.json'

def main():
    support=json.loads((BASE/'support_snapshot.json').read_text())
    inventory=json.loads((BASE/'inventory_snapshot.json').read_text())
    ids=[r['contest_id'] for r in inventory['contests'] if r['season']==2026]
    if OUT.exists():
        print('Reusing saved historical support:',OUT)
        return
    result={'read_only':True,'projections':{},'ownership':{},'payouts':[]}
    with create_engine(get_connection_string()).connect() as conn:
        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        result['payouts']=[dict(r) for r in conn.execute(text('SELECT * FROM target.dfs_contest_payout_tier WHERE contest_id = ANY(:ids)'),{'ids':ids}).mappings()]
        for week,projection in support['projections'].items():
            run=projection['run']
            result['projections'][week]=[dict(r) for r in conn.execute(text('''SELECT player_id,mean,p90,created_at,data_cutoff_at FROM target.player_projection
                WHERE projection_run_id=:run'''),{'run':run['projection_run_id']}).mappings()]
            result['ownership'][week]=[dict(r) for r in conn.execute(text('''SELECT p.player_id,p.roster_position,p.projected_ownership,p.created_at,p.data_cutoff_at,
                r.ownership_run_id,r.created_at AS run_created_at,r.data_cutoff_at AS run_cutoff,r.status,r.metrics_json
                FROM target.ownership_projection p JOIN target.ownership_model_run r USING(ownership_run_id)
                WHERE r.season=2026 AND r.week=:week AND UPPER(r.slate_id)='SUNDAY_MAIN'
                  AND r.status='completed' AND r.created_at < :lock AND p.created_at < :lock
                  AND r.data_cutoff_at < :lock AND p.data_cutoff_at < :lock
                ORDER BY r.created_at DESC'''),{'week':int(week),'lock':salary_lock([s for s in inventory['salaries'] if s['season']==run['season'] and s['week']==int(week) and s['slate'].upper()==run['slate_id'].upper()])}).mappings()]
    OUT.write_text(json.dumps(result,default=str,indent=2)+'\n')
    print('Exported supplement:', {k:len(v) for k,v in result['projections'].items()},'ownership',{k:len(v) for k,v in result['ownership'].items()},'payout rows',len(result['payouts']))

if __name__=='__main__':main()
