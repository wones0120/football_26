"""Opt-in, frozen learned-yard receipts; never reuse Showdown selection policy."""
from datetime import UTC
from uuid import UUID

from ..models import OperationalJob
from .evaluation_record import digest


def bind_preparation(request, session):
    from .single_stat import clock
    if request.variant != 'total_yards' or len(request.games) != 1:
        raise ValueError('Learned yards currently require one Total Yards game')
    job = session.get(OperationalJob, str(UUID(request.prepared_input_job_id)))
    if job is None or job.status != 'completed' or job.completed_at is None:
        raise ValueError('Learned yards require a completed preparation job')
    result = job.result_json or {}
    cutoff = clock(request.source_observed_at)
    completed = job.completed_at.replace(tzinfo=UTC) if job.completed_at.tzinfo is None else job.completed_at
    if completed > cutoff or result.get('action') != 'prepare' or (result.get('season'), result.get('week')) != (request.season, request.week):
        raise ValueError('Preparation scope or completion clock does not match the pool')
    forecast = result.get('workload_forecast') or {}
    if not forecast.get('learned_opportunities') or digest({k: v for k, v in forecast.items() if k != 'sha256'}) != forecast.get('sha256'):
        raise ValueError('Learned forecast receipt missing or hash mismatch')
    game = request.games[0]
    matches = [g for g in result.get('source_manifest', {}).get('games', [])
               if {g.get('away_team'), g.get('home_team')} == set(game.teams)
               and clock(g['kickoff_at']) == clock(game.scheduled_start_at)]
    if len(matches) != 1:
        raise ValueError('Preparation must match the native teams and kickoff exactly')
    model = forecast.get('yardage_model') or {}
    period = request.season * 100 + request.week
    count_max = forecast.get('model', {}).get('training_max_period')
    if forecast.get('before_period') != period or not isinstance(count_max, int) or count_max >= period:
        raise ValueError('Learned counts require matching target period and prior-only training evidence')
    if model.get('version') != 'role_efficiency_yards_v1' or not isinstance(model.get('training_max_period'), int) or model['training_max_period'] >= period:
        raise ValueError('Learned yard efficiency requires prior-only training evidence')
    source_clock = clock(forecast['source_cutoff_at'])
    if source_clock > cutoff or source_clock >= clock(game.scheduled_start_at) or clock(result['data_cutoff_at']) != source_clock:
        raise ValueError('Learned forecast source clock does not match the pregame cutoff')
    actors = {}
    for actor in forecast['players']:
        pid = str(UUID(actor['player_master_id']))
        if pid in actors:
            raise ValueError('Duplicate canonical player in learned forecast')
        actors[pid] = actor
    binding = dict(method='prepared_learned_total_yards_v1', prepared_input_job_id=job.job_id,
        completed_at=completed.isoformat(), preparation_run_id=job.run_id,
        preparation_result_sha256=digest(result), projection_run_id=result.get('projection_run_id'),
        forecast_sha256=forecast['sha256'], source_cutoff_at=forecast['source_cutoff_at'],
        game=matches[0], yardage_model={k: model.get(k) for k in ('version','method','code_sha256','history_sha256','training_max_period','limitations')},
        selection_weights=dict(rushing_yards=1, receiving_yards=1, passing_yards=0),
        limitations=forecast.get('limitations', []))
    return binding, actors


def actor_forecast(actor, row):
    from .single_stat import score
    if actor is not None and (actor['team'] != row['team'] or actor['position'] != row['position']):
        raise ValueError('Learned canonical actor team/position differs from native pool')
    actor = actor or {}
    components = {k: actor.get('projected_yards', {}).get(k) for k in ('rushing_yards','receiving_yards')}
    scored = score('total_yards', components)
    return dict(method='prepared_learned_total_yards_v1', components=components, **scored,
        covered_value=sum(v for v in components.values() if v is not None) if any(v is not None for v in components.values()) else None,
        sample_games=None, evidence=actor.get('source_ids', []),
        counts=actor.get('counts', {}), efficiency=actor.get('efficiency', {}),
        receiving_team_reconciliation_factor=actor.get('receiving_team_reconciliation_factor'),
        conditional_on=actor.get('conditional_on'), reasons=actor.get('reasons', []),
        warning='Learned attempts/targets × role-aware efficiency, with shared receiving-yard reconciliation. Conditional on active participation and supported role; uncertainty and expected-yard calibration remain unproven. Missing forecasts stay unknown.')
