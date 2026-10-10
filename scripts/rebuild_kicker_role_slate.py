"""Append one corrected local projection/portfolio; preserve and reuse saved results."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import argparse

from backend.app.product_services.predictions import PredictionsService
from backend.app.product_services.optimizer import OptimizerService
from scripts.run_showdown_qb_policy_experiment import read, write, solver, parameters


class CaptureService(OptimizerService):
    def _solve_lineup(self, pool, **kwargs):
        if kwargs.get('score_col') == 'optimizer_context_ceiling_score' and not hasattr(self, 'prepared'):
            self.prepared = pool.copy()
        return super()._solve_lineup(pool, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('artifacts/kicker_role_audit'))
    directory = parser.parse_args().directory
    if (directory / 'final_job.json').exists():
        job = read(directory / 'final_job.json')
        print('Reusing saved optimizer', job['job_id'], job['status'])
        return
    reference = read(directory / 'historical_audit.json')['reference_run'][0]
    params = parameters(directory / 'controlled', 'A')
    projection_path = directory / 'rebuilt_projections.json'
    if not projection_path.exists():
        cutoff = datetime.now(timezone.utc)
        result = PredictionsService().train_and_predict(reference['season'], reference['week'],
            slate=reference['slate_id'], data_cutoff_at=cutoff,
            availability_overrides=params.get('availability_overrides'),
            assume_questionable_out=params.get('exclusions_assumed_out', False))
        write(projection_path, dict(projection_run_id=str(result.projection_run_id),
            reference_projection_run_id=reference['projection_run_id'], cutoff=cutoff.isoformat(),
            records=[row.__dict__ for row in result.records]))
    projection = read(projection_path)
    service = CaptureService()
    with (directory / 'production_final.log').open('w') as log, redirect_stdout(log), \
         patch('backend.app.product_services.optimizer.pulp.PULP_CBC_CMD', side_effect=solver):
        job = service.run_job(reference['season'], reference['week'], reference['slate_id'],
            reference['strategy'], params, contest_format=reference['contest_format'],
            objective=reference['objective'], projection_run_id=projection['projection_run_id'])
    write(directory / 'final_job.json', job.__dict__)
    if hasattr(service, 'prepared'):
        write(directory / 'final_prepared_pool.json', service.prepared.to_dict('records'))
    print('Rebuilt optimizer', job.job_id, job.status, job.message, flush=True)


if __name__ == '__main__':
    main()
