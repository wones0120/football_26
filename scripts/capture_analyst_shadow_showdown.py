"""Read-only source capture; prepare an offline production Showdown ILP, never persist."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import text

from backend.app.product_services.analyst_shadow import freeze_model, digest
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from scripts.research_showdown_prelock import FrozenService, PreparationComplete, capture_model


class OfflinePreparation(FrozenService):
    def _persist_optimizer_run(self, job):
        if job.message != 'NON-PRODUCTION incomplete-evidence override' or job.status != 'running':
            raise AssertionError('Only the offline evidence-freeze checkpoint may be acknowledged')
        self.readiness = job.params['data_readiness']
        # Acknowledge an in-memory checkpoint, never write a run or mark READY.
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--projection-run-id', required=True)
    parser.add_argument('--source', type=Path, help='Replay an existing read-only source export without database access')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--game-id', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    packet = json.loads(args.packet.read_text())
    if args.source:
        frozen = json.loads(args.source.read_text())
        if frozen['projection_run_id'] != args.projection_run_id:
            raise ValueError('projection_source_mismatch')
        header = frozen['projection_header'][0]
        import pandas as pd
        frame = pd.DataFrame(frozen['player_pool'])
        captured_at = datetime.now(timezone.utc).isoformat()
    else:
        service = OptimizerService()
        # PostgreSQL enforces read-only on every transaction, including helper queries.
        service.engine = service.engine.execution_options(postgresql_readonly=True)
        with service.engine.connect() as connection:
            header = dict(connection.execute(text('SELECT * FROM target.projection_run WHERE projection_run_id=:id'), {'id':args.projection_run_id}).mappings().one())
        frame = service._load_player_pool(header['season'], header['week'], header['slate_id'], projection_run_id=args.projection_run_id)
        captured_at = datetime.now(timezone.utc).isoformat()
        frozen = _json_safe(dict(season=header['season'], week=header['week'], slate=header['slate_id'],
                       projection_run_id=args.projection_run_id, projection_header=[header], player_pool=frame.to_dict('records'), pool_attrs=dict(frame.attrs)))
    (args.output/'source.json').write_text(json.dumps(frozen, indent=2, allow_nan=False)+'\n')
    offline = OfflinePreparation(frozen)
    with (args.output/'preparation.log').open('w') as log, redirect_stdout(log):
        try:
            offline.run_job(header['season'], header['week'], header['slate_id'],
                            'showdown_single_entry_portfolio', {'num_single_entry_contests':3},
                            contest_format='showdown', objective='gpp', projection_run_id=args.projection_run_id, allow_incomplete_evidence=True)
        except PreparationComplete: pass
        if not hasattr(offline, 'prepared'):
            raise ValueError('production_preparation_did_not_reach_solver')
        pool = offline.prepared
        kwargs = offline.solve_kwargs
        model = capture_model(offline, pool, kwargs)
    prepared = _json_safe(pool.to_dict('records'))
    (args.output/'prepared.json').write_text(json.dumps(dict(rows=prepared, attrs=_json_safe(dict(pool.attrs))), indent=2, allow_nan=False)+'\n')
    decision = datetime.now(timezone.utc).isoformat()
    mapping = {}; players = []
    for i,row in enumerate(prepared):
        pid = str(row['player_id'])
        gid = args.game_id
        players.append({**row, 'player_master_id':pid, 'game_id':gid, 'team':row['player_team']})
        for prefix,role in [('captain','CPT'),('flex','FLEX')]: mapping[prefix+'_'+str(i)] = dict(player_master_id=pid,role=role)
    policy = dict(complete_prepared_model=True, strategy='showdown_single_entry_portfolio',
                  readiness_status='OFFLINE_RESEARCH_PREVIEW_not_live_READY',
                  original_readiness=offline.readiness,
                  preparation_gate='explicit allow_incomplete_evidence internal preview; never final selection',
                  solve_parameters=_json_safe({k:v for k,v in kwargs.items() if k!='rule_profile'}),
                  shortlist_ids=[str(r['player_id']) for r in prepared if r.get('showdown_captain_shortlisted')],
                  user_constraints='existing strategy defaults; no additional user treatment',
                  exposure_policy='exact initial production remaining gates; discovery alternatives do not form a portfolio')
    snapshot = freeze_model(model, variable_players=mapping, players=players,
                scope=dict(format='SHOWDOWN', season=header['season'], week=header['week'], slate_id=header['slate_id'], game_ids=sorted({p['game_id'] for p in players})),
                available_at=captured_at, decision_at=decision, policy=policy,
                provenance=dict(source_sha256=digest(frozen), prepared_sha256=digest(prepared),
                                analyst_packet_sha256=digest(packet), analyst_packet_path=str(args.packet),
                                analyst_decision_at=packet['decision_at'],
                                projection_run_id=args.projection_run_id, projection_cutoff_at=str(header['data_cutoff_at']),
                                snapshot_capture_at=captured_at, offline_preparation_at=decision,
                                chronology='Current research decision uses previously stored base projections plus current read-only eligibility; not a contemporaneous replay at projection cutoff.'))
    (args.output/'snapshot.json').write_text(json.dumps(snapshot, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(raw_rows=len(frame), prepared_rows=len(pool), captain_ids=policy['shortlist_ids'], snapshot_sha256=snapshot['sha256'])))


if __name__ == '__main__': main()
