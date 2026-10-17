"""Exercise normal Analyst generation/selection on a real exported pool, without writes."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path

from backend.app.product_services.analyst_packets import import_packet
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from scripts.research_showdown_prelock import FrozenService


class OfflineNormal(FrozenService):
    def _persist_optimizer_run(self, job):
        self.checkpoints = getattr(self, 'checkpoints', []) + [dict(message=job.message,status=job.status)]
        return True  # In-memory checkpoint only; SQLite engine has no application tables.

    def _solve_lineup(self, pool, **kwargs):
        return OptimizerService._solve_lineup(self, pool, **kwargs)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--strategy',default='showdown_single_entry_portfolio')
    parser.add_argument('--count',type=int,default=3)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    packet=json.loads(args.packet.read_text()); receipt=import_packet(packet)
    frozen=json.loads(args.source.read_text())
    services=[]; results={}
    for arm in ('without_analyst','with_analyst'):
        service=OfflineNormal(frozen); services.append(service)
        params={'num_single_entry_contests':args.count, 'num_lineups':args.count}
        if arm=='with_analyst': params.update(analyst_packet_sha256=receipt['analyst_packet_sha256'],analyst_candidates_per_thesis=2)
        with (args.output/(arm+'.log')).open('w') as log,redirect_stdout(log):
            job=service.run_job(frozen['season'],frozen['week'],frozen['slate'], args.strategy,params,
                contest_format='showdown',objective='gpp',projection_run_id=frozen['projection_run_id'],allow_incomplete_evidence=True)
        result=_json_safe(dict(status=job.status,message=job.message,lineups=job.results,params=job.params,
                          checkpoints=service.checkpoints,decision_at=datetime.now(timezone.utc).isoformat(),
                          live_persistence=False,readiness='OFFLINE_PREVIEW_not_live_READY'))
        results[arm]=result
        (args.output/(arm+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    comparison=dict(packet_receipt=receipt,baseline_candidate_count=(results['without_analyst']['params']['strategy_runtime'].get('single_entry') or results['without_analyst']['params']['strategy_runtime'].get('showdown_portfolio_policy', {}).get('candidate_selection') or {}).get('candidate_count'),
                    analyst_candidate_count=(results['with_analyst']['params']['strategy_runtime'].get('single_entry') or results['with_analyst']['params']['strategy_runtime'].get('showdown_portfolio_policy', {}).get('candidate_selection') or {}).get('candidate_count'),
                    production_defaults='opt-in Analyst input; no-packet path unchanged',live_persistence=False)
    (args.output/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    print(json.dumps(comparison,indent=2))


if __name__=='__main__':main()
