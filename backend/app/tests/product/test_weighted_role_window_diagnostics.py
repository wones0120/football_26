from copy import deepcopy
import pytest
from backend.app.product_services.weighted_role_window_diagnostics import build_weighted_role_window_diagnostics,INPUT_VERSION


def source(counts=(2,4),active=(True,True)):
    logs=[dict(week=i+1,native_game_id=f'2026_0{i+1}_SF_WAS',counts=dict(pass_attempts=0,rush_attempts=n,targets=n),positive_offensive_participation_proven=a) for i,(n,a) in enumerate(zip(counts,active))]
    return dict(version=INPUT_VERSION,before_period=202607,pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',rows=[dict(season=2026,team='SF',source_player_id='native',player_master_id='uuid',source_position='RB',logs=logs)],positive_participants_missing_weekly_rows=[],identity_review_requests=[],participation_identity_review_requests=[])


def run(p=None):return build_weighted_role_window_diagnostics(p or source(),before_period=202607)['rows'][0]


def test_fixed_recency_and_kish_support():
    row=run();w=2**(-1/4)
    assert row['game_effective_sample_size']==pytest.approx((1+w)**2/(1+w*w))
    assert row['metrics']['targets']['weighted_exposure']==pytest.approx(4+2*w)
    assert row['metrics']['pass_attempts']['applicable'] is False


def test_known_zero_count_is_exposure_zero_not_absent_game():
    row=run(source((0,0)));assert row['game_effective_sample_size']>1
    assert row['metrics']['targets']['weighted_exposure']==0
    assert row['metrics']['targets']['exposure_concentration_effective_games'] is None


def test_unknown_count_masks_full_metric_keeps_known_sample():
    row=run(source((None,4)));m=row['metrics']['targets']
    assert m['weighted_exposure'] is None and m['known_sample']['sum_weights_or_weighted_exposure']==4


def test_unproven_zero_snap_not_dnp_zero_or_completecase():
    row=run(source((2,4),(False,True)))
    assert row['game_effective_sample_size'] is None and row['metrics']['targets']['weighted_exposure'] is None
    assert row['known_sample_game_support']['kish_effective_games']==1


def test_missing_positive_weekly_row_masks_matching_scope_only():
    p=source();p['positive_participants_missing_weekly_rows']=[dict(season=2026,week=3,team='SF',player_master_id='uuid')]
    assert run(p)['game_effective_sample_size'] is None
    p['positive_participants_missing_weekly_rows'][0]['team']='WAS'
    assert run(p)['game_effective_sample_size'] is not None


def test_parent_logs_not_mutated():
    p=source();old=deepcopy(p);run(p);assert p==old


@pytest.mark.parametrize('kind',['future','duplicate','negative','bool','nonfinite','contract'])
def test_invalid_source_rejected(kind):
    p=source();logs=p['rows'][0]['logs']
    if kind=='future':logs[0]['week']=7
    if kind=='duplicate':logs[1]['week']=1
    if kind=='negative':logs[0]['counts']['targets']=-1
    if kind=='bool':logs[0]['counts']['targets']=False
    if kind=='nonfinite':logs[0]['counts']['targets']=float('inf')
    if kind=='contract':p['pregame_serving_eligible']=True
    with pytest.raises(ValueError):run(p)


def test_missing_count_does_not_destroy_proven_game_membership_ess():
    row=run(source((None,4)))
    assert row['game_effective_sample_size']>1 and row['metrics']['targets']['weighted_exposure'] is None


def test_missing_earlier_positive_row_when_window_not_full_masks_ranking():
    p=source();p['rows'][0]['logs']=p['rows'][0]['logs'][1:]
    p['positive_participants_missing_weekly_rows']=[dict(season=2026,week=1,team='SF',player_master_id='uuid')]
    assert run(p)['game_effective_sample_size'] is None


def test_last8_known_positive_games_and_older_unknown_membership():
    p=source();p['before_period']=202618
    p['rows'][0]['logs']=[dict(week=i,native_game_id=f'2026_{i:02}_SF_WAS',counts=dict(pass_attempts=0,rush_attempts=2,targets=2),positive_offensive_participation_proven=i!=1) for i in range(1,11)]
    row=build_weighted_role_window_diagnostics(p,before_period=202618)['rows'][0]
    assert len(row['selected_logs'])==8 and row['selected_logs'][0]['week']==3
    assert row['game_effective_sample_size'] is not None


def test_reader_authenticates_producer_bytes_publication_and_use(tmp_path,monkeypatch):
    import json,hashlib
    from pathlib import Path
    from backend.app.product_services import active_workload_distributions as module
    from backend.app.product_services.weighted_role_window_diagnostics import load_weighted_role_window_diagnostics,require_feature_use
    monkeypatch.chdir(tmp_path);p=source();p['provenance']=dict(actual_publication_at='2000-01-02T00:00:00+00:00',producer_code_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
    raw=json.dumps(p).encode();sha=hashlib.sha256(raw).hexdigest();folder=tmp_path/'artifacts/active_workload_distributions';folder.mkdir(parents=True);path=folder/(sha+'.json');path.write_bytes(raw);ref=dict(path=str(path),sha256=sha,bytes=len(raw))
    result=load_weighted_role_window_diagnostics(ref,actual_read_at='2000-01-03T00:00:00+00:00');assert result['rows'][0]['game_effective_sample_size']>1
    with pytest.raises(ValueError):require_feature_use(result,purpose='forecast')
    with pytest.raises(ValueError):load_weighted_role_window_diagnostics(ref,actual_read_at='2000-01-01T00:00:00+00:00')
    path.write_text('changed')
    with pytest.raises(ValueError):load_weighted_role_window_diagnostics(ref,actual_read_at='2000-01-03T00:00:00+00:00')
