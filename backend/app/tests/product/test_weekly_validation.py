from datetime import datetime, timedelta, timezone
from scripts.audit_weekly_validation import metrics, pregame, primary_run
from backend.app.product_services.optimizer_effectiveness import actual_points_by_player, score_signature


def test_missing_actuals_are_not_zero_and_bias_has_documented_direction():
    result=metrics([dict(mean=10,actual=8,p10=5,p90=15),dict(mean=20,actual=None)])
    assert result['matched']==1 and result['missing']==1
    assert result['mae']==2 and result['bias']==2 and result['interval_coverage']==1


def test_any_late_projection_row_or_model_disqualifies_whole_slate_snapshot():
    lock=datetime(2026,9,13,17,tzinfo=timezone.utc)
    row=dict(kickoff=lock,**{k:lock-timedelta(hours=1) for k in
        ('created_at','run_created_at','model_created_at','data_cutoff_at','run_cutoff_at')})
    assert pregame([row])
    for key in ('created_at','run_created_at','model_created_at','data_cutoff_at','run_cutoff_at'):
        assert not pregame([row,dict(row,**{key:lock})])
    assert not pregame([dict(row,kickoff=None)])


def test_primary_does_not_replace_unscoreable_latest_choice_with_hindsight_winner():
    old=dict(eligibility='exploratory',optimizer_created_at='2026-09-13T10:00:00Z',run_id='old',selected_actual_points=200)
    new=dict(old,optimizer_created_at='2026-09-13T11:00:00Z',run_id='new',selected_actual_points=None)
    assert primary_run([new,old]) is new


def test_captain_normalization_and_conflict_rejection():
    obs=[dict(player_id='p',roster_position='CPT',actual_points=30,resolution_status='resolved'),
         dict(player_id='p',roster_position='FLEX',actual_points=20,resolution_status='resolved')]
    points=actual_points_by_player(obs,'showdown')
    assert points=={'p':20}
    assert score_signature((('p',True),),points)==(30,[])
    obs.append(dict(obs[1],actual_points=21))
    assert actual_points_by_player(obs,'showdown')=={}


def test_captain_audit_preserves_required_native_slot_identity():
    from scripts.audit_weekly_validation import AUDIT_PLAYER_KEYS
    from backend.app.product_services.gpp_historical_audit import freeze_choice
    clock=datetime(2026,9,8,tzinfo=timezone.utc)
    run=dict(optimizer_run_id='r',season=2026,week=1,slate_id='WEDNESDAY_NIGHT',
             contest_format='showdown',projection_run_id='p',data_cutoff_at=clock)
    roster=[dict(player_id=f'p{i}',dk_player_id=str(100+i),dk_captain_id=str(200+i),
                 roster_position='CPT' if i==0 else 'FLEX',position='WR',salary=5000,
                 projection=15 if i==0 else 10,p90=25,game_id='A@B 09/09/2026 08:20PM ET') for i in range(6)]
    captured=[{k:v for k,v in r.items() if k in AUDIT_PLAYER_KEYS} for r in roster]
    assert freeze_choice(run,[captured])['recommended']['projected_points']==65


def test_game_alias_requires_unique_week_and_team_pair_and_never_hides_conflict():
    from scripts.audit_weekly_validation import resolve_kickoff
    lock=datetime(2026,9,21,20,tzinfo=timezone.utc)
    kicks={'2026_02_NYG_LA':{lock}}
    assert resolve_kickoff('2026_02_LAR_NYG',kicks)==(lock,'2026_02_NYG_LA','unique_season_week_team_pair_alias')
    assert resolve_kickoff('2026_03_LAR_NYG',kicks)[0] is None
    kicks['2026_02_LAR_NYG']={lock,lock+timedelta(hours=1)}
    assert resolve_kickoff('2026_02_LAR_NYG',kicks)[0] is None
