"""Register a reviewed prelock shadow artifact for automatic app outcome tracking."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.classic_strategy_contract import validate_strategy_contract
from backend.app.product_services.gpp_shadow_learning import ShadowLearningService


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--label', required=True)
    args=parser.parse_args()
    raw=args.experiment.read_bytes(); experiment=json.loads(raw)
    with engine.connect() as c:
        c.execute(text('SET TRANSACTION READ ONLY'))
        scope=dict(c.execute(text('SELECT season,week,slate_id AS slate,contest_format FROM target.optimizer_run WHERE optimizer_run_id=:id'),{'id':experiment['source_run_id']}).mappings().one())
    arms={};locks=[]
    for name,arm in experiment['arms'].items():
        contract=json.loads((args.experiment.parent/(name+'_contract.json')).read_text())
        validate_strategy_contract(contract)
        assert arm['portfolio']['validation']['status']=='verified'
        assert arm['portfolio']['contract_sha256']==contract['sha256']
        timing=arm.get('timing',arm.get('prelock_timing'))
        assert timing['status']=='predecision'
        locks.append(datetime.fromisoformat(timing['first_saved_kickoff_at']))
        recommendation=arm['recommendation']['recommended']
        roster=arm['rosters'][recommendation['lineup_number']-1]
        known={p['player_id'] for p in contract['effective']['players']}
        assert all(p['player_id'] in known for p in roster)
        arms[name]=dict(roster=roster,forecast_points=recommendation['projected_points'],
                       completed_at=arm['completed_at'],candidate_id=recommendation['candidate_id'],
                       contract_sha256=contract['sha256'])
    snapshot=dict(**scope,label=args.label,source_run_id=experiment['source_run_id'],
                  source_artifact_sha256=hashlib.sha256(raw).hexdigest(),arms=arms,
                  first_kickoff_at=min(locks).isoformat())
    print(ShadowLearningService(engine).register(snapshot))


if __name__=='__main__':main()
